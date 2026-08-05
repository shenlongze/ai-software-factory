"""dashboard/collector.py — DashboardCollector: 只读聚合全部 store → FactorySnapshot。

设计依据:
- phase4c4-status.md: DashboardCollector 读 TaskStore/AgentRegistry/WorkflowStore/
  RuntimeStore/EventStore/CheckpointStore → FactorySnapshot (只读, 不修改任何状态)
- dashboard-design.md §1.1: 只读投影 — 本类只调用各 store/registry 的读接口
  (list/get/count/query), 不调用任何写方法, 聚合期间不修改任何状态。

只读铁律 (工程规则): 聚合 = 纯查询函数组合, 无副作用; 事件审计 (dashboard.viewed)
由 CLI 命令层 (cmd_dashboard) 经 EventLogger 发出, 收集器自身不发事件
(模块解耦, 同 RecoveryService 装配模式 — 依赖注入 store 对象)。

project_id 过滤边界 (Phase 6A 增强): Task/Event/Execution/Workflow 运行实例有
项目维度 — Execution/WorkflowRun 无 project 字段, 经 task_id → task.project 归属
过滤 (孤儿记录不计入); Agent/Workflow 定义无项目维度, 恒为全局。Projects View
(Phase 6A) 按 workspace 项目定义 ∪ 任务 project 值聚合每项目计数。
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from agents.registry import AgentRegistry
from events.models import EventType
from events.store import EventStore
from metrics.collectors import MetricsCollector
from metrics.models import FactoryMetrics
from recovery.checkpoint import CheckpointStore
from runtime.store import RuntimeStore
from runtimes.catalog import RuntimeCatalog
from runtimes.store import CatalogStore
from tasks.store import TaskStore
from workflows.store import WorkflowStore

from .models import (
    AgentSnapshot,
    CheckpointSnapshot,
    ExecutionSnapshot,
    FactorySnapshot,
    MetricsSnapshot,
    ProjectSnapshot,
    ProjectsSnapshot,
    RuntimeCatalogSnapshot,
    TaskSnapshot,
    ValidationSummary,
    WorkflowSnapshot,
)


class DashboardCollector:
    """只读聚合器: 输入各 store, 输出 FactorySnapshot (查询时刻投影)。"""

    def __init__(
        self,
        *,
        task_store: TaskStore,
        agent_registry: AgentRegistry,
        workflow_store: WorkflowStore,
        runtime_store: RuntimeStore,
        catalog_store: CatalogStore | None = None,
        event_store: EventStore,
        checkpoint_store: CheckpointStore,
        project_id: str | None = None,
        projects: list | None = None,  # list[ProjectDefinition] (Phase 6A Projects View)
        recent_limit: int = 10,
    ) -> None:
        self._task_store = task_store
        self._agent_registry = agent_registry
        self._workflow_store = workflow_store
        self._runtime_store = runtime_store
        self._catalog_store = catalog_store
        self._event_store = event_store
        self._checkpoint_store = checkpoint_store
        self._project_id = project_id
        self._projects = projects or []
        self._recent_limit = max(1, recent_limit)

    # ------------------------------------------------------------------ 主入口

    def collect(self) -> FactorySnapshot:
        """聚合全部 store → FactorySnapshot (只读, 无副作用)。"""
        return FactorySnapshot(
            project_id=self._project_id,
            tasks=self._collect_tasks(),
            agents=self._collect_agents(),
            workflows=self._collect_workflows(),
            executions=self._collect_executions(),
            checkpoints=self._collect_checkpoints(),
            catalog=self._collect_catalog(),
            projects=self._collect_projects(),
            metrics=self._collect_metrics(),
            factory_metrics=self._collect_factory_metrics(),
            recent_events=self._collect_recent_events(),
        )

    # ------------------------------------------------------------------ 分域聚合

    def _collect_tasks(self) -> TaskSnapshot:
        tasks = self._task_store.list(project=self._project_id)
        by_status = Counter(t.status.value for t in tasks)
        by_project = Counter(t.project for t in tasks)
        done = by_status.get("DONE", 0)
        return TaskSnapshot(
            total=len(tasks),
            by_status=dict(sorted(by_status.items())),
            by_project=dict(sorted(by_project.items())),
            active=len(tasks) - done,
            done=done,
            items=[t.to_dict() for t in tasks],
        )

    def _collect_agents(self) -> AgentSnapshot:
        agents = self._agent_registry.list()
        by_status = Counter(a.status.value for a in agents)
        by_role = Counter(a.role for a in agents)
        return AgentSnapshot(
            total=len(agents),
            by_status=dict(sorted(by_status.items())),
            by_role=dict(sorted(by_role.items())),
            working=by_status.get("WORKING", 0),
            available=by_status.get("AVAILABLE", 0),
            items=[a.to_dict() for a in agents],
        )

    def _collect_workflows(self) -> WorkflowSnapshot:
        definitions = self._workflow_store.list_workflows()
        runs = self._workflow_store.list_runs()
        if self._project_id is not None:
            # Phase 6A 项目隔离: 运行实例按 run.task_id → task.project 归属过滤
            task_proj = self._task_project_map()
            runs = [r for r in runs if task_proj.get(r.task_id) == self._project_id]
        by_status = Counter(r.status.value for r in runs)
        return WorkflowSnapshot(
            definitions=len(definitions),
            runs_total=len(runs),
            runs_by_status=dict(sorted(by_status.items())),
            definitions_items=[w.to_dict() for w in definitions],
            runs_items=[r.to_dict() for r in runs],
        )

    def _collect_executions(self) -> ExecutionSnapshot:
        requests = self._runtime_store.list_executions()
        if self._project_id is not None:
            # Phase 6A 项目隔离: 执行请求按 req.task_id → task.project 归属过滤
            task_proj = self._task_project_map()
            requests = [r for r in requests if task_proj.get(r.task_id) == self._project_id]
        results = {res.request_id: res for res in self._runtime_store.list_results()}
        by_status = Counter(req.status.value for req in requests)
        success = by_status.get("SUCCESS", 0)
        failed = by_status.get("FAILED", 0)
        items = []
        for req in requests:
            item = req.to_dict()
            res = results.get(req.id)
            item["result"] = res.to_dict() if res is not None else None
            items.append(item)
        return ExecutionSnapshot(
            total=len(requests),
            by_status=dict(sorted(by_status.items())),
            success=success,
            failed=failed,
            success_rate=(success / len(requests)) if requests else 0.0,
            items=items,
        )

    def _collect_checkpoints(self) -> CheckpointSnapshot:
        checkpoints = self._checkpoint_store.list()
        return CheckpointSnapshot(
            total=len(checkpoints),
            tasks=[c.task_id for c in checkpoints],
            items=[c.to_dict() for c in checkpoints],
        )

    def _task_project_map(self) -> dict[str, str]:
        """task_id → project 归属映射 (Projects View 与项目隔离共用, 只读)。"""
        return {t.id: t.project for t in self._task_store.list()}

    def _collect_projects(self) -> ProjectsSnapshot:
        """Projects View (Phase 6A): workspace 定义 ∪ 任务 project 值的每项目计数。

        计数口径 (与 models.ProjectSnapshot docstring 一致): task_count 直接按
        Task.project; workflow/execution 经 task_id → project 归属 (无对应任务
        的运行/执行不计入 — 孤儿记录无法归属, KISS); success_rate = 该项目
        SUCCESS 执行 / 总执行。project_id 过滤时只保留该项目 (缺省补零行)。
        """
        rows: dict[str, dict] = {}
        for pd in self._projects:  # workspace 项目定义 (含 0 计数种子)
            rows[pd.id] = self._project_row(pd.id, name=pd.name, language=pd.language, status=pd.status)
        task_proj = self._task_project_map()
        for t in self._task_store.list():
            pid = t.project or "default"
            task_proj[t.id] = pid
            rows.setdefault(pid, self._project_row(pid))["task_count"] += 1
        for r in self._workflow_store.list_runs():
            pid = task_proj.get(r.task_id)
            if pid is not None:
                rows.setdefault(pid, self._project_row(pid))["workflow_count"] += 1
        for req in self._runtime_store.list_executions():
            pid = task_proj.get(req.task_id)
            if pid is None:
                continue
            row = rows.setdefault(pid, self._project_row(pid))
            row["execution_count"] += 1
            if req.status.value == "SUCCESS":
                row["execution_success"] += 1
            elif req.status.value == "FAILED":
                row["execution_failed"] += 1
        items = []
        for pid in sorted(rows):
            row = rows[pid]
            total = row["execution_count"]
            row["success_rate"] = (row["execution_success"] / total) if total else 0.0
            items.append(ProjectSnapshot(**row))
        if self._project_id is not None:
            items = [p for p in items if p.id == self._project_id]
            if not items:
                items = [ProjectSnapshot(id=self._project_id, name=self._project_id, status="unknown")]
        return ProjectsSnapshot(total=len(items), items=items)

    @staticmethod
    def _project_row(pid: str, *, name: str = "", language: str = "", status: str = "unknown") -> dict:
        return {
            "id": pid, "name": name or pid, "language": language, "status": status,
            "task_count": 0, "workflow_count": 0, "execution_count": 0,
            "execution_success": 0, "execution_failed": 0,
        }

    def _collect_catalog(self) -> RuntimeCatalogSnapshot:
        """能力目录汇总 (RuntimeCatalog 读路径, 含默认定义基线; 未装配 → 空快照)。

        只读: 仅调 catalog.list() 读接口; 不写 catalog.json、不发事件
        (与 dashboard.viewed 由 CLI 命令层发出同款边界, ADR-0014 决策 6)。
        """
        if self._catalog_store is None:
            return RuntimeCatalogSnapshot()
        catalog = RuntimeCatalog(self._catalog_store)
        definitions = catalog.list()
        by_type = Counter(d.type for d in definitions)
        by_status = Counter(d.status.value for d in definitions)
        return RuntimeCatalogSnapshot(
            total=len(definitions),
            by_type=dict(sorted(by_type.items())),
            by_status=dict(sorted(by_status.items())),
            items=[d.to_dict() for d in definitions],
        )

    def _collect_metrics(self) -> MetricsSnapshot:
        counts = self._event_store.count_by_type()
        # 验证汇总: rule.completed 的结果列 (PASS/FAIL/SKIP/ERROR) 为粒度数据,
        # 单次验证的每规则一条, 无重复计数 (validation.* 事件序见 phase3a-status.md)。
        rule_events = self._event_store.query(event_type=EventType.VALIDATION_RULE_COMPLETED)
        results = Counter(e.result or "" for e in rule_events)
        return MetricsSnapshot(
            event_count=self._event_store.count(),
            event_type_counts=counts,
            validation=ValidationSummary(
                total=len(rule_events),
                pass_count=results.get("PASS", 0),
                fail_count=results.get("FAIL", 0),
                skip_count=results.get("SKIP", 0),
                error_count=results.get("ERROR", 0),
                runs=counts.get(EventType.VALIDATION_COMPLETED.value, 0),
                failed_runs=counts.get(EventType.VALIDATION_FAILED.value, 0),
            ),
            recovery_started=counts.get(EventType.RECOVERY_STARTED.value, 0),
            recovery_completed=counts.get(EventType.RECOVERY_COMPLETED.value, 0),
            recovery_failed=counts.get(EventType.RECOVERY_FAILED.value, 0),
        )

    def _collect_factory_metrics(self) -> FactoryMetrics:
        """工厂生产指标 (Phase 5B, ADR-0015): 复用 MetricsCollector 只读聚合。

        只读: 仅调各 store 读接口; 不发事件 (metrics.viewed 由 CLI 命令层发出,
        同 dashboard.viewed 边界)。
        """
        return MetricsCollector(
            event_store=self._event_store,
            task_store=self._task_store,
            agent_registry=self._agent_registry,
            workflow_store=self._workflow_store,
            runtime_store=self._runtime_store,
            project_id=self._project_id,
        ).collect()

    def _collect_recent_events(self) -> list[dict[str, Any]]:
        """最近事件 (最近优先, 上限 recent_limit)。项目过滤时按项目时间线取尾段。"""
        if self._project_id is not None:
            events = self._event_store.query(project_id=self._project_id)
            tail = events[-self._recent_limit:][::-1]
        else:
            tail = self._event_store.recent(self._recent_limit)  # 已按 seq 倒序
        return [e.model_dump(mode="json") for e in tail]
