"""tests/dashboard/test_workspace_cli.py — CLI --workspace 命令测试 (Phase 6B, ADR-0017)。

覆盖: dashboard --workspace / metrics --workspace / event logs --workspace 的
人类可读输出 + --json 结构 + workspace.dashboard/metrics/events.viewed 审计事件
+ 空/大工作区 + 只读铁律 (命令唯一副作用 = 审计事件)。

项目集推导 (无 workspace.yaml): 任务 project 值 ∪ 事件 project_id 值 — 兼容
Phase 5A 无 workspace 场景 (dashboard/metrics 同款只读兜底)。
"""

from __future__ import annotations

import json
from pathlib import Path

from agents.models import AgentStatus
from agents.registry import AgentRegistry
from agents.store import AgentStore
from events.logger import EventLogger
from events.store import EventStore
from runtime.models import ExecutionStatus
from runtime.store import RuntimeStore
from tasks.models import TaskStatus
from tasks.store import TaskStore
from workflows.store import WorkflowStore

from cli_helpers import event_types, open_events, run_cli

from dashboard_helpers import (
    make_agent,
    make_execution,
    make_task,
    make_workflow,
    make_workflow_run,
)


def _seed_multi_project(cli_root: Path):
    """两项目数据 (直写 store + 事件库, 不经 CLI — 保持测试确定性)。"""
    cli_root.mkdir(parents=True, exist_ok=True)
    ts = TaskStore(cli_root / "tasks")
    ts.create(make_task("T-001", project="P-alpha", status=TaskStatus.DONE))
    ts.create(make_task("T-002", project="P-alpha", status=TaskStatus.DEVELOPMENT))
    ts.create(make_task("T-003", project="P-beta", status=TaskStatus.BACKLOG))
    reg = AgentRegistry(AgentStore(cli_root / "agents"))
    reg.register(make_agent("A-001", role="dev", status=AgentStatus.WORKING))[0]
    ws = WorkflowStore(cli_root / "workflows")
    wf = make_workflow("feature-delivery")
    ws.save_workflow(wf)
    ws.save_run(make_workflow_run("WR-001", workflow=wf, task_id="T-001"))
    rs = RuntimeStore(cli_root / "runtimes")
    rs.save_execution(make_execution("EX-001", task_id="T-001", runtime_id="R-hermes",
                                     status=ExecutionStatus.SUCCESS))
    rs.save_execution(make_execution("EX-002", task_id="T-002", runtime_id="R-hermes",
                                     status=ExecutionStatus.FAILED))
    rs.save_execution(make_execution("EX-003", task_id="T-003", runtime_id="R-hermes",
                                     status=ExecutionStatus.SUCCESS))
    store = EventStore(cli_root / "factory.db")
    try:
        logger = EventLogger(store)
        logger.record("task.created", source="cli", project_id="P-alpha", task_id="T-001",
                      action="create task", result="OK")
        logger.record("task.created", source="cli", project_id="P-beta", task_id="T-003",
                      action="create task", result="OK")
    finally:
        store.close()


