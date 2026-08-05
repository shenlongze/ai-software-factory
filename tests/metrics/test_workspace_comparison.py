"""tests/metrics/test_workspace_comparison.py — Workspace 项目对比测试 (Phase 6B, ADR-0017)。

覆盖: WorkspaceCollector.comparison() 多项目对比 (Project/Tasks/Success Rate/
Execution Count/Workflow/Validation) + 全局汇总行 + 项目集推导 + 只读性 +
空/大工作区。

口径 (metrics/workspace.py): 每项目行复用 MetricsCollector(project_id) 核心计算
(ADR-0017 决策 1 — 复用不复制); 汇总行 = 全局聚合 (project_id=None) 的同一组
口径, project 标记 "*" (TOTALS_PROJECT); 项目 id 集 = 显式传入 ∪ 任务 project
值 ∪ 事件 project_id 值 (覆盖「有数据但未注册」项目, 同 Dashboard Projects View)。
"""

from __future__ import annotations

from events.models import EventType
from runtime.models import ExecutionStatus
from tasks.models import TaskStatus
from workflows.models import WorkflowStatus

from dashboard_helpers import (
    make_execution,
    make_task,
    make_validation_events,
    make_workflow,
    make_workflow_run,
)

from metrics.models import ProjectComparisonRow, WorkspaceComparison
from metrics.workspace import TOTALS_PROJECT, WorkspaceCollector


def _ws_collector(collector) -> WorkspaceCollector:
    """以同一批 store 装配 WorkspaceCollector (复用 MetricsCollector 依赖)。"""
    return WorkspaceCollector(
        event_store=collector._event_store,
        task_store=collector._task_store,
        agent_registry=collector._agent_registry,
        workflow_store=collector._workflow_store,
        runtime_store=collector._runtime_store,
    )


def _row(c: WorkspaceComparison, project_id: str) -> ProjectComparisonRow:
    return next(r for r in c.projects if r.project == project_id)


class TestComparisonEmpty:
    def test_empty_workspace(self, collector):
        c = _ws_collector(collector).comparison()
        assert isinstance(c, WorkspaceComparison)
        assert c.total == 0
        assert c.projects == []
        assert c.totals.project == TOTALS_PROJECT  # 汇总行存在但全 0
        assert c.totals.tasks_total == 0
        assert c.totals.execution_count == 0
        assert c.totals.validation_pass_rate == 0.0

    def test_empty_with_explicit_project_ids(self, collector):
        """显式 project_ids (workspace 定义) 零数据也保留 (对比种子行)。"""
        c = _ws_collector(collector).comparison(project_ids=["P-empty"])
        assert c.total == 1
        row = _row(c, "P-empty")
        assert row.tasks_total == 0
        assert row.execution_count == 0
        assert row.execution_success_rate == 0.0

    def test_totals_default_factory(self):
        """WorkspaceComparison 默认构造: 汇总行 project='*' (to_dict 可用)。"""
        c = WorkspaceComparison()
        assert c.totals.project == "*"
        assert c.to_dict()["totals"]["project"] == "*"


