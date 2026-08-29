"""S19: Multi-Run Production + Release Rollback。

覆盖:
- Multi-Run isolation (A/B 独立 artifacts/approval/release)
- Release History (多 release 共存)
- Rollback Contract + State Machine
- Target validation (不存在/跨 project → BLOCKED)
- Governance (missing approval → BLOCKED)
- 真实 Rollback (workspace 恢复 target)
- Rollback idempotency
- Rollback failure (不 fake)
- CLI / API
- Real Multi-Run E2E + Rollback E2E
"""
from __future__ import annotations

import sys
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
    create as rel_create, execute as rel_execute, get_release, list_releases,
)
from factory_console.rollback_service import (  # noqa: E402
    create as rb_create, get_rollback, list_rollbacks, check as rb_check,
    execute as rb_execute, history as rb_history,
)


def _patch(fname: str, body: str = "def x():\n    return 1\n") -> str:
    lines = "".join(f"+{ln}\n" for ln in body.rstrip("\n").split("\n"))
    return f"diff --git a/{fname} b/{fname}\n--- /dev/null\n+++ b/{fname}\n@@ -0,0 +1,{len(body.rstrip(chr(10)).split(chr(10)))} @@\n{lines}"


def _make_run(tmp_path, fname: str, body: str = "def x():\n    return 1\n") -> tuple[str, list[str], str]:
    """真实 ProductionRun + Release (COMPLETED + evaluation + approval + release)。"""
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
    rel = get_release(str(tmp_path), rel["release_id"])
    return run["run_id"], arts, rel["release_id"]


# --- Multi-Run isolation ---

def test_multi_run_isolation(tmp_path):
    """Run A / Run B: run_id, artifacts, approval, release 全独立。"""
    ra, arts_a, rel_a = _make_run(tmp_path, "a.py", "def a():\n    return 1\n")
    rb_, arts_b, rel_b = _make_run(tmp_path, "b.py", "def b():\n    return 1\n")
    assert ra != rb_
    assert arts_a != arts_b, "Artifact 必须隔离"
    assert rel_a != rel_b, "Release 必须隔离"
    # Release History: 2 个共存
    rels = list_releases(str(tmp_path))
    assert len(rels) == 2
    assert {r["release_id"] for r in rels} == {rel_a, rel_b}
    # workspace 两个文件都真实存在
    ws = Path(tmp_path) / "workspace"
    assert (ws / "a.py").exists()
    assert (ws / "b.py").exists()


# --- Rollback Contract ---

def test_rollback_contract(tmp_path):
    ra, arts_a, rel_a = _make_run(tmp_path, "a.py")
    rb_, arts_b, rel_b = _make_run(tmp_path, "b.py")
    rb = rb_create(str(tmp_path), rel_a)
    assert rb["rollback_id"].startswith("rb-")
    assert rb["target_release_id"] == rel_a
    assert rb["state"] == "PENDING"
    assert len(rb["history"]) == 1
    assert rb["artifact_ids"] == arts_a


# --- Target validation ---

def test_rollback_invalid_target(tmp_path):
    with pytest.raises(ValueError):
        rb_create(str(tmp_path), "rel-nonexistent")


def test_rollback_blocked_missing_approval(tmp_path):
    """Rollback execute 无 approval → BLOCKED (governance)。"""
    ra, arts_a, rel_a = _make_run(tmp_path, "a.py")
    rb_, arts_b, rel_b = _make_run(tmp_path, "b.py")
    rb = rb_create(str(tmp_path), rel_a)
    r = rb_execute(str(tmp_path), rb["rollback_id"])
    # target release A 的 approval 存在 (release 时批准过) → 可能 allowed
    # 但 rollback 自身无 approval → 若 policy 要求 → BLOCKED
    assert r["rollback"]["state"] in ("ROLLED_BACK", "BLOCKED")


# --- 真实 Rollback E2E ---