class TestDashboardWorkspaceOutput:
    def test_dashboard_workspace_exit_zero(self, cli_root, capsys):
        rc, out, err = run_cli(capsys, cli_root, "dashboard", "--workspace")
        assert rc == 0, err
        assert out

    def test_dashboard_workspace_panels(self, cli_root, capsys):
        _seed_multi_project(cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "dashboard", "--workspace")
        assert rc == 0
        for title in ("Workspace Summary", "Projects", "Agent Utilization",
                      "Runtime Usage", "Factory Metrics", "Workspace Events"):
            assert title in out, f"缺少面板: {title}"

    def test_dashboard_workspace_rows(self, cli_root, capsys):
        _seed_multi_project(cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "dashboard", "--workspace")
        assert rc == 0
        assert "P-alpha" in out and "P-beta" in out
        assert "A-001" in out
        assert "R-hermes" in out
        assert "task.created" in out

    def test_dashboard_workspace_empty(self, cli_root, capsys):
        rc, out, _ = run_cli(capsys, cli_root, "dashboard", "--workspace")
        assert rc == 0
        assert "Workspace Summary" in out
        assert "(no projects)" in out

    def test_dashboard_view_workspace_no_flag(self, cli_root, capsys):
        """--view workspace 不传 --workspace 也渲染 (自动启用 workspace 聚合)。"""
        _seed_multi_project(cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "dashboard", "--view", "workspace")
        assert rc == 0
        assert "Workspace Summary" in out

    def test_dashboard_view_agents_utilization(self, cli_root, capsys):
        _seed_multi_project(cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "dashboard", "--view", "agents_utilization")
        assert rc == 0
        assert "Agent Utilization" in out
        assert "A-001" in out

    def test_dashboard_view_runtime_usage(self, cli_root, capsys):
        _seed_multi_project(cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "dashboard", "--view", "runtime_usage")
        assert rc == 0
        assert "Runtime Usage" in out
        assert "R-hermes" in out

    def test_dashboard_view_workspace_events(self, cli_root, capsys):
        _seed_multi_project(cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "dashboard", "--view", "workspace_events")
        assert rc == 0
        assert "Workspace Events" in out
        assert "task.created" in out


class TestDashboardWorkspaceJson:
    def test_dashboard_workspace_json_structure(self, cli_root, capsys):
        _seed_multi_project(cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "dashboard", "--workspace", "--json")
        assert rc == 0
        data = json.loads(out)
        assert data["ok"] is True
        assert data["workspace"] is True
        assert data["view"] == "workspace"
        assert "event_seq" in data

    def test_dashboard_workspace_json_snapshot(self, cli_root, capsys):
        _seed_multi_project(cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "dashboard", "--workspace", "--json")
        snap = json.loads(out)["snapshot"]
        assert snap["projects"]["total"] == 2
        assert snap["agent_utilization"]["total"] == 1
        assert snap["runtime_usage"]["total"] == 1
        assert snap["tasks"]["total"] == 3

    def test_dashboard_workspace_json_project_rows(self, cli_root, capsys):
        _seed_multi_project(cli_root)
        snap = json.loads(run_cli(capsys, cli_root, "dashboard", "--workspace", "--json")[1])["snapshot"]
        by_id = {p["id"]: p for p in snap["projects"]["items"]}
        assert by_id["P-alpha"]["task_count"] == 2
        assert by_id["P-alpha"]["execution_count"] == 2
        assert by_id["P-alpha"]["success_rate"] == 0.5
        assert by_id["P-beta"]["task_count"] == 1
        assert by_id["P-beta"]["execution_count"] == 1
        assert by_id["P-beta"]["success_rate"] == 1.0

    def test_dashboard_workspace_json_agent_utilization(self, cli_root, capsys):
        _seed_multi_project(cli_root)
        snap = json.loads(run_cli(capsys, cli_root, "dashboard", "--workspace", "--json")[1])["snapshot"]
        au = snap["agent_utilization"]["items"][0]
        assert au["agent_id"] == "A-001"
        # 无 assignment 事件 → 无法按 task_id → task.project 归属任何项目
        # (零分配 agent 的 projects 为空, 与 assignments == 0 自洽, ADR-0017 决策 2)。
        assert au["projects"] == []
        assert au["assignments"] == 0
        assert au["success_rate"] == 0.0

    def test_dashboard_workspace_json_runtime_usage(self, cli_root, capsys):
        _seed_multi_project(cli_root)
        snap = json.loads(run_cli(capsys, cli_root, "dashboard", "--workspace", "--json")[1])["snapshot"]
        ru = snap["runtime_usage"]["items"][0]
        assert ru["runtime_id"] == "R-hermes"
        assert ru["execution_count"] == 3
        assert ru["success"] == 2
        assert ru["failed"] == 1
        assert ru["success_rate"] == 2 / 3
        assert ru["projects"] == ["P-alpha", "P-beta"]

    def test_dashboard_workspace_json_empty(self, cli_root, capsys):
        rc, out, _ = run_cli(capsys, cli_root, "dashboard", "--workspace", "--json")
        assert rc == 0
        snap = json.loads(out)["snapshot"]
        assert snap["projects"]["total"] == 0
        assert snap["agent_utilization"]["total"] == 0


