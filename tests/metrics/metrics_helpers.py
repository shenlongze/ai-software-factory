"""tests/metrics/metrics_helpers.py — Metrics 测试数据构造 (纯函数 + 事件发射)。

复用 dashboard_helpers 的 make_task/make_agent/make_workflow/make_workflow_run/
make_execution/make_result/make_validation_events (数据构造, 无副作用);
本文件补充事件序列构造: 任务成败链 / 分配链 / 工作流链。
"""

from __future__ import annotations

from events.logger import EventLogger
from events.models import EventType


def make_task_events(
    logger: EventLogger,
    *,
    task_id: str = "T-001",
    project: str | None = None,
    start: bool = True,
    end: str | None = None,
    fail: str | None = None,
) -> list:
    """发任务链事件: task.start → (task.end result=done|failed 或 task.fail)。

    end: "done" 或 "failed" (task.end); fail: 失败阶段 (task.fail, payload.stage)。
    """
    events = []
    if start:
        events.append(logger.task_start(task_id, "demo task", "dev", project_id=project))
    if end is not None:
        events.append(logger.task_end(task_id, end, duration_s=1.0, project_id=project))
    if fail is not None:
        events.append(logger.task_fail(task_id, stage=fail, error=f"boom at {fail}",
                                       project_id=project))
    return events


def make_assignment_events(
    logger: EventLogger,
    *,
    agent_id: str = "A-001",
    task_id: str = "T-001",
    count: int = 1,
    successes: int | None = None,
    failures: int | None = None,
) -> list:
    """发分配链事件: agent.assignment.created × count + completed/failed。

    successes/failures 缺省 = count (全成功), 用于组合混合结果。
    """
    events = []
    created = [logger.record(
        EventType.ASSIGNMENT_CREATED, source="test", agent_id=agent_id, task_id=task_id,
        stage="assigned", action="assign agent", result="OK",
    ) for _ in range(count)]
    events += created
    ok = count if successes is None else successes
    for _ in range(ok):
        events.append(logger.record(
            EventType.ASSIGNMENT_COMPLETED, source="test", agent_id=agent_id, task_id=task_id,
            stage="completed", action="assignment completed", result="OK",
        ))
    bad = count if failures is None else failures
    for _ in range(bad):
        events.append(logger.record(
            EventType.ASSIGNMENT_FAILED, source="test", agent_id=agent_id, task_id=task_id,
            stage="failed", action="assignment failed", result="FAIL",
        ))
    return events


def make_workflow_events(
    logger: EventLogger,
    *,
    task_id: str = "T-001",
    completed: int = 1,
    failed: int = 0,
) -> list:
    """发工作流链事件: workflow.started → completed|failed (事件维度审计用)。"""
    events = []
    for _ in range(completed):
        events.append(logger.record(
            EventType.WORKFLOW_STARTED, source="test", task_id=task_id,
            stage="running", action="start workflow", result="OK",
        ))
        events.append(logger.record(
            EventType.WORKFLOW_COMPLETED, source="test", task_id=task_id,
            stage="completed", action="workflow completed", result="OK",
        ))
    for _ in range(failed):
        events.append(logger.record(
            EventType.WORKFLOW_STARTED, source="test", task_id=task_id,
            stage="running", action="start workflow", result="OK",
        ))
        events.append(logger.record(
            EventType.WORKFLOW_FAILED, source="test", task_id=task_id,
            stage="failed", action="workflow failed", result="FAIL",
        ))
    return events
