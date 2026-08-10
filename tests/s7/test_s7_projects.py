"""tests/s7/test_s7_projects.py — S7-001 统一生命周期模型 (Unit, ADR-0039)。

覆盖 (任务清单: Project 生命周期状态机/Sprint/Stage/Artifact CRUD/
ProjectTaskLink/事件):
- Project CRUD: create/get/list + 唯一性 + org.project.created 事件
- 生命周期状态机: idea→active→maintained→archived 单向流转;
  非法流转 ValueError; archived 终态; 同状态幂等 (不重复发事件);
  目标值大小写不敏感; 状态枚举宽容解析
- Sprint: create (项目必须存在) + org.sprint.created; add_task_to_sprint
  (任务须先 link 该项目 — 项目隔离铁律)
- Stage: create (role_id 经 exec 注册表校验 — 未注册 → ValueError) +
  org.stage.created; list_stages_by_workflow 按 order 排序
- Artifact: create (stage 必须存在) + org.artifact.created; type 宽容解析
  (大小写不敏感); 非法 type → ValueError
- ProjectTaskLink: link_task 重复拒绝 + list_project_tasks
- 事件 payload 契约: 从 payload 可重建生命周期关键字段

依赖: 本目录 conftest 已挂 factory-core + factory-org + factory-exec
(Stage.role_id 校验依赖 exec 注册表真实可用)。
"""

from __future__ import annotations

import pytest

from org.lifecycle import DuplicateError, NotFoundError
from org.projects import (
    ArtifactType,
    PROJECT_TRANSITIONS,
    ProjectLifecycle,
    ProjectState,
    StageStatus,
)
from org.store import OrgStore

from s7_helpers import (
    event_sequence,
    last_event,
    make_project,
    make_sprint,
    payload_of,
)


@pytest.fixture
def lifecycle(project_store, logger) -> ProjectLifecycle:
    return ProjectLifecycle(project_store, logger=logger)


@pytest.fixture
def no_logger(project_store) -> ProjectLifecycle:
    """logger=None: 事件全静默 (同既有 org 模式)。"""
    return ProjectLifecycle(project_store, logger=None)


# ------------------------------------------------------------------ Project


class TestProjectCrud:
    def test_create_defaults_to_idea(self, lifecycle, project_store):
        p = lifecycle.create_project("Build App", project_id="P-1")
        assert p.id == "P-1"
        assert p.name == "Build App"
        assert p.lifecycle == ProjectState.IDEA
        assert not p.is_archived
        assert project_store.get_project("P-1") is not None

    def test_create_with_user_and_goal(self, lifecycle):
        p = lifecycle.create_project(
            "Build App", user_id="U-1", goal="ship v1", project_id="P-1"
        )
        assert p.user_id == "U-1"
        assert p.goal == "ship v1"

    def test_duplicate_project_id_raises(self, lifecycle):
        lifecycle.create_project("A", project_id="P-1")
        with pytest.raises(DuplicateError, match="project already exists"):
            lifecycle.create_project("B", project_id="P-1")

    def test_get_not_found(self, lifecycle):
        with pytest.raises(NotFoundError, match="project not found"):
            lifecycle.get_project("P-999")

    def test_list_projects(self, lifecycle):
        lifecycle.create_project("A", project_id="P-1")
        lifecycle.create_project("B", project_id="P-2")
        assert [p.id for p in lifecycle.list_projects()] == ["P-1", "P-2"]

    def test_project_created_event_payload(self, lifecycle, event_store):
        lifecycle.create_project(
            "Build App", user_id="U-1", goal="ship", project_id="P-1"
        )
        payload = payload_of(event_store, "org.project.created")
        assert payload["project_id"] == "P-1"
        assert payload["name"] == "Build App"
        assert payload["user_id"] == "U-1"
        assert payload["goal"] == "ship"
        assert payload["lifecycle"] == "idea"

    def test_logger_none_silent(self, no_logger, event_store):
        """logger=None → 零事件 (全静默, 同既有 org 模式)。"""
        no_logger.create_project("A", project_id="P-1")
        assert event_sequence(event_store) == []


