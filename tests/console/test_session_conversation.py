"""tests/console/test_session_conversation.py — Conversation 状态模型 + Manager 基础 flow (S10-048 P3)。

设计: docs/sprint10/S10-048-intent-kernel-design.md §2.6
覆盖 (验收 A/B):
A. 初始 DISCOVERY; 识别 intent → CONFIRMATION; 未识别 → CLARIFICATION
B. transition (含非法值校验) / reset / history 记录正常
C. 基础 flow: 空输入/ slash 文本 / 默认解析器行为

basename 全仓库唯一 (test_session_* 前缀, tests/console 既有模式)。
"""

from __future__ import annotations

import importlib

import pytest

CONV_MOD = importlib.import_module("factory-console.session.conversation")
INTENT_MOD = importlib.import_module("factory-console.session.intent")


def _manager(**kw):
    return CONV_MOD.ConversationManager(**kw)


def _parser():
    return INTENT_MOD.KeywordIntentParser()


# ------------------------------------------------------------------ A: 初始状态 / 识别 / 未识别


def test_initial_state_discovery():
    """A: 初始 state = DISCOVERY, pending_intent=None, history 为空。"""
    mgr = _manager()
    assert mgr.state == CONV_MOD.ConversationState.DISCOVERY
    assert mgr.pending_intent is None
    assert mgr.history == []


def test_all_states_defined():
    """枚举完备: DISCOVERY/CLARIFICATION/PRODUCT_CONFIRMATION/CONFIRMATION/
    PROJECT_CREATION/EXECUTION/DONE (设计 §2.6 + S10-050 §2.4)。"""
    assert {s.name for s in CONV_MOD.ConversationState} == {
        "DISCOVERY",
        "CLARIFICATION",
        "PRODUCT_CONFIRMATION",
        "CONFIRMATION",
        "PROJECT_CREATION",
        "EXECUTION",
        "DONE",
    }


def test_handle_recognized_intent_goes_confirmation():
    """A: 识别 intent → 迁移 CONFIRMATION + pending_intent 挂起 + 计划确认消息。"""
    mgr = _manager()
    resp = mgr.handle("创建一个APP", _parser())
    assert resp.state == CONV_MOD.ConversationState.CONFIRMATION
    assert resp.needs_input is True
    assert "确认执行计划" in resp.message
    assert "create_project" in resp.message
    assert mgr.state == CONV_MOD.ConversationState.CONFIRMATION
    assert mgr.pending_intent is not None
    assert mgr.pending_intent.intent_type == INTENT_MOD.INTENT_CREATE_PROJECT
    assert mgr.pending_intent.parameters.get("name") == "一个APP"


def test_handle_unrecognized_goes_clarification():
    """A: 未识别 → 迁移 CLARIFICATION + 澄清提示, pending_intent 保持 None。"""
    mgr = _manager()
    resp = mgr.handle("foobar", _parser())
    assert resp.state == CONV_MOD.ConversationState.CLARIFICATION
    assert resp.needs_input is True
    assert "未识别意图" in resp.message
    assert mgr.state == CONV_MOD.ConversationState.CLARIFICATION
    assert mgr.pending_intent is None


# ------------------------------------------------------------------ B: transition / reset / history


def test_transition_changes_state_and_records_history():
    """B: transition 更新 state 并记录 history (from → to)。"""
    mgr = _manager()
    mgr.transition(CONV_MOD.ConversationState.CONFIRMATION)
    assert mgr.state == CONV_MOD.ConversationState.CONFIRMATION
    assert mgr.history[-1] == {
        "event": "transition",
        "from": "discovery",
        "to": "confirmation",
    }
    # 连续迁移 (EXECUTION → DONE) 均入史
    mgr.transition(CONV_MOD.ConversationState.EXECUTION)
    mgr.transition(CONV_MOD.ConversationState.DONE)
    assert mgr.history[-1]["to"] == "done"
    assert [h["to"] for h in mgr.history] == ["confirmation", "execution", "done"]


def test_transition_invalid_state_raises():
    """B: 非法迁移值 (非枚举) → ValueError (明确, 不静默)。"""
    mgr = _manager()
    with pytest.raises(ValueError, match="非法会话状态"):
        mgr.transition("confirmation")  # type: ignore[arg-type]


def test_handle_records_input_history():
    """B: handle 把每次输入记入 history (可审计)。"""
    mgr = _manager()
    mgr.handle("创建一个APP", _parser())
    assert mgr.history[0] == {"event": "input", "text": "创建一个APP"}
    assert mgr.history[1]["event"] == "transition"


def test_reset_restores_initial():
    """B: reset → 回到 DISCOVERY, 清空 pending_intent 与 history (全新会话)。"""
    mgr = _manager()
    mgr.handle("创建一个APP", _parser())
    assert mgr.state == CONV_MOD.ConversationState.CONFIRMATION
    mgr.reset()
    assert mgr.state == CONV_MOD.ConversationState.DISCOVERY
    assert mgr.pending_intent is None
    assert mgr.history == []


# ------------------------------------------------------------------ C: 基础 flow 边界


def test_handle_empty_input_clarification():
    """空输入 → CLARIFICATION (提示描述需求)。"""
    mgr = _manager()
    resp = mgr.handle("   ", _parser())
    assert resp.state == CONV_MOD.ConversationState.CLARIFICATION
    assert resp.needs_input is True


def test_handle_slash_keeps_state():
    """slash 文本 → 状态不变 + passthrough=True (S10-103: 宿主重分发命令注册表,
    不再死胡同消息 — 行为变化: needs_input False→True, message 空, passthrough 标记)。"""
    mgr = _manager()
    resp = mgr.handle("/status", _parser())
    assert resp.state == CONV_MOD.ConversationState.DISCOVERY
    assert resp.needs_input is True
    assert resp.passthrough is True
    assert resp.exit_requested is False
    assert resp.message == ""
    assert mgr.pending_intent is None


def test_manager_default_parser():
    """未传 parser → 内部默认 KeywordIntentParser (零配置可用)。"""
    mgr = _manager()
    resp = mgr.handle("项目列表")
    assert resp.state == CONV_MOD.ConversationState.CONFIRMATION
    assert mgr.pending_intent.intent_type == INTENT_MOD.INTENT_LIST_PROJECTS
