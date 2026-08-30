"""K2: Task Tree Work OS (Real Complex Work 最小实现)。

覆盖:
- 需求 → Task Tree 分解 (确定性模板, S43 task_ 实体层级)
- 子任务 parent/children 关系
- 串行依赖 (depends_on)
- 统一进度投影 (completed/total/percentage, 可重建)
- Task 状态更新 (S43 lifecycle)
- 从 Conversation 触发分解 (K1 集成)
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
from factory_console.task_tree import (  # noqa: E402
    decompose, get_tree, update_task_status, task_progress, tree_status,
    task_trees, execute_subtask, execute_tree,
)
from factory_console.unified_contract import get_entity, trace_lineage  # noqa: E402


# --- 分解 ---

def test_decompose(tmp_path):
    tree = decompose(str(tmp_path), title="记账 App", domain="app")
    assert tree["task_tree_id"].startswith("task_")
    assert tree["count"] == 6  # app 模板 6 步
    assert len(tree["subtasks"]) == 6
    root = get_entity(str(tmp_path), tree["root_task"])
    assert root["type"] == "task"
    assert len(root["children"]) == 6
    assert tree["requirement_id"] == ""  # 无 conv 时无 requirement


def test_decompose_from_conversation(tmp_path):
    """K1 集成: Conversation → Requirement → Task Tree。"""
    conv = create_conversation(str(tmp_path), title="记账")
    send_message(str(tmp_path), conv["id"], "我想做记账 App")
    tree = decompose(str(tmp_path), title="记账 App", domain="backend",
                     source_conv_id=conv["id"])
    assert tree["requirement_id"].startswith("req_")
    # requirement 可追溯 conv
    lg = trace_lineage(str(tmp_path), tree["requirement_id"])
    assert any(x["type"] == "conv" for x in lg)


# --- 依赖 ---

def test_serial_dependencies(tmp_path):
    tree = decompose(str(tmp_path), title="任务", domain="default")
    st = tree_status(str(tmp_path), tree["task_tree_id"])
    # 子任务串行依赖 (每个依赖前一个)
    for i, t in enumerate(st["tasks"][1:]):
        if i > 0:
            assert t["depends_on"], f"task {i} 应有依赖"
            assert st["tasks"][i]["id"] in t["depends_on"]


# --- 进度投影 ---

def test_progress_projection(tmp_path):
    tree = decompose(str(tmp_path), title="任务", domain="default")
    p0 = task_progress(str(tmp_path), tree["task_tree_id"])
    assert p0["completed_units"] == 0
    assert p0["percentage"] == 0
    assert p0["source"] == "task_graph"
    # 完成 2 个 → 进度更新 (Projection 非 UI 状态)
    for tid in tree["subtasks"][:2]:
        update_task_status(str(tmp_path), tid, status="COMPLETED")
    p1 = task_progress(str(tmp_path), tree["task_tree_id"])
    assert p1["completed_units"] == 2
    assert p1["percentage"] > 0
    # 全部完成 → 100%
    for tid in tree["subtasks"][2:]:
        update_task_status(str(tmp_path), tid, status="COMPLETED")
    p2 = task_progress(str(tmp_path), tree["task_tree_id"])
    assert p2["percentage"] == 100


# --- 状态查询 ---

def test_tree_status(tmp_path):
    tree = decompose(str(tmp_path), title="X", domain="default")
    st = tree_status(str(tmp_path), tree["task_tree_id"])
    assert st["title"] == "X"
    assert len(st["tasks"]) == tree["count"] + 1  # root + subtasks
    assert all("status" in t for t in st["tasks"])
    assert "progress" in st


# --- 子任务真实执行 ---

def test_execute_subtask(tmp_path):
    tree = decompose(str(tmp_path), title="任务", domain="default")

    def good_factory(node_id):
        def fn(input_data):
            return {"ok": True, "output": {"code": "x"},
                    "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n"
                                   "@@ -0,0 +1 @@\n+x = 1\n"),
                    "artifact_type": "code_change", "verification": {"result": "PASS"}}
        return fn
    r = execute_subtask(str(tmp_path), tree["subtasks"][0], executor_factory=good_factory,
                        artifact_root=str(tmp_path))
    assert r["state"] == "COMPLETED"
    assert r["production_run_id"].startswith("prun")
    t = get_entity(str(tmp_path), tree["subtasks"][0])
    assert t["status"] == "COMPLETED"
    assert t["production_run_id"] == r["production_run_id"]


def test_execute_tree(tmp_path):
    tree = decompose(str(tmp_path), title="任务", domain="default")

    def good_factory(node_id):
        def fn(input_data):
            return {"ok": True, "output": {"code": "x"},
                    "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n"
                                   "@@ -0,0 +1 @@\n+x = 1\n"),
                    "artifact_type": "code_change", "verification": {"result": "PASS"}}
        return fn
    r = execute_tree(str(tmp_path), tree["task_tree_id"], executor_factory=good_factory,
                     artifact_root=str(tmp_path))
    assert len(r["results"]) == tree["count"]
    assert all(x["state"] == "COMPLETED" for x in r["results"])
    assert r["progress"]["percentage"] == 100
    assert "全部" in r["summary"] or r["progress"]["completed_units"] == tree["count"]


def test_execute_tree_failure_stops(tmp_path):
    tree = decompose(str(tmp_path), title="任务", domain="default")

    def bad_factory(node_id):
        def fn(input_data):
            raise RuntimeError("boom")
        return fn
    r = execute_tree(str(tmp_path), tree["task_tree_id"], executor_factory=bad_factory,
                     artifact_root=str(tmp_path))
    assert len(r["results"]) == 1  # 第一个失败即停止 (串行依赖)
    assert r["results"][0]["state"] == "FAILED"
    assert r["progress"]["percentage"] == 0


# --- CLI ---

def test_cli_tasktree(tmp_path):
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["tasktree", "decompose", "--title", "CLI 任务", "--domain", "app",
                      "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["tasktree", "list", "--data-dir", str(tmp_path)]) == 0


# --- API ---

def test_api_tasktree(tmp_path):
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.post("/api/task-trees", json={"title": "API 任务", "domain": "app"})
    assert resp.status_code == 200
    tree = resp.json()
    assert tree["task_tree_id"].startswith("task_")
    resp = client.get(f"/api/task-trees/{tree['task_tree_id']}/progress")
    assert resp.status_code == 200
    assert resp.json()["total_units"] == 6
    resp = client.get(f"/api/task-trees/{tree['task_tree_id']}/status")
    assert resp.status_code == 200
    resp = client.post(f"/api/tasks/{tree['subtasks'][0]}/status",
                       json={"status": "COMPLETED"})
    assert resp.status_code == 200
