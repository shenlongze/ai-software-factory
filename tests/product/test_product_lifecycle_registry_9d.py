"""tests/product/test_product_lifecycle_registry_9d.py — Stage Registry + Template (Phase 9d, ADR-0029)。

覆盖: ProductStageRegistry 内置 software_project 注册 (查询/列表/多类型支持),
自定义模板注册 (多 lifecycle 类型: automation 预留), 同名冲突防覆盖,
require 未注册 → ProductNotFoundError; ProductWorkflowTemplate 声明式解析
(stage_names/stage 查询/to_dict), check_structure 结构校验 (无阶段 / 缺
artifact_type / approval 缺 gate / decision/task 缺 decision_type); 实例快照
隔离 (模板变更不影响已启动生命周期); 引擎按自定义模板启动。
"""

from __future__ import annotations

import pytest

from product.lifecycle import (
    BUILTIN_TEMPLATES,
    ProductStage,
    ProductStageRegistry,
    ProductWorkflowTemplate,
    SOFTWARE_PROJECT_STAGES,
)
from product.models import StageKind
from product.service import ProductError, ProductNotFoundError

from product_helpers import seed_idea


def _make_engine(store, service=None, **kw):
    from product.lifecycle import ProductLifecycleEngine

    return ProductLifecycleEngine(store, service, **kw)


def _custom_template(name: str = "automation") -> ProductWorkflowTemplate:
    """自定义生命周期模板 (多 lifecycle 类型: automation 预留, 阶段名不与
    software_project 硬编码集重叠)。"""
    return ProductWorkflowTemplate(
        name=name,
        description="自动化流水线生命周期",
        stages=[
            ProductStage(name="spec", kind="artifact_generation", artifact_type="spec"),
            ProductStage(name="approval", kind="approval", gate="spec"),
            ProductStage(name="task", kind="task", decision_type="task_plan"),
        ],
    )


class TestBuiltinTemplate:
    def test_software_project_stages_are_declarative(self):
        assert [s["name"] for s in SOFTWARE_PROJECT_STAGES] == [
            "idea", "research", "prd", "approval", "ui", "approval",
            "architecture", "task",
        ]
        # 阶段类型分类 (StageKind 驱动引擎行为)
        assert [s["kind"] for s in SOFTWARE_PROJECT_STAGES] == [
            "artifact_generation", "artifact_generation", "artifact_generation",
            "approval", "artifact_generation", "approval", "decision", "task",
        ]

    def test_builtin_templates_registered(self):
        reg = ProductStageRegistry()
        assert reg.supports("software_project")
        assert "software_project" in BUILTIN_TEMPLATES
        assert reg.types() == ["software_project"]

    def test_get_returns_template(self):
        reg = ProductStageRegistry()
        tpl = reg.get("software_project")
        assert tpl is not None
        assert tpl.name == "software_project"
        assert len(tpl.stages) == 8

    def test_get_unknown_returns_none(self):
        assert ProductStageRegistry().get("nope") is None

    def test_require_unknown_raises_not_found(self):
        with pytest.raises(ProductNotFoundError, match="no lifecycle template"):
            ProductStageRegistry().require("nope")

    def test_list_and_supports(self):
        reg = ProductStageRegistry()
        assert [t.name for t in reg.list()] == ["software_project"]
        assert reg.supports("software_project")
        assert not reg.supports("automation")

    def test_template_stage_names_and_lookup(self):
        tpl = ProductStageRegistry().get("software_project")
        assert tpl.stage_names() == [
            "idea", "research", "prd", "approval", "ui", "approval",
            "architecture", "task",
        ]
        assert tpl.stage("approval").gate == "prd"  # 按名取定义 (重复名取首个)
        assert tpl.stage("research").artifact_type == "research"
        assert tpl.stage("nope") is None

    def test_template_to_dict_roundtrip(self):
        tpl = ProductStageRegistry().get("software_project")
        data = tpl.to_dict()
        assert data["name"] == "software_project"
        assert data["stages"][0]["name"] == "idea"
        rebuilt = ProductWorkflowTemplate(**data)
        assert rebuilt.stage_names() == tpl.stage_names()


