"""tests/s8/test_s8_workflow_release.py — Workflow release stage 接入 (Integration, S8-004)。

覆盖 (任务清单: Workflow 接入测试 — release stage 定义 + Runner 执行 + 事件
+ Test VALIDATED 就绪门禁):
- release stage 定义: WorkflowLifecycle.create_stage(role_id="devops",
  name="release") → Stage.role_id / workflow.stage_ids 索引 / DAG 拓扑序
- Runner 执行 (mock release executor): build_release_executor(ReleaseAgent +
  mock provider) → stage COMPLETED → workflow COMPLETED + release artifact
  VALIDATED (5 节 + artifact_refs 强引用 [code_id, test_id])
- ★ 就绪判定 (Runner 零修改): 输入 test 仅 CREATED (未 VALIDATED) → stage
  BLOCKED → workflow ACTIVE; code+test 均 VALIDATED 后重跑 → COMPLETED
- 事件链: created→started→stage_ready→stage_started→stage_completed→completed
  + org.artifact.created/validated; stage_completed payload 带 role_id=devops
- 契约失败: executor 输出缺 5 节 → release INVALID → stage FAILED →
  workflow FAILED (org.workflow.failed 带 stage_id 审计)
- 缺双输入响亮失败: context 无 code/test 输入产物 → ReleaseError → stage
  FAILED → workflow FAILED (诚实, 不臆造输入)
- LLM 垃圾输出响亮失败: 不可解析 → stage FAILED → workflow FAILED

依赖: 本目录 conftest (wlife/project_id/pm_mock_provider/event_store) + s8_helpers。
"""

from __future__ import annotations

from exec.release import ReleaseAgent, build_release_executor
from org.models import utcnow
from org.projects import ArtifactStatus, StageStatus
from org.workflow import WorkflowRunner, WorkflowStatus

from s8_helpers import (
    code_payload_ok,
    event_sequence,
    payload_of,
    release_json,
    release_payload_ok,
    qa_payload_ok,
)


def _build_release_workflow(
    wlife,
    project_id,
    *,
    workflow_id: str = "WF-REL",
    stage_id: str = "STG-REL",
    input_artifacts: list[str] | None = None,
):
    """release 单阶段 workflow (role_ref=devops, 阶段名 release)。"""
    workflow = wlife.create_workflow(project_id, "发布流水线", workflow_id=workflow_id)
    stage = wlife.create_stage(
        workflow.id,
        "devops",
        name="release",
        stage_id=stage_id,
        input_artifacts=input_artifacts,
    )
    return workflow, stage


def _release_agent(provider) -> ReleaseAgent:
    """双输入齐备的 ReleaseAgent (构造强校验; executor 执行时从 context
    解析输入产物覆盖绑定 — 见 release.py build_release_executor)。"""
    return ReleaseAgent(
        provider, code=code_payload_ok(), test=qa_payload_ok()
    )


def _seed_validated_inputs(
    wlife,
    stage_id,
    *,
    code_id: str = "A-CODE-REL",
    test_id: str = "A-TEST-REL",
):
    """预建 VALIDATED code + test 产物 (release 阶段双输入; 就绪判定前置)。"""
    code = wlife.registry.create(
        stage_id,
        "code",
        project_id="P-8",
        producer_role="developer",
        metadata=code_payload_ok(),
        artifact_id=code_id,
    )
    wlife.registry.mark_generated(code.id)
    wlife.registry.validate(code.id)
    test = wlife.registry.create(
        stage_id,
        "test",
        project_id="P-8",
        producer_role="tester",
        metadata=qa_payload_ok(),
        artifact_id=test_id,
    )
    wlife.registry.mark_generated(test.id)
    wlife.registry.validate(test.id)
    return code, test


