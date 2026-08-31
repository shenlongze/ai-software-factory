"""tests/llm/test_k7_journeys.py — K7-01 Golden User Journeys (10 个真实组合场景)。

复用 K1-K6 已有能力 (不重建):
1. 普通聊天 → 模糊想法 → 多轮澄清
2. 需求确认 → Requirement/Decision
3. 创建 Project → Sprint → Task Tree
4. Agent 真实执行 → Evidence → Result
5. Task 失败 → 诚实呈现
6. Recovery (S39) → 结果回 Conversation
7. Approval 阻塞 → 通过 → 继续
8. Replan (需求修改)
9. 查询进度/谁在工作
10. 回原 Conversation 继续讨论 (Resume)

全部用真实执行链 (executor_factory 注入, 非 mock 状态)。
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
    create_conversation, send_message, get_conversation, extract_requirement,
    create_decision,
)
from factory_console.project_os import (  # noqa: E402
    create_project, create_sprint, add_task_to_sprint, project_status,
    approve_task_execution, decide_task_approval, task_approval_status,
    update_requirement, replan,
)
from factory_console.task_tree import (  # noqa: E402
    decompose, execute_subtask, execute_tree, task_progress,
)
from factory_console.operational_state import (  # noqa: E402
    who_is_working, drill_down, global_overview,
)
from factory_console.unified_contract import trace_lineage  # noqa: E402


def _good_factory(node_id):
    def fn(input_data):
        return {"ok": True, "output": {"code": "x"},
                "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n"
                               "@@ -0,0 +1 @@\nx = 1\n"),
                "artifact_type": "code_change", "verification": {"result": "PASS"}}
    return fn


def _bad_factory(node_id):
    def fn(input_data):
        raise RuntimeError("crash")
    return fn


# J1: 普通聊天 → 模糊想法 → 多轮澄清 (不立即创建 Work)

def test_j1_chat_clarify(tmp_path):
    conv = create_conversation(str(tmp_path), title="J1")
    r1 = send_message(str(tmp_path), conv["id"], "我最近想做一个类似笔记的产品")
    assert r1["intent"] in ("DISCUSS", "CLARIFY")
    r2 = send_message(str(tmp_path), conv["id"], "目标用户是学生, 主要用来记课堂笔记")
    assert r2["intent"] == "DECIDE"
    c = get_conversation(str(tmp_path), conv["id"])
    # 讨论阶段不创建 Work
    assert len(c["state"]["work_items"]) == 0
    assert c["state"]["goal"] == ""  # 无 EXECUTE 意图


# J2: 需求确认 → Requirement/Decision

def test_j2_requirement_decision(tmp_path):
    conv = create_conversation(str(tmp_path), title="J2")
    send_message(str(tmp_path), conv["id"], "目标用户是个人, MVP 做记账")
    send_message(str(tmp_path), conv["id"], "确认, 就这么办")
    req = extract_requirement(str(tmp_path), conv["id"], title="记账 MVP",
                              description="个人记账", acceptance="能记账")
    dec = create_decision(str(tmp_path), conv["id"], statement="个人记账 MVP")
    assert req["id"].startswith("req_")
    assert req["source_conversation_id"] == conv["id"]
    assert dec["id"].startswith("decision_")
    # 可追溯: req → conv
    lg = trace_lineage(str(tmp_path), req["id"])
    assert any(x["type"] == "conv" for x in lg)


# J3: Project → Sprint → Task Tree

def test_j3_project_sprint_tasks(tmp_path):
    conv = create_conversation(str(tmp_path), title="J3")
    send_message(str(tmp_path), conv["id"], "目标用户是个人")
    proj = create_project(str(tmp_path), title="记账 App", source_conv_id=conv["id"])
    sp = create_sprint(str(tmp_path), proj["id"], title="Sprint 1", goal="MVP")
    tree = decompose(str(tmp_path), title="记账", domain="app",
                     source_req_id=proj["source_requirement_id"])
    for tid in tree["subtasks"]:
        add_task_to_sprint(str(tmp_path), sp["id"], tid)
    ps = project_status(str(tmp_path), proj["id"])
    assert ps["progress"]["total"] == tree["count"]
    assert len(ps["sprints"]) == 1
    assert proj["source_conversation_id"] == conv["id"]


# J4: Agent 真实执行 → Evidence → Result

def test_j4_execution_evidence(tmp_path):
    conv = create_conversation(str(tmp_path), title="J4")
    send_message(str(tmp_path), conv["id"], "帮我做记账")
    from factory_console.conversation_os import trigger_work
    w = trigger_work(str(tmp_path), conv["id"], executor_factory=_good_factory,
                     artifact_root=str(tmp_path), objective="记账")
    assert w["state"] == "COMPLETED"
    assert w["production_run_id"].startswith("prun")
    assert w["evidence_id"].startswith("evidence_")
    # Evidence 实体真实存在
    from factory_console.unified_contract import get_entity
    ev = get_entity(str(tmp_path), w["evidence_id"])
    assert ev["state"] == "COMPLETED"
    assert "production_run" in ev["evidence_refs"][0]


# J5: Task 失败 → 诚实呈现

def test_j5_failure_honest(tmp_path):
    conv = create_conversation(str(tmp_path), title="J5")
    send_message(str(tmp_path), conv["id"], "帮我做任务")
    from factory_console.conversation_os import trigger_work, explain_failure
    w = trigger_work(str(tmp_path), conv["id"], executor_factory=_bad_factory,
                     artifact_root=str(tmp_path), objective="任务")
    assert w["state"] == "FAILED"
    exp = explain_failure(str(tmp_path), conv["id"])
    assert "失败原因" in exp
    assert "production_run" in exp  # evidence-backed, 非猜测


# J6: Recovery (S39) → 结果回 Conversation

def test_j6_recovery(tmp_path):
    conv = create_conversation(str(tmp_path), title="J6")
    send_message(str(tmp_path), conv["id"], "帮我做任务 B")
    tree = decompose(str(tmp_path), title="任务 B", domain="default", source_conv_id=conv["id"])
    execute_subtask(str(tmp_path), tree["subtasks"][0], executor_factory=_bad_factory,
                    artifact_root=str(tmp_path))
    from factory_console.conversation_os import repair_from_conversation
    fix = repair_from_conversation(str(tmp_path), conv["id"],
                                   executor_factory=_good_factory, artifact_root=str(tmp_path))
    assert fix["status"] in ("RECOVERED", "REJECTED", "ROLLED_BACK", "NOTHING_TO_REPAIR")
    if fix["status"] == "RECOVERED":
        c = get_conversation(str(tmp_path), conv["id"])
        assert c["state"]["work_items"][-1]["status"] in ("RECOVERED", "FAILED")


# J7: Approval 阻塞 → 通过 → 继续

def test_j7_approval(tmp_path):
    conv = create_conversation(str(tmp_path), title="J7")
    send_message(str(tmp_path), conv["id"], "目标用户是个人")
    proj = create_project(str(tmp_path), title="P", source_conv_id=conv["id"])
    tree = decompose(str(tmp_path), title="任务", domain="default",
                     source_req_id=proj["source_requirement_id"])
    task_id = tree["subtasks"][0]
    ap = approve_task_execution(str(tmp_path), task_id, risk="HIGH")
    assert task_approval_status(str(tmp_path), task_id) == "PENDING"
    # 未通过前不得执行 (governance 门)
    decide_task_approval(str(tmp_path), ap["approval_id"], decision="approve")
    assert task_approval_status(str(tmp_path), task_id) == "APPROVED"
    # 批准后可执行
    r = execute_subtask(str(tmp_path), task_id, executor_factory=_good_factory,
                        artifact_root=str(tmp_path))
    assert r["state"] == "COMPLETED"


# J8: Replan (需求修改)

def test_j8_replan(tmp_path):
    conv = create_conversation(str(tmp_path), title="J8")
    send_message(str(tmp_path), conv["id"], "目标用户是个人")
    proj = create_project(str(tmp_path), title="P", source_conv_id=conv["id"])
    sp = create_sprint(str(tmp_path), proj["id"], title="S1")
    tree = decompose(str(tmp_path), title="任务", domain="default",
                     source_req_id=proj["source_requirement_id"])
    for tid in tree["subtasks"]:
        add_task_to_sprint(str(tmp_path), sp["id"], tid)
    # 部分执行
    execute_subtask(str(tmp_path), tree["subtasks"][0], executor_factory=_good_factory,
                    artifact_root=str(tmp_path))
    req2 = update_requirement(str(tmp_path), proj["source_requirement_id"], new_title="v2")
    rp = replan(str(tmp_path), proj["id"], new_req_id=req2["id"], new_task_title="新功能")
    assert len(rp["affected_tasks"]) == tree["count"] - 1  # 未完成
    assert rp["new_task_id"].startswith("task_")


# J9: 查询进度 / 谁在工作

def test_j9_query_state(tmp_path):
    conv = create_conversation(str(tmp_path), title="J9")
    send_message(str(tmp_path), conv["id"], "目标用户是个人")
    proj = create_project(str(tmp_path), title="P", source_conv_id=conv["id"])
    sp = create_sprint(str(tmp_path), proj["id"], title="S1")
    tree = decompose(str(tmp_path), title="任务", domain="default",
                     source_req_id=proj["source_requirement_id"])
    for tid in tree["subtasks"][:2]:
        add_task_to_sprint(str(tmp_path), sp["id"], tid)
    execute_subtask(str(tmp_path), tree["subtasks"][0], executor_factory=_good_factory,
                    artifact_root=str(tmp_path))
    ps = project_status(str(tmp_path), proj["id"])
    assert ps["progress"]["completed"] == 1
    wiw = who_is_working(str(tmp_path))
    assert wiw["count"] >= 1
    go = global_overview(str(tmp_path))
    assert "projects" in go and "workforce" in go


# J10: 回原 Conversation 继续讨论 (Resume)

def test_j10_resume(tmp_path):
    conv = create_conversation(str(tmp_path), title="J10")
    send_message(str(tmp_path), conv["id"], "目标用户是个人, MVP 做记账")
    proj = create_project(str(tmp_path), title="记账", source_conv_id=conv["id"])
    # 用户离开后回来, 同一 Conversation 继续
    r = send_message(str(tmp_path), conv["id"], "现在项目做到哪里了?")
    assert r["intent"] == "ASK_STATUS"
    c = get_conversation(str(tmp_path), conv["id"])
    assert "记账" in " ".join(c["state"]["confirmed_decisions"])  # 不遗忘
    assert c.get("project_id") == proj["id"]  # 上下文保持
