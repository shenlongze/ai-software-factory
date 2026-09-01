"""tests/console/test_session_cancel.py — F-01: 会话消息执行取消。

覆盖:
- request_session_cancel 幂等 (重复 request 无副作用)
- session_cancelled 会话隔离 (A 取消不影响 B)
- clear_session_cancel 清理
- cancel API 端点 (fastapi): 404 (无会话) / CANCELLING (有会话)
- run_agent_native 取消: 循环边界检查 → 返回 cancelled
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from factory_console import run_liveness


# ---------------------------------------------------------------- run_liveness


def test_request_cancel_idempotent() -> None:
    run_liveness.clear_session_cancel("sess-a")
    assert run_liveness.request_session_cancel("sess-a") is True
    assert run_liveness.session_cancelled("sess-a") is True
    # 重复 request 无害
    assert run_liveness.request_session_cancel("sess-a") is True
    assert run_liveness.session_cancelled("sess-a") is True
    run_liveness.clear_session_cancel("sess-a")
    assert run_liveness.session_cancelled("sess-a") is False


def test_session_cancel_isolation() -> None:
    run_liveness.clear_session_cancel("sess-a")
    run_liveness.clear_session_cancel("sess-b")
    run_liveness.request_session_cancel("sess-a")
    assert run_liveness.session_cancelled("sess-a") is True
    assert run_liveness.session_cancelled("sess-b") is False  # B 不受影响
    run_liveness.clear_session_cancel("sess-a")


def test_session_cancel_distinct_from_run_cancel() -> None:
    """session cancel 与 workflow run cancel key 互不串扰。"""
    run_liveness.clear_session_cancel("sess-x")
    run_liveness.clear_cancel("P-1", "R-1")
    run_liveness.request_cancel("P-1", "R-1")
    assert run_liveness.is_cancelled("P-1", "R-1") is True
    assert run_liveness.session_cancelled("sess-x") is False  # session 未取消
    run_liveness.clear_cancel("P-1", "R-1")


# ---------------------------------------------------------------- run_agent_native 取消


def test_run_agent_native_returns_cancelled_when_requested(monkeypatch: Any, tmp_path: Path) -> None:
    """循环边界检查: 第一轮工具执行后设置取消, 第二轮循环顶部停止并返回 cancelled。"""
    from factory_console.session import agent_loop

    state = {"calls": 0}

    def fake_call_with_tools(messages, tools, **kwargs):
        state["calls"] += 1
        if state["calls"] == 1:
            # 第一轮发起真实工具调用 → agent_loop 执行 dispatch → 进入第二轮循环顶部
            return {"content": "", "tool_calls": [
                {"id": "t1", "function": {"name": "project_list", "arguments": "{}"}}
            ], "usage": {}}
        return {"content": "第二轮回答", "tool_calls": [], "usage": {}}

    monkeypatch.setattr(agent_loop, "call_with_tools", fake_call_with_tools)
    monkeypatch.setattr(agent_loop, "understand_intent",
                        lambda *a, **k: {"intent": "chat", "summary": "", "correction": False,
                                         "mode": "general", "emotion": ""})
    monkeypatch.setattr(agent_loop, "_simple_llm", lambda *a, **k: "{}")

    # 工具执行 (dispatch project_list) 时设置取消 → 第二轮循环顶部检查到
    orig_dispatch = agent_loop.dispatch

    def fake_dispatch(tool_id, args, **kwargs):
        if tool_id == "project_list":
            run_liveness.request_session_cancel("sess-cancel-test")
        return orig_dispatch(tool_id, args, **kwargs)

    monkeypatch.setattr(agent_loop, "dispatch", fake_dispatch)

    run_liveness.clear_session_cancel("sess-cancel-test")
    result = agent_loop.run_agent_native(
        "测试取消", data_dir=str(tmp_path), project_id="", service=None,
        session_id="sess-cancel-test", max_rounds=3,
    )
    assert result.get("cancelled") is True
    assert "已停止" in str(result.get("answer") or "")
    run_liveness.clear_session_cancel("sess-cancel-test")


# ---------------------------------------------------------------- cancel API 端点


def test_cancel_api_endpoint() -> None:
    """POST /api/sessions/{id}/cancel → CANCELLING; 无会话 → 404。"""
    from fastapi.testclient import TestClient

    from factory_console.web.backend.fastapi_adapter import create_app

    app = create_app(factory_root=str(tmp_root()))
    with TestClient(app) as c:
        # 无会话 → 404
        r404 = c.post("/api/sessions/nonexistent/cancel")
        assert r404.status_code == 404
        # 创建会话 → cancel → CANCELLING
        r = c.post("/api/sessions", json={"scope": "company", "title": "cancel-test"})
        assert r.status_code == 200
        sid = r.json()["id"]
        rc = c.post(f"/api/sessions/{sid}/cancel")
        assert rc.status_code == 200
        body = rc.json()
        assert body["ok"] is True
        assert body["status"] == "CANCELLING"
        # 幂等: 重复 cancel 仍 200
        rc2 = c.post(f"/api/sessions/{sid}/cancel")
        assert rc2.status_code == 200
        run_liveness.clear_session_cancel(sid)


def tmp_root() -> Path:
    import tempfile

    return Path(tempfile.mkdtemp(prefix="cancel-test-"))