class TestProjectStateMachine:
    def test_transition_table_single_way_acyclic(self):
        """流转表单向无环 (S10-009 扩展: 新生命周期链 + 旧值兼容保留)。"""
        # 新状态全链 (S10-009): draft→discovery→...→maintain→archived
        assert PROJECT_TRANSITIONS["draft"] == ("discovery", "archived")
        assert PROJECT_TRANSITIONS["discovery"] == ("product_defined", "archived")
        assert PROJECT_TRANSITIONS["product_defined"] == ("design", "archived")
        assert PROJECT_TRANSITIONS["design"] == ("architecture", "archived")
        assert PROJECT_TRANSITIONS["architecture"] == ("confirmed", "archived")
        assert PROJECT_TRANSITIONS["confirmed"] == ("development", "archived")
        assert PROJECT_TRANSITIONS["development"] == ("release", "archived")
        assert PROJECT_TRANSITIONS["release"] == ("maintain", "archived")
        assert PROJECT_TRANSITIONS["maintain"] == ("archived",)
        # 旧值兼容保留 (S7): idea→active→maintained→archived
        assert PROJECT_TRANSITIONS["idea"] == ("active", "archived")
        assert PROJECT_TRANSITIONS["active"] == ("maintained", "archived")
        assert PROJECT_TRANSITIONS["maintained"] == ("archived",)
        assert PROJECT_TRANSITIONS["archived"] == ()
        # 无环校验: 任一状态经任意步不回到自身
        for start in PROJECT_TRANSITIONS:
            seen: set[str] = set()
            current = start
            while current in PROJECT_TRANSITIONS and PROJECT_TRANSITIONS[current]:
                next_states = PROJECT_TRANSITIONS[current]
                assert next_states, f"{current} 应可继续或终态"
                # 单向: 后继不能再回到前驱链
                current = next_states[0]
                assert current not in seen, f"环检测: {start} → ... → {current}"
                seen.add(current)

    def test_idea_to_active(self, lifecycle):
        p = lifecycle.create_project("A", project_id="P-1")
        updated = lifecycle.transition_lifecycle("P-1", "active")
        assert updated.lifecycle == ProjectState.ACTIVE
        assert updated.updated_at >= p.updated_at

    def test_full_chain_to_archived(self, lifecycle):
        lifecycle.create_project("A", project_id="P-1")
        for state in ("active", "maintained", "archived"):
            updated = lifecycle.transition_lifecycle("P-1", state)
            assert updated.lifecycle.value == state
        assert lifecycle.get_project("P-1").is_archived

    def test_idea_can_archive_directly(self, lifecycle):
        lifecycle.create_project("A", project_id="P-1")
        updated = lifecycle.transition_lifecycle("P-1", "archived")
        assert updated.is_archived

    def test_invalid_transition_raises(self, lifecycle):
        """idea → maintained 非法 (须经 active) → ValueError 响亮。"""
        lifecycle.create_project("A", project_id="P-1")
        with pytest.raises(ValueError, match="invalid project lifecycle"):
            lifecycle.transition_lifecycle("P-1", "maintained")

    def test_archived_is_terminal(self, lifecycle):
        lifecycle.create_project("A", project_id="P-1")
        lifecycle.transition_lifecycle("P-1", "archived")
        with pytest.raises(ValueError, match="invalid project lifecycle"):
            lifecycle.transition_lifecycle("P-1", "active")

    def test_same_state_idempotent_no_event(self, lifecycle, event_store):
        """同状态流转幂等: 不重复发 lifecycle_changed 事件。"""
        lifecycle.create_project("A", project_id="P-1")
        lifecycle.transition_lifecycle("P-1", "active")
        lifecycle.transition_lifecycle("P-1", "active")  # 幂等
        count = sum(
            1
            for e in event_store.query()
            if e.type.value == "org.project.lifecycle_changed"
        )
        assert count == 1

    def test_target_case_insensitive(self, lifecycle):
        lifecycle.create_project("A", project_id="P-1")
        updated = lifecycle.transition_lifecycle("P-1", "ACTIVE")
        assert updated.lifecycle == ProjectState.ACTIVE

    def test_state_enum_parse_tolerant(self):
        assert ProjectState.parse("Active") == ProjectState.ACTIVE
        assert ProjectState.parse(ProjectState.IDEA) == ProjectState.IDEA
        with pytest.raises(ValueError, match="invalid project lifecycle"):
            ProjectState.parse("bogus")

    def test_lifecycle_changed_event_payload(self, lifecycle, event_store):
        lifecycle.create_project("A", project_id="P-1")
        lifecycle.transition_lifecycle("P-1", "active")
        payload = payload_of(event_store, "org.project.lifecycle_changed")
        assert payload["project_id"] == "P-1"
        assert payload["from_lifecycle"] == "idea"
        assert payload["to_lifecycle"] == "active"


