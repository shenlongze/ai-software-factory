"""call_with_tools 接入 llm_gateway + 能力协商降级 (S10-127 M1.2/M1.3) — 不触发真实 API。

覆盖:
- 模型无 tool-use 能力 → tools 降级 None, 响应带 no_fc=True (不挂)
- provider/model/base_url 正确透传给 llm_gateway.complete
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from factory_console.session import agent_loop as _al


def test_call_with_tools_degrade_no_fc(monkeypatch):
    """无 FC 模型 → 不传 tools, no_fc=True, 返回纯文本。"""
    calls = {}

    def fake_resolve(data_dir, *, explicit_provider=None, explicit_model=None, need_fc=False):
        return {"provider": "deepseek", "model": "deepseek-chat",
                "base_url": "https://x/v1/chat/completions", "api_key": "k",
                "capabilities": ["chat"]}  # 无 tool-use

    def fake_complete(messages, tools, *, provider_id, model, base_url, api_key,
                      temperature, timeout):
        calls["tools"] = tools
        calls["model"] = model
        return {"content": "纯文本回答", "tool_calls": []}

    monkeypatch.setattr(_al, "_resolve_model_conf", fake_resolve)
    monkeypatch.setattr(_al._lg, "complete", fake_complete)

    r = _al.call_with_tools(
        [{"role": "user", "content": "hi"}],
        [{"type": "function", "function": {"name": "project_scan", "description": "x",
                                           "parameters": {"type": "object", "properties": {}}}}],
        data_dir="/tmp/nonexistent",
    )
    assert calls["tools"] is None, "无 FC 模型必须降级 tools"
    assert r.get("no_fc") is True
    assert r["content"] == "纯文本回答"


def test_call_with_tools_fc_model_keeps_tools(monkeypatch):
    """有 tool-use 能力 → 工具保留, 无 no_fc。"""
    calls = {}

    def fake_resolve(data_dir, *, explicit_provider=None, explicit_model=None, need_fc=False):
        return {"provider": "deepseek", "model": "deepseek-chat",
                "base_url": "https://x/v1/chat/completions", "api_key": "k",
                "capabilities": ["chat", "tool-use"]}

    def fake_complete(messages, tools, *, provider_id, model, base_url, api_key,
                      temperature, timeout):
        calls["tools"] = tools
        calls["model"] = model
        calls["provider"] = provider_id
        return {"content": "", "tool_calls": [{"id": "1", "type": "function",
                                               "function": {"name": "project_scan", "arguments": "{}"}}]}

    monkeypatch.setattr(_al, "_resolve_model_conf", fake_resolve)
    monkeypatch.setattr(_al._lg, "complete", fake_complete)

    tools = [{"type": "function", "function": {"name": "project_scan", "description": "x",
                                               "parameters": {"type": "object", "properties": {}}}}]
    r = _al.call_with_tools([{"role": "user", "content": "hi"}], tools, data_dir="/tmp/nonexistent")
    assert calls["tools"] is not None
    assert r.get("no_fc") is None
    assert r["tool_calls"][0]["function"]["name"] == "project_scan"
