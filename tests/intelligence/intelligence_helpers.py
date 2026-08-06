"""tests/intelligence/intelligence_helpers.py — Intelligence 测试 helper (唯一名)。

工厂函数用固定 id/时间戳, 保证确定性断言 (created_at 默认时间戳的 round-trip
相等断言必失败 — 落盘读回保留原始时间戳, 逐字段比较 + created_at 相等即可)。
"""

from __future__ import annotations

from pathlib import Path

from events.store import EventStore

from intelligence.models import (
    Decision,
    Evidence,
    ExperienceRecord,
    Recommendation,
)
from intelligence.store import (
    DecisionStore,
    ExperienceStore,
    RecommendationStore,
)

#: 固定时间戳 (TS_FORMAT, 6 位微秒 — parse_timestamp 可解析)
TS_OLD = "2026-01-01T00:00:00.000000Z"
TS_MID = "2026-01-15T00:00:00.000000Z"
TS_LATE = "2026-03-02T00:00:00.000000Z"


def make_store(kind: str, intelligence_dir: Path):
    """构造指定 Store (测试内直接构造, 不依赖 fixture)。"""
    if kind == "decision":
        return DecisionStore(intelligence_dir)
    if kind == "recommendation":
        return RecommendationStore(intelligence_dir)
    if kind == "experience":
        return ExperienceStore(intelligence_dir)
    raise ValueError(f"unknown store kind {kind!r}")


def make_evidence(
    source_id: str = "evt-1",
    source_type: str = "event",
    description: str = "execution succeeded",
    confidence: float = 0.9,
    timestamp: str = TS_OLD,
) -> Evidence:
    return Evidence(
        source_type=source_type,
        source_id=source_id,
        description=description,
        confidence=confidence,
        timestamp=timestamp,
    )


def make_decision(
    decision_id: str = "dec-1",
    subject_id: str = "task-1",
    created_at: str = TS_OLD,
    **kw,
) -> Decision:
    base = dict(
        decision_type="provider_selection",
        subject_id=subject_id,
        description="choose provider for task",
        options=[{"id": "a", "title": "Option A"}, {"id": "b", "title": "Option B"}],
        recommendation="a",
        confidence=0.8,
        risk=0.2,
        evidence=[make_evidence()],
        created_at=created_at,
    )
    base.update(kw)
    return Decision(id=decision_id, **base)


def make_recommendation(
    rec_id: str = "rec-1",
    target_type: str = "provider",
    target_id: str = "hermes",
    created_at: str = TS_OLD,
    **kw,
) -> Recommendation:
    base = dict(
        target_type=target_type,
        target_id=target_id,
        score=0.92,
        reasoning=["capability match", "low cost"],
        evidence=[make_evidence(source_id="evt-1")],
        confidence=0.7,
        risk=0.1,
        created_at=created_at,
    )
    base.update(kw)
    return Recommendation(id=rec_id, **base)


def make_experience(
    exp_id: str = "exp-1",
    domain: str = "provider",
    subject_id: str = "hermes",
    result: str = "success",
    score: float = 0.95,
    confidence: float = 0.9,
    created_at: str = TS_OLD,
    last_used: str | None = None,
    usage_count: int = 0,
    freshness: float = 1.0,
) -> ExperienceRecord:
    return ExperienceRecord(
        id=exp_id,
        domain=domain,
        subject_id=subject_id,
        result=result,
        score=score,
        confidence=confidence,
        created_at=created_at,
        last_used=last_used,
        usage_count=usage_count,
        freshness=freshness,
    )


def assert_decision_equal(got: Decision, expected: Decision) -> None:
    """逐字段相等 (created_at 默认时间戳陷阱: 断言相等而非构造新 helper)。"""
    assert got.id == expected.id
    assert got.decision_type == expected.decision_type
    assert got.subject_id == expected.subject_id
    assert got.description == expected.description
    assert got.options == expected.options
    assert got.recommendation == expected.recommendation
    assert got.confidence == expected.confidence
    assert got.risk == expected.risk
    assert [e.lineage_ref() for e in got.evidence] == [e.lineage_ref() for e in expected.evidence]
    assert got.status == expected.status
    assert got.approval_request_id == expected.approval_request_id
    assert got.created_at == expected.created_at


def assert_recommendation_equal(got: Recommendation, expected: Recommendation) -> None:
    assert got.id == expected.id
    assert got.target_type == expected.target_type
    assert got.target_id == expected.target_id
    assert got.score == expected.score
    assert got.reasoning == expected.reasoning
    assert [e.lineage_ref() for e in got.evidence] == [e.lineage_ref() for e in expected.evidence]
    assert got.confidence == expected.confidence
    assert got.risk == expected.risk
    assert got.created_at == expected.created_at


def assert_experience_equal(got: ExperienceRecord, expected: ExperienceRecord) -> None:
    assert got.id == expected.id
    assert got.domain == expected.domain
    assert got.subject_id == expected.subject_id
    assert got.result == expected.result
    assert got.score == expected.score
    assert got.confidence == expected.confidence
    assert got.created_at == expected.created_at
    assert got.last_used == expected.last_used
    assert got.usage_count == expected.usage_count
    assert got.freshness == expected.freshness


# ------------------------------------------------------------------ 事件断言


def event_types_of(store: EventStore) -> list[str]:
    """事件类型列表 (断言审计链)。"""
    return [e.type.value for e in store.query()]


def payload_of(store: EventStore, event_type: str) -> dict:
    """最后一条指定类型事件的 payload。"""
    events = [e for e in store.query() if e.type.value == event_type]
    assert events, f"no event of type {event_type!r}"
    return events[-1].payload


def event_sequence(store: EventStore) -> list[str]:
    """全部事件类型序列 (按 seq 升序, 断言链序)。"""
    return [e.type.value for e in store.query()]
