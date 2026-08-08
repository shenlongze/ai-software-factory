"""tests/s9/test_s9_approval_lifecycle.py — WorkflowLifecycle 审批门接线。

覆盖 (S9-001 任务清单: lifecycle / 状态机受控):
- request_approval: 门创建 (PENDING, AG- 前缀, 绑定 stage/workflow) +
  workflow ACTIVE→PAUSED; 非门禁阶段拒建 / 重复门拒建 / 缺 stage 拒建
- approve_approval: →APPROVED (终态) + workflow 恢复 PAUSED→ACTIVE
  (幂等恢复: 已 ACTIVE 不重复转换)
- reject_approval: →REJECTED (终态) + workflow FAILED 停止 (failed_reason
  记录否决原因 + 决策人)
- 非 PENDING 门决定 → ApprovalStateError (决定不可撤销)
- list_approvals 过滤 (workflow/status/stage) / get_approval 未找到
- has_pending_approval / has_rejected_approval 守卫查询

依赖: 本目录 conftest + s9_helpers (workflow 构造)。
"""

from __future__ import annotations

import pytest

from org.approval import ApprovalStateError, ApprovalStatus
from org.lifecycle import DuplicateError, NotFoundError
from org.workflow import WorkflowLifecycle, WorkflowStatus, WorkflowStateError

from s9_helpers import build_approval_workflow


@pytest.fixture
def gate_workflow(wlife: WorkflowLifecycle, project_id: str):
    """带三挡板的 5 阶段 workflow (pm/arch/devops 三门; 其余无门)。"""
    return build_approval_workflow(wlife, project_id)


@pytest.fixture
def pending_gate(wlife: WorkflowLifecycle, gate_workflow):
    """首门: workflow 启动 (ACTIVE) → pm stage 完成 → request_approval →
    PENDING + workflow PAUSED。"""
    wlife.activate(gate_workflow.id)  # 门语义在运行中 workflow 上 (ACTIVE→PAUSED)
    pm = wlife.list_stages(gate_workflow.id)[0]
    wlife.transition_stage(pm.id, "ready")
    wlife.transition_stage(pm.id, "running")
    wlife.transition_stage(pm.id, "completed")
    gate = wlife.request_approval(pm.id)
    return gate


class TestRequestApproval:
    def test_creates_pending_gate_and_pauses(self, wlife, gate_workflow) -> None:
        wlife.activate(gate_workflow.id)  # ACTIVE → request → PAUSED
        pm = wlife.list_stages(gate_workflow.id)[0]
        gate = wlife.request_approval(pm.id)
        assert gate.id.startswith("AG-")
        assert gate.status == ApprovalStatus.PENDING
        assert gate.stage_id == pm.id
        assert gate.workflow_id == gate_workflow.id
        assert wlife.get_workflow(gate_workflow.id).status == WorkflowStatus.PAUSED
        assert wlife.has_pending_approval(gate_workflow.id) is True

    def test_stage_must_be_approval_required(self, wlife, gate_workflow) -> None:
        dev = wlife.list_stages(gate_workflow.id)[2]  # developer 无门
        with pytest.raises(WorkflowStateError, match="does not require approval"):
            wlife.request_approval(dev.id)

    def test_duplicate_gate_rejected(self, wlife, pending_gate) -> None:
        with pytest.raises(DuplicateError, match="already exists"):
            wlife.request_approval(pending_gate.stage_id)

    def test_missing_stage_rejected(self, wlife) -> None:
        with pytest.raises(NotFoundError, match="stage not found"):
            wlife.request_approval("STG-NOPE")

    def test_gate_id_unique_per_stage(self, wlife, gate_workflow) -> None:
        pm = wlife.list_stages(gate_workflow.id)[0]
        first = wlife.request_approval(pm.id)
        assert first.id != "AG-fixed"  # new_id 唯一 (AG- 前缀 + uuid)

    def test_get_approval_not_found(self, wlife) -> None:
        with pytest.raises(NotFoundError, match="approval gate not found"):
            wlife.get_approval("AG-NOPE")

    def test_get_approval_by_stage(self, wlife, pending_gate) -> None:
        got = wlife.get_approval_by_stage(pending_gate.stage_id)
        assert got is not None and got.id == pending_gate.id
        assert wlife.get_approval_by_stage("STG-NOPE") is None


