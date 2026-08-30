"""K2: Control Tower (实时状态投影)。

覆盖:
- work_overview (conversations/tasks/executions 真实投影)
- workforce_status (running/waiting/blocked/error/idle)
- governance_pending (PENDING approvals)
- realtime_stream (最近事件, correlation 可追溯)
- control_tower 总览 (全投影合成, 无伪数据)
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
from factory_console.task_tree import decompose, execute_tree  # noqa: E402
from factory_console.control_tower import (  # noqa: E402
    control_tower, work_overview, workforce_status, governance_pending,
    realtime_stream,
)


def _good_factory(node_id):
    def fn(input_data):
        return {"ok": True, "output": {"code": "x"},
                "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n"
                               "@@ -0,0 +1 @@\nx = 1\n"),
                "artifact_type": "code_change", "verification": {"result": "PASS"}}
    return fn


def _seed(tmp_path):
    """创建真实数据: 1 conv + 1 task tree + 执行。"""
    conv = create_conversation(str(tmp_path), title="项目 A")
    send_message(str(tmp_path), conv["id"], "我想做记账 App")
    tree = decompose(str(tmp_path), title="记账 App", domain="app",
                     source_conv_id=conv["id"])
    execute_tree(str(tmp_path), tree["task_tree_id"], executor_factory=_good_factory,
                 artifact_root=str(tmp_path))
    return conv, tree


# --- work_overview (真实投影) ---

def test_work_overview(tmp_path):
    _seed(tmp_path)
    w = work_overview(str(tmp_path))
    assert w["conversations"] >= 1
    assert w["conversation_open"] >= 1
    assert w["tasks"] >= 7  # root + 6 subtasks
    assert w["executions"] >= 6  # 6 subtasks 真实执行
    assert w["execution_states"].get("COMPLETED", 0) >= 6
    assert "calculated_at" in w


# --- workforce_status ---

def test_workforce_status(tmp_path):
    _seed(tmp_path)
    ws = workforce_status(str(tmp_path))
    assert ws["running"] == 0
    assert ws["error"] == 0
    assert ws["idle"] >= 6  # 全部完成 → idle
    assert "active_tasks" in ws


# --- governance_pending ---

def test_governance_pending_empty(tmp_path):
    gp = governance_pending(str(tmp_path))
    assert gp["pending_approvals"] == 0
    assert gp["items"] == []


# --- realtime_stream ---

def test_realtime_stream(tmp_path):
    _seed(tmp_path)
    rt = realtime_stream(str(tmp_path), limit=10)
    assert rt["count"] >= 1
    assert all("event_type" in e for e in rt["events"])
    assert all("correlation_id" in e for e in rt["events"])


# --- control_tower 总览 ---

def test_control_tower(tmp_path):
    _seed(tmp_path)
    ct = control_tower(str(tmp_path))
    assert "work" in ct and "workforce" in ct
    assert "governance" in ct and "realtime" in ct
    assert ct["work"]["executions"] >= 6
    assert "calculated_at" in ct


# --- CLI ---

def test_cli_tower(tmp_path):
    _seed(tmp_path)
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["tower", "overview", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["tower", "workforce", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["tower", "governance", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["tower", "realtime", "--data-dir", str(tmp_path)]) == 0


# --- API ---

def test_api_tower(tmp_path):
    _seed(tmp_path)
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.get("/api/control-tower")
    assert resp.status_code == 200
    assert resp.json()["work"]["executions"] >= 6
    resp = client.get("/api/control-tower/workforce")
    assert resp.status_code == 200
    resp = client.get("/api/control-tower/governance")
    assert resp.status_code == 200
    resp = client.get("/api/control-tower/realtime")
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1
