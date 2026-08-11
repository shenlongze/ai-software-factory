"""factory-org/org/execution.py — Execution Domain Model (S10-011 Task 001)。

设计依据 (唯一):
- docs/sprint10/S10-011-architecture-design.md §二 4/5/6/7 (7 项确认)
- AF-PRD-v1.md 4.8 (Execution Engine)

模型:
- WorkflowInstance: 执行实例实体 + 受控状态机
  CREATED → RUNNING → SUCCESS / FAILED / CANCELLED (非法转换拒绝);
  字段 instance_id/task_id/workflow_id/agent/skill/mcp/status/start_time/
  end_time/result/created_at (设计 §4)
- ExecutionPlan: 执行计划 (tasks 有序列表 + parallel_batch 批 + max_parallel
  + waiting_dependency 未满足原因; S10-011 Task 002)
- Scheduler 纯函数 (S10-011 §二 1): plan_tasks (只选 READY + dependency 满足
  + priority 排序 + max_parallel 分批) + can_execute (手动检查 ok/reason)
- Dispatcher 纯函数 (S10-011 §二 2/3 — Task 003): dispatch_task (can_execute
  校验 → 依赖未满足/非 READY 抛 DispatchError; 创建 WorkflowInstance CREATED
  + bindings agent/skill/mcp 选择 (取第一个, 空绑定可执行) + workflow_id
  缺省 software-development-v1) + WorkflowInstanceStore (workflow-instance/
  {id}.json 目录信源 — save/load/list, 原子写 + 失败安全)
- ExecutionLock: per-project 进程内互斥 (threading.RLock — 同线程重入安全);
  同项目写互斥, 不同项目各自独立锁互不阻塞 (设计 §7, 跨进程锁 S10-012+);
  Task 005 完善: acquire(project_id, timeout=None) -> bool (超时不阻塞返回
  False) + locked(project_id, timeout) 上下文管理器 (超时抛 LockTimeoutError);
  写路径集成: dispatch_task / execute_instance 提供 project_id 时持锁,
  transition_task_locked 封装 Task 状态更新; ExecutionEngine 门面
  (execute_project_tasks: plan→dispatch→execute 持锁串行化)
- RuntimeStore: workspace/projects/{slug}/runtime/ 三类 JSON 原子写
  (task-execution/{task_id}.json / agent-execution/{instance_id}.json /
  workflow-execution/{instance_id}.json) — 运行上下文 (可恢复), 失败安全
  (缺失/损坏 → None; 设计 §5)
- AuditStore: workspace/projects/{slug}/logs/audit.log 追加不可变
  (记录 {time, actor, action, entity, input, output, result}; 设计 §6)
  Task 006 完善: list_audit (按 time 排序 + actor/entity/action 过滤) +
  读取返回副本 (不可变语义 — 外部修改不影响落盘事实)
- NotificationSink: 通知预留接口 (Task 006 — 本 Sprint 不实现真实渠道):
  notify(project_id, event, payload) 默认 no-op; ExecutionEngine 可注入
  (notification=sink); 门面终态通知 event="task.completed"/"task.failed"
  (真实渠道 S10-012+ 注入替换)
- 全链路审计 (Task 006): dispatch_task (actor=dispatcher,
  action=instance.dispatched) + ExecutionEngine 门面 plan (actor=scheduler,
  action=plan.created) + Task 状态联动 (actor=executor, action=task.linked)
  均写 audit.log — scheduler/dispatcher/executor 每转换可审计

约束: 本模块零 Core 依赖 (stdlib + pydantic + org.models, Removal Isolation);
目录在项目空间 workspace/projects/{slug}/ 下 (与 org/space.py 布局一致 —
runtime/ 与 logs/ 平级); 原子写 = 临时文件 + os.replace (同 org/store.py 模式);
状态机受控 — 非法转换 ValueError 拒绝。
"""

from __future__ import annotations

import copy
import json
import logging
import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterator

from pydantic import Field, ValidationError, field_validator

from .models import _OrgModel, _norm_list, new_id, utcnow
from .management import Task, TaskStatus, _PRIORITY_RANK, transition_task

if TYPE_CHECKING:  # 仅类型标注 (运行时 duck-type registry.get_capability, 零耦合)
    from .capabilities import CapabilityRegistry

_LOGGER = logging.getLogger(__name__)

# ------------------------------------------------------------------ 枚举


class WorkflowInstanceStatus(str, Enum):
    """Workflow Instance 生命周期状态 (S10-011 §4: 单向受控流转)。

    CREATED → RUNNING → SUCCESS / FAILED / CANCELLED; 三个终态不可逆。
    """

    CREATED = "created"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def parse(cls, value: Any) -> "WorkflowInstanceStatus":
        """宽容解析: 大小写不敏感 (RUNNING → running); 枚举对象直接返回; 非法抛 ValueError。"""
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(
                f"invalid workflow instance status: {value!r} (expected one of: {valid})"
            ) from None


# ------------------------------------------------------------------ 实体


class WorkflowInstance(_OrgModel):
    """Workflow Instance 实体 (S10-011 §4 — Dispatcher 产出, Executor 消费)。

    instance_id: 实例唯一 id; task_id/workflow_id: 归属引用; agent/skill/mcp:
    binding 引用 (S10-009 Project.bindings, 可为空); status: 生命周期状态;
    start_time/end_time: 运行窗口 (进入 RUNNING / 终态时记录); result: 执行结果。
    """

    instance_id: str
    task_id: str
    workflow_id: str = ""
    agent: str = ""
    skill: str = ""
    mcp: str = ""
    status: WorkflowInstanceStatus = WorkflowInstanceStatus.CREATED
    start_time: datetime | None = None
    end_time: datetime | None = None
    result: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    capability_snapshot: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> WorkflowInstanceStatus:
        return WorkflowInstanceStatus.parse(v)


#: 受控状态转换表 (S10-011 §4; 三个终态无任何合法去向 — 不可逆)。
#: key=当前态, value=合法目标态元组。
WORKFLOW_INSTANCE_TRANSITIONS: dict[
    WorkflowInstanceStatus, tuple[WorkflowInstanceStatus, ...]
] = {
    WorkflowInstanceStatus.CREATED: (
        WorkflowInstanceStatus.RUNNING,
        WorkflowInstanceStatus.CANCELLED,
    ),
    WorkflowInstanceStatus.RUNNING: (
        WorkflowInstanceStatus.SUCCESS,
        WorkflowInstanceStatus.FAILED,
        WorkflowInstanceStatus.CANCELLED,
    ),
    WorkflowInstanceStatus.SUCCESS: (),
    WorkflowInstanceStatus.FAILED: (),
    WorkflowInstanceStatus.CANCELLED: (),
}

#: 终态集合 (进入终态时记录 end_time)。
_TERMINAL_STATUSES: frozenset[WorkflowInstanceStatus] = frozenset(
    {
        WorkflowInstanceStatus.SUCCESS,
        WorkflowInstanceStatus.FAILED,
        WorkflowInstanceStatus.CANCELLED,
    }
)


