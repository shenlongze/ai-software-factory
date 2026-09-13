"""events.query — 事实检索。纯过滤，零 IO。

调用方保证事件按时间序传入；latest/replay 依赖该序。
"""
from __future__ import annotations

from typing import Sequence

from ai_factory_os.contracts.events import Event, EventQuery


def select(events: Sequence[Event], query: EventQuery) -> list[Event]:
    """按主体 / 类型 / 主体人 / 时间窗过滤（空条件 = 不筛）。"""
    return [
        e for e in events
        if (not query.subject_ref or e.subject_ref == query.subject_ref)
        and (not query.type or e.type == query.type)
        and (not query.actor_id or e.actor_id == query.actor_id)
        and (not query.since or e.at >= query.since)
        and (not query.until or e.at <= query.until)
    ]


def latest(events: Sequence[Event], query: EventQuery) -> Event | None:
    """最后一条命中 —— 无命中返回 None。"""
    hits = select(events, query)
    return hits[-1] if hits else None
