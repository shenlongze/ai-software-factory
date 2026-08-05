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

from events.models import EventType
from tasks.models import Task, TaskStatus
from tasks.store import TaskExistsError, TaskStore

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
    """factory validate <id> — Validation Hook 占位 (Phase 3 接真引擎)。

    流程: 发 validation.started → 跑占位检查 → 发 validation.completed (result=PASS/FAIL)。
    退出码: 0 通过 / 3 验证失败 (--expect-status 不匹配) / 7 任务不存在。
    """
    expect_status = _parse_status(args.expect_status)
    level = args.level or "L2"
    task = ctx.open_task_store().get(args.task_id)

    with ctx.logger_scope() as logger:
        logger.record(
            EventType.VALIDATION_STARTED, source=SOURCE, project_id=task.project if task else None,
            task_id=args.task_id, stage=level, result="started", action="run validation",
            payload={"level": level, "expect_status": expect_status.value if expect_status else None},
        )
        if task is None:
            checks = [
                {"id": "L1.task_exists", "name": "任务存在", "status": "FAIL",
                 "detail": f"task not found: {args.task_id}"},
            ]
            logger.record(
                EventType.VALIDATION_COMPLETED, source=SOURCE, task_id=args.task_id,
                stage=level, result="FAIL", action="validation completed",
                payload={"level": level, "reason": "task_not_found", "checks": checks},
            )
            return {"ok": False, "task_id": args.task_id, "level": level, "checks": checks,
                    "reason": "task_not_found", "exit_code": 7}

        checks = [
            {"id": "L1.definition", "name": "任务定义完整", "status": "PASS",
             "detail": f"id={task.id} title={task.title!r} project={task.project} type={task.type}"},
            {"id": "L1.status", "name": "状态合法", "status": "PASS", "detail": task.status.value},
            {"id": "L2.build_test", "name": "构建+测试", "status": "SKIP",
             "detail": "validation engine 未实现, Phase 3 占位"},
        ]
        reason = None
        if expect_status is not None and task.status is not expect_status:
            reason = "status_mismatch"
            checks.append(
                {"id": "L2.expect_status", "name": "期望状态", "status": "FAIL",
                 "detail": f"expected {expect_status.value}, got {task.status.value}"},
            )
        result = "FAIL" if reason else "PASS"
        logger.record(
            EventType.VALIDATION_COMPLETED, source=SOURCE, project_id=task.project, task_id=task.id,
            stage=level, result=result, action="validation completed",
            payload={
                "level": level,
                "expect_status": expect_status.value if expect_status else None,
                "reason": reason,
                "checks": checks,
            },
        )
    return {
        "ok": result == "PASS",
        "task_id": task.id,
        "level": level,
        "checks": checks,
        "reason": reason,
        "exit_code": 0 if result == "PASS" else 3,
    }
