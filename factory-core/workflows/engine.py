"""workflows/engine.py — WorkflowEngine: 工作流定义管理 + 运行状态机。

设计依据:
- phase4a-status.md: create_workflow / start_workflow / start_step / complete_step / fail_workflow;
  状态机禁止非法转换 (CREATED 不能直接 COMPLETED; 必须 CREATED→RUNNING→COMPLETED;
  step 只能按 order 顺序 PENDING→RUNNING→COMPLETED; FAILED 终态)。
- Event 集成一律经 EventLogger (不直接写 EventStore); logger 可缺省 (纯存储操作, 库/测试场景)。
  写方法返回 `(对象, Event | None)` — 同 AgentRegistry 模式 (ADR-0004 决策 2)。
- Task 集成 (phase4a-status §2): start_workflow(task_id) 读取 task.workflow 字段 (workflow id),
  只建立关联; 启动后第一步状态置 RUNNING (设计语义: run 后第一步正在执行),
  但不自动分配 Agent、不自动执行步骤 (后续 Phase)。
- 状态变化可追踪: 每次转换产生 Event (六事件: created/started/step.started/step.completed/
  completed/failed; CLI 读命令另发 workflow.viewed, 见 ADR-0005)。

转换表 (WorkflowRun):
  CREATED   → {RUNNING, FAILED}
  RUNNING   → {COMPLETED, FAILED}
  COMPLETED → {}        (终态)
  FAILED    → {}        (终态)

转换表 (StepState):
  PENDING → {RUNNING, FAILED}
  RUNNING → {COMPLETED, FAILED}
  COMPLETED → {}        (终态)
  FAILED    → {}        (终态)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agents.registry import AgentRegistry
from events.logger import EventLogger
from events.models import Event, EventType
from runtime.models import ExecutionRequest
from runtime.store import RuntimeStore
from tasks.models import Task
from tasks.store import TaskStore

from .models import StepState, StepStatus, Workflow, WorkflowRun, WorkflowStatus
from .store import WorkflowStore

# 运行实例状态转换表
_RUN_TRANSITIONS: dict[WorkflowStatus, set[WorkflowStatus]] = {
    WorkflowStatus.CREATED: {WorkflowStatus.RUNNING, WorkflowStatus.FAILED},
    WorkflowStatus.RUNNING: {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED},
    WorkflowStatus.COMPLETED: set(),
    WorkflowStatus.FAILED: set(),
}

# 步骤状态转换表
_STEP_TRANSITIONS: dict[StepStatus, set[StepStatus]] = {
    StepStatus.PENDING: {StepStatus.RUNNING, StepStatus.FAILED},
    StepStatus.RUNNING: {StepStatus.COMPLETED, StepStatus.FAILED},
    StepStatus.COMPLETED: set(),
    StepStatus.FAILED: set(),
}


class WorkflowEngineError(Exception):
    """WorkflowEngine 基础异常。"""


class WorkflowStateError(WorkflowEngineError):
    """非法状态转换 (状态机拒绝)。"""


class WorkflowExistsError(WorkflowEngineError):
    """工作流定义已存在 (create_workflow 冲突)。"""


class WorkflowNotFoundError(WorkflowEngineError):
    """工作流定义不存在 (或任务未关联 workflow)。"""


class WorkflowRunNotFoundError(WorkflowEngineError):
    """任务没有运行实例 (尚未 start_workflow)。"""


class WorkflowAlreadyStartedError(WorkflowEngineError):
    """任务已有运行实例 (一个 task 至多一个 run)。"""


class StepNotFoundError(WorkflowEngineError):
    """步骤不在工作流中。"""


class StepNotReadyError(WorkflowEngineError):
    """步骤状态/顺序不满足操作前置条件 (未就绪 / 非当前步骤 / 已终态)。"""


class WorkflowEngine:
    """工作流定义管理 + 运行状态机 (单进程本地 JSON 持久化)。"""

    SOURCE = "workflow_engine"  # event-model §2.1 source 取值

    def __init__(
        self,
        store: WorkflowStore,
        task_store: TaskStore | None = None,
        logger: EventLogger | None = None,
        runtime_store: RuntimeStore | None = None,
        agent_registry: AgentRegistry | None = None,
    ):
        self._store = store
        self._task_store = task_store
        self._logger = logger
        self._runtime_store = runtime_store
        self._agent_registry = agent_registry

    @property
    def store(self) -> WorkflowStore:
        return self._store

    @property
    def task_store(self) -> TaskStore | None:
        """关联的 TaskStore (可为 None: 仅定义管理时无需任务维度)。"""
        return self._task_store

    @property
    def runtime_store(self) -> RuntimeStore | None:
        """关联的 RuntimeStore (可为 None; 执行边界方法 execute_step 要求非 None)。"""
        return self._runtime_store

    @property
    def agent_registry(self) -> AgentRegistry | None:
        """关联的 AgentRegistry (可为 None; execute_step 的 agent_id 解析留空)。"""
        return self._agent_registry

    # ------------------------------------------------------------------ 转换表 (审计/测试入口)

    @staticmethod
    def is_valid_run_transition(from_: WorkflowStatus, to: WorkflowStatus) -> bool:
        """运行实例转换是否合法 (状态机校验, 公开供审计/测试)。"""
        return to in _RUN_TRANSITIONS.get(from_, set())

    @staticmethod
    def is_valid_step_transition(from_: StepStatus, to: StepStatus) -> bool:
        """步骤转换是否合法。"""
        return to in _STEP_TRANSITIONS.get(from_, set())

    # ------------------------------------------------------------------ 定义管理

    def create_workflow(self, workflow: Workflow) -> tuple[Workflow, Event | None]:
        """注册工作流定义; id 冲突抛 WorkflowExistsError; 发 workflow.created。"""
        if self.get_workflow(workflow.id) is not None:
            raise WorkflowExistsError(f"workflow already exists: {workflow.id}")
        self._store.save_workflow(workflow)
        ev = self._emit(
            EventType.WORKFLOW_CREATED, stage="created", action="create workflow",
            payload={
                "workflow_id": workflow.id,
                "name": workflow.name,
                "description": workflow.description,
                "steps": workflow.step_ids(),
            },
        )
        return workflow, ev

    def get_workflow(self, workflow_id: str) -> Workflow | None:
        """按 id 取定义; 不存在返回 None。"""
        return self._store.get_workflow(workflow_id)

    def list_workflows(self) -> list[Workflow]:
        """全部定义 (按 id 排序)。"""
        return self._store.list_workflows()

    # ------------------------------------------------------------------ 运行: 启动

    def start_workflow(self, task_id: str) -> tuple[WorkflowRun, Event | None]:
        """为任务启动其关联工作流 (task.workflow → 定义), 发 workflow.started。

        流程: 任务存在 → 定义存在 → 无既有 run → 创建 run (CREATED) → 启动 (RUNNING)。
        状态机内部仍严格走 CREATED→RUNNING, 对外一次调用完成。
        设计语义 (phase4a-status): run 启动后第一步即处于 RUNNING (正在执行),
        故第一步自动置 RUNNING, 并追加发 workflow.step.started (事件序: started → step.started)。
        返回值保持主事件 workflow.started (start_step 语义: 后续步骤仍须显式 start_step)。
        """
        if self._task_store is None:
            raise WorkflowEngineError("engine has no task store: cannot start workflow by task")
        task = self._task_store.get(task_id)
        if task is None:
            raise WorkflowRunNotFoundError(f"task not found: {task_id}")
        if self._store.get_run_by_task(task_id) is not None:
            raise WorkflowAlreadyStartedError(f"task already has a workflow run: {task_id}")
        workflow = self._resolve_workflow(task)
        run = WorkflowRun.from_workflow(
            run_id=self._store.next_run_id(), workflow=workflow, task_id=task_id,
        )
        self._transition(run, WorkflowStatus.RUNNING)
        first = run.next_pending_step()  # 第一步自动启动: PENDING → RUNNING
        if first is not None:
            self._step_transition(first, StepStatus.RUNNING)
        self._store.save_run(run)
        ev = self._emit(
            EventType.WORKFLOW_STARTED, task_id=task_id, stage="running",
            action="start workflow", result="OK",
            payload={
                "workflow_id": run.workflow_id,
                "task_id": task_id,
                "run_id": run.run_id,
                "step_ids": [st.step_id for st in run.step_states],
            },
        )
        if first is not None:
            self._emit(
                EventType.WORKFLOW_STEP_STARTED, task_id=task_id, stage="running",
                action=f"start step {first.step_id}", result="OK",
                payload={
                    "workflow_id": run.workflow_id,
                    "task_id": task_id,
                    "run_id": run.run_id,
                    "step_id": first.step_id,
                    "step_name": self._step_name(run, first.step_id),
                },
            )
        return run, ev

    def _resolve_workflow(self, task: Task) -> Workflow:
        """task.workflow 字段 → 定义; 未关联/未注册抛 WorkflowNotFoundError。"""
        workflow_id = task.workflow
        if not workflow_id:
            raise WorkflowNotFoundError(f"task has no workflow: {task.id}")
        workflow = self._store.get_workflow(workflow_id)
        if workflow is None:
            raise WorkflowNotFoundError(
                f"workflow not registered: {workflow_id!r} (task {task.id}; "
                f"run 'factory workflow add' first)"
            )
        return workflow

    # ------------------------------------------------------------------ 运行: 步骤推进

    def start_step(self, task_id: str, step_id: str) -> tuple[WorkflowRun, Event | None]:
        """启动步骤: 仅当前步骤 (按 order 顺序第一个未完成) 且 PENDING → RUNNING。

        发 workflow.step.started。跳过未完成步骤 / 重复启动 / 未知步骤 → 拒绝。
        """
        run = self._require_running(task_id)
        step_state = self._require_step(run, step_id)
        current = run.next_pending_step()
        if current is None or current.step_id != step_id:
            expected = current.step_id if current is not None else "none"
            raise StepNotReadyError(
                f"step {step_id!r} is not the current step (expected {expected!r}); "
                f"steps must run in order"
            )
        self._step_transition(step_state, StepStatus.RUNNING)
        run.current_step = step_id
        run.updated_at = datetime.now(timezone.utc)
        self._store.save_run(run)
        step_name = self._step_name(run, step_id)
        ev = self._emit(
            EventType.WORKFLOW_STEP_STARTED, task_id=task_id, stage="running",
            action=f"start step {step_id}", result="OK",
            payload={
                "workflow_id": run.workflow_id,
                "task_id": task_id,
                "run_id": run.run_id,
                "step_id": step_id,
                "step_name": step_name,
            },
        )
        return run, ev

    def complete_step(
        self, task_id: str, step_id: str, *, result: str = "OK", evidence: str | None = None,
    ) -> tuple[WorkflowRun, Event | None]:
        """完成步骤: RUNNING → COMPLETED (result=OK) 或 RUNNING → FAILED (result≠OK)。

        - result=OK 且全部步骤完成 → run COMPLETED, 发 workflow.completed (在 step.completed 之后)
        - result≠OK → 步骤 FAILED + run FAILED, 发 workflow.failed
        - 事件顺序: 先 workflow.step.completed, 再 workflow.completed / workflow.failed;
          返回最后一个事件 (最相关)。
        """
        run = self._require_running(task_id)
        step_state = self._require_step(run, step_id)
        if step_state.status is not StepStatus.RUNNING:
            raise StepNotReadyError(
                f"step {step_id!r} is not running (status={step_state.status.value}); "
                f"call start_step first"
            )
        step_ok = result == "OK"
        self._step_transition(step_state, StepStatus.COMPLETED if step_ok else StepStatus.FAILED)
        step_state.result = result
        step_state.evidence = evidence
        run.updated_at = datetime.now(timezone.utc)

        step_name = self._step_name(run, step_id)
        step_ev = self._emit(
            EventType.WORKFLOW_STEP_COMPLETED, task_id=task_id,
            stage="running" if step_ok else "failed",
            action=f"complete step {step_id}", result=result,
            payload={
                "workflow_id": run.workflow_id,
                "task_id": task_id,
                "run_id": run.run_id,
                "step_id": step_id,
                "step_name": step_name,
                "result": result,
                "evidence": evidence,
            },
        )

        if not step_ok:
            run.status = WorkflowStatus.FAILED
            run.error = f"step {step_id} failed with result {result!r}"
            run.current_step = step_id
            self._store.save_run(run)
            fail_ev = self._emit(
                EventType.WORKFLOW_FAILED, task_id=task_id, stage="failed",
                action="fail workflow", result="failed",
                payload={
                    "workflow_id": run.workflow_id,
                    "task_id": task_id,
                    "run_id": run.run_id,
                    "error": run.error,
                },
            )
            return run, fail_ev if fail_ev is not None else step_ev

        next_step = run.next_pending_step()
        run.current_step = next_step.step_id if next_step is not None else None
        if run.all_steps_completed():
            self._transition(run, WorkflowStatus.COMPLETED)
            self._store.save_run(run)
            done_ev = self._emit(
                EventType.WORKFLOW_COMPLETED, task_id=task_id, stage="completed",
                action="complete workflow", result="OK",
                payload={
                    "workflow_id": run.workflow_id,
                    "task_id": task_id,
                    "run_id": run.run_id,
                },
            )
            return run, done_ev if done_ev is not None else step_ev
        self._store.save_run(run)
        return run, step_ev

    # ------------------------------------------------------------------ 运行: 执行边界 (Runtime 交接)

    def execute_step(self, task_id: str, step_id: str) -> tuple[ExecutionRequest, Event | None]:
        """为任务的当前步骤创建待执行请求 (PENDING), 不调用任何 Runtime。

        Phase 4B-1 边界语义 (phase4b1-status.md §Workflow 集成边界):
        - 前置: 任务有运行实例且 RUNNING; 步骤存在且为当前步骤 (按 order 顺序),
          且未处于终态 (COMPLETED/FAILED)。
        - 产物: ExecutionRequest 落 RuntimeStore (status=PENDING) + 发 execution.created;
          步骤状态不变 — 不自动执行, 派发属 Phase 4B-2 (RuntimeRegistry + Adapter)。
        - agent_id: 经 AgentRegistry 解析 — task.owner 精确引用命中已注册 Agent 则取,
          否则留空 (ADR-0006 决策 4; 按角色/技能自动分配属后续 Phase)。
        - runtime_id 本阶段恒为空: 尚无 Runtime 实现, 派发层 (4B-2) 解析填充。
        """
        if self._runtime_store is None:
            raise WorkflowEngineError("engine has no runtime store: cannot create execution")
        run = self._require_running(task_id)
        step_state = self._require_step(run, step_id)
        current = run.next_pending_step()
        if current is None or current.step_id != step_id:
            expected = current.step_id if current is not None else "none"
            raise StepNotReadyError(
                f"step {step_id!r} is not the current step (expected {expected!r}); "
                f"steps must run in order"
            )
        if step_state.status in (StepStatus.COMPLETED, StepStatus.FAILED):
            raise StepNotReadyError(
                f"step {step_id!r} is in terminal state {step_state.status.value}; "
                f"cannot create execution"
            )
        task = self._task_store.get(task_id) if self._task_store is not None else None
        agent_id = self._resolve_agent_id(task) if task is not None else None
        request = ExecutionRequest(
            id=self._runtime_store.next_execution_id(),
            task_id=task_id,
            workflow_id=run.workflow_id,
            step_id=step_id,
            agent_id=agent_id,
            runtime_id=None,
            input={},
        )
        self._runtime_store.save_execution(request)
        ev = self._emit(
            EventType.EXECUTION_CREATED, task_id=task_id, stage="pending",
            action=f"create execution for step {step_id}", result="OK",
            payload={
                "execution_id": request.id,
                "run_id": run.run_id,
                "workflow_id": run.workflow_id,
                "task_id": task_id,
                "step_id": step_id,
                "agent_id": agent_id,
                "runtime_id": request.runtime_id,
                "status": request.status.value,
            },
        )
        return request, ev

    def _resolve_agent_id(self, task: Task) -> str | None:
        """解析执行请求的 agent_id: task.owner 引用已注册 Agent 则取, 否则 None (留空)。

        KISS (ADR-0006 决策 4): 只做 owner 精确引用解析; 按角色/技能自动分配
        (如首个 AVAILABLE) 属 4B-2 派发层职责。
        """
        if self._agent_registry is None:
            return None
        if task.owner and self._agent_registry.get(task.owner) is not None:
            return task.owner
        return None

    # ------------------------------------------------------------------ 运行: 失败

    def fail_workflow(self, task_id: str, error: str) -> tuple[WorkflowRun, Event | None]:
        """标记运行失败: run → FAILED (终态), 当前 RUNNING 步骤同步 FAILED; 发 workflow.failed。

        CREATED/RUNNING 可失败; COMPLETED/FAILED (终态) 拒绝。
        """
        run = self._store.get_run_by_task(task_id)
        if run is None:
            raise WorkflowRunNotFoundError(f"no workflow run for task: {task_id}")
        if run.status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED):
            raise WorkflowStateError(
                f"workflow cannot fail: already in terminal state {run.status.value} (task {task_id})"
            )
        for st in run.step_states:  # 同步: 当前 RUNNING 步骤标记 FAILED
            if st.status is StepStatus.RUNNING:
                self._step_transition(st, StepStatus.FAILED)
                st.result = "failed"
        self._transition(run, WorkflowStatus.FAILED)
        run.error = error
        run.updated_at = datetime.now(timezone.utc)
        self._store.save_run(run)
        ev = self._emit(
            EventType.WORKFLOW_FAILED, task_id=task_id, stage="failed",
            action="fail workflow", result="failed",
            payload={
                "workflow_id": run.workflow_id,
                "task_id": task_id,
                "run_id": run.run_id,
                "error": error,
            },
        )
        return run, ev

    # ------------------------------------------------------------------ 运行: 查询

    def status(self, task_id: str) -> WorkflowRun | None:
        """按任务取运行实例 (只读, 不发事件; CLI 层另行发 workflow.viewed)。"""
        return self._store.get_run_by_task(task_id)

    # ------------------------------------------------------------------ 内部

    def _require_running(self, task_id: str) -> WorkflowRun:
        """取任务运行实例并校验处于 RUNNING (状态机前置条件)。"""
        run = self._store.get_run_by_task(task_id)
        if run is None:
            raise WorkflowRunNotFoundError(f"no workflow run for task: {task_id}")
        if run.status is not WorkflowStatus.RUNNING:
            raise WorkflowStateError(
                f"workflow is not running (status={run.status.value}, task {task_id}); "
                f"expected RUNNING"
            )
        return run

    def _require_step(self, run: WorkflowRun, step_id: str) -> StepState:
        step_state = run.step_state(step_id)
        if step_state is None:
            raise StepNotFoundError(f"step {step_id!r} not in workflow {run.workflow_id!r}")
        return step_state

    def _step_name(self, run: WorkflowRun, step_id: str) -> str:
        """步骤显示名: 优先定义, 定义缺失时退化为 step_id (run 快照不依赖定义)。"""
        wf = self._store.get_workflow(run.workflow_id)
        if wf is not None:
            for s in wf.steps:
                if s.id == step_id:
                    return s.name
        return step_id

    def _transition(self, run: WorkflowRun, to: WorkflowStatus) -> None:
        """运行实例状态转换 (校验 + 就地修改; 修改后由调用方落盘)。"""
        if not self.is_valid_run_transition(run.status, to):
            raise WorkflowStateError(
                f"invalid workflow transition: {run.status.value} -> {to.value} (task {run.task_id})"
            )
        run.status = to

    def _step_transition(self, step_state: StepState, to: StepStatus) -> None:
        """步骤状态转换 (校验 + 就地修改)。"""
        if not self.is_valid_step_transition(step_state.status, to):
            raise WorkflowStateError(
                f"invalid step transition: {step_state.step_id} "
                f"{step_state.status.value} -> {to.value}"
            )
        step_state.status = to

    def _emit(
        self,
        type_: EventType,
        *,
        task_id: str | None = None,
        stage: str,
        action: str,
        result: str = "OK",
        payload: dict[str, Any],
    ) -> Event | None:
        if self._logger is None:
            return None
        return self._logger.record(
            type_, source=self.SOURCE, task_id=task_id,
            stage=stage, action=action, result=result, payload=payload,
        )
