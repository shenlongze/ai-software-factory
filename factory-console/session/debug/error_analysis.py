"""factory-console/session/debug/error_analysis.py — ErrorAnalyzer (S10-068 G1)。

错误理解: 原始 error_message/stack_trace → 结构化 DebugCase + error_type 分类。

设计: docs/sprint10/S10-068-debug-intelligence-design.md §3
边界:
- 纯标准库, 零模块依赖; 规则分类 (关键词 → 类型), 未知 → ERROR_UNKNOWN 兜底
- 分类不抛 (空输入 → UNKNOWN); extract 失败安全 (字段缺省兜底)
"""

from __future__ import annotations

import re
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
)

#: 分类规则表 (顺序 = 优先级 — 先命中先赢; 关键词一律小写匹配):
#: (error_type, 关键词元组)
_CLASSIFY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (ERROR_TIMEOUT, ("timeout", "timed out", "超时", "time out")),
    (ERROR_IMPORT, ("import", "module", "modulenotfound", "无法导入", "导入失败", "no module")),
    (ERROR_ASSERTION, ("assert", "assertion", "断言")),
    (ERROR_AUTH, ("credential", "unauthorized", "authentication", "api key", "apikey",
                  "access denied", "密钥", "认证", "token", "invalid key")),
    (ERROR_API_CONTRACT, ("contract", "schema", "契约", "接口", "field", "payload")),
    (ERROR_NULL, ("null", "nonetype", "空指针", "none value", "为 null")),
    (ERROR_MISSING, ("missing", "not found", "不存在", "缺少", "缺失", "找不到", "no such")),
    (ERROR_TEST_FAILURE, ("pytest", "test failed", "test failure", "failed", "失败", "tests failed")),
)

#: 错误类型中文名 (展示/输出口径)
ERROR_TYPE_LABELS: dict[str, str] = {
    ERROR_TIMEOUT: "超时",
    ERROR_IMPORT: "导入错误",
    ERROR_ASSERTION: "断言失败",
    ERROR_AUTH: "认证/密钥错误",
    ERROR_API_CONTRACT: "API 契约错误",
    ERROR_NULL: "空值错误",
    ERROR_MISSING: "缺失错误",
    ERROR_TEST_FAILURE: "测试失败",
    ERROR_UNKNOWN: "未分类",
}


def _normalize(text: str) -> str:
    """匹配前归一化: 去空白 + 小写 (英文关键词大小写不敏感)。"""
    return re.sub(r"\s+", " ", str(text or "")).lower()


class ErrorAnalyzer:
    """错误分析器 (G1): classify + extract。

    classify(error_message, stack_trace=None) -> error_type:
      关键词规则 → 类型 (顺序 = 优先级); 无命中 → ERROR_UNKNOWN。
    extract(error_message, stack_trace=None, **kw) -> DebugCase:
      classify + 结构化 DebugCase (task_id/agent_id/affected_files/context/
      previous_attempts/project 由 kw 透传, 缺省兜底)。
    """

    #: 规则表 (可注入 — 测试/未来 LLM 扩展; 缺省 = 内置规则)
    def __init__(self, rules: Optional[tuple[tuple[str, tuple[str, ...]], ...]] = None) -> None:
        self._rules = rules if rules is not None else _CLASSIFY_RULES

    def classify(self, error_message: str, stack_trace: Optional[str] = None) -> str:
        """错误分类: 关键词 → error_type (顺序 = 优先级; 无命中 → UNKNOWN)。"""
        haystack = _normalize(error_message)
        if stack_trace:
            haystack = f"{haystack} {_normalize(stack_trace)}"
        if not haystack:
            return ERROR_UNKNOWN
        for error_type, keywords in self._rules:
            for keyword in keywords:
                if keyword in haystack:
                    return error_type
        return ERROR_UNKNOWN

    def extract(
        self,
        error_message: str,
        stack_trace: Optional[str] = None,
        **kw: Any,
    ) -> DebugCase:
        """错误 → DebugCase (classify 自动填充 error_type; 字段缺省兜底)。"""
        return DebugCase(
            error_message=str(error_message or ""),
            error_type=self.classify(error_message, stack_trace),
            stack_trace=str(stack_trace or ""),
            task_id=str(kw.get("task_id") or ""),
            agent_id=str(kw.get("agent_id") or ""),
            affected_files=list(kw.get("affected_files") or []),
            context=str(kw.get("context") or ""),
            previous_attempts=_as_int(kw.get("previous_attempts"), 0),
            project=str(kw.get("project") or ""),
        )


def _as_int(value: Any, default: int = 0) -> int:
    """任意值 → int (失败安全: 非法 → default)。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
