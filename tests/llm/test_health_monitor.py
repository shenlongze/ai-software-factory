"""S21: Production Health Monitor & Automatic Rollback。

覆盖:
- Health Check (确定性, 真实 subprocess)
- Health Result (HEALTHY/UNHEALTHY)
- Health Incident (OPEN/RECOVERING/RESOLVED/FAILED + append-only + 幂等)
- Automatic Recovery (Incident → rollback_service → RESOLVED)
- Rollback Failure → Incident FAILED (不伪造)
- Idempotency (重复 recover no-op)
- Concurrency (并发 health check 安全)
- CLI / API
- Real E2E: 退化检测 → incident → auto-rollback → 恢复
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.production_run import (  # noqa: E402
    register_workflow, create_production_run, execute_production_run, get_production_run,
)
from factory_console.production_evaluation import evaluate  # noqa: E402
from factory_console.governance_service import (  # noqa: E402
    request_approval, approve,
)
from factory_console.release_service import (  # noqa: E402
    create as rel_create, execute as rel_execute, get_release,
)
from factory_console.health_service import (  # noqa: E402
    health_check, create_incident, recover, get_incident, list_incidents,
)


def _patch(fname: str, body: str = "def x():\n    return 1\n") -> str:
    lines = "".join(f"+{ln}\n" for ln in body.rstrip("\n").split("\n"))
    return f"diff --git a/{fname} b/{fname}\n--- /dev/null\n+++ b/{fname}\n@@ -0,0 +1,{len(body.rstrip(chr(10)).split(chr(10)))} @@\n{lines}"


def _make_release(tmp_path, fname: str = "a.py", body: str = "def x():\n    return 1\n") -> str:
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=[
        {"node_id": "a", "name": "A", "type": "engineering", "executor_name": "a"}])
    run = create_production_run(str(tmp_path), "wf-1")
    patch = _patch(fname, body)

    def factory(node_id):
        def fn(input_data):
            return {"ok": True, "output": {"code": "x"}, "patch_text": patch,
                    "artifact_type": "code_change", "verification": {"result": "PASS"}}
        return fn
    execute_production_run(str(tmp_path), run["run_id"], executor_factory=factory,
                           artifact_root=str(tmp_path))
    run2 = get_production_run(str(tmp_path), run["run_id"])
    evaluate(str(tmp_path), run["run_id"])
    arts = list(run2.get("artifacts", []))
    a = request_approval(str(tmp_path), production_run_id=run["run_id"],
                         artifact_ids=arts, requested_by="dev-agent")
    approve(str(tmp_path), a["approval_id"], decided_by="human")
    rel = rel_create(str(tmp_path), run["run_id"])
    rel_execute(str(tmp_path), rel["release_id"])
    return get_release(str(tmp_path), rel["release_id"])["release_id"]


# --- E2E-1: Healthy ---

def test_healthy_release(tmp_path):
    """Release → Health Check → HEALTHY。"""
    rel_id = _make_release(tmp_path)
    hc = health_check(str(tmp_path), rel_id)
    assert hc["result"] == "HEALTHY"
    assert hc["status"] == "PASSED"
    assert all(c["status"] == "PASSED" for c in hc["checks"])


# --- E2E-2: Health Failure → Incident ---

def test_health_failure_incident(tmp_path):
    """Release → 退化 (坏语法) → Health FAIL → Incident OPEN。"""
    rel_id = _make_release(tmp_path)
    ws = Path(tmp_path) / "workspace"
    (ws / "a.py").write_text("def broken(:\n    return\n", encoding="utf-8")
    hc = health_check(str(tmp_path), rel_id)
    assert hc["result"] == "UNHEALTHY"
    assert any(c["check_type"] == "workspace_syntax" and c["status"] == "FAILED"
               for c in hc["checks"])
    inc = create_incident(str(tmp_path), hc)
    assert inc["status"] == "OPEN"
    assert inc["recommended_action"] == "rollback"
    assert inc["health_check_ids"] == [hc["health_check_id"]]
    # 幂等: 同 release 不重复创建
    inc2 = create_incident(str(tmp_path), hc)
    assert inc2["incident_id"] == inc["incident_id"]


# --- E2E-3: Automatic Recovery ---

def test_auto_recovery(tmp_path):
    """退化 → Incident → Policy → rollback → ROLLED_BACK → RESOLVED + workspace 恢复。"""
    rel_a = _make_release(tmp_path, "a.py", "def a():\n    return 1\n")
    time.sleep(1.1)
    rel_b = _make_release(tmp_path, "b.py", "def b():\n    return 1\n")
    ws = Path(tmp_path) / "workspace"
    (ws / "a.py").write_text("def broken(:\n    return\n", encoding="utf-8")
    hc = health_check(str(tmp_path), rel_b)
    assert hc["result"] == "UNHEALTHY"
    inc = create_incident(str(tmp_path), hc)
    r = recover(str(tmp_path), inc["incident_id"])
    assert r.get("resolved") is True, r
    assert r["incident"]["status"] == "RESOLVED"
    assert r["rollback"]["state"] == "ROLLED_BACK"
    # workspace 恢复 (a.py 回到 Release A 内容)
    assert "def a():" in (ws / "a.py").read_text(encoding="utf-8")
    # rollback_id 记录在 incident
    assert r["incident"]["rollback_id"]


# --- E2E-4: Rollback Failure → Incident FAILED ---

def test_rollback_failure_not_fake(tmp_path):
    """无更早 release 可回滚 → Incident FAILED (不伪造 RESOLVED)。"""
    rel_id = _make_release(tmp_path)
    ws = Path(tmp_path) / "workspace"
    (ws / "a.py").write_text("def broken(:\n    return\n", encoding="utf-8")
    hc = health_check(str(tmp_path), rel_id)
    inc = create_incident(str(tmp_path), hc)
    r = recover(str(tmp_path), inc["incident_id"])
    assert r.get("failed") is True
    assert r["incident"]["status"] == "FAILED"
    assert r["incident"]["failure_reason"]


# --- E2E-5: Idempotency ---

def test_recovery_idempotent(tmp_path):
    rel_a = _make_release(tmp_path, "a.py", "def a():\n    return 1\n")
    time.sleep(1.1)
    rel_b = _make_release(tmp_path, "b.py", "def b():\n    return 1\n")
    ws = Path(tmp_path) / "workspace"
    (ws / "a.py").write_text("def broken(:\n    return\n", encoding="utf-8")
    hc = health_check(str(tmp_path), rel_b)
    inc = create_incident(str(tmp_path), hc)
    r1 = recover(str(tmp_path), inc["incident_id"])
    assert r1.get("resolved") is True
    r2 = recover(str(tmp_path), inc["incident_id"])
    assert r2.get("already_resolved") is True
    # workspace 不变
    assert "def a():" in (ws / "a.py").read_text(encoding="utf-8")


# --- Concurrency ---

def test_concurrent_health_checks(tmp_path):
    """4 并发 health check → JSON 不 corrupt, 记录 4 条。"""
    rel_id = _make_release(tmp_path)
    import threading
    import json
    results = []
    barrier = threading.Barrier(4)

    def worker():
        barrier.wait()
        try:
            hc = health_check(str(tmp_path), rel_id)
            results.append(hc["health_check_id"])
        except Exception as exc:  # noqa: BLE001
            results.append(f"err:{exc}")

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 4
    assert all(str(r).startswith("hchk-") for r in results)
    data = json.loads((Path(tmp_path) / "health" / "checks.json").read_text(encoding="utf-8"))
    assert len(data) == 4


# --- CLI ---

def test_cli_health(tmp_path):
    rel_id = _make_release(tmp_path)
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["health", "check", rel_id, "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["health", "incidents", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["health", "incident", "inc-x", "--data-dir", str(tmp_path)]) == 1


# --- API ---

def test_api_health(tmp_path):
    rel_id = _make_release(tmp_path)
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.post(f"/api/releases/{rel_id}/health-check")
    assert resp.status_code == 200
    assert resp.json()["result"] == "HEALTHY"
    resp = client.get("/api/health-incidents")
    assert resp.status_code == 200
    assert "items" in resp.json()


# --- Audit ---

def test_health_audit_events(tmp_path):
    rel_id = _make_release(tmp_path)
    ws = Path(tmp_path) / "workspace"
    (ws / "a.py").write_text("def broken(:\n    return\n", encoding="utf-8")
    hc = health_check(str(tmp_path), rel_id)
    inc = create_incident(str(tmp_path), hc)
    recover(str(tmp_path), inc["incident_id"])
    from factory_console.audit.audit_store import AuditStore
    store = AuditStore(workspace=None,
                       file=str(Path(tmp_path) / "audit" / "audit_events.json"))
    types = {getattr(e, "event_type", "") for e in store.events()}
    assert "HEALTH_CHECK_STARTED" in types
    assert "HEALTH_CHECK_COMPLETED" in types
    assert "HEALTH_FAILED" in types
    assert "HEALTH_INCIDENT_CREATED" in types
