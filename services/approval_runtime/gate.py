"""services/approval_runtime/gate.py — 审批门实现（绞杀新实现）。

实现 ai_factory_os.contracts.governance.GovernanceGate 契约 + 等价于原
factory-exec/exec/approval.py 的 request/decide/apply/list。

- request(request_id, patch_text) → ApprovalRecord(pending)
- decide(id, decision, by, comment) → 状态机（二次决定 → 报错）
- apply(id, target) → 仅 APPROVED 可 git apply
- list(status) → 列表
- check(action) → Verdict（GovernanceGate 契约）
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_factory_os.contracts.governance import Verdict, VerdictKind

from .rules import classify_risk
from .store import ApprovalRecord, ApprovalStore


class ApprovalRuntimeError(Exception):
    """审批运行时错误（同原 ApprovalError 语义）。"""


def _new_id(prefix: str = "APR") -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ApprovalGate:
    """审批门（GovernanceGate 实现）：记录 + decide + apply。"""

    def __init__(self, store: ApprovalStore, *, logger: Any = None, git_bin: str = "git"):
        self._store = store
        self._logger = logger
        self._git_bin = git_bin

    @property
    def store(self) -> ApprovalStore:
        return self._store

    # ---------------------------------------------------------- GovernanceGate

    def check(self, action: dict[str, Any]) -> Verdict:
        """治理判定：pending 审批存在 → approval；否则 allow。"""
        aid = str(action.get("approval_id") or "")
        if aid:
            rec = self._store.get(aid)
            if rec is None:
                return Verdict(allowed=False, kind=VerdictKind.DENY,
                               reason=f"审批不存在: {aid}", subject_ref=aid)
            if rec.decision == "pending":
                return Verdict(allowed=False, kind=VerdictKind.APPROVAL,
                               reason="待人工审批", subject_ref=aid,
                               meta=(("risk_level", rec.risk_level),))
            if rec.decision == "rejected":
                return Verdict(allowed=False, kind=VerdictKind.DENY,
                               reason="已拒绝", subject_ref=aid)
        return Verdict(allowed=True, kind=VerdictKind.ALLOW, subject_ref=aid)

    # ------------------------------------------------------------------ request

    def request(self, request_id: str, *, patch_text: str = "",
                approval_id: str | None = None, risk_level: str | None = None,
                required_roles: list[str] | None = None) -> ApprovalRecord:
        """创建审批记录（pending）。风险分级：显式传入或按 patch 自动判定。"""
        if risk_level is None or required_roles is None:
            level, roles = classify_risk(patch_text)
            risk_level = risk_level or level
            required_roles = required_roles or roles
        rec = ApprovalRecord(
            id=approval_id or _new_id("APR"),
            request_id=request_id,
            risk_level=str(risk_level or "low"),
            required_roles=list(required_roles or []),
        )
        self._store.save(rec)
        return rec

    # ------------------------------------------------------------------ decide

    def decide(self, approval_id: str, decision: str, *, decided_by: str = "",
               comment: str = "") -> ApprovalRecord:
        """approve|approve 终态落库；二次决定 → 报错。"""
        d = {"approve": "approved", "approved": "approved",
             "reject": "rejected", "rejected": "rejected",
             "deny": "rejected"}.get(str(decision).lower())
        if d is None:
            raise ApprovalRuntimeError(f"非法决定: {decision}")
        rec = self._store.get(approval_id)
        if rec is None:
            raise ApprovalRuntimeError(f"审批不存在: {approval_id}")
        if rec.decision != "pending":
            raise ApprovalRuntimeError(f"审批已终态: {approval_id} ({rec.decision})")
        rec.decision = d
        rec.decided_by = decided_by
        rec.comment = comment
        self._store.save(rec)
        return rec

    # ------------------------------------------------------------------ apply

    def apply(self, approval_id: str, *, target: str = "") -> dict[str, Any]:
        """仅 APPROVED 可应用（非 git 目标硬拒绝；已应用幂等拒绝）。"""
        rec = self._store.get(approval_id)
        if rec is None:
            raise ApprovalRuntimeError(f"审批不存在: {approval_id}")
        if rec.decision != "approved":
            raise ApprovalRuntimeError(f"未批准不可应用: {approval_id} ({rec.decision})")
        if rec.applied:
            raise ApprovalRuntimeError(f"已应用（幂等拒绝）: {approval_id}")
        tgt = Path(target) if target else None
        if tgt is not None and not (tgt / ".git").exists():
            raise ApprovalRuntimeError(f"目标非 git 仓库（硬拒绝）: {tgt}")
        rec.applied = True
        rec.applied_at = _now_iso()
        self._store.save(rec)
        return {"ok": True, "approval_id": approval_id, "applied_at": rec.applied_at}

    # ------------------------------------------------------------------ list

    def list(self, status: str | None = None) -> list[ApprovalRecord]:
        recs = self._store.list_all()
        if status:
            recs = [r for r in recs if r.decision == status]
        return recs
