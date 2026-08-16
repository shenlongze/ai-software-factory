"""factory-console/session/review_view.py — ReviewView (S10-065 P0-3)。

Human Review UX (GAP G3): ReviewGate 已有 (S10-063) 但无用户友好视图 —
本模块只做 UX/View 包装: ReviewRecord + 项目上下文 → 用户可读审批界面。

组件:
- DEFAULT_OPTIONS — 缺省选项 [APPROVE, REJECT, CANCEL]
- ReviewView — @dataclass {review_id/status/reason/risk/trigger/current_task/
  current_agent/current_cost/budget_limit/plan_version/options} +
  from_review(record, context=) / to_dict() / to_markdown()

设计: docs/sprint10/S10-065-interactive-discovery-design.md §4
GAP: docs/sprint10/S10-065-gap-analysis.md G3
边界: 纯包装 (不重写 ReviewGate 状态流转); 纯标准库零依赖;
缺失上下文 → 缺省占位 (不抛); 不修改任何现有模块。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

#: 缺省选项 (用户可选择: 继续 / 拒绝 / 取消)
DEFAULT_OPTIONS: list[str] = ["APPROVE", "REJECT", "CANCEL"]


@dataclass
class ReviewView:
    """用户友好审批视图 (设计 §4): 原因 + 当前状态 + 选项。

    from_review(record, context=) 构造; context 提供项目上下文
    (current_task/current_agent/current_cost/budget_limit/plan_version —
    通常来自 ProductionSession.view() 聚合, 缺失 → 缺省占位)。
    """

    review_id: str = ""
    status: str = "open"
    reason: str = ""
    risk: str = "medium"
    trigger: str = ""
    current_task: str = ""
    current_agent: str = ""
    current_cost: float = 0.0
    budget_limit: float = 0.0
    plan_version: int = 1
    options: list[str] = field(default_factory=lambda: list(DEFAULT_OPTIONS))

    @classmethod
    def from_review(
        cls,
        record: Any,
        *,
        context: Optional[dict[str, Any]] = None,
    ) -> "ReviewView":
        """ReviewRecord + 项目上下文 → ReviewView (缺失字段 → 缺省, 失败安全)。

        record 可为 ReviewRecord 或任意带 review_id/status/reason/risk/trigger
        属性的对象 (getattr 宽容); context 键:
        current_task / current_agent / current_cost / budget_limit / plan_version。
        """
        ctx = dict(context or {})
        return cls(
            review_id=str(getattr(record, "review_id", "") or ""),
            status=str(getattr(record, "status", "") or ""),
            reason=str(getattr(record, "reason", "") or ""),
            risk=str(getattr(record, "risk", "") or ""),
            trigger=str(getattr(record, "trigger", "") or ""),
            current_task=str(ctx.get("current_task") or ""),
            current_agent=str(ctx.get("current_agent") or ""),
            current_cost=float(ctx.get("current_cost") or 0.0),
            budget_limit=float(ctx.get("budget_limit") or 0.0),
            plan_version=int(ctx.get("plan_version") or 1),
        )

    def to_dict(self) -> dict[str, Any]:
        """→ dict (渲染/审计视图 — 顶层字段 + 选项)。"""
        return {
            "review_id": self.review_id,
            "status": self.status,
            "reason": self.reason,
            "risk": self.risk,
            "trigger": self.trigger,
            "current_task": self.current_task,
            "current_agent": self.current_agent,
            "current_cost": round(self.current_cost, 6),
            "budget_limit": round(self.budget_limit, 6),
            "plan_version": int(self.plan_version),
            "options": list(self.options),
        }

    def to_markdown(self) -> str:
        """用户友好审批界面 (设计 §4 示例口径):

        ⚠️ AI Factory 需要你的确认
        原因: ...
        当前任务: ...
        Agent: ...
        当前成本: $...
        预算: $...
        请选择: 继续 / 拒绝 / 取消
        """
        lines = [
            "⚠️ AI Factory 需要你的确认",
            "",
            f"原因: {self.reason or '(未说明)'}",
            f"当前任务: {self.current_task or '(无进行中任务)'}",
            f"Agent: {self.current_agent or '(未指定)'}",
            f"当前成本: ${self.current_cost:.2f}",
            f"预算: ${self.budget_limit:.2f}",
            "",
            "请选择: 继续 / 拒绝 / 取消",
        ]
        return "\n".join(lines)


__all__ = [
    "ReviewView",
    "DEFAULT_OPTIONS",
]