# ------------------------------------------------------------------ Sprint


class TestSprint:
    def test_create_sprint_requires_project(self, lifecycle):
        with pytest.raises(NotFoundError, match="project not found"):
            lifecycle.create_sprint("P-999", "Sprint 1")

    def test_create_sprint(self, lifecycle, project_store):
        lifecycle.create_project("A", project_id="P-1")
        s = lifecycle.create_sprint("P-1", "Sprint 1", sprint_id="S-1")
        assert s.id == "S-1"
        assert s.project_id == "P-1"
        assert s.tasks == []
        assert project_store.get_sprint("S-1") is not None

    def test_duplicate_sprint_raises(self, lifecycle):
        lifecycle.create_project("A", project_id="P-1")
        lifecycle.create_sprint("P-1", "S1", sprint_id="S-1")
        with pytest.raises(DuplicateError, match="sprint already exists"):
            lifecycle.create_sprint("P-1", "S2", sprint_id="S-1")

    def test_sprint_created_event_payload(self, lifecycle, event_store):
        lifecycle.create_project("A", project_id="P-1")
        lifecycle.create_sprint("P-1", "Sprint 1", sprint_id="S-1")
        payload = payload_of(event_store, "org.sprint.created")
        assert payload["sprint_id"] == "S-1"
        assert payload["project_id"] == "P-1"
        assert payload["name"] == "Sprint 1"

    def test_add_task_to_sprint_requires_link_first(self, lifecycle):
        """任务须先 link 该项目, 否则 NotFoundError (项目隔离铁律)。"""
        lifecycle.create_project("A", project_id="P-1")
        lifecycle.create_sprint("P-1", "S1", sprint_id="S-1")
        with pytest.raises(NotFoundError, match="not linked to project"):
            lifecycle.add_task_to_sprint("S-1", "T-1")

    def test_add_task_to_sprint_after_link(self, lifecycle, project_store):
        lifecycle.create_project("A", project_id="P-1")
        lifecycle.link_task("P-1", "T-1")
        lifecycle.create_sprint("P-1", "S1", sprint_id="S-1")
        s = lifecycle.add_task_to_sprint("S-1", "T-1")
        assert s.tasks == ["T-1"]
        assert project_store.get_sprint("S-1").tasks == ["T-1"]

    def test_duplicate_task_in_sprint_raises(self, lifecycle):
        lifecycle.create_project("A", project_id="P-1")
        lifecycle.link_task("P-1", "T-1")
        lifecycle.create_sprint("P-1", "S1", sprint_id="S-1")
        lifecycle.add_task_to_sprint("S-1", "T-1")
        with pytest.raises(DuplicateError, match="already in sprint"):
            lifecycle.add_task_to_sprint("S-1", "T-1")

    def test_cross_project_task_blocked(self, lifecycle):
        """T-1 已关联 P-1; 加入 P-2 的 sprint → 拒绝 (项目隔离)。"""
        lifecycle.create_project("A", project_id="P-1")
        lifecycle.create_project("B", project_id="P-2")
        lifecycle.link_task("P-1", "T-1")
        lifecycle.create_sprint("P-2", "S2", sprint_id="S-2")
        with pytest.raises(NotFoundError, match="not linked to project"):
            lifecycle.add_task_to_sprint("S-2", "T-1")

    def test_sprint_task_added_event_payload(self, lifecycle, event_store):
        lifecycle.create_project("A", project_id="P-1")
        lifecycle.link_task("P-1", "T-1")
        lifecycle.create_sprint("P-1", "S1", sprint_id="S-1")
        lifecycle.add_task_to_sprint("S-1", "T-1")
        payload = payload_of(event_store, "org.sprint.task_added")
        assert payload["sprint_id"] == "S-1"
        assert payload["project_id"] == "P-1"
        assert payload["task_id"] == "T-1"

    def test_list_sprints_by_project(self, lifecycle):
        lifecycle.create_project("A", project_id="P-1")
        lifecycle.create_sprint("P-1", "S1", sprint_id="S-1")
        lifecycle.create_sprint("P-1", "S2", sprint_id="S-2")
        assert [s.id for s in lifecycle.store.list_sprints_by_project("P-1")] == [
            "S-1", "S-2",
        ]


