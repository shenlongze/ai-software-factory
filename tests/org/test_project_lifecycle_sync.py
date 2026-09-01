"""tests/org/test_project_lifecycle_sync.py — S35-P0: 任务拆分后项目 lifecycle 自动推进。

用户发现: 任务拆完了项目状态还停留在 idea。根因: 任务拆分链路 (execute_plan/
create_task) 创建任务但不更新 org lifecycle, 且转换表 idea 无通往 confirmed 的边。
本测试覆盖修复:
- 转换表新边: idea → confirmed (任务拆解完成 = 需求已明确)
- 旧边兼容: idea → active 仍合法
- reconcile_stale_ideas: 存量校正 — 已拆任务 (任务数>0) 但停在 idea 的项目 → confirmed;
  无任务 / 非 idea 项目不动; 返回实际校正列表
- execute_plan 建任务成功后 → 项目 lifecycle 自动从 idea 流转到 confirmed

约束: 零 console/frontend/Core 改动 — 只测 org 编排层 + agent_loop.execute_plan 同步点。
"""

from __future__ import annotations

from typing import Any

import pytest

from org.projects import (
    Project,
    ProjectLifecycle,
    ProjectState,
    ProjectStore,
)


@pytest.fixture
def project_store(org_dir) -> ProjectStore:
    return ProjectStore(org_dir)


@pytest.fixture
def lifecycle(project_store, logger) -> ProjectLifecycle:
    return ProjectLifecycle(project_store, logger=logger)


def _save(store: ProjectStore, project_id: str, state: ProjectState) -> None:
    store.save_project(Project(id=project_id, name="proj", lifecycle=state))


def _get_state(store: ProjectStore, project_id: str) -> ProjectState:
    return store.get_project(project_id).lifecycle


# ---------------------------------------------------------------- 转换表新边


def test_idea_to_confirmed_transition_valid(lifecycle, project_store) -> None:
    """新边: idea → confirmed 合法 (任务拆解完成 = 需求已明确)。"""
    _save(project_store, "P-idea", ProjectState.IDEA)
    updated = lifecycle.transition_lifecycle("P-idea", ProjectState.CONFIRMED)
    assert updated.lifecycle == ProjectState.CONFIRMED
    assert _get_state(project_store, "P-idea") == ProjectState.CONFIRMED


def test_idea_to_active_legacy_edge_still_valid(lifecycle, project_store) -> None:
    """旧边兼容: idea → active 仍合法 (不破坏既有行为)。"""
    _save(project_store, "P-idea", ProjectState.IDEA)
    updated = lifecycle.transition_lifecycle("P-idea", ProjectState.ACTIVE)
    assert updated.lifecycle == ProjectState.ACTIVE


# ---------------------------------------------------------------- 存量校正


def test_reconcile_moves_stale_ideas(lifecycle, project_store) -> None:
    """已拆任务 (任务数>0) 但停在 idea 的项目 → confirmed, 返回校正列表。"""
    _save(project_store, "P-a", ProjectState.IDEA)
    _save(project_store, "P-b", ProjectState.IDEA)
    moved = lifecycle.reconcile_stale_ideas({"P-a": 20, "P-b": 0})
    assert moved == ["P-a"]
    assert _get_state(project_store, "P-a") == ProjectState.CONFIRMED
    assert _get_state(project_store, "P-b") == ProjectState.IDEA  # 无任务不动


def test_reconcile_skips_non_idea(lifecycle, project_store) -> None:
    """非 idea 项目不动 (development 不降级, confirmed 不重复)。"""
    _save(project_store, "P-dev", ProjectState.DEVELOPMENT)
    _save(project_store, "P-conf", ProjectState.CONFIRMED)
    moved = lifecycle.reconcile_stale_ideas({"P-dev": 10, "P-conf": 5})
    assert moved == []
    assert _get_state(project_store, "P-dev") == ProjectState.DEVELOPMENT
    assert _get_state(project_store, "P-conf") == ProjectState.CONFIRMED


def test_reconcile_idempotent_second_run(lifecycle, project_store) -> None:
    """幂等: 二次校正不重复事件、不报错、列表为空。"""
    _save(project_store, "P-a", ProjectState.IDEA)
    first = lifecycle.reconcile_stale_ideas({"P-a": 3})
    assert first == ["P-a"]
    second = lifecycle.reconcile_stale_ideas({"P-a": 3})
    assert second == []
    assert _get_state(project_store, "P-a") == ProjectState.CONFIRMED


# ---------------------------------------------------------------- execute_plan 同步


class _FakeService:
    """最小 fake: 提供 _project_store + create_task/list_backlog (execute_plan 依赖)。"""

    def __init__(self, store: ProjectStore):
        self._project_store = store
        self.tasks: list[dict[str, Any]] = []

    def list_backlog(self, project_id: str) -> dict[str, Any]:
        return {"tasks": self.tasks}

    def create_task(
        self,
        project_id: str,
        title: str,
        description: str = "",
        priority: str = "P2",
        plan_id: str = "",
    ) -> dict[str, Any]:
        t = {
            "id": f"T-{len(self.tasks) + 1}",
            "title": title,
            "priority": priority,
            "plan_id": plan_id,
        }
        self.tasks.append(t)
        return t


def test_execute_plan_promotes_idea_to_confirmed(project_store) -> None:
    """execute_plan 建任务成功后 → 项目 lifecycle 从 idea 自动流转到 confirmed。"""
    from factory_console.session.agent_loop import execute_plan

    _save(project_store, "P-x", ProjectState.IDEA)
    svc = _FakeService(project_store)
    plan = {"plan_id": "PL-1", "tasks": [
        {"title": "任务一", "priority": "P0"},
        {"title": "任务二", "priority": "P1"},
    ]}
    r = execute_plan(plan, project_id="P-x", service=svc)
    assert r["ok"] is True
    assert len(r["created"]) == 2
    assert _get_state(project_store, "P-x") == ProjectState.CONFIRMED


def test_execute_plan_does_not_downgrade_development(project_store) -> None:
    """development 项目执行计划 → 不降级 (非法流转静默跳过)。"""
    from factory_console.session.agent_loop import execute_plan

    _save(project_store, "P-dev", ProjectState.DEVELOPMENT)
    svc = _FakeService(project_store)
    plan = {"plan_id": "PL-2", "tasks": [{"title": "任务", "priority": "P0"}]}
    r = execute_plan(plan, project_id="P-dev", service=svc)
    assert r["ok"] is True
    assert _get_state(project_store, "P-dev") == ProjectState.DEVELOPMENT


def test_execute_plan_idempotent_path_also_promotes(project_store) -> None:
    """幂等路径 (计划已执行过) 也确保 lifecycle 已推进。"""
    from factory_console.session.agent_loop import execute_plan

    _save(project_store, "P-x", ProjectState.IDEA)
    svc = _FakeService(project_store)
    plan = {"plan_id": "PL-3", "tasks": [{"title": "任务", "priority": "P0"}]}
    execute_plan(plan, project_id="P-x", service=svc)  # 首次执行 → confirmed
    r2 = execute_plan(plan, project_id="P-x", service=svc)  # 幂等返回
    assert r2.get("idempotent") is True
    assert _get_state(project_store, "P-x") == ProjectState.CONFIRMED
