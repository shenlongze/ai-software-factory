"""流式事件单测 (U1/U2): thinking + tool 带耗时 + done。

覆盖 run_agent/run_agent_native 的 on_event 事件流 (不触发真实 LLM)。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def test_run_agent_streams_thinking_tool_done(monkeypatch):
    from factory_console.session import agent_loop as _al

    # 固定意图 (跳过 LLM 意图判定)
    monkeypatch.setattr(_al, "understand_intent", lambda *a, **k: {
        "intent": "question", "emotion": "", "label": "查状态"})

    seq = {"tools_calls": 0}
    def fake_cwt(messages, tools, **kw):
        if tools:
            seq["tools_calls"] += 1
            if seq["tools_calls"] == 1:
                return {"content": "", "tool_calls": [
                    {"id": "1", "type": "function",
                     "function": {"name": "project_scan", "arguments": "{}"}}]}
            return {"content": "最终回答", "tool_calls": []}
        return {"content": "意图OK", "tool_calls": []}

    monkeypatch.setattr(_al, "call_with_tools", fake_cwt)
    monkeypatch.setattr(_al, "dispatch", lambda *a, **k: {"ok": True, "output": "扫描OK"})

    events = []
    r = _al.run_agent("扫描项目", root="/tmp/nodir", project_id="p", llm_fn=lambda p: "",
                      on_event=events.append, max_rounds=2)
    types = [e.get("type") for e in events]
    assert "thinking" in types, types
    assert "tool" in types, types
    tool_ev = next(e for e in events if e.get("type") == "tool")
    assert tool_ev["tool"] == "project_scan"
    assert tool_ev["ok"] is True
    assert isinstance(tool_ev.get("duration_ms"), int) and tool_ev["duration_ms"] >= 0
    # done 事件由 run_agent 层发
    assert any(e.get("type") == "done" for e in events)
    assert r.get("answer") == "最终回答"