class TestReleaseStageDefinition:
    def test_stage_role_ref_devops(self, wlife, project_id):
        """release stage: role_id=devops (exec 注册表校验通过, 阶段名 release)。"""
        workflow, stage = _build_release_workflow(wlife, project_id)
        assert stage.role_id == "devops"
        assert stage.name == "release"
        assert stage.workflow_id == workflow.id

    def test_stage_indexed_in_workflow(self, wlife, project_id):
        """workflow.stage_ids 索引 + DAG 拓扑序 (单阶段可执行)。"""
        _build_release_workflow(wlife, project_id)
        current = wlife.get_workflow("WF-REL")  # 重新取 — create 返回旧对象
        assert current.stage_ids == ["STG-REL"]
        assert wlife.validate_dag("WF-REL") == ["STG-REL"]


class TestRunnerReleaseStage:
    def test_happy_path_release_validated(self, wlife, project_id, pm_mock_provider):
        """Runner 执行: mock release executor → stage COMPLETED → workflow
        COMPLETED, release artifact VALIDATED (producer_role=devops, 5 节)。"""
        provider = pm_mock_provider(release_json())
        workflow, stage = _build_release_workflow(
            wlife, project_id, input_artifacts=["A-CODE-REL", "A-TEST-REL"]
        )
        _seed_validated_inputs(wlife, stage.id)
        runner = WorkflowRunner(
            wlife, executor=build_release_executor(_release_agent(provider))
        )
        workflow = runner.run("WF-REL")
        assert workflow.status is WorkflowStatus.COMPLETED
        assert wlife.get_stage("STG-REL").status is StageStatus.COMPLETED
        releases = wlife.registry.query(type_="release", project_id="P-8")
        assert len(releases) == 1
        artifact = releases[0]
        assert artifact.status is ArtifactStatus.VALIDATED
        assert artifact.producer_role == "devops"
        # 5 节契约载荷 + artifact_refs 强引用 (code/test 产物 id)
        for field in (
            "build_result", "version", "package", "release_notes", "deployment",
        ):
            assert field in artifact.metadata
        assert artifact.metadata["artifact_refs"] == ["A-CODE-REL", "A-TEST-REL"]

    def test_blocks_until_inputs_validated(self, wlife, project_id, pm_mock_provider):
        """★ Test VALIDATED 就绪门禁 (Runner 零修改): 输入 code/test 仅
        CREATED (未 VALIDATED) → stage BLOCKED → workflow ACTIVE;
        VALIDATED 后重跑 → COMPLETED。"""
        provider = pm_mock_provider(release_json())
        workflow, stage = _build_release_workflow(
            wlife, project_id, input_artifacts=["A-CODE-PEND", "A-TEST-PEND"]
        )
        wlife.registry.create(
            stage.id,
            "code",
            project_id="P-8",
            producer_role="developer",
            metadata=code_payload_ok(),
            artifact_id="A-CODE-PEND",
        )
        wlife.registry.create(
            stage.id,
            "test",
            project_id="P-8",
            producer_role="tester",
            metadata=qa_payload_ok(),
            artifact_id="A-TEST-PEND",
        )
        runner = WorkflowRunner(
            wlife, executor=build_release_executor(_release_agent(provider))
        )
        workflow = runner.run("WF-REL")
        assert workflow.status is WorkflowStatus.ACTIVE
        assert wlife.get_stage("STG-REL").status is StageStatus.BLOCKED
        assert wlife.registry.query(type_="release", project_id="P-8") == []
        # 输入就绪 (VALIDATED) → 重跑 → 推进完成
        wlife.registry.mark_generated("A-CODE-PEND")
        wlife.registry.validate("A-CODE-PEND")
        wlife.registry.mark_generated("A-TEST-PEND")
        wlife.registry.validate("A-TEST-PEND")
        workflow = runner.run("WF-REL")
        assert workflow.status is WorkflowStatus.COMPLETED
        assert wlife.get_stage("STG-REL").status is StageStatus.COMPLETED
        releases = wlife.registry.query(type_="release", project_id="P-8")
        assert len(releases) == 1
        assert releases[0].status is ArtifactStatus.VALIDATED

    def test_event_chain_and_payload(self, wlife, project_id, pm_mock_provider, event_store):
        """事件链: 全链序 + stage_completed payload (role_id 审计)。"""
        provider = pm_mock_provider(release_json())
        workflow, stage = _build_release_workflow(
            wlife, project_id, input_artifacts=["A-CODE-EV", "A-TEST-EV"]
        )
        _seed_validated_inputs(wlife, stage.id, code_id="A-CODE-EV", test_id="A-TEST-EV")
        runner = WorkflowRunner(
            wlife, executor=build_release_executor(_release_agent(provider))
        )
        runner.run("WF-REL")
        seq = event_sequence(event_store)
        expected = [
            "org.workflow.created",
            "org.workflow.started",
            "org.workflow.stage_ready",
            "org.workflow.stage_started",
            "org.workflow.stage_completed",
            "org.workflow.completed",
        ]
        assert [t for t in seq if t in expected] == expected
        assert "org.artifact.created" in seq
        assert "org.artifact.validated" in seq
        payload = payload_of(event_store, "org.workflow.stage_completed")
        assert payload["role_id"] == "devops"
        assert payload["stage_id"] == "STG-REL"

    def test_contract_failure_fails_workflow(self, wlife, project_id, event_store):
        """executor 输出缺 5 节 → release 契约 INVALID → stage FAILED →
        workflow FAILED (failed 事件带 stage_id)。"""
        def bad_executor(stage, context):  # noqa: ARG001 — executor 契约签名
            return {
                "artifact_type": "release",
                "ref": "file:///dist/release.json",
                "metadata": {"version": "只有一节"},
            }

        workflow, stage = _build_release_workflow(
            wlife, project_id, input_artifacts=["A-CODE-BAD", "A-TEST-BAD"]
        )
        _seed_validated_inputs(wlife, stage.id, code_id="A-CODE-BAD", test_id="A-TEST-BAD")
        runner = WorkflowRunner(wlife, executor=bad_executor)
        workflow = runner.run("WF-REL")
        assert workflow.status is WorkflowStatus.FAILED
        assert wlife.get_stage("STG-REL").status is StageStatus.FAILED
        assert "contract failed" in workflow.failed_reason
        releases = wlife.registry.query(type_="release", project_id="P-8")
        assert len(releases) == 1
        assert releases[0].status is ArtifactStatus.INVALID
        assert "build_result" in releases[0].invalid_reason
        failed = payload_of(event_store, "org.workflow.failed")
        assert failed["stage_id"] == "STG-REL"

    def test_no_inputs_honest_failure(self, wlife, project_id, pm_mock_provider):
        """无输入 code/test 产物 → ReleaseError → workflow FAILED
        (诚实, 不臆造输入; 即使 agent 构造已绑定 payload)。"""
        provider = pm_mock_provider(release_json())
        _build_release_workflow(wlife, project_id)
        runner = WorkflowRunner(
            wlife, executor=build_release_executor(_release_agent(provider))
        )
        workflow = runner.run("WF-REL")
        assert workflow.status is WorkflowStatus.FAILED
        assert wlife.get_stage("STG-REL").status is StageStatus.FAILED
        assert "BOTH" in workflow.failed_reason

    def test_bad_llm_output_fails_workflow(self, wlife, project_id, pm_mock_provider):
        """LLM 垃圾输出 (不可解析) → ReleaseError → workflow FAILED
        (响亮拒绝, 不假装生成成功)。"""
        provider = pm_mock_provider("这不是 JSON, 随便一段文字")
        workflow, stage = _build_release_workflow(
            wlife, project_id, input_artifacts=["A-CODE-BADLLM", "A-TEST-BADLLM"]
        )
        _seed_validated_inputs(wlife, stage.id, code_id="A-CODE-BADLLM", test_id="A-TEST-BADLLM")
        runner = WorkflowRunner(
            wlife, executor=build_release_executor(_release_agent(provider))
        )
        workflow = runner.run("WF-REL")
        assert workflow.status is WorkflowStatus.FAILED
        assert wlife.get_stage("STG-REL").status is StageStatus.FAILED
        assert "not valid JSON" in workflow.failed_reason


