"""factory-org/org/execution.py — Execution Domain Model (S10-011 Task 001)。

设计依据 (唯一):
- docs/sprint10/S10-011-architecture-design.md §二 4/5/6/7 (7 项确认)
- AF-PRD-v1.md 4.8 (Execution Engine)

模型:
- WorkflowInstance: 执行实例实体 + 受控状态机
  CREATED → RUNNING → SUCCESS / FAILED / CANCELLED (非法转换拒绝);
  字段 instance_id/task_id/workflow_id/agent/skill/mcp/status/start_time/
  end_time/result/created_at (设计 §4)
- ExecutionPlan: 执行计划 (tasks 有序列表 + parallel_batch 批 + max_parallel)
- ExecutionLock: per-project 进程内互斥 (threading.RLock — 同线程重入安全);
  同项目写互斥, 不同项目各自独立锁互不阻塞 (设计 §7, 跨进程锁 S10-012+)
- RuntimeStore: workspace/projects/{slug}/runtime/ 三类 JSON 原子写
  (task-execution/{task_id}.json / agent-execution/{instance_id}.json /
  workflow-execution/{instance_id}.json) — 运行上下文 (可恢复), 失败安全
  (缺失/损坏 → None; 设计 §5)
- AuditStore: workspace/projects/{slug}/logs/audit.log 追加不可变
  (记录 {time, actor, action, entity, input, output, result}; 设计 §6)

约束: 本模块零 Core 依赖 (stdlib + pydantic + org.models, Removal Isolation);
目录在项目空间 workspace/projects/{slug}/ 下 (与 org/space.py 布局一致 —
runtime/ 与 logs/ 平级); 原子写 = 临时文件 + os.replace (同 org/store.py 模式);
状态机受控 — 非法转换 ValueError 拒绝。
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator

from .models import _OrgModel, _norm_list, utcnow

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
    workspace/settings 可覆盖)。
    """

    plan_id: str
    project_id: str = ""
    tasks: list[PlanTask] = Field(default_factory=list)
    parallel_batch: list[list[str]] = Field(default_factory=list)
    max_parallel: int = 5

    @field_validator("tasks", "parallel_batch", mode="before")
    @classmethod
    def _lists_none(cls, v: Any) -> Any:
        return _norm_list(v)


# ------------------------------------------------------------------ ExecutionLock


class ExecutionLock:
    """per-project 进程内互斥锁 (S10-011 §7 — B1/B2 前置)。

    - acquire(project_id)/release(project_id): 写操作 (task 状态更新 /
      scheduler plan / workflow instance 创建) 持锁
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

    def acquire(self, project_id: str) -> None:
        """获取指定项目的进程内锁 (同项目互斥; 同线程可重入)。"""
        self._lock_for(project_id).acquire()

    def release(self, project_id: str) -> None:
        """释放指定项目的锁; 未持有 → 静默 (失败安全, 不抛 RuntimeError)。"""
        lock = self._lock_for(project_id)
        try:
            lock.release()
        except RuntimeError:
            pass


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
        """读取全部审计条目 (按追加顺序); 缺失 → []; 损坏行跳过。"""
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
                        entries.append(data)
        return entries
