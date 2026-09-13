"""metrics/workspace.py — Workspace 级只读聚合 (Phase 6B, ADR-0017)。

设计依据:
- phase6b-status.md: Workspace Summary / project comparison / Agent Utilization /
  Runtime Usage / 跨项目事件时间线 — 全部为「多项目聚合展示」, 只读。
- ADR-0017 决策 1/2: **复用不复制** — 项目对比 (WorkspaceComparison) 直接复用
  MetricsCollector (每项目 collect), Agent Utilization / Runtime Usage 为纯函数
  聚合 (输入序列化数据, 不碰 store, 同 metrics/calculators.py 模式)。

只读铁律: 本模块只调用各 store/registry 的读接口 (query/list/count), 不调用
任何写方法; 不发任何事件 — workspace.*.viewed 审计事件由 CLI 命令层发出
(同 DashboardCollector / MetricsCollector 边界, ADR-0015 决策 1)。

口径 (与 ADR-0015 决策 3 保持一致, 不另立口径):
- Agent Utilization: assignment_count = agent.assignment.created 数; 成败 =
  completed/failed 数; success_rate = completed / (completed + failed);
  projects = assignment 事件 task_id → task.project (无对应任务的孤儿事件不归属)。
- Runtime Usage: 请求状态为权威 (SUCCESS/FAILED); success_rate = success / 全部执行;
  projects = execution req.task_id → task.project (孤儿执行不归属, runtime_id 空归
  "unknown")。
"""

from __future__ import annotations

from collections import Counter, defaultdict

from agents.models import Agent
from agents.registry import AgentRegistry
from events.models import Event, EventType
from events.store import EventStore
from runtime.models import ExecutionRequest, ExecutionStatus
from runtime.store import RuntimeStore
from tasks.models import Task
from tasks.store import TaskStore
from workflows.store import WorkflowStore

from .collectors import MetricsCollector
from .models import (
    AgentUtilizationRow,
    AgentUtilizationSummary,
    FactoryMetrics,
    ProjectComparisonRow,
    RuntimeUsageRow,
    RuntimeUsageSummary,
    WorkspaceComparison,
)

# 汇总行项目标记 (WorkspaceComparison.totals.project, 全局聚合)
TOTALS_PROJECT = "*"


# ------------------------------------------------------------------ Agent Utilization (纯函数)

def collect_agent_utilization(
    events: list[Event],
    tasks: list[Task],
    agents: list[Agent],
) -> AgentUtilizationSummary:
    """跨项目 Agent 使用统计 (从 agent.assignment.* 事件聚合, 只读)。

    与 calculate_agent_metrics 同计数口径 (created/completed/failed 事件计数);
    额外聚合 projects = 该 agent 参与过的任务所在项目 (task_id → task.project,
    孤儿事件不归属 — 无对应任务无法判定项目, KISS)。注册表兜底: 无活动 Agent
    出 0 指标; 事件中出现的未注册 agent_id 也纳入 (事件维度完整, 排序输出)。
    """
    task_proj = {t.id: t.project for t in tasks}
    created: Counter[str] = Counter()
    completed: Counter[str] = Counter()
    failed: Counter[str] = Counter()
    agent_projects: dict[str, set[str]] = defaultdict(set)
    for e in events:
        if not e.agent_id:
            continue
        if e.type is EventType.ASSIGNMENT_CREATED:
            created[e.agent_id] += 1
        elif e.type is EventType.ASSIGNMENT_COMPLETED:
            completed[e.agent_id] += 1
        elif e.type is EventType.ASSIGNMENT_FAILED:
            failed[e.agent_id] += 1
        if e.task_id and e.task_id in task_proj:
            agent_projects[e.agent_id].add(task_proj[e.task_id])

    active = set(created) | set(completed) | set(failed)
    info = {a.id: a for a in agents}
    items = []
    for agent_id in sorted({a.id for a in agents} | active):
        c, s, f = created.get(agent_id, 0), completed.get(agent_id, 0), failed.get(agent_id, 0)
        a = info.get(agent_id)
        projects = sorted(agent_projects.get(agent_id, ()))
        items.append(AgentUtilizationRow(
            agent_id=agent_id,
            role=a.role if a is not None else "",
            status=a.status.value if a is not None else "",
            projects=projects,
            projects_count=len(projects),
            assignments=c,
            success_count=s,
            failed_count=f,
            success_rate=(s / (s + f)) if (s + f) else 0.0,
        ))
    return AgentUtilizationSummary(items=items, total=len(items))


# ------------------------------------------------------------------ Runtime Usage (纯函数)

