"""K3: Real Project Operating Loop。

覆盖:
- Conversation→Requirement→Project→Sprint→Task 全链
- Project 状态投影 (Project→Sprint→Task 各层, 实时计算)
- 执行回写 (task→sprint→project)
- Requirement v2 → Replan (识别受影响 task)
- Approval gate (阻塞/恢复; 批准→继续, 拒绝→不执行)
- 20+ 轮长对话 (不跑题/不遗忘)
- Conversation 续接 (用户回来问"做到哪里")
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

from factory_console.conversation_os import (  # noqa: E402
    create_conversation, send_message, get_conversation,
)
from factory_console.project_os import (  # noqa: E402
    create_project, create_sprint, add_task_to_sprint, project_status,
    sprint_status, projects, update_requirement, replan,
    approve_task_execution, decide_task_approval, task_approval_status,
)
from factory_console.task_tree import (  # noqa: E402
    decompose, execute_tree, execute_subtask,
)
from factory_console.unified_contract import trace_lineage, get_entity  # noqa: E402


def _good_factory(node_id):
    def fn(input_data):
        return {"ok": True, "output": {"code": "x"},
                "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n"
                               "@@ -0,0 +1 @@\nx = 1\n"),
                "artifact_type": "code_change", "verification": {"result": "PASS"}}
    return fn


def _seed_project(tmp_path):
    """完整 Project 环境: conv→req→project→sprint→task tree。"""
    conv = create_conversation(str(tmp_path), title="记账应用")
    send_message(str(tmp_path), conv["id"], "我要做一个简单的记账应用")
    proj = create_project(str(tmp_path), title="记账应用", source_conv_id=conv["id"])
    sp = create_sprint(str(tmp_path), proj["id"], title="Sprint 1", goal="记账 MVP")
    tree = decompose(str(tmp_path), title="记账 MVP", domain="app",
                     source_req_id=proj["source_requirement_id"])
    for tid in tree["subtasks"]:
        add_task_to_sprint(str(tmp_path), sp["id"], tid)
    return conv, proj, sp, tree


# --- Conversation→Requirement→Project→Sprint→Task 全链 ---

def test_project_chain(tmp_path):
    conv, proj, sp, tree = _seed_project(tmp_path)
    assert proj["id"].startswith("project_")
    assert proj["source_conversation_id"] == conv["id"]
    assert proj["source_requirement_id"].startswith("req_")
    assert sp["id"].startswith("sprint_")
    # 重读 sprint (持久化后 tasks 正确)
    from factory_console.project_os import get_sprint
    sp_live = get_sprint(str(tmp_path), sp["id"])
    assert len(sp_live["tasks"]) == tree["count"]
    # 可追溯: project → req → conv
    lg = trace_lineage(str(tmp_path), proj["id"])
    assert lg[0]["type"] == "project"
    assert any(x["type"] == "req" for x in lg)
    assert any(x["type"] == "conv" for x in lg)
    # conv 绑定 project
    c = get_conversation(str(tmp_path), conv["id"])
    assert c.get("project_id") == proj["id"]


# --- 执行回写 + Project/Sprint 状态投影 ---

def test_status_projection(tmp_path):
    conv, proj, sp, tree = _seed_project(tmp_path)
    # 执行 3 个 (部分完成)
    for tid in tree["subtasks"][:3]:
        execute_subtask(str(tmp_path), tid, executor_factory=_good_factory,
                        artifact_root=str(tmp_path))
    ps = project_status(str(tmp_path), proj["id"])
    assert ps["progress"]["completed"] == 3
    assert ps["progress"]["percentage"] == 50  # 3/6
    ss = sprint_status(str(tmp_path), sp["id"])
    assert ss["progress"]["completed"] == 3
    assert "calculated_at" in ps and "calculated_at" in ss
    # 全部完成 → 100%
    for tid in tree["subtasks"][3:]:
        execute_subtask(str(tmp_path), tid, executor_factory=_good_factory,
                        artifact_root=str(tmp_path))
    ps2 = project_status(str(tmp_path), proj["id"])
    assert ps2["progress"]["percentage"] == 100


# --- Requirement v2 → Replan ---

def test_replan(tmp_path):
    conv, proj, sp, tree = _seed_project(tmp_path)
    # 只执行 1 个 (5 个未完成)
    execute_subtask(str(tmp_path), tree["subtasks"][0], executor_factory=_good_factory,
                    artifact_root=str(tmp_path))
    req2 = update_requirement(str(tmp_path), proj["source_requirement_id"],
                              new_title="记账应用 v2", new_description="加月度统计")
    assert req2["id"].startswith("req_")
    assert req2["supersedes"] == proj["source_requirement_id"]
    assert req2["version"] > 1
    rp = replan(str(tmp_path), proj["id"], new_req_id=req2["id"],
                new_task_title="月度统计功能")
    assert len(rp["affected_tasks"]) == tree["count"] - 1  # 未完成
    assert rp["new_task_id"].startswith("task_")
    assert rp["project_id"] == proj["id"]


# --- Approval gate (阻塞/恢复) ---

def test_approval_gate(tmp_path):
    conv, proj, sp, tree = _seed_project(tmp_path)
    task_id = tree["subtasks"][0]
    # 初始无审批
    assert task_approval_status(str(tmp_path), task_id) == "NO_APPROVAL_REQUIRED"
    ap = approve_task_execution(str(tmp_path), task_id, risk="HIGH")
    assert ap["status"] == "PENDING"
    assert task_approval_status(str(tmp_path), task_id) == "PENDING"
    # Scenario A: 批准 → APPROVED (可继续)
    decide_task_approval(str(tmp_path), ap["approval_id"], decision="approve")
    assert task_approval_status(str(tmp_path), task_id) == "APPROVED"
    # Scenario B: 新 task 拒绝 → REJECTED (不执行)
    task2 = tree["subtasks"][1]
    ap2 = approve_task_execution(str(tmp_path), task2, risk="HIGH")
    decide_task_approval(str(tmp_path), ap2["approval_id"], decision="reject")
    assert task_approval_status(str(tmp_path), task2) == "REJECTED"


# --- 20+ 轮长对话 (不跑题/不遗忘) ---

def test_long_conversation(tmp_path):
    conv = create_conversation(str(tmp_path), title="长对话")
    turns = [
        "我想做一个产品", "目标用户是个人", "目标用户是个人用户, MVP 做记账", "确认",
        "帮我做记账", "现在什么进展", "今天天气怎么样", "继续做记账",
        "再加一个导出功能", "确认", "帮我执行", "测试结果如何",
        "为什么失败", "修复它", "现在状态", "加一个统计功能",
        "确认", "开始做", "完成了吗", "项目做到哪里了",
    ]
    for i, m in enumerate(turns):
        r = send_message(str(tmp_path), conv["id"], m)
        assert r["intent"] in ("DISCUSS", "DECIDE", "APPROVE", "EXECUTE", "ASK_STATUS", "CLARIFY")
    c = get_conversation(str(tmp_path), conv["id"])
    assert len(c["messages"]) == len(turns) * 2  # 消息 + 回复
    # 不遗忘: 记账决策保留
    decisions = " ".join(c["state"]["confirmed_decisions"])
    assert "记账" in decisions
    # 不跑题: goal 是记账
    assert "记账" in c["state"].get("goal", "")


# --- Conversation 续接 (用户回来问状态) ---

def test_conversation_continuation(tmp_path):
    conv, proj, sp, tree = _seed_project(tmp_path)
    # Day 1: 执行部分
    execute_subtask(str(tmp_path), tree["subtasks"][0], executor_factory=_good_factory,
                    artifact_root=str(tmp_path))
    # Day 2: 用户回来 (新 conversation, 基于真实 Project State)
    conv2 = create_conversation(str(tmp_path), title="继续")
    send_message(str(tmp_path), conv2["id"], "我之前做到哪里了?")
    ps = project_status(str(tmp_path), proj["id"])
    assert ps["progress"]["completed"] == 1
    assert ps["progress"]["total"] == tree["count"]
    # 答案来自真实投影 (非 conversation memory)
    assert ps["title"] == "记账应用"
    assert ps["source_conversation_id"] == conv["id"]


# --- CLI ---

def test_cli_project(tmp_path):
    conv, proj, sp, tree = _seed_project(tmp_path)
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["projectos", "list", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["projectos", "status", proj["id"], "--data-dir", str(tmp_path)]) == 0


# --- API ---

def test_api_project(tmp_path):
    conv, proj, sp, tree = _seed_project(tmp_path)
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.get(f"/api/projects-os/{proj['id']}/status")
    assert resp.status_code == 200
    assert resp.json()["progress"]["total"] == tree["count"]
    # 创建新 project via API
    resp = client.post("/api/projects-os", json={"title": "API 项目",
                                                 "source_conversation_id": conv["id"]})
    assert resp.status_code == 200
    assert resp.json()["id"].startswith("project_")