def transition_instance(
    instance: WorkflowInstance,
    target: WorkflowInstanceStatus | str,
    *,
    result: str = "",
) -> WorkflowInstance:
    """受控状态转换 (纯函数 — 返回新实例, 原对象不变)。

    - 目标态不在 WORKFLOW_INSTANCE_TRANSITIONS[当前态] → ValueError
      (跳级/回退/终态后/同态 — 非法拒绝)
    - 进入 RUNNING 且 start_time 未设 → 记录 start_time (运行窗口起点)
    - 进入终态 (SUCCESS/FAILED/CANCELLED) 且 end_time 未设 → 记录 end_time
    - result 非空 → 写入实例 result (失败原因/成功摘要)
    """
    from_status = instance.status
    target_status = WorkflowInstanceStatus.parse(target)
    if target_status not in WORKFLOW_INSTANCE_TRANSITIONS[from_status]:
        raise ValueError(
            f"illegal workflow instance transition: "
            f"{from_status.value} -> {target_status.value} "
            f"(allowed: {[s.value for s in WORKFLOW_INSTANCE_TRANSITIONS[from_status]]})"
        )
    now = utcnow()
    update: dict[str, Any] = {"status": target_status}
    if target_status == WorkflowInstanceStatus.RUNNING and instance.start_time is None:
        update["start_time"] = now
    if target_status in _TERMINAL_STATUSES and instance.end_time is None:
        update["end_time"] = now
    if result:
        update["result"] = result
    return instance.model_copy(update=update)


class PlanTask(_OrgModel):
    """计划内单任务条目 (S10-011 §1: {task_id, agent_hint, order})。"""

    task_id: str
    agent_hint: str = ""
    order: int = 0


class ExecutionPlan(_OrgModel):
    """执行计划 (S10-011 §1 — Scheduler 纯函数输出)。

    tasks: 有序执行列表 (调度顺序 = 执行顺序); parallel_batch: 可并行批
    (每批 task_id 列表); max_parallel: 同项目最大并行数 (缺省 5,
    workspace/settings 可覆盖); waiting_dependency: 未满足依赖的 READY
    任务 → 原因 (S10-011 Task 002, 验收场景 2 — 不入选但可解释)。
    """

    plan_id: str
    project_id: str = ""
    tasks: list[PlanTask] = Field(default_factory=list)
    parallel_batch: list[list[str]] = Field(default_factory=list)
    max_parallel: int = 5
    waiting_dependency: dict[str, str] = Field(default_factory=dict)

    @field_validator("tasks", "parallel_batch", mode="before")
    @classmethod
    def _lists_none(cls, v: Any) -> Any:
        return _norm_list(v)

    @field_validator("waiting_dependency", mode="before")
    @classmethod
    def _waiting_none(cls, v: Any) -> Any:
        return v if v is not None else {}


# ------------------------------------------------------------------ Scheduler 纯函数 (S10-011 Task 002)


def _unsatisfied_deps(task: Task, statuses: dict[str, TaskStatus]) -> list[str]:
    """未满足依赖列表: dependency 中非 DONE (含不在列表的未知 id) 的前置任务。"""
    return [dep for dep in task.dependency if statuses.get(dep) != TaskStatus.DONE]


def _waiting_reason(unsatisfied: list[str]) -> str:
    """依赖未满足原因 (验收场景 2: manual 执行返回原因)。"""
    return "Waiting dependency Task " + ", Task ".join(unsatisfied)


def can_execute(task: Task, all_tasks: list[Task]) -> tuple[bool, str]:
    """手动执行检查 (纯函数, 无副作用) → (ok, reason)。

    - READY 且依赖全部 DONE (或无依赖) → (True, "")
    - 依赖未满足 → (False, "Waiting dependency Task X"[, "Task Y"...])
    - 非 READY (BLOCKED/TODO/IN_PROGRESS/REVIEW/DONE) → (False, 状态原因)
      (BLOCKED 不执行 — S10-011 §二 1 / 验收场景 3)
    """
    if task.status != TaskStatus.READY:
        return False, f"task not ready (status: {task.status.value})"
    statuses = {t.id: t.status for t in all_tasks}
    unsatisfied = _unsatisfied_deps(task, statuses)
    if unsatisfied:
        return False, _waiting_reason(unsatisfied)
    return True, ""


def plan_tasks(tasks: list[Task], max_parallel: int = 5) -> ExecutionPlan:
    """生成执行计划 (S10-011 §二 1 — Scheduler 纯函数, 无副作用, 不改入参)。

    规则 (按序):
    1. 只选 READY 任务 (TODO/IN_PROGRESS/REVIEW/DONE/BLOCKED 不入选)
    2. dependency 必须满足 (依赖任务全部 DONE; 未知 id 视为未满足)
    3. BLOCKED 不执行 (非 READY 一律不入选)
    4. priority 排序: P0>P1>P2>P3 (同 priority → 输入序稳定 = 创建序)
    5. parallel_batch: 按 max_parallel (缺省 5, ≤0 防御按 1) 顺序分批
    6. 依赖未满足的 READY 任务不入选, 但记录 waiting_dependency[task_id] 原因
    """
    parallel = max(1, int(max_parallel))
    statuses = {t.id: t.status for t in tasks}
    selected: list[Task] = []
    waiting: dict[str, str] = {}
    for t in tasks:
        if t.status != TaskStatus.READY:
            continue
        unsatisfied = _unsatisfied_deps(t, statuses)
        if unsatisfied:
            waiting[t.id] = _waiting_reason(unsatisfied)
        else:
            selected.append(t)
    selected.sort(key=lambda t: _PRIORITY_RANK.get(t.priority, 99))  # 稳定 → 同 priority 保持创建序
    plan_tasks_out = [
        PlanTask(task_id=t.id, agent_hint=t.assignee, order=i)
        for i, t in enumerate(selected, start=1)
    ]
    batches = [
        [pt.task_id for pt in plan_tasks_out[i : i + parallel]]
        for i in range(0, len(plan_tasks_out), parallel)
    ]
    return ExecutionPlan(
        plan_id=new_id("plan"),
        tasks=plan_tasks_out,
        parallel_batch=batches,
        max_parallel=parallel,
        waiting_dependency=waiting,
    )


# ------------------------------------------------------------------ Dispatcher (S10-011 Task 003)


