"""tests/metrics/test_metrics_collectors.py — MetricsCollector 测试 (各 store 读取/只读性)。"""

from __future__ import annotations

from agents.models import Agent
from runtime.models import ExecutionRequest, ExecutionStatus
from tasks.models import Task, TaskStatus
from workflows.models import Workflow, WorkflowRun, WorkflowStatus, WorkflowStep

from dashboard_helpers import make_validation_events  # noqa: F401  (复用数据构造)

from metrics.collectors import MetricsCollector
from metrics_helpers import make_assignment_events, make_task_events
from tasks.store import TaskStore


def _seed_all(*, task_store, agent_registry, workflow_store, runtime_store, logger):
    """全 store 预置数据 (直写, 不经 CLI — 保持测试确定性)。"""
    task_store.create(Task(id="T-001", title="a", status=TaskStatus.DONE))
    task_store.create(Task(id="T-002", title="b", status=TaskStatus.BACKLOG))
    agent_registry.register(Agent(id="A-001", name="A-001", role="dev"))[0]
    wf = Workflow(id="feature-delivery", name="feature-delivery",
                  steps=[WorkflowStep(id="plan", name="plan", order=1)])
    workflow_store.save_workflow(wf)
    workflow_store.save_run(WorkflowRun(
        run_id="WR-001", workflow_id="feature-delivery", workflow_name="feature-delivery",
        task_id="T-001", step_states=[], status=WorkflowStatus.COMPLETED,
    ))
    runtime_store.save_execution(ExecutionRequest(
        id="EX-001", task_id="T-001", status=ExecutionStatus.SUCCESS,
    ))
    make_task_events(logger, task_id="T-002", fail="testing")
    make_assignment_events(logger, agent_id="A-001", task_id="T-001", count=1, successes=1, failures=0)
    make_validation_events(logger, results=("PASS", "PASS", "FAIL"))


class TestCollectorReads:
    def test_empty_factory(self, collector):
        m = collector.collect()
        assert m.tasks.total == 0
        assert m.executions.total == 0
        assert m.agents == {}
        assert m.workflows.run_count == 0
        assert m.validation.total_rules == 0
        assert m.failures.failure_reason_count == {}
        assert m.project_id is None

    def test_seeded_all_stores(self, collector, task_store, agent_registry,
                               workflow_store, runtime_store, logger):
        _seed_all(task_store=task_store, agent_registry=agent_registry,
                  workflow_store=workflow_store, runtime_store=runtime_store, logger=logger)
        m = collector.collect()
        assert m.tasks.total == 2
        assert m.tasks.completed == 1
        assert m.tasks.failed == 1
        assert m.executions.total == 1
        assert m.executions.success == 1
        assert m.agents_total == 1
        assert m.agents["A-001"].assignment_count == 1
        assert m.workflows.run_count == 1
        assert m.workflows.completed == 1
        assert m.validation.total_rules == 3
        assert m.validation.pass_count == 2
        assert m.failures.failure_reason_count == {"testing": 1}

    def test_tasks_from_task_store(self, collector, task_store, logger):
        task_store.create(Task(id="T-001", title="a", status=TaskStatus.DONE))
        task_store.create(Task(id="T-002", title="b", status=TaskStatus.DEVELOPMENT))
        make_task_events(logger, task_id="T-003", fail="dev")
        m = collector.collect()
        assert m.tasks.total == 2
        assert m.tasks.completed == 1
        assert m.tasks.failed == 1  # T-003 有 task.fail 事件
        assert m.tasks.success_rate == 0.5

    def test_executions_from_runtime_store(self, collector, runtime_store):
        """首次失败重试成功: 整体成功率 0.5, 但首次执行 (EX-001, created_at+id 决胜)
        即 FAILED → first_attempt_success_rate 0.0 (ADR-0015 决策 4)。"""
        runtime_store.save_execution(ExecutionRequest(id="EX-001", task_id="T-001",
                                                      status=ExecutionStatus.FAILED))
        runtime_store.save_execution(ExecutionRequest(id="EX-002", task_id="T-001",
                                                      status=ExecutionStatus.SUCCESS))
        m = collector.collect()
        assert m.executions.total == 2
        assert m.executions.success == 1
        assert m.executions.failed == 1
        assert m.executions.first_attempt_success_rate == 0.0

    def test_agents_from_registry_and_events(self, collector, agent_registry, logger):
        agent_registry.register(Agent(id="A-001", name="A-001", role="dev"))[0]
        make_assignment_events(logger, agent_id="A-001", count=2, successes=2, failures=0)
        m = collector.collect()
        assert m.agents_total == 1
        assert m.agents["A-001"].assignment_count == 2
        assert m.agents["A-001"].success_rate == 1.0

    def test_workflows_from_workflow_store(self, collector, workflow_store):
        wf = Workflow(id="wf", name="wf", steps=[WorkflowStep(id="s1", name="s1", order=1)])
        workflow_store.save_workflow(wf)
        workflow_store.save_run(WorkflowRun(run_id="WR-001", workflow_id="wf", workflow_name="wf",
                                            task_id="T-001", step_states=[],
                                            status=WorkflowStatus.COMPLETED))
        workflow_store.save_run(WorkflowRun(run_id="WR-002", workflow_id="wf", workflow_name="wf",
                                            task_id="T-002", step_states=[],
                                            status=WorkflowStatus.FAILED))
        m = collector.collect()
        assert m.workflows.run_count == 2
        assert m.workflows.completed == 1
        assert m.workflows.failed == 1
        assert m.workflows.success_rate == 0.5
        assert m.workflows.definitions == 1

    def test_validation_from_events(self, collector, logger):
        make_validation_events(logger, results=("PASS", "PASS", "FAIL", "SKIP"), runs=1, failed_runs=1)
        m = collector.collect()
        assert m.validation.total_rules == 4
        assert m.validation.pass_count == 2
        assert m.validation.fail_count == 1
        assert m.validation.skip_count == 1
        assert m.validation.pass_rate == 0.5
        assert m.validation.runs == 1
        assert m.validation.failed_runs == 1

    def test_failure_reasons_from_events(self, collector, logger):
        make_task_events(logger, task_id="T-001", fail="development")
        make_task_events(logger, task_id="T-002", fail="development")
        make_task_events(logger, task_id="T-003", fail="testing")
        m = collector.collect()
        assert m.failures.failure_reason_count == {"development": 2, "testing": 1}

    def test_project_filter(self, collector, logger, task_store):
        """project_id 过滤: 只聚合该项目事件/任务 (执行无项目维度, 恒为全局)。"""
        task_store.create(Task(id="T-001", title="a", project="P-1", status=TaskStatus.DONE))
        task_store.create(Task(id="T-002", title="b", project="P-2", status=TaskStatus.BACKLOG))
        make_task_events(logger, task_id="T-001", project="P-1", fail="dev")
        make_task_events(logger, task_id="T-002", project="P-2", fail="dev")

        filtered = MetricsCollector(
            event_store=collector._event_store, task_store=task_store,
            agent_registry=collector._agent_registry,
            workflow_store=collector._workflow_store,
            runtime_store=collector._runtime_store, project_id="P-1",
        )
        m = filtered.collect()
        assert m.project_id == "P-1"
        assert m.tasks.total == 1  # 只 P-1 任务
        assert m.tasks.failed == 1  # 只 P-1 的 task.fail 事件

    def test_repeated_collect_deterministic(self, collector, task_store, runtime_store):
        """重复 collect 确定性: 聚合值稳定 (generated_at 每次是新时间戳, 排除比较)。"""
        task_store.create(Task(id="T-001", title="a", status=TaskStatus.DONE))
        runtime_store.save_execution(ExecutionRequest(id="EX-001", task_id="T-001",
                                                      status=ExecutionStatus.SUCCESS))
        first = collector.collect().to_dict()
        second = collector.collect().to_dict()
        first.pop("generated_at")
        second.pop("generated_at")
        assert first == second

    def test_big_data_collect(self, collector, task_store, runtime_store, logger):
        """大数据: 500 任务 + 400 执行 + 300 事件, collect 不抛错且计数正确。"""
        for i in range(500):
            status = TaskStatus.DONE if i % 2 == 0 else TaskStatus.DEVELOPMENT
            task_store.create(Task(id=f"T-{i:04d}", title="t", status=status))
        for i in range(400):
            status = ExecutionStatus.SUCCESS if i % 2 == 0 else ExecutionStatus.FAILED
            runtime_store.save_execution(ExecutionRequest(
                id=f"EX-{i:04d}", task_id=f"T-{i % 500:04d}", status=status))
        for i in range(300):
            make_task_events(logger, task_id=f"T-{i:04d}", fail="dev")
        m = collector.collect()
        assert m.tasks.total == 500
        assert m.tasks.completed == 250
        assert m.executions.total == 400
        assert m.executions.success == 200
        assert m.failures.failure_reason_count["dev"] == 300


