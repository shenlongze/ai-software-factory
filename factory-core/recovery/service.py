"""recovery/service.py — RecoveryService: checkpoint / recover 两个操作流。

设计依据:
- phase4c3-status.md: RecoveryService — checkpoint(task_id) / recover(task_id):
  recover: load events → rebuild state → compare persisted state (workflow/assignments/
  executions) → return RecoveryResult。
- 恢复语义 (Event Audit 原则): 事件链是"发生了什么"的审计真相, 持久化状态是
  "现在卡在哪"的现场。recover 回放事件重建四域状态 (EventReplay), 与持久化
  (WorkflowRun / Assignment / Execution / Agent) 比对, 识别中断模式并纠正:
  - 场景1 (Workflow RUNNING): 继续当前 Step (resume_ok=True, 动作: continue step)。
  - 场景2 (Execution RUNNING): 标记可重试 — RUNNING → PENDING (可重新派发至 RUNNING)。
  - 场景3 (Agent WORKING / Assignment 非终态): 释放 Agent → AVAILABLE,
    Assignment 同步 → RELEASED (不留占用残留)。
  - 场景4 (Workflow 已完成/已失败): 拒绝 (resume_ok=False), 不改任何状态。
- 纠正动作直接经持久化原语 (RuntimeStore.save_execution / AssignmentStore.save /
  AgentRegistry.mark_available), 不发 agent.released 等域事件 — 恢复动作的审计
  由 recovery.* 事件承载 (ADR-0011 决策 3), 与正常释放流事件隔离。
- Event 集成 (经 EventLogger, source="recovery_service"):
  checkpoint: recovery.started (stage=checkpoint) → recovery.completed;
  recover: recovery.started → recovery.completed (result=OK / rejected) 或
  recovery.failed (异常时)。写方法返回 `(对象, Event | None)` — 与
  AgentRegistry/WorkflowEngine 模式一致, 返回最后一个事件 (最相关)。
- 幂等: 重复 recover 无 RUNNING execution / 非终态 assignment 可纠正时,
  结果与动作清单稳定, 不产生重复副作用 (纠正动作均以状态检查为前置)。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agents.registry import AgentNotFoundError, AgentRegistry
from assignment.models import AssignmentStatus
from assignment.store import AssignmentStore
from events.logger import EventLogger
from events.models import Event, EventType
from events.store import EventStore
from runtime.models import ExecutionStatus
from runtime.store import RuntimeStore
from tasks.store import TaskStore
from workflows.models import WorkflowStatus
from workflows.store import WorkflowStore

from .checkpoint import CheckpointStore
from .models import Checkpoint, RecoveryResult
from .replay import EventReplay


class RecoveryError(Exception):
    """RecoveryService 基础异常。"""


class TaskNotFoundError(RecoveryError):
    """任务不存在 (checkpoint/recover 前置条件)。"""


class RecoveryStateError(RecoveryError):
    """恢复流程内部状态错误 (如缺少 checkpoint store)。"""


class RecoveryService:
    """Checkpoint 快照 + 事件回放恢复 (单进程本地, JSON/SQLite 持久化)。"""

    SOURCE = "recovery_service"  # event-model §2.1 source 取值

    def __init__(
        self,
        *,
        task_store: TaskStore,
        workflow_store: WorkflowStore,
        assignment_store: AssignmentStore,
        runtime_store: RuntimeStore,
        agent_registry: AgentRegistry,
        event_store: EventStore,
        checkpoint_store: CheckpointStore | None = None,
        logger: EventLogger | None = None,
    ):
        self._task_store = task_store
        self._workflow_store = workflow_store
        self._assignment_store = assignment_store
        self._runtime_store = runtime_store
        self._agent_registry = agent_registry
        self._event_store = event_store
        self._checkpoint_store = checkpoint_store
        self._logger = logger

    # ------------------------------------------------------------------ 依赖暴露 (审计/测试)

    @property
    def task_store(self) -> TaskStore:
        return self._task_store

    @property
    def workflow_store(self) -> WorkflowStore:
        return self._workflow_store

    @property
    def assignment_store(self) -> AssignmentStore:
        return self._assignment_store

    @property
    def runtime_store(self) -> RuntimeStore:
        return self._runtime_store

    @property
    def agent_registry(self) -> AgentRegistry:
        return self._agent_registry

    @property
    def event_store(self) -> EventStore:
        return self._event_store

    @property
    def checkpoint_store(self) -> CheckpointStore | None:
        return self._checkpoint_store

    @property
    def logger(self) -> EventLogger | None:
        return self._logger

    # ------------------------------------------------------------------ checkpoint

    def checkpoint(self, task_id: str) -> tuple[Checkpoint, Event | None]:
        """创建任务 checkpoint: 持久化状态快照 + 事件回放锚点, 原子落盘。

        流程: 任务存在 → 读 WorkflowRun/Assignments/Executions/Agent 状态 →
        计算 event_seq 锚点 (该任务最近事件 seq) → 构建 Checkpoint → 落盘
        (存储先落地, 事件后发 — 铁律) → 发 recovery.started + recovery.completed。
        返回 (Checkpoint, 最后事件); 同任务重复调用覆盖旧快照 (最新停靠点为准)。
        """
        if self._task_store.get(task_id) is None:
            raise TaskNotFoundError(f"task not found: {task_id}")
        if self._checkpoint_store is None:
            raise RecoveryStateError("recovery service has no checkpoint store")
        run = self._workflow_store.get_run_by_task(task_id)
        assignments = self._assignment_store.list(task_id=task_id)
        executions = self._runtime_store.list_executions(task_id=task_id)
        events = self._event_store.by_task(task_id)
        last_seq = events[-1].seq if events else 0
        agents = self._agent_snapshot(assignments, executions)
        checkpoint = Checkpoint(
            id=f"CKPT-{task_id}",
            task_id=task_id,
            workflow_id=run.workflow_id if run is not None else None,
            event_seq=last_seq,
            workflow_state=run.to_dict() if run is not None else None,
            current_step=run.current_step if run is not None else None,
            agents=agents,
            executions={e.id: e.status.value for e in executions},
        )
        self._checkpoint_store.save(checkpoint)
        self._emit(
            EventType.RECOVERY_STARTED, task_id, stage="checkpoint",
            action=f"create checkpoint for task {task_id}", result="OK",
            payload={"checkpoint_id": checkpoint.id, "event_seq": last_seq},
        )
        ev = self._emit(
            EventType.RECOVERY_COMPLETED, task_id, stage="checkpoint",
            action="checkpoint created", result="OK",
            payload={
                "checkpoint_id": checkpoint.id,
                "event_seq": last_seq,
                "workflow_id": checkpoint.workflow_id,
                "current_step": checkpoint.current_step,
            },
        )
        return checkpoint, ev

    # ------------------------------------------------------------------ recover

    def recover(self, task_id: str) -> tuple[RecoveryResult, Event | None]:
        """恢复任务: 回放事件重建状态 → 比对持久化 → 纠正中断 → 返回 RecoveryResult。

        四场景判定 (见模块 docstring): RUNNING 继续 / Execution 重试 / Agent 释放 /
        已完成拒绝。发 recovery.started → recovery.completed|failed。
        返回 (RecoveryResult, 最后事件); 任务不存在抛 TaskNotFoundError (rc 7)。
        """
        self._emit(
            EventType.RECOVERY_STARTED, task_id, stage="recovering",
            action="start recovery", result="OK", payload={"task_id": task_id},
        )
        try:
            result = self._do_recover(task_id)
        except RecoveryError as exc:
            self._emit(
                EventType.RECOVERY_FAILED, task_id, stage="failed",
                action="recovery failed", result="failed",
                payload={"task_id": task_id, "error": str(exc)},
            )
            raise
        except Exception as exc:  # 兜底: 内部异常 → recovery.failed + 包装抛错
            message = f"{type(exc).__name__}: {exc}"
            self._emit(
                EventType.RECOVERY_FAILED, task_id, stage="failed",
                action="recovery failed", result="failed",
                payload={"task_id": task_id, "error": message},
            )
            raise RecoveryError(f"recovery failed: {message}") from exc
        ev = self._emit(
            EventType.RECOVERY_COMPLETED, task_id, stage=result.state.lower(),
            action="complete recovery", result="OK" if result.resume_ok else "rejected",
            payload={
                "task_id": task_id,
                "state": result.state,
                "resume_ok": result.resume_ok,
                "last_event": result.last_event,
                "actions": result.actions,
            },
        )
        return result, ev

    def _do_recover(self, task_id: str) -> RecoveryResult:
        """恢复核心: load events → rebuild → compare → correct → result (无事件发射)。"""
        if self._task_store.get(task_id) is None:
            raise TaskNotFoundError(f"task not found: {task_id}")
        events = self._event_store.by_task(task_id)
        rebuilt = EventReplay(events).state
        run = self._workflow_store.get_run_by_task(task_id)
        assignments = self._assignment_store.list(task_id=task_id)
        executions = self._runtime_store.list_executions(task_id=task_id)

        actions: list[str] = []
        resume_ok = True

        if run is None:
            # 无运行实例: 无现场可恢复 (任务未启动工作流或 run 被删)
            resume_ok = False
            actions.append(f"reject recovery: no workflow run for task {task_id}")
            state = rebuilt.state_label if rebuilt.workflow_status is not None else "none"
        elif run.status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED):
            # 场景4: 已完成/已失败 → 拒绝 (终态无出口, 不改任何状态)
            resume_ok = False
            actions.append(
                f"reject recovery: workflow already {run.status.value} (task {task_id})"
            )
            state = run.status.value
        else:
            # 场景1: Workflow RUNNING → 继续当前 Step
            state = WorkflowStatus.RUNNING.value
            step_id = self._current_step_id(run)
            if step_id is not None:
                actions.append(f"continue step {step_id} (workflow RUNNING)")
            else:
                actions.append("workflow RUNNING but no pending step")
            # 一致性核对 (Event Audit): 事件回放与持久化状态的分歧提示
            if rebuilt.workflow_status is not None and rebuilt.workflow_status is not WorkflowStatus.RUNNING:
                actions.append(
                    f"inconsistency: events replay shows {rebuilt.workflow_status.value} "
                    f"but persisted RUNNING"
                )
            # 场景2: RUNNING execution → 标记可重试 (PENDING, 可重新派发至 RUNNING)
            for ex in executions:
                if ex.status is ExecutionStatus.RUNNING:
                    ex.status = ExecutionStatus.PENDING
                    self._runtime_store.save_execution(ex)
                    actions.append(f"retry execution {ex.id} (RUNNING → PENDING)")
            # 场景3: 非终态 assignment → 释放 Agent (→ AVAILABLE), Assignment → RELEASED
            for asg in assignments:
                if asg.status in (AssignmentStatus.ASSIGNED, AssignmentStatus.WORKING):
                    self._release_assignment(asg)
                    actions.append(
                        f"release agent {asg.agent_id} "
                        f"(assignment {asg.id} {asg.status.value} → AVAILABLE)"
                    )

        result = RecoveryResult(
            task_id=task_id,
            last_event=rebuilt.last_seq,
            state=state,
            resume_ok=resume_ok,
            actions=actions,
            workflow=run.to_dict() if run is not None else None,
            assignments=[a.to_dict() for a in assignments],
            executions=[e.to_dict() for e in executions],
            agents=self._agent_snapshot(assignments, executions),
        )
        return result

    # ------------------------------------------------------------------ 内部

    def _current_step_id(self, run: Any) -> str | None:
        """当前步骤: 优先 run.current_step, 退化到下一个未完成步骤 (镜像引擎语义)。"""
        if run.current_step:
            return run.current_step
        step = run.next_pending_step()
        return step.step_id if step is not None else None

    def _release_assignment(self, assignment: Any) -> None:
        """恢复纠正: 非终态 Assignment → RELEASED, Agent → AVAILABLE (直接持久化原语)。

        不发 agent.released 事件 — 恢复动作的审计由 recovery.completed 的 actions
        承载 (ADR-0011 决策 3); Agent 已删除时只纠正 assignment 记录 (best-effort)。
        同一 Agent 仍被其他任务的非终态 assignment 占用时不回 AVAILABLE
        (恢复只纠正本任务现场, 不破坏其他任务的占用残留)。
        """
        assignment.status = AssignmentStatus.RELEASED
        assignment.completed_at = datetime.now(timezone.utc)
        assignment.updated_at = datetime.now(timezone.utc)
        self._assignment_store.save(assignment)
        still_used = any(
            a.agent_id == assignment.agent_id and a.id != assignment.id
            and a.status in (AssignmentStatus.ASSIGNED, AssignmentStatus.WORKING)
            for a in self._assignment_store.list()
        )
        if still_used:
            return
        try:
            self._agent_registry.mark_available(assignment.agent_id)
        except AgentNotFoundError:
            pass

    def _agent_snapshot(
        self, assignments: list[Any], executions: list[Any],
    ) -> dict[str, str]:
        """任务涉及的 Agent 状态快照: {agent_id: AgentStatus} (引用不复制)。"""
        agent_ids = sorted(
            {a.agent_id for a in assignments}
            | {e.agent_id for e in executions if e.agent_id}
        )
        snapshot: dict[str, str] = {}
        for agent_id in agent_ids:
            agent = self._agent_registry.get(agent_id)
            if agent is not None:
                snapshot[agent_id] = agent.status.value
        return snapshot

    def _emit(
        self,
        type_: EventType,
        task_id: str,
        *,
        stage: str,
        action: str,
        result: str,
        payload: dict[str, Any] | None = None,
    ) -> Event | None:
        if self._logger is None:
            return None
        return self._logger.record(
            type_, source=self.SOURCE, task_id=task_id,
            stage=stage, action=action, result=result, payload=payload or {},
        )
