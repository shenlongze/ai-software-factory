"""factory-console/models.py — Human Console 领域模型 (Pydantic v2)。

设计依据:
- phase11a-status.md: Console = Human Layer 产品入口 — 统一只读 API (为未来
  Web UI 11B 准备), Core → Extension → Console 分层。
- 只读铁律 (phase11a-status.md §禁止 + phase10a-plan.md §Q1 边界铁律):
  Console 只读各域状态 (Event/Artifact/Decision/Recommendation/Experience/
  Approval/Provider), **零写操作** — 本模块全部模型是只读投影 (响应模型),
  不携带任何执行/修改指令 (不自动批准/不修改 Decision/权重, 替代 Human 的
  决策权永远在 Approval 状态机)。
- 模型风格参照 product/models.py + intelligence/models.py: to_dict() =
  model_dump(mode="json") 供 CLI --json/测试断言/未来 FastAPI 薄层共用;
  时间戳统一 UTC 字符串 (events.models.format_timestamp 格式, 字符串排序
  == 时间排序)。
- 本模块只 import events.models (公共接口) — Removal Isolation: 删除
  factory-console/ 不影响 Factory (Core 零感知); 反向删除 product/ 等 Core
  包也不影响本层 (纯 stdlib + pydantic + Core 公共接口, 同 intelligence
  模型层铁律)。

ConsoleDashboard 七域 (phase11a-status.md §范围):
1. active_projects    活跃项目 (ProjectSummary 列表)
2. pending_approvals  待人工审批 (ApprovalSummary 列表 — 人工闸门 9c)
3. running_agents     运行中 Agent (AgentSummary 列表)
4. recent_decisions   最近决策 (DecisionSummary 列表 — AI 推荐产物, 只读)
5. cost_summary       成本汇总 (CostSummary — Provider usage 估算计量)
6. experience_summary 经验汇总 (ExperienceSummaryModel — 六域统计)
7. activity           最近活动 (EventSummary 列表 — 事件审计流)

API 响应模型 (api/ 路由函数返回值, 未来挂 FastAPI 薄层):
GET /projects → ProjectSummary; GET /projects/{id}/lifecycle → LifecycleSummary;
GET /approvals → ApprovalSummary; GET /decisions/{id} → DecisionSummary;
GET /recommendations → RecommendationSummary; GET /experience → ExperienceSummary;
GET /providers → ProviderSummary。
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, field_validator


def _now_str() -> str:
    """统一 UTC 时间戳 (与 Event 存储格式一致, 字符串排序 == 时间排序)。"""
    from events.models import format_timestamp
    from datetime import datetime, timezone

    return format_timestamp(datetime.now(timezone.utc))


def _coerce_str_list(v: Any) -> list[str]:
    """字符串/可迭代 → 去空串列表 (capability 等清单字段共用, 同 intelligence 模式)。"""
    if v is None:
        return []
    if isinstance(v, str):
        return [s.strip() for s in v.split(",") if s.strip()]
    return [str(s).strip() for s in v if str(s).strip()]


def _coerce_str_map(v: Any) -> dict[str, float]:
    """dict 字段归一 (因素/成本分项等; None → {}; 值转 float)。"""
    if v is None:
        return {}
    out: dict[str, float] = {}
    for key, value in v.items():
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            continue  # 非数值分项忽略 (只读投影宽容)
    return out


class ProjectSummary(BaseModel):
    """GET /projects — 项目只读投影: id/name/lifecycle stage/status/last activity。

    lifecycle_stage: 该项目关联生命周期的当前阶段名 (无生命周期 → None);
    pending_approvals: 该项目维度待审批数; tasks: 任务状态计数 (按五状态);
    last_activity: 最近活动时间 (项目维度事件最新时间戳, 无 → None)。

    S9-002 扩展 (org 聚合, 全部带默认值 — 既有消费方零破坏): workflow_id/
    workflow_name/workflow_status: 当前 (最近) 组织级 Workflow 运行;
    current_stage/current_stage_status: 当前阶段名与状态; progress: 阶段链
    完成度 (0-1, completed stages / total stages); stage_counts: 按 Stage
    状态计数 (pending/ready/running/blocked/completed/failed)。
    """

    id: str
    name: str = ""
    starred: bool = False                # Founder 2026-08-26: 收藏/关注
    archived: bool = False               # Founder 2026-08-26: 归档 (软归档可恢复)
    description: str = ""
    language: str = ""
    repository: str = ""
    tech_stack: list[str] = Field(default_factory=list)
    status: str = "active"
    lifecycle_stage: str | None = None
    lifecycle_status: str | None = None
    pending_approvals: int = Field(default=0, ge=0)
    tasks: dict[str, int] = Field(default_factory=dict)
    last_activity: str | None = None
    # S9-002: org 聚合 (workflow/stage/progress)
    workflow_id: str | None = None
    workflow_name: str | None = None
    workflow_status: str | None = None
    current_stage: str | None = None
    current_stage_status: str | None = None
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    stage_counts: dict[str, int] = Field(default_factory=dict)
    # v1.1.272: 我的公司列表 — 创建/更新时间 + 各阶段完成度 + 未完成计划
    created_at: str | None = None
    updated_at: str | None = None
    stage_progress: dict[str, dict[str, Any]] = Field(default_factory=dict)
    pending_plan_count: int = Field(default=0, ge=0)

    @field_validator("tech_stack", mode="before")
    @classmethod
    def _coerce_tech_stack(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)

    @field_validator("tasks", "stage_counts", mode="before")
    @classmethod
    def _coerce_int_maps(cls, v: Any) -> dict[str, int]:
        if v is None:
            return {}
        return {str(k): int(val) for k, val in v.items()}

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ProjectCreatedSummary(BaseModel):
    """POST /projects — 创建结果投影 (S10-006.5: 用户第一公里创建闭环)。

    {project_id, name, idea, status}: 前端创建成功 → 跳转
    #/workspace?project={project_id} 的数据源; idea 原样回显 (诚实 —
    不伪造 AI 理解), status 恒 "idea" (org Project 生命周期起点)。

    S10-007 阶段三增强: name = 用户确认的名称 (suggest 卡片确认后显式传),
    规则 slug 仅兜底 (无 name → extract_project_name)。
    """

    project_id: str
    name: str
    idea: str
    status: str = "idea"

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ProjectDraftSummary(BaseModel):
    """POST /projects — 草稿创建结果投影 (S10-009 Task 4: 无 name → unnamed draft)。

    {project_id, name, idea, status, lifecycle, draft}: 用户输入想法 (未确认
    名称) → 创建 DRAFT (lifecycle=discovery, draft=true, name=unnamed-project-
    {ts}) — Product Discovery Session 起点。与 ProjectCreatedSummary 形状
    区分 (draft 响应带 lifecycle/draft 字段; 旧 {idea, name} 兼容路径返回
    ProjectCreatedSummary, 零破坏)。status = lifecycle 同值 (前端旧字段兼容)。
    """

    project_id: str
    name: str
    idea: str
    status: str = "discovery"
    lifecycle: str = "discovery"
    draft: bool = True

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class DiscoveryAnswerSummary(BaseModel):
    """POST /projects/{id}/discovery/answer — 问答持久化结果投影 (S10-009 Task 4)。

    {project_id, question, answer, count}: 追加 discovery/conversation.json
    后回显 (count = 该会话累计问答条数, 前端可据此判断进度)。
    """

    project_id: str
    question: str
    answer: str
    count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class DiscoveryCompleteSummary(BaseModel):
    """POST /projects/{id}/discovery/complete — Discovery 完成结果投影 (S10-009 Task 4)。

    {project_id, name, lifecycle, product_definition_ref}: Discovery 沟通
    完成 → product-definition.md 落库 + lifecycle discovery → product_defined
    (product_definition_ref = 空间内相对路径, 供后续阶段消费)。
    """

    project_id: str
    name: str
    lifecycle: str = "product_defined"
    product_definition_ref: str = "discovery/product-definition.md"

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ConfirmProjectSummary(BaseModel):
    """POST /projects/{id}/confirm — Confirm+Rename 事务结果投影 (S10-009 Task 5)。

    {project_id, name, slug, lifecycle: confirmed}: 用户确认正式名称 →
    目录 rename (unnamed-project-xxx → {slug}/) + project.json/索引/org
    镜像引用全更新。slug = 新目录名 (前端跳转 workspace 数据源); id 稳定
    (rename 不变)。幂等: 已 confirmed 同 name 再次 confirm → 原样返回。
    """

    project_id: str
    name: str
    slug: str
    lifecycle: str = "confirmed"

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class IdeaSuggestion(BaseModel):
    """POST /projects/suggest — AI 想法理解卡片 (S10-007 阶段三增强)。

    {idea, suggested_name, slug, summary, questions, ai_generated}: 用户输入
    想法 → AI 提议名称/一句话理解/澄清问题 → 前端确认卡 (名称可编辑) →
    确认后 POST /projects {idea, name} 创建。

    - suggested_name: 有意义的中文名 (如 "记账小助手"; LLM 提议, 规则 fallback
      提炼核心词)
    - slug: URL 安全标识 (LLM 提议或规则生成; 创建时 name 显式优先, 规则仅兜底)
    - summary: 一句话理解 (AI 对想法的理解)
    - questions: 1-3 个澄清问题 (LLM 可用时); 规则 fallback → [] (诚实:
      规则无法提问, 不伪造)
    - ai_generated: True = 真实 LLM 理解; False = 诚实 fallback (前端标注
      "快速模式", 仍可确认创建 — 规则名仅兜底, 不冒充 AI)
    """

    idea: str
    suggested_name: str = ""
    slug: str = ""
    summary: str = ""
    questions: list[str] = Field(default_factory=list)
    ai_generated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ProjectUpdatedSummary(BaseModel):
    """PATCH /projects/{id} — 更新结果投影 (S10-006.5 项目管理: 重命名/改 idea)。

    {project_id, name, idea, status}: 更新后 org Project 摘要 (前端重命名
    Modal 成功后刷新列表的数据源; idea = org Project.goal 原样回显, 诚实
    不伪造)。status 为 org Project.lifecycle 当前值 (更新不改生命周期)。
    """

    project_id: str
    name: str
    idea: str
    status: str = "idea"

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class LifecycleSummary(BaseModel):
    """GET /projects/{id}/lifecycle — 生命周期只读快照。

    current_stage: 当前阶段运行记录 (status/completed 后为 None, 同 9d
    engine.status 口径); completed_stages: 已完成的阶段名列表 (按序);
    pending_approval: 待审批请求摘要 (ApprovalSummary 投影, 无 → None);
    next_actions: 下一步动作清单 (引擎 status() 输出投影)。
    """

    project_id: str
    lifecycle_id: str | None = None
    idea_id: str | None = None
    template_name: str = ""
    status: str = ""
    current_stage: dict[str, Any] | None = None
    completed_stages: list[str] = Field(default_factory=list)
    pending_approval: "ApprovalSummary | None" = None
    next_actions: list[str] = Field(default_factory=list)

    @field_validator("completed_stages", "next_actions", mode="before")
    @classmethod
    def _coerce_str_lists(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ApprovalSummary(BaseModel):
    """GET /approvals — 审批请求只读投影 (9c 状态机, Console 只读不决定)。

    artifact_type: 申请 Artifact 类型 (prd/ui/architecture/...); gate: 审批门 id;
    confidence: Artifact 置信度 (0-1, 审核优先级数据接口); risk: 风险等级
    (low/medium/high — 决策链绑定时的风险信号, 无 → None); evidence: 决策依据
    摘要 (approval 决策链 evidence 引用, 无 → []); status: 9c 状态机
    (pending/approved/rejected/changes_requested/delegated)。
    """

    id: str
    artifact_id: str
    artifact_type: str = ""
    gate: str = ""
    status: str = "pending"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    risk: str | None = None
    evidence: list[str] = Field(default_factory=list)
    idea_id: str | None = None
    by: str = "human"
    comment: str | None = None
    requested_at: str | None = None
    artifact_version: int | None = None

    @field_validator("evidence", mode="before")
    @classmethod
    def _coerce_evidence(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


# ------------------------------------------------------------------ S9-002 org 投影模型


class ApprovalGateSummary(BaseModel):
    """org ApprovalGate 投影 (S9-001 审批门; Console 决定操作对象)。

    与 org/approval.py ApprovalGate 字段一一对应 (宽容投影: 时间为 UTC
    字符串, 无 → None); workflow_id/stage_id 冗余 scoping 原样保留,
    前端据此展示上下文 (门绑定哪个阶段/工作流)。
    """

    id: str
    stage_id: str = ""
    workflow_id: str = ""
    project_id: str = ""
    status: str = "pending"
    reviewer: str = ""
    comment: str = ""
    requested_at: str | None = None
    approved_at: str | None = None
    rejected_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ApprovalDecisionSummary(BaseModel):
    """POST /approvals/{id}/approve|reject — 决定结果投影 (S9-002)。

    action: approve/reject; gate: 决定后门快照 (终态 APPROVED/REJECTED,
    决定不可撤销 — 审计铁律); workflow_id/workflow_status: 决定后工作流
    状态 (approve → PAUSED→ACTIVE 恢复; reject → FAILED 停止)。
    """

    action: str
    gate: ApprovalGateSummary
    workflow_id: str = ""
    workflow_status: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ArtifactSummary(BaseModel):
    """GET /artifacts — org Artifact 只读投影 (S9-002 六类产物链)。

    type: idea|product|ux_ui|prd|design|code|test|bug_report|release;
    status: 生命周期 (created/generated/validated/consumed/archived/invalid);
    producer_role: 生产者角色 (exec 注册表); workflow_id 经 stage 反查
    (Artifact 模型无 workflow 字段 — stage 冗余 scoping)。
    """

    id: str
    stage_id: str = ""
    workflow_id: str = ""
    project_id: str = ""
    type: str = ""
    ref: str = ""
    version: str = "1"
    status: str = "created"
    producer_role: str = ""
    producer_agent: str = ""
    location: str = ""
    created_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ArtifactDetail(ArtifactSummary):
    """GET /artifacts/{id} — 单产物详情 (S9-003 Review 数据源)。

    在 ArtifactSummary 基础上扩展 Review 视图字段 (全部带默认值 — 既有
    消费方零破坏):
    - metadata: 类型契约校验载荷 (product 6/7 节 / ux_ui 7 节等 — Review
      页按节渲染的原始数据)
    - review: 绑定本产物的审批门 (需求确认门 product / 设计确认门 ux_ui —
      gate.status + gate.comment, approve/reject 决定状态; 无门 → None)
    """

    metadata: dict[str, Any] = Field(default_factory=dict)
    review: "ApprovalGateSummary | None" = None

    @field_validator("metadata", mode="before")
    @classmethod
    def _metadata_none(cls, v: Any) -> Any:
        return v if v is not None else {}


class ArtifactContent(BaseModel):
    """GET /artifacts/{id}/content — 产物渲染内容 (S10-005 Artifact Center)。

    artifact 的原始内容 (location 指向文件的文本 — Code diff 兜底 / Release
    下载源); 文件缺失/不可读/越界 → content None (失败安全 — metadata 已在
    ArtifactDetail, 本端点只补渲染内容, 缺数据不拖垮查看器)。
    """

    artifact_id: str
    type: str = ""
    location: str = ""
    content: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class StageSummary(BaseModel):
    """GET /workflows/{id} — 阶段链节点投影 (status/role/artifact)。

    artifact: 该阶段输出产物摘要 (无 → None); pending_approval: 绑定本
    阶段的审批门 (approval_required stage COMPLETED 后创建, PENDING →
    workflow PAUSED; 无 → None)。input/output_artifacts: 依赖与产出索引
    (S7-003 DAG 语义, 原样投影)。
    """

    id: str
    workflow_id: str = ""
    role_id: str = ""
    name: str = ""
    order: int = 1
    status: str = "pending"
    depends_on: list[str] = Field(default_factory=list)
    input_artifacts: list[str] = Field(default_factory=list)
    output_artifacts: list[str] = Field(default_factory=list)
    approval_required: bool = False
    artifact: ArtifactSummary | None = None
    pending_approval: ApprovalGateSummary | None = None

    @field_validator("depends_on", "input_artifacts", "output_artifacts", mode="before")
    @classmethod
    def _coerce_str_lists(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class WorkflowSummary(BaseModel):
    """GET /workflows — 组织级 Workflow 运行摘要 (S9-002)。

    progress: 阶段链完成度 (completed / total); current_stage: 当前阶段名
    (无 → None); current_stage_status: 当前阶段状态 (paused 挂起时可见
    PENDING 门阶段为 completed — 门后 workflow PAUSED, current_stage 取
    第一个未 completed 阶段)。
    """

    id: str
    project_id: str = ""
    project_name: str = ""
    name: str = ""
    status: str = "draft"
    stage_count: int = Field(default=0, ge=0)
    completed_count: int = Field(default=0, ge=0)
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    current_stage: str | None = None
    current_stage_status: str | None = None
    failed_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class WorkflowDetail(BaseModel):
    """GET /workflows/{id} — 8 阶段链全视图 (S9-002)。

    stages: 阶段链 (按 order 升序; 每节点 status/role/artifact/pending_
    approval — Workflow View 页直接消费); template: 规范 8 阶段链
    (Idea→PM→Product→UX/UI→Architecture→Development→Test→Release —
    前端渲染占位/标签映射用); pending_approvals: 本 workflow 全部审批门
    (按 requested_at 升序, 含已决定历史 — 审计视图)。
    """

    id: str
    project_id: str = ""
    project_name: str = ""
    name: str = ""
    status: str = "draft"
    failed_reason: str = ""
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    stages: list[StageSummary] = Field(default_factory=list)
    pending_approvals: list[ApprovalGateSummary] = Field(default_factory=list)
    template: list[str] = Field(default_factory=list)
    # S10-002: mock fallback 标记 (数据缺失 → mock 数据, 明确标注不冒充真实)
    is_mock: bool = False

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class StageRunSummary(BaseModel):
    """GET /workflows/{id}/stages — 阶段运行明细 (S10-002 Runtime API)。

    Task 面板数据源: 每阶段状态/agent/artifacts/duration/cost 一次装配。

    agent_id: 执行 Agent (org 无独立 Agent 实体 — 阶段由 role_id 对应角色
    执行, 诚实投影: agent_id = role_id); artifacts: 输出产物摘要 (无 → []);
    duration_s: 从事件流推导 (org.workflow.stage_started → stage_completed
    时间戳差, 缺任一端 → None — 不臆造); cost_usd: org 未跟踪成本 → None
    (诚实 null, 前端显示 \"—\"; 仅 mock 数据带示例值)。
    """

    id: str
    workflow_id: str = ""
    role_id: str = ""
    name: str = ""
    order: int = 1
    status: str = "pending"
    agent_id: str | None = None
    duration_s: float | None = None
    cost_usd: float | None = None
    started_at: str | None = None
    completed_at: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    input_artifacts: list[str] = Field(default_factory=list)
    output_artifacts: list[str] = Field(default_factory=list)
    artifacts: list[ArtifactSummary] = Field(default_factory=list)

    @field_validator(
        "depends_on", "input_artifacts", "output_artifacts", "artifacts", mode="before"
    )
    @classmethod
    def _coerce_lists(cls, v: Any) -> list[Any]:
        return v if v is not None else []

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class TimelineEventSummary(BaseModel):
    """GET /projects/{id}/timeline — Timeline 事件节点 (S10-002 Runtime API)。

    从事件流 (events.db) 按 project_id 聚合映射 (Agent Timeline 数据源);
    与 SSE /api/events/stream 同源同映射 — Timeline 是历史快照, SSE 是增量。

    type: user|stage|artifact|review|error (api-data-model §1 TimelineEvent);
    event_type: 原始事件类型 (org.workflow.stage_completed 等 — 可追溯锚点);
    stage_id/agent_id/artifact_id/gate_id: 从 payload 提取的关联维度
    (无 → None); message: 人类可读摘要; status: 事件 result/stage 状态。
    """

    id: str
    seq: int = 0
    project_id: str = ""
    type: str = "stage"
    event_type: str = ""
    stage_id: str | None = None
    agent_id: str | None = None
    artifact_id: str | None = None
    gate_id: str | None = None
    message: str = ""
    status: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None

    @field_validator("payload", mode="before")
    @classmethod
    def _payload_none(cls, v: Any) -> Any:
        return v if v is not None else {}

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class RuntimeInstance(BaseModel):
    """S10-002 Runtime Instance 基础模型 (只建模型, 不实现 Browser/Terminal)。

    对应 workspace-architecture.md §4 (S10-004 调整版) 的 Runtime Instance
    数据模型 — 前端 Runtime Tab (S10-004) 与后端 Runtime 服务的共享契约。

    本 Sprint 只落模型 + SSE 事件契约 (runtime.created / runtime.status.changed),
    不实现实例创建/生命周期/截图 (Browser/Terminal 由 S10-004 实现, 该服务
    发射 org.runtime.* 事件 → SSE_EVENT_MAP 同映射)。

    type: browser|terminal (沙箱实例类型); status: starting|running|stopped|
    error (生命周期状态机); artifact_id: 绑定产物 (browser 预览 ux_ui/code/
    release 对应产物, 无 → None); url: browser 预览地址 / session: terminal
    会话标识 (按 type 二选一, 未就绪 → None); created_at: UTC 时间戳。
    """

    id: str
    project_id: str = ""
    type: Literal["browser", "terminal"] = "browser"
    status: Literal["starting", "running", "stopped", "error"] = "starting"
    artifact_id: str | None = None
    url: str | None = None
    session: str | None = None
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class RuntimeScreenshot(BaseModel):
    """S10-004 Runtime 截图记录 (截图反馈预留 — 只落记录, 不实现完整 Loop)。

    POST /runtimes/{id}/screenshot 的落库结果: 截图动作 → 生成一条截图
    记录 + artifact_id (预留产物引用)。完整 Feedback Loop (截图 → 意见 →
    Agent 修改) 由后续 Sprint 实现; 本模型只保证截图动作可审计/可追溯。

    id: shot-<hex>; instance_id: 所属 Runtime 实例; project_id: 项目;
    artifact_id: 截图产物引用 (预留, 后续渲染/反馈环节使用); created_at:
    UTC 时间戳。
    """

    id: str
    instance_id: str = ""
    project_id: str = ""
    artifact_id: str | None = None
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ReviewFeedback(BaseModel):
    """S10-006 审核反馈记录 (Feedback Loop 数据流 — Reject 意见落库)。

    对应 api-data-model.md §1 ReviewComment 的实践形态: 每次 Reject 决定
    除 gate.comment 落库 (S9-001 审计) 外, 另存一条结构化反馈记录, 供
    下一轮 Agent 重生成时作为输入 (reviewer/artifact_id/comment/round)。

    id: fb-<hex>; gate_id: 来源审批门 (Reject 决定); artifact_id: 被审
    产物 (重生成输入目标); reviewer: 决策人 (console); comment: 驳回意见
    (下轮重生成输入); round: 该产物第几轮反馈 (1 起, 按 artifact 递增);
    created_at: UTC 时间戳。
    """

    id: str
    gate_id: str = ""
    artifact_id: str = ""
    reviewer: str = ""
    comment: str = ""
    round: int = 1
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class DecisionSummary(BaseModel):
    """GET /decisions/{id} — 智能决策只读投影 (AI 推荐产物, ≠ Approval)。

    options: 选项快照 (id/name/score/factors/reasoning 摘要 — 引擎产物全链
    可追溯, 只读不修改); recommendation: 推荐选项 id (None = 未推荐);
    score: 推荐选项综合评分; reasoning: 推荐解释 (逐条为什么);
    evidence: 决策依据证据链 (lineage_ref 字符串列表, 可追溯);
    risk/risk_level/requires_approval: 风险量化 (9c ApprovalGate 复用信号);
    status: DecisionStatus (open/recommended/accepted/rejected — 人工决定回写
    由既有引擎负责, Console 只读)。
    """

    id: str
    decision_type: str = "general"
    subject_id: str = ""
    description: str = ""
    status: str = "open"
    options: list[dict[str, Any]] = Field(default_factory=list)
    recommendation: str | None = None
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reasoning: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    risk: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_level: str = "low"
    requires_approval: bool = False
    approval_request_id: str | None = None
    created_at: str | None = None

    @field_validator("options", mode="before")
    @classmethod
    def _coerce_options(cls, v: Any) -> list[dict[str, Any]]:
        if v is None:
            return []
        out: list[dict[str, Any]] = []
        for opt in v:
            if isinstance(opt, dict):
                item = dict(opt)
                item["factors"] = _coerce_str_map(item.get("factors"))
                out.append(item)
            else:
                out.append(dict(opt))  # type: ignore[arg-type]
        return out

    @field_validator("reasoning", "evidence", mode="before")
    @classmethod
    def _coerce_str_lists(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class RecommendationSummary(BaseModel):
    """GET /recommendations — 推荐产物只读投影 (只推荐不执行)。

    candidate: 推荐目标 (f"{target_type}:{target_id}" — provider/agent/skill/
    workflow 统一抽象); factors: 分项得分 (capability/performance/cost/
    experience); explanation: 逐条解释 (reasoning 文本); evidence: 依据证据链;
    confidence/risk: 量化不确定度。
    """

    id: str
    target_type: str = ""
    candidate: str = ""
    score: float = Field(ge=0.0, le=1.0)
    factors: dict[str, float] = Field(default_factory=dict)
    explanation: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    risk: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: str | None = None

    @field_validator("factors", mode="before")
    @classmethod
    def _coerce_factors(cls, v: Any) -> dict[str, float]:
        return _coerce_str_map(v)

    @field_validator("explanation", "evidence", mode="before")
    @classmethod
    def _coerce_str_lists(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ExperienceSummary(BaseModel):
    """GET /experience — 经验记录只读投影 (六域 provider/agent/skill/workflow/
    project/decision)。

    subject: 经验主体 (f"{subject_type}:{subject_id}"); result: success/failure
    (负样本 = 反事实记录); score/confidence: 表现分与可靠度; task_type/
    capability: 聚合过滤维度; freshness: 当前新鲜度 (0-1, 历史经验不永久有效)。
    """

    id: str
    domain: str = ""
    subject: str = ""
    result: str = "success"
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    freshness: float = Field(default=1.0, ge=0.0, le=1.0)
    task_type: str = ""
    capability: list[str] = Field(default_factory=list)
    created_at: str | None = None

    @field_validator("capability", mode="before")
    @classmethod
    def _coerce_capability(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ProviderSummary(BaseModel):
    """GET /providers — Provider 目录只读投影 (能力/成本/性能/经验)。

    capability: 能力标签 (capabilities 投影); cost/performance/experience:
    经验聚合维度打分 (来自 usage 统计 + experience 记录; 无数据 → None,
    不臆造); models: 可用模型; status: ACTIVE/DISABLED; usage_calls:
    usage 记录调用数 (估算计量)。
    """

    id: str
    name: str = ""
    type: str = "cloud"
    status: str = "ACTIVE"
    capabilities: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    version: str = "1.0.0"
    cost: float | None = Field(default=None, ge=0.0, le=1.0)
    performance: float | None = Field(default=None, ge=0.0, le=1.0)
    experience: float | None = Field(default=None, ge=0.0, le=1.0)
    usage_calls: int = Field(default=0, ge=0)

    @field_validator("capabilities", "models", mode="before")
    @classmethod
    def _coerce_str_lists(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class CostSummary(BaseModel):
    """Console Dashboard cost_summary — Provider usage 成本汇总 (估算计量)。

    total_cost: 估算成本累计 (USD, 非真实计费); calls: 调用数; success_rate:
    成功率; avg_cost: 单次平均成本; total_tokens: 全部 token 和; by_provider:
    按 Provider 分项 (provider_id → {calls, total_cost, success_rate})。
    """

    total_cost: float = Field(default=0.0, ge=0.0)
    calls: int = Field(default=0, ge=0)
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_cost: float = Field(default=0.0, ge=0.0)
    total_tokens: int = Field(default=0, ge=0)
    by_provider: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @field_validator("by_provider", mode="before")
    @classmethod
    def _coerce_by_provider(cls, v: Any) -> dict[str, dict[str, Any]]:
        if v is None:
            return {}
        return {str(k): dict(val) for k, val in v.items()}

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ExperienceSummaryModel(BaseModel):
    """Console Dashboard experience_summary — 经验汇总 (六域统计)。

    total: 记录总数; by_domain: 各域计数; success_rate: 总体成功率;
    avg_score: 平均表现分; avg_confidence: 平均可靠度。
    """

    total: int = Field(default=0, ge=0)
    by_domain: dict[str, int] = Field(default_factory=dict)
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_score: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("by_domain", mode="before")
    @classmethod
    def _coerce_by_domain(cls, v: Any) -> dict[str, int]:
        if v is None:
            return {}
        return {str(k): int(val) for k, val in v.items()}

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class AgentSummary(BaseModel):
    """Console Dashboard running_agents — Agent 运行投影 (只读状态)。

    id/name/role/skills: 身份与能力; status: AVAILABLE/WORKING/OFFLINE;
    current_task: 当前任务 id (Task.owner 引用, 不自动分配)。
    """

    id: str
    name: str = ""
    role: str = ""
    status: str = "AVAILABLE"
    skills: list[str] = Field(default_factory=list)
    current_task: str | None = None

    @field_validator("skills", mode="before")
    @classmethod
    def _coerce_skills(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class EventSummary(BaseModel):
    """Console Dashboard activity — 最近事件活动 (事件审计流只读投影)。

    type/timestamp/source/project_id/task_id/action/result: Event 语义列投影
    (append-only 审计, Console 只读不写)。
    """

    seq: int = Field(default=0, ge=0)
    type: str = ""
    timestamp: str = ""
    source: str = ""
    project_id: str | None = None
    task_id: str | None = None
    action: str | None = None
    result: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ConsoleDashboard(BaseModel):
    """Console Dashboard 七域汇总 (factory console dashboard / GET /dashboard)。

    只读聚合快照: 各域由 ConsoleService 从各 store 读接口装配, 本模型
    不携带任何执行/修改指令 (Human Layer 只读铁律)。空工厂 → 全空域,
    Console 永不因数据缺失失败 (失败安全, 同 dashboard/metrics 哲学)。
    """

    projects: list[ProjectSummary] = Field(default_factory=list)
    approvals: list[ApprovalSummary] = Field(default_factory=list)
    agents: list[AgentSummary] = Field(default_factory=list)
    decisions: list[DecisionSummary] = Field(default_factory=list)
    cost: CostSummary = Field(default_factory=CostSummary)
    experience: ExperienceSummaryModel = Field(default_factory=ExperienceSummaryModel)
    activity: list[EventSummary] = Field(default_factory=list)

    #: 七域字段名 (文档/CLI/事件 payload 共用; 键序即域序)。ClassVar —
    #: pydantic v2 会把带注解的类属性当 model field 处理 (类级访问被隐藏,
    #: 且会泄漏进 model_dump), ClassVar 保持常量语义。
    SECTIONS: ClassVar[tuple[str, ...]] = (
        "projects", "approvals", "agents", "decisions", "cost", "experience", "activity",
    )

    @field_validator("cost", mode="before")
    @classmethod
    def _coerce_cost(cls, v: Any) -> CostSummary:
        if v is None:
            return CostSummary()
        return v if isinstance(v, CostSummary) else CostSummary.model_validate(v)

    @field_validator("experience", mode="before")
    @classmethod
    def _coerce_experience(cls, v: Any) -> ExperienceSummaryModel:
        if v is None:
            return ExperienceSummaryModel()
        return v if isinstance(v, ExperienceSummaryModel) else ExperienceSummaryModel.model_validate(v)

    @property
    def active_projects(self) -> list[ProjectSummary]:
        """活跃项目 (七域 1): status == active 的项目投影。"""
        return [p for p in self.projects if p.status == "active"]

    @property
    def pending_approvals(self) -> list[ApprovalSummary]:
        """待人工审批 (七域 2): status == pending 的审批请求。"""
        return [a for a in self.approvals if a.status == "pending"]

    @property
    def running_agents(self) -> list[AgentSummary]:
        """运行中 Agent (七域 3): status == WORKING 的 Agent。"""
        return [a for a in self.agents if a.status == "WORKING"]

    @property
    def recent_decisions(self) -> list[DecisionSummary]:
        """最近决策 (七域 4): 全部决策投影 (service 侧已按最近排序截断)。"""
        return self.decisions

    @property
    def cost_summary(self) -> CostSummary:
        """成本汇总 (七域 5)。"""
        return self.cost

    @property
    def experience_summary(self) -> ExperienceSummaryModel:
        """经验汇总 (七域 6)。"""
        return self.experience

    @property
    def activity_summary(self) -> list[EventSummary]:
        """最近活动 (七域 7)。"""
        return self.activity

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


__all__ = [
    "AgentSummary",
    "ApprovalDecisionSummary",
    "ApprovalGateSummary",
    "ApprovalSummary",
    "ArtifactSummary",
    "ConsoleDashboard",
    "CostSummary",
    "DecisionSummary",
    "EventSummary",
    "ExperienceSummary",
    "ExperienceSummaryModel",
    "LifecycleSummary",
    "ProjectSummary",
    "ProjectCreatedSummary",
    "ProviderSummary",
    "RecommendationSummary",
    "ReviewFeedback",
    "RuntimeInstance",
    "RuntimeScreenshot",
    "StageRunSummary",
    "StageSummary",
    "TimelineEventSummary",
    "WorkflowDetail",
    "WorkflowSummary",
]
