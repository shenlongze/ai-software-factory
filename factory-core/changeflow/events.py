"""changeflow/events.py — change.trigger.* / change.workflow.* 审计事件辅助
(经 EventLogger, Phase 6E, ADR-0020)。

设计依据:
- phase6e-status.md: change.trigger.created/evaluated + change.workflow.started/
  completed 事件; trigger viewed 为读命令审计 (ADR-0002: 所有 CLI 行为必须
  产生 Event, 同 workflow.viewed / change 命令先例)。
- ADR-0001 决策 1: 事件类型扩展 = 加 EventType 枚举成员 (不改表结构)。
- 本模块只发审计事件, 不触碰任何业务状态/仓库写操作; source 缺省 "changeflow"
  (引擎/注册表层), CLI 命令层直接经 logger.record 用 source="cli" (同既有模式)。

payload 契约 (Dashboard Change Flow View 事件聚合依赖, 与 CLI --json 出口一致):
- change.trigger.created:   trigger_id/event_type/project_id/task_type/
  required_validation/target_workflow
- change.trigger.viewed:    count (triggers list 读命令)
- change.trigger.evaluated: task_id/trigger_id/status/rules/triggered_workflow/
  run_id/error (评估 + 触发结果一体)
- change.workflow.started:  task_id/trigger_id/workflow_id/run_id
- change.workflow.completed: task_id/trigger_id/workflow_id/run_id/result/error
  (result=COMPLETED/FAILED — 触发工作流执行终态, 触发失败不级联)
"""

from __future__ import annotations

from typing import Any

from events.models import Event, EventType

from .models import ChangeEvaluation, ChangeTrigger, RuleResult


def record_change_trigger_created(
    logger: Any,
    *,
    trigger: ChangeTrigger,
    source: str = "changeflow",
) -> Event:
    """ChangeTrigger 注册 (ChangeTriggerRegistry.register 装配)。"""
    return logger.record(
        EventType.CHANGE_TRIGGER_CREATED,
        source=source,
        project_id=trigger.project_id,
        stage="created",
        action=f"register change trigger {trigger.id}",
        result="OK",
        payload={
            "trigger_id": trigger.id,
            "event_type": trigger.event_type,
            "project_id": trigger.project_id,
            "task_type": trigger.task_type,
            "required_validation": trigger.required_validation,
            "target_workflow": trigger.target_workflow,
        },
    )


def record_change_trigger_viewed(
    logger: Any,
    *,
    count: int,
    source: str = "cli",
) -> Event:
    """触发器列表被查看 (CLI change triggers list 读命令审计, ADR-0002)。"""
    return logger.record(
        EventType.CHANGE_TRIGGER_VIEWED,
        source=source,
        stage="viewed",
        action="view change triggers",
        result="OK",
        payload={"count": count},
    )


def record_change_trigger_evaluated(
    logger: Any,
    *,
    evaluation: ChangeEvaluation,
    source: str = "changeflow",
) -> Event:
    """规则评估完成 (evaluate 装配; result=判定, 载荷含规则与触发结果)。"""
    return logger.record(
        EventType.CHANGE_TRIGGER_EVALUATED,
        source=source,
        task_id=evaluation.task_id,
        project_id=None,
        stage="evaluated",
        action=f"evaluate change trigger {evaluation.trigger_id or '-'}",
        result=evaluation.status,
        payload={
            "task_id": evaluation.task_id,
            "trigger_id": evaluation.trigger_id,
            "status": evaluation.status,
            "rules": [r.to_dict() for r in evaluation.rules],
            "triggered_workflow": evaluation.triggered_workflow,
            "run_id": evaluation.run_id,
            "error": evaluation.error,
        },
    )


def record_change_workflow_started(
    logger: Any,
    *,
    task_id: str,
    trigger: ChangeTrigger,
    workflow_id: str,
    run_id: str,
    source: str = "changeflow",
) -> Event:
    """触发工作流启动 (run 已创建并 RUNNING; 复用 WorkflowRun/WorkflowStore)。"""
    return logger.record(
        EventType.CHANGE_WORKFLOW_STARTED,
        source=source,
        task_id=task_id,
        project_id=trigger.project_id,
        stage="running",
        action=f"start triggered workflow {workflow_id}",
        result="OK",
        payload={
            "task_id": task_id,
            "trigger_id": trigger.id,
            "workflow_id": workflow_id,
            "run_id": run_id,
        },
    )


def record_change_workflow_completed(
    logger: Any,
    *,
    task_id: str,
    trigger_id: str,
    workflow_id: str,
    run_id: str,
    result: str,
    error: str | None = None,
    source: str = "changeflow",
) -> Event:
    """触发工作流执行终态 (result=COMPLETED/FAILED; 失败恢复不级联 — 只审计)。"""
    return logger.record(
        EventType.CHANGE_WORKFLOW_COMPLETED,
        source=source,
        task_id=task_id,
        stage="completed" if result == "COMPLETED" else "failed",
        action=f"complete triggered workflow {workflow_id}",
        result=result,
        payload={
            "task_id": task_id,
            "trigger_id": trigger_id,
            "workflow_id": workflow_id,
            "run_id": run_id,
            "result": result,
            "error": error,
        },
    )


def rule_result_to_dict(r: RuleResult) -> dict[str, Any]:
    """RuleResult → JSON 友好 dict (事件/CLI 共用)。"""
    return r.to_dict()
