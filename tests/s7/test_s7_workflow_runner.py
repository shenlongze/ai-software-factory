"""tests/s7/test_s7_workflow_runner.py — WorkflowRunner 执行循环 (Unit, S7-003)。

覆盖:
- 就绪判定 (Runner 核心): 依赖 COMPLETED + 输入 VALIDATED → READY;
  依赖未完成 → BLOCKED; 输入未 VALIDATED → BLOCKED; 条件满足解除 → READY
- 执行循环: DRAFT 自动转 ACTIVE / 单 stage 执行 / 线性链全推进 → COMPLETED
  / BLOCKED 时保持 ACTIVE (不假装完成) / 空 workflow → COMPLETED
- Executor 契约: 注入 callable (stage, context) → dict; 输出 Artifact
  自动注册 (create→generated→validated) + stage.output_artifacts 回写
- 失败路径: executor None → WorkflowExecutionError; executor 抛异常 →
  stage FAILED → workflow FAILED (failed_reason+stage_id); 契约失败 → FAILED
- 终态语义: COMPLETED run 幂等; FAILED run → WorkflowStateError
- 步数保护: max_steps 超限 → WorkflowExecutionError

依赖: 本目录 conftest (project_store + logger + event_store)。
"""

from __future__ import annotations

import pytest

from org.projects import ArtifactStatus, StageStatus
from org.workflow import (
    WorkflowExecutionError,
    WorkflowLifecycle,
    WorkflowRunner,
    WorkflowStateError,
    WorkflowStatus,
)

from s7_helpers import event_sequence


@pytest.fixture
def wlife(project_store, logger) -> WorkflowLifecycle:
    return WorkflowLifecycle(project_store, logger=logger)


@pytest.fixture
def wfid(wlife) -> str:
    from org.projects import ProjectLifecycle

    ProjectLifecycle(wlife.store).create_project("Build App", project_id="P-1")
    return wlife.create_workflow("P-1", "Ship v1", workflow_id="WF-1").id


def _prd_metadata() -> dict:
    return {"problem": "p", "user": "u", "features": ["f1"]}


def _code_metadata() -> dict:
    return {"files": ["a.py"], "changes": "impl"}


def _prd_executor(stage, context):
    return {"artifact_type": "prd", "ref": "file:///prd.md", "metadata": _prd_metadata()}


def _code_executor(stage, context):
    return {"artifact_type": "code", "ref": "file:///src", "metadata": _code_metadata()}


def make_runner(wlife, executor=None, **kw):
    return WorkflowRunner(wlife, executor=executor, **kw)


