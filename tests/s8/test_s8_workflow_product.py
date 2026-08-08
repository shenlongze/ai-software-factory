"""tests/s8/test_s8_workflow_product.py — Workflow product stage 接入 (Integration, S8-001)。

覆盖 (任务清单: Workflow 接入测试 — product stage 定义 + Runner 执行 + 事件):
- product stage 定义: WorkflowLifecycle.create_stage(role_id="product-manager",
  name="product") → Stage.role_id / workflow.stage_ids 索引 / DAG 拓扑序
- Runner 执行 (mock pm executor): build_pm_executor(PMAgent + mock provider) →
  stage COMPLETED → workflow COMPLETED + product artifact VALIDATED (7 节)
- idea 输入解析链: stage.input_artifacts 挂 idea artifact (VALIDATED) →
  executor 从 context 取 metadata.idea (PMAgent 无绑定 idea 也可)
- 事件链: created→started→stage_ready→stage_started→stage_completed→completed
  + org.artifact.created/validated; stage_completed payload 带 role_id
- 契约失败: executor 输出缺 7 节 → product INVALID → stage FAILED →
  workflow FAILED (org.workflow.failed 带 stage_id 审计)
- 无 idea 响亮失败: 无输入 idea 且无绑定 idea → ProductManagerError →
  stage FAILED → workflow FAILED (诚实, 不臆造输入)
- LLM 垃圾输出响亮失败: 不可解析 → stage FAILED → workflow FAILED

依赖: 本目录 conftest (wlife/project_id/pm_mock_provider/event_store) + s8_helpers。
"""

from __future__ import annotations

from exec.pm import PRODUCT_FIELDS, PMAgent, build_pm_executor
from org.projects import ArtifactStatus, StageStatus
from org.workflow import WorkflowRunner, WorkflowStatus

from s8_helpers import event_sequence, payload_of, product_json


def _build_product_workflow(
    wlife,
    project_id,
    *,
    workflow_id: str = "WF-PROD",
    stage_id: str = "STG-PROD",
    input_artifacts: list[str] | None = None,
):
    """product 单阶段 workflow (role_ref=product-manager, 阶段名 product)。"""
    workflow = wlife.create_workflow(project_id, "App 流水线", workflow_id=workflow_id)
    stage = wlife.create_stage(
        workflow.id,
        "product-manager",
        name="product",
        stage_id=stage_id,
        input_artifacts=input_artifacts,
    )
    return workflow, stage


class TestProductStageDefinition:
    def test_stage_role_ref_product_manager(self, wlife, project_id):
        """product stage: role_id=product-manager (exec 注册表校验通过, 阶段名 product)。"""
        workflow, stage = _build_product_workflow(wlife, project_id)
        assert stage.role_id == "product-manager"
        assert stage.name == "product"
        assert stage.workflow_id == workflow.id

    def test_stage_indexed_in_workflow(self, wlife, project_id):
        """workflow.stage_ids 索引 + DAG 拓扑序 (单阶段可执行)。"""
        _build_product_workflow(wlife, project_id)
        current = wlife.get_workflow("WF-PROD")  # 重新取 — create 返回旧对象
        assert current.stage_ids == ["STG-PROD"]
        assert wlife.validate_dag("WF-PROD") == ["STG-PROD"]


