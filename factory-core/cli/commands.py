"""cli/commands.py — 命令处理器 (薄层, 无 argparse 依赖, 可直接单测)。

铁律 (cli-design §1.3 + phase2 指令): 每个命令的唯一副作用是发布事件;
业务状态 (任务文件) 由命令先落地, 再发事件记录该行为。读命令也发事件
(task.viewed / system.logs_viewed / system.status_viewed) — phase2 指令
"所有 CLI 行为必须产生 Event" 优先于 cli-design "读命令不发事件" (ADR-0002)。

每个处理器返回 dict (CLI --json 直接输出; 人类可读由 main 格式化)。
"""

from __future__ import annotations

import os
from collections import Counter
from functools import partial
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

from git.client import GitClient
from git.service import GitChangeStore, GitService

from change.service import ChangeService, ChangeStore  # Phase 6D (ADR-0019)

from changeflow.engine import ChangeWorkflowEngine  # Phase 6E (ADR-0020)
from changeflow.events import record_change_trigger_viewed  # Phase 6E (ADR-0020)
from changeflow.models import ChangeTrigger  # Phase 6E (ADR-0020)
from changeflow.triggers import (  # Phase 6E (ADR-0020)
    ChangeTriggerExistsError,
    ChangeTriggerRegistry,
)

from understanding.events import record_understanding_viewed  # Phase 7 (ADR-0021)
from understanding.service import UnderstandingError, UnderstandingService  # Phase 7 (ADR-0021)

from metrics.collectors import MetricsCollector
from metrics.workspace import WorkspaceCollector

from project.loader import (
    ProjectLoadError,
    default_examples_dir,
    discover_projects,
    load_project,
)

