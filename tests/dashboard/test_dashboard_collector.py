"""tests/dashboard/test_dashboard_collector.py — DashboardCollector 只读聚合测试。

覆盖: 各 store 读取 / 空工厂 / 项目过滤 / 大数据 / 只读性 (状态不变)。
"""

from __future__ import annotations

from pathlib import Path

from agents.models import AgentStatus
from events.models import EventType
from runtime.models import ExecutionStatus
from tasks.models import TaskStatus
from workflows.models import WorkflowStatus

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


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    """目录树快照: {相对路径: 文件字节} (只读性断言用)。

    排除 SQLite WAL 瞬态文件 (-shm/-wal/-journal): 这些是连接级运行时工件,
    纯读操作也会更新其字节 (如读标记), 不代表业务状态变化; 业务状态 = 主库
    events.db + 各 store JSON 文件。
    """
    transient = ("-shm", "-wal", "-journal")
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and not p.name.endswith(transient)
    }


class TestEmptyFactory:
    def test_collect_empty_all_zero(self, collector):
        s = collector.collect()
        assert s.tasks.total == 0
        assert s.agents.total == 0
        assert s.workflows.definitions == 0
        assert s.workflows.runs_total == 0
        assert s.executions.total == 0
        assert s.checkpoints.total == 0
        assert s.metrics.event_count == 0
        assert s.recent_events == []
        assert s.project_id is None

    def test_collect_empty_creates_no_files(self, collector, factory_root):
        """空工厂 collect 不产生任何文件 (只读)。"""
        assert not factory_root.exists() or list(factory_root.rglob("*")) == []
        collector.collect()
        assert not factory_root.exists() or list(factory_root.rglob("*")) == []

    def test_collect_empty_validation_empty(self, collector):
        v = collector.collect().metrics.validation
        assert v.total == 0
        assert (v.pass_count, v.fail_count, v.skip_count, v.error_count) == (0, 0, 0, 0)


class TestTasks:
    def test_collect_tasks_counts(self, collector, task_store):
        task_store.create(make_task("T-001", status=TaskStatus.DEVELOPMENT))
        task_store.create(make_task("T-002", status=TaskStatus.DONE))
        task_store.create(make_task("T-003", status=TaskStatus.BACKLOG))
        s = collector.collect()
        assert s.tasks.total == 3
        assert s.tasks.by_status == {"BACKLOG": 1, "DEVELOPMENT": 1, "DONE": 1}
        assert s.tasks.active == 2
        assert s.tasks.done == 1

    def test_collect_tasks_items(self, collector, task_store):
        task_store.create(make_task("T-001", title="事件分发", project="P-markpad"))
        s = collector.collect()
        item = s.tasks.items[0]
        assert item["id"] == "T-001"
        assert item["title"] == "事件分发"
        assert item["project"] == "P-markpad"

    def test_collect_tasks_by_project(self, collector, task_store):
        task_store.create(make_task("T-001", project="P-a"))
        task_store.create(make_task("T-002", project="P-b"))
        s = collector.collect()
        assert s.tasks.by_project == {"P-a": 1, "P-b": 1}

    def test_collect_tasks_project_filter(self, collector, task_store, agent_registry):
        task_store.create(make_task("T-001", project="P-a"))
        task_store.create(make_task("T-002", project="P-b"))
        from dashboard.collector import DashboardCollector

        scoped = DashboardCollector(
            task_store=task_store,
            agent_registry=agent_registry,
            workflow_store=collector._workflow_store,
            runtime_store=collector._runtime_store,
            event_store=collector._event_store,
            checkpoint_store=collector._checkpoint_store,
            project_id="P-a",
        )
        s = scoped.collect()
        assert s.tasks.total == 1
        assert s.tasks.items[0]["id"] == "T-001"
        assert s.project_id == "P-a"


class TestAgents:
    def test_collect_agents_counts(self, collector, agent_registry):
        agent_registry.register(make_agent("A-001", role="dev", status=AgentStatus.AVAILABLE))[0]
        agent_registry.register(make_agent("A-002", role="debugger", status=AgentStatus.WORKING))[0]
        s = collector.collect()
        assert s.agents.total == 2
        assert s.agents.by_status == {"AVAILABLE": 1, "WORKING": 1}
        assert s.agents.working == 1
        assert s.agents.available == 1

    def test_collect_agents_items(self, collector, agent_registry):
        agent_registry.register(make_agent("A-001", role="dev", skills=["backend", "flutter"]))[0]
        s = collector.collect()
        item = s.agents.items[0]
        assert item["id"] == "A-001"
        assert item["skills"] == ["backend", "flutter"]

    def test_collect_agents_by_role(self, collector, agent_registry):
        agent_registry.register(make_agent("A-001", role="dev"))[0]
        agent_registry.register(make_agent("A-002", role="dev"))[0]
        agent_registry.register(make_agent("A-003", role="debugger"))[0]
        s = collector.collect()
        assert s.agents.by_role == {"debugger": 1, "dev": 2}


