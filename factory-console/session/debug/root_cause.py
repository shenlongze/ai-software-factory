"""factory-console/session/debug/root_cause.py — RootCauseAnalyzer (S10-068 G2)。

根因分析: DebugCase (error_type + message) → RootCause 假设 + evidence + confidence。

设计: docs/sprint10/S10-068-debug-intelligence-design.md §4
边界:
- 纯标准库, 零模块依赖; 规则兜底为主 (LLM 可选, 失败 → 规则兜底)
- analyze 不抛 (任何输入 → RootCause; error_type 空 → 自动 classify)
"""

from __future__ import annotations

from typing import Any, Optional

from . import (
    ERROR_API_CONTRACT,
    ERROR_ASSERTION,
    ERROR_AUTH,
    ERROR_IMPORT,
    ERROR_MISSING,
    ERROR_NULL,
    ERROR_TEST_FAILURE,
    ERROR_TIMEOUT,
    ERROR_UNKNOWN,
    DebugCase,
    RootCause,
)
from .error_analysis import ErrorAnalyzer

#: 每错误类型的基础根因假设 + 基础置信度 (规则口径)
_CAUSE_RULES: dict[str, tuple[str, float]] = {
    ERROR_TIMEOUT: ("执行超时 — 外部依赖/网络慢或挂起, 或资源耗尽", 0.7),
    ERROR_IMPORT: ("模块导入失败 — 依赖缺失/路径错误/循环导入", 0.75),
    ERROR_ASSERTION: ("断言失败 — 实际结果与预期不符 (业务逻辑/边界条件)", 0.7),
    ERROR_AUTH: ("认证/密钥缺失或无效 — API key/凭证未配置或已失效", 0.8),
    ERROR_API_CONTRACT: ("API 契约不匹配 — 字段/类型/schema 与调用方不一致", 0.75),
    ERROR_NULL: ("空值处理缺失 — None/null 未判空 (空指针/可选字段)", 0.7),
    ERROR_MISSING: ("资源/字段/文件缺失 — 引用的目标不存在", 0.7),
    ERROR_TEST_FAILURE: ("测试验证失败 — 用例失败/断言不通过 (实现或测试问题)", 0.7),
    ERROR_UNKNOWN: ("错误未分类 — 需要人工/LLM 进一步分析", 0.35),
}

#: 消息关键词 → 根因细化 (命中则覆盖 cause; (关键词, 细化描述))
_CAUSE_REFINEMENTS: dict[str, tuple[tuple[str, str], ...]] = {
    ERROR_API_CONTRACT: (
        ("missing field", "API 契约缺失字段 — 响应/请求缺少必需字段"),
        ("extra field", "API 契约多余字段 — 响应/请求携带未声明字段"),
        ("invalid type", "API 契约类型不匹配 — 字段类型与 schema 不一致"),
        ("schema", "API 契约 schema 校验失败"),
    ),
    ERROR_AUTH: (
        ("api key", "API key 缺失或无效 — 需要配置有效凭证"),
        ("credential", "凭证无效 — 需要更新/校验认证信息"),
        ("unauthorized", "未授权访问 — 权限/token 不足或过期"),
    ),
    ERROR_IMPORT: (
        ("no module", "模块未安装 — 缺少依赖包"),
        ("cannot import", "导入路径错误或循环导入"),
    ),
    ERROR_TIMEOUT: (
        ("connect", "连接超时 — 网络/服务不可达"),
        ("read", "读取超时 — 外部响应过慢"),
    ),
    ERROR_MISSING: (
        ("file", "文件缺失 — 引用的文件不存在"),
        ("field", "字段缺失 — 数据结构缺少必需字段"),
    ),
    ERROR_NULL: (
        ("none", "None 值未处理 — 可选字段/返回值未判空"),
    ),
}

#: 历史经验加成 (每条命中经验 → 置信度 + 0.05, 封顶 0.95)
_EXPERIENCE_BONUS = 0.05
_MAX_CONFIDENCE = 0.95


class RootCauseAnalyzer:
    """根因分析器 (G2): analyze(debug_case, related_experiences=None) -> RootCause。

    规则: error_type → 基础假设; 消息关键词 → 细化覆盖; 历史经验 → evidence
    补充 + 置信度加成。LLM 可选 (llm_provider) — 失败 → 规则兜底。
    """

    def __init__(self) -> None:
        self._classifier = ErrorAnalyzer()

    def analyze(
        self,
        debug_case: Any,
        related_experiences: Optional[list[Any]] = None,
        *,
        llm_provider: Any = None,
    ) -> RootCause:
        """DebugCase → RootCause (error_type 空 → 自动 classify; 不抛)。"""
        case = debug_case if isinstance(debug_case, DebugCase) else DebugCase.from_dict(debug_case)
        error_type = str(case.error_type or "").strip() or self._classifier.classify(
            case.error_message, case.stack_trace
        )
        if error_type not in _CAUSE_RULES:
            error_type = ERROR_UNKNOWN

        cause, confidence = _CAUSE_RULES[error_type]
        evidence: list[str] = [f"错误类型: {error_type}"]

        # 消息关键词细化 (命中 → cause 覆盖 + evidence)
        message = (case.error_message or "").lower()
        for keyword, refined in _CAUSE_REFINEMENTS.get(error_type, ()):
            if keyword in message:
                cause = refined
                evidence.append(f"关键词命中: {keyword}")
                break

        # 历史经验 → evidence + 置信度加成
        experiences = list(related_experiences or [])
        top = experiences[0] if experiences else None
        for record in experiences[:3]:
            action = getattr(record, "action", None) or ""
            problem = getattr(record, "problem", None) or ""
            if action or problem:
                evidence.append(f"历史经验: {action or problem}")
        if experiences:
            confidence = min(_MAX_CONFIDENCE, confidence + _EXPERIENCE_BONUS * len(experiences))

        # 可选 LLM: 结构化根因 (失败 → 规则兜底, 绝不裸抛)
        if llm_provider is not None:
            try:
                llm_cause = llm_provider(case, error_type)
                if isinstance(llm_cause, dict) and llm_cause.get("cause"):
                    cause = str(llm_cause["cause"])
                    try:
                        confidence = float(llm_cause.get("confidence") or confidence)
                    except (TypeError, ValueError):
                        pass
                    evidence.append("来源: LLM 根因分析")
            except Exception:  # noqa: BLE001 — LLM 失败 → 规则兜底
                pass

        related = top.to_dict() if top is not None and hasattr(top, "to_dict") else top
        return RootCause(
            cause=cause,
            evidence=evidence,
            confidence=max(0.0, min(1.0, confidence)),
            related_experience=related,
        )