class DispatchError(Exception):
    """Dispatcher 拒绝分发 (任务不可执行)。

    reason: 拒绝原因 (来自 can_execute — 依赖未满足
    "Waiting dependency Task X" / 非 READY 状态原因 / BLOCKED 不执行)。
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _first_binding_ref(bindings: dict[str, Any] | None, key: str, ref_key: str) -> str:
    """bindings.{key} 列表取第一个引用 (agent/skill/mcp; 设计 §3)。

    - 条目为字符串 → 直接用
    - 条目为 dict (如 {agent_ref, role} — project-lifecycle.md) → 优先
      {ref_key}, 回退 "ref"
    - bindings 缺失 / 非列表 / 空列表 / 无法解析 → "" (无绑定, 可执行)
    """
    if not bindings:
        return ""
    entries = bindings.get(key)
    if not isinstance(entries, list) or not entries:
        return ""
    first = entries[0]
    if isinstance(first, str):
        return first
    if isinstance(first, dict):
        for k in (ref_key, "ref"):
            val = first.get(k)
            if isinstance(val, str) and val:
                return val
    return ""


def _workflow_ref(bindings: dict[str, Any] | None, workflow_id: str) -> str:
    """workflow_id 选择: bindings.workflow.workflow_ref 优先, 否则参数缺省。

    兼容 PRD 4.8 / project-lifecycle.md 的 workflow_instance 键形式
    ({workflow_ref: software-development-v1, parameters})。
    """
    if bindings:
        wf = bindings.get("workflow")
        if not isinstance(wf, dict):
            wf = bindings.get("workflow_instance")
        if isinstance(wf, dict):
            ref = wf.get("workflow_ref") or wf.get("ref")
            if isinstance(ref, str) and ref:
                return ref
        elif isinstance(wf, str) and wf:
            return wf
    return workflow_id


# ------------------------------------------------------------------ Capability Resolver (S10-012 Task 007-001)


#: binding kind 规范名 (Resolver 支持五类 — Industry 不参与执行绑定)。
_CAPABILITY_RESOLVE_KINDS: tuple[str, ...] = (
    "agent",
    "skill",
    "mcp",
    "workflow",
    "llm_config",
)

#: binding kind 复数别名 → 规范名 (大小写/连字符由 _normalize_binding_kind 处理)。
_CAPABILITY_KIND_PLURALS: dict[str, str] = {
    "agents": "agent",
    "skills": "skill",
    "mcps": "mcp",
    "workflows": "workflow",
    "llm_configs": "llm_config",
    "llms": "llm_config",
}


def _normalize_binding_kind(kind: Any) -> str:
    """binding kind 规范化: 非空 + 小写 + "-" → "_" + 复数别名 → 规范名。

    "LLM-CONFIG" → "llm_config"; "skills" → "skill"; 未知原样返回
    (由 _CAPABILITY_RESOLVE_KINDS 白名单拒绝)。
    """
    if not isinstance(kind, str) or not kind.strip():
        raise ValueError("capability binding kind must be a non-empty string")
    key = kind.strip().lower().replace("-", "_")
    return _CAPABILITY_KIND_PLURALS.get(key, key)


def _binding_ref_id(binding_ref: Any, ref_key: str) -> tuple[str, str | None]:
    """binding reference → (ref_id, version_pin)。

    - 字符串 (旧格式裸引用) → (原字符串, None)
    - dict ({agent_ref/skill_ref/... 或 {id, version?}} — 设计 §四
      CapabilityBinding 引用) → 优先 {ref_key}, 回退 "ref"/"id" + 可选
      "version" pin
    - 无法解析 → ("", None) (无有效引用, 不进入解析/快照)
    """
    if isinstance(binding_ref, str):
        return binding_ref, None
    if isinstance(binding_ref, dict):
        for k in (ref_key, "ref", "id"):
            val = binding_ref.get(k)
            if isinstance(val, str) and val:
                version = binding_ref.get("version")
                return val, (version if isinstance(version, str) and version else None)
    return "", None


@dataclass(frozen=True)
class CapabilityResolution:
    """Resolver 输出: binding reference → Registry Capability 实体解析结果。

    - kind: 规范化 binding kind (agent|skill|mcp|workflow|llm_config)
    - ref_id: binding 引用的 id (解析输入); id: 实体 id (解析成功 == ref_id)
    - name/version/status: 实体字段 (解析失败 → ""; 仅 Skill 带 version,
      其余实体 Registry 无 version 字段 → "")
    - metadata: 实体全量字段 (entity.to_dict() — 实体无独立 metadata 字段,
      Task 001 约定以全量字段输出)
    - version_pin: binding dict 显式 pin 的 version (无 → None)
    - entity: 解析到的 CapabilityEntity (失败 → None)
    - resolved: 实体是否解析成功 (registry 有对应 id)
    """

    kind: str
    ref_id: str
    id: str = ""
    name: str = ""
    version: str = ""
    status: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    version_pin: str | None = None
    entity: Any = None  # CapabilityEntity | None (仅运行时, 不序列化)

    @property
    def resolved(self) -> bool:
        """是否解析到 Registry 实体。"""
        return self.entity is not None


def resolve_capability(
    binding_ref: Any,
    registry: Any,
    *,
    kind: str,
    ref_key: str = "ref",
) -> CapabilityResolution | None:
    """binding reference → Registry Capability 实体解析 (S10-012 Task 007-001)。

    输入:
    - binding_ref: 字符串 (旧格式裸引用) 或 dict ({agent_ref/skill_ref/...
      或 {id, version?}} — version pin 可选, 可复现)
    - registry: CapabilityRegistry (统一门面 get_capability — 大小写/复数
      别名已处理; 缺失实体 → None)
    - kind: binding 类型 (agent|skill|mcp|workflow|llm_config; 大小写/复数
      别名宽容; 未知 → ValueError 显式暴露)
    - ref_key: dict 引用键名 (agent_ref/skill_ref/mcp_ref/workflow_ref/
      llm_config_ref — 与 ProjectBindings 键对应; 回退 "ref"/"id")

    输出:
    - 解析成功 → CapabilityResolution (id/name/version/status/metadata +
      entity; metadata = 实体全量 to_dict — 实体无独立 metadata 字段)
    - Registry 无对应实体 / 无有效引用 → None (由调用方决定 legacy 降级
      或校验门拒绝; 不抛错 — 缺失是业务状态非异常)
    - 未知 kind → ValueError

    纯函数: 不改入参, 无副作用 (registry 只读)。
    """
    norm_kind = _normalize_binding_kind(kind)
    if norm_kind not in _CAPABILITY_RESOLVE_KINDS:
        raise ValueError(
            f"unknown capability binding kind: {kind!r} "
            f"(expected one of: {sorted(_CAPABILITY_RESOLVE_KINDS)})"
        )
    ref_id, version_pin = _binding_ref_id(binding_ref, ref_key)
    if not ref_id:
        return None
    entity = registry.get_capability(norm_kind, ref_id)
    if entity is None:
        return None
    state = getattr(entity, "state", None)
    return CapabilityResolution(
        kind=norm_kind,
        ref_id=ref_id,
        id=getattr(entity, "id", ref_id),
        name=getattr(entity, "name", "") or "",
        version=getattr(entity, "version", "") or "",
        status=state.value if state is not None else "",
        metadata=entity.to_dict(),
        version_pin=version_pin,
        entity=entity,
    )


# ------------------------------------------------------------------ Binding → Snapshot (S10-012 Task 007-002/003)


def _binding_first_entry(bindings: dict[str, Any] | None, key: str) -> Any:
    """bindings.{key} 列表取第一个原始条目 (str 或 dict; 缺失/非列表/空 → None)。

    原始条目 (而非解析后的引用串) 交给 Resolver — 保留 dict 里的 version pin。
    """
    if not bindings:
        return None
    entries = bindings.get(key)
    if not isinstance(entries, list) or not entries:
        return None
    return entries[0]


#: (bindings 键, dict 引用键, snapshot 键, binding kind) — 快照四类。
#: llm 兼容 bindings["llm_configs"] (新) 与 bindings["llm"] (简写) 两键。
_BINDING_SNAPSHOT_SPECS: tuple[tuple[str, str, str, str], ...] = (
    ("agents", "agent_ref", "agent", "agent"),
    ("skills", "skill_ref", "skill", "skill"),
    ("mcps", "mcp_ref", "mcp", "mcp"),
    ("llm_configs", "llm_config_ref", "llm", "llm_config"),
)


def _resolve_binding_snapshot(
    bindings: dict[str, Any] | None,
    registry: Any,
) -> tuple[dict[str, Any], dict[str, CapabilityResolution], list[tuple[str, str]]]:
    """binding → Registry 解析 → (capability_snapshot, resolutions, legacy)。

    - snapshot: {agent: {id, version}, skill: {...}, mcp: {...}, llm: {...}}
      — 只含非空引用; 解析成功 → {id, version} dict (历史可复现 — Registry
      后续升级不影响已落盘实例); Registry 无对应 → legacy 保留裸字符串
      (记录 warning, 不崩溃)
    - resolutions: snap_key → CapabilityResolution (只含解析成功; 供校验门)
    - legacy: [(kind, ref)] — Registry 无对应引用的降级清单 (供校验门拒绝)
    - registry 为 None → 纯 legacy 行为 (空 snapshot/resolutions/legacy —
      零破坏, 旧调用方不经 Resolver)
    """
    snapshot: dict[str, Any] = {}
    resolutions: dict[str, CapabilityResolution] = {}
    legacy: list[tuple[str, str]] = []
    if registry is None:
        return snapshot, resolutions, legacy
    for bind_key, ref_key, snap_key, kind in _BINDING_SNAPSHOT_SPECS:
        entry = _binding_first_entry(bindings, bind_key)
        if entry is None and snap_key == "llm":
            bind_key, ref_key = "llm", "llm_ref"
            entry = _binding_first_entry(bindings, "llm")
        if entry is None:
            continue
        resolution = resolve_capability(entry, registry, kind=kind, ref_key=ref_key)
        if resolution is None:
            ref = _first_binding_ref(bindings, bind_key, ref_key)
            if not ref:
                continue  # 无有效引用 (如 {role: pm} 无 ref 键) — 不进 snapshot
            snapshot[snap_key] = ref  # legacy: 保留裸字符串行为
            legacy.append((kind, ref))
            _LOGGER.warning(
                "capability binding legacy mode: %s %r not found in registry — "
                "raw binding preserved",
                kind,
                ref,
            )
        else:
            snapshot[snap_key] = {"id": resolution.id, "version": resolution.version}
            resolutions[snap_key] = resolution
    return snapshot, resolutions, legacy


# ------------------------------------------------------------------ Capability Validation Gate (S10-012 Task 007-004)


def _validate_capability_gate(
    resolutions: dict[str, CapabilityResolution],
) -> list[str]:
    """Capability Validation Gate — READY dispatch 前置检查 (S10-012 Task 007-004)。

    只检查 registry 提供 + binding 解析成功的 resolution (可解析场景);
    legacy 降级引用 (Registry 无对应 → 003 保留裸字符串 + warning) 与
    registry 缺省 None (纯 legacy) 一律不做 gate — 零破坏。

    检查项 (per resolution):
    - entity 存在 (resolved — resolutions 只含解析成功项, 防御性检查)
    - enabled == True (独立运行开关; §四b 语义)
    - state == ACTIVE (生命周期; capability_selectable 语义)
    - version 可用: binding dict pin 了 version → 实体 version 必须匹配
      (实体无 version 字段 → 无法满足 pin); 实体有 version 字段 (Skill)
      → 必须非空; 无 version 字段实体 (agent/mcp/llm_config) → version N/A

    返回失败原因列表 (空 = 通过); 失败原因以 "capability unavailable: "
    前缀 — ExecutionEngine 捕获 DispatchError 后据此 audit
    capability_unavailable + Task BLOCKED。
    """
    failures: list[str] = []
    for snap_key, res in resolutions.items():
        kind = res.kind
        label = f"{kind} {res.ref_id!r}"
        if res.entity is None:  # 防御 — 解析失败进 legacy, 不进 resolutions
            failures.append(f"capability unavailable: {label} not found in registry")
            continue
        entity = res.entity
        if getattr(entity, "enabled", True) is not True:
            failures.append(f"capability unavailable: {label} is not enabled")
        state = getattr(entity, "state", None)
        if state is None or str(getattr(state, "value", state)) != "active":
            state_txt = getattr(state, "value", None) if state is not None else None
            failures.append(
                f"capability unavailable: {label} state={state_txt or '?'} (expected active)"
            )
        has_version = hasattr(entity, "version")
        version = res.version or ""
        if res.version_pin is not None:
            if not has_version or version != res.version_pin:
                failures.append(
                    f"capability unavailable: {label} version pin "
                    f"{res.version_pin!r} != entity {version!r}"
                )
        elif has_version and not version:
            failures.append(f"capability unavailable: {label} has no version")
    return failures


def dispatch_task(
    task: Task,
    bindings: dict[str, Any] | None = None,
    all_tasks: list[Task] | None = None,
    workflow_id: str = "software-development-v1",
    *,
    project_id: str | None = None,
    lock: ExecutionLock | None = None,
    audit_store: AuditStore | None = None,
    registry: Any = None,
) -> WorkflowInstance:
    """Dispatcher 纯函数 (S10-011 §二 2/3 — Task → Workflow Instance 分发)。

    输入: task + bindings (ProjectBindings dict: agents/skills/mcps/workflow,
    可为空 — 无绑定可执行) + all_tasks (依赖状态上下文; 缺省 [task], 未知
    依赖 id 视为未满足) + workflow_id (缺省 software-development-v1,
    PRD 4.8 公共资源默认)。

    行为:
    1. can_execute 校验: 依赖未满足 / BLOCKED / 非 READY → DispatchError
       (reason = can_execute 原因; 依赖未满足 "Waiting dependency Task X")
    2. 创建 WorkflowInstance: status=CREATED, task_id, workflow_id
       (bindings workflow_ref 优先, 否则 workflow_id 参数), agent/skill/mcp
       (bindings 第一个引用, 无绑定 → 空串)
    3. registry 提供时 (S10-012 Task 007-002): binding 引用 → Registry 实体
       解析 → instance.capability_snapshot 记录 {agent/skill/mcp/llm:
       {id, version}} (历史可复现; Registry 无对应 → legacy 保留裸字符串
       + warning, 不崩溃); registry 缺省 None → 纯 legacy 行为 (零破坏)
    4. instance_id 唯一 (new_id)
    5. audit_store 提供时 (Task 006 全链路审计): 写 audit 条目
       (actor=dispatcher, action=instance.dispatched, entity=instance_id,
       input={task_id, workflow_id, agent, skill, mcp},
       output={instance_id, task_id, status}, result="OK")

    纯函数: 不实际执行 (执行在 Task 004 Executor), 不改入参; 审计写入是
    唯一副作用 (可选注入, 缺省不写)。

    project_id 提供时 (Task 005 写路径持锁): workflow instance 创建持
    per-project 锁 — 同项目写串行 (并发 dispatch 不交错), 跨项目并行,
    同线程重入安全; lock 缺省进程级默认锁 (可注入隔离锁)。
    """
    if project_id is None:
        return _dispatch_impl(
            task, bindings, all_tasks, workflow_id, audit_store=audit_store,
            registry=registry,
        )
    holder = lock if lock is not None else _EXECUTION_LOCK
    with holder.locked(project_id):
        return _dispatch_impl(
            task, bindings, all_tasks, workflow_id, audit_store=audit_store,
            registry=registry,
        )


def _dispatch_impl(
    task: Task,
    bindings: dict[str, Any] | None,
    all_tasks: list[Task] | None,
    workflow_id: str,
    audit_store: AuditStore | None = None,
    registry: Any = None,
) -> WorkflowInstance:
    """dispatch_task 无锁实现 (纯函数 — 校验 + 创建 WorkflowInstance + 可选审计)。"""
    all_tasks = [task] if all_tasks is None else all_tasks
    ok, reason = can_execute(task, all_tasks)
    if not ok:
        raise DispatchError(reason)
    snapshot, resolutions, _legacy = _resolve_binding_snapshot(bindings, registry)
    if registry is not None:  # S10-012 Task 007-004: Capability Validation Gate
        gate_failures = _validate_capability_gate(resolutions)
        if gate_failures:
            raise DispatchError("; ".join(gate_failures))
    instance = WorkflowInstance(
        instance_id=new_id("wi"),
        task_id=task.id,
        workflow_id=_workflow_ref(bindings, workflow_id),
        agent=_first_binding_ref(bindings, "agents", "agent_ref"),
        skill=_first_binding_ref(bindings, "skills", "skill_ref"),
        mcp=_first_binding_ref(bindings, "mcps", "mcp_ref"),
        capability_snapshot=snapshot,
        status=WorkflowInstanceStatus.CREATED,
    )
    if audit_store is not None:
        audit_store.append(
            actor="dispatcher",
            action="instance.dispatched",
            entity=instance.instance_id,
            input={
                "task_id": task.id,
                "workflow_id": instance.workflow_id,
                "agent": instance.agent,
                "skill": instance.skill,
                "mcp": instance.mcp,
            },
            output={
                "instance_id": instance.instance_id,
                "task_id": instance.task_id,
                "status": instance.status.value,
            },
            result="OK",
        )
    return instance


class WorkflowInstanceStore:
    """workflow-instance/ 目录信源 (S10-011 §4 — WorkflowInstance 持久化)。

    布局: workspace/projects/{slug}/workflow-instance/{instance_id}.json
    语义: 原子写 (临时文件 + os.replace — 同 RuntimeStore 模式);
    失败安全 (缺失/损坏/非 dict → load None; 目录缺失 → list 空);
    状态机转换后可重存续流转 (save → load → transition → save)。
    """

    def __init__(self, space_dir: str | Path):
        self._space_dir = Path(space_dir)
        self._dir = self._space_dir / "workflow-instance"

    @property
    def instance_dir(self) -> Path:
        return self._dir

    def _path(self, instance_id: str) -> Path:
        return self._dir / f"{instance_id}.json"

    def save_instance(self, instance: WorkflowInstance) -> Path:
        """写 workflow-instance/{instance_id}.json (原子); 返回落盘路径。"""
        path = self._path(instance.instance_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
        tmp.write_text(
            json.dumps(instance.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, path)
        return path

    def load_instance(self, instance_id: str) -> WorkflowInstance | None:
        """读 workflow-instance/{instance_id}.json; 缺失/损坏/非 dict → None。"""
        path = self._path(instance_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        try:
            return WorkflowInstance.model_validate(data)
        except ValidationError:
            return None

    def list_instances(self) -> list[WorkflowInstance]:
        """目录信源枚举 (按 instance_id 排序); 目录缺失 → []。"""
        if not self._dir.is_dir():
            return []
        instances: list[WorkflowInstance] = []
        for path in sorted(self._dir.glob("*.json")):
            loaded = self.load_instance(path.stem)
            if loaded is not None:
                instances.append(loaded)
        return instances


# ------------------------------------------------------------------ ExecutionLock


class LockTimeoutError(Exception):
    """ExecutionLock 获取超时 (Task 005)。

    acquire(project_id, timeout) 超时 → 返回 False (不阻塞, 不抛);
    locked(project_id, timeout) 上下文超时 → 抛 LockTimeoutError (快速失败)。
    """


class ExecutionLock:
    """per-project 进程内互斥锁 (S10-011 §7 — B1/B2 前置)。

    - acquire(project_id, timeout=None) -> bool: 写操作 (task 状态更新 /
      scheduler plan / workflow instance 创建) 持锁; 默认阻塞直到获取,
      timeout 给定 → 超时返回 False (不阻塞)
    - locked(project_id, timeout=None) 上下文管理器: 持锁代码块 (退出自动
      释放; 超时抛 LockTimeoutError)
    - 同项目互斥: 第一持有者未释放 → 第二 acquire 阻塞
    - 同线程重入安全 (threading.RLock): 嵌套 acquire 不阻塞
    - 不同项目各自独立锁: 跨项目不互斥 (互不阻塞)
    - release 未持有 → 静默 (失败安全)
    - 跨进程锁 S10-012+ 再评估 (本 Sprint 单进程服务)
    """

    def __init__(self) -> None:
        self._locks: dict[str, threading.RLock] = {}
        self._guard = threading.Lock()

    def _lock_for(self, project_id: str) -> threading.RLock:
        with self._guard:
            lock = self._locks.get(project_id)
            if lock is None:
                lock = threading.RLock()
                self._locks[project_id] = lock
            return lock

    def acquire(self, project_id: str, timeout: float | None = None) -> bool:
        """获取指定项目的进程内锁 (同项目互斥; 同线程可重入)。

        默认阻塞直到获取成功并返回 True; timeout 秒内未获取 → 返回 False
        (不阻塞, 不抛 — 调用方自行处理超时)。
        """
        return self._lock_for(project_id).acquire(
            timeout=-1 if timeout is None else timeout
        )

    def release(self, project_id: str) -> None:
        """释放指定项目的锁; 未持有 → 静默 (失败安全, 不抛 RuntimeError)。"""
        lock = self._lock_for(project_id)
        try:
            lock.release()
        except RuntimeError:
            pass

    @contextmanager
    def locked(self, project_id: str, timeout: float | None = None) -> Iterator[None]:
        """with lock.locked(project_id): 持锁代码块 (重入安全; 退出自动释放)。

        timeout 给定且超时未获取 → LockTimeoutError (acquire 超时语义的
        上下文形式 — 失败快速暴露, 不无限阻塞)。
        """
        if not self.acquire(project_id, timeout=timeout):
            raise LockTimeoutError(
                f"timed out acquiring execution lock for project: {project_id}"
            )
        try:
            yield
        finally:
            self.release(project_id)


#: 进程级默认锁 (单服务共享同一 ExecutionLock — 写路径/门面缺省持锁;
#: 跨进程锁 S10-012+ 再评估)。
_EXECUTION_LOCK = ExecutionLock()


# ------------------------------------------------------------------ RuntimeStore


class RuntimeStore:
    """runtime/ 三类执行上下文 JSON (S10-011 §5 — 运行上下文, 可恢复)。

    布局 (项目空间):
        workspace/projects/{slug}/runtime/
          task-execution/{task_id}.json         (当前任务执行状态)
          agent-execution/{instance_id}.json
          workflow-execution/{instance_id}.json

    语义: 原子写 (临时文件 + os.replace — 同 org/store.py 模式);
    失败安全 (缺失/损坏/非 dict → None — 运行上下文可重建, 不致命);
    不存业务状态 (management 职责)。
    """

    def __init__(self, space_dir: str | Path):
        self._space_dir = Path(space_dir)
        self._runtime_dir = self._space_dir / "runtime"

    @property
    def runtime_dir(self) -> Path:
        return self._runtime_dir

    def _path(self, kind: str, key: str) -> Path:
        return self._runtime_dir / kind / f"{key}.json"

    @staticmethod
    def _atomic_write(path: Path, data: dict[str, Any]) -> None:
        """原子写 JSON: 临时文件 + os.replace (同 ProjectSpaceStore 模式)。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, path)

    def _read(self, path: Path) -> dict[str, Any] | None:
        """失败安全读取: 缺失/损坏/非 dict → None。"""
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    # -------------------------------------------------- task-execution
    def save_task_execution(self, task_id: str, data: dict[str, Any]) -> Path:
        """写 task-execution/{task_id}.json (原子)。"""
        path = self._path("task-execution", task_id)
        self._atomic_write(path, data)
        return path

    def load_task_execution(self, task_id: str) -> dict[str, Any] | None:
        """读 task-execution/{task_id}.json; 缺失/损坏 → None。"""
        return self._read(self._path("task-execution", task_id))

    # -------------------------------------------------- agent-execution
    def save_agent_execution(self, instance_id: str, data: dict[str, Any]) -> Path:
        """写 agent-execution/{instance_id}.json (原子)。"""
        path = self._path("agent-execution", instance_id)
        self._atomic_write(path, data)
        return path

    def load_agent_execution(self, instance_id: str) -> dict[str, Any] | None:
        """读 agent-execution/{instance_id}.json; 缺失/损坏 → None。"""
        return self._read(self._path("agent-execution", instance_id))

    # -------------------------------------------------- workflow-execution
    def save_workflow_execution(self, instance_id: str, data: dict[str, Any]) -> Path:
        """写 workflow-execution/{instance_id}.json (原子)。"""
        path = self._path("workflow-execution", instance_id)
        self._atomic_write(path, data)
        return path

    def load_workflow_execution(self, instance_id: str) -> dict[str, Any] | None:
        """读 workflow-execution/{instance_id}.json; 缺失/损坏 → None。"""
        return self._read(self._path("workflow-execution", instance_id))


