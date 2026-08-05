"""metrics/calculators.py — 指标计算 (纯函数, 无副作用, 不碰 store)。

设计依据:
- phase5b-status.md: Task/Execution/Agent/Workflow/Validation/Failure 六域指标,
  含 first_attempt_success_rate 与 failure_reason_count
- ADR-0015 决策 3/4: 口径统一在 models.py docstring 与 ADR 中定义; 计算为
  「数据 → 指标模型」纯函数, 输入序列化数据 (models/事件), 输出 Pydantic 模型,
  便于单测直接构造输入 (空工厂/大数据/混合数据) 而不依赖任何 store。

只读铁律: 本模块不 import 任何 store, 不写任何状态。
"""

from __future__ import annotations

from collections import Counter
from typing import Sequence

from agents.models import Agent
from events.models import Event, EventType
from runtime.models import ExecutionRequest, ExecutionStatus
from tasks.models import Task, TaskStatus
from workflows.models import Workflow, WorkflowRun, WorkflowStatus

from .models import (
    AgentMetric,
    ExecutionMetrics,
    FailureMetrics,
    TaskMetrics,
    ValidationMetrics,
    WorkflowMetrics,
)


# ------------------------------------------------------------------ Task

def calculate_task_metrics(tasks: Sequence[Task], events: Sequence[Event]) -> TaskMetrics:
    """任务指标: total/completed/failed/success_rate/by_status。

    failed = 有 task.fail 事件的 distinct 任务数 (TaskStatus 无 FAILED 态,
    失败只能从事件观测 — ADR-0015 决策 3)。success_rate 分母 = completed + failed。
    """
    completed = sum(1 for t in tasks if t.status is TaskStatus.DONE)
    failed_tasks = {e.task_id for e in events if e.type is EventType.TASK_FAIL and e.task_id}
    failed = len(failed_tasks)
    denom = completed + failed
    by_status = Counter(t.status.value for t in tasks)
    return TaskMetrics(
        total=len(tasks),
        completed=completed,
        failed=failed,
        success_rate=(completed / denom) if denom else 0.0,
        by_status=dict(sorted(by_status.items())),
    )


# ------------------------------------------------------------------ Execution

def calculate_execution_metrics(requests: Sequence[ExecutionRequest]) -> ExecutionMetrics:
    """执行指标: total/success/failed/first_attempt_success_rate/by_status。

    请求状态为权威 (runtime/models.py: PENDING→RUNNING→SUCCESS|FAILED);
    first_attempt_success_rate 见 calculate_first_attempt_success_rate。
    """
    by_status = Counter(r.status.value for r in requests)
    success = by_status.get(ExecutionStatus.SUCCESS.value, 0)
    failed = by_status.get(ExecutionStatus.FAILED.value, 0)
    return ExecutionMetrics(
        total=len(requests),
        success=success,
        failed=failed,
        first_attempt_success_rate=calculate_first_attempt_success_rate(requests),
        by_status=dict(sorted(by_status.items())),
    )


def calculate_first_attempt_success_rate(requests: Sequence[ExecutionRequest]) -> float:
    """一次成功率 (ADR-0015 决策 4): 每任务取最早执行 (created_at, id 决胜),
    已到达终态 (SUCCESS/FAILED) 的任务中, 首次执行即 SUCCESS 的比例; 无则 0.0。

    未终态 (PENDING/RUNNING) 的首次执行不进分母 — 尚未分出成败, 不应拉低比率。
    """
    first: dict[str, ExecutionRequest] = {}
    for req in requests:
        prev = first.get(req.task_id)
        if prev is None or (req.created_at, req.id) < (prev.created_at, prev.id):
            first[req.task_id] = req
    resolved = [
        r for r in first.values()
        if r.status in (ExecutionStatus.SUCCESS, ExecutionStatus.FAILED)
    ]
    if not resolved:
        return 0.0
    ok = sum(1 for r in resolved if r.status is ExecutionStatus.SUCCESS)
    return ok / len(resolved)


# ------------------------------------------------------------------ Agent