class TestMetricsWorkspace:
    def test_metrics_workspace_exit_zero(self, cli_root, capsys):
        rc, out, err = run_cli(capsys, cli_root, "metrics", "--workspace")
        assert rc == 0, err
        assert out

    def test_metrics_workspace_report(self, cli_root, capsys):
        """人类可读: 项目对比报告 (format_workspace_comparison 经 CLI 输出)。"""
        _seed_multi_project(cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "metrics", "--workspace")
        assert rc == 0
        assert "Workspace Metrics" in out
        assert "Project Comparison" in out
        assert "P-alpha" in out and "P-beta" in out
        assert "Totals (all projects)" in out

    def test_metrics_workspace_json_structure(self, cli_root, capsys):
        _seed_multi_project(cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "metrics", "--workspace", "--json")
        assert rc == 0
        data = json.loads(out)
        assert data["ok"] is True
        assert data["workspace"] is True
        assert data["comparison"]["total"] == 2
        assert data["comparison"]["totals"]["project"] == "*"

    def test_metrics_workspace_json_rows(self, cli_root, capsys):
        _seed_multi_project(cli_root)
        comp = json.loads(run_cli(capsys, cli_root, "metrics", "--workspace", "--json")[1])["comparison"]
        by_id = {p["project"]: p for p in comp["projects"]}
        assert by_id["P-alpha"]["tasks_total"] == 2
        assert by_id["P-alpha"]["tasks_completed"] == 1
        assert by_id["P-alpha"]["execution_count"] == 2
        assert by_id["P-alpha"]["execution_success"] == 1
        assert by_id["P-alpha"]["execution_success_rate"] == 0.5
        assert by_id["P-beta"]["execution_count"] == 1
        assert by_id["P-beta"]["execution_success_rate"] == 1.0

    def test_metrics_workspace_json_totals(self, cli_root, capsys):
        _seed_multi_project(cli_root)
        t = json.loads(run_cli(capsys, cli_root, "metrics", "--workspace", "--json")[1])["comparison"]["totals"]
        assert t["tasks_total"] == 3
        assert t["execution_count"] == 3
        assert t["execution_success"] == 2
        assert t["execution_success_rate"] == 2 / 3

    def test_metrics_workspace_empty(self, cli_root, capsys):
        rc, out, _ = run_cli(capsys, cli_root, "metrics", "--workspace", "--json")
        assert rc == 0
        comp = json.loads(out)["comparison"]
        assert comp["total"] == 0
        assert comp["totals"]["tasks_total"] == 0

    def test_metrics_without_workspace_regression(self, cli_root, capsys):
        """metrics (无 --workspace) 仍输出六域报告 (Phase 5B 行为不变)。"""
        rc, out, err = run_cli(capsys, cli_root, "metrics")
        assert rc == 0, err
        assert "Factory Metrics" in out


