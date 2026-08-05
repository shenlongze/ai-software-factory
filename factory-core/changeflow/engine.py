"""changeflow/engine.py — ChangeWorkflowEngine: 变更事件 → 规则评估 → 触发下一 workflow
(Phase 6E, ADR-0020)。

设计依据:
- phase6e-status.md: ChangeWorkflowEngine — change event → evaluate rules →
  create workflow run → execute next workflow (复用 WorkflowEngine /
  OrchestrationPipeline, 不复制)。
- 复用不复制铁律 (phase4c2-status §2): 本模块只组装既有模块, 不修改
  WorkflowEngine / ExecutionRunner / OrchestrationPipeline:
  - 规则输入: ChangeService.validate / analyze / parse_commits (Phase 6D)。
  - 触发: WorkflowRun.from_workflow + WorkflowStore.save_run + 状态机转换
    校验经 WorkflowEngine.is_valid_run_transition / is_valid_step_transition
    (公开 API), run 状态推进语义与 start_workflow 一致 (CREATED→RUNNING +
    第一步 RUNNING)。
  - 执行: 注入 executor (CLI 层装配 orchestration.pipeline.execute_workflow
    部分应用) — 因 run 已 RUNNING, OrchestrationEngine._ensure_run 走续跑
    分支 (不读 task.workflow, 天然支持 target != task.workflow)。
- 失败恢复不级联 (任务硬性要求): evaluate 永不抛 — 内部异常 → ERROR 评估
  (失败安全, 同 ValidationEngine 规则兜底); 触发失败 (目标工作流未注册 /
  任务已有 run / 执行失败) → 评估结果记录 error + triggered_workflow=None,
  不向上传播, 不影响调用方 (CLI 退出码按评估状态)。
- 无匹配触发器 → SKIP 评估 (旧 Task 兼容, 不误报, 同 L4 SKIP 语义)。

事件流 (经注入 logger):
- evaluate 完成 → change.trigger.evaluated (result=判定, 含 rules/触发结果)
- 触发成功 → change.workflow.started (run RUNNING)
- 执行终态 → change.workflow.completed (result=COMPLETED/FAILED)
"""

from __future__ import annotations

from typing import Any, Callable

from change.service import ChangeService
from events.logger import EventLogger
from events.models import Event
from runtime.registry import RuntimeRegistry
from tasks.models import Task
from tasks.store import TaskStore
from workflows.engine import WorkflowEngine, WorkflowEngineError
from workflows.models import StepStatus, WorkflowRun, WorkflowStatus
from workflows.store import WorkflowStore

from .events import (
    record_change_trigger_evaluated,
    record_change_workflow_completed,
    record_change_workflow_started,
)
from .models import ChangeEvaluation, ChangeTrigger
from .rules import RuleContext, evaluate_rules, overall_status
from .triggers import ChangeTriggerRegistry

# executor 契约: task_id → 终态判定结果 (OrchestrationOutcome 兼容鸭子类型:
# 需 .status (WorkflowStatus) 或 .ok 布尔; 复用 orchestration/pipeline.py)。
Executor = Callable[[str], Any]


class ChangeFlowError(Exception):
    """ChangeWorkflowEngine 基础异常 (评估内部错误 → ERROR 评估, 不抛给调用方)。"""


