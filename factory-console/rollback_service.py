"""factory-console/rollback_service.py — S19 Release Rollback.

正式 Rollback: 从历史 Release Evidence 恢复到目标 Release (经 Artifact Lifecycle)。

- create(project_id, target_release_id): RollbackRecord (PENDING) + target 验证
- check(rollback_id): Governance + verification + approval (只读投影)
- execute(rollback_id): 经 Artifact Lifecycle apply target release artifacts → ROLLED_BACK + evidence
- 幂等: ROLLED_BACK 重复 execute → no-op
- 历史保留: Release A/B 不变, Rollback R1 是独立事实

状态机: PENDING → GATED → APPROVED → ROLLING_BACK → ROLLED_BACK
               ↘ BLOCKED / REJECTED / FAILED (terminal)

原则:
- 不 git checkout 冒充; 不重新执行 ProductionRun; 只经 Artifact Lifecycle 写 workspace
- Governance 不可绕过 (human approval); Agent 不能自批准
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .production_run import get_production_run
from .release_service import get_release, list_releases
from .governance_service import (
    check_governance, request_approval, approve, reject, get_approval,
    POLICIES,
)

ST_PENDING = "PENDING"
ST_GATED = "GATED"
ST_APPROVED = "APPROVED"
ST_ROLLING_BACK = "ROLLING_BACK"
ST_VERIFYING = "VERIFYING"
ST_ROLLED_BACK = "ROLLED_BACK"
ST_BLOCKED = "BLOCKED"
ST_REJECTED = "REJECTED"
ST_FAILED = "FAILED"

TERMINAL = (ST_ROLLED_BACK, ST_BLOCKED, ST_REJECTED, ST_FAILED)

TRANSITIONS = {
    ST_PENDING: (ST_GATED, ST_BLOCKED, ST_REJECTED, ST_FAILED),
    ST_GATED: (ST_APPROVED, ST_BLOCKED, ST_REJECTED, ST_FAILED),
    ST_APPROVED: (ST_ROLLING_BACK, ST_BLOCKED, ST_REJECTED, ST_FAILED),
    ST_ROLLING_BACK: (ST_VERIFYING, ST_FAILED),  # S20: apply → verifying
    ST_VERIFYING: (ST_ROLLED_BACK, ST_FAILED),   # S20: verify → rolled_back / failed
    ST_ROLLED_BACK: (),
    ST_BLOCKED: (),
    ST_REJECTED: (),
    ST_FAILED: (),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _rollbacks_file(root: Path | str) -> Path:
    return Path(root) / "rollbacks" / "rollbacks.json"


def _rollbacks_lock(root: Path | str) -> Path:
    return Path(root) / "rollbacks" / "rollbacks.lock"


def _load(root: Path | str) -> list[dict[str, Any]]:
    try:
        d = json.loads(_rollbacks_file(root).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(root: Path | str, data: list[dict[str, Any]]) -> None:
    p = _rollbacks_file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def _transition(root: Path | str, rb: dict[str, Any], to: str, *, actor: str, note: str) -> dict[str, Any]:
    from .integrity_lock import file_lock

    with file_lock(_rollbacks_lock(root)):
        if to not in TRANSITIONS.get(rb["state"], ()):
            raise ValueError(f"非法 Rollback 状态转换: {rb['state']} → {to}")
        rb["state"] = to
        rb["history"].append({"from": rb["history"][-1]["to"] if rb["history"] else None,
                              "to": to, "actor": actor, "at": _now_iso(), "note": note})
        data = _load(root)
        for i, r in enumerate(data):
            if r["rollback_id"] == rb["rollback_id"]:
                data[i] = rb
                break
        else:
            data.append(rb)
        _save(root, data)
    _audit(root, f"ROLLBACK_{to}", {"rollback_id": rb["rollback_id"],
                                    "target_release_id": rb["target_release_id"], "note": note})
    return rb


def _audit(root: Path | str, event_type: str, payload: dict[str, Any]) -> None:
    try:
        from .audit.audit_event import AuditEvent
        from .audit.audit_store import AuditStore

        store = AuditStore(workspace=None, file=str(Path(root) / "audit" / "audit_events.json"))
        ev = AuditEvent.create(
            event_type,
            trace_id=payload.get("rollback_id") or "",
            actor_type="system",
            actor_id=payload.get("note") or "rollback_service",
            action=f"rollback.{event_type.lower()}",
            source="rollback_service",
            decision="allow",
            decision_reason=payload.get("note") or "",
            evidence=[payload],
            result={"ok": True},
            metadata={"rollback": payload},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


def _validate_target(root: Path | str, target_release_id: str) -> dict[str, Any]:
    """Target Release 验证: 存在 + RELEASED + 有 evidence。"""
    rel = get_release(root, target_release_id)
    if rel is None:
        raise ValueError(f"Target Release 不存在: {target_release_id}")
    if rel["state"] != "RELEASED":
        raise ValueError(f"Target Release 未 RELEASED (当前: {rel['state']})")
    if not rel.get("evidence"):
        raise ValueError("Target Release 无 evidence, 不可作为 rollback 目标")
    return rel


def create(root: Path | str, target_release_id: str, *, created_by: str = "release_engineer",
           reason: str = "") -> dict[str, Any]:
    """创建 Rollback (幂等: 已有非 terminal 的返回现有)。"""
    target = _validate_target(root, target_release_id)
    from .integrity_lock import file_lock

    # S20.5: 跨进程锁 (幂等检查 + append 串行化)
    with file_lock(_rollbacks_lock(root)):
        data = _load(root)
        for r in data:
            if r["target_release_id"] == target_release_id and r["state"] not in TERMINAL:
                return r
        rb = {
            "rollback_id": f"rb-{uuid.uuid4().hex[:10]}",
            "project_id": target.get("project_id") or "",
            "target_release_id": target_release_id,
            "from_release_id": "",
            "artifact_ids": list(target.get("artifact_ids", [])),
            "verification_ids": [],
            "approval_ids": [],
            "state": ST_PENDING,
            "reason": reason,
            "evidence": [],
            "verification_attempts": [],
            "history": [{"from": None, "to": ST_PENDING, "actor": created_by,
                         "at": _now_iso(), "note": "created"}],
            "created_at": _now_iso(),
            "completed_at": "",
            "failure_reason": "",
        }
        data.append(rb)
        _save(root, data)
    _audit(root, "ROLLBACK_CREATED", {"rollback_id": rb["rollback_id"],
                                      "target_release_id": target_release_id})
    return rb


def get_rollback(root: Path | str, rollback_id: str) -> dict[str, Any] | None:
    for r in _load(root):
        if r["rollback_id"] == rollback_id:
            return r
    return None


def list_rollbacks(root: Path | str) -> list[dict[str, Any]]:
    return _load(root)


def check(root: Path | str, rollback_id: str) -> dict[str, Any]:
    """Rollback Gate 投影 (Governance + target 有效性)。"""
    rb = get_rollback(root, rollback_id)
    if rb is None:
        raise ValueError(f"Rollback 不存在: {rollback_id}")
    missing = []
    # target release 有效性
    try:
        target = _validate_target(root, rb["target_release_id"])
        target_run = get_production_run(root, target["production_run_id"])
        if target_run is None or target_run.get("state") != "COMPLETED":
            missing.append("target_verification")
    except ValueError as exc:
        return {"allowed": False, "reason": str(exc), "missing": ["target_release"],
                "rollback_id": rollback_id, "state": rb["state"]}
    # governance (release policy: human approval)
    gate = check_governance(root, target["production_run_id"], action="release")
    missing.extend(gate.get("missing", []))
    allowed = len(missing) == 0
    approval = gate.get("approval")
    if approval and "approval" not in missing:
        rb["approval_ids"] = [approval["approval_id"]]
        data = _load(root)
        for r in data:
            if r["rollback_id"] == rollback_id:
                r["approval_ids"] = rb["approval_ids"]
                break
        _save(root, data)
    return {"allowed": allowed, "reason": "" if allowed else f"缺少: {', '.join(missing)}",
            "missing": missing, "approval": approval, "rollback_id": rollback_id,
            "state": rb["state"], "policy_id": "rollback"}


def execute(root: Path | str, rollback_id: str, *, actor: str = "release_engineer") -> dict[str, Any]:
    """执行 Rollback: Gate 全过 → 经 Artifact Lifecycle apply target artifacts → ROLLED_BACK。"""
    rb = get_rollback(root, rollback_id)
    if rb is None:
        raise ValueError(f"Rollback 不存在: {rollback_id}")
    if rb["state"] == ST_ROLLED_BACK:
        return {"rollback": rb, "already_rolled_back": True}
    if rb["state"] in TERMINAL:
        raise ValueError(f"Rollback 已 terminal: {rb['state']}")
    g = check(root, rollback_id)
    rb = get_rollback(root, rollback_id)
    if rb["state"] == ST_PENDING:
        rb = _transition(root, rb, ST_GATED, actor=actor, note="gate evaluated")
    if not g["allowed"]:
        rb = _transition(root, rb, ST_BLOCKED, actor=actor, note=f"gate blocked: {g['reason']}")
        return {"rollback": rb, "blocked": True, "reason": g["reason"], "missing": g["missing"]}
    # from_release: 当前 workspace 的 release (最后一个非 rollback 的 release)
    from_rel = ""
    rels = list_releases(root)
    for r in reversed(rels):
        if r["release_id"] != rb["target_release_id"] and r["state"] == "RELEASED":
            from_rel = r["release_id"]
            break
    rb = get_rollback(root, rollback_id)
    rb["from_release_id"] = from_rel
    rb = _transition(root, rb, ST_APPROVED, actor=actor, note="gate passed")
    rb = _transition(root, rb, ST_ROLLING_BACK, actor=actor, note="rollback started")
    rb = get_rollback(root, rollback_id)
    evidence = []
    try:
        from .artifact_lifecycle import (
            apply_artifact, get_artifact, transition_artifact, approve_artifact,
            create_artifact,
        )

        ws = Path(root) / "workspace"
        ws.mkdir(parents=True, exist_ok=True)
        for aid in rb["artifact_ids"]:
            art = get_artifact(root, aid)
            if art is None:
                raise RuntimeError(f"Artifact 不存在: {aid}")
            if art.get("state") == "APPLIED":
                # Rollback Artifact: 复制 target patch 到新 artifact (走完整 lifecycle)
                payload = art.get("payload") or {}
                new_art = create_artifact(
                    root, artifact_type=art.get("artifact_type", "code_change"),
                    payload=payload,
                    patch_text=art.get("patch_text") or "",
                    producer=f"rollback:{rollback_id}",
                )
                aid = new_art["artifact_id"]
                art = new_art
            # 逐级推进到 APPROVED (rollback 授权)
            chain = {"GENERATED": "STAGED", "STAGED": "REVIEWED"}
            for _ in range(3):
                cur = get_artifact(root, aid).get("state")
                if cur in chain:
                    transition_artifact(root, aid, chain[cur], actor=actor)
                else:
                    break
            if get_artifact(root, aid).get("state") == "REVIEWED":
                approve_artifact(root, aid, approved_by=actor,
                                 note=f"rollback {rollback_id} approval")
            # Rollback: 若 target patch 的新建文件已存在 (被后续 Release 覆盖), 先移除 → 恢复 target 状态
            import re as _re
            patch_t = art.get("patch_text") or ""
            for m in _re.finditer(r"^diff --git a/(\S+) b/(\S+)", patch_t, _re.M):
                tfile = m.group(2)
                tpath = ws / tfile
                if tpath.exists() and (ws / tfile).is_file():
                    tpath.unlink()
                    evidence.append({"artifact_id": aid, "type": "rollback_remove",
                                     "file": tfile, "workspace": str(ws)})
            gov_approval = None
            if rb.get("approval_ids"):
                for aid_ in rb["approval_ids"]:
                    ap_ = get_approval(root, aid_)
                    if ap_ and ap_.get("decision") == "APPROVED":
                        gov_approval = {"approval_id": aid_, "state": "APPROVED",
                                        "decided_by": ap_.get("decided_by")}
                        break
            applied = apply_artifact(root, aid, workspace_dir=ws, approval=gov_approval)
            evidence.append({"artifact_id": aid, "type": "rollback_apply",
                             "result": applied, "workspace": str(ws)})
        # S21: 完整 workspace 恢复 — 删除比 target 更新的 RELEASED release 引入的文件
        def _patch_files(art: dict[str, Any]) -> list[str]:
            import re as _re
            return [m.group(2) for m in
                    _re.finditer(r"^diff --git a/(\S+) b/(\S+)", art.get("patch_text") or "", _re.M)]

        target_files = {f for a in rb["artifact_ids"]
                        for f in _patch_files(get_artifact(root, a) or {})}
        newer_files: list[str] = []
        for rel_ in list_releases(root):
            if rel_["release_id"] == rb["target_release_id"] or rel_.get("state") != "RELEASED":
                continue
            for aid_ in rel_.get("artifact_ids", []):
                art_ = get_artifact(root, aid_)
                if art_ is None:
                    continue
                for f in _patch_files(art_):
                    fpath = ws / f
                    if fpath.exists() and fpath.is_file() and f not in target_files:
                        fpath.unlink()
                        newer_files.append(f)
        if newer_files:
            evidence.append({"type": "rollback_cleanup", "files": newer_files, "workspace": str(ws)})
        rb = get_rollback(root, rollback_id)
        rb["evidence"] = evidence
        # S20.5: Rollback Verification — apply 后真实验证 (复用 release pipeline)
        from .release_service import _run_verification as _run_rel_verification

        rb = _transition(root, rb, "VERIFYING", actor=actor, note="rollback verification started")
        try:
            checks, all_pass, failure_reason, attempts = _run_rel_verification(root, ws, rb)
            rb = get_rollback(root, rollback_id)
            rb["verification_attempts"] = attempts
            rb["verification_checks"] = checks
            if not all_pass:
                rb["failure_reason"] = failure_reason or "rollback verification failed"
                rb = _transition(root, rb, "FAILED", actor=actor, note="rollback verification failed")
                return {"rollback": rb, "failed": True, "error": rb["failure_reason"]}
            _audit(root, "ROLLBACK_VERIFICATION_COMPLETED",
                   {"rollback_id": rollback_id, "checks": checks})
        except Exception as exc:  # noqa: BLE001
            rb = get_rollback(root, rollback_id)
            rb["failure_reason"] = f"verification error: {exc}"
            rb = _transition(root, rb, "FAILED", actor=actor, note=f"verification error: {exc}")
            return {"rollback": rb, "failed": True, "error": str(exc)}
        rb = get_rollback(root, rollback_id)
        rb["verification_attempts"] = attempts
        rb["verification_checks"] = checks
        rb["completed_at"] = _now_iso()
        rb = _transition(root, rb, "ROLLED_BACK", actor=actor, note="rollback completed (verified)")
        return {"rollback": rb, "already_rolled_back": False}
    except Exception as exc:  # noqa: BLE001
        rb = get_rollback(root, rollback_id)
        rb["failure_reason"] = str(exc)
        rb = _transition(root, rb, ST_FAILED, actor=actor, note=f"rollback failed: {exc}")
        return {"rollback": rb, "failed": True, "error": str(exc)}


def history(root: Path | str, rollback_id: str) -> list[dict[str, Any]]:
    rb = get_rollback(root, rollback_id)
    if rb is None:
        raise ValueError(f"Rollback 不存在: {rollback_id}")
    return rb.get("history", [])


# ------------------------------------------------------------------ S20.5: VERIFYING Recovery

def recover_verifying(root: Path | str, rollback_id: str, *, actor: str = "recovery") -> dict[str, Any]:
    """Rollback VERIFYING 中断恢复 (S20.5 GAP-2)。

    注意: 不在外层持锁 (内部 _transition 已逐个加锁, 避免 flock 重入死锁)。
    """
    rb = get_rollback(root, rollback_id)
    if rb is None:
        raise ValueError(f"Rollback 不存在: {rollback_id}")
    if rb["state"] != "VERIFYING":
        return {"rollback": rb, "recovered": False,
                "reason": f"state={rb['state']} (非 VERIFYING, 无需恢复)"}
    attempts = rb.get("verification_attempts", [])
    for a in reversed(attempts):
        if a.get("result") == "PASS":
            rb["completed_at"] = _now_iso()
            rb = _transition(root, rb, "ROLLED_BACK", actor=actor,
                             note="recovered: verification PASS evidence found")
            return {"rollback": rb, "recovered": True, "reason": "verification PASS evidence"}
    # 无 PASS evidence → 重新 verification
    from .release_service import _run_verification as _run_rel_verification

    ws = Path(root) / "workspace"
    checks, all_pass, failure_reason, attempts = _run_rel_verification(root, ws, rb)
    rb = get_rollback(root, rollback_id)
    rb["verification_attempts"] = attempts
    rb["verification_checks"] = checks
    if not all_pass:
        rb["failure_reason"] = failure_reason or "rollback verification failed"
        rb = _transition(root, rb, "FAILED", actor=actor,
                         note="recovered: re-verification failed (真实失败, 不伪造)")
        return {"rollback": rb, "recovered": False, "reason": "re-verification failed"}
    rb["completed_at"] = _now_iso()
    rb = _transition(root, rb, "ROLLED_BACK", actor=actor,
                     note="recovered: re-verification PASS")
    return {"rollback": rb, "recovered": True, "reason": "re-verification PASS"}
