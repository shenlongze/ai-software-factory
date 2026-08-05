"""tests/metrics/test_workspace_aggregation.py — Workspace 运营视图聚合测试 (Phase 6B, ADR-0017)。

覆盖: collect_agent_utilization (agent/projects/assignments/success_rate) 与
collect_runtime_usage (runtime/execution_count/success_rate) 纯函数 + 只读性;
WorkspaceCollector.agent_utilization()/runtime_usage() 装配读取。

口径 (metrics/workspace.py docstring): assignment_count = agent.assignment.created 数;
success_rate = completed / (completed + failed); Runtime 请求状态为权威
(SUCCESS/FAILED 计数, 全部执行作分母); runtime_id 空归 "unknown"; 孤儿事件/执行
不归属项目。只读铁律: 聚合不写任何 store、不发任何事件。
"""

from __future__ import annotations

from agents.models import Agent, AgentStatus
from events.models import EventType
from runtime.models import ExecutionStatus
from tasks.models import Task, TaskStatus

from dashboard_helpers import make_execution, make_task

from metrics.models import AgentUtilizationSummary, RuntimeUsageSummary
from metrics.workspace import WorkspaceCollector, collect_agent_utilization, collect_runtime_usage


def _ws_collector(collector) -> WorkspaceCollector:
    """以同一批 store 装配 WorkspaceCollector (复用 MetricsCollector 依赖)。"""
    return WorkspaceCollector(
        event_store=collector._event_store,
        task_store=collector._task_store,
        agent_registry=collector._agent_registry,
        workflow_store=collector._workflow_store,
        runtime_store=collector._runtime_store,
    )


class TestAgentUtilizationEmpty:
    def test_empty_no_events(self, logger):
        au = collect_agent_utilization([], [], [])
        assert isinstance(au, AgentUtilizationSummary)
        assert au.total == 0
        assert au.items == []

    def test_empty_with_registered_agents(self, logger):
        agents = [Agent(id="A-001", name="A-001", role="dev")]
        au = collect_agent_utilization([], [], agents)
        assert au.total == 1  # 注册表兜底: 无活动 Agent 也出 0 指标行
        row = au.items[0]
        assert row.agent_id == "A-001"
        assert row.assignments == 0
        assert row.success_rate == 0.0
        assert row.projects == []


class TestAgentUtilizationCounts:
    def test_assignments_created_completed_failed(self, logger):
        events = [
            logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-001"),
            logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-002"),
            logger.record(EventType.ASSIGNMENT_COMPLETED, source="test", agent_id="A-001", task_id="T-001"),
            logger.record(EventType.ASSIGNMENT_FAILED, source="test", agent_id="A-001", task_id="T-002"),
        ]
        tasks = [make_task("T-001"), make_task("T-002")]
        au = collect_agent_utilization(events, tasks, [])
        assert au.total == 1
        row = au.items[0]
        assert row.assignments == 2          # created 计数
        assert row.success_count == 1        # completed 计数
        assert row.failed_count == 1         # failed 计数
        assert row.success_rate == 0.5

    def test_success_rate_all_success(self, logger):
        events = [
            logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-001"),
            logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-002"),
            logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-003"),
            logger.record(EventType.ASSIGNMENT_COMPLETED, source="test", agent_id="A-001", task_id="T-001"),
            logger.record(EventType.ASSIGNMENT_COMPLETED, source="test", agent_id="A-001", task_id="T-002"),
            logger.record(EventType.ASSIGNMENT_COMPLETED, source="test", agent_id="A-001", task_id="T-003"),
        ]
        au = collect_agent_utilization(events, [], [])
        assert au.items[0].success_rate == 1.0

    def test_success_rate_no_terminal_zero(self, logger):
        events = [
            logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-001"),
        ]
        au = collect_agent_utilization(events, [], [])
        assert au.items[0].success_rate == 0.0  # 无 completed/failed → 0.0 不除零

    def test_multiple_agents_independent(self, logger):
        events = [
            logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-001"),
            logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-002", task_id="T-002"),
            logger.record(EventType.ASSIGNMENT_COMPLETED, source="test", agent_id="A-001", task_id="T-001"),
            logger.record(EventType.ASSIGNMENT_FAILED, source="test", agent_id="A-002", task_id="T-002"),
        ]
        au = collect_agent_utilization(events, [], [])
        by_id = {r.agent_id: r for r in au.items}
        assert by_id["A-001"].success_rate == 1.0
        assert by_id["A-002"].success_rate == 0.0

    def test_only_assignment_events_counted(self, logger):
        """非 assignment 事件不参与计数 (task.created 等)。"""
        events = [
            logger.record(EventType.TASK_CREATED, source="test", agent_id="A-001", task_id="T-001"),
            logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-001"),
        ]
        au = collect_agent_utilization(events, [], [])
        assert au.items[0].assignments == 1

    def test_sorted_by_agent_id(self, logger):
        events = [
            logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-002", task_id="T-001"),
            logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-002"),
        ]
        au = collect_agent_utilization(events, [], [])
        assert [r.agent_id for r in au.items] == ["A-001", "A-002"]


