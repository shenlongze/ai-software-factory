"""tests/product/test_product_events_9c.py — 9c 事件链序 + 9a 兼容 (Phase 9C, ADR-0028)。

覆盖: 申请链序 (approval.created → approval.pending → approval.required 9a 兼容),
批准 8 链序 (idea.created → approval.created → approval.pending → approval.required
→ approval.approved → approval.granted 9a 兼容 → approval.resumed → workflow
联动), 9a 遗留 denied → approval.rejected + approval.denied 双事件 + resumed,
changes_requested/delegated 终态事件 + resumed (reason 语义), 手动 resume 事件
payload (reason=manual), 9c 事件 payload 契约 (artifact_version/gate/decided_by/
comment), logger=None 静默。
"""

from __future__ import annotations

from events.models import EventType

from product.events import (
    record_approval_approved,
    record_approval_changes_requested,
    record_approval_created,
    record_approval_delegated,
    record_approval_pending,
    record_approval_rejected,
    record_approval_resumed,
)
from product.models import (
    ApprovalDecision,
    ApprovalRequest,
    Artifact,
    ProductWorkflow,
)

from product_helpers import (
    event_sequence,
    event_types_of,
    payload_of,
    seed_artifact,
    seed_idea,
    seed_workflow,
)


class TestRequestChain:
    def test_request_emits_created_pending_required_in_order(self, event_service):
        idea = seed_idea(event_service)
        a = seed_artifact(event_service, "prd", idea_id=idea.id)
        event_service.request_approval(a.id)
        seq = event_sequence(event_service._logger.store)
        types = [t for t in seq if t.startswith("approval.")]
        assert types == [
            "approval.created",
            "approval.pending",
            "approval.required",  # 9a 兼容 (最后发出, 链序稳定)
        ]

    def test_request_chain_idea_first(self, event_service):
        idea = seed_idea(event_service)
        a = seed_artifact(event_service, "prd", idea_id=idea.id)
        event_service.request_approval(a.id)
        seq = event_sequence(event_service._logger.store)
        assert seq[0] == "idea.created"
        assert seq.index("idea.created") < seq.index("approval.created")

    def test_approval_created_payload_contract(self, event_service):
        idea = seed_idea(event_service)
        a = seed_artifact(event_service, "prd", idea_id=idea.id, confidence=0.7)
        event_service.request_approval(a.id, by="alice", note="请审")
        store = event_service._logger.store
        payload = payload_of(store, "approval.created")
        assert payload["request_id"] == "APR-001"
        assert payload["artifact_id"] == a.id
        assert payload["gate"] == "prd"
        assert payload["idea_id"] == idea.id
        assert payload["artifact_version"] == 1
        assert payload["artifact_type"] == "prd"
        assert payload["status"] == "pending"


class TestApproveChain:
    def test_approve_8_event_chain_order(self, event_service):
        """完整批准链: idea.created → approval.created|pending|required →
        approval.approved → approval.granted (9a 兼容) → approval.resumed
        → product.workflow.started (工作流先启动再申请)。"""
        idea = seed_idea(event_service)
        seed_workflow(event_service, idea.id)  # 先启动工作流 (暂停联动可恢复)
        a = seed_artifact(event_service, "prd", idea_id=idea.id)
        r = event_service.request_approval(a.id)
        event_service.decide_approval(r.id, "approved")
        seq = event_sequence(event_service._logger.store)
        assert seq == [
            "idea.created",
            "product.workflow.started",
            "approval.created",
            "approval.pending",
            "approval.required",
            "approval.approved",
            "approval.granted",
            "approval.resumed",
        ]

    def test_approve_9a_compat_granted_and_approved_both_emitted(self, event_service):
        idea = seed_idea(event_service)
        a = seed_artifact(event_service, "prd", idea_id=idea.id)
        r = event_service.request_approval(a.id)
        event_service.decide_approval(r.id, "approved")
        store = event_service._logger.store
        types = event_types_of(store)
        assert "approval.approved" in types
        assert "approval.granted" in types  # 9a 兼容 (Product Decision 锚点)

    def test_approved_event_payload_contract(self, event_service):
        idea = seed_idea(event_service)
        a = seed_artifact(event_service, "prd", idea_id=idea.id, confidence=0.6)
        r = event_service.request_approval(a.id)
        event_service.decide_approval(r.id, "approved", by="reviewer", comment="通过")
        payload = payload_of(event_service._logger.store, "approval.approved")
        assert payload["decision"] == "approved"
        assert payload["decided_by"] == "reviewer"
        assert payload["comment"] == "通过"
        assert payload["artifact_version"] == 1
        assert payload["artifact_type"] == "prd"
        assert payload["idea_id"] == idea.id

    def test_resumed_approved_payload_reason(self, event_service):
        idea = seed_idea(event_service)
        seed_workflow(event_service, idea.id)
        a = seed_artifact(event_service, "prd", idea_id=idea.id)
        r = event_service.request_approval(a.id)
        event_service.decide_approval(r.id, "approved")
        payload = payload_of(event_service._logger.store, "approval.resumed")
        assert payload["reason"] == "approved"
        assert payload["workflow_id"] == "PW-001"
        assert payload["idea_id"] == idea.id
        assert payload["status"] == "running"
        assert payload["current_stage"] == "prd"  # 批准推进下一 stage


