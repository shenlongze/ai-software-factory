"""tests/dashboard/test_cli_dashboard.py — factory dashboard 命令测试 (输出 / --json / 事件 / 只读)。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.models import AgentStatus
from agents.registry import AgentRegistry
from agents.store import AgentStore
from runtime.models import ExecutionStatus
from runtime.store import RuntimeStore
from tasks.models import TaskStatus

from cli.main import main
from cli_helpers import event_types, open_events, run_cli

from dashboard_helpers import (
    make_agent,
    make_execution,
    make_task,
    make_workflow,
    make_workflow_run,
)
from tasks.store import TaskStore
from workflows.store import WorkflowStore


def _seed_factory(cli_root: Path):
    """预置数据 (直写 store, 不经 CLI — 保持测试确定性)。"""
    ts = TaskStore(cli_root / "tasks")
    ts.create(make_task("T-001", status=TaskStatus.DEVELOPMENT))
    ts.create(make_task("T-002", status=TaskStatus.DONE))
    reg = AgentRegistry(AgentStore(cli_root / "agents"))
    reg.register(make_agent("A-001", role="dev", status=AgentStatus.AVAILABLE))[0]
    ws = WorkflowStore(cli_root / "workflows")
    wf = make_workflow("feature-delivery")
    ws.save_workflow(wf)
    ws.save_run(make_workflow_run("WR-001", workflow=wf, task_id="T-001"))
    rs = RuntimeStore(cli_root / "runtimes")
    rs.save_execution(make_execution("EX-001", status=ExecutionStatus.SUCCESS))
    rs.save_execution(make_execution("EX-002", status=ExecutionStatus.FAILED))


class TestCliDashboardOutput:
    def test_dashboard_exit_zero(self, cli_root, capsys):
        rc, out, err = run_cli(capsys, cli_root, "dashboard")
        assert rc == 0, err
        assert out

    def test_dashboard_output_contains_views(self, cli_root, capsys):
        _seed_factory(cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "dashboard")
        assert rc == 0
        for title in ("Overview", "Tasks", "Agents", "Workflows", "Executions",
                      "Recovery", "Recent Events"):
            assert title in out

    def test_dashboard_output_counts(self, cli_root, capsys):
        _seed_factory(cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "dashboard")
        assert rc == 0
        assert "T-001" in out and "T-002" in out
        assert "A-001" in out
        assert "WR-001" in out
        assert "EX-001" in out and "EX-002" in out

    def test_dashboard_single_view(self, cli_root, capsys):
        _seed_factory(cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "dashboard", "--view", "tasks")
        assert rc == 0
        assert "Tasks" in out
        assert "Overview" not in out  # 单视图不含总览
        assert "T-001" in out

    def test_dashboard_view_invalid_exit_2(self, cli_root, capsys):
        rc, out, err = run_cli(capsys, cli_root, "dashboard", "--view", "bogus")
        assert rc == 2
        assert "invalid view" in err

    def test_dashboard_empty_factory(self, cli_root, capsys):
        rc, out, _ = run_cli(capsys, cli_root, "dashboard")
        assert rc == 0
        assert "Overview" in out
        assert "(no tasks)" in out

    def test_dashboard_limit(self, cli_root, capsys):
        from events.logger import EventLogger
        from events.store import EventStore

        cli_root.mkdir(parents=True, exist_ok=True)  # 先建根目录 (SQLite 需父目录存在)
        store = EventStore(cli_root / "factory.db")
        try:
            logger = EventLogger(store)
            for i in range(15):
                logger.record("task.created", source="test", action="create task", result="OK")
        finally:
            store.close()
        rc, out, _ = run_cli(capsys, cli_root, "dashboard", "--limit", "5")
        assert rc == 0
        assert out.count("task.created") == 5


class TestCliDashboardJson:
    def test_dashboard_json_structure(self, cli_root, capsys):
        _seed_factory(cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "dashboard", "--json")
        assert rc == 0
        data = json.loads(out)
        assert data["ok"] is True
        assert data["view"] == "all"
        assert "snapshot" in data
        assert "event_seq" in data

    def test_dashboard_json_counts(self, cli_root, capsys):
        _seed_factory(cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "dashboard", "--json")
        assert rc == 0
        snap = json.loads(out)["snapshot"]
        assert snap["tasks"]["total"] == 2
        assert snap["tasks"]["by_status"]["DEVELOPMENT"] == 1
        assert snap["agents"]["total"] == 1
        assert snap["workflows"]["runs_total"] == 1
        assert snap["executions"]["total"] == 2
        assert snap["executions"]["success_rate"] == 0.5
        assert snap["executions"]["failed"] == 1

    def test_dashboard_json_items(self, cli_root, capsys):
        _seed_factory(cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "dashboard", "--json")
        snap = json.loads(out)["snapshot"]
        assert len(snap["tasks"]["items"]) == 2
        assert snap["tasks"]["items"][0]["id"] == "T-001"
        assert snap["executions"]["items"][0]["result"] is None

    def test_dashboard_json_single_view(self, cli_root, capsys):
        _seed_factory(cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "dashboard", "--view", "agents", "--json")
        data = json.loads(out)
        assert data["view"] == "agents"
        assert data["snapshot"]["agents"]["total"] == 1


class TestCliDashboardEvents:
    def test_dashboard_emits_viewed_event(self, cli_root, capsys):
        rc, out, _ = run_cli(capsys, cli_root, "dashboard")
        assert rc == 0
        store = open_events(cli_root)
        try:
            types = event_types(store)
        finally:
            store.close()
        assert types.count("dashboard.viewed") == 1

    def test_dashboard_event_payload_counts(self, cli_root, capsys):
        _seed_factory(cli_root)
        run_cli(capsys, cli_root, "dashboard")
        store = open_events(cli_root)
        try:
            viewed = [e for e in store.query() if e.type.value == "dashboard.viewed"][-1]
        finally:
            store.close()
        assert viewed.result == "OK"
        assert viewed.stage == "viewed"
        assert viewed.payload["tasks_total"] == 2
        assert viewed.payload["agents_total"] == 1
        assert viewed.payload["execution_success"] == 1
        assert viewed.payload["execution_failed"] == 1
        assert viewed.payload["view"] == "all"

    def test_dashboard_event_project_filter(self, cli_root, capsys):
        _seed_factory(cli_root)
        run_cli(capsys, cli_root, "dashboard", "--project", "P-x")
        store = open_events(cli_root)
        try:
            viewed = [e for e in store.query() if e.type.value == "dashboard.viewed"][-1]
        finally:
            store.close()
        assert viewed.project_id == "P-x"

    def test_dashboard_read_only(self, cli_root, capsys):
        """只读铁律: dashboard 只追加 dashboard.viewed 事件, 不改任何业务状态。"""
        _seed_factory(cli_root)
        store = open_events(cli_root)
        try:
            before = store.count()
        finally:
            store.close()
        rc, out, _ = run_cli(capsys, cli_root, "dashboard")
        assert rc == 0
        store = open_events(cli_root)
        try:
            assert store.count() == before + 1  # 仅 dashboard.viewed
            types = event_types(store)
            assert types[-1] == "dashboard.viewed"
        finally:
            store.close()
        # 业务状态不变: 任务仍 DEVELOPMENT, 执行仍 SUCCESS/FAILED
        ts = TaskStore(cli_root / "tasks")
        assert ts.get("T-001").status is TaskStatus.DEVELOPMENT
        rs = RuntimeStore(cli_root / "runtimes")
        assert [e.status.value for e in rs.list_executions()] == ["SUCCESS", "FAILED"]


class TestCliDashboardValidation:
    def test_dashboard_validation_counts_in_json(self, cli_root, capsys):
        from events.logger import EventLogger
        from events.store import EventStore
        from dashboard_helpers import make_validation_events

        cli_root.mkdir(parents=True, exist_ok=True)  # 先建根目录 (SQLite 需父目录存在)
        store = EventStore(cli_root / "factory.db")
        try:
            make_validation_events(EventLogger(store), results=("PASS", "FAIL", "SKIP"))
        finally:
            store.close()
        rc, out, _ = run_cli(capsys, cli_root, "dashboard", "--json")
        assert rc == 0
        val = json.loads(out)["snapshot"]["metrics"]["validation"]
        assert val["pass_count"] == 1
        assert val["fail_count"] == 1
        assert val["skip_count"] == 1
