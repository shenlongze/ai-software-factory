"""tests/metrics/test_metrics_calculators.py — 指标计算纯函数测试 (空工厂/大数据/混合数据)。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from events.models import Event, EventType
from runtime.models import ExecutionRequest, ExecutionStatus
from tasks.models import Task, TaskStatus
from workflows.models import Workflow, WorkflowRun, WorkflowStatus, WorkflowStep

from metrics.calculators import (
    calculate_agent_metrics,
    calculate_execution_metrics,
    calculate_failure_reason_count,
    calculate_first_attempt_success_rate,
    calculate_task_metrics,
    calculate_validation_metrics,
    calculate_workflow_metrics,
)


def _event(type_: EventType, **kw) -> Event:
    return Event.create(type_, source="test", **kw)


def _task(task_id: str, status: TaskStatus | str = TaskStatus.BACKLOG, project: str = "default") -> Task:
    return Task(id=task_id, title=task_id, project=project, status=status)


def _exec(execution_id: str, task_id: str, status: ExecutionStatus | str = ExecutionStatus.SUCCESS,
          created_at: datetime | None = None) -> ExecutionRequest:
    return ExecutionRequest(id=execution_id, task_id=task_id, status=status,
                            created_at=created_at or datetime(2026, 8, 6, tzinfo=timezone.utc))


def _run(run_id: str, status: WorkflowStatus | str = WorkflowStatus.COMPLETED) -> WorkflowRun:
    return WorkflowRun(
        run_id=run_id, workflow_id="wf", workflow_name="wf", task_id="T-001",
        step_states=[], status=status,
    )


def _workflow(wf_id: str = "wf") -> Workflow:
    return Workflow(id=wf_id, name=wf_id, steps=[WorkflowStep(id="s1", name="s1", order=1)])


# ------------------------------------------------------------------ Task

class TestTaskMetrics:
    def test_empty(self):
        m = calculate_task_metrics([], [])
        assert (m.total, m.completed, m.failed, m.success_rate) == (0, 0, 0, 0.0)
        assert m.by_status == {}

    def test_mixed_statuses(self):
        tasks = [_task("T-001", TaskStatus.DONE), _task("T-002", TaskStatus.DEVELOPMENT),
                 _task("T-003", TaskStatus.BACKLOG)]
        m = calculate_task_metrics(tasks, [])
        assert m.total == 3
        assert m.completed == 1
        assert m.failed == 0
        assert m.success_rate == 1.0
        assert m.by_status == {"BACKLOG": 1, "DEVELOPMENT": 1, "DONE": 1}

    def test_failed_from_task_fail_events(self):
        tasks = [_task("T-001", TaskStatus.DONE), _task("T-002", TaskStatus.BACKLOG)]
        events = [_event(EventType.TASK_FAIL, task_id="T-002")]
        m = calculate_task_metrics(tasks, events)
        assert m.completed == 1
        assert m.failed == 1
        assert m.success_rate == 0.5

    def test_failed_counts_distinct_tasks(self):
        """同任务多次 task.fail 只计一次 (distinct 任务口径)。"""
        tasks = [_task("T-001")]
        events = [_event(EventType.TASK_FAIL, task_id="T-001"),
                  _event(EventType.TASK_FAIL, task_id="T-001")]
        m = calculate_task_metrics(tasks, events)
        assert m.failed == 1

    def test_success_rate_zero_when_no_terminal(self):
        tasks = [_task("T-001", TaskStatus.BACKLOG)]
        m = calculate_task_metrics(tasks, [])
        assert m.success_rate == 0.0

    def test_no_fail_events_ignored(self):
        tasks = [_task("T-001", TaskStatus.DONE)]
        events = [_event(EventType.TASK_START, task_id="T-001")]
        m = calculate_task_metrics(tasks, events)
        assert m.failed == 0
        assert m.success_rate == 1.0


# ------------------------------------------------------------------ Execution

class TestExecutionMetrics:
    def test_empty(self):
        m = calculate_execution_metrics([])
        assert (m.total, m.success, m.failed) == (0, 0, 0)
        assert m.first_attempt_success_rate == 0.0
        assert m.by_status == {}

    def test_success_failed_counts(self):
        reqs = [_exec("EX-001", "T-001", ExecutionStatus.SUCCESS),
                _exec("EX-002", "T-001", ExecutionStatus.FAILED),
                _exec("EX-003", "T-002", ExecutionStatus.PENDING)]
        m = calculate_execution_metrics(reqs)
        assert m.total == 3
        assert m.success == 1
        assert m.failed == 1
        assert m.by_status == {"FAILED": 1, "PENDING": 1, "SUCCESS": 1}

    def test_big_data_counts(self):
        """大数据: 500 执行 (50% 成功) 计数正确。"""
        reqs = [_exec(f"EX-{i:04d}", f"T-{i % 100:03d}",
                      ExecutionStatus.SUCCESS if i % 2 == 0 else ExecutionStatus.FAILED)
                for i in range(500)]
        m = calculate_execution_metrics(reqs)
        assert m.total == 500
        assert m.success == 250
        assert m.failed == 250


class TestFirstAttemptSuccessRate:
    def test_empty(self):
        assert calculate_first_attempt_success_rate([]) == 0.0

    def test_single_task_first_success(self):
        reqs = [_exec("EX-001", "T-001", ExecutionStatus.SUCCESS)]
        assert calculate_first_attempt_success_rate(reqs) == 1.0

    def test_single_task_first_failed(self):
        reqs = [_exec("EX-001", "T-001", ExecutionStatus.FAILED)]
        assert calculate_first_attempt_success_rate(reqs) == 0.0

    def test_retry_success_after_fail(self):
        """首次失败 → 重试成功: 一次成功率 0.0 (首次执行才是口径)。"""
        reqs = [_exec("EX-001", "T-001", ExecutionStatus.FAILED, created_at=datetime(2026, 8, 1, tzinfo=timezone.utc)),
                _exec("EX-002", "T-001", ExecutionStatus.SUCCESS, created_at=datetime(2026, 8, 2, tzinfo=timezone.utc))]
        assert calculate_first_attempt_success_rate(reqs) == 0.0

    def test_mixed_tasks(self):
        """2 任务首次成功 + 1 任务首次失败 → 2/3。"""
        base = datetime(2026, 8, 1, tzinfo=timezone.utc)
        reqs = [
            _exec("EX-001", "T-001", ExecutionStatus.SUCCESS, created_at=base),
            _exec("EX-002", "T-002", ExecutionStatus.SUCCESS, created_at=base),
            _exec("EX-003", "T-003", ExecutionStatus.FAILED, created_at=base),
            _exec("EX-004", "T-003", ExecutionStatus.SUCCESS, created_at=base + timedelta(days=1)),
        ]
        assert calculate_first_attempt_success_rate(reqs) == 2 / 3

    def test_unresolved_first_attempt_excluded(self):
        """首次执行 PENDING (未终态) 不进分母。"""
        reqs = [_exec("EX-001", "T-001", ExecutionStatus.PENDING),
                _exec("EX-002", "T-002", ExecutionStatus.SUCCESS)]
        assert calculate_first_attempt_success_rate(reqs) == 1.0

    def test_all_unresolved_zero(self):
        reqs = [_exec("EX-001", "T-001", ExecutionStatus.RUNNING)]
        assert calculate_first_attempt_success_rate(reqs) == 0.0

    def test_tie_break_by_id(self):
        """created_at 相同 → id 最小为首次执行。"""
        base = datetime(2026, 8, 1, tzinfo=timezone.utc)
        reqs = [_exec("EX-002", "T-001", ExecutionStatus.SUCCESS, created_at=base),
                _exec("EX-001", "T-001", ExecutionStatus.FAILED, created_at=base)]
        assert calculate_first_attempt_success_rate(reqs) == 0.0  # EX-001 (id 小) 为首次


# ------------------------------------------------------------------ Agent

class TestAgentMetrics:
    def test_empty(self):
        agents, total = calculate_agent_metrics([], [])
        assert agents == {}
        assert total == 0

    def test_registered_agents_zero_metrics(self):
        from agents.models import Agent

        agents = [Agent(id="A-001", name="A-001", role="dev"),
                  Agent(id="A-002", name="A-002", role="dev")]
        out, total = calculate_agent_metrics(agents, [])
        assert total == 2
        assert out["A-001"].assignment_count == 0
        assert out["A-002"].success_rate == 0.0

    def test_assignment_counts_and_rate(self):
        from agents.models import Agent

        agents = [Agent(id="A-001", name="A-001", role="dev")]
        events = [
            _event(EventType.ASSIGNMENT_CREATED, agent_id="A-001"),
            _event(EventType.ASSIGNMENT_COMPLETED, agent_id="A-001"),
            _event(EventType.ASSIGNMENT_CREATED, agent_id="A-001"),
            _event(EventType.ASSIGNMENT_FAILED, agent_id="A-001"),
        ]
        out, total = calculate_agent_metrics(agents, events)
        a = out["A-001"]
        assert a.assignment_count == 2
        assert a.success_count == 1
        assert a.failed_count == 1
        assert a.success_rate == 0.5
        assert total == 1

    def test_unregistered_agent_from_events(self):
        """事件中出现但未注册的 agent_id 也纳入 (事件维度完整)。"""
        events = [_event(EventType.ASSIGNMENT_COMPLETED, agent_id="A-999")]
        out, total = calculate_agent_metrics([], events)
        assert out["A-999"].success_count == 1
        assert out["A-999"].assignment_count == 0
        assert total == 0

    def test_sorted_output(self):
        from agents.models import Agent

        agents = [Agent(id="A-002", name="A-002", role="dev"),
                  Agent(id="A-001", name="A-001", role="dev")]
        out, _ = calculate_agent_metrics(agents, [])
        assert list(out) == ["A-001", "A-002"]

    def test_events_without_agent_id_ignored(self):
        events = [_event(EventType.ASSIGNMENT_CREATED), _event(EventType.TASK_START)]
        out, total = calculate_agent_metrics([], events)
        assert out == {}
        assert total == 0


# ------------------------------------------------------------------ Workflow

class TestWorkflowMetrics:
    def test_empty(self):
        m = calculate_workflow_metrics([], [])
        assert (m.run_count, m.completed, m.failed, m.success_rate, m.definitions) == (0, 0, 0, 0.0, 0)

    def test_counts_and_rate(self):
        runs = [_run("WR-001", WorkflowStatus.COMPLETED),
                _run("WR-002", WorkflowStatus.FAILED),
                _run("WR-003", WorkflowStatus.RUNNING)]
        m = calculate_workflow_metrics(runs, [_workflow(), _workflow("wf2")])
        assert m.run_count == 3
        assert m.completed == 1
        assert m.failed == 1
        assert m.success_rate == 1 / 3
        assert m.definitions == 2
        assert m.by_status == {"COMPLETED": 1, "FAILED": 1, "RUNNING": 1}


# ------------------------------------------------------------------ Validation

class TestValidationMetrics:
    def test_empty(self):
        m = calculate_validation_metrics([])
        assert (m.total_rules, m.pass_count, m.fail_count, m.skip_count, m.error_count) == (0, 0, 0, 0, 0)
        assert m.pass_rate == 0.0
        assert (m.runs, m.failed_runs) == (0, 0)

    def test_pass_rate_with_skip_error(self):
        """pass_rate = PASS / 全部规则 (SKIP/ERROR 进分母)。"""
        events = [
            _event(EventType.VALIDATION_RULE_COMPLETED, result="PASS"),
            _event(EventType.VALIDATION_RULE_COMPLETED, result="PASS"),
            _event(EventType.VALIDATION_RULE_COMPLETED, result="FAIL"),
            _event(EventType.VALIDATION_RULE_COMPLETED, result="SKIP"),
            _event(EventType.VALIDATION_RULE_COMPLETED, result="ERROR"),
        ]
        m = calculate_validation_metrics(events)
        assert m.total_rules == 5
        assert m.pass_count == 2
        assert m.fail_count == 1
        assert m.skip_count == 1
        assert m.error_count == 1
        assert m.pass_rate == 0.4

    def test_runs_and_failed_runs(self):
        events = [
            _event(EventType.VALIDATION_COMPLETED),
            _event(EventType.VALIDATION_COMPLETED),
            _event(EventType.VALIDATION_FAILED),
        ]
        m = calculate_validation_metrics(events)
        assert m.runs == 2
        assert m.failed_runs == 1
        assert m.total_rules == 0  # 无 rule.completed → 规则数 0, pass_rate 0.0
        assert m.pass_rate == 0.0

    def test_big_data_pass_rate(self):
        """大数据: 200 规则 (75% PASS) → pass_rate 0.75。"""
        events = [
            _event(EventType.VALIDATION_RULE_COMPLETED,
                   result="PASS" if i % 4 != 0 else "FAIL")
            for i in range(200)
        ]
        m = calculate_validation_metrics(events)
        assert m.total_rules == 200
        assert m.pass_count == 150
        assert m.pass_rate == 0.75


# ------------------------------------------------------------------ Failure

class TestFailureReasonCount:
    def test_empty(self):
        assert calculate_failure_reason_count([]) == {}

    def test_grouped_by_stage(self):
        events = [
            _event(EventType.TASK_FAIL, task_id="T-001",
                   payload={"stage": "development", "error": "compile error"}),
            _event(EventType.TASK_FAIL, task_id="T-002",
                   payload={"stage": "development", "error": "lint error"}),
            _event(EventType.TASK_FAIL, task_id="T-003",
                   payload={"stage": "testing", "error": "test failed"}),
        ]
        assert calculate_failure_reason_count(events) == {"development": 2, "testing": 1}

    def test_fallback_to_error_without_stage(self):
        events = [_event(EventType.TASK_FAIL, task_id="T-001",
                         payload={"error": "timeout"})]
        assert calculate_failure_reason_count(events) == {"timeout": 1}

    def test_fallback_unknown(self):
        events = [_event(EventType.TASK_FAIL, task_id="T-001", payload={})]
        assert calculate_failure_reason_count(events) == {"unknown": 1}

    def test_ignores_non_fail_events(self):
        events = [
            _event(EventType.TASK_END, task_id="T-001", payload={"stage": "x"}),
            _event(EventType.VALIDATION_FAILED, task_id="T-001"),
            _event(EventType.WORKFLOW_FAILED, task_id="T-001"),
        ]
        assert calculate_failure_reason_count(events) == {}

    def test_big_data_histogram(self):
        """大数据: 300 task.fail 分布在 3 个 stage。"""
        stages = ["architecture", "development", "testing"]
        events = [_event(EventType.TASK_FAIL, task_id=f"T-{i:04d}",
                         payload={"stage": stages[i % 3]})
                  for i in range(300)]
        counts = calculate_failure_reason_count(events)
        assert counts == {s: 100 for s in stages}
