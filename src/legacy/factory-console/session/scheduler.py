"""factory-console/session/scheduler.py — M3c 并行调度执行 (S10-090 M3-3)。

并行调度器 (M3-3): 消费 plan.json (M3b 产出 tasks/edges/critical_path/order)
+ execution_state (已完成任务) → 依赖驱动调度:
  就绪队列 (入度=0 且依赖全部完成) → 冲突检测 (同 target_file, 复用
  ConflictResolver.resolve 串行化) → 并发分桶 (就绪按 max_concurrency 分轮)
  → rounds 落盘 schedule.json {rounds, order, conflicts, max_concurrency,
  created_at} (可审计可回放)。

复用地基 (只读, 不修改核心):
- dependencies.TaskDependencyGraph.topological_order — Kahn 稳定拓扑 (无依赖 →
  输入原顺序; 环 → 失败安全追加)
- conflicts.ConflictResolver.resolve — 同文件冲突 → 串行化 (a→b 边 + 策略记录)
- agents.AgentMatcher — M3-4 动态分配不做, 仅接口预留 (schedule 参数透传)

失败安全 (诚实标注, 不伪造并行):
- 无 plan / plan 无任务 → 降级顺序执行 (rounds 空, degraded=True 诚实标注)
- 依赖成环 (调度推进卡死) → 降级顺序执行 (topological_order 失败安全序,
  degraded=True + reason)
- 落盘故障 → 静默跳过 (调度结果仍返回, 不中断)

边界 (S10-090 §8): 不做 M3-4 动态 Agent 分配 / 质量评估 / 快照恢复点;
max_concurrency=1 = 旧顺序执行 (向后兼容零变化)。

设计: docs/sprint10/S10-090-m3c-parallel-scheduler-plan.md
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from .conflicts import ConflictResolver
from .dependencies import TaskDependencyGraph

#: 默认 schedule.json 文件名 (projects/<slug>/schedule.json)
SCHEDULE_FILE_NAME = "schedule.json"

#: 冲突条目缺省 resolution 标记 (ConflictResolver 策略透传失败安全缺省)
_DEFAULT_RESOLUTION = "serial_execution"


def _now_iso() -> str:
    """UTC 时间戳 (ISO8601, 落盘审计)。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _task_id(task: Any) -> str:
    """任务 dict → id (缺失/空 → ""; 非 dict → "")。"""
    if not isinstance(task, dict):
        return ""
    return str(task.get("id") or "").strip()


def _norm_file(path: Any) -> str:
    """target_file 归一化 (空/缺失 → ""; 相对路径正斜杠, 与 critical_path 口径一致)。"""
    if not path:
        return ""
    return str(path).strip().replace("\\", "/").lstrip("./")


def _completed_ids(state: Any) -> set[str]:
    """execution_state → 已完成任务 id 集合 (兼容 dict/set/list/None)。

    - dict: state["completed"] (list/set) 或 state["tasks"] (每任务 status=="completed")
    - 集合/列表: 元素即已完成 id (字符串)
    """
    if state is None:
        return set()
    if isinstance(state, dict):
        completed = state.get("completed")
        if completed is None:
            completed = set()
            for t in state.get("tasks") or []:
                if isinstance(t, dict) and str(t.get("status") or "") == "completed":
                    tid = str(t.get("id") or "")
                    if tid:
                        completed.add(tid)
        if isinstance(completed, str):
            return {completed} if completed else set()
        return {str(c) for c in (completed or []) if str(c)}
    if isinstance(state, str):
        return {state} if state else set()
    return {str(c) for c in (state or []) if str(c)}