class TestWorkflows:
    def test_collect_workflows_definitions(self, collector, workflow_store):
        workflow_store.save_workflow(make_workflow("feature-delivery"))
        workflow_store.save_workflow(make_workflow("bugfix"))
        s = collector.collect()
        assert s.workflows.definitions == 2
        ids = [w["id"] for w in s.workflows.definitions_items]
        assert ids == ["bugfix", "feature-delivery"]

    def test_collect_workflows_runs(self, collector, workflow_store):
        wf = make_workflow("feature-delivery")
        workflow_store.save_workflow(wf)
        workflow_store.save_run(make_workflow_run("WR-001", workflow=wf, task_id="T-001",
                                                  status=WorkflowStatus.RUNNING))
        workflow_store.save_run(make_workflow_run("WR-002", workflow=wf, task_id="T-002",
                                                  status=WorkflowStatus.COMPLETED))
        s = collector.collect()
        assert s.workflows.runs_total == 2
        assert s.workflows.runs_by_status == {"COMPLETED": 1, "RUNNING": 1}
        assert s.workflows.runs_items[0]["run_id"] == "WR-001"


class TestExecutions:
    def test_collect_executions_counts(self, collector, runtime_store):
        runtime_store.save_execution(make_execution("EX-001", status=ExecutionStatus.SUCCESS))
        runtime_store.save_execution(make_execution("EX-002", status=ExecutionStatus.FAILED))
        runtime_store.save_execution(make_execution("EX-003", status=ExecutionStatus.PENDING))
        s = collector.collect()
        assert s.executions.total == 3
        assert s.executions.by_status == {"FAILED": 1, "PENDING": 1, "SUCCESS": 1}
        assert s.executions.success == 1
        assert s.executions.failed == 1

    def test_collect_executions_result_join(self, collector, runtime_store):
        runtime_store.save_execution(make_execution("EX-001", status=ExecutionStatus.SUCCESS))
        runtime_store.save_result(make_result("RES-001", request_id="EX-001",
                                              status=ExecutionStatus.SUCCESS))
        s = collector.collect()
        item = s.executions.items[0]
        assert item["id"] == "EX-001"
        assert item["result"]["status"] == "SUCCESS"

    def test_collect_executions_no_result_none(self, collector, runtime_store):
        runtime_store.save_execution(make_execution("EX-001", status=ExecutionStatus.PENDING))
        s = collector.collect()
        assert s.executions.items[0]["result"] is None


class TestCheckpoints:
    def test_collect_checkpoints(self, collector, checkpoint_store):
        checkpoint_store.save(make_checkpoint("T-001", event_seq=5, agents={"A-001": "WORKING"}))
        checkpoint_store.save(make_checkpoint("T-002", event_seq=2))
        s = collector.collect()
        assert s.checkpoints.total == 2
        assert s.checkpoints.tasks == ["T-001", "T-002"]
        assert s.checkpoints.items[0]["event_seq"] == 5


class TestRecentEvents:
    def test_collect_recent_events_order(self, collector, logger):
        """最近事件最近优先 (seq 倒序)。"""
        for i in range(5):
            logger.record(EventType.TASK_CREATED, source="test", task_id=f"T-00{i + 1}",
                          action="create task", result="OK")
        s = collector.collect()
        seqs = [e["seq"] for e in s.recent_events]
        assert seqs == sorted(seqs, reverse=True)
        assert len(seqs) == 5

    def test_collect_recent_events_limit(self, collector, logger):
        for i in range(20):
            logger.record(EventType.TASK_CREATED, source="test", action="create task", result="OK")
        s = collector.collect()
        assert len(s.recent_events) == 10  # 默认 recent_limit=10

    def test_collect_recent_events_custom_limit(self, collector, logger):
        for i in range(20):
            logger.record(EventType.TASK_CREATED, source="test", action="create task", result="OK")
        scoped = collector.__class__(
            task_store=collector._task_store,
            agent_registry=collector._agent_registry,
            workflow_store=collector._workflow_store,
            runtime_store=collector._runtime_store,
            event_store=collector._event_store,
            checkpoint_store=collector._checkpoint_store,
            recent_limit=3,
        )
        assert len(scoped.collect().recent_events) == 3

    def test_collect_recent_events_project_filter(self, collector, logger, task_store):
        logger.record(EventType.TASK_CREATED, source="test", project_id="P-a", task_id="T-001",
                      action="create task", result="OK")
        logger.record(EventType.TASK_CREATED, source="test", project_id="P-b", task_id="T-002",
                      action="create task", result="OK")
        scoped = collector.__class__(
            task_store=task_store,
            agent_registry=collector._agent_registry,
            workflow_store=collector._workflow_store,
            runtime_store=collector._runtime_store,
            event_store=collector._event_store,
            checkpoint_store=collector._checkpoint_store,
            project_id="P-a",
        )
        s = scoped.collect()
        assert len(s.recent_events) == 1
        assert s.recent_events[0]["project_id"] == "P-a"


