"""scheduler.loop — tick：判定 → 排序 → 分配。

边界：
    互斥与持久化由调用方负责 —— core 不做 IO（文件锁属 infrastructure）。
    幂等由判定条件 no_active_execution 保证：同一节点至多一个活跃执行。
    抢占策略（policy=preempt）尚未实现，留待下一刀。
"""
from __future__ import annotations

from ai_factory_os.contracts.scheduling import Decision, DecisionKind, SortKey, TickResult

from .allocate import allocate
from .evaluate import evaluate
from .ports import Ports
from .rank import order


def collect(ports: Ports, *, task_id: str = "") -> tuple[Decision, ...]:
    """判定范围内全部节点的就绪状态。"""
    return tuple(evaluate(ports, node.id) for node in ports.work.list_nodes(task_id))


def tick(ports: Ports, *, task_id: str = "") -> TickResult:
    """一次调度推进：判定 → 排序 → 分配。"""
    decisions = collect(ports, task_id=task_id)
    ready = [d for d in decisions if d.kind is DecisionKind.READY]
    by_id = {d.task_node_id: d for d in ready}
    ordered = order(
        (SortKey(deadline=ports.work.deadline_of(d.task_node_id),
                 priority=ports.work.priority_of(d.task_node_id),
                 cost_estimate=d.cost_estimate,
                 sequence=d.sequence), d.task_node_id)
        for d in ready
    )
    scheduled, deferred = allocate(ports, [by_id[node_id] for node_id in ordered])
    return TickResult(scheduled=scheduled, decisions=decisions, deferred=deferred)
