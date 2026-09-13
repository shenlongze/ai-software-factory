"""factory-console/recovery_service.py — S28 Production Quality Recovery & Verification Closure.

真实 Verification Failure → S27 Classification → Recovery Policy (bounded)
→ repair_fn (真实 failed artifact + pytest evidence) → re-production → new artifact
→ new verification (新 id) → PASS → RECOVERED; FAIL → retry ≤ max; 超限 → EXHAUSTED;
被阻 → BLOCKED; 证据不足 → 不猜测。

- Recovery Attempt Contract (append-only, attempt-1 FAIL 保留)
- Verification Closure (新 verification_id, 禁复用旧)
- Idempotency + Concurrency (flock) + Restart (状态持久化)
- 只走 Production Kernel (artifact lifecycle + verification), 不改 Production Truth

复用: S12 repair_fn (production_run.execute) + S20 _run_verification + S27 classify_failure + S17 governance
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .production_run import get_production_run
from .experiment_reliability import (
    classify_failure, FC_VERIFICATION, FC_AGENT, FC_GOV, FC_UNKNOWN,
)

#: 单一 Policy 来源 (S20.5 retry_policy 风格)
MAX_ATTEMPTS = 3
REPAIRABLE = (FC_VERIFICATION,)
NON_REPAIRABLE = (FC_AGENT, FC_GOV, FC_UNKNOWN)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "recovery" / f"{name}.json"


def _load(root: Path | str, name: str) -> list[dict[str, Any]]:
    try:
        d = json.loads(_file(root, name).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(root: Path | str, name: str, data: list[dict[str, Any]]) -> None:
    p = _file(root, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def _audit(root: Path | str, event_type: str, payload: dict[str, Any]) -> None:
    try:
        from .audit.audit_event import AuditEvent
        from .audit.audit_store import AuditStore

        store = AuditStore(workspace=None, file=str(Path(root) / "audit" / "audit_events.json"))
        ev = AuditEvent.create(
            event_type,
            trace_id=payload.get("recovery_attempt_id") or payload.get("production_run_id") or "",
            actor_type="system", actor_id="recovery",
            action=f"recovery.{event_type.lower()}",
            source="recovery_service", decision="allow",
            decision_reason=payload.get("note") or "",
            evidence=[payload], result={"ok": True}, metadata={"recovery": payload},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


def _lock(root: Path | str):
    """跨进程 flock + 进程内互斥 (复用 S20.5 教训: 线程本地重入)。"""
    import threading

    _local = threading.local()
    lock_path = Path(root) / "ops" / "recovery" / ".lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    f = open(lock_path, "a+")  # noqa: SIM115
    import fcntl
    if not getattr(_local, "held", False):
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        _local.held = True
        _local.f = f
    else:
        _local.f = f
    return _local


def _unlock(local) -> None:
    import fcntl
    if getattr(local, "held", False):
        fcntl.flock(local.f.fileno(), fcntl.LOCK_UN)
        local.held = False
        try:
            local.f.close()
        except OSError:
            pass


# ------------------------------------------------------------------ Recovery Policy

def recovery_policy(root: Path | str, classification: str) -> dict[str, Any]:
    """Recovery Policy 判定 (bounded; 非 repair 类 → 不自动)。"""
    if classification in REPAIRABLE:
        return {"allowed": True, "reason": f"{classification} 可自动 repair (bounded {MAX_ATTEMPTS})"}
    if classification in NON_REPAIRABLE:
        return {"allowed": False, "reason": f"{classification} 不可自动 repair (需人工/不猜测)"}
    return {"allowed": False, "reason": f"{classification} 无 repair 策略 (直接 FAILED/BLOCKED)"}


# ------------------------------------------------------------------ Recovery Execution

def recover_production_run(root: Path | str, production_run_id: str, *,
                           executor_factory: Callable[[str], Callable[[dict[str, Any]], dict[str, Any]]],
                           repair_fn: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], dict[str, Any]],
                           max_attempts: int = MAX_ATTEMPTS,
                           actor: str = "recovery") -> dict[str, Any]:
    """完整 Recovery 闭环: 分类 → policy → repair → re-production → re-verification。

    真实 Verification Failure → bounded repair → new artifact + new verification → RECOVERED。
    executor_factory: 原节点工厂 (首次 FAIL 触发 repair_fn); repair_fn: 真实修复器。
    """
    from .production_run import execute_production_run
    from .verification import verify_python_syntax, verify_pytest
    from .artifact_lifecycle import get_artifact

    run = get_production_run(root, production_run_id)
    if run is None:
        raise ValueError(f"ProductionRun 不存在: {production_run_id}")
    cls = classify_failure(root, production_run_id)
    policy = recovery_policy(root, cls["classification"])
    # 幂等 (前置): 已有 RECOVERED/EXHAUSTED recovery → 不再重复
    existing = _load(root, "attempts")
    if any(a["production_run_id"] == production_run_id and a["status"] in ("RECOVERED", "EXHAUSTED")
           for a in existing):
        return {"recovery_attempt_id": "dup", "production_run_id": production_run_id,
                "status": "ALREADY_CLOSED", "evidence_refs": [production_run_id],
                "explain": "该 run 已有终态 recovery (幂等)"}
    if not policy["allowed"]:
        attempt = _record_attempt(root, production_run_id, cls, policy=policy,
                                  status="BLOCKED", note=policy["reason"])
        return attempt

    local = _lock(root)
    try:
        last_verification = None
        for attempt_number in range(1, max_attempts + 1):
            # 每个 attempt: 真实 production (executor 触发 FAIL → repair_fn 自动修复) → 新 verification
            done = execute_production_run(
                root, production_run_id, executor_factory=executor_factory,
                artifact_root=str(root), resume=True, max_attempts=1,
                repair_fn=repair_fn)
            run_updated = get_production_run(root, production_run_id)
            # 新 artifact (resume 后最新)
            new_artifact = None
            for aid in run_updated.get("artifacts", []) or []:
                art = get_artifact(root, aid)
                if art is not None:
                    new_artifact = art
            # 真实 verification (workspace 含新 artifact; 新 verification_id)
            ws = Path(root) / "workspace"
            syn = verify_python_syntax(ws)
            test_files = list(ws.glob("test_*.py")) + list(ws.glob("*_test.py"))
            pt = verify_pytest(ws) if test_files else None
            vf_ok = syn.get("status") == "PASS" and (pt is None or pt.get("status") == "PASS")
            verification = {"verification_id": f"ver-{uuid.uuid4().hex[:10]}",
                            "attempt": attempt_number, "syntax": syn, "pytest": pt,
                            "result": "PASS" if vf_ok else "FAIL",
                            "artifact_ref": new_artifact["artifact_id"] if new_artifact else ""}
            last_verification = verification
            if vf_ok:
                attempt = _record_attempt(
                    root, production_run_id, cls, policy=policy, status="RECOVERED",
                    attempt_number=attempt_number, verification=verification,
                    artifact_ref=verification["artifact_ref"],
                    note=f"attempt-{attempt_number} 新 verification PASS → RECOVERED")
                return attempt
            # FAIL → 下一 attempt (bounded)
            _record_attempt(root, production_run_id, cls, policy=policy, status="VERIFICATION_PENDING",
                            attempt_number=attempt_number, verification=verification,
                            note=f"attempt-{attempt_number} verification FAIL, retry")
        # 超限
        attempt = _record_attempt(root, production_run_id, cls, policy=policy, status="EXHAUSTED",
                                  attempt_number=max_attempts, verification=last_verification,
                                  note=f"达到 max_attempts={max_attempts} → EXHAUSTED")
        return attempt
    finally:
        _unlock(local)


def _record_attempt(root: Path | str, production_run_id: str, cls: dict[str, Any], *,
                    policy: dict[str, Any], status: str, attempt_number: int = 1,
                    verification: dict[str, Any] | None = None,
                    artifact_ref: str = "", note: str = "") -> dict[str, Any]:
    attempt = {
        "recovery_attempt_id": f"rec-{uuid.uuid4().hex[:10]}",
        "production_run_id": production_run_id,
        "failure_classification": cls["classification"],
        "classification_confidence": cls["confidence"],
        "policy": policy,
        "attempt_number": attempt_number,
        "status": status,
        "verification": verification,
        "artifact_ref": artifact_ref,
        "evidence_refs": cls["evidence_refs"] + ([verification["verification_id"]] if verification else []),
        "started_at": _now_iso(), "completed_at": _now_iso() if status in ("RECOVERED", "EXHAUSTED", "BLOCKED", "FAILED") else "",
        "note": note,
    }
    _save(root, "attempts", _load(root, "attempts") + [attempt])
    _audit(root, "RECOVERY_ATTEMPT", {"recovery_attempt_id": attempt["recovery_attempt_id"],
                                      "production_run_id": production_run_id, "status": status,
                                      "classification": cls["classification"]})
    return attempt


# ------------------------------------------------------------------ Query

def recovery_attempts(root: Path | str, production_run_id: str) -> list[dict[str, Any]]:
    """该 run 的全部 recovery attempts (append-only, 含失败历史)。"""
    return [a for a in _load(root, "attempts") if a["production_run_id"] == production_run_id]


def recovery_status(root: Path | str, production_run_id: str) -> dict[str, Any]:
    """Recovery 状态 + explain (兼容 S8 analyze 语义: recoverable_state)。"""
    attempts = recovery_attempts(root, production_run_id)
    run = get_production_run(root, production_run_id)
    if not attempts:
        # S8 兼容: 无 recovery 记录 → 按 S8 规则投影
        state = run.get("state") if run else "UNKNOWN"
        if state == "COMPLETED":
            rec_state = "already_completed"
        elif state in ("EXHAUSTED", "BLOCKED"):
            rec_state = "not_recoverable"
        else:
            # PENDING/RUNNING/FAILED → 可重跑 (S8: 崩溃可恢复)
            rec_state = "recoverable"
        return {"production_run_id": production_run_id, "status": "NO_RECOVERY",
                "recoverable_state": rec_state, "recoverable": rec_state == "recoverable",
                "recommended_action": "recover" if rec_state == "recoverable" else "none",
                "attempts": [],
                "explain": "该 run 无 recovery 记录"}
    last = attempts[-1]
    # 终态映射: RECOVERED→already_completed, EXHAUSTED→not_recoverable, 其他→recoverable
    rec_state = {"RECOVERED": "already_completed",
                 "EXHAUSTED": "not_recoverable",
                 "BLOCKED": "not_recoverable"}.get(last["status"], "recoverable")
    return {"production_run_id": production_run_id, "status": last["status"],
            "recoverable_state": rec_state, "recoverable": rec_state == "recoverable",
            "recommended_action": "recover" if rec_state == "recoverable" else "none",
            "attempts": attempts,
            "explain": f"最后 attempt-{last['attempt_number']}: {last['status']} — {last['note']}"}


def recovery_evidence(root: Path | str, recovery_attempt_id: str) -> dict[str, Any]:
    """Attempt 完整 evidence (lineage 可反查)。"""
    for a in _load(root, "attempts"):
        if a["recovery_attempt_id"] == recovery_attempt_id:
            return {"recovery_attempt_id": recovery_attempt_id,
                    "production_run_id": a["production_run_id"],
                    "classification": a["failure_classification"],
                    "evidence_refs": a["evidence_refs"],
                    "verification": a.get("verification"),
                    "artifact_ref": a.get("artifact_ref"),
                    "explain": a["note"]}
    raise ValueError(f"Recovery attempt 不存在: {recovery_attempt_id}")


def recovery_lineage(root: Path | str, production_run_id: str) -> dict[str, Any]:
    """完整 lineage: run → classification → attempts → verifications → outcome。"""
    run = get_production_run(root, production_run_id)
    attempts = recovery_attempts(root, production_run_id)
    return {"production_run_id": production_run_id,
            "run_state": run.get("state") if run else "UNKNOWN",
            "failure_classification": attempts[0]["failure_classification"] if attempts else "",
            "attempts": [{"recovery_attempt_id": a["recovery_attempt_id"],
                          "attempt_number": a["attempt_number"], "status": a["status"],
                          "verification_result": (a.get("verification") or {}).get("result"),
                          "artifact_ref": a.get("artifact_ref"),
                          "evidence_refs": a["evidence_refs"]} for a in attempts],
            "outcome": attempts[-1]["status"] if attempts else "NO_RECOVERY"}