class TestMetricsCollection:
    def test_collect_event_type_counts(self, collector, logger):
        logger.record(EventType.TASK_CREATED, source="test", result="OK")
        logger.record(EventType.TASK_CREATED, source="test", result="OK")
        logger.record(EventType.AGENT_VIEWED, source="test", result="OK")
        s = collector.collect()
        assert s.metrics.event_count == 3
        assert s.metrics.event_type_counts["task.created"] == 2
        assert s.metrics.event_type_counts["agent.viewed"] == 1

    def test_collect_validation_aggregation(self, collector, logger):
        make_validation_events(logger, results=("PASS", "PASS", "FAIL", "SKIP", "ERROR"),
                               runs=1, failed_runs=1)
        s = collector.collect()
        v = s.metrics.validation
        assert v.total == 5
        assert v.pass_count == 2
        assert v.fail_count == 1
        assert v.skip_count == 1
        assert v.error_count == 1
        assert v.runs == 1
        assert v.failed_runs == 1

    def test_collect_recovery_counts(self, collector, logger):
        logger.record(EventType.RECOVERY_STARTED, source="test", action="checkpoint", result="OK")
        logger.record(EventType.RECOVERY_COMPLETED, source="test", action="checkpoint", result="OK")
        logger.record(EventType.RECOVERY_FAILED, source="test", action="recover", result="FAIL")
        s = collector.collect()
        assert s.metrics.recovery_started == 1
        assert s.metrics.recovery_completed == 1
        assert s.metrics.recovery_failed == 1


class TestReadOnly:
    def test_collect_read_only_no_state_change(self, collector, task_store, agent_registry,
                                               workflow_store, runtime_store, checkpoint_store,
                                               logger, factory_root, tmp_path):
        """只读铁律: collect 后全部 store 文件与事件库字节不变。"""
        # 预置数据 (写操作只发生在 fixture 阶段)
        task_store.create(make_task("T-001", status=TaskStatus.DEVELOPMENT))
        agent_registry.register(make_agent("A-001", status=AgentStatus.WORKING))[0]
        wf = make_workflow("feature-delivery")
        workflow_store.save_workflow(wf)
        workflow_store.save_run(make_workflow_run("WR-001", workflow=wf, task_id="T-001"))
        runtime_store.save_execution(make_execution("EX-001", status=ExecutionStatus.SUCCESS))
        checkpoint_store.save(make_checkpoint("T-001"))
        logger.record(EventType.TASK_CREATED, source="test", task_id="T-001", result="OK")

        before_files = _tree_snapshot(tmp_path)
        before_events = collector._event_store.count()

        s = collector.collect()
        assert s.tasks.total == 1  # 聚合确实读到数据

        after_files = _tree_snapshot(tmp_path)
        assert after_files == before_files, "collect 修改了任何存储文件"
        assert collector._event_store.count() == before_events, "collect 写入了事件"

        # 状态语义不变: 任务仍是 DEVELOPMENT, Agent 仍 WORKING
        assert task_store.get("T-001").status is TaskStatus.DEVELOPMENT
        assert agent_registry.get("A-001").status is AgentStatus.WORKING

    def test_collect_does_not_emit_events(self, collector, logger):
        """收集器自身不发事件 (事件审计由 CLI 命令层负责)。"""
        logger.record(EventType.TASK_CREATED, source="test", result="OK")
        before = logger.store.count()
        collector.collect()
        assert logger.store.count() == before


class TestBigData:
    def test_collect_big_data(self, collector, task_store, agent_registry, workflow_store,
                              runtime_store, checkpoint_store, logger):
        """大数据: 1000 任务 / 500 Agent / 300 执行 / 200 checkpoint / 1500 事件。"""
        for i in range(1000):
            task_store.create(make_task(f"T-{i:04d}", status=TaskStatus.DEVELOPMENT,
                                        project="P-big"))
        for i in range(500):
            agent_registry.register(make_agent(f"A-{i:04d}", role="dev",
                                               status=AgentStatus.AVAILABLE))[0]
        wf = make_workflow("feature-delivery")
        workflow_store.save_workflow(wf)
        for i in range(50):
            workflow_store.save_run(make_workflow_run(f"WR-{i:03d}", workflow=wf,
                                                      task_id=f"T-{i:04d}"))
        for i in range(300):
            status = ExecutionStatus.SUCCESS if i % 3 else ExecutionStatus.FAILED
            runtime_store.save_execution(make_execution(f"EX-{i:03d}", task_id=f"T-{i:04d}",
                                                        status=status))
        for i in range(200):
            checkpoint_store.save(make_checkpoint(f"T-{i:04d}", event_seq=i))
        for i in range(1500):
            logger.record(EventType.TOOL_CALL, source="test", task_id=f"T-{i % 100:04d}",
                          action="run tool", result="OK")

        s = collector.collect()
        assert s.tasks.total == 1000
        assert s.agents.total == 500
        assert s.workflows.definitions == 1
        assert s.workflows.runs_total == 50
        assert s.executions.total == 300
        assert s.executions.success == 200
        assert s.executions.failed == 100
        assert s.checkpoints.total == 200
        assert s.metrics.event_count == 1500
        assert len(s.recent_events) == 10
        # 全部明细保留 (渲染与 --json 消费)
        assert len(s.tasks.items) == 1000
        assert len(s.executions.items) == 300
