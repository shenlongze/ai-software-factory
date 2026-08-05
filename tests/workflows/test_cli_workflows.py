"""tests/workflows/test_cli_workflows.py — CLI workflow list/add/run/status。

覆盖: 输出格式 (✓/▶/○) / 退出码 (cli-design §5: 1 一般 / 2 用法 / 7 未找到) /
--json / Event 集成 (workflow.* 经 EventLogger)。
"""

from __future__ import annotations

import json
from pathlib import Path

from cli_helpers import event_types, open_events, run_cli

FEATURE_STEPS = "architecture,development,testing,validation"


def _add_builtin(capsys, cli_root: Path, wf_id: str = "feature-delivery") -> None:
    run_cli(capsys, cli_root, "workflow", "add", "--id", wf_id)


def _create_task(capsys, cli_root: Path, task_id: str = "T-001", wf: str = "feature-delivery") -> None:
    run_cli(capsys, cli_root, "task", "create", "--id", task_id, "--title", "任务", "--workflow", wf)


class TestWorkflowAdd:
    def test_add_custom_steps(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(capsys, cli_root, "workflow", "add", "--id", "wf-a",
                             "--name", "自定义", "--steps", "s1,s2,s3")
        assert rc == 0
        assert "wf-a" in out and "s1 → s2 → s3" in out
        with open_events(cli_root) as store:
            assert event_types(store) == ["workflow.created"]

    def test_add_builtin(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(capsys, cli_root, "workflow", "add", "--id", "feature-delivery")
        assert rc == 0
        assert "feature-delivery" in out
        assert "architecture → development → testing → validation" in out

    def test_add_builtin_unknown_exit_2(self, capsys, cli_root: Path):
        rc, _, err = run_cli(capsys, cli_root, "workflow", "add", "--id", "ghost")
        assert rc == 2
        assert "no builtin workflow" in err

    def test_add_duplicate_exit_1(self, capsys, cli_root: Path):
        _add_builtin(capsys, cli_root)
        rc, _, err = run_cli(capsys, cli_root, "workflow", "add", "--id", "feature-delivery")
        assert rc == 1
        assert "already exists" in err

    def test_add_json(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(capsys, cli_root, "workflow", "add", "--id", "wf-a",
                             "--steps", "x,y", "--json")
        assert rc == 0
        d = json.loads(out)
        assert d["ok"] is True
        assert d["workflow"]["id"] == "wf-a"
        assert [s["id"] for s in d["workflow"]["steps"]] == ["x", "y"]


class TestWorkflowList:
    def test_list_empty(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(capsys, cli_root, "workflow", "list")
        assert rc == 0
        assert "0 workflows" in out
        with open_events(cli_root) as store:
            assert event_types(store) == ["workflow.viewed"]

    def test_list_entries(self, capsys, cli_root: Path):
        _add_builtin(capsys, cli_root, "feature-delivery")
        _add_builtin(capsys, cli_root, "bug-fix")
        rc, out, _ = run_cli(capsys, cli_root, "workflow", "list")
        assert rc == 0
        assert "2 workflows" in out
        assert "feature-delivery" in out and "bug-fix" in out
        with open_events(cli_root) as store:
            viewed = [e for e in store.query() if e.type.value == "workflow.viewed" and e.action == "list workflows"]
            assert len(viewed) == 1
            assert viewed[0].payload["count"] == 2


class TestWorkflowRun:
    def test_run_starts_workflow(self, capsys, cli_root: Path):
        _add_builtin(capsys, cli_root)
        _create_task(capsys, cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "workflow", "run", "T-001")
        assert rc == 0
        assert "WR-001" in out
        assert "feature-delivery" in out
        assert "architecture" in out  # Current step
        with open_events(cli_root) as store:
            types = event_types(store)
            assert "workflow.created" in types and "workflow.started" in types
            started = [e for e in store.query() if e.type.value == "workflow.started"][-1]
            assert started.task_id == "T-001"
            assert started.payload["workflow_id"] == "feature-delivery"

    def test_run_task_not_found_exit_7(self, capsys, cli_root: Path):
        _add_builtin(capsys, cli_root)
        rc, _, err = run_cli(capsys, cli_root, "workflow", "run", "T-999")
        assert rc == 7
        assert "task not found" in err

    def test_run_workflow_not_registered_exit_7(self, capsys, cli_root: Path):
        _create_task(capsys, cli_root, wf="ghost-wf")
        rc, _, err = run_cli(capsys, cli_root, "workflow", "run", "T-001")
        assert rc == 7
        assert "workflow not registered" in err

    def test_run_already_started_exit_1(self, capsys, cli_root: Path):
        _add_builtin(capsys, cli_root)
        _create_task(capsys, cli_root)
        run_cli(capsys, cli_root, "workflow", "run", "T-001")
        rc, _, err = run_cli(capsys, cli_root, "workflow", "run", "T-001")
        assert rc == 1
        assert "already has a workflow run" in err

    def test_run_json(self, capsys, cli_root: Path):
        _add_builtin(capsys, cli_root)
        _create_task(capsys, cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "workflow", "run", "T-001", "--json")
        assert rc == 0
        d = json.loads(out)
        assert d["run"]["status"] == "RUNNING"
        assert d["current_step"] == "architecture"


class TestWorkflowStatus:
    def test_status_symbols(self, capsys, cli_root: Path):
        """✓ 完成 / ▶ 当前 / ○ 待办。"""
        _add_builtin(capsys, cli_root)
        _create_task(capsys, cli_root)
        run_cli(capsys, cli_root, "workflow", "run", "T-001")
        rc, out, _ = run_cli(capsys, cli_root, "workflow", "status", "T-001")
        assert rc == 0
        assert "▶ architecture" in out
        assert "○ development" in out and "○ testing" in out and "○ validation" in out
        assert "RUNNING" in out
        with open_events(cli_root) as store:
            viewed = [e for e in store.query() if e.type.value == "workflow.viewed" and e.action == "show workflow status"]
            assert len(viewed) == 1
            assert viewed[0].task_id == "T-001"

    def test_status_completed_symbols(self, capsys, cli_root: Path):
        """推进部分步骤后 status 显示 ✓ 已完成 / ▶ 当前。"""
        _add_builtin(capsys, cli_root)
        _create_task(capsys, cli_root)
        run_cli(capsys, cli_root, "workflow", "run", "T-001")
        # 经 store 直接推进: architecture RUNNING→COMPLETED, development→RUNNING (模拟后续阶段 CLI)
        from workflows.engine import WorkflowEngine
        from workflows.models import StepStatus
        from workflows.store import WorkflowStore
        engine = WorkflowEngine(WorkflowStore(cli_root / "workflows"))
        run = engine.store.get_run_by_task("T-001")
        run.step_state("architecture").status = StepStatus.COMPLETED
        run.step_state("development").status = StepStatus.RUNNING
        run.current_step = "development"
        engine.store.save_run(run)

        rc, out, _ = run_cli(capsys, cli_root, "workflow", "status", "T-001")
        assert rc == 0
        assert "✓ architecture" in out
        assert "▶ development" in out
        assert "○ testing" in out and "○ validation" in out

    def test_status_no_run_exit_1(self, capsys, cli_root: Path):
        _create_task(capsys, cli_root)
        rc, _, err = run_cli(capsys, cli_root, "workflow", "status", "T-001")
        assert rc == 1
        assert "no workflow run" in err

    def test_status_task_not_found_exit_7(self, capsys, cli_root: Path):
        rc, _, err = run_cli(capsys, cli_root, "workflow", "status", "T-999")
        assert rc == 7
        assert "task not found" in err

    def test_status_json(self, capsys, cli_root: Path):
        _add_builtin(capsys, cli_root)
        _create_task(capsys, cli_root)
        run_cli(capsys, cli_root, "workflow", "run", "T-001")
        rc, out, _ = run_cli(capsys, cli_root, "workflow", "status", "T-001", "--json")
        assert rc == 0
        d = json.loads(out)
        assert d["steps"][0]["symbol"] == "▶"
        assert d["steps"][0]["status"] == "RUNNING"
        assert all(s["symbol"] == "○" for s in d["steps"][1:])


class TestWorkflowSmoke:
    def test_full_chain(self, capsys, cli_root: Path):
        """冒烟: workflow add → task create (带 workflow) → workflow run → status。"""
        rc, _, _ = run_cli(capsys, cli_root, "workflow", "add", "--id", "feature-delivery")
        assert rc == 0
        rc, _, _ = run_cli(capsys, cli_root, "task", "create", "--id", "T-001",
                           "--title", "冒烟任务", "--workflow", "feature-delivery")
        assert rc == 0
        rc, out, _ = run_cli(capsys, cli_root, "workflow", "run", "T-001")
        assert rc == 0 and "WR-001" in out
        rc, out, _ = run_cli(capsys, cli_root, "workflow", "status", "T-001")
        assert rc == 0 and "▶ architecture" in out
        # 事件链: created + task.created + started + viewed
        with open_events(cli_root) as store:
            types = event_types(store)
            assert "workflow.created" in types
            assert "workflow.started" in types
            assert "workflow.viewed" in types
            assert "task.created" in types