@dataclass
class ScheduleResult:
    """调度结果 (schedule.json 内容模型 + 内存视图)。

    - rounds: [[task_id, ...], ...] — 每轮可并行执行的任务组 (轮内并行意图,
      同轮内按现有执行链跑; max_concurrency=1 → 每轮单任务 = 旧顺序)
    - order:  扁平执行序 (rounds 展开, 向后兼容顺序执行消费方)
    - conflicts: [{task, reason, resolution}] — 被串行化的同文件冲突 (审计)
    - state:  落盘/审计视图 (completed + schedule_file + 摘要)
    - max_concurrency / created_at: 调度配置与时间戳 (schedule.json 字段)
    - degraded / degradation_reason: 失败安全降级标注 (诚实不伪造并行)
    """

    rounds: list[list[str]] = field(default_factory=list)
    order: list[str] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
    max_concurrency: int = 1
    created_at: str = ""
    degraded: bool = False
    degradation_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        """schedule.json 落盘视图 (spec §5: rounds/order/conflicts/max_concurrency/
        created_at + 降级标注)。"""
        data: dict[str, Any] = {
            "rounds": [list(r) for r in self.rounds],
            "order": list(self.order),
            "conflicts": [dict(c) for c in self.conflicts],
            "max_concurrency": int(self.max_concurrency or 1),
            "created_at": self.created_at or _now_iso(),
        }
        if self.degraded:
            data["degraded"] = True
            data["degradation_reason"] = self.degradation_reason or "未知原因"
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScheduleResult":
        """dict → ScheduleResult (未知键忽略; 缺失字段缺省 — 前向兼容)。"""
        data = data or {}
        rounds = [
            [str(t) for t in (r or []) if not isinstance(t, dict)]
            for r in (data.get("rounds") or [])
            if isinstance(r, list)
        ]
        return cls(
            rounds=rounds,
            order=[str(t) for t in (data.get("order") or []) if not isinstance(t, dict)],
            conflicts=[
                dict(c) for c in (data.get("conflicts") or []) if isinstance(c, dict)
            ],
            state={},
            max_concurrency=int(data.get("max_concurrency") or 1),
            created_at=str(data.get("created_at") or ""),
            degraded=bool(data.get("degraded")),
            degradation_reason=str(data.get("degradation_reason") or ""),
        )