class TestWorkspaceAuditEvents:
    def test_dashboard_workspace_emits_viewed(self, cli_root, capsys):
        _seed_multi_project(cli_root)
        run_cli(capsys, cli_root, "dashboard", "--workspace")
        store = open_events(cli_root)
        try:
            types = event_types(store)
            viewed = [e for e in store.query()
                      if e.type.value == "workspace.dashboard.viewed"][-1]
        finally:
            store.close()
        assert types.count("workspace.dashboard.viewed") == 1
        assert viewed.result == "OK"
        assert viewed.stage == "viewed"
        assert viewed.payload["projects_total"] == 2
        assert viewed.payload["tasks_total"] == 3
        assert viewed.payload["agents_total"] == 1
        assert viewed.payload["executions_total"] == 3
        assert viewed.payload["execution_success"] == 2
        assert viewed.payload["runtimes_used"] == 1
        assert viewed.payload["view"] == "workspace"
        assert viewed.payload["workspace"] is True

    def test_dashboard_view_workspace_no_flag_emits_dashboard_viewed(self, cli_root, capsys):
        """--view workspace 无 --workspace 标志 → dashboard.viewed (只读审计按标志区分)。"""
        _seed_multi_project(cli_root)
        run_cli(capsys, cli_root, "dashboard", "--view", "workspace")
        store = open_events(cli_root)
        try:
            types = event_types(store)
        finally:
            store.close()
        assert types.count("dashboard.viewed") == 1
        assert "workspace.dashboard.viewed" not in types

    def test_metrics_workspace_emits_viewed(self, cli_root, capsys):
        _seed_multi_project(cli_root)
        run_cli(capsys, cli_root, "metrics", "--workspace")
        store = open_events(cli_root)
        try:
            viewed = [e for e in store.query()
                      if e.type.value == "workspace.metrics.viewed"][-1]
        finally:
            store.close()
        assert viewed.result == "OK"
        assert viewed.payload["projects_total"] == 2
        assert viewed.payload["tasks_total"] == 3
        assert viewed.payload["tasks_completed"] == 1
        assert viewed.payload["executions_total"] == 3
        assert viewed.payload["executions_success"] == 2

    def test_metrics_without_workspace_emits_metrics_viewed(self, cli_root, capsys):
        _seed_multi_project(cli_root)
        run_cli(capsys, cli_root, "metrics")
        store = open_events(cli_root)
        try:
            types = event_types(store)
        finally:
            store.close()
        assert types.count("metrics.viewed") == 1
        assert "workspace.metrics.viewed" not in types


class TestEventLogsWorkspace:
    def test_event_logs_workspace_exit_zero(self, cli_root, capsys):
        rc, out, err = run_cli(capsys, cli_root, "event", "logs", "--workspace")
        assert rc == 0, err
        assert out

    def test_event_logs_workspace_cross_project(self, cli_root, capsys):
        """跨项目时间线: 两项目事件同屏, 按 seq 倒序。"""
        _seed_multi_project(cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "event", "logs", "--workspace")
        assert rc == 0
        assert "P-alpha" in out and "P-beta" in out
        assert "2 events" in out

    def test_event_logs_workspace_json_desc_order(self, cli_root, capsys):
        _seed_multi_project(cli_root)
        data = json.loads(run_cli(capsys, cli_root, "event", "logs", "--workspace", "--json")[1])
        assert data["workspace"] is True
        assert data["count"] == 2
        events = data["events"]
        assert [e["seq"] for e in events] == sorted((e["seq"] for e in events), reverse=True)
        assert {e["project_id"] for e in events} == {"P-alpha", "P-beta"}

    def test_event_logs_workspace_limit(self, cli_root, capsys):
        _seed_multi_project(cli_root)
        data = json.loads(run_cli(capsys, cli_root, "event", "logs", "--workspace",
                                  "--limit", "1", "--json")[1])
        assert data["count"] == 1
        assert len(data["events"]) == 1

    def test_event_logs_workspace_emits_viewed(self, cli_root, capsys):
        _seed_multi_project(cli_root)
        run_cli(capsys, cli_root, "event", "logs", "--workspace")
        store = open_events(cli_root)
        try:
            viewed = [e for e in store.query()
                      if e.type.value == "workspace.events.viewed"][-1]
            types = event_types(store)
        finally:
            store.close()
        assert types.count("workspace.events.viewed") == 1
        assert viewed.payload["count"] == 2
        assert viewed.payload["limit"] == 20

    def test_event_logs_without_workspace_regression(self, cli_root, capsys):
        """event logs (无 --workspace) 仍发 system.logs_viewed (Phase 2 行为不变)。"""
        _seed_multi_project(cli_root)
        run_cli(capsys, cli_root, "event", "logs")
        store = open_events(cli_root)
        try:
            types = event_types(store)
        finally:
            store.close()
        assert types.count("system.logs_viewed") == 1
        assert "workspace.events.viewed" not in types

    def test_event_logs_workspace_empty(self, cli_root, capsys):
        rc, out, _ = run_cli(capsys, cli_root, "event", "logs", "--workspace", "--json")
        assert rc == 0
        assert json.loads(out)["count"] == 0


