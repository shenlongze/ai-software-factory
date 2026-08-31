"""K4: Control Tower & Real-time Operations。

覆盖:
- Unified Operational State Contract (Task/Agent 语义)
- 全链路钻取 (project→sprint→task→run→evidence + why)
- 谁在工作 (agent 级真实依据 + Idle 原因)
- Global Operations View
- Snapshot + restore (断线恢复一致性)
- 实时一致性 (task 状态变化 → tower 投影)
- 并发 (多 project/task 无串数据)
- CLI / API
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.conversation_os import create_conversation, send_message  # noqa: E402
from factory_console.project_os import (  # noqa: E402
    create_project, create_sprint, add_task_to_sprint,
)
from factory_console.task_tree import (  # noqa: E402
    decompose, execute_subtask, update_task_status,
)
from factory_console.operational_state import (  # noqa: E402
    task_operational_state, agent_operational_state, drill_down,
    who_is_working, global_overview, snapshot, restore_from_snapshot,
    TASK_STATES, AGENT_STATES,
)
from factory_console.control_tower import control_tower  # noqa: E402


def _good_factory(node_id):
    def fn(input_data):
        return {"ok": True, "output": {"code": "x"},
                "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n"
                               "@@ -0,0 +1 @@\nx = 1\n"),
                "artifact_type": "code_change", "verification": {"result": "PASS"}}
    return fn


def _seed(tmp_path, title="项目", domain="default"):
    conv = create_conversation(str(tmp_path), title=title)
    send_message(str(tmp_path), conv["id"], f"我要做{title}")
    proj = create_project(str(tmp_path), title=title, source_conv_id=conv["id"])
    sp = create_sprint(str(tmp_path), proj["id"], title="S1")
    tree = decompose(str(tmp_path), title=title, domain=domain,
                     source_req_id=proj["source_requirement_id"])
    for tid in tree["subtasks"]:
        add_task_to_sprint(str(tmp_path), sp["id"], tid)
    return conv, proj, sp, tree


# --- Operational State Contract ---

def test_state_contract(tmp_path):
    assert "RUNNING" in TASK_STATES
    assert "WAITING_APPROVAL" in TASK_STATES
    assert "IDLE" in AGENT_STATES
    # entity.status → operational state (确定性)
    assert task_operational_state({"status": "DRAFT"}) == "PLANNED"
    assert task_operational_state({"status": "RUNNING"}) == "RUNNING"
    assert task_operational_state({"status": "BLOCKED"}) == "BLOCKED"
    assert task_operational_state({"status": "COMPLETED"}) == "COMPLETED"


# --- 全链路钻取 ---

def test_drill_down(tmp_path):
    conv, proj, sp, tree = _seed(tmp_path)
    execute_subtask(str(tmp_path), tree["subtasks"][0], executor_factory=_good_factory,
                    artifact_root=str(tmp_path))
    dd = drill_down(str(tmp_path), proj["id"])
    assert dd["project"]["id"] == proj["id"]
    assert len(dd["sprints"]) == 1
    t0 = dd["sprints"][0]["tasks"][0]
    assert t0["status"] == "COMPLETED"
    assert "COMPLETED" in t0["why"]
    assert "operational_state" in t0
    assert t0["production_run_id"].startswith("prun")
    # evidence 关联
    assert isinstance(t0["evidence"], list)


# --- 谁在工作 (agent 级) ---

def test_who_is_working(tmp_path):
    conv, proj, sp, tree = _seed(tmp_path)
    # 执行 1 个 → 其余 waiting
    execute_subtask(str(tmp_path), tree["subtasks"][0], executor_factory=_good_factory,
                    artifact_root=str(tmp_path))
    wiw = who_is_working(str(tmp_path))
    assert wiw["count"] >= 1
    states = {a["state"] for a in wiw["agents"]}
    assert "IDLE" in states or "WAITING" in states or "RUNNING" in states
    # Idle 有原因 (非猜测)
    for a in wiw["agents"]:
        if a["state"] in ("IDLE", "WAITING"):
            assert a.get("idle_reason"), f"agent {a['agent']} 缺 idle_reason"


# --- Global Operations View ---

def test_global_overview(tmp_path):
    conv, proj, sp, tree = _seed(tmp_path)
    execute_subtask(str(tmp_path), tree["subtasks"][0], executor_factory=_good_factory,
                    artifact_root=str(tmp_path))
    go = global_overview(str(tmp_path))
    assert "projects" in go and "workforce" in go and "recent_activity" in go
    assert "calculated_at" in go


# --- Snapshot + 断线恢复 ---

def test_snapshot_consistency(tmp_path):
    conv, proj, sp, tree = _seed(tmp_path)
    execute_subtask(str(tmp_path), tree["subtasks"][0], executor_factory=_good_factory,
                    artifact_root=str(tmp_path))
    snap = snapshot(str(tmp_path))
    assert snap["snapshot_id"].startswith("snap_")
    assert restore_from_snapshot(str(tmp_path), snap) is True
    # 状态变化 → 旧快照不一致 (断线后检测到变化)
    update_task_status(str(tmp_path), tree["subtasks"][1], status="COMPLETED")
    assert restore_from_snapshot(str(tmp_path), snap) is False


# --- 实时一致性 (task → tower 投影) ---

def test_realtime_consistency(tmp_path):
    conv, proj, sp, tree = _seed(tmp_path)
    # 初始: 全部 PLANNED
    ct0 = control_tower(str(tmp_path))
    assert ct0["work"]["executions"] == 0
    # 执行 → tower 实时反映
    execute_subtask(str(tmp_path), tree["subtasks"][0], executor_factory=_good_factory,
                    artifact_root=str(tmp_path))
    ct1 = control_tower(str(tmp_path))
    assert ct1["work"]["executions"] == 1
    assert ct1["work"]["execution_states"].get("COMPLETED", 0) == 1
    # 再执行 → 递增
    execute_subtask(str(tmp_path), tree["subtasks"][1], executor_factory=_good_factory,
                    artifact_root=str(tmp_path))
    ct2 = control_tower(str(tmp_path))
    assert ct2["work"]["executions"] == 2


# --- 并发 (多 project 无串数据) ---

def test_concurrent_projects(tmp_path):
    p1 = _seed(tmp_path, title="项目A", domain="app")
    p2 = _seed(tmp_path, title="项目B", domain="app")
    # 各自执行
    execute_subtask(str(tmp_path), p1[3]["subtasks"][0], executor_factory=_good_factory,
                    artifact_root=str(tmp_path))
    execute_subtask(str(tmp_path), p2[3]["subtasks"][1], executor_factory=_good_factory,
                    artifact_root=str(tmp_path))
    # 各自投影独立 (无串数据)
    ps1 = drill_down(str(tmp_path), p1[1]["id"])
    ps2 = drill_down(str(tmp_path), p2[1]["id"])
    assert ps1["sprints"][0]["tasks"][0]["status"] == "COMPLETED"
    assert ps1["sprints"][0]["tasks"][1]["status"] != "COMPLETED"
    assert ps2["sprints"][0]["tasks"][0]["status"] != "COMPLETED"
    assert ps2["sprints"][0]["tasks"][1]["status"] == "COMPLETED"
    # ID 不冲突
    assert p1[1]["id"] != p2[1]["id"]


# --- CLI ---

def test_cli_ct(tmp_path):
    conv, proj, sp, tree = _seed(tmp_path)
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["ct", "overview", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["ct", "whoworking", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["ct", "drill", proj["id"], "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["ct", "snapshot", "--data-dir", str(tmp_path)]) == 0


# --- API ---

def test_api_ct(tmp_path):
    conv, proj, sp, tree = _seed(tmp_path)
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.get("/api/ops/overview")
    assert resp.status_code == 200
    assert "projects" in resp.json()
    resp = client.get("/api/ops/who-working")
    assert resp.status_code == 200
    resp = client.get(f"/api/ops/drill/{proj['id']}")
    assert resp.status_code == 200
    assert resp.json()["project"]["id"] == proj["id"]
    resp = client.get("/api/ops/snapshot")
    assert resp.status_code == 200
    assert resp.json()["snapshot_id"].startswith("snap_")
