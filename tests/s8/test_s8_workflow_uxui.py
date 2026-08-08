"""tests/s8/test_s8_workflow_uxui.py — Workflow ux_ui stage 接入 (Integration, S8-002)。

覆盖 (任务清单: product → ux_ui stage, Runner 零修改 + 事件链):
- ux_ui stage 定义: WorkflowLifecycle.create_stage(role_id="ui-designer",
  name="ux_ui") → Stage.role_id / workflow.stage_ids 索引 / DAG 拓扑序
- Runner 执行 (mock uxui executor): build_uxui_executor(UXUIDesignerAgent +
  mock provider) → stage COMPLETED → workflow COMPLETED + ux_ui artifact
  VALIDATED (7 节, producer_role=ui-designer)
- product 输入解析链: stage.input_artifacts 挂 product artifact (VALIDATED) →
  executor 从 context 取 metadata (agent 无绑定 product 也可)
- agent 绑定 product 回退: 无输入 artifact → 构造绑定 product (架构 §3)
- 就绪判定: 输入 product 未 VALIDATED → stage BLOCKED → workflow ACTIVE;
  VALIDATED 后重跑 → COMPLETED (Runner 现有语义零修改)
- product → ux_ui 全链: product 阶段 (pm executor) → 动态接线 product 产物
  → ux_ui 阶段 (uxui executor) → 双 VALIDATED + 消费证明 (prompt 含画像)
- 事件链: created→started→stage_ready→stage_started→stage_completed→completed
  + org.artifact.created/validated; stage_completed payload 带 role_id
- 失败路径: 契约失败 / 无 product / LLM 垃圾输出 → stage FAILED → workflow
  FAILED (org.workflow.failed 带 stage_id 审计)

依赖: 本目录 conftest (wlife/project_id/pm_mock_provider/event_store) + s8_helpers。
"""

from __future__ import annotations

from exec.pm import PMAgent, build_pm_executor
from exec.uxui import UXUI_FIELDS, UXUIDesignerAgent, build_uxui_executor
from org.models import utcnow
from org.projects import ArtifactStatus, StageStatus
from org.workflow import WorkflowRunner, WorkflowStatus

from s8_helpers import (
    event_sequence,
    payload_of,
    product_json,
    product_payload_ok,
    uxui_json,
)


def _build_uxui_workflow(
    wlife,
    project_id,
    *,
    workflow_id: str = "WF-UXUI",
    stage_id: str = "STG-UXUI",
    input_artifacts: list[str] | None = None,
):
    """ux_ui 单阶段 workflow (role_ref=ui-designer, 阶段名 ux_ui)。"""
    workflow = wlife.create_workflow(project_id, "App 流水线", workflow_id=workflow_id)
    stage = wlife.create_stage(
        workflow.id,
        "ui-designer",
        name="ux_ui",
        stage_id=stage_id,
        input_artifacts=input_artifacts,
    )
    return workflow, stage


def _seed_validated_product(
    wlife, stage_id, *, artifact_id: str = "A-PROD-UXUI", payload=None
):
    """预建 VALIDATED product 产物 (ux_ui 阶段输入; 就绪判定前置)。"""
    artifact = wlife.registry.create(
        stage_id,
        "product",
        project_id="P-8",
        producer_role="product-manager",
        metadata=payload or product_payload_ok(),
        artifact_id=artifact_id,
    )
    wlife.registry.mark_generated(artifact.id)
    wlife.registry.validate(artifact.id)
    return artifact


class TestUxUiStageDefinition:
    def test_stage_role_ref_ui_designer(self, wlife, project_id):
        """ux_ui stage: role_id=ui-designer (exec 注册表校验通过, 阶段名 ux_ui)。"""
        workflow, stage = _build_uxui_workflow(wlife, project_id)
        assert stage.role_id == "ui-designer"
        assert stage.name == "ux_ui"
        assert stage.workflow_id == workflow.id

    def test_stage_indexed_in_workflow(self, wlife, project_id):
        """workflow.stage_ids 索引 + DAG 拓扑序 (单阶段可执行)。"""
        _build_uxui_workflow(wlife, project_id)
        current = wlife.get_workflow("WF-UXUI")  # 重新取 — create 返回旧对象
        assert current.stage_ids == ["STG-UXUI"]
        assert wlife.validate_dag("WF-UXUI") == ["STG-UXUI"]


