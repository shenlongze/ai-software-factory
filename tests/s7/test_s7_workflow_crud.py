"""tests/s7/test_s7_workflow_crud.py — Workflow/Stage CRUD + 依赖校验 (Unit, S7-003)。

覆盖:
- Workflow: create (DRAFT/自定义 id/重复拒绝/项目引用完整) / get / list (项目过滤)
  / count
- Stage: create (默认值/order 自增/显式 order/依赖校验/重复拒绝/角色校验) /
  list (order+id 确定性序) / get
- workflow.stage_ids 索引同步 (权威读取仍为 store 查询)
- set_stage_dependencies: 替换依赖 (合法); 未定义依赖拒绝 (WorkflowDependencyError)

依赖: 本目录 conftest (project_store + logger fixtures)。
"""

from __future__ import annotations

import pytest

from org.lifecycle import DuplicateError, NotFoundError
from org.projects import StageStatus
from org.workflow import (
    WorkflowDependencyError,
    WorkflowLifecycle,
    WorkflowStatus,
)


@pytest.fixture
def wlife(project_store, logger) -> WorkflowLifecycle:
    return WorkflowLifecycle(project_store, logger=logger)


@pytest.fixture
def seeded(wlife) -> str:
    """项目 + 工作流 (返回 workflow id)。"""
    from org.projects import ProjectLifecycle

    ProjectLifecycle(wlife.store).create_project("Build App", project_id="P-1")
    return wlife.create_workflow("P-1", "Ship v1", workflow_id="WF-1").id


class TestWorkflowCreate:
    def test_create_defaults_to_draft(self, wlife, seeded):
        wf = wlife.get_workflow("WF-1")
        assert wf.id == "WF-1"
        assert wf.project_id == "P-1"
        assert wf.name == "Ship v1"
        assert wf.status is WorkflowStatus.DRAFT
        assert wf.stage_ids == []
        assert wlife.count_workflows() == 1

    def test_create_auto_id(self, wlife, seeded):
        wf = wlife.create_workflow("P-1", "Second")
        assert wf.id.startswith("WF-")
        assert wf.id != "WF-1"

    def test_create_duplicate_rejected(self, wlife, seeded):
        with pytest.raises(DuplicateError, match="workflow already exists"):
            wlife.create_workflow("P-1", "Dup", workflow_id="WF-1")

    def test_create_missing_project_rejected(self, wlife):
        with pytest.raises(NotFoundError, match="project not found"):
            wlife.create_workflow("P-999", "Orphan", workflow_id="WF-9")

    def test_created_persisted(self, wlife, seeded, project_store):
        """workflows.json 独立文件持久化 (与 ProjectStore 同目录)。"""
        reloaded = WorkflowLifecycle(project_store)
        assert reloaded.get_workflow("WF-1").name == "Ship v1"


class TestWorkflowRead:
    def test_get_not_found(self, wlife):
        with pytest.raises(NotFoundError, match="workflow not found"):
            wlife.get_workflow("WF-999")

    def test_list_all_and_by_project(self, wlife, seeded):
        wlife.create_workflow("P-1", "W2", workflow_id="WF-2")
        assert [w.id for w in wlife.list_workflows()] == ["WF-1", "WF-2"]
        assert [w.id for w in wlife.list_workflows(project_id="P-1")] == ["WF-1", "WF-2"]
        assert wlife.list_workflows(project_id="P-2") == []

    def test_count(self, wlife, seeded):
        assert wlife.count_workflows() == 1
        wlife.create_workflow("P-1", "W2")
        assert wlife.count_workflows() == 2


