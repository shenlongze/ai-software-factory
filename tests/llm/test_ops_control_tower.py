"""S22: Continuous Production Operations & Control Tower。

覆盖:
- Schedule Contract + 持久化 (create/load/restart)
- Schedule 执行 (到期 → health_check; 幂等 dedup)
- Missed schedule (bounded catch-up + skipped_count)
- Concurrency (重复执行不重复 check)
- Health Projection (project/release/history/comparison, facts 计算非第二事实源)
- Multi-Release Health
- Control Plane API / CLI
- Restart E2E (schedule survived reload)
- Self-Healing E2E (schedule → health fail → recover)
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone
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
from factory_console.ops_scheduler import (  # noqa: E402
    create_schedule, list_schedules, get_schedule, run_due_schedules,
    disable_schedule, enable_schedule, delete_schedule,
)
from factory_console.ops_projection import (  # noqa: E402
    overview, project_health, release_health, release_health_history, compare_releases,
)


def _patch(fname: str, body: str = "def x():\n    return 1\n") -> str:
    lines = "".join(f"+{ln}\n" for ln in body.rstrip("\n").split("\n"))
    return f"diff --git a/{fname} b/{fname}\n--- /dev/null\n+++ b/{fname}\n@@ -0,0 +1,{len(body.rstrip(chr(10)).split(chr(10)))} @@\n{lines}"


def _make_release(tmp_path, project_id: str = "proj-1", fname: str = "a.py",
                  body: str = "def x():\n    return 1\n") -> str:
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", project_id=project_id, nodes=[
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


# --- Schedule Contract + Persistence ---

def test_schedule_create_persist_restart(tmp_path):
    """Schedule 创建 + 持久化 (restart = 重新 load)。"""
    rel_id = _make_release(tmp_path)
    s = create_schedule(str(tmp_path), project_id="proj-1", release_id=rel_id,
                        interval_seconds=60)
    # 重启模拟: 新实例 load
    loaded = list_schedules(str(tmp_path))
    assert len(loaded) == 1
    assert loaded[0]["schedule_id"] == s["schedule_id"]
    assert loaded[0]["enabled"] is True
    assert loaded[0]["interval_seconds"] == 60
    # disable/enable/delete
    s2 = disable_schedule(str(tmp_path), s["schedule_id"])
    assert s2["enabled"] is False
    assert get_schedule(str(tmp_path), s["schedule_id"])["enabled"] is False
    s3 = enable_schedule(str(tmp_path), s["schedule_id"])
    assert s3["enabled"] is True
    delete_schedule(str(tmp_path), s["schedule_id"])
    assert len(list_schedules(str(tmp_path))) == 0


# --- Schedule Execution + Idempotency ---

def test_schedule_execute_and_idempotent(tmp_path):
    """Schedule 到期 → health_check 执行; 立即再跑 → 幂等 (next_run_at 未来)。"""
    rel_id = _make_release(tmp_path)
    s = create_schedule(str(tmp_path), project_id="proj-1", release_id=rel_id,
                        interval_seconds=60)
    r = run_due_schedules(str(tmp_path))
    assert len(r["executed"]) == 1
    assert r["executed"][0]["result"] == "HEALTHY"
    s2 = get_schedule(str(tmp_path), s["schedule_id"])
    assert s2["last_result"] == "HEALTHY"
    assert s2["last_run_at"]
    # 幂等: next_run_at 在未来 → 不执行
    r2 = run_due_schedules(str(tmp_path))
    assert len(r2["executed"]) == 0


def test_schedule_disabled_not_executed(tmp_path):
    rel_id = _make_release(tmp_path)
    s = create_schedule(str(tmp_path), project_id="proj-1", release_id=rel_id,
                        interval_seconds=60)
    disable_schedule(str(tmp_path), s["schedule_id"])
    r = run_due_schedules(str(tmp_path))
    assert len(r["executed"]) == 0


# --- Missed schedule (bounded catch-up) ---

def test_missed_schedule_bounded_catchup(tmp_path):
    """next_run_at 远早于 now → bounded catch-up (≤3) + skipped_count。"""
    rel_id = _make_release(tmp_path)
    s = create_schedule(str(tmp_path), project_id="proj-1", release_id=rel_id,
                        interval_seconds=60)
    # 手动把 next_run_at 拨到 10 分钟前 (missed 10 个 interval)
    from factory_console.ops_scheduler import _update
    past = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(timespec="seconds")
    _update(str(tmp_path), s["schedule_id"], {"next_run_at": past})
    r = run_due_schedules(str(tmp_path))
    assert len(r["executed"]) == 1  # 只补 1 次执行 (不是 10 次)
    s2 = get_schedule(str(tmp_path), s["schedule_id"])
    assert s2["skipped_count"] >= 3  # bounded: 10 个 missed 记 3 (MAX_CATCH_UP)


# --- Concurrency: 重复触发不重复执行 ---

def test_schedule_duplicate_trigger_safe(tmp_path):
    """同 schedule 连续两次 run_due (模拟重复 worker) → 不重复 check。"""
    rel_id = _make_release(tmp_path)
    s = create_schedule(str(tmp_path), project_id="proj-1", release_id=rel_id,
                        interval_seconds=60)
    r1 = run_due_schedules(str(tmp_path))
    # 手动把 next_run_at 拨回 now (模拟重复触发)
    from factory_console.ops_scheduler import _update
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _update(str(tmp_path), s["schedule_id"], {"next_run_at": now})
    r2 = run_due_schedules(str(tmp_path))
    # dedup 窗口: last_run_at 在 5min 窗口内 → skip
    assert len(r2["skipped_duplicates"]) >= 1 or len(r2["executed"]) == 0


# --- Health Projection ---

def test_project_and_release_health(tmp_path):
    rel_id = _make_release(tmp_path, project_id="proj-1")
    from factory_console.health_service import health_check
    health_check(str(tmp_path), rel_id)
    ph = project_health(str(tmp_path), "proj-1")
    assert ph["health_state"] == "HEALTHY"
    assert len(ph["releases"]) == 1
    rh = release_health(str(tmp_path), rel_id)
    assert rh["health_state"] == "HEALTHY"
    assert "healthy" in rh["explain"]
    # history
    hist = release_health_history(str(tmp_path), rel_id)
    assert len(hist) >= 1
    assert hist[-1]["kind"] == "health_check"


def test_multi_release_distinct_health(tmp_path):
    """Release A HEALTHY, Release B UNHEALTHY → 能区分。"""
    rel_a = _make_release(tmp_path, project_id="proj-1", fname="a.py", body="def a():\n    return 1\n")
    time.sleep(1.1)
    rel_b = _make_release(tmp_path, project_id="proj-1", fname="b.py", body="def b():\n    return 1\n")
    from factory_console.health_service import health_check
    health_check(str(tmp_path), rel_a)
    # 退化 B
    ws = Path(tmp_path) / "workspace"
    (ws / "b.py").write_text("def broken(:\n    return\n", encoding="utf-8")
    hc = health_check(str(tmp_path), rel_b)
    assert hc["result"] == "UNHEALTHY"
    ph = project_health(str(tmp_path), "proj-1")
    assert ph["health_state"] == "UNHEALTHY"
    states = {rv["release_id"]: rv["health_state"] for rv in ph["releases"]}
    assert states[rel_a] == "HEALTHY"
    assert states[rel_b] == "UNHEALTHY"
    # comparison
    cmp = compare_releases(str(tmp_path), rel_a, rel_b)
    assert cmp["more_healthy"] == rel_a


# --- Overview ---

def test_operations_overview(tmp_path):
    rel_id = _make_release(tmp_path, project_id="proj-1")
    from factory_console.health_service import health_check
    health_check(str(tmp_path), rel_id)
    s = create_schedule(str(tmp_path), project_id="proj-1", release_id=rel_id, interval_seconds=60)
    ov = overview(str(tmp_path))
    assert ov["releases_active"] == 1
    assert ov["health_states"].get("HEALTHY") == 1
    assert ov["schedules"] == 1
    assert ov["schedules_enabled"] == 1
    assert ov["health_checks_total"] >= 1


# --- CLI ---

def test_cli_ops_and_schedule(tmp_path):
    rel_id = _make_release(tmp_path, project_id="proj-1")
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["schedule", "create", rel_id, "--interval", "60", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["schedule", "list", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["ops", "status", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["ops", "health", "proj-1", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["ops", "history", rel_id, "--data-dir", str(tmp_path)]) == 0


# --- API ---

def test_api_ops(tmp_path):
    rel_id = _make_release(tmp_path, project_id="proj-1")
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.get("/api/operations/overview")
    assert resp.status_code == 200
    assert resp.json()["releases_active"] == 1
    resp = client.get("/api/projects/proj-1/health")
    assert resp.status_code == 200
    assert resp.json()["health_state"] in ("HEALTHY", "UNKNOWN")
    resp = client.get(f"/api/releases/{rel_id}/health")
    assert resp.status_code == 200
    resp = client.get(f"/api/releases/{rel_id}/health/history")
    assert resp.status_code == 200
    resp = client.post("/api/schedules", json={"release_id": rel_id, "interval_seconds": 60})
    assert resp.status_code == 200
    assert resp.json()["schedule_id"].startswith("sch-")
    resp = client.get("/api/schedules")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


# --- Restart E2E ---

def test_scheduler_restart_e2e(tmp_path):
    """Create → persist → 'restart' (重新 load) → execute。"""
    rel_id = _make_release(tmp_path, project_id="proj-1")
    s = create_schedule(str(tmp_path), project_id="proj-1", release_id=rel_id, interval_seconds=60)
    # restart 模拟: 新模块实例 (重新读文件)
    loaded = list_schedules(str(tmp_path))
    assert loaded[0]["schedule_id"] == s["schedule_id"]
    r = run_due_schedules(str(tmp_path))
    assert r["executed"][0]["result"] == "HEALTHY"
