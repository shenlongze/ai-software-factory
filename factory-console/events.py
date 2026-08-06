"""factory-console/events.py — Human Console 事件辅助 (console.*, 经 EventLogger)。

设计依据:
- phase11a-status.md §Event 集成: console.viewed / console.approval.opened /
  console.dashboard.viewed 三事件 (EventType 枚举扩展见 events/models.py,
  ADR-0034)。
- ADR-0002 铁律 (所有 CLI 行为必须产生 Event) 的 Console 延伸: 只读审计
  事件, 不触发任何写操作 (Human Layer 只读铁律 — 打开审批 ≠ 决定审批,
  决策权永远在 9c Approval 状态机)。
- source 语义: 写路径辅助供 factory-console service/api 调用 (source="console"),
  CLI 读命令经 source="cli" 直接 logger.record (同 product/intelligence 事件
  辅助模式, 不双发)。
- 本模块只依赖 events.models (公共接口) — Removal Isolation: 删除本包
  不影响 Factory (Core 零感知)。

payload 契约:
- console.viewed: {view, count, project_id?} — 通用视图审计 (projects/
  lifecycle/approvals/decisions/recommendations/experience/providers)。
- console.approval.opened: {approval_id, artifact_id, gate, status, project_id?}
  — 审批详情只读打开 (非决定: 不携带任何 approve/reject 指令)。
- console.dashboard.viewed: {projects, pending_approvals, running_agents,
  decisions, total_cost, experiences, events} — 七域计数汇总 (只读聚合)。
"""

from __future__ import annotations

from typing import Any

from events.logger import EventLogger
from events.models import Event, EventType

SOURCE = "console"


def record_console_viewed(
    logger: EventLogger,
    *,
    view: str,
    count: int,
    project_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Event | None:
    """console.viewed — Console 任意视图被查看 (只读审计)。

    logger 为 None → 静默 (同 product/intelligence 事件辅助模式)。
    """
    if logger is None:
        return None
    payload: dict[str, Any] = {"view": view, "count": count}
    if project_id is not None:
        payload["project_id"] = project_id
    if extra:
        payload.update(extra)
    return logger.record(
        EventType.CONSOLE_VIEWED,
        source=SOURCE,
        project_id=project_id,
        stage="viewed",
        action=f"view console {view}",
        result="OK",
        payload=payload,
    )


def record_console_approval_opened(
    logger: EventLogger,
    *,
    approval_id: str,
    artifact_id: str,
    gate: str,
    status: str,
    project_id: str | None = None,
) -> Event | None:
    """console.approval.opened — 审批详情被打开 (只读, 非决定)。

    只读打开审计: 不产生任何 approve/reject/changes_requested/delegated
    决定 (决策权在 9c Approval 状态机, Human Layer 不自动批准)。
    """
    if logger is None:
        return None
    return logger.record(
        EventType.CONSOLE_APPROVAL_OPENED,
        source=SOURCE,
        project_id=project_id,
        stage="opened",
        action="open approval detail",
        result="OK",
        payload={
            "approval_id": approval_id,
            "artifact_id": artifact_id,
            "gate": gate,
            "status": status,
        },
    )


def record_console_dashboard_viewed(
    logger: EventLogger,
    *,
    projects: int,
    pending_approvals: int,
    running_agents: int,
    decisions: int,
    total_cost: float,
    experiences: int,
    events: int,
    project_id: str | None = None,
) -> Event | None:
    """console.dashboard.viewed — Console Dashboard 七域汇总被查看 (只读审计)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.CONSOLE_DASHBOARD_VIEWED,
        source=SOURCE,
        project_id=project_id,
        stage="viewed",
        action="view console dashboard",
        result="OK",
        payload={
            "projects": projects,
            "pending_approvals": pending_approvals,
            "running_agents": running_agents,
            "decisions": decisions,
            "total_cost": round(float(total_cost), 6),
            "experiences": experiences,
            "events": events,
        },
    )


__all__ = [
    "SOURCE",
    "record_console_approval_opened",
    "record_console_dashboard_viewed",
    "record_console_viewed",
]
