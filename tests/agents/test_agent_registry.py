"""tests/agents/test_agent_registry.py — AgentRegistry (register/get/list/remove/find_by_skill + 事件)。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agents.models import Agent, AgentStatus
from agents.registry import AgentExistsError, AgentNotFoundError, AgentRegistry
from events.models import EventType

from agent_helpers import make_agent


# ------------------------------------------------------------------ register

def test_register_and_get(agent_registry: AgentRegistry):
    a = make_agent("A-001", role="backend-developer", skills=["backend"])
    agent_registry.register(a)
    got = agent_registry.get("A-001")
    assert got is not None
    assert got.id == "A-001"
    assert got.role == "backend-developer"
    assert got.skills == ["backend"]


def test_register_duplicate_raises(agent_registry: AgentRegistry):
    agent_registry.register(make_agent("A-001"))
    with pytest.raises(AgentExistsError, match="A-001"):
        agent_registry.register(make_agent("A-001"))


def test_register_persists_to_disk(agent_registry: AgentRegistry):
    agent_registry.register(make_agent("A-001"))
    # 新实例重读 (模拟重启)
    fresh = AgentRegistry(type(agent_registry.store)(agent_registry.store.dir))
    assert fresh.get("A-001") is not None


def test_register_returns_event_with_seq(agent_registry: AgentRegistry, logger):
    reg = AgentRegistry(agent_registry.store, logger=logger)
    agent, ev = reg.register(make_agent("A-001"))
    assert ev is not None
    assert ev.type is EventType.AGENT_REGISTERED
    assert ev.agent_id == "A-001"
    assert ev.source == "agent_registry"
    assert ev.stage == "available"
    assert ev.result == "OK"
    assert ev.payload["role"] == "backend-developer"
    assert ev.payload["skills"] == ["backend"]
    assert ev.seq > 0


def test_register_no_logger_returns_none_event(agent_registry: AgentRegistry):
    agent, ev = agent_registry.register(make_agent("A-001"))
    assert agent.id == "A-001"
    assert ev is None


# ------------------------------------------------------------------ get/list

def test_get_missing_returns_none(agent_registry: AgentRegistry):
    assert agent_registry.get("A-999") is None


def test_list_empty(agent_registry: AgentRegistry):
    assert agent_registry.list() == []


def test_list_sorted_by_id(agent_registry: AgentRegistry):
    agent_registry.register(make_agent("A-003"))
    agent_registry.register(make_agent("A-001"))
    agent_registry.register(make_agent("A-002"))
    assert [a.id for a in agent_registry.list()] == ["A-001", "A-002", "A-003"]


def test_list_filter_status(agent_registry: AgentRegistry):
    agent_registry.register(make_agent("A-001"))
    agent_registry.register(make_agent("A-002", status=AgentStatus.WORKING))
    assert [a.id for a in agent_registry.list(status=AgentStatus.WORKING)] == ["A-002"]
    assert [a.id for a in agent_registry.list(status="available")] == ["A-001"]


def test_list_filter_role(agent_registry: AgentRegistry):
    agent_registry.register(make_agent("A-001", role="backend-developer"))
    agent_registry.register(make_agent("A-002", role="test-engineer"))
    assert [a.id for a in agent_registry.list(role="test-engineer")] == ["A-002"]
    assert agent_registry.list(role="nobody") == []


def test_list_filter_skill(agent_registry: AgentRegistry):
    agent_registry.register(make_agent("A-001", skills=["backend"]))
    agent_registry.register(make_agent("A-002", skills=["backend", "flutter"]))
    assert [a.id for a in agent_registry.list(skill="flutter")] == ["A-002"]


def test_count(agent_registry: AgentRegistry):
    assert agent_registry.count() == 0
    agent_registry.register(make_agent("A-001"))
    agent_registry.register(make_agent("A-002"))
    assert agent_registry.count() == 2


# ------------------------------------------------------------------ find_by_skill

def test_find_by_skill(agent_registry: AgentRegistry):
    agent_registry.register(make_agent("A-001", skills=["backend"]))
    agent_registry.register(make_agent("A-002", skills=["backend", "flutter"]))
    agent_registry.register(make_agent("A-003", skills=["flutter"]))
    found = agent_registry.find_by_skill("flutter")
    assert [a.id for a in found] == ["A-002", "A-003"]


def test_find_by_skill_no_match(agent_registry: AgentRegistry):
    agent_registry.register(make_agent("A-001", skills=["backend"]))
    assert agent_registry.find_by_skill("rust") == []


def test_find_by_skill_ignores_agents_without_skills(agent_registry: AgentRegistry):
    agent_registry.register(make_agent("A-001", skills=[]))
    assert agent_registry.find_by_skill("backend") == []


def test_find_by_skill_exact_match(agent_registry: AgentRegistry):
    agent_registry.register(make_agent("A-001", skills=["Backend"]))
    assert agent_registry.find_by_skill("backend") == []  # 精确匹配, 大小写敏感


# ------------------------------------------------------------------ update

def test_update_refreshes_updated_at(agent_registry: AgentRegistry):
    a = make_agent("A-001")
    agent_registry.register(a)
    before = a.updated_at
    updated = a.model_copy(update={"role": "frontend-developer", "status": AgentStatus.WORKING})
    agent_registry.update(updated)
    got = agent_registry.get("A-001")
    assert got.role == "frontend-developer"
    assert got.status is AgentStatus.WORKING
    assert got.updated_at >= before


def test_update_missing_raises(agent_registry: AgentRegistry):
    with pytest.raises(AgentNotFoundError, match="A-999"):
        agent_registry.update(make_agent("A-999"))


def test_update_emits_event(agent_registry: AgentRegistry, logger):
    reg = AgentRegistry(agent_registry.store, logger=logger)
    reg.register(make_agent("A-001", status=AgentStatus.AVAILABLE))
    updated = make_agent("A-001", status=AgentStatus.WORKING)
    _, ev = reg.update(updated)
    assert ev is not None
    assert ev.type is EventType.AGENT_UPDATED
    assert ev.payload["from_status"] == "AVAILABLE"
    assert ev.payload["status"] == "WORKING"


# ------------------------------------------------------------------ remove

def test_remove(agent_registry: AgentRegistry):
    agent_registry.register(make_agent("A-001"))
    agent, ev = agent_registry.remove("A-001")
    assert agent.id == "A-001"
    assert ev is None  # 无 logger
    assert agent_registry.get("A-001") is None
    assert agent_registry.count() == 0


def test_remove_missing_raises(agent_registry: AgentRegistry):
    with pytest.raises(AgentNotFoundError, match="A-999"):
        agent_registry.remove("A-999")


def test_remove_emits_event(agent_registry: AgentRegistry, logger):
    reg = AgentRegistry(agent_registry.store, logger=logger)
    reg.register(make_agent("A-001", skills=["backend"]))
    _, ev = reg.remove("A-001")
    assert ev is not None
    assert ev.type is EventType.AGENT_REMOVED
    assert ev.agent_id == "A-001"
    assert ev.payload["skills"] == ["backend"]


def test_remove_persists_to_disk(agent_registry: AgentRegistry):
    agent_registry.register(make_agent("A-001"))
    agent_registry.remove("A-001")
    fresh = AgentRegistry(type(agent_registry.store)(agent_registry.store.dir))
    assert fresh.get("A-001") is None


# ------------------------------------------------------------------ 编号

def test_next_id_starts_at_001(agent_registry: AgentRegistry):
    assert agent_registry.next_id() == "A-001"


def test_next_id_increments(agent_registry: AgentRegistry):
    agent_registry.register(make_agent("A-001"))
    agent_registry.register(make_agent("A-002"))
    assert agent_registry.next_id() == "A-003"
    assert agent_registry.next_id("A-") == "A-003"


def test_next_id_ignores_foreign_prefix(agent_registry: AgentRegistry):
    agent_registry.register(make_agent("A-001"))
    agent_registry.register(make_agent("B-999"))
    assert agent_registry.next_id() == "A-002"


def test_ids_sorted(agent_registry: AgentRegistry):
    agent_registry.register(make_agent("A-003"))
    agent_registry.register(make_agent("A-001"))
    assert agent_registry.ids() == ["A-001", "A-003"]
