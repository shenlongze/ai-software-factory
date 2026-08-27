"""ProjectSpine + 记忆升级单测 (S10-127 M3.1/M3.2)。

覆盖:
- Spine 读写 / current_goal / requirements / handoff_card / resume / closure
- 权威分层: 低等级 (agent_claim/summary) 不注入; 高等级覆盖低等级
- Closure over replay: 只投影摘要
- 记忆 5 类 + 权威提升 + 时间衰减排序
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_HD = _ROOT / "factory-console" / "session" / "handoff.py"
_MEM = _ROOT / "factory-console" / "session" / "project_memory.py"


@pytest.fixture(scope="module")
def hd():
    spec = importlib.util.spec_from_file_location("handoff", _HD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mem():
    import sys
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    from factory_console.session import project_memory as _pm
    return _pm


def test_spine_persist_roundtrip(hd, tmp_path):
    sp = hd.ProjectSpine.load(tmp_path, "p1")
    sp.set_current_goal("把会话做成人话", source="user_intent")
    sp.set_requirement("支持切换模型", source="user_intent")
    sp.set_handoff(progress="M1 完成", next_steps=["M2"], source="verified_state")
    sp.set_resume_point(task_id="T-1", note="做到一半", source="verified_state")
    sp.add_closure(task_id="T-1", title="任务1", summary="完成了A", source="verified_state")
    sp.add_source_pointer("docs/x.md", source="repo_evidence")
    sp.save(tmp_path)

    sp2 = hd.ProjectSpine.load(tmp_path, "p1")
    assert sp2.data["current_goal"]["text"] == "把会话做成人话"
    assert sp2.data["active_requirements"][0]["text"] == "支持切换模型"
    assert sp2.data["handoff_card"]["progress"] == "M1 完成"
    assert sp2.data["resume_point"]["task_id"] == "T-1"
    assert sp2.data["closure_memory"][0]["summary"] == "完成了A"
    s = sp2.summary()
    assert s["has_goal"] and s["has_handoff"] and s["has_resume"] and s["closures"] == 1


def test_authority_filter_low_rank_not_in_view(hd, tmp_path):
    sp = hd.ProjectSpine.load(tmp_path, "p2")
    # 低权威: agent_claim / summary — view(默认 min=3) 应过滤
    sp.set_current_goal("低可信目标", source="summary")
    sp.set_handoff(progress="AI 自述进展", source="agent_claim")
    v = sp.view()
    assert "低可信目标" not in v
    assert "AI 自述进展" not in v
    # 高权威可见
    sp.set_current_goal("用户确认目标", source="user_intent")
    v2 = sp.view()
    assert "用户确认目标" in v2
    # 显式放低阈值 → agent_claim 可见
    v3 = sp.view(min_authority=2)
    assert "AI 自述进展" in v3


def test_authority_upgrade_on_requirement(hd, tmp_path):
    sp = hd.ProjectSpine.load(tmp_path, "p3")
    sp.set_requirement("做X", source="agent_claim")
    assert sp.data["active_requirements"][0]["source"] == "agent_claim"
    sp.set_requirement("做X", source="user_intent")  # 高权威覆盖
    assert sp.data["active_requirements"][0]["source"] == "user_intent"
    assert len(sp.data["active_requirements"]) == 1  # 去重


def test_closure_over_replay_only_summary(hd, tmp_path):
    sp = hd.ProjectSpine.load(tmp_path, "p4")
    sp.add_closure(task_id="T-9", title="旧任务", summary="已归档摘要", source="verified_state")
    v = sp.view()
    assert "旧任务: 已归档摘要" in v
    assert len(sp.data["closure_memory"]) == 1
    # 重复归档同任务 → 更新不新增
    sp.add_closure(task_id="T-9", title="旧任务", summary="更新摘要", source="verified_state")
    assert len(sp.data["closure_memory"]) == 1
    assert sp.data["closure_memory"][0]["summary"] == "更新摘要"


def test_memory_kinds_and_authority(mem, tmp_path):
    st = mem.MemoryStore.load(tmp_path, "p1")
    st.add("记住用Zod", kind="learning", authority="user_intent")
    st.add("报错A → 解法B", kind="error", authority="verified_state")
    st.add("普通观察", kind="observation", authority="agent_claim")
    st.save(tmp_path)

    st2 = mem.MemoryStore.load(tmp_path, "p1")
    assert len(st2.entries) == 3
    kinds = {e["kind"] for e in st2.entries}
    assert kinds == {"learning", "error", "observation"}
    # 权威提升: 同文本 observation → user_intent
    st2.add("普通观察", kind="learning", authority="user_intent")
    e = next(x for x in st2.entries if x["text"] == "普通观察")
    assert e["authority"] == "user_intent"
    assert e["kind"] == "learning"
    # 降级不覆盖
    st2.add("记住用Zod", authority="summary")
    e2 = next(x for x in st2.entries if x["text"] == "记住用Zod")
    assert e2["authority"] == "user_intent"


def test_memory_recent_authority_priority(mem, tmp_path):
    st = mem.MemoryStore.load(tmp_path, "p1")
    st.add("低权威新条目", authority="agent_claim")
    st.add("高权威旧条目", authority="user_intent")
    rec = st.recent(n=2)
    assert rec[0]["text"] == "高权威旧条目", "高权威应排前 (权威*10 主导)"


def test_memory_inject_block_labels(mem, tmp_path):
    st = mem.MemoryStore.load(tmp_path, "p1")
    st.add("带类型记忆", kind="decision", authority="verified_state")
    block = st.inject_block()
    assert "[decision|verified_state]" in block
    assert "低等级仅参考" in block