class TestOtherTerminalChains:
    def test_denied_alias_emits_rejected_denied_resumed(self, event_service):
        """9a 遗留 denied → approval.rejected + approval.denied (兼容) + resumed
        (reason=rejected — 语义映射后按 rejected 恢复)。"""
        idea = seed_idea(event_service)
        seed_workflow(event_service, idea.id)
        a = seed_artifact(event_service, "prd", idea_id=idea.id)
        r = event_service.request_approval(a.id)
        event_service.decide_approval(r.id, "denied", comment="旧调用")
        store = event_service._logger.store
        types = event_types_of(store)
        assert "approval.rejected" in types
        assert "approval.denied" in types  # 9a 兼容
        assert "approval.approved" not in types
        payload = payload_of(store, "approval.resumed")
        assert payload["reason"] == "rejected"

    def test_changes_requested_chain_and_resume_reason(self, event_service):
        idea = seed_idea(event_service)
        seed_workflow(event_service, idea.id)
        a = seed_artifact(event_service, "prd", idea_id=idea.id)
        r = event_service.request_approval(a.id)
        event_service.decide_approval(r.id, "changes_requested", comment="改一下")
        store = event_service._logger.store
        assert "approval.changes_requested" in event_types_of(store)
        payload = payload_of(store, "approval.resumed")
        assert payload["reason"] == "changes_requested"
        assert payload["current_stage"] == "research"  # 停留当前 stage

    def test_delegated_chain_and_resume_reason(self, event_service):
        idea = seed_idea(event_service)
        seed_workflow(event_service, idea.id)
        a = seed_artifact(event_service, "prd", idea_id=idea.id)
        r = event_service.request_approval(a.id)
        event_service.decide_approval(r.id, "delegated", by="lead")
        store = event_service._logger.store
        assert "approval.delegated" in event_types_of(store)
        payload = payload_of(store, "approval.delegated")
        assert payload["decided_by"] == "lead"
        assert payload_of(store, "approval.resumed")["reason"] == "delegated"

    def test_manual_resume_event_payload(self, event_service):
        idea = seed_idea(event_service)
        seed_workflow(event_service, idea.id)
        a = seed_artifact(event_service, "prd", idea_id=idea.id)
        event_service.request_approval(a.id)  # paused
        event_service.workflow_resume(idea.id)  # 手动恢复
        payload = payload_of(event_service._logger.store, "approval.resumed")
        assert payload["reason"] == "manual"
        assert payload["status"] == "running"
        assert payload["current_stage"] == "research"  # 停留 (不推进)


class Test9cHelperUnits:
    def test_created_pending_helpers(self, logger):
        request = ApprovalRequest(id="APR-001", artifact_id="ART-001", gate="prd",
                                  idea_id="PI-001", artifact_version=2)
        ev = record_approval_created(logger, request=request)
        assert ev.type == EventType.APPROVAL_CREATED
        assert ev.payload["artifact_version"] == 2
        ev2 = record_approval_pending(logger, request=request)
        assert ev2.type == EventType.APPROVAL_PENDING
        assert ev2.stage == "pending"

    def test_terminal_helpers_types(self, logger):
        request = ApprovalRequest(id="APR-001", artifact_id="ART-001", gate="prd")
        decision = ApprovalDecision(id="APD-001", request_id="APR-001", decision="rejected")
        assert record_approval_rejected(logger, request=request, decision=decision).type \
            == EventType.APPROVAL_REJECTED
        assert record_approval_changes_requested(
            logger, request=request, decision=decision,
        ).type == EventType.APPROVAL_CHANGES_REQUESTED
        assert record_approval_delegated(logger, request=request, decision=decision).type \
            == EventType.APPROVAL_DELEGATED
        assert record_approval_approved(
            logger, request=request, decision=decision,
        ).type == EventType.APPROVAL_APPROVED

    def test_resumed_helper(self, logger):
        wf = ProductWorkflow(id="PW-001", idea_id="PI-001",
                             stages=["research", "prd"], current_stage="research")
        ev = record_approval_resumed(logger, workflow=wf, reason="manual")
        assert ev.type == EventType.APPROVAL_RESUMED
        assert ev.payload["reason"] == "manual"
        assert ev.payload["workflow_id"] == "PW-001"

    def test_9c_helpers_silent_without_logger(self):
        request = ApprovalRequest(id="APR-001", artifact_id="ART-001", gate="prd")
        decision = ApprovalDecision(id="APD-001", request_id="APR-001", decision="approved")
        artifact = Artifact(id="ART-001", type="prd")
        wf = ProductWorkflow(id="PW-001", idea_id="PI-001")
        assert record_approval_created(None, request=request) is None
        assert record_approval_pending(None, request=request) is None
        assert record_approval_approved(None, request=request, decision=decision) is None
        assert record_approval_rejected(None, request=request, decision=decision) is None
        assert record_approval_changes_requested(None, request=request, decision=decision) is None
        assert record_approval_delegated(None, request=request, decision=decision) is None
        assert record_approval_resumed(None, workflow=wf) is None
        assert artifact.id == "ART-001"  # 哨兵: 辅助函数不产生副作用