class TestReadiness:
    def test_no_deps_no_inputs_ready(self, wlife, wfid):
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        runner = make_runner(wlife, executor=_prd_executor)
        runner.run("WF-1")
        assert wlife.get_stage("STG-1").status is StageStatus.COMPLETED

    def test_dependency_not_completed_blocks(self, wlife, wfid):
        """依赖未 COMPLETED → 阶段 BLOCKED, workflow 保持 ACTIVE。"""
        wlife.create_stage("WF-1", "developer", input_artifacts=["A-1"], stage_id="STG-1")
        wlife.create_stage("WF-1", "tester", depends_on=["STG-1"], stage_id="STG-2")
        # A-1 存在但未 VALIDATED → STG-1 自身 BLOCKED → STG-2 依赖未完成 → BLOCKED
        wlife.registry.create("STG-1", "prd", project_id="P-1", artifact_id="A-1")
        runner = make_runner(wlife, executor=_code_executor)
        wf = runner.run("WF-1")
        assert wlife.get_stage("STG-1").status is StageStatus.BLOCKED
        assert wlife.get_stage("STG-2").status is StageStatus.BLOCKED
        assert wf.status is WorkflowStatus.ACTIVE  # 不假装完成

    def test_input_not_validated_blocks(self, wlife, wfid):
        """输入产物未 VALIDATED → BLOCKED (输入门禁)。"""
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        wlife.create_stage("WF-1", "tester", depends_on=["STG-1"],
                           input_artifacts=["A-1"], stage_id="STG-2")
        # 产物创建但未校验 (created)
        wlife.registry.create("STG-1", "prd", project_id="P-1", artifact_id="A-1")
        runner = make_runner(wlife, executor=_code_executor)
        wf = runner.run("WF-1")
        assert wlife.get_stage("STG-2").status is StageStatus.BLOCKED
        assert wf.status is WorkflowStatus.ACTIVE

    def test_dependency_and_input_satisfied_ready(self, wlife, wfid):
        """依赖 COMPLETED + 输入 VALIDATED → 放行执行。"""
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        wlife.create_stage("WF-1", "tester", depends_on=["STG-1"],
                           input_artifacts=["A-1"], stage_id="STG-2")
        wlife.registry.create("STG-1", "prd", project_id="P-1",
                              metadata=_prd_metadata(), artifact_id="A-1")
        wlife.registry.mark_generated("A-1")
        wlife.registry.validate("A-1")
        runner = make_runner(wlife, executor=_code_executor)
        wf = runner.run("WF-1")
        assert wlife.get_stage("STG-2").status is StageStatus.COMPLETED
        assert wf.status is WorkflowStatus.COMPLETED

    def test_missing_input_artifact_blocks(self, wlife, wfid):
        """input_artifacts 指向不存在的产物 → BLOCKED (不崩溃)。"""
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        wlife.create_stage("WF-1", "tester", depends_on=["STG-1"],
                           input_artifacts=["A-999"], stage_id="STG-2")
        runner = make_runner(wlife, executor=_code_executor)
        wf = runner.run("WF-1")
        assert wlife.get_stage("STG-2").status is StageStatus.BLOCKED
        assert wf.status is WorkflowStatus.ACTIVE

    def test_blocked_stage_resolves_on_next_run(self, wlife, wfid):
        """输入未验证 → BLOCKED; 人工验证后再次 run → 解除阻塞执行。"""
        wlife.create_stage("WF-1", "developer", input_artifacts=["A-1"], stage_id="STG-1")
        wlife.create_stage("WF-1", "tester", depends_on=["STG-1"], stage_id="STG-2")
        wlife.registry.create("STG-1", "prd", project_id="P-1",
                              metadata=_prd_metadata(), artifact_id="A-1")
        runner = make_runner(wlife, executor=_code_executor)
        wf1 = runner.run("WF-1")
        assert wf1.status is WorkflowStatus.ACTIVE
        assert wlife.get_stage("STG-1").status is StageStatus.BLOCKED
        # 人工验证输入产物后再次 run → STG-1 解除阻塞, 全链推进
        wlife.registry.mark_generated("A-1")
        wlife.registry.validate("A-1")
        wf2 = runner.run("WF-1")
        assert wf2.status is WorkflowStatus.COMPLETED
        assert wlife.get_stage("STG-1").status is StageStatus.COMPLETED
        assert wlife.get_stage("STG-2").status is StageStatus.COMPLETED


