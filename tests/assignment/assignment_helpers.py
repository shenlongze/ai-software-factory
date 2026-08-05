"""tests/assignment/assignment_helpers.py — Agent/Assignment/Step 构造 helper (测试共享)。"""

from __future__ import annotations

from agents.models import Agent
from assignment.models import AgentAssignment, AssignmentStatus
from workflows.models import WorkflowStep


def make_agent(agent_id: str = "A-001", **overrides) -> Agent:
    """默认 backend-developer/development Agent; overrides 覆盖任意字段。"""
    defaults = {
        "id": agent_id,
        "name": f"agent {agent_id}",
        "role": "backend-developer",
        "description": "默认测试 Agent",
        "skills": ["development"],
    }
    defaults.update(overrides)
    return Agent(**defaults)


def make_step(
    step_id: str = "development",
    *,
    name: str | None = None,
    order: int = 1,
    required_skill: str | None = "development",
    required_role: str | None = "backend-developer",
) -> WorkflowStep:
    """默认 development 步骤 (feature-delivery 内置定义同款声明)。"""
    return WorkflowStep(
        id=step_id, name=name or step_id, order=order,
        required_skill=required_skill, required_role=required_role,
    )


def make_assignment(assignment_id: str = "ASG-001", **overrides) -> AgentAssignment:
    """默认 ASSIGNED 工作关系; overrides 覆盖任意字段。"""
    defaults = {
        "id": assignment_id,
        "agent_id": "A-001",
        "task_id": "T-001",
        "workflow_id": "feature-delivery",
        "workflow_step_id": "development",
        "status": AssignmentStatus.ASSIGNED,
    }
    defaults.update(overrides)
    return AgentAssignment(**defaults)
