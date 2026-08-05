"""tests/assignment/test_agent_status.py — AgentRegistry 状态更新 (WORKING↔AVAILABLE, 不复制数据)。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agents.models import AgentStatus
from agents.registry import AgentNotFoundError, AgentRegistry
from assignment.allocator import AgentAllocator

from assignment_helpers import make_agent, make_step


class TestStatusPrimitives:
    def test_mark_working_sets_status(self, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        agent = agent_registry.mark_working("A-001")
        assert agent.status is AgentStatus.WORKING

    def test_mark_working_sets_current_task(self, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        agent = agent_registry.mark_working("A-001", task_id="T-001")
        assert agent.current_task == "T-001"

    def test_mark_working_without_task_keeps_task(self, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        agent = agent_registry.mark_working("A-001")
        assert agent.current_task is None

    def test_mark_available_clears_current_task(self, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        agent_registry.mark_working("A-001", task_id="T-001")
        agent = agent_registry.mark_available("A-001")
        assert agent.status is AgentStatus.AVAILABLE
        assert agent.current_task is None

    def test_set_status_generic(self, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        agent = agent_registry.set_status("A-001", AgentStatus.OFFLINE)
        assert agent.status is AgentStatus.OFFLINE
        agent = agent_registry.set_status("A-001", "available")  # 字符串宽容解析
        assert agent.status is AgentStatus.AVAILABLE

    def test_set_status_invalid_string_raises(self, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        with pytest.raises(ValueError, match="invalid agent status"):
            agent_registry.set_status("A-001", "bogus")

    def test_mark_working_unknown_agent(self, agent_registry: AgentRegistry):
        with pytest.raises(AgentNotFoundError):
            agent_registry.mark_working("A-999")

    def test_mark_available_unknown_agent(self, agent_registry: AgentRegistry):
        with pytest.raises(AgentNotFoundError):
            agent_registry.mark_available("A-999")

    def test_status_change_updates_updated_at(self, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        before = agent_registry.get("A-001").updated_at
        agent = agent_registry.mark_working("A-001")
        assert agent.updated_at >= before

    def test_status_persisted_in_store(self, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        agent_registry.mark_working("A-001", task_id="T-001")
        reloaded = agent_registry.get("A-001")
        assert reloaded is not None
        assert reloaded.status is AgentStatus.WORKING
        assert reloaded.current_task == "T-001"

    def test_list_filters_working(self, agent_registry: AgentRegistry):
        agent_registry.register(make_agent("A-001"))
        agent_registry.register(make_agent("A-002"))
        agent_registry.mark_working("A-002", task_id="T-001")
        working = agent_registry.list(status=AgentStatus.WORKING)
        assert [a.id for a in working] == ["A-002"]


class TestAllocatorIntegration:
    def test_assign_then_release_updates_registry(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        """分配层状态原语联动: assign→WORKING, release→AVAILABLE (Registry 是唯一事实源)。"""
        agent_registry.register(make_agent("A-001"))
        assignment, _ = allocator.assign("T-001", step=make_step())
        assert agent_registry.get("A-001").status is AgentStatus.WORKING
        allocator.release(assignment.id)
        assert agent_registry.get("A-001").status is AgentStatus.AVAILABLE
        assert agent_registry.get("A-001").current_task is None

    def test_assign_does_not_copy_agent_data(self, allocator: AgentAllocator, agent_registry: AgentRegistry):
        """Agent != Assignment: Assignment 只引用 agent_id, 不内嵌 Agent 字段。"""
        agent_registry.register(make_agent("A-001", name="专用名", role="backend-developer"))
        assignment, _ = allocator.assign("T-001", step=make_step())
        d = assignment.to_dict()
        assert d["agent_id"] == "A-001"
        assert "name" not in d
        assert "role" not in d
        assert "skills" not in d
        assert "status" in d  # Assignment 自身状态
