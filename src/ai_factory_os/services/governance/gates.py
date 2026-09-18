"""services.governance.gates — 治理门（Governance Gate / Release Gate）。

★ 2026-09-15 自 _pending_migration/factory_console/governance_service.py 迁入
   （Founder 裁决 A: 审批部分切+删, 两个门迁到治理域）。

本模块只做**投影式判定**（从 domain facts 读, 不建第二事实源）:

- `check_governance(root, production_run_id, action=…)` → GovernanceGate 投影
    allowed / reason / policy / missing / approval / approval_expired
    读: ProductionRun 状态 · 审批记录（绑定 run + artifact, 不可 stale/expired）
- `release(root, production_run_id, …)` → Release Gate
    verification + evaluation + approval + policy 全过才 allowed; 不执行任何 workspace 变更
    （变更由调用方经 Artifact Lifecycle）

存储: 审批记录统一在 `services/governance/store.py`（`<root>/governance/approvals.json`）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .store import ApprovalStore

#: 策略表（哪些动作需要什么）
POLICIES: dict[str, dict[str, Any]] = {
    "code_generation": {"risk_level": "low", "approval_required": False,
                        "allowed_approvers": [], "required_verification": False},
    "test_execution": {"risk_level": "low", "approval_required": False,
                       "allowed_approvers": [], "required_verification": False},
    "production_apply": {"risk_level": "high", "approval_required": True,
                         "allowed_approvers": ["human"], "required_verification": True},
    "release": {"risk_level": "high", "approval_required": True,
                "allowed_approvers": ["human"], "required_verification": True,
                "required_evaluation": True},
    "learning_promotion": {"risk_level": "medium", "approval_required": True,
                           "allowed_approvers": ["human"], "required_verification": False},
}

#: Agent 不能批准（approver 必须是 human; Agent 只可 request）
AGENT_APPROVERS: set[str] = set()

#: 旧数据用大写 decision（APPROVED / PENDING / REJECTED）; 新记录用小写 —— 比较时统一
_APPROVED = "approved"


def _now_epoch() -> float:
    return datetime.now(timezone.utc).timestamp()


def _norm(decision: Any) -> str:
    return str(decision or "").strip().lower()


def _store(root: Path | str) -> ApprovalStore:
    return ApprovalStore(Path(root) / "governance")


def check_governance(root: Path | str, production_run_id: str, *,
                     action: str = "production_apply") -> dict[str, Any]:
    """Governance Gate 投影（从 domain facts 读, 非第二事实源）。"""
    from ai_factory_os.services.execution.production_run import get_production_run

    policy = POLICIES.get(action)
    if policy is None:
        return {"allowed": False, "reason": f"未知 policy: {action}",
                "policy_id": action, "missing": ["policy"]}
    run = get_production_run(root, production_run_id)
    if run is None:
        return {"allowed": False, "reason": "ProductionRun 不存在",
                "policy_id": action, "missing": ["production_run"]}
    missing: list[str] = []

    # verification: run 已 COMPLETED
    if policy.get("required_verification") and run.get("state") != "COMPLETED":
        missing.append("verification")

    # approval: 绑 run 的 APPROVED（不可 stale; 过期视为不可靠）
    approved = None
    approved_expired = False
    if policy.get("approval_required"):
        recs = [r for r in _store(root).list_all()
                if str(getattr(r, "request_id", "") or "") == production_run_id
                or str(getattr(r, "subject_id", "") or "") == production_run_id]
        for r in recs:
            if _norm(r.decision) == _APPROVED:
                approved = r
        if approved is None:
            missing.append("approval")
        else:
            # 过期检查（新版模型暂无 expires_at, 有则查）
            exp = getattr(approved, "expires_at", None) or ""
            if exp:
                try:
                    ts = datetime.fromisoformat(str(exp).replace("Z", "+00:00")).timestamp()
                    if _now_epoch() >= ts:
                        approved, approved_expired = None, True
                        missing.append("approval_expired")
                except (ValueError, TypeError):
                    missing.append("approval_expired")
    allowed = len(missing) == 0
    return {"allowed": allowed,
            "reason": "" if allowed else f"缺少: {', '.join(missing)}",
            "policy_id": action, "policy": policy,
            "missing": missing,
            "approval": approved.to_dict() if approved is not None else None,
            "approval_expired": approved_expired}


def release(root: Path | str, production_run_id: str, *, released_by: str = "release_engineer",
            approval_id: str = "") -> dict[str, Any]:
    """Release Gate: verification + evaluation + approval + policy 全过才允许。

    返回 {allowed, reason, missing} — 不执行任何 workspace 变更（由调用方经 Lifecycle）。
    """
    from ai_factory_os.services.execution.production_run import get_production_run

    run = get_production_run(root, production_run_id)
    if run is None:
        return {"allowed": False, "reason": "ProductionRun 不存在", "missing": ["production_run"]}
    missing: list[str] = []
    if run.get("state") != "COMPLETED":
        missing.append("verification")
    # evaluation
    try:
        from ai_factory_os.services.execution.production_evaluation import get_evaluation
        ev = get_evaluation(root, production_run_id)
        if ev is None or str(ev.get("status") or "").upper() != "COMPLETED":
            missing.append("evaluation")
    except Exception:  # noqa: BLE001 — 失败安全
        missing.append("evaluation")
    # approval（含 artifact 一致性: Artifact 变了旧 Approval 失效）
    rec = _store(root).get(approval_id) if approval_id else None
    if rec is None or _norm(rec.decision) != _APPROVED:
        missing.append("approval")
    elif set(getattr(rec, "artifact_ids", []) or []) != set(run.get("artifacts", []) or []):
        missing.append("approval_stale")
    allowed = len(missing) == 0
    return {"allowed": allowed,
            "reason": "" if allowed else f"缺少: {', '.join(missing)}",
            "policy_id": "release", "missing": missing}
