"""tests/recovery/recovery_helpers.py — Recovery 测试数据构造 (平铺模块, 唯一名防遮蔽)。

与其他测试目录 helper 不同名 (backend-developer skill 陷阱记录); 工作流/任务/
Agent 构造自包含, 不跨目录 import (与 runtime_helpers 同款约定)。
"""

from __future__ import annotations

from agents.models import Agent
from tasks.models import Task
from workflows.models import Workflow, WorkflowStep


def make_step(step_id: str, order: int, *, skill: str | None = None,
              role: str | None = None) -> WorkflowStep:
    """构造步骤 (required_skill/required_role 可缺省 — 匹配时不限制)。"""
    return WorkflowStep(
        id=step_id, name=step_id, order=order,
        required_skill=skill, required_role=role,
    )


def make_workflow(workflow_id: str = "wf-a", *, steps: list[str] | None = None) -> Workflow:
    """构造工作流定义; 缺省两步主干 (s1, s2)。"""
    if steps is None:
        steps = ["s1", "s2"]
    return Workflow(
        id=workflow_id,
        name=f"{workflow_id} 测试",
        description="测试定义",
        steps=[WorkflowStep(id=s, name=s, order=i + 1) for i, s in enumerate(steps)],
    )


def make_task(task_id: str = "T-001", *, workflow: str | None = "wf-a", **overrides) -> Task:
    """构造任务 (直接经 Task 模型, 不走 CLI/事件)。"""
    defaults = {
        "id": task_id,
        "title": f"任务 {task_id}",
        "project": "markpad",
        "type": "feature",
        "workflow": workflow,
    }
    defaults.update(overrides)
    return Task(**defaults)


def make_agent(agent_id: str, *, role: str = "backend-developer",
               skills: list[str] | None = None) -> Agent:
    """构造 Agent (默认 AVAILABLE)。"""
    return Agent(id=agent_id, name=agent_id, role=role, skills=skills or [])
