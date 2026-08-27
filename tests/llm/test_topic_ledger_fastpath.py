"""TopicLedger 语义快路径单测 (S10-127 P1.2)。

覆盖:
- Dice 相似度: 相关话题高、无关低
- 高相似 → 直接 continue (不调 LLM, 计数为 0)
- 低相似 + 无 LLM → 相似度兜底判定
- 低相似 + LLM 可用 → 走 LLM 判定
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_TL = _ROOT / "factory-console" / "session" / "topic_ledger.py"


@pytest.fixture(scope="module")
def tl():
    spec = importlib.util.spec_from_file_location("topic_ledger", _TL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ledger(tl, label="记账App", summary="聊记账 App 的核心功能", msgs=None):
    lg = tl.TopicLedger("s1")
    lg.topics = [{"id": "t1", "label": label, "summary": summary,
                  "messages": [{"role": "user", "content": c} for c in (msgs or [])],
                  "count": 1, "last_active_at": "2026-01-01T00:00:00Z", "frozen": False}]
    return lg


def test_similarity_high_low(tl):
    lg = _ledger(tl)
    ref = lg._topic_ref(lg._active())
    high = lg._semantic_similarity("记账 App 加一个导出功能", ref)
    low = lg._semantic_similarity("今天天气怎么样", ref)
    assert high > low
    assert high >= tl.CONTINUE_SIM
    assert low < tl.SWITCH_SIM


def test_high_sim_no_llm_called(tl):
    lg = _ledger(tl)
    calls = {"n": 0}
    def fake_llm(p):
        calls["n"] += 1
        return '{"continue": false, "label": "x"}'
    d = lg._decide("记账 App 我想加个预算功能", llm_fn=fake_llm)
    assert d["continue"] is True
    assert calls["n"] == 0, "高相似必须走快路径, 不调 LLM"


def test_low_sim_no_llm_fallback(tl):
    lg = _ledger(tl)
    d = lg._decide("今天天气怎么样", llm_fn=None)
    assert d["continue"] is False  # 无 LLM + 低相似 → 切换


def test_low_sim_with_llm(tl):
    lg = _ledger(tl)
    calls = {"n": 0}
    def fake_llm(p):
        calls["n"] += 1
        return '{"continue": true}'
    d = lg._decide("今天天气怎么样", llm_fn=fake_llm)
    assert d["continue"] is True
    assert calls["n"] == 1, "低相似必须走 LLM 判定"


def test_switch_back_by_label_still_works(tl):
    lg = tl.TopicLedger("s1")
    lg.topics = [
        {"id": "t1", "label": "记账App", "summary": "记账核心", "messages": [],
         "count": 1, "last_active_at": "2026-01-01T00:00:00Z", "frozen": True},
        {"id": "t2", "label": "番茄钟", "summary": "番茄钟功能", "messages": [],
         "count": 1, "last_active_at": "2026-01-02T00:00:00Z", "frozen": False},
    ]
    # 低相似 → LLM 判定切回 t1
    d = lg._decide("我们回到记账 App 的事", llm_fn=lambda p: '{"continue": false, "label": "记账App", "switch_to": "t1"}')
    assert d["continue"] is False
    assert d["switch_to"] == "t1"
