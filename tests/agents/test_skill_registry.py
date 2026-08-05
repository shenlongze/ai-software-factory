"""tests/agents/test_skill_registry.py — SkillRegistry (register/get/list/remove + 事件)。"""

from __future__ import annotations

import pytest

from agents.models import Skill
from agents.registry import SkillExistsError, SkillNotFoundError, SkillRegistry
from events.models import EventType

from agent_helpers import make_skill


def test_register_and_get(skill_registry: SkillRegistry):
    skill_registry.register(make_skill("flutter", category="frontend"))
    got = skill_registry.get("flutter")
    assert got is not None
    assert got.category == "frontend"
    assert got.version == "1.0.0"


def test_register_duplicate_raises(skill_registry: SkillRegistry):
    skill_registry.register(make_skill("flutter"))
    with pytest.raises(SkillExistsError, match="flutter"):
        skill_registry.register(make_skill("flutter"))


def test_register_persists_to_disk(skill_registry: SkillRegistry):
    skill_registry.register(make_skill("flutter"))
    fresh = SkillRegistry(type(skill_registry.store)(skill_registry.store.dir))
    assert fresh.get("flutter") is not None


def test_register_emits_event(skill_registry: SkillRegistry, logger):
    reg = SkillRegistry(skill_registry.store, logger=logger)
    skill, ev = reg.register(make_skill("flutter", category="frontend", version="2.0.0"))
    assert ev is not None
    assert ev.type is EventType.SKILL_REGISTERED
    assert ev.source == "skill_registry"
    assert ev.stage == "frontend"
    assert ev.payload["version"] == "2.0.0"
    assert ev.payload["capabilities"] == ["java", "spring boot"]
    assert ev.seq > 0


def test_register_no_logger_returns_none_event(skill_registry: SkillRegistry):
    skill, ev = skill_registry.register(make_skill("flutter"))
    assert skill.id == "flutter"
    assert ev is None


def test_get_missing_returns_none(skill_registry: SkillRegistry):
    assert skill_registry.get("nope") is None


def test_list_sorted_by_id(skill_registry: SkillRegistry):
    skill_registry.register(make_skill("flutter"))
    skill_registry.register(make_skill("backend"))
    assert [s.id for s in skill_registry.list()] == ["backend", "flutter"]


def test_list_filter_category(skill_registry: SkillRegistry):
    skill_registry.register(make_skill("flutter", category="frontend"))
    skill_registry.register(make_skill("backend", category="backend"))
    assert [s.id for s in skill_registry.list(category="frontend")] == ["flutter"]
    assert skill_registry.list(category="nope") == []


def test_count(skill_registry: SkillRegistry):
    assert skill_registry.count() == 0
    skill_registry.register(make_skill("flutter"))
    assert skill_registry.count() == 1


def test_remove(skill_registry: SkillRegistry):
    skill_registry.register(make_skill("flutter"))
    skill, ev = skill_registry.remove("flutter")
    assert skill.id == "flutter"
    assert ev is None
    assert skill_registry.get("flutter") is None


def test_remove_missing_raises(skill_registry: SkillRegistry):
    with pytest.raises(SkillNotFoundError, match="nope"):
        skill_registry.remove("nope")


def test_remove_emits_event(skill_registry: SkillRegistry, logger):
    reg = SkillRegistry(skill_registry.store, logger=logger)
    reg.register(make_skill("flutter", category="frontend"))
    _, ev = reg.remove("flutter")
    assert ev is not None
    assert ev.type is EventType.SKILL_REMOVED
    assert ev.payload["category"] == "frontend"


def test_remove_persists_to_disk(skill_registry: SkillRegistry):
    skill_registry.register(make_skill("flutter"))
    skill_registry.remove("flutter")
    fresh = SkillRegistry(type(skill_registry.store)(skill_registry.store.dir))
    assert fresh.get("flutter") is None


def test_next_id(skill_registry: SkillRegistry):
    assert skill_registry.next_id() == "S-001"
    skill_registry.register(make_skill("S-001"))
    assert skill_registry.next_id() == "S-002"


def test_ids_sorted(skill_registry: SkillRegistry):
    skill_registry.register(make_skill("S-002"))
    skill_registry.register(make_skill("S-001"))
    assert skill_registry.ids() == ["S-001", "S-002"]