class TestAgentUtilizationProjects:
    def test_projects_from_tasks(self, logger):
        events = [
            logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-001"),
            logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-002"),
        ]
        tasks = [make_task("T-001", project="P-alpha"), make_task("T-002", project="P-beta")]
        au = collect_agent_utilization(events, tasks, [])
        row = au.items[0]
        assert row.projects == ["P-alpha", "P-beta"]
        assert row.projects_count == 2

    def test_projects_dedup_sorted(self, logger):
        events = [
            logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-001"),
            logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-002"),
            logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-003"),
        ]
        tasks = [make_task("T-001", project="P-z"), make_task("T-002", project="P-z"),
                 make_task("T-003", project="P-a")]
        row = collect_agent_utilization(events, tasks, []).items[0]
        assert row.projects == ["P-a", "P-z"]  # 排序去重
        assert row.projects_count == 2

    def test_orphan_event_no_project(self, logger):
        """task_id 无对应任务 → 分配计数保留, 但项目不归属 (KISS)。"""
        events = [
            logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-NOPE"),
            logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-001"),
        ]
        tasks = [make_task("T-001", project="P-1")]
        row = collect_agent_utilization(events, tasks, []).items[0]
        assert row.assignments == 2
        assert row.projects == ["P-1"]

    def test_agent_without_task_events_no_projects(self, logger):
        events = [logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id=None)]
        row = collect_agent_utilization(events, [], []).items[0]
        assert row.assignments == 1
        assert row.projects == []


class TestAgentUtilizationRegistry:
    def test_role_status_from_registry(self, logger):
        events = [
            logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-001"),
        ]
        agents = [Agent(id="A-001", name="A-001", role="dev", status=AgentStatus.WORKING)]
        row = collect_agent_utilization(events, [], agents).items[0]
        assert row.role == "dev"
        assert row.status == "WORKING"

    def test_unregistered_agent_included(self, logger):
        """事件中出现但未注册的 agent_id 也纳入 (事件维度完整), role/status 缺省。"""
        events = [
            logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-999", task_id="T-001"),
        ]
        agents = [Agent(id="A-001", name="A-001", role="dev")]
        au = collect_agent_utilization(events, [], agents)
        by_id = {r.agent_id: r for r in au.items}
        assert by_id["A-999"].assignments == 1
        assert by_id["A-999"].role == ""
        assert by_id["A-999"].status == ""

    def test_registered_inactive_agent_row(self, logger):
        """已注册但无活动 → 0 指标行 (注册表兜底)。"""
        agents = [Agent(id="A-001", name="A-001", role="ops"), Agent(id="A-002", name="A-002", role="dev")]
        au = collect_agent_utilization([], [], agents)
        assert au.total == 2
        assert all(r.assignments == 0 for r in au.items)


class TestRuntimeUsage:
    def test_empty(self, logger):
        ru = collect_runtime_usage([], [])
        assert isinstance(ru, RuntimeUsageSummary)
        assert ru.total == 0
        assert ru.items == []

    def test_counts_and_rate(self, logger):
        requests = [
            make_execution("EX-001", task_id="T-001", runtime_id="R-hermes", status=ExecutionStatus.SUCCESS),
            make_execution("EX-002", task_id="T-002", runtime_id="R-hermes", status=ExecutionStatus.FAILED),
            make_execution("EX-003", task_id="T-003", runtime_id="R-hermes", status=ExecutionStatus.SUCCESS),
        ]
        ru = collect_runtime_usage(requests, [])
        assert ru.total == 1
        row = ru.items[0]
        assert row.runtime_id == "R-hermes"
        assert row.execution_count == 3
        assert row.success == 2
        assert row.failed == 1
        assert row.success_rate == 2 / 3

    def test_multiple_runtimes_grouped(self, logger):
        requests = [
            make_execution("EX-001", task_id="T-001", runtime_id="R-a", status=ExecutionStatus.SUCCESS),
            make_execution("EX-002", task_id="T-002", runtime_id="R-a", status=ExecutionStatus.FAILED),
            make_execution("EX-003", task_id="T-003", runtime_id="R-b", status=ExecutionStatus.SUCCESS),
        ]
        ru = collect_runtime_usage(requests, [])
        by_id = {r.runtime_id: r for r in ru.items}
        assert by_id["R-a"].execution_count == 2
        assert by_id["R-a"].success_rate == 0.5
        assert by_id["R-b"].execution_count == 1
        assert by_id["R-b"].success_rate == 1.0

    def test_non_terminal_statuses_in_count_only(self, logger):
        """PENDING/RUNNING 计入 execution_count, 不计 success/failed。"""
        requests = [
            make_execution("EX-001", task_id="T-001", runtime_id="R-1", status=ExecutionStatus.SUCCESS),
            make_execution("EX-002", task_id="T-002", runtime_id="R-1", status=ExecutionStatus.PENDING),
            make_execution("EX-003", task_id="T-003", runtime_id="R-1", status=ExecutionStatus.RUNNING),
        ]
        row = collect_runtime_usage(requests, []).items[0]
        assert row.execution_count == 3
        assert row.success == 1
        assert row.failed == 0
        assert row.success_rate == 1 / 3

    def test_projects_attribution(self, logger):
        requests = [
            make_execution("EX-001", task_id="T-001", runtime_id="R-1", status=ExecutionStatus.SUCCESS),
            make_execution("EX-002", task_id="T-002", runtime_id="R-1", status=ExecutionStatus.SUCCESS),
        ]
        tasks = [make_task("T-001", project="P-x"), make_task("T-002", project="P-y")]
        row = collect_runtime_usage(requests, tasks).items[0]
        assert row.projects == ["P-x", "P-y"]

    def test_orphan_execution_no_project(self, logger):
        requests = [
            make_execution("EX-001", task_id="T-NOPE", runtime_id="R-1", status=ExecutionStatus.SUCCESS),
            make_execution("EX-002", task_id="T-001", runtime_id="R-1", status=ExecutionStatus.SUCCESS),
        ]
        tasks = [make_task("T-001", project="P-1")]
        row = collect_runtime_usage(requests, tasks).items[0]
        assert row.execution_count == 2
        assert row.projects == ["P-1"]

    def test_empty_runtime_id_unknown(self, logger):
        requests = [
            make_execution("EX-001", task_id="T-001", runtime_id="", status=ExecutionStatus.SUCCESS),
            make_execution("EX-002", task_id="T-002", runtime_id="R-1", status=ExecutionStatus.SUCCESS),
        ]
        ru = collect_runtime_usage(requests, [])
        by_id = {r.runtime_id: r for r in ru.items}
        assert by_id["unknown"].execution_count == 1  # 计数守恒 (模型允许空 runtime_id)
        assert by_id["R-1"].execution_count == 1

    def test_sorted_by_runtime_id(self, logger):
        requests = [
            make_execution("EX-001", task_id="T-001", runtime_id="R-b", status=ExecutionStatus.SUCCESS),
            make_execution("EX-002", task_id="T-002", runtime_id="R-a", status=ExecutionStatus.SUCCESS),
        ]
        ru = collect_runtime_usage(requests, [])
        assert [r.runtime_id for r in ru.items] == ["R-a", "R-b"]


