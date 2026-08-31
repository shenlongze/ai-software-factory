"""K9 Workspace: GET /api/projects-os 列表投影 (SSOT, 无第二套状态)。"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console import project_os as _po  # noqa: E402
from factory_console.conversation_os import create_conversation  # noqa: E402


def test_list_projects_returns_created(tmp_path):
    conv = create_conversation(str(tmp_path), title="P")
    _po.create_project(str(tmp_path), title="项目A", source_conv_id=conv["id"])
    _po.create_project(str(tmp_path), title="项目B", source_conv_id=conv["id"])
    items = _po.projects(str(tmp_path))
    assert len(items) == 2
    assert {p["title"] for p in items} == {"项目A", "项目B"}
    # 字段契约: id/title/status/source_conversation_id
    assert all(p["id"].startswith("project_") for p in items)
    assert all("source_conversation_id" in p for p in items)


def test_list_empty(tmp_path):
    assert _po.projects(str(tmp_path)) == []


def test_list_after_create_sprint(tmp_path):
    conv = create_conversation(str(tmp_path), title="P")
    proj = _po.create_project(str(tmp_path), title="项目", source_conv_id=conv["id"])
    _po.create_sprint(str(tmp_path), proj["id"], title="S1")
    items = _po.projects(str(tmp_path))
    assert len(items) == 1


# ─── K9 消息卡片打通: reply 带 card payload (前端 MessageCardView 消费) ───

def test_reply_carries_card_discuss(tmp_path):
    from factory_console.conversation_os import create_conversation, send_message
    conv = create_conversation(str(tmp_path), title="卡片")
    r = send_message(str(tmp_path), conv["id"], "我想做台球计分")
    assert r["intent"] == "DISCUSS"
    assert r["reply"].get("card", {}).get("type") == "analysis"
    assert "done" in r["reply"]["card"] and "pending" in r["reply"]["card"]


def test_reply_carries_card_decision(tmp_path):
    from factory_console.conversation_os import create_conversation, send_message
    conv = create_conversation(str(tmp_path), title="卡片2")
    send_message(str(tmp_path), conv["id"], "我想做台球计分")
    r = send_message(str(tmp_path), conv["id"], "目标用户是个人玩家")
    assert r["intent"] == "DECIDE"
    assert r["reply"].get("card", {}).get("type") == "prd"
    assert "summary" in r["reply"]["card"]


def test_reply_carries_card_execute(tmp_path):
    from factory_console.conversation_os import create_conversation, send_message
    conv = create_conversation(str(tmp_path), title="卡片3")
    send_message(str(tmp_path), conv["id"], "帮我做台球计分")
    r = send_message(str(tmp_path), conv["id"], "开始做")
    assert r["intent"] == "EXECUTE"
    assert r["reply"].get("card", {}).get("type") == "execution"


def test_reply_carries_card_status(tmp_path):
    from factory_console.conversation_os import create_conversation, send_message
    conv = create_conversation(str(tmp_path), title="卡片4")
    send_message(str(tmp_path), conv["id"], "帮我做台球计分")
    r = send_message(str(tmp_path), conv["id"], "现在什么进展")
    assert r["intent"] == "ASK_STATUS"
    assert r["reply"].get("card", {}).get("type") == "task_tree"


# ─── 用户实测回归: "我有哪些项目" 必须走 ASK_STATUS (非 DISCUSS) ───

def test_query_projects_is_ask_status(tmp_path):
    from factory_console.conversation_os import create_conversation, send_message
    conv = create_conversation(str(tmp_path), title="查询")
    r = send_message(str(tmp_path), conv["id"], "我有哪些项目")
    assert r["intent"] == "ASK_STATUS", f"应为 ASK_STATUS, 实得 {r['intent']}"
    assert "项目" in r["reply"]["text"]


def test_query_projects_returns_real_list(tmp_path):
    from factory_console.conversation_os import create_conversation, send_message
    from factory_console.project_os import create_project
    conv = create_conversation(str(tmp_path), title="查询2")
    create_project(str(tmp_path), title="台球计分", source_conv_id=conv["id"])
    r = send_message(str(tmp_path), conv["id"], "我有哪些项目")
    assert r["intent"] == "ASK_STATUS"
    assert "台球计分" in r["reply"]["text"]


def test_greeting_still_discuss(tmp_path):
    from factory_console.conversation_os import create_conversation, send_message
    conv = create_conversation(str(tmp_path), title="问候")
    r = send_message(str(tmp_path), conv["id"], "你好")
    assert r["intent"] == "DISCUSS"


def test_execute_still_works(tmp_path):
    from factory_console.conversation_os import create_conversation, send_message
    conv = create_conversation(str(tmp_path), title="执行")
    r = send_message(str(tmp_path), conv["id"], "帮我做计算器")
    assert r["intent"] == "EXECUTE"
