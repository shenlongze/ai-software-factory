"""factory-core/product/lifecycle.py — Phase 9d 产品生命周期编排引擎。

设计依据:
- phase9d-status.md: Stage Registry (ProductStageRegistry, 多 lifecycle 类型) +
  Product Workflow Template (声明式 software_project) + ProductLifecycleEngine
  (start/advance/pause-resume/completed, 可扩展)。
- 冻结约束: Core 零修改 / Extension only / Event 唯一事实源 / Artifact lineage /
  Approval & Provider Intelligence 复用 / 禁止复制 Workflow Core。
- 分层 (业务生命周期 vs 任务执行):
  - ProductLifecycle (9d) = 业务生命周期编排: Idea→Research→PRD→Approval→UI→
    Approval→Architecture→Task 阶段链, 跟踪当前阶段/暂停恢复/决策链。
  - 9c ProductWorkflow = 审批门暂停/恢复骨架 (request_approval/decide 联动,
    本层经 ProductService 复用 — 不复制状态机)。
  - Core Workflow (tasks/workflows) = 任务执行: task 阶段经 TaskStore.create
    生成 Task (task.workflow 既有字段关联), 之后由 Core Workflow 执行 —
    本层不调 WorkflowEngine/不复制编排逻辑。
- 阶段类型分类 (StageKind): artifact_generation (产物存在性校验, 生成由 9b
  ProductGenerator 负责) / approval (复用 9c request_approval, 进入即暂停) /
  decision (校验前序决策链 + 产生决策产物) / task (task_plan + Task 生成)。
- 事件 (经 EventLogger): product.lifecycle.started / product.stage.entered /
  product.stage.completed / product.decision.created / product.lifecycle.completed
  (EventType 枚举扩展见 events/models.py; 辅助函数见 product/events.py)。
- 引擎依赖注入: store (ProductStore 持久化) + service (ProductService — 复用
  request_approval/decide/artifact 链; 缺省自装配) + task_store (TaskStore —
  task 阶段生成 Task, 缺省 None 时 task 阶段响亮报错) + logger (事件审计)。
- 无 Database/Web API (纯本地 JSON + 事件审计, 同 9a-9c)。

Decision Artifact 链 (Product → Architecture → Task Plan):
- approval(prd) 通过 → 9c decide 已产 product_decision Artifact; 本层记录
  DecisionArtifact(type=product, decision_id=ApprovalDecision.id,
  source_artifact_id=prd Artifact, approved_reference=product_decision id)。
- architecture 阶段 (decision) → 产生 architecture_decision Artifact +
  DecisionArtifact(type=architecture, source=architecture Artifact)。
- task 阶段 (task) → 产生 task_plan Artifact + DecisionArtifact(type=task_plan)
  + TaskStore.create 生成 Core Task (task.workflow 关联, 衔接执行)。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .models import (
    Artifact,
    DecisionArtifact,
    DecisionType,
    LifecycleStatus,
    ProductLifecycle,
    ProductStageRun,
    StageKind,
    _now,
)
from .service import ProductError, ProductNotFoundError, ProductService
from .store import ProductStore

# ------------------------------------------------------------------ 阶段/模板定义

SOFTWARE_PROJECT_STAGES: list[dict[str, Any]] = [
    # Idea 即 Artifact (9a 约定): idea 创建时已同步落 product_idea Artifact
    {"name": "idea", "kind": StageKind.ARTIFACT_GENERATION.value, "artifact_type": "product_idea"},
    {"name": "research", "kind": StageKind.ARTIFACT_GENERATION.value, "artifact_type": "research"},
    {"name": "prd", "kind": StageKind.ARTIFACT_GENERATION.value, "artifact_type": "prd"},
    # prd 审批通过 → Product Decision (决策链起点)
    {"name": "approval", "kind": StageKind.APPROVAL.value, "gate": "prd", "decision_type": DecisionType.PRODUCT.value},
    {"name": "ui", "kind": StageKind.ARTIFACT_GENERATION.value, "artifact_type": "ui"},
    {"name": "approval", "kind": StageKind.APPROVAL.value, "gate": "ui"},
    # architecture 产物经 9b 生成 (architecture 门 recommended 可跳过审批);
    # 完成时产生 Architecture Decision (决策链中段)
    {"name": "architecture", "kind": StageKind.DECISION.value, "artifact_type": "architecture", "decision_type": DecisionType.ARCHITECTURE.value},
    # task 阶段: 校验 Product + Architecture 决策链完整 → Task Plan + Task 生成
    {"name": "task", "kind": StageKind.TASK.value, "decision_type": DecisionType.TASK_PLAN.value},
]

#: 内置生命周期类型 (多生命周期支持: 未来 automation/business 模板在此注册,
#: 引擎零改动 — 阶段注册表不硬编码 research/prd/ui/architecture/task)。
BUILTIN_TEMPLATES: dict[str, dict[str, Any]] = {
    "software_project": {
        "description": "软件产品全生命周期: Idea→Research→PRD→Approval→UI→Approval→Architecture→Task→Development",
        "stages": SOFTWARE_PROJECT_STAGES,
    },
}


class ProductStage(BaseModel):
    """声明式阶段定义 (模板的组成单元)。

    kind 驱动引擎行为: artifact_generation (artifact_type 产物存在性校验) /
    approval (gate 审批门, decision_type 非空 → 通过时产生决策链记录) /
    decision (artifact_type 源产物 + decision_type 决策链位置) /
    task (decision_type=task_plan + Task 生成)。
    """

    name: str
    kind: str = StageKind.ARTIFACT_GENERATION.value
    artifact_type: str | None = None
    gate: str | None = None
    decision_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ProductWorkflowTemplate(BaseModel):
    """声明式流程模板: 生命周期类型 → 阶段链 (软件项目 software_project 默认)。

    模板为只读声明 (注册后不修改); 实例化时阶段定义复制进 ProductStageRun
    (生命周期自洽 — 模板后续变更不影响已启动实例)。validate() 在注册时校验
    结构完整性 (阶段名唯一 / 阶段类型合法 / approval 需 gate / decision/task
    需 decision_type)。
    """

    name: str
    description: str = ""
    stages: list[ProductStage] = Field(default_factory=list)

    def stage_names(self) -> list[str]:
        """阶段名顺序列表 (声明式解析/状态展示)。"""
        return [s.name for s in self.stages]

    def stage(self, name: str) -> ProductStage | None:
        """按名取阶段定义; 不存在 → None。"""
        for s in self.stages:
            if s.name == name:
                return s
        return None

    def check_structure(self) -> None:
        """结构校验 (注册时调用): 阶段名允许重复 (如 software_project 含两个
        approval 阶段 — prd/ui 各一次, 由索引定位); artifact_generation/decision
        需 artifact_type; approval 需 gate; decision/task 需 decision_type。"""
        if not self.stages:
            raise ProductError(f"template {self.name!r} has no stages")
        for s in self.stages:
            if s.kind in (StageKind.ARTIFACT_GENERATION.value, StageKind.DECISION.value) and not s.artifact_type:
                raise ProductError(
                    f"template {self.name!r} stage {s.name!r} needs artifact_type"
                )
            if s.kind == StageKind.APPROVAL.value and not s.gate:
                raise ProductError(
                    f"template {self.name!r} stage {s.name!r} needs gate"
                )
            if s.kind in (StageKind.DECISION.value, StageKind.TASK.value) and not s.decision_type:
                raise ProductError(
                    f"template {self.name!r} stage {s.name!r} needs decision_type"
                )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ProductStageRegistry:
    """阶段注册表: 生命周期类型 → 声明式模板 (多 lifecycle 类型)。

    内置 software_project (BUILTIN_TEMPLATES); 未来 automation/business 等
    类型经 register() 追加 — 引擎只查模板, 不硬编码阶段名。同名模板冲突 → 错误
    (防覆盖); 查询未注册 → ProductNotFoundError (CLI 退出码 7)。
    """

    def __init__(self, templates: list[ProductWorkflowTemplate] | None = None) -> None:
        self._templates: dict[str, ProductWorkflowTemplate] = {}
        for builtin_name, builtin in BUILTIN_TEMPLATES.items():
            self.register(self._build_template(builtin_name, builtin))
        for template in templates or []:
            self.register(template)

    @staticmethod
    def _build_template(name: str, spec: dict[str, Any]) -> ProductWorkflowTemplate:
        return ProductWorkflowTemplate(
            name=name,
            description=spec.get("description", ""),
            stages=[ProductStage(**stage) for stage in spec["stages"]],
        )

    def register(self, template: ProductWorkflowTemplate) -> None:
        """注册模板 (结构校验 + 防同名覆盖); 已存在 → ProductError。"""
        template.check_structure()
        if template.name in self._templates:
            raise ProductError(f"template already registered: {template.name!r}")
        self._templates[template.name] = template

    def get(self, name: str) -> ProductWorkflowTemplate | None:
        """按生命周期类型取模板; 未注册 → None。"""
        return self._templates.get(name)

    def require(self, name: str) -> ProductWorkflowTemplate:
        """按生命周期类型取模板; 未注册 → ProductNotFoundError (CLI 退出码 7)。"""
        template = self._templates.get(name)
        if template is None:
            raise ProductNotFoundError(f"no lifecycle template: {name!r}")
        return template

    def list(self) -> list[ProductWorkflowTemplate]:
        """全部已注册模板 (按注册序)。"""
        return list(self._templates.values())

    def types(self) -> list[str]:
        """生命周期类型名列表 (模板列表命令)。"""
        return list(self._templates.keys())

    def supports(self, name: str) -> bool:
        """是否支持该生命周期类型 (多 lifecycle 类型查询)。"""
        return name in self._templates


# ------------------------------------------------------------------ 生命周期引擎

class ProductLifecycleEngine:
    """生命周期编排引擎: start → stage 推进 → approval 等待 (复用 9c
    Pause/Resume) → 决策链 → task 生成 → completed; 可暂停/恢复/扩展。

    编排语义 (KISS, 显式推进):
    - start_lifecycle: 实例创建 + lifecycle.started + 首阶段 entered (不自动
      推进 — 每步产物/审批由用户经 advance/decide 驱动)。
    - advance: 手动推进非 approval 阶段 (校验阶段前置产物/决策链存在 → 完成
      当前阶段 stage.completed → 下一阶段 entered)。下一阶段是 approval →
      自动 request_approval (复用 9c) + lifecycle 进入 paused (等待人工);
      全部阶段完成 → lifecycle.completed。
    - handle_approval_outcome: 审批决定后同步 (CLI decide 命令装配点调用):
      approval 阶段终态 approved → 记录决策链 (gate 有 decision_type 时) +
      完成阶段 + 推进; 非 approved → 停留 (生命周期保持 paused, 修改后重新
      审批 — 9c 终态可逆语义)。
    - pause/resume: 手动暂停/恢复 (引擎 API; CLI 不暴露, 5 事件契约不变)。

    Task 集成 (禁修改 Core): task 阶段经 TaskStore.create (既有 API, 只调用)
    生成 Task — task.workflow 既有字段关联 (默认 feature-delivery), 之后由
    Core Workflow 执行 (WorkflowRun.from_workflow + execute_workflow 由既有
    装配点负责, 本层不复制 Workflow Core 逻辑)。
    """

    def __init__(
        self,
        store: ProductStore,
        service: ProductService | None = None,
        *,
        registry: ProductStageRegistry | None = None,
        task_store: Any | None = None,
        logger: Any = None,
    ) -> None:
        self._store = store
        self._service = service if service is not None else ProductService(store, logger=logger)
        self._registry = registry if registry is not None else ProductStageRegistry()
        self._task_store = task_store
        self._logger = logger

    # ------------------------------------------------------------------ 查询

    def templates(self) -> list[dict[str, Any]]:
        """全部生命周期模板 (模板列表命令; 声明式解析输出)。"""
        return [t.to_dict() for t in self._registry.list()]

    def status(self, idea_id: str) -> dict[str, Any]:
        """生命周期状态快照: 当前阶段 + 待审批 + 产物 + 决策链 + 下一步动作。

        无生命周期 → ProductNotFoundError (CLI 退出码 7)。Dashboard Lifecycle
        View 与 CLI status 消费同一形状 (collector 只读聚合)。
        """
        lifecycle = self._require_lifecycle(idea_id)
        # completed → 无当前阶段 (阶段链全部完成, 任务已交 Core Workflow 执行;
        # Dashboard Lifecycle View 同口径 — current_stages 空)。
        stage = None if lifecycle.status == LifecycleStatus.COMPLETED.value else lifecycle.current_stage
        pending = self._pending_approval_for(lifecycle)
        return {
            "lifecycle": lifecycle.to_dict(),
            "current_stage": stage.to_dict() if stage is not None else None,
            "pending_approval": pending.to_dict() if pending is not None else None,
            "artifacts": [
                a.to_dict() for a in self._artifacts_for_idea(idea_id)
            ],
            "decisions": [
                d.to_dict() for d in self._decision_chain(idea_id)
            ],
            "next_actions": self._next_actions(lifecycle, pending),
        }

    # ------------------------------------------------------------------ 编排

    def start_lifecycle(
        self,
        idea_id: str,
        template: str = "software_project",
        *,
        by: str = "human",
    ) -> ProductLifecycle:
        """启动生命周期: 校验 idea 存在 + 无重复实例 + 模板注册; 实例落库 →
        lifecycle.started → 首阶段 entered (running)。一个 idea 至多一个 run。
        """
        self._service.get_idea(idea_id)  # idea 须存在 (→ ProductNotFoundError)
        if self._store.get_lifecycle_by_idea(idea_id) is not None:
            raise ProductError(f"lifecycle already started for idea {idea_id}")
        tpl = self._registry.require(template)
        from .service import _next_id

        stages = [
            ProductStageRun(
                name=s.name,
                kind=s.kind,
                artifact_type=s.artifact_type,
                gate=s.gate,
                decision_type=s.decision_type,
            )
            for s in tpl.stages
        ]
        lifecycle = ProductLifecycle(
            id=_next_id("LC", self._store.list_lifecycles()),
            idea_id=idea_id,
            template_name=tpl.name,
            stages=stages,
            current_stage_index=0,
        )
        self._store.save_lifecycle(lifecycle)
        self._record_lifecycle_started(lifecycle)
        self._enter_stage(lifecycle)
        return lifecycle

    def advance(self, idea_id: str, *, by: str = "human") -> ProductLifecycle:
        """手动推进当前阶段 (非 approval 阶段)。

        artifact_generation: 校验 idea 下存在该类型产物 (生成由 9b 负责, 编排
        层只校验不生成); decision: 校验源产物 + 前序决策链; task: 校验决策链
        完整 + task_store 装配。完成当前阶段 → 下一阶段 entered → approval 自动
        申请审批 (lifecycle → paused) / 全部完成 → lifecycle.completed。
        """
        lifecycle = self._require_lifecycle(idea_id)
        if lifecycle.status != LifecycleStatus.RUNNING.value:
            # 暂停于 approval 阶段 → 同样提示走审批决定 (比裸 "not running"
            # 更可操作; 引擎测试契约 "is not running" 仍命中)。
            stage = lifecycle.current_stage
            if stage is not None and stage.kind == StageKind.APPROVAL.value:
                raise ProductError(
                    f"stage {stage.name!r} is an approval stage; advance via "
                    f"approval decision (product approval decide) — lifecycle "
                    f"{lifecycle.id} is not running (status: {lifecycle.status})"
                )
            raise ProductError(
                f"lifecycle {lifecycle.id} is not running (status: {lifecycle.status}); "
                f"resume it first or handle pending approval"
            )
        stage = lifecycle.current_stage
        if stage is None:
            raise ProductError(f"lifecycle {lifecycle.id} has no current stage")
        if stage.kind == StageKind.APPROVAL.value:
            raise ProductError(
                f"stage {stage.name!r} is an approval stage; advance via approval "
                f"decision (product approval decide)"
            )
        self._check_stage_prereq(lifecycle, stage)
        if stage.kind in (StageKind.DECISION.value, StageKind.TASK.value):
            self._complete_decision_stage(lifecycle, stage)  # 决策产物 + Task 生成
        self._complete_stage(lifecycle, stage)
        return self._advance_after_completion(lifecycle)

    def handle_approval_outcome(self, idea_id: str | None) -> ProductLifecycle | None:
        """审批决定后同步 (CLI decide 命令装配点调用; 无生命周期 → None no-op)。

        当前阶段为 approval 且其审批请求已终态:
        - approved → 决策链记录 (阶段有 decision_type 时) + 完成阶段 + 推进
          (下一 approval 阶段自动申请审批 / 全部完成 → completed)。
        - rejected/changes_requested/delegated → 停留 (生命周期保持 paused,
          修改后重新审批 — 9c 终态可逆; 不发阶段完成事件)。
        - pending → 不动。
        """
        if idea_id is None:
            return None
        lifecycle = self._store.get_lifecycle_by_idea(idea_id)
        if lifecycle is None:
            return None
        stage = lifecycle.current_stage
        if stage is None or stage.kind != StageKind.APPROVAL.value:
            return lifecycle
        request = self._approval_request_for(lifecycle, stage)
        if request is None or request.status == "pending":
            return lifecycle
        if request.status != "approved":
            return lifecycle  # 非批准终态: 停留 (修改后重新审批)
        if stage.decision_type:
            self._record_decision_for_approval(lifecycle, stage, request)
        self._complete_stage(lifecycle, stage)
        return self._advance_after_completion(lifecycle)

    def pause(self, idea_id: str, *, reason: str = "manual") -> ProductLifecycle:
        """手动暂停生命周期 (running → paused; 状态操作, 不发新事件类型 —
        5 事件契约固定)。已完成/未运行 → ProductError。"""
        lifecycle = self._require_lifecycle(idea_id)
        if lifecycle.status != LifecycleStatus.RUNNING.value:
            raise ProductError(
                f"lifecycle {lifecycle.id} cannot pause (status: {lifecycle.status})"
            )
        updated = lifecycle.model_copy(update={"status": LifecycleStatus.PAUSED.value})
        self._store.save_lifecycle(updated)
        return updated

    def resume(self, idea_id: str) -> ProductLifecycle:
        """手动恢复暂停的生命周期 (paused → running; 停留当前阶段)。"""
        lifecycle = self._require_lifecycle(idea_id)
        if lifecycle.status != LifecycleStatus.PAUSED.value:
            raise ProductError(
                f"lifecycle {lifecycle.id} is not paused (status: {lifecycle.status})"
            )
        updated = lifecycle.model_copy(update={"status": LifecycleStatus.RUNNING.value})
        self._store.save_lifecycle(updated)
        return updated

    # ------------------------------------------------------------------ 内部: 阶段推进

    def _enter_stage(self, lifecycle: ProductLifecycle) -> None:
        """当前阶段 → running + entered_at + stage.entered 事件; approval 阶段
        自动申请审批 (复用 9c request_approval) + lifecycle → paused。"""
        stage = lifecycle.current_stage
        if stage is None:
            return
        stage.status = "running"
        stage.entered_at = _now()
        self._store.save_lifecycle(lifecycle)
        self._record_stage_entered(lifecycle, stage)
        if stage.kind == StageKind.APPROVAL.value:
            self._begin_approval(lifecycle, stage)

    def _begin_approval(self, lifecycle: ProductLifecycle, stage: ProductStageRun) -> None:
        """approval 阶段进入: 对前序产物 (gate 类型) 自动申请审批 (复用 9c
        request_approval — 门解析/队列守卫/事件全复用, 零复制); 已有 pending
        请求 → 复用不重申请 (幂等)。申请后 lifecycle → paused (等待人工)。"""
        artifact = self._artifact_for_idea(lifecycle.idea_id, stage.gate or "")
        if artifact is None:
            return  # 产物缺失: 保持 running, advance 前置校验会提示 (防御)
        pending = self._pending_request_for_artifact(artifact.id)
        if pending is not None:
            stage.approval_request_id = pending.id
        else:
            request = self._service.request_approval(
                artifact.id,
                gate_id=stage.gate,
                by="lifecycle",
                idea_id=lifecycle.idea_id,
            )
            stage.approval_request_id = request.id
        lifecycle.status = LifecycleStatus.PAUSED.value
        self._store.save_lifecycle(lifecycle)

    def _complete_stage(self, lifecycle: ProductLifecycle, stage: ProductStageRun) -> None:
        """完成当前阶段 (completed + completed_at + stage.completed 事件)。"""
        stage.status = "completed"
        stage.completed_at = _now()
        self._store.save_lifecycle(lifecycle)
        self._record_stage_completed(lifecycle, stage)

    def _advance_after_completion(self, lifecycle: ProductLifecycle) -> ProductLifecycle:
        """阶段完成后推进: 下一阶段 entered (approval → 自动审批暂停) 或
        全部完成 → lifecycle.completed (completed_at + completed 事件)。"""
        next_idx = lifecycle.current_stage_index + 1
        if next_idx >= len(lifecycle.stages):
            lifecycle.status = LifecycleStatus.COMPLETED.value
            lifecycle.completed_at = _now()
            self._store.save_lifecycle(lifecycle)
            self._record_lifecycle_completed(lifecycle)
            return lifecycle
        lifecycle.current_stage_index = next_idx
        # 审批通过/恢复后推进: 恢复 running (下一阶段若是 approval → _begin_approval
        # 会再置 paused; 非 approval 阶段保持 running — 9c Pause/Resume 语义)。
        lifecycle.status = LifecycleStatus.RUNNING.value
        self._store.save_lifecycle(lifecycle)
        self._enter_stage(lifecycle)
        return lifecycle

    # ------------------------------------------------------------------ 内部: 前置校验

    def _check_stage_prereq(self, lifecycle: ProductLifecycle, stage: ProductStageRun) -> None:
        """阶段前置校验 (advance): 产物存在性 / 决策链完整性 / task_store 装配。

        artifact_generation → 该 idea 下存在 stage.artifact_type 的 Artifact
        (生成由 9b generate 或 create_artifact 负责); decision → 源产物存在 +
        前序 product 决策已产生; task → product + architecture 决策链完整 +
        task_store 装配 (缺省 None → 响亮配置缺口错误)。
        """
        if stage.kind == StageKind.ARTIFACT_GENERATION.value:
            artifact = self._artifact_for_idea(lifecycle.idea_id, stage.artifact_type or "")
            if artifact is None:
                raise ProductError(
                    f"stage {stage.name!r} needs a {stage.artifact_type!r} artifact "
                    f"for idea {lifecycle.idea_id} (generate it first: product generate "
                    f"--type {stage.artifact_type})"
                )
            stage.artifact_id = artifact.id
            self._store.save_lifecycle(lifecycle)
            return
        if stage.kind == StageKind.DECISION.value:
            artifact = self._artifact_for_idea(lifecycle.idea_id, stage.artifact_type or "")
            if artifact is None:
                raise ProductError(
                    f"stage {stage.name!r} needs a {stage.artifact_type!r} artifact "
                    f"for idea {lifecycle.idea_id} (generate it first: product generate "
                    f"--type {stage.artifact_type})"
                )
            if DecisionType.PRODUCT.value not in self._decision_types(lifecycle.idea_id):
                raise ProductError(
                    f"stage {stage.name!r} needs the Product Decision first "
                    f"(approve the prd approval)"
                )
            stage.artifact_id = artifact.id
            self._store.save_lifecycle(lifecycle)
            return
        if stage.kind == StageKind.TASK.value:
            missing = [
                t for t in (DecisionType.PRODUCT.value, DecisionType.ARCHITECTURE.value)
                if t not in self._decision_types(lifecycle.idea_id)
            ]
            if missing:
                raise ProductError(
                    f"stage {stage.name!r} needs the decision chain "
                    f"({' + '.join(missing)}) first"
                )
            if self._task_store is None:
                raise ProductError(
                    f"stage {stage.name!r} needs a TaskStore (task integration "
                    f"not wired — pass task_store to ProductLifecycleEngine)"
                )

    def _complete_decision_stage(self, lifecycle: ProductLifecycle, stage: ProductStageRun) -> None:
        """decision/task 阶段的产物生成: 决策 Artifact + DecisionArtifact 链记录
        (+ task 阶段 TaskStore.create 生成 Core Task)。在 _complete_stage 前调用。"""
        idea = self._service.get_idea(lifecycle.idea_id)
        if stage.kind == StageKind.DECISION.value:
            source = self._artifact_for_idea(lifecycle.idea_id, stage.artifact_type or "")
            decision_artifact = self._service.create_artifact(
                "architecture_decision",
                content={
                    "idea_id": lifecycle.idea_id,
                    "architecture_artifact_id": source.id if source is not None else None,
                    "decision_type": stage.decision_type,
                    "basis": "architecture stage completion",
                },
                created_by="lifecycle",
                idea_id=lifecycle.idea_id,
            )
            stage.decision_id = decision_artifact.id
            self._record_decision_artifact(
                artifact_type=stage.decision_type or DecisionType.ARCHITECTURE.value,
                source_artifact_id=source.id if source is not None else None,
                approved_reference=decision_artifact.id,
                idea_id=lifecycle.idea_id,
                decision_id=None,
            )
            return
        if stage.kind == StageKind.TASK.value:
            chain = self._decision_chain(lifecycle.idea_id)
            by_type = {d.type: d for d in chain}
            task_plan = self._service.create_artifact(
                "task_plan",
                content={
                    "idea_id": lifecycle.idea_id,
                    "title": idea.title,
                    "product_decision": (
                        by_type[DecisionType.PRODUCT.value].approved_reference
                        if DecisionType.PRODUCT.value in by_type else None
                    ),
                    "architecture_decision": (
                        by_type[DecisionType.ARCHITECTURE.value].approved_reference
                        if DecisionType.ARCHITECTURE.value in by_type else None
                    ),
                    "decision_chain": [d.to_dict() for d in chain],
                },
                created_by="lifecycle",
                idea_id=lifecycle.idea_id,
            )
            stage.decision_id = task_plan.id
            self._record_decision_artifact(
                artifact_type=DecisionType.TASK_PLAN.value,
                source_artifact_id=(
                    by_type[DecisionType.ARCHITECTURE.value].approved_reference
                    if DecisionType.ARCHITECTURE.value in by_type else None
                ),
                approved_reference=task_plan.id,
                idea_id=lifecycle.idea_id,
                decision_id=None,
            )
            # 回填决策链 (含 task_plan 决策自身) — 内容闭环: task_plan 的
            # decision_chain 引用全部 3 节点 (Product → Architecture → Task Plan)。
            task_plan.content = {
                **task_plan.content,
                "decision_chain": [
                    d.to_dict() for d in self._decision_chain(lifecycle.idea_id)
                ],
            }
            self._store.save_artifact(task_plan)
            task = self._create_core_task(idea, task_plan)
            stage.task_id = task.id
            self._store.save_lifecycle(lifecycle)

    def _create_core_task(self, idea: Any, task_plan: Artifact) -> Any:
        """经 TaskStore.create 生成 Core Task (既有 API, 只调用 — 禁修改 Core)。

        task.workflow 既有字段 (默认 feature-delivery) 关联 Core Workflow —
        任务执行由既有 WorkflowEngine/OrchestrationPipeline 装配点负责, 本层
        不复制 Workflow Core 逻辑。Task 标题含 task_plan 锚点 (任务 → 决策链
        可追溯); project 从 idea.context 推导 (缺省 default)。
        """
        from tasks.models import Task
        from tasks.store import TaskStore

        task_store = self._task_store
        assert task_store is not None  # _check_stage_prereq 已保证装配 (配置缺口响亮)
        project = str(idea.context.get("project") or "default") if isinstance(idea.context, dict) else "default"
        task = Task(
            id=task_store.next_id("T-"),
            title=f"Implement {idea.title} (task plan {task_plan.id})",
            project=project,
            type="feature",
            workflow="feature-delivery",
        )
        task_store.create(task)
        return task

    def _record_decision_artifact(
        self,
        *,
        artifact_type: str,
        source_artifact_id: str | None,
        approved_reference: str | None,
        idea_id: str,
        decision_id: str | None,
    ) -> DecisionArtifact:
        """落 DecisionArtifact (决策链记录) + product.decision.created 事件。"""
        from .service import _next_id

        decision = DecisionArtifact(
            id=_next_id("DEC", self._store.list_decision_artifacts()),
            type=artifact_type,
            decision_id=decision_id,
            source_artifact_id=source_artifact_id,
            approved_reference=approved_reference,
            idea_id=idea_id,
        )
        self._store.save_decision_artifact(decision)
        from .events import record_decision_created

        record_decision_created(
            self._logger,
            decision=decision,
            source="product",
        )
        return decision

    def _record_decision_for_approval(
        self,
        lifecycle: ProductLifecycle,
        stage: ProductStageRun,
        request: Any,
    ) -> None:
        """approval 阶段通过 → 决策链记录 (9c decide 已产 product_decision
        Artifact, 本层只记链索引 — 不复制 9c 决策产物生成)。"""
        decision_record = None
        for d in self._store.list_decisions():
            if d.request_id == request.id:
                decision_record = d
        product_decision = None
        for a in self._store.list_artifacts_by_type("product_decision"):
            if isinstance(a.content, dict) and a.content.get("request_id") == request.id:
                product_decision = a
        self._record_decision_artifact(
            artifact_type=stage.decision_type or "",
            source_artifact_id=request.artifact_id,
            approved_reference=product_decision.id if product_decision is not None else None,
            idea_id=lifecycle.idea_id,
            decision_id=decision_record.id if decision_record is not None else None,
        )

    # ------------------------------------------------------------------ 内部: 查询辅助

    def _require_lifecycle(self, idea_id: str) -> ProductLifecycle:
        lifecycle = self._store.get_lifecycle_by_idea(idea_id)
        if lifecycle is None:
            raise ProductNotFoundError(f"no product lifecycle for idea {idea_id}")
        return lifecycle

    def _artifacts_for_idea(self, idea_id: str) -> list[Artifact]:
        return [
            a for a in self._store.list_artifacts()
            if isinstance(a.content, dict) and a.content.get("idea_id") == idea_id
        ]

    def _artifact_for_idea(self, idea_id: str, artifact_type: str) -> Artifact | None:
        """idea 下指定类型的最新版本 Artifact (version 最大); 无 → None。"""
        arts = [
            a for a in self._artifacts_for_idea(idea_id) if a.type == artifact_type
        ]
        return max(arts, key=lambda a: a.version) if arts else None

    def _decision_chain(self, idea_id: str) -> list[DecisionArtifact]:
        """决策链 (Product → Architecture → Task Plan 类型序; 每类型多条取最新,
        链序稳定 — Dashboard/CLI/任务前置校验共用)。"""
        by_type: dict[str, DecisionArtifact] = {}
        for d in self._store.list_decision_artifacts():
            if d.idea_id != idea_id:
                continue
            if d.type not in by_type or d.created_at > by_type[d.type].created_at:
                by_type[d.type] = d
        order = [DecisionType.PRODUCT.value, DecisionType.ARCHITECTURE.value, DecisionType.TASK_PLAN.value]
        return [by_type[t] for t in order if t in by_type]

    def _decision_types(self, idea_id: str) -> set[str]:
        return {d.type for d in self._decision_chain(idea_id)}

    def _approval_request_for(self, lifecycle: ProductLifecycle, stage: ProductStageRun):
        """approval 阶段关联的审批请求 (回填 id 优先; 兜底按 gate 类型找该 idea
        的最新请求 — 兼容手工 request_approval 路径)。"""
        if stage.approval_request_id is not None:
            request = self._store.get_request(stage.approval_request_id)
            if request is not None:
                return request
        candidates = [
            r for r in self._store.list_requests()
            if r.idea_id == lifecycle.idea_id and r.gate == stage.gate
        ]
        return max(candidates, key=lambda r: r.requested_at) if candidates else None

    def _pending_request_for_artifact(self, artifact_id: str):
        """artifact 的 pending 审批请求 (幂等复用); 无 → None。"""
        for r in self._store.list_requests():
            if r.artifact_id == artifact_id and r.status == "pending":
                return r
        return None

    def _pending_approval_for(self, lifecycle: ProductLifecycle):
        """当前阶段的 pending 审批请求 (Dashboard/CLI status 展示); 无 → None。"""
        stage = lifecycle.current_stage
        if stage is None or stage.kind != StageKind.APPROVAL.value:
            return None
        request = self._approval_request_for(lifecycle, stage)
        if request is not None and request.status == "pending":
            return request
        return None

    # ------------------------------------------------------------------ 内部: 下一步动作

    def _next_actions(self, lifecycle: ProductLifecycle, pending: Any | None) -> list[str]:
        """人类可读的下一步动作列表 (status/Dashboard 消费)。"""
        stage = lifecycle.current_stage
        if lifecycle.status == LifecycleStatus.COMPLETED.value:
            return ["lifecycle completed — tasks are ready for Core Workflow execution"]
        if lifecycle.status == LifecycleStatus.PAUSED.value:
            if pending is not None:
                return [
                    f"decide approval {pending.id} (product approval decide {pending.id} "
                    f"approve|reject|changes_requested|delegate)"
                ]
            if stage is not None and stage.kind == StageKind.APPROVAL.value:
                return ["waiting for approval outcome (already decided — lifecycle will advance)"]
            return [f"resume lifecycle (product lifecycle resume is engine API)"]
        if stage is None:
            return ["no current stage"]
        if stage.kind == StageKind.APPROVAL.value:
            return ["approval stage entered — lifecycle paused"]
        if stage.kind == StageKind.ARTIFACT_GENERATION.value:
            return [
                f"generate {stage.artifact_type or 'artifact'} artifact "
                f"(product generate --type {stage.artifact_type} {lifecycle.idea_id}), "
                f"then advance (product lifecycle advance {lifecycle.idea_id})"
            ]
        if stage.kind == StageKind.DECISION.value:
            return [f"advance to produce architecture decision (product lifecycle advance {lifecycle.idea_id})"]
        return [f"advance to produce task plan + tasks (product lifecycle advance {lifecycle.idea_id})"]

    # ------------------------------------------------------------------ 内部: 事件

    def _record_lifecycle_started(self, lifecycle: ProductLifecycle) -> None:
        from .events import record_lifecycle_started

        record_lifecycle_started(self._logger, lifecycle=lifecycle, source="product")

    def _record_stage_entered(self, lifecycle: ProductLifecycle, stage: ProductStageRun) -> None:
        from .events import record_stage_entered

        record_stage_entered(self._logger, lifecycle=lifecycle, stage=stage, source="product")

    def _record_stage_completed(self, lifecycle: ProductLifecycle, stage: ProductStageRun) -> None:
        from .events import record_stage_completed

        record_stage_completed(self._logger, lifecycle=lifecycle, stage=stage, source="product")

    def _record_lifecycle_completed(self, lifecycle: ProductLifecycle) -> None:
        from .events import record_lifecycle_completed

        record_lifecycle_completed(self._logger, lifecycle=lifecycle, source="product")