def collect_runtime_usage(
    requests: list[ExecutionRequest],
    tasks: list[Task],
) -> RuntimeUsageSummary:
    """Runtime 使用统计 (从 execution 记录聚合, 请求状态为权威, 只读)。

    按 runtime_id 分组: execution_count / success / failed / success_rate
    (同 calculate_execution_metrics 口径 — SUCCESS/FAILED 计数, 全部执行作分母);
    projects = 使用该 runtime 的任务所在项目 (req.task_id → task.project, 孤儿
    执行不归属)。runtime_id 为空 (模型允许) 归 "unknown", 保证计数守恒。
    """
    task_proj = {t.id: t.project for t in tasks}
    rows: dict[str, dict] = {}
    for req in requests:
        rid = req.runtime_id or "unknown"
        row = rows.setdefault(rid, {"success": 0, "failed": 0, "count": 0, "projects": set()})
        row["count"] += 1
        if req.status is ExecutionStatus.SUCCESS:
            row["success"] += 1
        elif req.status is ExecutionStatus.FAILED:
            row["failed"] += 1
        pid = task_proj.get(req.task_id)
        if pid:
            row["projects"].add(pid)
    items = []
    for runtime_id in sorted(rows):
        row = rows[runtime_id]
        total = row["count"]
        items.append(RuntimeUsageRow(
            runtime_id=runtime_id,
            execution_count=total,
            success=row["success"],
            failed=row["failed"],
            success_rate=(row["success"] / total) if total else 0.0,
            projects=sorted(row["projects"]),
        ))
    return RuntimeUsageSummary(items=items, total=len(items))


# ------------------------------------------------------------------ WorkspaceCollector (装配 + 对比)

class WorkspaceCollector:
    """Workspace 级只读聚合器: 项目对比 (复用 MetricsCollector) + 两张运营视图。

    装配模式同 DashboardCollector / MetricsCollector (依赖注入 store 对象,
    只读铁律一致 — 本类只调用各 store 读接口, 不发事件)。
    """

    def __init__(
        self,
        *,
        event_store: EventStore,
        task_store: TaskStore,
        agent_registry: AgentRegistry,
        workflow_store: WorkflowStore,
        runtime_store: RuntimeStore,
    ) -> None:
        self._event_store = event_store
        self._task_store = task_store
        self._agent_registry = agent_registry
        self._workflow_store = workflow_store
        self._runtime_store = runtime_store

    # ------------------------------------------------------------------ 项目对比 (metrics --workspace)

    def comparison(self, project_ids: list[str] | None = None) -> WorkspaceComparison:
        """项目对比表: 每项目 MetricsCollector(project_id) 行 + 全局汇总行。

        project_ids 缺省/为空 → 从任务 project 值 ∪ 事件 project_id 值推导
        (覆盖「有数据但未注册到 workspace」的项目)。汇总行 = 全局聚合
        (project_id=None) 的同一组口径, project 标记为 "*"。
        """
        ids = self._resolve_project_ids(project_ids)
        rows = [self._row(pid, self._collect_project(pid)) for pid in sorted(ids)]
        totals = self._row(TOTALS_PROJECT, self._collect_project(None))
        return WorkspaceComparison(projects=rows, total=len(rows), totals=totals)

    def _collect_project(self, project_id: str | None) -> FactoryMetrics:
        """单项目 FactoryMetrics (复用 MetricsCollector 核心计算, 不复制)。"""
        return MetricsCollector(
            event_store=self._event_store,
            task_store=self._task_store,
            agent_registry=self._agent_registry,
            workflow_store=self._workflow_store,
            runtime_store=self._runtime_store,
            project_id=project_id,
        ).collect()

    def _resolve_project_ids(self, project_ids: list[str] | None) -> list[str]:
        """项目 id 集 = 显式传入 (workspace 定义) ∪ 任务 project 值 ∪ 事件 project_id 值。

        始终合并任务/事件维度 — 对比表完整呈现「有数据但未注册到 workspace」的
        项目 (同 Dashboard Projects View 语义, ADR-0016 决策 5); workspace 定义
        项目即使零数据也保留 (对比种子行)。
        """
        ids = {p for p in (project_ids or []) if p}
        ids |= {t.project for t in self._task_store.list()}
        ids |= {e.project_id for e in self._event_store.query() if e.project_id}
        return sorted(ids)

    @staticmethod
    def _row(pid: str, m: FactoryMetrics) -> ProjectComparisonRow:
        """FactoryMetrics 六域子模型 → 对比行 (口径同 ADR-0015 决策 3)。"""
        x = m.executions
        return ProjectComparisonRow(
            project=pid,
            tasks_total=m.tasks.total,
            tasks_completed=m.tasks.completed,
            tasks_failed=m.tasks.failed,
            task_success_rate=m.tasks.success_rate,
            execution_count=x.total,
            execution_success=x.success,
            execution_failed=x.failed,
            execution_success_rate=(x.success / x.total) if x.total else 0.0,
            workflow_runs=m.workflows.run_count,
            workflow_success_rate=m.workflows.success_rate,
            validation_rules=m.validation.total_rules,
            validation_pass_rate=m.validation.pass_rate,
        )

    # ------------------------------------------------------------------ 运营视图 (Dashboard --workspace)

    def agent_utilization(self) -> AgentUtilizationSummary:
        """跨项目 Agent 使用统计 (全量事件查询, 只读)。"""
        return collect_agent_utilization(
            self._event_store.query(), self._task_store.list(), self._agent_registry.list(),
        )

    def runtime_usage(self) -> RuntimeUsageSummary:
        """Runtime 使用统计 (全部 execution 记录, 只读)。"""
        return collect_runtime_usage(self._runtime_store.list_executions(), self._task_store.list())