# ------------------------------------------------------------------ AuditStore


class AuditStore:
    """logs/audit.log 不可变审计日志 (S10-011 §6)。

    记录: {time, actor, action, entity, input, output, result} 单行 JSON
    (actor: scheduler|dispatcher|executor|user|system)。
    语义:
    - 追加不可变 (append-only): 只追加不覆盖 — 历史条目不丢不重写
    - 原子追加: 进程内 threading.Lock 串行 + 单行 JSON 单次 write (O_APPEND)
    - 读取失败安全: 缺失 → 空列表; 损坏行跳过 (日志为不可变事实源, 不整体失败)
    """

    _FIELDS = ("time", "actor", "action", "entity", "input", "output", "result")

    def __init__(self, space_dir: str | Path):
        self._space_dir = Path(space_dir)
        self._logs_dir = self._space_dir / "logs"
        self._path = self._logs_dir / "audit.log"
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def append(
        self,
        *,
        actor: str,
        action: str,
        entity: str,
        input: Any = None,
        output: Any = None,
        result: str = "",
    ) -> dict[str, Any]:
        """追加一条审计记录 (返回落盘条目; time 自动 UTC ISO)。"""
        entry: dict[str, Any] = {
            "time": utcnow().isoformat(),
            "actor": actor,
            "action": action,
            "entity": entity,
            "input": input,
            "output": output,
            "result": result,
        }
        with self._lock:
            self._logs_dir.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def list(self) -> list[dict[str, Any]]:
        """读取全部审计条目 (按追加顺序); 缺失 → []; 损坏行跳过; 返回副本。

        Task 006 不可变语义: 返回 deep copy — 调用方修改返回值不影响
        落盘事实 (audit.log 为不可变事实源, 只追加不覆盖)。
        """
        if not self._path.is_file():
            return []
        entries: list[dict[str, Any]] = []
        with self._lock:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(data, dict):
                        entries.append(copy.deepcopy(data))
        return entries

    def list_audit(
        self,
        *,
        actor: str | None = None,
        entity: str | None = None,
        action: str | None = None,
    ) -> list[dict[str, Any]]:
        """读取审计条目 (Task 006 — 按 time 升序) + 过滤 (actor/entity/action)。

        - 排序: 按 time (ISO 字符串, 同格式字典序 == 时间序; 同时间稳定
          保持追加序 — 与 list() 顺序一致)
        - 过滤: actor / entity / action 任意组合 (None = 不过滤)
        - 不可变: 返回 deep copy (同 list()); 缺失 → []; 损坏行跳过
        - 项目空间隔离: store 按 space_dir 归属, 天然项目级作用域
        """
        entries = self.list()
        if actor is not None:
            entries = [e for e in entries if e.get("actor") == actor]
        if entity is not None:
            entries = [e for e in entries if e.get("entity") == entity]
        if action is not None:
            entries = [e for e in entries if e.get("action") == action]
        return sorted(entries, key=lambda e: e.get("time", ""))


