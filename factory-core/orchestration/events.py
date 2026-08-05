"""orchestration/events.py — orchestration.* 事件发射辅助 (经 EventLogger)。

设计依据:
- phase4c2-status.md §Event 集成: 新增 orchestration.started / step.started /
  step.completed / completed / failed 五事件; EventType 枚举扩展 (ADR-0010)。
- 铁律 (ADR-0002/ADR-0006): 事件一律经 EventLogger, 不直接写 EventStore;
  logger 可缺省 (纯存储/测试场景) — 此时各函数返回 None。
- source 统一 "orchestration_engine" (event-model §2.1 source 取值)。

事件序 (成功, N 步):
  orchestration.started → (workflow.started → workflow.step.started 由 WorkflowEngine 发)
  → 每步: orchestration.step.started → (assignment.*/execution.* 由既有模块发)
  → orchestration.step.completed → ... → orchestration.completed
失败 (任一步): orchestration.step.started → ... → orchestration.failed (Workflow FAILED)。

本模块只负责构造/发射事件, 不含编排逻辑 (逻辑在 engine.py)。
"""

from __future__ import annotations

from events.logger import EventLogger
from events.models import Event, EventType

SOURCE = "orchestration_engine"  # event-model §2.1 source 取值


def emit_started(
    logger: EventLogger | None,
    *,
    task_id: str,
) -> Event | None:
    """orchestration.started: 流水线开始 (workflow_id/run_id 尚未知, 后续事件补齐)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORCHESTRATION_STARTED, source=SOURCE, task_id=task_id,
        stage="running", action="execute workflow", result="OK",
        payload={"task_id": task_id},
    )


def emit_step_started(
    logger: EventLogger | None,
    *,
    task_id: str,
    workflow_id: str,
    run_id: str,
    step_id: str,
    step_name: str | None = None,
    agent_id: str | None = None,
) -> Event | None:
    """orchestration.step.started: 单步编排开始 (匹配→分配→执行之前)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORCHESTRATION_STEP_STARTED, source=SOURCE, task_id=task_id,
        agent_id=agent_id, stage="running", action=f"start step {step_id}",
        result="OK",
        payload={
            "workflow_id": workflow_id, "run_id": run_id, "task_id": task_id,
            "step_id": step_id, "step_name": step_name, "agent_id": agent_id,
        },
    )


def emit_step_completed(
    logger: EventLogger | None,
    *,
    task_id: str,
    workflow_id: str,
    run_id: str,
    step_id: str,
    step_name: str | None = None,
    agent_id: str | None = None,
    execution_id: str | None = None,
    result: str = "OK",
) -> Event | None:
    """orchestration.step.completed: 单步编排完成 (执行 SUCCESS + 步骤推进)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORCHESTRATION_STEP_COMPLETED, source=SOURCE, task_id=task_id,
        agent_id=agent_id, stage="running", action=f"complete step {step_id}",
        result=result,
        payload={
            "workflow_id": workflow_id, "run_id": run_id, "task_id": task_id,
            "step_id": step_id, "step_name": step_name, "agent_id": agent_id,
            "execution_id": execution_id, "result": result,
        },
    )


def emit_completed(
    logger: EventLogger | None,
    *,
    task_id: str,
    workflow_id: str,
    run_id: str,
    steps: list[dict],
) -> Event | None:
    """orchestration.completed: 全部步骤完成 (Workflow COMPLETED)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORCHESTRATION_COMPLETED, source=SOURCE, task_id=task_id,
        stage="completed", action="complete workflow", result="OK",
        payload={
            "workflow_id": workflow_id, "run_id": run_id, "task_id": task_id,
            "steps": steps,
        },
    )


def emit_failed(
    logger: EventLogger | None,
    *,
    task_id: str,
    workflow_id: str | None = None,
    run_id: str | None = None,
    error: str,
) -> Event | None:
    """orchestration.failed: 流水线失败 (执行失败 → Workflow FAILED; 前置错误不改状态)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORCHESTRATION_FAILED, source=SOURCE, task_id=task_id,
        stage="failed", action="fail workflow", result="failed",
        payload={
            "workflow_id": workflow_id, "run_id": run_id, "task_id": task_id,
            "error": error,
        },
    )