class TestRunnerUxUiStage:
    def test_happy_path_uxui_validated(self, wlife, project_id, pm_mock_provider):
        """Runner 执行: mock uxui executor → stage COMPLETED → workflow
        COMPLETED, ux_ui artifact VALIDATED (producer_role=ui-designer, 7 节)。"""
        provider = pm_mock_provider(uxui_json())
        workflow, stage = _build_uxui_workflow(
            wlife, project_id, input_artifacts=["A-PROD-UXUI"]
        )
        _seed_validated_product(wlife, stage.id)
        runner = WorkflowRunner(
            wlife, executor=build_uxui_executor(UXUIDesignerAgent(provider))
        )
        workflow = runner.run("WF-UXUI")
        assert workflow.status is WorkflowStatus.COMPLETED
        assert wlife.get_stage("STG-UXUI").status is StageStatus.COMPLETED
        uxuis = wlife.registry.query(type_="ux_ui", project_id="P-8")
        assert len(uxuis) == 1
        artifact = uxuis[0]
        assert artifact.status is ArtifactStatus.VALIDATED
        assert artifact.producer_role == "ui-designer"
        assert list(artifact.metadata) == list(UXUI_FIELDS)  # 7 节全字段
        assert "user_persona" in provider.last_request.task_context

    def test_agent_bound_product_fallback(self, wlife, project_id, pm_mock_provider):
        """回退链: 无输入 artifact → 构造绑定 product (架构 §3 stage input
        可无 artifact; 不臆造 — 绑定即显式声明)。"""
        provider = pm_mock_provider(uxui_json())
        _build_uxui_workflow(wlife, project_id)
        runner = WorkflowRunner(
            wlife,
            executor=build_uxui_executor(
                UXUIDesignerAgent(provider, product=product_payload_ok())
            ),
        )
        workflow = runner.run("WF-UXUI")
        assert workflow.status is WorkflowStatus.COMPLETED
        uxuis = wlife.registry.query(type_="ux_ui", project_id="P-8")
        assert len(uxuis) == 1
        assert uxuis[0].status is ArtifactStatus.VALIDATED

    def test_event_chain_and_payload(self, wlife, project_id, pm_mock_provider, event_store):
        """事件链: 全链序 + stage_completed payload (role_id 审计)。"""
        provider = pm_mock_provider(uxui_json())
        workflow, stage = _build_uxui_workflow(
            wlife, project_id, input_artifacts=["A-PROD-UXUI"]
        )
        _seed_validated_product(wlife, stage.id)
        runner = WorkflowRunner(
            wlife, executor=build_uxui_executor(UXUIDesignerAgent(provider))
        )
        runner.run("WF-UXUI")
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
        assert payload["role_id"] == "ui-designer"
        assert payload["stage_id"] == "STG-UXUI"

    def test_blocks_until_product_validated(self, wlife, project_id, pm_mock_provider):
        """就绪判定 (Runner 零修改): 输入 product 仅 CREATED (未 VALIDATED) →
        stage BLOCKED → workflow ACTIVE; VALIDATED 后重跑 → COMPLETED。"""
        provider = pm_mock_provider(uxui_json())
        workflow, stage = _build_uxui_workflow(
            wlife, project_id, input_artifacts=["A-PROD-PEND"]
        )
        wlife.registry.create(
            stage.id,
            "product",
            project_id="P-8",
            producer_role="product-manager",
            metadata=product_payload_ok(),
            artifact_id="A-PROD-PEND",
        )
        runner = WorkflowRunner(
            wlife, executor=build_uxui_executor(UXUIDesignerAgent(provider))
        )
        workflow = runner.run("WF-UXUI")
        assert workflow.status is WorkflowStatus.ACTIVE
        assert wlife.get_stage("STG-UXUI").status is StageStatus.BLOCKED
        assert wlife.registry.query(type_="ux_ui", project_id="P-8") == []
        # 输入就绪 (VALIDATED) → 重跑 → 推进完成
        wlife.registry.mark_generated("A-PROD-PEND")
        wlife.registry.validate("A-PROD-PEND")
        workflow = runner.run("WF-UXUI")
        assert workflow.status is WorkflowStatus.COMPLETED
        assert wlife.get_stage("STG-UXUI").status is StageStatus.COMPLETED
        uxuis = wlife.registry.query(type_="ux_ui", project_id="P-8")
        assert len(uxuis) == 1
        assert uxuis[0].status is ArtifactStatus.VALIDATED

    def test_contract_failure_fails_workflow(self, wlife, project_id, event_store):
        """executor 输出缺 7 节 → ux_ui 契约 INVALID → stage FAILED →
        workflow FAILED (failed 事件带 stage_id)。"""
        def bad_executor(stage, context):  # noqa: ARG001 — executor 契约签名
            return {
                "artifact_type": "ux_ui",
                "ref": "file:///docs/ux_ui.json",
                "metadata": {"prototype": "只有一节"},
            }

        workflow, stage = _build_uxui_workflow(
            wlife, project_id, input_artifacts=["A-PROD-UXUI"]
        )
        _seed_validated_product(wlife, stage.id)
        runner = WorkflowRunner(wlife, executor=bad_executor)
        workflow = runner.run("WF-UXUI")
        assert workflow.status is WorkflowStatus.FAILED
        assert wlife.get_stage("STG-UXUI").status is StageStatus.FAILED
        assert "contract failed" in workflow.failed_reason
        uxuis = wlife.registry.query(type_="ux_ui", project_id="P-8")
        assert len(uxuis) == 1
        assert uxuis[0].status is ArtifactStatus.INVALID
        assert "wireframe" in uxuis[0].invalid_reason
        failed = payload_of(event_store, "org.workflow.failed")
        assert failed["stage_id"] == "STG-UXUI"

    def test_no_product_honest_failure(self, wlife, project_id, pm_mock_provider):
        """无输入 product 且无绑定 product → UXUIDesignerError → workflow
        FAILED (诚实, 不臆造输入)。"""
        provider = pm_mock_provider(uxui_json())
        _build_uxui_workflow(wlife, project_id)
        runner = WorkflowRunner(
            wlife, executor=build_uxui_executor(UXUIDesignerAgent(provider))
        )
        workflow = runner.run("WF-UXUI")
        assert workflow.status is WorkflowStatus.FAILED
        assert wlife.get_stage("STG-UXUI").status is StageStatus.FAILED
        assert "product" in workflow.failed_reason

    def test_bad_llm_output_fails_workflow(self, wlife, project_id, pm_mock_provider):
        """LLM 垃圾输出 (不可解析) → UXUIDesignerError → workflow FAILED
        (响亮拒绝, 不假装生成成功)。"""
        provider = pm_mock_provider("这不是 JSON, 随便一段文字")
        workflow, stage = _build_uxui_workflow(
            wlife, project_id, input_artifacts=["A-PROD-UXUI"]
        )
        _seed_validated_product(wlife, stage.id)
        runner = WorkflowRunner(
            wlife, executor=build_uxui_executor(UXUIDesignerAgent(provider))
        )
        workflow = runner.run("WF-UXUI")
        assert workflow.status is WorkflowStatus.FAILED
        assert wlife.get_stage("STG-UXUI").status is StageStatus.FAILED
        assert "not valid JSON" in workflow.failed_reason