# ------------------------------------------------------------------ Executor (S10-011 Task 004)


class ExecutionOutcome(_OrgModel):
    """execute_instance 结果 (Task 004 — 终态实例 + 联动后的 Task)。

    instance: 终态 WorkflowInstance (SUCCESS/FAILED — start_time/end_time/result 已记录);
    task: 联动后的 Task (execute_instance 收到 task 参数时; 未提供/非法跳过 → None/原对象)。
    """

    instance: WorkflowInstance
    task: Task | None = None


def _default_executor(instance: WorkflowInstance) -> str:
    """内置 stub executor (本 Sprint 注入点缺省 — 真实 Agent S10-012+ 替换)。

    纯标记执行: 返回 \"executed by {agent|stub}\" — 不调用任何 Agent/LLM。
    """
    agent = instance.agent or "stub"
    return f"executed by {agent}"


def _error_text(exc: Exception) -> str:
    """异常 → 可读 error 文本 (类型名 + 消息)。"""
    return f"{type(exc).__name__}: {exc}"


def _record_runtime(runtime_store: RuntimeStore | None, instance: WorkflowInstance) -> None:
    """每次状态转换写 runtime 快照 (workflow-execution + agent-execution; 可恢复)。"""
    if runtime_store is None:
        return
    runtime_store.save_workflow_execution(instance.instance_id, instance.to_dict())
    runtime_store.save_agent_execution(instance.instance_id, instance.to_dict())


