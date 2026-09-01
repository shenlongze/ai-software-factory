"""tests/console/test_plan_lifecycle.py — P2-①: Plan 生命周期闭环 + 幂等消费。

状态机: pending → executing/completed/failed
- 批准 = 一次性消费 (pending → executing)
- 已消费 plan 再次 execute_plan → 返回真实状态, 不重复创建任务
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory_console.session.agent_loop import PendingPlanStore, dispatch


class _FakeService:
    def __init__(self) -> None:
        self.created: list[dict] = []

    def create_task(self, project_id: str, **kw) -> dict:
        t = {"id": f"T-{len(self.created)+1}", "title": kw.get("title", ""), "ok": True}
        self.created.append(t)
        return t

    def list_backlog(self, project_id: str) -> dict:
        return {"tasks": self.created}


def _make_plan(session_id: str, root: Path, status: str = "pending", n: int = 2) -> dict:
    plan = {
        "plan_id": "PLAN-test001",
        "project_id": "P-1",
        "session_id": session_id,
        "status": status,
        "tasks": [{"title": f"T{i}", "description": "", "priority": "P2"} for i in range(n)],
        "order": [f"T{i}" for i in range(n)],
        "acceptance": [],
    }
    PendingPlanStore(root).save(session_id, plan)
    return plan


def test_pending_to_executing_consumes_plan(tmp_path: Path) -> None:
    """批准执行: pending → executing, 任务真实创建。"""
    _make_plan("s1", tmp_path)
    svc = _FakeService()
    r = dispatch("execute_plan", {}, root=tmp_path, project_id="P-1",
                 service=svc, ctx={"session_id": "s1"})
    assert r["ok"] is True
    assert len(svc.created) == 2, "应创建 2 个任务"
    st = PendingPlanStore(tmp_path).get("s1")
    assert st["status"] == "executing", "消费后 status=executing"


def test_second_execute_plan_idempotent(tmp_path: Path) -> None:
    """同一 plan 第二次执行 → 返回已消费, 不重复创建任务。"""
    _make_plan("s1", tmp_path)
    svc = _FakeService()
    r1 = dispatch("execute_plan", {}, root=tmp_path, project_id="P-1",
                  service=svc, ctx={"session_id": "s1"})
    assert r1["ok"] is True
    r2 = dispatch("execute_plan", {}, root=tmp_path, project_id="P-1",
                  service=svc, ctx={"session_id": "s1"})
    assert r2["ok"] is False, "重复执行必须被拒绝"
    assert "已消费" in r2["error"]
    assert r2["plan_status"] == "executing"
    assert len(svc.created) == 2, "不得重复创建任务"


def test_completed_plan_not_reexecuted(tmp_path: Path) -> None:
    """completed 计划再次批准 → 不执行 (终态)。"""
    _make_plan("s1", tmp_path, status="completed")
    svc = _FakeService()
    r = dispatch("execute_plan", {}, root=tmp_path, project_id="P-1",
                 service=svc, ctx={"session_id": "s1"})
    assert r["ok"] is False
    assert r["plan_status"] == "completed"
    assert len(svc.created) == 0


def test_failed_plan_not_reexecuted(tmp_path: Path) -> None:
    """failed 计划再次批准 → 不执行。"""
    _make_plan("s1", tmp_path, status="failed")
    svc = _FakeService()
    r = dispatch("execute_plan", {}, root=tmp_path, project_id="P-1",
                 service=svc, ctx={"session_id": "s1"})
    assert r["ok"] is False
    assert r["plan_status"] == "failed"


def test_update_status_mark_completed(tmp_path: Path) -> None:
    """状态机支持 executing → completed (外部回写)。"""
    _make_plan("s1", tmp_path, status="executing")
    PendingPlanStore(tmp_path).update_status("s1", "completed")
    st = PendingPlanStore(tmp_path).get("s1")
    assert st["status"] == "completed"
