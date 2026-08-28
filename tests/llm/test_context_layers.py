"""L0/L1/L2 分层上下文加载单测 (S10-127 P1.3)。

覆盖:
- pick_depth: 极端小窗口→l0; 弱模型→l1; 强模型→l2
- build_context: l0 只含目标/归档; l1 含交接/需求/记忆; l2 含更多
- 空项目 → 空串 (不崩)
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_CL = _ROOT / "factory-console" / "session" / "context_layers.py"


@pytest.fixture(scope="module")
def cl():
    import sys
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    from factory_console.session import context_layers as _cl
    return _cl


def test_pick_depth(cl):
    assert cl.pick_depth("light", 32000) == "l1"
    assert cl.pick_depth(None, 8000) == "l0"
    assert cl.pick_depth("strong", 200000) == "l2"
    assert cl.pick_depth(None, None) == "l2"


def test_build_l0_only_summary(cl, tmp_path):
    from factory_console.session.handoff import ProjectSpine

    sp = ProjectSpine.load(tmp_path, "p1")
    sp.set_current_goal("把会话做成人话", source="user_intent")
    sp.add_closure(task_id="T-1", title="M1模型适配", summary="完成", source="verified_state")
    sp.save(tmp_path)
    block = cl.build_context(str(tmp_path), "p1", depth="l0")
    assert "当前目标: 把会话做成人话" in block
    assert "M1模型适配" in block
    assert "上次进展" not in block  # L0 不含 L1 内容


def test_build_l1_adds_handoff_memory(cl, tmp_path):
    from factory_console.session.handoff import ProjectSpine
    from factory_console.session.project_memory import MemoryStore

    sp = ProjectSpine.load(tmp_path, "p1")
    sp.set_current_goal("做X", source="user_intent")
    sp.set_handoff(progress="M1完成", source="verified_state")
    sp.save(tmp_path)
    mem = MemoryStore.load(tmp_path, "p1")
    mem.add("记住用Pydantic", kind="learning", authority="user_intent")
    mem.save(tmp_path)

    block = cl.build_context(str(tmp_path), "p1", depth="l1")
    assert "上次进展: M1完成" in block
    assert "记住用Pydantic" in block
    assert block.startswith("【项目上下文】(L1)")


def test_build_l2_more_memory(cl, tmp_path):
    from factory_console.session.handoff import ProjectSpine
    from factory_console.session.project_memory import MemoryStore

    sp = ProjectSpine.load(tmp_path, "p1")
    sp.set_current_goal("做X", source="user_intent")
    sp.save(tmp_path)
    mem = MemoryStore.load(tmp_path, "p1")
    for i in range(6):
        mem.add(f"记忆条目{i}", kind="learning", authority="agent_claim")
    mem.save(tmp_path)

    l1 = cl.build_context(str(tmp_path), "p1", depth="l1")
    l2 = cl.build_context(str(tmp_path), "p1", depth="l2")
    # L1 只带最近 3 条 (不含最早); L2 带 8 条 (含最早)
    assert "记忆条目0" not in l1
    assert "记忆条目0" in l2


def test_empty_project_no_crash(cl, tmp_path):
    assert cl.build_context(str(tmp_path), "ghost") == ""


def test_t9_query_prioritizes_relevant_memory(cl, tmp_path):
    """T9: query → 相关记忆优先召回 (关键词加权)。"""
    from factory_console.session.project_memory import MemoryStore

    mem = MemoryStore.load(tmp_path, "p1")
    mem.add("版本号统一用 pyproject 作为唯一真源", kind="decision", authority="verified_state")
    mem.add("今天天气不错适合散步", kind="observation")
    mem.save(tmp_path)

    # 无 query → 高权威(verified_state)优先
    top = mem.recent(3)
    assert "版本号" in top[0]["text"]
    # query=版本 → 相关记忆仍优先 (关键词加权叠加)
    topq = mem.recent(3, query="版本管理方案")
    assert "版本号" in topq[0]["text"]
    # build_context 透传 query → 相关记忆排在天气前 (召回是排序非过滤)
    ctx = cl.build_context(str(tmp_path), "p1", depth="l1", query="版本管理")
    assert "版本号" in ctx
    assert ctx.index("版本号") < ctx.index("天气")


def test_t9_query_tokens_chinese_bigrams():
    """T9: 中文 2-gram / 英文整词分词。"""
    from factory_console.session.project_memory import _query_tokens

    zh = _query_tokens("版本管理")
    assert "版本" in zh and "管理" in zh
    en = _query_tokens("fix the bug")
    assert "fix" in en and "bug" in en