# ------------------------------------------------------------------ Stage


class TestStage:
    def test_create_stage_valid_role(self, lifecycle, project_store):
        s = lifecycle.create_stage(
            "WF-1", "developer", order=1, stage_id="STG-1"
        )
        assert s.id == "STG-1"
        assert s.workflow_id == "WF-1"
        assert s.role_id == "developer"
        assert s.status == StageStatus.PENDING
        assert project_store.get_stage("STG-1") is not None

    def test_create_stage_unknown_role_raises(self, lifecycle):
        """role_id 未注册 → ValueError (拼写错误立即暴露, 单一事实源)。"""
        with pytest.raises(ValueError, match="unknown role"):
            lifecycle.create_stage("WF-1", "develoepr", stage_id="STG-1")

    def test_create_stage_alias_role_resolved(self, lifecycle):
        """role_id 经 exec 注册表校验: 别名不可用 (须注册表 role_id)。"""
        with pytest.raises(ValueError, match="unknown role"):
            lifecycle.create_stage("WF-1", "dev", stage_id="STG-1")

    def test_duplicate_stage_raises(self, lifecycle):
        lifecycle.create_stage("WF-1", "developer", stage_id="STG-1")
        with pytest.raises(DuplicateError, match="stage already exists"):
            lifecycle.create_stage("WF-1", "tester", stage_id="STG-1")

    def test_stage_created_event_payload(self, lifecycle, event_store):
        lifecycle.create_stage("WF-1", "developer", order=2, stage_id="STG-1")
        payload = payload_of(event_store, "org.stage.created")
        assert payload["stage_id"] == "STG-1"
        assert payload["workflow_id"] == "WF-1"
        assert payload["role_id"] == "developer"
        assert payload["order"] == 2

    def test_list_stages_sorted_by_order(self, lifecycle):
        lifecycle.create_stage("WF-1", "product-manager", order=1, stage_id="STG-1")
        lifecycle.create_stage("WF-1", "tester", order=3, stage_id="STG-3")
        lifecycle.create_stage("WF-1", "developer", order=2, stage_id="STG-2")
        assert [s.id for s in lifecycle.list_stages_by_workflow("WF-1")] == [
            "STG-1", "STG-2", "STG-3",
        ]


# ------------------------------------------------------------------ Artifact


