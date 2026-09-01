"""tests/org/test_plan_dependency.py — P1-R1: execute_plan → Task.dependency 传递。

覆盖:
- 显式 dependency (plan task.dependency) → task id 解析落库
- plan.order 顺序链兜底 (无显式依赖)
- 无依赖 plan 正常 (dependency=[])
- DAG 可重建 (TaskDependencyGraph 拓扑序)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def svc(tmp_path: Path):
    from org.management import ManagementStore
    from org.projects import ProjectLifecycle, ProjectStore
    from org.space import ProjectSpaceStore

    from factory_console.service import ConsoleService

    d = tmp_path
    (d / "org").mkdir()
    (d / "org" / "projects.json").write_text(json.dumps({"projects": {}}))
    ps = ProjectStore(str(d / "org"))
    lc = ProjectLifecycle(ps)
    project = lc.create_project("P1-TEST")
    s = ConsoleService(
        workspace_manager=None, task_store=None, agent_registry=None,
        product_store=None, decision_store=None, recommendation_store=None,
        experience_store=None, usage_store=None, provider_registry=None,
        project_store=ps, workflow_lifecycle=None, project_space=ProjectSpaceStore(d),
    )
    s._mount_org()
    return s, project, ManagementStore(d / "workspace" / "projects" / "p1-test" / "management")


def _load_tasks(mgmt) -> dict:
    return {t.title: t for t in mgmt.list_tasks()}


def test_explicit_dependency_resolved_to_task_ids(svc) -> None:
    from factory_console.session.agent_loop import execute_plan

    s, p, mgmt = svc
    plan = {"plan_id": "plan-1", "tasks": [
        {"title": "A", "priority": "P0", "dependency": []},
        {"title": "B", "priority": "P0", "dependency": ["A"]},
        {"title": "C", "priority": "P1", "dependency": ["A", "B"]},
    ]}
    r = execute_plan(plan, project_id=p.id, service=s)
    assert r["ok"] is True
    tasks = _load_tasks(mgmt)
    assert tasks["B"].dependency == [tasks["A"].id], "B 应依赖 A 的真实 task id"
    assert sorted(tasks["C"].dependency) == sorted([tasks["A"].id, tasks["B"].id])


def test_order_chain_fallback(svc) -> None:
    from factory_console.session.agent_loop import execute_plan

    s, p, mgmt = svc
    plan = {"plan_id": "plan-2", "tasks": [
        {"title": "X", "priority": "P0"},
        {"title": "Y", "priority": "P0"},
        {"title": "Z", "priority": "P1"},
    ], "order": ["X", "Y", "Z"]}
    execute_plan(plan, project_id=p.id, service=s)
    tasks = _load_tasks(mgmt)
    assert tasks["Y"].dependency == [tasks["X"].id], "order 链: Y 依赖 X"
    assert tasks["Z"].dependency == [tasks["Y"].id], "order 链: Z 依赖 Y"


def test_no_dependency_plan_still_works(svc) -> None:
    from factory_console.session.agent_loop import execute_plan

    s, p, mgmt = svc
    plan = {"plan_id": "plan-3", "tasks": [{"title": "S", "priority": "P2"}]}
    r = execute_plan(plan, project_id=p.id, service=s)
    assert r["ok"] is True
    tasks = _load_tasks(mgmt)
    assert tasks["S"].dependency == []


def test_dag_rebuildable_from_backlog(svc) -> None:
    """DAG = 从 Task.dependency 可重建投影 (TaskDependencyGraph 拓扑序)。"""
    from factory_console.session.agent_loop import execute_plan
    from factory_console.session.dependencies import TaskDependencyGraph

    s, p, mgmt = svc
    plan = {"plan_id": "plan-4", "tasks": [
        {"title": "R", "priority": "P0", "dependency": []},
        {"title": "M", "priority": "P0", "dependency": ["R"]},
        {"title": "L", "priority": "P1", "dependency": ["M"]},
    ]}
    execute_plan(plan, project_id=p.id, service=s)
    tasks = _load_tasks(mgmt)
    g = TaskDependencyGraph()
    for t in tasks.values():
        for dep in t.dependency:
            g.add_task(t.id)
            g.add_dependency(t.id, dep)
    order = g.topological_order([t.id for t in tasks.values()])
    id2t = {t.id: t.title for t in tasks.values()}
    assert id2t[order[0]] == "R"
    assert id2t[order[-1]] == "L"