class TestTemplateStructureValidation:
    def test_empty_template_rejected(self):
        with pytest.raises(ProductError, match="has no stages"):
            ProductWorkflowTemplate(name="empty").check_structure()

    def test_artifact_generation_needs_artifact_type(self):
        tpl = ProductWorkflowTemplate(name="bad", stages=[ProductStage(name="x")])
        with pytest.raises(ProductError, match="needs artifact_type"):
            tpl.check_structure()

    def test_decision_needs_artifact_type(self):
        tpl = ProductWorkflowTemplate(
            name="bad",
            stages=[ProductStage(name="d", kind=StageKind.DECISION.value)],
        )
        with pytest.raises(ProductError, match="needs artifact_type"):
            tpl.check_structure()

    def test_approval_needs_gate(self):
        tpl = ProductWorkflowTemplate(
            name="bad", stages=[ProductStage(name="a", kind=StageKind.APPROVAL.value)],
        )
        with pytest.raises(ProductError, match="needs gate"):
            tpl.check_structure()

    def test_decision_needs_decision_type(self):
        tpl = ProductWorkflowTemplate(
            name="bad",
            stages=[ProductStage(name="d", kind=StageKind.DECISION.value, artifact_type="arch")],
        )
        with pytest.raises(ProductError, match="needs decision_type"):
            tpl.check_structure()

    def test_task_needs_decision_type(self):
        tpl = ProductWorkflowTemplate(
            name="bad",
            stages=[ProductStage(name="t", kind=StageKind.TASK.value)],
        )
        with pytest.raises(ProductError, match="needs decision_type"):
            tpl.check_structure()

    def test_register_validates_structure(self):
        reg = ProductStageRegistry()
        with pytest.raises(ProductError, match="needs gate"):
            reg.register(ProductWorkflowTemplate(
                name="broken", stages=[ProductStage(name="a", kind="approval")],
            ))
        assert not reg.supports("broken")  # 校验失败不落库


class TestMultiTypeRegistry:
    def test_register_custom_template(self):
        reg = ProductStageRegistry()
        reg.register(_custom_template())
        assert reg.supports("automation")
        assert reg.types() == ["software_project", "automation"]
        assert reg.get("automation").stage_names() == ["spec", "approval", "task"]

    def test_duplicate_register_rejected(self):
        reg = ProductStageRegistry()
        with pytest.raises(ProductError, match="already registered"):
            reg.register(reg.get("software_project"))

    def test_constructor_registers_extra_templates(self):
        reg = ProductStageRegistry(templates=[_custom_template("business")])
        assert reg.supports("business")
        assert reg.supports("software_project")  # 内置不丢

    def test_engine_starts_custom_template(self, store, service):
        engine = _make_engine(store, service)
        engine._registry.register(_custom_template())  # 装配点注册 (多生命周期类型)
        idea = seed_idea(service, "自动化")
        lc = engine.start_lifecycle(idea.id, template="automation")
        assert lc.template_name == "automation"
        assert lc.current_stage.name == "spec"
        assert lc.current_stage.kind == StageKind.ARTIFACT_GENERATION.value
        assert lc.status == "running"

    def test_engine_start_unknown_template_raises(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        with pytest.raises(ProductNotFoundError, match="no lifecycle template"):
            engine.start_lifecycle(idea.id, template="nope")

    def test_engine_templates_lists_all(self, store, service):
        engine = _make_engine(store, service)
        engine._registry.register(_custom_template())
        names = [t["name"] for t in engine.templates()]
        assert names == ["software_project", "automation"]


class TestTemplateInstanceIsolation:
    def test_running_instance_snapshots_template(self, store, service):
        """实例阶段是模板快照: 启动后改模板不影响已启动生命周期 (自洽)。"""
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        lc = engine.start_lifecycle(idea.id)
        tpl = engine._registry.get("software_project")
        original = [s.name for s in lc.stages]
        tpl.stages.pop()  # 启动后删掉模板最后一个阶段 (task)
        after = engine._require_lifecycle(idea.id)
        assert [s.name for s in after.stages] == original  # 实例阶段链不变

    def test_run_snapshot_copies_stage_fields(self, store, service):
        engine = _make_engine(store, service)
        idea = seed_idea(service)
        lc = engine.start_lifecycle(idea.id)
        run = lc.stages[0]
        tpl_stage = engine._registry.get("software_project").stages[0]
        tpl_stage.artifact_type = "mutated"
        assert run.artifact_type == "product_idea"  # 值复制, 非引用
