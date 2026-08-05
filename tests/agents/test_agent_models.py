"""tests/agents/test_agent_models.py — Agent 模型 (创建/序列化/状态/技能列表)。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agents.models import Agent, AgentStatus


def test_agent_defaults():
    a = Agent(id="A-001", name="alice", role="backend-developer")
    assert a.status is AgentStatus.AVAILABLE
    assert a.skills == []
    assert a.description == ""
    assert a.current_task is None
    assert not hasattr(a, "workflow")  # 无多余字段


def test_agent_full_fields():
    a = Agent(
        id="A-001", name="alice", role="backend-developer", description="desc",
        skills=["backend", "flutter"], status="working", current_task="T-001",
    )
    assert a.status is AgentStatus.WORKING
    assert a.current_task == "T-001"
    assert a.skills == ["backend", "flutter"]


def test_agent_to_dict_json_serializable():
    a = Agent(id="A-001", name="alice", role="r", skills=["s1"])
    d = a.to_dict()
    assert d["id"] == "A-001"
    assert d["status"] == "AVAILABLE"
    assert isinstance(d["created_at"], str)  # ISO 字符串 (JSON 友好)
    assert isinstance(d["updated_at"], str)


def test_agent_roundtrip_from_dict():
    a = Agent(id="A-001", name="alice", role="r", skills=["s1"], status="offline")
    b = Agent.model_validate(a.to_dict())
    assert b == a
    assert b.status is AgentStatus.OFFLINE


def test_agent_status_parse_case_insensitive():
    assert AgentStatus.parse("working") is AgentStatus.WORKING
    assert AgentStatus.parse(" Working ") is AgentStatus.WORKING
    assert AgentStatus.parse("OFFLINE") is AgentStatus.OFFLINE
    assert AgentStatus.parse(AgentStatus.AVAILABLE) is AgentStatus.AVAILABLE


def test_agent_status_parse_invalid_raises():
    with pytest.raises(ValueError, match="invalid agent status"):
        AgentStatus.parse("bogus")


def test_agent_status_coerced_from_string():
    a = Agent(id="A-1", name="n", role="r", status="available")
    assert a.status is AgentStatus.AVAILABLE


def test_agent_status_invalid_string_rejected():
    with pytest.raises(ValidationError):
        Agent(id="A-1", name="n", role="r", status="flying")


def test_agent_id_rejects_path_separators():
    for bad in ("a/b", "..", ".", "a\\b", ""):
        with pytest.raises(ValidationError):
            Agent(id=bad, name="n", role="r")


def test_agent_skills_dedup_keep_order():
    a = Agent(id="A-1", name="n", role="r", skills=["backend", "backend", "flutter", ""])
    assert a.skills == ["backend", "flutter"]


def test_agent_timestamps_utc_aware():
    a = Agent(id="A-1", name="n", role="r")
    assert a.created_at.tzinfo is not None
    assert a.created_at.utcoffset() == timezone.utc.utcoffset(None)
    assert isinstance(a.created_at, datetime)


def test_agent_current_task_default_none_and_settable():
    a = Agent(id="A-1", name="n", role="r")
    assert a.current_task is None
    b = a.model_copy(update={"current_task": "T-042"})
    assert b.current_task == "T-042"
