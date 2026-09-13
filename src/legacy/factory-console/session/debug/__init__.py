"""factory-console/session/debug — Debug Intelligence (S10-068 Part 1)。

DebugEngine 五模块 (DebugCase → DebugDecision):
- error_analysis.py   — ErrorAnalyzer: 错误理解 (error → error_type + DebugCase)
- root_cause.py       — RootCauseAnalyzer: 根因分析 (DebugCase → RootCause)
- debug_memory.py     — DebugExperienceRetriever: 历史经验检索 (Memory Top-K)
- debug_strategy.py   — DebugStrategySelector: 修复策略选择 (RootCause → DebugDecision)
- debug_engine.py     — DebugEngine: 完整流程 + feedback 循环 + 持久化

设计: docs/sprint10/S10-068-debug-intelligence-design.md
边界:
- 纯标准库 (dataclasses/enum/json/pathlib), 零模块依赖 (S10-067 Memory 只读复用)
- 规则兜底为主, LLM 可选 (llm_provider 失败 → 规则兜底, 绝不裸抛)
- 不替换 Repair Loop (quality.py 不动); 不引入 Vector DB (接口预留)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

# ------------------------------------------------------------ 错误类型 (ErrorAnalyzer.classify 口径)

#: 错误类型常量 (规则分类口径 — ErrorAnalyzer.classify 返回值)
ERROR_TIMEOUT = "TIMEOUT"
ERROR_IMPORT = "IMPORT_ERROR"
ERROR_ASSERTION = "ASSERTION"
ERROR_AUTH = "AUTH"
ERROR_API_CONTRACT = "API_CONTRACT"
ERROR_NULL = "NULL"
ERROR_MISSING = "MISSING"
ERROR_TEST_FAILURE = "TEST_FAILURE"
ERROR_UNKNOWN = "UNKNOWN"

#: 全部错误类型 (统计/校验口径)
ERROR_TYPES: tuple[str, ...] = (
    ERROR_TIMEOUT,
    ERROR_IMPORT,
    ERROR_ASSERTION,
    ERROR_AUTH,
    ERROR_API_CONTRACT,
    ERROR_NULL,
    ERROR_MISSING,
    ERROR_TEST_FAILURE,
    ERROR_UNKNOWN,
)


@dataclass
class DebugCase:
    """一次调试案件的完整描述 (G1 — 错误理解的结构化载体)。

    error_type:       ErrorAnalyzer.classify 结果 ("" = 未分类, analyze 时自动补)
    error_message:    错误信息 (必填 — 检索/根因/策略的主输入)
    stack_trace:      堆栈 (可选 — classify/evidence 补充面)
    task_id:          失败任务 id (历史/反馈关联)
    agent_id:         失败 Agent id (反馈沉淀关联)
    affected_files:   受影响文件 (修复范围提示)
    context:          上下文 (任务/intent/环境描述 — 检索关键词面)
    previous_attempts: 已重试次数 (>=2 → ROLLBACK 策略信号)
    project:          项目 slug (Memory 项目过滤/反馈沉淀)
    """

    error_message: str
    error_type: str = ""
    stack_trace: str = ""
    task_id: str = ""
    agent_id: str = ""
    affected_files: list[str] = field(default_factory=list)
    context: str = ""
    previous_attempts: int = 0
    project: str = ""

    def to_dict(self) -> dict[str, Any]:
        """序列化 (JSON 落盘/API 响应口径)。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "DebugCase":
        """反序列化 (失败安全: 非 dict → ValueError; 字段缺省兜底)。"""
        if not isinstance(data, dict):
            raise ValueError(
                f"DebugCase.from_dict 需要 dict, 收到 {type(data).__name__}"
            )
        files = data.get("affected_files") or []
        if not isinstance(files, (list, tuple)):
            files = []
        try:
            attempts = int(data.get("previous_attempts") or 0)
        except (TypeError, ValueError):
            attempts = 0
        return cls(
            error_message=str(data.get("error_message") or ""),
            error_type=str(data.get("error_type") or ""),
            stack_trace=str(data.get("stack_trace") or ""),
            task_id=str(data.get("task_id") or ""),
            agent_id=str(data.get("agent_id") or ""),
            affected_files=[str(f) for f in files],
            context=str(data.get("context") or ""),
            previous_attempts=attempts,
            project=str(data.get("project") or ""),
        )