class TestRunnerProductStage:
    def test_happy_path_product_validated(self, wlife, project_id, pm_mock_provider):
        """Runner 执行: mock pm executor → stage COMPLETED → workflow COMPLETED,
        product artifact VALIDATED (producer_role=product-manager, 7 节)。"""
        provider = pm_mock_provider(product_json())
        _build_product_workflow(wlife, project_id)
        runner = WorkflowRunner(
            wlife, executor=build_pm_executor(PMAgent(provider, idea="记账 App"))
        )
        workflow = runner.run("WF-PROD")
        assert workflow.status is WorkflowStatus.COMPLETED
        assert wlife.get_stage("STG-PROD").status is StageStatus.COMPLETED
        products = wlife.registry.query(type_="product", project_id="P-8")
        assert len(products) == 1
        artifact = products[0]
        assert artifact.status is ArtifactStatus.VALIDATED
        assert artifact.producer_role == "product-manager"
        assert list(artifact.metadata) == list(PRODUCT_FIELDS)  # 7 节全字段
        assert "记账 App" in provider.last_request.task_context

    def test_idea_from_input_artifact(self, wlife, project_id, pm_mock_provider):
        """idea 输入解析链: input_artifacts 挂 idea artifact (VALIDATED) →
        executor 从 context 取 metadata.idea (PMAgent 无绑定 idea 也可)。"""
        provider = pm_mock_provider(product_json())
        workflow, stage = _build_product_workflow(
            wlife, project_id, input_artifacts=["A-IDEA-WF"]
        )
        idea = wlife.registry.create(
            stage.id,
            "idea",
            project_id="P-8",
            metadata={"idea": "来自输入的记账想法"},
            artifact_id="A-IDEA-WF",
        )
        wlife.registry.mark_generated(idea.id)
        wlife.registry.validate(idea.id)
        runner = WorkflowRunner(wlife, executor=build_pm_executor(PMAgent(provider)))
        workflow = runner.run("WF-PROD")
        assert workflow.status is WorkflowStatus.COMPLETED
        assert "来自输入的记账想法" in provider.last_request.task_context
        products = wlife.registry.query(type_="product", project_id="P-8")
        assert len(products) == 1
        assert products[0].status is ArtifactStatus.VALIDATED

    def test_event_chain_and_payload(self, wlife, project_id, pm_mock_provider, event_store):
        """事件链: 全链序 + stage_completed payload (role_id 审计)。"""
        provider = pm_mock_provider(product_json())
        _build_product_workflow(wlife, project_id)
        runner = WorkflowRunner(
            wlife, executor=build_pm_executor(PMAgent(provider, idea="x"))
        )
        runner.run("WF-PROD")
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
        assert payload["role_id"] == "product-manager"
        assert payload["stage_id"] == "STG-PROD"

    def test_contract_failure_fails_workflow(self, wlife, project_id, event_store):
        """executor 输出缺 7 节 → product 契约 INVALID → stage FAILED →
        workflow FAILED (failed 事件带 stage_id)。"""
        def bad_executor(stage, context):  # noqa: ARG001 — executor 契约签名
            return {
                "artifact_type": "product",
                "ref": "file:///docs/product.json",
                "metadata": {"market_analysis": "只有一节"},
            }

        _build_product_workflow(wlife, project_id)
        runner = WorkflowRunner(wlife, executor=bad_executor)
        workflow = runner.run("WF-PROD")
        assert workflow.status is WorkflowStatus.FAILED
        assert wlife.get_stage("STG-PROD").status is StageStatus.FAILED
        assert "contract failed" in workflow.failed_reason
        products = wlife.registry.query(type_="product", project_id="P-8")
        assert len(products) == 1
        assert products[0].status is ArtifactStatus.INVALID
        assert "user_persona" in products[0].invalid_reason
        failed = payload_of(event_store, "org.workflow.failed")
        assert failed["stage_id"] == "STG-PROD"

    def test_no_idea_honest_failure(self, wlife, project_id, pm_mock_provider):
        """无输入 idea 且无绑定 idea → ProductManagerError → workflow FAILED
        (诚实, 不臆造输入)。"""
        provider = pm_mock_provider(product_json())
        _build_product_workflow(wlife, project_id)
        runner = WorkflowRunner(wlife, executor=build_pm_executor(PMAgent(provider)))
        workflow = runner.run("WF-PROD")
        assert workflow.status is WorkflowStatus.FAILED
        assert wlife.get_stage("STG-PROD").status is StageStatus.FAILED
        assert "idea" in workflow.failed_reason

    def test_bad_llm_output_fails_workflow(self, wlife, project_id, pm_mock_provider):
        """LLM 垃圾输出 (不可解析) → ProductManagerError → workflow FAILED
        (响亮拒绝, 不假装生成成功)。"""
        provider = pm_mock_provider("这不是 JSON, 随便一段文字")
        _build_product_workflow(wlife, project_id)
        runner = WorkflowRunner(
            wlife, executor=build_pm_executor(PMAgent(provider, idea="x"))
        )
        workflow = runner.run("WF-PROD")
        assert workflow.status is WorkflowStatus.FAILED
        assert wlife.get_stage("STG-PROD").status is StageStatus.FAILED
        assert "not valid JSON" in workflow.failed_reason
