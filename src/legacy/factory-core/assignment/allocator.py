"""assignment/allocator.py — AgentAllocator: assign/start/complete/fail/release 生命周期。

设计依据:
- phase4b3-status.md: AgentAllocator — assign()/release()/complete() + Agent 状态
  WORKING↔AVAILABLE; 原则 Agent != Assignment (Registry 只存员工信息+状态, Assignment
  存工作关系, 不混写); Event 集成 (agent.assignment.created/started/completed/failed +
  agent.released); Execution 集成 (填充 ExecutionRequest.agent_id, 不自动执行)。
- 事件序 (ADR-0008 决策 1): assign→created; start→started; complete→completed+released;
  fail→failed+released; release→released。写方法返回 `(对象, Event | None)` —
  与 AgentRegistry/WorkflowEngine 模式一致 (Event 含存储层回填的 seq); 多事件时
  返回最后一个 (最相关, 同 workflows.complete_step 口径)。

状态机 (AssignmentStatus):
  ASSIGNED → {WORKING, COMPLETED, FAILED, RELEASED}
  WORKING  → {COMPLETED, FAILED, RELEASED}
  COMPLETED/FAILED/RELEASED → 终态 (无出口)

Agent 侧同步: assign → mark_working (status=WORKING, current_task=task_id);
complete/fail/release → mark_available (status=AVAILABLE, current_task=None)。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agents.models import AgentStatus
from agents.registry import AgentNotFoundError, AgentRegistry
from events.logger import EventLogger
from events.models import Event, EventType
from runtime.store import RuntimeStore
from workflows.models import WorkflowStep

from .matcher import AgentMatcher
from .models import AgentAssignment, AssignmentStatus
from .store import AssignmentStore

# Assignment 状态转换表 (终态无出口)
_TRANSITIONS: dict[AssignmentStatus, set[AssignmentStatus]] = {
    AssignmentStatus.ASSIGNED: {
        AssignmentStatus.WORKING, AssignmentStatus.COMPLETED,
        AssignmentStatus.FAILED, AssignmentStatus.RELEASED,
    },
    AssignmentStatus.WORKING: {
        AssignmentStatus.COMPLETED, AssignmentStatus.FAILED, AssignmentStatus.RELEASED,
    },
    AssignmentStatus.COMPLETED: set(),
    AssignmentStatus.FAILED: set(),
    AssignmentStatus.RELEASED: set(),
}


class AgentAllocatorError(Exception):
    """AgentAllocator 基础异常。"""


class NoAvailableAgentError(AgentAllocatorError):
    """没有满足步骤要求的 AVAILABLE Agent (匹配失败)。"""


class AgentNotAvailableError(AgentAllocatorError):
    """显式指定的 Agent 存在但不可用 (非 AVAILABLE)。"""


class AssignmentNotFoundError(AgentAllocatorError):
    """Assignment 不存在。"""


class AssignmentStateError(AgentAllocatorError):
    """非法状态转换 (状态机拒绝)。"""


class AgentAllocator:
    """Agent 分配器: Assignment 生命周期 + Agent 状态同步 + Event/Execution 集成。"""

    SOURCE = "agent_allocator"  # event-model §2.1 source 取值

    def __init__(
        self,
        store: AssignmentStore,
        registry: AgentRegistry,
        matcher: AgentMatcher | None = None,
        logger: EventLogger | None = None,
        runtime_store: RuntimeStore | None = None,
    ):
        self._store = store
        self._registry = registry
        self._matcher = matcher if matcher is not None else AgentMatcher(registry)
        self._logger = logger
        self._runtime_store = runtime_store

    @property
    def store(self) -> AssignmentStore:
        return self._store

    @property
    def matcher(self) -> AgentMatcher:
        return self._matcher

    # ------------------------------------------------------------------ 转换表 (审计/测试入口)

    @staticmethod
    def is_valid_transition(from_: AssignmentStatus, to: AssignmentStatus) -> bool:
        """Assignment 状态转换是否合法 (状态机校验, 公开供审计/测试)。"""
        return to in _TRANSITIONS.get(from_, set())

    # ------------------------------------------------------------------ 分配

    def assign(
        self,
        task_id: str,
        *,
        step: WorkflowStep | None = None,
        agent_id: str | None = None,
        workflow_id: str | None = None,
        workflow_step_id: str | None = None,
        execution_id: str | None = None,
    ) -> tuple[AgentAssignment, Event | None]:
        """分配: AVAILABLE Agent → 创建 Assignment (ASSIGNED) → Agent WORKING → 发 created。

        - agent_id 显式指定: 须存在 (AgentNotFoundError) 且 AVAILABLE (AgentNotAvailableError)。
        - 未指定: matcher 按 step 挑最优候选; 无候选抛 NoAvailableAgentError。
        - execution_id 且装配 runtime_store: 校验执行存在并回填 agent_id (不自动执行)。
        """
        if agent_id is not None:
            agent = self._registry.get(agent_id)
            if agent is None:
                raise AgentNotFoundError(f"agent not found: {agent_id}")
            if agent.status is not AgentStatus.AVAILABLE:
                raise AgentNotAvailableError(
                    f"agent not available: {agent_id} (status={agent.status.value}); "
                    f"expected AVAILABLE"
                )
        elif step is not None:
            agent = self._matcher.best(step)
            if agent is None:
                raise NoAvailableAgentError(
                    f"no available agent for step {step.id!r} "
                    f"(role={step.required_role!r}, skill={step.required_skill!r})"
                )
        else:
            raise AgentAllocatorError("assign requires either agent_id or step")

        if execution_id is not None:
            self._require_execution(execution_id)  # 先校验, 再落状态 (避免半途变更)

        assignment = AgentAssignment(
            id=self._store.next_id(),
            agent_id=agent.id,
            task_id=task_id,
            workflow_id=workflow_id,
            workflow_step_id=workflow_step_id or (step.id if step is not None else None),
            execution_id=execution_id,
            status=AssignmentStatus.ASSIGNED,
        )
        self._store.save(assignment)
        self._registry.mark_working(agent.id, task_id=task_id)
        if execution_id is not None and self._runtime_store is not None:
            self._fill_execution_agent(execution_id, agent.id)
        ev = self._emit(
            EventType.ASSIGNMENT_CREATED, assignment,
            action=f"assign agent {agent.id} to task {task_id}",
            agent_status=AgentStatus.WORKING.value,
        )
        return assignment, ev

    def start(self, assignment_id: str) -> tuple[AgentAssignment, Event | None]:
        """开始工作: ASSIGNED → WORKING; 发 agent.assignment.started。"""
        assignment = self._require_non_terminal(assignment_id)
        self._transition(assignment, AssignmentStatus.WORKING)
        self._save(assignment)
        ev = self._emit(
            EventType.ASSIGNMENT_STARTED, assignment,
            action=f"start assignment {assignment_id}",
            agent_status=AgentStatus.WORKING.value,
        )
        return assignment, ev

    def complete(self, assignment_id: str, *, result: str = "OK") -> tuple[AgentAssignment, Event | None]:
        """完成工作: ASSIGNED/WORKING → COMPLETED, Agent 回 AVAILABLE;
        发 agent.assignment.completed + agent.released (释放是完成的后果, 事件序 completed→released)。"""
        assignment = self._require_non_terminal(assignment_id)
        self._finish(assignment, AssignmentStatus.COMPLETED, payload={"result": result})
        self._emit(
            EventType.ASSIGNMENT_COMPLETED, assignment,
            action=f"complete assignment {assignment_id}", result=result,
            agent_status=AgentStatus.AVAILABLE.value, payload={"result": result},
        )
        ev = self._emit(
            EventType.AGENT_RELEASED, assignment,
            action=f"release agent {assignment.agent_id} after completion",
            agent_status=AgentStatus.AVAILABLE.value,
        )
        return assignment, ev

    def fail(self, assignment_id: str, *, error: str | None = None) -> tuple[AgentAssignment, Event | None]:
        """标记失败: ASSIGNED/WORKING → FAILED, Agent 回 AVAILABLE;
        发 agent.assignment.failed + agent.released。"""
        assignment = self._require_non_terminal(assignment_id)
        self._finish(assignment, AssignmentStatus.FAILED, payload={"error": error})
        self._emit(
            EventType.ASSIGNMENT_FAILED, assignment,
            action=f"fail assignment {assignment_id}", result="failed",
            agent_status=AgentStatus.AVAILABLE.value, payload={"error": error},
        )
        ev = self._emit(
            EventType.AGENT_RELEASED, assignment,
            action=f"release agent {assignment.agent_id} after failure",
            agent_status=AgentStatus.AVAILABLE.value,
        )
        return assignment, ev

    def release(self, assignment_id: str) -> tuple[AgentAssignment, Event | None]:
        """提前解除: ASSIGNED/WORKING → RELEASED, Agent 回 AVAILABLE; 发 agent.released。"""
        assignment = self._require_non_terminal(assignment_id)
        self._finish(assignment, AssignmentStatus.RELEASED)
        ev = self._emit(
            EventType.AGENT_RELEASED, assignment,
            action=f"release agent {assignment.agent_id} (assignment {assignment_id})",
            agent_status=AgentStatus.AVAILABLE.value,
        )
        return assignment, ev

    # ------------------------------------------------------------------ 读

    def get(self, assignment_id: str) -> AgentAssignment | None:
        """按 id 取 Assignment; 不存在返回 None。"""
        return self._store.load(assignment_id)

    def list(
        self,
        *,
        task_id: str | None = None,
        agent_id: str | None = None,
        status: AssignmentStatus | str | None = None,
    ) -> list[AgentAssignment]:
        """全部 Assignment (按 id 排序), 可选按任务/Agent/状态过滤。"""
        return self._store.list(task_id=task_id, agent_id=agent_id, status=status)

    # ------------------------------------------------------------------ 内部

    def _require_non_terminal(self, assignment_id: str) -> AgentAssignment:
        """取 Assignment 并校验非终态 (状态机前置条件)。"""
        assignment = self._store.load(assignment_id)
        if assignment is None:
            raise AssignmentNotFoundError(f"assignment not found: {assignment_id}")
        if assignment.status in (AssignmentStatus.COMPLETED, AssignmentStatus.FAILED,
                                 AssignmentStatus.RELEASED):
            raise AssignmentStateError(
                f"assignment is in terminal state {assignment.status.value}: {assignment_id}"
            )
        return assignment

    def _finish(self, assignment: AgentAssignment, to: AssignmentStatus, *, payload: dict | None = None) -> None:
        """终态收尾 (共用): 状态转换 + completed_at 回填 + Agent 回 AVAILABLE + 落盘。"""
        self._transition(assignment, to)
        assignment.completed_at = datetime.now(timezone.utc)
        self._save(assignment)
        self._registry.mark_available(assignment.agent_id)

    def _transition(self, assignment: AgentAssignment, to: AssignmentStatus) -> None:
        """Assignment 状态转换 (校验 + 就地修改; 修改后由调用方落盘)。"""
        if not self.is_valid_transition(assignment.status, to):
            raise AssignmentStateError(
                f"invalid assignment transition: {assignment.id} "
                f"{assignment.status.value} -> {to.value}"
            )
        assignment.status = to

    def _save(self, assignment: AgentAssignment) -> None:
        assignment.updated_at = datetime.now(timezone.utc)
        self._store.save(assignment)

    def _require_execution(self, execution_id: str) -> None:
        """校验执行请求存在 (显式 execution_id 引用须有效; 不自动执行)。"""
        if self._runtime_store is None:
            return
        if self._runtime_store.get_execution(execution_id) is None:
            raise AgentAllocatorError(f"execution not found: {execution_id}")

    def _fill_execution_agent(self, execution_id: str, agent_id: str) -> None:
        """Execution 集成: 回填 ExecutionRequest.agent_id (状态/事件不动, ADR-0008 决策 4)。"""
        if self._runtime_store is None:
            return  # 未装配 runtime_store: 不填充 (调用方已校验 execution_id 引用)
        request = self._runtime_store.get_execution(execution_id)
        if request is None:
            return  # _require_execution 已校验; 双保险
        request.agent_id = agent_id
        self._runtime_store.save_execution(request)

    def _emit(
        self,
        type_: EventType,
        assignment: AgentAssignment,
        *,
        action: str,
        agent_status: str,
        result: str = "OK",
        payload: dict[str, Any] | None = None,
    ) -> Event | None:
        if self._logger is None:
            return None
        return self._logger.record(
            type_, source=self.SOURCE,
            task_id=assignment.task_id, agent_id=assignment.agent_id,
            stage=assignment.status.value.lower(), action=action, result=result,
            payload={
                "assignment_id": assignment.id,
                "agent_id": assignment.agent_id,
                "task_id": assignment.task_id,
                "workflow_id": assignment.workflow_id,
                "workflow_step_id": assignment.workflow_step_id,
                "execution_id": assignment.execution_id,
                "status": assignment.status.value,
                "agent_status": agent_status,
                **(payload or {}),
            },
        )