class TestArtifact:
    def test_create_artifact(self, lifecycle, project_store):
        lifecycle.create_stage("WF-1", "developer", stage_id="STG-1")
        a = lifecycle.create_artifact(
            "STG-1", "code", ref="file:///x", artifact_id="A-1"
        )
        assert a.id == "A-1"
        assert a.stage_id == "STG-1"
        assert a.type == ArtifactType.CODE
        assert project_store.get_artifact("A-1") is not None

    def test_create_artifact_requires_stage(self, lifecycle):
        with pytest.raises(NotFoundError, match="stage not found"):
            lifecycle.create_artifact("STG-999", "prd")

    def test_type_case_insensitive(self, lifecycle):
        lifecycle.create_stage("WF-1", "developer", stage_id="STG-1")
        a = lifecycle.create_artifact("STG-1", "PRD", artifact_id="A-1")
        assert a.type == ArtifactType.PRD

    def test_invalid_type_raises(self, lifecycle):
        lifecycle.create_stage("WF-1", "developer", stage_id="STG-1")
        with pytest.raises(ValueError, match="invalid artifact type"):
            lifecycle.create_artifact("STG-1", "bogus")

    def test_artifact_created_event_payload(self, lifecycle, event_store):
        lifecycle.create_stage("WF-1", "developer", stage_id="STG-1")
        lifecycle.create_artifact("STG-1", "prd", ref="ref://req", artifact_id="A-1")
        payload = payload_of(event_store, "org.artifact.created")
        assert payload["artifact_id"] == "A-1"
        assert payload["stage_id"] == "STG-1"
        assert payload["type"] == "prd"
        assert payload["ref"] == "ref://req"

    def test_list_artifacts_by_stage(self, lifecycle):
        lifecycle.create_stage("WF-1", "developer", stage_id="STG-1")
        lifecycle.create_artifact("STG-1", "prd", artifact_id="A-1")
        lifecycle.create_artifact("STG-1", "design", artifact_id="A-2")
        assert [a.id for a in lifecycle.list_artifacts_by_stage("STG-1")] == [
            "A-1", "A-2",
        ]


# ------------------------------------------------------------------ ProjectTaskLink


class TestProjectTaskLink:
    def test_link_task(self, lifecycle, project_store):
        lifecycle.create_project("A", project_id="P-1")
        link = lifecycle.link_task("P-1", "T-1", link_id="PTL-1")
        assert link.id == "PTL-1"
        assert link.project_id == "P-1"
        assert link.task_id == "T-1"
        assert project_store.get_task_link("PTL-1") is not None

    def test_link_requires_project(self, lifecycle):
        with pytest.raises(NotFoundError, match="project not found"):
            lifecycle.link_task("P-999", "T-1")

    def test_duplicate_task_link_raises(self, lifecycle):
        lifecycle.create_project("A", project_id="P-1")
        lifecycle.link_task("P-1", "T-1")
        with pytest.raises(DuplicateError, match="already linked to project"):
            lifecycle.link_task("P-1", "T-1")

    def test_task_linked_event_payload(self, lifecycle, event_store):
        lifecycle.create_project("A", project_id="P-1")
        lifecycle.link_task("P-1", "T-1")
        payload = payload_of(event_store, "org.project.task_linked")
        assert payload["project_id"] == "P-1"
        assert payload["task_id"] == "T-1"
        # 事件顶层 task_id 字段 (审计锚点)
        ev = last_event(event_store)
        assert ev.task_id == "T-1"

    def test_list_project_tasks(self, lifecycle):
        lifecycle.create_project("A", project_id="P-1")
        lifecycle.link_task("P-1", "T-1")
        lifecycle.link_task("P-1", "T-2")
        assert sorted(lifecycle.list_project_tasks("P-1")) == ["T-1", "T-2"]

    def test_list_project_tasks_empty(self, lifecycle):
        lifecycle.create_project("A", project_id="P-1")
        assert lifecycle.list_project_tasks("P-1") == []
