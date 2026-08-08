"""tests/s7/test_s7_workflow_integration.py — Project→Workflow→Stage→Artifact→Runner
全链集成 (Integration, S7-003)。

覆盖 (任务清单: 全链/阻塞/失败/重试):
- 全链: Project (ProjectLifecycle) → Workflow (编排壳) → Stage (DAG 依赖)
  → Artifact (输出自动注册) → Runner (推进) — 端到端 COMPLETED,
  3 阶段 3 产物 (prd/code/test) 全 VALIDATED + 事件闭环
- 阻塞: 外部输入未验证 → BLOCKED/ACTIVE; 人工验证后重跑 → 解除推进
- 失败: executor 抛异常 → stage FAILED → workflow FAILED (failed_reason
  + org.workflow.failed 事件 stage_id 定位)
- 重试: 人工介入 (重置失败 stage + failed→paused→active) → 换好 executor
  重跑 → 全链 COMPLETED (失败可重试路径)
- 持久化: workflows.json 落盘 + 新生命周期实例重开数据空间可见
  (workflow/stages/artifacts 全量恢复)

依赖: 本目录 conftest (org_dir/project_store/logger/event_store)。

"""

from __future__ import annotations

import pytest

from org.projects import ArtifactStatus, ProjectLifecycle, StageStatus
from org.workflow import (
    WorkflowLifecycle,
    WorkflowRunner,
    WorkflowStatus,
    workflow_files,
)

from s7_helpers import event_sequence


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


def _test_metadata() -> dict:
    return {"results": {"pass": 3}, "bugs": []}


def make_role_executor(executors: dict):
    """角色分派 executor: 按 stage.role_id 查表, 缺角色 → 响亮失败。"""

    def run(stage, context):
        fn = executors.get(stage.role_id)
        if fn is None:
            raise RuntimeError(f"no executor for role {stage.role_id!r}")
        return fn(stage, context)

    return run


def make_runner(wlife, executor=None, **kw):
    return WorkflowRunner(wlife, executor=executor, **kw)


class TestFullChain:
    """Project → Workflow → Stage → Artifact → Runner 端到端全链。"""

    def test_full_pipeline_completes(self, wlife, wfid, event_store):
        """PM → Developer → Tester: 全链推进, 每阶段产物自动注册并成为下阶段输入。"""
        wlife.create_stage("WF-1", "product-manager", stage_id="STG-1")
        wlife.create_stage("WF-1", "developer", depends_on=["STG-1"], stage_id="STG-2")
        wlife.create_stage("WF-1", "tester", depends_on=["STG-2"], stage_id="STG-3")

        executor = make_role_executor({
            "product-manager": lambda s, c: {
                "artifact_type": "prd", "ref": "file:///prd.md", "metadata": _prd_metadata()},
            "developer": lambda s, c: {
                "artifact_type": "code", "ref": "file:///src", "metadata": _code_metadata()},
            "tester": lambda s, c: {
                "artifact_type": "test", "metadata": _test_metadata()},
        })

        wf = make_runner(wlife, executor=executor).run("WF-1")

        # Workflow 终态 + 审计时间戳
        assert wf.status is WorkflowStatus.COMPLETED
        assert wf.completed_at is not None
        # 全阶段完成
        assert [s.status for s in wlife.list_stages("WF-1")] == [
            StageStatus.COMPLETED] * 3
        # 全产物注册且 VALIDATED (类型契约通过)
        artifacts = wlife.registry.list()
        assert sorted(a.type.value for a in artifacts) == ["code", "prd", "test"]
        assert all(a.status is ArtifactStatus.VALIDATED for a in artifacts)
        assert all(a.project_id == "P-1" for a in artifacts)
        # 事件闭环: 全链 workflow 事件序 (含 org.artifact.* 伴生事件)
        seq = event_sequence(event_store)
        assert "org.workflow.completed" in seq
        assert seq.count("org.workflow.stage_completed") == 3
        assert seq.count("org.artifact.validated") == 3

    def test_upstream_artifact_flows_to_downstream(self, wlife, wfid):
        """上游产物流入下游 executor 输入 (Artifact 即工作流上下文)。"""
        wlife.create_stage("WF-1", "product-manager", stage_id="STG-1")
        wlife.create_stage("WF-1", "developer", depends_on=["STG-1"],
                           input_artifacts=["A-PRD"], stage_id="STG-2")
        seen: dict = {}

        def dev(stage, context):
            seen["inputs"] = context["inputs"]
            return {"artifact_type": "code", "metadata": _code_metadata()}

        executor = make_role_executor({
            "product-manager": lambda s, c: {
                "artifact_type": "prd", "artifact_id": "A-PRD",
                "ref": "file:///prd.md", "metadata": _prd_metadata()},
            "developer": dev,
        })
        make_runner(wlife, executor=executor).run("WF-1")
        assert seen["inputs"], "developer 阶段应收到 PM 产物输入"
        assert seen["inputs"][0]["id"] == "A-PRD"
        assert seen["inputs"][0]["type"] == "prd"
        assert seen["inputs"][0]["status"] == "validated"


