"""分模型 prompt 模板单测 (S10-127 P1.1)。

覆盖:
- 强模型 (reasoning / 大上下文) → 完整模板 + 高收敛上限
- 弱模型 → 精简模板 + 严收敛
- pick_prompt 判定逻辑
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_MP = _ROOT / "factory-console" / "session" / "model_prompt.py"


@pytest.fixture(scope="module")
def mp():
    spec = importlib.util.spec_from_file_location("model_prompt", _MP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_strong_by_reasoning(mp):
    p = mp.pick_prompt(["code", "reasoning", "chat"], 64000)
    assert p["tier"] == "strong"
    assert p["max_tool_calls"] == mp.STRONG_MAX_TOOL_CALLS
    assert "铁律" in p["system"]


def test_strong_by_context_window(mp):
    p = mp.pick_prompt(["code", "chat"], 200000)
    assert p["tier"] == "strong"
    assert p["max_tool_calls"] == mp.STRONG_MAX_TOOL_CALLS


def test_light_small_model(mp):
    p = mp.pick_prompt(["code", "chat"], 64000)
    assert p["tier"] == "light"
    assert p["max_tool_calls"] == mp.LIGHT_MAX_TOOL_CALLS
    assert "规则" in p["system"]
    # 精简版更短
    assert len(p["system"]) < len(mp.AGENT_SYSTEM_STRONG)


def test_light_no_capabilities(mp):
    p = mp.pick_prompt(None, None)
    assert p["tier"] == "light"


def test_light_reflection_shorter(mp):
    p = mp.pick_prompt(["code"], 32000)
    assert len(p["reflection"]) < len(mp.REFLECTION_STRONG)


def test_is_strong_model(mp):
    assert mp.is_strong_model(["reasoning"], None) is True
    assert mp.is_strong_model(None, 200000) is True
    assert mp.is_strong_model(["chat"], 64000) is False
    assert mp.is_strong_model(None, None) is False