def _record_audit(
    audit_store: AuditStore | None,
    instance: WorkflowInstance,
    *,
    actor: str,
    from_status: WorkflowInstanceStatus,
    result: str = "OK",
) -> None:
    """每次状态转换写 audit (actor=executor, action=instance.transition)。"""
    if audit_store is None:
        return
    audit_store.append(
        actor=actor,
        action="instance.transition",
        entity=instance.instance_id,
        input={"from": from_status.value, "to": instance.status.value},
        output={
            "instance_id": instance.instance_id,
            "task_id": instance.task_id,
            "status": instance.status.value,
        },
        result=result,
    )


def _link_task(
    task: Task | None,
    instance: WorkflowInstance,
    *,
    actor: str,
    dependency_status: dict[str, TaskStatus] | None,
    audit_store: AuditStore | None = None,
) -> Task | None:
    """Task 状态联动 (走 management.transition_task 受控状态机)。

    - instance SUCCESS → task IN_PROGRESS→REVIEW; 未开始 (READY) → IN_PROGRESS
    - instance FAILED → task READY/IN_PROGRESS→BLOCKED
    - 其他 task 状态 (TODO/BLOCKED/REVIEW/DONE 等) → 不联动 (返回原 task)
    - 受控转换非法 (如依赖门控拒绝) → 失败安全跳过, 返回原 task
      (执行结果已落盘, 不因联动失败破坏; 异常路径由调用方/人工处理)
    - audit_store 提供时 (Task 006 全链路审计): 联动成功写 audit 条目
      (actor=executor, action=task.linked, entity=task.id,
      input={from, to}, output={task_id, instance_id, status},
      result=instance 终态值)
    """
    if task is None:
        return None
    if instance.status == WorkflowInstanceStatus.SUCCESS:
        if task.status == TaskStatus.IN_PROGRESS:
            target = TaskStatus.REVIEW
        elif task.status == TaskStatus.READY:
            target = TaskStatus.IN_PROGRESS
        else:
            return task
    elif instance.status == WorkflowInstanceStatus.FAILED:
        if task.status in (TaskStatus.READY, TaskStatus.IN_PROGRESS):
            target = TaskStatus.BLOCKED
        else:
            return task
    else:
        return task
    try:
        updated = transition_task(
            task,
            target,
            actor=actor,
            action="instance.linked",
            result=instance.status.value,
            dependency_status=dependency_status,
        )
    except ValueError:
        return task
    if audit_store is not None:
        audit_store.append(
            actor=actor,
            action="task.linked",
            entity=task.id,
            input={"from": task.status.value, "to": updated.status.value},
            output={
                "task_id": task.id,
                "instance_id": instance.instance_id,
                "status": instance.status.value,
            },
            result=instance.status.value,
        )
    return updated


