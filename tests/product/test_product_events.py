"""tests/product/test_product_events.py — product/idea/approval 事件辅助 (Phase 9A, ADR-0026)。

覆盖: 写路径事件 (idea.created / approval.required|granted|denied /
product.workflow.started) 由服务层发出 (source=product), 读命令审计事件
(idea.viewed / approval.viewed / product.workflow.status_viewed) source 缺省 cli,
payload 契约 (idea_id/artifact_id/gate/artifact_type/source_events/stages),
logger=None 全部静默返回 None。
"""

from __future__ import annotations

from events.models import EventType

from product.events import (
    record_approval_denied,
    record_approval_granted,
    record_approval_required,
    record_approval_viewed,
    record_idea_created,
    record_idea_updated,
    record_idea_viewed,
    record_workflow_started,
    record_workflow_status_viewed,
)
from product.models import (
    ApprovalDecision,
    ApprovalGate,
    ApprovalRequest,
    Artifact,
    ProductIdea,
    ProductWorkflow,
)

from product_helpers import event_types_of, payload_of, seed_artifact, seed_idea


def _idea() -> ProductIdea:
    return ProductIdea(id="PI-001", title="AI 助手", goals=["g1"])


def _artifact() -> Artifact:
    return Artifact(id="ART-001", type="prd", source_events=["ev-1"])


def _gate() -> ApprovalGate:
    return ApprovalGate(id="prd", artifact_type="prd", required="mandatory", rule="r")


def _request() -> ApprovalRequest:
    return ApprovalRequest(id="APR-001", artifact_id="ART-001", gate="prd", idea_id="PI-001")


def _decision() -> ApprovalDecision:
    return ApprovalDecision(id="APD-001", request_id="APR-001", decision="approved", decided_by="bob")


def _workflow() -> ProductWorkflow:
    return ProductWorkflow(id="PW-001", idea_id="PI-001", stages=["research", "prd"], current_stage="research")


class TestWritePathEvents:
    def test_idea_created_event(self, logger):
        ev = record_idea_created(logger, idea=_idea(), artifact=_artifact())
        assert ev.type == EventType.IDEA_CREATED
        assert ev.source == "product"
        assert ev.stage == "created"
        assert ev.payload["idea_id"] == "PI-001"
        assert ev.payload["artifact_id"] == "ART-001"
        assert ev.payload["goals"] == ["g1"]

    def test_approval_required_event(self, logger):
        ev = record_approval_required(logger, request=_request(), gate=_gate(), artifact=_artifact())
        assert ev.type == EventType.APPROVAL_REQUIRED
        assert ev.payload["gate"] == "prd"
        assert ev.payload["artifact_type"] == "prd"
        assert ev.payload["required"] == "mandatory"
        assert ev.payload["idea_id"] == "PI-001"
        assert ev.payload["source_events"] == ["ev-1"]  # Lineage 摘要

    def test_approval_granted_event(self, logger):
        ev = record_approval_granted(
            logger, request=_request(), decision=_decision(), artifact=_artifact()
        )
        assert ev.type == EventType.APPROVAL_GRANTED
        assert ev.result == "APPROVED"
        assert ev.payload["decision"] == "approved"
        assert ev.payload["decided_by"] == "bob"
        assert ev.payload["artifact_type"] == "prd"

    def test_approval_denied_event(self, logger):
        d = ApprovalDecision(id="APD-002", request_id="APR-001", decision="denied", comment="no")
        ev = record_approval_denied(logger, request=_request(), decision=d, artifact=_artifact())
        assert ev.type == EventType.APPROVAL_DENIED
        assert ev.result == "DENIED"
        assert ev.payload["comment"] == "no"

    def test_workflow_started_event(self, logger):
        ev = record_workflow_started(logger, workflow=_workflow())
        assert ev.type == EventType.PRODUCT_WORKFLOW_STARTED
        assert ev.payload["stages"] == ["research", "prd"]
        assert ev.payload["current_stage"] == "research"
        assert ev.payload["idea_id"] == "PI-001"


class TestReadAuditEvents:
    def test_idea_viewed_default_source_cli(self, logger):
        ev = record_idea_viewed(logger, count=2, idea_id="PI-001")
        assert ev.type == EventType.IDEA_VIEWED
        assert ev.source == "cli"
        assert ev.payload == {"count": 2, "idea_id": "PI-001"}

    def test_approval_viewed_event(self, logger):
        ev = record_approval_viewed(logger, count=1, pending_only=True)
        assert ev.type == EventType.APPROVAL_VIEWED
        assert ev.payload == {"count": 1, "pending_only": True}

    def test_workflow_status_viewed_event(self, logger):
        ev = record_workflow_status_viewed(logger, workflow=_workflow())
        assert ev.type == EventType.PRODUCT_WORKFLOW_STATUS_VIEWED
        assert ev.payload["current_stage"] == "research"
        assert ev.payload["status"] == "running"
        assert ev.payload["product_decision"] is None

    def test_idea_updated_event(self, logger):
        ev = record_idea_updated(logger, idea=_idea())
        assert ev.type == EventType.IDEA_UPDATED
        assert ev.payload["status"] == "created"


class TestNoneLoggerSilent:
    def test_all_helpers_return_none_without_logger(self):
        assert record_idea_created(None, idea=_idea()) is None
        assert record_idea_viewed(None, count=1) is None
        assert record_idea_updated(None, idea=_idea()) is None
        assert record_approval_required(None, request=_request()) is None
        assert record_approval_granted(None, request=_request(), decision=_decision()) is None
        assert record_approval_denied(None, request=_request(), decision=_decision()) is None
        assert record_approval_viewed(None, count=1) is None
        assert record_workflow_started(None, workflow=_workflow()) is None
        assert record_workflow_status_viewed(None, workflow=_workflow()) is None


class TestServiceIntegration:
    def test_create_idea_emits_idea_created(self, event_service):
        event_service.create_idea("t")
        assert "idea.created" in event_types_of(event_service._logger.store)

    def test_full_approval_chain_event_types(self, event_service):
        idea = seed_idea(event_service)
        a = seed_artifact(event_service, "prd", idea_id=idea.id)
        r = event_service.request_approval(a.id)
        event_service.decide_approval(r.id, "approved")
        types = event_types_of(event_service._logger.store)
        assert "idea.created" in types
        assert "approval.required" in types
        assert "approval.granted" in types
        assert "approval.denied" not in types

    def test_deny_chain_emits_denied(self, event_service):
        idea = seed_idea(event_service)
        a = seed_artifact(event_service, "prd", idea_id=idea.id)
        r = event_service.request_approval(a.id)
        event_service.decide_approval(r.id, "denied")
        types = event_types_of(event_service._logger.store)
        assert "approval.denied" in types
        assert "approval.granted" not in types

    def test_workflow_started_event_payload(self, event_service):
        idea = seed_idea(event_service)
        event_service.start_workflow(idea.id)
        payload = payload_of(event_service._logger.store, "product.workflow.started")
        assert payload["workflow_id"] == "PW-001"
        assert payload["current_stage"] == "research"
