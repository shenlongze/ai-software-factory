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


# ------------------------------------------------------------------ S10-004 Runtime 事件
# Runtime 实例生命周期事件 (org.runtime.created / org.runtime.status_changed):
# 用字符串事件类型落库 (EventLogger.record 接受 str — 零 Core 修改, 不扩展
# events/models.py 枚举); SSE 侧 SSE_EVENT_MAP 同字符串 key 映射 (S10-002
# 契约先行已锁定: runtime.created / runtime.status.changed), 事件经既有
# iter_sse_events/_sse_event 自动推送, Timeline/前端零改动。
#
# 诚实边界 (Core 冻结): EventType 枚举尚无 org.runtime.* 成员 (扩枚举 = 改
# factory-core/events/models.py — 冻结铁律), 字符串类型经 pydantic 校验被拒
# (ValidationError)。故 record_runtime_* 对落库失败做**失败安全跳过** (返回
# None, 不拖垮 API/审计链) — 与无 event_logger 静默同哲学; S10-005+ 依
# ADR-0001 扩展枚举后自动恢复, record_runtime_* 本身零改动。SSE 侧 runtime.*
# 事件在真实事件落库前不推送 (前端 Runtime Panel 走 REST 轮询, 不依赖 SSE)。


def _record_runtime_event(logger: EventLogger, type_: str, **kwargs: Any) -> Event | None:
    """落库 runtime 事件 (失败安全: 字符串类型被 EventType 拒 → 跳过不崩溃)。"""
    if logger is None:
        return None
    try:
        return logger.record(type_, **kwargs)
    except Exception:
        # Core 冻结期 EventType 无 org.runtime.* 成员 → pydantic 拒绝字符串
        # 类型; 审计失败安全 (不因审计事件拖垮实例生命周期 API)
        return None


def record_runtime_created(
    logger: EventLogger,
    *,
    instance: Any,
    source: str = SOURCE,
) -> Event | None:
    """org.runtime.created — Runtime 实例创建 (payload 含 instance/type/
    status/artifact_id/project_id, 匹配 SSE runtime.created 映射)。"""
    return _record_runtime_event(
        logger,
        "org.runtime.created",
        source=source,
        project_id=instance.project_id,
        stage=instance.status,
        action="runtime instance created",
        result="OK",
        payload={
            "instance_id": instance.id,
            "type": instance.type,
            "status": instance.status,
            "artifact_id": instance.artifact_id,
            "project_id": instance.project_id,
        },
    )


def record_runtime_status_changed(
    logger: EventLogger,
    *,
    instance: Any,
    previous_status: str,
    source: str = SOURCE,
) -> Event | None:
    """org.runtime.status_changed — 实例状态流转 (payload 含 instance_id/
    status/previous_status, 匹配 SSE runtime.status.changed 映射)。"""
    return _record_runtime_event(
        logger,
        "org.runtime.status_changed",
        source=source,
        project_id=instance.project_id,
        stage=instance.status,
        action="runtime status changed",
        result="OK",
        payload={
            "instance_id": instance.id,
            "status": instance.status,
            "previous_status": previous_status,
        },
    )


__all__ = [
    "SOURCE",
    "record_console_approval_opened",
    "record_console_dashboard_viewed",
    "record_console_viewed",
    "record_runtime_created",
    "record_runtime_status_changed",
]
