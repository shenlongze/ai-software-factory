"""tests/org/test_task_cancelled.py — P2-①: CANCELLED 状态语义。

CANCELLED = 用户主动取消 (≠ FAILED 执行失败, ≠ BLOCKED 依赖传播)
- Stop → 任务 CANCELLED (Task SSOT 事实)
- 连续 Stop 幂等
- cancelled → ready 重试
- 重启保持 cancelled
- 依赖 cancelled 任务 → 下游 waiting (不自动 blocked)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from org.management import (
    ManagementStore, TASK_TRANSITIONS, Task, TaskStatus, transition_task,
)


def _mk(tid: str = "T-1", deps: list[str] | None = None) -> Task:
    return Task(id=tid, title="x", priority="P2", status=TaskStatus.TODO,
                dependency=deps or [])


def test_cancelled_enum_and_transitions() -> None:
    assert TaskStatus.CANCELLED.value == "cancelled"
    assert TaskStatus.CANCELLED not in (TaskStatus.FAILED, TaskStatus.BLOCKED)
    assert TaskStatus.CANCELLED in TASK_TRANSITIONS[TaskStatus.IN_PROGRESS]
    assert TaskStatus.READY in TASK_TRANSITIONS[TaskStatus.CANCELLED]


def test_in_progress_to_cancelled() -> None:
    t = _mk()
    t2 = transition_task(t, TaskStatus.READY, actor="t")
    t3 = transition_task(t2, TaskStatus.IN_PROGRESS, actor="t")
    t4 = transition_task(t3, TaskStatus.CANCELLED, actor="user-stop")
    assert t4.status == TaskStatus.CANCELLED


def test_cancelled_retry_to_ready() -> None:
    t = _mk()
    t2 = transition_task(t, TaskStatus.READY, actor="t")
    t3 = transition_task(t2, TaskStatus.IN_PROGRESS, actor="t")
    t4 = transition_task(t3, TaskStatus.CANCELLED, actor="user-stop")
    t5 = transition_task(t4, TaskStatus.READY, actor="human")
    assert t5.status == TaskStatus.READY


def test_finish_task_exec_cancelled(tmp_path: Path) -> None:
    """finish_task_exec(cancelled=True) → CANCELLED 落库 (非 FAILED)。"""
    from factory_console.service import ConsoleService

    from org.projects import ProjectLifecycle, ProjectStore
    from org.space import ProjectSpaceStore

    d = tmp_path
    (d / "org").mkdir()
    (d / "org" / "projects.json").write_text(json.dumps({"projects": {}}))
    ps = ProjectStore(str(d / "org"))
    p = ProjectLifecycle(ps).create_project("C-TEST")
    svc = ConsoleService(
        workspace_manager=None, task_store=None, agent_registry=None,
        product_store=None, decision_store=None, recommendation_store=None,
        experience_store=None, usage_store=None, provider_registry=None,
        project_store=ps, workflow_lifecycle=None, project_space=ProjectSpaceStore(d),
    )
    svc._mount_org()
    mgmt = ManagementStore(d / "workspace" / "projects" / "c-test" / "management")
    t = _mk()
    mgmt.save_task(t)
    tid = t.id
    r = svc.finish_task_exec(p.id, tid, success=False, cancelled=True,
                             actor="user-stop", exec_result="cancelled")
    got = mgmt.get_task(tid)
    assert got.status == TaskStatus.CANCELLED
    assert got.status != TaskStatus.FAILED


def test_finish_task_exec_cancelled_idempotent(tmp_path: Path) -> None:
    """连续 Stop: 二次回写幂等 (保持 CANCELLED)。"""
    from factory_console.service import ConsoleService

    from org.projects import ProjectLifecycle, ProjectStore
    from org.space import ProjectSpaceStore

    d = tmp_path
    (d / "org").mkdir()
    (d / "org" / "projects.json").write_text(json.dumps({"projects": {}}))
    ps = ProjectStore(str(d / "org"))
    p = ProjectLifecycle(ps).create_project("C-TEST2")
    svc = ConsoleService(
        workspace_manager=None, task_store=None, agent_registry=None,
        product_store=None, decision_store=None, recommendation_store=None,
        experience_store=None, usage_store=None, provider_registry=None,
        project_store=ps, workflow_lifecycle=None, project_space=ProjectSpaceStore(d),
    )
    svc._mount_org()
    mgmt = ManagementStore(d / "workspace" / "projects" / "c-test2" / "management")
    t = _mk()
    mgmt.save_task(t)
    svc.finish_task_exec(p.id, t.id, success=False, cancelled=True, actor="user-stop")
    svc.finish_task_exec(p.id, t.id, success=False, cancelled=True, actor="user-stop")
    got = mgmt.get_task(t.id)
    assert got.status == TaskStatus.CANCELLED, "状态幂等 (不重复转换)"
    assert len([h for h in got.history if h.action == "exec:cancelled"]) >= 1


def test_cancelled_persists_restart(tmp_path: Path) -> None:
    """重启后 CANCELLED 保持 (不被转 FAILED/BLOCKED/TODO)。"""
    mgmt = ManagementStore(tmp_path)
    t = _mk()
    mgmt.save_task(t)
    t2 = transition_task(t, TaskStatus.READY, actor="t")
    t3 = transition_task(t2, TaskStatus.IN_PROGRESS, actor="t")
    t4 = transition_task(t3, TaskStatus.CANCELLED, actor="user-stop")
    mgmt.save_task(t4)
    reloaded = mgmt.get_task("T-1")
    assert reloaded.status == TaskStatus.CANCELLED
