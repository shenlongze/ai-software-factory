"""tests/s9/test_s9_workflow_approve.py — approve 继续 workflow (Runner 集成)。

覆盖 (S9-001 任务清单: approve 继续):
- 冒烟链路: 三挡板 (MVP/架构/发布) 逐一 approve → Runner 继续下一 stage →
  全部 COMPLETED → workflow COMPLETED (产物全 VALIDATED — CONTRACTS 同源)
- 挂起守卫: 待审门 PENDING → Runner 返回 PAUSED (禁绕过审批门自动恢复)
- approve 后继续: 恢复 ACTIVE → 下一 stage 执行 → 下一门挂起
- 无门 workflow 行为不变 (向后兼容: approval_required=False 零影响)

依赖: 本目录 conftest + s9_helpers (approval_chain_executor — mock executor,
metadata 与 org CONTRACTS 同源, 冒烟阻断修复点)。
"""

from __future__ import annotations

import pytest

from org.artifact import validate_artifact
from org.projects import ArtifactStatus
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


class TestApproveContinues:
    def test_full_chain_three_gates_approve_to_completed(self, runner, wlife, chain) -> None:
        """冒烟主链路: 5 阶段三挡板, 逐一 approve → COMPLETED。"""
        wf = runner.run(chain.id)
        assert wf.status == WorkflowStatus.PAUSED  # P1 MVP 门挂起
        assert len(_pending_gates(wlife, chain.id)) == 1

        for expected in ("P1", "P2", "P3"):
            gates = _pending_gates(wlife, chain.id)
            assert len(gates) == 1
            wlife.approve_approval(gates[0].id, reviewer=f"reviewer-{expected}")
            wf = runner.run(chain.id)
            if expected != "P3":
                assert wf.status == WorkflowStatus.PAUSED  # 下一门挂起
        # P3 发布门放行后 → 全部 COMPLETED
        assert wf.status == WorkflowStatus.COMPLETED
        stages = wlife.list_stages(chain.id)
        assert all(s.status.value == "completed" for s in stages)

    def test_all_output_artifacts_validated_against_contracts(
        self, runner, wlife, chain
    ) -> None:
        """冒烟阻断修复断言: 每个 executor 产物 metadata 通过 CONTRACTS 校验
        (prd/design/code/test/release 全 VALIDATED — 曾用错误字段致 INVALID)。"""
        wf = runner.run(chain.id)
        for _ in range(2):
            gates = _pending_gates(wlife, chain.id)
            wlife.approve_approval(gates[0].id, reviewer="alice")
            wf = runner.run(chain.id)
        artifacts = list(wlife.store.list_artifacts())
        assert len(artifacts) == 5  # prd + design + code + test + release
        for artifact in artifacts:
            assert artifact.status == ArtifactStatus.VALIDATED
            result = validate_artifact(artifact.type.value, artifact.metadata)
            assert result.ok, f"{artifact.type.value} contract failed: {result.errors}"

    def test_pending_gate_hangs_runner(self, runner, wlife, chain) -> None:
        """待审门守卫: PENDING → run 直接返回 PAUSED, 不推进后续 stage。"""
        wf = runner.run(chain.id)
        assert wf.status == WorkflowStatus.PAUSED
        wf2 = runner.run(chain.id)  # 未决定 → 仍挂起 (禁绕过审批门)
        assert wf2.status == WorkflowStatus.PAUSED
        stages = wlife.list_stages(chain.id)
        assert stages[0].status.value == "completed"  # 门禁 stage 已完成
        assert stages[1].status.value != "running"  # 后续未执行
        # 后续 stage 保持未执行: pending (从未就绪) 或 blocked (Runner 就绪
        # 评估标记依赖未满足 — 同为"未执行"语义, 禁绕过审批门)
        assert all(
            s.status.value in ("pending", "completed", "blocked") for s in stages
        )

    def test_approve_continues_to_next_stage(self, runner, wlife, chain) -> None:
        """approve 后恢复 ACTIVE → 下一 stage 执行 → 下一门挂起。"""
        runner.run(chain.id)
        gate = _pending_gates(wlife, chain.id)[0]
        wlife.approve_approval(gate.id, reviewer="alice")
        wf = runner.run(chain.id)
        assert wf.status == WorkflowStatus.PAUSED  # P2 架构门
        stages = wlife.list_stages(chain.id)
        assert stages[0].status.value == "completed"
        assert stages[1].status.value == "completed"  # architect 已执行
        assert len(_pending_gates(wlife, chain.id)) == 1

    def test_rejected_gate_blocks_rerun(self, runner, wlife, chain) -> None:
        """否决门守卫: REJECTED → run 响亮拒绝 (决定不可撤销, 禁绕过)。"""
        runner.run(chain.id)
        gate = _pending_gates(wlife, chain.id)[0]
        wlife.reject_approval(gate.id, reviewer="bob", comment="no")
        with pytest.raises(WorkflowStateError, match="rejected approval gate"):
            runner.run(chain.id)


class TestBackwardCompat:
    def test_no_gate_workflow_unaffected(self, wlife, project_id) -> None:
        """approval_required=False (默认) → 行为与 S7-003 完全一致。"""
        wf = build_approval_workflow(wlife, project_id)
        # 全部门去掉 → 全链一次跑完
        for stage in wlife.list_stages(wf.id):
            updated = stage.model_copy(update={"approval_required": False})
            wlife.store.save_stage(updated)
        runner = WorkflowRunner(wlife, executor=approval_chain_executor, logger=None)
        result = runner.run(wf.id)
        assert result.status == WorkflowStatus.COMPLETED
        assert wlife.list_approvals(workflow_id=wf.id) == []
