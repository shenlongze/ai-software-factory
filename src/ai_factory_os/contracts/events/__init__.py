"""events — 事件（链式事实）。零依赖。

事实源 = 追加不可变。无更新、无删除。
"""
from __future__ import annotations

from dataclasses import dataclass

# 内核事件类型（插件可自定义，用字符串即可）
CORE_EVENT_TYPES: tuple[str, ...] = (
    "identity.created",
    "organization.created",
    "work.created",
    "work.status_changed",
    "task.created",
    "task_node.created",
    "task_node.status_changed",
    "capability.declared",
    "resolution.resolved",
    "execution.created",
    "execution.started",
    "execution.finished",
    "outcome.accepted",
    "outcome.rejected",
    "gate.requested",
    "gate.approved",
    "gate.rejected",
    "budget.consumed",
    "experience.recorded",
    "scheduler.decided",
)


@dataclass(frozen=True)
class Event:
    """一条事实 —— 链式哈希，追加不可变。"""

    id: str
    type: str
    at: str
    actor_id: str = ""
    subject_ref: str = ""
    payload: tuple[tuple[str, str], ...] = ()
    prev_hash: str = ""
    hash: str = ""


@dataclass(frozen=True)
class EventQuery:
    """事实检索条件。"""

    subject_ref: str = ""
    type: str = ""
    actor_id: str = ""
    since: str = ""
    until: str = ""
