"""tests/console/test_execution_truth_intent.py — P0-FIX: 意图路由出口 (send_message) 校验。

场景: facts 驱动回复中, LLM 声称超越 facts (未创建却声称创建 N 个任务) → 降级。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from factory_console.console_sessions import SessionStore, send_message


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    s = SessionStore(tmp_path / "console_sessions.json")
    return s


@pytest.fixture
def sess_id(store: SessionStore) -> str:
    r = store.create_session(scope="company", title="t")
    return r["id"]


def _llm(text: str) -> str:
    return text


def test_intent_reply_with_fake_success_degraded(store: SessionStore, sess_id: str) -> None:
    """LLM 声称 '已创建 4 个任务' + facts 无任务 id → 降级标注, 不保留成功声称。"""
    r = send_message(
        store, sess_id,
        "请创建 4 个任务",
        facts="未定位到目标项目 — 请说项目名",
        llm_fn=lambda p: "好的，已将上述 4 个任务创建到任务列表。",
    )
    content = r["assistant"]["content"]
    assert "执行真实性提示" in content, f"必须降级: {content}"
    assert "已创建到任务列表" not in content or "未真实" in content or "没有真实工具执行记录" in content


def test_intent_reply_with_real_fact_allowed(store: SessionStore, sess_id: str) -> None:
    """LLM 声称 '已创建任务' + facts 含真实任务 id → 放行 (facts 是证据)。"""
    r = send_message(
        store, sess_id,
        "创建任务",
        facts="任务已创建: 数据模型 (id: TASK-abc123, 项目: 记账)。已进入待办树。",
        llm_fn=lambda p: "已为你创建任务: 数据模型 (id: TASK-abc123)。",
    )
    content = r["assistant"]["content"]
    assert "执行真实性提示" not in content, f"facts 驱动不应降级: {content}"


def test_intent_reply_count_mismatch_degraded(store: SessionStore, sess_id: str) -> None:
    """声称 4 个 + facts 只有 1 个任务 id → 降级 (partial)。"""
    r = send_message(
        store, sess_id,
        "创建 4 个任务",
        facts="任务已创建: 数据模型 (id: TASK-abc123)。",
        llm_fn=lambda p: "已创建 4 个任务。",
    )
    content = r["assistant"]["content"]
    assert "执行真实性提示" in content, f"数量不符必须降级: {content}"
