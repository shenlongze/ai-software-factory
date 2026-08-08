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
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from pydantic import Field, field_validator

from . import events as org_events
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
        """执行工作流 (全链推进; 返回终态/挂起 workflow)。"""
        workflow = self._lifecycle.get_workflow(workflow_id)
        if workflow.status == WorkflowStatus.COMPLETED:
            return workflow  # 幂等: 已完成不重复执行
        if workflow.status == WorkflowStatus.FAILED:
            raise WorkflowStateError(
                f"failed workflow cannot run: {workflow_id} "
                f"(pause 后人工修复再恢复 — failed → paused → active 重试路径)"
            )
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


def workflow_files(org_dir: str | Path) -> list[Path]:
    """workflow 数据文件 (存在者; 测试/审计用 — workflows.json)。"""
    path = Path(org_dir) / "workflows.json"
    return [path] if path.exists() else []
