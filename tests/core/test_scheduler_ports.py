"""core.scheduler.ports —— 端口契约与唯一注入点。"""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from ai_factory_os.contracts.execution import Execution
from ai_factory_os.contracts.governance import GateKind
from ai_factory_os.core.scheduler.ports import (
    ClockPort,
    ExecutionPort,
    GatePort,
    LoadPort,
    Ports,
    ResourcePort,
    WorkPort,
)


class FakeClock:
    def now_iso(self) -> str:
        return "2026-01-01T00:00:00Z"


class FakeWork:
    def get_node(self, node_id: str): return None
    def list_nodes(self, task_id: str = ""): return []
    def has_accepted_outcome(self, node_id: str) -> bool: return False
    def deadline_of(self, node_id: str) -> str: return ""
    def priority_of(self, node_id: str) -> str: return "P2"


class FakeResource:
    def resolution_for(self, node_id: str): return None
    def member(self, member_id: str): return None
    def capability(self, capability_id: str): return None


class FakeLoad:
    def active_count(self, member_id: str) -> int: return 0
    def remaining_budget(self, scope_ref: str) -> float: return 0.0


class FakeGate:
    def is_approved(self, subject_ref: str, kind: GateKind = GateKind.BEFORE) -> bool: return False


class FakeExecution:
    def active_for(self, node_id: str): return None

    def create(self, node_id: str, *, resolution_id: str,
               member_id: str, identity_id: str) -> Execution:
        return Execution(id="EX-1", task_node_id=node_id, resolution_id=resolution_id,
                         member_id=member_id, actor_identity_id=identity_id)


def _ports() -> Ports:
    return Ports(clock=FakeClock(), work=FakeWork(), resource=FakeResource(),
                 load=FakeLoad(), gate=FakeGate(), execution=FakeExecution())


def test_fakes_conform_to_protocols() -> None:
    assert isinstance(FakeClock(), ClockPort)
    assert isinstance(FakeWork(), WorkPort)
    assert isinstance(FakeResource(), ResourcePort)
    assert isinstance(FakeLoad(), LoadPort)
    assert isinstance(FakeGate(), GatePort)
    assert isinstance(FakeExecution(), ExecutionPort)


def test_ports_bundle_is_the_injection_point() -> None:
    p = _ports()
    ex = p.execution.create("TN-1", resolution_id="RS-1", member_id="M-1", identity_id="ID-1")
    assert ex.id == "EX-1"
    assert p.clock.now_iso() == "2026-01-01T00:00:00Z"
    assert p.load.active_count("M-1") == 0


def test_ports_are_frozen() -> None:
    p = _ports()
    with pytest.raises(FrozenInstanceError):
        p.gate = FakeGate()  # type: ignore[misc]
