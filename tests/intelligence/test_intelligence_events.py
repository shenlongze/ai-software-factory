"""tests/intelligence/test_intelligence_events.py — 4 事件链序/payload (Phase 10A-1)。

覆盖: intelligence.decision.created / recommendation.created / experience.recorded
/ viewed 的发射、payload 契约、链序 (seq 升序)、logger=None 静默、EventType 枚举
扩展与既有成员零影响 (Backward compatibility)。
"""

from __future__ import annotations

from events.models import EventType
from events.store import EventStore

from intelligence.events import (
    record_decision_created,
    record_experience_recorded,
    record_intelligence_viewed,
    record_recommendation_created,
)

from intelligence_helpers import (
    event_sequence,
    event_types_of,
    make_decision,
    make_experience,
    make_recommendation,
    payload_of,
)


class TestDecisionCreatedEvent:
    def test_emits_with_payload(self, logger, event_store: EventStore):
        d = make_decision(confidence=0.8, risk=0.2, evidence=None)
        record_decision_created(logger, decision=d)
        assert event_types_of(event_store) == ["intelligence.decision.created"]
        payload = payload_of(event_store, "intelligence.decision.created")
        assert payload["decision_id"] == "dec-1"
        assert payload["decision_type"] == "provider_selection"
        assert payload["subject_id"] == "task-1"
        assert payload["recommendation"] == "a"
        assert payload["confidence"] == 0.8
        assert payload["risk"] == 0.2
        assert payload["evidence_count"] == 0
        assert payload["approval_request_id"] is None

    def test_stage_is_status(self, logger, event_store: EventStore):
        d = make_decision(status="recommended")
        record_decision_created(logger, decision=d)
        ev = event_store.query()[-1]
        assert ev.stage == "recommended"
        assert ev.source == "intelligence"
        assert ev.result == "OK"
        assert ev.action == "create intelligence decision"

    def test_evidence_count_reflects_list(self, logger, event_store: EventStore):
        record_decision_created(logger, decision=make_decision())
        assert payload_of(event_store, "intelligence.decision.created")["evidence_count"] == 1


class TestRecommendationCreatedEvent:
    def test_emits_with_payload(self, logger, event_store: EventStore):
        r = make_recommendation()
        record_recommendation_created(logger, recommendation=r)
        payload = payload_of(event_store, "intelligence.recommendation.created")
        assert payload["recommendation_id"] == "rec-1"
        assert payload["target_type"] == "provider"
        assert payload["target_id"] == "hermes"
        assert payload["score"] == 0.92
        assert payload["confidence"] == 0.7
        assert payload["risk"] == 0.1
        assert payload["reasoning_count"] == 2
        assert payload["evidence_count"] == 1

    def test_stage_and_source(self, logger, event_store: EventStore):
        record_recommendation_created(logger, recommendation=make_recommendation())
        ev = event_store.query()[-1]
        assert ev.stage == "recommended"
        assert ev.source == "intelligence"
        assert ev.type == EventType.INTELLIGENCE_RECOMMENDATION_CREATED

    def test_explanation_not_in_payload_but_counted(self, logger, event_store: EventStore):
        """reasoning 全文不入事件 payload (事件只承载锚点 + 计数, KISS)。"""
        record_recommendation_created(
            logger, recommendation=make_recommendation(reasoning=["r1", "r2", "r3"])
        )
        payload = payload_of(event_store, "intelligence.recommendation.created")
        assert payload["reasoning_count"] == 3
        assert "reasoning" not in payload


class TestExperienceRecordedEvent:
    def test_emits_with_payload(self, logger, event_store: EventStore):
        e = make_experience(result="failure", score=0.2)
        record_experience_recorded(logger, experience=e)
        payload = payload_of(event_store, "intelligence.experience.recorded")
        assert payload["experience_id"] == "exp-1"
        assert payload["domain"] == "provider"
        assert payload["subject_id"] == "hermes"
        assert payload["result"] == "failure"
        assert payload["score"] == 0.2
        assert payload["confidence"] == 0.9

    def test_result_stage(self, logger, event_store: EventStore):
        record_experience_recorded(logger, experience=make_experience())
        ev = event_store.query()[-1]
        assert ev.result == "SUCCESS"
        assert ev.stage == "recorded"
        assert ev.source == "intelligence"


class TestViewedEvent:
    def test_emits_with_payload(self, logger, event_store: EventStore):
        record_intelligence_viewed(logger, view="experiences", count=3)
        payload = payload_of(event_store, "intelligence.viewed")
        assert payload == {"view": "experiences", "count": 3}

    def test_source_default_cli(self, logger, event_store: EventStore):
        """读命令审计: source 缺省 cli (ADR-0002), 写路径事件 source=intelligence。"""
        record_intelligence_viewed(logger, view="decisions", count=0)
        ev = event_store.query()[-1]
        assert ev.source == "cli"
        assert ev.stage == "viewed"


