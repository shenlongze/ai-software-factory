"""factory-console/release_service.py — S18 Production Release Pipeline.

正式 Release Contract + State Machine + Governance 接线 + 真实 Release Evidence。

- create(run_id): ReleaseRecord (PENDING)
- check(release_id): Gate 投影 (Governance + verification + evaluation + approval)
- execute(release_id): 经 Artifact Lifecycle Apply (真实 workspace) → RELEASED + evidence
- 幂等: RELEASED 重复 execute → already_released; 同 run 重复 create → 返回现有

状态机: PENDING → GATED → APPROVED → RELEASING → RELEASED
                 ↘ BLOCKED / REJECTED / FAILED (terminal)

原则:
- Release ≠ 修改状态; 必须产生真实 evidence (apply result / workspace)
- 复用 S17 Governance Gate (不重造)
- 只经 Artifact Lifecycle 写 workspace (不 bypass)
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .production_run import get_production_run
from .governance_service import check_governance, release as _gate_release

#: 状态机
ST_PENDING = "PENDING"
ST_GATED = "GATED"
ST_APPROVED = "APPROVED"
ST_RELEASING = "RELEASING"
ST_RELEASED = "RELEASED"
ST_BLOCKED = "BLOCKED"
ST_REJECTED = "REJECTED"
ST_FAILED = "FAILED"

TERMINAL = (ST_RELEASED, ST_BLOCKED, ST_REJECTED, ST_FAILED)

TRANSITIONS = {
    ST_PENDING: (ST_GATED, ST_BLOCKED, ST_REJECTED, ST_FAILED),
    ST_GATED: (ST_APPROVED, ST_BLOCKED, ST_REJECTED, ST_FAILED),
    ST_APPROVED: (ST_RELEASING, ST_BLOCKED, ST_REJECTED, ST_FAILED),
    ST_RELEASING: (ST_RELEASED, ST_FAILED),
    ST_RELEASED: (),
    ST_BLOCKED: (),
    ST_REJECTED: (),
    ST_FAILED: (),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _releases_file(root: Path | str) -> Path:
    return Path(root) / "releases" / "releases.json"


def _load(root: Path | str) -> list[dict[str, Any]]:
    try:
        d = json.loads(_releases_file(root).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(root: Path | str, data: list[dict[str, Any]]) -> None:
    p = _releases_file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def _transition(root: Path | str, rel: dict[str, Any], to: str, *, actor: str, note: str) -> dict[str, Any]:
    if to not in TRANSITIONS.get(rel["state"], ()):
        raise ValueError(f"非法 Release 状态转换: {rel['state']} → {to}")
    rel["state"] = to
    rel["history"].append({"from": rel["history"][-1]["to"] if rel["history"] else None,
                           "to": to, "actor": actor, "at": _now_iso(), "note": note})
    # 持久化 (替换同 release_id 记录)
    data = _load(root)
    for i, r in enumerate(data):
        if r["release_id"] == rel["release_id"]:
            data[i] = rel
            break
    else:
        data.append(rel)
    _save(root, data)
    _audit(root, f"RELEASE_{to}", {"release_id": rel["release_id"], "run_id": rel["production_run_id"], "note": note})
    return rel


def create(root: Path | str, production_run_id: str, *, created_by: str = "release_engineer") -> dict[str, Any]:
    """创建 ReleaseRecord (幂等: 已有非 terminal 的返回现有)。"""
    run = get_production_run(root, production_run_id)
    if run is None:
        raise ValueError(f"ProductionRun 不存在: {production_run_id}")
    data = _load(root)
    # 幂等: 同 run 已有 active (非 terminal) release → 返回
    for r in data:
        if r["production_run_id"] == production_run_id and r["state"] not in TERMINAL:
            return r
    rel = {
        "release_id": f"rel-{uuid.uuid4().hex[:10]}",
        "production_run_id": production_run_id,
        "project_id": run.get("project_id") or "",
        "artifact_ids": list(run.get("artifacts", [])),
        "verification_ids": [],
        "evaluation_ids": [],
        "approval_ids": [],
        "state": ST_PENDING,
        "created_at": _now_iso(),
        "started_at": "",
        "completed_at": "",
        "failure_reason": "",
        "history": [{"from": None, "to": ST_PENDING, "actor": created_by, "at": _now_iso(), "note": "created"}],
        "evidence": [],
    }
    data.append(rel)
    _save(root, data)
    _audit(root, "RELEASE_CREATED", {"release_id": rel["release_id"], "run_id": production_run_id})
    return rel


def get_release(root: Path | str, release_id: str) -> dict[str, Any] | None:
    for r in _load(root):
        if r["release_id"] == release_id:
            return r
    return None


def list_releases(root: Path | str, *, production_run_id: str | None = None) -> list[dict[str, Any]]:
    data = _load(root)
    if production_run_id:
        data = [d for d in data if d.get("production_run_id") == production_run_id]
    return data


def check(root: Path | str, release_id: str) -> dict[str, Any]:
    """Gate 投影: Governance + verification + evaluation + approval (只读)。"""
    rel = get_release(root, release_id)
    if rel is None:
        raise ValueError(f"Release 不存在: {release_id}")
    run = get_production_run(root, rel["production_run_id"])
    if run is None:
        return {"allowed": False, "reason": "ProductionRun 不存在", "missing": ["production_run"]}
    gate = check_governance(root, rel["production_run_id"], action="release")
    missing = list(gate.get("missing", []))
    if run.get("state") != "COMPLETED":
        missing.append("verification")
    from .production_evaluation import get_evaluation
    if get_evaluation(root, rel["production_run_id"]) is None:
        missing.append("evaluation")
    allowed = len(missing) == 0
    # 保留 approval (Gate 里找)
    approval = gate.get("approval")
    if approval and "approval" not in missing:
        rel["approval_ids"] = [approval["approval_id"]]
        # 持久化 approval_ids (check 是只读投影, 但 approval binding 是事实)
        data = _load(root)
        for r in data:
            if r["release_id"] == release_id:
                r["approval_ids"] = rel["approval_ids"]
                break
        _save(root, data)
    return {"allowed": allowed, "reason": "" if allowed else f"缺少: {', '.join(missing)}",
            "missing": missing, "approval": approval,
            "policy_id": "release", "release_id": release_id,
            "state": rel["state"]}


def execute(root: Path | str, release_id: str, *, actor: str = "release_engineer") -> dict[str, Any]:
    """执行 Release: Gate 全过 → 经 Artifact Lifecycle Apply → RELEASED + evidence。"""
    rel = get_release(root, release_id)
    if rel is None:
        raise ValueError(f"Release 不存在: {release_id}")
    if rel["state"] == ST_RELEASED:
        return {"release": rel, "already_released": True}
    if rel["state"] in TERMINAL:
        raise ValueError(f"Release 已 terminal: {rel['state']}")
    # Gate
    g = check(root, release_id)
    rel = get_release(root, release_id)  # 重新读取 (check 可能写 approval_ids)
    if rel["state"] == ST_PENDING:
        rel = _transition(root, rel, ST_GATED, actor=actor, note="gate evaluated")
    if not g["allowed"]:
        rel = _transition(root, rel, ST_BLOCKED, actor=actor, note=f"gate blocked: {g['reason']}")
        return {"release": rel, "blocked": True, "reason": g["reason"], "missing": g["missing"]}
    # Apply 经 Artifact Lifecycle
    from .artifact_lifecycle import apply_artifact, get_artifact

    rel = _transition(root, rel, ST_APPROVED, actor=actor, note="gate passed")
    _transition(root, rel, ST_RELEASING, actor=actor, note="release started")
    rel = get_release(root, release_id)
    rel["started_at"] = _now_iso()
    evidence = []
    try:
        # workspace: 从 Artifact payload 或默认 workspace 目录
        from .artifact_lifecycle import apply_artifact, get_artifact, transition_artifact, approve_artifact

        ws = Path(root) / "workspace"
        ws.mkdir(parents=True, exist_ok=True)
        for aid in rel["artifact_ids"]:
            art = get_artifact(root, aid)
            if art is None:
                raise RuntimeError(f"Artifact 不存在: {aid}")
            # 逐级推进 GENERATED→STAGED→REVIEWED (Release 授权) → approve → APPROVED → apply
            chain = {"GENERATED": "STAGED", "STAGED": "REVIEWED"}
            for _ in range(3):
                cur = get_artifact(root, aid).get("state")
                if cur in chain:
                    transition_artifact(root, aid, chain[cur], actor=actor)
                else:
                    break
            if get_artifact(root, aid).get("state") == "REVIEWED":
                approve_artifact(root, aid, approved_by=actor,
                                 note=f"release {release_id} approval")
            # governance approval (Release 授权, 传给 apply 满足 I12)
            gov_approval = None
            if rel.get("approval_ids"):
                from .governance_service import get_approval as _get_appr
                for aid_ in rel["approval_ids"]:
                    ap_ = _get_appr(root, aid_)
                    if ap_ and ap_.get("decision") == "APPROVED":
                        gov_approval = {"approval_id": aid_, "state": "APPROVED",
                                        "decided_by": ap_.get("decided_by")}
                        break
            applied = apply_artifact(root, aid, workspace_dir=ws, approval=gov_approval)
            evidence.append({"artifact_id": aid, "type": "apply", "result": applied,
                             "workspace": str(ws)})
        rel = get_release(root, release_id)
        rel["evidence"] = evidence
        rel["completed_at"] = _now_iso()
        rel = _transition(root, rel, ST_RELEASED, actor=actor, note="release completed")
        return {"release": rel, "already_released": False}
    except Exception as exc:  # noqa: BLE001
        rel = get_release(root, release_id)
        rel["failure_reason"] = str(exc)
        rel = _transition(root, rel, ST_FAILED, actor=actor, note=f"release failed: {exc}")
        return {"release": rel, "failed": True, "error": str(exc)}


def history(root: Path | str, release_id: str) -> list[dict[str, Any]]:
    rel = get_release(root, release_id)
    if rel is None:
        raise ValueError(f"Release 不存在: {release_id}")
    return rel.get("history", [])


def _audit(root: Path | str, event_type: str, payload: dict[str, Any]) -> None:
    try:
        from .audit.audit_event import AuditEvent
        from .audit.audit_store import AuditStore

        store = AuditStore(workspace=None, file=str(Path(root) / "audit" / "audit_events.json"))
        ev = AuditEvent.create(
            event_type,
            trace_id=payload.get("run_id") or payload.get("release_id") or "",
            actor_type="system",
            actor_id=payload.get("note") or "release_service",
            action=f"release.{event_type.lower()}",
            source="release_service",
            decision="allow",
            decision_reason=payload.get("note") or "",
            evidence=[payload],
            result={"ok": True},
            metadata={"release": payload},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass
