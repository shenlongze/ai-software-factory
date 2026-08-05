"""tests/events/helpers.py — 事件构造 helper (测试共享, pytest rootdir 插入机制可直接 import)。"""

from __future__ import annotations

from datetime import datetime

from events.models import Event, EventType


def ev(
    type_: EventType | str,
    *,
    source: str = "test",
    project_id: str | None = None,
    task_id: str | None = None,
    agent_id: str | None = None,
    stage: str | None = None,
    action: str | None = None,
    result: str | None = None,
    evidence: str | None = None,
    payload: dict | None = None,
    timestamp: datetime | None = None,
) -> Event:
    """构造 Event, 可选覆盖 timestamp (metrics 时间类测试用)。"""
    e = Event.create(
        type_, source=source, project_id=project_id, task_id=task_id, agent_id=agent_id,
        stage=stage, action=action, result=result, evidence=evidence, payload=payload,
    )
    return e.model_copy(update={"timestamp": timestamp}) if timestamp is not None else e