class TestEventChain:
    def test_full_chain_sequence(self, logger, event_store: EventStore):
        """写路径 3 事件 + 读审计 1 事件, 链序 = seq 升序。"""
        record_decision_created(logger, decision=make_decision())
        record_recommendation_created(logger, recommendation=make_recommendation())
        record_experience_recorded(logger, experience=make_experience())
        record_intelligence_viewed(logger, view="all", count=3)
        assert event_sequence(event_store) == [
            "intelligence.decision.created",
            "intelligence.recommendation.created",
            "intelligence.experience.recorded",
            "intelligence.viewed",
        ]
        seqs = [e.seq for e in event_store.query()]
        assert seqs == sorted(seqs)  # seq 单调递增
        assert seqs == [1, 2, 3, 4]

    def test_events_persisted_and_queryable(self, db_path, logger, event_store: EventStore):
        record_decision_created(logger, decision=make_decision())
        event_store.close()
        # 重新打开事件库: 事件已持久化 (事件是唯一事实源)
        reopened = EventStore(db_path)
        assert [e.type.value for e in reopened.query()] == ["intelligence.decision.created"]
        reopened.close()


class TestLoggerNone:
    def test_decision_helper_silent(self):
        assert record_decision_created(None, decision=make_decision()) is None

    def test_recommendation_helper_silent(self):
        assert record_recommendation_created(None, recommendation=make_recommendation()) is None

    def test_experience_helper_silent(self):
        assert record_experience_recorded(None, experience=make_experience()) is None

    def test_viewed_helper_silent(self):
        assert record_intelligence_viewed(None, view="x", count=0) is None


class TestEventTypeEnumExtension:
    def test_new_members_exist(self):
        assert EventType.INTELLIGENCE_DECISION_CREATED.value == "intelligence.decision.created"
        assert EventType.INTELLIGENCE_RECOMMENDATION_CREATED.value == "intelligence.recommendation.created"
        assert EventType.INTELLIGENCE_EXPERIENCE_RECORDED.value == "intelligence.experience.recorded"
        assert EventType.INTELLIGENCE_VIEWED.value == "intelligence.viewed"

    def test_legacy_members_unchanged(self):
        """Backward compatibility: 既有事件值逐位不变 (120 → 124 纯增量)。"""
        assert EventType.TASK_START.value == "task.start"
        assert EventType.APPROVAL_APPROVED.value == "approval.approved"
        assert EventType.APPROVAL_REQUIRED.value == "approval.required"
        assert EventType.PRODUCT_LIFECYCLE_COMPLETED.value == "product.lifecycle.completed"
        assert EventType.PROVIDER_USAGE_RECORDED.value == "provider.usage.recorded"
        assert EventType.INTELLIGENCE_VIEWED in EventType

    def test_total_member_count(self):
        # 124 (10A-1) → 127: 10A-2 决策链 +3 (analysis.started/analysis.completed/
        # option.evaluated); 127 → 131: 10A-3 推荐链 +4 (recommendation.started/
        # candidate.evaluated/explained/completed); 131 → 134: 10A-4 经验闭环 +3
        # (experience.analyzed / task.evaluated / feedback.learned, ADR-0033);
        # 134 → 137: 11A Human Console +3 (console.viewed / console.approval.opened
        # / console.dashboard.viewed, ADR-0034); 137 → 151: 16A Organization
        # Extension +14 (org.* 14 事件, ADR-0036); 151 → 158: Phase A Execution
        # Extension +7 (org.execution.* 7 事件, ADR-0037 — factory-exec:
        # requested/started/completed/failed/approved/applied + viewed 读审计);
        # 158 → 165: S7-001 Organization Model +7 (org.project.created /
        # org.sprint.created / org.stage.created / org.artifact.created /
        # org.project.lifecycle_changed / org.project.task_linked /
        # org.sprint.task_added, ADR-0039)。
        # 纯增量扩展 (ADR-0001 决策 1 路径, 既有值零改动)
        assert len(EventType) == 165
        assert EventType.ORG_PROJECT_CREATED.value == "org.project.created"
        assert EventType.ORG_SPRINT_CREATED.value == "org.sprint.created"
        assert EventType.ORG_STAGE_CREATED.value == "org.stage.created"
        assert EventType.ORG_ARTIFACT_CREATED.value == "org.artifact.created"
        assert EventType.ORG_PROJECT_LIFECYCLE_CHANGED.value == "org.project.lifecycle_changed"
        assert EventType.ORG_PROJECT_TASK_LINKED.value == "org.project.task_linked"
        assert EventType.ORG_SPRINT_TASK_ADDED.value == "org.sprint.task_added"

    def test_event_accepts_new_type_string(self):
        from events.models import Event

        ev = Event.create("intelligence.decision.created", source="test")
        assert ev.type == EventType.INTELLIGENCE_DECISION_CREATED
