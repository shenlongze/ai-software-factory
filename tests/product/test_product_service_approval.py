"""tests/product/test_product_service_approval.py — Approval Gate: 任何 Artifact 可申请 (Phase 9A, ADR-0026)。

覆盖: DEFAULT_GATES (prd/ui mandatory, architecture recommended)、默认门自动注册、
product_idea 无默认门 → ProductError (设计行为)、显式 --gate / 自定义门 save_gate、
idea_id 从 artifact.content 推导、pending → approved|denied 终态不可逆 (重复 decide
抛错)、无效 decision 抛错、请求未找到抛 ProductNotFoundError、approve 产生
Product Decision Artifact (Lineage 继承 + source_events 锚定)、pending 过滤。
"""

from __future__ import annotations

import pytest

from product.service import DEFAULT_GATES, ProductError, ProductNotFoundError

from product_helpers import seed_artifact, seed_gate, seed_idea


class TestDefaultGates:
    def test_default_gates_definition(self):
        assert set(DEFAULT_GATES) == {"prd", "ui", "architecture"}
        assert DEFAULT_GATES["prd"][0] == "mandatory"
        assert DEFAULT_GATES["ui"][0] == "mandatory"
        assert DEFAULT_GATES["architecture"][0] == "recommended"


class TestRequestApproval:
    def test_request_prd_artifact_uses_default_gate(self, service):
        a = seed_artifact(service, "prd")
        request = service.request_approval(a.id)
        assert request.id == "APR-001"
        assert request.artifact_id == a.id
        assert request.gate == "prd"
        assert request.status == "pending"

    def test_request_registers_default_gate_automatically(self, service):
        a = seed_artifact(service, "prd")
        service.request_approval(a.id)
        gate = service._store.get_gate("prd")
        assert gate is not None
        assert gate.required == "mandatory"

    def test_request_product_idea_without_gate_raises(self, service):
        # Idea 即 Artifact, 但 product_idea 类型无默认门 — 设计行为 (提示显式门/注册门)
        idea = seed_idea(service)
        artifact = service.get_artifact_by_idea(idea.id)
        with pytest.raises(ProductError) as exc:
            service.request_approval(artifact.id)
        assert "no approval gate" in str(exc.value)
        assert "product_idea" in str(exc.value)

    def test_request_product_idea_with_explicit_gate(self, service):
        idea = seed_idea(service)
        artifact = service.get_artifact_by_idea(idea.id)
        request = service.request_approval(artifact.id, gate_id="prd")
        assert request.gate == "prd"
        assert request.idea_id == idea.id  # 从 artifact.content.idea_id 推导

    def test_request_with_custom_saved_gate(self, service):
        seed_gate(service, "research", required="optional")
        a = seed_artifact(service, "research")
        request = service.request_approval(a.id)
        assert request.gate == "research"

    def test_request_with_unknown_custom_type_raises(self, service):
        a = seed_artifact(service, "deployment")
        with pytest.raises(ProductError):
            service.request_approval(a.id)

    def test_request_missing_artifact_raises(self, service):
        with pytest.raises(ProductNotFoundError):
            service.request_approval("ART-999")

    def test_request_idea_id_override(self, service):
        a = seed_artifact(service, "prd")
        request = service.request_approval(a.id, idea_id="PI-042")
        assert request.idea_id == "PI-042"

    def test_request_by_and_note(self, service):
        a = seed_artifact(service, "prd")
        request = service.request_approval(a.id, by="alice", note="请审 PRD")
        assert request.by == "alice"
        assert request.comment == "请审 PRD"

    def test_request_id_increments(self, service):
        a = seed_artifact(service, "prd")
        service.request_approval(a.id)
        b = seed_artifact(service, "ui")
        r2 = service.request_approval(b.id)
        assert r2.id == "APR-002"


