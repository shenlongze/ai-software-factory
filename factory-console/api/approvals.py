"""factory-console/api/approvals.py — GET /approvals + POST 决定路由函数。

GET /approvals: 全部审批请求只读投影 (ApprovalSummary)。**只读不决定** —
打开审批 ≠ 决定审批。

S9-002 扩展 (Console MVP, 用户明确解除 Console 冻结 — 可操作):
- POST /approvals/{id}/approve — 审批放行 (接 org.approval S9-001:
  WorkflowLifecycle.approve_approval; gate → APPROVED 终态 + workflow
  PAUSED→ACTIVE 恢复; source="console" 审计)
- POST /approvals/{id}/reject  — 审批否决 (gate → REJECTED 终态 +
  workflow FAILED 停止; 决定不可撤销 — 审计铁律)
错误语义 (HTTP 层映射): 门不存在 → None (404); 非 PENDING 门 →
org ApprovalStateError 抛出 (409 Conflict); org 扩展缺失 → None (404)。
决定事件: org.approval.approved/rejected (source="console") — 复用
S9-001 事件链, Console 层零新事件类型。
"""

from __future__ import annotations

from typing import Any

from ..events import record_console_viewed
from ..models import ApprovalDecisionSummary, ApprovalGateSummary, ApprovalSummary
from ..service import ConsoleService

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


def conflict_status(exc: BaseException) -> bool:
    """org ApprovalStateError → True (HTTP 409 映射, 11B 薄层共用)。

    非 PENDING 门决定 (终态不可撤销) → 409 Conflict; org 缺失/异常类型
    非已知 → False (调用方按默认错误路径处理)。
    """
    _, state_error = _org_exceptions()
    return bool(state_error and isinstance(exc, state_error))


def list_approval_gates(
    service: Any,
    *,
    logger: Any = None,
    status: str | None = None,
    workflow_id: str | None = None,
) -> list[ApprovalGateSummary]:
    """GET /approval-gates — org 审批门清单 (S9-002 决定操作对象 + 审计)。

    与 list_approvals (product 9c 遗留只读视图) 区分: 本清单的 id 即
    POST /approvals/{id}/approve|reject 的操作对象 (org ApprovalGate,
    S9-001)。logger 存在时发 console.viewed (view="approval_gates")。
    """
    gates = service.list_approval_gates(status=status, workflow_id=workflow_id)
    if logger is not None:
        record_console_viewed(
            logger,
            view="approval_gates",
            count=len(gates),
            extra={
                "status": status,
                "workflow_id": workflow_id,
                "pending": sum(1 for g in gates if g.status == "pending"),
            },
        )
    return gates


def _org_exceptions() -> tuple[type[BaseException], type[BaseException]]:
    """org 异常类型 (延迟导入 — 先挂 factory-org 到 sys.path)。

    失败安全: org 不可导入 → 空异常元组 (调用方按无 org 处理 → None)。
    """
    ConsoleService._mount_org()
    try:
        from org.approval import ApprovalStateError  # type: ignore[import-not-found]
        from org.lifecycle import NotFoundError  # type: ignore[import-not-found]
    except Exception:
        return (), ()
    return NotFoundError, ApprovalStateError  # type: ignore[return-value]


def _decide(
    service: Any,
    approval_id: str,
    action: str,
    *,
    reviewer: str,
    comment: str,
) -> ApprovalDecisionSummary | None:
    """POST 决定公共路径 (approve/reject; 错误语义统一映射)。"""
    method = getattr(service, f"{action}_approval")
    try:
        result = method(approval_id, reviewer=reviewer, comment=comment)
    except Exception as exc:
        not_found, state_error = _org_exceptions()
        if not_found and isinstance(exc, not_found):
            return None  # 门不存在 → 404 (HTTP 层映射)
        if state_error and isinstance(exc, state_error):
            raise  # 非 PENDING 决定 → 409 (HTTP 层映射)
        raise
    return result


def approve_approval(
    service: Any,
    approval_id: str,
    *,
    reviewer: str = "",
    comment: str = "",
    logger: Any = None,
) -> ApprovalDecisionSummary | None:
    """POST /approvals/{id}/approve — 审批放行 (接 org.approval S9-001)。

    返回决定投影 (ApprovalDecisionSummary); 门不存在/org 缺失 → None
    (404); 非 PENDING 门 → org ApprovalStateError (409)。审计事件:
    org.approval.approved (source="console", reviewer/comment 落库)。
    """
    return _decide(
        service, approval_id, "approve", reviewer=reviewer, comment=comment
    )


def reject_approval(
    service: Any,
    approval_id: str,
    *,
    reviewer: str = "",
    comment: str = "",
    logger: Any = None,
) -> ApprovalDecisionSummary | None:
    """POST /approvals/{id}/reject — 审批否决 (接 org.approval S9-001)。

    决定投影同 approve; 审计事件: org.approval.rejected (source="console").
    reject 后 workflow FAILED 停止 (failed_reason 记录否决原因)。
    """
    return _decide(
        service, approval_id, "reject", reviewer=reviewer, comment=comment
    )


__all__ = [
    "VIEW",
    "approve_approval",
    "conflict_status",
    "list_approval_gates",
    "list_approvals",
    "reject_approval",
]
