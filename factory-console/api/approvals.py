"""factory-console/api/approvals.py — GET /approvals 路由函数 (只读)。

返回全部审批请求只读投影 (ApprovalSummary): artifact/gate/confidence/risk/
evidence/status。**只读不决定**: 打开审批 ≠ 决定审批 — approve/reject/
changes_requested/delegated 决策权永远在 9c Approval 状态机 (product
approval decide), Console 层不提供任何写路径。
"""

from __future__ import annotations

from typing import Any

from ..events import record_console_viewed
from ..models import ApprovalSummary

VIEW = "approvals"


def list_approvals(
    service: Any,
    *,
    logger: Any = None,
    pending_only: bool = False,
) -> list[ApprovalSummary]:
    """GET /approvals — 审批清单 (只读聚合 + console.viewed 审计)。

    pending_only=True 时只返回待审批请求 (Console Dashboard 待审批域同源,
    不复制过滤逻辑 — Dashboard 直接消费派生属性)。
    """
    approvals = service.list_approvals()
    if pending_only:
        approvals = [a for a in approvals if a.status == "pending"]
    if logger is not None:
        record_console_viewed(
            logger,
            view=VIEW,
            count=len(approvals),
            extra={"pending_only": pending_only, "pending": sum(1 for a in approvals if a.status == "pending")},
        )
    return approvals


__all__ = ["VIEW", "list_approvals"]
