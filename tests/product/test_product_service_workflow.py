"""tests/product/test_product_service_workflow.py — ProductWorkflow 状态机: stages / awaiting_approval / product_decision (Phase 9A, ADR-0026)。

覆盖: start_workflow 默认阶段链 (research/prd/ui/architecture/tasks) + current_stage
首阶段、自定义 stages、idea 须存在、一个 idea 至多一个 run、workflow_status 未找到
抛错、approval.required → running→awaiting_approval、granted → awaiting_approval→
running + 推进 current_stage + product_decision 回填、denied → 回 running 停留当前
stage、无 workflow 时 approval 不炸 (联动 no-op)。
"""

from __future__ import annotations

import pytest

from product.models import WorkflowStatus
from product.service import ProductError, ProductNotFoundError

from product_helpers import seed_artifact, seed_idea


class TestStartWorkflow:
    def test_start_default_stages(self, service):
        idea = seed_idea(service)
        wf = service.start_workflow(idea.id)
        assert wf.id == "PW-001"
        assert wf.stages == ["research", "prd", "ui", "architecture", "tasks"]
        assert wf.current_stage == "research"
        assert wf.status == WorkflowStatus.RUNNING.value

    def test_start_custom_stages(self, service):
        idea = seed_idea(service)
        wf = service.start_workflow(idea.id, stages=["prd", "ui"])
        assert wf.stages == ["prd", "ui"]
        assert wf.current_stage == "prd"

    def test_start_requires_idea(self, service):
        with pytest.raises(ProductNotFoundError):
            service.start_workflow("PI-999")

    def test_start_twice_raises(self, service):
        idea = seed_idea(service)
        service.start_workflow(idea.id)
        with pytest.raises(ProductError) as exc:
            service.start_workflow(idea.id)
        assert "already started" in str(exc.value)

    def test_workflow_id_increments(self, service):
        i1 = seed_idea(service, "a")
        i2 = seed_idea(service, "b")
        assert service.start_workflow(i1.id).id == "PW-001"
        assert service.start_workflow(i2.id).id == "PW-002"

    def test_two_ideas_two_workflows(self, service):
        i1 = seed_idea(service, "a")
        i2 = seed_idea(service, "b")
        service.start_workflow(i1.id)
        service.start_workflow(i2.id)
        assert len(service._store.list_workflows()) == 2


class TestWorkflowStatus:
    def test_status_returns_workflow(self, service):
        idea = seed_idea(service)
        wf = service.start_workflow(idea.id)
        assert service.workflow_status(idea.id).id == wf.id

    def test_status_missing_raises(self, service):
        with pytest.raises(ProductNotFoundError):
            service.workflow_status("PI-999")


class TestApprovalLinking:
    def test_request_approval_pauses_workflow(self, service):
        idea = seed_idea(service)
        service.start_workflow(idea.id)
        a = seed_artifact(service, "prd", idea_id=idea.id)
        service.request_approval(a.id)
        wf = service.workflow_status(idea.id)
        assert wf.status == WorkflowStatus.AWAITING_APPROVAL.value

    def test_approve_resumes_and_advances_stage(self, service):
        idea = seed_idea(service)
        service.start_workflow(idea.id)
        a = seed_artifact(service, "prd", idea_id=idea.id)
        request = service.request_approval(a.id)
        _, _, decision_artifact = service.decide_approval(request.id, "approved")
        wf = service.workflow_status(idea.id)
        assert wf.status == WorkflowStatus.RUNNING.value
        assert wf.current_stage == "prd"  # research → prd
        assert wf.product_decision == decision_artifact.id

    def test_deny_resumes_stays_on_stage(self, service):
        idea = seed_idea(service)
        service.start_workflow(idea.id)
        a = seed_artifact(service, "prd", idea_id=idea.id)
        request = service.request_approval(a.id)
        service.decide_approval(request.id, "denied", comment="重做")
        wf = service.workflow_status(idea.id)
        assert wf.status == WorkflowStatus.RUNNING.value
        assert wf.current_stage == "research"  # 停留当前 stage
        assert wf.product_decision is None

    def test_approval_without_workflow_is_noop(self, service):
        idea = seed_idea(service)
        a = seed_artifact(service, "prd", idea_id=idea.id)
        request = service.request_approval(a.id)  # 无 workflow → 联动跳过
        service.decide_approval(request.id, "approved")
        # request 对象已过期 (decide 经 model_copy 新实例) — 重新取
        assert service.get_approval_request(request.id).status == "approved"

    def test_approval_unknown_idea_id_noop(self, service):
        a = seed_artifact(service, "prd")  # 无 idea_id 锚点
        request = service.request_approval(a.id)
        assert request.idea_id is None  # 无关联 → workflow 联动 no-op
        assert request.status == "pending"

    def test_workflow_paused_only_when_running(self, service):
        idea = seed_idea(service)
        wf = service.start_workflow(idea.id)
        # 手工把 workflow 置为已完成 (终态不回头) — 申请审批不改变非 running 状态
        from product.models import ProductWorkflow

        done = ProductWorkflow(**{**wf.to_dict(), "status": WorkflowStatus.COMPLETED.value})
        service._store.save_workflow(done)
        a = seed_artifact(service, "prd", idea_id=idea.id)
        service.request_approval(a.id)
        assert service.workflow_status(idea.id).status == WorkflowStatus.COMPLETED.value

    def test_advance_at_last_stage_stays(self, service):
        idea = seed_idea(service)
        service.start_workflow(idea.id, stages=["research", "tasks"])
        a = seed_artifact(service, "prd", idea_id=idea.id)
        r1 = service.request_approval(a.id)
        service.decide_approval(r1.id, "approved")  # research → tasks
        wf = service.workflow_status(idea.id)
        assert wf.current_stage == "tasks"
        # 最后一阶段再次 granted → 停留 (无下一阶段)
        b = seed_artifact(service, "ui", idea_id=idea.id)
        r2 = service.request_approval(b.id)
        service.decide_approval(r2.id, "approved")
        assert service.workflow_status(idea.id).current_stage == "tasks"


class TestWorkflowHelpers:
    def test_seed_workflow_helper(self, service):
        idea = seed_idea(service)
        wf = service.start_workflow(idea.id)
        assert wf.current_stage == "research"