class TestCollectorReadOnly:
    def test_no_state_change(self, collector, task_store, agent_registry,
                              workflow_store, runtime_store, logger):
        """只读铁律: collect 后所有 store 内容不变。"""
        task_store.create(Task(id="T-001", title="a", status=TaskStatus.DEVELOPMENT))
        agent_registry.register(Agent(id="A-001", name="A-001", role="dev"))[0]
        runtime_store.save_execution(ExecutionRequest(id="EX-001", task_id="T-001",
                                                      status=ExecutionStatus.SUCCESS))
        make_task_events(logger, task_id="T-001", fail="dev")
        make_assignment_events(logger, agent_id="A-001", count=1, successes=1, failures=0)

        before = {
            "tasks": [t.to_dict() for t in task_store.list()],
            "agents": [a.to_dict() for a in agent_registry.list()],
            "runs": [r.to_dict() for r in workflow_store.list_runs()],
            "execs": [e.to_dict() for e in runtime_store.list_executions()],
        }
        event_count_before = collector._event_store.count()

        collector.collect()

        assert [t.to_dict() for t in task_store.list()] == before["tasks"]
        assert [a.to_dict() for a in agent_registry.list()] == before["agents"]
        assert [r.to_dict() for r in workflow_store.list_runs()] == before["runs"]
        assert [e.to_dict() for e in runtime_store.list_executions()] == before["execs"]
        assert collector._event_store.count() == event_count_before  # 不发任何事件

    def test_no_events_written(self, collector, logger):
        """collect 不追加任何事件 (审计由 CLI 命令层负责)。"""
        before = collector._event_store.count()
        collector.collect()
        assert collector._event_store.count() == before
        assert collector._event_store.query() == []

    def test_task_status_unchanged(self, collector, task_store):
        task_store.create(Task(id="T-001", title="a", status=TaskStatus.TESTING))
        collector.collect()
        assert task_store.get("T-001").status is TaskStatus.TESTING

    def test_agent_status_unchanged(self, collector, agent_registry, logger):
        from agents.models import AgentStatus

        agent_registry.register(Agent(id="A-001", name="A-001", role="dev"))[0]
        agent_registry.set_status("A-001", AgentStatus.WORKING)
        collector.collect()
        assert agent_registry.get("A-001").status is AgentStatus.WORKING