class TestFullChainProductToUxUi:
    def test_full_chain_product_to_uxui(self, wlife, project_id, pm_mock_provider):
        """product → ux_ui 全链: product 阶段 (pm executor) 产出 VALIDATED
        product → 动态接线为 ux_ui 输入 → ux_ui 阶段 (uxui executor) 消费
        product 契约载荷 → ux_ui VALIDATED (Runner 零修改, 事件链完整)。"""
        workflow = wlife.create_workflow(
            project_id, "App 流水线", workflow_id="WF-CHAIN"
        )
        wlife.create_stage(
            workflow.id,
            "product-manager",
            name="product",
            stage_id="STG-CHAIN-P",
        )
        wlife.create_stage(
            workflow.id,
            "ui-designer",
            name="ux_ui",
            stage_id="STG-CHAIN-UX",
            depends_on=["STG-CHAIN-P"],
            input_artifacts=["A-PROD-PENDING"],  # 占位: 未就绪 → BLOCKED
        )
        # 阶段 1: product 阶段执行 (ux_ui 阶段输入占位未 VALIDATED → BLOCKED)
        pm_provider = pm_mock_provider(product_json())
        runner1 = WorkflowRunner(
            wlife,
            executor=build_pm_executor(PMAgent(pm_provider, idea="记账 App")),
        )
        workflow = runner1.run("WF-CHAIN")
        assert workflow.status is WorkflowStatus.ACTIVE
        assert wlife.get_stage("STG-CHAIN-P").status is StageStatus.COMPLETED
        assert wlife.get_stage("STG-CHAIN-UX").status is StageStatus.BLOCKED
        products = wlife.registry.query(type_="product", project_id="P-8")
        assert len(products) == 1
        assert products[0].status is ArtifactStatus.VALIDATED
        # 动态接线: ux_ui 阶段输入 = product 产物 id (同 S7-005 _wire 模式,
        # 数据更新非状态转换; Workflow/Artifact 核心零修改)
        stage = wlife.get_stage("STG-CHAIN-UX")
        wired = stage.model_copy(
            update={
                "input_artifacts": [products[0].id],
                "updated_at": utcnow(),
            }
        )
        wlife.store.save_stage(wired)
        # 阶段 2: ux_ui 阶段执行 (uxui executor, 无绑定 product — 从 context 消费)
        ux_provider = pm_mock_provider(uxui_json())
        runner2 = WorkflowRunner(
            wlife, executor=build_uxui_executor(UXUIDesignerAgent(ux_provider))
        )
        workflow = runner2.run("WF-CHAIN")
        assert workflow.status is WorkflowStatus.COMPLETED
        assert wlife.get_stage("STG-CHAIN-UX").status is StageStatus.COMPLETED
        uxuis = wlife.registry.query(type_="ux_ui", project_id="P-8")
        assert len(uxuis) == 1
        assert uxuis[0].status is ArtifactStatus.VALIDATED
        assert uxuis[0].producer_role == "ui-designer"
        assert list(uxuis[0].metadata) == list(UXUI_FIELDS)
        # 消费证明: uxui prompt 含 product 画像内容 (product → UX 设计驱动)
        assert "25-40 岁上班族" in ux_provider.last_request.task_context
