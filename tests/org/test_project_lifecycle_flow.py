"""tests/org/test_project_lifecycle_flow.py — S10-009 Task 002: Lifecycle State Machine 迁移方法。

覆盖 (Task 002: ProjectLifecycle 驱动 9 新态 + 旧值兼容 + 非法拒绝):
- 新状态全链流转: draft→discovery→product_defined→design→architecture→confirmed→
  development→release→maintain (transition_lifecycle 逐步推进, 每步校验 lifecycle +
  落库持久化)
- 新状态归档路径: 全部 9 新态可直接 →archived (弃用直达)
- 旧值兼容: idea→active→maintained→archived 既有行为不破坏; 旧数据落库
  (lifecycle=active) 加载后可继续流转
- 非法流转拒绝: draft→confirmed (跳级) / development→discovery (回退) /
  confirmed→idea (跨入旧态) / release→active (新→旧) / discovery→maintain (远跳)
  → ValueError, 且状态不被破坏
- archived 终态: 任何异态流转 → ValueError; 同态幂等 no-op (不重复发事件)
- updated_at: 真实流转后严格递增 + 落库持久化; 幂等 no-op 不触碰
- lifecycle_changed 事件 payload (from/to) — 迁移方法审计契约

实现说明 (诚实): 状态机由 PROJECT_TRANSITIONS 转换表驱动 (Task 001 已扩展),
transition_lifecycle 天然支持新态 — 本文件是迁移方法的真实行为断言/回归网,
不引入生产代码 (Task 002 无需改 org/projects.py)。

约束: 零 console/frontend/Core 改动 — 只测 org/projects.py 编排层。
"""

from __future__ import annotations

import pytest

from org.projects import (
    Project,
    ProjectLifecycle,
    ProjectState,
    ProjectStore,
)

from org_helpers import payload_of

#: 新状态主链 (project-lifecycle.md §2; 首态 draft 为测试入口, 经 store 落库 —
#: Task 4 之前无 draft 创建 API)。
MAIN_CHAIN: list[ProjectState] = [
    ProjectState.DRAFT,
    ProjectState.DISCOVERY,
    ProjectState.PRODUCT_DEFINED,
    ProjectState.DESIGN,
    ProjectState.ARCHITECTURE,
    ProjectState.CONFIRMED,
    ProjectState.DEVELOPMENT,
    ProjectState.RELEASE,
    ProjectState.MAINTAIN,
]

ALL_NEW_STATES: list[ProjectState] = [
    ProjectState.DRAFT,
    ProjectState.DISCOVERY,
    ProjectState.PRODUCT_DEFINED,
    ProjectState.DESIGN,
    ProjectState.ARCHITECTURE,
    ProjectState.CONFIRMED,
    ProjectState.DEVELOPMENT,
    ProjectState.RELEASE,
    ProjectState.MAINTAIN,
]


@pytest.fixture
def project_store(org_dir) -> ProjectStore:
    return ProjectStore(org_dir)


@pytest.fixture
def lifecycle(project_store, logger) -> ProjectLifecycle:
    return ProjectLifecycle(project_store, logger=logger)


def _save(store: ProjectStore, project_id: str, state: ProjectState) -> None:
    """直接落库指定状态的项目 (draft 等无创建 API 的状态经 store 建, 测试入口)。"""
    store.save_project(
        Project(id=project_id, name="unnamed-project-1", lifecycle=state)
    )


def _lifecycle_changed_count(event_store) -> int:
    return sum(
        1
        for e in event_store.query()
        if e.type.value == "org.project.lifecycle_changed"
    )