class TaskScheduler:
    """并行调度器 (M3-3): plan.json + execution_state → rounds/order/conflicts。

    schedule(plan, state, *, max_concurrency=1, agent_matcher=None,
    conflict_resolver=None, persist=True) → ScheduleResult:
      1. 依赖边提取 (plan.edges / plan.tasks[].depends_on, 图内取边)
      2. 同 target_file 冲突检测 → ConflictResolver.resolve 串行化 (a→b 边)
      3. 逐轮调度: ready (依赖全部 ∈ completed) → 并发分桶 → 当前轮 = 首桶
      4. 卡死 (环) / 无 plan → 降级顺序执行 (degraded=True, 诚实标注)
      5. persist → projects/<slug>/schedule.json (可审计)

    ready_tasks(completed): 公开就绪判定 (入度=0 且依赖全部完成, 依赖最近一次
    schedule/prepare 的 plan)。
    """

    def __init__(self, workspace: Optional[Path] = None) -> None:
        self.workspace = Path(workspace) if workspace is not None else None
        self._deps: dict[str, list[str]] = {}
        self._ids: list[str] = []
        self._tasks_by_id: dict[str, dict[str, Any]] = {}
        self._plan: dict[str, Any] = {}
        self._conflicts: list[dict[str, Any]] = []

    # ------------------------------------------------------------ 计划装载

    def prepare(
        self,
        plan: Optional[dict[str, Any]],
        conflict_resolver: Optional[ConflictResolver] = None,
    ) -> None:
        """装载 plan + 冲突检测 (供 schedule/ready_tasks 共享; 幂等可重入)。

        失败安全: plan 缺失/非 dict/无任务 → 空图 (ready 恒空, schedule 降级)。
        """
        self._plan = plan if isinstance(plan, dict) else {}
        tasks = [t for t in (self._plan.get("tasks") or []) if isinstance(t, dict)]
        self._ids = [tid for t in tasks if (tid := _task_id(t))]
        self._tasks_by_id = {tid: t for t in tasks if (tid := _task_id(t))}
        # 依赖边: plan.edges (M3b {from_task, to_task}) + tasks[].depends_on
        deps: dict[str, list[str]] = {tid: [] for tid in self._ids}
        node_set = set(self._ids)
        for edge in self._plan.get("edges") or []:
            if not isinstance(edge, dict):
                continue
            src = str(edge.get("from_task") or "").strip()
            dst = str(edge.get("to_task") or "").strip()
            if src in node_set and dst in node_set and src != dst:
                if src not in deps[dst]:
                    deps[dst].append(src)
        for t in tasks:
            tid = _task_id(t)
            if not tid:
                continue
            for dep in t.get("depends_on") or []:
                if isinstance(dep, dict):
                    continue
                dep_id = str(dep).strip()
                if dep_id in node_set and dep_id != tid and dep_id not in deps[tid]:
                    deps[tid].append(dep_id)
        # 同文件冲突 → ConflictResolver.resolve 串行化 (a→b 边, 复用不重造)
        resolver = conflict_resolver if conflict_resolver is not None else ConflictResolver()
        self._conflicts = []  # 审计条目 (task/reason/resolution), 幂等重入清零
        raw_conflicts = self._detect_file_conflicts(tasks)
        for edge in self._resolve_conflict_edges(raw_conflicts, tasks, resolver):
            src, dst = edge
            if src in node_set and dst in node_set and src != dst:
                if src not in deps[dst]:
                    deps[dst].append(src)
        self._deps = deps

    # ------------------------------------------------------------ 就绪判定

    def ready_tasks(self, completed: Iterable[str]) -> list[str]:
        """就绪判定: 任务依赖 (depends_on/edges 指向它) 全部 ∈ completed。

        返回就绪任务 id 列表 (按 plan/拓扑稳定序, 非集合无序)。空图 → []。
        """
        done = {str(c) for c in (completed or []) if str(c)}
        return [tid for tid in self._ids if all(d in done for d in self._deps.get(tid, []))]

    # ------------------------------------------------------------ 并发分桶

    def _concurrency_bucket(self, ready: list[str], max_c: int) -> list[list[str]]:
        """就绪任务按 max_concurrency 分桶 (每桶 ≤ max_c; 桶序稳定)。

        max_c <= 0 → 视为 1 (非法配置失败安全降级为顺序); 空就绪 → []。
        """
        cap = max(int(max_c or 1), 1)
        return [list(ready[i : i + cap]) for i in range(0, len(ready), cap)]

    # ------------------------------------------------------------ 调度

    def schedule(
        self,
        plan: Optional[dict[str, Any]],
        state: Any,
        *,
        max_concurrency: int = 1,
        agent_matcher: Any = None,
        conflict_resolver: Optional[ConflictResolver] = None,
        persist: bool = True,
    ) -> ScheduleResult:
        """plan.json + execution_state → ScheduleResult (rounds/order/conflicts/state)。

        逐轮: ready = 未调度且依赖完成 → 冲突已由冲突边串行化 (同文件不并轮)
        → 并发分桶取首桶为本轮 (超限推下一轮) → 直到全部调度。
        失败安全: 无任务 → 空调度; 环/无 plan → 降级顺序执行 (诚实标注);
        落盘故障 → 静默跳过 (不中断)。
        """
        max_c = max(int(max_concurrency or 1), 1)
        self.prepare(plan, conflict_resolver=conflict_resolver)
        completed = _completed_ids(state)
        ids = list(self._ids)
        created_at = _now_iso()
        degraded = False
        degrade_reason = ""

        # 无 plan / 无任务 → 降级顺序执行 (诚实标注, 不伪造并行)
        if not ids:
            result = ScheduleResult(
                rounds=[],
                order=[],
                conflicts=[],
                state={},
                max_concurrency=max_c,
                created_at=created_at,
                degraded=True,
                degradation_reason="无 plan 或 plan 无任务 — 降级顺序执行 (空调度)",
            )
            return self._finalize(result, state, persist=persist)

        # 稳定基础序: 复用 dependencies.topological_order (Kahn, 失败安全)
        graph = TaskDependencyGraph({tid: list(d) for tid, d in self._deps.items()})
        base_order = graph.topological_order(ids)

        # resume 语义: 已完成任务不再调度 (只排剩余工作; 全新执行 completed=∅ → 全量)
        unscheduled = [t for t in base_order if t not in completed]
        rounds: list[list[str]] = []
        guard = 0
        while unscheduled:
            guard += 1
            if guard > len(ids) + 1:  # 防呆 (理论不可达: 每轮至少调度 1 个)
                degraded = True
                degrade_reason = "调度推进异常 — 降级顺序执行 (失败安全)"
                break
            ready = [
                t
                for t in unscheduled
                if all(d in completed for d in self._deps.get(t, []))
            ]
            if not ready:
                # 剩余任务依赖无法满足 (环) → 降级顺序执行 (诚实标注)
                degraded = True
                degrade_reason = "依赖成环 — 降级顺序执行 (不伪造并行)"
                break
            buckets = self._concurrency_bucket(ready, max_c)
            current = list(buckets[0])
            rounds.append(current)
            for t in current:
                unscheduled.remove(t)
                completed.add(t)
        if degraded:
            # 失败安全: 已排轮次保留 + 剩余任务按拓扑失败安全序逐轮追加
            remaining = [t for t in base_order if t not in {x for r in rounds for x in r}]
            rounds.extend([t] for t in remaining)
        order = [t for r in rounds for t in r]
        conflicts = [dict(c) for c in self._conflicts]
        result = ScheduleResult(
            rounds=rounds,
            order=order,
            conflicts=conflicts,
            state={},
            max_concurrency=max_c,
            created_at=created_at,
            degraded=degraded,
            degradation_reason=degrade_reason,
        )
        return self._finalize(result, state, persist=persist)

    # ------------------------------------------------------------ 冲突检测

    def _detect_file_conflicts(
        self, tasks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """同 target_file 冲突检测 (确定性): 同文件多个任务 → 按计划序
        {file, task_a, task_b} (task_a 先归属, task_b 冲突延迟)。

        只取图内任务; 无 target_file/文件唯一 → 无冲突 (可并行)。
        """
        ordered = [t for t in tasks if _task_id(t)]
        ownership: dict[str, str] = {}
        conflicts: list[dict[str, Any]] = []
        for task in ordered:
            tid = _task_id(task)
            file = _norm_file(task.get("target_file"))
            if not file:
                file = _norm_file(task.get("files")[0]) if task.get("files") else ""
            if not file:
                continue
            owner = ownership.get(file)
            if owner is None:
                ownership[file] = tid
            elif owner != tid:
                conflicts.append({"file": file, "task_a": owner, "task_b": tid})
        return conflicts

    def _resolve_conflict_edges(
        self,
        conflicts: list[dict[str, Any]],
        tasks: list[dict[str, Any]],
        resolver: ConflictResolver,
    ) -> list[tuple[str, str]]:
        """复用 ConflictResolver.resolve (S10-057, 不修改): 同文件冲突 →
        串行化边 (task_a → task_b, 即 b 依赖 a → 不同轮)。

        无冲突 → 直接返回 [] (不调用 resolve, 零副作用零落盘)。
        冲突 → resolve 返回 ordered_tasks 重排 + serial_groups 串行分组;
        本调度器取 冲突对 (a 先 b 后) 转调度边 (b 不并行于 a)。
        """
        if not conflicts:
            return []
        plan_tasks = [t for t in tasks if _task_id(t)]
        try:
            resolved = resolver.resolve(conflicts, plan_tasks)
        except Exception:  # noqa: BLE001 — 失败安全: 解决故障 → 仍按冲突对串行
            resolved = {}
        # 冲突对本身即串行语义 (task_b 延迟到 task_a 之后), 不依赖 resolve 返回值
        edges: list[tuple[str, str]] = []
        for c in conflicts:
            file = str(c.get("file") or "")
            task_a = str(c.get("task_a") or "")
            task_b = str(c.get("task_b") or "")
            if task_a and task_b and task_a != task_b:
                edges.append((task_a, task_b))
            # 冲突审计: 附带 resolution 策略 (resolve 结果或失败安全缺省)
            resolution = _DEFAULT_RESOLUTION
            for r in resolved.get("resolutions") or []:
                if (
                    isinstance(r, dict)
                    and str(r.get("file") or "") == file
                    and str(r.get("task_a") or "") == task_a
                    and str(r.get("task_b") or "") == task_b
                ):
                    resolution = str(r.get("strategy") or _DEFAULT_RESOLUTION)
                    break
            self._conflicts.append(
                {
                    "task": task_b,
                    "reason": (
                        f"同文件冲突: {file} (与 {task_a} 并行会写冲突) "
                        f"— 串行化 {task_b} 到 {task_a} 之后"
                    ),
                    "resolution": resolution,
                }
            )
        return edges

    # ------------------------------------------------------------ 落盘

    def _finalize(
        self,
        result: ScheduleResult,
        state: Any,
        *,
        persist: bool,
    ) -> ScheduleResult:
        """调度结果收尾: 装配 state 视图 (completed + schedule_file + 摘要) + 落盘。

        落盘路径: state["schedule_file"] 或 state["project_dir"]/schedule.json;
        无路径 → 跳过落盘 (调度结果仍返回, 失败安全)。落盘故障 → 静默。
        """
        state_in = state if isinstance(state, dict) else {}
        completed = _completed_ids(state)
        schedule_file: Optional[Path] = None
        raw_path = state_in.get("schedule_file") or (
            Path(str(state_in["project_dir"])) / SCHEDULE_FILE_NAME
            if state_in.get("project_dir")
            else None
        )
        if raw_path:
            schedule_file = Path(str(raw_path))
        view: dict[str, Any] = dict(state_in)
        view["completed"] = sorted(completed)
        if schedule_file is not None:
            view["schedule_file"] = str(schedule_file)
        view["rounds"] = [list(r) for r in result.rounds]
        view["order"] = list(result.order)
        view["max_concurrency"] = result.max_concurrency
        if result.degraded:
            view["degraded"] = True
            view["degradation_reason"] = result.degradation_reason
        result.state = view
        if persist and schedule_file is not None:
            try:
                schedule_file.parent.mkdir(parents=True, exist_ok=True)
                schedule_file.write_text(
                    json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:  # noqa: BLE001 — 失败安全: 落盘故障不中断调度
                pass
        return result


__all__ = [
    "SCHEDULE_FILE_NAME",
    "ScheduleResult",
    "TaskScheduler",
]