def calculate_agent_metrics(
    agents: Sequence[Agent], events: Sequence[Event],
) -> tuple[dict[str, AgentMetric], int]:
    """Agent 指标: {agent_id: AgentMetric} + 注册 Agent 总数。

    assignment_count 来自 agent.assignment.created 事件; 成败来自
    agent.assignment.completed/failed。注册表兜底: 无活动 Agent 出 0 指标;
    事件中出现的未注册 agent_id 也纳入 (事件维度完整, 排序输出)。
    """
    created: Counter[str] = Counter()
    completed: Counter[str] = Counter()
    failed: Counter[str] = Counter()
    for e in events:
        if not e.agent_id:
            continue
        if e.type is EventType.ASSIGNMENT_CREATED:
            created[e.agent_id] += 1
        elif e.type is EventType.ASSIGNMENT_COMPLETED:
            completed[e.agent_id] += 1
        elif e.type is EventType.ASSIGNMENT_FAILED:
            failed[e.agent_id] += 1

    active = set(created) | set(completed) | set(failed)
    out: dict[str, AgentMetric] = {}
    for agent_id in sorted({a.id for a in agents} | active):
        c, s, f = created.get(agent_id, 0), completed.get(agent_id, 0), failed.get(agent_id, 0)
        out[agent_id] = AgentMetric(
            assignment_count=c,
            success_count=s,
            failed_count=f,
            success_rate=(s / (s + f)) if (s + f) else 0.0,
        )
    return out, len(agents)


# ------------------------------------------------------------------ Workflow

def calculate_workflow_metrics(
    runs: Sequence[WorkflowRun], definitions: Sequence[Workflow],
) -> WorkflowMetrics:
    """工作流指标: run_count/completed/failed/success_rate/definitions/by_status。

    success_rate = completed / run_count (全部运行实例, 同 dashboard 执行口径 —
    未完成运行计入分母, ADR-0015 决策 3)。
    """
    by_status = Counter(r.status.value for r in runs)
    completed = by_status.get(WorkflowStatus.COMPLETED.value, 0)
    failed = by_status.get(WorkflowStatus.FAILED.value, 0)
    return WorkflowMetrics(
        run_count=len(runs),
        completed=completed,
        failed=failed,
        success_rate=(completed / len(runs)) if runs else 0.0,
        definitions=len(definitions),
        by_status=dict(sorted(by_status.items())),
    )


# ------------------------------------------------------------------ Validation

def calculate_validation_metrics(events: Sequence[Event]) -> ValidationMetrics:
    """验证指标: validation.rule.completed 结果列聚合 (PASS/FAIL/SKIP/ERROR 粒度,
    单次验证每规则一条, 无重复计数); pass_rate = PASS / total_rules (含 SKIP/ERROR 分母)。
    runs/failed_runs 来自 validation.completed / validation.failed 事件数。
    """
    rule_events = [e for e in events if e.type is EventType.VALIDATION_RULE_COMPLETED]
    results = Counter(e.result or "" for e in rule_events)
    total = len(rule_events)
    pass_count = results.get("PASS", 0)
    return ValidationMetrics(
        total_rules=total,
        pass_count=pass_count,
        fail_count=results.get("FAIL", 0),
        skip_count=results.get("SKIP", 0),
        error_count=results.get("ERROR", 0),
        pass_rate=(pass_count / total) if total else 0.0,
        runs=sum(1 for e in events if e.type is EventType.VALIDATION_COMPLETED),
        failed_runs=sum(1 for e in events if e.type is EventType.VALIDATION_FAILED),
    )


# ------------------------------------------------------------------ Failure

def calculate_failure_reason_count(events: Sequence[Event]) -> dict[str, int]:
    """失败原因直方图 (ADR-0015 决策 3): task.fail 事件的 payload.stage (失败阶段)
    为归类键, 无 stage 回落 payload.error, 再回落 "unknown"; 次数降序输出。

    注: stage 是有界类别 (架构/开发/测试/运行等), 比自由文本 error 更适合作直方图键。
    """
    counts: Counter[str] = Counter()
    for e in events:
        if e.type is not EventType.TASK_FAIL:
            continue
        payload = e.payload or {}
        reason = payload.get("stage") or payload.get("error") or "unknown"
        counts[str(reason)] += 1
    return dict(counts.most_common())


def calculate_failure_metrics(events: Sequence[Event]) -> FailureMetrics:
    """FailureMetrics 便捷装配 (collector 用)。"""
    return FailureMetrics(failure_reason_count=calculate_failure_reason_count(events))