class TestNewStateFullChain:
    """新状态全链流转: draft→discovery→...→maintain, 逐步推进每步校验。"""

    def test_full_chain_step_by_step(self, lifecycle, project_store):
        _save(project_store, "P-D1", ProjectState.DRAFT)
        for expected in MAIN_CHAIN[1:]:
            updated = lifecycle.transition_lifecycle("P-D1", expected)
            assert updated.lifecycle == expected
            # 落库持久化: 每次流转后存储中的状态一致
            persisted = project_store.get_project("P-D1")
            assert persisted.lifecycle == expected
        assert project_store.get_project("P-D1").lifecycle == ProjectState.MAINTAIN

    def test_chain_continues_to_archived(self, lifecycle, project_store):
        """主链终段: maintain→archived (全链终点)。"""
        _save(project_store, "P-D1", ProjectState.MAINTAIN)
        updated = lifecycle.transition_lifecycle("P-D1", "archived")
        assert updated.is_archived
        assert project_store.get_project("P-D1").is_archived

    def test_transition_accepts_string_and_enum(self, lifecycle, project_store):
        """目标值宽容: str 与 ProjectState 枚举等价。"""
        _save(project_store, "P-D1", ProjectState.DRAFT)
        p1 = lifecycle.transition_lifecycle("P-D1", "discovery")
        assert p1.lifecycle == ProjectState.DISCOVERY
        p2 = lifecycle.transition_lifecycle("P-D1", ProjectState.PRODUCT_DEFINED)
        assert p2.lifecycle == ProjectState.PRODUCT_DEFINED

    def test_transition_emits_lifecycle_changed_payload(self, lifecycle, event_store):
        """迁移方法审计契约: org.project.lifecycle_changed payload (from/to)。"""
        _save(lifecycle.store, "P-D1", ProjectState.DRAFT)
        lifecycle.transition_lifecycle("P-D1", "discovery")
        payload = payload_of(event_store, "org.project.lifecycle_changed")
        assert payload["project_id"] == "P-D1"
        assert payload["from_lifecycle"] == "draft"
        assert payload["to_lifecycle"] == "discovery"


class TestArchivePaths:
    """新状态归档路径: 任一 9 新态可直接 →archived (弃用直达)。"""

    @pytest.mark.parametrize(
        "from_state", ALL_NEW_STATES, ids=lambda s: s.value
    )
    def test_new_state_archives_directly(self, lifecycle, project_store, from_state):
        project_id = "P-ARC-" + from_state.value
        _save(project_store, project_id, from_state)
        updated = lifecycle.transition_lifecycle(project_id, "archived")
        assert updated.lifecycle == ProjectState.ARCHIVED
        assert updated.is_archived
        assert project_store.get_project(project_id).is_archived


class TestLegacyCompat:
    """旧值兼容: idea→active→maintained→archived 既有行为不破坏。"""

    def test_legacy_chain_idea_active_maintained_archived(
        self, lifecycle, project_store
    ):
        lifecycle.create_project("Legacy App", project_id="P-LEG")
        assert lifecycle.get_project("P-LEG").lifecycle == ProjectState.IDEA
        for state in ("active", "maintained", "archived"):
            updated = lifecycle.transition_lifecycle("P-LEG", state)
            assert updated.lifecycle.value == state
        assert project_store.get_project("P-LEG").is_archived

    def test_legacy_persisted_state_continues_transitions(self, lifecycle, project_store):
        """旧数据 (lifecycle=active 落库) 加载后可继续流转 — 零破坏。"""
        project_store.save_project(
            Project(id="P-LEG2", name="MarkPad", lifecycle="active")
        )
        updated = lifecycle.transition_lifecycle("P-LEG2", "maintained")
        assert updated.lifecycle == ProjectState.MAINTAINED
        assert lifecycle.transition_lifecycle("P-LEG2", "archived").is_archived


