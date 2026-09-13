"""core.scheduler —— 判定 / 排序 / 分配 / tick。"""
from __future__ import annotations

from ai_factory_os.contracts.execution import Execution
from ai_factory_os.contracts.governance import ApprovalMode, ApprovalSpec, GateKind
from ai_factory_os.contracts.organization import Capacity, Member
from ai_factory_os.contracts.resource import Capability, CostSpec, Match, ProviderType, Resolution
from ai_factory_os.contracts.scheduling import DecisionKind, SortKey
from ai_factory_os.contracts.work import TaskNode
from ai_factory_os.core.scheduler.allocate import allocate
from ai_factory_os.core.scheduler.evaluate import evaluate
from ai_factory_os.core.scheduler.loop import tick
from ai_factory_os.core.scheduler.ports import Ports
from ai_factory_os.core.scheduler.rank import order

NODE = "TN-1"
MEMBER = "M-1"


class World:
    """内存世界 —— 一个类实现全部端口，供调度器读取，并记录分配结果。"""

    def __init__(self, *, now: str = "2026-01-01T00:00:00Z") -> None:
        self.now = now
        self.nodes: dict[str, TaskNode] = {}
        self.priorities: dict[str, str] = {}
        self.deadlines: dict[str, str] = {}
        self.accepted: set[str] = set()
        self.members: dict[str, Member] = {}
        self.resolutions: dict[str, Resolution] = {}
        self.caps: dict[str, Capability] = {}
        self.approved: set[str] = set()
        self.actives: dict[str, Execution] = {}
        self.loads: dict[str, int] = {}
        self.budgets: dict[str, float] = {}
        self.created: list[Execution] = []
        self._seq = 0

    # ---------------------------------------------------------- 组装

    def node(self, node_id: str, *, status: str = "pending", deps: tuple[str, ...] = (),
             caps: tuple[str, ...] = ("CAP-1",), sequence: int = 0,
             priority: str = "P2", deadline: str = "") -> World:
        self.nodes[node_id] = TaskNode(id=node_id, task_id="T-1", name=node_id, sequence=sequence,
                                       depends_on=deps, required_capability_refs=caps, status=status)
        self.priorities[node_id] = priority
        self.deadlines[node_id] = deadline
        return self

    def hire(self, member_id: str = MEMBER, *, concurrent: int = 1,
             identity: str = "ID-1") -> World:
        self.members[member_id] = Member(id=member_id, org_id="O-1", identity_id=identity,
                                         capacity=Capacity(max_concurrent=concurrent))
        return self

    def cap(self, cap_id: str = "CAP-1", *, money: float = 0.0,
            approval: ApprovalMode = ApprovalMode.NONE) -> World:
        self.caps[cap_id] = Capability(id=cap_id, name=cap_id, verify="v", effects=("write",),
                                       approval=ApprovalSpec(mode=approval), cost=CostSpec(money=money))
        return self

    def resolves(self, node_id: str, *member_ids: str, status: str = "resolved",
                 unsolved: tuple[str, ...] = ()) -> World:
        matches = tuple(Match(capability_id="CAP-1", member_id=m, identity_id="ID-1",
                              provider_type=ProviderType.AGENT) for m in member_ids)
        self.resolutions[node_id] = Resolution(id=f"RS-{node_id}", task_node_id=node_id,
                                               required_capability_refs=("CAP-1",), matches=matches,
                                               status=status, unresolved_capabilities=unsolved)
        return self

    # ---------------------------------------------------------- 端口

    def now_iso(self) -> str:
        return self.now

    def get_node(self, node_id: str) -> TaskNode | None:
        return self.nodes.get(node_id)

    def list_nodes(self, task_id: str = "") -> list[TaskNode]:
        return list(self.nodes.values())

    def has_accepted_outcome(self, node_id: str) -> bool:
        return node_id in self.accepted

    def deadline_of(self, node_id: str) -> str:
        return self.deadlines.get(node_id, "")

    def priority_of(self, node_id: str) -> str:
        return self.priorities.get(node_id, "P2")

    def resolution_for(self, node_id: str) -> Resolution | None:
        return self.resolutions.get(node_id)

    def member(self, member_id: str) -> Member | None:
        return self.members.get(member_id)

    def capability(self, capability_id: str) -> Capability | None:
        return self.caps.get(capability_id)

    def active_count(self, member_id: str) -> int:
        return self.loads.get(member_id, 0)

    def remaining_budget(self, scope_ref: str) -> float:
        return self.budgets.get(scope_ref, 1e9)

    def is_approved(self, subject_ref: str, kind: GateKind = GateKind.BEFORE) -> bool:
        return subject_ref in self.approved

    def active_for(self, node_id: str) -> Execution | None:
        return self.actives.get(node_id)

    def create(self, node_id: str, *, resolution_id: str, member_id: str,
               identity_id: str) -> Execution:
        self._seq += 1
        execution = Execution(id=f"EX-{self._seq}", task_node_id=node_id, resolution_id=resolution_id,
                              member_id=member_id, actor_identity_id=identity_id, status="queued")
        self.created.append(execution)
        self.actives[node_id] = execution
        return execution

    @property
    def ports(self) -> Ports:
        return Ports(clock=self, work=self, resource=self, load=self, gate=self, execution=self)


def _ready(ports: Ports, node_id: str = NODE):
    decision = evaluate(ports, node_id)
    assert decision.kind is DecisionKind.READY, decision.reasons
    return decision


