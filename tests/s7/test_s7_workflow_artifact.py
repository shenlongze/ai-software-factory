"""tests/s7/test_s7_workflow_artifact.py — Workflow ↔ Artifact 集成 (Unit, S7-003)。

覆盖 (任务清单: Artifact 集成):
- 输入门禁: input_artifacts 全部 VALIDATED → 放行执行; 未验证 (created/generated)
  → BLOCKED; 缺失 → BLOCKED (不崩溃)
- 项目隔离铁律: 跨项目输入拒绝 (P-2 产物 → P-1 workflow 阶段 BLOCKED);
  空 project_id 产物兼容 (S7-001 既有数据, 放行)
- 输出自动注册: executor 结果 → Artifact create→generated→validated,
  producer_role/project_id/stage_id 继承 workflow/stage (输出即下阶段输入)
- 契约失败: 输出校验失败 → INVALID (产物留在注册表可审计) → stage FAILED
- 查询: stage_artifacts / workflow_artifacts 组合查询

依赖: 本目录 conftest (project_store + logger + event_store)。

"""

from __future__ import annotations

import pytest

from org.projects import ArtifactStatus, ProjectLifecycle, StageStatus
from org.workflow import WorkflowLifecycle, WorkflowRunner, WorkflowStatus


@pytest.fixture
def wlife(project_store, logger) -> WorkflowLifecycle:
    return WorkflowLifecycle(project_store, logger=logger)


@pytest.fixture
def wfid(wlife) -> str:
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


def make_validated(wlife, artifact_id: str, *, project_id: str = "P-1",
                   stage_id: str = "STG-1") -> None:
    """快速构造 VALIDATED 产物 (契约满足 prd 类型)。"""
    wlife.registry.create(stage_id, "prd", project_id=project_id,
                          metadata=_prd_metadata(), artifact_id=artifact_id)
    wlife.registry.mark_generated(artifact_id)
    wlife.registry.validate(artifact_id)


class TestInputGate:
    """输入门禁: input_artifacts 全部 VALIDATED 才放行执行。"""

    def test_validated_input_passes(self, wlife, wfid):
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        wlife.create_stage("WF-1", "tester", depends_on=["STG-1"],
                           input_artifacts=["A-1"], stage_id="STG-2")
        make_validated(wlife, "A-1")
        wf = make_runner(wlife, executor=_code_executor).run("WF-1")
        assert wf.status is WorkflowStatus.COMPLETED
        assert wlife.get_stage("STG-2").status is StageStatus.COMPLETED

    def test_created_input_blocks(self, wlife, wfid):
        """输入产物仅 created → BLOCKED (门禁: 须 VALIDATED)。"""
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        wlife.create_stage("WF-1", "tester", depends_on=["STG-1"],
                           input_artifacts=["A-1"], stage_id="STG-2")
        wlife.registry.create("STG-1", "prd", project_id="P-1", artifact_id="A-1")
        wf = make_runner(wlife, executor=_code_executor).run("WF-1")
        assert wlife.get_stage("STG-2").status is StageStatus.BLOCKED
        assert wf.status is WorkflowStatus.ACTIVE  # 不假装完成

    def test_generated_input_blocks(self, wlife, wfid):
        """输入产物 generated (未过契约校验) → BLOCKED。"""
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        wlife.create_stage("WF-1", "tester", depends_on=["STG-1"],
                           input_artifacts=["A-1"], stage_id="STG-2")
        wlife.registry.create("STG-1", "prd", project_id="P-1", artifact_id="A-1")
        wlife.registry.mark_generated("A-1")
        wf = make_runner(wlife, executor=_code_executor).run("WF-1")
        assert wlife.get_stage("STG-2").status is StageStatus.BLOCKED
        assert wf.status is WorkflowStatus.ACTIVE

    def test_missing_input_blocks(self, wlife, wfid):
        """input_artifacts 指向不存在产物 → BLOCKED (引用缺口不崩溃)。"""
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        wlife.create_stage("WF-1", "tester", input_artifacts=["A-999"], stage_id="STG-2")
        wf = make_runner(wlife, executor=_code_executor).run("WF-1")
        assert wlife.get_stage("STG-2").status is StageStatus.BLOCKED
        assert wf.status is WorkflowStatus.ACTIVE

    def test_cross_project_input_blocked(self, wlife, wfid):
        """项目隔离铁律: P-2 的产物不能作为 P-1 workflow 的输入。"""
        # P-2 + WF-2 + STG-9 产出的 A-1 属于项目 P-2
        ProjectLifecycle(wlife.store).create_project("Other", project_id="P-2")
        wlife.create_workflow("P-2", "Other WF", workflow_id="WF-2")
        wlife.create_stage("WF-2", "developer", stage_id="STG-9")
        make_validated(wlife, "A-1", project_id="P-2", stage_id="STG-9")
        # P-1 workflow 阶段引用该产物 → 跨项目拒绝 → BLOCKED
        wlife.create_stage("WF-1", "tester", input_artifacts=["A-1"], stage_id="STG-1")
        wf = make_runner(wlife, executor=_code_executor).run("WF-1")
        assert wlife.get_stage("STG-1").status is StageStatus.BLOCKED
        assert wf.status is WorkflowStatus.ACTIVE

    def test_empty_project_id_input_allowed(self, wlife, wfid):
        """S7-001 兼容: 空 project_id 产物 (既有数据) 放行。"""
        wlife.create_stage("WF-1", "developer", input_artifacts=["A-1"], stage_id="STG-1")
        make_validated(wlife, "A-1", project_id="")
        wf = make_runner(wlife, executor=_code_executor).run("WF-1")
        assert wf.status is WorkflowStatus.COMPLETED
        assert wlife.get_stage("STG-1").status is StageStatus.COMPLETED