class TestExecutionLoop:
    def test_draft_auto_activates(self, wlife, wfid, event_store):
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        make_runner(wlife, executor=_prd_executor).run("WF-1")
        seq = event_sequence(event_store)
        assert "org.workflow.started" in seq

    def test_empty_workflow_completes(self, wlife, wfid):
        wf = make_runner(wlife).run("WF-1")
        assert wf.status is WorkflowStatus.COMPLETED

    def test_single_stage_full_run(self, wlife, wfid):
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        wf = make_runner(wlife, executor=_prd_executor).run("WF-1")
        assert wf.status is WorkflowStatus.COMPLETED
        assert wf.completed_at is not None

    def test_linear_chain_all_completed(self, wlife, wfid):
        """PM → 开发者: 前置完成自动推进到后置。"""
        wlife.create_stage("WF-1", "product-manager", stage_id="STG-1")
        wlife.create_stage("WF-1", "developer", depends_on=["STG-1"], stage_id="STG-2")
        wf = make_runner(wlife, executor=_code_executor).run("WF-1")
        assert wf.status is WorkflowStatus.COMPLETED
        assert wlife.get_stage("STG-1").status is StageStatus.COMPLETED
        assert wlife.get_stage("STG-2").status is StageStatus.COMPLETED

    def test_executor_gets_context(self, wlife, wfid):
        """executor 契约: (stage, context) — context 含 workflow/project_id/inputs。"""
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        seen: dict = {}

        def spy(stage, context):
            seen["stage_id"] = stage.id
            seen["project_id"] = context["project_id"]
            seen["workflow_status"] = context["workflow"].status.value
            seen["inputs"] = context["inputs"]
            return {"artifact_type": "code", "metadata": _code_metadata()}

        make_runner(wlife, executor=spy).run("WF-1")
        assert seen["stage_id"] == "STG-1"
        assert seen["project_id"] == "P-1"
        assert seen["workflow_status"] == WorkflowStatus.ACTIVE.value
        assert seen["inputs"] == []

    def test_paused_workflow_resumes(self, wlife, wfid):
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        wlife.activate("WF-1")
        wlife.pause("WF-1")
        wf = make_runner(wlife, executor=_prd_executor).run("WF-1")  # PAUSED 自动恢复
        assert wf.status is WorkflowStatus.COMPLETED


class TestOutputRegistration:
    def test_output_auto_registered_validated(self, wlife, wfid):
        wlife.create_stage("WF-1", "product-manager", stage_id="STG-1")
        make_runner(wlife, executor=_prd_executor).run("WF-1")
        artifacts = wlife.registry.list()
        assert len(artifacts) == 1
        a = artifacts[0]
        assert a.type.value == "prd"
        assert a.status is ArtifactStatus.VALIDATED
        assert a.producer_role == "product-manager"
        assert a.project_id == "P-1"
        assert a.stage_id == "STG-1"
        assert a.ref == "file:///prd.md"

    def test_stage_output_artifacts_backfilled(self, wlife, wfid):
        wlife.create_stage("WF-1", "product-manager", stage_id="STG-1")

        def prd_named(stage, context):
            return {"artifact_type": "prd", "artifact_id": "A-1",
                    "ref": "file:///prd.md", "metadata": _prd_metadata()}

        make_runner(wlife, executor=prd_named).run("WF-1")
        assert wlife.get_stage("STG-1").output_artifacts == ["A-1"]

    def test_role_default_output_type(self, wlife, wfid):
        """executor 未声明 artifact_type → 按角色默认类型推断 (developer→code)。"""
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")

        def bare_executor(stage, context):
            return {"ref": "file:///src", "metadata": _code_metadata()}

        make_runner(wlife, executor=bare_executor).run("WF-1")
        assert wlife.registry.list()[0].type.value == "code"

    def test_role_default_output_types(self, wlife, wfid):
        """角色 → 默认输出类型契约 (exec 注册表 role_id 单一事实源)。"""
        from org.workflow import ROLE_OUTPUT_TYPES

        assert ROLE_OUTPUT_TYPES["product-manager"] == "prd"
        assert ROLE_OUTPUT_TYPES["architect"] == "design"
        assert ROLE_OUTPUT_TYPES["ui-designer"] == "design"
        assert ROLE_OUTPUT_TYPES["developer"] == "code"
        assert ROLE_OUTPUT_TYPES["tester"] == "test"
        assert ROLE_OUTPUT_TYPES["devops"] == "release"

    def test_multi_artifact_output(self, wlife, wfid):
        """多产物契约: result[\"artifacts\"] list → 全部注册校验。"""
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")

        def multi(stage, context):
            return {"artifacts": [
                {"type": "code", "ref": "file:///a.py", "metadata": _code_metadata()},
                {"type": "test", "ref": "file:///t.py",
                 "metadata": {"results": {"pass": 1}, "bugs": []}},
            ]}

        make_runner(wlife, executor=multi).run("WF-1")
        artifacts = wlife.registry.list()
        assert {a.type.value for a in artifacts} == {"code", "test"}
        assert all(a.status is ArtifactStatus.VALIDATED for a in artifacts)
        assert set(wlife.get_stage("STG-1").output_artifacts) == {a.id for a in artifacts}


