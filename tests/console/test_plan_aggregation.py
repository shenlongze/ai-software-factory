"""tests/console/test_plan_aggregation.py — P2-④: Plan 终态聚合。

基于 Task SSOT (plan_id 反查 backlog), 幂等, 不读 ExecState。
Case A: 空 → completed / B: 全 DONE → completed / C: 非终态 → executing
D: 全终态含 FAILED → failed / E: cancelled 无 failed → executing + finding
F: FAILED→retry→DONE → completed
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from org.management import ManagementStore, Task, TaskStatus
from org.projects import ProjectLifecycle, ProjectStore
from org.space import ProjectSpaceStore
from factory_console.session.agent_loop import PendingPlanStore, reconcile_plan


def _env(tmp_path: Path):
    d = tmp_path
    (d / "org").mkdir()
    (d / "org" / "projects.json").write_text(json.dumps({"projects": {}}))
    ps = ProjectStore(str(d / "org"))
    p = ProjectLifecycle(ps).create_project("AGG")
    wd = d / "workspace" / "projects" / "agg"
    wd.mkdir(parents=True, exist_ok=True)
    (wd / "project.json").write_text(json.dumps({"id": p.id, "name": "AGG"}))
    mgmt = ManagementStore(wd / "management")
    return d, p, mgmt


def _save_plan(d: Path, plan_id: str, project_id: str, status: str = "executing") -> None:
    PendingPlanStore(d).save("sess-agg", {
        "plan_id": plan_id, "project_id": project_id, "status": status,
        "tasks": [{"title": "t"}], "order": [], "acceptance": [],
    })


def _task(pid: str, title: str, status: TaskStatus, tid: str = "") -> Task:
    return Task(id=tid or f"T-{abs(hash(title)) % 10000}", title=title,
                priority="P2", status=status, plan_id=pid)


def _load_plan(d: Path, plan_id: str) -> dict:
    sp = json.loads((d / "session_plans.json").read_text(encoding="utf-8"))
    for v in sp.values():
        if v.get("plan_id") == plan_id:
            return v
    raise AssertionError("plan missing")


# Case A: 空 Plan → completed
def test_empty_plan_completed(tmp_path: Path) -> None:
    d, p, _ = _env(tmp_path)
    _save_plan(d, "PLAN-A", p.id)
    r = reconcile_plan(d, "PLAN-A")
    assert r["status"] == "completed" and r["changed"]
    assert _load_plan(d, "PLAN-A")["status"] == "completed"


# Case B: 全 DONE → completed
def test_all_done_completed(tmp_path: Path) -> None:
    d, p, mgmt = _env(tmp_path)
    _save_plan(d, "PLAN-B", p.id)
    for i in range(3):
        mgmt.save_task(_task("PLAN-B", f"t{i}", TaskStatus.DONE))
    r = reconcile_plan(d, "PLAN-B")
    assert r["status"] == "completed"
    assert r["task_count"] == 3


# Case C: DONE + TODO → executing
def test_done_plus_todo_executing(tmp_path: Path) -> None:
    d, p, mgmt = _env(tmp_path)
    _save_plan(d, "PLAN-C", p.id)
    mgmt.save_task(_task("PLAN-C", "a", TaskStatus.DONE))
    mgmt.save_task(_task("PLAN-C", "b", TaskStatus.TODO))
    r = reconcile_plan(d, "PLAN-C")
    assert r["status"] == "executing" and not r["changed"]


# Case C2: FAILED + TODO → executing (独立任务可继续/retry)
def test_failed_plus_todo_executing(tmp_path: Path) -> None:
    d, p, mgmt = _env(tmp_path)
    _save_plan(d, "PLAN-C2", p.id)
    mgmt.save_task(_task("PLAN-C2", "a", TaskStatus.FAILED))
    mgmt.save_task(_task("PLAN-C2", "b", TaskStatus.TODO))
    r = reconcile_plan(d, "PLAN-C2")
    assert r["status"] == "executing", "非全终态 → 不 failed"


# Case D: FAILED + DONE → failed
def test_failed_done_failed(tmp_path: Path) -> None:
    d, p, mgmt = _env(tmp_path)
    _save_plan(d, "PLAN-D", p.id)
    mgmt.save_task(_task("PLAN-D", "a", TaskStatus.FAILED))
    mgmt.save_task(_task("PLAN-D", "b", TaskStatus.DONE))
    r = reconcile_plan(d, "PLAN-D")
    assert r["status"] == "failed" and r["changed"]


# Case E: CANCELLED + DONE (无 FAILED) → 保持 executing + finding
def test_cancelled_done_keeps_executing(tmp_path: Path) -> None:
    d, p, mgmt = _env(tmp_path)
    _save_plan(d, "PLAN-E", p.id)
    mgmt.save_task(_task("PLAN-E", "a", TaskStatus.CANCELLED))
    mgmt.save_task(_task("PLAN-E", "b", TaskStatus.DONE))
    r = reconcile_plan(d, "PLAN-E")
    assert r["status"] == "executing", "PlanStatus 无 cancelled → 不擅自扩展"
    assert "cancelled" in r["note"]


# Case F: FAILED → retry → DONE → completed
def test_failed_retry_then_done_completed(tmp_path: Path) -> None:
    d, p, mgmt = _env(tmp_path)
    _save_plan(d, "PLAN-F", p.id)
    mgmt.save_task(_task("PLAN-F", "a", TaskStatus.FAILED))
    mgmt.save_task(_task("PLAN-F", "b", TaskStatus.DONE))
    assert reconcile_plan(d, "PLAN-F")["status"] == "failed"
    # retry: FAILED → DONE (定位 FAILED 任务, 不依赖列表顺序)
    tx = next(t for t in mgmt.list_tasks() if t.status == TaskStatus.FAILED)
    mgmt.save_task(Task(id=tx.id, title=tx.title, priority="P2",
                        status=TaskStatus.DONE, plan_id="PLAN-F"))
    r2 = reconcile_plan(d, "PLAN-F")
    assert r2["status"] == "completed", "retry 后可恢复为 completed"


# Idempotency: 重复聚合无变化; 终态保持
def test_idempotent_reconcile(tmp_path: Path) -> None:
    d, p, mgmt = _env(tmp_path)
    _save_plan(d, "PLAN-I", p.id)
    mgmt.save_task(_task("PLAN-I", "a", TaskStatus.DONE))
    r1 = reconcile_plan(d, "PLAN-I")
    assert r1["changed"]
    r2 = reconcile_plan(d, "PLAN-I")
    assert not r2["changed"], "重复聚合无状态变化"
    r3 = reconcile_plan(d, "PLAN-I")
    assert not r3["changed"]
    assert _load_plan(d, "PLAN-I")["status"] == "completed"


# Relationship: 只聚合本 Plan 的 Task
def test_plan_isolation(tmp_path: Path) -> None:
    d, p, mgmt = _env(tmp_path)
    _save_plan(d, "PLAN-X", p.id)
    mgmt.save_task(_task("PLAN-X", "x1", TaskStatus.DONE))
    mgmt.save_task(_task("PLAN-Y", "y1", TaskStatus.TODO))  # 另一计划
    r = reconcile_plan(d, "PLAN-X")
    assert r["task_count"] == 1, "只聚合 PLAN-X 的 Task"
    assert r["status"] == "completed"
