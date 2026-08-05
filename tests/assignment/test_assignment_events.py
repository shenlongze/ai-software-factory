"""tests/assignment/test_assignment_events.py — Event 集成 (agent.assignment.* + agent.released)。"""

from __future__ import annotations

from agents.models import AgentStatus
from agents.registry import AgentRegistry
from assignment.allocator import AgentAllocator
from events.models import EventType
from events.store import EventStore

from assignment_helpers import make_agent, make_step


def _event_types(store: EventStore) -> list[str]:
    return [e.type.value for e in store.query()]


class TestLifecycleEvents:
    def test_assign_emits_created(self, event_allocator: AgentAllocator, agent_registry: AgentRegistry, logger):
        agent_registry.register(make_agent("A-001"))
        event_allocator.assign("T-001", step=make_step())
        assert _event_types(logger.store) == ["agent.assignment.created"]

    def test_start_emits_started(self, event_allocator: AgentAllocator, agent_registry: AgentRegistry, logger):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = event_allocator.assign("T-001", step=make_step())
        event_allocator.start(assignment.id)
        assert _event_types(logger.store) == [
            "agent.assignment.created", "agent.assignment.started",
        ]

    def test_complete_emits_completed_then_released(self, event_allocator: AgentAllocator, agent_registry: AgentRegistry, logger):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = event_allocator.assign("T-001", step=make_step())
        event_allocator.complete(assignment.id)
        assert _event_types(logger.store) == [
            "agent.assignment.created", "agent.assignment.completed", "agent.released",
        ]

    def test_fail_emits_failed_then_released(self, event_allocator: AgentAllocator, agent_registry: AgentRegistry, logger):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = event_allocator.assign("T-001", step=make_step())
        event_allocator.fail(assignment.id, error="boom")
        assert _event_types(logger.store) == [
            "agent.assignment.created", "agent.assignment.failed", "agent.released",
        ]

    def test_release_emits_released(self, event_allocator: AgentAllocator, agent_registry: AgentRegistry, logger):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = event_allocator.assign("T-001", step=make_step())
        event_allocator.release(assignment.id)
        assert _event_types(logger.store) == [
            "agent.assignment.created", "agent.released",
        ]

    def test_no_logger_no_events(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        assignment, ev = allocator.assign("T-001", step=make_step())
        assert ev is None
        _, ev = allocator.release(assignment.id)
        assert ev is None


class TestEventContent:
    def test_created_event_dimensions(self, event_allocator: AgentAllocator, agent_registry: AgentRegistry, logger):
        agent_registry.register(make_agent("A-001"))
        event_allocator.assign("T-001", step=make_step(), workflow_id="feature-delivery")
        ev = logger.store.get(1)
        assert ev.type is EventType.ASSIGNMENT_CREATED
        assert ev.source == "agent_allocator"
        assert ev.task_id == "T-001"
        assert ev.agent_id == "A-001"
        assert ev.stage == "assigned"
        assert ev.result == "OK"
        assert ev.payload["assignment_id"] == "ASG-001"
        assert ev.payload["workflow_step_id"] == "development"
        assert ev.payload["workflow_id"] == "feature-delivery"
        assert ev.payload["status"] == "ASSIGNED"
        assert ev.payload["agent_status"] == "WORKING"  # 分配即占用

    def test_released_event_agent_available(self, event_allocator: AgentAllocator, agent_registry: AgentRegistry, logger):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = event_allocator.assign("T-001", step=make_step())
        event_allocator.release(assignment.id)
        ev = logger.store.get(2)
        assert ev.type is EventType.AGENT_RELEASED
        assert ev.stage == "released"
        assert ev.payload["agent_status"] == "AVAILABLE"
        assert ev.payload["status"] == "RELEASED"

    def test_completed_event_carries_result(self, event_allocator: AgentAllocator, agent_registry: AgentRegistry, logger):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = event_allocator.assign("T-001", step=make_step())
        event_allocator.complete(assignment.id, result="OK")
        ev = logger.store.get(2)
        assert ev.type is EventType.ASSIGNMENT_COMPLETED
        assert ev.payload["result"] == "OK"
        assert ev.payload["agent_status"] == "AVAILABLE"

    def test_failed_event_carries_error(self, event_allocator: AgentAllocator, agent_registry: AgentRegistry, logger):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = event_allocator.assign("T-001", step=make_step())
        event_allocator.fail(assignment.id, error="boom")
        ev = logger.store.get(2)
        assert ev.type is EventType.ASSIGNMENT_FAILED
        assert ev.payload["error"] == "boom"
        assert ev.result == "failed"

    def test_full_lifecycle_sequence(self, event_allocator: AgentAllocator, agent_registry: AgentRegistry, logger):
        agent_registry.register(make_agent("A-001"))
        assignment, _ = event_allocator.assign("T-001", step=make_step())
        event_allocator.start(assignment.id)
        event_allocator.complete(assignment.id)
        assert _event_types(logger.store) == [
            "agent.assignment.created",
            "agent.assignment.started",
            "agent.assignment.completed",
            "agent.released",
        ]
