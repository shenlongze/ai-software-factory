"""tests/assignment/test_cli_assignments.py — CLI: factory agent assign/assignments/release。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli_helpers import event_types, open_events, run_cli
from cli.main import main


def _setup_agent(capsys, root: Path, agent_id: str = "A-001") -> None:
    """注册一个可匹配 development 步骤的 Agent (role/skill 与 feature-delivery 声明对齐)。"""
    run_cli(capsys, root, "agent", "add", "--id", agent_id, "--role", "backend-developer",
            "--skills", "development")


def _setup_task_and_workflow(capsys, root: Path, task_id: str = "T-001") -> None:
    run_cli(capsys, root, "task", "create", "--id", task_id, "--title", "测试任务")
    run_cli(capsys, root, "workflow", "add", "--id", "feature-delivery")


class TestAssign:
    def test_assign_auto_picks_and_prints(self, capsys, cli_root: Path):
        _setup_task_and_workflow(capsys, cli_root)
        _setup_agent(capsys, cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "agent", "assign", "--task", "T-001",
                             "--step", "development")
        assert rc == 0
        assert "Assigned: A-001" in out
        assert "ASG-001" in out

    def test_assign_json(self, capsys, cli_root: Path):
        _setup_task_and_workflow(capsys, cli_root)
        _setup_agent(capsys, cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "agent", "assign", "--task", "T-001",
                             "--step", "development", "--json")
        assert rc == 0
        d = json.loads(out)
        assert d["ok"] is True
        assert d["assignment"]["agent_id"] == "A-001"
        assert d["assignment"]["status"] == "ASSIGNED"
        assert d["assignment"]["workflow_step_id"] == "development"
        assert d["agent"]["status"] == "WORKING"

    def test_assign_explicit_agent(self, capsys, cli_root: Path):
        _setup_task_and_workflow(capsys, cli_root)
        _setup_agent(capsys, cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "agent", "assign", "--task", "T-001",
                             "--agent", "A-001")
        assert rc == 0
        assert "Assigned: A-001" in out

    def test_assign_emits_created_event(self, capsys, cli_root: Path):
        _setup_task_and_workflow(capsys, cli_root)
        _setup_agent(capsys, cli_root)
        run_cli(capsys, cli_root, "agent", "assign", "--task", "T-001", "--step", "development")
        with open_events(cli_root) as store:
            assert event_types(store)[-1] == "agent.assignment.created"
            ev = store.query()[-1]
            assert ev.agent_id == "A-001"
            assert ev.task_id == "T-001"
            assert ev.payload["workflow_step_id"] == "development"

    def test_assign_missing_step_and_agent_usage_exit_2(self, capsys, cli_root: Path):
        _setup_task_and_workflow(capsys, cli_root)
        rc, _, err = run_cli(capsys, cli_root, "agent", "assign", "--task", "T-001")
        assert rc == 2
        assert "requires --step or --agent" in err

    def test_assign_task_not_found_exit_7(self, capsys, cli_root: Path):
        rc, _, err = run_cli(capsys, cli_root, "agent", "assign", "--task", "T-999",
                             "--step", "development")
        assert rc == 7
        assert "task not found" in err

    def test_assign_workflow_not_registered_exit_7(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "x")
        rc, _, err = run_cli(capsys, cli_root, "agent", "assign", "--task", "T-001",
                             "--step", "development")
        assert rc == 7
        assert "workflow not registered" in err

    def test_assign_step_not_found_exit_7(self, capsys, cli_root: Path):
        _setup_task_and_workflow(capsys, cli_root)
        _setup_agent(capsys, cli_root)
        rc, _, err = run_cli(capsys, cli_root, "agent", "assign", "--task", "T-001",
                             "--step", "nosuchstep")
        assert rc == 7
        assert "step not found" in err

    def test_assign_no_available_agent_exit_1(self, capsys, cli_root: Path):
        _setup_task_and_workflow(capsys, cli_root)
        run_cli(capsys, cli_root, "agent", "add", "--id", "A-001", "--role",
                "test-engineer", "--skills", "testing")
        rc, _, err = run_cli(capsys, cli_root, "agent", "assign", "--task", "T-001",
                             "--step", "development")
        assert rc == 1
        assert "no available agent" in err

    def test_assign_explicit_agent_not_found_exit_7(self, capsys, cli_root: Path):
        _setup_task_and_workflow(capsys, cli_root)
        rc, _, err = run_cli(capsys, cli_root, "agent", "assign", "--task", "T-001",
                             "--agent", "A-999")
        assert rc == 7
        assert "agent not found" in err

    def test_assign_explicit_agent_not_available_exit_1(self, capsys, cli_root: Path):
        _setup_task_and_workflow(capsys, cli_root)
        _setup_agent(capsys, cli_root)
        run_cli(capsys, cli_root, "agent", "assign", "--task", "T-001", "--agent", "A-001")
        rc, _, err = run_cli(capsys, cli_root, "agent", "assign", "--task", "T-001",
                             "--agent", "A-001")
        assert rc == 1
        assert "not available" in err


class TestAssignments:
    def test_assignments_empty(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(capsys, cli_root, "agent", "assignments")
        assert rc == 0
        assert "0 assignments" in out

    def test_assignments_shows_rows(self, capsys, cli_root: Path):
        _setup_task_and_workflow(capsys, cli_root)
        _setup_agent(capsys, cli_root)
        run_cli(capsys, cli_root, "agent", "assign", "--task", "T-001", "--step", "development")
        rc, out, _ = run_cli(capsys, cli_root, "agent", "assignments")
        assert rc == 0
        assert "ASG-001" in out
        assert "A-001" in out
        assert "T-001" in out
        assert "development" in out
        assert "ASSIGNED" in out

    def test_assignments_json(self, capsys, cli_root: Path):
        _setup_task_and_workflow(capsys, cli_root)
        _setup_agent(capsys, cli_root)
        run_cli(capsys, cli_root, "agent", "assign", "--task", "T-001", "--step", "development")
        rc, out, _ = run_cli(capsys, cli_root, "agent", "assignments", "--json")
        assert rc == 0
        d = json.loads(out)
        assert d["count"] == 1
        assert d["assignments"][0]["agent_id"] == "A-001"

    def test_assignments_filter_by_status(self, capsys, cli_root: Path):
        _setup_task_and_workflow(capsys, cli_root)
        _setup_agent(capsys, cli_root)
        run_cli(capsys, cli_root, "agent", "assign", "--task", "T-001", "--step", "development")
        rc, out, _ = run_cli(capsys, cli_root, "agent", "assignments", "--status", "RELEASED")
        assert rc == 0
        assert "0 assignments" in out

    def test_assignments_filter_status_invalid_exit_2(self, capsys, cli_root: Path):
        rc, _, err = run_cli(capsys, cli_root, "agent", "assignments", "--status", "bogus")
        assert rc == 2
        assert "invalid assignment status" in err

    def test_assignments_emits_viewed_event(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "agent", "assignments")
        with open_events(cli_root) as store:
            assert event_types(store) == ["agent.assignment.viewed"]


class TestRelease:
    def test_release_success(self, capsys, cli_root: Path):
        _setup_task_and_workflow(capsys, cli_root)
        _setup_agent(capsys, cli_root)
        run_cli(capsys, cli_root, "agent", "assign", "--task", "T-001", "--step", "development")
        rc, out, _ = run_cli(capsys, cli_root, "agent", "release", "ASG-001")
        assert rc == 0
        assert "已释放 A-001" in out
        assert "AVAILABLE" in out

    def test_release_returns_agent_to_available(self, capsys, cli_root: Path):
        _setup_task_and_workflow(capsys, cli_root)
        _setup_agent(capsys, cli_root)
        run_cli(capsys, cli_root, "agent", "assign", "--task", "T-001", "--step", "development")
        run_cli(capsys, cli_root, "agent", "release", "ASG-001")
        rc, out, _ = run_cli(capsys, cli_root, "agent", "list", "--status", "AVAILABLE")
        assert rc == 0
        assert "A-001" in out

    def test_release_not_found_exit_7(self, capsys, cli_root: Path):
        rc, _, err = run_cli(capsys, cli_root, "agent", "release", "ASG-999")
        assert rc == 7
        assert "assignment not found" in err

    def test_release_already_terminal_exit_1(self, capsys, cli_root: Path):
        _setup_task_and_workflow(capsys, cli_root)
        _setup_agent(capsys, cli_root)
        run_cli(capsys, cli_root, "agent", "assign", "--task", "T-001", "--step", "development")
        run_cli(capsys, cli_root, "agent", "release", "ASG-001")
        rc, _, err = run_cli(capsys, cli_root, "agent", "release", "ASG-001")
        assert rc == 1
        assert "terminal state" in err

    def test_release_json(self, capsys, cli_root: Path):
        _setup_task_and_workflow(capsys, cli_root)
        _setup_agent(capsys, cli_root)
        run_cli(capsys, cli_root, "agent", "assign", "--task", "T-001", "--step", "development")
        rc, out, _ = run_cli(capsys, cli_root, "agent", "release", "ASG-001", "--json")
        assert rc == 0
        d = json.loads(out)
        assert d["assignment"]["status"] == "RELEASED"
        assert d["agent_id"] == "A-001"


class TestSmokeFlow:
    def test_assign_then_release_full_flow(self, capsys, cli_root: Path):
        """冒烟: agent add → task create → workflow add → assign → assignments → release。"""
        _setup_task_and_workflow(capsys, cli_root)
        _setup_agent(capsys, cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "agent", "assign", "--task", "T-001",
                             "--step", "development")
        assert rc == 0
        assert "Assigned: A-001" in out
        rc, out, _ = run_cli(capsys, cli_root, "agent", "assignments")
        assert rc == 0
        assert "1 assignments" in out
        rc, out, _ = run_cli(capsys, cli_root, "agent", "release", "ASG-001")
        assert rc == 0
        assert "AVAILABLE" in out
        with open_events(cli_root) as store:
            types = event_types(store)
            assert "agent.assignment.created" in types
            assert "agent.assignment.viewed" in types
            assert "agent.released" in types

    def test_assign_requires_argparse_task(self, capsys, cli_root: Path):
        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "agent", "assign", "--step", "development"])
        assert exc.value.code == 2  # 缺 --task → argparse 用法错误