# ------------------------------------------------------------------ 判定

def test_ready_when_all_conditions_hold() -> None:
    w = World().node(NODE).hire().resolves(NODE, MEMBER)
    decision = _ready(w.ports)
    assert (decision.member_id, decision.identity_id) == (MEMBER, "ID-1")
    assert decision.failed_conditions == ()


def test_missing_node_is_unresolved() -> None:
    decision = evaluate(World().ports, "NOPE")
    assert decision.kind is DecisionKind.UNRESOLVED
    assert decision.failed_conditions == ("status_actionable",)


def test_terminal_states() -> None:
    for status, expected in (("completed", DecisionKind.COMPLETED),
                             ("cancelled", DecisionKind.CANCELLED),
                             ("running", DecisionKind.BLOCKED)):
        assert evaluate(World().node(NODE, status=status).ports, NODE).kind is expected


def test_dependency_requires_accepted_outcome() -> None:
    w = World().node(NODE, deps=("TN-0",)).hire().resolves(NODE, MEMBER)
    decision = evaluate(w.ports, NODE)
    assert decision.kind is DecisionKind.BLOCKED
    assert decision.failed_conditions == ("dependencies_satisfied",)
    w.accepted.add("TN-0")
    _ready(w.ports)


def test_no_declared_capability_is_unresolved() -> None:
    assert evaluate(World().node(NODE, caps=()).ports, NODE).failed_conditions == \
        ("capability_available",)


def test_unresolved_resolution_reports_missing_capability() -> None:
    w = World().node(NODE).hire().resolves(NODE, status="unresolved", unsolved=("CAP-1",))
    decision = evaluate(w.ports, NODE)
    assert decision.kind is DecisionKind.UNRESOLVED
    assert decision.failed_conditions == ("capability_available",)
    assert any("CAP-1" in r for r in decision.reasons)


def test_approval_gate_blocks_until_granted() -> None:
    w = World().node(NODE).hire().resolves(NODE, MEMBER).cap(approval=ApprovalMode.BEFORE)
    assert evaluate(w.ports, NODE).failed_conditions == ("approval_granted",)
    w.approved.add(NODE)
    _ready(w.ports)


def test_capacity_exhausted_blocks() -> None:
    w = World().node(NODE).hire().resolves(NODE, MEMBER)
    w.loads[MEMBER] = 1
    assert evaluate(w.ports, NODE).failed_conditions == ("capacity_available",)


def test_budget_shortfall_blocks() -> None:
    w = World().node(NODE).hire().resolves(NODE, MEMBER).cap(money=5.0)
    w.budgets[MEMBER] = 1.0
    assert evaluate(w.ports, NODE).failed_conditions == ("budget_available",)
    w.budgets[MEMBER] = 9.0
    _ready(w.ports)


def test_expired_deadline_blocks() -> None:
    w = World(now="2026-02-01T00:00:00Z").node(NODE, deadline="2026-01-01T00:00:00Z")
    w.hire().resolves(NODE, MEMBER)
    assert evaluate(w.ports, NODE).failed_conditions == ("deadline_feasible",)


# ------------------------------------------------------------------ 排序

def test_rank_precedence_and_order() -> None:
    k = SortKey
    assert order([(k(deadline="2026-02-01T00:00:00Z"), "late"),
                  (k(deadline="2026-01-01T00:00:00Z"), "early")]) == ["early", "late"]
    assert order([(k(priority="P2"), "p2"), (k(priority="P0"), "p0")]) == ["p0", "p2"]
    assert order([(k(cost_estimate=9.0), "pricey"),
                  (k(cost_estimate=1.0), "cheap")]) == ["cheap", "pricey"]
    assert order([(k(sequence=5), "b"), (k(sequence=1), "a")]) == ["a", "b"]


def test_rank_treats_no_deadline_as_latest() -> None:
    assert order([(SortKey(), "none"), (SortKey(deadline="2026-01-01T00:00:00Z"), "timed")]) == \
        ["timed", "none"]


# ------------------------------------------------------------------ 分配与循环

def test_allocate_defers_beyond_capacity_within_one_tick() -> None:
    w = World().node(NODE).node("TN-2").hire(concurrent=1)
    w.resolves(NODE, MEMBER).resolves("TN-2", MEMBER)
    scheduled, deferred = allocate(w.ports, [evaluate(w.ports, NODE), evaluate(w.ports, "TN-2")])
    assert len(scheduled) == 1
    assert deferred == ("TN-2",)


def test_tick_is_idempotent_on_second_run() -> None:
    w = World().node(NODE).hire().resolves(NODE, MEMBER)
    first = tick(w.ports)
    assert first.scheduled == ("EX-1",) and first.deferred == ()
    second = tick(w.ports)
    assert second.scheduled == () and second.deferred == ()
    assert [d.failed_conditions for d in second.decisions] == [("no_active_execution",)]


def test_tick_honours_priority_under_capacity_pressure() -> None:
    w = World().hire(concurrent=1)
    w.node("TN-low", priority="P2").node("TN-high", priority="P0")
    w.resolves("TN-low", MEMBER).resolves("TN-high", MEMBER)
    result = tick(w.ports)
    assert len(result.scheduled) == 1
    assert result.deferred == ("TN-low",)
    assert len(result.decisions) == 2
