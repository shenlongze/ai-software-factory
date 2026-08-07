"""factory-exec/exec/events.py — org.execution.* 事件辅助 (经 factory-core EventLogger)。

设计依据:
- docs/architecture/phase-a-execution-mvp-design.md §11: org.execution.* 事件
  (Extension 内新增, Core 零顶层架构修改)。
- ADR-0001 决策 1 扩展路径: EventType 枚举加成员即可 (events/models.py 已
  扩展 151 → 157); logger 为 None 时全部静默 (同 org/intelligence events 模式)。
- ADR-0002: 所有 CLI 行为必须产生 Event — viewed/checked 为读命令审计
  (source="cli"); 写路径事件 source="exec"。

payload 契约 (事件唯一事实源: 从事件 payload 可重建执行闭环关键字段):
- execution.requested: request_id/task_id/objective/employee_id/agent_id/provider_id
- execution.started:   request_id/employee_id/agent_id/sandbox_path
- execution.completed: request_id/result_id/status/artifact_count/usage
- execution.failed:    request_id/error (稳定前缀: provider error: / patch parse / validation ...)
- execution.approved:  approval_id/request_id/decided_by/decision
- execution.applied:   approval_id/request_id/result_id/patch_path
"""

from __future__ import annotations

from typing import Any

from events.models import Event, EventType


def last_seq(logger: Any, event_type: EventType) -> int | None:
    """该事件类型最近一条的 seq (CLI 审计锚点); logger=None → None。"""
    if logger is None:
        return None
    events = logger.store.query(event_type=event_type)
    return events[-1].seq if events else None


def record_execution_requested(
    logger: Any, *, request: Any, employee: Any = None, agent: Any = None,
    provider_id: str = "", source: str = "exec",
) -> Event | None:
    """执行请求创建 (org.execution.requested; ExecutionRequest 落库后发)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_EXECUTION_REQUESTED,
        source=source,
        stage="requested",
        action="request execution",
        result="OK",
        task_id=request.task_id or None,
        payload={
            "request_id": request.id,
            "task_id": request.task_id,
            "objective": request.objective,
            "employee_id": getattr(employee, "id", "") or "",
            "agent_id": getattr(agent, "id", "") or "",
            "provider_id": provider_id,
        },
    )


def record_execution_started(
    logger: Any, *, request: Any, employee: Any = None, agent: Any = None,
    sandbox_path: str = "", source: str = "exec",
) -> Event | None:
    """Runtime 开始执行 (org.execution.started; 沙箱就绪后发)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_EXECUTION_STARTED,
        source=source,
        stage="started",
        action="start execution",
        result="OK",
        task_id=request.task_id or None,
        payload={
            "request_id": request.id,
            "employee_id": getattr(employee, "id", "") or "",
            "agent_id": getattr(agent, "id", "") or "",
            "sandbox_path": sandbox_path,
        },
    )


def record_execution_completed(
    logger: Any, *, result: Any, source: str = "exec",
) -> Event | None:
    """执行成功 (org.execution.completed; 产物齐全后发, 终态单一)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_EXECUTION_COMPLETED,
        source=source,
        stage="completed",
        action="execution completed",
        result="OK",
        task_id=None,
        payload={
            "request_id": result.request_id,
            "result_id": result.id,
            "status": result.status.value,
            "artifact_count": len(result.artifacts),
            "usage": result.usage,
            "duration": round(result.duration, 3),
        },
    )


def record_execution_failed(
    logger: Any, *, request: Any, error: str, source: str = "exec",
) -> Event | None:
    """执行失败 (org.execution.failed; error 稳定前缀供审计/Experience)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_EXECUTION_FAILED,
        source=source,
        stage="failed",
        action="execution failed",
        result="FAILED",
        task_id=getattr(request, "task_id", None) or None,
        payload={"request_id": getattr(request, "id", ""), "error": error[:500]},
    )


def record_execution_approved(
    logger: Any, *, approval: Any, source: str = "exec",
) -> Event | None:
    """Human 审批通过 (org.execution.approved; approve 落库后发)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_EXECUTION_APPROVED,
        source=source,
        stage="approved",
        action="approve execution patch",
        result="OK",
        task_id=None,
        payload={
            "approval_id": approval.id,
            "request_id": approval.request_id,
            "decided_by": approval.decided_by,
            "decision": approval.decision.value,
        },
    )


def record_execution_applied(
    logger: Any, *, approval: Any, result: Any, patch_path: str = "", source: str = "exec",
) -> Event | None:
    """patch 已应用 (org.execution.applied; 批准后 apply 成功发, 终态单一)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_EXECUTION_APPLIED,
        source=source,
        stage="applied",
        action="apply approved patch",
        result="OK",
        task_id=None,
        payload={
            "approval_id": approval.id,
            "request_id": approval.request_id,
            "result_id": getattr(result, "id", ""),
            "patch_path": patch_path,
        },
    )


def record_execution_viewed(
    logger: Any, *, count: int = 0, source: str = "cli",
) -> Event | None:
    """执行结果/审批清单被查看 (org.execution.viewed; 读命令审计, ADR-0002)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_EXECUTION_VIEWED,
        source=source,
        stage="viewed",
        action="view execution status",
        result="OK",
        task_id=None,
        payload={"count": count},
    )
