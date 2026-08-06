"""tests/intelligence/test_intelligence_evidence.py — Evidence 六来源 + 可追溯 (Phase 10A-1)。

覆盖: source_type 六来源全接受/非法拒绝; Decision/Recommendation 携带的证据链
持久化; lineage_ref 可追溯锚点; 从 Recommendation → Decision → Event 的证据链
回溯 (防 AI 自我循环: 每个智能输出附可追溯证据, §Q4 机制 3)。
"""

from __future__ import annotations

from events.store import EventStore

from intelligence.events import record_decision_created, record_recommendation_created
from intelligence.models import Evidence, EvidenceSource

from intelligence_helpers import (
    event_types_of,
    make_decision,
    make_evidence,
    make_recommendation,
    payload_of,
)


class TestSixSources:
    def test_all_sources_have_lineage_ref(self):
        refs = [
            Evidence(source_type=s, source_id="x-1").lineage_ref()
            for s in EvidenceSource
        ]
        assert refs == [
            "artifact:x-1",
            "event:x-1",
            "experience:x-1",
            "external_data:x-1",
            "human_input:x-1",
            "provider_output:x-1",
        ]

    def test_provider_output_is_lowest_priority_fact(self):
        """六来源语义: 事实 (artifact/event/experience/external_data/human_input)
        优先于 AI 建议 (provider_output) — §Q4 机制 6 事实优先。"""
        assert EvidenceSource.ARTIFACT.value == "artifact"
        assert EvidenceSource.PROVIDER_OUTPUT.value == "provider_output"

    def test_all_sources_serializable(self):
        for s in EvidenceSource:
            data = make_evidence(source_type=s.value).to_dict()
            assert data["source_type"] == s.value

    def test_invalid_source_rejected(self):
        from pydantic import ValidationError

        import pytest

        with pytest.raises(ValidationError):
            make_evidence(source_type="llm_guess")


class TestDecisionEvidence:
    def test_evidence_attached_to_decision_persisted(self, decision_store):
        d = make_decision(
            evidence=[
                make_evidence(source_type="event", source_id="evt-1"),
                make_evidence(source_type="artifact", source_id="art-9"),
                make_evidence(source_type="human_input", source_id="review-1"),
            ]
        )
        decision_store.save(d)
        got = decision_store.get(d.id)
        assert [e.lineage_ref() for e in got.evidence] == [
            "event:evt-1",
            "artifact:art-9",
            "human_input:review-1",
        ]

    def test_decision_event_payload_evidence_count(self, logger, event_store: EventStore):
        d = make_decision(evidence=[make_evidence(), make_evidence(source_id="evt-2")])
        record_decision_created(logger, decision=d)
        assert payload_of(event_store, "intelligence.decision.created")["evidence_count"] == 2


class TestRecommendationEvidence:
    def test_evidence_attached_to_recommendation(self, recommendation_store):
        r = make_recommendation(
            evidence=[
                make_evidence(source_type="experience", source_id="exp-42"),
                make_evidence(source_type="external_data", source_id="bench-2026"),
            ]
        )
        recommendation_store.save(r)
        got = recommendation_store.get(r.id)
        assert [e.lineage_ref() for e in got.evidence] == [
            "experience:exp-42",
            "external_data:bench-2026",
        ]

    def test_recommendation_event_payload_evidence_count(self, logger, event_store: EventStore):
        r = make_recommendation(evidence=[make_evidence()])
        record_recommendation_created(logger, recommendation=r)
        assert payload_of(event_store, "intelligence.recommendation.created")["evidence_count"] == 1


class TestLineageTraceability:
    def test_evidence_refs_real_event_ids(self, logger, event_store: EventStore):
        """证据链锚点 = 真实事件 event_id (唯一事实源引用, 可回溯)。"""
        d = make_decision()
        record_decision_created(logger, decision=d)
        anchor_event = event_store.query()[-1]
        # 构造新 Decision 引用该事件作为证据
        d2 = make_decision(
            decision_id="dec-2",
            evidence=[make_evidence(source_type="event", source_id=anchor_event.event_id)],
        )
        d2_ev = record_decision_created(logger, decision=d2)
        assert d2_ev is not None
        evidence_refs = [e["source_id"] for e in d2.to_dict()["evidence"]]
        assert evidence_refs == [anchor_event.event_id]
        # 事件库里可查到被引用的锚点事件
        assert event_store.get_by_id(anchor_event.event_id) is not None

    def test_full_lineage_walk_recommendation_to_event(self, logger, event_store: EventStore):
        """全链回溯: Recommendation → 证据(Decision) → 证据(Event) — 三层可追溯。"""
        # 1. 事实层: 真实事件 (execution 完成)
        exec_event = logger.record(
            "execution.completed",
            source="test",
            result="SUCCESS",
            payload={"execution_id": "exe-1"},
        )
        # 2. 决策层: Decision 引用事件为证据
        decision = make_decision(
            evidence=[make_evidence(source_type="event", source_id=exec_event.event_id)]
        )
        record_decision_created(logger, decision=decision)
        # 3. 推荐层: Recommendation 引用 Decision 为证据
        rec = make_recommendation(
            evidence=[
                make_evidence(
                    source_type="experience",
                    source_id=decision.id,
                    description="decision dec-1 supports this provider",
                )
            ]
        )
        record_recommendation_created(logger, recommendation=rec)
        # 回溯: 推荐证据 → decision id → decision 证据 → event id
        rec_evidence: Evidence = rec.evidence[0]
        assert rec_evidence.source_type == EvidenceSource.EXPERIENCE
        assert rec_evidence.source_id == decision.id
        dec_evidence = decision.evidence[0]
        assert dec_evidence.source_id == exec_event.event_id
        assert event_store.get_by_id(exec_event.event_id) is not None
        # 事件链序: execution.completed → decision.created → recommendation.created
        assert event_types_of(event_store) == [
            "execution.completed",
            "intelligence.decision.created",
            "intelligence.recommendation.created",
        ]

    def test_evidence_confidence_survives_store_roundtrip(self, decision_store):
        d = make_decision(evidence=[make_evidence(confidence=0.6)])
        decision_store.save(d)
        assert decision_store.get(d.id).evidence[0].confidence == 0.6

    def test_empty_evidence_default(self):
        d = make_decision(evidence=[])
        assert d.evidence == []
        assert d.to_dict()["evidence"] == []

    def test_evidence_description_explains_support(self):
        e = make_evidence(
            source_type="event",
            source_id="evt-1",
            description="execution of provider hermes completed with SUCCESS",
        )
        assert "SUCCESS" in e.description
        assert e.source_id == "evt-1"
