"""factory_console/governance_service — ★ 已切: 本模块**只做转发**（2026-09-15）。

沿革: S17 Workforce Governance & Human Approval（348 行的原实现, 含自己的存储）。

它曾是审批的第 3 套实现（与 `services/governance/` 各写各的, 甚至格式不同:
老区写 list、新版读 dict ⇒ 新版一直读不了老区数据）。

★ 2026-09-15 Founder 裁决 A 后的处置:
   · **审批实现**: 切到 `services/governance/`（ApprovalGate · ApprovalStore · rules）
     —— 存储统一在 `<root>/governance/approvals.json`（84 条真实记录已无损迁移）
   · **两个门**（check_governance / release）: 迁到 `services/governance/gates.py`
     —— 它们是新地基地原本没有的能力
   · 本模块保留为**薄转发层**, 只为让 16 个既有引用方（adaptive_workforce ·
     optimization_service · project_os · learning_truth · release_truth · rollback_service ·
     effectiveness_service · llm_experiment_service · session/agent_loop · …）**零改动**。

⇒ 实现只有一处; 这里只做「老签名 → 新实现」的适配 + 返回值字段名兼容
  （老: `approval_id`/大写 decision; 新: `id`/小写）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_factory_os.services.governance.gates import (  # noqa: F401 — 转发
    AGENT_APPROVERS,
    POLICIES,
    check_governance,
    release,
)
from ai_factory_os.services.governance.service import ApprovalGate
from ai_factory_os.services.governance.store import ApprovalStore

#: 老格式的 decision 常量（大写; 调用方按这个传/比）
APPROVAL_PENDING = "PENDING"
APPROVAL_APPROVED = "APPROVED"
APPROVAL_REJECTED = "REJECTED"

_TO_NEW = {"approve": "approved", "approved": "approved", "APPROVED": "approved",
           "reject": "rejected", "rejected": "rejected", "REJECTED": "rejected",
           "pending": "pending", "PENDING": "pending"}


def _store(root: Path | str) -> ApprovalStore:
    return ApprovalStore(Path(root) / "governance")


def _gate(root: Path | str) -> ApprovalGate:
    return ApprovalGate(_store(root))


def _legacy(rec: Any) -> dict[str, Any]:
    """新记录 → 老格式 dict（字段名 + decision 大小写兼容）。"""
    if rec is None:
        return {}
    d = rec.to_dict() if hasattr(rec, "to_dict") else dict(rec)
    d["approval_id"] = d.get("id", "")            # ★ 老字段名
    d["decision"] = str(d.get("decision", "")).upper()   # ★ 老大写
    d["reason"] = d.get("comment", "")
    d["requested_at"] = d.get("created_at", "")
    return d


# ── 审批（全部转发到 services/governance）

def request_approval(root: Path | str, *, production_run_id: str = "",
                     artifact_ids: list[str] | None = None, requested_by: str = "",
                     subject_type: str = "", subject_id: str = "",
                     policy_id: str = "", **_: Any) -> dict[str, Any]:
    """创建审批记录（老签名 → ApprovalGate.request）。"""
    rec = _gate(root).request(
        production_run_id or subject_id or "",
        subject_type=subject_type, subject_id=subject_id,
        artifact_ids=artifact_ids, requested_by=requested_by,
        approval_id=None, risk_level=None, required_roles=None,
    )
    return _legacy(rec)


def decide_approval(root: Path | str, approval_id: str, *, decision: str = "",
                    decided_by: str = "", comment: str = "", **_: Any) -> dict[str, Any]:
    """决定（老签名; decision 可大写 APPROVED/REJECTED）。"""
    d = _TO_NEW.get(str(decision or "").strip(), "rejected")
    return _legacy(_gate(root).decide(approval_id, d, decided_by=decided_by, comment=comment))


def approve(root: Path | str, approval_id: str, *, decided_by: str = "human",
            comment: str = "", **_: Any) -> dict[str, Any]:
    return decide_approval(root, approval_id, decision="approved",
                           decided_by=decided_by, comment=comment)


def reject(root: Path | str, approval_id: str, *, decided_by: str = "human",
           comment: str = "", **_: Any) -> dict[str, Any]:
    return decide_approval(root, approval_id, decision="rejected",
                           decided_by=decided_by, comment=comment)


def get_approval(root: Path | str, approval_id: str) -> dict[str, Any] | None:
    rec = _store(root).get(approval_id)
    return _legacy(rec) if rec is not None else None


def list_approvals(root: Path | str, *, production_run_id: str | None = None,
                   **_: Any) -> list[dict[str, Any]]:
    recs = _store(root).list_all()
    if production_run_id:
        recs = [r for r in recs
                if str(getattr(r, "request_id", "") or "") == production_run_id
                or str(getattr(r, "subject_id", "") or "") == production_run_id]
    return [_legacy(r) for r in recs]


def set_clock(fn: Any) -> None:  # noqa: ARG001 — 兼容旧调用点（新实现用 UTC now）
    """★ 已废弃: 时钟注入随原实现退役; 保留空实现以免旧调用点报错。"""
