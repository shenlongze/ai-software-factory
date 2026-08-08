"""factory-org/org/workflow.py — 组织级 Workflow 编排壳 (Sprint 7 S7-003)。

设计依据 (sprint7-architecture.md §3 任务级 → 组织级):
- 本模块是 **组织级编排壳** (org 侧): 编排 Project→Workflow→Stage→Artifact
  全链, 与 Core 任务级 WorkflowEngine (factory-core/workflows, 4 技术模板
  CREATED/RUNNING/COMPLETED/FAILED + Step 顺序执行) **区分且解耦**:
    * Core WorkflowEngine: 单任务内步骤执行 (技术模板, 冻结, 零修改)
    * org Workflow: 组织级工作流运行 (角色编排壳: PM→Architect→Developer→
      Tester→Release→Analytics 全链, 本层只建壳/流转/编排, 不调 LLM)
  org Workflow 复用 Core 概念 (状态机/事件模式) 但不 import Core 业务模块
  (Removal Isolation, 同 S7-001/002: 仅依赖 events 层)。

模型层级:
```
User → Project → Workflow (run) → Stage (role_id=exec 注册表角色)
                                      └─ input_artifacts[]/output_artifacts[]
                                          → Artifact (VALIDATED 门禁/自动注册)
```

Workflow 状态机 (WORKFLOW_TRANSITIONS 受控转换表, 单向无环):
```
DRAFT → ACTIVE (启动)        ACTIVE → PAUSED (人工暂停)
ACTIVE → COMPLETED (全完成)  ACTIVE → FAILED (stage 失败)
PAUSED → ACTIVE (恢复/重试)  FAILED → PAUSED (人工介入后重试 — 失败可重试路径)
COMPLETED → () 终态
```

Stage 状态机 (STAGE_TRANSITIONS, projects.py — 与 Stage 模型同源):
```
PENDING → READY/BLOCKED → RUNNING → COMPLETED (终态) / FAILED (→READY 重试)
阻塞: 依赖未 COMPLETED 或输入未 VALIDATED → BLOCKED (条件满足回 READY)
```

Stage 依赖 (DAG):
- depends_on: 本 workflow 内前置 stage id 列表; 未定义/跨 workflow 依赖拒绝
  (WorkflowDependencyError); 循环依赖拒绝 (WorkflowCycleError, Kahn 拓扑检测)
- ready 判定 (Runner): 全部 depends_on COMPLETED 且 input_artifacts 全部
  VALIDATED → READY, 否则 BLOCKED

Runner 执行循环 (WorkflowRunner.run):
```
读 workflow → DRAFT/PAUSED 自动转 ACTIVE → validate_dag (循环响亮拒绝)
→ 评估各 stage 就绪 (READY/BLOCKED) → 按 order 取首个 READY stage
→ 触发 Role Executor (注入 callable: executor(stage, context) → dict;
   不重写 EmployeeExecutor — S7-005 接入真实执行适配器)
→ 输出 Artifact 自动注册 (ArtifactRegistry: create→generated→validated,
   契约失败 → stage FAILED → workflow FAILED)
→ 推进下一 stage; 全部 COMPLETED → workflow COMPLETED; 无可推进 (BLOCKED)
   → workflow 保持 ACTIVE (等待外部输入/修复); stage 失败 → workflow FAILED
→ 计数保护: 每步执行一个 stage, 步数上限 = stage 数 + 1 (防无限循环)
```

Artifact 集成:
- 输入: stage.input_artifacts 全部须 VALIDATED (未验证 → BLOCKED); 跨项目
  输入拒绝 (项目隔离铁律, 兼容 S7-001 空 project_id 产物)
- 输出: Runner 完成后自动注册 (producer_role=stage.role_id, project_id 继承
  workflow), 契约校验通过置 VALIDATED; 查询: stage_artifacts /
  workflow_artifacts (复用 ArtifactRegistry.query)

存储: <root>/org/workflows.json (WorkflowSection, 与 ProjectStore 同目录
独立文件; Stage/Artifact 复用 ProjectStore — 零新数据空间)。

约束: Core 冻结 (仅 events 枚举新增, ADR-0001 扩展路径); 零 LLM/零执行
副作用 (真实执行 S7-005 接入; 本层只编排状态与审计事件); executor=None
时 Runner 响亮拒绝执行 (不假装执行 — 编排壳诚实边界)。
事件 (org.workflow.*, 见 org/events.py): created/started/stage_ready/
stage_started/stage_completed/completed/failed + viewed (读命令审计)。
logger=None 全静默 (同既有 org 模式); 每转换审计 payload 唯一事实源。

Sprint 9 S9-001 扩展 (Approval Gate 接线, 只扩展不改核心):
- Stage 增加 approval_required 属性 (projects.py; 三挡板: product 后 MVP /
  design 后架构 / release 前发布)
- 执行链: approval_required stage COMPLETED → ApprovalGate (PENDING) 创建
  (org/approval.py 模型 + approvals.json 持久化) → workflow PAUSED (受控
  转换表 active→paused 已有语义)
- approve → gate APPROVED → workflow 恢复 (PAUSED→ACTIVE, started 事件
  from_status=paused) → Runner 继续下一 stage
- reject → gate REJECTED → workflow FAILED 停止 (复用既有合法路径
  PAUSED→ACTIVE→FAILED 两跳 — WORKFLOW_TRANSITIONS 零修改; failed_reason
  记录审批否决原因)
- Runner 守卫 (禁绕过审批门): 待审门 PENDING → 挂起不自动恢复;
  否决门 REJECTED → WorkflowStateError 响亮拒绝 (含 failed→paused→active
  重试路径 — 决定不可撤销)
- 事件 +3 (factory-core events/models.py 枚举扩展, ADR-0001 路径):
  org.approval.created / approved / rejected
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from pydantic import Field, field_validator

from . import events as org_events
from .approval import (
    ApprovalGate,
    ApprovalGateStore,
    ApprovalStatus,
    transition_approval,
)
from .artifact import ArtifactRegistry
from .lifecycle import DuplicateError, NotFoundError
from .models import _OrgModel, _norm_list, new_id, utcnow
from .projects import (
    STAGE_TRANSITIONS,
    ArtifactStatus,
    ProjectStore,
    Stage,
    StageStatus,
    _validate_exec_role,
)
from .store import _SectionStore

# ------------------------------------------------------------------ 枚举


class WorkflowStatus(str, Enum):
    """Workflow 生命周期状态 (组织级编排壳; 受控转换表 WORKFLOW_TRANSITIONS)。

    DRAFT → ACTIVE → COMPLETED (终态) / FAILED (可经 PAUSED 重试)。
    """

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"

    @classmethod
    def parse(cls, value: Any) -> "WorkflowStatus":
        """宽容解析: 大小写不敏感; 枚举对象直接返回; 非法值抛 ValueError。"""
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(
                f"invalid workflow status: {value!r} (expected one of: {valid})"
            ) from None


#: Workflow 合法流转 (受控转换表; 单向无环; completed 终态)。
#: 主链: draft→active→completed; 失败: active→failed (stage 失败);
#: 暂停: active→paused (人工) / failed→paused (失败重试前置 — 可 PAUSED
#: 重试路径); 恢复: paused→active (重试/继续); draft 不可直接 completed。
WORKFLOW_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "draft": ("active",),
    "active": ("paused", "completed", "failed"),
    "paused": ("active",),
    "completed": (),
    "failed": ("paused",),
}


#: 角色 → 默认输出产物类型 (exec 注册表 role_id 单一事实源; 阶段产物 =
#: 下一阶段输入: PRD→Design→Code→Test→Release)。executor 结果未声明
#: artifact_type 时按此推断; 未知角色 → None (须显式声明, 否则执行错误)。
ROLE_OUTPUT_TYPES: dict[str, str] = {
    "product-manager": "prd",
    "architect": "design",
    "ui-designer": "design",
    "developer": "code",
    "tester": "test",
    "devops": "release",
}


# ------------------------------------------------------------------ 模型


class Workflow(_OrgModel):
    """Workflow (组织级编排壳运行; 状态机受控流转, CRUD 经 WorkflowLifecycle)。

    stage_ids: 阶段索引 (S7-003 编排层维护; 权威读取 = ProjectStore
    list_stages_by_workflow — 兼容 S7-001 直建 stage 的场景)。
    started_at/completed_at: 运行审计时间戳; failed_reason: 失败原因审计。
    """

    id: str
    project_id: str
    name: str
    status: WorkflowStatus = WorkflowStatus.DRAFT
    stage_ids: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_reason: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> WorkflowStatus:
        return WorkflowStatus.parse(v)

    @field_validator("stage_ids", mode="before")
    @classmethod
    def _stage_ids_none(cls, v: Any) -> Any:
        return _norm_list(v)

    @property
    def is_terminal(self) -> bool:
        """终态判断 (completed/failed 后不可再流转/执行)。"""
        return self.status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED)


class WorkflowSection(_SectionStore[Workflow]):
    """Workflow 持久化 (workflows.json; 与 ProjectStore 同目录独立文件)。"""

    _filename = "workflows.json"
    _section = "workflows"
    _model = Workflow


# ------------------------------------------------------------------ 异常


class WorkflowError(Exception):
    """Workflow Engine 基础异常。"""


class WorkflowStateError(WorkflowError):
    """非法状态转换 (受控转换表拒绝) / 终态操作。"""


class WorkflowCycleError(WorkflowError):
    """Stage 依赖成环 (DAG 校验拒绝 — 循环依赖响亮失败)。"""


class WorkflowDependencyError(WorkflowError):
    """依赖未定义 (跨 workflow / 不存在 stage / 自依赖)。"""


class WorkflowExecutionError(WorkflowError):
    """执行期错误 (executor 缺失/异常、产物契约失败、步数保护触发)。"""


# ------------------------------------------------------------------ 编排


class WorkflowLifecycle:
    """组织级 Workflow 编排 (Workflow/Stage 全生命周期 + DAG 校验)。

    只编排状态与审计事件, 零 LLM/零执行副作用 (真实执行 S7-005 接入)。
    数据: WorkflowSection (workflows.json) + ProjectStore (stages/artifacts
    同数据空间); 事件: org.workflow.* / org.stage.* (logger=None 静默)。
    """

    def __init__(self, store: ProjectStore, *, logger: Any = None):
        self._store = store
        self._logger = logger
        self._workflows = WorkflowSection(store.dir)
        self._approvals = ApprovalGateStore(store.dir)  # S9-001: approvals.json
        self._registry = ArtifactRegistry(store, logger=logger)

    @property
    def store(self) -> ProjectStore:
        return self._store

    @property
    def registry(self) -> ArtifactRegistry:
        """ArtifactRegistry (输出自动注册/输入查询复用, 与 S7-002 同源)。"""
        return self._registry

    # ------------------------------------------------------------ Workflow

    def create_workflow(
        self,
        project_id: str,
        name: str,
        *,
        workflow_id: str | None = None,
    ) -> Workflow:
        """创建 Workflow (org.workflow.created; 状态 DRAFT)。

        与 Project 关联校验 (引用完整): project 必须存在 → NotFoundError;
        workflow id 唯一性 → DuplicateError。
        """
        self._require_project(project_id)
        workflow_id = workflow_id or new_id("WF")
        if self._workflows.get(workflow_id) is not None:
            raise DuplicateError(f"workflow already exists: {workflow_id}")
        workflow = Workflow(id=workflow_id, project_id=project_id, name=name)
        self._workflows.save(workflow)
        org_events.record_workflow_created(self._logger, workflow=workflow)
        return workflow

    def get_workflow(self, workflow_id: str) -> Workflow:
        workflow = self._workflows.get(workflow_id)
        if workflow is None:
            raise NotFoundError(f"workflow not found: {workflow_id}")
        return workflow

    def list_workflows(self, project_id: str | None = None) -> list[Workflow]:
        workflows = self._workflows.list_all()
        if project_id is not None:
            workflows = [w for w in workflows if w.project_id == project_id]
        return workflows

    def count_workflows(self) -> int:
        return self._workflows.count()

    def transition_workflow(
        self,
        workflow_id: str,
        to_status: WorkflowStatus | str,
        *,
        reason: str = "",
        event_extra: dict[str, Any] | None = None,
    ) -> Workflow:
        """受控状态转换 (WORKFLOW_TRANSITIONS 转换表; 每转换审计事件)。

        非法跳转 → WorkflowStateError; 同状态幂等 (不发事件); completed
        终态不可再转 (转换表空)。started_at/completed_at/failed_reason 随
        转换落库 (审计)。事件: →active 发 started (含 paused→active 重试
        恢复); →completed 发 completed; →failed 发 failed (event_extra 可
        带 stage_id — Runner 失败审计); →paused 不独立发事件 (与 S7-001
        stage 状态转换同先例, 恢复路径已由 started 覆盖)。
        """
        workflow = self.get_workflow(workflow_id)
        target = WorkflowStatus.parse(to_status)
        if target == workflow.status:
            return workflow  # 幂等: 同状态不重复发事件
        allowed = WORKFLOW_TRANSITIONS.get(workflow.status.value, ())
        if target.value not in allowed:
            raise WorkflowStateError(
                f"invalid workflow transition: {workflow.status.value} → "
                f"{target.value} (allowed from {workflow.status.value}: "
                f"{', '.join(allowed) or 'none'})"
            )
        updates: dict[str, Any] = {"status": target, "updated_at": utcnow()}
        if target == WorkflowStatus.ACTIVE:
            updates["started_at"] = workflow.started_at or utcnow()
        elif target == WorkflowStatus.COMPLETED:
            updates["completed_at"] = utcnow()
        elif target == WorkflowStatus.FAILED:
            updates["failed_reason"] = reason
        updated = workflow.model_copy(update=updates)
        self._workflows.save(updated)
        self._emit_workflow_transition(workflow, updated, reason=reason, extra=event_extra)
        return updated

    def activate(self, workflow_id: str) -> Workflow:
        """启动/恢复 (→active; DRAFT 启动 或 PAUSED 重试恢复)。"""
        return self.transition_workflow(workflow_id, WorkflowStatus.ACTIVE)

    def pause(self, workflow_id: str) -> Workflow:
        """人工暂停 (active→paused; 失败重试前置 failed→paused)。"""
        return self.transition_workflow(workflow_id, WorkflowStatus.PAUSED)

    # -------------------------------------------------------------- Stage

    def create_stage(
        self,
        workflow_id: str,
        role_id: str,
        *,
        name: str = "",
        order: int | None = None,
        depends_on: list[str] | None = None,
        input_artifacts: list[str] | None = None,
        output_artifacts: list[str] | None = None,
        approval_required: bool = False,  # S9-001: 人工审批门 (三挡板)
        stage_id: str | None = None,
    ) -> Stage:
        """创建 Stage (org.stage.created; 组织级编排壳阶段, 不执行)。

        校验:
        - workflow 必须存在 (引用完整)
        - role_id 经 exec 注册表校验 (S7-001 单一事实源; 未安装 → 跳过)
        - depends_on: 全部须为本 workflow 内已存在 stage (未定义/跨
          workflow 依赖 → WorkflowDependencyError); 新 stage 无出边,
          循环不可能 (set_stage_dependencies 才可能成环)
        - order 缺省 = 当前最大 order + 1 (追加语义; S7-001 直建不受影响)
        - approval_required: S9-001 审批门标记 (product/design/release 三
          挡板; COMPLETED 后 Runner 自动创建 ApprovalGate + PAUSED)
        stage_ids 索引同步 (workflow.stage_ids 追加 + updated_at 落库)。
        """
        self.get_workflow(workflow_id)  # 工作流必须存在 (引用完整)
        _validate_exec_role(role_id)
        depends_on = list(depends_on or [])
        input_artifacts = list(input_artifacts or [])
        output_artifacts = list(output_artifacts or [])
        existing = self._store.list_stages_by_workflow(workflow_id)
        self._require_same_workflow(existing, depends_on, workflow_id)
        if order is None:
            order = max([s.order for s in existing] or [0]) + 1
        stage_id = stage_id or new_id("STG")
        if self._store.get_stage(stage_id) is not None:
            raise DuplicateError(f"stage already exists: {stage_id}")
        stage = Stage(
            id=stage_id,
            workflow_id=workflow_id,
            role_id=role_id,
            name=name,
            order=int(order),
            depends_on=depends_on,
            input_artifacts=input_artifacts,
            output_artifacts=output_artifacts,
            approval_required=bool(approval_required),
        )
        self._store.save_stage(stage)
        self._append_stage_id(workflow_id, stage_id)
        org_events.record_stage_created(self._logger, stage=stage)
        return stage

    def get_stage(self, stage_id: str) -> Stage:
        stage = self._store.get_stage(stage_id)
        if stage is None:
            raise NotFoundError(f"stage not found: {stage_id}")
        return stage

    def list_stages(self, workflow_id: str) -> list[Stage]:
        """Workflow 的阶段序列 (order 升序, 同 order 按 id — 确定性执行序)。"""
        return sorted(
            self._store.list_stages_by_workflow(workflow_id),
            key=lambda s: (s.order, s.id),
        )

    def set_stage_dependencies(self, stage_id: str, depends_on: list[str]) -> Stage:
        """替换 Stage 依赖 (DAG 校验: 未定义拒绝 + 循环拒绝)。

        对既有 stage 加依赖可能成环 (A 依赖 B, 给 B 加依赖 A → 环) —
        增量检查: 从每个新依赖出发 DFS, 能回到本 stage → WorkflowCycleError。
        """
        stage = self.get_stage(stage_id)
        depends_on = list(depends_on or [])
        siblings = self._store.list_stages_by_workflow(stage.workflow_id)
        self._require_same_workflow(siblings, depends_on, stage.workflow_id)
        by_id = {s.id: s for s in siblings}
        for dep in depends_on:
            if self._reaches(stage_id, dep, by_id):
                raise WorkflowCycleError(
                    f"stage dependency cycle detected: {stage_id} → {dep}"
                )
        updated = stage.model_copy(
            update={"depends_on": depends_on, "updated_at": utcnow()}
        )
        self._store.save_stage(updated)
        return updated

    def transition_stage(
        self,
        stage_id: str,
        to_status: StageStatus | str,
        *,
        reason: str = "",
    ) -> Stage:
        """受控 Stage 状态转换 (STAGE_TRANSITIONS 转换表; 每转换审计事件)。

        非法跳转 → WorkflowStateError (如 pending 直接 completed); 同状态
        幂等 (不发事件); completed 终态不可再转 (转换表空)。事件:
        →ready 发 stage_ready; →running 发 stage_started; →completed 发
        stage_completed (output_artifacts 随 payload); →blocked/failed/
        pending 不独立发事件 (blocked 为评估瞬态, 解除回 ready 时发
        stage_ready; failed 随 workflow.failed 审计 — stage 级转换事件
        列表见 org/events.py 契约)。
        """
        stage = self.get_stage(stage_id)
        target = StageStatus.parse(to_status)
        if target == stage.status:
            return stage  # 幂等: 同状态不重复发事件
        allowed = STAGE_TRANSITIONS.get(stage.status.value, ())
        if target.value not in allowed:
            raise WorkflowStateError(
                f"invalid stage transition: {stage.status.value} → "
                f"{target.value} (allowed from {stage.status.value}: "
                f"{', '.join(allowed) or 'none'})"
            )
        updated = stage.model_copy(update={"status": target, "updated_at": utcnow()})
        self._store.save_stage(updated)
        workflow = self.get_workflow(stage.workflow_id)
        self._emit_stage_transition(workflow, updated, reason=reason)
        return updated

    # -------------------------------------------------------------- DAG

    def validate_dag(self, workflow_id: str) -> list[str]:
        """全 workflow DAG 校验 → 拓扑序 (Kahn; 循环 → WorkflowCycleError)。

        未定义依赖 (dep 不在本 workflow) → WorkflowDependencyError; 自依赖
        视为环 (Kahn 天然检出); 返回拓扑序 (执行友好, 测试断言用)。
        """
        stages = self.list_stages(workflow_id)
        by_id = {s.id: s for s in stages}
        for s in stages:
            for dep in s.depends_on:
                if dep not in by_id:
                    raise WorkflowDependencyError(
                        f"stage {s.id} depends on undefined stage {dep!r} "
                        f"(workflow {workflow_id})"
                    )
        indegree = {s.id: 0 for s in stages}
        adj: dict[str, list[str]] = {s.id: [] for s in stages}
        for s in stages:
            for dep in s.depends_on:
                adj[dep].append(s.id)  # dep → s (s 依赖 dep)
                indegree[s.id] += 1
        queue = [sid for sid, d in indegree.items() if d == 0]
        order: list[str] = []
        while queue:
            sid = queue.pop()
            order.append(sid)
            for nxt in adj[sid]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)
        if len(order) != len(stages):
            cycle = [s.id for s in stages if s.id not in order]
            raise WorkflowCycleError(
                f"stage dependency cycle detected in workflow {workflow_id}: "
                f"stages not topologically sortable: {', '.join(sorted(cycle))}"
            )
        return order

    # ------------------------------------------------------------ 查询

    def stage_artifacts(self, stage_id: str) -> list[Any]:
        """阶段产物 (stage_id 过滤; 含 S7-001/002 直建产物 — 组合查询)。"""
        return self._registry.query(stage_id=stage_id)

    def workflow_artifacts(self, workflow_id: str) -> list[Any]:
        """workflow 全阶段产物 (阶段产物可查 — 按 stage 归属汇总)。"""
        stage_ids = [s.id for s in self.list_stages(workflow_id)]
        return [
            a
            for sid in stage_ids
            for a in self._registry.query(stage_id=sid)
        ]

    # ---------------------------------------------------- Approval Gate (S9-001)
    # 人工审批门接线 (只扩展不改核心 — 状态机复用 WORKFLOW_TRANSITIONS 既有
    # 语义: active→paused 挂起 / paused→active 恢复 / active→failed 停止):
    # - request_approval: approval_required stage 的门创建 (Runner 在 stage
    #   COMPLETED 后调用; PENDING + workflow PAUSED; org.approval.created)
    # - approve_approval: PENDING→APPROVED (终态) + workflow 恢复
    #   PAUSED→ACTIVE (started 事件 from_status=paused) → Runner 继续下一 stage
    # - reject_approval: PENDING→REJECTED (终态) + workflow FAILED 停止
    #   (复用 PAUSED→ACTIVE→FAILED 两跳合法路径; failed_reason 记录否决原因)
    # 模型/状态机/持久化见 org/approval.py (APPROVAL_TRANSITIONS + Store)。

    def get_approval(self, gate_id: str) -> ApprovalGate:
        """审批门详情 (不存在 → NotFoundError)。"""
        gate = self._approvals.get(gate_id)
        if gate is None:
            raise NotFoundError(f"approval gate not found: {gate_id}")
        return gate

    def get_approval_by_stage(self, stage_id: str) -> ApprovalGate | None:
        """按 stage 查审批门 (每 stage 至多一门; 无 → None)。"""
        for gate in self._approvals.list_all():
            if gate.stage_id == stage_id:
                return gate
        return None

    def list_approvals(
        self,
        *,
        workflow_id: str | None = None,
        status: ApprovalStatus | str | None = None,
        stage_id: str | None = None,
    ) -> list[ApprovalGate]:
        """审批门清单 (workflow/status/stage 过滤; id 排序, 审计友好)。"""
        gates = self._approvals.list_all()
        if workflow_id is not None:
            gates = [g for g in gates if g.workflow_id == workflow_id]
        if status is not None:
            target = ApprovalStatus.parse(status)
            gates = [g for g in gates if g.status == target]
        if stage_id is not None:
            gates = [g for g in gates if g.stage_id == stage_id]
        return gates

    def has_pending_approval(self, workflow_id: str) -> bool:
        """workflow 是否有待审门 (PENDING — Runner 挂起守卫, 禁绕过审批门)。"""
        return any(
            g.status == ApprovalStatus.PENDING
            for g in self._approvals.list_all()
            if g.workflow_id == workflow_id
        )

    def has_rejected_approval(self, workflow_id: str) -> bool:
        """workflow 是否有否决门 (REJECTED — Runner 禁绕过守卫, 决定不可撤销)。"""
        return any(
            g.status == ApprovalStatus.REJECTED
            for g in self._approvals.list_all()
            if g.workflow_id == workflow_id
        )

    def request_approval(self, stage_id: str, *, comment: str = "") -> ApprovalGate:
        """创建审批门 (approval_required stage → PENDING + workflow PAUSED)。

        由 Runner 在 approval_required stage COMPLETED 后调用 (人工介入点);
        校验 (响亮, 防误挂/重复):
        - stage 必须存在 (NotFoundError)
        - stage.approval_required 必须为 True (非门禁阶段拒建)
        - 每 stage 至多一个门 (DuplicateError; COMPLETED 终态保证 Runner
          路径天然唯一, 手工重复调用防护)
        workflow ACTIVE → PAUSED (受控转换表); 发 org.approval.created
        (Runner 自动, source="org")。
        """
        stage = self.get_stage(stage_id)
        if not stage.approval_required:
            raise WorkflowStateError(
                f"stage {stage_id} does not require approval "
                f"(approval_required=False)"
            )
        if self.get_approval_by_stage(stage_id) is not None:
            raise DuplicateError(
                f"approval gate already exists for stage {stage_id}"
            )
        workflow = self.get_workflow(stage.workflow_id)
        gate = ApprovalGate(
            id=new_id("AG"),
            stage_id=stage.id,
            workflow_id=workflow.id,
            comment=comment,
        )
        self._approvals.save(gate)
        org_events.record_approval_created(self._logger, gate=gate, workflow=workflow)
        if workflow.status == WorkflowStatus.ACTIVE:
            self.transition_workflow(workflow.id, WorkflowStatus.PAUSED)
        return gate

    def approve_approval(
        self, gate_id: str, *, reviewer: str = "", comment: str = ""
    ) -> tuple[ApprovalGate, Workflow]:
        """审批放行 (→APPROVED 终态 + workflow 恢复 PAUSED→ACTIVE)。

        非 PENDING 门 → ApprovalStateError (终态决定不可撤销); 恢复复用
        受控转换表 paused→active (started 事件 from_status=paused — 既有
        语义); 已 ACTIVE 不重复转换 (幂等恢复)。返回 (gate, workflow)。
        """
        gate = self.get_approval(gate_id)
        updated = transition_approval(
            gate, ApprovalStatus.APPROVED, reviewer=reviewer, comment=comment
        )
        self._approvals.save(updated)
        workflow = self.get_workflow(gate.workflow_id)
        org_events.record_approval_approved(
            self._logger,
            gate=updated,
            workflow=workflow,
            reviewer=reviewer,
            comment=comment,
        )
        if workflow.status == WorkflowStatus.PAUSED:
            workflow = self.transition_workflow(workflow.id, WorkflowStatus.ACTIVE)
        return updated, workflow

    def reject_approval(
        self, gate_id: str, *, reviewer: str = "", comment: str = ""
    ) -> tuple[ApprovalGate, Workflow]:
        """审批否决 (→REJECTED 终态 + workflow FAILED 停止, 记录原因)。

        非 PENDING 门 → ApprovalStateError; workflow 停止复用既有合法路径
        PAUSED→ACTIVE→FAILED (两跳 — WORKFLOW_TRANSITIONS 零修改, 禁改核心
        约束); failed_reason = "approval rejected: <comment> (reviewer:
        <reviewer>)" 审计。返回 (gate, workflow)。
        """
        gate = self.get_approval(gate_id)
        updated = transition_approval(
            gate, ApprovalStatus.REJECTED, reviewer=reviewer, comment=comment
        )
        self._approvals.save(updated)
        workflow = self.get_workflow(gate.workflow_id)
        org_events.record_approval_rejected(
            self._logger,
            gate=updated,
            workflow=workflow,
            reviewer=reviewer,
            comment=comment,
        )
        if workflow.status == WorkflowStatus.PAUSED:
            workflow = self.transition_workflow(workflow.id, WorkflowStatus.ACTIVE)
        if workflow.status == WorkflowStatus.ACTIVE:
            reason = "approval rejected"
            if comment:
                reason += f": {comment}"
            reason += f" (reviewer: {reviewer or 'unknown'})"
            workflow = self.transition_workflow(
                workflow.id,
                WorkflowStatus.FAILED,
                reason=reason,
                event_extra={"stage_id": updated.stage_id},
            )
        return updated, workflow

    # ------------------------------------------------------------ 内部辅助

    def _require_project(self, project_id: str) -> None:
        if self._store.get_project(project_id) is None:
            raise NotFoundError(f"project not found: {project_id}")

    def _require_same_workflow(
        self, siblings: list[Stage], depends_on: list[str], workflow_id: str
    ) -> None:
        """依赖校验: 全部为本 workflow 已存在 stage (未定义/跨 workflow 拒绝)。"""
        known = {s.id for s in siblings}
        for dep in depends_on:
            if dep not in known:
                raise WorkflowDependencyError(
                    f"stage depends on undefined stage {dep!r} "
                    f"(workflow {workflow_id})"
                )

    @staticmethod
    def _reaches(start: str, node: str, by_id: dict[str, Stage]) -> bool:
        """从 node 出发沿 depends_on DFS, 能否回到 start (增量环检测)。"""
        if node == start:
            return True
        seen: set[str] = set()
        stack = [node]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for dep in by_id[cur].depends_on:
                if dep == start:
                    return True
                if dep not in seen:
                    stack.append(dep)
        return False

    def _append_stage_id(self, workflow_id: str, stage_id: str) -> None:
        """workflow.stage_ids 索引追加 (权威读取仍为 store 查询)。"""
        workflow = self.get_workflow(workflow_id)
        if stage_id in workflow.stage_ids:
            return
        updated = workflow.model_copy(
            update={"stage_ids": workflow.stage_ids + [stage_id], "updated_at": utcnow()}
        )
        self._workflows.save(updated)

    def _emit_workflow_transition(
        self,
        before: Workflow,
        after: Workflow,
        *,
        reason: str,
        extra: dict[str, Any] | None,
    ) -> None:
        """workflow 转换审计事件 (→active/completed/failed; paused 无独立事件)。"""
        extra = extra or {}
        if after.status == WorkflowStatus.ACTIVE:
            org_events.record_workflow_started(
                self._logger, workflow=after, from_status=before.status.value
            )
        elif after.status == WorkflowStatus.COMPLETED:
            org_events.record_workflow_completed(self._logger, workflow=after)
        elif after.status == WorkflowStatus.FAILED:
            org_events.record_workflow_failed(
                self._logger,
                workflow=after,
                stage_id=extra.get("stage_id", ""),
                reason=reason or after.failed_reason,
            )

    def _emit_stage_transition(
        self, workflow: Workflow, stage: Stage, *, reason: str
    ) -> None:
        """stage 转换审计事件 (→ready/running/completed; 其余状态无独立事件)。"""
        if stage.status == StageStatus.READY:
            org_events.record_workflow_stage_ready(self._logger, workflow=workflow, stage=stage)
        elif stage.status == StageStatus.RUNNING:
            org_events.record_workflow_stage_started(self._logger, workflow=workflow, stage=stage)
        elif stage.status == StageStatus.COMPLETED:
            org_events.record_workflow_stage_completed(
                self._logger, workflow=workflow, stage=stage
            )


# ------------------------------------------------------------------ Runner

#: Executor 调用契约: executor(stage, context) → dict[str, Any]
#:   stage: 待执行 Stage (role_id 指向 exec 注册表角色)
#:   context: {"workflow": Workflow, "inputs": [Artifact dict], "project_id": str}
#:   返回 dict 键 (KISS 单产物; "artifacts" 多产物可选):
#:     artifact_type: 产物类型 (缺省按 ROLE_OUTPUT_TYPES 角色推断)
#:     ref: 产物引用 (file:// / ref://)
#:     metadata: 契约校验载荷 (validate_artifact 校验; 失败 → stage FAILED)
#:     artifacts: list[dict] | None (多产物: 每项 type/ref/metadata/id)
#: 真实执行 S7-005 接入 (EmployeeExecutor 适配器); S7-003 编排壳只消费
#: 本契约, 不重写执行链 (约束)。
ExecutorFn = Callable[[Stage, dict[str, Any]], dict[str, Any]]


class WorkflowRunner:
    """组织级 Workflow Runner: 就绪判定 → Role Executor → Artifact 注册 → 推进。

    执行循环 (run): 读 workflow → DRAFT/PAUSED 自动转 ACTIVE → validate_dag
    (循环响亮拒绝) → 评估各 stage 就绪 (READY/BLOCKED) → 按 order 取首个
    READY → RUNNING → executor 调用 → 输出 Artifact 自动注册 (create →
    generated → validated; 契约失败 → stage FAILED) → COMPLETED → 推进。
    终止条件:
    - 全部 stage COMPLETED → workflow COMPLETED (终态)
    - 无 READY 且存在非终态 stage (BLOCKED) → workflow 保持 ACTIVE
      (等待外部输入/人工修复 — 编排壳不假装完成)
    - stage FAILED → workflow FAILED (failed_reason + stage_id 审计)
    - 步数保护: 每步执行一个 stage, 步数上限 = stage 数 + 1 (逻辑缺陷
      防护, 防无限循环); 超限 → WorkflowExecutionError

    终态语义 (幂等): COMPLETED → run 直接返回 (不重复执行); FAILED →
    WorkflowStateError (须先 pause 人工介入后重试 — 可 PAUSED 重试路径)。
    executor=None → 需执行时 WorkflowExecutionError (编排壳诚实边界,
    S7-005 接真实 Role Executor; 测试/编排场景注入 callable)。
    """

    def __init__(
        self,
        lifecycle: WorkflowLifecycle,
        *,
        executor: ExecutorFn | None = None,
        logger: Any = None,
        max_steps: int | None = None,
    ):
        self._lifecycle = lifecycle
        self._executor = executor
        self._logger = logger
        self._max_steps = max_steps

    @property
    def lifecycle(self) -> WorkflowLifecycle:
        return self._lifecycle

    # ------------------------------------------------------------------ run

    def run(self, workflow_id: str, *, max_steps: int | None = None) -> Workflow:
        """执行工作流 (全链推进; 返回终态/挂起 workflow)。

        S9-001 审批门守卫 (禁绕过): 待审门 PENDING → 直接返回挂起 workflow
        (不自动恢复执行); 否决门 REJECTED → WorkflowStateError 响亮拒绝
        (含 failed→paused→active 重试路径 — 审批决定不可撤销)。
        """
        workflow = self._lifecycle.get_workflow(workflow_id)
        if workflow.status == WorkflowStatus.COMPLETED:
            return workflow  # 幂等: 已完成不重复执行
        if self._lifecycle.has_rejected_approval(workflow_id):
            raise WorkflowStateError(
                f"workflow {workflow_id} has a rejected approval gate — "
                f"不可恢复 (审批否决为终态决定, 禁绕过审批门)"
            )
        if workflow.status == WorkflowStatus.FAILED:
            raise WorkflowStateError(
                f"failed workflow cannot run: {workflow_id} "
                f"(pause 后人工修复再恢复 — failed → paused → active 重试路径)"
            )
        if self._lifecycle.has_pending_approval(workflow_id):
            return workflow  # S9-001: 待审门挂起 — 等 approve/reject 再继续
        if workflow.status != WorkflowStatus.ACTIVE:
            workflow = self._lifecycle.activate(workflow_id)  # DRAFT/PAUSED → ACTIVE
        stages = self._lifecycle.list_stages(workflow_id)
        self._lifecycle.validate_dag(workflow_id)  # 循环依赖响亮拒绝 (执行前)
        cap = max_steps if max_steps is not None else (
            self._max_steps if self._max_steps is not None else len(stages) + 1
        )
        executed = 0
        while executed < cap:
            stages = self._lifecycle.list_stages(workflow_id)
            by_id = {s.id: s for s in stages}
            # 就绪判定 (READY/BLOCKED 评估, 幂等转换)
            ready_stage: Stage | None = None
            for stage in stages:
                if stage.status in (StageStatus.COMPLETED, StageStatus.FAILED):
                    continue
                if self._is_ready(stage, by_id):
                    if stage.status != StageStatus.READY:
                        self._lifecycle.transition_stage(stage.id, StageStatus.READY)
                    if ready_stage is None:
                        ready_stage = stage
                elif stage.status != StageStatus.BLOCKED:
                    self._lifecycle.transition_stage(stage.id, StageStatus.BLOCKED)
            if ready_stage is None:
                break  # 无可推进: 全部完成或存在阻塞 (workflow 保持 ACTIVE)
            self._execute_stage(workflow_id, ready_stage)
            executed += 1
            # S9-001: Approval Gate — approval_required stage COMPLETED →
            # 创建审批门 (PENDING) + workflow PAUSED (人工介入点; 返回挂起态)
            fresh = self._lifecycle.get_stage(ready_stage.id)
            if fresh.status == StageStatus.COMPLETED and fresh.approval_required:
                self._lifecycle.request_approval(ready_stage.id)
                return self._lifecycle.get_workflow(workflow_id)
        else:
            raise WorkflowExecutionError(
                f"workflow {workflow_id} exceeded max steps ({cap}) — "
                f"stage 计数保护触发 (防无限循环)"
            )
        workflow = self._lifecycle.get_workflow(workflow_id)
        stages = self._lifecycle.list_stages(workflow_id)
        if all(s.status == StageStatus.COMPLETED for s in stages):
            return self._lifecycle.transition_workflow(workflow_id, WorkflowStatus.COMPLETED)
        return workflow  # ACTIVE + BLOCKED (等待外部输入/修复)

    # ------------------------------------------------------------ 内部

    def _is_ready(self, stage: Stage, by_id: dict[str, Stage]) -> bool:
        """就绪判定: 全部 depends_on COMPLETED 且 input_artifacts 全部
        VALIDATED (同项目/空项目 — 项目隔离铁律, S7-001 空 project_id 兼容)。"""
        for dep_id in stage.depends_on:
            dep = by_id.get(dep_id)
            if dep is None or dep.status != StageStatus.COMPLETED:
                return False
        workflow = self._lifecycle.get_workflow(stage.workflow_id)
        for artifact_id in stage.input_artifacts:
            artifact = self._lifecycle.store.get_artifact(artifact_id)
            if artifact is None or artifact.status != ArtifactStatus.VALIDATED:
                return False
            if artifact.project_id not in ("", workflow.project_id):
                return False  # 跨项目输入拒绝 (项目隔离铁律)
        return True

    def _execute_stage(self, workflow_id: str, stage: Stage) -> None:
        """单 stage 执行: RUNNING → executor → 输出注册 → COMPLETED/FAILED。"""
        if self._executor is None:
            # 编排壳诚实边界: 不假装执行 — 在流转 RUNNING 前响亮拒绝
            # (executor=None 且需执行 → WorkflowExecutionError 向上传播,
            # 状态保持 READY, 注入 executor 后可直接重跑)
            raise WorkflowExecutionError(
                f"no executor configured for stage {stage.id} "
                f"(role={stage.role_id}) — S7-003 编排壳不执行, "
                f"S7-005 接入 Role Executor; 编排场景注入 executor callable"
            )
        self._lifecycle.transition_stage(stage.id, StageStatus.RUNNING)
        workflow = self._lifecycle.get_workflow(workflow_id)
        try:
            result = self._invoke_executor(stage, workflow)
            artifact_ids = self._register_outputs(workflow, stage, result)
        except WorkflowExecutionError as exc:
            self._fail_stage(workflow, stage, str(exc))
            return
        except Exception as exc:  # noqa: BLE001 — executor 任意异常 → stage 失败
            self._fail_stage(workflow, stage, f"{type(exc).__name__}: {exc}")
            return
        # 输出产物引用回写 + 完成 (重新取最新 stage — 执行期状态已流转,
        # 用旧对象回写会覆盖 RUNNING → PENDING, 破坏 COMPLETED 转换)
        fresh = self._lifecycle.get_stage(stage.id)
        updated = fresh.model_copy(
            update={
                "output_artifacts": list(
                    dict.fromkeys(fresh.output_artifacts + artifact_ids)
                ),
                "updated_at": utcnow(),
            }
        )
        self._lifecycle.store.save_stage(updated)
        self._lifecycle.transition_stage(stage.id, StageStatus.COMPLETED)

    def _invoke_executor(self, stage: Stage, workflow: Workflow) -> dict[str, Any]:
        """Role Executor 调用 (注入 callable 契约; 不重写 EmployeeExecutor)。"""
        if self._executor is None:
            raise WorkflowExecutionError(
                f"no executor configured for stage {stage.id} "
                f"(role={stage.role_id}) — S7-003 编排壳不执行, "
                f"S7-005 接入 Role Executor; 编排场景注入 executor callable"
            )
        inputs = [
            self._lifecycle.registry.get(aid).to_dict()
            for aid in stage.input_artifacts
        ]
        context: dict[str, Any] = {
            "workflow": workflow,
            "project_id": workflow.project_id,
            "inputs": inputs,
        }
        result = self._executor(stage, context)
        if result is None:
            raise WorkflowExecutionError(f"executor returned None for stage {stage.id}")
        return result

    def _register_outputs(
        self, workflow: Workflow, stage: Stage, result: dict[str, Any]
    ) -> list[str]:
        """输出 Artifact 自动注册: create → generated → validated (契约驱动)。

        单产物 (artifact_type/ref/metadata) 或多产物 (artifacts[]); 契约
        校验失败 → 产物 INVALID → WorkflowExecutionError (stage FAILED 由
        调用方处理)。producer_role=stage.role_id, project_id 继承 workflow。
        """
        specs = result.get("artifacts")
        if specs is None:
            specs = [
                {
                    "type": result.get("artifact_type"),
                    "ref": result.get("ref", ""),
                    "metadata": result.get("metadata", {}),
                    "id": result.get("artifact_id"),
                }
            ]
        registered: list[str] = []
        for spec in specs:
            type_name = spec.get("type") or ROLE_OUTPUT_TYPES.get(stage.role_id, "")
            if not type_name:
                raise WorkflowExecutionError(
                    f"stage {stage.id} output artifact type missing "
                    f"(executor result must declare artifact_type; "
                    f"no default for role {stage.role_id!r})"
                )
            artifact = self._lifecycle.registry.create(
                stage_id=stage.id,
                type_=type_name,
                project_id=workflow.project_id,
                ref=spec.get("ref", ""),
                producer_role=stage.role_id,
                metadata=spec.get("metadata") or {},
                artifact_id=spec.get("id"),
            )
            self._lifecycle.registry.mark_generated(artifact.id)
            artifact, validation = self._lifecycle.registry.validate(artifact.id)
            if not validation.ok:
                raise WorkflowExecutionError(
                    f"output artifact {artifact.id} contract failed: "
                    f"missing={validation.missing} errors={validation.errors}"
                )
            registered.append(artifact.id)
        return registered

    def _fail_stage(self, workflow: Workflow, stage: Stage, reason: str) -> None:
        """stage FAILED → workflow FAILED (failed_reason + stage_id 审计)。"""
        self._lifecycle.transition_stage(stage.id, StageStatus.FAILED, reason=reason)
        self._lifecycle.transition_workflow(
            workflow.id,
            WorkflowStatus.FAILED,
            reason=reason,
            event_extra={"stage_id": stage.id},
        )


# ------------------------------------------------------------------ Dev↔Tester Loop (S7-004)

#: 自动修复轮数上限 (架构 §4: ≤2 轮防无限; 测试轮数上限 = 该值 + 1)
DEFAULT_MAX_REPAIR_ROUNDS = 2


def build_dev_test_workflow(
    lifecycle: WorkflowLifecycle,
    project_id: str,
    name: str,
    *,
    workflow_id: str | None = None,
) -> Workflow:
    """创建 Dev↔Tester Loop workflow (初始对: developer stage → tester stage)。

    修复轮 (repair developer + retest tester) 由 DevTestLoopRunner 按需动态
    创建 (≤ max_repair_rounds, 计数保护); 通过后剩余阶段 (如 release 前置)
    交回 base Runner 推进。
    """
    workflow = lifecycle.create_workflow(project_id, name, workflow_id=workflow_id)
    dev = lifecycle.create_stage(workflow.id, "developer", name="develop")
    lifecycle.create_stage(workflow.id, "tester", name="test", depends_on=[dev.id])
    return workflow


class DevTestLoopRunner(WorkflowRunner):
    """Developer↔Tester Loop 编排 (S7-004): dev → test → (bug → repair → retest)。

    复用 S7-003 WorkflowRunner 执行原语 (_is_ready/_execute_stage/_invoke_executor/
    _register_outputs — 同一 executor 注入点 + 产物自动注册 + 就绪判定),
    不重写 Runner 核心 run() 循环 (约束: 只扩展)。

    循环语义:
    - 初始对: developer stage (develop) → tester stage (test), 经
      build_dev_test_workflow 创建。
    - 每轮: 执行 developer 阶段 (产出 code 产物, 自动接线为 test 输入) →
      执行 tester 阶段 (产出 test + bug_report 产物)。
    - tester 通过 (无 bug_report 产物) → 剩余阶段 (如 release 前置) 交回
      base Runner 推进 → workflow COMPLETED。
    - tester 失败 (有 bug_report) 且修复轮次未耗尽 → 动态创建 repair
      (developer, 输入 = bug_report 产物) + retest (tester) 阶段 → 下一轮。
    - 修复轮次耗尽 (默认 ≤2 轮自动修复 = 3 次测试) 仍有缺陷 → workflow
      FAILED (质量门禁, failed_reason + stage_id 审计) — 禁无限循环。
    - 计数保护: 测试轮数上限 = max_repair_rounds + 1; 中断重跑幂等 (已
      COMPLETED 轮次计入, 不超限); 重跑后仍有未决缺陷 → 保持 ACTIVE
      (不假装完成, 等待人工介入)。
    """

    def __init__(
        self,
        lifecycle: WorkflowLifecycle,
        *,
        executor: ExecutorFn | None = None,
        logger: Any = None,
        max_repair_rounds: int = DEFAULT_MAX_REPAIR_ROUNDS,
    ) -> None:
        super().__init__(lifecycle, executor=executor, logger=logger)
        self._max_repair_rounds = max(0, int(max_repair_rounds))

    @property
    def max_repair_rounds(self) -> int:
        """自动修复轮数上限 (计数保护配置)。"""
        return self._max_repair_rounds

    def run(self, workflow_id: str, *, max_steps: int | None = None) -> Workflow:
        """执行 Dev↔Tester Loop (轮次计数保护; 返回终态/挂起 workflow)。

        max_steps 透传 base Runner (测试通过后剩余阶段推进的步数上限);
        Loop 本身的防无限保护 = 轮次计数 (max_repair_rounds + 1), 与 base
        Runner 的步数保护语义一致。
        """
        workflow = self._lifecycle.get_workflow(workflow_id)
        if workflow.status == WorkflowStatus.COMPLETED:
            return workflow  # 幂等: 已完成不重复执行
        if self._lifecycle.has_rejected_approval(workflow_id):
            raise WorkflowStateError(
                f"workflow {workflow_id} has a rejected approval gate — "
                f"不可恢复 (审批否决为终态决定, 禁绕过审批门)"
            )
        if workflow.status == WorkflowStatus.FAILED:
            raise WorkflowStateError(
                f"failed workflow cannot run: {workflow_id} "
                f"(pause 后人工介入再恢复 — failed → paused → active 重试路径)"
            )
        if self._lifecycle.has_pending_approval(workflow_id):
            return workflow  # S9-001: 待审门挂起 — 等 approve/reject 再继续
        if workflow.status != WorkflowStatus.ACTIVE:
            workflow = self._lifecycle.activate(workflow_id)  # DRAFT/PAUSED → ACTIVE
        stages = self._lifecycle.list_stages(workflow_id)
        if not stages:
            return self._lifecycle.transition_workflow(workflow_id, WorkflowStatus.COMPLETED)
        self._lifecycle.validate_dag(workflow_id)  # 循环依赖响亮拒绝

        max_test_rounds = self._max_repair_rounds + 1
        # 幂等恢复: 已 COMPLETED 的 tester 阶段计入已执行轮次 (中断重跑不超限)
        executed_rounds = sum(
            1 for s in stages
            if s.role_id == "tester" and s.status == StageStatus.COMPLETED
        )

        while executed_rounds < max_test_rounds:
            workflow = self._lifecycle.get_workflow(workflow_id)
            if workflow.status != WorkflowStatus.ACTIVE:
                break  # 已 FAILED (stage 执行失败) — 返回既有终态
            stages = self._lifecycle.list_stages(workflow_id)
            dev = next(
                (s for s in stages
                 if s.role_id == "developer"
                 and s.status not in (StageStatus.COMPLETED, StageStatus.FAILED)),
                None,
            )
            test = next(
                (s for s in stages
                 if s.role_id == "tester"
                 and s.status not in (StageStatus.COMPLETED, StageStatus.FAILED)),
                None,
            )
            if dev is None or test is None:
                break  # 阶段不足 → 兜底完成/挂起判定

            # --- 自动接线: 修复轮 dev 输入 = 前序 test 的 bug_report 产物 ---
            prev_tests = [
                s for s in stages
                if s.role_id == "tester" and s.status == StageStatus.COMPLETED
            ]
            if prev_tests:
                prev = prev_tests[-1]
                bug_ids = [
                    a.id for a in self._lifecycle.stage_artifacts(prev.id)
                    if a.type.value == "bug_report" and a.status == ArtifactStatus.VALIDATED
                ]
                if bug_ids:
                    dev = self._wire(dev, depends_on=[prev.id], input_artifacts=bug_ids)
            by_id = {s.id: s for s in self._lifecycle.list_stages(workflow_id)}
            if not self._is_ready(dev, by_id):
                self._to_blocked(dev)
                break  # 依赖/输入未满足 → 保持 ACTIVE (等待外部输入, 诚实)
            if dev.status != StageStatus.READY:
                self._lifecycle.transition_stage(dev.id, StageStatus.READY)
            self._execute_stage(workflow_id, dev)
            if self._lifecycle.get_stage(dev.id).status == StageStatus.FAILED:
                return self._lifecycle.get_workflow(workflow_id)  # workflow 已 FAILED

            # --- test 接线: 输入 = 本 dev 的 code 产物 (自动注册后回查) ---
            test = self._lifecycle.get_stage(test.id)
            code_artifacts = [
                a for a in self._lifecycle.stage_artifacts(dev.id)
                if a.type.value == "code" and a.status == ArtifactStatus.VALIDATED
            ]
            if not code_artifacts:
                self._to_blocked(test)
                break  # dev 未产出 code 产物 → 测试无可测输入 (诚实阻塞)
            test = self._wire(test, depends_on=[dev.id], input_artifacts=[code_artifacts[0].id])
            by_id = {s.id: s for s in self._lifecycle.list_stages(workflow_id)}
            if not self._is_ready(test, by_id):
                self._to_blocked(test)
                break
            if test.status != StageStatus.READY:
                self._lifecycle.transition_stage(test.id, StageStatus.READY)
            self._execute_stage(workflow_id, test)
            if self._lifecycle.get_stage(test.id).status == StageStatus.FAILED:
                return self._lifecycle.get_workflow(workflow_id)
            executed_rounds += 1

            # --- 缺陷判定 (bug_report 产物 = 质量门禁) ---
            bugs = [
                a for a in self._lifecycle.stage_artifacts(test.id)
                if a.type.value == "bug_report" and a.status == ArtifactStatus.VALIDATED
            ]
            if not bugs:
                # 测试通过 → 剩余阶段 (如 release 前置) 交回 base Runner 推进
                return super().run(workflow_id, max_steps=max_steps)
            if executed_rounds >= max_test_rounds:
                # 修复轮次耗尽仍有缺陷 → 质量门禁失败 (响亮, 不假装完成)
                return self._lifecycle.transition_workflow(
                    workflow_id,
                    WorkflowStatus.FAILED,
                    reason=(
                        f"test loop exhausted after {executed_rounds} rounds: "
                        f"{len(bugs)} bug(s) remaining (max repair rounds="
                        f"{self._max_repair_rounds})"
                    ),
                    event_extra={"stage_id": test.id},
                )
            # 创建修复轮: repair (developer, 输入 = bug_report) + retest (tester)
            repair = self._lifecycle.create_stage(
                workflow_id,
                "developer",
                name=f"repair {executed_rounds}",
                depends_on=[test.id],
                input_artifacts=[a.id for a in bugs],
            )
            self._lifecycle.create_stage(
                workflow_id,
                "tester",
                name=f"retest {executed_rounds}",
                depends_on=[repair.id],
            )

        # 兜底: 阶段不足/阻塞 — 全部 COMPLETED 且无未决缺陷 → COMPLETED;
        # 否则保持 ACTIVE (诚实, 不假装完成; 未决缺陷交人工介入)
        workflow = self._lifecycle.get_workflow(workflow_id)
        stages = self._lifecycle.list_stages(workflow_id)
        if all(s.status == StageStatus.COMPLETED for s in stages):
            last_test = [s for s in stages if s.role_id == "tester"]
            unresolved = last_test and any(
                a.type.value == "bug_report" and a.status == ArtifactStatus.VALIDATED
                for a in self._lifecycle.stage_artifacts(last_test[-1].id)
            )
            if not unresolved:
                return self._lifecycle.transition_workflow(workflow_id, WorkflowStatus.COMPLETED)
        return workflow  # ACTIVE (等待外部输入 / 人工介入)

    # ------------------------------------------------------------ 内部辅助

    def _wire(
        self,
        stage: Stage,
        *,
        depends_on: list[str] | None = None,
        input_artifacts: list[str] | None = None,
    ) -> Stage:
        """阶段 DAG 接线 (depends_on/input_artifacts 数据更新, 非状态转换)。

        循环编排层动态接线: dev ← bug_report 产物 / test ← code 产物。
        """
        updates: dict[str, Any] = {"updated_at": utcnow()}
        if depends_on is not None:
            updates["depends_on"] = list(depends_on)
        if input_artifacts is not None:
            updates["input_artifacts"] = list(input_artifacts)
        updated = stage.model_copy(update=updates)
        self._lifecycle.store.save_stage(updated)
        return updated

    def _to_blocked(self, stage: Stage) -> None:
        """阶段置 BLOCKED (依赖/输入未满足; 幂等, 不重复发事件)。"""
        if stage.status != StageStatus.BLOCKED:
            self._lifecycle.transition_stage(stage.id, StageStatus.BLOCKED)


def workflow_files(org_dir: str | Path) -> list[Path]:
    """workflow 数据文件 (存在者; 测试/审计用 — workflows.json)。"""
    path = Path(org_dir) / "workflows.json"
    return [path] if path.exists() else []