@dataclass
class RootCause:
    """根因分析结果 (G2 + Part 2 G9): cause/evidence/confidence + related_experience
    + root_cause_type (9 类) + reasoning_summary。

    cause:              根因假设 (自然语言)
    evidence:           证据 (匹配关键词/错误类型/历史经验 — list[str])
    confidence:         置信度 0-1 (规则确定性 + 经验加成)
    related_experience: 关联历史经验 (ExperienceRecord.to_dict() | None)
    root_cause_type:    根因类型 (Part 2 G9 — CODE_DEFECT/TEST_DEFECT/.../UNKNOWN)
    reasoning_summary:  推理摘要 (为什么归为这个根因类型 — Audit-ready)
    """

    cause: str
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.5
    related_experience: Optional[Any] = None
    root_cause_type: str = "UNKNOWN"
    reasoning_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """序列化 (related_experience 有 to_dict → dict, 否则原样)。"""
        exp = self.related_experience
        if exp is not None and hasattr(exp, "to_dict"):
            exp = exp.to_dict()
        return {
            "cause": self.cause,
            "evidence": list(self.evidence),
            "confidence": self.confidence,
            "related_experience": exp,
            "root_cause_type": self.root_cause_type,
            "reasoning_summary": self.reasoning_summary,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "RootCause":
        """反序列化 (失败安全: 非 dict → ValueError; 字段缺省兜底)。"""
        if not isinstance(data, dict):
            raise ValueError(
                f"RootCause.from_dict 需要 dict, 收到 {type(data).__name__}"
            )
        evidence = data.get("evidence") or []
        if not isinstance(evidence, (list, tuple)):
            evidence = []
        try:
            confidence = float(data.get("confidence") or 0.5)
        except (TypeError, ValueError):
            confidence = 0.5
        return cls(
            cause=str(data.get("cause") or ""),
            evidence=[str(e) for e in evidence],
            confidence=max(0.0, min(1.0, confidence)),
            related_experience=data.get("related_experience"),
            root_cause_type=str(data.get("root_cause_type") or "UNKNOWN"),
            reasoning_summary=str(data.get("reasoning_summary") or ""),
        )


class FixStrategy(str, Enum):
    """修复策略枚举 (G3): DebugDecision.strategy 的合法面。

    FIX_CODE:        直接修改代码 (历史成功经验/常规缺陷)
    FIX_TEST:        修改/补充测试 (验证失败/断言失败)
    CHANGE_DESIGN:   修改设计/契约 (API 契约/架构问题)
    ROLLBACK:        回滚/重试 (重复失败 >= 2 次)
    REQUEST_REVIEW:  请求人工评审 (错误未分类/低置信无经验)
    """

    FIX_CODE = "FIX_CODE"
    FIX_TEST = "FIX_TEST"
    CHANGE_DESIGN = "CHANGE_DESIGN"
    ROLLBACK = "ROLLBACK"
    REQUEST_REVIEW = "REQUEST_REVIEW"


#: 全部策略值 (统计/校验口径)
FIX_STRATEGIES: tuple[str, ...] = tuple(s.value for s in FixStrategy)


def coerce_strategy(value: Any) -> FixStrategy:
    """策略值 → FixStrategy (非法 → ValueError — 校验铁律)。"""
    if isinstance(value, FixStrategy):
        return value
    text = str(value or "").strip().upper()
    for strategy in FixStrategy:
        if strategy.value == text:
            return strategy
    raise ValueError(f"未知修复策略: {value!r} (合法: {', '.join(FIX_STRATEGIES)})")


@dataclass
class DebugDecision:
    """调试决策 (G4): 修复策略 + 理由 + 置信度 + 证据 + 相关经验。

    strategy:            FixStrategy (枚举)
    reason:              决策理由 (自然语言 — 修复执行/人工评审参考)
    confidence:          决策置信度 0-1
    evidence:            证据链 (根因 + 历史经验摘要)
    related_experiences: 相关历史经验 (list[ExperienceRecord.to_dict()] 或记录)
    """

    strategy: FixStrategy = FixStrategy.REQUEST_REVIEW
    reason: str = ""
    confidence: float = 0.5
    evidence: list[str] = field(default_factory=list)
    related_experiences: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """序列化 (strategy → 字符串值; 经验 → to_dict)。"""
        exps = []
        for r in self.related_experiences:
            exps.append(r.to_dict() if hasattr(r, "to_dict") else r)
        return {
            "strategy": self.strategy.value
            if isinstance(self.strategy, FixStrategy)
            else str(self.strategy),
            "reason": self.reason,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "related_experiences": exps,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "DebugDecision":
        """反序列化 (失败安全: 非 dict → ValueError; strategy 非法 → 兜底
        REQUEST_REVIEW, 不抛 — 历史数据兼容)。"""
        if not isinstance(data, dict):
            raise ValueError(
                f"DebugDecision.from_dict 需要 dict, 收到 {type(data).__name__}"
            )
        try:
            strategy = coerce_strategy(data.get("strategy"))
        except ValueError:
            strategy = FixStrategy.REQUEST_REVIEW
        evidence = data.get("evidence") or []
        if not isinstance(evidence, (list, tuple)):
            evidence = []
        exps = data.get("related_experiences") or []
        if not isinstance(exps, (list, tuple)):
            exps = []
        try:
            confidence = float(data.get("confidence") or 0.5)
        except (TypeError, ValueError):
            confidence = 0.5
        return cls(
            strategy=strategy,
            reason=str(data.get("reason") or ""),
            confidence=max(0.0, min(1.0, confidence)),
            evidence=[str(e) for e in evidence],
            related_experiences=list(exps),
        )


__all__ = [
    "ContextBudget",
    "DebugAttempt",
    "DebugPipeline",
    "DebugRetrievalPolicy",
    "DebugSession",
    "DebugSessionStore",
    "DebugTrace",
    "ERROR_API_CONTRACT",
    "ERROR_ASSERTION",
    "ERROR_AUTH",
    "ERROR_IMPORT",
    "ERROR_MISSING",
    "ERROR_NULL",
    "ERROR_TEST_FAILURE",
    "ERROR_TIMEOUT",
    "ERROR_TYPES",
    "ERROR_UNKNOWN",
    "RepairSafety",
    "SESSION_ANALYZING",
    "SESSION_BLOCKED",
    "SESSION_REPAIRING",
    "SESSION_RETRYING",
    "SESSION_ROOT_CAUSE_IDENTIFIED",
    "SESSION_STATUSES",
    "SESSION_STRATEGY_SELECTED",
    "SESSION_SUCCESS",
    "SESSION_VALIDATING",
    "SESSION_WAITING_FOR_REVIEW",
    "StrategyAdapter",
    "DebugCase",
    "DebugDecision",
    "DebugEngine",
    "FixStrategy",
    "FIX_STRATEGIES",
    "RootCause",
    "coerce_strategy",
]


def DebugEngine(*args: Any, **kwargs: Any) -> Any:
    """DebugEngine 惰性实例化 (避免 debug_engine 循环依赖)。"""
    from .debug_engine import DebugEngine as _DebugEngine

    return _DebugEngine(*args, **kwargs)


# ---------------------------------------------------------------- Part 2 模块再导出
# 置于全部数据模型定义之后 — 子模块 `from . import ...` 依赖本包已定义的名字

from .context_budget import ContextBudget  # noqa: E402
from .debug_session import (  # noqa: E402
    SESSION_ANALYZING,
    SESSION_BLOCKED,
    SESSION_REPAIRING,
    SESSION_RETRYING,
    SESSION_ROOT_CAUSE_IDENTIFIED,
    SESSION_STATUSES,
    SESSION_STRATEGY_SELECTED,
    SESSION_SUCCESS,
    SESSION_VALIDATING,
    SESSION_WAITING_FOR_REVIEW,
    DebugAttempt,
    DebugSession,
    DebugSessionStore,
)
from .debug_trace import DebugTrace  # noqa: E402
from .repair_safety import RepairSafety  # noqa: E402
from .retrieval_policy import DebugRetrievalPolicy  # noqa: E402
from .strategy_adaptation import StrategyAdapter  # noqa: E402


def DebugPipeline(*args: Any, **kwargs: Any) -> Any:
    """DebugPipeline 惰性实例化 (避免 debug_pipeline 循环依赖)。"""
    from .debug_pipeline import DebugPipeline as _DebugPipeline

    return _DebugPipeline(*args, **kwargs)
