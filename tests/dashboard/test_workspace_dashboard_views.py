"""tests/dashboard/test_workspace_dashboard_views.py — Workspace 视图渲染测试 (Phase 6B, ADR-0017)。

覆盖: DashboardRenderer 的 workspace 视图组 (Workspace Summary/Projects/Agent
Utilization/Runtime Usage/Factory Metrics/Workspace Events) + projects/
agents_utilization/runtime_usage/workspace_events 单视图 + collector
include_workspace 模式 (默认关, workspace 模式开) + 空/大工作区渲染。

数据源 = FactorySnapshot 只读投影 (collector workspace 模式聚合, ADR-0017
决策 3); 渲染 = Rich 纯文本 (无 ANSI, 管道/CI 安全, 同 dashboard-design §3)。
"""

from __future__ import annotations

import pytest

from agents.models import AgentStatus
from events.models import EventType
from runtime.models import ExecutionStatus
from tasks.models import TaskStatus

from dashboard.collector import DashboardCollector
from dashboard.renderer import DashboardRenderer, VIEWS

from dashboard_helpers import (
    make_agent,
    make_execution,
    make_task,
    make_workflow,
    make_workflow_run,
)


def _ws_collector(collector, **kw) -> DashboardCollector:
    """以同一批 store 重新装配 collector (workspace 模式 / 自定义参数)。"""
    return collector.__class__(
        task_store=collector._task_store,
        agent_registry=collector._agent_registry,
        workflow_store=collector._workflow_store,
        runtime_store=collector._runtime_store,
        catalog_store=collector._catalog_store,
        event_store=collector._event_store,
        checkpoint_store=collector._checkpoint_store,
        projects=collector._projects,
        **kw,
    )


def _seed_multi_project(task_store, agent_registry, workflow_store, runtime_store, logger):
    """两项目数据: P-alpha (2 任务 2 执行 1 Agent 1 运行) + P-beta (1 任务 1 执行)。"""
    task_store.create(make_task("T-001", project="P-alpha", status=TaskStatus.DONE))
    task_store.create(make_task("T-002", project="P-alpha", status=TaskStatus.DEVELOPMENT))
    task_store.create(make_task("T-003", project="P-beta", status=TaskStatus.BACKLOG))
    agent_registry.register(make_agent("A-001", role="dev", status=AgentStatus.WORKING))[0]
    wf = make_workflow("feature-delivery")
    workflow_store.save_workflow(wf)
    workflow_store.save_run(make_workflow_run("WR-001", workflow=wf, task_id="T-001"))
    runtime_store.save_execution(make_execution("EX-001", task_id="T-001", status=ExecutionStatus.SUCCESS))
    runtime_store.save_execution(make_execution("EX-002", task_id="T-002", status=ExecutionStatus.FAILED))
    runtime_store.save_execution(make_execution("EX-003", task_id="T-003", status=ExecutionStatus.SUCCESS))
    logger.record(EventType.TASK_CREATED, source="test", project_id="P-alpha", task_id="T-001",
                  action="create task", result="OK")
    logger.record(EventType.TASK_CREATED, source="test", project_id="P-beta", task_id="T-003",
                  action="create task", result="OK")


class TestCollectorWorkspaceMode:
    def test_default_mode_workspace_views_empty(self, collector, task_store, runtime_store, logger):
        """默认 (include_workspace=False): 行为与成本完全不变 — 运营视图空。"""
        _seed_multi_project(task_store, collector._agent_registry,
                            collector._workflow_store, runtime_store, logger)
        s = collector.collect()
        assert s.agent_utilization.total == 0
        assert s.runtime_usage.total == 0

    def test_workspace_mode_populates_views(self, collector, task_store, agent_registry,
                                            workflow_store, runtime_store, logger):
        _seed_multi_project(task_store, agent_registry, workflow_store, runtime_store, logger)
        s = _ws_collector(collector, include_workspace=True).collect()
        assert s.agent_utilization.total == 1
        assert s.agent_utilization.items[0].agent_id == "A-001"
        assert s.runtime_usage.total == 1
        assert s.runtime_usage.items[0].runtime_id == "R-001"

    def test_workspace_mode_projects_from_tasks(self, collector, task_store):
        task_store.create(make_task("T-001", project="P-x"))
        task_store.create(make_task("T-002", project="P-y"))
        s = _ws_collector(collector, include_workspace=True).collect()
        assert s.projects.total == 2
        assert [p.id for p in s.projects.items] == ["P-x", "P-y"]

    def test_workspace_mode_recent_events_have_project(self, collector, logger):
        logger.record(EventType.TASK_CREATED, source="test", project_id="P-1", task_id="T-001",
                      action="create task", result="OK")
        s = _ws_collector(collector, include_workspace=True).collect()
        assert len(s.recent_events) == 1
        assert s.recent_events[0]["project_id"] == "P-1"
        assert s.recent_events[0]["type"] == "task.created"

    def test_workspace_mode_empty_stores(self, collector):
        s = _ws_collector(collector, include_workspace=True).collect()
        assert s.agent_utilization.total == 0
        assert s.runtime_usage.total == 0
        assert s.projects.total == 0


