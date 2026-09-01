"""tests/console/test_orchestration_dag.py — P1-R2: 依赖感知执行 (TaskScheduler 接入)。

验证 execute_project 真实按依赖执行:
- 依赖任务: 依赖在前 (拓扑序)
- 依赖失败: 后继任务 blocked (失败传播), 不执行
- 无依赖: 原数组顺序 (旧行为零变化)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory_console.session import orchestrator as ORCH


def _make_project(root: Path, slug: str, tasks: list[dict]) -> Path:
    pdir = root / "projects" / slug
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "execution_plan.json").write_text(
        json.dumps({"tasks": tasks, "count": len(tasks)}), encoding="utf-8"
    )
    (pdir / "project.json").write_text(
        json.dumps({"name": slug, "status": "execution_ready"}), encoding="utf-8"
    )
    (pdir / "product.json").write_text(
        json.dumps({"name": slug, "problem": "p", "user": "u", "platform": "mobile",
                    "core_features": ["f"], "status": "execution_ready"}),
        encoding="utf-8",
    )
    return pdir


def _recording_fn(calls: list):
    def fn(task, project_dir, workspace):
        calls.append(str(task.get("id")))
        return {"success": True, "artifact": f"art-{task.get('id')}", "cost": "0.01"}
    return fn


def test_dependency_order_executed_first(tmp_path: Path) -> None:
    """T001 → T002: T001 必须先执行 (拓扑序, 非数组顺序)。"""
    tasks = [
        {"id": "T001", "name": "A", "agent_type": "dev", "depends_on": []},
        {"id": "T002", "name": "B", "agent_type": "dev", "depends_on": ["T001"]},
    ]
    _make_project(tmp_path, "demo", tasks)
    # 故意乱序 (数组序 T002 在前) — 依赖图必须纠正
    tasks[0], tasks[1] = tasks[1], tasks[0]
    (tmp_path / "projects" / "demo" / "execution_plan.json").write_text(
        json.dumps({"tasks": tasks, "count": 2}), encoding="utf-8"
    )
    calls: list[str] = []
    orch = ORCH.ExecutionOrchestrator(tmp_path)
    result = orch.execute_project("demo", execute_fn=_recording_fn(calls))
    assert result.completed_tasks == 2, result.errors
    assert calls == ["T001", "T002"], f"执行顺序必须依赖在前: {calls}"


def test_dependency_failure_blocks_successor(tmp_path: Path) -> None:
    """T001 失败 → T002 (依赖 T001) 必须 blocked, 不得执行。"""
    tasks = [
        {"id": "T001", "name": "A", "agent_type": "dev", "depends_on": []},
        {"id": "T002", "name": "B", "agent_type": "dev", "depends_on": ["T001"]},
    ]
    _make_project(tmp_path, "demo", tasks)

    calls: list[str] = []

    def fail_first(task, project_dir, workspace):
        calls.append(str(task.get("id")))
        if task.get("id") == "T001":
            return {"success": False, "error": "boom"}
        return {"success": True, "artifact": "x", "cost": "0.01"}

    orch = ORCH.ExecutionOrchestrator(tmp_path)
    result = orch.execute_project("demo", execute_fn=fail_first)
    assert result.failed_tasks >= 1
    assert "T002" not in calls, f"依赖失败必须阻断后继: {calls}"
    # T002 应为 blocked
    state_file = tmp_path / "projects" / "demo" / "execution_state.json"
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
        t2 = next(t for t in state.get("tasks", []) if t.get("id") == "T002")
        assert t2.get("status") in ("blocked", "pending"), f"T002 应 blocked: {t2.get('status')}"


def test_no_dependency_preserves_order(tmp_path: Path) -> None:
    """无依赖: 保持数组顺序执行 (旧行为零变化)。"""
    tasks = [
        {"id": "T001", "name": "A", "agent_type": "dev", "depends_on": []},
        {"id": "T002", "name": "B", "agent_type": "dev", "depends_on": []},
    ]
    _make_project(tmp_path, "demo", tasks)
    calls: list[str] = []
    orch = ORCH.ExecutionOrchestrator(tmp_path)
    result = orch.execute_project("demo", execute_fn=_recording_fn(calls))
    assert result.completed_tasks == 2
    assert calls == ["T001", "T002"]


def test_schedule_projection_written(tmp_path: Path) -> None:
    """P1-R2/Phase 6: 正式执行默认落盘 schedule.json (projection, 可重建)。"""
    tasks = [
        {"id": "T001", "name": "A", "agent_type": "dev", "depends_on": []},
        {"id": "T002", "name": "B", "agent_type": "dev", "depends_on": ["T001"]},
        {"id": "T003", "name": "C", "agent_type": "dev", "depends_on": []},
    ]
    _make_project(tmp_path, "demo", tasks)
    orch = ORCH.ExecutionOrchestrator(tmp_path)
    result = orch.execute_project("demo", execute_fn=_recording_fn([]))
    assert result.completed_tasks == 3
    sched = tmp_path / "projects" / "demo" / "schedule.json"
    assert sched.exists(), "schedule.json 必须落盘"
    data = json.loads(sched.read_text(encoding="utf-8"))
    assert "rounds" in data or "order" in data, f"schedule 需含轮次/顺序: {list(data.keys())}"
