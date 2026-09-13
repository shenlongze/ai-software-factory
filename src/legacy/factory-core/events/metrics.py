"""events/metrics.py — 指标聚合 (从事件计算, 不另建统计表)。

设计依据:
- phase1-plan.md §5: compute_metrics + Metrics 模型 + to_markdown
- event-model.md §6: 指标一律按需从 events 表聚合, 不维护统计表

口径 (phase1-plan §5):
- task_count        = 有 task.start 的 distinct task_id 数
- success_count     = task.end 且 payload.result == "done"
- fail_count        = task.fail 事件数
- success_rate      = success / (success + fail), 无任务时为 0.0
- avg_task_duration = task.end.timestamp − task.start.timestamp (秒, 取最后一次 start)
- avg_retry_count   = 同一 task_id 的 task.start 次数 − 1 的平均
- interrupted_count = 有 checkpoint 但无 task.end 的任务数 (中断/未完成)
- result_counts     = 按 result 语义列计数 (OK/PASS/FAIL/ERROR/done/failed/...)
                      承载 event-model 的 validation 结果统计: 扩出 validation.* 事件后
                      直接聚合 result 列即可, 无需改表。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Iterable, Sequence

from pydantic import BaseModel, Field

from .models import Event, EventType


class Metrics(BaseModel):
    """一个分组键下的指标快照。"""

    group_by: str = "all"                    # all / day / session / agent
    event_count: int = 0
    task_count: int = 0                      # distinct task (有 task.start)
    success_count: int = 0                   # task.end result=="done"
    fail_count: int = 0                      # task.fail
    success_rate: float = 0.0                # success / (success + fail)
    avg_task_duration_s: float = 0.0
    avg_retry_count: float = 0.0
    tool_call_count: int = 0
    avg_tool_calls_per_task: float = 0.0
    interrupted_count: int = 0               # checkpoint 后无 task.end 的任务数
    result_counts: dict[str, int] = Field(default_factory=dict)  # 按 result 列计数

    def to_markdown(self) -> str:
        """供 Phase 2 Dashboard / factory metrics 直接渲染。"""
        return "\n".join(
            [
                f"## Metrics ({self.group_by})",
                "",
                f"- 事件数 event_count: {self.event_count}",
                f"- 任务数 task_count: {self.task_count}",
                f"- 成功/失败 success/fail: {self.success_count}/{self.fail_count}",
                f"- 成功率 success_rate: {self.success_rate:.1%}",
                f"- 平均任务耗时 avg_task_duration_s: {self.avg_task_duration_s:.2f}",
                f"- 平均重试 avg_retry_count: {self.avg_retry_count:.2f}",
                f"- 工具调用 tool_call_count: {self.tool_call_count}",
                f"- 每任务工具调用 avg_tool_calls_per_task: {self.avg_tool_calls_per_task:.2f}",
                f"- 中断任务 interrupted_count: {self.interrupted_count}",
            ]
        )


class AgentMetrics(BaseModel):
    """单个 Agent 的执行统计 (metrics_by_agent 用)。"""

    agent_id: str
    event_count: int = 0                     # Agent 执行次数 (事件数)
    task_count: int = 0
    tool_call_count: int = 0
    success_count: int = 0                   # result == "done"
    fail_count: int = 0                      # result == "failed"


def compute_metrics(events: Sequence[Event], *, group_by: str = "all", project_id: str | None = None) -> Metrics:
    """单组聚合。project_id 非空时先按项目过滤 (指标按项目维度查询)。"""
    evs = [e for e in events if project_id is None or e.project_id == project_id]
    m = _aggregate(evs)
    return m.model_copy(update={"group_by": group_by})


def metrics_by_day(events: Sequence[Event], *, project_id: str | None = None) -> dict[str, Metrics]:
    """按事件日期 (YYYY-MM-DD, UTC) 分组聚合。"""
    evs = [e for e in events if project_id is None or e.project_id == project_id]
    groups: dict[str, list[Event]] = defaultdict(list)
    for e in evs:
        groups[e.timestamp.date().isoformat()].append(e)
    return {k: _aggregate(v).model_copy(update={"group_by": f"day:{k}"}) for k, v in sorted(groups.items())}


def metrics_by_session(events: Sequence[Event], *, project_id: str | None = None) -> dict[str, Metrics]:
    """按会话分组聚合 (组键 = payload.session_id; 无则归 "unknown")。"""
    evs = [e for e in events if project_id is None or e.project_id == project_id]
    groups: dict[str, list[Event]] = defaultdict(list)
    for e in evs:
        sid = (e.payload or {}).get("session_id")
        groups[str(sid) if sid else "unknown"].append(e)
    return {k: _aggregate(v).model_copy(update={"group_by": f"session:{k}"}) for k, v in sorted(groups.items())}


def metrics_by_agent(events: Sequence[Event], *, project_id: str | None = None) -> dict[str, AgentMetrics]:
    """按 agent_id 分组: Agent 执行次数 / 工具调用 / 成败。agent_id 为空的事件忽略。"""
    evs = [e for e in events if project_id is None or e.project_id == project_id]
    groups: dict[str, list[Event]] = defaultdict(list)
    for e in evs:
        if e.agent_id:
            groups[e.agent_id].append(e)
    out: dict[str, AgentMetrics] = {}
    for agent_id, g in sorted(groups.items()):
        m = _aggregate(g)
        out[agent_id] = AgentMetrics(
            agent_id=agent_id,
            event_count=len(g),
            task_count=m.task_count,
            tool_call_count=m.tool_call_count,
            success_count=sum(1 for e in g if e.result == "done"),
            fail_count=sum(1 for e in g if e.result == "failed"),
        )
    return out


def _aggregate(events: Iterable[Event]) -> Metrics:
    """核心聚合: 单次遍历事件流, 状态放局部 dict, 不落库 (KISS)。"""
    task_starts: Counter[str] = Counter()            # task_id -> task.start 次数
    last_start_ts: dict[str, datetime] = {}          # task_id -> 最后一次 start 时间
    ended_tasks: set[str] = set()                    # 有 task.end 的任务
    checkpoint_tasks: set[str] = set()               # 有 checkpoint 的任务
    durations: list[float] = []
    event_count = 0
    success = fail = tool_calls = 0
    result_counts: Counter[str] = Counter()

    for e in events:
        event_count += 1
        if e.result:
            result_counts[e.result] += 1
        tid = e.task_id or ""  # task_id 可空 (Event 模型), 聚合时归 "" 键
        if e.type is EventType.TASK_START:
            task_starts[tid] += 1
            last_start_ts[tid] = e.timestamp
        elif e.type is EventType.TASK_END:
            ended_tasks.add(tid)
            if (e.payload or {}).get("result") == "done":
                success += 1
            else:
                fail += 1
            start = last_start_ts.get(tid)
            if start is not None:
                durations.append((e.timestamp - start).total_seconds())
        elif e.type is EventType.TASK_FAIL:
            fail += 1
        elif e.type is EventType.TOOL_CALL:
            tool_calls += 1
        elif e.type is EventType.CHECKPOINT:
            checkpoint_tasks.add(tid)

    task_count = len(task_starts)
    total_end = success + fail
    retries = sum(c - 1 for c in task_starts.values() if c > 1)
    return Metrics(
        event_count=event_count,
        task_count=task_count,
        success_count=success,
        fail_count=fail,
        success_rate=(success / total_end) if total_end else 0.0,
        avg_task_duration_s=sum(durations) / len(durations) if durations else 0.0,
        avg_retry_count=(retries / task_count) if task_count else 0.0,
        tool_call_count=tool_calls,
        avg_tool_calls_per_task=(tool_calls / task_count) if task_count else 0.0,
        interrupted_count=len(checkpoint_tasks - ended_tasks),
        result_counts=dict(result_counts),
    )