class TestWorkspaceViewGroup:
    def test_render_workspace_all_panels(self, collector, task_store, agent_registry,
                                         workflow_store, runtime_store, logger):
        """workspace 视图组 = 六面板同屏 (Workspace Summary/Projects/Utilization/Runtime/Metrics/Events)。"""
        _seed_multi_project(task_store, agent_registry, workflow_store, runtime_store, logger)
        out = DashboardRenderer().render(
            _ws_collector(collector, include_workspace=True).collect(), view="workspace")
        for title in ("Workspace Summary", "Projects", "Agent Utilization",
                      "Runtime Usage", "Factory Metrics", "Workspace Events"):
            assert title in out, f"缺少面板: {title}"

    def test_render_workspace_no_ansi(self, collector, task_store, agent_registry,
                                      workflow_store, runtime_store, logger):
        _seed_multi_project(task_store, agent_registry, workflow_store, runtime_store, logger)
        out = DashboardRenderer().render(
            _ws_collector(collector, include_workspace=True).collect(), view="workspace")
        assert "\x1b[" not in out

    def test_render_workspace_header_counts(self, collector, task_store, agent_registry,
                                            workflow_store, runtime_store, logger):
        _seed_multi_project(task_store, agent_registry, workflow_store, runtime_store, logger)
        out = DashboardRenderer().render(
            _ws_collector(collector, include_workspace=True).collect(), view="workspace")
        assert "AI Software Factory Workspace" in out
        assert "Projects" in out
        assert "2" in out          # 2 项目
        assert "recent events" in out

    def test_render_workspace_data_rows(self, collector, task_store, agent_registry,
                                        workflow_store, runtime_store, logger):
        _seed_multi_project(task_store, agent_registry, workflow_store, runtime_store, logger)
        out = DashboardRenderer().render(
            _ws_collector(collector, include_workspace=True).collect(), view="workspace")
        assert "P-alpha" in out and "P-beta" in out
        assert "A-001" in out
        assert "R-001" in out
        assert "EX-001" in out or "SUCCESS" in out

    def test_render_workspace_empty_factory(self, collector):
        out = DashboardRenderer().render(
            _ws_collector(collector, include_workspace=True).collect(), view="workspace")
        assert "Workspace Summary" in out
        assert "(no projects)" in out   # Projects 表占位
        assert "(no agents)" in out     # Agent Utilization 表占位
        assert "(no executions)" in out  # Runtime Usage 表占位
        assert "(no events)" in out     # Workspace Events 表占位
        assert "(none)" in out          # 头面板状态计数空 (header 口径)

    def test_render_workspace_project_events_timeline(self, collector, logger):
        logger.record(EventType.TASK_CREATED, source="test", project_id="P-1", task_id="T-001",
                      action="create task", result="OK")
        out = DashboardRenderer().render(
            _ws_collector(collector, include_workspace=True).collect(), view="workspace")
        assert "task.created" in out
        assert "P-1" in out  # Workspace Events 时间线含 Project 列


