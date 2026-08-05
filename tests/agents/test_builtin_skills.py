"""tests/agents/test_builtin_skills.py — 内置技能目录辅助。"""

from __future__ import annotations

from agents.models import Skill
from agents.skills import BUILTIN_SKILLS, builtin_skill, builtin_skill_ids


def test_builtin_skill_ids_sorted():
    ids = builtin_skill_ids()
    assert ids == sorted(ids)
    assert "flutter" in ids


def test_builtin_skill_returns_model():
    s = builtin_skill("flutter")
    assert s is not None
    assert isinstance(s, Skill)
    assert s.id == "flutter"
    assert s.category == "frontend"
    assert s.capabilities  # 能力描述非空


def test_builtin_skill_missing_returns_none():
    assert builtin_skill("nope") is None


def test_builtin_catalog_shape():
    for skill_id, data in BUILTIN_SKILLS.items():
        assert data["name"] == skill_id
        assert "category" in data
        assert "description" in data
        assert "capabilities" in data
        assert "version" in data
