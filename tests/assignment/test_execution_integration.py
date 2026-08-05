"""tests/assignment/test_execution_integration.py — Execution 集成 (自动分配后回填 agent_id)。"""

from __future__ import annotations

import pytest

from assignment.allocator import AgentAllocator, AgentAllocatorError
from runtime.models import ExecutionRequest, ExecutionStatus
from runtime.store import RuntimeStore

from assignment_helpers import make_agent, make_step


def _make_request(runtime_store: RuntimeStore, request_id: str = "EX-001") -> ExecutionRequest:
    req = ExecutionRequest(id=request_id, task_id="T-001", workflow_id="feature-delivery",
                           step_id="development")
    runtime_store.save_execution(req)
    return req


class TestFillExecutionAgent:
    def test_assign_fills_execution_agent_id(self, exec_allocator: AgentAllocator, agent_registry, runtime_store: RuntimeStore):
        agent_registry.register(make_agent("A-001"))
        _make_request(runtime_store)
        assignment, _ = exec_allocator.assign(
            "T-001", step=make_step(), execution_id="EX-001",
        )
        assert assignment.execution_id == "EX-001"
        req = runtime_store.get_execution("EX-001")
        assert req is not None
        assert req.agent_id == "A-001"

    def test_assign_explicit_agent_fills_execution(self, exec_allocator: AgentAllocator, agent_registry, runtime_store: RuntimeStore):
        agent_registry.register(make_agent("A-001"))
        _make_request(runtime_store)
        exec_allocator.assign("T-001", agent_id="A-001", execution_id="EX-001")
        assert runtime_store.get_execution("EX-001").agent_id == "A-001"

    def test_fill_keeps_request_status_pending(self, exec_allocator: AgentAllocator, agent_registry, runtime_store: RuntimeStore):
        agent_registry.register(make_agent("A-001"))
        _make_request(runtime_store)
        exec_allocator.assign("T-001", step=make_step(), execution_id="EX-001")
        req = runtime_store.get_execution("EX-001")
        assert req is not None
        assert req.status is ExecutionStatus.PENDING  # 不自动执行, 状态不动

    def test_fill_does_not_change_other_request_fields(self, exec_allocator: AgentAllocator, agent_registry, runtime_store: RuntimeStore):
        agent_registry.register(make_agent("A-001"))
        _make_request(runtime_store)
        exec_allocator.assign("T-001", step=make_step(), execution_id="EX-001")
        req = runtime_store.get_execution("EX-001")
        assert req is not None
        assert req.task_id == "T-001"
        assert req.workflow_id == "feature-delivery"
        assert req.step_id == "development"
        assert req.input == {}

    def test_execution_fill_persisted(self, exec_allocator: AgentAllocator, agent_registry, runtimes_dir, runtime_store: RuntimeStore):
        agent_registry.register(make_agent("A-001"))
        _make_request(runtime_store)
        exec_allocator.assign("T-001", step=make_step(), execution_id="EX-001")
        fresh = RuntimeStore(runtimes_dir)
        assert fresh.get_execution("EX-001").agent_id == "A-001"

    def test_assign_execution_missing_raises(self, exec_allocator: AgentAllocator, agent_registry):
        agent_registry.register(make_agent("A-001"))
        with pytest.raises(AgentAllocatorError, match="execution not found"):
            exec_allocator.assign("T-001", step=make_step(), execution_id="EX-999")

    def test_assign_execution_missing_leaves_no_state(self, exec_allocator: AgentAllocator, agent_registry):
        """先校验后落状态: 执行不存在时 Assignment/Agent 状态均不变。"""
        agent_registry.register(make_agent("A-001"))
        with pytest.raises(AgentAllocatorError):
            exec_allocator.assign("T-001", step=make_step(), execution_id="EX-999")
        assert exec_allocator.store.load_all() == {}
        assert agent_registry.get("A-001").status.value == "AVAILABLE"

    def test_assign_without_runtime_store_skips_fill(self, allocator: AgentAllocator, agent_registry):
        """未装配 runtime_store: execution_id 仅记录引用, 不校验/不填充。"""
        agent_registry.register(make_agent("A-001"))
        assignment, _ = allocator.assign("T-001", step=make_step(), execution_id="EX-001")
        assert assignment.execution_id == "EX-001"
