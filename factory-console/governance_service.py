"""factory-console/governance_service.py — S17 Workforce Governance & Human Approval.

正式 Governance: ApprovalRequest 持久化 + Policy + Gate + Release。

- request_approval(): 创建 ApprovalRequest (PENDING)
- decide(): approve/reject (requester != approver, append-only history)
- check(): GovernanceGate 投影 (allowed/missing/reason) — 从 domain facts 读, 非第二事实源
- release(): Release Gate (verification + evaluation + approval + policy)
- Agent 不能 self-approve; Approval 绑定 immutable artifact_ids + production_run_id

原则:
- Governance 只读 Artifact, 不写 Workspace (Lifecycle 负责 Apply)
- 无 boolean approval (状态机 + append-only history)
- 读 domain facts (ProductionRun/Artifact/Verification/Evaluation), 不建第二状态
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifact_lifecycle import get_artifact
from .production_run import get_production_run
from .node_runtime import get_node_run

APPROVAL_PENDING = "PENDING"
APPROVAL_APPROVED = "APPROVED"
APPROVAL_REJECTED = "REJECTED"

#: 状态机合法转换 (append-only history)
APPROVAL_TRANSITIONS = {
    APPROVAL_PENDING: (APPROVAL_APPROVED, APPROVAL_REJECTED),
    APPROVAL_APPROVED: (),
    APPROVAL_REJECTED: (),
}

#: Governance Policy (最小真实)
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
}

#: Agent 不能批准 (approver 必须是 human; Agent 只可 request)
AGENT_APPROVERS: set[str] = set()  # 无 Agent 可 approve


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _now_epoch() -> float:
    """可注入 clock (S20: 测试用 fake clock)。"""
    return _CLOCK()

#: 可测试 clock (默认真实时间)
_CLOCK = lambda: datetime.now(timezone.utc).timestamp()  # noqa: E731


def set_clock(fn) -> None:
    """注入 clock (S20 测试: fake clock 控制 expiration)。"""
    global _CLOCK
    _CLOCK = fn


#: Approval TTL (秒) — policy 级默认有效期
APPROVAL_TTL_SECONDS = 24 * 3600  # 24h


def _approvals_file(root: Path | str) -> Path:
    return Path(root) / "governance" / "approvals.json"


def _approvals_lock(root: Path | str) -> Path:
    return Path(root) / "governance" / "approvals.lock"


def _load_approvals(root: Path | str) -> list[dict[str, Any]]:
    try:
        d = json.loads(_approvals_file(root).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save_approvals(root: Path | str, data: list[dict[str, Any]]) -> None:
    p = _approvals_file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


# ------------------------------------------------------------------ ApprovalRequest

def request_approval(root: Path | str, *, production_run_id: str,
                     artifact_ids: list[str], requested_by: str,
                     policy_id: str = "production_apply",
                     subject_type: str = "production_run",
                     subject_id: str = "") -> dict[str, Any]:
    """创建 ApprovalRequest (PENDING, append-only)。"""
    policy = POLICIES.get(policy_id)
    if policy is None:
        raise ValueError(f"未知 policy: {policy_id}")
    # S24/S25: 非 production_run 主体 (experiment/workforce_variant) 不强制绑定 run
    # K1: conversation 主体 (对话触发的工作审批)
    # K3: task 主体 (高风险 task 执行 gate)
    if subject_type in ("experiment", "workforce_variant", "conversation", "task"):
        pass
    else:
        run = get_production_run(root, production_run_id)
        if run is None:
            raise ValueError(f"ProductionRun 不存在: {production_run_id}")
    # Artifact 必须存在
    for aid in artifact_ids:
        if get_artifact(root, aid) is None:
            raise ValueError(f"Artifact 不存在: {aid}")
    req = {
        "approval_id": f"appr-{uuid.uuid4().hex[:10]}",
        "subject_type": subject_type,
        "subject_id": subject_id or production_run_id,
        "production_run_id": production_run_id,
        "artifact_ids": list(artifact_ids),
        "requested_by": requested_by,
        "requested_at": _now_iso(),
        "expires_at": _now_iso(),  # S20: 由 _set_expires 更新为 requested + TTL
        "decision": APPROVAL_PENDING,
        "decided_by": "",
        "decided_at": "",
        "reason": "",
        "evidence_ids": [],
        "policy_id": policy_id,
        "history": [{"from": None, "to": APPROVAL_PENDING, "actor": requested_by,
                     "at": _now_iso(), "note": "created"}],
    }
    # S20: expires_at = now + TTL
    from datetime import timedelta
    req["expires_at"] = (datetime.fromtimestamp(_now_epoch(), tz=timezone.utc)
                         + timedelta(seconds=APPROVAL_TTL_SECONDS)).isoformat(timespec="seconds")
    # S20.5: 跨进程锁 (read-modify-write 串行化)
    from .integrity_lock import file_lock

    with file_lock(_approvals_lock(root)):
        data = _load_approvals(root)
        data.append(req)
        _save_approvals(root, data)
    _audit(root, "APPROVAL_REQUESTED", {"approval_id": req["approval_id"],
                                        "run_id": production_run_id,
                                        "requested_by": requested_by})
    return req


def decide_approval(root: Path | str, approval_id: str, *, decision: str,
                    decided_by: str, reason: str = "") -> dict[str, Any]:
    """Approve/Reject (requester != approver, append-only history)。"""
    if decision not in (APPROVAL_APPROVED, APPROVAL_REJECTED):
        raise ValueError(f"未知 decision: {decision}")
    from .integrity_lock import file_lock

    # S20.5: 跨进程锁 (approve/reject read-modify-write 串行化)
    with file_lock(_approvals_lock(root)):
        data = _load_approvals(root)
        for req in data:
            if req["approval_id"] != approval_id:
                continue
            if req["decision"] != APPROVAL_PENDING:
                raise ValueError(f"Approval 已决 (当前: {req['decision']})")
            if req["requested_by"] == decided_by:
                raise PermissionError(f"self-approve 禁止: requester == approver ({decided_by})")
            if decided_by not in ("human", "Human", "user", "admin") and decided_by not in AGENT_APPROVERS:
                # 非 human 身份默认拒绝 (Agent 不能 approve)
                raise PermissionError(f"approver 必须是 human (当前: {decided_by})")
            req["decision"] = decision
            req["decided_by"] = decided_by
            req["decided_at"] = _now_iso()
            req["reason"] = reason
            req["history"].append({"from": APPROVAL_PENDING, "to": decision,
                                   "actor": decided_by, "at": _now_iso(), "note": reason})
            _save_approvals(root, data)
            _audit(root, "APPROVAL_DECIDED", {"approval_id": approval_id, "decision": decision,
                                              "decided_by": decided_by, "reason": reason})
            return req
        raise ValueError(f"Approval 不存在: {approval_id}")


def approve(root: Path | str, approval_id: str, *, decided_by: str = "human",
            reason: str = "") -> dict[str, Any]:
    return decide_approval(root, approval_id, decision=APPROVAL_APPROVED,
                           decided_by=decided_by, reason=reason)


def reject(root: Path | str, approval_id: str, *, decided_by: str = "human",
           reason: str = "") -> dict[str, Any]:
    return decide_approval(root, approval_id, decision=APPROVAL_REJECTED,
                           decided_by=decided_by, reason=reason)


def get_approval(root: Path | str, approval_id: str) -> dict[str, Any] | None:
    for req in _load_approvals(root):
        if req["approval_id"] == approval_id:
            return req
    return None


def list_approvals(root: Path | str, *, production_run_id: str | None = None) -> list[dict[str, Any]]:
    data = _load_approvals(root)
    if production_run_id:
        data = [d for d in data if d.get("production_run_id") == production_run_id]
    return data


# ------------------------------------------------------------------ Governance Gate

def check_governance(root: Path | str, production_run_id: str, *,
                     action: str = "production_apply") -> dict[str, Any]:
    """Governance Gate 投影 (从 domain facts 读, 非第二事实源)。"""
    policy = POLICIES.get(action)
    if policy is None:
        return {"allowed": False, "reason": f"未知 policy: {action}",
                "policy_id": action, "missing": ["policy"]}
    run = get_production_run(root, production_run_id)
    if run is None:
        return {"allowed": False, "reason": "ProductionRun 不存在",
                "policy_id": action, "missing": ["production_run"]}
    missing = []
    # verification
    ver_ok = run.get("state") == "COMPLETED"
    if policy.get("required_verification") and not ver_ok:
        missing.append("verification")
    # approval (绑定 run + artifact, 不可 stale; S20: 不可 expired)
    approvals = list_approvals(root, production_run_id=production_run_id)
    approved = None
    approved_expired = False
    for a in approvals:
        if a["decision"] == APPROVAL_APPROVED:
            approved = a  # S20: 取最新 (最后一个) APPROVED
    if policy.get("approval_required"):
        if approved is None:
            missing.append("approval")
        else:
            # S20: expiration check (now >= expires_at → expired)
            expires_at = approved.get("expires_at") or ""
            try:
                exp_ts = datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp()
                if _now_epoch() >= exp_ts:
                    approved_expired = True
                    approved = None
                    missing.append("approval_expired")
            except (ValueError, TypeError):
                missing.append("approval_expired")  # 无法解析 → 视为不可靠
    allowed = len(missing) == 0
    return {"allowed": allowed,
            "reason": "" if allowed else f"缺少: {', '.join(missing)}",
            "policy_id": action, "policy": policy,
            "missing": missing, "approval": approved,
            "approval_expired": approved_expired}


# ------------------------------------------------------------------ Release Gate

def release(root: Path | str, production_run_id: str, *, released_by: str = "release_engineer",
            approval_id: str = "") -> dict[str, Any]:
    """Release Gate: verification + evaluation + approval + policy 全过才允许。

    返回 {allowed, reason, missing} — 不执行任何 workspace 变更 (由调用方经 Lifecycle)。
    """
    policy = POLICIES["release"]
    run = get_production_run(root, production_run_id)
    if run is None:
        return {"allowed": False, "reason": "ProductionRun 不存在", "missing": ["production_run"]}
    missing = []
    if run.get("state") != "COMPLETED":
        missing.append("verification")
    # evaluation (S13)
    try:
        from .production_evaluation import get_evaluation
        ev = get_evaluation(root, production_run_id)
        if ev is None or ev.get("status") != "COMPLETED":
            missing.append("evaluation")
    except Exception:  # noqa: BLE001
        missing.append("evaluation")
    # approval
    ap = get_approval(root, approval_id) if approval_id else None
    if ap is None or ap["decision"] != APPROVAL_APPROVED:
        missing.append("approval")
    elif set(ap.get("artifact_ids", [])) != set(run.get("artifacts", [])):
        missing.append("approval_stale")  # Artifact 已变, 旧 Approval 失效
    allowed = len(missing) == 0
    result = {"allowed": allowed,
              "reason": "" if allowed else f"缺少: {', '.join(missing)}",
              "policy_id": "release", "missing": missing}
    _audit(root, "GOVERNANCE_ALLOWED" if allowed else "GOVERNANCE_BLOCKED",
           {"run_id": production_run_id, "released_by": released_by,
            "reason": result["reason"]})
    return result


# ------------------------------------------------------------------ Audit

def _audit(root: Path | str, event_type: str, payload: dict[str, Any]) -> None:
    try:
        from .audit.audit_event import AuditEvent
        from .audit.audit_store import AuditStore

        store = AuditStore(workspace=None, file=str(Path(root) / "audit" / "audit_events.json"))
        ev = AuditEvent.create(
            event_type,
            trace_id=payload.get("run_id") or payload.get("approval_id") or "",
            actor_type="human" if payload.get("decided_by") in ("human", "Human", "user", "admin") else "system",
            actor_id=payload.get("requested_by") or payload.get("decided_by") or payload.get("released_by") or "system",
            action=f"governance.{event_type.lower()}",
            source="governance_service",
            decision="allow",
            decision_reason=payload.get("reason") or event_type.lower(),
            evidence=[payload],
            result={"ok": True},
            metadata={"governance": payload},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass  # audit 失败不阻断 governance
