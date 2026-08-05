"""tests/dashboard/test_dashboard_renderer.py — DashboardRenderer (Rich) 输出测试。

覆盖: 纯文本无 ANSI / 六视图 / 各视图内容 / 空工厂 / 非法视图 / 大数据 / 颜色语义。
"""

from __future__ import annotations

import pytest

from agents.models import AgentStatus
from events.models import EventType
from runtime.models import ExecutionStatus
from tasks.models import TaskStatus
from workflows.models import WorkflowStatus

from dashboard.models import FactorySnapshot
from dashboard.renderer import DashboardRenderer, VIEWS
from dashboard import views

from dashboard_helpers import (
    make_agent,
    make_checkpoint,
    make_execution,
    make_result,
    make_task,
    make_validation_events,
    make_workflow,
    make_workflow_run,
)


def _snapshot(collector) -> FactorySnapshot:
    return collector.collect()


class TestRendererBasics:
    def test_render_returns_plain_text_no_ansi(self, collector, task_store):
        task_store.create(make_task("T-001"))
        out = DashboardRenderer().render(_snapshot(collector))
        assert "\x1b[" not in out  # 无 ANSI 转义码 (管道/CI 安全)
        assert isinstance(out, str)
        assert out.strip()

    def test_render_all_views_present(self, collector, task_store, agent_registry,
                                      workflow_store, runtime_store, checkpoint_store, logger):
        task_store.create(make_task("T-001", status=TaskStatus.DEVELOPMENT))
        agent_registry.register(make_agent("A-001"))[0]
        wf = make_workflow("feature-delivery")
        workflow_store.save_workflow(wf)
        workflow_store.save_run(make_workflow_run("WR-001", workflow=wf, task_id="T-001"))
        runtime_store.save_execution(make_execution("EX-001", status=ExecutionStatus.SUCCESS))
        checkpoint_store.save(make_checkpoint("T-001"))
        logger.record(EventType.TASK_CREATED, source="test", task_id="T-001", result="OK")

        out = DashboardRenderer().render(_snapshot(collector))
        for title in ("Overview", "Tasks", "Agents", "Workflows", "Executions",
                      "Recovery", "Recent Events"):
            assert title in out, f"缺少视图: {title}"

    def test_render_empty_factory(self, collector):
        out = DashboardRenderer().render(_snapshot(collector))
        assert "Overview" in out
        assert "(no tasks)" in out
        assert "(no agents)" in out
        assert "(no executions)" in out
        assert "(no checkpoints)" in out

    def test_render_invalid_view_raises(self, collector):
        with pytest.raises(ValueError, match="unknown dashboard view"):
            DashboardRenderer().render(_snapshot(collector), view="nope")

    def test_view_names_exported(self):
        # Phase 5B 新增第八视图 metrics (ADR-0015); Phase 6A 新增第九视图 projects
        # (ADR-0016); Phase 6B 新增 workspace 组四视图 workspace/agents_utilization/
        # runtime_usage/workspace_events (ADR-0017); Phase 6C 新增第十四视图 git
        # (ADR-0018); Phase 6D 新增第十五视图 change (ADR-0019) — 精确集合断言随
        # 视图集扩展最小化更新 (行为观察点, 非 API; 见 ADR-0014 冲突消解)。
        assert set(VIEWS) == {
            "overview", "tasks", "agents", "workflows", "executions", "recovery",
            "catalog", "metrics", "projects", "workspace", "agents_utilization",
            "runtime_usage", "workspace_events", "git", "change",
        }

    def test_render_views_iterates_all_single_views(self, collector):
        """每个单视图都能独立渲染不抛错。"""
        for view in VIEWS:
            out = DashboardRenderer().render(_snapshot(collector), view=view)
            assert isinstance(out, str)