class TestDecideApproval:
    def test_approve_transitions_request(self, service):
        a = seed_artifact(service, "prd")
        request = service.request_approval(a.id)
        request2, decision, _ = service.decide_approval(request.id, "approved", by="bob", comment="ok")
        assert request2.status == "approved"
        assert request2.decided_by == "bob"
        assert request2.decided_at
        assert decision.decision == "approved"
        assert decision.request_id == request.id
        assert decision.decided_by == "bob"
        assert decision.comment == "ok"

    def test_deny_transitions_request(self, service):
        a = seed_artifact(service, "prd")
        request = service.request_approval(a.id)
        request2, decision, artifact = service.decide_approval(request.id, "denied", comment="no")
        assert request2.status == "denied"
        assert decision.decision == "denied"
        assert artifact is None  # denied 不产生 Product Decision

    def test_deny_accepts_uppercase(self, service):
        a = seed_artifact(service, "prd")
        request = service.request_approval(a.id)
        request2, _, _ = service.decide_approval(request.id, "APPROVED")
        assert request2.status == "approved"

    def test_invalid_decision_raises(self, service):
        a = seed_artifact(service, "prd")
        request = service.request_approval(a.id)
        with pytest.raises(ProductError):
            service.decide_approval(request.id, "maybe")

    def test_decide_twice_raises_terminal(self, service):
        a = seed_artifact(service, "prd")
        request = service.request_approval(a.id)
        service.decide_approval(request.id, "approved")
        with pytest.raises(ProductError) as exc:
            service.decide_approval(request.id, "denied")
        assert "already approved" in str(exc.value)

    def test_decide_missing_request_raises(self, service):
        with pytest.raises(ProductNotFoundError):
            service.decide_approval("APR-999", "approved")

    def test_decision_id_increments(self, service):
        a = seed_artifact(service, "prd")
        r1 = service.request_approval(a.id)
        _, d1, _ = service.decide_approval(r1.id, "approved")
        b = seed_artifact(service, "ui")
        r2 = service.request_approval(b.id)
        _, d2, _ = service.decide_approval(r2.id, "approved")
        assert d1.id == "APD-001"
        assert d2.id == "APD-002"


class TestProductDecisionArtifact:
    def test_approve_creates_product_decision(self, service):
        a = seed_artifact(service, "prd", idea_id="PI-001", confidence=0.8, provider_id="hermes")
        request = service.request_approval(a.id)
        _, decision, decision_artifact = service.decide_approval(request.id, "approved", comment="ok")
        assert decision_artifact is not None
        assert decision_artifact.type == "product_decision"
        assert decision_artifact.status == "approved"
        assert decision_artifact.content["request_id"] == request.id
        assert decision_artifact.content["artifact_id"] == a.id
        assert decision_artifact.content["decision"] == "approved"
        assert decision_artifact.content["idea_id"] == "PI-001"

    def test_decision_artifact_lineage_inherited(self, service, event_service):
        a = seed_artifact(service, "prd", provider_id="hermes", agent_id="ag-1",
                          confidence=0.75, source_events=["ev-9"])
        request = service.request_approval(a.id)
        _, decision, da = service.decide_approval(request.id, "approved")
        assert da.provider_id == "hermes"
        assert da.agent_id == "ag-1"
        assert da.confidence == 0.75

    def test_decision_artifact_source_events_anchored(self, service, event_service):
        # 带 logger 的链路: approval.granted 事件 event_id 回填到 decision Artifact
        a = seed_artifact(event_service, "prd")
        request = event_service.request_approval(a.id)
        _, decision, da = event_service.decide_approval(request.id, "approved")
        assert len(da.source_events) == 1
        # granted 事件的 event_id 与 source_events[0] 一致 (Lineage 闭环)
        from events.models import EventType

        granted = [
            e for e in event_service._logger.store.query()
            if e.type == EventType.APPROVAL_GRANTED
        ][-1]
        assert granted.event_id == da.source_events[0]


class TestListApprovals:
    def test_list_all_and_pending(self, service):
        a = seed_artifact(service, "prd")
        r1 = service.request_approval(a.id)
        b = seed_artifact(service, "ui")
        service.request_approval(b.id)
        service.decide_approval(r1.id, "approved")
        assert len(service.list_approvals()) == 2
        pending = service.list_approvals(pending_only=True)
        assert [r.id for r in pending] == ["APR-002"]

    def test_get_approval_request(self, service):
        a = seed_artifact(service, "prd")
        r = service.request_approval(a.id)
        assert service.get_approval_request(r.id).id == r.id

    def test_get_approval_request_missing_raises(self, service):
        with pytest.raises(ProductNotFoundError):
            service.get_approval_request("APR-999")
