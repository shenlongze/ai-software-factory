"""tests/agents/test_store.py — AgentStore/SkillStore JSON 持久化 (读写/原子写/损坏文件)。"""

from __future__ import annotations

import json
import os

import pytest

from agents.models import Agent, Skill
from agents.store import AgentStore, CorruptStoreError, SkillStore

from agent_helpers import make_agent, make_skill


# ------------------------------------------------------------------ AgentStore

def test_save_load_roundtrip(agent_store: AgentStore):
    agent_store.save(make_agent("A-001", role="backend-developer"))
    got = agent_store.load("A-001")
    assert got is not None
    assert isinstance(got, Agent)
    assert got.role == "backend-developer"


def test_load_missing_returns_none(agent_store: AgentStore):
    assert agent_store.load("A-999") is None


def test_load_all_empty(agent_store: AgentStore):
    assert agent_store.load_all() == {}


def test_load_all_sorted_and_typed(agent_store: AgentStore):
    agent_store.save(make_agent("A-002"))
    agent_store.save(make_agent("A-001"))
    all_ = agent_store.load_all()
    assert list(all_) == ["A-001", "A-002"]
    assert all(v.id == k for k, v in all_.items())


def test_save_overwrite_same_id(agent_store: AgentStore):
    agent_store.save(make_agent("A-001", role="old"))
    agent_store.save(make_agent("A-001", role="new"))
    assert agent_store.load("A-001").role == "new"
    assert agent_store.load_all().__len__() == 1


def test_remove_existing_returns_true(agent_store: AgentStore):
    agent_store.save(make_agent("A-001"))
    assert agent_store.remove("A-001") is True
    assert agent_store.load("A-001") is None


def test_remove_missing_returns_false(agent_store: AgentStore):
    assert agent_store.remove("A-999") is False


def test_store_dir_created_automatically(agent_store: AgentStore):
    assert not agent_store.dir.exists()
    agent_store.save(make_agent("A-001"))
    assert agent_store.dir.is_dir()
    assert agent_store.path.exists()


def test_file_format_is_json_object(agent_store: AgentStore):
    agent_store.save(make_agent("A-001"))
    raw = json.loads(agent_store.path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    assert "A-001" in raw


def test_corrupt_json_raises(agent_store: AgentStore):
    agent_store.dir.mkdir(parents=True, exist_ok=True)
    agent_store.path.write_text("{not json", encoding="utf-8")
    with pytest.raises(CorruptStoreError):
        agent_store.load("A-001")
    with pytest.raises(CorruptStoreError):
        agent_store.load_all()


def test_corrupt_non_object_json_raises(agent_store: AgentStore):
    agent_store.dir.mkdir(parents=True, exist_ok=True)
    agent_store.path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(CorruptStoreError, match="expected JSON object"):
        agent_store.load_all()


def test_corrupt_schema_raises(agent_store: AgentStore):
    agent_store.dir.mkdir(parents=True, exist_ok=True)
    agent_store.path.write_text(json.dumps({"A-001": {"id": "A-001"}}), encoding="utf-8")
    with pytest.raises(CorruptStoreError):
        agent_store.load("A-001")  # 缺 name/role → 模型校验失败


def test_atomic_write_no_tmp_leftover(agent_store: AgentStore):
    agent_store.save(make_agent("A-001"))
    leftovers = [p for p in agent_store.dir.iterdir() if p.name.startswith(".")]
    assert leftovers == []


def test_atomic_write_uses_replace(agent_store: AgentStore, monkeypatch):
    """写入走临时文件 + os.replace (原子替换语义)。"""
    replaced: list[str] = []
    real_replace = os.replace
    monkeypatch.setattr(os, "replace", lambda src, dst: (replaced.append(str(dst)), real_replace(src, dst))[1])
    agent_store.save(make_agent("A-001"))
    assert replaced == [str(agent_store.path)]


# ------------------------------------------------------------------ SkillStore

def test_skill_store_roundtrip(skill_store: SkillStore):
    skill_store.save(make_skill("flutter", category="frontend", version="2.0.0"))
    got = skill_store.load("flutter")
    assert got is not None
    assert isinstance(got, Skill)
    assert got.version == "2.0.0"


def test_skill_store_separate_file_from_agent(agent_store: AgentStore, skill_store: SkillStore):
    agent_store.save(make_agent("A-001"))
    skill_store.save(make_skill("flutter"))
    assert skill_store.load("A-001") is None
    assert agent_store.load("flutter") is None


def test_skill_store_corrupt_raises(skill_store: SkillStore):
    skill_store.dir.mkdir(parents=True, exist_ok=True)
    skill_store.path.write_text("###", encoding="utf-8")
    with pytest.raises(CorruptStoreError):
        skill_store.load_all()


def test_skill_store_remove(skill_store: SkillStore):
    skill_store.save(make_skill("flutter"))
    assert skill_store.remove("flutter") is True
    assert skill_store.remove("flutter") is False
