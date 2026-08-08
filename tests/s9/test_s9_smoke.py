"""tests/s9/test_s9_smoke.py — S9-001 冒烟 (executor 全链 + CONTRACTS 同源)。

冒烟阻断修复 (任务清单): executor metadata 曾用 prd/code 错误字段致产物
INVALID (validate_artifact 契约失败 → stage FAILED → workflow FAILED)。
本文件按 factory-org/org/artifact.py CONTRACTS 逐字段构造 payload, 并显式
断言:
- 5 类 payload helper 全部通过 validate_artifact (与契约同源)
- 全链三挡板: 3 门逐一 approve → workflow COMPLETED, 产物全 VALIDATED
- 坏 metadata 响亮失败 (契约失败 → stage FAILED → workflow FAILED —
  证明阻断机理与修复)
- 中途否决 → workflow FAILED, 后续 stage 不执行

依赖: 本目录 conftest + s9_helpers。
"""

from __future__ import annotations

import pytest

from org.artifact import validate_artifact
from org.workflow import (
    WorkflowLifecycle,
    WorkflowRunner,
    WorkflowStatus,
)

from s9_helpers import (
    build_approval_workflow,
    code_payload_ok,
    design_payload_ok,
    prd_payload_ok,
    qa_payload_ok,
    release_payload_ok,
)


class TestContractPayloads:
    """冒烟阻断修复断言: 每类 executor payload 与 CONTRACTS 同源 (全通过)。"""

    @pytest.mark.parametrize(
        "type_,payload",
        [
            ("prd", prd_payload_ok()),
            ("design", design_payload_ok()),
            ("code", code_payload_ok()),
            ("test", qa_payload_ok()),
            ("release", release_payload_ok()),
        ],
        ids=["prd", "design", "code", "test", "release"],
    )
    def test_payload_ok_validates(self, type_: str, payload: dict) -> None:
        result = validate_artifact(type_, payload)
        assert result.ok, f"{type_} contract failed: missing={result.missing} errors={result.errors}"

    def test_bad_metadata_fails_contract(self) -> None:
        """冒烟阻断复现: 错误字段 (如缺 design 必填) → 契约响亮失败。"""
        bad = {"system_architecture": "only one field"}  # 缺 6 个必填
        result = validate_artifact("design", bad)
        assert result.ok is False
        assert len(result.missing) == 6


class TestSmokeChain:
    def test_full_chain_three_gates_to_completed(self, wlife, project_id) -> None:
        """冒烟主链路: 5 阶段 (pm/arch/dev/tester/devops) 三挡板全放行 →
        COMPLETED; 每阶段产物 VALIDATED (CONTRACTS 契约门禁)。"""
        from s9_helpers import approval_chain_executor

        wf = build_approval_workflow(wlife, project_id)
        runner = WorkflowRunner(wlife, executor=approval_chain_executor)
        wf = runner.run(wf.id)
        assert wf.status == WorkflowStatus.PAUSED
        pending = [
            g for g in wlife.list_approvals(workflow_id=wf.id)
            if g.status.value == "pending"
        ]
        while pending:
            wlife.approve_approval(pending[0].id, reviewer="smoke", comment="ok")
            wf = runner.run(wf.id)
            pending = [
                g for g in wlife.list_approvals(workflow_id=wf.id)
                if g.status.value == "pending"
            ]
        assert wf.status == WorkflowStatus.COMPLETED
        artifacts = list(wlife.store.list_artifacts())
        types = sorted(a.type.value for a in artifacts)
        assert types == ["code", "design", "prd", "release", "test"]
        for artifact in artifacts:
            result = validate_artifact(artifact.type.value, artifact.metadata)
            assert result.ok, f"{artifact.type.value} INVALID: {result.errors}"

    def test_reject_mid_chain_stops_execution(self, wlife, project_id) -> None:
        """冒烟中途否决: P2 架构门否决 → workflow FAILED, developer 不执行。"""
        from s9_helpers import approval_chain_executor

        wf = build_approval_workflow(wlife, project_id)
        runner = WorkflowRunner(wlife, executor=approval_chain_executor)
        runner.run(wf.id)
        g1 = [
            g for g in wlife.list_approvals(workflow_id=wf.id)
            if g.status.value == "pending"
        ][0]
        wlife.approve_approval(g1.id, reviewer="smoke", comment="P1 ok")
        runner.run(wf.id)
        g2 = [
            g for g in wlife.list_approvals(workflow_id=wf.id)
            if g.status.value == "pending"
        ][0]
        wlife.reject_approval(g2.id, reviewer="smoke", comment="架构方案不采纳")
        workflow = wlife.get_workflow(wf.id)
        assert workflow.status == WorkflowStatus.FAILED
        stages = wlife.list_stages(wf.id)
        dev = [s for s in stages if s.role_id == "developer"][0]
        assert dev.status.value in ("pending", "blocked")  # 未执行
        artifacts = [a.type.value for a in wlife.store.list_artifacts()]
        assert "code" not in artifacts  # developer 未产出

    def test_executor_requires_valid_contract(self, wlife, project_id) -> None:
        """坏 executor (错误 metadata) → 产物 INVALID → stage FAILED →
        workflow FAILED (响亮, 不假装完成 — 冒烟阻断机理)。"""
        wf = build_approval_workflow(wlife, project_id)

        def bad_executor(stage, context):
            return {"artifact_type": "prd", "metadata": {"wrong": "field"}}

        runner = WorkflowRunner(wlife, executor=bad_executor)
        result = runner.run(wf.id)
        assert result.status == WorkflowStatus.FAILED
        assert "contract failed" in result.failed_reason
        pm = wlife.list_stages(wf.id)[0]
        assert pm.status.value == "failed"
        # 契约失败 → 门不创建 (未 COMPLETED, 无审批点)
        assert wlife.list_approvals(workflow_id=wf.id) == []
