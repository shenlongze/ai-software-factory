"""llm_gateway 形状转换单测 (S10-127 M1.1) — 不触发真实 API。

覆盖: provider_kind 判定 / Anthropic 形状互转 / Gemini 形状互转 / 能力协商。
"""
import importlib.util
import json
from pathlib import Path

import pytest

_GATEWAY = Path(__file__).resolve().parents[2] / "factory-console" / "session" / "llm_gateway.py"


@pytest.fixture(scope="module")
def lg():
    spec = importlib.util.spec_from_file_location("llm_gateway", _GATEWAY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _msgs():
    return [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "扫描项目"},
        {"role": "assistant", "content": "我来查",
         "tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "project_scan", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": '{"ok": true}'},
        {"role": "user", "content": "继续"},
    ]


def _tools():
    return [{"type": "function", "function": {
        "name": "project_scan", "description": "扫描项目",
        "parameters": {"type": "object", "properties": {}}}}]


def test_provider_kind(lg):
    assert lg.provider_kind("anthropic") == "anthropic"
    assert lg.provider_kind("claude") == "anthropic"
    assert lg.provider_kind("deepseek") == "openai_compat"
    assert lg.provider_kind("openai") == "openai_compat"
    assert lg.provider_kind("ollama") == "openai_compat"
    assert lg.provider_kind("gemini") == "gemini"
    assert lg.provider_kind("google") == "gemini"


def test_anthropic_roundtrip(lg):
    system, anth, at = lg._to_anthropic(_msgs(), _tools())
    assert system == "你是助手"
    assert len(anth) == 4
    # assistant: text 块 + tool_use 块
    assert anth[1]["content"][0]["type"] == "text"
    assert anth[1]["content"][1]["type"] == "tool_use"
    assert anth[1]["content"][1]["name"] == "project_scan"
    assert anth[1]["content"][1]["input"] == {}
    # tool 结果 → user/tool_result
    assert anth[2]["content"][0]["type"] == "tool_result"
    assert anth[2]["content"][0]["tool_use_id"] == "c1"
    assert at[0]["input_schema"] == {"type": "object", "properties": {}}

    resp = lg._from_anthropic({"content": [
        {"type": "text", "text": "完成"},
        {"type": "tool_use", "id": "x", "name": "project_scan", "input": {"a": 1}},
    ]})
    assert resp["content"] == "完成"
    assert resp["tool_calls"][0]["function"]["name"] == "project_scan"
    assert json.loads(resp["tool_calls"][0]["function"]["arguments"]) == {"a": 1}


def test_gemini_roundtrip(lg):
    si, contents, gt = lg._to_gemini(_msgs(), _tools())
    assert si == "你是助手"
    assert contents[0]["role"] == "user"
    assert contents[1]["role"] == "model"
    assert contents[1]["parts"][1]["functionCall"]["name"] == "project_scan"
    assert contents[2]["parts"][0]["functionResponse"]["name"] == ""
    assert gt[0]["functionDeclarations"][0]["name"] == "project_scan"

    resp = lg._from_gemini({"candidates": [{"content": {"parts": [
        {"text": "好"},
        {"functionCall": {"name": "project_scan", "args": {}}},
    ]}}]})
    assert resp["content"] == "好"
    assert resp["tool_calls"][0]["function"]["name"] == "project_scan"


def test_supports_tool_use(lg):
    assert lg.supports_tool_use(["code", "tool-use"]) is True
    assert lg.supports_tool_use(["fc"]) is True
    assert lg.supports_tool_use(["code", "chat"]) is False
    assert lg.supports_tool_use(None) is False
