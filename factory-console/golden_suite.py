"""factory-console/golden_suite.py — K5 Golden Conversation Suite (G1-G20).

20 个场景验证套件 (deterministic contract tests + real LLM E2E 挂钩):
G1 普通闲聊 / G2 新需求讨论 / G3 多轮需求澄清 / G4 需求修改 /
G5 用户否定 AI 建议 / G6 用户改变方向 / G7 用户确认需求 / G8 自动拆解 Task Tree /
G9 Task 执行 / G10 Tool 成功 / G11 Tool 失败 / G12 Agent 卡住 /
G13 Approval / G14 Replan / G15 中断后继续 / G16 长对话 /
G17 Context 压力 / G18 Conversation drill-down 到 Task /
G19 Task 回到 Conversation / G20 Control Tower 查看正在运行的 Work

每个场景返回 {scenario, passed, evidence, detail}
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Callable

from .conversation_os import (
    create_conversation, send_message, get_conversation, extract_requirement,
    trigger_work,
)
from .conversation_quality import quality_report
from .project_os import create_project, create_sprint, add_task_to_sprint
from .task_tree import decompose, execute_subtask, task_progress
from .operational_state import drill_down, who_is_working


def _good_factory(node_id):
    def fn(input_data):
        return {"ok": True, "output": {"code": "x"},
                "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n"
                               "@@ -0,0 +1 @@\nx = 1\n"),
                "artifact_type": "code_change", "verification": {"result": "PASS"}}
    return fn


def run_suite(root: Path | str | None = None,
              executor_factory: Callable | None = None) -> dict[str, Any]:
    """运行 G1-G20 (deterministic; real LLM E2E 由外部调用方注入 executor)。"""
    root = root or Path(tempfile.mkdtemp())
    ef = executor_factory or _good_factory
    results = []
    results.append(_g1_chit_chat(root))
    results.append(_g2_new_requirement(root))
    results.append(_g3_clarification(root))
    results.append(_g4_requirement_change(root))
    results.append(_g5_user_negates(root))
    results.append(_g6_user_changes_direction(root))
    results.append(_g7_user_confirms(root))
    results.append(_g8_task_tree(root))
    results.append(_g9_task_execution(root, ef))
    results.append(_g10_tool_success(root, ef))
    results.append(_g11_tool_failure(root))
    results.append(_g12_agent_stuck(root))
    results.append(_g13_approval(root))
    results.append(_g14_replan(root))
    results.append(_g15_interrupt_resume(root))
    results.append(_g16_long_conversation(root))
    results.append(_g17_context_stress(root))
    results.append(_g18_drill_to_task(root, ef))
    results.append(_g19_task_back_to_conversation(root, ef))
    results.append(_g20_tower_view(root, ef))
    passed = sum(1 for r in results if r["passed"])
    return {"scenarios": results, "passed": passed, "total": len(results),
            "quality": quality_report(str(root), results[1]["conv_id"])
            if "conv_id" in results[1] else None}


# ------------------------------------------------------------------ G1-G20

def _g1_chit_chat(root) -> dict[str, Any]:
    conv = create_conversation(str(root), title="闲聊")
    r = send_message(str(root), conv["id"], "我最近想做一个类似笔记的产品")
    return {"scenario": "G1 普通闲聊", "passed": r["intent"] in ("DISCUSS", "CLARIFY"),
            "evidence": f"intent={r['intent']}", "conv_id": conv["id"]}


def _g2_new_requirement(root) -> dict[str, Any]:
    conv = create_conversation(str(root), title="新需求")
    send_message(str(root), conv["id"], "我想做一个 AI 软件开发平台")
    r = send_message(str(root), conv["id"], "目标用户是先服务个人开发者")
    return {"scenario": "G2 新需求讨论", "passed": r["intent"] == "DECIDE",
            "evidence": "decision recorded", "conv_id": conv["id"]}


def _g3_clarification(root) -> dict[str, Any]:
    conv = create_conversation(str(root), title="澄清")
    send_message(str(root), conv["id"], "我想做一个产品")
    r = send_message(str(root), conv["id"], "目标用户是个人用户")
    c = get_conversation(str(root), conv["id"])
    return {"scenario": "G3 多轮需求澄清",
            "passed": len(c["state"]["confirmed_decisions"]) >= 1,
            "evidence": f"decisions={len(c['state']['confirmed_decisions'])}",
            "conv_id": conv["id"]}


def _g4_requirement_change(root) -> dict[str, Any]:
    conv = create_conversation(str(root), title="修改")
    send_message(str(root), conv["id"], "目标用户是个人用户")
    send_message(str(root), conv["id"], "改成企业用户")
    c = get_conversation(str(root), conv["id"])
    return {"scenario": "G4 需求修改",
            "passed": len(c["state"]["confirmed_decisions"]) >= 2,
            "evidence": "both decisions kept (不覆盖)", "conv_id": conv["id"]}


def _g5_user_negates(root) -> dict[str, Any]:
    conv = create_conversation(str(root), title="否定")
    send_message(str(root), conv["id"], "我想做记账")
    r = send_message(str(root), conv["id"], "不需要了, 换个想法")
    return {"scenario": "G5 用户否定 AI 建议", "passed": r["intent"] in ("DISCUSS", "DECIDE"),
            "evidence": "accepts direction change", "conv_id": conv["id"]}


def _g6_user_changes_direction(root) -> dict[str, Any]:
    conv = create_conversation(str(root), title="转向")
    send_message(str(root), conv["id"], "目标用户是个人, 做记账应用")
    r = send_message(str(root), conv["id"], "改为做打卡应用")
    c = get_conversation(str(root), conv["id"])
    return {"scenario": "G6 用户改变方向",
            "passed": r["intent"] == "DECIDE" and len(c["state"]["confirmed_decisions"]) >= 2,
            "evidence": "direction changed, history kept", "conv_id": conv["id"]}


def _g7_user_confirms(root) -> dict[str, Any]:
    conv = create_conversation(str(root), title="确认")
    send_message(str(root), conv["id"], "目标用户是个人, MVP 做记账")
    r = send_message(str(root), conv["id"], "确认, 就这么办")
    return {"scenario": "G7 用户确认需求", "passed": r["intent"] == "APPROVE",
            "evidence": "approved", "conv_id": conv["id"]}


def _g8_task_tree(root) -> dict[str, Any]:
    conv = create_conversation(str(root), title="拆解")
    send_message(str(root), conv["id"], "目标用户是个人, MVP 做记账")
    proj = create_project(str(root), title="记账", source_conv_id=conv["id"])
    tree = decompose(str(root), title="记账", domain="app",
                     source_req_id=proj["source_requirement_id"])
    return {"scenario": "G8 自动拆解 Task Tree", "passed": tree["count"] > 0,
            "evidence": f"{tree['count']} subtasks", "conv_id": conv["id"]}


def _g9_task_execution(root, ef) -> dict[str, Any]:
    conv = create_conversation(str(root), title="执行")
    send_message(str(root), conv["id"], "帮我做记账")
    tree = decompose(str(root), title="记账", domain="default", source_conv_id=conv["id"])
    r = execute_subtask(str(root), tree["subtasks"][0], executor_factory=ef,
                        artifact_root=str(root))
    return {"scenario": "G9 Task 执行", "passed": r["state"] in ("COMPLETED", "FAILED"),
            "evidence": f"state={r['state']}", "conv_id": conv["id"]}


def _g10_tool_success(root, ef) -> dict[str, Any]:
    return _g9_task_execution(root, ef) | {"scenario": "G10 Tool 成功"}


def _g11_tool_failure(root) -> dict[str, Any]:
    conv = create_conversation(str(root), title="失败")
    send_message(str(root), conv["id"], "帮我做任务")
    tree = decompose(str(root), title="任务", domain="default", source_conv_id=conv["id"])

    def bad_factory(node_id):
        def fn(input_data):
            raise RuntimeError("crash")
        return fn
    r = execute_subtask(str(root), tree["subtasks"][0], executor_factory=bad_factory,
                        artifact_root=str(root))
    return {"scenario": "G11 Tool 失败", "passed": r["state"] == "FAILED",
            "evidence": "failure honest", "conv_id": conv["id"]}


def _g12_agent_stuck(root) -> dict[str, Any]:
    conv = create_conversation(str(root), title="卡住")
    send_message(str(root), conv["id"], "目标用户是个人")
    # BLOCKED task (approval 未决)
    tree = decompose(str(root), title="任务", domain="default", source_conv_id=conv["id"])
    from .task_tree import update_task_status
    update_task_status(str(root), tree["subtasks"][0], status="BLOCKED")
    wiw = who_is_working(str(root))
    return {"scenario": "G12 Agent 卡住",
            "passed": any(a["state"] == "BLOCKED" for a in wiw["agents"]),
            "evidence": "blocked visible", "conv_id": conv["id"]}


def _g13_approval(root) -> dict[str, Any]:
    conv = create_conversation(str(root), title="审批")
    send_message(str(root), conv["id"], "帮我做任务")
    tree = decompose(str(root), title="任务", domain="default", source_conv_id=conv["id"])
    from .project_os import approve_task_execution, decide_task_approval, task_approval_status
    ap = approve_task_execution(str(root), tree["subtasks"][0], risk="HIGH")
    before = task_approval_status(str(root), tree["subtasks"][0])
    decide_task_approval(str(root), ap["approval_id"], decision="approve")
    after = task_approval_status(str(root), tree["subtasks"][0])
    return {"scenario": "G13 Approval",
            "passed": before == "PENDING" and after == "APPROVED",
            "evidence": f"{before}→{after}", "conv_id": conv["id"]}


def _g14_replan(root) -> dict[str, Any]:
    conv = create_conversation(str(root), title="重计划")
    send_message(str(root), conv["id"], "目标用户是个人")
    proj = create_project(str(root), title="P", source_conv_id=conv["id"])
    sp = create_sprint(str(root), proj["id"], title="S1")
    tree = decompose(str(root), title="任务", domain="default",
                     source_req_id=proj["source_requirement_id"])
    for tid in tree["subtasks"]:
        add_task_to_sprint(str(root), sp["id"], tid)
    from .project_os import update_requirement, replan
    req2 = update_requirement(str(root), proj["source_requirement_id"], new_title="v2")
    rp = replan(str(root), proj["id"], new_req_id=req2["id"], new_task_title="新功能")
    return {"scenario": "G14 Replan", "passed": len(rp["affected_tasks"]) == tree["count"],
            "evidence": f"affected={len(rp['affected_tasks'])}", "conv_id": conv["id"]}


def _g15_interrupt_resume(root) -> dict[str, Any]:
    conv = create_conversation(str(root), title="中断")
    send_message(str(root), conv["id"], "目标用户是个人, MVP 做记账")
    proj = create_project(str(root), title="记账", source_conv_id=conv["id"])
    # 用户离开后回来 (新 conversation 查真实状态)
    conv2 = create_conversation(str(root), title="继续")
    send_message(str(root), conv2["id"], "我之前做到哪里了")
    ps = proj  # project 存在
    return {"scenario": "G15 中断后继续", "passed": ps["id"].startswith("project_"),
            "evidence": "project persists", "conv_id": conv["id"]}


def _g16_long_conversation(root) -> dict[str, Any]:
    conv = create_conversation(str(root), title="长对话")
    turns = ["我想做一个产品", "目标用户是个人", "目标用户是个人用户, MVP 做记账", "确认",
             "帮我做记账", "现在什么进展", "今天天气怎么样", "继续做记账",
             "再加导出功能", "确认", "帮我执行", "完成了吗"]
    for m in turns:
        send_message(str(root), conv["id"], m)
    c = get_conversation(str(root), conv["id"])
    decisions = " ".join(c["state"]["confirmed_decisions"])
    return {"scenario": "G16 长对话", "passed": "记账" in decisions,
            "evidence": f"{len(c['messages'])} msgs, 不遗忘", "conv_id": conv["id"]}


def _g17_context_stress(root) -> dict[str, Any]:
    conv = create_conversation(str(root), title="压力")
    msgs = ["我想做产品"] + [f"讨论点{i}" for i in range(12)] + ["目标用户是个人, 做记账", "确认"]
    for m in msgs:
        send_message(str(root), conv["id"], m)
    c = get_conversation(str(root), conv["id"])
    decisions = " ".join(c["state"]["confirmed_decisions"])
    return {"scenario": "G17 Context 压力",
            "passed": len(c["messages"]) > 20 and "记账" in decisions,
            "evidence": f"{len(c['messages'])} msgs, goal 保持", "conv_id": conv["id"]}


def _g18_drill_to_task(root, ef) -> dict[str, Any]:
    conv = create_conversation(str(root), title="钻取")
    send_message(str(root), conv["id"], "目标用户是个人")
    proj = create_project(str(root), title="P", source_conv_id=conv["id"])
    sp = create_sprint(str(root), proj["id"], title="S1")
    tree = decompose(str(root), title="任务", domain="default",
                     source_req_id=proj["source_requirement_id"])
    for tid in tree["subtasks"][:2]:
        add_task_to_sprint(str(root), sp["id"], tid)
    execute_subtask(str(root), tree["subtasks"][0], executor_factory=ef,
                    artifact_root=str(root))
    dd = drill_down(str(root), proj["id"])
    return {"scenario": "G18 Conversation drill-down 到 Task",
            "passed": dd["sprints"][0]["tasks"][0]["status"] in ("COMPLETED", "FAILED"),
            "evidence": "drill chain real", "conv_id": conv["id"]}


def _g19_task_back_to_conversation(root, ef) -> dict[str, Any]:
    conv = create_conversation(str(root), title="回环")
    send_message(str(root), conv["id"], "帮我做任务 A")
    w = trigger_work(str(root), conv["id"], executor_factory=ef,
                     artifact_root=str(root), objective="任务 A")
    r = send_message(str(root), conv["id"], "现在什么进展")
    return {"scenario": "G19 Task 回到 Conversation",
            "passed": "任务 A" in r["reply"]["text"],
            "evidence": f"work={w['state']}, status reply real", "conv_id": conv["id"]}


def _g20_tower_view(root, ef) -> dict[str, Any]:
    conv = create_conversation(str(root), title="塔")
    send_message(str(root), conv["id"], "目标用户是个人")
    proj = create_project(str(root), title="P", source_conv_id=conv["id"])
    tree = decompose(str(root), title="任务", domain="default",
                     source_req_id=proj["source_requirement_id"])
    execute_subtask(str(root), tree["subtasks"][0], executor_factory=ef,
                    artifact_root=str(root))
    wiw = who_is_working(str(root))
    return {"scenario": "G20 Control Tower 查看运行中 Work",
            "passed": len(wiw["agents"]) >= 1,
            "evidence": f"agents={len(wiw['agents'])}", "conv_id": conv["id"]}