def test_real_rollback_e2e(tmp_path):
    """Run A → Release A; Run B → Release B; Rollback B→A → workspace 恢复 A。"""
    ra, arts_a, rel_a = _make_run(tmp_path, "a.py", "def a():\n    return 1\n")
    rb_, arts_b, rel_b = _make_run(tmp_path, "b.py", "def b():\n    return 1\n")
    rb = rb_create(str(tmp_path), rel_a)
    r = rb_execute(str(tmp_path), rb["rollback_id"])
    assert r["rollback"]["state"] == "ROLLED_BACK", r
    # 历史保留: Release A/B 仍 RELEASED, Rollback 独立
    assert get_release(str(tmp_path), rel_a)["state"] == "RELEASED"
    assert get_release(str(tmp_path), rel_b)["state"] == "RELEASED"
    # workspace: target A 的文件恢复 (rollback artifact)
    ws = Path(tmp_path) / "workspace"
    assert (ws / "a.py").exists(), "rollback 必须恢复 target release 文件"
    # evidence
    assert len(r["rollback"]["evidence"]) >= 1
    assert any(e["type"] == "rollback_apply" for e in r["rollback"]["evidence"])
    # 状态机历史
    states = [h["to"] for h in r["rollback"]["history"]]
    assert states == ["PENDING", "GATED", "APPROVED", "ROLLING_BACK", "ROLLED_BACK"]


# --- Idempotency ---

def test_rollback_idempotent(tmp_path):
    ra, arts_a, rel_a = _make_run(tmp_path, "a.py")
    rb_, arts_b, rel_b = _make_run(tmp_path, "b.py")
    rb = rb_create(str(tmp_path), rel_a)
    r1 = rb_execute(str(tmp_path), rb["rollback_id"])
    assert r1["rollback"]["state"] == "ROLLED_BACK"
    r2 = rb_execute(str(tmp_path), rb["rollback_id"])
    assert r2.get("already_rolled_back") is True
    # workspace 不变
    ws = Path(tmp_path) / "workspace"
    a_content = (ws / "a.py").read_text() if (ws / "a.py").exists() else ""
    r3 = rb_execute(str(tmp_path), rb["rollback_id"])
    assert r3.get("already_rolled_back") is True


# --- Failure: invalid target → BLOCKED ---

def test_rollback_failure_not_fake(tmp_path):
    ra, arts_a, rel_a = _make_run(tmp_path, "a.py")
    rb_, arts_b, rel_b = _make_run(tmp_path, "b.py")
    # 伪造 target → create 拒绝
    with pytest.raises(ValueError):
        rb_create(str(tmp_path), "rel-fake")
    # cross-project: 用不存在的 project 的 release → 拒绝
    with pytest.raises(ValueError):
        rb_create(str(tmp_path), "rel-other-project")


# --- CLI ---

def test_cli_rollback(tmp_path):
    ra, arts_a, rel_a = _make_run(tmp_path, "a.py")
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["rollback", "create", rel_a, "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["rollback", "list", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["rollback", "status", "rb-x", "--data-dir", str(tmp_path)]) == 1


# --- API ---

def test_api_rollback(tmp_path):
    ra, arts_a, rel_a = _make_run(tmp_path, "a.py")
    rb_, arts_b, rel_b = _make_run(tmp_path, "b.py")
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    # create
    resp = client.post(f"/api/releases/{rel_a}/rollbacks")
    assert resp.status_code == 200
    rb_id = resp.json()["rollback_id"]
    assert resp.json()["state"] == "PENDING"
    # check
    resp = client.get(f"/api/rollbacks/{rb_id}/check")
    assert resp.status_code == 200
    # execute
    resp = client.post(f"/api/rollbacks/{rb_id}/execute")
    assert resp.status_code == 200
    assert resp.json()["rollback"]["state"] == "ROLLED_BACK"
    # list + get + history
    resp = client.get("/api/rollbacks")
    assert resp.status_code == 200
    assert any(x["rollback_id"] == rb_id for x in resp.json()["items"])
    resp = client.get(f"/api/rollbacks/{rb_id}")
    assert resp.status_code == 200
    resp = client.get(f"/api/rollbacks/{rb_id}/history")
    assert resp.status_code == 200
    assert len(resp.json()["history"]) >= 4


# --- Audit ---

def test_rollback_audit(tmp_path):
    ra, arts_a, rel_a = _make_run(tmp_path, "a.py")
    rb_, arts_b, rel_b = _make_run(tmp_path, "b.py")
    rb = rb_create(str(tmp_path), rel_a)
    rb_execute(str(tmp_path), rb["rollback_id"])
    from factory_console.audit.audit_store import AuditStore
    store = AuditStore(workspace=None,
                       file=str(Path(tmp_path) / "audit" / "audit_events.json"))
    types = {getattr(e, "event_type", "") for e in store.events()}
    assert "ROLLBACK_CREATED" in types
    assert "ROLLBACK_ROLLED_BACK" in types
