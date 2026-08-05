"""recovery/replay.py — EventReplay: 按 seq 回放事件 → 重建四域状态。

设计依据:
- phase4c3-status.md: EventReplay — 读 EventStore 按 seq 顺序回放 → 重建
  Workflow 状态 / Step 状态 / Assignment 状态 / Execution 状态。
- 事件链即审计真相 (Event Audit): 回放是纯函数 — 给定按 seq 升序的事件列表,
  输出确定性的重建状态, 不读写任何持久化存储 (可测试, 单进程本地)。
- 重建语义镜像既有状态机 (workflows/engine.py + assignment/allocator.py):
  - workflow.started → RUNNING; workflow.completed → COMPLETED; workflow.failed → FAILED;
    全部步骤 COMPLETED 且无终态事件时推导 COMPLETED (事件缺失兜底)。
  - workflow.step.started → 步骤 RUNNING + current_step; step.completed → COMPLETED
    (current_step 推进到下一个未完成步骤, 顺序以 workflow.started 的 step_ids 为准)。
  - execution.created/started/completed/failed → PENDING/RUNNING/SUCCESS/FAILED。
  - agent.assignment.created/started/completed/failed → ASSIGNED/WORKING/COMPLETED/FAILED,
    同步 Agent 状态 (created→WORKING, completed/failed/released→AVAILABLE);
    agent.released → Assignment RELEASED + Agent AVAILABLE; agent.registered → AVAILABLE。
- 未知/无关事件类型静默跳过 (回放容错: 事件库含全局事件, 按 task 过滤后仍可能有
  跨域类型)。

输出 ReplayedState (dataclass): 四域状态 + last_seq (最后回放锚点, RecoveryResult 用)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.models import AgentStatus
from assignment.models import AssignmentStatus
from events.models import Event, EventType
from runtime.models import ExecutionStatus
from workflows.models import StepStatus, WorkflowStatus


@dataclass
class ReplayedState:
    """事件回放重建的四域状态 (纯内存, 无持久化副作用)。"""

    workflow_status: WorkflowStatus | None = None
    run_id: str | None = None
    workflow_id: str | None = None
    current_step: str | None = None
    step_order: list[str] = field(default_factory=list)   # workflow.started 的 step_ids
    steps: dict[str, StepStatus] = field(default_factory=dict)
    assignments: dict[str, AssignmentStatus] = field(default_factory=dict)
    executions: dict[str, ExecutionStatus] = field(default_factory=dict)
    agents: dict[str, AgentStatus] = field(default_factory=dict)
    last_seq: int = 0

    @property
    def state_label(self) -> str:
        """重建工作流状态的人类可读标签 (RecoveryResult.state; 无工作流 → 'none')。"""
        return self.workflow_status.value if self.workflow_status is not None else "none"


class EventReplay:
    """按 seq 顺序回放事件流, 增量重建 Workflow/Step/Assignment/Execution/Agent 状态。"""

    def __init__(self, events: list[Event] | None = None):
        self._state = ReplayedState()
        if events:
            self.replay(events)

    @property
    def state(self) -> ReplayedState:
        return self._state

    # ------------------------------------------------------------------ 回放

    def replay(self, events: list[Event]) -> ReplayedState:
        """按 seq 升序回放事件列表 (调用方保证顺序; 内部仍防御性排序)。"""
        for event in sorted(events, key=lambda e: e.seq):
            self.feed(event)
        return self._state

    def feed(self, event: Event) -> None:
        """回放单条事件 (seq 单调递增, 更新 last_seq 锚点)。"""
        if event.seq > self._state.last_seq:
            self._state.last_seq = event.seq
        handler = _HANDLERS.get(event.type)
        if handler is not None:
            handler(self._state, event.payload)

    # ------------------------------------------------------------------ 便捷

    @staticmethod
    def from_store(event_store: Any, task_id: str) -> "EventReplay":
        """从 EventStore 按任务加载事件链并回放 (EventStore.by_task 按 seq 升序)。"""
        return EventReplay(event_store.by_task(task_id))


# ------------------------------------------------------------------ 事件处理表
# 每个 handler 就地修改 ReplayedState (payload 为 Event.payload, JSON dict)。

# Assignment 终态: RELEASED/COMPLETED/FAILED 后, 后续 assignment.* 事件不回改状态
# (回放幂等 — 终态即审计终点, ADR-0011 决策 2)。
_ASSIGNMENT_TERMINAL = {
    AssignmentStatus.COMPLETED, AssignmentStatus.FAILED, AssignmentStatus.RELEASED,
}


def _on_workflow_started(s: ReplayedState, p: dict) -> None:
    s.workflow_status = WorkflowStatus.RUNNING
    s.run_id = p.get("run_id") or s.run_id
    s.workflow_id = p.get("workflow_id") or s.workflow_id
    step_ids = p.get("step_ids")
    if isinstance(step_ids, list):
        s.step_order = [str(x) for x in step_ids]


def _on_step_started(s: ReplayedState, p: dict) -> None:
    step_id = p.get("step_id")
    if not step_id:
        return
    s.steps[str(step_id)] = StepStatus.RUNNING
    s.current_step = str(step_id)
    if str(step_id) not in s.step_order:
        s.step_order.append(str(step_id))


def _on_step_completed(s: ReplayedState, p: dict) -> None:
    step_id = p.get("step_id")
    if not step_id:
        return
    s.steps[str(step_id)] = StepStatus.COMPLETED
    s.current_step = _next_uncompleted(s)
    if _all_completed(s):
        s.workflow_status = WorkflowStatus.COMPLETED  # 事件缺失兜底 (正常走 workflow.completed)


def _on_workflow_completed(s: ReplayedState, p: dict) -> None:
    s.workflow_status = WorkflowStatus.COMPLETED


def _on_workflow_failed(s: ReplayedState, p: dict) -> None:
    s.workflow_status = WorkflowStatus.FAILED


def _on_execution_created(s: ReplayedState, p: dict) -> None:
    _set_execution(s, p, ExecutionStatus.PENDING)


def _on_execution_started(s: ReplayedState, p: dict) -> None:
    _set_execution(s, p, ExecutionStatus.RUNNING)


def _on_execution_completed(s: ReplayedState, p: dict) -> None:
    _set_execution(s, p, ExecutionStatus.SUCCESS)


def _on_execution_failed(s: ReplayedState, p: dict) -> None:
    _set_execution(s, p, ExecutionStatus.FAILED)


def _set_execution(s: ReplayedState, p: dict, status: ExecutionStatus) -> None:
    execution_id = p.get("execution_id")
    if execution_id:
        s.executions[str(execution_id)] = status


def _on_assignment_created(s: ReplayedState, p: dict) -> None:
    assignment_id = p.get("assignment_id")
    if assignment_id and str(assignment_id) not in s.assignments:
        s.assignments[str(assignment_id)] = AssignmentStatus.ASSIGNED
    agent_id = p.get("agent_id")
    if agent_id:
        s.agents[str(agent_id)] = AgentStatus.WORKING


def _on_assignment_started(s: ReplayedState, p: dict) -> None:
    assignment_id = p.get("assignment_id")
    if not assignment_id:
        return
    if s.assignments.get(str(assignment_id)) in _ASSIGNMENT_TERMINAL:
        return  # 终态不回头 (回放幂等)
    s.assignments[str(assignment_id)] = AssignmentStatus.WORKING


def _on_assignment_completed(s: ReplayedState, p: dict) -> None:
    assignment_id = p.get("assignment_id")
    if assignment_id:
        if s.assignments.get(str(assignment_id)) in _ASSIGNMENT_TERMINAL:
            return  # 终态不回头 (回放幂等)
        s.assignments[str(assignment_id)] = AssignmentStatus.COMPLETED
    agent_id = p.get("agent_id")
    if agent_id:
        s.agents[str(agent_id)] = AgentStatus.AVAILABLE


def _on_assignment_failed(s: ReplayedState, p: dict) -> None:
    assignment_id = p.get("assignment_id")
    if assignment_id:
        if s.assignments.get(str(assignment_id)) in _ASSIGNMENT_TERMINAL:
            return  # 终态不回头 (回放幂等)
        s.assignments[str(assignment_id)] = AssignmentStatus.FAILED
    agent_id = p.get("agent_id")
    if agent_id:
        s.agents[str(agent_id)] = AgentStatus.AVAILABLE


def _on_agent_released(s: ReplayedState, p: dict) -> None:
    assignment_id = p.get("assignment_id")
    if assignment_id:
        s.assignments[str(assignment_id)] = AssignmentStatus.RELEASED
    agent_id = p.get("agent_id")
    if agent_id:
        s.agents[str(agent_id)] = AgentStatus.AVAILABLE


def _on_agent_registered(s: ReplayedState, p: dict) -> None:
    # agent.registered 无 agent_id 载荷 (agent_id 在事件列); 此处仅兜底已知 agent_id
    pass


def _next_uncompleted(s: ReplayedState) -> str | None:
    """按 step_order 找下一个非 COMPLETED 步骤 (含 RUNNING/PENDING/缺失); 全完成 → None。"""
    for step_id in s.step_order:
        if s.steps.get(step_id) is not StepStatus.COMPLETED:
            return step_id
    return None


def _all_completed(s: ReplayedState) -> bool:
    return bool(s.step_order) and all(
        s.steps.get(step_id) is StepStatus.COMPLETED for step_id in s.step_order
    )


_HANDLERS: dict[EventType, Any] = {
    EventType.WORKFLOW_STARTED: _on_workflow_started,
    EventType.WORKFLOW_STEP_STARTED: _on_step_started,
    EventType.WORKFLOW_STEP_COMPLETED: _on_step_completed,
    EventType.WORKFLOW_COMPLETED: _on_workflow_completed,
    EventType.WORKFLOW_FAILED: _on_workflow_failed,
    EventType.EXECUTION_CREATED: _on_execution_created,
    EventType.EXECUTION_STARTED: _on_execution_started,
    EventType.EXECUTION_COMPLETED: _on_execution_completed,
    EventType.EXECUTION_FAILED: _on_execution_failed,
    EventType.ASSIGNMENT_CREATED: _on_assignment_created,
    EventType.ASSIGNMENT_STARTED: _on_assignment_started,
    EventType.ASSIGNMENT_COMPLETED: _on_assignment_completed,
    EventType.ASSIGNMENT_FAILED: _on_assignment_failed,
    EventType.AGENT_RELEASED: _on_agent_released,
    EventType.AGENT_REGISTERED: _on_agent_registered,
}