class TestOutputRegistration:
    """输出自动注册: executor 结果 → Artifact 继承 workflow/stage 上下文。"""

    def test_output_inherits_context(self, wlife, wfid):
        wlife.create_stage("WF-1", "product-manager", stage_id="STG-1")
        make_runner(wlife, executor=_prd_executor).run("WF-1")
        artifacts = wlife.registry.list()
        assert len(artifacts) == 1
        a = artifacts[0]
        assert a.type.value == "prd"
        assert a.status is ArtifactStatus.VALIDATED  # create→generated→validated
        assert a.producer_role == "product-manager"  # 继承 stage.role_id
        assert a.project_id == "P-1"                 # 继承 workflow.project_id
        assert a.stage_id == "STG-1"                 # 归属执行 stage
        assert a.ref == "file:///prd.md"

    def test_output_becomes_next_stage_input(self, wlife, wfid):
        """输出即下阶段输入: PM 产物自动成为 Dev 阶段输入 (全链 Artifact 传递)。"""
        wlife.create_stage("WF-1", "product-manager", stage_id="STG-1")
        wlife.create_stage("WF-1", "developer", depends_on=["STG-1"],
                           input_artifacts=["A-PRD"], stage_id="STG-2")
        seen: dict = {}

        def prd_named(stage, context):
            return {"artifact_type": "prd", "artifact_id": "A-PRD",
                    "ref": "file:///prd.md", "metadata": _prd_metadata()}

        def dev(stage, context):
            seen["inputs"] = context["inputs"]
            return {"artifact_type": "code", "metadata": _code_metadata()}

        runner = make_runner(wlife, executor=lambda s, c: (
            prd_named(s, c) if s.id == "STG-1" else dev(s, c)
        ))
        wf = runner.run("WF-1")
        assert wf.status is WorkflowStatus.COMPLETED
        assert wlife.get_stage("STG-2").output_artifacts  # dev 输出已回写
        # dev 的 executor 收到 PM 产物作为输入 (VALIDATED 契约载荷)
        assert seen["inputs"][0]["id"] == "A-PRD"
        assert seen["inputs"][0]["type"] == "prd"
        assert seen["inputs"][0]["status"] == "validated"

    def test_contract_failure_leaves_invalid_artifact(self, wlife, wfid):
        """输出契约失败 → 产物 INVALID 留在注册表 (审计) → stage/workflow FAILED。"""
        wlife.create_stage("WF-1", "product-manager", stage_id="STG-1")

        def bad_prd(stage, context):
            return {"artifact_type": "prd", "metadata": {"problem": "p"}}  # 缺 user/features

        wf = make_runner(wlife, executor=bad_prd).run("WF-1")
        assert wf.status is WorkflowStatus.FAILED
        assert "contract failed" in wf.failed_reason
        artifact = wlife.registry.list()[0]
        assert artifact.status is ArtifactStatus.INVALID  # 失败产物可审计可重生成
        assert artifact.stage_id == "STG-1"


class TestArtifactQuery:
    """阶段/工作流产物组合查询 (复用 ArtifactRegistry.query)。"""

    def _role_executor(self):
        """角色分派 executor: PM → prd, Dev → code (查询断言确定性)。"""

        def run(stage, context):
            if stage.role_id == "product-manager":
                return _prd_executor(stage, context)
            return _code_executor(stage, context)

        return run

    def test_stage_artifacts_query(self, wlife, wfid):
        wlife.create_stage("WF-1", "product-manager", stage_id="STG-1")
        wlife.create_stage("WF-1", "developer", depends_on=["STG-1"], stage_id="STG-2")
        make_runner(wlife, executor=self._role_executor()).run("WF-1")
        stg1 = wlife.stage_artifacts("STG-1")
        stg2 = wlife.stage_artifacts("STG-2")
        assert [a.type.value for a in stg1] == ["prd"]
        assert [a.type.value for a in stg2] == ["code"]
        assert wlife.stage_artifacts("STG-999") == []  # 未知 stage → 空

    def test_workflow_artifacts_query(self, wlife, wfid):
        """workflow_artifacts 汇总全阶段产物 (按 stage 归属)。"""
        wlife.create_stage("WF-1", "product-manager", stage_id="STG-1")
        wlife.create_stage("WF-1", "developer", depends_on=["STG-1"], stage_id="STG-2")
        make_runner(wlife, executor=self._role_executor()).run("WF-1")
        all_artifacts = wlife.workflow_artifacts("WF-1")
        assert sorted(a.type.value for a in all_artifacts) == ["code", "prd"]
        assert all(a.project_id == "P-1" for a in all_artifacts)