class TestFullChainCodeTestToRelease:
    def test_full_chain_code_test_to_release(self, wlife, project_id, pm_mock_provider):
        """code → release 全链: code 阶段 (dev executor) 产出 VALIDATED code
        + test 阶段 (tester executor) 产出 VALIDATED test → 动态接线为
        release 输入 → release 阶段 (release executor) 消费双输入契约载荷 →
        release VALIDATED (Runner 零修改, 事件链完整)。"""
        provider = pm_mock_provider(release_json())
        workflow = wlife.create_workflow(
            project_id, "发布流水线", workflow_id="WF-CHAIN-REL"
        )
        wlife.create_stage(
            workflow.id,
            "developer",
            name="development",
            stage_id="STG-CHAIN-DEV",
        )
        wlife.create_stage(
            workflow.id,
            "tester",
            name="testing",
            stage_id="STG-CHAIN-T",
            depends_on=["STG-CHAIN-DEV"],
            input_artifacts=["A-CODE-PENDING"],  # 占位: 未就绪 → BLOCKED
        )
        wlife.create_stage(
            workflow.id,
            "devops",
            name="release",
            stage_id="STG-CHAIN-REL",
            depends_on=["STG-CHAIN-T"],
            input_artifacts=["A-CODE-PENDING", "A-TEST-PENDING"],  # 占位
        )

        def dev_executor(stage, context):  # noqa: ARG001 — executor 契约签名
            return {
                "artifact_type": "code",
                "ref": "file:///src",
                "metadata": code_payload_ok(),
            }

        def tester_executor(stage, context):  # noqa: ARG001 — executor 契约签名
            return {
                "artifact_type": "test",
                "ref": "file:///test_result.json",
                "metadata": qa_payload_ok(),
            }

        # 阶段 1: development 执行 (testing/release 输入占位未 VALIDATED → BLOCKED)
        runner1 = WorkflowRunner(wlife, executor=dev_executor)
        workflow = runner1.run("WF-CHAIN-REL")
        assert workflow.status is WorkflowStatus.ACTIVE
        assert wlife.get_stage("STG-CHAIN-DEV").status is StageStatus.COMPLETED
        assert wlife.get_stage("STG-CHAIN-T").status is StageStatus.BLOCKED
        code_artifact = wlife.registry.query(type_="code", project_id="P-8")[0]
        assert code_artifact.status is ArtifactStatus.VALIDATED
        # 动态接线: testing 阶段输入 = code 产物 id (同 S7-005 _wire 模式)
        stage = wlife.get_stage("STG-CHAIN-T")
        wired = stage.model_copy(
            update={
                "input_artifacts": [code_artifact.id],
                "updated_at": utcnow(),
            }
        )
        wlife.store.save_stage(wired)
        # 阶段 2: testing 执行 → test VALIDATED (release 输入 test 占位仍未就绪)
        runner2 = WorkflowRunner(wlife, executor=tester_executor)
        workflow = runner2.run("WF-CHAIN-REL")
        assert workflow.status is WorkflowStatus.ACTIVE
        assert wlife.get_stage("STG-CHAIN-T").status is StageStatus.COMPLETED
        test_artifact = wlife.registry.query(type_="test", project_id="P-8")[0]
        assert test_artifact.status is ArtifactStatus.VALIDATED
        # 动态接线: release 阶段输入 = [code_id, test_id]
        stage = wlife.get_stage("STG-CHAIN-REL")
        wired = stage.model_copy(
            update={
                "input_artifacts": [code_artifact.id, test_artifact.id],
                "updated_at": utcnow(),
            }
        )
        wlife.store.save_stage(wired)
        # 阶段 3: release 执行 (release executor, 无绑定 payload — 从 context 消费)
        runner3 = WorkflowRunner(
            wlife, executor=build_release_executor(_release_agent(provider))
        )
        workflow = runner3.run("WF-CHAIN-REL")
        assert workflow.status is WorkflowStatus.COMPLETED
        assert wlife.get_stage("STG-CHAIN-REL").status is StageStatus.COMPLETED
        releases = wlife.registry.query(type_="release", project_id="P-8")
        assert len(releases) == 1
        assert releases[0].status is ArtifactStatus.VALIDATED
        # artifact_refs 指向链上前序产物 (dev→code id, tester→test id)
        assert releases[0].metadata["artifact_refs"] == [
            code_artifact.id, test_artifact.id,
        ]