class TestComparisonSingleProject:
    def test_tasks_counts_and_rate(self, collector, task_store, logger):
        task_store.create(make_task("T-001", project="P-1", status=TaskStatus.DONE))
        task_store.create(make_task("T-002", project="P-1", status=TaskStatus.BACKLOG))
        logger.record(EventType.TASK_FAIL, source="test", project_id="P-1", task_id="T-002",
                      payload={"stage": "dev"})
        c = _ws_collector(collector).comparison()
        row = _row(c, "P-1")
        assert row.tasks_total == 2
        assert row.tasks_completed == 1
        assert row.tasks_failed == 1
        assert row.task_success_rate == 0.5  # completed / (completed + failed)

    def test_execution_counts_and_rate(self, collector, task_store, runtime_store):
        task_store.create(make_task("T-001", project="P-1"))
        runtime_store.save_execution(make_execution("EX-001", task_id="T-001", status=ExecutionStatus.SUCCESS))
        runtime_store.save_execution(make_execution("EX-002", task_id="T-001", status=ExecutionStatus.FAILED))
        runtime_store.save_execution(make_execution("EX-003", task_id="T-001", status=ExecutionStatus.RUNNING))
        c = _ws_collector(collector).comparison()
        row = _row(c, "P-1")
        assert row.execution_count == 3
        assert row.execution_success == 1
        assert row.execution_failed == 1
        assert row.execution_success_rate == 1 / 3  # success / 全部执行

    def test_workflow_runs_and_rate(self, collector, task_store, workflow_store):
        task_store.create(make_task("T-001", project="P-1"))
        wf = make_workflow("feature-delivery")
        workflow_store.save_workflow(wf)
        workflow_store.save_run(make_workflow_run("WR-001", workflow=wf, task_id="T-001",
                                                  status=WorkflowStatus.COMPLETED))
        workflow_store.save_run(make_workflow_run("WR-002", workflow=wf, task_id="T-001",
                                                  status=WorkflowStatus.FAILED))
        c = _ws_collector(collector).comparison()
        row = _row(c, "P-1")
        assert row.workflow_runs == 2
        assert row.workflow_success_rate == 0.5  # completed / run_count

    def test_validation_without_project_not_attributed(self, collector, logger):
        """validation 事件无 project_id → 不推导项目行, 但全局汇总含规则计数。"""
        make_validation_events(logger, task_id="T-001", results=("PASS", "PASS", "FAIL", "SKIP"))
        c = _ws_collector(collector).comparison()
        assert c.total == 0  # 事件无 project_id, 任务为空: 无项目维度可推导
        assert c.totals.validation_rules == 4  # 全局口径含全部规则
        assert c.totals.validation_pass_rate == 0.5

    def test_validation_project_scoped(self, collector, logger):
        """validation 事件带 project_id → 该项目行含规则计数。"""
        for res in ("PASS", "PASS", "FAIL"):
            logger.record(EventType.VALIDATION_RULE_COMPLETED, source="test", project_id="P-1",
                          task_id="T-001", stage="L2", action="run rule", result=res,
                          payload={"rule": f"L2.{res}", "level": "L2"})
        c = _ws_collector(collector).comparison()
        row = _row(c, "P-1")
        assert row.validation_rules == 3
        assert row.validation_pass_rate == 2 / 3  # PASS / total_rules

    def test_totals_equal_single_project(self, collector, task_store, runtime_store):
        task_store.create(make_task("T-001", project="P-1", status=TaskStatus.DONE))
        runtime_store.save_execution(make_execution("EX-001", task_id="T-001", status=ExecutionStatus.SUCCESS))
        c = _ws_collector(collector).comparison()
        t = c.totals
        assert t.tasks_total == 1
        assert t.tasks_completed == 1
        assert t.execution_count == 1
        assert t.execution_success == 1
        assert t.execution_success_rate == 1.0