class TestStageCreate:
    def test_create_defaults(self, wlife, seeded):
        stage = wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        assert stage.id == "STG-1"
        assert stage.workflow_id == "WF-1"
        assert stage.role_id == "developer"
        assert stage.name == ""
        assert stage.order == 1
        assert stage.status is StageStatus.PENDING
        assert stage.depends_on == []
        assert stage.input_artifacts == []
        assert stage.output_artifacts == []
        # workflow.stage_ids 索引同步
        assert wlife.get_workflow("WF-1").stage_ids == ["STG-1"]

    def test_create_order_auto_increment(self, wlife, seeded):
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        stage2 = wlife.create_stage("WF-1", "tester", stage_id="STG-2")
        assert stage2.order == 2

    def test_create_explicit_order(self, wlife, seeded):
        stage = wlife.create_stage("WF-1", "developer", order=9, stage_id="STG-1")
        assert stage.order == 9

    def test_create_with_dependencies(self, wlife, seeded):
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        stage2 = wlife.create_stage(
            "WF-1", "tester", depends_on=["STG-1"], stage_id="STG-2"
        )
        assert stage2.depends_on == ["STG-1"]

    def test_create_undefined_dependency_rejected(self, wlife, seeded):
        with pytest.raises(WorkflowDependencyError, match="undefined stage"):
            wlife.create_stage("WF-1", "developer", depends_on=["STG-999"])

    def test_create_cross_workflow_dependency_rejected(self, wlife, seeded):
        """跨 workflow 依赖拒绝: dep 属另一 workflow 的 stage 视为未定义。"""
        wlife.create_workflow("P-1", "W2", workflow_id="WF-2")
        wlife.create_stage("WF-2", "developer", stage_id="STG-9")
        with pytest.raises(WorkflowDependencyError, match="undefined stage"):
            wlife.create_stage("WF-1", "developer", depends_on=["STG-9"], stage_id="STG-1")

    def test_create_missing_workflow_rejected(self, wlife):
        with pytest.raises(NotFoundError, match="workflow not found"):
            wlife.create_stage("WF-999", "developer")

    def test_create_duplicate_stage_rejected(self, wlife, seeded):
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        with pytest.raises(DuplicateError, match="stage already exists"):
            wlife.create_stage("WF-1", "developer", stage_id="STG-1")

    def test_create_unknown_role_rejected(self, wlife, seeded):
        with pytest.raises(ValueError, match="unknown role"):
            wlife.create_stage("WF-1", "bogus-role")

    def test_stage_index_kept_in_sync(self, wlife, seeded):
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        wlife.create_stage("WF-1", "tester", stage_id="STG-2")
        assert wlife.get_workflow("WF-1").stage_ids == ["STG-1", "STG-2"]


class TestStageRead:
    def test_list_ordered_by_order_then_id(self, wlife, seeded):
        wlife.create_stage("WF-1", "tester", order=1, stage_id="STG-2")
        wlife.create_stage("WF-1", "developer", order=1, stage_id="STG-1")
        wlife.create_stage("WF-1", "architect", order=0, stage_id="STG-0")
        assert [s.id for s in wlife.list_stages("WF-1")] == ["STG-0", "STG-1", "STG-2"]

    def test_get_stage_not_found(self, wlife):
        with pytest.raises(NotFoundError, match="stage not found"):
            wlife.get_stage("STG-999")

    def test_get_stage_roundtrip(self, wlife, seeded):
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        assert wlife.get_stage("STG-1").role_id == "developer"


class TestSetDependencies:
    def test_replace_dependencies(self, wlife, seeded):
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        wlife.create_stage("WF-1", "tester", stage_id="STG-2")
        updated = wlife.set_stage_dependencies("STG-2", ["STG-1"])
        assert updated.depends_on == ["STG-1"]
        assert wlife.get_stage("STG-2").depends_on == ["STG-1"]

    def test_replace_clears_old(self, wlife, seeded):
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        wlife.create_stage("WF-1", "tester", stage_id="STG-2")
        wlife.set_stage_dependencies("STG-2", ["STG-1"])
        assert wlife.set_stage_dependencies("STG-2", []).depends_on == []

    def test_undefined_dependency_rejected(self, wlife, seeded):
        wlife.create_stage("WF-1", "developer", stage_id="STG-1")
        with pytest.raises(WorkflowDependencyError, match="undefined stage"):
            wlife.set_stage_dependencies("STG-1", ["STG-999"])
