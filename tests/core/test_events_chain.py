"""core.events —— 链式事实的封存、校验与检索。"""
from __future__ import annotations

from dataclasses import replace

from ai_factory_os.contracts.events import Event, EventQuery
from ai_factory_os.core.events.append import GENESIS, seal, verify_chain
from ai_factory_os.core.events.query import latest, select


def _chain(n: int = 3) -> list[Event]:
    events: list[Event] = []
    prev: Event | None = None
    for i in range(n):
        draft = Event(id=f"EV-{i}", type="execution.finished",
                      at=f"2026-01-0{i + 1}T00:00:00Z", actor_id="ID-1",
                      subject_ref=f"TN-{i}", payload=(("k", str(i)),))
        prev = seal(prev, draft)
        events.append(prev)
    return events


def test_first_event_chains_to_genesis() -> None:
    first = _chain(1)[0]
    assert first.prev_hash == GENESIS
    assert len(first.hash) == 64


def test_seal_does_not_mutate_draft() -> None:
    draft = Event(id="EV-9", type="t", at="now")
    sealed = seal(None, draft)
    assert draft.prev_hash == "" and draft.hash == ""
    assert sealed.hash != ""


def test_chain_is_continuous_and_valid() -> None:
    events = _chain(3)
    assert events[1].prev_hash == events[0].hash
    assert verify_chain(events) is True


def test_tampering_breaks_the_chain() -> None:
    events = _chain(3)
    events[1] = replace(events[1], subject_ref="TN-X")
    assert verify_chain(events) is False


def test_select_filters_and_latest() -> None:
    events = _chain(3)
    assert len(select(events, EventQuery(type="execution.finished"))) == 3
    assert len(select(events, EventQuery(subject_ref="TN-2"))) == 1
    assert len(select(events, EventQuery(since="2026-01-02T00:00:00Z"))) == 2
    last = latest(events, EventQuery())
    assert last is not None and last.id == "EV-2"
    assert latest(events, EventQuery(subject_ref="nope")) is None
