"""scheduler.allocate — 分配：受容量与预算约束，超出的推迟到下一 tick。

关键：同一 tick 内，同一成员的容量与预算会被**前面的分配**占掉，
本函数维护 tick 内预留量，避免超发。
"""
from __future__ import annotations

from collections.abc import Sequence

from ai_factory_os.contracts.scheduling import Decision

from .ports import Ports


def allocate(ports: Ports, ordered: Sequence[Decision]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """按序创建执行。返回（已调度的 execution_id, 被推迟的 task_node_id）。"""
    reserved: dict[str, int] = {}
    spent: dict[str, float] = {}
    scheduled: list[str] = []
    deferred: list[str] = []

    for d in ordered:
        member = ports.resource.member(d.member_id)
        capacity = member.capacity.max_concurrent if member is not None else 0
        used = ports.load.active_count(d.member_id) + reserved.get(d.member_id, 0)
        left = ports.load.remaining_budget(d.member_id) - spent.get(d.member_id, 0.0)

        if used >= capacity or left < d.cost_estimate:
            deferred.append(d.task_node_id)
            continue

        execution = ports.execution.create(d.task_node_id, resolution_id=d.resolution_id,
                                           member_id=d.member_id, identity_id=d.identity_id)
        reserved[d.member_id] = reserved.get(d.member_id, 0) + 1
        spent[d.member_id] = spent.get(d.member_id, 0.0) + d.cost_estimate
        scheduled.append(execution.id)

    return tuple(scheduled), tuple(deferred)
