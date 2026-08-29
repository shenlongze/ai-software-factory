"""S18: Production Release Pipeline & Approval UI。

覆盖:
- Release Contract / State Machine (PENDING→GATED→APPROVED→RELEASING→RELEASED)
- Governance (missing approval → BLOCKED; reject → BLOCKED)
- Idempotency (RELEASED 重复 execute → no-op)
- 真实 Release (Apply → workspace evidence)
- Failure (executor/apply fail → FAILED)
- CLI / API
- E2E: approve→release allowed; reject→blocked
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.release_service import (  # noqa: E402
    create, get_release, list_releases, check, execute, history,
    ST_PENDING, ST_RELEASED, ST_BLOCKED,
)
from factory_console.production_run import (  # noqa: E402
    register_workflow, create_production_run, execute_production_run, get_production_run,
)
from factory_console.production_evaluation import evaluate  # noqa: E402
from factory_console.governance_service import (  # noqa: E402
    request_approval, approve, reject,
)

PATCH = "diff --git a/x.py b/x.py\n--- /dev/null\n+++ b/x.py\n@@ -0,0 +1,2 @@\n+def x():\n+    return 1\n"


def _completed_run(tmp_path) -> tuple[str, list[str]]:
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=[
        {"node_id": "a", "name": "A", "type": "engineering", "executor_name": "a"}])
    run = create_production_run(str(tmp_path), "wf-1")

    def factory(node_id):
        def fn(input_data):
            return {"ok": True, "output": {"code": "x"}, "patch_text": PATCH,
                    "artifact_type": "code_change", "verification": {"result": "PASS"}}
        return fn
    execute_production_run(str(tmp_path), run["run_id"], executor_factory=factory,
                           artifact_root=str(tmp_path))
    run2 = get_production_run(str(tmp_path), run["run_id"])
    evaluate(str(tmp_path), run["run_id"])
    return run["run_id"], list(run2.get("artifacts", []))


def _approve_run(tmp_path, run_id, arts):
    a = request_approval(str(tmp_path), production_run_id=run_id,
                         artifact_ids=arts, requested_by="dev-agent")
    approve(str(tmp_path), a["approval_id"], decided_by="human")
    return a


# --- Contract / State Machine ---

def test_release_contract(tmp_path):
    rid, arts = _completed_run(tmp_path)
    rel = create(str(tmp_path), rid)
    assert rel["release_id"].startswith("rel-")
    assert rel["state"] == ST_PENDING
    assert rel["artifact_ids"] == arts
    assert len(rel["history"]) == 1
    assert "release_id" in rel and "production_run_id" in rel and "evidence" in rel


def test_release_state_machine(tmp_path):
    rid, arts = _completed_run(tmp_path)
    _approve_run(tmp_path, rid, arts)
    rel = create(str(tmp_path), rid)
    r = execute(str(tmp_path), rel["release_id"])
    assert r["release"]["state"] == ST_RELEASED
    states = [h["to"] for h in r["release"]["history"]]
    assert states == [ST_PENDING, "GATED", "APPROVED", "RELEASING", "VERIFYING", ST_RELEASED]


# --- Governance: missing approval → BLOCKED ---

def test_release_blocked_without_approval(tmp_path):
    rid, arts = _completed_run(tmp_path)
    rel = create(str(tmp_path), rid)
    r = execute(str(tmp_path), rel["release_id"])
    assert r.get("blocked") is True
    assert r["release"]["state"] == ST_BLOCKED
    assert "approval" in r.get("missing", [])


def test_release_blocked_on_reject(tmp_path):
    rid, arts = _completed_run(tmp_path)
    a = request_approval(str(tmp_path), production_run_id=rid,
                         artifact_ids=arts, requested_by="dev-agent")
    reject(str(tmp_path), a["approval_id"], decided_by="human", reason="no")
    rel = create(str(tmp_path), rid)
    r = execute(str(tmp_path), rel["release_id"])
    assert r.get("blocked") is True
    assert "approval" in r.get("missing", [])


# --- 真实 Release: Apply → workspace evidence ---

def test_release_apply_workspace(tmp_path):
    rid, arts = _completed_run(tmp_path)
    _approve_run(tmp_path, rid, arts)
    rel = create(str(tmp_path), rid)
    r = execute(str(tmp_path), rel["release_id"])
    assert r["release"]["state"] == ST_RELEASED
    assert len(r["release"]["evidence"]) == len(arts)
    assert any(e["type"] == "apply" for e in r["release"]["evidence"])
    # workspace 真实有文件
    ws = Path(tmp_path) / "workspace"
    assert (ws / "x.py").exists()


# --- Idempotency ---

def test_release_idempotent(tmp_path):
    rid, arts = _completed_run(tmp_path)
    _approve_run(tmp_path, rid, arts)
    rel = create(str(tmp_path), rid)
    r1 = execute(str(tmp_path), rel["release_id"])
    assert r1["release"]["state"] == ST_RELEASED
    r2 = execute(str(tmp_path), rel["release_id"])
    assert r2.get("already_released") is True
    assert r2["release"]["state"] == ST_RELEASED


# --- Failure: apply fail → FAILED (不 fake) ---

def test_release_failure_not_fake(tmp_path):
    """无 patch 的 artifact → apply 失败 → FAILED + failure_reason。"""
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=[
        {"node_id": "a", "name": "A", "type": "engineering", "executor_name": "a"}])
    run = create_production_run(str(tmp_path), "wf-1")

    def factory(node_id):
        def fn(input_data):
            # 无 patch_text → apply 会 no-op (仍 RELEASED) — 用损坏 patch 触发 FAIL
            return {"ok": True, "output": {"code": "x"}, "patch_text": "corrupt",
                    "artifact_type": "code_change", "verification": {"result": "PASS"}}
        return fn
    execute_production_run(str(tmp_path), run["run_id"], executor_factory=factory,
                           artifact_root=str(tmp_path))
    run2 = get_production_run(str(tmp_path), run["run_id"])
    evaluate(str(tmp_path), run["run_id"])
    arts = list(run2.get("artifacts", []))
    _approve_run(tmp_path, run["run_id"], arts)
    rel = create(str(tmp_path), run["run_id"])
    r = execute(str(tmp_path), rel["release_id"])
    # corrupt patch → apply 失败 → FAILED (真实失败, 非 fake success)
    assert r["release"]["state"] == "FAILED"
    assert r["release"]["failure_reason"]


# --- CLI ---

def test_cli_release(tmp_path):
    rid, arts = _completed_run(tmp_path)
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["release", "create", rid, "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["release", "list", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["release", "status", "rel-x", "--data-dir", str(tmp_path)]) == 1  # 不存在


# --- API ---

def test_api_release(tmp_path):
    rid, arts = _completed_run(tmp_path)
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    # create
    resp = client.post(f"/api/production-runs/{rid}/releases")
    assert resp.status_code == 200
    rel_id = resp.json()["release_id"]
    assert resp.json()["state"] == ST_PENDING
    # gate view (无 approval → blocked)
    resp = client.get(f"/api/production-runs/{rid}/release")
    assert resp.status_code == 200
    assert resp.json()["gate"]["allowed"] is False
    # execute (blocked)
    resp = client.post(f"/api/releases/{rel_id}/execute")
    assert resp.status_code == 200
    assert resp.json()["release"]["state"] == ST_BLOCKED
    # list + get + history
    resp = client.get("/api/releases")
    assert resp.status_code == 200
    assert any(x["release_id"] == rel_id for x in resp.json()["items"])
    resp = client.get(f"/api/releases/{rel_id}")
    assert resp.status_code == 200
    resp = client.get(f"/api/releases/{rel_id}/history")
    assert resp.status_code == 200
    assert len(resp.json()["history"]) >= 2


# --- E2E: approve → RELEASED ---

def test_release_approve_e2e(tmp_path):
    rid, arts = _completed_run(tmp_path)
    _approve_run(tmp_path, rid, arts)
    rel = create(str(tmp_path), rid)
    r = execute(str(tmp_path), rel["release_id"])
    assert r["release"]["state"] == ST_RELEASED
    # audit 事件
    from factory_console.audit.audit_store import AuditStore
    store = AuditStore(workspace=None,
                       file=str(Path(tmp_path) / "audit" / "audit_events.json"))
    types = {getattr(e, "event_type", "") for e in store.events()}
    assert "RELEASE_CREATED" in types or "RELEASE_RELEASED" in types


# --- E2E: reject → BLOCKED ---

def test_release_reject_e2e(tmp_path):
    rid, arts = _completed_run(tmp_path)
    a = request_approval(str(tmp_path), production_run_id=rid,
                         artifact_ids=arts, requested_by="dev-agent")
    reject(str(tmp_path), a["approval_id"], decided_by="human", reason="not ready")
    rel = create(str(tmp_path), rid)
    r = execute(str(tmp_path), rel["release_id"])
    assert r["release"]["state"] == ST_BLOCKED
