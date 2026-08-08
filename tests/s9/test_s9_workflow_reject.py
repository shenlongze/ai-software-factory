"""tests/s9/test_s9_workflow_reject.py — reject 停止 workflow (Runner 集成)。

覆盖 (S9-001 任务清单: reject 停止):
- reject → workflow FAILED (failed_reason 记录否决原因 + 决策人 + stage_id)
- Runner 否决守卫: REJECTED → run 响亮拒绝 (含 failed→paused→active 重试
  路径 — 审批决定不可撤销, 禁绕过审批门)
- 部分放行后否决: 已 approve 的门保持 APPROVED (历史决定不翻转)

依赖: 本目录 conftest + s9_helpers。
"""

from __future__ import annotations

import pytest

from org.approval import ApprovalStatus
from org.workflow import (
    WorkflowLifecycle,
    WorkflowRunner,
    WorkflowStatus,
    WorkflowStateError,
)

from s9_helpers import approval_chain_executor, build_approval_workflow


@pytest.fixture
def runner(wlife: WorkflowLifecycle) -> WorkflowRunner:
    return WorkflowRunner(wlife, executor=approval_chain_executor, logger=None)


@pytest.fixture
def chain(runner: WorkflowRunner, project_id: str):
    return build_approval_workflow(runner.lifecycle, project_id)


def _pending_gates(wlife: WorkflowLifecycle, workflow_id: str) -> list:
    return [
        g for g in wlife.list_approvals(workflow_id=workflow_id)
        if g.status.value == "pending"
    ]


class TestRejectStops:
    def test_reject_fails_workflow_and_records_reason(self, runner, wlife, chain) -> None:
        runner.run(chain.id)
        gate = _pending_gates(wlife, chain.id)[0]
        wlife.reject_approval(gate.id, reviewer="bob", comment="MVP scope 不合格")
        workflow = wlife.get_workflow(chain.id)
        assert workflow.status == WorkflowStatus.FAILED
        assert "MVP scope 不合格" in workflow.failed_reason
        assert "bob" in workflow.failed_reason
        fresh = wlife.get_approval(gate.id)
        assert fresh.status == ApprovalStatus.REJECTED

    def test_rejected_workflow_cannot_rerun(self, runner, wlife, chain) -> None:
        """否决守卫: run 响亮拒绝 (禁绕过 — 即便状态被人工改回也拒绝)。"""
        runner.run(chain.id)
        gate = _pending_gates(wlife, chain.id)[0]
        wlife.reject_approval(gate.id, reviewer="bob")
        with pytest.raises(WorkflowStateError, match="rejected approval gate"):
            runner.run(chain.id)

    def test_rejected_workflow_retry_path_still_blocked(
        self, runner, wlife, chain
    ) -> None:
        """failed→paused→active 重试路径同样被否决守卫拦截 (决定不可撤销)。"""
        runner.run(chain.id)
        gate = _pending_gates(wlife, chain.id)[0]
        wlife.reject_approval(gate.id, reviewer="bob")
        # 人工介入: failed → paused → active (S7 既有重试路径)
        wlife.transition_workflow(chain.id, WorkflowStatus.PAUSED)
        wlife.transition_workflow(chain.id, WorkflowStatus.ACTIVE)
        with pytest.raises(WorkflowStateError, match="rejected approval gate"):
            runner.run(chain.id)

    def test_prior_approved_gates_unchanged_after_reject(
        self, runner, wlife, chain
    ) -> None:
        """部分放行后否决: 历史 APPROVED 门保持 (决定不可撤销, 审计完整)。"""
        runner.run(chain.id)
        g1 = _pending_gates(wlife, chain.id)[0]
        wlife.approve_approval(g1.id, reviewer="alice", comment="P1 ok")
        runner.run(chain.id)
        g2 = _pending_gates(wlife, chain.id)[0]
        wlife.reject_approval(g2.id, reviewer="bob", comment="P2 方案不采纳")
        assert wlife.get_approval(g1.id).status == ApprovalStatus.APPROVED
        assert wlife.get_approval(g2.id).status == ApprovalStatus.REJECTED
        assert wlife.get_workflow(chain.id).status == WorkflowStatus.FAILED

    def test_reject_at_release_gate_blocks_publish(self, runner, wlife, chain) -> None:
        """P3 发布门否决: 全部 stage COMPLETED 但 workflow FAILED (未放行不发布)。"""
        wf = runner.run(chain.id)
        for _ in range(2):
            g = _pending_gates(wlife, chain.id)[0]
            wlife.approve_approval(g.id, reviewer="alice")
            wf = runner.run(chain.id)
        assert wf.status == WorkflowStatus.PAUSED  # P3 发布门
        assert all(
            s.status.value == "completed" for s in wlife.list_stages(chain.id)
        )
        g3 = _pending_gates(wlife, chain.id)[0]
        wlife.reject_approval(g3.id, reviewer="bob", comment="发布前发现阻断缺陷")
        workflow = wlife.get_workflow(chain.id)
        assert workflow.status == WorkflowStatus.FAILED
        assert "发布前发现阻断缺陷" in workflow.failed_reason
        with pytest.raises(WorkflowStateError, match="rejected approval gate"):
            runner.run(chain.id)
