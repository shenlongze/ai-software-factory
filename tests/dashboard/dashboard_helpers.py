"""tests/dashboard/dashboard_helpers.py — Dashboard 测试数据构造 (纯函数, 无副作用)。"""

from __future__ import annotations

from agents.models import Agent, AgentStatus
from events.logger import EventLogger
from events.models import EventType
from recovery.models import Checkpoint
from runtime.models import ExecutionRequest, ExecutionResult, ExecutionStatus
from tasks.models import Task, TaskStatus
from workflows.models import Workflow, WorkflowRun, WorkflowStatus, WorkflowStep


def make_task(
    task_id: str = "T-001",
    title: str = "demo task",
    project: str = "default",
    status: TaskStatus | str = TaskStatus.BACKLOG,
    **kw,
) -> Task:
    return Task(id=task_id, title=title, project=project, status=status, **kw)


def make_agent(
    agent_id: str = "A-001",
    role: str = "dev",
    status: AgentStatus | str = AgentStatus.AVAILABLE,
    skills: list[str] | None = None,
    **kw,
) -> Agent:
    return Agent(id=agent_id, name=agent_id, role=role, status=status,
                 skills=skills or [], **kw)


def make_workflow(workflow_id: str = "feature-delivery", steps=("plan", "develop", "verify"), **kw) -> Workflow:
    return Workflow(
        id=workflow_id,
        name=workflow_id,
        steps=[WorkflowStep(id=s, name=s, order=i + 1) for i, s in enumerate(steps)],
        **kw,
    )


def make_workflow_run(
    run_id: str = "WR-001",
    workflow: Workflow | None = None,
    task_id: str = "T-001",
    status: WorkflowStatus | str = WorkflowStatus.RUNNING,
) -> WorkflowRun:
    run = WorkflowRun.from_workflow(run_id=run_id, workflow=workflow or make_workflow(), task_id=task_id)
    run.status = status if isinstance(status, WorkflowStatus) else WorkflowStatus.parse(str(status))
    return run


def make_execution(
    execution_id: str = "EX-001",
    task_id: str = "T-001",
    runtime_id: str = "R-001",
    status: ExecutionStatus | str = ExecutionStatus.SUCCESS,
    **kw,
) -> ExecutionRequest:
    return ExecutionRequest(id=execution_id, task_id=task_id, runtime_id=runtime_id,
                            status=status, **kw)


def make_result(
    result_id: str = "RES-001",
    request_id: str = "EX-001",
    status: ExecutionStatus | str = ExecutionStatus.SUCCESS,
    **kw,
) -> ExecutionResult:
    return ExecutionResult(id=result_id, request_id=request_id, status=status, **kw)


def make_checkpoint(
    task_id: str = "T-001",
    event_seq: int = 3,
    current_step: str = "develop",
    agents: dict | None = None,
    executions: dict | None = None,
    **kw,
) -> Checkpoint:
    return Checkpoint(
        id=f"CKPT-{task_id}", task_id=task_id, event_seq=event_seq,
        current_step=current_step, agents=agents or {}, executions=executions or {},
        **kw,
    )


def make_validation_events(
    logger: EventLogger,
    *,
    task_id: str = "T-001",
    results: tuple[str, ...] = ("PASS", "PASS", "FAIL", "SKIP"),
    runs: int = 1,
    failed_runs: int = 0,
) -> list:
    """发 validation.rule.completed 结果序列 + (可选) completed/failed 运行事件。

    事件序 (phase3a-status.md): rule.started → rule.completed; 失败追加
    validation.failed; 汇总经 validation.completed。
    """
    events = []
    for res in results:
        events.append(logger.record(
            EventType.VALIDATION_RULE_COMPLETED, source="test", task_id=task_id,
            stage="L2", action="run rule", result=res,
            payload={"rule": f"L2.{res}", "level": "L2"},
        ))
    for _ in range(runs):
        events.append(logger.record(
            EventType.VALIDATION_COMPLETED, source="test", task_id=task_id,
            stage="L2", action="validation completed", result="PASS",
        ))
    for _ in range(failed_runs):
        events.append(logger.record(
            EventType.VALIDATION_FAILED, source="test", task_id=task_id,
            stage="L2", action="validation failed", result="FAIL",
        ))
    return events