class TestComparisonMultiProject:
    def _seed_two_projects(self, task_store, runtime_store):
        task_store.create(make_task("T-001", project="P-alpha", status=TaskStatus.DONE))
        task_store.create(make_task("T-002", project="P-alpha", status=TaskStatus.DONE))
        task_store.create(make_task("T-003", project="P-beta", status=TaskStatus.BACKLOG))
        runtime_store.save_execution(make_execution("EX-001", task_id="T-001", status=ExecutionStatus.SUCCESS))
        runtime_store.save_execution(make_execution("EX-002", task_id="T-002", status=ExecutionStatus.FAILED))
        runtime_store.save_execution(make_execution("EX-003", task_id="T-003", status=ExecutionStatus.SUCCESS))

    def test_two_projects_rows(self, collector, task_store, runtime_store):
        self._seed_two_projects(task_store, runtime_store)
        c = _ws_collector(collector).comparison()
        assert c.total == 2
        assert [p.project for p in c.projects] == ["P-alpha", "P-beta"]  # 排序输出
        alpha = _row(c, "P-alpha")
        assert alpha.tasks_total == 2
        assert alpha.execution_count == 2
        assert alpha.execution_success_rate == 0.5
        beta = _row(c, "P-beta")
        assert beta.tasks_total == 1
        assert beta.execution_count == 1
        assert beta.execution_success_rate == 1.0

    def test_totals_aggregate_all_projects(self, collector, task_store, runtime_store):
        self._seed_two_projects(task_store, runtime_store)
        t = _ws_collector(collector).comparison().totals
        assert t.tasks_total == 3
        assert t.tasks_completed == 2
        assert t.execution_count == 3
        assert t.execution_success == 2
        assert t.execution_failed == 1
        assert t.execution_success_rate == 2 / 3

    def test_task_success_rate_totals(self, collector, task_store, logger):
        task_store.create(make_task("T-001", project="P-a", status=TaskStatus.DONE))
        task_store.create(make_task("T-002", project="P-b", status=TaskStatus.BACKLOG))
        logger.record(EventType.TASK_FAIL, source="test", project_id="P-b", task_id="T-002",
                      payload={"stage": "dev"})
        t = _ws_collector(collector).comparison().totals
        assert t.tasks_completed == 1
        assert t.tasks_failed == 1
        assert t.task_success_rate == 0.5

    def test_project_isolation_between_rows(self, collector, task_store, runtime_store):
        """执行按 task_id → project 归属: 跨项目执行互不串行。"""
        self._seed_two_projects(task_store, runtime_store)
        alpha = _row(_ws_collector(collector).comparison(), "P-alpha")
        assert alpha.execution_count == 2  # EX-001/EX-002 (T-001/T-002)
        assert alpha.execution_success == 1
        assert alpha.execution_failed == 1

    def test_orphan_execution_not_attributed(self, collector, runtime_store):
        """孤儿执行 (task 不存在) 不归属任何项目行, 但进全局汇总。"""
        runtime_store.save_execution(make_execution("EX-001", task_id="T-NOPE", status=ExecutionStatus.SUCCESS))
        c = _ws_collector(collector).comparison()
        assert c.total == 0  # 无任务/事件项目维度可推导
        assert c.totals.execution_count == 1  # 全局口径包含孤儿执行


class TestComparisonProjectResolution:
    def test_ids_from_tasks_only(self, collector, task_store):
        task_store.create(make_task("T-001", project="P-task"))
        c = _ws_collector(collector).comparison()  # 无显式 project_ids
        assert c.total == 1
        assert _row(c, "P-task").tasks_total == 1

    def test_ids_from_events_only(self, collector, logger):
        logger.record(EventType.TASK_CREATED, source="test", project_id="P-event", task_id="T-001")
        c = _ws_collector(collector).comparison()
        assert c.total == 1
        assert _row(c, "P-event").tasks_total == 0  # 事件推导项目, 无任务

    def test_ids_merge_explicit_and_data(self, collector, task_store):
        task_store.create(make_task("T-001", project="P-data"))
        c = _ws_collector(collector).comparison(project_ids=["P-explicit", "P-data"])
        assert c.total == 2
        assert _row(c, "P-explicit").tasks_total == 0  # 显式种子保留
        assert _row(c, "P-data").tasks_total == 1

    def test_blank_project_ids_ignored(self, collector, task_store):
        task_store.create(make_task("T-001", project="P-1"))
        c = _ws_collector(collector).comparison(project_ids=["", None])
        assert c.total == 1  # 空串/None 过滤, 不产生空项目行

    def test_event_project_plus_task_project_merged(self, collector, task_store, logger):
        task_store.create(make_task("T-001", project="P-task"))
        logger.record(EventType.TASK_CREATED, source="test", project_id="P-event", task_id="T-001")
        c = _ws_collector(collector).comparison()
        assert {p.project for p in c.projects} == {"P-task", "P-event"}


