"""tests/changeflow/changeflow_helpers.py — Change Driven Workflow 测试数据构造 (纯函数)。

唯一 basename 规则 (backend-developer skill): helper 模块命名 changeflow_helpers,
避免与 tests/change/change_helpers.py、tests/workflows/workflow_helpers.py 等
非包目录共存时同名模块互相遮蔽。
"""

from __future__ import annotations

from datetime import datetime, timezone

from changeflow.models import ChangeEvaluation, ChangeTrigger, RuleResult
from tasks.models import Task
from workflows.models import Workflow, WorkflowStep


def make_trigger(
    trigger_id: str = "TRIG-FEATURE-RELEASE",
    *,
    event_type: str | None = "workflow.completed",
    project_id: str | None = None,
    task_type: str | None = None,
    required_validation: str | None = "PASS",
    target_workflow: str = "release",
) -> ChangeTrigger:
    return ChangeTrigger(
        id=trigger_id,
        event_type=event_type,
        project_id=project_id,
        task_type=task_type,
        required_validation=required_validation,
        target_workflow=target_workflow,
    )


def make_rule_result(
    rule_id: str = "validation.l4",
    status: str = "PASS",
    message: str = "",
) -> RuleResult:
    return RuleResult(rule_id=rule_id, status=status, message=message)


def make_evaluation(
    task_id: str = "MP-BUG-001",
    *,
    trigger_id: str | None = "TRIG-FEATURE-RELEASE",
    status: str = "PASS",
    rules: list[RuleResult] | None = None,
    triggered_workflow: str | None = None,
    run_id: str | None = None,
    error: str | None = None,
) -> ChangeEvaluation:
    return ChangeEvaluation(
        task_id=task_id,
        trigger_id=trigger_id,
        status=status,
        rules=rules or [],
        triggered_workflow=triggered_workflow,
        run_id=run_id,
        error=error,
    )


def make_task(
    task_id: str = "MP-BUG-001",
    *,
    title: str = "Fix login crash",
    project: str = "markpad",
    type_: str = "feature",
    workflow: str | None = "feature-delivery",
) -> Task:
    return Task(id=task_id, title=title, project=project, type=type_,
                workflow=workflow)


def make_workflow(
    workflow_id: str = "release",
    *,
    name: str | None = None,
    steps: tuple[str, ...] = ("build", "publish"),
) -> Workflow:
    return Workflow(
        id=workflow_id,
        name=name or workflow_id,
        steps=[WorkflowStep(id=s, name=s, order=i + 1) for i, s in enumerate(steps)],
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
