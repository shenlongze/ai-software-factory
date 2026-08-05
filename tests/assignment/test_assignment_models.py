"""tests/assignment/test_assignment_models.py — AgentAssignment 模型 (创建/序列化/状态)。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from assignment.models import AgentAssignment, AssignmentStatus


class TestAssignmentDefaults:
    def test_default_status_is_assigned(self):
        a = AgentAssignment(id="ASG-001", agent_id="A-001", task_id="T-001")
        assert a.status is AssignmentStatus.ASSIGNED
        assert a.workflow_step_id is None
        assert a.execution_id is None
        assert a.completed_at is None

    def test_create_with_all_fields(self):
        a = AgentAssignment(
            id="ASG-001", agent_id="A-001", task_id="T-001",
            workflow_id="feature-delivery", workflow_step_id="development",
            execution_id="EX-001", status=AssignmentStatus.WORKING,
        )
        assert a.id == "ASG-001"
        assert a.agent_id == "A-001"
        assert a.task_id == "T-001"
        assert a.workflow_id == "feature-delivery"
        assert a.workflow_step_id == "development"
        assert a.execution_id == "EX-001"
        assert a.status is AssignmentStatus.WORKING

    def test_timestamps_are_utc_aware(self):
        a = AgentAssignment(id="ASG-001", agent_id="A-001", task_id="T-001")
        assert a.created_at.tzinfo is not None
        assert a.updated_at.tzinfo is not None


class TestAssignmentStatus:
    def test_parse_case_insensitive(self):
        assert AssignmentStatus.parse("assigned") is AssignmentStatus.ASSIGNED
        assert AssignmentStatus.parse(" Working ") is AssignmentStatus.WORKING
        assert AssignmentStatus.parse("completed") is AssignmentStatus.COMPLETED
        assert AssignmentStatus.parse("failed") is AssignmentStatus.FAILED
        assert AssignmentStatus.parse("released") is AssignmentStatus.RELEASED

    def test_parse_enum_passthrough(self):
        assert AssignmentStatus.parse(AssignmentStatus.WORKING) is AssignmentStatus.WORKING

    def test_parse_invalid_raises(self):
        with pytest.raises(ValueError, match="invalid assignment status"):
            AssignmentStatus.parse("bogus")

    def test_status_coerced_from_string(self):
        a = AgentAssignment(
            id="ASG-001", agent_id="A-001", task_id="T-001", status="released",
        )
        assert a.status is AssignmentStatus.RELEASED

    def test_status_invalid_string_raises(self):
        with pytest.raises(ValidationError):
            AgentAssignment(id="ASG-001", agent_id="A-001", task_id="T-001", status="nope")


class TestIdValidation:
    @pytest.mark.parametrize("bad", ["", ".", "..", "a/b", "a\\b"])
    def test_id_rejects_unsafe(self, bad):
        with pytest.raises(ValidationError):
            AgentAssignment(id=bad, agent_id="A-001", task_id="T-001")

    @pytest.mark.parametrize("bad", ["", "a/b"])
    def test_agent_id_rejects_unsafe(self, bad):
        with pytest.raises(ValidationError):
            AgentAssignment(id="ASG-001", agent_id=bad, task_id="T-001")

    @pytest.mark.parametrize("bad", ["", "x/y"])
    def test_task_id_rejects_unsafe(self, bad):
        with pytest.raises(ValidationError):
            AgentAssignment(id="ASG-001", agent_id="A-001", task_id=bad)


class TestSerialization:
    def test_to_dict_json_safe(self):
        a = AgentAssignment(
            id="ASG-001", agent_id="A-001", task_id="T-001", workflow_step_id="development",
        )
        d = a.to_dict()
        assert d["id"] == "ASG-001"
        assert d["agent_id"] == "A-001"
        assert d["status"] == "ASSIGNED"
        assert isinstance(d["created_at"], str)  # ISO 字符串, JSON 友好
        assert d["completed_at"] is None

    def test_roundtrip_from_dict(self):
        a = AgentAssignment(
            id="ASG-001", agent_id="A-001", task_id="T-001",
            workflow_id="feature-delivery", workflow_step_id="development",
        )
        restored = AgentAssignment.model_validate(a.to_dict())
        assert restored == a
        assert restored.status is AssignmentStatus.ASSIGNED