class TestWorkspaceCollectorWiring:
    def test_agent_utilization_from_stores(self, collector, task_store, agent_registry, logger):
        """WorkspaceCollector.agent_utilization 读 store 聚合 (集成路径)。"""
        task_store.create(make_task("T-001", project="P-1"))
        agent_registry.register(Agent(id="A-001", name="A-001", role="dev"))[0]
        logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-001")
        logger.record(EventType.ASSIGNMENT_COMPLETED, source="test", agent_id="A-001", task_id="T-001")
        au = _ws_collector(collector).agent_utilization()
        assert au.total == 1
        row = au.items[0]
        assert row.projects == ["P-1"]
        assert row.assignments == 1
        assert row.success_rate == 1.0

    def test_runtime_usage_from_stores(self, collector, task_store, runtime_store):
        task_store.create(make_task("T-001", project="P-1"))
        runtime_store.save_execution(make_execution(
            "EX-001", task_id="T-001", runtime_id="R-1", status=ExecutionStatus.SUCCESS))
        runtime_store.save_execution(make_execution(
            "EX-002", task_id="T-001", runtime_id="R-1", status=ExecutionStatus.FAILED))
        ru = _ws_collector(collector).runtime_usage()
        assert ru.total == 1
        row = ru.items[0]
        assert row.runtime_id == "R-1"
        assert row.execution_count == 2
        assert row.success_rate == 0.5
        assert row.projects == ["P-1"]

    def test_empty_stores(self, collector):
        ws = _ws_collector(collector)
        assert ws.agent_utilization().total == 0
        assert ws.runtime_usage().total == 0

    def test_read_only_no_events_written(self, collector, logger):
        """只读铁律: 聚合不追加任何事件 (审计由 CLI 命令层负责)。"""
        logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-001")
        before = collector._event_store.count()
        ws = _ws_collector(collector)
        ws.agent_utilization()
        ws.runtime_usage()
        assert collector._event_store.count() == before

    def test_pure_functions_do_not_mutate_inputs(self, logger):
        """纯函数不修改输入列表 (序列化数据输入, 同 calculators 模式)。"""
        events = [logger.record(EventType.ASSIGNMENT_CREATED, source="test", agent_id="A-001", task_id="T-001")]
        tasks = [make_task("T-001")]
        requests = [make_execution("EX-001", task_id="T-001", runtime_id="R-1", status=ExecutionStatus.SUCCESS)]
        events_before = [e.model_dump(mode="json") for e in events]
        tasks_before = [t.to_dict() for t in tasks]
        req_before = [r.to_dict() for r in requests]
        collect_agent_utilization(events, tasks, [])
        collect_runtime_usage(requests, tasks)
        assert [e.model_dump(mode="json") for e in events] == events_before
        assert [t.to_dict() for t in tasks] == tasks_before
        assert [r.to_dict() for r in requests] == req_before