class TestProjectsView:
    def test_render_project_rows(self, collector, task_store, runtime_store):
        task_store.create(make_task("T-001", project="P-1", status=TaskStatus.DONE))
        task_store.create(make_task("T-002", project="P-1", status=TaskStatus.DEVELOPMENT))
        runtime_store.save_execution(make_execution("EX-001", task_id="T-001", status=ExecutionStatus.SUCCESS))
        runtime_store.save_execution(make_execution("EX-002", task_id="T-002", status=ExecutionStatus.FAILED))
        out = DashboardRenderer().render(
            _ws_collector(collector, include_workspace=True).collect(), view="projects")
        assert "Projects" in out
        assert "P-1" in out
        assert "2" in out       # 任务数
        assert "50.0%" in out   # success rate (1/2)

    def test_render_projects_empty(self, collector):
        out = DashboardRenderer().render(
            _ws_collector(collector, include_workspace=True).collect(), view="projects")
        assert "(no projects)" in out

    def test_render_projects_unknown_status_neutral(self, collector, task_store):
        """任务中出现但未定义的项目 → status unknown (中性色渲染不抛错)。"""
        task_store.create(make_task("T-001", project="P-orphan"))
        out = DashboardRenderer().render(
            _ws_collector(collector, include_workspace=True).collect(), view="projects")
        assert "P-orphan" in out
        assert "unknown" in out

    def test_render_projects_language_and_status(self, collector, task_store):
        task_store.create(make_task("T-001", project="P-1"))
        out = DashboardRenderer().render(
            _ws_collector(collector, include_workspace=True).collect(), view="projects")
        assert "0.0%" in out  # 无执行 → 0.0%


class TestAgentUtilizationView:
    def test_render_agent_rows(self, collector, task_store, agent_registry, logger):
        task_store.create(make_task("T-001", project="P-1"))
        agent_registry.register(make_agent("A-001", role="dev", status=AgentStatus.WORKING))[0]
        logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-001")
        logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-001")
        logger.record(EventType.ASSIGNMENT_COMPLETED, source="test", agent_id="A-001", task_id="T-001")
        logger.record(EventType.ASSIGNMENT_FAILED, source="test", agent_id="A-001", task_id="T-001")
        out = DashboardRenderer().render(
            _ws_collector(collector, include_workspace=True).collect(), view="agents_utilization")
        assert "Agent Utilization" in out
        assert "A-001" in out
        assert "dev" in out
        assert "P-1" in out          # 参与项目列
        assert "2" in out            # assignments
        assert "50.0%" in out        # success_rate 1/2

    def test_render_agent_utilization_empty(self, collector):
        out = DashboardRenderer().render(
            _ws_collector(collector, include_workspace=True).collect(), view="agents_utilization")
        assert "(no agents)" in out

    def test_render_agent_utilization_registered_inactive(self, collector, agent_registry):
        """已注册但无活动 → 0 指标行渲染 (注册表兜底)。"""
        agent_registry.register(make_agent("A-001", role="dev"))[0]
        out = DashboardRenderer().render(
            _ws_collector(collector, include_workspace=True).collect(), view="agents_utilization")
        assert "A-001" in out
        assert "0" in out


class TestRuntimeUsageView:
    def test_render_runtime_rows(self, collector, task_store, runtime_store):
        task_store.create(make_task("T-001", project="P-1"))
        runtime_store.save_execution(make_execution("EX-001", task_id="T-001", runtime_id="R-hermes",
                                                    status=ExecutionStatus.SUCCESS))
        runtime_store.save_execution(make_execution("EX-002", task_id="T-001", runtime_id="R-hermes",
                                                    status=ExecutionStatus.FAILED))
        out = DashboardRenderer().render(
            _ws_collector(collector, include_workspace=True).collect(), view="runtime_usage")
        assert "Runtime Usage" in out
        assert "R-hermes" in out
        assert "2" in out       # execution_count
        assert "50.0%" in out   # success_rate
        assert "P-1" in out     # projects 列

    def test_render_runtime_usage_empty(self, collector):
        out = DashboardRenderer().render(
            _ws_collector(collector, include_workspace=True).collect(), view="runtime_usage")
        assert "(no executions)" in out

    def test_render_runtime_usage_unknown(self, collector, runtime_store):
        """runtime_id 空 → 'unknown' 行渲染。"""
        runtime_store.save_execution(make_execution("EX-001", task_id="T-001", runtime_id="",
                                                    status=ExecutionStatus.SUCCESS))
        out = DashboardRenderer().render(
            _ws_collector(collector, include_workspace=True).collect(), view="runtime_usage")
        assert "unknown" in out


