"""cli/commands.py — 命令处理器 (薄层, 无 argparse 依赖, 可直接单测)。

铁律 (cli-design §1.3 + phase2 指令): 每个命令的唯一副作用是发布事件;
业务状态 (任务文件) 由命令先落地, 再发事件记录该行为。读命令也发事件
(task.viewed / system.logs_viewed / system.status_viewed) — phase2 指令
"所有 CLI 行为必须产生 Event" 优先于 cli-design "读命令不发事件" (ADR-0002)。

每个处理器返回 dict (CLI --json 直接输出; 人类可读由 main 格式化)。
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from agents.models import Agent, AgentStatus, Skill
from agents.registry import (
    AgentExistsError,
    AgentNotFoundError,
    AgentRegistry,
    SkillExistsError,
    SkillRegistry,
)
from assignment.allocator import (
    AgentAllocator,
    AgentAllocatorError,
    AssignmentNotFoundError,
)
from assignment.models import AssignmentStatus
from assignment.store import AssignmentStore
from events.models import EventType
from execution.dispatcher import (
    ExecutionDispatchError,
    ExecutionDispatcherError,
    NoAvailableRuntimeError,
    RuntimeAdapterNotFoundError,
)
from execution.runner import ExecutionNotFoundError, ExecutionRunnerError, ExecutionStateError
from execution.service import ExecutionService
from runtime.adapters import BUILTIN_ADAPTERS
from runtime.models import ExecutionRequest, ExecutionStatus, RuntimeInfo, RuntimeStatus
from runtime.registry import RuntimeExistsError, RuntimeNotFoundError, RuntimeRegistry
from runtime.store import RuntimeStore
from runtimes.catalog import RuntimeCatalog
from runtimes.store import CatalogStore
from tasks.models import Task, TaskStatus
from tasks.store import TaskExistsError, TaskStore
from validation.engine import ValidationEngine
from validation.models import ValidationStatus
from validation.reports import render_checks
from workflows.definitions import get_builtin
from workflows.engine import (
    StepNotReadyError,
    StepNotFoundError,
    WorkflowAlreadyStartedError,
    WorkflowEngine,
    WorkflowEngineError,
    WorkflowExistsError,
    WorkflowNotFoundError,
    WorkflowRunNotFoundError,
    WorkflowStateError,
)
from workflows.models import Workflow, WorkflowStep
from workflows.store import WorkflowStore

from recovery.checkpoint import CheckpointStore
from recovery.service import RecoveryError, RecoveryService, TaskNotFoundError

from orchestration.pipeline import execute_workflow as run_orchestration

from dashboard.collector import DashboardCollector
from dashboard.renderer import VIEWS as DASHBOARD_VIEWS

from metrics.collectors import MetricsCollector

from project.loader import (
    ProjectLoadError,
    default_examples_dir,
    discover_projects,
    load_project,
)

from workspace.loader import resolve_projects_root
from workspace.manager import (
    ProjectExistsError,
    ProjectNotFoundError,
    WorkspaceConfigError,
    WorkspaceExistsError,
    WorkspaceManager,
    WorkspaceNotFoundError,
)

from .context import FactoryContext

SOURCE = "cli"


class CliError(Exception):
    """命令级错误: 携带退出码 (cli-design §5: 1 一般错误 / 2 用法 / 3 验证失败 / 7 未找到)。"""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


def _parse_status(value: str | None) -> TaskStatus | None:
    if value is None:
        return None
    try:
        return TaskStatus.parse(value)
    except ValueError as exc:
        raise CliError(str(exc), exit_code=2) from exc


def _parse_agent_status(value: str | None) -> AgentStatus | None:
    if value is None:
        return None
    try:
        return AgentStatus.parse(value)
    except ValueError as exc:
        raise CliError(str(exc), exit_code=2) from exc


def _parse_csv(value: str | None) -> list[str]:
    """逗号分隔列表 → 去空串列表 (skills/capabilities 共用)。"""
    return [s.strip() for s in (value or "").split(",") if s.strip()]


# ------------------------------------------------------------------ factory init

def cmd_init(ctx: FactoryContext) -> dict:
    """初始化工厂: 幂等建目录骨架 + 事件库, 发 system.init。"""
    ctx.ensure_dirs()
    dirs = [d.name for d in ctx.subdirs()]
    with ctx.logger_scope() as logger:
        ev = logger.record(
            EventType.SYSTEM_INIT, source=SOURCE, action="init factory", result="OK",
            payload={"root": str(ctx.root), "db": str(ctx.db_path), "dirs": dirs},
        )
    return {
        "ok": True,
        "root": str(ctx.root),
        "db": str(ctx.db_path),
        "dirs": dirs,
        "event_seq": ev.seq,
    }


# ------------------------------------------------------------------ task 子命令

def cmd_task_create(ctx: FactoryContext, args: Any) -> dict:
    """factory task create — 定义任务, 发 task.created。"""
    task_id = args.id or ctx.open_task_store().next_id()
    task = Task(
        id=task_id,
        title=args.title,
        project=args.project or "default",
        type=args.type or "feature",
        owner=args.owner,
        workflow=args.workflow or "feature-delivery",
    )
    try:
        ctx.open_task_store().create(task)
    except TaskExistsError as exc:
        raise CliError(str(exc), exit_code=1) from exc
    with ctx.logger_scope() as logger:
        ev = logger.record(
            EventType.TASK_CREATED, source=SOURCE, project_id=task.project, task_id=task.id,
            stage=task.status.value.lower(), action="create task", result="OK",
            payload={"title": task.title, "type": task.type, "workflow": task.workflow, "owner": task.owner},
        )
    return {"ok": True, "task": task.to_dict(), "event_seq": ev.seq}


def cmd_task_list(ctx: FactoryContext, args: Any) -> dict:
    """factory task list — 任务列表 (可过滤), 发 task.viewed。"""
    status = _parse_status(args.status)
    tasks = ctx.open_task_store().list(status=status, project=args.project)
    with ctx.logger_scope() as logger:
        ev = logger.record(
            EventType.TASK_VIEWED, source=SOURCE, project_id=args.project, action="list tasks",
            result="OK", payload={"count": len(tasks), "status": args.status, "project": args.project},
        )
    return {"ok": True, "count": len(tasks), "tasks": [t.to_dict() for t in tasks], "event_seq": ev.seq}


def cmd_task_status(ctx: FactoryContext, args: Any) -> dict:
    """factory task status <id> — 任务详情 + 最近事件时间线, 发 task.viewed。"""
    store = ctx.open_task_store()
    task = store.get(args.task_id)
    if task is None:
        raise CliError(f"task not found: {args.task_id}", exit_code=7)
    with ctx.logger_scope() as logger:
        ev = logger.record(
            EventType.TASK_VIEWED, source=SOURCE, project_id=task.project, task_id=task.id,
            stage=task.status.value.lower(), action="show task", result="OK",
        )
        events = logger.store.query(task_id=task.id)
    timeline = [e.model_dump(mode="json") for e in events[-5:][::-1]]
    return {"ok": True, "task": task.to_dict(), "timeline": timeline, "event_seq": ev.seq}


def cmd_task_update(ctx: FactoryContext, args: Any) -> dict:
    """factory task update <id> --status S — 状态流转, 发 task.updated。"""
    new_status = _parse_status(args.status)
    assert new_status is not None
    store = ctx.open_task_store()
    old = store.get(args.task_id)
    if old is None:
        raise CliError(f"task not found: {args.task_id}", exit_code=7)
    task = store.update_status(args.task_id, new_status)
    with ctx.logger_scope() as logger:
        ev = logger.record(
            EventType.TASK_UPDATED, source=SOURCE, project_id=task.project, task_id=task.id,
            stage=task.status.value.lower(), action="update task status", result="OK",
            payload={"from": old.status.value, "to": task.status.value},
        )
    return {"ok": True, "task": task.to_dict(), "event_seq": ev.seq}


# ------------------------------------------------------------------ event 子命令

def cmd_event_logs(ctx: FactoryContext, args: Any) -> dict:
    """factory event logs — 事件日志查询 (倒序, 可过滤), 发 system.logs_viewed。"""
    limit = args.limit or 20
    with ctx.logger_scope() as logger:
        events = logger.store.query(project_id=args.project, task_id=args.task)
        tail = events[-limit:][::-1]
        ev = logger.record(
            EventType.SYSTEM_LOGS_VIEWED, source=SOURCE, action="view event logs", result="OK",
            payload={"limit": limit, "count": len(tail), "project": args.project, "task": args.task},
        )
    return {
        "ok": True,
        "count": len(tail),
        "events": [e.model_dump(mode="json") for e in tail],
        "event_seq": ev.seq,
    }


# ------------------------------------------------------------------ factory status

def cmd_status(ctx: FactoryContext, args: Any | None = None) -> dict:
    """factory status — 工厂总览 (Projects/Tasks/Agents/Events 计数), 发 system.status_viewed。"""
    store = ctx.open_task_store()
    tasks = store.list()
    by_status = Counter(t.status.value for t in tasks)
    projects = sorted({t.project for t in tasks})
    with ctx.logger_scope() as logger:
        all_events = logger.store.query()
        event_count = len(all_events)
        agents = sorted({e.agent_id for e in all_events if e.agent_id})
        ev = logger.record(
            EventType.SYSTEM_STATUS_VIEWED, source=SOURCE, action="factory status", result="OK",
            payload={
                "projects": projects,
                "tasks_total": len(tasks),
                "tasks_by_status": dict(by_status),
                "agents": agents,
                "events_total": event_count,
            },
        )
    return {
        "ok": True,
        "root": str(ctx.root),
        "projects": projects,
        "projects_count": len(projects),
        "tasks_count": len(tasks),
        "tasks_by_status": dict(by_status),
        "agents": agents,
        "agents_count": len(agents),
        "events_count": event_count,
        "event_seq": ev.seq,
    }


# ------------------------------------------------------------------ validate

def cmd_validate(ctx: FactoryContext, args: Any) -> dict:
    """factory validate <id> — 三层验证引擎 (L1 Factory / L2 Workflow / L3 Artifact Hook)。

    流程 (铁律): validation.started → rule.started → rule.completed → validation.completed;
    失败追加 validation.failed。所有验证行为经 EventLogger。
    退出码 (cli-design §5): 0 通过 / 3 验证失败 / 7 任务不存在 / 1 规则内部错误。
    """
    expect_status = _parse_status(args.expect_status)
    level = args.level or "L2"
    store = ctx.open_task_store()
    with ctx.logger_scope() as logger:
        engine = ValidationEngine(task_store=store, logger=logger, source=SOURCE)
        report = engine.validate(args.task_id, level=level, expect_status=expect_status)

    if not report.task_found:
        exit_code = 7   # 未找到 (cli-design §5) 优先于验证失败
    elif report.result is ValidationStatus.FAIL:
        exit_code = 3   # 验证失败
    elif report.result is ValidationStatus.ERROR:
        exit_code = 1   # 规则内部错误 → 一般错误
    else:
        exit_code = 0
    return {
        "ok": report.passed,
        "task_id": report.task_id,
        "level": report.level,
        "result": report.result.value,
        "checks": render_checks(report.results),
        "reason": report.reason,
        "exit_code": exit_code,
        "report": report.model_dump(mode="json"),
        "report_text": report.to_text(),
    }


# ------------------------------------------------------------------ agent 子命令

def cmd_agent_add(ctx: FactoryContext, args: Any) -> dict:
    """factory agent add — 注册 Agent, 发 agent.registered。"""
    agent = Agent(
        id=args.id,
        name=args.name or args.id,
        role=args.role,
        description=args.description or "",
        skills=_parse_csv(args.skills),
    )
    with ctx.logger_scope() as logger:
        registry = AgentRegistry(ctx.open_agent_store(), logger=logger)
        try:
            agent, ev = registry.register(agent)
        except AgentExistsError as exc:
            raise CliError(str(exc), exit_code=1) from exc
    return {"ok": True, "agent": agent.to_dict(), "event_seq": ev.seq if ev else None}


def cmd_agent_list(ctx: FactoryContext, args: Any) -> dict:
    """factory agent list — Agent 列表 (可过滤), 发 agent.viewed。"""
    status = _parse_agent_status(args.status)
    with ctx.logger_scope() as logger:
        registry = AgentRegistry(ctx.open_agent_store(), logger=logger)
        agents = registry.list(status=status, role=args.role, skill=args.skill)
        ev = logger.record(
            EventType.AGENT_VIEWED, source=SOURCE, action="list agents", result="OK",
            payload={"count": len(agents), "status": args.status, "role": args.role, "skill": args.skill},
        )
    return {
        "ok": True, "count": len(agents),
        "agents": [a.to_dict() for a in agents], "event_seq": ev.seq,
    }


# ------------------------------------------------------------------ agent assignment 子命令

def _open_assignment_store(ctx: FactoryContext) -> AssignmentStore:
    """装配 AssignmentStore (路径 = <root>/assignments, 目录由 store 首次原子写自动创建,
    同 runtime 模式 ADR-0006 决策 5 — 不依赖 context.py 骨架)。"""
    return AssignmentStore(ctx.root / "assignments")


def _parse_assignment_status(value: str | None) -> AssignmentStatus | None:
    if value is None:
        return None
    try:
        return AssignmentStatus.parse(value)
    except ValueError as exc:
        raise CliError(str(exc), exit_code=2) from exc


def _assignment_cli_error(exc: Exception) -> CliError:
    """assignment 域异常 → CliError (cli-design §5: 7 未找到 / 1 状态冲突或不可用)。"""
    if isinstance(exc, (AssignmentNotFoundError, AgentNotFoundError)):
        return CliError(str(exc), exit_code=7)
    return CliError(str(exc), exit_code=1)


def _resolve_step(ctx: FactoryContext, task_id: str, step_id: str):
    """解析任务关联工作流中的步骤定义 (task.workflow → 定义 → 步骤), 供分配匹配。"""
    task = ctx.open_task_store().get(task_id)
    if task is None:
        raise CliError(f"task not found: {task_id}", exit_code=7)
    workflow_id = task.workflow
    if not workflow_id:
        raise CliError(f"task has no workflow: {task_id}", exit_code=7)
    engine = WorkflowEngine(WorkflowStore(ctx.workflows_dir), task_store=ctx.open_task_store())
    workflow = engine.get_workflow(workflow_id)
    if workflow is None:
        raise CliError(
            f"workflow not registered: {workflow_id!r} (task {task_id}; "
            f"run 'factory workflow add' first)",
            exit_code=7,
        )
    for step in workflow.steps:
        if step.id == step_id:
            return step
    raise CliError(f"step not found: {step_id!r} in workflow {workflow_id!r}", exit_code=7)


def cmd_agent_assign(ctx: FactoryContext, args: Any) -> dict:
    """factory agent assign --task T-001 --step development [--agent A-001]
    — 分配 Agent (自动匹配或显式指定), 发 agent.assignment.created (+ Agent→WORKING)。

    退出码: 7 任务/工作流/步骤/Agent 未找到; 1 无可用 Agent / Agent 不可用 / 执行不存在。
    """
    if not args.step and not args.agent:
        raise CliError("assign requires --step or --agent", exit_code=2)
    task = ctx.open_task_store().get(args.task)
    if task is None:
        raise CliError(f"task not found: {args.task}", exit_code=7)
    step = None
    workflow_id = task.workflow
    if args.step:
        step = _resolve_step(ctx, args.task, args.step)
    with ctx.logger_scope() as logger:
        allocator = AgentAllocator(
            _open_assignment_store(ctx),
            AgentRegistry(ctx.open_agent_store(), logger=logger),
            logger=logger,
            runtime_store=_open_runtime_store(ctx),
        )
        try:
            assignment, ev = allocator.assign(
                args.task, step=step, agent_id=args.agent, workflow_id=workflow_id,
                execution_id=args.execution,
            )
        except (AgentAllocatorError, AgentNotFoundError) as exc:
            raise _assignment_cli_error(exc) from exc
        agent = AgentRegistry(ctx.open_agent_store(), logger=logger).get(assignment.agent_id)
    return {
        "ok": True,
        "assignment": assignment.to_dict(),
        "agent": agent.to_dict() if agent is not None else None,
        "event_seq": ev.seq if ev else None,
    }


def cmd_agent_assignments(ctx: FactoryContext, args: Any) -> dict:
    """factory agent assignments — Assignment 列表 (可过滤), 发 agent.assignment.viewed。"""
    status = _parse_assignment_status(args.status)
    with ctx.logger_scope() as logger:
        allocator = AgentAllocator(_open_assignment_store(ctx), AgentRegistry(ctx.open_agent_store()))
        assignments = allocator.list(task_id=args.task, agent_id=args.agent, status=status)
        ev = logger.record(
            EventType.ASSIGNMENT_VIEWED, source=SOURCE, task_id=args.task,
            action="list assignments", result="OK",
            payload={"count": len(assignments), "task": args.task, "agent": args.agent,
                     "status": args.status},
        )
    return {
        "ok": True, "count": len(assignments),
        "assignments": [a.to_dict() for a in assignments], "event_seq": ev.seq,
    }


def cmd_agent_release(ctx: FactoryContext, args: Any) -> dict:
    """factory agent release ASSIGNMENT_ID — 解除分配, Agent 回 AVAILABLE, 发 agent.released。"""
    with ctx.logger_scope() as logger:
        allocator = AgentAllocator(
            _open_assignment_store(ctx),
            AgentRegistry(ctx.open_agent_store(), logger=logger),
            logger=logger,
        )
        try:
            assignment, ev = allocator.release(args.assignment_id)
        except AgentAllocatorError as exc:
            raise _assignment_cli_error(exc) from exc
    return {
        "ok": True,
        "assignment": assignment.to_dict(),
        "agent_id": assignment.agent_id,
        "event_seq": ev.seq if ev else None,
    }


# ------------------------------------------------------------------ skill 子命令

def cmd_skill_add(ctx: FactoryContext, args: Any) -> dict:
    """factory skill add — 注册 Skill (能力目录), 发 skill.registered。"""
    skill = Skill(
        id=args.id,
        name=args.name or args.id,
        category=args.category or "general",
        description=args.description or "",
        capabilities=_parse_csv(args.capabilities),
        version=args.version or "1.0.0",
    )
    with ctx.logger_scope() as logger:
        registry = SkillRegistry(ctx.open_skill_store(), logger=logger)
        try:
            skill, ev = registry.register(skill)
        except SkillExistsError as exc:
            raise CliError(str(exc), exit_code=1) from exc
    return {"ok": True, "skill": skill.to_dict(), "event_seq": ev.seq if ev else None}


def cmd_skill_list(ctx: FactoryContext, args: Any) -> dict:
    """factory skill list — Skill 列表 (可过滤), 发 skill.viewed。"""
    with ctx.logger_scope() as logger:
        registry = SkillRegistry(ctx.open_skill_store(), logger=logger)
        skills = registry.list(category=args.category)
        ev = logger.record(
            EventType.SKILL_VIEWED, source=SOURCE, action="list skills", result="OK",
            payload={"count": len(skills), "category": args.category},
        )
    return {
        "ok": True, "count": len(skills),
        "skills": [s.to_dict() for s in skills], "event_seq": ev.seq,
    }


# ------------------------------------------------------------------ workflow 子命令

def _open_workflow_engine(ctx: FactoryContext, logger) -> WorkflowEngine:
    """装配 WorkflowEngine (store 路径 = <root>/workflows/workflows.json, 不经 context.py)。"""
    return WorkflowEngine(
        WorkflowStore(ctx.workflows_dir),
        task_store=ctx.open_task_store(),
        logger=logger,
    )


def _wf_cli_error(exc: WorkflowEngineError) -> CliError:
    """engine 异常 → CliError (cli-design §5: 7 未找到 / 1 一般错误 / 2 用法)。"""
    if isinstance(exc, (WorkflowRunNotFoundError, WorkflowNotFoundError)):
        return CliError(str(exc), exit_code=7)
    if isinstance(exc, (WorkflowExistsError, WorkflowAlreadyStartedError,
                        WorkflowStateError, StepNotFoundError, StepNotReadyError)):
        return CliError(str(exc), exit_code=1)
    return CliError(str(exc), exit_code=1)


def cmd_workflow_list(ctx: FactoryContext, args: Any) -> dict:
    """factory workflow list — 工作流定义列表, 发 workflow.viewed。"""
    with ctx.logger_scope() as logger:
        engine = _open_workflow_engine(ctx, logger)
        workflows = engine.list_workflows()
        ev = logger.record(
            EventType.WORKFLOW_VIEWED, source=SOURCE, action="list workflows", result="OK",
            payload={"count": len(workflows)},
        )
    return {
        "ok": True, "count": len(workflows),
        "workflows": [w.to_dict() for w in workflows], "event_seq": ev.seq,
    }


def cmd_workflow_add(ctx: FactoryContext, args: Any) -> dict:
    """factory workflow add — 注册工作流定义 (--steps 自定义或内置定义), 发 workflow.created。"""
    if args.steps:
        names = _parse_csv(args.steps)
        if not names:
            raise CliError("--steps requires at least one step", exit_code=2)
        steps = [
            WorkflowStep(id=s, name=s, order=i + 1) for i, s in enumerate(names)
        ]
        workflow = Workflow(
            id=args.id, name=args.name or args.id,
            description=args.description or "", steps=steps,
        )
    else:
        builtin = get_builtin(args.id)
        if builtin is None:
            raise CliError(
                f"no builtin workflow: {args.id} (pass --steps a,b,c to define custom)",
                exit_code=2,
            )
        workflow = Workflow(
            id=args.id, name=args.name or builtin.name,
            description=args.description or builtin.description,
            steps=builtin.steps,
        )
    with ctx.logger_scope() as logger:
        engine = _open_workflow_engine(ctx, logger)
        try:
            wf, ev = engine.create_workflow(workflow)
        except WorkflowExistsError as exc:
            raise _wf_cli_error(exc) from exc
    return {"ok": True, "workflow": wf.to_dict(), "event_seq": ev.seq if ev else None}


def cmd_workflow_run(ctx: FactoryContext, args: Any) -> dict:
    """factory workflow run TASK_ID [--auto] — 启动任务对应工作流 (发 workflow.started);
    --auto 自动执行完整链路 (Workflow→Matcher→Allocator→Execution→Runner→推进),
    发 orchestration.* 事件; 失败 → Workflow FAILED (无半完成状态)。"""
    if getattr(args, "auto", False):
        return _cmd_workflow_run_auto(ctx, args)
    with ctx.logger_scope() as logger:
        engine = _open_workflow_engine(ctx, logger)
        try:
            run, ev = engine.start_workflow(args.task_id)
        except WorkflowEngineError as exc:
            raise _wf_cli_error(exc) from exc
    return {
        "ok": True,
        "task_id": args.task_id,
        "run": run.to_dict(),
        "workflow": {"id": run.workflow_id, "name": run.workflow_name},
        "current_step": run.current_step,
        "event_seq": ev.seq if ev else None,
    }


def _cmd_workflow_run_auto(ctx: FactoryContext, args: Any) -> dict:
    """workflow run --auto: 完整自动执行链路 (经 orchestration.pipeline 单一组合根)。

    输出 Workflow/Step/Agent/Runtime/Result (phase4c2-status §3 CLI)。
    退出码: 0 COMPLETED; 7 任务未找到; 1 执行失败 (无 Agent/无 Runtime/执行 FAILED/
    前置错误 → Workflow FAILED 或编排失败)。
    """
    task = ctx.open_task_store().get(args.task_id)
    if task is None:
        raise CliError(f"task not found: {args.task_id}", exit_code=7)
    with ctx.logger_scope() as logger:
        outcome = run_orchestration(
            args.task_id,
            workflow_store=WorkflowStore(ctx.workflows_dir),
            task_store=ctx.open_task_store(),
            agent_store=ctx.open_agent_store(),
            assignment_store=_open_assignment_store(ctx),
            runtime_store=_open_runtime_store(ctx),
            logger=logger,
        )
    data = {
        "ok": outcome.ok,
        "auto": True,
        "task_id": args.task_id,
        "workflow": {
            "id": outcome.workflow_id,
            "name": outcome.run.workflow_name if outcome.run is not None else None,
        },
        "run_id": outcome.run_id,
        "status": outcome.status.value,
        "steps": [s.to_dict() for s in outcome.steps],
        "error": outcome.error,
        "events": [e.type.value for e in outcome.events],
        "event_seq": outcome.events[-1].seq if outcome.events else None,
    }
    if outcome.run is not None:
        data["run"] = outcome.run.to_dict()
    if not outcome.ok:
        data["exit_code"] = 1  # 执行失败: workflow 未能 COMPLETED (cli-design §5: 1 一般错误)
    return data


def cmd_workflow_status(ctx: FactoryContext, args: Any) -> dict:
    """factory workflow status TASK_ID — 步骤进度 (✓/▶/○/✘), 发 workflow.viewed。"""
    with ctx.logger_scope() as logger:
        engine = _open_workflow_engine(ctx, logger)
        run = engine.status(args.task_id)
        if run is None:
            task = ctx.open_task_store().get(args.task_id)
            if task is None:
                raise CliError(f"task not found: {args.task_id}", exit_code=7)
            raise CliError(
                f"task has no workflow run: {args.task_id} "
                f"(run 'factory workflow run {args.task_id}' first)",
                exit_code=1,
            )
        ev = logger.record(
            EventType.WORKFLOW_VIEWED, source=SOURCE, task_id=args.task_id,
            stage=run.status.value.lower(), action="show workflow status", result="OK",
            payload={"workflow_id": run.workflow_id, "run_id": run.run_id},
        )
    symbols = {  # ✓ 完成 / ▶ 当前 / ○ 待办 / ✘ 失败
        "COMPLETED": "✓", "RUNNING": "▶", "PENDING": "○", "FAILED": "✘",
    }
    steps = [
        {
            "step_id": st.step_id,
            "status": st.status.value,
            "symbol": symbols.get(st.status.value, "?"),
        }
        for st in run.step_states
    ]
    # current_step 为 PENDING 时标记 ▶ (run 启动后第一步尚未 start_step, 仍属"当前待办")
    for st in steps:
        if st["status"] == "PENDING" and st["step_id"] == run.current_step:
            st["symbol"] = "▶"
    return {
        "ok": True,
        "task_id": args.task_id,
        "run": run.to_dict(),
        "steps": steps,
        "event_seq": ev.seq,
    }


# ------------------------------------------------------------------ runtime 子命令

def _open_runtime_store(ctx: FactoryContext) -> RuntimeStore:
    """装配 RuntimeStore (路径 = <root>/runtimes/runtimes.json, 不经 context.py;
    目录由 store 首次原子写时自动创建, 见 ADR-0006 决策 5)。"""
    return RuntimeStore(ctx.root / "runtimes")


def _parse_runtime_status(value: str | None) -> RuntimeStatus | None:
    if value is None:
        return None
    try:
        return RuntimeStatus.parse(value)
    except ValueError as exc:
        raise CliError(str(exc), exit_code=2) from exc


def cmd_runtime_add(ctx: FactoryContext, args: Any) -> dict:
    """factory runtime add — 注册 Runtime 身份, 发 runtime.registered。"""
    runtime = RuntimeInfo(
        id=args.id,
        name=args.name or args.id,
        type=args.type,
        description=args.description or "",
    )
    with ctx.logger_scope() as logger:
        registry = RuntimeRegistry(_open_runtime_store(ctx), logger=logger)
        try:
            runtime, ev = registry.register(runtime)
        except RuntimeExistsError as exc:
            raise CliError(str(exc), exit_code=1) from exc
    return {"ok": True, "runtime": runtime.to_dict(), "event_seq": ev.seq if ev else None}


def cmd_runtime_list(ctx: FactoryContext, args: Any) -> dict:
    """factory runtime list — Runtime 列表 (可过滤), 发 runtime.viewed。"""
    status = _parse_runtime_status(args.status)
    with ctx.logger_scope() as logger:
        registry = RuntimeRegistry(_open_runtime_store(ctx), logger=logger)
        runtimes = registry.list(status=status)
        ev = logger.record(
            EventType.RUNTIME_VIEWED, source=SOURCE, action="list runtimes", result="OK",
            payload={"count": len(runtimes), "status": args.status},
        )
    return {
        "ok": True, "count": len(runtimes),
        "runtimes": [r.to_dict() for r in runtimes], "event_seq": ev.seq,
    }


SMOKE_INSTRUCTION = "Reply with exactly: OK"  # runtime test 默认冒烟指令 (最小 Hermes 调用)


def cmd_runtime_test(ctx: FactoryContext, args: Any) -> dict:
    """factory runtime test <runtime_id> — smoke test: 构造最小 execution →
    内置 Adapter.execute → 输出 Runtime/Status (SUCCESS/FAILED), 发 runtime.viewed。

    前置 (ADR-0007 决策 3): runtime 身份须已注册 (registry 是派发解析的唯一事实源);
    已注册但无 Adapter 实现 → 配置缺口 (rc 1, 同 cmd_execution_run 契约)。
    退出码: 0 smoke SUCCESS / 1 smoke FAILED (runtime 不健康) 或配置缺口 /
    7 runtime 未注册。
    副作用边界: smoke 为临时执行 — 不落库 (runtimes.json 无 executions/results 残留)、
    Adapter 不写 Event (ADR-0006 解耦铁律); 本命令仅发 runtime.viewed 审计事件
    (ADR-0002: 所有 CLI 行为必须产生 Event)。
    """
    with ctx.logger_scope() as logger:
        registry = RuntimeRegistry(_open_runtime_store(ctx), logger=logger)
        runtime = registry.get(args.runtime_id)
        if runtime is None:
            raise CliError(f"runtime not found: {args.runtime_id}", exit_code=7)
        adapter = BUILTIN_ADAPTERS.get(args.runtime_id)
        if adapter is None:
            raise CliError(
                f"no adapter implementation for runtime: {args.runtime_id} "
                f"(registered but not built-in)",
                exit_code=1,
            )
        request = ExecutionRequest(
            id=f"EX-SMOKE-{args.runtime_id}",
            task_id="SMOKE",
            runtime_id=args.runtime_id,
            input={"instruction": args.instruction or SMOKE_INSTRUCTION},
        )
        result = adapter.execute(request)
        ev = logger.record(
            EventType.RUNTIME_VIEWED, source=SOURCE, task_id=request.task_id,
            stage=runtime.status.value.lower(), action="test runtime", result="OK",
            payload={
                "runtime_id": args.runtime_id,
                "execution_id": request.id,
                "smoke_status": result.status.value,
                "error": result.error,
            },
        )
    data = {
        "ok": result.status is ExecutionStatus.SUCCESS,
        "runtime": args.runtime_id,
        "status": result.status.value,
        "execution_id": request.id,
        "result": result.to_dict(),
        "event_seq": ev.seq,
    }
    if result.status is not ExecutionStatus.SUCCESS:
        data["exit_code"] = 1  # smoke FAILED = runtime 不健康 → rc 1
    return data


# ------------------------------------------------------------------ runtime catalog 子命令 (Phase 5A.1, ADR-0014)

def _open_catalog_store(ctx: FactoryContext) -> CatalogStore:
    """装配 CatalogStore (路径 = <root>/runtimes/catalog.json — 与实例库
    runtimes.json 独立文件, phase5a1-status.md 注意; 目录由首次原子写自动创建)。"""
    return CatalogStore(ctx.root / "runtimes")


def cmd_runtime_catalog_list(ctx: FactoryContext, args: Any) -> dict:
    """factory runtime catalog list — 能力目录列表 (默认定义基线 + 注册定义,
    只读), 发 runtime.catalog.viewed。"""
    with ctx.logger_scope() as logger:
        catalog = RuntimeCatalog(_open_catalog_store(ctx), logger=logger)
        definitions = catalog.list(type=args.type)
        ev = logger.record(
            EventType.RUNTIME_CATALOG_VIEWED, source=SOURCE,
            action="list runtime catalog", result="OK",
            payload={"count": len(definitions), "type": args.type},
        )
    return {
        "ok": True, "count": len(definitions),
        "definitions": [d.to_dict() for d in definitions], "event_seq": ev.seq,
    }


def cmd_runtime_catalog_show(ctx: FactoryContext, args: Any) -> dict:
    """factory runtime catalog show <id> — 定义详情 (默认定义或已注册定义, 只读),
    发 runtime.catalog.viewed; 未找到 → 退出码 7。"""
    with ctx.logger_scope() as logger:
        catalog = RuntimeCatalog(_open_catalog_store(ctx), logger=logger)
        definition = catalog.get(args.definition_id)
        if definition is None:
            raise CliError(
                f"runtime definition not found: {args.definition_id}", exit_code=7
            )
        ev = logger.record(
            EventType.RUNTIME_CATALOG_VIEWED, source=SOURCE,
            action="show runtime definition", result="OK",
            payload={
                "definition_id": definition.id,
                "type": definition.type,
                "version": definition.version,
                "status": definition.status.value,
            },
        )
    return {"ok": True, "definition": definition.to_dict(), "event_seq": ev.seq}


# ------------------------------------------------------------------ execution 子命令

def cmd_execution_list(ctx: FactoryContext, args: Any) -> dict:
    """factory execution list — 执行记录列表 (可过滤), 发 execution.viewed。"""
    with ctx.logger_scope() as logger:
        store = _open_runtime_store(ctx)
        requests = store.list_executions(task_id=args.task)
        results = {res.request_id: res for res in store.list_results()}
        executions = []
        for req in requests:
            item = req.to_dict()
            res = results.get(req.id)
            item["result"] = res.to_dict() if res is not None else None
            executions.append(item)
        ev = logger.record(
            EventType.EXECUTION_VIEWED, source=SOURCE, task_id=args.task,
            action="list executions", result="OK",
            payload={"count": len(executions), "task": args.task},
        )
    return {
        "ok": True, "count": len(executions),
        "executions": executions, "event_seq": ev.seq,
    }


def _open_execution_service(ctx: FactoryContext, logger) -> ExecutionService:
    """装配 ExecutionService: RuntimeStore + Registry (同事件库) + 内置 Adapter + Workflow 联动。

    内置 Adapter (BUILTIN_ADAPTERS: echo) 提供实现; runtime 身份 (RuntimeInfo) 须
    经 `factory runtime add` 显式注册 — registry 是派发解析的唯一事实源 (ADR-0007 决策 3)。
    Workflow 联动经 _open_workflow_engine (complete_step/fail_workflow 不需 runtime_store)。
    """
    store = _open_runtime_store(ctx)
    registry = RuntimeRegistry(store, logger=logger)
    engine = _open_workflow_engine(ctx, logger)
    return ExecutionService(
        store, registry, adapters=BUILTIN_ADAPTERS, logger=logger, workflow_engine=engine,
    )


def _exec_cli_error(exc: Exception) -> CliError:
    """execution 域异常 → CliError (cli-design §5: 7 未找到 / 1 状态冲突)。"""
    if isinstance(exc, (ExecutionNotFoundError, RuntimeNotFoundError)):
        return CliError(str(exc), exit_code=7)
    return CliError(str(exc), exit_code=1)


def cmd_execution_run(ctx: FactoryContext, args: Any) -> dict:
    """factory execution run EXECUTION_ID — 执行 pending execution (发 execution.started/completed/failed)。

    退出码: 0 成功 (含执行结果为 FAILED 的业务失败 — run 命令本身成功);
    7 执行/runtime 未找到; 1 状态冲突 (非 PENDING / 无可用 runtime / 无 Adapter 实现)。
    """
    with ctx.logger_scope() as logger:
        service = _open_execution_service(ctx, logger)
        try:
            outcome = service.run(args.execution_id)
        except (ExecutionRunnerError, ExecutionDispatcherError, RuntimeNotFoundError) as exc:
            raise _exec_cli_error(exc) from exc
    return {
        "ok": True,
        "execution_id": args.execution_id,
        "runtime": outcome.request.runtime_id,
        "status": outcome.request.status.value,
        "execution": outcome.request.to_dict(),
        "result": outcome.result.to_dict() if outcome.result is not None else None,
        "workflow": {
            "step_completed": outcome.workflow_step_completed,
            "workflow_failed": outcome.workflow_failed,
            "error": outcome.workflow_error,
        },
        "events": [e.type.value for e in outcome.events],
        "event_seq": outcome.events[-1].seq if outcome.events else None,
    }


def cmd_execution_status(ctx: FactoryContext, args: Any) -> dict:
    """factory execution status EXECUTION_ID — 查看执行状态/结果 (发 execution.viewed)。"""
    with ctx.logger_scope() as logger:
        service = _open_execution_service(ctx, logger)
        request, result = service.status(args.execution_id)
        if request is None:
            raise CliError(f"execution not found: {args.execution_id}", exit_code=7)
        ev = logger.record(
            EventType.EXECUTION_VIEWED, source=SOURCE, task_id=request.task_id,
            stage=request.status.value.lower(), action="show execution status", result="OK",
            payload={"execution_id": request.id},
        )
    return {
        "ok": True,
        "execution_id": args.execution_id,
        "execution": request.to_dict(),
        "result": result.to_dict() if result is not None else None,
        "event_seq": ev.seq,
    }


# ------------------------------------------------------------------ checkpoint / recover 子命令

def _open_checkpoint_store(ctx: FactoryContext) -> CheckpointStore:
    """装配 CheckpointStore (路径 = <root>/checkpoints, 目录由 store 首次原子写自动创建,
    同 runtime/assignments 模式 ADR-0006 决策 5 — 不依赖 context.py 骨架)。"""
    return CheckpointStore(ctx.root / "checkpoints")


def _open_recovery_service(ctx: FactoryContext, logger) -> RecoveryService:
    """装配 RecoveryService: 事件库 (logger.store) + 全存储 + CheckpointStore + 同一 logger。"""
    return RecoveryService(
        task_store=ctx.open_task_store(),
        workflow_store=WorkflowStore(ctx.workflows_dir),
        assignment_store=_open_assignment_store(ctx),
        runtime_store=_open_runtime_store(ctx),
        agent_registry=AgentRegistry(ctx.open_agent_store(), logger=logger),
        event_store=logger.store,
        checkpoint_store=_open_checkpoint_store(ctx),
        logger=logger,
    )


def _recovery_cli_error(exc: RecoveryError) -> CliError:
    """recovery 域异常 → CliError (cli-design §5: 7 未找到 / 1 一般错误)。"""
    if isinstance(exc, TaskNotFoundError):
        return CliError(str(exc), exit_code=7)
    return CliError(str(exc), exit_code=1)


def cmd_checkpoint_create(ctx: FactoryContext, args: Any) -> dict:
    """factory checkpoint create TASK_ID — 创建任务 checkpoint 快照
    (发 recovery.started + recovery.completed)。退出码: 0 成功 / 7 任务不存在。"""
    with ctx.logger_scope() as logger:
        service = _open_recovery_service(ctx, logger)
        try:
            checkpoint, ev = service.checkpoint(args.task_id)
        except RecoveryError as exc:
            raise _recovery_cli_error(exc) from exc
    return {"ok": True, "checkpoint": checkpoint.to_dict(), "event_seq": ev.seq if ev else None}


def cmd_checkpoint_list(ctx: FactoryContext, args: Any) -> dict:
    """factory checkpoint list — checkpoint 列表 (发 recovery.started 审计, ADR-0002 铁律)。"""
    with ctx.logger_scope() as logger:
        store = _open_checkpoint_store(ctx)
        checkpoints = store.list()
        ev = logger.record(
            EventType.RECOVERY_STARTED, source=SOURCE, action="list checkpoints", result="OK",
            payload={"count": len(checkpoints)},
        )
    return {
        "ok": True, "count": len(checkpoints),
        "checkpoints": [c.to_dict() for c in checkpoints], "event_seq": ev.seq,
    }


def cmd_recover(ctx: FactoryContext, args: Any) -> dict:
    """factory recover TASK_ID — 恢复中断任务: 事件回放 + 状态纠正
    (发 recovery.started → completed|failed)。

    退出码 (同 execution run 契约): 0 恢复操作完成 — resume_ok 携带于结果
    (True 可继续 / False 已终态拒绝, 操作本身成功); 7 任务不存在; 1 恢复内部错误。
    """
    with ctx.logger_scope() as logger:
        service = _open_recovery_service(ctx, logger)
        try:
            result, ev = service.recover(args.task_id)
        except RecoveryError as exc:
            raise _recovery_cli_error(exc) from exc
    return {
        "ok": True,
        "task_id": result.task_id,
        "recovery": result.to_dict(),
        "event_seq": ev.seq if ev else None,
    }


# ------------------------------------------------------------------ dashboard

def cmd_dashboard(ctx: FactoryContext, args: Any) -> dict:
    """factory dashboard — 只读控制台总览 (Rich 六视图), 发 dashboard.viewed。

    只读铁律 (phase4c4-status.md): 收集器只调用各 store 读接口, 本命令唯一的
    副作用是 dashboard.viewed 审计事件 (ADR-0002: 所有 CLI 行为必须产生 Event)。
    非法 --view → 用法错误 (退出码 2)。
    """
    view = args.view or "all"
    if view != "all" and view not in DASHBOARD_VIEWS:
        raise CliError(
            f"invalid view: {view!r} (expected one of: all, {', '.join(DASHBOARD_VIEWS)})",
            exit_code=2,
        )
    with ctx.logger_scope() as logger:
        # Phase 6A Projects View 数据源: workspace 项目定义 (无 workspace/损坏 →
        # 空列表, Dashboard 永不因 workspace 配置问题失败 — 只读兜底)。
        try:
            ws_projects = _open_workspace_manager(ctx).list_projects()
        except (WorkspaceNotFoundError, WorkspaceConfigError):
            ws_projects = []
        collector = DashboardCollector(
            task_store=ctx.open_task_store(),
            agent_registry=AgentRegistry(ctx.open_agent_store()),
            workflow_store=WorkflowStore(ctx.workflows_dir),
            runtime_store=_open_runtime_store(ctx),
            catalog_store=_open_catalog_store(ctx),
            event_store=logger.store,
            checkpoint_store=_open_checkpoint_store(ctx),
            project_id=args.project,
            projects=ws_projects,
            recent_limit=args.limit,
        )
        snapshot = collector.collect()
        ev = logger.record(
            EventType.DASHBOARD_VIEWED, source=SOURCE, project_id=args.project,
            stage="viewed", action="view dashboard", result="OK",
            payload={
                "view": view,
                "tasks_total": snapshot.tasks.total,
                "agents_total": snapshot.agents.total,
                "workflow_runs": snapshot.workflows.runs_total,
                "executions_total": snapshot.executions.total,
                "execution_success": snapshot.executions.success,
                "execution_failed": snapshot.executions.failed,
                "checkpoints_total": snapshot.checkpoints.total,
                "catalog_definitions": snapshot.catalog.total,
                "projects_total": snapshot.projects.total,
                "events_total": snapshot.metrics.event_count,
            },
        )
    return {
        "ok": True,
        "view": view,
        "snapshot": snapshot.to_dict(),
        "event_seq": ev.seq,
    }


# ------------------------------------------------------------------ metrics (Phase 5B, ADR-0015)

def cmd_metrics(ctx: FactoryContext, args: Any) -> dict:
    """factory metrics — 工厂生产指标 (六域 + 失败原因, 只读), 发 metrics.viewed。

    只读铁律 (phase5b-status.md): 收集器只调用各 store 读接口 (query/list/count),
    本命令唯一的副作用是 metrics.viewed 审计事件 (ADR-0002: 所有 CLI 行为必须
    产生 Event, 同 dashboard.viewed)。指标纯计算不持久化 (ADR-0015 决策 2)。
    """
    project_id = getattr(args, "project", None)
    with ctx.logger_scope() as logger:
        collector = MetricsCollector(
            event_store=logger.store,
            task_store=ctx.open_task_store(),
            agent_registry=AgentRegistry(ctx.open_agent_store()),
            workflow_store=WorkflowStore(ctx.workflows_dir),
            runtime_store=_open_runtime_store(ctx),
            project_id=project_id,
        )
        metrics = collector.collect()
        ev = logger.record(
            EventType.METRICS_VIEWED, source=SOURCE, project_id=project_id,
            stage="viewed", action="view metrics", result="OK",
            payload={
                "tasks_total": metrics.tasks.total,
                "tasks_completed": metrics.tasks.completed,
                "tasks_failed": metrics.tasks.failed,
                "executions_total": metrics.executions.total,
                "executions_success": metrics.executions.success,
                "executions_failed": metrics.executions.failed,
                "first_attempt_success_rate": metrics.executions.first_attempt_success_rate,
                "agents_total": metrics.agents_total,
                "workflow_runs": metrics.workflows.run_count,
                "workflow_success_rate": metrics.workflows.success_rate,
                "validation_pass_rate": metrics.validation.pass_rate,
                "failure_reasons": len(metrics.failures.failure_reason_count),
            },
        )
    return {
        "ok": True,
        "metrics": metrics.to_dict(),
        "event_seq": ev.seq,
    }


# ------------------------------------------------------------------ workspace 子命令 (Phase 6A, ADR-0016)

def _open_workspace_manager(ctx: FactoryContext) -> WorkspaceManager:
    """装配 WorkspaceManager (examples_dir = 内置示例源, FACTORY_EXAMPLES_DIR 覆盖)。"""
    return WorkspaceManager(ctx.root, examples_dir=default_examples_dir())


def _ws_cli_error(exc: Exception) -> CliError:
    """workspace 域异常 → CliError (cli-design §5: 7 未找到 / 1 配置错误)。"""
    if isinstance(exc, WorkspaceNotFoundError):
        return CliError(str(exc), exit_code=7)
    if isinstance(exc, (WorkspaceExistsError, ProjectExistsError, ProjectNotFoundError,
                        WorkspaceConfigError)):
        return CliError(str(exc), exit_code=1)
    return CliError(str(exc), exit_code=1)


def cmd_workspace_init(ctx: FactoryContext, args: Any) -> dict:
    """factory workspace init — 创建 workspace.yaml (含示例项目引用), 发 workspace.created。

    项目引用默认 = 自动发现 (managed projects 目录 ∪ examples 内置示例源);
    已存在且未 --force → 退出码 1; 引用项目配置损坏 → 退出码 1 (先解析后落盘,
    不留下半写配置)。只创建 workspace.yaml, 不复制/修改任何项目配置 (KISS)。
    """
    manager = _open_workspace_manager(ctx)
    with ctx.logger_scope() as logger:
        try:
            workspace, ev = manager.create_workspace(
                name=args.name, logger=logger, force=args.force,
            )
        except (WorkspaceExistsError, WorkspaceConfigError) as exc:
            raise _ws_cli_error(exc) from exc
    return {
        "ok": True,
        "workspace": workspace.to_dict(),
        "workspace_file": str(manager.workspace_path),
        "event_seq": ev.seq if ev else None,
    }


def cmd_workspace_show(ctx: FactoryContext, args: Any) -> dict:
    """factory workspace show — Workspace 详情 + 项目列表 (含状态), 发 workspace.viewed。

    退出码: 7 未初始化 (无 workspace.yaml); 1 配置损坏/引用项目缺失。
    """
    manager = _open_workspace_manager(ctx)
    try:
        workspace = manager.load_workspace()
    except (WorkspaceNotFoundError, WorkspaceConfigError) as exc:
        raise _ws_cli_error(exc) from exc
    with ctx.logger_scope() as logger:
        ev = logger.record(
            EventType.WORKSPACE_VIEWED, source=SOURCE, stage="viewed",
            action="show workspace", result="OK",
            payload={
                "name": workspace.name,
                "version": workspace.version,
                "projects": workspace.project_ids(),
                "projects_count": len(workspace.projects),
            },
        )
    return {
        "ok": True,
        "workspace": workspace.to_dict(),
        "workspace_file": str(manager.workspace_path),
        "event_seq": ev.seq,
    }


# ------------------------------------------------------------------ project 子命令 (Phase 5A + Phase 6A 增强)

def cmd_project_list(ctx: FactoryContext, args: Any) -> dict:
    """factory project list — 项目列表 (Project/Language/Status/Repository), 发 project.viewed。

    数据源 (Phase 6A 增强): 有 workspace → workspace.projects (注册列表, 含
    status/runtime_preferences 增强字段); 无 workspace → 回落扫描 examples
    (Phase 5A 兼容行为)。配置损坏 → 退出码 1 (不静默跳过)。
    """
    manager = _open_workspace_manager(ctx)
    try:
        workspace = manager.load_workspace()
        projects = workspace.projects
        source, source_path = "workspace", str(manager.workspace_path)
    except WorkspaceNotFoundError:
        examples_dir = default_examples_dir()
        try:
            projects = discover_projects(examples_dir)
        except ProjectLoadError as exc:
            raise CliError(str(exc), exit_code=1) from exc
        source, source_path = "examples", str(examples_dir)
    except WorkspaceConfigError as exc:
        raise CliError(str(exc), exit_code=1) from exc
    with ctx.logger_scope() as logger:
        ev = logger.record(
            EventType.PROJECT_VIEWED, source=SOURCE, action="list projects", result="OK",
            payload={
                "count": len(projects),
                "source": source,
                "source_path": source_path,
                "projects": [getattr(p, "id", None) or p.name for p in projects],
            },
        )
    return {
        "ok": True, "count": len(projects),
        "projects": [p.to_dict() for p in projects],
        "source": source, "source_path": source_path,
        "examples_dir": source_path,  # 兼容 Phase 5A 输出键
        "event_seq": ev.seq,
    }


def cmd_project_show(ctx: FactoryContext, args: Any) -> dict:
    """factory project show <name> — 项目详情: 技术栈/状态/运行偏好/Agent/技能/工作流。

    数据源 (Phase 6A 增强): managed projects 目录优先, examples 兜底 (workspace
    是上层组织单位); 详情含 ProjectDef 增强字段 (status/runtime_preferences)。
    退出码: 7 项目不存在; 1 配置解析/校验失败; 0 成功。只读 (ADR-0013)。
    """
    examples_dir = default_examples_dir()
    src = resolve_projects_root(ctx.root, args.name, examples_dir)
    if src is None:
        raise CliError(
            f"project not found: {args.name} "
            f"(no project.yaml in workspace projects or examples)",
            exit_code=7,
        )
    try:
        config = load_project(src, args.name)
    except ProjectLoadError as exc:
        raise CliError(str(exc), exit_code=1) from exc
    if config is None:  # resolve 已确认 project.yaml 存在, 理论不可达
        raise CliError(f"project not found: {args.name}", exit_code=7)
    with ctx.logger_scope() as logger:
        ev = logger.record(
            EventType.PROJECT_VIEWED, source=SOURCE, project_id=config.project.name,
            action="show project", result="OK",
            payload={
                "project": config.project.name,
                "language": config.project.language,
                "status": config.project.status,
                "agents": len(config.agents),
                "skills": len(config.skills),
                "workflows": len(config.workflows),
            },
        )
    return {
        "ok": True,
        "project": config.project.to_dict(),
        "agents": [a.to_dict() for a in config.agents],
        "skills": [s.to_dict() for s in config.skills],
        "workflows": [w.to_dict() for w in config.workflows],
        "examples_dir": str(src),
        "event_seq": ev.seq,
    }
