"""scheduler.evaluate — 就绪判定：八条件 → 五态 + reasons。

确定性、无副作用、可解释。判定顺序固定，第一条不满足的条件即原因。
"""
from __future__ import annotations

from ai_factory_os.contracts.governance import ApprovalMode
from ai_factory_os.contracts.resource import Match, Resolution
from ai_factory_os.contracts.scheduling import Decision, DecisionKind
from ai_factory_os.contracts.work import TaskNode

from .ports import Ports

_TERMINAL = {"completed": DecisionKind.COMPLETED, "cancelled": DecisionKind.CANCELLED}


def evaluate(ports: Ports, node_id: str) -> Decision:
    """判定某 TaskNode 此刻能否被调度。"""
    node = ports.work.get_node(node_id)
    if node is None:
        return _no(node_id, DecisionKind.UNRESOLVED, "status_actionable", "TaskNode 不存在")

    if (done := _TERMINAL.get(node.status)) is not None:
        return _no(node_id, done, "status_actionable", f"节点状态 {node.status}")
    if node.status == "running":
        return _no(node_id, DecisionKind.BLOCKED, "status_actionable", "节点正在运行")

    if ports.work.has_accepted_outcome(node_id):
        return _no(node_id, DecisionKind.COMPLETED, "status_actionable",
                   "已有 accepted Outcome（不重复调度，完成由验收定义）")

    unmet = [f"前驱 {d} 未验收" for d in node.depends_on if not ports.work.has_accepted_outcome(d)]
    if unmet:
        return _no(node_id, DecisionKind.BLOCKED, "dependencies_satisfied", *unmet)

    if (active := ports.execution.active_for(node_id)) is not None:
        return _no(node_id, DecisionKind.BLOCKED, "no_active_execution", f"已有活跃执行 {active.id}")

    resolution, err = _resolution(ports, node)
    if resolution is None:
        return _no(node_id, DecisionKind.UNRESOLVED, "capability_available", *err)

    if _needs_gate(ports, resolution) and not ports.gate.is_approved(node_id):
        return _no(node_id, DecisionKind.BLOCKED, "approval_granted", "等待审批")

    deadline = ports.work.deadline_of(node_id)
    if deadline and ports.clock.now_iso() > deadline:
        return _no(node_id, DecisionKind.BLOCKED, "deadline_feasible", f"已过期 {deadline}")

    match, reasons, condition = _pick(ports, resolution)
    if match is None:
        return _no(node_id, DecisionKind.BLOCKED, condition, *reasons)

    return Decision(
        task_node_id=node_id,
        kind=DecisionKind.READY,
        reasons=("八条件全满足",),
        resolution_id=resolution.id,
        member_id=match.member_id,
        identity_id=match.identity_id,
        cost_estimate=_estimate(ports, match),
        sequence=node.sequence,
    )


# ------------------------------------------------------------------ helpers

def _resolution(ports: Ports, node: TaskNode) -> tuple[Resolution | None, tuple[str, ...]]:
    """取该节点的可用解析；不可用则给出原因。"""
    if not node.required_capability_refs:
        return None, ("未声明 required_capability_refs",)
    resolution = ports.resource.resolution_for(node.id)
    if resolution is None:
        return None, ("无解析结果",)
    if resolution.status != "resolved" or not resolution.matches:
        head = f"解析 {resolution.status}" + (f": {resolution.reason}" if resolution.reason else "")
        return None, (head, *(f"缺能力 {c}" for c in resolution.unresolved_capabilities))
    return resolution, ()


def _needs_gate(ports: Ports, resolution: Resolution) -> bool:
    """只要有任一匹配能力声明了 before 审批，就需门。"""
    for m in resolution.matches:
        cap = ports.resource.capability(m.capability_id)
        if cap is not None and cap.approval.mode is ApprovalMode.BEFORE:
            return True
    return False


def _pick(ports: Ports, resolution: Resolution) -> tuple[Match | None, tuple[str, ...], str]:
    """按匹配顺序取第一个有容量且预算够的；全不行则给最贴切的原因。"""
    full: list[str] = []
    poor: list[str] = []
    for m in resolution.matches:
        member = ports.resource.member(m.member_id)
        if member is None or not m.identity_id:
            full.append(f"匹配不可用 {m.member_id}")
            continue
        if ports.load.active_count(m.member_id) >= member.capacity.max_concurrent:
            full.append(f"成员已满 {m.member_id}（上限 {member.capacity.max_concurrent}）")
            continue
        if ports.load.remaining_budget(m.member_id) < _estimate(ports, m):
            poor.append(f"预算不足 {m.member_id}")
            continue
        return m, (), "capacity_available"
    if poor and not full:
        return None, tuple(poor), "budget_available"
    return None, tuple(full) or ("无可用匹配",), "capacity_available"


def _estimate(ports: Ports, match: Match) -> float:
    cap = ports.resource.capability(match.capability_id)
    return cap.cost.money if cap is not None else 0.0


def _no(node_id: str, kind: DecisionKind, condition: str, *reasons: str) -> Decision:
    return Decision(task_node_id=node_id, kind=kind, reasons=tuple(reasons),
                    failed_conditions=(condition,))