class TestWorkspaceEventsView:
    def test_render_timeline_with_project_column(self, collector, logger):
        logger.record(EventType.TASK_CREATED, source="test", project_id="P-1", task_id="T-001",
                      action="create task", result="OK")
        out = DashboardRenderer().render(
            _ws_collector(collector, include_workspace=True).collect(), view="workspace_events")
        assert "Workspace Events" in out
        assert "task.created" in out
        assert "P-1" in out

    def test_render_timeline_empty(self, collector):
        out = DashboardRenderer().render(
            _ws_collector(collector, include_workspace=True).collect(), view="workspace_events")
        assert "(no events)" in out

    def test_render_timeline_limit(self, collector, logger):
        for i in range(15):
            logger.record(EventType.TASK_CREATED, source="test", project_id="P-1",
                          action="create task", result="OK")
        s = _ws_collector(collector, include_workspace=True, recent_limit=5).collect()
        out = DashboardRenderer().render(s, view="workspace_events")
        assert out.count("task.created") == 5  # recent_limit 生效

    def test_render_timeline_global_events(self, collector, logger):
        """无 project_id 的全局事件也展示 (project 列显示 '-')。"""
        logger.record(EventType.SYSTEM_INIT, source="cli", action="init factory", result="OK")
        out = DashboardRenderer().render(
            _ws_collector(collector, include_workspace=True).collect(), view="workspace_events")
        assert "system.init" in out
        assert "-" in out


class TestWorkspaceViewsRegistry:
    def test_new_views_in_VIEWS(self):
        for view in ("workspace", "projects", "agents_utilization", "runtime_usage",
                     "workspace_events"):
            assert view in VIEWS

    def test_all_new_views_render_empty(self, collector):
        """4 个新单视图 + workspace 组在空工厂可独立渲染不抛错。"""
        s = _ws_collector(collector, include_workspace=True).collect()
        for view in ("workspace", "projects", "agents_utilization", "runtime_usage",
                     "workspace_events"):
            out = DashboardRenderer().render(s, view=view)
            assert isinstance(out, str)
            assert out.strip()

    def test_workspace_view_in_all_mode(self, collector, task_store):
        """'all' 视图含 Projects (Phase 6A), 不含 workspace 组 (默认行为不变)。"""
        task_store.create(make_task("T-001", project="P-1"))
        out = DashboardRenderer().render(
            _ws_collector(collector, include_workspace=True).collect(), view="all")
        assert "Projects" in out
        assert "Workspace Summary" not in out
        assert "P-1" in out


class TestWorkspaceBigDataRender:
    def test_render_large_workspace(self, collector, task_store, agent_registry, runtime_store, logger):
        """大工作区渲染: 40 项目 × 5 任务/执行 + 事件, 视图渲染不抛错且计数正确。"""
        for p in range(40):
            pid = f"P-{p:02d}"
            for i in range(5):
                tid = f"T-{p:02d}-{i}"
                task_store.create(make_task(tid, project=pid,
                                            status=TaskStatus.DONE if i % 2 == 0 else TaskStatus.BACKLOG))
                runtime_store.save_execution(make_execution(
                    f"EX-{p:02d}-{i}", task_id=tid,
                    status=ExecutionStatus.SUCCESS if i % 2 == 0 else ExecutionStatus.FAILED))
        agent_registry.register(make_agent("A-001", role="dev"))[0]
        for i in range(300):
            logger.record(EventType.TASK_CREATED, source="test", project_id="P-00",
                          action="create task", result="OK")
        s = _ws_collector(collector, include_workspace=True).collect()
        assert s.projects.total == 40
        assert s.tasks.total == 200
        assert s.executions.total == 200
        out = DashboardRenderer().render(s, view="workspace")
        assert "Workspace Summary" in out
        assert "P-00" in out
        assert "200" in out
        out_util = DashboardRenderer().render(s, view="agents_utilization")
        assert "A-001" in out_util
