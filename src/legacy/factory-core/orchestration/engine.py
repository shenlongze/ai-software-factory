"""orchestration/engine.py — OrchestrationEngine: Workflow 自动执行流水线编排。

设计依据:
- phase4c2-status.md: workflow started → 读当前 step → 解析 step requirement
  (required_skill/required_role) → AgentMatcher → AgentAllocator → 创建 Execution →
  ExecutionRunner → 处理 Result → 推进 Workflow (complete_step → 下一步)。
- 模块调用规则 (phase4c2-status §2, 核心约束): 只组装不重写 — 复用 WorkflowEngine
  (start_workflow/start_step/execute_step/complete_step/fail_workflow)、AgentMatcher
  (best)、AgentAllocator (assign/start/complete/fail + Execution 回填 ADR-0008 决策 4)、
  ExecutionService (run, 经 Dispatcher 解析 Runtime + Runner 生命周期)。本模块不复制
  任何既有业务逻辑, 只做顺序编排与失败聚合。
- 失败语义 (phase4c2-status §5): 无匹配 Agent / 无 Runtime / Hermes FAILED /
  Step FAILED → engine.fail_workflow → Workflow FAILED (终态), 当前 RUNNING 步骤同步
  FAILED; 已分配的 Agent 经 allocator.fail 回 AVAILABLE (不留占用残留)。
  **绝不产生半完成运行态**: 任一步失败即整体 FAILED (无 COMPLETED 步骤混在 FAILED 里
  之外的中间态 — WorkflowRun 只有 RUNNING/FAILED/COMPLETED 三态, 终态即整体判定)。
- 前置条件错误 (任务不存在 / 工作流未注册 / 运行已终态) 属 OrchestrationStateError:
  不改工作流状态 (状态机终态无出口), outcome 记 FAILED + orchestration.failed 事件。
- Event 集成 (经 EventLogger, source="orchestration_engine"): orchestration.started →
  每步 step.started → step.completed → completed; 失败 failed。workflow.*/assignment.*/
  execution.* 事件由被复用模块经同一 logger 落库, 事件序完整可审计 (见 events.py)。
- 单步流水线 (逻辑链): start_step(RUNNING) → matcher.best → execute_step(创建 PENDING
  执行) → allocator.assign(execution_id 回填 agent_id) → allocator.start(WORKING) →
  service.run → SUCCESS: complete_step + allocator.complete (Agent→AVAILABLE) + 下一步;
  FAILED: allocator.fail (Agent→AVAILABLE) + 整体失败。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.models import Agent
from assignment.allocator import AgentAllocator, AgentAllocatorError
from assignment.matcher import AgentMatcher
from events.logger import EventLogger
from events.models import Event
from execution.dispatcher import ExecutionDispatcherError
from execution.runner import ExecutionRunnerError
from execution.service import ExecutionService
from runtime.models import ExecutionStatus
from runtime.registry import RuntimeNotFoundError
from workflows.engine import WorkflowEngine, WorkflowEngineError
from workflows.models import StepState, StepStatus, WorkflowRun, WorkflowStatus, WorkflowStep

from . import events as orch_events


class OrchestrationError(Exception):
    """编排流水线执行期失败 (无匹配 Agent / 无 Runtime / 执行 FAILED / 步骤异常)。

    语义: 已/将导致 Workflow FAILED (经 engine.fail_workflow), 不留半完成状态。
    """


class OrchestrationStateError(OrchestrationError):
    """前置条件错误 (任务不存在 / 工作流未注册 / 运行已终态): 不改工作流状态。"""


class StepExecutionError(OrchestrationError):
    """单步执行失败: 携带该步的 StepOutcome (agent/execution 引用, 审计用)。"""

    def __init__(self, message: str, step_outcome: "StepOutcome"):
        super().__init__(message)
        self.step_outcome = step_outcome


@dataclass
class StepOutcome:
    """单步编排结果 (审计/CLI 展示)。status 为 Workflow 步骤状态; result 为执行结果。"""

    step_id: str
    status: StepStatus
    agent_id: str | None = None
    assignment_id: str | None = None
    execution_id: str | None = None
    runtime_id: str | None = None
    result: str | None = None       # 执行结果 (SUCCESS/FAILED; 未执行到则为 None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "status": self.status.value,
            "agent_id": self.agent_id,
            "assignment_id": self.assignment_id,
            "execution_id": self.execution_id,
            "runtime_id": self.runtime_id,
            "result": self.result,
        }


@dataclass
class OrchestrationOutcome:
    """一次 execute_workflow 的完整结果 (终态判定 + 步骤清单 + orchestration.* 事件)。"""

    task_id: str
    status: WorkflowStatus
    workflow_id: str | None = None
    run_id: str | None = None
    run: WorkflowRun | None = None   # 终态运行实例快照 (CLI/审计展示)
    steps: list[StepOutcome] = field(default_factory=list)
    error: str | None = None
    events: list[Event] = field(default_factory=list)  # 本模块发出的 orchestration.* 事件

    @property
    def ok(self) -> bool:
        """终态判定: 仅 COMPLETED 为成功 (失败无半完成)。"""
        return self.status is WorkflowStatus.COMPLETED

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "status": self.status.value,
            "steps": [s.to_dict() for s in self.steps],
            "error": self.error,
            "events": [e.type.value for e in self.events],
        }


class OrchestrationEngine:
    """工作流自动执行编排器: 组装既有模块, 驱动完整链路 (Workflow→Matcher→Allocator→
    Execution→Runner→Result→推进)。"""

    SOURCE = orch_events.SOURCE

    def __init__(
        self,
        *,
        workflow_engine: WorkflowEngine,
        allocator: AgentAllocator,
        matcher: AgentMatcher | None = None,
        execution_service: ExecutionService,
        logger: EventLogger | None = None,
    ):
        self._wf = workflow_engine
        self._allocator = allocator
        self._matcher = matcher if matcher is not None else allocator.matcher
        self._execution = execution_service
        self._logger = logger

    # ------------------------------------------------------------------ 依赖暴露 (审计/测试)

    @property
    def workflow_engine(self) -> WorkflowEngine:
        return self._wf

    @property
    def allocator(self) -> AgentAllocator:
        return self._allocator

    @property
    def matcher(self) -> AgentMatcher:
        return self._matcher

    @property
    def execution_service(self) -> ExecutionService:
        return self._execution

    @property
    def logger(self) -> EventLogger | None:
        return self._logger

    # ------------------------------------------------------------------ 完整链路

    def execute_workflow(self, task_id: str) -> OrchestrationOutcome:
        """自动执行任务关联工作流 (可续跑): 完整链路直至 COMPLETED 或 FAILED (无半完成)。

        流程: orchestration.started → 确保 run RUNNING (无则 start_workflow) → 循环执行
        当前步骤 (匹配→分配→执行→结果→推进) → 全部完成 orchestration.completed;
        任一步失败 → fail_workflow (Workflow FAILED) + orchestration.failed。
        """
        steps: list[StepOutcome] = []
        events: list[Event] = self._append(
            orch_events.emit_started(self._logger, task_id=task_id), [],
        )
        workflow_id: str | None = None
        run_id: str | None = None
        run: WorkflowRun | None = None
        error: str | None = None

        try:
            run = self._ensure_run(task_id)
            workflow_id, run_id = run.workflow_id, run.run_id
            while run.status is WorkflowStatus.RUNNING:
                step_state = run.next_pending_step()
                if step_state is None:
                    break
                try:
                    step = self._execute_step(task_id, run, step_state, events)
                except StepExecutionError as exc:
                    steps.append(exc.step_outcome)
                    raise
                steps.append(step)
                run = self._wf.status(task_id)
                if run is None:
                    raise OrchestrationError(f"workflow run vanished: task {task_id}")
            final = self._wf.status(task_id)
            if final is None or final.status is not WorkflowStatus.COMPLETED:
                raise OrchestrationError(
                    f"workflow did not complete (status={final.status.value if final else 'none'}, "
                    f"task {task_id})"
                )
            events = self._append(
                orch_events.emit_completed(
                    self._logger, task_id=task_id, workflow_id=workflow_id,
                    run_id=run_id, steps=[s.to_dict() for s in steps],
                ),
                events,
            )
            return OrchestrationOutcome(
                task_id=task_id, status=WorkflowStatus.COMPLETED,
                workflow_id=workflow_id, run_id=run_id, run=final,
                steps=steps, events=events,
            )
        except OrchestrationStateError as exc:
            error = str(exc)
            events = self._append(
                orch_events.emit_failed(
                    self._logger, task_id=task_id, workflow_id=workflow_id,
                    run_id=run_id, error=error,
                ),
                events,
            )
            return OrchestrationOutcome(
                task_id=task_id, status=WorkflowStatus.FAILED,
                workflow_id=workflow_id, run_id=run_id, run=run,
                steps=steps, error=error, events=events,
            )
        except OrchestrationError as exc:
            error = str(exc)
            self._fail_workflow(task_id, error)  # Workflow → FAILED (无半完成)
            run = self._wf.status(task_id)
            workflow_id = workflow_id or (run.workflow_id if run is not None else None)
            run_id = run_id or (run.run_id if run is not None else None)
            events = self._append(
                orch_events.emit_failed(
                    self._logger, task_id=task_id, workflow_id=workflow_id,
                    run_id=run_id, error=error,
                ),
                events,
            )
            return OrchestrationOutcome(
                task_id=task_id, status=WorkflowStatus.FAILED,
                workflow_id=workflow_id, run_id=run_id, run=run,
                steps=steps, error=error, events=events,
            )

    # ------------------------------------------------------------------ 单步

    def _execute_step(
        self, task_id: str, run: WorkflowRun, step_state: StepState, events: list[Event],
    ) -> StepOutcome:
        """执行一个步骤: RUNNING → 匹配 → 分配 → 执行 → 结果 → 推进 (或失败)。

        失败 (无匹配 Agent / 无 Runtime / 执行 FAILED / 引擎异常) 统一抛
        StepExecutionError(携带 step_outcome); 已创建的分配经 allocator.fail 释放 Agent。
        """
        step_id = step_state.step_id
        step_def = self._require_step_def(run, step_id)
        step = StepOutcome(step_id=step_id, status=StepStatus.RUNNING)

        # 1. 步骤就绪: PENDING → RUNNING (第一步在 start_workflow 时已自动 RUNNING)
        if step_state.status is StepStatus.PENDING:
            self._wf.start_step(task_id, step_id)
        self._append(
            orch_events.emit_step_started(
                self._logger, task_id=task_id, workflow_id=run.workflow_id,
                run_id=run.run_id, step_id=step_id, step_name=step_def.name,
            ),
            events,
        )

        # 2. AgentMatcher: 解析 step requirement (required_skill/required_role) → 最优候选
        agent = self._matcher.best(step_def)
        if agent is None:
            step.status = StepStatus.FAILED
            raise StepExecutionError(
                f"no available agent for step {step_id!r} "
                f"(role={step_def.required_role!r}, skill={step_def.required_skill!r})",
                step,
            )
        step.agent_id = agent.id

        # 3. 创建 Execution (PENDING, 不自动执行) — WorkflowEngine.execute_step
        request, _ = self._wf.execute_step(task_id, step_id)
        step.execution_id = request.id

        # 4. AgentAllocator: 分配 (Agent→WORKING, 回填 execution.agent_id, ADR-0008 决策 4)
        assignment, _ = self._allocator.assign(
            task_id,
            agent_id=agent.id,
            workflow_id=run.workflow_id,
            workflow_step_id=step_id,
            execution_id=request.id,
        )
        step.assignment_id = assignment.id
        self._allocator.start(assignment.id)  # ASSIGNED → WORKING

        # 5. ExecutionRunner (经 ExecutionService): 解析 Runtime → 执行 → 结果
        try:
            outcome = self._execution.run(request.id)
        except (ExecutionDispatcherError, ExecutionRunnerError, RuntimeNotFoundError) as exc:
            # 无可用 Runtime / 无 Adapter 实现 / 状态冲突: 执行保持原状, 释放 Agent
            step.status = StepStatus.FAILED
            self._allocator_fail(assignment.id, str(exc))
            raise StepExecutionError(str(exc), step) from exc
        step.runtime_id = outcome.request.runtime_id
        step.result = outcome.request.status.value

        if outcome.request.status is ExecutionStatus.SUCCESS:
            # 6. 结果 → 推进: complete_step (下一步), 完成分配 (Agent→AVAILABLE)
            self._wf.complete_step(task_id, step_id, result="OK", evidence=f"execution {request.id}")
            self._allocator.complete(assignment.id, result="OK")
            step.status = StepStatus.COMPLETED
            self._append(
                orch_events.emit_step_completed(
                    self._logger, task_id=task_id, workflow_id=run.workflow_id,
                    run_id=run.run_id, step_id=step_id, step_name=step_def.name,
                    agent_id=agent.id, execution_id=request.id, result="OK",
                ),
                events,
            )
            return step

        # 7. 执行结果 FAILED → 整体失败 (Workflow FAILED); 释放 Agent
        error = outcome.result.error if outcome.result is not None else None
        error = error or f"execution {request.id} failed"
        step.status = StepStatus.FAILED
        self._allocator_fail(assignment.id, error)
        raise StepExecutionError(error, step)

    # ------------------------------------------------------------------ 内部

    def _ensure_run(self, task_id: str) -> WorkflowRun:
        """确保任务有 RUNNING 运行实例: 无则 start_workflow; 终态/缺失 → 前置错误。"""
        run = self._wf.status(task_id)
        if run is None:
            try:
                run, _ = self._wf.start_workflow(task_id)  # 发 workflow.started (+第一步 RUNNING)
            except WorkflowEngineError as exc:
                raise OrchestrationStateError(str(exc)) from exc
            return run
        if run.status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED):
            raise OrchestrationStateError(
                f"workflow already in terminal state {run.status.value} (task {task_id})"
            )
        return run  # RUNNING: 续跑 (从当前步骤继续)

    def _require_step_def(self, run: WorkflowRun, step_id: str) -> WorkflowStep:
        """运行快照中的步骤 → 工作流定义 (required_skill/required_role 来源)。"""
        workflow = self._wf.get_workflow(run.workflow_id)
        if workflow is None:
            raise OrchestrationError(f"workflow definition missing: {run.workflow_id!r}")
        for s in workflow.steps:
            if s.id == step_id:
                return s
        raise OrchestrationError(f"step {step_id!r} not in workflow {run.workflow_id!r}")

    def _fail_workflow(self, task_id: str, error: str) -> None:
        """标记 Workflow FAILED (best-effort: 已终态/无运行则忽略, 不掩盖原始错误)。"""
        try:
            self._wf.fail_workflow(task_id, error)
        except WorkflowEngineError:
            pass

    def _allocator_fail(self, assignment_id: str, error: str) -> None:
        """失败时释放 Agent (Assignment FAILED + Agent→AVAILABLE; 已终态则忽略)。"""
        try:
            self._allocator.fail(assignment_id, error=error)
        except AgentAllocatorError:
            pass

    @staticmethod
    def _append(ev: Event | None, events: list[Event]) -> list[Event]:
        """追加事件 (logger 缺省时 ev 为 None, 跳过)。"""
        if ev is not None:
            events.append(ev)
        return events