from workspace.loader import load_project_definition, resolve_projects_root
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
    """factory event logs — 事件日志查询 (倒序, 可过滤), 发 system.logs_viewed;
    --workspace → 跨项目事件时间线 (全量最近事件, 含 project 列), 发 workspace.events.viewed。

    workspace 时间线 = EventStore.recent 全量倒序 (跨项目, 不做 project 过滤),
    project_id 为空的事件 (全局/未归属) 原样展示 — 事件时间线的完整投影。
    """
    limit = args.limit or 20
    workspace = getattr(args, "workspace", False)
    with ctx.logger_scope() as logger:
        if workspace:
            events = logger.store.recent(limit)  # 跨项目: 按 seq 倒序
            ev = logger.record(
                EventType.WORKSPACE_EVENTS_VIEWED, source=SOURCE,
                action="view workspace timeline", result="OK",
                payload={"limit": limit, "count": len(events)},
            )
        else:
            events = logger.store.query(project_id=args.project, task_id=args.task)
            events = events[-limit:][::-1]
            ev = logger.record(
                EventType.SYSTEM_LOGS_VIEWED, source=SOURCE, action="view event logs", result="OK",
                payload={"limit": limit, "count": len(events), "project": args.project, "task": args.task},
            )
    return {
        "ok": True,
        "workspace": workspace,
        "count": len(events),
        "events": [e.model_dump(mode="json") for e in events],
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

    Phase 8B-1 Provider 集成 (ADR-0023, 可选注入): 装配 execute_workflow 时经
    context 传递 provider 选择 (Executor 注入模式, Phase 6E) — 项目配置选中
    provider 时, adapters 参数注入 ProviderCarrierAdapter 载波映射 (引擎创建的
    每次执行在派发点注入 input.provider_id + 发 provider.* 事件); 无 provider
    配置 → adapters=None → 既有 --auto 行为逐位不变。
    """
    task = ctx.open_task_store().get(args.task_id)
    if task is None:
        raise CliError(f"task not found: {args.task_id}", exit_code=7)
    with ctx.logger_scope() as logger:
        provider_context = _provider_context_from_selection(
            _resolve_provider_selection(ctx, task=task)
        )
        outcome = run_orchestration(
            args.task_id,
            workflow_store=WorkflowStore(ctx.workflows_dir),
            task_store=ctx.open_task_store(),
            agent_store=ctx.open_agent_store(),
            assignment_store=_open_assignment_store(ctx),
            runtime_store=_open_runtime_store(ctx),
            logger=logger,
            adapters=(
                _provider_carrier_adapters(ctx, provider_context, logger)
                if provider_context is not None else None
            ),
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


# ------------------------------------------------------------------ provider 子命令 (Phase 8A, ADR-0022 / 8B-2, ADR-0024)

PROVIDER_SMOKE_INSTRUCTION = "Reply with exactly: OK"  # provider test 默认冒烟提示词


def _open_provider_store(ctx: FactoryContext):
    """装配 ProviderStore (路径 = <root>/providers/catalog.json — 独立数据空间,
    与 runtime catalog (runtimes/catalog.json) / 实例库 (runtimes/runtimes.json)
    完全分离; 目录由首次原子写自动创建)。

    延迟导入 providers.store: 删除 providers 不影响本模块加载 (Removal Isolation
    — 核心命令不依赖 Provider 层, phase8a-status.md 冻结约束)。
    """
    from providers.store import ProviderStore

    return ProviderStore(ctx.root / "providers")


def _open_provider_usage_store(ctx: FactoryContext):
    """装配 UsageStore (路径 = <root>/providers/usage.json — 独立数据空间,
    与 Provider 定义 catalog.json 同目录不同文件, phase8b2-plan.md §7)。

    延迟导入 providers.usage: 删除 providers 不影响本模块加载 (Removal Isolation)。
    """
    from providers.usage import UsageStore

    return UsageStore(ctx.root / "providers")


def _parse_provider_status(value: str | None):
    if value is None:
        return None
    from providers.models import ProviderStatus

    try:
        return ProviderStatus.parse(value)
    except ValueError as exc:
        raise CliError(str(exc), exit_code=2) from exc


def cmd_provider_list(ctx: FactoryContext, args: Any) -> dict:
    """factory provider list — Provider 目录列表 (默认定义基线 + 注册定义, 可过滤),
    发 provider.viewed; 结果含 default 标记。"""
    from providers.registry import ProviderRegistry

    status = _parse_provider_status(args.status)
    with ctx.logger_scope() as logger:
        registry = ProviderRegistry(_open_provider_store(ctx), logger=logger)
        providers = registry.list(type=args.type, status=status)
        default = registry.default()
        default_id = default.id if default is not None else None
        ev = logger.record(
            EventType.PROVIDER_VIEWED, source=SOURCE, action="list providers", result="OK",
            payload={"count": len(providers), "type": args.type,
                     "status": args.status, "default": default_id},
        )
    return {
        "ok": True, "count": len(providers),
        "providers": [p.to_dict() for p in providers],
        "default": default_id, "event_seq": ev.seq,
    }


def cmd_provider_show(ctx: FactoryContext, args: Any) -> dict:
    """factory provider show <id> — Provider 定义详情 (默认定义或已注册定义, 只读),
    发 provider.viewed; 未找到 → 退出码 7。"""
    from providers.registry import ProviderRegistry

    with ctx.logger_scope() as logger:
        registry = ProviderRegistry(_open_provider_store(ctx), logger=logger)
        definition = registry.get(args.provider_id)
        if definition is None:
            raise CliError(f"provider not found: {args.provider_id}", exit_code=7)
        default = registry.default()
        is_default = default is not None and default.id == definition.id
        ev = logger.record(
            EventType.PROVIDER_VIEWED, source=SOURCE, action="show provider", result="OK",
            payload={
                "provider_id": definition.id,
                "type": definition.type,
                "version": definition.version,
                "status": definition.status.value,
                "default": is_default,
            },
        )
    return {
        "ok": True, "provider": definition.to_dict(),
        "default": is_default, "event_seq": ev.seq,
    }


def cmd_provider_test(ctx: FactoryContext, args: Any) -> dict:
    """factory provider test <id> — smoke test: 最小生成调用 (adapter.generate),
    发 provider.selected → provider.execution.started → completed|failed →
    provider.viewed。

    前置: provider 定义须在目录合并视图中 (默认 hermes 常驻; 自定义经注册);
    已注册但无内置实现 → 配置缺口 rc 1 (同 cmd_runtime_test 契约)。
    退出码: 0 smoke SUCCESS / 1 smoke FAILED (provider 不健康) 或配置缺口 /
    7 provider 未找到。
    副作用边界: smoke 为临时调用 — 不落任何 Provider 状态 (目录零残留);
    Adapter 不写 Event (ADR-0006 解耦铁律); 本命令的事件全部经 EventLogger
    (ADR-0002: 所有 CLI 行为必须产生 Event)。
    """
    from providers.adapters import BUILTIN_PROVIDER_ADAPTERS
    from providers.models import ProviderRequest, ProviderResponse
    from providers.registry import ProviderRegistry

    with ctx.logger_scope() as logger:
        registry = ProviderRegistry(_open_provider_store(ctx), logger=logger)
        definition = registry.get(args.provider_id)
        if definition is None:
            raise CliError(f"provider not found: {args.provider_id}", exit_code=7)
        adapter = BUILTIN_PROVIDER_ADAPTERS.get(args.provider_id)
        if adapter is None:
            raise CliError(
                f"no adapter implementation for provider: {args.provider_id} "
                f"(registered but not built-in)",
                exit_code=1,
            )
        model = args.model or (definition.models[0] if definition.models else None)
        request = ProviderRequest(
            provider_id=args.provider_id,
            prompt=args.prompt or PROVIDER_SMOKE_INSTRUCTION,
            model=model,
            metadata={"smoke": True, "task_id": "SMOKE"},
        )
        # 事件序 (provider.* 生命周期): selected → execution.started →
        # completed|failed → viewed (审计)
        logger.record(
            EventType.PROVIDER_SELECTED, source=SOURCE, stage="selected",
            action="select provider", result="OK",
            payload={"provider_id": args.provider_id, "model": model},
        )
        logger.record(
            EventType.PROVIDER_EXECUTION_STARTED, source=SOURCE, stage="running",
            action="execute provider", result="OK",
            payload={"provider_id": args.provider_id, "model": model},
        )
        try:
            response = adapter.generate(request)
        except Exception as exc:  # 意外异常 → 稳定响应 (不抛, 同 ADR-0007 决策 4)
            response = ProviderResponse(
                provider_id=args.provider_id, model=model,
                error=f"{type(exc).__name__}: {exc}",
            )
        if response.ok:
            logger.record(
                EventType.PROVIDER_EXECUTION_COMPLETED, source=SOURCE, stage="completed",
                action="execute provider", result="OK",
                payload={"provider_id": args.provider_id, "model": response.model,
                         "usage": response.usage},
            )
        else:
            logger.record(
                EventType.PROVIDER_EXECUTION_FAILED, source=SOURCE, stage="failed",
                action="execute provider", result="ERROR",
                payload={"provider_id": args.provider_id, "model": response.model,
                         "error": response.error},
            )
        ev = logger.record(
            EventType.PROVIDER_VIEWED, source=SOURCE, action="test provider", result="OK",
            payload={"provider_id": args.provider_id, "model": response.model,
                     "smoke_status": "SUCCESS" if response.ok else "FAILED",
                     "error": response.error},
        )
    data = {
        "ok": response.ok,
        "provider": args.provider_id,
        "status": "SUCCESS" if response.ok else "FAILED",
        "model": response.model,
        "response": response.to_dict(),
        "events": [
            "provider.selected", "provider.execution.started",
            "provider.execution.completed" if response.ok else "provider.execution.failed",
            "provider.viewed",
        ],
        "event_seq": ev.seq,
    }
    if not response.ok:
        data["exit_code"] = 1  # smoke FAILED = provider 不健康 → rc 1
    return data


def cmd_provider_usage(ctx: FactoryContext, args: Any) -> dict:
    """factory provider usage [--provider X] [--period day|week|all] — 使用记录
    (估算成本, 非真实计费), 发 provider.viewed (只读审计, ADR-0002)。

    数据源 = <root>/providers/usage.json (UsageStore 独立数据空间); 记录按
    recorded_at 升序; --provider 过滤 provider 维度; --period 过滤聚合周期
    (day=今天 / week=最近 7 天 / all=全部)。
    """
    from providers.usage import filter_by_period

    with ctx.logger_scope() as logger:
        store = _open_provider_usage_store(ctx)
        records = store.list()
        if args.provider is not None:
            records = [r for r in records if r.provider_id == args.provider]
        records = filter_by_period(records, args.period)
        ev = logger.record(
            EventType.PROVIDER_VIEWED, source=SOURCE, action="list provider usage", result="OK",
            payload={
                "count": len(records), "provider": args.provider, "period": args.period,
                "total_cost": round(sum(r.estimated_cost for r in records), 6),
            },
        )
    return {
        "ok": True, "count": len(records),
        "records": [r.to_dict() for r in records],
        "provider": args.provider, "period": args.period, "event_seq": ev.seq,
    }


def cmd_provider_stats(ctx: FactoryContext, args: Any) -> dict:
    """factory provider stats [--provider X] [--period day|week|all] — 性能聚合
    (provider/model/version/period 维度: calls/success_rate/avg_latency/total_cost),
    发 provider.viewed (只读审计)。

    聚合从 usage 记录计算 (不落库, phase8b2-plan.md §7 存储边界); 统计口径见
    providers/usage.py stats_from_usage docstring。
    """
    from providers.usage import stats_from_usage

    with ctx.logger_scope() as logger:
        store = _open_provider_usage_store(ctx)
        stats = stats_from_usage(store.list(), provider_id=args.provider, period=args.period)
        ev = logger.record(
            EventType.PROVIDER_VIEWED, source=SOURCE, action="view provider stats", result="OK",
            payload={
                "count": len(stats), "provider": args.provider, "period": args.period,
                "total_cost": round(sum(s.total_cost for s in stats), 6),
            },
        )
    return {
        "ok": True, "count": len(stats),
        "stats": [s.to_dict() for s in stats],
        "provider": args.provider, "period": args.period, "event_seq": ev.seq,
    }


def cmd_provider_compare(ctx: FactoryContext, args: Any) -> dict:
    """factory provider compare <a> <b> — 能力/成本对比 (估算模型, 非真实计费),
    发 provider.viewed; 任一未找到 → 退出码 7。

    对比列: 定义 (capabilities/models/type) + 能力矩阵 (默认基线, 无 → None) +
    成本模式 (默认基线, 无 → None) + 估算调用成本 (estimate_call_cost 归一)。
    """
    from providers.costs import estimate_call_cost
    from providers.definitions import DEFAULT_CAPABILITY_PROFILES, DEFAULT_COST_MODELS
    from providers.registry import ProviderRegistry

    with ctx.logger_scope() as logger:
        registry = ProviderRegistry(_open_provider_store(ctx), logger=logger)
        a = registry.get(args.a)
        if a is None:
            raise CliError(f"provider not found: {args.a}", exit_code=7)
        b = registry.get(args.b)
        if b is None:
            raise CliError(f"provider not found: {args.b}", exit_code=7)
        pa = DEFAULT_CAPABILITY_PROFILES.get(a.id)
        pb = DEFAULT_CAPABILITY_PROFILES.get(b.id)
        ca = DEFAULT_COST_MODELS.get(a.id)
        cb = DEFAULT_COST_MODELS.get(b.id)
        ev = logger.record(
            EventType.PROVIDER_VIEWED, source=SOURCE, action="compare providers", result="OK",
            payload={
                "a": a.id, "b": b.id,
                "a_estimated_cost": estimate_call_cost(ca),
                "b_estimated_cost": estimate_call_cost(cb),
            },
        )
    return {
        "ok": True,
        "providers": [a.to_dict(), b.to_dict()],
        "capability": {
            a.id: pa.to_dict() if pa is not None else None,
            b.id: pb.to_dict() if pb is not None else None,
        },
        "cost": {
            a.id: ca.to_dict() if ca is not None else None,
            b.id: cb.to_dict() if cb is not None else None,
        },
        "estimated_call_cost": {
            a.id: estimate_call_cost(ca),
            b.id: estimate_call_cost(cb),
        },
        "event_seq": ev.seq,
    }


def cmd_provider_recommend(ctx: FactoryContext, args: Any) -> dict:
    """factory provider recommend --task <type> [--capabilities a,b] [--min-quality F]
    [--budget F] — TaskRequirement → 能力匹配 + 成本感知 + 性能感知推荐
    (只推荐不自动切换), 发 provider.viewed + provider.selected (source=recommendation)。

    选择流程 (phase8b2-plan.md §4 + phase8b3-status.md §3): 能力过滤 (quality >=
    min_quality, budget 上限) → 配置优先 (默认基线外无项目配置; 未来接
    Project>Agent>Runtime>Default 链) → 三分数加权 (capability 0.4 + cost 0.3 +
    performance 0.3) → 成本感知排序 (token/request/time/free 模式归一估算,
    同成本性能分降序)。Phase 8B-3 (ADR-0025): 注入 UsageStore 实测统计
    (stats_by_provider 合并桶) — 有 usage 数据时 performance_score 反映实测
    表现, 无数据 → 0.5 中性 (8B-2 兼容)。推荐不修改任何配置 (评审调整 4);
    无通过候选 → 推荐为空 (rc 0)。
    """
    from providers.definitions import DEFAULT_CAPABILITY_PROFILES, DEFAULT_COST_MODELS
    from providers.models import TaskRequirement
    from providers.registry import ProviderRegistry
    from providers.selector import CostAwareSelector
    from providers.usage import stats_by_provider

    capabilities = [c.strip() for c in args.capabilities.split(",") if c.strip()]
    with ctx.logger_scope() as logger:
        registry = ProviderRegistry(_open_provider_store(ctx), logger=logger)
        selector = CostAwareSelector(
            registry, DEFAULT_CAPABILITY_PROFILES, DEFAULT_COST_MODELS,
            usage_stats=stats_by_provider(
                _open_provider_usage_store(ctx).list(), period="all",
            ),
        )
        requirement = TaskRequirement(
            task_type=args.task,
            required_capabilities=capabilities,
            min_quality=args.min_quality or 0.0,
            budget=args.budget,
        )
        recommendation = selector.recommend(requirement)
        ev = logger.record(
            EventType.PROVIDER_VIEWED, source=SOURCE, action="recommend provider", result="OK",
            payload={
                "task_type": args.task,
                "capabilities": capabilities,
                "recommended": recommendation.provider_id if recommendation is not None else None,
            },
        )
        if recommendation is not None:
            # 推荐审计: provider.selected (source=recommendation) — 只审计,
            # 不自动切换任何配置 (评审调整 4)
            logger.record(
                EventType.PROVIDER_SELECTED, source=SOURCE, stage="recommended",
                action="recommend provider", result="OK",
                payload={
                    "provider_id": recommendation.provider_id,
                    "source": "recommendation",
                    "score": recommendation.score,
                    "estimated_cost": recommendation.estimated_cost,
                },
            )
    return {
        "ok": True,
        "task": args.task,
        "recommended": recommendation.to_dict() if recommendation is not None else None,
        "event_seq": ev.seq,
    }


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


def _open_execution_service(
    ctx: FactoryContext, logger, provider_context=None,
) -> ExecutionService:
    """装配 ExecutionService: RuntimeStore + Registry (同事件库) + 内置 Adapter + Workflow 联动。

    内置 Adapter (BUILTIN_ADAPTERS: echo) 提供实现; runtime 身份 (RuntimeInfo) 须
    经 `factory runtime add` 显式注册 — registry 是派发解析的唯一事实源 (ADR-0007 决策 3)。
    Workflow 联动经 _open_workflow_engine (complete_step/fail_workflow 不需 runtime_store)。

    Phase 8B-1 (ADR-0023): provider_context 非 None 时全部内置 Adapter 经
    ProviderCarrierAdapter 载波包装 (派发时注入 input.provider_id + 发 provider.*
    审计事件); None → 原装配 (旧链路零变化)。
    """
    store = _open_runtime_store(ctx)
    registry = RuntimeRegistry(store, logger=logger)
    engine = _open_workflow_engine(ctx, logger)
    adapters = BUILTIN_ADAPTERS
    if provider_context is not None:
        adapters = _provider_carrier_adapters(ctx, provider_context, logger)
    return ExecutionService(
        store, registry, adapters=adapters, logger=logger, workflow_engine=engine,
    )


# ------------------------------------------------------------------ Phase 8B-1: Provider 选择 + 执行集成 (ADR-0023)


def _project_runtime_preferences(ctx: FactoryContext, task) -> dict | None:
    """project.yaml runtime_preferences (Phase 6A 字段, 8B-1 生效); 任务/项目
    缺失或配置损坏 → None (选择链降级, 不破坏执行)。"""
    if task is None or not getattr(task, "project", None):
        return None
    try:
        definition = load_project_definition(ctx.root, task.project)
    except WorkspaceConfigError:
        return None
    if definition is None:
        return None
    prefs = getattr(definition, "runtime_preferences", None)
    return prefs if isinstance(prefs, dict) else None


def _runtime_definition(ctx: FactoryContext, runtime_id: str | None):
    """Runtime 目录定义 (runtime_default 层数据源); 未指定/未注册 → None (降级)。"""
    if not runtime_id:
        return None
    return RuntimeCatalog(_open_catalog_store(ctx)).get(runtime_id)


def _resolve_provider_selection(
    ctx: FactoryContext,
    *,
    task,
    explicit: str | None = None,
    preferred_runtime: str | None = None,
):
    """四层优先级选择 (Phase 8B-1, ADR-0023): explicit > 项目 > Agent > Runtime > Default。

    - 无任何 provider 配置 → None (旧链路行为不变, 零 provider 事件)。
    - 显式 --provider 未注册/禁用 → CliError rc 7 (同 cmd_provider_test 契约,
      在 CLI 层转换 — 选择层抛 ProviderNotFoundError)。
    - Agent 层: Agent 模型无 runtime_preferences 字段 (角色级偏好留待未来),
      恒 None — 选择链自动降级到 Runtime/Default 层。
    - Removal Isolation: 延迟导入 providers + ImportError 兜底 → 无 providers
      层时等同无配置, Factory 正常。
    """
    try:
        from providers.config import parse_runtime_preferences, runtime_default_provider
        from providers.registry import ProviderNotFoundError, ProviderRegistry
        from providers.selector import ProviderSelector
    except ImportError:
        return None  # Removal Isolation: 无 providers 层 → 旧链路
    project_prefs = _project_runtime_preferences(ctx, task)
    task_type = getattr(task, "type", None) or "feature"
    prefs = parse_runtime_preferences(project_prefs, task_type)
    registry = ProviderRegistry(_open_provider_store(ctx))
    default_def = registry.default()
    selector = ProviderSelector(registry)
    try:
        return selector.resolve(
            task_type=task_type,
            explicit=explicit,
            project_prefs=project_prefs,
            agent_prefs=None,  # Agent 角色级偏好 (模型无此字段, 未来扩展)
            runtime_default=runtime_default_provider(
                _runtime_definition(ctx, preferred_runtime or prefs["runtime"])
            ),
            registry_default=default_def.id if default_def is not None else None,
        )
    except ProviderNotFoundError as exc:
        raise CliError(str(exc), exit_code=7) from exc


def _provider_carrier_adapters(ctx: FactoryContext, provider_context, logger) -> dict:
    """装配 Provider 载波 Adapter 映射 (Phase 8B-1/8B-3); 仅 provider_context
    非 None 时调用。

    provider_context 非 None ⇒ providers 层必然可导入 (选择已成功) — 延迟导入
    保持 Removal Isolation (删除 providers 不影响其他命令)。

    Phase 8B-3 (ADR-0025): 注入 usage_store + DEFAULT_COST_MODELS — 每次
    执行自动落库 usage 记录 (provider.usage.recorded 事件, 终态后追加);
    estimated_cost 用默认成本基线估算 (非真实计费)。
    """
    from providers.definitions import DEFAULT_COST_MODELS
    from providers.integration import wrap_adapters_with_provider

    return wrap_adapters_with_provider(
        BUILTIN_ADAPTERS, provider_context, logger=logger,
        usage_store=_open_provider_usage_store(ctx),
        cost_models=DEFAULT_COST_MODELS,
    )


def _provider_context_from_selection(selection):
    """ProviderSelection → ProviderContext (延迟导入, 供装配点消费)。

    Removal Isolation: providers 层不可导入 → None (等同无配置, 旧链路 —
    与 _resolve_provider_selection 的 ImportError 兜底对称; --auto 装配点
    对 None 直接跳过载波)。
    """
    try:
        from providers.integration import provider_context_from_selection
    except ImportError:
        return None

    return provider_context_from_selection(selection)


def _resolve_execution_provider(
    ctx: FactoryContext, logger, execution_id: str, explicit: str | None = None,
):
    """执行前 Provider 选择 + input 携带 (Phase 8B-1, ADR-0023)。

    - 执行请求不存在 → ExecutionNotFoundError (rc 7, 同 runner 契约)。
    - 无 provider 配置 → None (旧链路: 零 provider 事件、input 零注入)。
    - 选中 → 选择结果经 ExecutionRequest.input dict 携带 provider_id (调用方
      构造, 不改模型; HermesRuntimeAdapter 忽略未知键, 兼容) + 返回
      ProviderContext (ExecutionService 载波装配 — 派发点发 provider.selected →
      provider.execution.started → completed|failed, payload 含 execution_id)。
    - 仅 PENDING 请求做 input 携带 (非 PENDING 由 runner 拒执行 rc 1, 不改写
      已落盘请求)。
    """
    store = _open_runtime_store(ctx)
    request = store.get_execution(execution_id)
    if request is None:
        raise ExecutionNotFoundError(f"execution not found: {execution_id}")
    task = ctx.open_task_store().get(request.task_id) if request.task_id else None
    selection = _resolve_provider_selection(
        ctx, task=task, explicit=explicit, preferred_runtime=request.runtime_id,
    )
    if selection is None:
        return None
    if request.status is ExecutionStatus.PENDING:
        request = request.model_copy(update={
            "input": {**request.input, "provider_id": selection.provider_id},
        })
        store.save_execution(request)
    return _provider_context_from_selection(selection)


def _exec_cli_error(exc: Exception) -> CliError:
    """execution 域异常 → CliError (cli-design §5: 7 未找到 / 1 状态冲突)。"""
    if isinstance(exc, (ExecutionNotFoundError, RuntimeNotFoundError)):
        return CliError(str(exc), exit_code=7)
    return CliError(str(exc), exit_code=1)


def cmd_execution_run(ctx: FactoryContext, args: Any) -> dict:
    """factory execution run EXECUTION_ID [--provider ID] — 执行 pending execution
    (发 execution.started/completed/failed)。

    退出码: 0 成功 (含执行结果为 FAILED 的业务失败 — run 命令本身成功);
    7 执行/runtime 未找到 / --provider 未注册; 1 状态冲突 (非 PENDING /
    无可用 runtime / 无 Adapter 实现)。

    Phase 8B-1 Provider 集成 (ADR-0023): --provider 显式指定或项目配置
    (runtime_preferences.<task_type>.provider) 选中后, 选择结果经
    ExecutionRequest.input dict 携带 provider_id (调用方构造, 不改模型 —
    HermesRuntimeAdapter 忽略未知键, 兼容), 执行派发点发 provider.selected →
    provider.execution.started → completed|failed 审计事件 (payload 含
    execution_id); 无 provider 配置 → 旧链路零变化。

    Phase 6D 快照钩子 (ADR-0019 决策 7): 执行完成后在 CLI 层关联 Execution Git
    Snapshot (ChangeStore, <root>/change/snapshots.json) — 不改 execution 核心;
    失败安全: git 查询/存储异常 → snapshot=None, run 结果不受影响 (快照是审计增强)。
    """
    with ctx.logger_scope() as logger:
        try:
            provider_context = _resolve_execution_provider(
                ctx, logger, args.execution_id,
                explicit=getattr(args, "provider", None),
            )
            service = _open_execution_service(ctx, logger, provider_context=provider_context)
            outcome = service.run(args.execution_id)
        except (ExecutionRunnerError, ExecutionDispatcherError, RuntimeNotFoundError) as exc:
            raise _exec_cli_error(exc) from exc
    # 快照钩子 (CLI 层, 执行核心零改动): 非 git 目录 → after_commit=None/files=[]
    # 照常记录\"执行发生在无仓库环境\"的事实; 任何异常 → 快照 None (不破坏 run)。
    snapshot = None
    try:
        change = ChangeService(
            client=GitClient(str(ctx.root)),
            change_store=ChangeStore(ctx.root / "change"),
            git_changes_store=GitChangeStore(ctx.root / "git"),
        )
        snapshot = change.snapshot_execution(
            execution_id=args.execution_id,
            task_id=outcome.request.task_id,
        )
    except Exception:
        snapshot = None  # 失败安全: 快照是审计增强, 不因 git 问题破坏 run
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
        "snapshot": snapshot.to_dict() if snapshot is not None else None,
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

def _open_git_services(ctx: FactoryContext, projects: list) -> list[GitService]:
    """按项目装配 GitService 列表 (Git View 数据源, Phase 6C, ADR-0018)。

    只取有 repository 字段的项目 (本地路径或远程 URL 均可 — GitClient 失败
    安全, 非 git/远程 URL → error 上下文照常入表); 无 repository 的项目跳过。
    store = <root>/git/changes.json (关联持久化, 不依赖 cwd)。
    """
    services: list[GitService] = []
    for p in projects:
        repo = (getattr(p, "repository", "") or "").strip()
        if not repo:
            continue
        services.append(GitService(
            GitClient(os.path.expanduser(repo)),
            project_id=getattr(p, "id", None) or getattr(p, "name", None),
            changes_store=GitChangeStore(ctx.root / "git"),
        ))
    return services


def cmd_dashboard(ctx: FactoryContext, args: Any) -> dict:
    """factory dashboard — 只读控制台总览 (Rich 视图), 发 dashboard.viewed;
    --workspace → Workspace Summary (跨项目运营视图组), 发 workspace.dashboard.viewed。

    只读铁律 (phase4c4-status.md / ADR-0017): 收集器只调用各 store 读接口,
    本命令唯一的副作用是审计事件 (ADR-0002: 所有 CLI 行为必须产生 Event)。
    非法 --view → 用法错误 (退出码 2)。
    """
    workspace = getattr(args, "workspace", False)
    view = args.view or ("workspace" if workspace else "all")
    if view != "all" and view not in DASHBOARD_VIEWS:
        raise CliError(
            f"invalid view: {view!r} (expected one of: all, {', '.join(DASHBOARD_VIEWS)})",
            exit_code=2,
        )
    # workspace 专属视图 (workspace 组/agents_utilization/runtime_usage/workspace_events)
    # 需要 collector workspace 模式聚合; 经 --view 单独指定时自动启用 (数据完整),
    # 但事件类型仍按 --workspace 标志区分 (只读审计, ADR-0017 决策 4)。
    workspace_views = {"workspace", "agents_utilization", "runtime_usage", "workspace_events"}
    with ctx.logger_scope() as logger:
        # Phase 6A Projects View 数据源: workspace 项目定义 (无 workspace/损坏 →
        # 空列表, Dashboard 永不因 workspace 配置问题失败 — 只读兜底)。用
        # load_workspace() 而非 list_projects(): 后者在无 workspace.yaml 时自动
        # 发现 (managed ∪ examples), 会把内置示例项目泄漏进 workspace 聚合 —
        # 无 workspace 时项目集应完全由任务/事件数据推导 (ADR-0017 决策 6)。
        try:
            ws_projects = _open_workspace_manager(ctx).load_workspace().projects
        except (WorkspaceNotFoundError, WorkspaceConfigError):
            ws_projects = []
        # Phase 6C Git View: 仅 --view git 聚合 (include_git 默认关闭, 既有
        # dashboard 行为/成本不变; 数据源 = 项目 repository 的 GitService 列表)。
        git_services = _open_git_services(ctx, ws_projects) if view == "git" else []
        # Phase 6D Change View: 仅 --view change 聚合 (include_change 默认关闭,
        # 数据源 = ChangeStore <root>/change/snapshots.json + change.validation 事件)。
        change_store = ChangeStore(ctx.root / "change") if view == "change" else None
        # Phase 6E Change Flow View: 仅 --view changeflow 聚合 (include_changeflow
        # 默认关闭, 数据源 = ChangeTriggerRegistry <root>/changeflow/triggers.json
        # + change.trigger.evaluated / change.workflow.started|completed 事件)。
        change_trigger_registry = (
            ChangeTriggerRegistry(ctx.root / "changeflow") if view == "changeflow" else None
        )
        # Phase 7 Understanding View: 仅 --view understanding 聚合
        # (include_understanding 默认关闭, 数据源 = workspace 项目 repository
        # 本地目录, 每项目跑一次只读理解分析; 失败安全 — 缺失/非本地目录跳过)。
        understanding_paths: list[tuple[str, str]] = []
        if view == "understanding":
            for p in ws_projects:
                repo = (getattr(p, "repository", "") or "").strip()
                if not repo:
                    continue
                expanded = os.path.expanduser(repo)
                if os.path.isdir(expanded):
                    understanding_paths.append((p.id, expanded))
        # Phase 8A Provider View: 仅 --view provider 聚合 (include_provider 默认
        # 关闭, 数据源 = ProviderRegistry <root>/providers 只读合并视图: 默认
        # 定义基线 hermes + 已持久化定义)。延迟导入 providers (Removal Isolation
        # — 删除 providers 不影响本模块加载, phase8a-status.md 冻结约束)。
        provider_registry = None
        if view == "provider":
            from providers.registry import ProviderRegistry

            provider_registry = ProviderRegistry(_open_provider_store(ctx))
        # Phase 9A Product View: 仅 --view product 聚合 (include_product 默认
        # 关闭, 数据源 = ProductStore 独立空间 <root>/product/ 只读:
        # ideas/artifacts/approvals/workflows)。Phase 9d Lifecycle View: 同数据源
        # (include_lifecycle 默认关闭, 复用 ProductStore 读接口聚合生命周期)。
        # 延迟导入 product (Removal Isolation — 删除 product 不影响本模块加载,
        # 同 provider 模式; 显式 --view lifecycle 时装配点响亮 rc 1)。
        product_store = None
        if view in ("product", "lifecycle"):
            from product.store import ProductStore

            product_store = ProductStore(ctx.root / "product")
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
            include_workspace=workspace or view in workspace_views,
            git_services=git_services,
            include_git=view == "git",
            change_store=change_store,
            include_change=view == "change",
            change_trigger_registry=change_trigger_registry,
            include_changeflow=view == "changeflow",
            understanding_paths=understanding_paths,
            include_understanding=view == "understanding",
            provider_registry=provider_registry,
            include_provider=view == "provider",
            product_store=product_store,
            include_product=view == "product",
            include_lifecycle=view == "lifecycle",  # Phase 9d (ADR-0029)
        )
        snapshot = collector.collect()
        ev = logger.record(
            EventType.WORKSPACE_DASHBOARD_VIEWED if workspace else EventType.DASHBOARD_VIEWED,
            source=SOURCE, project_id=args.project,
            stage="viewed",
            action="view workspace dashboard" if workspace else "view dashboard",
            result="OK",
            payload={
                "view": view,
                "workspace": workspace,
                "tasks_total": snapshot.tasks.total,
                "agents_total": snapshot.agents.total,
                "agents_utilized": snapshot.agent_utilization.total,
                "workflow_runs": snapshot.workflows.runs_total,
                "executions_total": snapshot.executions.total,
                "execution_success": snapshot.executions.success,
                "execution_failed": snapshot.executions.failed,
                "runtimes_used": snapshot.runtime_usage.total,
                "checkpoints_total": snapshot.checkpoints.total,
                "catalog_definitions": snapshot.catalog.total,
                "projects_total": snapshot.projects.total,
                "events_total": snapshot.metrics.event_count,
                "git_repositories": snapshot.git.total,   # Phase 6C (ADR-0018)
                "git_changes": len(snapshot.git.changes),
                "git_commits": len(snapshot.git.commits),
                "change_snapshots": snapshot.change.total,  # Phase 6D (ADR-0019)
                "change_validations": snapshot.change.validation_total,
                "changeflow_triggers": snapshot.changeflow.trigger_total,  # Phase 6E (ADR-0020)
                "changeflow_evaluations": snapshot.changeflow.evaluation_total,
                "changeflow_links": snapshot.changeflow.workflow_links_total,
                "understanding_projects": snapshot.understanding.total,  # Phase 7 (ADR-0021)
                "providers_total": snapshot.providers.total,  # Phase 8A (ADR-0022)
                "providers_default": snapshot.providers.default,
                "product_ideas": snapshot.product.idea_total,  # Phase 9A (ADR-0026)
                "product_artifacts": snapshot.product.artifact_total,
                "product_approvals_pending": snapshot.product.approval_pending,
                "product_workflows": snapshot.product.workflow_total,
                "lifecycle_total": snapshot.product.lifecycle.lifecycle_total,  # Phase 9d (ADR-0029)
                "lifecycle_paused": snapshot.product.lifecycle.by_status.get("paused", 0),
                "lifecycle_completed": snapshot.product.lifecycle.by_status.get("completed", 0),
            },
        )
    return {
        "ok": True,
        "view": view,
        "workspace": workspace,
        "snapshot": snapshot.to_dict(),
        "event_seq": ev.seq,
    }


# ------------------------------------------------------------------ metrics (Phase 5B, ADR-0015)

def cmd_metrics(ctx: FactoryContext, args: Any) -> dict:
    """factory metrics — 工厂生产指标 (六域 + 失败原因, 只读), 发 metrics.viewed;
    --workspace → 项目对比 (复用 MetricsCollector 每项目聚合), 发 workspace.metrics.viewed。

    只读铁律 (phase5b-status.md / ADR-0017): 收集器只调用各 store 读接口
    (query/list/count), 本命令唯一的副作用是审计事件 (ADR-0002: 所有 CLI 行为必须
    产生 Event, 同 dashboard.viewed)。指标纯计算不持久化 (ADR-0015 决策 2)。
    """
    if getattr(args, "workspace", False):
        return _cmd_metrics_workspace(ctx, args)
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


def _cmd_metrics_workspace(ctx: FactoryContext, args: Any) -> dict:
    """metrics --workspace: 项目对比表 (WorkspaceComparison) + workspace.metrics.viewed。

    项目集 = workspace 项目定义 ∪ 任务 project 值 ∪ 事件 project_id 值
    (WorkspaceCollector.comparison 合并推导, 同 Dashboard Projects View 语义);
    每项目行直接复用 MetricsCollector(project_id) 核心计算 (ADR-0017 决策 1),
    汇总行 = 全局聚合。无 workspace/配置损坏 → 缺省推导 (任务/事件维度,
    兼容 Phase 5A 无 workspace 场景, Dashboard 同款只读兜底)。
    """
    try:
        # load_workspace() 而非 list_projects(): 无 workspace.yaml 时后者自动
        # 发现 examples, 会把内置示例项目 (markpad) 泄漏进对比表 — 缺省推导
        # (任务 project ∪ 事件 project_id) 才是无 workspace 的契约 (ADR-0017 决策 6)。
        ws_projects = [p.id for p in _open_workspace_manager(ctx).load_workspace().projects]
    except (WorkspaceNotFoundError, WorkspaceConfigError):
        ws_projects = None
    with ctx.logger_scope() as logger:
        collector = WorkspaceCollector(
            event_store=logger.store,
            task_store=ctx.open_task_store(),
            agent_registry=AgentRegistry(ctx.open_agent_store()),
            workflow_store=WorkflowStore(ctx.workflows_dir),
            runtime_store=_open_runtime_store(ctx),
        )
        comparison = collector.comparison(project_ids=ws_projects)
        t = comparison.totals
        ev = logger.record(
            EventType.WORKSPACE_METRICS_VIEWED, source=SOURCE,
            stage="viewed", action="view workspace metrics", result="OK",
            payload={
                "projects_total": comparison.total,
                "tasks_total": t.tasks_total,
                "tasks_completed": t.tasks_completed,
                "tasks_failed": t.tasks_failed,
                "task_success_rate": t.task_success_rate,
                "executions_total": t.execution_count,
                "executions_success": t.execution_success,
                "executions_failed": t.execution_failed,
                "workflow_runs": t.workflow_runs,
                "validation_rules": t.validation_rules,
                "validation_pass_rate": t.validation_pass_rate,
            },
        )
    return {
        "ok": True,
        "workspace": True,
        "comparison": comparison.to_dict(),
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


# ------------------------------------------------------------------ git 子命令 (Phase 6C, ADR-0018)

_REMOTE_URL_PREFIXES = ("http://", "https://", "git@", "ssh://", "git://")


def _is_remote_url(repository: str) -> bool:
    """repository 是否远程 URL (仅本地路径可读; URL 失败安全转错误)。"""
    return repository.startswith(_REMOTE_URL_PREFIXES)


def _git_resolve_repository(ctx: FactoryContext, args: Any) -> str:
    """解析仓库路径: --repo 显式 > --project 的 project.yaml repository。

    退出码: 2 两者皆缺 (用法); 7 项目不存在; 1 无 repository / 远程 URL。
    """
    repo = getattr(args, "repo", None)
    if repo:
        return os.path.expanduser(repo)
    project_id = getattr(args, "project", None)
    if not project_id:
        raise CliError("specify --project or --repo", exit_code=2)
    definition = load_project_definition(ctx.root, project_id)
    if definition is None:
        raise CliError(f"project not found: {project_id}", exit_code=7)
    if not definition.repository:
        raise CliError(f"project has no repository configured: {project_id}", exit_code=1)
    if _is_remote_url(definition.repository):
        raise CliError(
            f"repository is a remote URL, not a local path: {definition.repository}",
            exit_code=1,
        )
    return os.path.expanduser(definition.repository)


def _open_git_service(ctx: FactoryContext, args: Any) -> GitService:
    """装配 GitService (只读 client + project 维度; store = <root>/git/changes.json)。

    GitChangeStore 显式传路径 (不依赖 cwd); task_store 不装配 — CLI git 命令
    是纯只读查询 (bind_task_change 关联经服务层 API, 任务校验由调用方负责)。
    """
    repository = _git_resolve_repository(ctx, args)
    return GitService(
        GitClient(repository),
        project_id=getattr(args, "project", None),
        changes_store=GitChangeStore(ctx.root / "git"),
    )


def cmd_git_status(ctx: FactoryContext, args: Any) -> dict:
    """factory git status — 仓库状态 (branch/current_commit/changes), 发 git.status.viewed。

    失败安全: 非 git 目录/命令缺失 → status.is_repo=False + error 摘要, 退出码
    仍为 0 (只读查询执行成功, 错误经输出呈现 — phase6c-status.md §失败安全)。
    唯一副作用 = 审计事件 (ADR-0002); Git 零写命令 (只读铁律)。
    """
    with ctx.logger_scope() as logger:
        service = _open_git_service(ctx, args)
        status = service.get_status()
        ev = logger.record(
            EventType.GIT_STATUS_VIEWED, source=SOURCE, project_id=args.project,
            stage="viewed", action="view git status",
            result="OK" if status.is_repo else "ERROR",
            payload={
                "repository": status.repository,
                "branch": status.branch,
                "current_commit": status.current_commit,
                "changes": len(status.changes),
                "is_repo": status.is_repo,
                "error": status.error,
            },
        )
    return {
        "ok": True,
        "status": status.to_dict(),
        "error": status.error,
        "event_seq": ev.seq,
    }


def cmd_git_diff(ctx: FactoryContext, args: Any) -> dict:
    """factory git diff — 工作区变更列表 (逐文件 + 行数 + task 关联), 发 git.change.detected。

    失败安全: 非 git 目录 → changes 空列表, 退出码 0 (错误经 status.error 输出
    由 status 命令呈现; 此处记录 error 字段供审计)。只读 (零写命令)。
    """
    with ctx.logger_scope() as logger:
        service = _open_git_service(ctx, args)
        changes = service.get_changes()
        status = service.get_status()
        ev = logger.record(
            EventType.GIT_CHANGE_DETECTED, source=SOURCE, project_id=args.project,
            stage="detected", action="view git diff", result="OK",
            payload={
                "repository": service.client.repository,
                "count": len(changes),
                "error": status.error,
            },
        )
    return {
        "ok": True,
        "count": len(changes),
        "changes": [c.to_dict() for c in changes],
        "error": status.error,
        "event_seq": ev.seq,
    }


def cmd_git_commits(ctx: FactoryContext, args: Any) -> dict:
    """factory git commits — 提交历史 (hash/message/branch/task), 发 git.commit.viewed。

    失败安全: 非 git 目录/空仓库 → commits 空列表, 退出码 0。只读 (零写命令)。
    """
    limit = getattr(args, "limit", None) or 20
    with ctx.logger_scope() as logger:
        service = _open_git_service(ctx, args)
        commits = service.get_commits(limit=limit)
        status = service.get_status()
        ev = logger.record(
            EventType.GIT_COMMIT_VIEWED, source=SOURCE, project_id=args.project,
            stage="viewed", action="view git commits", result="OK",
            payload={
                "repository": service.client.repository,
                "count": len(commits),
                "limit": limit,
                "hashes": [c.hash for c in commits[:20]],
                "error": status.error,
            },
        )
    return {
        "ok": True,
        "count": len(commits),
        "commits": [c.to_dict() for c in commits],
        "error": status.error,
        "event_seq": ev.seq,
    }


# ------------------------------------------------------------------ change 子命令 (Phase 6D, ADR-0019)

def _open_change_service(
    ctx: FactoryContext, args: Any, logger: Any = None,
) -> ChangeService:
    """装配 ChangeService (Commit 解析 / 路径分析 / L4 验证 / 快照关联)。

    仓库路径: --repo 显式 > 缺省工厂根目录 (ctx.root) — Change Intelligence 以
    任务为中心, 工厂根即仓库是单仓冒烟/常规场景; 非 git 目录由服务层失败安全
    (is_repo=False → L4 SKIP / commits 空), 不抛错 (ADR-0019 决策 8)。
    存储路径全部显式传 <root>/ 下 (change/snapshots.json + git/changes.json),
    不依赖 cwd (backend-developer skill: store 默认路径禁用 cwd 相对)。
    task_store 装配 → L4 路径匹配可读取任务标题; logger 装配 → 审计事件。
    """
    repo = getattr(args, "repo", None)
    repository = os.path.expanduser(repo) if repo else str(ctx.root)
    return ChangeService(
        client=GitClient(repository),
        task_store=ctx.open_task_store(),
        logger=logger,
        change_store=ChangeStore(ctx.root / "change"),
        git_changes_store=GitChangeStore(ctx.root / "git"),
    )


def _change_last_seq(logger) -> int | None:
    """当前事件库最后一条 seq (命令结果 event_seq 审计锚点)。"""
    events = logger.store.query()
    return events[-1].seq if events else None


def cmd_change_commits(ctx: FactoryContext, args: Any) -> dict:
    """factory change commits — 提交 + 任务关联解析 (message > execution > branch),
    发 git.commit.linked (命中) + git.commit.viewed (审计)。

    失败安全: 非 git 目录/空仓库 → commits 空, 退出码 0 (错误经 status 呈现)。
    只读: 零仓库写命令 (Git 只读铁律)。
    """
    limit = getattr(args, "limit", None) or 20
    with ctx.logger_scope() as logger:
        service = _open_change_service(ctx, args, logger)
        commits = service.parse_commits(limit=limit)
        status = service.client.status()
        ev = logger.record(
            EventType.GIT_COMMIT_VIEWED, source=SOURCE, stage="viewed",
            action="view change commits", result="OK",
            payload={
                "repository": service.client.repository,
                "count": len(commits),
                "limit": limit,
                "hashes": [c.hash for c in commits[:20]],
                "linked": [c.task_id for c in commits if c.task_id],
                "error": status.error,
            },
        )
    return {
        "ok": True,
        "count": len(commits),
        "commits": [c.to_dict() for c in commits],
        "error": status.error,
        "event_seq": ev.seq,
    }


def cmd_change_analyze(ctx: FactoryContext, args: Any) -> dict:
    """factory change analyze TASK_ID — 任务变更路径分析 (Files/Insertions/
    Deletions/Affected modules), 发 git.commit.linked (命中) + change.analyzed。

    禁 LLM (ADR-0019 决策 2): 全部确定性规则 (路径分段/模块推断/行数对账)。
    失败安全: 非 git 目录 → 空分析, 退出码 0 (L4 语义: 无 git 关联 → SKIP)。
    """
    with ctx.logger_scope() as logger:
        service = _open_change_service(ctx, args, logger)
        analysis = service.analyze(args.task_id)
        event_seq = _change_last_seq(logger)  # 须在作用域内取 (退出即关库)
    return {
        "ok": True,
        "task_id": args.task_id,
        "analysis": analysis.to_dict(),
        "event_seq": event_seq,
    }


def cmd_change_validate(ctx: FactoryContext, args: Any) -> dict:
    """factory change validate TASK_ID — L4 Change Validation (Task 描述 vs Git
    变更证据 → PASS/FAIL/SKIP), 发 change.validation.completed。

    退出码 (ADR-0019 决策 8): 0 PASS/SKIP (SKIP = 无 git 关联, 旧 Task 兼容,
    非失败) / 3 FAIL (变更证据与任务不符) / 1 ERROR (规则内部错误)。
    失败安全: 内部异常 → ERROR 结果 (不抛, 同 ValidationEngine 规则兜底语义)。
    """
    with ctx.logger_scope() as logger:
        service = _open_change_service(ctx, args, logger)
        result = service.validate(args.task_id)
        event_seq = _change_last_seq(logger)  # 须在作用域内取 (退出即关库)
    exit_code = 0 if result.status in ("PASS", "SKIP") else (3 if result.status == "FAIL" else 1)
    return {
        "ok": result.status == "PASS",
        "task_id": args.task_id,
        "result": result.to_dict(),
        "exit_code": exit_code,
        "event_seq": event_seq,
    }


# ------------------------------------------------------------------ change triggers / evaluate / workflows (Phase 6E, ADR-0020)

def _open_changeflow_engine(
    ctx: FactoryContext, args: Any, logger: Any, *, execute: bool,
) -> ChangeWorkflowEngine:
    """装配 ChangeWorkflowEngine (Phase 6E, ADR-0020)。

    复用不复制 (ADR-0020 决策 2): 规则输入 = ChangeService (L4 判定/关联提交/
    变更文件, repo 缺省 = 工厂根 — 同 change validate 模式); 触发 = WorkflowEngine
    /WorkflowStore (run 落盘 + 状态机校验); 执行 = orchestration.pipeline
    .execute_workflow 部分应用 (run 已 RUNNING → OrchestrationEngine._ensure_run
    续跑分支, 天然支持 target != task.workflow)。execute=False → 不装配 executor
    (纯评估 / workflows 查询命令, 零执行副作用)。
    """
    executor = None
    if execute:
        executor = partial(
            run_orchestration,
            workflow_store=WorkflowStore(ctx.workflows_dir),
            task_store=ctx.open_task_store(),
            agent_store=ctx.open_agent_store(),
            assignment_store=_open_assignment_store(ctx),
            runtime_store=_open_runtime_store(ctx),
            logger=logger,
        )
    return ChangeWorkflowEngine(
        triggers=ChangeTriggerRegistry(ctx.root / "changeflow"),
        task_store=ctx.open_task_store(),
        change_service=_open_change_service(ctx, args, logger),
        workflow_engine=_open_workflow_engine(ctx, logger),
        workflow_store=WorkflowStore(ctx.workflows_dir),
        runtime_registry=RuntimeRegistry(_open_runtime_store(ctx), logger=logger),
        executor=executor,
        logger=logger,
    )


def cmd_change_triggers_list(ctx: FactoryContext, args: Any) -> dict:
    """factory change triggers list — 触发器列表 (只读), 发 change.trigger.viewed。

    数据源 = ChangeTriggerRegistry (<root>/changeflow/triggers.json, 只读);
    失败安全: 文件缺失/损坏 → 空列表 (失败安全, 同 registry 语义)。
    """
    with ctx.logger_scope() as logger:
        registry = ChangeTriggerRegistry(ctx.root / "changeflow")
        triggers = registry.list()
        ev = record_change_trigger_viewed(logger, count=len(triggers))
    return {
        "ok": True,
        "count": len(triggers),
        "triggers": [t.to_dict() for t in triggers],
        "event_seq": ev.seq,
    }


def cmd_change_triggers_register(ctx: FactoryContext, args: Any) -> dict:
    """factory change triggers register — 注册变更触发器, 发 change.trigger.created。

    声明式驱动规则: 事件类型 (workflow.completed 等) + 项目/任务类型限定 +
    目标工作流; 目标工作流存在性在 evaluate 触发时校验 (注册只落盘, KISS)。
    冲突 id → CliError 退出码 1。
    """
    trigger = ChangeTrigger(
        id=args.id,
        event_type=args.event_type,
        project_id=args.project,
        task_type=args.task_type,
        required_validation=args.required_validation,
        target_workflow=args.target_workflow,
    )
    with ctx.logger_scope() as logger:
        registry = ChangeTriggerRegistry(ctx.root / "changeflow")
        try:
            trigger, ev = registry.register(trigger, logger=logger)
        except ChangeTriggerExistsError as exc:
            raise CliError(str(exc), exit_code=1) from exc
    return {
        "ok": True,
        "trigger": trigger.to_dict(),
        "event_seq": ev.seq if ev is not None else None,
    }


def cmd_change_evaluate(ctx: FactoryContext, args: Any) -> dict:
    """factory change evaluate TASK_ID — Change 规则评估 + 触发执行, 发
    change.trigger.evaluated (+ 触发成功 change.workflow.started/completed)。

    装配 executor=orchestration pipeline (ADR-0020 决策 3): 4 规则全 PASS → 启动
    target_workflow 运行实例并执行 (run 已 RUNNING 续跑分支); FAIL/SKIP/ERROR
    不触发。失败恢复不级联: 触发/执行失败 → ERROR 评估 (含 error), 不抛。
    退出码 (同 validate 契约): PASS/SKIP → 0 (SKIP = 无匹配触发器, 非失败) /
    FAIL → 3 / ERROR → 1。
    """
    execute = None if args.execute else False  # 默认执行 (executor 已装配)
    with ctx.logger_scope() as logger:
        engine = _open_changeflow_engine(ctx, args, logger, execute=execute is not False)
        evaluation = engine.evaluate(args.task_id)
        event_seq = _change_last_seq(logger)  # 须在作用域内取 (退出即关库)
    exit_code = (
        0 if evaluation.status in ("PASS", "SKIP")
        else (3 if evaluation.status == "FAIL" else 1)
    )
    return {
        "ok": evaluation.status == "PASS",
        "task_id": args.task_id,
        "evaluation": evaluation.to_dict(),
        "exit_code": exit_code,
        "event_seq": event_seq,
    }


def cmd_change_workflows(ctx: FactoryContext, args: Any) -> dict:
    """factory change workflows TASK_ID — 任务关联 workflow 链 (只读), 审计经
    change.trigger.viewed 之外由 engine 查询 (无写路径, 不发业务事件)。

    链 = 任务工作流 (task.workflow → 定义/运行实例) + 触发工作流
    (change.workflow.started 事件: target workflow/run_id/状态)。无记录 → 空链
    (CLI 输出占位)。失败安全: 任务不存在 → 空链。
    """
    with ctx.logger_scope() as logger:
        engine = _open_changeflow_engine(ctx, args, logger, execute=False)
        chain = engine.workflow_chain(args.task_id)
        event_seq = _change_last_seq(logger)
    return {
        "ok": True,
        "task_id": args.task_id,
        "count": len(chain),
        "chain": chain,
        "event_seq": event_seq,
    }


# ------------------------------------------------------------------ understand (Phase 7, ADR-0021)

def cmd_understand(ctx: FactoryContext, args: Any) -> dict:
    """factory understand <path> — 项目理解报告 (只读, 规则分析, 禁 LLM)。

    编排 = UnderstandingService.analyze (基本信息 → 文档检测 → 产物检测 →
    阶段识别 → 缺失分析 → 建议); 服务层发 understanding.started/completed
    (失败 → failed), 命令层发 understanding.viewed (ADR-0002 读命令审计,
    source="cli", 经 events.py 辅助 — 载荷键契约与 CLI --json 出口一致)。
    退出码: 0 成功 / 1 路径无效或内部错误 (UnderstandingError → CliError)。
    --stage: 仅输出阶段识别 (--json 时结果只含 stage 段)。
    只读铁律: 分析不写任何文件 (字节级只读性由 tests/understanding 守住)。
    """
    path = os.path.expanduser(args.path)
    with ctx.logger_scope() as logger:
        service = UnderstandingService(logger=logger)
        try:
            report = service.analyze(path)
        except UnderstandingError as exc:
            raise CliError(str(exc), exit_code=1) from exc
        present = [a.artifact for a in report.artifacts if a.present]
        record_understanding_viewed(
            logger,
            path=report.path,
            stage=report.stage.stage,
            confidence=report.stage.confidence,
            present=len(present),
            missing=len(report.missing.missing),
        )
        event_seq = _change_last_seq(logger)  # 须在作用域内取 (退出即关库)
    if getattr(args, "stage", False):
        return {
            "ok": True,
            "path": path,
            "stage": report.stage.to_dict(),
            "stage_only": True,
            "event_seq": event_seq,
        }
    return {
        "ok": True,
        "path": path,
        "report": report.to_dict(),
        "stage_only": False,
        "event_seq": event_seq,
    }


# ------------------------------------------------------------------ product (Phase 9A, ADR-0026)

def _open_product_service(ctx: FactoryContext, logger: Any):
    """装配 ProductService (延迟导入 product 包 — Removal Isolation: 删除
    product/ 不影响本模块加载, 同 provider 延迟导入模式)。"""
    from product.service import ProductService

    from product.store import ProductStore

    return ProductService(ProductStore(ctx.root / "product"), logger=logger)


def _product_last_seq(logger: Any, type_: Any) -> int | None:
    """最后一条指定类型事件的 seq (写命令 event_seq 审计锚点)。"""
    events = logger.store.query(event_type=type_)
    return events[-1].seq if events else None


def _product_errors():
    """延迟导入异常类 (Removal Isolation: 无顶层 product imports)。"""
    from product.service import ProductError, ProductNotFoundError

    return ProductError, ProductNotFoundError


#: 9c 终态决定值 → CLI 审计锚点事件 (decide 命令 event_seq; 9a 兼容事件
#: granted/denied 由服务层同时发出, 不参与 CLI 取序)。
_DECISION_EVENT = {
    "approved": EventType.APPROVAL_APPROVED,
    "rejected": EventType.APPROVAL_REJECTED,
    "changes_requested": EventType.APPROVAL_CHANGES_REQUESTED,
    "delegated": EventType.APPROVAL_DELEGATED,
}


def cmd_product_idea_create(ctx: FactoryContext, args: Any) -> dict:
    """factory product idea create — 创建想法 (发 idea.created, source=product)。

    同步落 product_idea Artifact (Artifact 抽象: Idea 即 Artifact, 任何 Artifact
    可申请审批 — 返回 artifact_id 供 approval request 使用)。
    """
    with ctx.logger_scope() as logger:
        service = _open_product_service(ctx, logger)
        idea = service.create_idea(
            args.title,
            description=args.description or "",
            goals=_parse_csv(args.goals) if getattr(args, "goals", None) else [],
            created_by="cli",
        )
        artifact = service.get_artifact_by_idea(idea.id)
        event_seq = _product_last_seq(logger, EventType.IDEA_CREATED)
    return {
        "ok": True,
        "idea": idea.to_dict(),
        "artifact": artifact.to_dict() if artifact is not None else None,
        "event_seq": event_seq,
    }


def cmd_product_idea_list(ctx: FactoryContext, args: Any) -> dict:
    """factory product idea list — 想法列表 (发 idea.viewed, source=cli 审计)。"""
    from product.events import record_idea_viewed

    with ctx.logger_scope() as logger:
        service = _open_product_service(ctx, logger)
        ideas = service.list_ideas()
        record_idea_viewed(logger, count=len(ideas))
        event_seq = _product_last_seq(logger, EventType.IDEA_VIEWED)
    return {"ok": True, "count": len(ideas), "ideas": [i.to_dict() for i in ideas], "event_seq": event_seq}


def cmd_product_idea_show(ctx: FactoryContext, args: Any) -> dict:
    """factory product idea show <id> — 想法详情 (发 idea.viewed; 未找到 → 退出码 7)。"""
    from product.events import record_idea_viewed

    ProductError, ProductNotFoundError = _product_errors()
    with ctx.logger_scope() as logger:
        service = _open_product_service(ctx, logger)
        try:
            idea = service.get_idea(args.idea_id)
        except ProductNotFoundError as exc:
            raise CliError(str(exc), exit_code=7) from exc
        artifact = service.get_artifact_by_idea(idea.id)
        record_idea_viewed(logger, count=1, idea_id=idea.id)
        event_seq = _product_last_seq(logger, EventType.IDEA_VIEWED)
    return {
        "ok": True,
        "idea": idea.to_dict(),
        "artifact": artifact.to_dict() if artifact is not None else None,
        "event_seq": event_seq,
    }


def cmd_product_approval_request(ctx: FactoryContext, args: Any) -> dict:
    """factory product approval request <artifact_id> [--gate prd|ui|architecture]
    — 申请审批: 任何 Artifact 可申请 (发 approval.required; 关联 workflow 暂停)。

    门解析: --gate 显式指定 (门 id == artifact_type); 缺省按 artifact.type 匹配
    默认门 (prd/ui mandatory, architecture recommended); 无门 → 退出码 1。
    artifact 不存在 → 退出码 7。
    """
    ProductError, ProductNotFoundError = _product_errors()
    with ctx.logger_scope() as logger:
        service = _open_product_service(ctx, logger)
        try:
            request = service.request_approval(
                args.artifact_id,
                gate_id=getattr(args, "gate", None),
                by=getattr(args, "by", None) or "cli",
                note=getattr(args, "note", None),
            )
        except ProductNotFoundError as exc:
            raise CliError(str(exc), exit_code=7) from exc
        except ProductError as exc:
            raise CliError(str(exc), exit_code=1) from exc
        event_seq = _product_last_seq(logger, EventType.APPROVAL_REQUIRED)
    return {"ok": True, "approval": request.to_dict(), "event_seq": event_seq}


def cmd_product_approval_decide(ctx: FactoryContext, args: Any) -> dict:
    """factory product approval decide <request_id> approve|reject|changes_requested|delegate
    [--comment] [--by] — 审批决定 (发 approval.approved/rejected/changes_requested/delegated;
    approved 产生 Product Decision Artifact)。

    CLI 动词 → 服务层终态值映射 (Phase 9a 教训: 动词 ≠ 领域终态值); "deny" 为 9a
    兼容别名 → denied → 服务层映射 rejected (ADR-0028 决策 1)。状态机: pending →
    终态 (不可重复 decide, 重复决定 → 退出码 1); request 不存在 → 退出码 7。
    """
    ProductError, ProductNotFoundError = _product_errors()
    # CLI 动词 → 服务层语义终态值 (状态机契约; deny 保留 9a 兼容别名)
    decision_value = {
        "approve": "approved",
        "reject": "rejected",
        "changes_requested": "changes_requested",
        "delegate": "delegated",
        "deny": "denied",  # 9a 遗留别名 → 服务层映射 rejected
    }[args.decision]
    with ctx.logger_scope() as logger:
        service = _open_product_service(ctx, logger)
        try:
            request, decision, decision_artifact = service.decide_approval(
                args.request_id,
                decision_value,
                by=args.by or "cli",
                comment=args.comment or "",
            )
        except ProductNotFoundError as exc:
            raise CliError(str(exc), exit_code=7) from exc
        except ProductError as exc:
            raise CliError(str(exc), exit_code=1) from exc
        # Phase 9d (ADR-0029): 生命周期联动 — 审批终态同步生命周期 (approval 阶段
        # approved → 决策链记录 + 阶段完成 + 推进; 非 approved → 停留)。无生命
        # 周期 → no-op (9c 既有流程不变, 零回归)。
        engine = _open_lifecycle_engine(ctx, logger)
        lifecycle = engine.handle_approval_outcome(request.idea_id)
        # 9c 终态事件 (approval.approved/rejected/changes_requested/delegated) 为
        # CLI 审计锚点; 9a 兼容事件 (granted/denied) 由服务层同时发出, 不在此取序
        event_seq = _product_last_seq(logger, _DECISION_EVENT[decision.decision])
    return {
        "ok": True,
        "approval": request.to_dict(),
        "decision": decision.to_dict(),
        "product_decision": decision_artifact.to_dict() if decision_artifact is not None else None,
        "lifecycle": lifecycle.to_dict() if lifecycle is not None else None,
        "event_seq": event_seq,
    }


def cmd_product_approval_list(ctx: FactoryContext, args: Any) -> dict:
    """factory product approval list [--pending] [--status <status>] — 审批清单
    (发 approval.viewed 审计; --status 过滤 = Approval Queue 视图)。"""
    from product.events import record_approval_viewed

    status = getattr(args, "status", None)
    pending_only = getattr(args, "pending", False)
    with ctx.logger_scope() as logger:
        service = _open_product_service(ctx, logger)
        requests = service.list_approvals(pending_only=pending_only, status=status)
        record_approval_viewed(logger, count=len(requests), pending_only=pending_only, status=status)
        event_seq = _product_last_seq(logger, EventType.APPROVAL_VIEWED)
    return {
        "ok": True,
        "count": len(requests),
        "approvals": [r.to_dict() for r in requests],
        "event_seq": event_seq,
    }


def cmd_product_approval_history(ctx: FactoryContext, args: Any) -> dict:
    """factory product approval history <artifact_id> — Artifact 审批历史
    (全部请求 + 决定联表, 按 requested_at 升序; 发 approval.viewed 审计)。

    artifact 不存在 → 退出码 7; 无请求 → 空历史 (count 0)。
    """
    from product.events import record_approval_viewed

    ProductError, ProductNotFoundError = _product_errors()
    with ctx.logger_scope() as logger:
        service = _open_product_service(ctx, logger)
        try:
            history = service.approval_history(args.artifact_id)
        except ProductNotFoundError as exc:
            raise CliError(str(exc), exit_code=7) from exc
        record_approval_viewed(logger, count=len(history), artifact_id=args.artifact_id)
        event_seq = _product_last_seq(logger, EventType.APPROVAL_VIEWED)
    return {
        "ok": True,
        "artifact_id": args.artifact_id,
        "count": len(history),
        "history": history,
        "event_seq": event_seq,
    }


def cmd_product_workflow_start(ctx: FactoryContext, args: Any) -> dict:
    """factory product workflow start <idea_id> — 启动产品工作流 (发 product.workflow.started)。

    idea 不存在 → 退出码 7; 已启动 → 退出码 1 (一个 idea 至多一个 run)。
    """
    ProductError, ProductNotFoundError = _product_errors()
    with ctx.logger_scope() as logger:
        service = _open_product_service(ctx, logger)
        try:
            workflow = service.start_workflow(args.idea_id)
        except ProductNotFoundError as exc:
            raise CliError(str(exc), exit_code=7) from exc
        except ProductError as exc:
            raise CliError(str(exc), exit_code=1) from exc
        event_seq = _product_last_seq(logger, EventType.PRODUCT_WORKFLOW_STARTED)
    return {"ok": True, "workflow": workflow.to_dict(), "event_seq": event_seq}


def cmd_product_workflow_status(ctx: FactoryContext, args: Any) -> dict:
    """factory product workflow status <idea_id> — 工作流状态 (发 product.workflow.status_viewed)。

    无工作流 → 退出码 7。
    """
    from product.events import record_workflow_status_viewed

    ProductError, ProductNotFoundError = _product_errors()
    with ctx.logger_scope() as logger:
        service = _open_product_service(ctx, logger)
        try:
            workflow = service.workflow_status(args.idea_id)
        except ProductNotFoundError as exc:
            raise CliError(str(exc), exit_code=7) from exc
        record_workflow_status_viewed(logger, workflow=workflow)
        event_seq = _product_last_seq(logger, EventType.PRODUCT_WORKFLOW_STATUS_VIEWED)
    return {"ok": True, "workflow": workflow.to_dict(), "event_seq": event_seq}


def cmd_product_workflow_resume(ctx: FactoryContext, args: Any) -> dict:
    """factory product workflow resume <idea_id> — 手动恢复暂停的工作流
    paused → running (发 approval.resumed reason=manual)。

    通用决策系统的恢复入口: 审批终态 (rejected/changes_requested) 后用户决定
    不重审直接推进时使用。无工作流 → 退出码 7; 未暂停 → 退出码 1。
    """
    ProductError, ProductNotFoundError = _product_errors()
    with ctx.logger_scope() as logger:
        service = _open_product_service(ctx, logger)
        try:
            workflow = service.workflow_resume(args.idea_id)
        except ProductNotFoundError as exc:
            raise CliError(str(exc), exit_code=7) from exc
        except ProductError as exc:
            raise CliError(str(exc), exit_code=1) from exc
        event_seq = _product_last_seq(logger, EventType.APPROVAL_RESUMED)
    return {"ok": True, "workflow": workflow.to_dict(), "event_seq": event_seq}


# ------------------------------------------------------------------ product generate/experience (Phase 9B, ADR-0027)


def _open_product_generator(ctx: FactoryContext, logger: Any, *, experience_store: Any = None):
    """装配 ProductGenerator (延迟导入 product + providers — Removal Isolation)。

    生成编排复用 Phase 8: CostAwareSelector (默认能力/成本基线 + UsageStore 实测
    统计) + BUILTIN_PROVIDER_ADAPTERS 实现映射; 删除 providers 包 → selector/
    adapters/usage_store 为 None → generate 抛明确错误 (配置缺口响亮暴露, 同
    dashboard --view provider 删包模式)。experience_store 独立装配 (product 包内,
    删 providers 不影响经验记录)。
    """
    from product.experience import ExperienceStore
    from product.generation import ProductGenerator
    from product.service import ProductService
    from product.store import ProductStore

    service = ProductService(ProductStore(ctx.root / "product"), logger=logger)
    try:
        from providers.adapters import BUILTIN_PROVIDER_ADAPTERS
        from providers.definitions import DEFAULT_CAPABILITY_PROFILES, DEFAULT_COST_MODELS
        from providers.registry import ProviderRegistry
        from providers.selector import CostAwareSelector
        from providers.usage import UsageStore, stats_by_provider

        registry = ProviderRegistry(_open_provider_store(ctx), logger=logger)
        selector = CostAwareSelector(
            registry, DEFAULT_CAPABILITY_PROFILES, DEFAULT_COST_MODELS,
            usage_stats=stats_by_provider(
                _open_provider_usage_store(ctx).list(), period="all",
            ),
        )
        adapters = dict(BUILTIN_PROVIDER_ADAPTERS)
        usage_store = _open_provider_usage_store(ctx)
    except ImportError:
        selector = adapters = usage_store = None
    return ProductGenerator(
        service, logger=logger,
        selector=selector, adapters=adapters, usage_store=usage_store,
        experience_store=experience_store if experience_store is not None else ExperienceStore(ctx.root / "product"),
    )


def cmd_product_generate(ctx: FactoryContext, args: Any) -> dict:
    """factory product generate <idea_id> --type research|prd|ui [--provider <id>]
    — AI 生成产品 Artifact (TaskRequirement → CostAwareSelector → ProviderAdapter)。

    选择: --provider 显式覆盖 (未注册/禁用 → 退出码 1); 缺省经 CostAwareSelector
    推荐 (能力过滤 + 配置优先 + 成本排序, 复用 Phase 8, 禁硬编码)。产出 Artifact
    (GeneratedArtifactContext + Lineage) + PRD/UI 自动申请审批 (mandatory, 生成后
    等待人工批准)。事件链: product.generation.started → provider.selected →
    provider.execution.started|completed → product.generation.completed →
    approval.required。退出码: 0 成功 / 1 无 Provider/无 Adapter/生成失败/无效类型
    / 2 用法 / 7 idea 未找到。无 Provider 可用 → 明确错误 (不静默)。
    """
    ProductError, ProductNotFoundError = _product_errors()
    with ctx.logger_scope() as logger:
        generator = _open_product_generator(ctx, logger)
        try:
            result = generator.generate(
                args.idea_id,
                args.type,
                provider_id=getattr(args, "provider", None),
                created_by="cli",
            )
        except ProductNotFoundError as exc:
            raise CliError(str(exc), exit_code=7) from exc
        except ProductError as exc:
            raise CliError(str(exc), exit_code=1) from exc
        event_seq = _product_last_seq(logger, EventType.PRODUCT_GENERATION_COMPLETED)
    return {
        "ok": True,
        "artifact": result.artifact.to_dict(),
        "context": result.context.to_dict(),
        "approval": result.approval_request.to_dict() if result.approval_request is not None else None,
        "provider_id": result.provider_id,
        "recommendation": result.recommendation,
        "event_seq": event_seq,
    }


def cmd_product_experience_list(ctx: FactoryContext, args: Any) -> dict:
    """factory product experience list [--artifact-type X] — 生成经验清单 (发
    product.experience.viewed 审计; ADR-0002: 所有 CLI 行为必须产生 Event)。"""
    from product.events import record_experience_viewed

    with ctx.logger_scope() as logger:
        generator = _open_product_generator(ctx, logger)
        experiences = generator.list_experiences(
            artifact_type=getattr(args, "artifact_type", None),
        )
        record_experience_viewed(
            logger, count=len(experiences),
            artifact_type=getattr(args, "artifact_type", None),
        )
        event_seq = _product_last_seq(logger, EventType.PRODUCT_EXPERIENCE_VIEWED)
    return {
        "ok": True,
        "count": len(experiences),
        "experiences": [e.to_dict() for e in experiences],
        "event_seq": event_seq,
    }


def cmd_product_experience_record(ctx: FactoryContext, args: Any) -> dict:
    """factory product experience record <artifact_id> --rating 1-5 [--comment]
    [--approved true|false] — 记录人工对生成产物的经验 (数据接口, 不实现优化逻辑)。

    从 Artifact Lineage 推导 provider_id/confidence/generated_at; 落 ExperienceStore
    + 发 product.experience.recorded。artifact 不存在 → 退出码 7; 经验库未装配 →
    退出码 1。rating 越界 (非 1-5) → 模型校验错误 → 退出码 1。
    """
    ProductError, ProductNotFoundError = _product_errors()
    with ctx.logger_scope() as logger:
        generator = _open_product_generator(ctx, logger)
        try:
            experience = generator.record_experience(
                args.artifact_id,
                rating=args.rating,
                comment=getattr(args, "comment", None) or "",
                approved=getattr(args, "approved", None),
                by=getattr(args, "by", None) or "cli",
            )
        except ProductNotFoundError as exc:
            raise CliError(str(exc), exit_code=7) from exc
        except ProductError as exc:
            raise CliError(str(exc), exit_code=1) from exc
        event_seq = _product_last_seq(logger, EventType.PRODUCT_EXPERIENCE_RECORDED)
    return {"ok": True, "experience": experience.to_dict(), "event_seq": event_seq}


# ------------------------------------------------------------------ product lifecycle (Phase 9d, ADR-0029)


def _open_lifecycle_engine(ctx: FactoryContext, logger: Any, *, task_store: Any = None):
    """装配 ProductLifecycleEngine (延迟导入 product + tasks — Removal Isolation)。

    task_store: task 阶段经 TaskStore.create 生成 Core Task (复用既有 API, 禁
    修改 Core); 缺省按 ctx.root/tasks 装配 — task 阶段无 task_store 时引擎
    响亮报错 (配置缺口, 同 9b 装配点模式)。
    """
    from product.lifecycle import ProductLifecycleEngine
    from product.service import ProductService
    from product.store import ProductStore

    service = ProductService(ProductStore(ctx.root / "product"), logger=logger)
    ts = task_store if task_store is not None else TaskStore(ctx.root / "tasks")
    return ProductLifecycleEngine(
        ProductStore(ctx.root / "product"), service, task_store=ts, logger=logger,
    )


def cmd_product_lifecycle_start(ctx: FactoryContext, args: Any) -> dict:
    """factory product lifecycle start <idea_id> [--template software_project]
    — 启动生命周期 (发 product.lifecycle.started + product.stage.entered)。

    idea 不存在 → 退出码 7; 已启动/模板未注册 → 退出码 1。启动后当前阶段 =
    首阶段 (idea — product_idea Artifact 已存在, 可直接 advance)。
    """
    ProductError, ProductNotFoundError = _product_errors()
    with ctx.logger_scope() as logger:
        engine = _open_lifecycle_engine(ctx, logger)
        try:
            lifecycle = engine.start_lifecycle(
                args.idea_id,
                template=getattr(args, "template", None) or "software_project",
                by="cli",
            )
        except ProductNotFoundError as exc:
            raise CliError(str(exc), exit_code=7) from exc
        except ProductError as exc:
            raise CliError(str(exc), exit_code=1) from exc
        event_seq = _product_last_seq(logger, EventType.PRODUCT_LIFECYCLE_STARTED)
    return {
        "ok": True,
        "lifecycle": lifecycle.to_dict(),
        "current_stage": (
            lifecycle.current_stage.to_dict() if lifecycle.current_stage is not None else None
        ),
        "event_seq": event_seq,
    }


def cmd_product_lifecycle_status(ctx: FactoryContext, args: Any) -> dict:
    """factory product lifecycle status <idea_id> — 生命周期状态: 当前阶段/
    待审批/产物/决策链/下一步动作 (发 product.lifecycle.status_viewed 审计)。

    无生命周期 → 退出码 7。Dashboard Lifecycle View 与 CLI status 消费同一
    快照形状 (engine.status)。
    """
    from product.events import record_lifecycle_status_viewed

    ProductError, ProductNotFoundError = _product_errors()
    with ctx.logger_scope() as logger:
        engine = _open_lifecycle_engine(ctx, logger)
        try:
            snapshot = engine.status(args.idea_id)
        except ProductNotFoundError as exc:
            raise CliError(str(exc), exit_code=7) from exc
        record_lifecycle_status_viewed(
            logger, lifecycle=snapshot["lifecycle"]["id"] and _load_lifecycle_for_view(ctx, logger, args.idea_id),
        )
        event_seq = _product_last_seq(logger, EventType.PRODUCT_LIFECYCLE_STATUS_VIEWED)
    return {"ok": True, **snapshot, "event_seq": event_seq}


def _load_lifecycle_for_view(ctx: FactoryContext, logger: Any, idea_id: str):
    """status 读审计的 lifecycle 对象 (从 store 重取, 事件 payload 需领域对象)。"""
    from product.store import ProductStore

    return ProductStore(ctx.root / "product").get_lifecycle_by_idea(idea_id)


def cmd_product_lifecycle_advance(ctx: FactoryContext, args: Any) -> dict:
    """factory product lifecycle advance <idea_id> — 手动推进当前阶段 (非 approval
    阶段; 发 product.stage.completed + product.stage.entered)。

    artifact_generation 阶段须先有产物 (product generate --type <type>); decision
    阶段须前序决策链完整; task 阶段生成 task_plan + Core Task (TaskStore.create)
    并完成生命周期。approval 阶段 → 退出码 1 (经审批决定推进, 见 decide 联动);
    无生命周期 → 退出码 7; 生命周期非 running → 退出码 1。
    """
    ProductError, ProductNotFoundError = _product_errors()
    with ctx.logger_scope() as logger:
        engine = _open_lifecycle_engine(ctx, logger)
        try:
            lifecycle = engine.advance(args.idea_id, by="cli")
        except ProductNotFoundError as exc:
            raise CliError(str(exc), exit_code=7) from exc
        except ProductError as exc:
            raise CliError(str(exc), exit_code=1) from exc
        event_seq = _product_last_seq(logger, EventType.PRODUCT_STAGE_COMPLETED)
    return {
        "ok": True,
        "lifecycle": lifecycle.to_dict(),
        "current_stage": (
            lifecycle.current_stage.to_dict() if lifecycle.current_stage is not None else None
        ),
        "event_seq": event_seq,
    }


def cmd_product_lifecycle_templates(ctx: FactoryContext, args: Any) -> dict:
    """factory product lifecycle templates — 生命周期模板列表 (声明式解析; 发
    product.lifecycle.templates_viewed 审计, ADR-0002)。"""
    from product.events import record_lifecycle_templates_viewed

    with ctx.logger_scope() as logger:
        engine = _open_lifecycle_engine(ctx, logger)
        templates = engine.templates()
        record_lifecycle_templates_viewed(
            logger, count=len(templates),
            template_names=[t["name"] for t in templates],
        )
        event_seq = _product_last_seq(logger, EventType.PRODUCT_LIFECYCLE_TEMPLATES_VIEWED)
    return {
        "ok": True,
        "count": len(templates),
        "templates": templates,
        "event_seq": event_seq,
    }
