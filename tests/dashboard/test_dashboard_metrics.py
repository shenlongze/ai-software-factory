"""tests/dashboard/test_dashboard_metrics.py — Metrics 展示测试 (success rate / failure / validation)。"""

from __future__ import annotations

import pytest

from events.models import EventType
from runtime.models import ExecutionStatus

from dashboard.collector import DashboardCollector

from dashboard_helpers import (
    make_execution,
    make_task,
    make_validation_events,
)
from tasks.models import TaskStatus


def _fresh_collector(collector, **kw) -> DashboardCollector:
    """以同一批 store 重新装配带自定义参数的收集器。"""
    return collector.__class__(
        task_store=collector._task_store,
        agent_registry=collector._agent_registry,
        workflow_store=collector._workflow_store,
        runtime_store=collector._runtime_store,
        event_store=collector._event_store,
        checkpoint_store=collector._checkpoint_store,
        **kw,
    )


class TestSuccessRate:
    def test_all_success(self, collector, runtime_store):
        runtime_store.save_execution(make_execution("EX-001", status=ExecutionStatus.SUCCESS))
        runtime_store.save_execution(make_execution("EX-002", status=ExecutionStatus.SUCCESS))
        x = collector.collect().executions
        assert x.success_rate == 1.0
        assert x.success == 2

    def test_mixed(self, collector, runtime_store):
        for i in range(10):
            status = ExecutionStatus.SUCCESS if i < 9 else ExecutionStatus.FAILED
            runtime_store.save_execution(make_execution(f"EX-{i:03d}", status=status))
        x = collector.collect().executions
        assert x.success == 9
        assert x.failed == 1
        assert x.success_rate == pytest.approx(0.9)

    def test_empty_zero(self, collector):
        x = collector.collect().executions
        assert x.total == 0
        assert x.success_rate == 0.0

    def test_success_rate_includes_pending_running(self, collector, runtime_store):
        """口径: SUCCESS / 全部执行 (含未完成) — 4 条执行 2 成功 = 0.5。"""
        runtime_store.save_execution(make_execution("EX-001", status=ExecutionStatus.SUCCESS))
        runtime_store.save_execution(make_execution("EX-002", status=ExecutionStatus.SUCCESS))
        runtime_store.save_execution(make_execution("EX-003", status=ExecutionStatus.PENDING))
        runtime_store.save_execution(make_execution("EX-004", status=ExecutionStatus.RUNNING))
        x = collector.collect().executions
        assert x.total == 4
        assert x.success_rate == pytest.approx(0.5)

    def test_failure_count(self, collector, runtime_store):
        runtime_store.save_execution(make_execution("EX-001", status=ExecutionStatus.SUCCESS))
        runtime_store.save_execution(make_execution("EX-002", status=ExecutionStatus.FAILED))
        runtime_store.save_execution(make_execution("EX-003", status=ExecutionStatus.FAILED))
        x = collector.collect().executions
        assert x.failed == 2


class TestValidation:
    def test_validation_summary_counts(self, collector, logger):
        make_validation_events(logger, results=("PASS", "PASS", "FAIL", "SKIP"))
        v = collector.collect().metrics.validation
        assert v.total == 4
        assert v.pass_count == 2
        assert v.fail_count == 1
        assert v.skip_count == 1
        assert v.error_count == 0

    def test_validation_summary_error(self, collector, logger):
        make_validation_events(logger, results=("ERROR",))
        v = collector.collect().metrics.validation
        assert v.error_count == 1
        assert v.pass_count == 0

    def test_validation_empty(self, collector):
        v = collector.collect().metrics.validation
        assert v.total == 0
        assert v.runs == 0
        assert v.failed_runs == 0

    def test_validation_runs_and_failed_runs(self, collector, logger):
        make_validation_events(logger, results=("PASS",), runs=2, failed_runs=3)
        v = collector.collect().metrics.validation
        assert v.runs == 2
        assert v.failed_runs == 3
        assert v.pass_count == 1

    def test_validation_other_events_not_counted(self, collector, logger):
        """非 rule.completed 的验证事件不计入 PASS/FAIL/SKIP/ERROR 粒度计数。"""
        logger.record(EventType.VALIDATION_STARTED, source="test", result="started")
        logger.record(EventType.VALIDATION_COMPLETED, source="test", result="PASS")
        v = collector.collect().metrics.validation
        assert v.total == 0
        assert v.runs == 1  # completed 计为 runs, 不进粒度计数


class TestEventMetrics:
    def test_event_count_total(self, collector, logger):
        logger.record(EventType.SYSTEM_INIT, source="test", result="OK")
        logger.record(EventType.TASK_CREATED, source="test", result="OK")
        m = collector.collect().metrics
        assert m.event_count == 2

    def test_recovery_event_counts(self, collector, logger):
        logger.record(EventType.RECOVERY_STARTED, source="test", action="checkpoint", result="OK")
        logger.record(EventType.RECOVERY_COMPLETED, source="test", action="checkpoint", result="OK")
        logger.record(EventType.RECOVERY_FAILED, source="test", action="recover", result="FAIL")
        m = collector.collect().metrics
        assert (m.recovery_started, m.recovery_completed, m.recovery_failed) == (1, 1, 1)


class TestMetricsWithTasks:
    def test_metrics_combined_snapshot(self, collector, task_store, runtime_store, logger):
        """多域指标共存于同一快照 (--json 单次查询全量)。"""
        task_store.create(make_task("T-001", status=TaskStatus.DONE))
        runtime_store.save_execution(make_execution("EX-001", status=ExecutionStatus.SUCCESS))
        make_validation_events(logger, results=("PASS",))
        s = collector.collect()
        assert s.tasks.done == 1
        assert s.executions.success_rate == 1.0
        assert s.metrics.validation.pass_count == 1
        assert s.metrics.event_count == 2  # rule.completed + validation.completed (make_validation_events 默认 runs=1)
