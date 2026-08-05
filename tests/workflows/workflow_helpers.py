"""tests/workflows/workflow_helpers.py — Workflow 测试数据构造。"""

from __future__ import annotations

from tasks.models import Task
from workflows.models import Workflow, WorkflowStep

FEATURE_STEP_IDS = ["architecture", "development", "testing", "validation"]


def make_step(step_id: str, order: int | None = None, *, name: str | None = None) -> WorkflowStep:
    """构造步骤; order 缺省按位置推断 (从 1 起)。"""
    if order is None:
        order = FEATURE_STEP_IDS.index(step_id) + 1 if step_id in FEATURE_STEP_IDS else 1
    return WorkflowStep(id=step_id, name=name or step_id, order=order)


def make_workflow(workflow_id: str = "wf-test", *, steps: list[WorkflowStep] | None = None) -> Workflow:
    """构造工作流定义; 缺省为四步特性主干。"""
    if steps is None:
        steps = [make_step(s) for s in FEATURE_STEP_IDS]
    return Workflow(id=workflow_id, name=f"{workflow_id} 测试", description="测试定义", steps=steps)


def make_task(task_id: str = "T-001", *, workflow: str | None = "feature-delivery") -> Task:
    """构造任务 (直接经 Task 模型, 不走 CLI/事件)。"""
    return Task(id=task_id, title=f"任务 {task_id}", project="markpad", type="feature", workflow=workflow)