def execute_instance(
    instance: WorkflowInstance,
    executor: Callable[[WorkflowInstance], str] | None = None,
    *,
    runtime_store: RuntimeStore | None = None,
    audit_store: AuditStore | None = None,
    task: Task | None = None,
    actor: str = "executor",
    dependency_status: dict[str, TaskStatus] | None = None,
    project_id: str | None = None,
    lock: ExecutionLock | None = None,
) -> ExecutionOutcome:
    """Workflow Instance Runtime 执行 (S10-011 §三 Task 004 — 生命周期执行)。

    输入: CREATED 实例 + executor 回调 (stub — 本 Sprint 注入点; 真实 Agent
    S10-012+ 替换; 缺省内置 stub 直接成功) + runtime_store/audit_store (可注入
    项目空间 store) + task (Task 状态联动; 可选) + actor (审计 actor, 缺省
    executor) + dependency_status (有依赖 task 联动时透传状态机)。

    流程 (同步模型 — 异步/并发 Task 005):
    1. 非法状态拒绝: status != CREATED → ValueError (RUNNING/终态直接 execute 非法)
    2. CREATED → RUNNING (transition_instance 记录 start_time) → 写 runtime
       (workflow-execution/{id}.json + agent-execution/{id}.json) + audit
       (actor=executor, action=instance.transition)
    3. 调用 executor(running 实例):
       - 成功 (返回 str, 非 "ERROR:" 前缀) → SUCCESS + end_time + result
       - 抛异常 → FAILED + end_time + error (result 字段 = "TypeName: msg")
       - 返回 "ERROR: ..." 前缀 → 视为失败 → FAILED + error (前缀后内容)
    4. 终态转换同样写 runtime + audit (每次转换都落盘)
    5. Task 状态联动 (task 参数提供时): SUCCESS → IN_PROGRESS→REVIEW 或
       READY→IN_PROGRESS; FAILED → READY/IN_PROGRESS→BLOCKED; 非法跳过
       (失败安全 — 执行结果不因联动失败而回滚); 联动成功写 audit
       (actor=executor, action=task.linked — Task 006 全链路审计)
    6. 返回 ExecutionOutcome {终态 instance, 联动后 task}

    纯函数风格: 不改入参 (instance/task 原对象不变, 转换返回新对象)。

    project_id 提供时 (Task 005 写路径持锁): 生命周期执行全程 (状态转换 +
    executor + Task 联动) 持 per-project 锁 — 同项目执行串行 (无交错,
    数据一致), 跨项目并行, 同线程重入安全; lock 缺省进程级默认锁。
    """
    if project_id is None:
        return _execute_impl(
            instance,
            executor,
            runtime_store=runtime_store,
            audit_store=audit_store,
            task=task,
            actor=actor,
            dependency_status=dependency_status,
        )
    holder = lock if lock is not None else _EXECUTION_LOCK
    with holder.locked(project_id):
        return _execute_impl(
            instance,
            executor,
            runtime_store=runtime_store,
            audit_store=audit_store,
            task=task,
            actor=actor,
            dependency_status=dependency_status,
        )


def _execute_impl(
    instance: WorkflowInstance,
    executor: Callable[[WorkflowInstance], str] | None,
    *,
    runtime_store: RuntimeStore | None,
    audit_store: AuditStore | None,
    task: Task | None,
    actor: str,
    dependency_status: dict[str, TaskStatus] | None,
) -> ExecutionOutcome:
    """execute_instance 无锁实现 (生命周期执行 — 状态转换 + executor + 联动)。"""
    if instance.status != WorkflowInstanceStatus.CREATED:
        raise ValueError(
            f"cannot execute workflow instance: status {instance.status.value} "
            f"(expected: {WorkflowInstanceStatus.CREATED.value})"
        )
    running = transition_instance(instance, WorkflowInstanceStatus.RUNNING)
    _record_runtime(runtime_store, running)
    _record_audit(
        audit_store, running, actor=actor, from_status=WorkflowInstanceStatus.CREATED
    )

    run_executor = executor if executor is not None else _default_executor
    try:
        result = run_executor(running)
    except Exception as exc:  # noqa: BLE001 — executor 任意异常 → FAILED (失败捕获)
        error = _error_text(exc)
        terminal = transition_instance(running, WorkflowInstanceStatus.FAILED, result=error)
        outcome_result = f"FAILED: {error}"
    else:
        if isinstance(result, str) and result.startswith("ERROR:"):
            error = result[len("ERROR:") :].strip()
            terminal = transition_instance(running, WorkflowInstanceStatus.FAILED, result=error)
            outcome_result = f"FAILED: {error}"
        else:
            terminal = transition_instance(
                running, WorkflowInstanceStatus.SUCCESS, result=result or ""
            )
            outcome_result = "OK"
    _record_runtime(runtime_store, terminal)
    _record_audit(
        audit_store,
        terminal,
        actor=actor,
        from_status=WorkflowInstanceStatus.RUNNING,
        result=outcome_result,
    )

    linked = _link_task(
        task,
        terminal,
        actor=actor,
        dependency_status=dependency_status,
        audit_store=audit_store,
    )
    return ExecutionOutcome(instance=terminal, task=linked)


# ------------------------------------------------------------------ Task 状态更新封装 + ExecutionEngine 门面 (S10-011 Task 005)


def transition_task_locked(
    task: Task,
    target: TaskStatus | str,
    project_id: str,
    *,
    lock: ExecutionLock | None = None,
    **kwargs: Any,
) -> Task:
    """Task 状态更新封装 (S10-011 Task 005 — 写路径持锁)。

    per-project 锁内调用 management.transition_task (受控状态机透传 — 非法
    转换/依赖门控 ValueError 原样抛; actor/action/result/dependency_status
    经 kwargs 透传); 与 execute_instance 的 Task 联动共用同一锁 (重入安全 —
    执行内联动不 deadlock)。lock 缺省进程级默认锁。纯函数风格: 不改入参。
    """
    holder = lock if lock is not None else _EXECUTION_LOCK
    with holder.locked(project_id):
        return transition_task(task, target, **kwargs)


class ProjectExecutionResult(_OrgModel):
    """execute_project_tasks 汇总结果 (计划 + 实例 + 执行结果 + task 终态)。"""

    project_id: str
    plan: ExecutionPlan
    instances: list[WorkflowInstance] = Field(default_factory=list)
    outcomes: list[ExecutionOutcome] = Field(default_factory=list)
    final_tasks: dict[str, str] = Field(default_factory=dict)

    @field_validator("instances", "outcomes", mode="before")
    @classmethod
    def _lists_none(cls, v: Any) -> Any:
        return _norm_list(v)

    @field_validator("final_tasks", mode="before")
    @classmethod
    def _final_tasks_none(cls, v: Any) -> Any:
        return v if v is not None else {}


# ------------------------------------------------------------------ NotificationSink (S10-011 Task 006)


