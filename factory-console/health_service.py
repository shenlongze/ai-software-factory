"""factory-console/health_service.py — S21 Production Health Monitor & Automatic Rollback.

HealthMonitor(观察) → HealthCheck(事实) → HealthPolicy(判定) → HealthIncident(记录)
→ Recovery(经 rollback_service 复用 Governance/Lifecycle/Verification)

原则:
- HealthMonitor 只观察, 不写 workspace, 不绕过 rollback_service
- 确定性 Policy (无 LLM 判断)
- 复用 verification.verify_pytest / verify_python_syntax (真实 subprocess)
- 复用 rollback_service (idempotency + Governance + Lifecycle)
- 复用 integrity_lock (并发安全)
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .release_service import get_release, list_releases
from .production_run import get_production_run

#: Health 状态
HC_PENDING = "PENDING"
HC_RUNNING = "RUNNING"
HC_PASSED = "PASSED"
HC_FAILED = "FAILED"

#: Health Result
HR_HEALTHY = "HEALTHY"
HR_DEGRADED = "DEGRADED"
HR_UNHEALTHY = "UNHEALTHY"
HR_UNKNOWN = "UNKNOWN"

#: Incident 状态
INC_OPEN = "OPEN"
INC_ACKNOWLEDGED = "ACKNOWLEDGED"
INC_RECOVERING = "RECOVERING"
INC_RESOLVED = "RESOLVED"
INC_FAILED = "FAILED"

#: 严重度
SEV_LOW = "low"
SEV_MED = "medium"
SEV_HIGH = "high"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _checks_file(root: Path | str) -> Path:
    return Path(root) / "health" / "checks.json"


def _incidents_file(root: Path | str) -> Path:
    return Path(root) / "health" / "incidents.json"


def _lock_path(root: Path | str, name: str) -> Path:
    return Path(root) / "health" / f"{name}.lock"


def _load(root: Path | str, p: Path) -> list[dict[str, Any]]:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(root: Path | str, p: Path, data: list[dict[str, Any]]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    import os
    import tempfile
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
            trace_id=payload.get("incident_id") or payload.get("release_id") or "",
            actor_type="system",
            actor_id="health_service",
            action=f"health.{event_type.lower()}",
            source="health_service",
            decision="allow",
            decision_reason=payload.get("note") or "",
            evidence=[payload],
            result={"ok": True},
            metadata={"health": payload},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ Health Check

def _run_checks(root: Path | str, release: dict[str, Any]) -> list[dict[str, Any]]:
    """确定性 health checks (真实 subprocess, 无 LLM)。"""
    from .verification import verify_pytest, verify_python_syntax
    from .retry_policy import is_retryable_verification

    ws = Path(root) / "workspace"
    checks: list[dict[str, Any]] = []
    # Check 1: Release state
    checks.append({"check_type": "release_state", "status": HC_PASSED if release["state"] == "RELEASED" else HC_FAILED,
                   "detail": f"state={release['state']}"})
    # Check 2: Verification state (latest release verification_attempts PASS)
    attempts = release.get("verification_attempts", [])
    ver_ok = any(a.get("result") == "PASS" for a in attempts) if attempts else bool(release.get("verification_checks"))
    checks.append({"check_type": "verification_state",
                   "status": HC_PASSED if ver_ok else HC_FAILED,
                   "detail": f"attempts={len(attempts)}"})
    # Check 3: Workspace integrity (release artifacts applied → workspace 文件存在)
    art_ok = True
    for aid in release.get("artifact_ids", []):
        from .artifact_lifecycle import get_artifact
        art = get_artifact(root, aid)
        if art is None:
            art_ok = False
            break
    checks.append({"check_type": "artifact_integrity",
                   "status": HC_PASSED if art_ok else HC_FAILED,
                   "detail": f"artifacts={len(release.get('artifact_ids', []))}"})
    # Check 4: Workspace syntax integrity (真实 subprocess — 坏语法 = UNHEALTHY)
    from .verification import verify_python_syntax as _syn
    syn = _syn(ws)
    checks.append({"check_type": "workspace_syntax",
                   "status": HC_PASSED if syn.get("status") == "PASS" else HC_FAILED,
                   "exit_code": syn.get("exit_code"), "stdout": syn.get("stdout", ""),
                   "stderr": syn.get("stderr", ""), "detail": f"exit={syn.get('exit_code')}"})
    # Check 5: Test health (真实 pytest subprocess, workspace 有 test 才跑)
    test_files = list(ws.glob("test_*.py")) + list(ws.glob("*_test.py"))
    if test_files:
        pt = verify_pytest(ws)
        retryable = is_retryable_verification(pt)
        checks.append({"check_type": "test_health",
                       "status": HC_PASSED if pt.get("status") == "PASS" else HC_FAILED,
                       "exit_code": pt.get("exit_code"), "stdout": pt.get("stdout", ""),
                       "stderr": pt.get("stderr", ""), "duration": pt.get("duration", 0),
                       "retryable": retryable, "detail": f"exit={pt.get('exit_code')}"})
    else:
        checks.append({"check_type": "test_health", "status": HC_PASSED, "detail": "no tests"})
    return checks


def health_check(root: Path | str, release_id: str, *, actor: str = "health_monitor") -> dict[str, Any]:
    """执行 Health Check (确定性, 真实 subprocess)。"""
    from .integrity_lock import file_lock

    release = get_release(root, release_id)
    if release is None:
        raise ValueError(f"Release 不存在: {release_id}")
    hc = {
        "health_check_id": f"hchk-{uuid.uuid4().hex[:10]}",
        "release_id": release_id,
        "run_id": release.get("production_run_id", ""),
        "status": HC_RUNNING,
        "result": HR_UNKNOWN,
        "started_at": _now_iso(),
        "completed_at": "",
        "checks": [],
        "evidence": [],
        "history": [{"from": HC_PENDING, "to": HC_RUNNING, "actor": actor, "at": _now_iso(), "note": "started"}],
    }
    _audit(root, "HEALTH_CHECK_STARTED", {"release_id": release_id, "health_check_id": hc["health_check_id"]})
    checks = _run_checks(root, release)
    hc["checks"] = checks
    hc["completed_at"] = _now_iso()
    failed = [c for c in checks if c["status"] == HC_FAILED]
    retryable_fail = [c for c in failed if c.get("retryable")]
    if not failed:
        hc["result"] = HR_HEALTHY
        hc["status"] = HC_PASSED
    elif len(failed) == len(retryable_fail) and failed:
        hc["result"] = HR_DEGRADED
        hc["status"] = HC_FAILED
    else:
        hc["result"] = HR_UNHEALTHY
        hc["status"] = HC_FAILED
    hc["evidence"] = [{"check_id": c["check_type"], "status": c["status"], "detail": c.get("detail", "")}
                      for c in checks]
    hc["history"].append({"from": HC_RUNNING, "to": hc["status"], "actor": actor,
                          "at": _now_iso(), "note": f"result={hc['result']}"})
    with file_lock(_lock_path(root, "checks")):
        data = _load(root, _checks_file(root))
        data.append(hc)
        _save(root, _checks_file(root), data)
    _audit(root, "HEALTH_CHECK_COMPLETED",
           {"release_id": release_id, "health_check_id": hc["health_check_id"], "result": hc["result"]})
    if hc["result"] == HR_DEGRADED:
        _audit(root, "HEALTH_DEGRADED", {"release_id": release_id, "health_check_id": hc["health_check_id"]})
    elif hc["result"] == HR_UNHEALTHY:
        _audit(root, "HEALTH_FAILED", {"release_id": release_id, "health_check_id": hc["health_check_id"]})
    return hc


def get_health_check(root: Path | str, health_check_id: str) -> dict[str, Any] | None:
    for c in _load(root, _checks_file(root)):
        if c["health_check_id"] == health_check_id:
            return c
    return None


def list_health_checks(root: Path | str, *, release_id: str | None = None) -> list[dict[str, Any]]:
    data = _load(root, _checks_file(root))
    if release_id:
        return [c for c in data if c.get("release_id") == release_id]
    return data


def run_health(root: Path | str, run_id: str) -> dict[str, Any]:
    """对 run 的最近 RELEASED release 执行 health check。"""
    rels = list_releases(root, production_run_id=run_id)
    released = [r for r in rels if r["state"] == "RELEASED"]
    if not released:
        raise ValueError(f"Run {run_id} 无 RELEASED release")
    latest = max(released, key=lambda r: r.get("created_at", ""))
    return health_check(root, latest["release_id"])


# ------------------------------------------------------------------ Incident

def create_incident(root: Path | str, health_check: dict[str, Any], *,
                    actor: str = "health_monitor") -> dict[str, Any]:
    """创建 Incident (幂等: 同 release 已有 active incident → 返回现有)。"""
    from .integrity_lock import file_lock

    release_id = health_check["release_id"]
    with file_lock(_lock_path(root, "incidents")):
        data = _load(root, _incidents_file(root))
        # 幂等: 同 release 已有 active (非 terminal) incident → 返回
        for inc in data:
            if inc.get("release_id") == release_id and inc["status"] in (INC_OPEN, INC_ACKNOWLEDGED, INC_RECOVERING):
                return inc
        failed_checks = [c.get("check_type") for c in health_check.get("checks", [])
                         if c.get("status") == HC_FAILED]
        inc = {
            "incident_id": f"inc-{uuid.uuid4().hex[:10]}",
            "release_id": release_id,
            "run_id": health_check.get("run_id", ""),
            "health_check_ids": [health_check["health_check_id"]],
            "severity": SEV_HIGH if health_check["result"] == HR_UNHEALTHY else SEV_MED,
            "health_result": health_check["result"],
            "failed_checks": failed_checks,
            "recommended_action": "rollback" if health_check["result"] == HR_UNHEALTHY else "retry",
            "status": INC_OPEN,
            "rollback_id": "",
            "evidence": [{"health_check_id": health_check["health_check_id"],
                          "result": health_check["result"], "failed_checks": failed_checks}],
            "history": [{"from": None, "to": INC_OPEN, "actor": actor, "at": _now_iso(),
                         "note": f"created from {health_check['health_check_id']}"}],
            "created_at": _now_iso(),
            "resolved_at": "",
            "failure_reason": "",
        }
        data.append(inc)
        _save(root, _incidents_file(root), data)
    _audit(root, "HEALTH_INCIDENT_CREATED", {"incident_id": inc["incident_id"],
                                             "release_id": release_id,
                                             "health_check_id": health_check["health_check_id"],
                                             "result": health_check["result"]})
    return inc


def _transition_incident(root: Path | str, inc: dict[str, Any], to: str, *, actor: str, note: str) -> dict[str, Any]:
    from .integrity_lock import file_lock

    with file_lock(_lock_path(root, "incidents")):
        inc["status"] = to
        inc["history"].append({"from": inc["history"][-1]["to"] if inc["history"] else None,
                               "to": to, "actor": actor, "at": _now_iso(), "note": note})
        data = _load(root, _incidents_file(root))
        for i, x in enumerate(data):
            if x["incident_id"] == inc["incident_id"]:
                data[i] = inc
                break
        _save(root, _incidents_file(root), data)
    return inc


def get_incident(root: Path | str, incident_id: str) -> dict[str, Any] | None:
    for inc in _load(root, _incidents_file(root)):
        if inc["incident_id"] == incident_id:
            return inc
    return None


def list_incidents(root: Path | str, *, status: str | None = None) -> list[dict[str, Any]]:
    data = _load(root, _incidents_file(root))
    if status:
        return [x for x in data if x.get("status") == status]
    return data


# ------------------------------------------------------------------ Automatic Recovery

def recover(root: Path | str, incident_id: str, *, actor: str = "health_monitor") -> dict[str, Any]:
    """Automatic Recovery: Incident → rollback_service (复用 Governance/Lifecycle/Verification)。

    - UNHEALTHY → rollback (经 rollback_service)
    - rollback 完成 + verification PASS → RESOLVED
    - rollback 失败 → incident FAILED (真实失败, 不伪造)
    """
    from .rollback_service import create as rb_create, execute as rb_execute

    inc = get_incident(root, incident_id)
    if inc is None:
        raise ValueError(f"Incident 不存在: {incident_id}")
    if inc["status"] == INC_RESOLVED:
        return {"incident": inc, "already_resolved": True}
    if inc["status"] == INC_FAILED:
        raise ValueError(f"Incident 已 FAILED: {incident_id}")
    if inc["status"] == INC_RECOVERING:
        return {"incident": inc, "already_recovering": True}
    inc = _transition_incident(root, inc, INC_RECOVERING, actor=actor, note="recovery started")
    # 找到比当前 release 更早的 RELEASED release 作为 rollback 目标 (同 project, 不限于同 run)
    rels = list_releases(root)
    released = [r for r in rels if r["state"] == "RELEASED"]
    released.sort(key=lambda r: r.get("created_at", ""))
    target = None
    for r in reversed(released):
        if r["release_id"] != inc["release_id"]:
            target = r
            break
    _audit(root, "HEALTH_RECOVERY_STARTED", {"incident_id": incident_id,
                                             "release_id": inc["release_id"],
                                             "target_release_id": target["release_id"] if target else ""})
    if target is None:
        inc = get_incident(root, incident_id)
        inc["failure_reason"] = "无更早 RELEASED release 可回滚"
        inc = _transition_incident(root, inc, INC_FAILED, actor=actor, note="no rollback target")
        _audit(root, "HEALTH_RECOVERY_FAILED", {"incident_id": incident_id, "reason": "no rollback target"})
        return {"incident": inc, "failed": True, "error": "no rollback target"}
    try:
        rb = rb_create(root, target["release_id"], created_by=actor,
                       reason=f"auto-recovery for incident {incident_id}")
        r = rb_execute(root, rb["rollback_id"], actor=actor)
        inc = get_incident(root, incident_id)
        inc["rollback_id"] = rb["rollback_id"]
        if r.get("failed"):
            inc["failure_reason"] = r.get("error", "rollback failed")
            inc = _transition_incident(root, inc, INC_FAILED, actor=actor, note="rollback failed")
            _audit(root, "HEALTH_RECOVERY_FAILED", {"incident_id": incident_id,
                                                    "rollback_id": rb["rollback_id"],
                                                    "error": r.get("error", "")})
            return {"incident": inc, "failed": True, "error": r.get("error", "")}
        if r["rollback"]["state"] == "ROLLED_BACK":
            inc["resolved_at"] = _now_iso()
            inc = _transition_incident(root, inc, INC_RESOLVED, actor=actor,
                                       note=f"recovered via rollback {rb['rollback_id']}")
            _audit(root, "HEALTH_RECOVERY_COMPLETED", {"incident_id": incident_id,
                                                       "rollback_id": rb["rollback_id"]})
            return {"incident": inc, "resolved": True, "rollback": r["rollback"]}
        return {"incident": inc, "status": inc["status"]}
    except Exception as exc:  # noqa: BLE001
        inc = get_incident(root, incident_id)
        inc["failure_reason"] = str(exc)
        inc = _transition_incident(root, inc, INC_FAILED, actor=actor, note=f"recovery error: {exc}")
        _audit(root, "HEALTH_RECOVERY_FAILED", {"incident_id": incident_id, "error": str(exc)})
        return {"incident": inc, "failed": True, "error": str(exc)}
