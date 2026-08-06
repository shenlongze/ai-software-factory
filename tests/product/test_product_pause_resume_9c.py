"""tests/product/test_product_pause_resume_9c.py — Workflow Pause/Resume (Phase 9C, ADR-0028)。

覆盖: workflow_resume (paused → running, 停留当前 stage, 发 approval.resumed
reason=manual), 未暂停 (running/completed/failed) 抛错, 无工作流抛错, 9a 遗留
awaiting_approval 兼容恢复, PAUSED → approved → resume 推进 stage, rejected →
修改流程 (revise v2 → 重新审批), changes_requested → v2 → 重新审批 (冒烟核心),
rejected 后手动 resume 停留当前 stage (通用决策系统入口)。
"""

from __future__ import annotations

import pytest

from product.models import WorkflowStatus
from product.service import ProductError, ProductNotFoundError

from product_helpers import seed_artifact, seed_idea, seed_workflow


class TestManualResume:
    def test_resume_paused_to_running_stays_stage(self, service):
        idea = seed_idea(service)
        service.start_workflow(idea.id)
        a = seed_artifact(service, "prd", idea_id=idea.id)
        service.request_approval(a.id)  # running → paused
        assert service.workflow_status(idea.id).status == WorkflowStatus.PAUSED.value
        wf = service.workflow_resume(idea.id)
        assert wf.status == WorkflowStatus.RUNNING.value
        assert wf.current_stage == "research"  # 停留当前 stage (不推进)
        assert service.workflow_status(idea.id).status == WorkflowStatus.RUNNING.value

    def test_resume_missing_workflow_raises(self, service):
        with pytest.raises(ProductNotFoundError, match="no product workflow"):
            service.workflow_resume("PI-999")

    def test_resume_running_raises(self, service):
        idea = seed_idea(service)
        service.start_workflow(idea.id)
        with pytest.raises(ProductError, match="not paused"):
            service.workflow_resume(idea.id)

    def test_resume_completed_raises(self, service):
        idea = seed_idea(service)
        wf = service.start_workflow(idea.id)
        from product.models import ProductWorkflow

        done = ProductWorkflow(**{**wf.to_dict(), "status": WorkflowStatus.COMPLETED.value})
        service._store.save_workflow(done)
        with pytest.raises(ProductError, match="not paused"):
            service.workflow_resume(idea.id)

    def test_resume_failed_raises(self, service):
        idea = seed_idea(service)
        wf = service.start_workflow(idea.id)
        from product.models import ProductWorkflow

        failed = ProductWorkflow(**{**wf.to_dict(), "status": WorkflowStatus.FAILED.value})
        service._store.save_workflow(failed)
        with pytest.raises(ProductError, match="not paused"):
            service.workflow_resume(idea.id)

    def test_resume_legacy_awaiting_approval_compat(self, service):
        # 9a 遗留状态 awaiting_approval → 手动恢复兼容 (同 paused 语义)
        idea = seed_idea(service)
        wf = service.start_workflow(idea.id)
        from product.models import ProductWorkflow

        legacy = ProductWorkflow(**{**wf.to_dict(), "status": "awaiting_approval"})
        service._store.save_workflow(legacy)
        wf2 = service.workflow_resume(idea.id)
        assert wf2.status == WorkflowStatus.RUNNING.value


class TestApprovedResume:
    def test_paused_approved_resume_advances_stage(self, service):
        """PAUSED → approved → running + 推进 current_stage + product_decision。"""
        idea = seed_idea(service)
        service.start_workflow(idea.id)
        a = seed_artifact(service, "prd", idea_id=idea.id)
        request = service.request_approval(a.id)
        assert service.workflow_status(idea.id).status == WorkflowStatus.PAUSED.value
        _, _, decision_artifact = service.decide_approval(request.id, "approved")
        wf = service.workflow_status(idea.id)
        assert wf.status == WorkflowStatus.RUNNING.value
        assert wf.current_stage == "prd"  # research → prd
        assert wf.product_decision == decision_artifact.id

    def test_approved_auto_resume_then_manual_resume_idempotent_error(self, service):
        # approved 已自动恢复 → 再手动 resume 报"未暂停" (终态语义一致)
        idea = seed_idea(service)
        service.start_workflow(idea.id)
        a = seed_artifact(service, "prd", idea_id=idea.id)
        request = service.request_approval(a.id)
        service.decide_approval(request.id, "approved")
        with pytest.raises(ProductError, match="not paused"):
            service.workflow_resume(idea.id)


class TestRevisionCycles:
    def test_rejected_revise_v2_reapproval_cycle(self, service):
        """rejected → revise v2 → 重新审批 → approved (修改流程闭环)。"""
        idea = seed_idea(service)
        service.start_workflow(idea.id)
        a = seed_artifact(service, "prd", idea_id=idea.id)
        r1 = service.request_approval(a.id)
        service.decide_approval(r1.id, "rejected", comment="重做")
        # rejected → workflow 自动回 running 停留 stage (进入修改流程)
        assert service.workflow_status(idea.id).status == WorkflowStatus.RUNNING.value
        assert service.workflow_status(idea.id).current_stage == "research"
        v2 = service.revise_artifact(a.id, {"title": "v2"}, note="按意见修改")
        r2 = service.request_approval(v2.id)
        assert r2.artifact_version == 2
        # v2 申请 → workflow 再次 paused
        assert service.workflow_status(idea.id).status == WorkflowStatus.PAUSED.value
        service.decide_approval(r2.id, "approved")
        wf = service.workflow_status(idea.id)
        assert wf.status == WorkflowStatus.RUNNING.value
        assert wf.current_stage == "prd"  # 批准推进下一 stage

    def test_changes_requested_v2_reapproval_cycle(self, service):
        """changes_requested → v2 重新生成 → 重新审批 → approved (冒烟核心语义)。"""
        idea = seed_idea(service)
        service.start_workflow(idea.id)
        a = seed_artifact(service, "prd", idea_id=idea.id, confidence=0.4)
        r1 = service.request_approval(a.id)
        service.decide_approval(r1.id, "changes_requested", by="reviewer", comment="缺竞品分析")
        v2 = service.revise_artifact(a.id, {"title": "v2"}, confidence=0.85)
        r2 = service.request_approval(v2.id)
        service.decide_approval(r2.id, "approved", by="reviewer", comment="改好了")
        assert service.get_approval_request(r2.id).status == "approved"
        assert service.get_approval_request(r1.id).status == "changes_requested"  # 历史不变
        assert service.workflow_status(idea.id).product_decision is not None

    def test_rejected_then_manual_resume_stays_stage(self, service):
        """rejected 自动恢复 → 再次申请 paused → 不 decide 直接手动 resume
        (通用决策系统入口: 人工决定不再重审, 直接推进)。"""
        idea = seed_idea(service)
        service.start_workflow(idea.id)
        a = seed_artifact(service, "prd", idea_id=idea.id)
        r1 = service.request_approval(a.id)
        service.decide_approval(r1.id, "rejected")  # 自动回 running (修改流程)
        assert service.workflow_status(idea.id).status == WorkflowStatus.RUNNING.value
        # 再次申请 → paused → 不 decide, 手动恢复 (停留当前 stage)
        service.request_approval(a.id)
        assert service.workflow_status(idea.id).status == WorkflowStatus.PAUSED.value
        wf = service.workflow_resume(idea.id)
        assert wf.status == WorkflowStatus.RUNNING.value
        assert wf.current_stage == "research"
