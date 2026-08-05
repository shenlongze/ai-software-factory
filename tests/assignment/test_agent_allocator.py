"""tests/assignment/test_agent_allocator.py — AgentAllocator (assign/start/complete/fail/release 流程)。"""

from __future__ import annotations

import pytest

from agents.models import AgentStatus
from agents.registry import AgentNotFoundError, AgentRegistry
from assignment.allocator import (
    AgentAllocator,
    AgentAllocatorError,
    AgentNotAvailableError,
    AssignmentNotFoundError,
    AssignmentStateError,
    NoAvailableAgentError,
)
from assignment.models import AssignmentStatus

from assignment_helpers import make_agent, make_step


class TestAssign:
    def test_assign_creates_assignment(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = allocator.assign("T-001", step=make_step())
        assert assignment.id == "ASG-001"
        assert assignment.agent_id == "A-001"
        assert assignment.task_id == "T-001"
        assert assignment.status is AssignmentStatus.ASSIGNED
        assert assignment.completed_at is None

    def test_assign_records_step_and_workflow_refs(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = allocator.assign(
            "T-001", step=make_step(), workflow_id="feature-delivery",
        )
        assert assignment.workflow_step_id == "development"
        assert assignment.workflow_id == "feature-delivery"

    def test_assign_sets_agent_working(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        allocator.assign("T-001", step=make_step())
        agent = agent_registry.get("A-001")
        assert agent is not None
        assert agent.status is AgentStatus.WORKING
        assert agent.current_task == "T-001"

    def test_assign_auto_picks_best_candidate(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001", skills=["flutter"]))
        agent_registry.register(make_agent("A-002", skills=["development"]))
        assignment, _ = allocator.assign("T-001", step=make_step(required_skill="development"))
        assert assignment.agent_id == "A-002"

    def test_assign_explicit_agent(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = allocator.assign("T-001", agent_id="A-001")
        assert assignment.agent_id == "A-001"
        assert assignment.workflow_step_id is None

    def test_assign_explicit_agent_not_found(self, allocator: AgentAllocator):
        with pytest.raises(AgentNotFoundError):
            allocator.assign("T-001", agent_id="A-999")

    def test_assign_explicit_agent_not_available(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001", status=AgentStatus.WORKING))
        with pytest.raises(AgentNotAvailableError):
            allocator.assign("T-001", agent_id="A-001")

    def test_assign_no_available_agent(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001", role="test-engineer", skills=["testing"]))
        with pytest.raises(NoAvailableAgentError):
            allocator.assign("T-001", step=make_step())

    def test_assign_requires_agent_or_step(self, allocator: AgentAllocator):
        with pytest.raises(AgentAllocatorError):
            allocator.assign("T-001")

    def test_assign_id_auto_increments(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        a1, _ = allocator.assign("T-001", agent_id="A-001")
        agent_registry.register(make_agent("A-002"))
        a2, _ = allocator.assign("T-002", agent_id="A-002")
        assert a1.id == "ASG-001"
        assert a2.id == "ASG-002"

    def test_assign_working_agent_not_rematched(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        """已 WORKING 的 Agent 不再进入自动匹配候选 (状态必须 AVAILABLE)。"""
        agent_registry.register(make_agent("A-001"))
        allocator.assign("T-001", step=make_step())
        with pytest.raises(NoAvailableAgentError):
            allocator.assign("T-002", step=make_step())


class TestStart:
    def test_start_transitions_to_working(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = allocator.assign("T-001", step=make_step())
        started, _ = allocator.start(assignment.id)
        assert started.status is AssignmentStatus.WORKING
        assert allocator.get(assignment.id).status is AssignmentStatus.WORKING

    def test_start_requires_assigned(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = allocator.assign("T-001", step=make_step())
        allocator.start(assignment.id)
        with pytest.raises(AssignmentStateError):
            allocator.start(assignment.id)  # WORKING → WORKING 非法

    def test_start_unknown_assignment(self, allocator: AgentAllocator):
        with pytest.raises(AssignmentNotFoundError):
            allocator.start("ASG-999")


class TestComplete:
    def test_complete_transitions_and_releases_agent(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = allocator.assign("T-001", step=make_step())
        done, _ = allocator.complete(assignment.id, result="OK")
        assert done.status is AssignmentStatus.COMPLETED
        assert done.completed_at is not None
        agent = agent_registry.get("A-001")
        assert agent is not None
        assert agent.status is AgentStatus.AVAILABLE
        assert agent.current_task is None

    def test_complete_accepts_working_assignment(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = allocator.assign("T-001", step=make_step())
        allocator.start(assignment.id)
        done, _ = allocator.complete(assignment.id)
        assert done.status is AssignmentStatus.COMPLETED

    def test_complete_rejects_terminal(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = allocator.assign("T-001", step=make_step())
        allocator.complete(assignment.id)
        with pytest.raises(AssignmentStateError):
            allocator.complete(assignment.id)

    def test_complete_unknown_assignment(self, allocator: AgentAllocator):
        with pytest.raises(AssignmentNotFoundError):
            allocator.complete("ASG-999")


class TestFail:
    def test_fail_transitions_and_releases_agent(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = allocator.assign("T-001", step=make_step())
        failed, _ = allocator.fail(assignment.id, error="boom")
        assert failed.status is AssignmentStatus.FAILED
        assert failed.completed_at is not None
        agent = agent_registry.get("A-001")
        assert agent is not None
        assert agent.status is AgentStatus.AVAILABLE

    def test_fail_rejects_terminal(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = allocator.assign("T-001", step=make_step())
        allocator.fail(assignment.id)
        with pytest.raises(AssignmentStateError):
            allocator.fail(assignment.id)


class TestRelease:
    def test_release_transitions_and_releases_agent(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = allocator.assign("T-001", step=make_step())
        released, _ = allocator.release(assignment.id)
        assert released.status is AssignmentStatus.RELEASED
        assert released.completed_at is not None
        agent = agent_registry.get("A-001")
        assert agent is not None
        assert agent.status is AgentStatus.AVAILABLE

    def test_release_allows_working_assignment(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = allocator.assign("T-001", step=make_step())
        allocator.start(assignment.id)
        released, _ = allocator.release(assignment.id)
        assert released.status is AssignmentStatus.RELEASED

    def test_release_rejects_terminal(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = allocator.assign("T-001", step=make_step())
        allocator.release(assignment.id)
        with pytest.raises(AssignmentStateError):
            allocator.release(assignment.id)

    def test_release_unknown_assignment(self, allocator: AgentAllocator):
        with pytest.raises(AssignmentNotFoundError):
            allocator.release("ASG-999")


class TestQueries:
    def test_list_by_task(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        agent_registry.register(make_agent("A-002"))
        allocator.assign("T-001", agent_id="A-001")
        allocator.assign("T-002", agent_id="A-002")
        assert [a.task_id for a in allocator.list(task_id="T-001")] == ["T-001"]

    def test_list_by_agent(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        agent_registry.register(make_agent("A-002"))
        allocator.assign("T-001", agent_id="A-001")
        allocator.assign("T-002", agent_id="A-002")
        assert [a.agent_id for a in allocator.list(agent_id="A-002")] == ["A-002"]

    def test_list_by_status(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = allocator.assign("T-001", step=make_step())
        allocator.release(assignment.id)
        assert [a.id for a in allocator.list(status=AssignmentStatus.RELEASED)] == [assignment.id]

    def test_get_missing_returns_none(self, allocator: AgentAllocator):
        assert allocator.get("ASG-999") is None


class TestStateMachine:
    def test_valid_transitions(self):
        assert AgentAllocator.is_valid_transition(AssignmentStatus.ASSIGNED, AssignmentStatus.WORKING)
        assert AgentAllocator.is_valid_transition(AssignmentStatus.ASSIGNED, AssignmentStatus.RELEASED)
        assert AgentAllocator.is_valid_transition(AssignmentStatus.WORKING, AssignmentStatus.COMPLETED)
        assert AgentAllocator.is_valid_transition(AssignmentStatus.WORKING, AssignmentStatus.FAILED)

    def test_invalid_transitions(self):
        assert not AgentAllocator.is_valid_transition(AssignmentStatus.ASSIGNED, AssignmentStatus.ASSIGNED)
        assert not AgentAllocator.is_valid_transition(AssignmentStatus.COMPLETED, AssignmentStatus.RELEASED)
        assert not AgentAllocator.is_valid_transition(AssignmentStatus.FAILED, AssignmentStatus.WORKING)
        assert not AgentAllocator.is_valid_transition(AssignmentStatus.RELEASED, AssignmentStatus.ASSIGNED)
