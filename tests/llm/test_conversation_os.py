"""K1: Conversation OS Reality。

覆盖:
- 用户进入 + 多轮讨论 (Intent 理解: DISCUSS/DECIDE/APPROVE/EXECUTE/ASK_STATUS/CLARIFY)
- Goal/Topic 稳定 (不跑题)
- Decision 保留 + 用户纠正 (新 decision, 不覆盖历史)
- Requirement 提取 (req_ 实体, 可追溯 Conversation)
- Decision 实体 (decision_ 前缀)
- Work 触发 (Conversation → 真实执行 → evidence)
- Result 呈现 (说人话)
- 继续追问 (状态/为什么失败/修复)
- Golden Scenario 全链
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
    create_conversation, send_message, get_conversation, conversations,
    extract_requirement, create_decision, trigger_work, explain_failure,
    repair_from_conversation, detect_intent,
)
from factory_console.unified_contract import (  # noqa: E402
    get_entity, trace_lineage, entities,
)


def _good_factory(node_id):
    def fn(input_data):
        return {"ok": True, "output": {"code": "x"},
                "patch_text": ("diff --git a/app.py b/app.py\n--- /dev/null\n+++ b/app.py\n"
                               "@@ -0,0 +1,2 @@\n+def add():\n+    return 1\n"),
                "artifact_type": "code_change", "verification": {"result": "PASS"}}
    return fn


def _bad_factory(node_id):
    def fn(input_data):
        raise RuntimeError("crash")
    return fn


# --- 用户进入 + Intent 理解 ---

def test_user_entry_and_intent(tmp_path):
    conv = create_conversation(str(tmp_path), title="测试")
    assert conv["id"].startswith("conv_")
    assert conv["status"] == "OPEN"
    # Intent 检测 (deterministic)
    assert detect_intent("帮我做记账") == "EXECUTE"
    assert detect_intent("确认, 就这么办") == "APPROVE"
    assert detect_intent("进展怎么样") == "ASK_STATUS"
    assert detect_intent("目标用户是个人") == "DECIDE"
    assert detect_intent("我想做一个产品") == "DISCUSS"


# --- 多轮讨论 (Goal 稳定, 不跑题) ---

def test_multi_turn_discussion(tmp_path):
    conv = create_conversation(str(tmp_path), title="记账")
    r1 = send_message(str(tmp_path), conv["id"], "我想做一个产品")
    assert r1["intent"] == "DISCUSS"
    r2 = send_message(str(tmp_path), conv["id"], "主要给个人用户使用")
    assert r2["intent"] == "DISCUSS"
    r3 = send_message(str(tmp_path), conv["id"], "目标用户是个人用户, MVP 做记账功能")
    assert r3["intent"] == "DECIDE"
    # 决策保留在 state
    c = get_conversation(str(tmp_path), conv["id"])
    assert len(c["state"]["confirmed_decisions"]) >= 1
    assert "记账" in c["state"]["confirmed_decisions"][0]
    # 版本递增 (可追溯)
    assert c["version"] > 1


# --- 用户纠正 (不覆盖历史) ---

def test_user_correction(tmp_path):
    conv = create_conversation(str(tmp_path), title="t")
    send_message(str(tmp_path), conv["id"], "目标用户是个人用户")
    send_message(str(tmp_path), conv["id"], "改成企业用户")
    c = get_conversation(str(tmp_path), conv["id"])
    decisions = c["state"]["confirmed_decisions"]
    assert len(decisions) == 2  # 两条都保留 (不覆盖)
    assert "个人用户" in decisions[0]
    assert "企业用户" in decisions[1]


# --- Requirement / Decision 实体 ---

def test_requirement_decision_entities(tmp_path):
    conv = create_conversation(str(tmp_path), title="t")
    send_message(str(tmp_path), conv["id"], "目标用户是个人用户, MVP 做记账")
    req = extract_requirement(str(tmp_path), conv["id"], title="记账 MVP",
                              description="个人用户记账", acceptance="能记账")
    assert req["id"].startswith("req_")
    assert req["source_conversation_id"] == conv["id"]
    assert req["status"] == "VALIDATED"
    dec = create_decision(str(tmp_path), conv["id"], statement="个人记账 MVP")
    assert dec["id"].startswith("decision_")
    # 可追溯: req → conv
    lg = trace_lineage(str(tmp_path), req["id"])
    assert lg[0]["type"] == "req"
    assert any(x["type"] == "conv" for x in lg)


# --- Work 触发 (真实执行) ---

def test_trigger_work(tmp_path):
    conv = create_conversation(str(tmp_path), title="t")
    send_message(str(tmp_path), conv["id"], "帮我做记账 MVP")
    w = trigger_work(str(tmp_path), conv["id"], executor_factory=_good_factory,
                     artifact_root=str(tmp_path), objective="记账 MVP")
    assert w["state"] == "COMPLETED"
    assert w["task_id"].startswith("task_")
    assert w["production_run_id"].startswith("prun")
    assert w["evidence_id"].startswith("evidence_")
    assert "已完成" in w["summary"]  # 说人话
    # Evidence 真实
    ev = get_entity(str(tmp_path), w["evidence_id"])
    assert ev["state"] == "COMPLETED"
    assert "production_run" in ev["evidence_refs"][0]
    # Conversation state 更新 (可继续追问)
    c = get_conversation(str(tmp_path), conv["id"])
    assert c["state"]["work_items"][-1]["status"] == "COMPLETED"


# --- 状态追问 ---

def test_status_followup(tmp_path):
    conv = create_conversation(str(tmp_path), title="t")
    send_message(str(tmp_path), conv["id"], "帮我做任务 A")
    trigger_work(str(tmp_path), conv["id"], executor_factory=_good_factory,
                 artifact_root=str(tmp_path), objective="任务 A")
    r = send_message(str(tmp_path), conv["id"], "现在什么进展了")
    assert r["intent"] == "ASK_STATUS"
    assert "任务 A" in r["reply"]["text"]


# --- 为什么失败 (evidence-backed) + 修复 ---

def test_explain_and_repair(tmp_path):
    conv = create_conversation(str(tmp_path), title="t")
    send_message(str(tmp_path), conv["id"], "帮我做任务 B")
    w = trigger_work(str(tmp_path), conv["id"], executor_factory=_bad_factory,
                     artifact_root=str(tmp_path), objective="任务 B")
    assert w["state"] == "FAILED"
    exp = explain_failure(str(tmp_path), conv["id"])
    assert "失败原因" in exp
    assert "production_run" in exp  # evidence-backed
    # 修复 (S39 复用, 不重新开始)
    fix = repair_from_conversation(str(tmp_path), conv["id"], executor_factory=_good_factory,
                                   artifact_root=str(tmp_path))
    assert fix["status"] == "RECOVERED"
    c = get_conversation(str(tmp_path), conv["id"])
    assert c["state"]["work_items"][-1]["status"] == "RECOVERED"


# --- Golden Scenario 全链 ---

def test_golden_scenario(tmp_path):
    """「我想做 ScorePocket MVP → 讨论 → 确认 → 执行 → 测试 → 结果」。"""
    conv = create_conversation(str(tmp_path), title="ScorePocket MVP")
    send_message(str(tmp_path), conv["id"], "我想做一个 ScorePocket MVP")
    send_message(str(tmp_path), conv["id"], "先和我讨论需求")
    send_message(str(tmp_path), conv["id"], "目标用户是个人用户, MVP 做记账")
    send_message(str(tmp_path), conv["id"], "确认, 就这么办")
    req = extract_requirement(str(tmp_path), conv["id"], title="ScorePocket MVP",
                              description="个人记账", acceptance="能记账")
    dec = create_decision(str(tmp_path), conv["id"], statement="个人记账 MVP")
    w = trigger_work(str(tmp_path), conv["id"], executor_factory=_good_factory,
                     artifact_root=str(tmp_path), objective="ScorePocket MVP")
    assert w["state"] == "COMPLETED"
    # 全链可追溯
    chain = trace_lineage(str(tmp_path), w["evidence_id"])
    types = [x["type"] for x in chain]
    assert "evidence" in types and "task" in types and "conv" in types
    # 用户继续追问
    r = send_message(str(tmp_path), conv["id"], "刚才测试为什么失败?")
    assert r["intent"] == "ASK_STATUS"


# --- CLI ---

def test_cli_chat(tmp_path):
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["chat", "new", "--title", "CLI 测试", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["chat", "list", "--data-dir", str(tmp_path)]) == 0


# --- API ---

def test_api_chat(tmp_path):
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.post("/api/conversations", json={"title": "API 测试"})
    assert resp.status_code == 200
    conv = resp.json()
    assert conv["id"].startswith("conv_")
    resp = client.post(f"/api/conversations/{conv['id']}/messages",
                       json={"message": "我想做一个产品"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "DISCUSS"
    resp = client.post(f"/api/conversations/{conv['id']}/messages",
                       json={"message": "确认, 就这么办"})
    assert resp.status_code == 200
    assert resp.json()["intent"] == "APPROVE"
    resp = client.get(f"/api/conversations/{conv['id']}")
    assert resp.status_code == 200
    resp = client.get("/api/conversations")
    assert resp.status_code == 200
    resp = client.post(f"/api/conversations/{conv['id']}/requirements",
                       json={"title": "需求 A"})
    assert resp.status_code == 200
    assert resp.json()["id"].startswith("req_")