class ChangeWorkflowEngine:
    """变更驱动引擎: 触发器匹配 → 4 规则评估 → PASS 则启动/执行目标工作流。

    装配 (全部可缺省, 缺省规则 SKIP — 纯触发器/评估场景兼容):
    - triggers: ChangeTriggerRegistry (缺省新建, 路径 ~/.factory/changeflow)。
    - task_store: Task 装载 (缺省 None → evaluate 无法读取任务 → ERROR)。
    - change_service: L4 验证/关联提交/变更文件 (规则①②③ 输入; 缺省 → 对应
      规则 SKIP — 纯评估模式)。
    - workflow_engine: 触发 run 落盘 + 状态机校验 (缺省 → 触发前置失败)。
    - runtime_registry: 规则④可用 runtime 集合 (缺省 → 空集)。
    - project_runtime_prefs: {project_id: runtime_id} 规则④偏好 (缺省 {} —
      markpad 未配置偏好时 SKIP, 不误报)。
    - required_files_map: {task_type 或 trigger_id: [必需文件]} 规则③配置。
    - executor: 触发后执行 (CLI 注入 orchestration pipeline; 缺省只启动不执行)。
    - logger: 审计事件 (缺省不发)。
    """

    SOURCE = "changeflow"

    def __init__(
        self,
        *,
        triggers: ChangeTriggerRegistry | None = None,
        task_store: TaskStore | None = None,
        change_service: ChangeService | None = None,
        workflow_engine: WorkflowEngine | None = None,
        workflow_store: WorkflowStore | None = None,
        runtime_registry: RuntimeRegistry | None = None,
        project_runtime_prefs: dict[str, str] | None = None,
        required_files_map: dict[str, list[str]] | None = None,
        executor: Executor | None = None,
        logger: EventLogger | None = None,
    ) -> None:
        self._triggers = triggers or ChangeTriggerRegistry()
        self._tasks = task_store
        self._change = change_service
        self._wf = workflow_engine
        self._wf_store = workflow_store or (
            workflow_engine.store if workflow_engine is not None else None
        )
        self._runtimes = runtime_registry
        self._prefs = project_runtime_prefs or {}
        self._required_files = required_files_map or {}
        self._executor = executor
        self._logger = logger

    # ------------------------------------------------------------------ 依赖暴露 (审计/测试)

    @property
    def triggers(self) -> ChangeTriggerRegistry:
        return self._triggers

    @property
    def task_store(self) -> TaskStore | None:
        return self._tasks

    @property
    def change_service(self) -> ChangeService | None:
        return self._change

    @property
    def workflow_engine(self) -> WorkflowEngine | None:
        return self._wf

    @property
    def logger(self) -> EventLogger | None:
        return self._logger

    # ------------------------------------------------------------------ 触发器匹配

    def matching_triggers(self, task: Task) -> list[ChangeTrigger]:
        """命中任务的触发器 (项目/类型维度; 无 → 空 — 评估 SKIP)。"""
        return self._triggers.matching(
            project_id=task.project, task_type=task.type,
        )

    # ------------------------------------------------------------------ 规则上下文装配

    def build_context(self, task: Task, trigger: ChangeTrigger) -> RuleContext:
        """装配 RuleContext (4 规则只读输入; 全部失败安全, 永不抛)。

        - validation_status: ChangeService.validate (L4 判定; 未装配 → None)。
        - linked_commits: parse_commits 中解析出 task_id 的提交哈希。
        - changed_files: ChangeService.analyze 的关联文件。
        - required_files: 按 task_type 或 trigger_id 查找 (required_files_map)。
        - runtime_pref: project_runtime_prefs[task.project]。
        - available_runtimes: RuntimeRegistry AVAILABLE runtime id 集合。
        """
        validation_status: str | None = None
        linked_commits: list[str] = []
        changed_files: list[str] = []
        if self._change is not None:
            try:
                validation_status = self._change.validate(task.id).status
            except Exception:  # 失败安全: L4 异常 → 规则① SKIP (无结果)
                validation_status = None
            try:
                analysis = self._change.analyze(task.id)
                # analyze.commits 已按 task_id 过滤 (ChangeService.analyze
                # linked_hashes); 此处再保序去重双保险
                changed_files = analysis.files
                linked_commits = list(dict.fromkeys(analysis.commits))
            except Exception:  # 失败安全: 分析异常 → 证据为空
                changed_files = []
                linked_commits = []
        required_files = self._required_files.get(trigger.id) or self._required_files.get(
            task.type or "", []
        )
        runtime_pref = self._prefs.get(task.project)
        available: set[str] = set()
        if self._runtimes is not None:
            try:
                available = {r.id for r in self._runtimes.list(status="AVAILABLE")}
            except Exception:  # 失败安全: 注册表异常 → 空集 (规则④ FAIL/SKIP)
                available = set()
        return RuleContext(
            task_id=task.id,
            project_id=task.project or "default",
            validation_status=validation_status,
            required_validation=trigger.required_validation,
            linked_commits=linked_commits,
            changed_files=changed_files,
            required_files=required_files,
            runtime_pref=runtime_pref,
            available_runtimes=available,
        )

    # ------------------------------------------------------------------ 评估 + 触发

    def evaluate(
        self, task_id: str, trigger: ChangeTrigger | None = None, *,
        execute: bool | None = None,
    ) -> ChangeEvaluation:
        """完整评估: 匹配触发器 → 4 规则 → PASS 则触发目标工作流 (可选执行)。

        - trigger 缺省: 取第一个命中任务 (项目/类型) 的触发器; 无匹配 → SKIP
          评估 (trigger_id=None, 旧 Task 兼容)。
        - execute 缺省 = 本引擎是否装配 executor (CLI 装配时默认执行);
          显式 False → 只评估不触发 (纯评估模式)。
        - 失败恢复不级联: 本方法永不抛 — 内部异常 → ERROR 评估 (含 error 摘要);
          触发失败 (目标工作流未注册 / 任务已有 run / 执行失败) → 评估记
          error + triggered_workflow=None, 事件照发 (审计), 调用方不受影响。
        """
        if self._tasks is None:
            return self._error_evaluation(
                task_id, "engine has no task store: cannot evaluate",
            )
        task = self._tasks.get(task_id)
        if task is None:
            return self._error_evaluation(
                task_id, f"task not found: {task_id}",
            )
        if trigger is None:
            matched = self.matching_triggers(task)
            trigger = matched[0] if matched else None
        if trigger is None:
            evaluation = ChangeEvaluation(
                task_id=task_id, trigger_id=None, status="SKIP",
                rules=[],
                error="无匹配触发器 (项目/任务类型维度)",
            )
            self._emit_evaluated(evaluation)
            return evaluation

        # 规则评估 (build_context 失败安全; 规则纯函数不抛)
        ctx = self.build_context(task, trigger)
        rules = evaluate_rules(ctx)
        status = overall_status(rules)
        evaluation = ChangeEvaluation(
            task_id=task_id, trigger_id=trigger.id, status=status, rules=rules,
        )
        run: WorkflowRun | None = None
        outcome: Any = None
        if status == "PASS" and (execute if execute is not None else self._executor is not None):
            try:
                run, started_ev = self._launch(task, trigger)
                evaluation.triggered_workflow = trigger.target_workflow
                evaluation.run_id = run.run_id
                if self._executor is not None:
                    outcome = self._executor(task_id)
                    result = self._outcome_status(outcome)
                    self._emit_completed(task, trigger, run, result, error=outcome_error(outcome))
            except Exception as exc:  # 触发失败不级联 → ERROR 评估 (失败安全)
                evaluation.status = "ERROR"
                evaluation.error = f"{type(exc).__name__}: {exc}"
        self._emit_evaluated(evaluation)
        return evaluation

    # ------------------------------------------------------------------ 触发 (内部)

    def _launch(self, task: Task, trigger: ChangeTrigger) -> tuple[WorkflowRun, Event | None]:
        """创建目标工作流运行实例并置 RUNNING (复用 WorkflowRun/WorkflowStore +
        WorkflowEngine 公开状态机校验; 不修改 workflows/ 模块)。

        前置 (失败抛 ChangeFlowError, 由 evaluate 捕获转 ERROR 评估):
        - target_workflow 定义已注册 (WorkflowStore.get_workflow)。
        - 任务无既有运行实例 (一个 task 至多一个 run — 同 WorkflowEngine 语义)。
        run 状态推进与 WorkflowEngine.start_workflow 一致: CREATED → RUNNING,
        第一步 PENDING → RUNNING; 转换合法性经 is_valid_run_transition /
        is_valid_step_transition (公开 API) 校验。
        事件: change.workflow.started (run RUNNING 后发, 同 started 语义)。
        """
        if self._wf_store is None:
            raise ChangeFlowError("engine has no workflow store: cannot trigger workflow")
        workflow = self._wf_store.get_workflow(trigger.target_workflow)
        if workflow is None:
            raise ChangeFlowError(
                f"target workflow not registered: {trigger.target_workflow!r} "
                f"(run 'factory workflow add' first)"
            )
        existing = self._wf_store.get_run_by_task(task.id)
        if existing is not None:
            raise ChangeFlowError(
                f"task {task.id} already has a workflow run: {existing.run_id} "
                f"(one run per task)"
            )
        run = WorkflowRun.from_workflow(
            run_id=self._wf_store.next_run_id(), workflow=workflow, task_id=task.id,
        )
        # 状态机推进 (校验经公开 API; 语义同 WorkflowEngine.start_workflow)
        if not WorkflowEngine.is_valid_run_transition(run.status, WorkflowStatus.RUNNING):
            raise ChangeFlowError(
                f"invalid run transition {run.status.value} -> RUNNING (task {task.id})"
            )
        run.status = WorkflowStatus.RUNNING
        first = run.next_pending_step()
        if first is not None:
            if not WorkflowEngine.is_valid_step_transition(first.status, StepStatus.RUNNING):
                raise ChangeFlowError(
                    f"invalid step transition {first.status.value} -> RUNNING "
                    f"(step {first.step_id})"
                )
            first.status = StepStatus.RUNNING
        self._wf_store.save_run(run)
        ev = None
        if self._logger is not None:
            ev = record_change_workflow_started(
                self._logger, task_id=task.id, trigger=trigger,
                workflow_id=workflow.id, run_id=run.run_id,
            )
        return run, ev

    # ------------------------------------------------------------------ 事件

    def _emit_evaluated(self, evaluation: ChangeEvaluation) -> None:
        if self._logger is not None:
            record_change_trigger_evaluated(self._logger, evaluation=evaluation)

    def _emit_completed(
        self, task: Task, trigger: ChangeTrigger, run: WorkflowRun,
        result: str, *, error: str | None = None,
    ) -> None:
        if self._logger is not None:
            record_change_workflow_completed(
                self._logger, task_id=task.id, trigger_id=trigger.id,
                workflow_id=run.workflow_id, run_id=run.run_id,
                result=result, error=error,
            )

    # ------------------------------------------------------------------ 查询

    def workflow_chain(self, task_id: str) -> list[dict[str, Any]]:
        """任务关联的 workflow 链 (只读; change workflows 命令数据源)。

        链 = 任务工作流 (task.workflow → 定义/运行) + 触发工作流
        (change.workflow.started 事件, 含 target workflow/run_id/状态)。
        无任何记录 → [] (CLI 输出占位)。
        """
        chain: list[dict[str, Any]] = []
        task = self._tasks.get(task_id) if self._tasks is not None else None
        if task is not None and task.workflow:
            wf = self._wf_store.get_workflow(task.workflow) if self._wf_store is not None else None
            run = self._wf_store.get_run_by_task(task_id) if self._wf_store is not None else None
            chain.append({
                "task_id": task_id,
                "workflow_id": task.workflow,
                "workflow_name": wf.name if wf is not None else "",
                "run_id": run.run_id if run is not None else None,
                "status": run.status.value if run is not None else "NOT_STARTED",
                "triggered": False,
            })
        if self._logger is not None:
            events = self._logger.store.query(
                event_type="change.workflow.started", task_id=task_id,
            )
            for e in events:
                p = e.payload or {}
                chain.append({
                    "task_id": task_id,
                    "workflow_id": p.get("workflow_id", ""),
                    "workflow_name": p.get("workflow_id", ""),
                    "run_id": p.get("run_id"),
                    "status": "STARTED",
                    "triggered": True,
                    "trigger_id": p.get("trigger_id"),
                })
        return chain

    # ------------------------------------------------------------------ 内部

    def _error_evaluation(self, task_id: str, error: str) -> ChangeEvaluation:
        evaluation = ChangeEvaluation(
            task_id=task_id, status="ERROR", rules=[], error=error,
        )
        self._emit_evaluated(evaluation)
        return evaluation

    @staticmethod
    def _outcome_status(outcome: Any) -> str:
        """executor 结果 → 终态判定 (OrchestrationOutcome 兼容鸭子类型)。"""
        if outcome is None:
            return "COMPLETED"
        status = getattr(outcome, "status", None)
        if status is not None:
            return getattr(status, "value", str(status))
        ok = getattr(outcome, "ok", None)
        return "COMPLETED" if ok else "FAILED"


def outcome_error(outcome: Any) -> str | None:
    """executor 结果 → 错误摘要 (OrchestrationOutcome.error / 失败原因)。"""
    if outcome is None:
        return None
    error = getattr(outcome, "error", None)
    return str(error) if error else None