class TestIllegalTransitions:
    """非法流转拒绝: 跳级 / 回退 / 跨入旧态 / 远跳 → ValueError, 状态不破坏。"""

    @pytest.mark.parametrize(
        "from_state,to_state",
        [
            (ProjectState.DRAFT, ProjectState.CONFIRMED),        # 跳级
            (ProjectState.DEVELOPMENT, ProjectState.DISCOVERY),  # 回退
            (ProjectState.CONFIRMED, ProjectState.IDEA),         # 跨入旧态
            (ProjectState.RELEASE, ProjectState.ACTIVE),         # 新态→旧态
            (ProjectState.DISCOVERY, ProjectState.MAINTAIN),     # 远跳
        ],
        ids=lambda v: v.value if isinstance(v, ProjectState) else str(v),
    )
    def test_illegal_transition_raises(
        self, lifecycle, project_store, from_state, to_state
    ):
        project_id = "P-ILL-" + from_state.value
        _save(project_store, project_id, from_state)
        with pytest.raises(ValueError, match="invalid project lifecycle"):
            lifecycle.transition_lifecycle(project_id, to_state)
        # 拒绝后状态原位不动 (无半写入)
        assert project_store.get_project(project_id).lifecycle == from_state


class TestArchivedTerminal:
    """archived 终态: 不可再流转 (异态 → ValueError; 同态幂等 no-op)。"""

    @pytest.mark.parametrize(
        "to_state",
        [
            ProjectState.DEVELOPMENT,
            ProjectState.DRAFT,
            ProjectState.IDEA,
            ProjectState.ACTIVE,
            ProjectState.MAINTAINED,
            ProjectState.DISCOVERY,
        ],
        ids=lambda s: s.value,
    )
    def test_archived_rejects_any_transition(
        self, lifecycle, project_store, to_state
    ):
        _save(project_store, "P-TERM", ProjectState.ARCHIVED)
        with pytest.raises(ValueError, match="invalid project lifecycle"):
            lifecycle.transition_lifecycle("P-TERM", to_state)

    def test_archived_same_state_idempotent_no_event(self, lifecycle, project_store, event_store):
        """archived→archived: 同态幂等 no-op (既有行为 — 不重复发事件, 不触碰时间戳)。"""
        _save(project_store, "P-TERM2", ProjectState.ARCHIVED)
        before = project_store.get_project("P-TERM2").updated_at
        result = lifecycle.transition_lifecycle("P-TERM2", "archived")
        assert result.lifecycle == ProjectState.ARCHIVED
        assert result.updated_at == before
        assert _lifecycle_changed_count(event_store) == 0


class TestUpdatedAt:
    """updated_at: 真实流转后更新 (严格递增 + 落库持久化)。"""

    def test_transition_bumps_updated_at(self, lifecycle, project_store):
        _save(project_store, "P-D1", ProjectState.DRAFT)
        before = project_store.get_project("P-D1").updated_at
        updated = lifecycle.transition_lifecycle("P-D1", "discovery")
        assert updated.updated_at > before
        # 落库持久化: 重载后的 updated_at 与返回值一致且晚于流转前
        persisted = project_store.get_project("P-D1")
        assert persisted.updated_at == updated.updated_at
        assert persisted.updated_at > before

    def test_chain_bumps_updated_at_each_step(self, lifecycle, project_store):
        """全链逐步推进: 每步 updated_at 严格递增。"""
        _save(project_store, "P-D1", ProjectState.DRAFT)
        previous = project_store.get_project("P-D1").updated_at
        for expected in MAIN_CHAIN[1:]:
            updated = lifecycle.transition_lifecycle("P-D1", expected)
            assert updated.updated_at > previous
            previous = updated.updated_at

    def test_same_state_idempotent_keeps_updated_at(self, lifecycle, project_store):
        """同态幂等 no-op: 不重写时间戳 (无副作用)。"""
        lifecycle.create_project("A", project_id="P-1")
        lifecycle.transition_lifecycle("P-1", "active")
        before = project_store.get_project("P-1").updated_at
        lifecycle.transition_lifecycle("P-1", "active")  # 幂等
        assert project_store.get_project("P-1").updated_at == before
