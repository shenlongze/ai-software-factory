"""factory-console/session/debug/repair_safety.py — RepairSafety (S10-068 Part 2, G3)。

Governance 接入: Budget/Cost/Retry limit/LoopGuard/Policy/ReviewGate 约束 Debug 执行
→ 决策 AUTO / SAFE_AUTO / REVIEW / BLOCKED (缺省安全: 组件缺失 → 对应维度
不设卡, 但尝试上限与终态约束始终生效)。

设计: docs/sprint10/S10-068-part2-design.md §4
复用 (只读, 不修改): session/budget.py BudgetEnforcer + BudgetUsage、
session/loop_guard.py LoopGuard、session/execution_policy.py ExecutionPolicy、
session/review_gate.py ReviewGate。

决策优先级 (从高到低): BLOCKED > REVIEW > SAFE_AUTO > AUTO。
边界:
- 纯标准库, 零新依赖; 只判定, 不执行动作
- 缺省安全: budget=None → 预算维度不设卡; loop_guard=None → 循环维度不设卡;
  policy=None → 策略维度按 AUTO 宽松; review_gate=None → 评审维度不设卡;
  但 attempts >= max_attempts → REVIEW、>= 2*max_attempts → BLOCKED 恒生效
  (不无限重试铁律)
"""

from __future__ import annotations

from typing import Any, Optional

from ..budget import BudgetEnforcer, BudgetUsage
from ..execution_policy import MODE_AUTO, MODE_SAFE_AUTO
from . import SESSION_BLOCKED, SESSION_WAITING_FOR_REVIEW  # noqa: F401 — 状态口径再导出

# ---------------------------------------------------------------- 决策常量

DECISION_AUTO = "AUTO"
DECISION_SAFE_AUTO = "SAFE_AUTO"
DECISION_REVIEW = "REVIEW"
DECISION_BLOCKED = "BLOCKED"

#: 全部合法决策
DECISIONS: tuple[str, ...] = (
    DECISION_AUTO,
    DECISION_SAFE_AUTO,
    DECISION_REVIEW,
    DECISION_BLOCKED,
)


class RepairSafety:
    """修复安全闸 (G3): check(session, ...) -> (decision, reason)。

    check(session, *, budget, usage, loop_guard, history, policy, review_gate,
          max_attempts) -> (decision, reason):
      1. budget enforce("repair") level=block → BLOCKED; level=review → REVIEW;
      2. loop_guard.check_failure action=block → BLOCKED; action=review → REVIEW;
      3. review_gate.pending() 非空 → REVIEW (WAITING_FOR_REVIEW 语义);
      4. policy.can_repair 不允许 → REVIEW; 模式 SAFE_AUTO 且允许 → SAFE_AUTO;
      5. attempts >= 2*max_attempts → BLOCKED; >= max_attempts → REVIEW
         (连续失败超限 — 不无限重试);
      6. 其余 → AUTO (预算充足 + 未超限 + policy 允许)。
    """

    DECISION_AUTO = DECISION_AUTO
    DECISION_SAFE_AUTO = DECISION_SAFE_AUTO
    DECISION_REVIEW = DECISION_REVIEW
    DECISION_BLOCKED = DECISION_BLOCKED

    @classmethod
    def check(
        cls,
        session: Any,
        *,
        budget: Any = None,
        usage: Any = None,
        loop_guard: Any = None,
        history: Any = None,
        policy: Any = None,
        review_gate: Any = None,
        max_attempts: int = 3,
    ) -> tuple[str, str]:
        """修复决策 (BLOCKED > REVIEW > SAFE_AUTO > AUTO; 失败安全)。"""
        reasons: list[str] = []
        attempts = int(getattr(session, "attempt_number", 0) or 0)
        limit = max(1, int(max_attempts or 3))

        # 1) 预算闸 (S10-063 BudgetEnforcer: block 级禁 repair; review 级等审批)
        if budget is not None:
            usage_obj = usage if usage is not None else BudgetUsage.from_records([], budget=budget)
            result = BudgetEnforcer.enforce(budget, usage_obj, "repair")
            if result["level"] == BudgetEnforcer.LEVEL_BLOCK:
                return DECISION_BLOCKED, f"BUDGET BLOCK: {result['reason']}"
            if result["level"] == BudgetEnforcer.LEVEL_REVIEW:
                reasons.append(f"预算评审线: {result['reason']}")

        # 2) 循环总闸 (S10-063 LoopGuard: 同失败/总执行超限)
        if loop_guard is not None:
            key = str(getattr(session, "error_summary", "") or "")[:80] or "debug-failure"
            guard = loop_guard.check_failure(
                str(getattr(session, "task_id", "") or ""), key, list(history or [])
            )
            if guard["action"] == "block":
                return DECISION_BLOCKED, f"LOOP BLOCK: {guard['reason']}"
            if guard["action"] == "review":
                reasons.append(f"循环评审: {guard['reason']}")

        # 3) 人工评审闸 (ReviewGate: 存在 open 评审 → WAITING_FOR_REVIEW)
        if review_gate is not None:
            try:
                pending = review_gate.pending()
            except Exception:  # noqa: BLE001 — 失败安全: 评审闸异常 → 不设卡
                pending = []
            if pending:
                return DECISION_REVIEW, (
                    f"存在 {len(pending)} 个待评审请求 (WAITING_FOR_REVIEW) — "
                    f"修复需人工审批"
                )

        # 4) 执行策略闸 (ExecutionPolicy: AUTO 全放行 / SAFE_AUTO 风险+置信度 /
        #    REVIEW_REQUIRED、MANUAL 无批准 → 禁)
        if policy is not None:
            context: dict[str, Any] = {
                "confidence": float(getattr(session, "root_cause_confidence", 0.0) or 0.0),
                "reason": f"debug repair for {getattr(session, 'error_summary', '') or ''}",
                "task": str(getattr(session, "error_type", "") or ""),
            }
            allowed, reason = policy.can_repair(context)
            if not allowed:
                return DECISION_REVIEW, f"POLICY REVIEW: {reason}"
            if getattr(policy, "mode", MODE_AUTO) == MODE_SAFE_AUTO:
                reasons.append(f"SAFE_AUTO: {reason}")

        # 5) 连续失败超限 (不无限重试铁律 — 即使无外部治理组件也生效)
        if attempts >= limit * 2:
            return DECISION_BLOCKED, (
                f"已尝试 {attempts} 次 (>= 2×max_attempts {limit * 2}) — "
                f"连续失败超限 BLOCKED"
            )
        if attempts >= limit:
            reasons.append(
                f"已尝试 {attempts} 次 (>= max_attempts {limit}) — 需人工评审"
            )

        if reasons:
            return DECISION_REVIEW, "; ".join(reasons)
        return DECISION_AUTO, (
            "预算充足 + 未超限 + 策略允许 — 自动修复 (AUTO)"
        )
