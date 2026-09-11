"""kernel/events/contracts.py — 事件与证据契约（唯一事实源，append-only）。

只定义"做什么"，不含"怎么做"。禁止 import services/extensions。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class Event:
    """一条事实事件（不可变）。"""

    event_id: str
    kind: str
    subject: str
    payload: dict[str, Any] = field(default_factory=dict)
    at: str = ""


@runtime_checkable
class EventStore(Protocol):
    """事件存储契约：唯一事实源，append-only。"""

    def append(self, event: Event) -> str:
        """追加一条事件，返回 event_id（不可修改/删除）。"""
        ...

    def query(self, *, kind: str = "", subject: str = "") -> list[Event]:
        """按条件查询事件（只读）。"""
        ...