class TestWorkspaceReadOnly:
    def test_dashboard_workspace_read_only(self, cli_root, capsys):
        """只读铁律: dashboard --workspace 只追加 workspace.dashboard.viewed。"""
        _seed_multi_project(cli_root)
        store = open_events(cli_root)
        try:
            before = store.count()
        finally:
            store.close()
        rc, out, _ = run_cli(capsys, cli_root, "dashboard", "--workspace")
        assert rc == 0
        store = open_events(cli_root)
        try:
            assert store.count() == before + 1
            assert event_types(store)[-1] == "workspace.dashboard.viewed"
        finally:
            store.close()
        # 业务状态不变
        ts = TaskStore(cli_root / "tasks")
        assert ts.get("T-001").status is TaskStatus.DONE
        rs = RuntimeStore(cli_root / "runtimes")
        assert [e.status.value for e in rs.list_executions()] == ["SUCCESS", "FAILED", "SUCCESS"]

    def test_metrics_workspace_read_only(self, cli_root, capsys):
        _seed_multi_project(cli_root)
        store = open_events(cli_root)
        try:
            before = store.count()
        finally:
            store.close()
        rc, out, _ = run_cli(capsys, cli_root, "metrics", "--workspace")
        assert rc == 0
        store = open_events(cli_root)
        try:
            assert store.count() == before + 1
            assert event_types(store)[-1] == "workspace.metrics.viewed"
        finally:
            store.close()


class TestWorkspaceLargeCli:
    def test_dashboard_workspace_large_json(self, cli_root, capsys):
        """大工作区: 30 项目 → dashboard --workspace 计数正确。"""
        cli_root.mkdir(parents=True, exist_ok=True)
        ts = TaskStore(cli_root / "tasks")
        rs = RuntimeStore(cli_root / "runtimes")
        for p in range(30):
            pid = f"P-{p:02d}"
            for i in range(4):
                tid = f"T-{p:02d}-{i}"
                ts.create(make_task(tid, project=pid,
                                    status=TaskStatus.DONE if i % 2 == 0 else TaskStatus.BACKLOG))
                rs.save_execution(make_execution(
                    f"EX-{p:02d}-{i}", task_id=tid,
                    status=ExecutionStatus.SUCCESS if i % 2 == 0 else ExecutionStatus.FAILED))
        rc, out, _ = run_cli(capsys, cli_root, "dashboard", "--workspace", "--json")
        assert rc == 0
        snap = json.loads(out)["snapshot"]
        assert snap["projects"]["total"] == 30
        assert snap["tasks"]["total"] == 120
        assert snap["executions"]["total"] == 120
        assert snap["executions"]["success"] == 60

    def test_metrics_workspace_large_json(self, cli_root, capsys):
        cli_root.mkdir(parents=True, exist_ok=True)
        ts = TaskStore(cli_root / "tasks")
        rs = RuntimeStore(cli_root / "runtimes")
        for p in range(30):
            pid = f"P-{p:02d}"
            for i in range(4):
                tid = f"T-{p:02d}-{i}"
                ts.create(make_task(tid, project=pid,
                                    status=TaskStatus.DONE if i % 2 == 0 else TaskStatus.BACKLOG))
                rs.save_execution(make_execution(
                    f"EX-{p:02d}-{i}", task_id=tid,
                    status=ExecutionStatus.SUCCESS if i % 2 == 0 else ExecutionStatus.FAILED))
        rc, out, _ = run_cli(capsys, cli_root, "metrics", "--workspace", "--json")
        assert rc == 0
        comp = json.loads(out)["comparison"]
        assert comp["total"] == 30
        assert comp["totals"]["tasks_total"] == 120
        assert comp["totals"]["execution_count"] == 120
        assert comp["totals"]["execution_success"] == 60
        assert comp["totals"]["execution_success_rate"] == 0.5
