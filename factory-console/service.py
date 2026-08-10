"""factory-console/service.py — ConsoleService: Human Console 只读聚合服务。

设计依据:
- phase11a-status.md: Console 只读聚合各域 — workspace projects → lifecycle
  (product) → approvals (product 9c) → decisions/recommendations/experience
  (intelligence) → providers (providers)。**零写操作** (Human Layer 铁律:
  只查看/理解/审批/控制流程状态; 禁自动批准/禁修改 Decision/权重)。
- 边界 (phase10a-plan.md §Q1): Console 只读 Core/Extension 数据
  (Event/Artifact/Decision/Recommendation/Experience/Approval/Provider),
  不写任何状态 — 本服务全部方法只调用各 store 读接口
  (list/get/query/count), 无 save/update/record。
- 失败安全 (同 dashboard/metrics 哲学): 所有 store 依赖可选 (None → 空),
  缺 store/损坏文件不拖垮 Console (读命令永不因数据缺失失败)。
- 项目 → 生命周期关联 (复用 9d 既有约定, lifecycle.py:602): idea.context
  ["project"] 即项目 id (task 阶段生成 Core Task 时同款推导) — 本服务按
  该约定把 workspace 项目与 product lifecycle 关联, 不复制/不修改引擎逻辑。
- 延迟导入 Core 包 (Removal Isolation): 本模块函数内 import product/
  intelligence/providers 等 — 删除任一 Core 包不影响 Console 加载。
- 无 Database/Web API 依赖: 纯本地 JSON/SQLite 读接口 + 事件审计 (未来
  11B 经 api/ 路由函数挂 FastAPI 薄层)。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import (
    AgentSummary,
    ApprovalDecisionSummary,
    ApprovalGateSummary,
    ApprovalSummary,
    ArtifactDetail,
    ArtifactSummary,
    ConsoleDashboard,
    CostSummary,
    DecisionSummary,
    EventSummary,
    ExperienceSummary,
    ExperienceSummaryModel,
    LifecycleSummary,
    ProjectSummary,
    ProviderSummary,
    RecommendationSummary,
    RuntimeInstance,
    RuntimeScreenshot,
    StageRunSummary,
    StageSummary,
    TimelineEventSummary,
    WorkflowDetail,
    WorkflowSummary,
)

#: 默认最近决策/活动条数 (KISS: Dashboard 不无限增长, CLI --limit 可覆盖)
DEFAULT_RECENT_LIMIT = 10


class RuntimeStateError(Exception):
    """S10-004: Runtime 状态机非法流转 (start/stop/screenshot 状态不符)。

    HTTP 层映射 409 Conflict (与审批决定冲突同语义 — 终态/非法跳转拒绝)。
    """


def _utc_now_str() -> str:
    """当前 UTC 时间 ISO 字符串 (Runtime 实例/截图 created_at)。"""
    return datetime.now(timezone.utc).isoformat()

#: 规范 8 阶段链 (S9-002 Workflow View 模板; 前端渲染占位/标签映射用 —
#: Idea→PM→Product→UX/UI→Architecture→Development→Test→Release)。
WORKFLOW_TEMPLATE: tuple[str, ...] = (
    "Idea",
    "PM",
    "Product",
    "UX/UI",
    "Architecture",
    "Development",
    "Test",
    "Release",
)

#: Timeline 事件类型映射 (S10-002 — events.db org.* 事件 → Timeline 节点 type)。
#: 只聚合 org.* 运行事件 (user/stage/artifact/review/error 五类), 其余事件
#: (console.viewed 等审计事件) 不进 Timeline (KISS: Timeline 是运行视图)。
TIMELINE_TYPES: dict[str, tuple[str, str]] = {
    "org.project.created": ("user", "项目创建"),
    "org.project.registered": ("user", "项目注册"),
    "org.project.lifecycle_changed": ("user", "生命周期流转"),
    "org.workflow.created": ("stage", "工作流创建"),
    "org.workflow.started": ("stage", "工作流启动"),
    "org.workflow.stage_ready": ("stage", "阶段就绪"),
    "org.workflow.stage_started": ("stage", "阶段开始"),
    "org.workflow.stage_completed": ("stage", "阶段完成"),
    "org.workflow.completed": ("stage", "工作流完成"),
    "org.workflow.failed": ("error", "工作流失败"),
    "org.artifact.created": ("artifact", "产物生成"),
    "org.artifact.updated": ("artifact", "产物更新"),
    "org.artifact.validated": ("artifact", "产物验证通过"),
    "org.artifact.consumed": ("artifact", "产物被消费"),
    "org.artifact.archived": ("artifact", "产物归档"),
    "org.artifact.failed": ("error", "产物契约失败"),
    "org.approval.created": ("review", "审批待处理"),
    "org.approval.approved": ("review", "审批通过"),
    "org.approval.rejected": ("review", "审批驳回"),
}

#: mock fallback 阶段链 (S10-002 — 形状对齐前端 mock/workspace.ts MOCK_PROJECTS:
#: Product→UX/UI→Architecture→Code→Test→Release; 状态沿用设计 token 语义)。
MOCK_STAGE_CHAIN: tuple[tuple[str, str, str, str], ...] = (
    # (role_id, name, status, artifact_type)
    ("product-manager", "Product", "completed", "product"),
    ("ui-designer", "UX/UI", "completed", "ux_ui"),
    ("architect", "Architecture", "waiting_review", "design"),
    ("developer", "Code", "pending", "code"),
    ("tester", "Test", "pending", "test"),
    ("devops", "Release", "pending", "release"),
)


def _dt_str(value: Any) -> str | None:
    """datetime → UTC 字符串 (宽容; 已字符串/None 原样 — 投影模型时间字段)。"""
    if value is None or isinstance(value, str):
        return value
    try:
        return value.isoformat()
    except Exception:
        return str(value)


class ConsoleService:
    """Human Console 只读聚合服务 (依赖注入各 store, 全部可选)。

    构造: 传 None 的依赖在对应查询时按空数据处理 (冷启动/缺装 Console
    照常工作, 失败安全)。典型装配见 cli.commands._open_console_service。
    """

    def __init__(
        self,
        *,
        workspace_manager: Any = None,
        task_store: Any = None,
        agent_registry: Any = None,
        product_store: Any = None,
        decision_store: Any = None,
        recommendation_store: Any = None,
        experience_store: Any = None,
        usage_store: Any = None,
        provider_registry: Any = None,
        event_store: Any = None,
        project_store: Any = None,
        workflow_lifecycle: Any = None,
        # S10-004: Runtime 持久化 (Instance 模式 — browser|terminal 实例;
        # 全部可选, 失败安全: 缺 store → runtime 操作按空/不存在处理)
        runtime_store: Any = None,
        runtime_screenshot_store: Any = None,
    ) -> None:
        self._workspace = workspace_manager
        self._task_store = task_store
        self._agent_registry = agent_registry
        self._product = product_store
        self._decisions = decision_store
        self._recommendations = recommendation_store
        self._experiences = experience_store
        self._usage = usage_store
        self._providers = provider_registry
        self._events = event_store
        # S9-002: org 层 (组织级 Workflow/Stage/Artifact/ApprovalGate 聚合 —
        # 全部可选, 失败安全; 典型装配见 web/backend/fastapi_adapter.py)
        self._project_store = project_store
        self._workflow = workflow_lifecycle
        # S10-004: Runtime 层 (RuntimeInstanceStore + RuntimeScreenshotStore —
        # 独立数据空间 <root>/runtimes, 与 org 并存; 缺任一 → 对应操作失败安全)
        self._runtime_store = runtime_store
        self._runtime_screenshots = runtime_screenshot_store

    # ------------------------------------------------------------------ 七域 Dashboard

    def dashboard(self, *, recent_limit: int = DEFAULT_RECENT_LIMIT) -> ConsoleDashboard:
        """七域汇总快照 (只读聚合, 失败安全)。

        projects/approvals/agents/decisions/cost/experience/activity 七域
        一次装配; 空工厂 → 全空域, Console 永不因数据缺失失败。
        """
        return ConsoleDashboard(
            projects=self.list_projects(),
            approvals=self.list_approvals(),
            agents=self._agent_summaries(),
            decisions=self.list_recent_decisions(recent_limit),
            cost=self._cost_summary(),
            experience=self._experience_summary(),
            activity=self._recent_events(recent_limit),
        )

    # ------------------------------------------------------------------ GET /projects

    def list_projects(self) -> list[ProjectSummary]:
        """全部项目只读投影 (workspace 项目定义 + org 项目并集, 含 S9-002
        workflow/stage/progress 聚合)。

        数据源 (全部可选, 失败安全): workspace 项目定义 (id/name/language/
        repository/tech_stack) ∪ org Project (id/name/lifecycle); 同 id 合并。
        org 聚合: 当前 (最近创建) Workflow 运行 → workflow_id/status +
        当前阶段 + progress (completed stages / total stages) + stage_counts。
        """
        definitions = self._project_definitions()
        tasks = self._tasks_by_project()
        org_by_id = {p.id: p for p in self._org_projects()}
        wf_by_project = self._workflows_by_project()
        summaries: list[ProjectSummary] = []
        seen: set[str] = set()
        for definition in definitions:
            project_id = definition.id
            seen.add(project_id)
            org = org_by_id.get(project_id)
            lifecycle = self._lifecycle_for_project(project_id)
            summary = ProjectSummary(
                id=project_id,
                name=definition.name or (org.name if org else project_id),
                description=definition.description,
                language=definition.language,
                repository=definition.repository,
                tech_stack=list(definition.tech_stack or []),
                status=definition.status,
                lifecycle_stage=(
                    lifecycle["current_stage"]["name"]
                    if lifecycle and lifecycle.get("current_stage")
                    else None
                ),
                lifecycle_status=(
                    (lifecycle.get("lifecycle") or {}).get("status")
                    if lifecycle
                    else None
                ),
                pending_approvals=self._pending_approvals_for_project(project_id),
                tasks=tasks.get(project_id, {}),
                last_activity=self._project_last_activity(project_id),
            )
            self._apply_workflow_projection(summary, wf_by_project.get(project_id))
            summaries.append(summary)
        # org-only 项目 (无 workspace 定义 — 纯 org 数据空间项目)
        for project_id, org in org_by_id.items():
            if project_id in seen:
                continue
            lifecycle = self._lifecycle_for_project(project_id)
            summary = ProjectSummary(
                id=project_id,
                name=org.name or project_id,
                status=org.lifecycle.value
                if hasattr(org.lifecycle, "value")
                else str(org.lifecycle),
                lifecycle_stage=(
                    lifecycle["current_stage"]["name"]
                    if lifecycle and lifecycle.get("current_stage")
                    else None
                ),
                lifecycle_status=(
                    (lifecycle.get("lifecycle") or {}).get("status")
                    if lifecycle
                    else None
                ),
                pending_approvals=self._pending_approvals_for_project(project_id),
                tasks=tasks.get(project_id, {}),
                last_activity=self._project_last_activity(project_id),
            )
            self._apply_workflow_projection(summary, wf_by_project.get(project_id))
            summaries.append(summary)
        return summaries

    # ------------------------------------------------------------------ S9-002: Workflow/Artifact/Approval

    def list_workflows(self, project_id: str | None = None) -> list[WorkflowSummary]:
        """组织级 Workflow 运行清单 (阶段链进度聚合; 无 org → 空)。"""
        lifecycle = self._workflow_lifecycle()
        if lifecycle is None:
            return []
        try:
            workflows = lifecycle.list_workflows(project_id=project_id)
        except Exception:
            return []  # 损坏 store → 空 (失败安全)
        project_names = {
            p.id: p.name for p in self._org_projects()
        }
        workspace_names = {p.id: p.name for p in self._project_definitions()}
        out: list[WorkflowSummary] = []
        for workflow in workflows:
            stages = self._stages_of(workflow.id)
            completed = sum(1 for s in stages if s.status.value == "completed")
            total = len(stages)
            current = next(
                (s for s in stages if s.status.value != "completed"), None
            )
            out.append(
                WorkflowSummary(
                    id=workflow.id,
                    project_id=workflow.project_id,
                    project_name=(
                        workspace_names.get(workflow.project_id)
                        or project_names.get(workflow.project_id)
                        or workflow.project_id
                    ),
                    name=workflow.name,
                    status=workflow.status.value,
                    stage_count=total,
                    completed_count=completed,
                    progress=round(completed / total, 4) if total else 0.0,
                    current_stage=current.name or current.role_id if current else None,
                    current_stage_status=current.status.value if current else None,
                    failed_reason=workflow.failed_reason,
                )
            )
        return out

    def get_workflow(self, workflow_id: str) -> WorkflowDetail | None:
        """单 Workflow 8 阶段链全视图; 无 org/不存在 → None (404 语义由调用方定)。

        阶段链: 按 order 升序; 每节点 status/role/artifact (输出产物摘要)/
        pending_approval (绑定本阶段的审批门)。template = 规范 8 阶段链
        (前端占位/标签映射)。org NotFoundError → None (失败安全, 同
        project_lifecycle None 语义)。
        """
        lifecycle = self._workflow_lifecycle()
        if lifecycle is None:
            return None
        try:
            workflow = lifecycle.get_workflow(workflow_id)
        except Exception:
            return None
        project_names = {p.id: p.name for p in self._org_projects()}
        workspace_names = {p.id: p.name for p in self._project_definitions()}
        stages = self._stages_of(workflow.id)
        stage_summaries = [
            self._stage_summary(lifecycle, stage, workflow.project_id)
            for stage in stages
        ]
        gates = sorted(
            lifecycle.list_approvals(workflow_id=workflow.id),
            key=lambda g: g.requested_at,
        )
        return WorkflowDetail(
            id=workflow.id,
            project_id=workflow.project_id,
            project_name=(
                workspace_names.get(workflow.project_id)
                or project_names.get(workflow.project_id)
                or workflow.project_id
            ),
            name=workflow.name,
            status=workflow.status.value,
            failed_reason=workflow.failed_reason,
            created_at=_dt_str(workflow.created_at),
            started_at=_dt_str(workflow.started_at),
            completed_at=_dt_str(workflow.completed_at),
            stages=stage_summaries,
            pending_approvals=[self._gate_summary(g) for g in gates],
            template=list(WORKFLOW_TEMPLATE),
        )

    # ------------------------------------------------ S10-002: Runtime API
    # Adapter 层 (UI 与 CLI 共用): 只消费 org.* 查询 + events 流, 零 Core 修改。

    def project_exists(self, project_id: str) -> bool:
        """项目存在性 (org 项目 ∪ workspace 定义; 失败安全 → False)。

        Runtime 端点的 404 语义依据: 项目不存在 → 404; 项目存在但无运行
        数据 → mock fallback (is_mock=True, 前端可展示不崩溃)。
        """
        for project in self._org_projects():
            if project.id == project_id:
                return True
        for definition in self._project_definitions():
            if definition.id == project_id:
                return True
        return False

    def get_project_workflow(self, project_id: str) -> WorkflowDetail | None:
        """项目当前 (最近) Workflow 详情; 无 org/无 workflow → None。

        复用 _workflows_by_project (created_at 升序遍历, 后写覆盖 = 最新
        运行); 404 语义由调用方定; mock fallback (is_mock=True) 由 api 层
        在项目存在但无 workflow 时提供 (诚实标注, 不冒充真实)。
        """
        workflow = self._workflows_by_project().get(project_id)
        if workflow is None:
            return None
        return self.get_workflow(workflow.id)

    def get_workflow_stage_runs(
        self, workflow_id: str, *, event_logger: Any = None
    ) -> list[StageRunSummary] | None:
        """GET /workflows/{id}/stages — 阶段运行明细 (状态/agent/artifacts/
        duration/cost); 无 org/不存在 → None (404 语义由调用方定)。

        - agent_id: org 无独立 Agent 实体 — 阶段由 role_id 角色执行,
          诚实投影 agent_id = role_id (Task 面板 Agent 列)
        - duration_s: 从事件流推导 (stage_started → stage_completed 时间戳差;
          缺任一端 → None, 不臆造)
        - cost_usd: org 未跟踪成本 → None (诚实 null; 仅 mock 数据带示例值)
        - artifacts: 输出产物摘要 (output_artifacts + artifact_ref 去重)
        """
        lifecycle = self._workflow_lifecycle()
        if lifecycle is None:
            return None
        try:
            workflow = lifecycle.get_workflow(workflow_id)
        except Exception:
            return None  # 不存在/损坏 → None (失败安全)
        stages = self._stages_of(workflow.id)
        started_at, completed_at = self._stage_event_times(
            workflow.project_id, event_logger=event_logger
        )
        out: list[StageRunSummary] = []
        for stage in stages:
            artifacts: list[ArtifactSummary] = []
            artifact_ids = list(stage.output_artifacts or [])
            if stage.artifact_ref and stage.artifact_ref not in artifact_ids:
                artifact_ids.append(stage.artifact_ref)
            for artifact_id in artifact_ids:
                found = lifecycle.store.get_artifact(artifact_id)
                if found is not None:
                    artifacts.append(self._artifact_summary(found, stage.workflow_id))
            duration_s: float | None = None
            if stage.id in started_at and stage.id in completed_at:
                duration_s = round(
                    (completed_at[stage.id] - started_at[stage.id]).total_seconds(), 3
                )
            out.append(
                StageRunSummary(
                    id=stage.id,
                    workflow_id=stage.workflow_id,
                    role_id=stage.role_id,
                    name=stage.name,
                    order=stage.order,
                    status=stage.status.value,
                    agent_id=stage.role_id,
                    duration_s=duration_s,
                    cost_usd=None,  # org 未跟踪成本 — 诚实 null (mock 才带示例值)
                    started_at=_dt_str(started_at.get(stage.id)),
                    completed_at=_dt_str(completed_at.get(stage.id)),
                    depends_on=list(stage.depends_on or []),
                    input_artifacts=list(stage.input_artifacts or []),
                    output_artifacts=list(stage.output_artifacts or []),
                    artifacts=artifacts,
                )
            )
        return out

    def get_project_timeline(
        self,
        project_id: str,
        *,
        event_logger: Any = None,
        limit: int = 200,
    ) -> list[TimelineEventSummary] | None:
        """GET /projects/{id}/timeline — Timeline 事件聚合 (user/stage/
        artifact/review/error 五类节点)。

        数据源: events.db 按 project_id 过滤的 org.* 运行事件 (与 SSE
        /api/events/stream 同源同映射 — Timeline = 历史快照, SSE = 增量);
        项目不存在 → None (404 语义); 无事件 → [] (诚实空态, 前端空态展示)。
        """
        if not self.project_exists(project_id):
            return None
        store = getattr(event_logger, "store", None) if event_logger is not None else None
        if store is None:
            return []  # 无事件库 → 空 (失败安全)
        try:
            events = store.query(project_id=project_id)
        except Exception:
            return []  # 事件库损坏 → 空 (失败安全)
        mapped: list[TimelineEventSummary] = []
        for event in events:
            summary = self._timeline_summary(event)
            if summary is not None:
                mapped.append(summary)
        return mapped[-max(limit, 0):]

    # ------------------------------------------------ S10-004: Runtime Workspace
    # Instance 模式 (workspace-architecture.md §4 调整版): "+" 创建 browser|
    # terminal 实例; RuntimeInstanceStore 持久化; 状态机 starting→running→
    # stopped (error 为异常终态); screenshot 预留 (只落记录, 不实现完整 Loop)。

    #: 沙箱预览 URL 模板 (S10-004 预留: 沙箱静态服务器由后续 Sprint 实现;
    #: URL 为设计占位, 前端 iframe 按此加载, 不可达时显示"沙箱未就绪")。
    RUNTIME_PREVIEW_URL = "http://127.0.0.1:8099/preview/{project_id}"

    def _get_runtime_store(self) -> Any:
        """RuntimeInstanceStore (缺失 → None; 失败安全 — 调用方按空处理)。

        注意: 方法名避开实例属性 `self._runtime_store` (同名遮蔽陷阱 —
        属性会覆盖方法, 导致 store 注入后 `self._get_runtime_store()` 不可调用)。
        """
        return self._runtime_store

    def _get_runtime_screenshot_store(self) -> Any:
        """RuntimeScreenshotStore (缺失 → None; 失败安全)。"""
        return self._runtime_screenshots

    def create_runtime(
        self,
        project_id: str,
        runtime_type: str,
        artifact_id: str | None = None,
    ) -> RuntimeInstance | None:
        """POST /projects/{id}/runtimes — 创建 Runtime Instance (starting)。

        项目不存在 → None (404); runtime store 缺失 → None (失败安全 —
        Console 冷启动照常工作); 非法 type (非 browser|terminal) → ValueError
        (HTTP 层 400); 创建后 status=starting (生命周期起点, start 后 running)。
        """
        if not self.project_exists(project_id):
            return None
        store = self._get_runtime_store()
        if store is None:
            return None
        from .runtime_store import new_runtime_id

        instance = RuntimeInstance(
            id=new_runtime_id(),
            project_id=project_id,
            type=runtime_type,  # type: ignore[arg-type]  # Literal 校验在 pydantic
            status="starting",
            artifact_id=artifact_id,
            url=None,
            session=None,
            created_at=_utc_now_str(),
        )
        store.save(instance)
        return instance

    def list_runtimes(self, project_id: str) -> list[RuntimeInstance] | None:
        """GET /projects/{id}/runtimes — 项目实例列表 (id 排序)。

        项目不存在 → None (404); store 缺失 → [] (失败安全); 无实例 → []
        (诚实空态 — 前端显示"还没有 Runtime, 点击 + 创建")。
        """
        if not self.project_exists(project_id):
            return None
        store = self._get_runtime_store()
        if store is None:
            return []
        return store.list_by_project(project_id)

    def get_runtime(self, runtime_id: str) -> RuntimeInstance | None:
        """GET /runtimes/{id} — 实例详情; 不存在 → None (404)。"""
        store = self._get_runtime_store()
        if store is None:
            return None
        return store.get(runtime_id)

    def start_runtime(self, runtime_id: str) -> RuntimeInstance | None:
        """POST /runtimes/{id}/start — starting|stopped → running (重启允许)。

        不存在 → None (404); 状态机非法流转 (running/error → start) →
        RuntimeStateError (HTTP 层 409); start 时生成连接信息: browser →
        url (沙箱预览 URL 模板), terminal → session (tty 会话标识)。
        """
        instance = self.get_runtime(runtime_id)
        if instance is None:
            return None
        if instance.status not in ("starting", "stopped"):
            raise RuntimeStateError(
                f"runtime {runtime_id} cannot start from status {instance.status!r}"
            )
        updated = instance.model_copy(
            update={
                "status": "running",
                **self._runtime_endpoint(instance, runtime_id),
            }
        )
        self._get_runtime_store().save(updated)
        return updated

    def stop_runtime(self, runtime_id: str) -> RuntimeInstance | None:
        """POST /runtimes/{id}/stop — starting|running → stopped。

        不存在 → None (404); 已 stopped/error → RuntimeStateError (409,
        终态不可重复停止); 停止保留 url/session (历史连接信息可复查)。
        """
        instance = self.get_runtime(runtime_id)
        if instance is None:
            return None
        if instance.status not in ("starting", "running"):
            raise RuntimeStateError(
                f"runtime {runtime_id} cannot stop from status {instance.status!r}"
            )
        updated = instance.model_copy(update={"status": "stopped"})
        self._get_runtime_store().save(updated)
        return updated

    def capture_runtime_screenshot(self, runtime_id: str) -> RuntimeScreenshot | None:
        """POST /runtimes/{id}/screenshot — 截图预留 (只落记录 + artifact 引用)。

        不存在 → None (404); 非 running 实例 → RuntimeStateError (409 —
        截图只在运行态有意义); 返回截图记录 (artifact_id 预留 — 完整
        Feedback Loop 由后续 Sprint 实现, 本 Sprint 只保存)。
        """
        instance = self.get_runtime(runtime_id)
        if instance is None:
            return None
        if instance.status != "running":
            raise RuntimeStateError(
                f"runtime {runtime_id} screenshot requires running status "
                f"(got {instance.status!r})"
            )
        store = self._get_runtime_screenshot_store()
        if store is None:
            return None
        from .runtime_store import new_screenshot_id

        screenshot = RuntimeScreenshot(
            id=new_screenshot_id(),
            instance_id=runtime_id,
            project_id=instance.project_id,
            artifact_id=f"shot-{runtime_id}",  # 预留产物引用 (后续渲染环节)
            created_at=_utc_now_str(),
        )
        store.save(screenshot)
        return screenshot

    def _runtime_endpoint(self, instance: RuntimeInstance, runtime_id: str) -> dict[str, str | None]:
        """start 时按类型生成连接信息: browser → url / terminal → session。

        url 为沙箱预览 URL 模板 (RUNTIME_PREVIEW_URL — 静态服务器后续实现);
        session 为 tty 会话标识 (mock 会话 — 真实 PTY 由后续 Sprint 接入)。
        """
        if instance.type == "browser":
            return {"url": self.RUNTIME_PREVIEW_URL.format(project_id=instance.project_id), "session": None}
        return {"session": f"tty://{instance.project_id}/{runtime_id}", "url": None}

    def build_mock_workflow(self, project_id: str) -> WorkflowDetail:
        """mock fallback (S10-002): 项目存在但无运行数据 → is_mock=True 详情。

        形状对齐前端 mock/workspace.ts MOCK_PROJECTS (Product→UX/UI→
        Architecture→Code→Test→Release, Architecture 待审核); 示例
        duration/cost 仅 mock 数据携带 — 真实数据 cost 恒 None (诚实边界:
        mock 明确标注 is_mock, 前端据此显示演示标识)。
        """
        org_names = {p.id: p.name for p in self._org_projects()}
        workspace_names = {p.id: p.name for p in self._project_definitions()}
        name = org_names.get(project_id) or workspace_names.get(project_id) or project_id
        now_iso = _dt_str(datetime.now(timezone.utc))
        stages: list[StageSummary] = []
        for order, (role_id, label, status, artifact_type) in enumerate(
            MOCK_STAGE_CHAIN, start=1
        ):
            artifact = None
            if status == "completed":
                artifact = ArtifactSummary(
                    id=f"mock-art-{role_id}",
                    stage_id=f"mock-{role_id}",
                    workflow_id=f"mock-wf-{project_id}",
                    project_id=project_id,
                    type=artifact_type,
                    ref=f"mock://{artifact_type}",
                    status="validated",
                    producer_role=role_id,
                    created_at=now_iso,
                    updated_at=now_iso,
                )
            stages.append(
                StageSummary(
                    id=f"mock-{role_id}",
                    workflow_id=f"mock-wf-{project_id}",
                    role_id=role_id,
                    name=label,
                    order=order,
                    status=status,
                    depends_on=[
                        prev for prev, *_ in MOCK_STAGE_CHAIN[: order - 1]
                    ],
                    artifact=artifact,
                    approval_required=(status == "waiting_review"),
                )
            )
        return WorkflowDetail(
            id=f"mock-wf-{project_id}",
            project_id=project_id,
            project_name=name,
            name="Mock Workflow (演示数据)",
            status="active",
            created_at=now_iso,
            started_at=now_iso,
            stages=stages,
            pending_approvals=[
                ApprovalGateSummary(
                    id="mock-gate-arch",
                    stage_id="mock-architect",
                    workflow_id=f"mock-wf-{project_id}",
                    project_id=project_id,
                    status="pending",
                    requested_at=now_iso,
                )
            ],
            template=list(WORKFLOW_TEMPLATE),
            is_mock=True,
        )

    def _stage_event_times(
        self,
        project_id: str,
        *,
        event_logger: Any = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """从事件流推导阶段 started/completed 时间戳 (S10-002 duration 数据源)。

        查询 org.workflow.stage_started / stage_completed 事件 (project_id
        维度), 按 payload.stage_id 归组: started 取首个 (setdefault — 重试
        场景保留首次开始), completed 取最近 (后写覆盖); 无事件库/损坏 →
        空映射 (duration=None, 诚实不臆造)。
        """
        store = getattr(event_logger, "store", None) if event_logger is not None else None
        started_at: dict[str, Any] = {}
        completed_at: dict[str, Any] = {}
        if store is None:
            return started_at, completed_at
        try:
            from events.models import EventType

            started_events = store.query(
                project_id=project_id, event_type=EventType.ORG_WORKFLOW_STAGE_STARTED
            )
            completed_events = store.query(
                project_id=project_id, event_type=EventType.ORG_WORKFLOW_STAGE_COMPLETED
            )
        except Exception:
            return started_at, completed_at  # 事件库损坏 → 空 (失败安全)
        for event in started_events:
            stage_id = (event.payload or {}).get("stage_id")
            if stage_id:
                started_at.setdefault(stage_id, event.timestamp)
        for event in completed_events:
            stage_id = (event.payload or {}).get("stage_id")
            if stage_id:
                completed_at[stage_id] = event.timestamp
        return started_at, completed_at

    def _timeline_summary(self, event: Any) -> TimelineEventSummary | None:
        """Event → TimelineEventSummary (TIMELINE_TYPES 映射; 未知类型 → None)。

        五类节点: user (项目创建/注册) / stage (workflow 流转) / artifact
        (产物生命周期) / review (审批门) / error (失败)。审计事件
        (console.viewed 等) 不在映射 → None (不进 Timeline, 运行视图纯净)。
        """
        event_type = (
            event.type.value if hasattr(event.type, "value") else str(event.type)
        )
        mapping = TIMELINE_TYPES.get(event_type)
        if mapping is None:
            return None
        timeline_type, verb = mapping
        payload = dict(event.payload or {})
        name = payload.get("name") or ""
        detail = f" {name}" if name else ""
        if timeline_type == "error" and payload.get("reason"):
            detail = f": {payload['reason']}"  # 失败原因入 message (可读摘要)
        return TimelineEventSummary(
            id=f"evt-{event.seq}",
            seq=event.seq,
            project_id=event.project_id or "",
            type=timeline_type,
            event_type=event_type,
            stage_id=payload.get("stage_id"),
            agent_id=payload.get("role_id") or event.agent_id,
            artifact_id=payload.get("artifact_id"),
            gate_id=payload.get("gate_id"),
            message=f"{verb}{detail}",
            status=event.result or event.stage,
            payload=payload,
            created_at=_dt_str(event.timestamp),
        )

    def list_artifacts(
        self,
        *,
        project_id: str | None = None,
        workflow_id: str | None = None,
        type: str | None = None,
    ) -> list[ArtifactSummary]:
        """org Artifact 清单 (按 project/workflow/type 过滤; 无 org → 空)。

        workflow 过滤经 stage 反查 (Artifact 模型无 workflow 字段 — stage
        冗余 scoping): 仅保留 stage 属于该 workflow 的产物; 无 stage 的
        产物 (project_id 直挂) 在无 workflow 过滤时保留。
        """
        lifecycle = self._workflow_lifecycle()
        if lifecycle is None:
            return []
        store = lifecycle.store
        try:
            artifacts = store.list_artifacts()
            stages = store.list_stages()
        except Exception:
            return []  # 损坏 store → 空 (失败安全)
        wf_by_stage = {s.id: s.workflow_id for s in stages}
        out: list[ArtifactSummary] = []
        for artifact in artifacts:
            if project_id is not None and artifact.project_id != project_id:
                continue
            if type is not None:
                artifact_type = (
                    artifact.type.value
                    if hasattr(artifact.type, "value")
                    else str(artifact.type)
                )
                if artifact_type != type:
                    continue
            stage_wf = wf_by_stage.get(artifact.stage_id)
            if workflow_id is not None and stage_wf != workflow_id:
                continue
            out.append(self._artifact_summary(artifact, stage_wf or ""))
        return out

    def get_artifact(self, artifact_id: str) -> "ArtifactDetail | None":
        """单 Artifact 详情 (S9-003: metadata 契约载荷 + review 审批门)。

        返回 ArtifactDetail (含 metadata 原始载荷 + 绑定本产物的审批门 —
        按 stage_id 关联的 gate, 即需求/设计确认门: status/comment/reviewer
        决定状态); 无 org / 产物不存在 / store 损坏 → None (404 语义由
        调用方定, 失败安全同其余查询)。
        """
        lifecycle = self._workflow_lifecycle()
        if lifecycle is None:
            return None
        store = lifecycle.store
        try:
            artifact = store.get_artifact(artifact_id)
        except Exception:
            return None  # 损坏 store → None (失败安全)
        if artifact is None:
            return None
        try:
            stages = {s.id: s for s in store.list_stages()}
        except Exception:
            stages = {}
        stage = stages.get(artifact.stage_id)
        workflow_id = stage.workflow_id if stage else ""
        summary = self._artifact_summary(artifact, workflow_id)
        gate = None
        try:
            gate = lifecycle.get_approval_by_stage(artifact.stage_id)
        except Exception:
            gate = None  # 门 store 损坏 → review=None (只读视图不拖垮详情)
        return ArtifactDetail(
            **summary.to_dict(),
            metadata=dict(artifact.metadata or {}),
            review=self._gate_summary(gate, artifact.project_id) if gate else None,
        )

    def list_approval_gates(
        self,
        *,
        status: str | None = None,
        workflow_id: str | None = None,
    ) -> list[ApprovalGateSummary]:
        """org 审批门清单 (S9-002 — Console 审批中心的决定操作对象)。

        与 11A list_approvals (product 9c 请求, 只读遗留视图) 区分: 本方法
        返回 org ApprovalGate (S9-001), id 即 POST /approvals/{id}/approve|
        reject 的操作对象。project_id 经 gate → stage → workflow 反查
        (org ApprovalGate 模型无 project_id 字段 — stage/workflow 冗余
        scoping)。无 org → 空 (失败安全)。
        """
        lifecycle = self._workflow_lifecycle()
        if lifecycle is None:
            return []
        try:
            gates = lifecycle.list_approvals(
                workflow_id=workflow_id, status=status
            )
            stages = {s.id: s for s in lifecycle.store.list_stages()}
            workflows = {w.id: w for w in lifecycle.list_workflows()}
        except Exception:
            return []  # 损坏 store → 空 (失败安全)
        out: list[ApprovalGateSummary] = []
        for gate in gates:
            workflow = workflows.get(gate.workflow_id)
            project_id = workflow.project_id if workflow else ""
            out.append(self._gate_summary(gate, project_id))
        return out

    def approve_approval(
        self,
        gate_id: str,
        *,
        reviewer: str = "",
        comment: str = "",
    ) -> ApprovalDecisionSummary | None:
        """审批放行 (POST /approvals/{id}/approve; 接 org.approval S9-001)。

        委托 WorkflowLifecycle.approve_approval (source=\"console\" — 审计
        区分决策入口); 无 org → None (调用方 404 语义); 门不存在 → 抛
        org NotFoundError; 非 PENDING 门 → 抛 org ApprovalStateError
        (终态决定不可撤销 — 由 HTTP 层映射 409)。
        """
        lifecycle = self._workflow_lifecycle()
        if lifecycle is None:
            return None
        gate, workflow = lifecycle.approve_approval(
            gate_id, reviewer=reviewer, comment=comment, source="console"
        )
        return self._approval_decision_summary("approve", gate, workflow)

    def reject_approval(
        self,
        gate_id: str,
        *,
        reviewer: str = "",
        comment: str = "",
    ) -> ApprovalDecisionSummary | None:
        """审批否决 (POST /approvals/{id}/reject; 接 org.approval S9-001)。

        委托 WorkflowLifecycle.reject_approval (source=\"console\"); 错误
        语义同 approve_approval (NotFound → 抛 org NotFoundError;
        非 PENDING → org ApprovalStateError)。
        """
        lifecycle = self._workflow_lifecycle()
        if lifecycle is None:
            return None
        gate, workflow = lifecycle.reject_approval(
            gate_id, reviewer=reviewer, comment=comment, source="console"
        )
        return self._approval_decision_summary("reject", gate, workflow)

    # ------------------------------------------------------ S9-002 内部: org 装配/投影

    def _workflow_lifecycle(self) -> Any:
        """org WorkflowLifecycle (注入优先; 否则按 project_store 懒构建)。

        logger=None 懒构建路径 (仅测试/无注入场景) → 决定事件静默; 生产
        装配 (fastapi_adapter) 注入带 EventLogger 的生命周期 — org.approval.*
        事件 source=\"console\" 落库审计。失败安全: org 缺失/损坏 → None。
        """
        if self._workflow is not None:
            return self._workflow
        if self._project_store is None:
            return None
        self._mount_org()
        try:
            from org.workflow import WorkflowLifecycle

            return WorkflowLifecycle(self._project_store, logger=None)
        except Exception:
            return None

    @staticmethod
    def _mount_org() -> None:
        """挂载 factory-org 包目录到 sys.path (幂等; 缺目录 → 跳过)。

        org 包名不含连字符但位于 factory-org/ 子目录 — 延迟导入需该目录
        在 sys.path (Removal Isolation: 删除 factory-org 不影响 Console)。
        """
        import sys
        from pathlib import Path

        org_dir = Path(__file__).resolve().parents[1] / "factory-org"
        if org_dir.is_dir() and str(org_dir) not in sys.path:
            sys.path.insert(0, str(org_dir))

    def _org_projects(self) -> list[Any]:
        """org Project 清单 (无 org store → 空, 失败安全)。"""
        store = self._project_store
        if store is None:
            return []
        try:
            return store.list_projects()
        except Exception:
            return []

    def _stages_of(self, workflow_id: str) -> list[Any]:
        """workflow 阶段链 (按 order 升序; 失败安全 → 空)。"""
        lifecycle = self._workflow_lifecycle()
        if lifecycle is None:
            return []
        try:
            return sorted(
                lifecycle.store.list_stages_by_workflow(workflow_id),
                key=lambda s: s.order,
            )
        except Exception:
            return []

    def _workflows_by_project(self) -> dict[str, Any]:
        """项目 → 最近 Workflow (按 created_at 升序遍历, 后写覆盖 = 最新)。"""
        lifecycle = self._workflow_lifecycle()
        if lifecycle is None:
            return {}
        try:
            workflows = lifecycle.list_workflows()
        except Exception:
            return {}
        out: dict[str, Any] = {}
        for workflow in sorted(workflows, key=lambda w: w.created_at):
            out[workflow.project_id] = workflow
        return out

    def _apply_workflow_projection(
        self, summary: ProjectSummary, workflow: Any | None
    ) -> None:
        """workflow → ProjectSummary 聚合字段 (无 workflow → 零修改)。"""
        if workflow is None:
            return
        stages = self._stages_of(workflow.id)
        statuses = [s.status.value for s in stages]
        completed = sum(1 for st in statuses if st == "completed")
        total = len(statuses)
        counts: dict[str, int] = {}
        for st in statuses:
            counts[st] = counts.get(st, 0) + 1
        current = next((s for s in stages if s.status.value != "completed"), None)
        summary.workflow_id = workflow.id
        summary.workflow_name = workflow.name
        summary.workflow_status = workflow.status.value
        summary.current_stage = current.name or current.role_id if current else None
        summary.current_stage_status = current.status.value if current else None
        summary.progress = round(completed / total, 4) if total else 0.0
        summary.stage_counts = counts

    def _stage_summary(
        self, lifecycle: Any, stage: Any, project_id: str = ""
    ) -> StageSummary:
        """Stage → StageSummary (含输出产物摘要 + 绑定审批门)。"""
        artifact = None
        artifact_ids = list(stage.output_artifacts or [])
        if stage.artifact_ref and stage.artifact_ref not in artifact_ids:
            artifact_ids.append(stage.artifact_ref)
        for artifact_id in reversed(artifact_ids):
            found = lifecycle.store.get_artifact(artifact_id)
            if found is not None:
                artifact = self._artifact_summary(found, stage.workflow_id)
                break
        gate = lifecycle.get_approval_by_stage(stage.id)
        return StageSummary(
            id=stage.id,
            workflow_id=stage.workflow_id,
            role_id=stage.role_id,
            name=stage.name,
            order=stage.order,
            status=stage.status.value,
            depends_on=list(stage.depends_on or []),
            input_artifacts=list(stage.input_artifacts or []),
            output_artifacts=list(stage.output_artifacts or []),
            approval_required=stage.approval_required,
            artifact=artifact,
            pending_approval=(
                self._gate_summary(gate, project_id) if gate else None
            ),
        )

    def _artifact_summary(self, artifact: Any, workflow_id: str) -> ArtifactSummary:
        """org Artifact → ArtifactSummary (workflow_id 经 stage 反查传入)。"""
        return ArtifactSummary(
            id=artifact.id,
            stage_id=artifact.stage_id,
            workflow_id=workflow_id,
            project_id=artifact.project_id,
            type=artifact.type.value
            if hasattr(artifact.type, "value")
            else str(artifact.type),
            ref=artifact.ref,
            version=artifact.version,
            status=artifact.status.value
            if hasattr(artifact.status, "value")
            else str(artifact.status),
            producer_role=artifact.producer_role,
            producer_agent=artifact.producer_agent,
            location=artifact.location,
            created_at=_dt_str(artifact.created_at),
            updated_at=_dt_str(artifact.updated_at),
        )

    @staticmethod
    def _gate_summary(gate: Any, project_id: str = "") -> ApprovalGateSummary:
        """org ApprovalGate → ApprovalGateSummary (时间 ISO 投影)。

        org ApprovalGate 模型无 project_id 字段 (stage/workflow 冗余 scoping)
        — 由调用方 (workflow 上下文) 传入, 前端项目维度定位用。
        """
        return ApprovalGateSummary(
            id=gate.id,
            stage_id=gate.stage_id,
            workflow_id=gate.workflow_id,
            project_id=project_id,
            status=gate.status.value,
            reviewer=gate.reviewer,
            comment=gate.comment,
            requested_at=_dt_str(gate.requested_at),
            approved_at=_dt_str(gate.approved_at),
            rejected_at=_dt_str(gate.rejected_at),
        )

    @staticmethod
    def _approval_decision_summary(
        action: str, gate: Any, workflow: Any
    ) -> ApprovalDecisionSummary:
        """(gate, workflow) → ApprovalDecisionSummary (决定结果投影)。"""
        return ApprovalDecisionSummary(
            action=action,
            gate=ConsoleService._gate_summary(gate, workflow.project_id),
            workflow_id=workflow.id,
            workflow_status=workflow.status.value,
        )

    def project_lifecycle(self, project_id: str) -> LifecycleSummary | None:
        """单项目生命周期只读快照; 无生命周期/无项目 → None (404 语义由调用方定)。

        经 idea.context["project"] == project_id 关联 (9d 既有约定); 阶段
        完成清单按 stages 链过滤; next_actions 投影引擎建议 (只读, 不执行)。
        """
        lifecycle = self._lifecycle_for_project(project_id)
        if lifecycle is None:
            return None
        raw = lifecycle["lifecycle"]
        stages = raw.get("stages") or []
        completed = [s["name"] for s in stages if s.get("status") == "completed"]
        return LifecycleSummary(
            project_id=project_id,
            lifecycle_id=raw.get("id"),
            idea_id=raw.get("idea_id"),
            template_name=raw.get("template_name", ""),
            status=raw.get("status", ""),
            current_stage=lifecycle.get("current_stage"),
            completed_stages=completed,
            pending_approval=lifecycle.get("pending_approval"),
            next_actions=lifecycle.get("next_actions") or [],
        )

    # ------------------------------------------------------------------ GET /approvals

    def list_approvals(self) -> list[ApprovalSummary]:
        """全部审批请求只读投影 (9c 状态机, Console 只读不决定)。

        evidence 投影: 审批绑定 Artifact 的决策链证据 (evidence 字段引用
        lineage 字符串, 无 → 空列表); risk 投影: Artifact confidence < 0.5
        时标 medium (低置信度需人工确认信号, 同 9c 审核优先级语义)。
        """
        store = self._product
        if store is None:
            return []
        try:
            requests = store.list_requests()
        except Exception:
            return []  # 损坏 store → 空 (失败安全, 同其余域)
        summaries: list[ApprovalSummary] = []
        for request in requests:
            artifact = store.get_artifact(request.artifact_id) if request.artifact_id else None
            summaries.append(
                ApprovalSummary(
                    id=request.id,
                    artifact_id=request.artifact_id,
                    artifact_type=artifact.type if artifact else "",
                    gate=request.gate,
                    status=request.status,
                    confidence=artifact.confidence if artifact else 0.0,
                    risk="medium" if artifact is not None and artifact.confidence < 0.5 else None,
                    evidence=self._artifact_evidence(artifact),
                    idea_id=request.idea_id,
                    by=request.by,
                    comment=request.comment,
                    requested_at=request.requested_at,
                    artifact_version=request.artifact_version,
                )
            )
        return summaries

    # ------------------------------------------------------------------ GET /decisions/{id}

    def get_decision(self, decision_id: str) -> DecisionSummary | None:
        """单决策只读投影 (AI 推荐产物全链可追溯); 不存在 → None。

        options 投影为引擎产物快照 (id/name/score/factors/reasoning);
        recommendation 评分取推荐选项的 score (无推荐 → 0.0); evidence 投影
        lineage_ref (source_type:source_id, 可审计锚点)。
        """
        store = self._decisions
        if store is None:
            return None
        try:
            decision = store.get(decision_id)
        except Exception:
            return None  # 损坏 store → None (失败安全)
        if decision is None:
            return None
        options = [dict(o) for o in decision.options]
        recommended = next(
            (o for o in decision.options if o["id"] == decision.recommendation), None
        )
        return DecisionSummary(
            id=decision.id,
            decision_type=decision.decision_type,
            subject_id=decision.subject_id,
            description=decision.description,
            status=decision.status.value
            if hasattr(decision.status, "value")
            else str(decision.status),
            options=options,
            recommendation=decision.recommendation,
            score=float(recommended.get("score", 0.0)) if recommended else 0.0,
            confidence=decision.confidence,
            reasoning=self._decision_reasoning(options, decision.recommendation),
            evidence=[e.lineage_ref() for e in decision.evidence],
            risk=decision.risk,
            risk_level=decision.risk_level,
            requires_approval=decision.requires_approval,
            approval_request_id=decision.approval_request_id,
            created_at=decision.created_at,
        )

    def list_recent_decisions(self, limit: int = DEFAULT_RECENT_LIMIT) -> list[DecisionSummary]:
        """最近决策投影 (按 created_at 倒序截断; 无 store → 空)。"""
        store = self._decisions
        if store is None:
            return []
        try:
            decisions = sorted(store.list_all(), key=lambda d: d.created_at, reverse=True)
        except Exception:
            return []  # 损坏 store → 空 (失败安全)
        return [self._decision_summary(d) for d in decisions[: max(limit, 0)]]

    # ------------------------------------------------------------------ GET /recommendations

    def list_recommendations(self, limit: int = DEFAULT_RECENT_LIMIT) -> list[RecommendationSummary]:
        """推荐产物只读投影 (只推荐不执行; 按 created_at 倒序截断)。"""
        store = self._recommendations
        if store is None:
            return []
        recommendations = sorted(store.list_all(), key=lambda r: r.created_at, reverse=True)
        out: list[RecommendationSummary] = []
        for rec in recommendations[: max(limit, 0)]:
            candidate = (
                f"{rec.target_type}:{rec.target_id}"
                if rec.target_type and rec.target_id
                else rec.target_id
            )
            out.append(
                RecommendationSummary(
                    id=rec.id,
                    target_type=rec.target_type,
                    candidate=candidate,
                    score=rec.score,
                    factors=self._recommendation_factors(rec),
                    explanation=list(rec.reasoning),
                    evidence=[e.lineage_ref() for e in rec.evidence],
                    confidence=rec.confidence,
                    risk=rec.risk,
                    created_at=rec.created_at,
                )
            )
        return out

    # ------------------------------------------------------------------ GET /experience

    def list_experience(self, limit: int = DEFAULT_RECENT_LIMIT) -> list[ExperienceSummary]:
        """经验记录只读投影 (六域; 按 created_at 倒序截断)。

        subject = f"{subject_type}:{subject_id}" (统一经验模型定位键);
        freshness = 当前新鲜度 (0-1, 历史经验不永久有效)。
        """
        store = self._experiences
        if store is None:
            return []
        records = sorted(store.list_all(), key=lambda r: r.created_at, reverse=True)
        out: list[ExperienceSummary] = []
        for record in records[: max(limit, 0)]:
            subject_type = record.subject_type or record.domain.value
            out.append(
                ExperienceSummary(
                    id=record.id,
                    domain=record.domain.value,
                    subject=f"{subject_type}:{record.subject_id}",
                    result=record.result.value,
                    score=record.score,
                    confidence=record.confidence,
                    freshness=record.freshness,
                    task_type=record.task_type,
                    capability=list(record.capability),
                    created_at=record.created_at,
                )
            )
        return out

    # ------------------------------------------------------------------ GET /providers

    def list_providers(self) -> list[ProviderSummary]:
        """Provider 目录只读投影 (能力/成本/性能/经验聚合)。

        cost/performance/experience: 从 usage 统计 + experience 记录聚合
        (无数据 → None, 冷启动不臆造 — 与推荐引擎中性分语义一致)。
        """
        registry = self._providers
        if registry is None:
            return []
        usage_by_provider = self._usage_by_provider()
        experience_by_subject = self._experience_by_subject()
        out: list[ProviderSummary] = []
        for definition in registry.list():
            usage = usage_by_provider.get(definition.id)
            records = experience_by_subject.get(definition.id, [])
            out.append(
                ProviderSummary(
                    id=definition.id,
                    name=definition.name,
                    type=definition.type,
                    status=definition.status.value
                    if hasattr(definition.status, "value")
                    else str(definition.status),
                    capabilities=list(definition.capabilities),
                    models=list(definition.models),
                    version=definition.version,
                    cost=self._provider_cost_score(usage, records),
                    performance=self._provider_performance_score(usage),
                    experience=self._provider_experience_score(records),
                    usage_calls=usage.get("calls", 0) if usage else 0,
                )
            )
        return out

    # ------------------------------------------------------------------ 内部: 项目域

    def _project_definitions(self) -> list[Any]:
        """workspace 项目定义 (无 workspace → 空, 失败安全)。"""
        manager = self._workspace
        if manager is None:
            return []
        try:
            return manager.list_projects()
        except Exception:
            return []  # workspace 缺失/损坏 → 空 (Console 永不失败)

    def _lifecycle_for_project(self, project_id: str) -> dict[str, Any] | None:
        """项目关联生命周期快照 (idea.context["project"] == project_id)。

        复用 9d engine.status 形状 (lifecycle/current_stage/pending_approval/
        artifacts/decisions/next_actions); 无 idea/无生命周期 → None。
        """
        store = self._product
        if store is None:
            return None
        try:
            idea_ids = [
                idea.id
                for idea in store.list_ideas()
                if isinstance(idea.context, dict) and idea.context.get("project") == project_id
            ]
        except Exception:
            return None
        if not idea_ids:
            return None
        try:
            from product.lifecycle import ProductLifecycleEngine
            from product.service import ProductService

            engine = ProductLifecycleEngine(store, ProductService(store))
            for idea_id in idea_ids:
                if store.get_lifecycle_by_idea(idea_id) is None:
                    continue
                return engine.status(idea_id)
        except Exception:
            return None
        return None

    def _pending_approvals_for_project(self, project_id: str) -> int:
        """项目维度待审批数 (pending 请求 ∩ 项目 idea 关联)。"""
        store = self._product
        if store is None:
            return 0
        try:
            project_idea_ids = {
                idea.id
                for idea in store.list_ideas()
                if isinstance(idea.context, dict) and idea.context.get("project") == project_id
            }
            return sum(
                1
                for request in store.list_pending_requests()
                if request.idea_id in project_idea_ids
            )
        except Exception:
            return 0

    def _tasks_by_project(self) -> dict[str, dict[str, int]]:
        """任务状态计数 (project → {BACKLOG: n, ...}); 无 task_store → {}。"""
        store = self._task_store
        if store is None:
            return {}
        try:
            out: dict[str, dict[str, int]] = {}
            for task in store.list():
                bucket = out.setdefault(task.project, {})
                status = task.status.value if hasattr(task.status, "value") else str(task.status)
                bucket[status] = bucket.get(status, 0) + 1
            return out
        except Exception:
            return {}

    def _project_last_activity(self, project_id: str) -> str | None:
        """项目维度最近事件时间 (无事件 → None)。"""
        store = self._events
        if store is None:
            return None
        try:
            events = store.query(project_id=project_id, limit=1)
            if not events:
                return None
            from events.models import format_timestamp

            return format_timestamp(events[-1].timestamp)
        except Exception:
            return None

    # ------------------------------------------------------------------ 内部: 审批/证据域

    def _artifact_evidence(self, artifact: Any) -> list[str]:
        """Artifact 证据引用投影 (content.evidence 或 source_events 摘要)。"""
        if artifact is None:
            return []
        evidence: list[str] = []
        content = artifact.content or {}
        if isinstance(content, dict) and isinstance(content.get("evidence"), list):
            evidence.extend(str(e) for e in content["evidence"])
        for event_id in getattr(artifact, "source_events", None) or []:
            evidence.append(f"event:{event_id}")
        return evidence

    # ------------------------------------------------------------------ 内部: 决策域

    def _decision_summary(self, decision: Any) -> DecisionSummary:
        """单决策 → 投影 (get_decision 与 list_recent_decisions 共用)。"""
        options = [dict(o) for o in decision.options]
        recommended = next(
            (o for o in decision.options if o["id"] == decision.recommendation), None
        )
        return DecisionSummary(
            id=decision.id,
            decision_type=decision.decision_type,
            subject_id=decision.subject_id,
            description=decision.description,
            status=decision.status.value
            if hasattr(decision.status, "value")
            else str(decision.status),
            options=options,
            recommendation=decision.recommendation,
            score=float(recommended.get("score", 0.0)) if recommended else 0.0,
            confidence=decision.confidence,
            reasoning=self._decision_reasoning(options, decision.recommendation),
            evidence=[e.lineage_ref() for e in decision.evidence],
            risk=decision.risk,
            risk_level=decision.risk_level,
            requires_approval=decision.requires_approval,
            approval_request_id=decision.approval_request_id,
            created_at=decision.created_at,
        )

    @staticmethod
    def _decision_reasoning(options: list[dict[str, Any]], recommendation: str | None) -> list[str]:
        """推荐解释投影: 推荐选项的 reasoning 逐条复制 (无推荐 → 空)。"""
        for option in options:
            if option.get("id") == recommendation:
                reasoning = option.get("reasoning")
                if isinstance(reasoning, list):
                    return [str(r) for r in reasoning]
                return []
        return []

    def _recommendation_factors(self, rec: Any) -> dict[str, float]:
        """推荐分项投影 (factors dict 宽容解析)。

        factors 数据源宽容读取 rec.factors / rec.basis (模型变体自适应;
        当前 Recommendation 模型无分项字段 → 空 dict, 不臆造)。
        """
        raw = getattr(rec, "factors", None) or getattr(rec, "basis", None) or {}
        if isinstance(raw, dict):
            return {
                str(k): float(v) for k, v in raw.items() if isinstance(v, (int, float))
            }
        return {}

    # ------------------------------------------------------------------ 内部: 成本/经验/Provider 域

    def _cost_summary(self) -> CostSummary:
        """成本汇总 (usage 估算计量; 无 usage_store → 空汇总)。"""
        store = self._usage
        if store is None:
            return CostSummary()
        try:
            records = store.list()
        except Exception:
            return CostSummary()
        total_cost = sum(r.estimated_cost for r in records)
        calls = len(records)
        success = sum(1 for r in records if r.success)
        by_provider: dict[str, dict[str, Any]] = {}
        for record in records:
            bucket = by_provider.setdefault(
                record.provider_id,
                {"calls": 0, "total_cost": 0.0, "success_rate": 0.0, "success": 0},
            )
            bucket["calls"] += 1
            bucket["total_cost"] = round(bucket["total_cost"] + record.estimated_cost, 6)
            if record.success:
                bucket["success"] += 1
        for bucket in by_provider.values():
            bucket["success_rate"] = (
                round(bucket["success"] / bucket["calls"], 4) if bucket["calls"] else 0.0
            )
            bucket.pop("success", None)
        return CostSummary(
            total_cost=round(total_cost, 6),
            calls=calls,
            success_rate=round(success / calls, 4) if calls else 0.0,
            avg_cost=round(total_cost / calls, 6) if calls else 0.0,
            total_tokens=sum(r.total_tokens for r in records),
            by_provider=by_provider,
        )

    def _experience_summary(self) -> ExperienceSummaryModel:
        """经验汇总 (六域统计; 无 experience_store → 空汇总)。"""
        store = self._experiences
        if store is None:
            return ExperienceSummaryModel()
        try:
            records = store.list_all()
        except Exception:
            return ExperienceSummaryModel()
        by_domain: dict[str, int] = {}
        success = 0
        score_total = 0.0
        conf_total = 0.0
        for record in records:
            domain = record.domain.value if hasattr(record.domain, "value") else str(record.domain)
            by_domain[domain] = by_domain.get(domain, 0) + 1
            if record.result.value == "success":
                success += 1
            score_total += record.score
            conf_total += record.confidence
        total = len(records)
        return ExperienceSummaryModel(
            total=total,
            by_domain=by_domain,
            success_rate=round(success / total, 4) if total else 0.0,
            avg_score=round(score_total / total, 4) if total else 0.0,
            avg_confidence=round(conf_total / total, 4) if total else 0.0,
        )

    def _agent_summaries(self) -> list[AgentSummary]:
        """Agent 运行投影 (全量, 状态过滤在 Dashboard 派生属性)。"""
        registry = self._agent_registry
        if registry is None:
            return []
        try:
            agents = registry.list()
        except Exception:
            return []
        out: list[AgentSummary] = []
        for agent in agents:
            out.append(
                AgentSummary(
                    id=agent.id,
                    name=agent.name,
                    role=agent.role,
                    status=agent.status.value,
                    skills=list(agent.skills),
                    current_task=agent.current_task,
                )
            )
        return out

    def _recent_events(self, limit: int) -> list[EventSummary]:
        """最近事件活动投影 (事件审计流; 无 event_store → 空)。"""
        store = self._events
        if store is None:
            return []
        try:
            events = store.query(limit=max(limit, 0))
        except Exception:
            return []
        out: list[EventSummary] = []
        for event in events:
            from events.models import format_timestamp

            out.append(
                EventSummary(
                    seq=event.seq,
                    type=event.type.value,
                    timestamp=format_timestamp(event.timestamp),
                    source=event.source,
                    project_id=event.project_id,
                    task_id=event.task_id,
                    action=event.action,
                    result=event.result,
                )
            )
        return out

    def _usage_by_provider(self) -> dict[str, dict[str, Any]]:
        """usage 按 Provider 聚合 (calls/total_cost/success_rate; 失败安全)。"""
        store = self._usage
        if store is None:
            return {}
        try:
            records = store.list()
        except Exception:
            return {}
        out: dict[str, dict[str, Any]] = {}
        for record in records:
            bucket = out.setdefault(
                record.provider_id, {"calls": 0, "total_cost": 0.0, "success": 0}
            )
            bucket["calls"] += 1
            bucket["total_cost"] = round(bucket["total_cost"] + record.estimated_cost, 6)
            if record.success:
                bucket["success"] += 1
        for bucket in out.values():
            bucket["success_rate"] = (
                round(bucket["success"] / bucket["calls"], 4) if bucket["calls"] else 0.0
            )
            bucket.pop("success", None)
        return out

    def _experience_by_subject(self) -> dict[str, list[Any]]:
        """经验记录按 subject_id 分组 (Provider 经验聚合输入; 失败安全)。"""
        store = self._experiences
        if store is None:
            return {}
        try:
            records = store.list_all()
        except Exception:
            return {}
        out: dict[str, list[Any]] = {}
        for record in records:
            out.setdefault(record.subject_id, []).append(record)
        return out

    @staticmethod
    def _provider_cost_score(usage: dict[str, Any] | None, records: list[Any]) -> float | None:
        """成本效益分 (0-1, 高 = 单位产出成本低)。

        avg_cost 越低越好 → 1/(1+avg_cost) 归一 (0 成本 → 1.0; 无 usage →
        None 不臆造); 经验记录的 cost 分 (0-1) 补充均值。
        """
        if not usage and not records:
            return None
        cost_parts: list[float] = []
        if usage and usage.get("calls"):
            avg = float(usage["total_cost"]) / float(usage["calls"])
            cost_parts.append(1.0 / (1.0 + avg))
        for record in records:
            if record.cost is not None:
                cost_parts.append(float(record.cost))
        if not cost_parts:
            return None
        return round(sum(cost_parts) / len(cost_parts), 4)

    @staticmethod
    def _provider_performance_score(usage: dict[str, Any] | None) -> float | None:
        """性能分 (0-1): success_rate 为主 (usage 调用成功率); 无 usage → None。"""
        if not usage or not usage.get("calls"):
            return None
        return round(float(usage["success_rate"]), 4)

    @staticmethod
    def _provider_experience_score(records: list[Any]) -> float | None:
        """经验分 (0-1): 记录 score×confidence×freshness 均值 (正负经验语义,
        同 ExperienceAnalyzer 聚合; 无记录 → None 冷启动不臆造)。"""
        if not records:
            return None
        from intelligence.experience import aggregate_experience_factor

        try:
            return round(aggregate_experience_factor(records), 4)
        except Exception:
            return None


__all__ = ["ConsoleService", "DEFAULT_RECENT_LIMIT"]
