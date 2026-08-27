"""tests/console/test_llm_intent_parser.py — LLMIntentParser 契约测试 (v1.1.20)。

覆盖: LLM 理解→注册意图 / 参数提取 / unknown→None(规则兜底) / 无key→None /
低置信→None / 非法JSON→None / 只映射注册类型(安全边界)。
"""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest

LLM_INTENT = import_module("factory-console.session.llm_intent")


def _llm(payload):
    calls = []

    def fn(prompt, operation=""):
        calls.append(prompt)
        return payload

    return fn, calls


class TestLLMIntentParser:
    def test_llm_understands_natural_language(self):
        fn, calls = _llm('{"intent_type": "org_manage", "params": {"name": "测试科技"}, "confidence": 0.9}')
        it = LLM_INTENT.LLMIntentParser(llm_fn=fn).parse("建个公司叫测试科技")
        assert it is not None
        assert it.intent_type == "org_manage"
        assert it.params.get("name") == "测试科技"
        assert it.confidence == 0.9
        assert "org_manage" in calls[0]  # prompt 含意图清单

    def test_unknown_intent_returns_none(self):
        fn, _ = _llm('{"intent_type": "unknown", "params": {}, "confidence": 0.5}')
        assert LLM_INTENT.LLMIntentParser(llm_fn=fn).parse("随便说点啥") is None

    def test_invalid_type_not_in_catalog(self):
        """安全边界: 清单外 intent_type → None (不生成任意命令)。"""
        fn, _ = _llm('{"intent_type": "delete_everything", "params": {}, "confidence": 0.9}')
        assert LLM_INTENT.LLMIntentParser(llm_fn=fn).parse("删库") is None

    def test_low_confidence_returns_none(self):
        fn, _ = _llm('{"intent_type": "list_projects", "params": {}, "confidence": 0.3}')
        assert LLM_INTENT.LLMIntentParser(llm_fn=fn).parse("随便") is None

    def test_no_llm_returns_none(self, tmp_path, monkeypatch):
        """无 key/装配失败 → None（上层规则兜底, 诚实降级）。

        hermetic: 隔离 HOME + 清空 LLM env — 本机若配置了 provider/key,
        _default_llm_fn 会懒装配出真实 LLM, 使"无 LLM"断言失效 (环境依赖)。
        """
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        for _k in (
            "LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY",
            "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY",
        ):
            monkeypatch.delenv(_k, raising=False)
        assert LLM_INTENT.LLMIntentParser(llm_fn=None)._llm() is None
        assert LLM_INTENT.LLMIntentParser(llm_fn=None).parse("建个公司") is None

    def test_llm_failure_returns_none(self):
        def boom(prompt, operation=""):
            raise RuntimeError("llm down")

        assert LLM_INTENT.LLMIntentParser(llm_fn=boom).parse("查项目") is None

    def test_invalid_json_returns_none(self):
        fn, _ = _llm("不是JSON")
        assert LLM_INTENT.LLMIntentParser(llm_fn=fn).parse("查项目") is None

    def test_code_fence_json_parsed(self):
        fn, _ = _llm('```json\n{"intent_type": "list_projects", "params": {}, "confidence": 0.9}\n```')
        it = LLM_INTENT.LLMIntentParser(llm_fn=fn).parse("查项目")
        assert it is not None and it.intent_type == "list_projects"
