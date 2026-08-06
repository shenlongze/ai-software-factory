"""dashboard/models.py — FactorySnapshot 领域模型 (Pydantic v2, 只读投影)。

设计依据:
- phase4c4-status.md: FactorySnapshot (tasks/agents/workflows/executions/checkpoints/metrics 各汇总)
- dashboard-design.md §1.1: 只读投影 — Dashboard 不写任何状态, 所有数据来自各 store
  读接口的聚合; 崩溃/重启后重查即可重建。
- 参照 tasks/agents/runtime models 风格: to_dict() (model_dump(mode="json")) 供
  CLI --json 与测试断言共用; 时间戳统一 UTC 带时区。

Snapshot 语义: 快照是"查询时刻"的只读投影 — 每个子模型同时携带汇总计数
(by_status 等) 与明细 items (JSON 友好 dict), Rich 渲染器与 --json 消费同一数据源。
空工厂: 所有字段取默认值 (total=0 / 空 dict), collect 永不抛错。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from metrics.models import AgentUtilizationSummary, FactoryMetrics, RuntimeUsageSummary

from git.models import GitChange, GitCommit, GitContext


class TaskSnapshot(BaseModel):
    """任务汇总 (TaskStore)。状态为 TaskStatus 五态 (BACKLOG/ARCHITECTURE/DEVELOPMENT/TESTING/DONE)。"""

    total: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    by_project: dict[str, int] = Field(default_factory=dict)
    active: int = 0           # 非 DONE 任务数 (待办 + 进行中)
    done: int = 0
    items: list[dict[str, Any]] = Field(default_factory=list)  # Task.to_dict()

    def to_dict(self) -> dict:
        """JSON 友好序列化 (CLI --json / 测试断言共用)。"""
        return self.model_dump(mode="json")


class AgentSnapshot(BaseModel):
    """Agent 汇总 (AgentRegistry)。状态为 AgentStatus 三态 (AVAILABLE/WORKING/OFFLINE)。"""

    total: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    by_role: dict[str, int] = Field(default_factory=dict)
    working: int = 0
    available: int = 0
    items: list[dict[str, Any]] = Field(default_factory=list)  # Agent.to_dict()

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class WorkflowSnapshot(BaseModel):
    """工作流汇总 (WorkflowStore): 定义 + 运行实例双节 (同 store 单文件双节)。"""

    definitions: int = 0
    runs_total: int = 0
    runs_by_status: dict[str, int] = Field(default_factory=dict)
    definitions_items: list[dict[str, Any]] = Field(default_factory=list)
    runs_items: list[dict[str, Any]] = Field(default_factory=list)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class ExecutionSnapshot(BaseModel):
    """执行汇总 (RuntimeStore.executions + results)。状态为 ExecutionStatus 四态。

    success_rate 口径 (phase4c4-status.md §Metrics): SUCCESS / 全部执行 (含未完成),
    无执行时为 0.0。
    """

    total: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    success: int = 0
    failed: int = 0
    success_rate: float = 0.0
    items: list[dict[str, Any]] = Field(default_factory=list)  # request dict + result

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class CheckpointSnapshot(BaseModel):
    """Checkpoint 汇总 (CheckpointStore, 每任务单文件)。"""

    total: int = 0
    tasks: list[str] = Field(default_factory=list)
    items: list[dict[str, Any]] = Field(default_factory=list)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class ValidationSummary(BaseModel):
    """验证汇总: validation.rule.completed 结果列聚合 (PASS/FAIL/SKIP/ERROR 粒度数据)。"""

    total: int = 0
    pass_count: int = 0
    fail_count: int = 0
    skip_count: int = 0
    error_count: int = 0
    runs: int = 0          # validation.completed 次数
    failed_runs: int = 0   # validation.failed 次数

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class RuntimeCatalogSnapshot(BaseModel):
    """Runtime 能力目录汇总 (RuntimeCatalog, Phase 5A.1 / ADR-0014)。

    Catalog=能力描述层: 与 ExecutionSnapshot (实例执行记录) 语义分离。
    状态为 CatalogStatus 二态 (ACTIVE/DEPRECATED); items 含默认定义基线
    (hermes/echo/mock) + 已注册定义 (读路径合并, 见 runtimes/catalog.py)。
    """

    total: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    by_status: dict[str, int] = Field(default_factory=dict)
    items: list[dict[str, Any]] = Field(default_factory=list)  # RuntimeDefinition.to_dict()

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class ProviderSnapshot(BaseModel):
    """Provider 目录汇总 (ProviderRegistry, Phase 8A / ADR-0022)。

    数据源 = ProviderRegistry 只读合并视图 (默认定义基线 hermes + 已持久化
    定义, 见 providers/registry.py): 与 RuntimeCatalogSnapshot 语义平行 —
    Provider = 智能来源目录, Runtime Catalog = 执行机制目录, 两者数据空间
    完全分离 (providers/catalog.json vs runtimes/catalog.json)。状态为
    ProviderStatus 二态 (ACTIVE/DISABLED); default 为默认 Provider id
    (未设置 → None); items 含默认定义 + 已注册定义 (合并视图)。
    """

    total: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    by_status: dict[str, int] = Field(default_factory=dict)
    default: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)  # ProviderDefinition.to_dict()

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class ProjectSnapshot(BaseModel):
    """单个项目的汇总 (Phase 6A Workspace Layer, ADR-0016)。

    计数口径: task_count = 该项目任务数 (Task.project == id); workflow_count =
    归属该项目的运行实例数 (run.task_id → task.project); execution_count/success/
    failed = 归属该项目的执行请求数 (req.task_id → task.project); success_rate =
    execution_success / execution_count (无执行 0.0, 同 ExecutionSnapshot 口径)。
    项目 id 集 = workspace 定义 ∪ 任务中出现过的 project 值 (未定义项目 status
    为 "unknown") — Projects View 完整呈现工厂内所有项目维度。
    """

    id: str
    name: str = ""
    language: str = ""
    status: str = "active"
    task_count: int = 0
    workflow_count: int = 0
    execution_count: int = 0
    execution_success: int = 0
    execution_failed: int = 0
    success_rate: float = 0.0

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class ProjectsSnapshot(BaseModel):
    """Projects View 汇总: 每项目计数 + success rate (Phase 6A)。"""

    total: int = 0
    items: list[ProjectSnapshot] = Field(default_factory=list)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class MetricsSnapshot(BaseModel):
    """指标汇总 (事件聚合, 不建统计表 — event-model.md §6 按需聚合原则)。"""

    event_count: int = 0
    event_type_counts: dict[str, int] = Field(default_factory=dict)
    validation: ValidationSummary = Field(default_factory=ValidationSummary)
    recovery_started: int = 0
    recovery_completed: int = 0
    recovery_failed: int = 0

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class GitSnapshot(BaseModel):
    """Git View 汇总 (Phase 6C, ADR-0018): 每项目仓库状态 + 变更 + 提交。

    数据源 = GitService 只读聚合 (collector include_git=True 时装配, 默认关闭
    — 既有 dashboard 行为/成本完全不变, 同 ADR-0017 include_workspace 模式)。
    repos 含失败安全上下文 (非 git 目录 → is_repo=False + error 行照常展示);
    commits 跨项目按 created_at 倒序 (上限 git_commit_limit)。
    """

    total: int = 0                                    # 仓库数 (有 repository 的项目)
    repos: list[GitContext] = Field(default_factory=list)    # 每项目 GitContext (含 changes)
    changes: list[GitChange] = Field(default_factory=list)   # 全部工作区变更 (跨项目)
    commits: list[GitCommit] = Field(default_factory=list)   # 最近提交 (跨项目)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class ChangeSnapshot(BaseModel):
    """Change View 汇总 (Phase 6D, ADR-0019): Execution Git Snapshots + L4 验证。

    数据源 = ChangeStore 关联存储 (collector include_change=True 时装配, 默认
    关闭 — 既有 dashboard 行为/成本完全不变, 同 include_git 模式) + 事件库的
    change.validation.completed 事件聚合。snapshots 为持久化关联 (旧执行记录
    无快照 → 空, 兼容); validations 为最近 L4 判定 (含 task_id/status/message)。
    """

    total: int = 0                                     # Execution Git Snapshot 数
    snapshots: list[dict[str, Any]] = Field(default_factory=list)  # ExecutionGitSnapshot.to_dict()
    validation_total: int = 0                          # L4 change.validation.completed 数
    validations: list[dict[str, Any]] = Field(default_factory=list)  # 紧凑判定行

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class ChangeFlowSnapshot(BaseModel):
    """Change Flow View 汇总 (Phase 6E, ADR-0020): Triggers + Evaluations + Links。

    数据源 = ChangeTriggerRegistry (collector include_changeflow=True 时装配,
    默认关闭 — 既有 dashboard 行为/成本完全不变, 同 include_change 模式) +
    事件库的 change.trigger.evaluated / change.workflow.started|completed 事件
    聚合。triggers 为注册表快照 (只读); evaluations 为最近评估判定 (含
    triggered_workflow/run_id); workflow_links 为触发工作流链 (started/completed
    事件配对, result 取最近终态); by_status 为评估状态计数。
    """

    trigger_total: int = 0
    triggers: list[dict[str, Any]] = Field(default_factory=list)  # ChangeTrigger.to_dict()
    evaluation_total: int = 0
    evaluations: list[dict[str, Any]] = Field(default_factory=list)  # 紧凑评估行
    workflow_links_total: int = 0
    workflow_links: list[dict[str, Any]] = Field(default_factory=list)  # 触发链行
    by_status: dict[str, int] = Field(default_factory=dict)  # 评估状态计数

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class UnderstandingItem(BaseModel):
    """单个项目的理解行 (Phase 7 Understanding View, ADR-0021)。

    数据源 = UnderstandingService.analyze 只读分析 (规则推断, 禁 LLM);
    stage 来自 STAGES 注册表; confidence 为证据强度; present/missing 为
    7 类产物按 ARTIFACT_KEYS 序分列。
    """

    project: str = ""
    path: str = ""
    stage: str = ""
    confidence: float = 0.0
    present: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class UnderstandingSnapshot(BaseModel):
    """Understanding View 汇总 (Phase 7, ADR-0021): 每项目阶段 + 置信度 + 缺失。

    数据源 = collector include_understanding=True 时装配 (默认关闭 — 既有
    dashboard 行为/成本完全不变, 同 include_git 模式): CLI 命令层按 workspace
    项目 repository 本地目录注入 (project_id, path) 对, 每项目跑一次只读
    理解分析; 失败安全 (目录缺失/分析异常 → 跳过该项目)。
    """

    total: int = 0
    items: list[UnderstandingItem] = Field(default_factory=list)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class FactorySnapshot(BaseModel):
    """一次 Dashboard 查询的完整只读投影 (全 store 汇总 + 最近事件)。"""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    project_id: str | None = None
    tasks: TaskSnapshot = Field(default_factory=TaskSnapshot)
    agents: AgentSnapshot = Field(default_factory=AgentSnapshot)
    workflows: WorkflowSnapshot = Field(default_factory=WorkflowSnapshot)
    executions: ExecutionSnapshot = Field(default_factory=ExecutionSnapshot)
    checkpoints: CheckpointSnapshot = Field(default_factory=CheckpointSnapshot)
    catalog: RuntimeCatalogSnapshot = Field(default_factory=RuntimeCatalogSnapshot)
    # Phase 8A (ADR-0022): Provider View — 仅 --view provider 聚合 (collector
    # include_provider=True), 默认空 (既有 dashboard 行为/成本完全一致;
    # 数据源 = ProviderRegistry 只读合并视图, 智能来源目录)。
    providers: ProviderSnapshot = Field(default_factory=ProviderSnapshot)
    projects: ProjectsSnapshot = Field(default_factory=ProjectsSnapshot)  # Phase 6A (ADR-0016)
    metrics: MetricsSnapshot = Field(default_factory=MetricsSnapshot)
    factory_metrics: FactoryMetrics = Field(default_factory=FactoryMetrics)  # Phase 5B (ADR-0015)
    recent_events: list[dict[str, Any]] = Field(default_factory=list)
    # Phase 6B (ADR-0017): Workspace 运营视图 — 仅 workspace 模式聚合 (collector
    # include_workspace=True), 默认空 (与既有 dashboard 行为/成本完全一致)。
    agent_utilization: AgentUtilizationSummary = Field(default_factory=AgentUtilizationSummary)
    runtime_usage: RuntimeUsageSummary = Field(default_factory=RuntimeUsageSummary)
    # Phase 6C (ADR-0018): Git View — 仅 --view git 聚合 (collector include_git=True),
    # 默认空 (既有 dashboard 行为/成本完全一致; Git 查询经 subprocess 只读)。
    git: GitSnapshot = Field(default_factory=GitSnapshot)
    # Phase 6D (ADR-0019): Change View — 仅 --view change 聚合 (collector
    # include_change=True), 默认空 (既有 dashboard 行为/成本完全一致)。
    change: ChangeSnapshot = Field(default_factory=ChangeSnapshot)
    # Phase 6E (ADR-0020): Change Flow View — 仅 --view changeflow 聚合
    # (collector include_changeflow=True), 默认空 (既有 dashboard 行为/成本
    # 完全一致; 数据源 = ChangeTriggerRegistry + change.* 事件聚合)。
    changeflow: ChangeFlowSnapshot = Field(default_factory=ChangeFlowSnapshot)
    # Phase 7 (ADR-0021): Understanding View — 仅 --view understanding 聚合
    # (collector include_understanding=True), 默认空 (既有 dashboard 行为/成本
    # 完全一致; 数据源 = UnderstandingService 只读分析, 每项目一条)。
    understanding: UnderstandingSnapshot = Field(default_factory=UnderstandingSnapshot)

    def to_dict(self) -> dict:
        """JSON 友好序列化 (CLI --json 输出 / 测试断言共用)。"""
        return self.model_dump(mode="json")
