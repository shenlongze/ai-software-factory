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

import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import (
    AgentSummary,
    ApprovalDecisionSummary,
    ApprovalGateSummary,
    ApprovalSummary,
    ArtifactContent,
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
    ReviewFeedback,
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


class ProjectConflictError(Exception):
    """S10-006.5: 项目删除冲突 (workflow 运行中 → HTTP 409 诚实拒绝)。

    与 RuntimeStateError/WorkflowConflictError 同语义 — 破坏性操作
    (删除) 在执行进行中不可执行, 前端提示等待完成后再试。
    """


class ProjectConfirmConflictError(Exception):
    """S10-009 Task 5: Confirm 冲突 (HTTP 409 诚实拒绝)。

    两类: ① 状态未到确认点 (非 discovery/product_defined 的确认请求 —
    含已 confirmed 后不同 name 的重复确认) ② slug 冲突 (目标目录名已被
    其他项目占用)。与 RuntimeStateError/ProjectConflictError 同语义 —
    事务预检失败, 未发生任何变更 (回滚点之前)。
    """


class ConfirmTransactionError(Exception):
    """S10-009 Task 5: Confirm 事务执行失败 (HTTP 503)。

    rename/索引/镜像任一步 IO 失败 → 已回滚到快照 (目录/信源/索引/引用
    全量还原), 事务对外表现为失败 — 存储不可用语义 (与创建 503 同口径),
    前端可重试。
    """


class BacklogNotFoundError(Exception):
    """S10-010 Task 3: Backlog 资源不存在 (HTTP 404)。

    两类: ① Task 不存在 (GET/PATCH/DELETE /backlog/task/{id}) ② 子级
    绑定目标不存在 (Feature→Epic / Story→Feature / Task→Story 引用缺失)。
    与项目不存在 (路由函数返回 None → 404) 区分 — 语义均为 404, 详情不同。
    """


class BacklogStateError(Exception):
    """S10-010 Task 3: Task 状态机非法转换 (HTTP 409)。

    目标态不在 TASK_TRANSITIONS[当前态] (跳级/回退/终态后) → 诚实冲突,
    与 RuntimeStateError/ProjectConflictError 同语义 (409, 非输入错误)。
    依赖未满足 (依赖 gate) 属输入校验 → ValueError → 400, 不在此类。
    """


def _utc_now_str() -> str:
    """当前 UTC 时间 ISO 字符串 (Runtime 实例/截图 created_at)。"""
    return datetime.now(timezone.utc).isoformat()


def _norm_any_list(v: Any) -> Any:
    """None → [] 归一 (S10-010 Task 4: task_refs/daily_progress 输入, 同
    org.models._norm_list 语义 — 容器字段 None 输入宽容)。"""
    return v if v is not None else []


def _confirm_slug(name: str) -> str:
    """Confirm 名称 → 目录 slug (S10-009 Task 5)。

    与 api/projects._slugify 同口径 (CJK 保留 — 中文项目名可作目录名,
    与 create_project 中文名保留一致): 小写; 非字母数字/中文 → '-';
    压缩连续 '-' 并去首尾。纯符号/空 → "" (调用方按非法 name 拒绝)。
    """
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", str(name).strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def _derived_slug(project: Any) -> str:
    """项目目录名 (与 org.space._effective_slug 同口径): slug 优先, 无 → name slug 化, 再兜底 id。"""
    if getattr(project, "slug", ""):
        return project.slug
    derived = _confirm_slug(getattr(project, "name", "") or "")
    return derived if derived else (project.id if project.id else "")


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """原子写原始字节 (回滚还原用 — 临时文件 + os.replace, 同 store 模式)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _safe_read_bytes(path: Path) -> bytes | None:
    """读取原始字节; 不存在/IO 错误 → None (回滚快照失败安全)。"""
    try:
        return path.read_bytes()
    except OSError:
        return None

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
        # S10-006: 审核反馈持久化 (Feedback Loop — Reject 意见落库; 可选,
        # 失败安全: 缺 store → 反馈保存/查询按空处理, 不拖垮审批决定)
        review_feedback_store: Any = None,
        # S10-006.5 P1-A: 对话记录持久化 (POST /projects/{id}/chat 消息落库;
        # 可选, 失败安全: 缺 store → 消息记录跳过, 对话仍可用)
        conversation_store: Any = None,
        # S10-009 Task 4: Project Space (workspace/projects/{slug}/ 目录信源
        # + idea/discovery 资产; 可选, 失败安全: 缺 space → draft/发现流程
        # 按存储不可用处理 → HTTP 503)
        project_space: Any = None,
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
        # S10-006: 审核反馈 store (缺失 → None; 保存/查询失败安全)
        self._review_feedback_store = review_feedback_store
        # S10-006.5 P1-A: 对话记录 store (POST /projects/{id}/chat 消息落库;
        # 可选, 失败安全: 缺 store → 消息记录跳过, 对话仍可用)
        self._conversation_store = conversation_store
        # S10-009 Task 4: Project Space store (workspace/projects/{slug}/ 目录
        # 信源 — draft/idea/discovery 资产落位; 可选, 失败安全)
        self._project_space = project_space

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

    def _migrate_legacy_spaces(self) -> None:
        """旧项目懒迁移 (S10-009 Task 6 场景 3: list/get 首次访问回填目录镜像)。

        project-lifecycle.md §八 方案 A: 旧项目 (仅 org/projects.json, 无
        workspace 目录) 在读取路径首次访问时经 ProjectSpaceStore.migrate_legacy
        回填目录镜像 (幂等 — 已存在目录跳过, 重复读取零额外写)。失败安全:
        org/space store 任一缺失 → 静默 (读取不因回填失败崩溃)。
        """
        store = self._project_store
        space = self._project_space
        if store is None or space is None:
            return
        try:
            space.migrate_legacy(store)
        except Exception:
            return  # 回填失败 → 静默 (读取路径永不因迁移失败 5xx)

    def list_projects(self) -> list[ProjectSummary]:
        """全部项目只读投影 (workspace 项目定义 + org 项目并集, 含 S9-002
        workflow/stage/progress 聚合)。

        数据源 (全部可选, 失败安全): workspace 项目定义 (id/name/language/
        repository/tech_stack) ∪ org Project (id/name/lifecycle); 同 id 合并。
        org 聚合: 当前 (最近创建) Workflow 运行 → workflow_id/status +
        当前阶段 + progress (completed stages / total stages) + stage_counts。
        """
        self._migrate_legacy_spaces()  # S10-009 Task 6: 旧项目懒迁移 (list 首次访问回填)
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

    # ------------------------------------------------------------------ POST /projects (S10-006.5)

    def create_project(
        self,
        idea: str,
        *,
        name: str | None = None,
        project_type: str | None = None,
        tech: str | None = None,
    ) -> Any | None:
        """创建 org 项目 (POST /projects — 用户第一公里创建闭环)。

        复用 org ProjectLifecycle.create_project (org.project.created 事件
        审计, 不扩 Core 枚举); project_type/tech 落 org Project 已有字段
        (project_type / framework — S9-004 兼容, 零新数据空间)。失败安全:
        org store 缺失/创建失败 → None (HTTP 层 503); 成功 → org Project
        (id/name/lifecycle 起点 idea)。
        """
        store = self._project_store
        if store is None:
            return None
        self._mount_org()
        try:
            from org.projects import ProjectLifecycle
            from org.models import utcnow

            # logger: 生产装配注入带 EventLogger 的 WorkflowLifecycle —
            # 提取其 logger 供 ProjectLifecycle 复用 (org.project.created
            # source=console 落库审计; 无注入 → None 静默, 失败安全)
            logger = (
                getattr(self._workflow, "_logger", None)
                if self._workflow is not None
                else None
            )
            lifecycle = ProjectLifecycle(store, logger=logger)
            project = lifecycle.create_project(
                name or idea,
                user_id="console",
                goal=idea,
            )
            if project_type or tech:
                project = project.model_copy(
                    update={
                        "project_type": project_type or project.project_type,
                        "framework": tech or project.framework,
                        "updated_at": utcnow(),
                    }
                )
                store.save_project(project)
            return project
        except Exception:
            return None  # org 缺失/损坏 → 503 (失败安全, 不拖垮 API)

    # ------------------------------------------------------------------ S10-009 Task 4: Draft + Discovery

    def _org_logger(self) -> Any:
        """org 事件 logger (生产装配注入带 EventLogger 的 WorkflowLifecycle —
        提取其 logger; 无注入 → None 静默, 失败安全)。"""
        return (
            getattr(self._workflow, "_logger", None)
            if self._workflow is not None
            else None
        )

    @staticmethod
    def _record_fail_safe(logger: Any, type_: str, **kwargs: Any) -> None:
        """Core 冻结期字符串事件类型落库 (失败安全 — 同 org _record_fail_safe 模式)。

        EventType 枚举尚无 org.project.discovery.* 成员 (扩枚举 = 改
        factory-core, 冻结铁律) → pydantic ValidationError → 静默跳过,
        不拖垮 draft/answer/complete 链路; 依 ADR-0001 扩枚举后自动恢复。
        """
        if logger is None:
            return
        try:
            logger.record(type_, **kwargs)
        except Exception:
            return

    def create_draft_project(
        self,
        idea: str,
        *,
        project_type: str | None = None,
        tech: str | None = None,
    ) -> Any | None:
        """创建草稿项目 (S10-009 Task 4: POST /projects 无 name → unnamed draft)。

        idea → org Project (name=unnamed-project-{ts}, lifecycle=DISCOVERY,
        draft=True, slug="" — 无正式名/目录名, rename 时更新) + ProjectSpace
        目录骨架 (workspace/projects/{slug}/) + idea/ 初始化 (conversation.json
        + idea.md 含原始想法) + discovery/conversation.json 初始化 (空会话)。
        org.project.created 事件复用既有 record 函数 (不扩 Core 枚举)。
        失败安全: org store / space store 缺失或创建失败 → None (HTTP 503);
        成功 → org Project (id/name/lifecycle/goal)。
        """
        store = self._project_store
        space = self._project_space
        if store is None or space is None:
            return None
        self._mount_org()
        try:
            from org import events as org_events
            from org.models import new_id, utcnow
            from org.projects import Project, ProjectState

            logger = self._org_logger()
            project_id = new_id("P")
            now = utcnow()
            # R1 修复 (S10-009 GATE-PASS R1): 秒级时间戳 + 项目 id 片段 —
            # 同秒连续创建 draft 时 name/slug 不再碰撞 (ensure_space 幂等
            # 已存在不覆盖 → 旧实现第二个 draft get_slug 永久 None →
            # complete/confirm 404 无恢复路径; 现 slug 含 id 后 8 位唯一)。
            name = (
                f"unnamed-project-{now.strftime('%Y%m%d-%H%M%S')}"
                f"-{project_id[2:]}"
            )
            project = Project(
                id=project_id,
                name=name,
                slug="",  # draft 期无正式 slug (Task 5 confirm/rename 时更新)
                user_id="console",
                goal=idea,
                lifecycle=ProjectState.DISCOVERY,
                draft=True,
            )
            if project_type or tech:
                project = project.model_copy(
                    update={
                        "project_type": project_type or project.project_type,
                        "framework": tech or project.framework,
                        "updated_at": utcnow(),
                    }
                )
            store.save_project(project)
            org_events.record_project_created(logger, project=project)
            # ProjectSpace: 骨架 + project.json 镜像 + idea/discovery 初始化
            space_dir = space.ensure_space(project)
            slug = space_dir.name
            now_iso = now.isoformat()
            space.write_json(
                slug,
                "idea/conversation.json",
                {
                    "project_id": project_id,
                    "idea": idea,
                    "created_at": now_iso,
                    "conversation": [
                        {"role": "user", "content": idea, "at": now_iso}
                    ],
                },
            )
            space.write_text(
                slug, "idea/idea.md", f"# Idea\n\n{idea}\n"
            )
            space.write_json(
                slug,
                "discovery/conversation.json",
                {
                    "project_id": project_id,
                    "session_id": f"DS-{project_id[2:]}",
                    "status": "active",
                    "started_at": now_iso,
                    "updated_at": now_iso,
                    "conversation": [],
                },
            )
            return project
        except Exception:
            return None  # org/space 缺失或损坏 → 503 (失败安全, 不拖垮 API)

    def save_discovery_answer(
        self, project_id: str, question: str, answer: str
    ) -> dict[str, Any] | None:
        """记录 Discovery 问答 (S10-009 Task 4: discovery/conversation.json 追加)。

        追加条目 {question, asked_at, answer, answered_at} (可多次, 顺序保留);
        org Project.discovery 字段镜像 + space project.json 同步 (引用完整,
        失败安全)。错误语义: 空 answer/question → ValueError (HTTP 400 —
        空问答不记录); 项目不存在 / store 缺失 / 损坏 → None (HTTP 404,
        失败安全)。成功 → {project_id, question, answer, count}。
        """
        cleaned_q = str(question or "").strip()
        cleaned_a = str(answer or "").strip()
        if not cleaned_a:
            raise ValueError("answer is required (空答案不记录)")
        if not cleaned_q:
            raise ValueError("question is required (空问题不记录)")
        store = self._project_store
        space = self._project_space
        if store is None or space is None:
            return None
        self._mount_org()
        try:
            from org.models import utcnow

            project = store.get_project(project_id)
            if project is None:
                return None
            slug = space.get_slug(project_id)
            if slug is None:
                return None
            data = space.read_json(slug, "discovery/conversation.json") or {}
            conversation = data.get("conversation")
            if not isinstance(conversation, list):
                conversation = []
            now = utcnow().isoformat()
            conversation.append(
                {
                    "question": cleaned_q,
                    "asked_at": now,
                    "answer": cleaned_a,
                    "answered_at": now,
                }
            )
            data.update(
                {
                    "project_id": project_id,
                    "status": "active",
                    "updated_at": now,
                    "conversation": conversation,
                }
            )
            space.write_json(slug, "discovery/conversation.json", data)
            # org Project.discovery 镜像 (Task 5 项目详情数据源; 失败安全)
            self._sync_discovery_state(project, data, slug)
            self._record_fail_safe(
                self._org_logger(),
                "org.project.discovery.answered",
                source="console",
                project_id=project_id,
                question=cleaned_q,
                result="OK",
            )
            return {
                "project_id": project_id,
                "question": cleaned_q,
                "answer": cleaned_a,
                "count": len(conversation),
            }
        except Exception:
            return None  # org/space 损坏 → 404 (失败安全, 不拖垮 API)

    def _sync_discovery_state(self, project: Any, data: dict[str, Any], slug: str) -> None:
        """org Project.discovery 镜像 + space project.json 同步 (失败安全)。

        discovery dict 携带 session_id/status/answered_count/product_definition
        (Task 5 GET 项目详情数据源); 同步写 org store + space 信源, 任一步
        失败 → 静默 (主体操作已完成, 不撤销)。
        """
        try:
            from org.models import utcnow

            conversation = data.get("conversation")
            answered_count = len(conversation) if isinstance(conversation, list) else 0
            discovery = {
                "session_id": data.get("session_id"),
                "status": data.get("status", "active"),
                "started_at": data.get("started_at"),
                "updated_at": data.get("updated_at"),
                "answered_count": answered_count,
            }
            if data.get("product_definition"):
                discovery["product_definition"] = data["product_definition"]
            updated = project.model_copy(
                update={"discovery": discovery, "updated_at": utcnow()}
            )
            self._project_store.save_project(updated)
            if self._project_space is not None:
                self._project_space.save_project(updated)
        except Exception:
            return  # 镜像失败 → 静默 (不拖垮问答/完成链路)

    def complete_discovery(self, project_id: str) -> Any | None:
        """完成 Discovery (S10-009 Task 4: product-definition.md + lifecycle 流转)。

        生成 discovery/product-definition.md (规则式 markdown — 基于原始想法
        + 澄清沟通记录, 不伪造 AI); lifecycle discovery → product_defined
        (受控转换, org.project.lifecycle_changed 事件); discovery 会话
        status → completed + product_definition 引用 (org Project.discovery
        镜像 + space project.json 同步)。错误语义: 未在 discovery 状态 →
        ValueError (HTTP 层 409 — 状态冲突, 诚实拒绝); 项目不存在 / store
        缺失 → None (HTTP 404)。成功 → 流转后 org Project。
        """
        store = self._project_store
        space = self._project_space
        if store is None or space is None:
            return None
        self._mount_org()
        try:
            from org.models import utcnow
            from org.projects import ProjectLifecycle, ProjectState

            logger = self._org_logger()
            project = store.get_project(project_id)
            if project is None:
                return None
            if project.lifecycle != ProjectState.DISCOVERY:
                raise ValueError(
                    f"project is not in discovery state: {project_id} "
                    f"(lifecycle={project.lifecycle.value}; discovery/complete "
                    f"仅限 discovery 状态)"
                )
            slug = space.get_slug(project_id)
            if slug is None:
                return None
            data = space.read_json(slug, "discovery/conversation.json") or {}
            conversation = data.get("conversation")
            if not isinstance(conversation, list):
                conversation = []
            content = self._build_product_definition(project, conversation)
            space.write_text(slug, "discovery/product-definition.md", content)
            # lifecycle 流转: discovery → product_defined (受控转换表 + 事件)
            lifecycle = ProjectLifecycle(store, logger=logger)
            updated = lifecycle.transition_lifecycle(project_id, ProjectState.PRODUCT_DEFINED)
            # discovery 会话收尾: status=completed + product_definition 引用
            now = utcnow()
            data.update(
                {
                    "status": "completed",
                    "updated_at": now.isoformat(),
                    "product_definition": "discovery/product-definition.md",
                }
            )
            space.write_json(slug, "discovery/conversation.json", data)
            self._sync_discovery_state(updated, data, slug)
            self._record_fail_safe(
                logger,
                "org.project.discovery.completed",
                source="console",
                project_id=project_id,
                product_definition_ref="discovery/product-definition.md",
                result="OK",
            )
            return updated
        except ValueError:
            raise  # 非法状态 → HTTP 409 (状态冲突语义)
        except Exception:
            return None  # org/space 损坏 → 404 (失败安全, 不拖垮 API)

    @staticmethod
    def _build_product_definition(project: Any, conversation: list[dict[str, Any]]) -> str:
        """规则式 product-definition.md (诚实: 基于原始想法 + 澄清记录, 不伪造 AI)。"""
        lines = [
            "# Product Definition",
            "",
            f"- project: {project.id}",
            f"- name: {project.name}",
            f"- lifecycle: {project.lifecycle.value} → product_defined",
            "",
            "## Idea (原始想法)",
            "",
            project.goal or project.name,
            "",
            "## Discovery Conversation (澄清记录)",
            "",
        ]
        if not conversation:
            lines.append("(无澄清问答)")
        for entry in conversation:
            lines.append(f"- Q: {entry.get('question', '')}")
            lines.append(f"  A: {entry.get('answer', '')}")
        lines += [
            "",
            "## Summary (产品定义结论)",
            "",
            "产品围绕原始想法展开, 结合澄清沟通形成初步产品定义。",
            "",
        ]
        return "\n".join(lines)

    # ------------------------------------------------- S10-009 Task 5: Confirm + Rename 事务

    def confirm_project(self, project_id: str, name: str) -> Any | None:
        """Confirm + Rename 事务 (S10-009 Task 5: POST /projects/{id}/confirm)。

        流程 (project-lifecycle.md §6 rename 机制 + S10-009-plan Task 5):
          校验 (name 合法 + slug 唯一 + 状态到确认点) → 快照 (回滚点) →
          写 project.json (name/slug/lifecycle=confirmed/draft=false) →
          目录 rename (os.replace 原子, 旧目录内信源随目录一并移动) →
          索引更新 (workspace/projects.json → id: 新 slug) →
          引用更新 (org/projects.json 镜像 — id 稳定, rename 不变; 其余
          引用均按 project_id 寻址 [workflow_runs/runtimes/chat], 无需改写)。
        任一步失败 → 回滚到快照 (目录/信源/索引/引用全量逐字节还原) +
        抛 ConfirmTransactionError (HTTP 503 — 存储不可用语义)。

        错误语义:
        - 非法 name (空 / 无法 slug 化) → ValueError (HTTP 400)
        - 状态未到确认点 (非 discovery/product_defined) → ProjectConfirmConflictError
          (HTTP 409); 已 confirmed 后不同 name 重复确认 → 同 409 (已过确认点)
        - slug 冲突 (目标目录已存在) → ProjectConfirmConflictError (HTTP 409,
          事务预检失败, 零变更)
        - 项目不存在 / org/space 缺失或损坏 → None (HTTP 404, 失败安全)
        幂等: 已 confirmed 且 name/slug 与当前一致 → 原样返回 (200, 零变更)。
        兼容: 旧项目 (仅 org 记录, 无目录) → 先 ensure_space 回填镜像再 rename。
        """
        store = self._project_store
        space = self._project_space
        if store is None or space is None:
            return None
        self._mount_org()
        try:
            from org.models import utcnow
            from org.projects import ProjectState

            logger = self._org_logger()
            project = store.get_project(project_id)
            if project is None:
                return None
            # 1. name 校验 (空 / 无法 slug 化 → 400)
            cleaned = str(name or "").strip()
            if not cleaned:
                raise ValueError("name is required (空名字不确认)")
            new_slug = _confirm_slug(cleaned)
            if not new_slug:
                raise ValueError(
                    f"name cannot form a slug: {cleaned!r} (非法名字不确认)"
                )
            # 2. 状态约束 (discovery/product_defined 为确认点; 已 confirmed 同
            #    name/slug → 幂等返回; 其余状态 → 409 未到确认点)
            if project.lifecycle not in (
                ProjectState.DISCOVERY,
                ProjectState.PRODUCT_DEFINED,
            ):
                if (
                    project.lifecycle == ProjectState.CONFIRMED
                    and project.name == cleaned
                    and project.slug == new_slug
                ):
                    return project  # 幂等: 零变更
                raise ProjectConfirmConflictError(
                    f"project is not at confirmation point: {project_id} "
                    f"(lifecycle={project.lifecycle.value}; confirm 仅限 "
                    f"discovery/product_defined 状态)"
                )
            # 3. slug 唯一性预检 (事务开始前 — 失败零变更)
            old_slug = space.get_slug(project_id)
            if old_slug is None:
                # 兼容: 旧项目无目录 → 先回填目录镜像再 rename
                space.ensure_space(project)
                old_slug = space.get_slug(project_id)
            if old_slug is None:
                return None  # 空间仍不可用 → 404 (失败安全)
            if space.has_space(new_slug) and new_slug != old_slug:
                raise ProjectConfirmConflictError(
                    f"slug already exists: {new_slug} (目录名冲突, 已存在同名项目)"
                )
            # 4. 快照 (回滚点) + 提交
            updated = project.model_copy(
                update={
                    "name": cleaned,
                    "slug": new_slug,
                    "lifecycle": ProjectState.CONFIRMED,
                    "draft": False,
                    "updated_at": utcnow(),
                }
            )
            snap = self._confirm_snapshot(space, store, old_slug)
            try:
                # 5. 写 project.json (旧目录内 — 随目录 rename 一并移动)
                space.write_json(old_slug, "project.json", updated.to_dict())
                # 6. 目录 rename (os.replace 原子 — 整目录移动, 内容零丢失)
                space.rename_space(old_slug, new_slug)
                snap["new_slug"] = new_slug
                # 7. 索引更新 (workspace/projects.json → id: 新 slug)
                space.rebuild_index()
                # 8. 引用更新 (org/projects.json 镜像)
                store.save_project(updated)
            except Exception as exc:
                self._confirm_rollback(space, store, snap)
                raise ConfirmTransactionError(
                    f"confirm transaction failed and rolled back: "
                    f"{project_id} → {new_slug}: {exc}"
                ) from exc
            # 审计 (失败安全: 审计事件失败不撤销已提交事务)
            try:
                from org import events as org_events

                org_events.record_project_lifecycle_changed(
                    logger,
                    project=updated,
                    from_lifecycle=project.lifecycle.value,
                    to_lifecycle=ProjectState.CONFIRMED.value,
                    source="console",
                )
            except Exception:
                pass
            self._record_fail_safe(
                logger,
                "org.project.confirmed",
                source="console",
                project_id=project_id,
                name=cleaned,
                slug=new_slug,
                result="OK",
            )
            return updated
        except ValueError:
            raise  # 非法 name → HTTP 400
        except ProjectConfirmConflictError:
            raise  # 状态/冲突 → HTTP 409
        except ConfirmTransactionError:
            raise  # 事务失败已回滚 → HTTP 503
        except Exception:
            return None  # org/space 损坏 → 404 (失败安全, 不拖垮 API)

    @staticmethod
    def _confirm_snapshot(space: Any, store: Any, old_slug: str) -> dict[str, Any]:
        """Confirm 事务回滚点快照 (旧目录/信源/索引/org 镜像原始字节)。"""
        old_dir = space.space_dir(old_slug)
        return {
            "old_slug": old_slug,
            "new_slug": None,  # rename 成功后才记录 (回滚据此判断是否需 rename 还原)
            "project_json": _safe_read_bytes(old_dir / "project.json"),
            "index": _safe_read_bytes(space.index_path),
            "org": _safe_read_bytes(Path(store.dir) / "projects.json"),
        }

    @staticmethod
    def _confirm_rollback(space: Any, store: Any, snap: dict[str, Any]) -> None:
        """回滚到快照: 目录 rename 还原 + project.json/索引/org 镜像逐字节还原。

        尽力而为: 任一步失败静默 (原始事务异常优先上抛 — 回滚是兜底, 不掩盖
        主失败); 幂等 — 未发生步骤的还原是 no-op; 快照为 None 的文件 (事务前
        不存在) → 删除 (逐字节还原, 不留事务残留)。
        """
        try:
            if snap.get("new_slug") and space.has_space(snap["new_slug"]):
                if not space.has_space(snap["old_slug"]):
                    space.rename_space(snap["new_slug"], snap["old_slug"])
            project_json_path = space.space_dir(snap["old_slug"]) / "project.json"
            if snap.get("project_json") is not None:
                _atomic_write_bytes(project_json_path, snap["project_json"])
            elif project_json_path.exists():
                project_json_path.unlink()
            index_path = space.index_path
            if snap.get("index") is not None:
                _atomic_write_bytes(index_path, snap["index"])
            elif index_path.exists():
                index_path.unlink()
            org_path = Path(store.dir) / "projects.json"
            if snap.get("org") is not None:
                _atomic_write_bytes(org_path, snap["org"])
            elif org_path.exists():
                org_path.unlink()
        except Exception:
            return  # 回滚尽力而为 (主异常已上抛)

    # ------------------------------------------------------------------ S10-006.5 P1-A: Workflow 启动/对话

    def workflow_run_paths(self) -> dict[str, Any] | None:
        """Workflow 运行数据空间路径 (org 数据空间派生的目录布局)。

        返回 {org_dir, runs_dir}: org_dir = <root>/org (ProjectStore 根),
        runs_dir = <root>/workflow_runs (运行沙箱/报告目录); project_store
        缺失 → None (HTTP 层 503 — 存储不可用, 失败安全)。events db 路径
        由 Adapter 层从 event_logger.store.db_path 提供 (本服务不持事件库)。
        """
        store = self._project_store
        if store is None:
            return None
        try:
            org_dir = store.dir
        except Exception:
            return None
        return {
            "org_dir": str(org_dir),
            "runs_dir": str(Path(org_dir).parent / "workflow_runs"),
        }

    def project_idea(self, project_id: str) -> str | None:
        """项目 idea (org Project.goal; 无 org/不存在 → None)。"""
        if self._project_store is None:
            return None
        try:
            project = self._project_store.get_project(project_id)
        except Exception:
            return None
        if project is None:
            return None
        return project.goal or project.name or None

    def update_project_idea(self, project_id: str, idea: str) -> bool:
        """更新项目 idea (org Project.goal — 聊天未启动场景); 失败 → False。

        只改 org Project 数据 (不触碰 Core Workflow/Artifact/Approval —
        冻结铁律); 更新后 Workflow 启动链以新 idea 为输入。
        """
        if self._project_store is None:
            return False
        try:
            from org.models import utcnow

            project = self._project_store.get_project(project_id)
            if project is None:
                return False
            updated = project.model_copy(update={"goal": idea, "updated_at": utcnow()})
            self._project_store.save_project(updated)
            return True
        except Exception:
            return False  # org 缺失/损坏 → False (失败安全)

    def update_project(
        self,
        project_id: str,
        *,
        name: str | None = None,
        idea: str | None = None,
    ) -> Any | None:
        """更新 org 项目 (PATCH /projects/{id} — 重命名/改 idea)。

        name/idea 任一提供 → org Project 对应字段 (name/goal) + updated_at
        落库 (复用 save_project 原子写, 零新数据空间)。错误语义:
        - 显式空 name/idea (strip 后) → ValueError (HTTP 400 — 空字段不落库)
        - 两者皆空 (未提供任何更新) → ValueError (HTTP 400 — 无事可做)
        - org store 缺失 / 项目不存在 / org 损坏 → None (HTTP 404, 失败安全)
        成功 → 更新后 org Project (更新摘要由 API 层投影)。
        """
        cleaned_name = name.strip() if isinstance(name, str) else ""
        cleaned_idea = idea.strip() if isinstance(idea, str) else ""
        if name is not None and not cleaned_name:
            raise ValueError("name is required (空名字不落库)")
        if idea is not None and not cleaned_idea:
            raise ValueError("idea is required (空想法不落库)")
        if not cleaned_name and not cleaned_idea:
            raise ValueError("nothing to update (name/idea 至少提供一项)")
        store = self._project_store
        if store is None:
            return None
        self._mount_org()
        try:
            from org.models import utcnow

            project = store.get_project(project_id)
            if project is None:
                return None
            update: dict[str, Any] = {"updated_at": utcnow()}
            if cleaned_name:
                update["name"] = cleaned_name
            if cleaned_idea:
                update["goal"] = cleaned_idea
            updated = project.model_copy(update=update)
            store.save_project(updated)
            # B4 治理 (S10-010 Task 5): 目录镜像同步 — name 变化 → rename 目录;
            # idea 变化 → 镜像 goal 同步 (信源不陈旧)
            if self._project_space is not None:
                try:
                    space = self._project_space
                    if cleaned_name:
                        old_slug = space.get_slug(project_id) or _derived_slug(project)
                        new_slug = _derived_slug(updated)
                        if old_slug and new_slug and old_slug != new_slug:
                            if space.has_space(old_slug):
                                space.rename_space(old_slug, new_slug)
                                updated = updated.model_copy(
                                    update={"slug": new_slug, "updated_at": updated.updated_at}
                                )
                                store.save_project(updated)
                            space.save_project(updated)
                            space.rebuild_index()
                    elif cleaned_idea:
                        space.save_project(updated)  # 镜像 goal 同步
                except Exception:
                    pass  # 镜像同步失败安全 (org 主记录已成功)
            return updated
        except Exception:
            return None  # org 缺失/损坏 → 404 (失败安全, 不拖垮 API)

    def delete_project(self, project_id: str) -> bool | None:
        """删除 org 项目 (DELETE /projects/{id} — 项目管理; 运行中保护)。

        顺序: ① 运行中检查 (workflow_runner.is_project_running — 模块级
        _RUNNING; 运行中 → ProjectConflictError, HTTP 层 409 诚实拒绝 —
        防删除执行中的数据) → ② org 删除 (ProjectLifecycle.delete_project:
        不存在 → NotFoundError → None 404; org.project.deleted 事件失败安全
        落库) → ③ 运行数据清理 (workflow_runs/{id} 目录 + chat.json 该项目
        对话记录 — 失败安全: 清理失败不撤销删除)。org store 缺失/损坏 →
        None (失败安全, 不拖垮 API)。
        """
        store = self._project_store
        if store is None:
            return None
        # 延迟导入 workflow_runner (模块级副作用隔离, 同 api/workflow_start 模式)
        from .workflow_runner import is_project_running

        if is_project_running(project_id):
            raise ProjectConflictError(
                f"project is running: {project_id} (运行中不可删除, 等待完成后重试)"
            )
        self._mount_org()
        try:
            from org.projects import NotFoundError, ProjectLifecycle

            logger = (
                getattr(self._workflow, "_logger", None)
                if self._workflow is not None
                else None
            )
            lifecycle = ProjectLifecycle(store, logger=logger)
            try:
                lifecycle.delete_project(project_id)
            except NotFoundError:
                return None  # 项目不存在 → HTTP 404
        except Exception:
            return None  # org 缺失/损坏 → 失败安全
        # B3 治理 (S10-010 Task 5): 清理项目空间目录 (防 rebuild_index 扫回幽灵)
        if self._project_space is not None:
            try:
                space = self._project_space
                slug = space.get_slug(project_id)
                if slug:
                    space.remove_space(slug)
            except Exception:
                pass  # 空间清理失败安全 (org 删除已成功)
        self._cleanup_project_data(project_id)
        return True

    def _cleanup_project_data(self, project_id: str) -> None:
        """删除项目运行数据 (workflow_runs/{id} + chat.json 对话; 失败安全)。

        尽力而为: 目录/记录不存在或清理失败 → 静默 (删除主体已成功, 残留
        孤儿数据不阻塞 — 同 chat 记录 缺 store 静默哲学)。
        """
        try:
            runs_dir = Path(self._project_store.dir).parent / "workflow_runs"
            shutil.rmtree(runs_dir / project_id, ignore_errors=True)
        except Exception:
            pass
        try:
            conversation = self._conversation_store
            if conversation is not None:
                conversation.clear_project(project_id)
        except Exception:
            pass

    def get_conversation_store(self) -> Any:
        """对话记录 store (S10-006.5 P1-A — POST /projects/{id}/chat 落库)。

        缺失 → None (失败安全: 消息记录跳过, 对话/启动不受影响 — 同
        _get_runtime_store 模式, 方法名避开实例属性遮蔽陷阱)。
        """
        return self._conversation_store

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
        self._migrate_legacy_spaces()  # S10-009 Task 6: 旧项目懒迁移 (get 首次访问回填)
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

    def get_artifact_content(self, artifact_id: str) -> "ArtifactContent | None":
        """产物渲染内容 (GET /artifacts/{id}/content; S10-005)。

        复用 get_artifact 定位产物 (无 org/不存在 → None, 404 语义同详情);
        content 尝试读 location 指向的文本文件 — 相对 org store 目录解析,
        越界/缺失/不可读 → None (失败安全: 查看器以 metadata 为主, content
        仅补 Code diff 兜底 / Release 下载, 缺数据不拖垮)。
        """
        detail = self.get_artifact(artifact_id)
        if detail is None:
            return None
        content: str | None = None
        if detail.location:
            lifecycle = self._workflow_lifecycle()
            store = getattr(lifecycle, "store", None) if lifecycle else None
            root = getattr(store, "dir", None) if store else None
            if root is not None:
                try:
                    base = Path(root).resolve()
                    target = (base / detail.location).resolve()
                    if target.is_relative_to(base) and target.is_file():
                        content = target.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    content = None  # 读取失败 → None (失败安全)
        return ArtifactContent(
            artifact_id=detail.id,
            type=detail.type,
            location=detail.location,
            content=content,
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

    # ------------------------------------------------------ S10-006 审核反馈 (Feedback Loop)

    def save_review_feedback(
        self,
        *,
        gate_id: str,
        artifact_id: str,
        reviewer: str = "console",
        comment: str = "",
    ) -> ReviewFeedback | None:
        """保存一条审核反馈记录 (POST /api/review-feedback)。

        对应 api-data-model.md §1 ReviewComment 的实践形态: Reject 意见除
        gate.comment 落库 (S9-001 审计) 外, 另存结构化记录 (round 按产物
        递增), 作为下一轮 Agent 重生成输入的数据源。store 缺失 → None
        (失败安全 — 审批决定不受反馈保存失败影响); 空意见 → None (无反馈
        不落库, 诚实边界)。
        """
        store = self._review_feedback_store
        if store is None:
            return None
        trimmed = comment.strip()
        if not trimmed:
            return None
        from .review_feedback import new_feedback_id

        record = ReviewFeedback(
            id=new_feedback_id(),
            gate_id=gate_id,
            artifact_id=artifact_id,
            reviewer=reviewer or "console",
            comment=trimmed,
            round=store.next_round(artifact_id),
            created_at=_utc_now_str(),
        )
        store.save(record)
        return record

    def list_review_feedback(
        self,
        artifact_id: str | None = None,
        gate_id: str | None = None,
    ) -> list[ReviewFeedback]:
        """审核反馈历史 (GET /api/review-feedback — 按 artifact/gate 过滤)。

        artifact_id 提供 → 该产物全部反馈; 否则全库。gate_id 提供 → 追加
        来源门过滤。按 round 升序 (下轮输入按序消费); store 缺失 → []
        (失败安全)。
        """
        store = self._review_feedback_store
        if store is None:
            return []
        records = (
            store.list_by_artifact(artifact_id) if artifact_id else store.list_all()
        )
        if gate_id:
            records = [r for r in records if r.gate_id == gate_id]
        return records

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

    # ------------------------------------------------- S10-010 Task 3: Backlog API
    # Requirement Management (AF-PRD-v1.md 4.3): Epic→Feature→Story→Task 层级
    # CRUD。数据信源 = workspace/projects/{slug}/management/backlog/*.json
    # (org ManagementStore 目录信源 — project-management-system.md §十);
    # Task 状态机/priority/dependency 校验复用 org.management (Task 002)。
    # 错误语义: 项目不存在/缺 store → None (HTTP 404); 任务/绑定不存在 →
    # BacklogNotFoundError (404); 参数/依赖/priority 非法 → ValueError (400);
    # 状态机非法转换 → BacklogStateError (409)。

    def _management_store(self, project_id: str) -> Any | None:
        """定位项目 management 目录并构造 ManagementStore。

        项目不存在 / org ProjectStore 或 ProjectSpaceStore 缺失 → None
        (调用方 → HTTP 404, 与既有项目不存在语义同口径)。目录名经
        space.ensure_space 决定 (project.slug → name slugify → id, 与
        migrate_legacy 同口径) 并幂等建骨架 (含 management/ 子目录);
        ManagementStore 首次 save 才写 backlog/*.json (旧项目零破坏)。
        """
        store = self._project_store
        space = self._project_space
        if store is None or space is None:
            return None
        project = store.get_project(project_id)
        if project is None:
            return None
        space_dir = space.ensure_space(project)
        self._mount_org()  # factory-org 挂载 (幂等; Removal Isolation)
        from org.management import ManagementStore

        return ManagementStore(space_dir / "management")

    @staticmethod
    def _task_dependency_map(mgmt: Any) -> dict[str, list[str]]:
        """全量任务依赖声明图 {task_id: [dependency ids]} (环检测构图用)。"""
        return {t.id: list(t.dependency) for t in mgmt.list_tasks()}

    @staticmethod
    def _task_status_map(mgmt: Any) -> dict[str, Any]:
        """全量任务当前状态 {task_id: status} (依赖 gate 校验用)。"""
        return {t.id: t.status for t in mgmt.list_tasks()}

    def create_epic(
        self, project_id: str, *, name: str, description: str = ""
    ) -> dict[str, Any] | None:
        """POST /backlog/epic — 创建 Epic (children 引用 Feature, 非包含)。"""
        mgmt = self._management_store(project_id)
        if mgmt is None:
            return None
        cleaned = str(name or "").strip()
        if not cleaned:
            raise ValueError("name is required (空名字不创建)")
        self._mount_org()
        from org.management import Epic
        from org.models import new_id

        epic = Epic(
            id=new_id("EPIC"),
            name=cleaned,
            description=str(description or "").strip(),
        )
        mgmt.save_epic(epic)
        return epic.to_dict()

    def create_feature(
        self,
        project_id: str,
        *,
        name: str,
        description: str = "",
        epic_id: str = "",
    ) -> dict[str, Any] | None:
        """POST /backlog/feature — 创建 Feature (可选绑定 Epic)。"""
        mgmt = self._management_store(project_id)
        if mgmt is None:
            return None
        cleaned = str(name or "").strip()
        if not cleaned:
            raise ValueError("name is required (空名字不创建)")
        self._mount_org()
        from org.management import Feature
        from org.models import new_id, utcnow

        feature = Feature(
            id=new_id("FEAT"),
            name=cleaned,
            description=str(description or "").strip(),
        )
        bound_epic = str(epic_id or "").strip()
        if bound_epic:
            epic = mgmt.get_epic(bound_epic)
            if epic is None:
                raise BacklogNotFoundError(f"epic not found: {bound_epic}")
            mgmt.save_epic(
                epic.model_copy(
                    update={
                        "children": list(epic.children) + [feature.id],
                        "updated_at": utcnow(),
                    }
                )
            )
        mgmt.save_feature(feature)
        result = feature.to_dict()
        result["epic_id"] = bound_epic
        return result

    def create_story(
        self,
        project_id: str,
        *,
        name: str,
        description: str = "",
        feature_id: str = "",
    ) -> dict[str, Any] | None:
        """POST /backlog/story — 创建 Story (可选绑定 Feature)。"""
        mgmt = self._management_store(project_id)
        if mgmt is None:
            return None
        cleaned = str(name or "").strip()
        if not cleaned:
            raise ValueError("name is required (空名字不创建)")
        self._mount_org()
        from org.management import Story
        from org.models import new_id, utcnow

        story = Story(
            id=new_id("STORY"),
            name=cleaned,
            description=str(description or "").strip(),
        )
        bound_feature = str(feature_id or "").strip()
        if bound_feature:
            feature = mgmt.get_feature(bound_feature)
            if feature is None:
                raise BacklogNotFoundError(f"feature not found: {bound_feature}")
            mgmt.save_feature(
                feature.model_copy(
                    update={
                        "children": list(feature.children) + [story.id],
                        "updated_at": utcnow(),
                    }
                )
            )
        mgmt.save_story(story)
        result = story.to_dict()
        result["feature_id"] = bound_feature
        return result

    def create_task(
        self,
        project_id: str,
        *,
        title: str,
        description: str = "",
        priority: Any = None,
        dependency: Any = None,
        story_id: str = "",
    ) -> dict[str, Any] | None:
        """POST /backlog/task — 创建 Task (可选绑定 Story; priority/dependency 校验)。

        priority 非法 (非 P0-P3) → ValueError (HTTP 400); dependency 自引用/
        环 → ValueError (HTTP 400); story_id 不存在 → BacklogNotFoundError (404)。
        """
        mgmt = self._management_store(project_id)
        if mgmt is None:
            return None
        cleaned_title = str(title or "").strip()
        if not cleaned_title:
            raise ValueError("title is required (空标题不创建)")
        self._mount_org()
        from org.management import Task, TaskPriority, validate_dependency
        from org.models import new_id, utcnow

        task_id = new_id("TASK")
        deps = validate_dependency(
            dependency,
            task_id,
            known_dependencies=self._task_dependency_map(mgmt),
        )
        prio = (
            TaskPriority.parse(priority)
            if priority not in (None, "")
            else TaskPriority.P2
        )
        task = Task(
            id=task_id,
            title=cleaned_title,
            description=str(description or "").strip(),
            priority=prio,
            dependency=deps,
        )
        bound_story = str(story_id or "").strip()
        if bound_story:
            story = mgmt.get_story(bound_story)
            if story is None:
                raise BacklogNotFoundError(f"story not found: {bound_story}")
            mgmt.save_story(
                story.model_copy(
                    update={
                        "children": list(story.children) + [task_id],
                        "updated_at": utcnow(),
                    }
                )
            )
        mgmt.save_task(task)
        result = task.to_dict()
        result["story_id"] = bound_story
        return result

    def list_backlog(self, project_id: str) -> dict[str, Any] | None:
        """GET /backlog — 全量分组 (epics/features/stories/tasks; 失败安全空)。"""
        mgmt = self._management_store(project_id)
        if mgmt is None:
            return None
        return {
            "project_id": project_id,
            "epics": [e.to_dict() for e in mgmt.list_epics()],
            "features": [f.to_dict() for f in mgmt.list_features()],
            "stories": [s.to_dict() for s in mgmt.list_stories()],
            "tasks": [t.to_dict() for t in mgmt.list_tasks()],
        }

    def get_task(self, project_id: str, task_id: str) -> dict[str, Any] | None:
        """GET /backlog/task/{id} — Task 详情 (不存在 → BacklogNotFoundError)。"""
        mgmt = self._management_store(project_id)
        if mgmt is None:
            return None
        task = mgmt.get_task(task_id)
        if task is None:
            raise BacklogNotFoundError(f"task not found: {task_id}")
        return task.to_dict()

    def update_task(
        self,
        project_id: str,
        task_id: str,
        *,
        title: Any = None,
        description: Any = None,
        priority: Any = None,
        status: Any = None,
        assignee: Any = None,
        dependency: Any = None,
    ) -> dict[str, Any] | None:
        """PATCH /backlog/task/{id} — 字段更新 + 状态机转换 + 依赖校验。

        错误语义: 空 title → ValueError (400); priority/status 非法值 →
        ValueError (400); dependency 自引用/环 → ValueError (400); 依赖未
        满足 (目标态 ∈ {READY, IN_PROGRESS} 且依赖非 DONE) → ValueError
        (400); 状态机非法转换 → BacklogStateError (409); 任务不存在 →
        BacklogNotFoundError (404)。
        """
        mgmt = self._management_store(project_id)
        if mgmt is None:
            return None
        task = mgmt.get_task(task_id)
        if task is None:
            raise BacklogNotFoundError(f"task not found: {task_id}")
        self._mount_org()
        from org.management import (
            TASK_TRANSITIONS,
            TaskPriority,
            TaskStatus,
            transition_task,
            validate_dependency,
        )
        from org.models import utcnow

        updates: dict[str, Any] = {}
        if title is not None:
            cleaned = str(title).strip()
            if not cleaned:
                raise ValueError("title is required (空标题不落库)")
            updates["title"] = cleaned
        if description is not None:
            updates["description"] = str(description)
        if priority is not None:
            updates["priority"] = TaskPriority.parse(priority)  # 非法 → 400
        if assignee is not None:
            updates["assignee"] = str(assignee)
        if dependency is not None:
            updates["dependency"] = validate_dependency(
                dependency,
                task_id,
                known_dependencies=self._task_dependency_map(mgmt),
            )
        updated = task.model_copy(update=updates)
        if status is not None:
            target = TaskStatus.parse(status)  # 非法 status → ValueError → 400
            if target not in TASK_TRANSITIONS[updated.status]:
                raise BacklogStateError(
                    f"illegal task transition: {updated.status.value} -> "
                    f"{target.value} (allowed: "
                    f"{[s.value for s in TASK_TRANSITIONS[updated.status]]})"
                )
            try:
                updated = transition_task(
                    updated,
                    target,
                    actor="console",
                    dependency_status=self._task_status_map(mgmt),
                )
            except ValueError as exc:
                raise ValueError(str(exc)) from exc  # 依赖未满足 → 400
        else:
            updated = updated.model_copy(update={"updated_at": utcnow()})
        mgmt.save_task(updated)
        return updated.to_dict()

    def delete_task(self, project_id: str, task_id: str) -> dict[str, Any] | None:
        """DELETE /backlog/task/{id} — 删除 Task (引用可留: sprint/story 引用
        不清理 — 引用非包含语义; 不存在 → BacklogNotFoundError)。"""
        mgmt = self._management_store(project_id)
        if mgmt is None:
            return None
        if not mgmt.delete_task(task_id):
            raise BacklogNotFoundError(f"task not found: {task_id}")
        return {"deleted": True, "task_id": task_id}

    # --------------------------------- S10-010 Task 4: Sprint/Milestone/Roadmap API
    # 执行窗口与路线 (AF-PRD-v1.md 4.4/4.5 + project-management-system.md §五/§十):
    # Sprint/Milestone 引用 Task (非包含 — 引用不影响 Task 本身); Roadmap 引用
    # Milestone; Sprint 状态受控 (planning→active→completed, org SPRINT_TRANSITIONS);
    # Planning 端点只返回建议 (sort_tasks 纯函数排序), 不实际调度 (S10-011)。
    # 目录信源: management/sprint/{id}.json + milestone.json + roadmap.md。
    # 错误语义: 项目不存在/缺 store → None (404); Sprint/Milestone 不存在 →
    # BacklogNotFoundError (404); 参数非法/空 name/task_ref 引用不存在 Task →
    # ValueError (400); Sprint 状态机非法转换 → BacklogStateError (409)。

    @staticmethod
    def _norm_task_refs(mgmt: Any, task_refs: Any) -> list[str]:
        """task_refs 规范化 + 存在性校验 (引用非包含 — 只记 id)。

        元素必须为非空 str; 引用不存在的 Task → ValueError (HTTP 400, 引用
        校验属输入错误); 去重保序返回新列表。
        """
        refs: list[str] = []
        for ref in _norm_any_list(task_refs):
            ref_id = str(ref).strip()
            if not ref_id:
                raise ValueError("invalid task_ref: empty reference (expected task id)")
            if mgmt.get_task(ref_id) is None:
                raise ValueError(f"task not found: {ref_id} (task_refs 引用不存在 Task)")
            if ref_id not in refs:
                refs.append(ref_id)
        return refs

    # ----------------------------------------------------------------- Sprint
    def create_sprint(
        self,
        project_id: str,
        *,
        name: str,
        goal: str = "",
        start_date: str = "",
        end_date: str = "",
        task_refs: Any = None,
    ) -> dict[str, Any] | None:
        """POST /sprints — 创建 Sprint 执行窗口 (默认 planning; 引用 Task)。"""
        mgmt = self._management_store(project_id)
        if mgmt is None:
            return None
        cleaned = str(name or "").strip()
        if not cleaned:
            raise ValueError("name is required (空名字不创建)")
        refs = self._norm_task_refs(mgmt, task_refs)
        self._mount_org()
        from org.management import Sprint
        from org.models import new_id

        sprint = Sprint(
            id=new_id("SPRINT"),
            name=cleaned,
            goal=str(goal or "").strip(),
            start_date=str(start_date or "").strip(),
            end_date=str(end_date or "").strip(),
            task_refs=refs,
        )
        mgmt.save_sprint(sprint)
        return sprint.to_dict()

    def list_sprints(self, project_id: str) -> dict[str, Any] | None:
        """GET /sprints — Sprint 列表 (失败安全空态)。"""
        mgmt = self._management_store(project_id)
        if mgmt is None:
            return None
        return {
            "project_id": project_id,
            "sprints": [s.to_dict() for s in mgmt.list_sprints()],
        }

    def get_sprint(self, project_id: str, sprint_id: str) -> dict[str, Any] | None:
        """GET /sprints/{id} — Sprint 详情 (不存在 → BacklogNotFoundError)。"""
        mgmt = self._management_store(project_id)
        if mgmt is None:
            return None
        sprint = mgmt.get_sprint(sprint_id)
        if sprint is None:
            raise BacklogNotFoundError(f"sprint not found: {sprint_id}")
        return sprint.to_dict()

    def update_sprint(
        self,
        project_id: str,
        sprint_id: str,
        *,
        goal: Any = None,
        planning: Any = None,
        task_refs: Any = None,
        start_date: Any = None,
        end_date: Any = None,
        status: Any = None,
        daily_progress: Any = None,
        review: Any = None,
    ) -> dict[str, Any] | None:
        """PATCH /sprints/{id} — 字段更新 + 受控状态转换 + task_refs 校验。

        task_refs 引用不存在 Task → ValueError (400); status 非法值 →
        ValueError (400); 状态机非法转换 → BacklogStateError (409)。
        """
        mgmt = self._management_store(project_id)
        if mgmt is None:
            return None
        sprint = mgmt.get_sprint(sprint_id)
        if sprint is None:
            raise BacklogNotFoundError(f"sprint not found: {sprint_id}")
        self._mount_org()
        from org.management import SprintStatus, transition_sprint
        from org.models import utcnow

        updates: dict[str, Any] = {}
        if goal is not None:
            updates["goal"] = str(goal)
        if planning is not None:
            updates["planning"] = str(planning)
        if task_refs is not None:
            updates["task_refs"] = self._norm_task_refs(mgmt, task_refs)
        if start_date is not None:
            updates["start_date"] = str(start_date)
        if end_date is not None:
            updates["end_date"] = str(end_date)
        if daily_progress is not None:
            items = _norm_any_list(daily_progress)
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError(
                        "invalid daily_progress entry (expected object with day/note)"
                    )
            updates["daily_progress"] = [dict(item) for item in items]
        if review is not None:
            updates["review"] = str(review)
        updated = sprint.model_copy(update=updates)
        if status is not None:
            target = SprintStatus.parse(status)  # 非法值 → ValueError → 400
            try:
                updated = transition_sprint(updated, target)
            except ValueError as exc:
                raise BacklogStateError(str(exc)) from exc  # 非法转换 → 409
        else:
            updated = updated.model_copy(update={"updated_at": utcnow()})
        mgmt.save_sprint(updated)
        return updated.to_dict()

    def delete_sprint(self, project_id: str, sprint_id: str) -> dict[str, Any] | None:
        """DELETE /sprints/{id} — 删除 Sprint (Task 保留 — 引用非包含)。"""
        mgmt = self._management_store(project_id)
        if mgmt is None:
            return None
        if not mgmt.delete_sprint(sprint_id):
            raise BacklogNotFoundError(f"sprint not found: {sprint_id}")
        return {"deleted": True, "sprint_id": sprint_id}

    def plan_sprint(
        self,
        project_id: str,
        sprint_id: str,
        *,
        goal: str = "",
    ) -> dict[str, Any] | None:
        """POST /sprints/{id}/plan — Planning 预留端点 (S10-011 才实际调度)。

        只返回可执行任务建议: 候选池 = sprint.task_refs (非空) 否则全量
        Backlog Task; 用 org.management.sort_tasks 纯函数排序 (依赖满足组
        优先, 组内按 priority P0 最前), 不执行任何调度/落库。
        """
        mgmt = self._management_store(project_id)
        if mgmt is None:
            return None
        sprint = mgmt.get_sprint(sprint_id)
        if sprint is None:
            raise BacklogNotFoundError(f"sprint not found: {sprint_id}")
        self._mount_org()
        from org.management import TaskStatus, sort_tasks

        tasks = mgmt.list_tasks()
        if sprint.task_refs:
            by_id = {t.id: t for t in tasks}
            tasks = [by_id[r] for r in sprint.task_refs if r in by_id]
        dependency_status = {t.id: t.status for t in tasks}
        ordered = sort_tasks(tasks, dependency_status=dependency_status)
        suggestions = [
            {
                "id": t.id,
                "title": t.title,
                "priority": t.priority.value,
                "status": t.status.value,
                "dependency_satisfied": all(
                    dependency_status.get(dep) == TaskStatus.DONE
                    for dep in t.dependency
                ),
            }
            for t in ordered
        ]
        return {
            "sprint_id": sprint_id,
            "goal": str(goal or "").strip(),
            "suggestions": suggestions,
        }

    # -------------------------------------------------------------- Milestone
    def create_milestone(
        self,
        project_id: str,
        *,
        name: str,
        description: str = "",
        target_date: str = "",
        task_refs: Any = None,
    ) -> dict[str, Any] | None:
        """POST /milestones — 创建 Milestone (默认 planned; 引用 Task)。"""
        mgmt = self._management_store(project_id)
        if mgmt is None:
            return None
        cleaned = str(name or "").strip()
        if not cleaned:
            raise ValueError("name is required (空名字不创建)")
        refs = self._norm_task_refs(mgmt, task_refs)
        self._mount_org()
        from org.management import Milestone
        from org.models import new_id

        milestone = Milestone(
            id=new_id("MS"),
            name=cleaned,
            description=str(description or "").strip(),
            target_date=str(target_date or "").strip(),
            task_refs=refs,
        )
        mgmt.save_milestone(milestone)
        return milestone.to_dict()

    def list_milestones(self, project_id: str) -> dict[str, Any] | None:
        """GET /milestones — Milestone 列表 (失败安全空态)。"""
        mgmt = self._management_store(project_id)
        if mgmt is None:
            return None
        return {
            "project_id": project_id,
            "milestones": [m.to_dict() for m in mgmt.list_milestones()],
        }

    def get_milestone(
        self, project_id: str, milestone_id: str
    ) -> dict[str, Any] | None:
        """GET /milestones/{id} — Milestone 详情 (不存在 → BacklogNotFoundError)。"""
        mgmt = self._management_store(project_id)
        if mgmt is None:
            return None
        milestone = mgmt.get_milestone(milestone_id)
        if milestone is None:
            raise BacklogNotFoundError(f"milestone not found: {milestone_id}")
        return milestone.to_dict()

    def update_milestone(
        self,
        project_id: str,
        milestone_id: str,
        *,
        name: Any = None,
        description: Any = None,
        target_date: Any = None,
        status: Any = None,
        task_refs: Any = None,
    ) -> dict[str, Any] | None:
        """PATCH /milestones/{id} — 字段更新 (status 自由文本宽容, 无状态机)。"""
        mgmt = self._management_store(project_id)
        if mgmt is None:
            return None
        milestone = mgmt.get_milestone(milestone_id)
        if milestone is None:
            raise BacklogNotFoundError(f"milestone not found: {milestone_id}")
        self._mount_org()
        from org.models import utcnow

        updates: dict[str, Any] = {}
        if name is not None:
            cleaned = str(name).strip()
            if not cleaned:
                raise ValueError("name is required (空名字不落库)")
            updates["name"] = cleaned
        if description is not None:
            updates["description"] = str(description)
        if target_date is not None:
            updates["target_date"] = str(target_date)
        if status is not None:
            updates["status"] = str(status)
        if task_refs is not None:
            updates["task_refs"] = self._norm_task_refs(mgmt, task_refs)
        updated = milestone.model_copy(
            update=updates or {"updated_at": utcnow()}
        ).model_copy(update={"updated_at": utcnow()})
        mgmt.save_milestone(updated)
        return updated.to_dict()

    def delete_milestone(
        self, project_id: str, milestone_id: str
    ) -> dict[str, Any] | None:
        """DELETE /milestones/{id} — 删除 Milestone (Roadmap 引用可留)。"""
        mgmt = self._management_store(project_id)
        if mgmt is None:
            return None
        if not mgmt.delete_milestone(milestone_id):
            raise BacklogNotFoundError(f"milestone not found: {milestone_id}")
        return {"deleted": True, "milestone_id": milestone_id}

    # ---------------------------------------------------------------- Roadmap
    def get_roadmap(self, project_id: str) -> dict[str, Any] | None:
        """GET /roadmap — 路线 (每项目单例; milestone_refs 引用 Milestone)。"""
        mgmt = self._management_store(project_id)
        if mgmt is None:
            return None
        roadmap = mgmt.get_roadmap()
        result = roadmap.to_dict()
        result["project_id"] = project_id
        return result

    def add_roadmap_milestone_ref(
        self, project_id: str, milestone_id: str
    ) -> dict[str, Any] | None:
        """POST /roadmap/milestone-ref — 追加 Milestone 引用 (去重幂等)。

        milestone 不存在 → ValueError (400, 同 task_ref 引用校验语义)。
        """
        mgmt = self._management_store(project_id)
        if mgmt is None:
            return None
        ref_id = str(milestone_id or "").strip()
        if not ref_id:
            raise ValueError("milestone_id is required (空引用不追加)")
        if mgmt.get_milestone(ref_id) is None:
            raise ValueError(f"milestone not found: {ref_id}")
        self._mount_org()
        from org.models import utcnow

        roadmap = mgmt.get_roadmap()
        refs = list(roadmap.milestone_refs)
        if ref_id not in refs:
            refs.append(ref_id)
        roadmap = roadmap.model_copy(
            update={"milestone_refs": refs, "updated_at": utcnow()}
        )
        mgmt.save_roadmap(roadmap)
        result = roadmap.to_dict()
        result["project_id"] = project_id
        return result


__all__ = ["ConsoleService", "DEFAULT_RECENT_LIMIT"]