class TestViews:
    def test_render_overview_header_counts(self, collector, task_store, runtime_store):
        task_store.create(make_task("T-001", status=TaskStatus.DONE))
        task_store.create(make_task("T-002", status=TaskStatus.DEVELOPMENT))
        runtime_store.save_execution(make_execution("EX-001", status=ExecutionStatus.SUCCESS))
        runtime_store.save_execution(make_execution("EX-002", status=ExecutionStatus.FAILED))
        out = DashboardRenderer().render(_snapshot(collector), view="overview")
        assert "AI Software Factory" in out
        assert "DONE 1" in out
        assert "SUCCESS 1" in out
        assert "FAILED 1" in out
        assert "rate 50.0%" in out

    def test_render_tasks_rows(self, collector, task_store):
        task_store.create(make_task("T-001", title="事件分发", project="P-markpad",
                                    status=TaskStatus.DEVELOPMENT))
        out = DashboardRenderer().render(_snapshot(collector), view="tasks")
        assert "T-001" in out
        assert "事件分发" in out
        assert "P-markpad" in out
        assert "DEVELOPMENT" in out

    def test_render_agents_rows(self, collector, agent_registry):
        agent_registry.register(make_agent("A-001", role="dev", status=AgentStatus.WORKING,
                                           skills=["backend"]))[0]
        out = DashboardRenderer().render(_snapshot(collector), view="agents")
        assert "A-001" in out
        assert "dev" in out
        assert "WORKING" in out
        assert "backend" in out

    def test_render_workflows_view(self, collector, workflow_store):
        wf = make_workflow("feature-delivery")
        workflow_store.save_workflow(wf)
        workflow_store.save_run(make_workflow_run("WR-001", workflow=wf, task_id="T-001",
                                                  status=WorkflowStatus.RUNNING))
        out = DashboardRenderer().render(_snapshot(collector), view="workflows")
        assert "1 definitions" in out
        assert "WR-001" in out
        assert "RUNNING" in out

    def test_render_executions_view(self, collector, runtime_store):
        runtime_store.save_execution(make_execution("EX-001", status=ExecutionStatus.SUCCESS))
        runtime_store.save_result(make_result("RES-001", request_id="EX-001",
                                              status=ExecutionStatus.SUCCESS))
        out = DashboardRenderer().render(_snapshot(collector), view="executions")
        assert "EX-001" in out
        assert "SUCCESS" in out

    def test_render_recovery_view(self, collector, checkpoint_store, logger):
        checkpoint_store.save(make_checkpoint("T-001", event_seq=7, current_step="verify",
                                              agents={"A-001": "WORKING"}))
        logger.record(EventType.RECOVERY_STARTED, source="test", action="checkpoint", result="OK")
        out = DashboardRenderer().render(_snapshot(collector), view="recovery")
        assert "CKPT-T-001" in out
        assert "T-001" in out
        assert "A-001=WORKING" in out
        assert "started 1" in out

    def test_render_recent_events_rows(self, collector, logger):
        logger.record(EventType.TASK_CREATED, source="test", task_id="T-001",
                      action="create task", result="OK")
        out = DashboardRenderer().render(_snapshot(collector), view="overview")
        assert "task.created" in out
        assert "create task" in out

    def test_render_recent_events_limit(self, collector, logger):
        for i in range(15):
            logger.record(EventType.TASK_CREATED, source="test", action="create task", result="OK")
        out = DashboardRenderer().render(_snapshot(collector), view="overview")
        # limit=10 默认: 15 条事件只渲染 10 行 seq
        assert "14" in out  # 最近事件 seq 14 在
        assert "1" in out
        # 不能简单断言计数 — 用行数近似: 渲染文本含 10 次 "task.created"
        assert out.count("task.created") == 10


class TestStatusColors:
    def test_style_status_done_green(self):
        assert views._style_status("DONE") == "green"
        assert views._style_status("SUCCESS") == "green"
        assert views._style_status("PASS") == "green"

    def test_style_status_running_yellow(self):
        assert views._style_status("RUNNING") == "yellow"
        assert views._style_status("WORKING") == "yellow"
        assert views._style_status("PENDING") == "yellow"

    def test_style_status_failed_red(self):
        assert views._style_status("FAILED") == "red"
        assert views._style_status("FAIL") == "red"
        assert views._style_status("ERROR") == "red"

    def test_style_status_unknown_neutral(self):
        assert views._style_status("WEIRD") == "white"
        assert views._style_status(None) == "white"

    def test_status_counts_text_empty(self):
        t = views._status_counts_text({})
        assert "(none)" in t.plain


class TestBigDataRender:
    def test_render_big_data(self, collector, task_store, runtime_store, logger):
        """大数据渲染不抛错且计数正确 (2000 任务 / 1000 执行 / 800 事件)。"""
        for i in range(2000):
            task_store.create(make_task(f"T-{i:04d}", status=TaskStatus.DONE))
        for i in range(1000):
            status = ExecutionStatus.SUCCESS if i % 2 == 0 else ExecutionStatus.FAILED
            runtime_store.save_execution(make_execution(f"EX-{i:04d}", status=status))
        for i in range(800):
            logger.record(EventType.TOOL_CALL, source="test", action="run tool", result="OK")
        out = DashboardRenderer().render(_snapshot(collector))
        assert "2000" in out
        assert "SUCCESS 500" in out
        assert "FAILED 500" in out
        assert "rate 50.0%" in out
