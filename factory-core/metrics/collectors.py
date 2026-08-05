"""metrics/collectors.py — MetricsCollector: 只读聚合全部 store → FactoryMetrics。

设计依据:
- phase5b-status.md: 数据来源 EventStore/TaskStore/AgentRegistry/WorkflowStore/
  ExecutionStore (只读) — ExecutionStore 在本仓库即 RuntimeStore 的执行记录节
  (runtimes.json executions, runtime/store.py), 与 dashboard 收集器同款装配。
- ADR-0015 决策 1/5: 纯计算不持久化 (event-model §6 按需聚合); 只读铁律 — 本类
  只调用各 store/registry 的读接口 (query/list/count), 不调用任何写方法; 事件
  审计 (metrics.viewed) 由 CLI 命令层 (cmd_metrics) 经 EventLogger 发出, 收集器
  自身不发事件 (模块解耦, 同 DashboardCollector 模式)。

project_id 过滤边界 (同 DashboardCollector): Task/Event 有项目维度; Execution/
Agent/Workflow 定义无项目维度, 恒为全局。
"""

from __future__ import annotations

from agents.registry import AgentRegistry
from events.store import EventStore
from runtime.store import RuntimeStore
from tasks.store import TaskStore
from workflows.store import WorkflowStore

from .calculators import (
    calculate_agent_metrics,
    calculate_execution_metrics,
    calculate_failure_metrics,
    calculate_task_metrics,
    calculate_validation_metrics,
    calculate_workflow_metrics,
)
from .models import FactoryMetrics


class MetricsCollector:
    """只读聚合器: 输入各 store, 输出 FactoryMetrics (查询时刻投影)。"""

    def __init__(
        self,
        *,
        event_store: EventStore,
        task_store: TaskStore,
        agent_registry: AgentRegistry,
        workflow_store: WorkflowStore,
        runtime_store: RuntimeStore,
        project_id: str | None = None,
    ) -> None:
        self._event_store = event_store
        self._task_store = task_store
        self._agent_registry = agent_registry
        self._workflow_store = workflow_store
        self._runtime_store = runtime_store
        self._project_id = project_id

    # ------------------------------------------------------------------ 主入口

    def collect(self) -> FactoryMetrics:
        """聚合全部 store → FactoryMetrics (只读, 无副作用)。"""
        events = self._event_store.query(project_id=self._project_id)
        tasks = self._task_store.list(project=self._project_id)
        agents = self._agent_registry.list()
        runs = self._workflow_store.list_runs()
        definitions = self._workflow_store.list_workflows()
        requests = self._runtime_store.list_executions()

        agent_metrics, agents_total = calculate_agent_metrics(agents, events)
        return FactoryMetrics(
            project_id=self._project_id,
            tasks=calculate_task_metrics(tasks, events),
            executions=calculate_execution_metrics(requests),
            agents=agent_metrics,
            agents_total=agents_total,
            workflows=calculate_workflow_metrics(runs, definitions),
            validation=calculate_validation_metrics(events),
            failures=calculate_failure_metrics(events),
        )