class TestApproveApproval:
    def test_approve_resumes_workflow(self, wlife, pending_gate) -> None:
        gate, workflow = wlife.approve_approval(
            pending_gate.id, reviewer="alice", comment="MVP scope ok"
        )
        assert gate.status == ApprovalStatus.APPROVED
        assert gate.reviewer == "alice"
        assert gate.comment == "MVP scope ok"
        assert gate.approved_at is not None
        assert workflow.status == WorkflowStatus.ACTIVE
        assert wlife.has_pending_approval(workflow.id) is False

    def test_approve_non_pending_rejected(self, wlife, pending_gate) -> None:
        wlife.approve_approval(pending_gate.id, reviewer="alice")
        with pytest.raises(ApprovalStateError, match="invalid approval transition"):
            wlife.approve_approval(pending_gate.id, reviewer="bob")

    def test_approve_missing_gate_rejected(self, wlife) -> None:
        with pytest.raises(NotFoundError, match="approval gate not found"):
            wlife.approve_approval("AG-NOPE", reviewer="alice")


class TestRejectApproval:
    def test_reject_stops_workflow(self, wlife, pending_gate) -> None:
        gate, workflow = wlife.reject_approval(
            pending_gate.id, reviewer="bob", comment="scope too big"
        )
        assert gate.status == ApprovalStatus.REJECTED
        assert gate.reviewer == "bob"
        assert gate.rejected_at is not None
        assert workflow.status == WorkflowStatus.FAILED
        assert "scope too big" in workflow.failed_reason
        assert "bob" in workflow.failed_reason
        assert wlife.has_rejected_approval(workflow.id) is True

    def test_reject_non_pending_rejected(self, wlife, pending_gate) -> None:
        wlife.reject_approval(pending_gate.id, reviewer="bob")
        with pytest.raises(ApprovalStateError, match="invalid approval transition"):
            wlife.reject_approval(pending_gate.id, reviewer="carol")

    def test_reject_missing_gate_rejected(self, wlife) -> None:
        with pytest.raises(NotFoundError, match="approval gate not found"):
            wlife.reject_approval("AG-NOPE", reviewer="bob")


class TestListApprovals:
    def test_filters_by_workflow_status_stage(self, wlife, gate_workflow) -> None:
        stages = wlife.list_stages(gate_workflow.id)
        g1 = wlife.request_approval(stages[0].id)
        g2 = wlife.request_approval(stages[1].id)
        wlife.approve_approval(g1.id, reviewer="alice")
        # workflow 过滤
        assert {g.id for g in wlife.list_approvals(workflow_id=gate_workflow.id)} == {g1.id, g2.id}
        # status 过滤
        assert [g.id for g in wlife.list_approvals(status="approved")] == [g1.id]
        assert [g.id for g in wlife.list_approvals(status=ApprovalStatus.PENDING)] == [g2.id]
        # stage 过滤
        assert [g.id for g in wlife.list_approvals(stage_id=stages[0].id)] == [g1.id]
        # 空结果
        assert wlife.list_approvals(workflow_id="WF-NOPE") == []


class TestApprovalGuards:
    def test_pending_then_approved_guard_flips(self, wlife, pending_gate) -> None:
        wf_id = pending_gate.workflow_id
        assert wlife.has_pending_approval(wf_id) is True
        wlife.approve_approval(pending_gate.id, reviewer="alice")
        assert wlife.has_pending_approval(wf_id) is False
        assert wlife.has_rejected_approval(wf_id) is False

    def test_rejected_guard_persists(self, wlife, pending_gate) -> None:
        wf_id = pending_gate.workflow_id
        wlife.reject_approval(pending_gate.id, reviewer="bob")
        assert wlife.has_pending_approval(wf_id) is False
        assert wlife.has_rejected_approval(wf_id) is True