class TestFailurePaths:
    def test_no_executor_rejected(self, wlife, wfid):
        """executor=None 且需执行 → 响亮拒绝 (编排壳诚实边界)。"""
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        with pytest.raises(WorkflowExecutionError, match="no executor"):
            make_runner(wlife).run("WF-1")

    def test_executor_raises_fails_workflow(self, wlife, wfid):
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")

        def boom(stage, context):
            raise RuntimeError("llm timeout")

        wf = make_runner(wlife, executor=boom).run("WF-1")
        assert wf.status is WorkflowStatus.FAILED
        assert wlife.get_stage("STG-1").status is StageStatus.FAILED
        assert "RuntimeError" in wf.failed_reason

    def test_executor_none_result_fails(self, wlife, wfid):
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")

        def none_executor(stage, context):
            return None

        wf = make_runner(wlife, executor=none_executor).run("WF-1")
        assert wf.status is WorkflowStatus.FAILED
        assert "returned None" in wf.failed_reason

    def test_contract_failure_fails_workflow(self, wlife, wfid):
        """输出契约校验失败 → 产物 INVALID → stage FAILED → workflow FAILED。"""
        wlife.create_stage("WF-1", "product-manager", stage_id="STG-1")

        def bad_prd(stage, context):
            return {"artifact_type": "prd", "metadata": {"problem": "p"}}  # 缺 user/features

        wf = make_runner(wlife, executor=bad_prd).run("WF-1")
        assert wf.status is WorkflowStatus.FAILED
        assert "contract failed" in wf.failed_reason
        assert wlife.registry.list()[0].status is ArtifactStatus.INVALID

    def test_failed_workflow_cannot_run(self, wlife, wfid):
        """FAILED 终态 run → WorkflowStateError (须 pause 人工介入后重试)。"""
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")

        def boom(stage, context):
            raise RuntimeError("x")

        runner = make_runner(wlife, executor=boom)
        wf = runner.run("WF-1")
        assert wf.status is WorkflowStatus.FAILED
        with pytest.raises(WorkflowStateError, match="failed workflow cannot run"):
            runner.run("WF-1")

    def test_completed_run_idempotent(self, wlife, wfid):
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        calls = []

        def spy(stage, context):
            calls.append(stage.id)
            return {"artifact_type": "code", "metadata": _code_metadata()}

        runner = make_runner(wlife, executor=spy)
        wf1 = runner.run("WF-1")
        assert wf1.status is WorkflowStatus.COMPLETED
        wf2 = runner.run("WF-1")  # 幂等: 不重复执行
        assert wf2.status is WorkflowStatus.COMPLETED
        assert len(calls) == 1

    def test_max_steps_guard(self, wlife, wfid):
        """步数保护: max_steps 超限 → WorkflowExecutionError (防无限循环)。"""
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        wlife.create_stage("WF-1", "tester", stage_id="STG-2")
        runner = make_runner(wlife, executor=_code_executor)
        with pytest.raises(WorkflowExecutionError, match="max steps"):
            runner.run("WF-1", max_steps=1)

    def test_failed_retry_path_via_pause(self, wlife, wfid):
        """失败 → 人工介入 (重置 stage + pause→active) → 换好 executor 重跑成功。"""
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")

        def boom(stage, context):
            raise RuntimeError("first attempt")

        runner = make_runner(wlife, executor=boom)
        assert runner.run("WF-1").status is WorkflowStatus.FAILED
        # 人工介入: 重置失败 stage (failed → pending) + 恢复 workflow
        wlife.transition_stage("STG-1", StageStatus.PENDING)
        wlife.pause("WF-1")
        wlife.activate("WF-1")
        wf = make_runner(wlife, executor=_code_executor).run("WF-1")  # 换好 executor
        assert wf.status is WorkflowStatus.COMPLETED