class TestBlockedFlow:
    """阻塞路径: 外部输入未验证 → 保持 ACTIVE; 人工验证后解除推进。"""

    def test_external_input_blocks_then_unblocks(self, wlife, wfid):
        """外部 PRD (人工闸门): 未验证 → BLOCKED; 验证后重跑 → 全链完成。"""
        wlife.create_stage("WF-1", "developer", input_artifacts=["A-1"], stage_id="STG-1")
        wlife.create_stage("WF-1", "tester", depends_on=["STG-1"], stage_id="STG-2")
        # 外部产物仅 created (人工闸门未放行)
        wlife.registry.create("STG-1", "prd", project_id="P-1",
                              metadata=_prd_metadata(), artifact_id="A-1")
        executor = make_role_executor({
            "developer": lambda s, c: {
                "artifact_type": "code", "metadata": _code_metadata()},
            "tester": lambda s, c: {
                "artifact_type": "test", "metadata": _test_metadata()},
        })
        runner = make_runner(wlife, executor=executor)

        wf1 = runner.run("WF-1")
        assert wf1.status is WorkflowStatus.ACTIVE  # 不假装完成
        assert wlife.get_stage("STG-1").status is StageStatus.BLOCKED
        assert wlife.get_stage("STG-2").status is StageStatus.BLOCKED

        # 人工验证外部输入 → 再次 run → 解除阻塞, 全链推进
        wlife.registry.mark_generated("A-1")
        wlife.registry.validate("A-1")
        wf2 = runner.run("WF-1")
        assert wf2.status is WorkflowStatus.COMPLETED
        assert wlife.get_stage("STG-1").status is StageStatus.COMPLETED
        assert wlife.get_stage("STG-2").status is StageStatus.COMPLETED


class TestFailureAndRetry:
    """失败路径 + 人工介入重试 (failed → paused → active)。"""

    def test_executor_failure_fails_workflow(self, wlife, wfid, event_store):
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")

        def boom(stage, context):
            raise RuntimeError("llm timeout")

        wf = make_runner(wlife, executor=boom).run("WF-1")
        assert wf.status is WorkflowStatus.FAILED
        assert "llm timeout" in wf.failed_reason
        assert wlife.get_stage("STG-1").status is StageStatus.FAILED
        # 失败事件: workflow.failed 带 stage_id 定位
        from s7_helpers import payload_of

        payload = payload_of(event_store, "org.workflow.failed")
        assert payload["stage_id"] == "STG-1"
        assert payload["status"] == "failed"

    def test_manual_retry_after_failure(self, wlife, wfid):
        """失败 → 人工介入 (重置 stage + pause→active) → 换好 executor → 全链完成。"""
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        wlife.create_stage("WF-1", "tester", depends_on=["STG-1"], stage_id="STG-2")

        def boom(stage, context):
            raise RuntimeError("first attempt")

        runner = make_runner(wlife, executor=boom)
        assert runner.run("WF-1").status is WorkflowStatus.FAILED

        # 人工介入: 重置失败 stage (failed → pending) + 恢复 workflow
        wlife.transition_stage("STG-1", StageStatus.PENDING)
        wlife.pause("WF-1")
        wlife.activate("WF-1")

        good = make_role_executor({
            "developer": lambda s, c: {
                "artifact_type": "code", "metadata": _code_metadata()},
            "tester": lambda s, c: {
                "artifact_type": "test", "metadata": _test_metadata()},
        })
        wf = make_runner(wlife, executor=good).run("WF-1")
        assert wf.status is WorkflowStatus.COMPLETED
        assert all(
            s.status is StageStatus.COMPLETED for s in wlife.list_stages("WF-1")
        )
        assert sorted(a.type.value for a in wlife.registry.list()) == ["code", "test"]


class TestPersistence:
    """持久化: workflows.json 落盘 + 新实例重开数据空间全量恢复。"""

    def test_workflow_files_created(self, wlife, wfid, org_dir):
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        make_runner(wlife, executor=lambda s, c: {
            "artifact_type": "code", "metadata": _code_metadata()}).run("WF-1")
        files = workflow_files(str(org_dir))
        assert files == [org_dir / "workflows.json"]

    def test_new_instance_sees_full_state(self, wlife, wfid, org_dir, project_store):
        """新 WorkflowLifecycle 实例重开同一数据空间: workflow/stages/artifacts 恢复。"""
        wlife.create_stage("WF-1", "product-manager", stage_id="STG-1")
        wlife.create_stage("WF-1", "developer", depends_on=["STG-1"], stage_id="STG-2")
        make_runner(wlife, executor=lambda s, c: {
            "artifact_type": "prd" if s.role_id == "product-manager" else "code",
            "metadata": _prd_metadata() if s.role_id == "product-manager" else _code_metadata(),
        }).run("WF-1")

        reopened = WorkflowLifecycle(project_store)  # 同数据空间新实例
        wf = reopened.get_workflow("WF-1")
        assert wf.status is WorkflowStatus.COMPLETED
        assert wf.completed_at is not None
        assert [s.id for s in reopened.list_stages("WF-1")] == ["STG-1", "STG-2"]
        artifacts = reopened.registry.list()
        assert sorted(a.type.value for a in artifacts) == ["code", "prd"]
        assert all(a.status is ArtifactStatus.VALIDATED for a in artifacts)
