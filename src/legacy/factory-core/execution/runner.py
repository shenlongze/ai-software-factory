"""execution/runner.py — ExecutionRunner: 执行生命周期编排 + Workflow 联动。

设计依据:
- phase4b2-status.md: 生命周期 PENDING → execution.started → adapter.execute() →
  SUCCESS/FAILED → execution.completed/failed; 所有事件经 EventLogger。
- 事件发射点 (ADR-0006 决策 1 的落地): execution.started/completed/failed 由本层发出
  (source="execution_runner"), 载荷含 execution_id/workflow_id/task_id/step_id/
  agent_id/runtime_id/status (+ completed/failed 附 result_id; failed 附 error)。
  run_id 不在 ExecutionRequest 模型上, 已由 execution.created 携带, 经 execution_id
  关联即可 (ADR-0007 决策 2)。
- Result 持久化复用 RuntimeStore (runtimes.json 三节, results 以 request_id 为键):
  终态请求 + 结果一起落盘, 不新增数据库 (phase4b2-status §Result 持久化)。
- Workflow 联动 (phase4b2-status §Workflow 联动): 成功 → engine.complete_step
  (发 workflow.step.completed, 全步完成则 workflow.completed); 失败 →
  engine.fail_workflow (发 workflow.failed)。best-effort: 联动异常记录
  workflow_error, 不影响执行终态落盘 (执行与工作流各自独立持久化)。
- 防御 (ADR-0007 决策 4): adapter.execute 抛异常 → 转换为 FAILED 结果
  (error 描述异常), 走 execution.failed 事件与失败联动, 不阻断生命周期。
- 重入防护: 仅 PENDING 可执行; RUNNING/终态拒绝 (results 1:1, 不可重跑覆盖)。

边界 (phase4b2-status §Agent 边界): agent_id 来自请求, 无则 None — Runner 不做
自动 Agent 选择/调度 (后续 Phase)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from events.logger import EventLogger
from events.models import Event, EventType
from runtime.models import ExecutionRequest, ExecutionResult, ExecutionStatus
from runtime.store import RuntimeStore
from workflows.engine import WorkflowEngine, WorkflowEngineError

from .dispatcher import (
    ExecutionDispatcher,
    RuntimeAdapterNotFoundError,
)


class ExecutionRunnerError(Exception):
    """ExecutionRunner 基础异常。"""


class ExecutionNotFoundError(ExecutionRunnerError):
    """执行请求不存在。"""


class ExecutionStateError(ExecutionRunnerError):
    """执行状态不满足前置条件 (非 PENDING / 已终态)。"""


@dataclass
class ExecutionRunOutcome:
    """一次 run 的完整结果: 终态请求 + 结果 + 事件序 + Workflow 联动摘要。

    - events: 本 runner 发出的事件 (started + completed|failed; logger 缺省时空),
      联动事件由 WorkflowEngine 经同一 logger 落库 (如装配了同一 logger)。
    - workflow_step_completed / workflow_failed: 联动是否成功执行
      (未绑定 workflow/无 engine 时均为 False)。
    - workflow_error: 联动异常描述 (best-effort: 不影响执行终态)。
    """

    request: ExecutionRequest
    result: ExecutionResult | None = None
    events: list[Event] = field(default_factory=list)
    workflow_step_completed: bool = False
    workflow_failed: bool = False
    workflow_error: str | None = None


class ExecutionRunner:
    """执行生命周期编排: 状态推进 + 事件 + 持久化 + Workflow 联动。"""

    SOURCE = "execution_runner"  # event-model §2.1 source 取值

    def __init__(
        self,
        store: RuntimeStore,
        dispatcher: ExecutionDispatcher,
        logger: EventLogger | None = None,
        workflow_engine: WorkflowEngine | None = None,
    ):
        self._store = store
        self._dispatcher = dispatcher
        self._logger = logger
        self._workflow_engine = workflow_engine

    @property
    def store(self) -> RuntimeStore:
        return self._store

    @property
    def dispatcher(self) -> ExecutionDispatcher:
        return self._dispatcher

    @property
    def workflow_engine(self) -> WorkflowEngine | None:
        """联动的工作流引擎 (可为 None: 独立执行不联动工作流)。"""
        return self._workflow_engine

    # ------------------------------------------------------------------ 执行

    def run(self, execution_id: str) -> ExecutionRunOutcome:
        """执行一次 PENDING 执行请求, 返回终态请求 + 结果 + 事件 + 联动摘要。

        生命周期: 校验 PENDING → 解析 runtime_id → RUNNING (execution.started) →
        adapter.execute → SUCCESS/FAILED (execution.completed/failed) → 结果落库 →
        Workflow 联动 (成功 complete_step / 失败 fail_workflow)。

        Raises:
            ExecutionNotFoundError: 执行请求不存在
            ExecutionStateError: 状态非 PENDING (已启动/已终态)
            NoAvailableRuntimeError: 无可用 Runtime (执行保持 PENDING, 无事件)
            RuntimeNotFoundError: 请求显式指定的 runtime 未注册
            RuntimeAdapterNotFoundError: runtime 已注册但无 Adapter 实现 — 配置缺口
                (执行保持 PENDING, 无事件; CLI 报 rc 1, 与 NoAvailableRuntimeError 对称,
                不落入 FAILED 业务结果 — CLI 契约见 cli/commands.py cmd_execution_run)
        """
        request = self._store.get_execution(execution_id)
        if request is None:
            raise ExecutionNotFoundError(f"execution not found: {execution_id}")
        if request.status is not ExecutionStatus.PENDING:
            raise ExecutionStateError(
                f"execution {execution_id} is {request.status.value}, expected PENDING"
            )

        # 解析 runtime (失败即抛: 执行保持 PENDING, 不产生任何事件/结果)
        runtime_id = self._dispatcher.resolve_runtime_id(request)
        # 配置缺口检查 (身份已注册但无 Adapter 实现): 在状态变更前暴露, 与
        # NoAvailableRuntimeError 一致 — 执行保持 PENDING, 无事件, CLI 报 rc 1。
        # (dispatch 内同类异常不可达 — 此处已前置拦截; 防御 catch 只兜 adapter 运行期错误)
        if self._dispatcher.get_adapter(runtime_id) is None:
            raise RuntimeAdapterNotFoundError(
                f"no adapter implementation for runtime: {runtime_id} "
                f"(execution {request.id})"
            )
        request = request.model_copy(update={
            "status": ExecutionStatus.RUNNING,
            "runtime_id": runtime_id,
        })
        self._store.save_execution(request)
        events: list[Event] = self._append(self._emit_started(request), [])

        try:
            result = self._dispatcher.dispatch(request)
        except Exception as exc:  # Adapter 内部错误/契约违反 → FAILED 结果 (防御)
            result = ExecutionResult(
                id=f"EXR-{execution_id}",
                request_id=execution_id,
                status=ExecutionStatus.FAILED,
                error=f"{type(exc).__name__}: {exc}",
            )

        request = request.model_copy(update={"status": result.status})
        self._store.save_execution(request)
        self._store.save_result(result)
        events = self._append(self._emit_finished(request, result), events)

        outcome = ExecutionRunOutcome(request=request, result=result, events=events)
        self._link_workflow(request, result, outcome)
        return outcome

    # ------------------------------------------------------------------ Workflow 联动

    def _link_workflow(
        self,
        request: ExecutionRequest,
        result: ExecutionResult,
        outcome: ExecutionRunOutcome,
    ) -> None:
        """Workflow 联动 (best-effort): 成功 complete_step / 失败 fail_workflow。

        仅当请求绑定 workflow_id+step_id 且装配了 workflow_engine 时执行; 联动异常
        记录 outcome.workflow_error, 不影响执行终态 (执行与工作流各自独立落盘)。
        """
        engine = self._workflow_engine
        if engine is None or request.workflow_id is None or request.step_id is None:
            return
        try:
            if result.status is ExecutionStatus.SUCCESS:
                engine.complete_step(
                    request.task_id, request.step_id,
                    result="OK", evidence=f"execution {request.id}",
                )
                outcome.workflow_step_completed = True
            else:
                error = result.error or f"execution {request.id} failed"
                engine.fail_workflow(request.task_id, error)
                outcome.workflow_failed = True
        except WorkflowEngineError as exc:
            outcome.workflow_error = str(exc)

    # ------------------------------------------------------------------ 事件

    def _emit_started(self, request: ExecutionRequest) -> Event | None:
        return self._emit(
            EventType.EXECUTION_STARTED, request, stage="running",
            action=f"dispatch execution {request.id}", result="OK",
            payload={**self._base_payload(request), "status": ExecutionStatus.RUNNING.value},
        )

    def _emit_finished(
        self, request: ExecutionRequest, result: ExecutionResult,
    ) -> Event | None:
        if result.status is ExecutionStatus.SUCCESS:
            return self._emit(
                EventType.EXECUTION_COMPLETED, request, stage="success",
                action=f"complete execution {request.id}", result="OK",
                payload={
                    **self._base_payload(request),
                    "status": ExecutionStatus.SUCCESS.value,
                    "result_id": result.id,
                },
            )
        return self._emit(
            EventType.EXECUTION_FAILED, request, stage="failed",
            action=f"fail execution {request.id}", result="failed",
            payload={
                **self._base_payload(request),
                "status": ExecutionStatus.FAILED.value,
                "result_id": result.id,
                "error": result.error,
            },
        )

    @staticmethod
    def _base_payload(request: ExecutionRequest) -> dict[str, Any]:
        """execution.* 事件公共载荷 (run_id 见 ADR-0007 决策 2)。"""
        return {
            "execution_id": request.id,
            "workflow_id": request.workflow_id,
            "task_id": request.task_id,
            "step_id": request.step_id,
            "agent_id": request.agent_id,
            "runtime_id": request.runtime_id,
        }

    def _emit(
        self,
        type_: EventType,
        request: ExecutionRequest,
        *,
        stage: str,
        action: str,
        result: str,
        payload: dict[str, Any],
    ) -> Event | None:
        if self._logger is None:
            return None
        return self._logger.record(
            type_, source=self.SOURCE, task_id=request.task_id,
            stage=stage, action=action, result=result, payload=payload,
        )

    @staticmethod
    def _append(ev: Event | None, events: list[Event]) -> list[Event]:
        """追加事件 (logger 缺省时 ev 为 None, 跳过)。"""
        if ev is not None:
            events.append(ev)
        return events
