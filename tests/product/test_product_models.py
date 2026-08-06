"""tests/product/test_product_models.py — Artifact 抽象 / Approval Gate / Workflow 模型 (Phase 9A, ADR-0026)。

覆盖: Artifact 抽象基础字段 (id/type/content/status/created_by/created_at) +
AI Artifact Lineage (provider_id/agent_id/source_events/version) + Confidence
Model (0-1 校验) + ProductIdea / ApprovalGate / ApprovalRequest / ApprovalDecision
/ ProductWorkflow 五模型默认值与 JSON 序列化。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from product.models import (
    ApprovalDecision,
    ApprovalGate,
    ApprovalRequest,
    ApprovalRequired,
    ApprovalStatus,
    Artifact,
    ProductIdea,
    ProductWorkflow,
    WorkflowStatus,
)


class TestArtifactAbstraction:
    def test_minimal_artifact(self):
        a = Artifact(id="ART-001", type="product_idea")
        assert a.id == "ART-001"
        assert a.type == "product_idea"
        assert a.content == {}
        assert a.status == "created"
        assert a.created_by == "human"
        assert a.created_at  # 默认时间戳

    def test_artifact_requires_id_and_type(self):
        with pytest.raises(ValidationError):
            Artifact()  # type: ignore[call-arg]

    def test_artifact_lineage_fields(self):
        a = Artifact(
            id="ART-002",
            type="prd",
            provider_id="hermes",
            agent_id="ag-1",
            source_events=["ev-1", "ev-2"],
            version=3,
        )
        assert a.provider_id == "hermes"
        assert a.agent_id == "ag-1"
        assert a.source_events == ["ev-1", "ev-2"]
        assert a.version == 3

    def test_artifact_lineage_defaults(self):
        a = Artifact(id="ART-003", type="prd")
        assert a.provider_id is None
        assert a.agent_id is None
        assert a.source_events == []
        assert a.version == 1

    def test_confidence_valid_range(self):
        for v in (0.0, 0.5, 1.0):
            assert Artifact(id="ART-004", type="prd", confidence=v).confidence == v

    def test_confidence_out_of_range_rejected(self):
        for v in (-0.01, 1.01, 2.0):
            with pytest.raises(ValidationError):
                Artifact(id="ART-005", type="prd", confidence=v)

    def test_version_must_be_positive(self):
        with pytest.raises(ValidationError):
            Artifact(id="ART-006", type="prd", version=0)

    def test_to_dict_json_roundtrip(self):
        a = Artifact(
            id="ART-007", type="prd",
            content={"idea_id": "PI-001"},
            source_events=["ev-1"], confidence=0.8,
        )
        d = a.to_dict()
        assert d["id"] == "ART-007"
        assert d["content"] == {"idea_id": "PI-001"}
        assert d["confidence"] == 0.8
        assert d["version"] == 1
        # model_dump(mode="json") 可再回读
        assert Artifact.model_validate(d) == a


class TestProductIdea:
    def test_defaults(self):
        i = ProductIdea(id="PI-001", title="AI 助手")
        assert i.description == ""
        assert i.goals == []
        assert i.context == {}
        assert i.status == "created"
        assert i.created_at

    def test_full_fields(self):
        i = ProductIdea(
            id="PI-002", title="t", description="d",
            goals=["g1"], context={"k": "v"}, status="refined",
        )
        assert i.goals == ["g1"]
        assert i.context == {"k": "v"}
        assert i.status == "refined"

    def test_to_dict(self):
        i = ProductIdea(id="PI-003", title="t", goals=["g"])
        d = i.to_dict()
        assert d["id"] == "PI-003"
        assert d["goals"] == ["g"]


class TestApprovalGate:
    def test_defaults(self):
        g = ApprovalGate(id="prd", artifact_type="prd")
        assert g.required == ApprovalRequired.MANDATORY.value
        assert g.rule == ""

    def test_recommended_required(self):
        g = ApprovalGate(id="architecture", artifact_type="architecture", required="recommended")
        assert g.required == "recommended"

    def test_to_dict(self):
        g = ApprovalGate(id="ui", artifact_type="ui", rule="UI 必须批准")
        d = g.to_dict()
        assert d["id"] == "ui"
        assert d["rule"] == "UI 必须批准"


class TestApprovalRequest:
    def test_defaults(self):
        r = ApprovalRequest(id="APR-001", artifact_id="ART-001", gate="prd")
        assert r.status == ApprovalStatus.PENDING.value
        assert r.by == "human"
        assert r.idea_id is None
        assert r.decided_by is None
        assert r.decided_at is None
        assert r.requested_at

    def test_full_fields(self):
        r = ApprovalRequest(
            id="APR-002", artifact_id="ART-001", gate="prd",
            idea_id="PI-001", by="alice", comment="请审",
            status="approved", decided_by="bob", decided_at="2026-01-01T00:00:00.000000Z",
        )
        assert r.idea_id == "PI-001"
        assert r.status == "approved"
        assert r.decided_by == "bob"

    def test_to_dict(self):
        r = ApprovalRequest(id="APR-003", artifact_id="ART-001", gate="prd")
        assert r.to_dict()["artifact_id"] == "ART-001"


class TestApprovalDecision:
    def test_defaults(self):
        d = ApprovalDecision(id="APD-001", request_id="APR-001")
        assert d.decision == "approved"
        assert d.decided_by == "human"
        assert d.comment == ""
        assert d.decided_at

    def test_denied_decision(self):
        d = ApprovalDecision(id="APD-002", request_id="APR-001", decision="denied", comment="no")
        assert d.decision == "denied"
        assert d.comment == "no"

    def test_to_dict(self):
        d = ApprovalDecision(id="APD-003", request_id="APR-001", decision="approved")
        assert d.to_dict()["request_id"] == "APR-001"


class TestProductWorkflow:
    def test_defaults(self):
        w = ProductWorkflow(id="PW-001", idea_id="PI-001")
        assert w.stages == []
        assert w.current_stage == ""
        assert w.status == WorkflowStatus.RUNNING.value
        assert w.product_decision is None
        assert w.created_at

    def test_full_fields(self):
        w = ProductWorkflow(
            id="PW-002", idea_id="PI-001",
            stages=["research", "prd"], current_stage="prd",
            status=WorkflowStatus.AWAITING_APPROVAL.value,
            product_decision="ART-009",
        )
        assert w.current_stage == "prd"
        assert w.status == "awaiting_approval"
        assert w.product_decision == "ART-009"

    def test_to_dict(self):
        w = ProductWorkflow(id="PW-003", idea_id="PI-001", stages=["research"])
        assert w.to_dict()["idea_id"] == "PI-001"


class TestEnums:
    def test_approval_required_values(self):
        assert ApprovalRequired.MANDATORY.value == "mandatory"
        assert ApprovalRequired.RECOMMENDED.value == "recommended"
        assert ApprovalRequired.OPTIONAL.value == "optional"

    def test_approval_status_values(self):
        assert ApprovalStatus.PENDING.value == "pending"
        assert ApprovalStatus.APPROVED.value == "approved"
        assert ApprovalStatus.DENIED.value == "denied"

    def test_workflow_status_values(self):
        assert WorkflowStatus.RUNNING.value == "running"
        assert WorkflowStatus.AWAITING_APPROVAL.value == "awaiting_approval"
        assert WorkflowStatus.COMPLETED.value == "completed"
        assert WorkflowStatus.FAILED.value == "failed"