class NotificationSink:
    """通知预留接口 (Task 006 — 本 Sprint 不实现真实渠道)。

    notify(project_id, event, payload) → 默认无操作 (no-op sink); 真实通知
    渠道 (邮件/IM/WebSocket — docs/design/execution-engine.md §七 Notification
    Engine) S10-012+ 注入替换。本类只定义契约:

    - event: "task.completed" | "task.failed" (ExecutionEngine 门面终态通知;
      预留扩展: dispatch.queued / plan.created 等)
    - payload: 事件上下文 dict (含 project_id/task_id/instance_id/status/result)
    - 注入: ExecutionEngine(notification=sink) — 测试收集 / 生产渠道替换
      (可注入 = 依赖注入点; 默认 no-op 保证不注入也可运行)
    """

    def notify(self, project_id: str, event: str, payload: dict[str, Any]) -> None:
        """发送一条通知事件; 默认无操作 (no-op)。"""
        return None


class ExecutionEngine:
    """ExecutionEngine 门面 (S10-011 Task 005 — 项目级执行入口, 持锁串行化)。

    execute_project_tasks: plan→dispatch→execute 全程持 per-project 锁 —
    同项目并发写串行 (无交错, 数据一致), 跨项目并行 (互不阻塞), 同线程重入
    安全 (内部 dispatch/execute 再取同锁不 deadlock); 锁缺省进程级默认锁
    (_EXECUTION_LOCK), 可注入隔离锁 (测试/多租户)。

    Task 006 完善:
    - 全链路审计: 门面 plan 写 audit (actor=scheduler, action=plan.created);
      dispatch/execute 透传 audit_store (actor=dispatcher/executor)
    - NotificationSink 预留: notification 可注入 (缺省 no-op); 每个实例
      终态 notify — SUCCESS → event="task.completed", FAILED →
      event="task.failed" (payload 含 project_id/task_id/instance_id/status/result)
    """

    def __init__(
        self,
        *,
        lock: ExecutionLock | None = None,
        notification: NotificationSink | None = None,
    ) -> None:
        self._lock = lock if lock is not None else _EXECUTION_LOCK
        self._notification = (
            notification if notification is not None else NotificationSink()
        )

    @property
    def lock(self) -> ExecutionLock:
        """本门面使用的 ExecutionLock (注入或进程级默认)。"""
        return self._lock

    @property
    def notification(self) -> NotificationSink:
        """本门面使用的 NotificationSink (注入或默认 no-op)。"""
        return self._notification

    def _notify_terminal(
        self,
        project_id: str,
        task: Task,
        instance: WorkflowInstance,
        outcome: ExecutionOutcome,
    ) -> None:
        """终态通知 (Task 006): SUCCESS → task.completed; FAILED → task.failed。"""
        event = (
            "task.completed"
            if outcome.instance.status == WorkflowInstanceStatus.SUCCESS
            else "task.failed"
        )
        self._notification.notify(
            project_id,
            event,
            {
                "project_id": project_id,
                "task_id": task.id,
                "instance_id": instance.instance_id,
                "status": outcome.instance.status.value,
                "result": outcome.instance.result,
            },
        )

    def execute_project_tasks(
        self,
        project_id: str,
        tasks: list[Task],
        *,
        bindings: dict[str, Any] | None = None,
        workflow_id: str = "software-development-v1",
        max_parallel: int = 5,
        executor: Callable[[WorkflowInstance], str] | None = None,
        runtime_store: RuntimeStore | None = None,
        audit_store: AuditStore | None = None,
        actor: str = "executor",
        registry: Any = None,
    ) -> ProjectExecutionResult:
        """项目任务一键执行 (plan→dispatch→execute 持锁串行化)。

        1. 持 per-project 锁 (同项目其他写/执行阻塞; 跨项目不阻塞; 重入安全)
        2. plan_tasks 生成计划 (READY + 依赖满足 + priority 排序 +
           max_parallel 分批; 非 READY 不入选, 依赖未满足记录 waiting_dependency);
           audit_store 提供时写 plan 审计 (actor=scheduler, action=plan.created)
        3. 逐任务 dispatch (创建 WorkflowInstance; audit actor=dispatcher) →
           execute (缺省 stub executor 或注入 executor) → Task 状态联动
           (SUCCESS → IN_PROGRESS→REVIEW 或 READY→IN_PROGRESS; FAILED →
           BLOCKED; 走受控状态机, 依赖门控透传; audit actor=executor) →
           终态 notify (task.completed / task.failed)
        4. 返回 ProjectExecutionResult {plan, instances, outcomes, final_tasks}

        registry (S10-012 Task 007-003): CapabilityRegistry 可注入 — 提供时
        dispatch 解析 binding → snapshot; 缺省 None → 纯 legacy 行为
        (旧项目裸 binding 不经 Resolver, 零破坏 — 验收场景 5)。
        """
        with self._lock.locked(project_id):
            plan = plan_tasks(tasks, max_parallel=max_parallel)
            if audit_store is not None:
                audit_store.append(
                    actor="scheduler",
                    action="plan.created",
                    entity=plan.plan_id,
                    input={
                        "project_id": project_id,
                        "task_ids": [pt.task_id for pt in plan.tasks],
                    },
                    output={
                        "tasks": [pt.to_dict() for pt in plan.tasks],
                        "parallel_batch": plan.parallel_batch,
                        "max_parallel": plan.max_parallel,
                        "waiting_dependency": plan.waiting_dependency,
                    },
                    result="OK",
                )
            instances: list[WorkflowInstance] = []
            outcomes: list[ExecutionOutcome] = []
            final_tasks: dict[str, str] = {t.id: t.status.value for t in tasks}
            by_id = {t.id: t for t in tasks}
            dependency_status = {t.id: t.status for t in tasks}
            for pt in plan.tasks:
                task = by_id.get(pt.task_id)
                if task is None:
                    continue
                try:
                    instance = dispatch_task(
                        task,
                        bindings=bindings,
                        all_tasks=tasks,
                        workflow_id=workflow_id,
                        project_id=project_id,
                        lock=self._lock,
                        audit_store=audit_store,
                        registry=registry,
                    )
                except DispatchError as exc:
                    # S10-012 Task 007-004: Capability Validation Gate 失败
                    # (或依赖/状态拒绝) → Task BLOCKED + audit
                    # capability_unavailable — 不创建 instance, 不执行。
                    blocked = transition_task(
                        task,
                        TaskStatus.BLOCKED,
                        actor="dispatcher",
                        action="capability.blocked",
                        result=exc.reason,
                    )
                    final_tasks[task.id] = blocked.status.value
                    if audit_store is not None:
                        audit_store.append(
                            actor="dispatcher",
                            action="capability.unavailable",
                            entity=task.id,
                            input={"task_id": task.id, "reason": exc.reason},
                            output={
                                "task_id": task.id,
                                "status": blocked.status.value,
                            },
                            result="BLOCKED",
                        )
                    continue
                instances.append(instance)
                outcome = execute_instance(
                    instance,
                    executor=executor,
                    runtime_store=runtime_store,
                    audit_store=audit_store,
                    task=task,
                    actor=actor,
                    dependency_status=dependency_status,
                    project_id=project_id,
                    lock=self._lock,
                )
                outcomes.append(outcome)
                if outcome.task is not None:
                    final_tasks[task.id] = outcome.task.status.value
                self._notify_terminal(project_id, task, instance, outcome)
            return ProjectExecutionResult(
                project_id=project_id,
                plan=plan,
                instances=instances,
                outcomes=outcomes,
                final_tasks=final_tasks,
            )
