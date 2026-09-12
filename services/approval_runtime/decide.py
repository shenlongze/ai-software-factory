"""services/approval_runtime/decide.py — 审批决定（状态机，绞杀 S1.5）。

逐条对照 factory-exec/exec/approval.py:decide：
- pending → approved|rejected（终态不可逆）
- 二次决定 → 报错（"already decided"）
- approve → 触发审计事件（经 on_approved 回调注入，不硬依赖 factory-exec）
存储沿用 <exec_dir>/approvals.json（不改格式）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from .store import ApprovalRecord, ApprovalStore


class ApprovalDecideError(Exception):
    """审批决定失败（不存在 / 非法值 / 已终态）。"""


#: CLI 动词 → 语义终态（同原实现）
_DECISION_MAP = {
    "approve": "approved", "approved": "approved",
    "reject": "rejected", "rejected": "rejected", "deny": "rejected",
}


def decide(
    store: ApprovalStore,
    approval_id: str,
    decision: str,
    *,
    decided_by: str = "",
    comment: str = "",
    on_approved: Callable[[ApprovalRecord], None] | None = None,
) -> ApprovalRecord:
    """Human 决定（approve → approved / reject → rejected；终态不可逆）。

    on_approved: 审批通过时的审计回调（调用方注入；默认不发）。
    """
    record = store.get(approval_id)
    if record is None:
        raise ApprovalDecideError(f"approval not found: {approval_id}")
    value = _DECISION_MAP.get(str(decision).lower())
    if value is None:
        raise ApprovalDecideError(f"invalid approval decision: {decision!r}")
    if record.decision != "pending":
        raise ApprovalDecideError(
            f"approval already decided: {approval_id} = {record.decision}")
    record.decision = value
    record.decided_by = decided_by
    record.comment = comment
    record.decided_at = datetime.now(timezone.utc).isoformat()
    store.save(record)
    if value == "approved" and on_approved is not None:
        on_approved(record)
    return record
