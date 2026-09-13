"""factory-console/session/debug/debug_strategy.py — DebugStrategySelector (S10-068 G4)。

修复策略选择: RootCause + 历史经验 + DebugCase → DebugDecision。

设计: docs/sprint10/S10-068-debug-intelligence-design.md §6
规则 (顺序 = 优先级, 确定性):
  1. REQUEST_REVIEW — 错误未分类 (UNKNOWN)
  2. FIX_CODE       — 历史成功经验 (SUCCESS_PATTERN/DEBUG 且 confidence >= 0.6)
  3. FIX_TEST       — 验证失败 (TEST_FAILURE/ASSERTION)
  4. CHANGE_DESIGN  — 架构/契约问题 (API_CONTRACT)
  5. ROLLBACK       — 重复失败 (previous_attempts >= 2)
  6. REQUEST_REVIEW — 低置信无经验 (无相关经验且根因置信 < 0.5)
  7. FIX_CODE       — 兜底 (常规缺陷)
LLM 可选 (llm_provider) — 失败 → 规则兜底。
"""

from __future__ import annotations

import re
from typing import Any, Optional

from . import (
    ERROR_API_CONTRACT,
    ERROR_ASSERTION,
    ERROR_TEST_FAILURE,
    ERROR_UNKNOWN,
    DebugCase,
    DebugDecision,
    FixStrategy,
    RootCause,
)
from ...memory.experience import DEBUG_EXPERIENCE, SUCCESS_PATTERN

#: 成功经验判定阈值 (confidence >= 0.6 且 success=True → 可信修复先例)
_SUCCESS_CONFIDENCE = 0.6

#: 低置信阈值 (无经验且根因置信 < 0.5 → 请求人工评审)
_LOW_CONFIDENCE = 0.5

#: 重复失败阈值 (previous_attempts >= 2 → ROLLBACK)
_MAX_ATTEMPTS = 2


class DebugStrategySelector:
    """策略选择器 (G4): select(root_cause, related_experiences, debug_case) -> DebugDecision。"""

    def select(
        self,
        root_cause: Any,
        related_experiences: Optional[list[Any]] = None,
        debug_case: Any = None,
        *,
        llm_provider: Any = None,
    ) -> DebugDecision:
        """根因 + 经验 + 案件 → DebugDecision (规则顺序见模块 docstring; 不抛)。"""
        cause = root_cause if isinstance(root_cause, RootCause) else RootCause.from_dict(root_cause)
        case = debug_case
        if case is None:
            case = DebugCase(error_message=cause.cause)
        elif not isinstance(case, DebugCase):
            case = DebugCase.from_dict(case)

        error_type = str(case.error_type or "")
        attempts = _as_int(case.previous_attempts, 0)
        experiences = list(related_experiences or [])
        evidence = _evidence_lines(cause, experiences)

        # 可选 LLM: 策略生成 (失败 → 规则兜底, 绝不裸抛)
        if llm_provider is not None:
            try:
                llm_decision = llm_provider(case, cause, experiences)
                if isinstance(llm_decision, dict) and llm_decision.get("strategy"):
                    return self._build(
                        llm_decision["strategy"],
                        str(llm_decision.get("reason") or "LLM 策略推荐"),
                        _as_float(llm_decision.get("confidence"), 0.6),
                        evidence,
                        experiences,
                    )
            except Exception:  # noqa: BLE001 — LLM 失败 → 规则兜底
                pass

        # 1) 错误未分类 → 人工评审 (最高优先级: 无法理解就不能盲目修复)
        if not error_type or error_type == ERROR_UNKNOWN:
            return self._build(
                FixStrategy.REQUEST_REVIEW,
                "错误未分类, 无法确定修复策略 — 请求人工评审",
                max(0.4, cause.confidence),
                evidence,
                experiences,
            )

        # 2) 历史成功经验 → 直接修复代码
        success_exp = next(
            (
                r
                for r in experiences
                if getattr(r, "success", False)
                and getattr(r, "type", "") in (SUCCESS_PATTERN, DEBUG_EXPERIENCE)
                and getattr(r, "confidence", 0.0) >= _SUCCESS_CONFIDENCE
            ),
            None,
        )
        if success_exp is not None:
            action = getattr(success_exp, "action", "") or getattr(success_exp, "problem", "") or "历史修复方案"
            return self._build(
                FixStrategy.FIX_CODE,
                f"历史成功经验可复用: {action}",
                max(0.7, cause.confidence),
                evidence,
                experiences,
            )

        # 3) 验证失败 → 修测试
        if error_type in (ERROR_TEST_FAILURE, ERROR_ASSERTION):
            # S10-071 P0-1: ASSERTION 含 expected/got → 测试=需求定义, 修正实现 (FIX_CODE)
            msg = str(getattr(case, "error_message", "") or "")
            if error_type == ERROR_ASSERTION and re.search(
                    r"expected\s+.+?(?:but\s+)?got\s+", msg, re.IGNORECASE):
                return self._build(
                    FixStrategy.FIX_CODE,
                    "断言失败且含期望/实际对比 — 测试为需求定义, 修正实现代码",
                    max(0.7, cause.confidence),
                    evidence,
                    experiences,
                )
            return self._build(
                FixStrategy.FIX_TEST,
                "验证失败 (测试/断言) — 先修正测试或实现以通过验证",
                0.7,
                evidence,
                experiences,
            )

        # 4) 架构/契约问题 → 改设计
        if error_type == ERROR_API_CONTRACT:
            return self._build(
                FixStrategy.CHANGE_DESIGN,
                "API 契约/架构问题 — 需要调整契约或设计",
                0.7,
                evidence,
                experiences,
            )

        # 5) 重复失败 → 回滚
        if attempts >= _MAX_ATTEMPTS:
            return self._build(
                FixStrategy.ROLLBACK,
                f"已重试 {attempts} 次仍失败 — 建议回滚/停止重试",
                max(0.7, cause.confidence),
                evidence,
                experiences,
            )

        # 6) 低置信无经验 → 人工评审
        if not experiences and cause.confidence < _LOW_CONFIDENCE:
            return self._build(
                FixStrategy.REQUEST_REVIEW,
                "无历史经验且根因置信度低 — 请求人工评审",
                cause.confidence,
                evidence,
                experiences,
            )

        # 7) 兜底: 常规缺陷 → 修代码
        return self._build(
            FixStrategy.FIX_CODE,
            "常规缺陷 — 按根因修复代码",
            max(0.6, cause.confidence),
            evidence,
            experiences,
        )

    # ------------------------------------------------------------ 内部

    def _build(
        self,
        strategy: Any,
        reason: str,
        confidence: float,
        evidence: list[str],
        experiences: list[Any],
    ) -> DebugDecision:
        """DebugDecision 装配 (strategy 非法 → ValueError — 校验铁律)。"""
        from . import coerce_strategy

        return DebugDecision(
            strategy=coerce_strategy(strategy),
            reason=reason,
            confidence=max(0.0, min(1.0, confidence)),
            evidence=list(evidence),
            related_experiences=list(experiences),
        )


def _evidence_lines(cause: RootCause, experiences: list[Any]) -> list[str]:
    """证据链: 根因 + 历史经验摘要。"""
    lines = [cause.cause] if cause.cause else []
    for record in experiences[:3]:
        action = getattr(record, "action", None) or ""
        problem = getattr(record, "problem", None) or ""
        lines.append(f"历史经验: {action or problem or '无描述'}")
    return lines


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.5) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