class TestComparisonReadOnly:
    def test_no_events_written(self, collector, task_store, runtime_store):
        """只读铁律: comparison 不追加任何事件 (审计由 CLI 命令层负责)。"""
        task_store.create(make_task("T-001", project="P-1"))
        runtime_store.save_execution(make_execution("EX-001", task_id="T-001", status=ExecutionStatus.SUCCESS))
        before = collector._event_store.count()
        _ws_collector(collector).comparison()
        assert collector._event_store.count() == before

    def test_store_state_unchanged(self, collector, task_store, runtime_store):
        task_store.create(make_task("T-001", project="P-1"))
        runtime_store.save_execution(make_execution("EX-001", task_id="T-001", status=ExecutionStatus.SUCCESS))
        tasks_before = [t.to_dict() for t in task_store.list()]
        execs_before = [e.to_dict() for e in runtime_store.list_executions()]
        _ws_collector(collector).comparison()
        assert [t.to_dict() for t in task_store.list()] == tasks_before
        assert [e.to_dict() for e in runtime_store.list_executions()] == execs_before


class TestComparisonSerialization:
    def test_to_dict_structure(self, collector, task_store):
        task_store.create(make_task("T-001", project="P-1", status=TaskStatus.DONE))
        d = _ws_collector(collector).comparison().to_dict()
        assert d["total"] == 1
        assert d["projects"][0]["project"] == "P-1"
        assert d["projects"][0]["tasks_total"] == 1
        assert d["projects"][0]["execution_count"] == 0
        assert d["totals"]["project"] == "*"
        assert d["totals"]["tasks_total"] == 1

    def test_row_serialization(self, collector, task_store, runtime_store):
        task_store.create(make_task("T-001", project="P-1"))
        runtime_store.save_execution(make_execution("EX-001", task_id="T-001", status=ExecutionStatus.SUCCESS))
        row = _row(_ws_collector(collector).comparison(), "P-1")
        d = row.to_dict()
        assert d["execution_count"] == 1
        assert d["execution_success_rate"] == 1.0


class TestComparisonLargeWorkspace:
    def test_many_projects(self, collector, task_store, runtime_store):
        """大工作区: 30 项目 × 各 5 任务 + 执行, 对比行/汇总计数正确。"""
        for p in range(30):
            pid = f"P-{p:02d}"
            for i in range(5):
                tid = f"T-{p:02d}-{i}"
                task_store.create(make_task(tid, project=pid,
                                            status=TaskStatus.DONE if i % 2 == 0 else TaskStatus.BACKLOG))
                runtime_store.save_execution(make_execution(
                    f"EX-{p:02d}-{i}", task_id=tid,
                    status=ExecutionStatus.SUCCESS if i % 2 == 0 else ExecutionStatus.FAILED))
        c = _ws_collector(collector).comparison()
        assert c.total == 30
        assert all(p.tasks_total == 5 for p in c.projects)
        assert all(p.execution_count == 5 for p in c.projects)
        assert all(p.execution_success == 3 for p in c.projects)
        t = c.totals
        assert t.tasks_total == 150
        assert t.execution_count == 150
        assert t.execution_success == 90
        assert t.execution_success_rate == 90 / 150

    def test_large_totals_success_rate(self, collector, task_store, runtime_store):
        task_store.create(make_task("T-001", project="P-a", status=TaskStatus.DONE))
        task_store.create(make_task("T-002", project="P-b", status=TaskStatus.DONE))
        runtime_store.save_execution(make_execution("EX-001", task_id="T-001", status=ExecutionStatus.SUCCESS))
        runtime_store.save_execution(make_execution("EX-002", task_id="T-002", status=ExecutionStatus.FAILED))
        t = _ws_collector(collector).comparison().totals
        assert t.execution_success_rate == 0.5
