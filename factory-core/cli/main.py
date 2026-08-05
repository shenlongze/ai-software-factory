"""cli/main.py — factory CLI 入口 (argparse, 标准库零依赖)。

命令 (phase2-status 核心子集): init / task create|list|status|update /
event logs / status / validate。
退出码 (cli-design §5): 0 成功 / 1 一般错误 / 2 用法 (argparse 默认) / 3 验证失败 / 7 未找到。

入口: `factory` console script 或 `.venv/bin/python -m cli.main`。
"""

from __future__ import annotations

import json
import sys
from typing import Any

from .commands import (
    CliError,
    cmd_agent_add,
    cmd_agent_assign,
    cmd_agent_assignments,
    cmd_agent_list,
    cmd_agent_release,
    cmd_checkpoint_create,
    cmd_checkpoint_list,
    cmd_dashboard,
    cmd_event_logs,
    cmd_execution_list,
    cmd_execution_run,
    cmd_execution_status,
    cmd_init,
    cmd_project_list,
    cmd_project_show,
    cmd_recover,
    cmd_runtime_add,
    cmd_runtime_catalog_list,
    cmd_runtime_catalog_show,
    cmd_runtime_list,
    cmd_runtime_test,
    cmd_skill_add,
    cmd_skill_list,
    cmd_status,
    cmd_task_create,
    cmd_task_list,
    cmd_task_status,
    cmd_task_update,
    cmd_validate,
    cmd_workflow_add,
    cmd_workflow_list,
    cmd_workflow_run,
    cmd_workflow_status,
)
from .context import DEFAULT_ROOT, FactoryContext

__all__ = ["main", "build_parser"]


def build_parser() -> Any:
    """argparse 树: factory [--root DIR] [--json] <command> ..."""
    import argparse

    p = argparse.ArgumentParser(
        prog="factory",
        description="AI Software Factory — 工厂控制平面 CLI",
    )
    p.add_argument("--root", default=None, help=f"工厂根目录 (默认: {DEFAULT_ROOT})")
    p.add_argument("--json", action="store_true", help="输出 JSON (脚本消费)")
    sub = p.add_subparsers(dest="command", required=True)

    def json_opt(sp: Any) -> None:
        """每个子命令也接受 --json (全局选项须在子命令前, 此处双保险)。

        default 必须为 SUPPRESS: Python 3.12 的 _SubParsersAction.__call__ 会把子解析器
        结果解析进全新 namespace 再整体拷贝回原 namespace — 子解析器任何非 SUPPRESS
        默认值都会无条件覆盖已解析的全局 --json 值。
        """
        sp.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    # factory init
    json_opt(sub.add_parser("init", help="初始化工厂: 目录骨架 + 事件库 (幂等)"))

    # factory task <sub>
    p_task = sub.add_parser("task", help="任务管理")
    json_opt(p_task)
    tsub = p_task.add_subparsers(dest="task_command", required=True)
    p_create = tsub.add_parser("create", help="定义任务 (发 task.created)")
    json_opt(p_create)
    p_create.add_argument("--id", default=None, help="任务 ID (默认自动生成 T-XXX)")
    p_create.add_argument("--title", required=True, help="任务标题")
    p_create.add_argument("--project", default=None, help="项目 (默认 default)")
    p_create.add_argument("--type", default=None, help="任务类型 (默认 feature)")
    p_create.add_argument("--owner", default=None, help="负责人")
    p_create.add_argument("--workflow", default=None, help="工作流 (默认 feature-delivery)")
    p_list = tsub.add_parser("list", help="任务列表 (发 task.viewed)")
    json_opt(p_list)
    p_list.add_argument("--status", default=None, help="按状态过滤 (BACKLOG/ARCHITECTURE/DEVELOPMENT/TESTING/DONE)")
    p_list.add_argument("--project", default=None, help="按项目过滤")
    p_status = tsub.add_parser("status", help="任务详情 + 事件时间线 (发 task.viewed)")
    json_opt(p_status)
    p_status.add_argument("task_id")
    p_update = tsub.add_parser("update", help="更新任务状态 (发 task.updated)")
    json_opt(p_update)
    p_update.add_argument("task_id")
    p_update.add_argument("--status", required=True, help="新状态 (BACKLOG/ARCHITECTURE/DEVELOPMENT/TESTING/DONE)")

    # factory event <sub>
    p_event = sub.add_parser("event", help="事件查询")
    json_opt(p_event)
    esub = p_event.add_subparsers(dest="event_command", required=True)
    p_logs = esub.add_parser("logs", help="事件日志查询, 倒序 (发 system.logs_viewed)")
    json_opt(p_logs)
    p_logs.add_argument("--limit", type=int, default=20, help="条数上限 (默认 20)")
    p_logs.add_argument("--project", default=None, help="按项目过滤")
    p_logs.add_argument("--task", default=None, help="按任务过滤")

    # factory status
    json_opt(sub.add_parser("status", help="工厂总览: Projects/Tasks/Agents/Events 计数 (发 system.status_viewed)"))

    # factory validate
    p_val = sub.add_parser("validate", help="验证任务 — 三层验证引擎 L1/L2/L3 (发 validation.* 事件)")
    json_opt(p_val)
    p_val.add_argument("task_id")
    p_val.add_argument("--level", default="L2", choices=["L1", "L2", "L3"], help="验证级别 (事件标记, 默认 L2)")
    p_val.add_argument("--expect-status", default=None, help="期望状态, 不匹配则验证失败 (退出码 3)")

    # factory agent <sub>
    p_agent = sub.add_parser("agent", help="Agent 管理 (注册表, 发 agent.* 事件)")
    json_opt(p_agent)
    asub = p_agent.add_subparsers(dest="agent_command", required=True)
    p_agent_add = asub.add_parser("add", help="注册 Agent (发 agent.registered)")
    json_opt(p_agent_add)
    p_agent_add.add_argument("--id", required=True, help="Agent ID (如 A-001)")
    p_agent_add.add_argument("--role", required=True, help="角色 (如 backend-developer)")
    p_agent_add.add_argument("--skills", required=True, help="技能列表, 逗号分隔 (如 backend,flutter)")
    p_agent_add.add_argument("--name", default=None, help="显示名 (默认 = id)")
    p_agent_add.add_argument("--description", default=None, help="描述")
    p_agent_list = asub.add_parser("list", help="Agent 列表 (发 agent.viewed)")
    json_opt(p_agent_list)
    p_agent_list.add_argument("--status", default=None, help="按状态过滤 (AVAILABLE/WORKING/OFFLINE)")
    p_agent_list.add_argument("--role", default=None, help="按角色过滤")
    p_agent_list.add_argument("--skill", default=None, help="按技能过滤 (find_by_skill)")
    p_agent_assign = asub.add_parser(
        "assign", help="分配 Agent: 按步骤自动匹配或显式指定 (发 agent.assignment.created)"
    )
    json_opt(p_agent_assign)
    p_agent_assign.add_argument("--task", required=True, help="任务 ID (如 T-001)")
    p_agent_assign.add_argument("--step", default=None, help="工作流步骤 (按 role/skill 自动匹配)")
    p_agent_assign.add_argument("--agent", default=None, help="显式指定 Agent ID (跳过匹配)")
    p_agent_assign.add_argument("--execution", default=None, help="执行请求 ID (回填 agent_id)")
    p_agent_assignments = asub.add_parser("assignments", help="Assignment 列表 (发 agent.assignment.viewed)")
    json_opt(p_agent_assignments)
    p_agent_assignments.add_argument("--task", default=None, help="按任务过滤")
    p_agent_assignments.add_argument("--agent", default=None, help="按 Agent 过滤")
    p_agent_assignments.add_argument("--status", default=None, help="按状态过滤 (ASSIGNED/WORKING/COMPLETED/FAILED/RELEASED)")
    p_agent_release = asub.add_parser(
        "release", help="解除分配: Agent 回 AVAILABLE (发 agent.released)"
    )
    json_opt(p_agent_release)
    p_agent_release.add_argument("assignment_id", help="Assignment ID (如 ASG-001)")

    # factory skill <sub>
    p_skill = sub.add_parser("skill", help="Skill 管理 (能力目录, 发 skill.* 事件)")
    json_opt(p_skill)
    ssub = p_skill.add_subparsers(dest="skill_command", required=True)
    p_skill_add = ssub.add_parser("add", help="注册 Skill (发 skill.registered)")
    json_opt(p_skill_add)
    p_skill_add.add_argument("--id", required=True, help="Skill ID (如 flutter)")
    p_skill_add.add_argument("--category", default="general", help="技能类别 (默认 general)")
    p_skill_add.add_argument("--capabilities", default=None, help="能力列表, 逗号分隔")
    p_skill_add.add_argument("--version", default="1.0.0", help="版本 (默认 1.0.0)")
    p_skill_add.add_argument("--name", default=None, help="技能名 (默认 = id)")
    p_skill_add.add_argument("--description", default=None, help="描述")
    p_skill_list = ssub.add_parser("list", help="Skill 列表 (发 skill.viewed)")
    json_opt(p_skill_list)
    p_skill_list.add_argument("--category", default=None, help="按类别过滤")

    # factory workflow <sub>
    p_workflow = sub.add_parser("workflow", help="工作流管理 (发 workflow.* 事件)")
    json_opt(p_workflow)
    wsub = p_workflow.add_subparsers(dest="workflow_command", required=True)
    p_wf_list = wsub.add_parser("list", help="工作流定义列表 (发 workflow.viewed)")
    json_opt(p_wf_list)
    p_wf_add = wsub.add_parser("add", help="注册工作流定义: 内置或 --steps 自定义 (发 workflow.created)")
    json_opt(p_wf_add)
    p_wf_add.add_argument("--id", required=True, help="工作流 ID (如 feature-delivery)")
    p_wf_add.add_argument("--name", default=None, help="显示名 (默认 = id 或内置名)")
    p_wf_add.add_argument("--description", default=None, help="描述")
    p_wf_add.add_argument("--steps", default=None, help="自定义步骤, 逗号分隔 (省略则用同名内置定义)")
    p_wf_run = wsub.add_parser(
        "run", help="启动任务对应工作流 (发 workflow.started); --auto 自动执行完整链路 (发 orchestration.*)"
    )
    json_opt(p_wf_run)
    p_wf_run.add_argument("task_id")
    p_wf_run.add_argument("--auto", action="store_true",
                          help="自动执行完整链路: 匹配→分配→执行→推进 (失败 → Workflow FAILED)")
    p_wf_status = wsub.add_parser("status", help="任务工作流进度: ✓ 完成 / ▶ 当前 / ○ 待办 (发 workflow.viewed)")
    json_opt(p_wf_status)
    p_wf_status.add_argument("task_id")

    # factory runtime <sub>
    p_runtime = sub.add_parser("runtime", help="Runtime 管理 (适配器注册表, 发 runtime.* 事件)")
    json_opt(p_runtime)
    rsub = p_runtime.add_subparsers(dest="runtime_command", required=True)
    p_rt_add = rsub.add_parser("add", help="注册 Runtime 身份 (发 runtime.registered)")
    json_opt(p_rt_add)
    p_rt_add.add_argument("--id", required=True, help="Runtime ID (如 R-001)")
    p_rt_add.add_argument("--type", default="agent", help="运行时类型 (默认 agent)")
    p_rt_add.add_argument("--name", default=None, help="显示名 (默认 = id)")
    p_rt_add.add_argument("--description", default=None, help="描述")
    p_rt_list = rsub.add_parser("list", help="Runtime 列表 (发 runtime.viewed)")
    json_opt(p_rt_list)
    p_rt_list.add_argument("--status", default=None, help="按状态过滤 (AVAILABLE/DISABLED)")
    p_rt_test = rsub.add_parser(
        "test", help="Runtime smoke test: 内置 Adapter 执行最小 execution (发 runtime.viewed)"
    )
    json_opt(p_rt_test)
    p_rt_test.add_argument("runtime_id", help="Runtime ID (如 hermes-runtime)")
    p_rt_test.add_argument("--instruction", default=None,
                           help="冒烟指令 (默认: Reply with exactly: OK)")
    p_rt_catalog = rsub.add_parser(
        "catalog", help="Runtime 能力目录: 默认定义 hermes/echo/mock + 注册定义 (发 runtime.catalog.viewed)"
    )
    json_opt(p_rt_catalog)
    ctsub = p_rt_catalog.add_subparsers(dest="runtime_catalog_command", required=True)
    p_rt_cat_list = ctsub.add_parser("list", help="Runtime 定义列表 (发 runtime.catalog.viewed)")
    json_opt(p_rt_cat_list)
    p_rt_cat_list.add_argument("--type", default=None, help="按类型过滤 (agent/mock)")
    p_rt_cat_show = ctsub.add_parser("show", help="Runtime 定义详情 (发 runtime.catalog.viewed)")
    json_opt(p_rt_cat_show)
    p_rt_cat_show.add_argument("definition_id", help="定义 ID (如 hermes)")

    # factory execution <sub>
    p_exec = sub.add_parser("execution", help="执行记录查询 (发 execution.viewed)")
    json_opt(p_exec)
    xsub = p_exec.add_subparsers(dest="execution_command", required=True)
    p_ex_list = xsub.add_parser("list", help="执行记录列表 (发 execution.viewed)")
    json_opt(p_ex_list)
    p_ex_list.add_argument("--task", default=None, help="按任务过滤")
    p_ex_run = xsub.add_parser("run", help="执行 pending execution (发 execution.started/completed/failed)")
    json_opt(p_ex_run)
    p_ex_run.add_argument("execution_id", help="执行请求 ID (如 EX-001)")
    p_ex_status = xsub.add_parser("status", help="查看执行状态/结果 (发 execution.viewed)")
    json_opt(p_ex_status)
    p_ex_status.add_argument("execution_id", help="执行请求 ID (如 EX-001)")

    # factory checkpoint <sub>
    p_checkpoint = sub.add_parser(
        "checkpoint", help="Checkpoint 管理: 停靠点快照 (发 recovery.* 事件)"
    )
    json_opt(p_checkpoint)
    csub = p_checkpoint.add_subparsers(dest="checkpoint_command", required=True)
    p_cp_create = csub.add_parser("create", help="创建任务 checkpoint 快照 (发 recovery.started/completed)")
    json_opt(p_cp_create)
    p_cp_create.add_argument("task_id", help="任务 ID (如 T-001)")
    p_cp_list = csub.add_parser("list", help="Checkpoint 列表 (发 recovery.started)")
    json_opt(p_cp_list)

    # factory recover
    p_recover = sub.add_parser(
        "recover", help="恢复中断任务: 事件回放重建 + 状态纠正 (发 recovery.started/completed/failed)"
    )
    json_opt(p_recover)
    p_recover.add_argument("task_id", help="任务 ID (如 T-001)")

    # factory dashboard
    p_dashboard = sub.add_parser(
        "dashboard", help="只读控制台总览: Rich 六视图 (发 dashboard.viewed)"
    )
    json_opt(p_dashboard)
    p_dashboard.add_argument(
        "--view", default="all",
        help="单视图: overview/tasks/agents/workflows/executions/recovery/catalog (默认 all 同屏)",
    )
    p_dashboard.add_argument("--limit", type=int, default=10, help="最近事件条数上限 (默认 10)")
    p_dashboard.add_argument("--project", default=None, help="按项目过滤 (任务/事件维度)")

    # factory project <sub> (Phase 5A: Example Layer, 只读)
    p_project = sub.add_parser("project", help="项目配置 (只读: examples/*/project.yaml)")
    json_opt(p_project)
    prsub = p_project.add_subparsers(dest="project_command", required=True)
    p_pr_list = prsub.add_parser("list", help="项目列表 (发 project.viewed)")
    json_opt(p_pr_list)
    p_pr_show = prsub.add_parser("show", help="项目详情: 技术栈/Agent/技能/工作流映射 (发 project.viewed)")
    json_opt(p_pr_show)
    p_pr_show.add_argument("name", help="项目名 (如 markpad)")

    return p


def main(argv: list[str] | None = None) -> int:
    """CLI 入口: 返回退出码 (console script 以返回值作为进程退出码)。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    ctx = FactoryContext(args.root)
    ctx.ensure_dirs()  # ADR-0002 决策 5: 所有命令幂等自建目录与 DB, 不强制先 init
    try:
        if args.command == "init":
            result = cmd_init(ctx)
        elif args.command == "task":
            result = _dispatch_task(ctx, args)
        elif args.command == "event":
            result = _dispatch_event(ctx, args)
        elif args.command == "status":
            result = cmd_status(ctx)
        elif args.command == "validate":
            result = cmd_validate(ctx, args)
        elif args.command == "agent":
            result = _dispatch_agent(ctx, args)
        elif args.command == "skill":
            result = _dispatch_skill(ctx, args)
        elif args.command == "workflow":
            result = _dispatch_workflow(ctx, args)
        elif args.command == "runtime":
            result = _dispatch_runtime(ctx, args)
        elif args.command == "execution":
            result = _dispatch_execution(ctx, args)
        elif args.command == "checkpoint":
            result = _dispatch_checkpoint(ctx, args)
        elif args.command == "recover":
            result = cmd_recover(ctx, args)
        elif args.command == "dashboard":
            result = cmd_dashboard(ctx, args)
        elif args.command == "project":
            result = _dispatch_project(ctx, args)
        else:  # pragma: no cover — argparse required=True 已拦截
            raise CliError(f"unknown command: {args.command}", exit_code=2)
    except CliError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return exc.exit_code
    except Exception as exc:  # 兜底: 内部异常 → 退出码 1 (cli-design §5)
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    exit_code = int(result.get("exit_code", 0))
    _print_output(args, result)
    return exit_code


def _dispatch_task(ctx: FactoryContext, args: Any) -> dict:
    if args.task_command == "create":
        return cmd_task_create(ctx, args)
    if args.task_command == "list":
        return cmd_task_list(ctx, args)
    if args.task_command == "status":
        return cmd_task_status(ctx, args)
    if args.task_command == "update":
        return cmd_task_update(ctx, args)
    raise CliError(f"unknown task command: {args.task_command}", exit_code=2)


def _dispatch_event(ctx: FactoryContext, args: Any) -> dict:
    if args.event_command == "logs":
        return cmd_event_logs(ctx, args)
    raise CliError(f"unknown event command: {args.event_command}", exit_code=2)


def _dispatch_agent(ctx: FactoryContext, args: Any) -> dict:
    if args.agent_command == "add":
        return cmd_agent_add(ctx, args)
    if args.agent_command == "list":
        return cmd_agent_list(ctx, args)
    if args.agent_command == "assign":
        return cmd_agent_assign(ctx, args)
    if args.agent_command == "assignments":
        return cmd_agent_assignments(ctx, args)
    if args.agent_command == "release":
        return cmd_agent_release(ctx, args)
    raise CliError(f"unknown agent command: {args.agent_command}", exit_code=2)


def _dispatch_skill(ctx: FactoryContext, args: Any) -> dict:
    if args.skill_command == "add":
        return cmd_skill_add(ctx, args)
    if args.skill_command == "list":
        return cmd_skill_list(ctx, args)
    raise CliError(f"unknown skill command: {args.skill_command}", exit_code=2)


def _dispatch_workflow(ctx: FactoryContext, args: Any) -> dict:
    if args.workflow_command == "list":
        return cmd_workflow_list(ctx, args)
    if args.workflow_command == "add":
        return cmd_workflow_add(ctx, args)
    if args.workflow_command == "run":
        return cmd_workflow_run(ctx, args)
    if args.workflow_command == "status":
        return cmd_workflow_status(ctx, args)
    raise CliError(f"unknown workflow command: {args.workflow_command}", exit_code=2)


def _dispatch_runtime(ctx: FactoryContext, args: Any) -> dict:
    if args.runtime_command == "add":
        return cmd_runtime_add(ctx, args)
    if args.runtime_command == "list":
        return cmd_runtime_list(ctx, args)
    if args.runtime_command == "test":
        return cmd_runtime_test(ctx, args)
    if args.runtime_command == "catalog":
        return _dispatch_runtime_catalog(ctx, args)
    raise CliError(f"unknown runtime command: {args.runtime_command}", exit_code=2)


def _dispatch_runtime_catalog(ctx: FactoryContext, args: Any) -> dict:
    if args.runtime_catalog_command == "list":
        return cmd_runtime_catalog_list(ctx, args)
    if args.runtime_catalog_command == "show":
        return cmd_runtime_catalog_show(ctx, args)
    raise CliError(f"unknown runtime catalog command: {args.runtime_catalog_command}", exit_code=2)


def _dispatch_execution(ctx: FactoryContext, args: Any) -> dict:
    if args.execution_command == "list":
        return cmd_execution_list(ctx, args)
    if args.execution_command == "run":
        return cmd_execution_run(ctx, args)
    if args.execution_command == "status":
        return cmd_execution_status(ctx, args)
    raise CliError(f"unknown execution command: {args.execution_command}", exit_code=2)


def _dispatch_checkpoint(ctx: FactoryContext, args: Any) -> dict:
    if args.checkpoint_command == "create":
        return cmd_checkpoint_create(ctx, args)
    if args.checkpoint_command == "list":
        return cmd_checkpoint_list(ctx, args)
    raise CliError(f"unknown checkpoint command: {args.checkpoint_command}", exit_code=2)


def _dispatch_project(ctx: FactoryContext, args: Any) -> dict:
    if args.project_command == "list":
        return cmd_project_list(ctx, args)
    if args.project_command == "show":
        return cmd_project_show(ctx, args)
    raise CliError(f"unknown project command: {args.project_command}", exit_code=2)


# ------------------------------------------------------------------ 输出

def _print_output(args: Any, result: dict) -> None:
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.command == "init":
        _print_init(result)
    elif args.command == "task":
        _print_task(args.task_command, result)
    elif args.command == "event":
        _print_event_logs(result)
    elif args.command == "status":
        _print_status(result)
    elif args.command == "validate":
        _print_validate(result)
    elif args.command == "agent":
        _print_agent(args.agent_command, result)
    elif args.command == "skill":
        _print_skill(args.skill_command, result)
    elif args.command == "workflow":
        _print_workflow(args.workflow_command, result)
    elif args.command == "runtime":
        _print_runtime(args, result)
    elif args.command == "execution":
        _print_execution(args.execution_command, result)
    elif args.command == "checkpoint":
        _print_checkpoint(args.checkpoint_command, result)
    elif args.command == "recover":
        _print_recover(result)
    elif args.command == "dashboard":
        _print_dashboard(result)
    elif args.command == "project":
        _print_project(args.project_command, result)


def _render_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "  (无记录)"
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    lines = [
        "  " + "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)),
        "  " + "  ".join("-" * widths[i] for i in range(len(headers))),
    ]
    lines += ["  " + "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)) for row in rows]
    return "\n".join(lines)


def _print_init(r: dict) -> None:
    print("✔ 初始化完成 (幂等)")
    print(f"  root      {r['root']}")
    print(f"  db        {r['db']}")
    print(f"  dirs      {' '.join(d + '/' for d in r['dirs'])}")
    print(f"  事件      system.init seq={r['event_seq']}")


def _print_task(sub: str, r: dict) -> None:
    if sub == "create":
        t = r["task"]
        print(f"✔ 任务 {t['id']} 已创建 (project: {t['project']})")
        print(f"  title     {t['title']}")
        print(f"  type      {t['type']}")
        print(f"  status    {t['status']}")
        print(f"  owner     {t['owner'] or '-'}")
        print(f"  workflow  {t['workflow'] or '-'}")
    elif sub == "list":
        rows = [[t["id"], t["status"], t["type"], t["project"], t["title"], t["owner"] or "-"]
                for t in r["tasks"]]
        print(_render_table(["Task", "Status", "Type", "Project", "Title", "Owner"], rows))
        print(f"{r['count']} tasks")
    elif sub == "status":
        t = r["task"]
        print(f"{t['id']}  {t['title']}  [{t['type']}]  状态: {t['status']}")
        print(f"  project   {t['project']}")
        print(f"  owner     {t['owner'] or '-'}")
        print(f"  workflow  {t['workflow'] or '-'}")
        print(f"  created   {t['created_at']}")
        print(f"  updated   {t['updated_at']}")
        print("  时间线 (最近 %d 条, 倒序)" % len(r["timeline"]))
        for e in r["timeline"]:
            print(f"    seq {e['seq']:<5} {e['type']:<18} {e['action'] or '-'}")
    elif sub == "update":
        t = r["task"]
        print(f"✔ 任务 {t['id']} 状态已更新 → {t['status']}")


def _print_event_logs(r: dict) -> None:
    rows = [[str(e["seq"]), e["timestamp"], e["type"], e["source"],
             e["task_id"] or "-", e["project_id"] or "-", e["action"] or "-", e["result"] or "-"]
            for e in r["events"]]
    print(_render_table(["seq", "timestamp", "type", "source", "task", "project", "action", "result"], rows))
    print(f"{r['count']} events")


def _print_status(r: dict) -> None:
    print(f"✔ 工厂状态 (root: {r['root']})")
    print(f"  projects  {r['projects_count']}  {r['projects']}")
    print(f"  tasks     {r['tasks_count']}  {r['tasks_by_status']}")
    print(f"  agents    {r['agents_count']}  {r['agents']}")
    print(f"  events    {r['events_count']}")


def _print_validate(r: dict) -> None:
    print(r["report_text"])
    if r["ok"]:
        print("✔ 验证通过 (退出码 0)")
    else:
        print(f"✘ 验证失败: {r['reason']} (退出码 {r['exit_code']})")


def _print_agent(sub: str, r: dict) -> None:
    if sub == "add":
        a = r["agent"]
        print(f"✔ Agent {a['id']} 已注册 (role: {a['role']})")
        print(f"  name        {a['name']}")
        print(f"  status      {a['status']}")
        print(f"  skills      {', '.join(a['skills']) or '-'}")
        print(f"  description {a['description'] or '-'}")
    elif sub == "list":
        rows = [[a["id"], a["name"], a["role"], a["status"], ", ".join(a["skills"]) or "-"]
                for a in r["agents"]]
        print(_render_table(["Agent", "Name", "Role", "Status", "Skills"], rows))
        print(f"{r['count']} agents")
    elif sub == "assign":
        a = r["agent"]
        asg = r["assignment"]
        print(f"Assigned: {a['name'] if a is not None else asg['agent_id']}")
        print(f"  assignment  {asg['id']}")
        print(f"  agent       {asg['agent_id']}  (status: {a['status'] if a is not None else '-'})")
        print(f"  task        {asg['task_id']}")
        print(f"  step        {asg['workflow_step_id'] or '-'}")
        print(f"  status      {asg['status']}")
    elif sub == "assignments":
        rows = [[a["id"], a["agent_id"], a["task_id"], a["workflow_step_id"] or "-", a["status"]]
                for a in r["assignments"]]
        print(_render_table(["Assignment", "Agent", "Task", "Step", "Status"], rows))
        print(f"{r['count']} assignments")
    elif sub == "release":
        asg = r["assignment"]
        print(f"✔ 已释放 {asg['agent_id']} (assignment {asg['id']}) → AVAILABLE")


def _print_skill(sub: str, r: dict) -> None:
    if sub == "add":
        s = r["skill"]
        print(f"✔ Skill {s['id']} 已注册 (category: {s['category']})")
        print(f"  name         {s['name']}")
        print(f"  version      {s['version']}")
        print(f"  capabilities {', '.join(s['capabilities']) or '-'}")
        print(f"  description  {s['description'] or '-'}")
    elif sub == "list":
        rows = [[s["id"], s["name"], s["category"], s["version"], ", ".join(s["capabilities"]) or "-"]
                for s in r["skills"]]
        print(_render_table(["Skill", "Name", "Category", "Version", "Capabilities"], rows))
        print(f"{r['count']} skills")


def _print_workflow(sub: str, r: dict) -> None:
    if sub == "add":
        w = r["workflow"]
        print(f"✔ 工作流 {w['id']} 已注册 ({len(w['steps'])} 步)")
        print(f"  name        {w['name']}")
        print(f"  description {w['description'] or '-'}")
        print(f"  steps       {' → '.join(w['steps'][i]['id'] for i in range(len(w['steps'])))}")
    elif sub == "list":
        rows = [[w["id"], w["name"], " → ".join(w["steps"][i]["id"] for i in range(len(w["steps"])))]
                for w in r["workflows"]]
        print(_render_table(["Workflow", "Name", "Steps"], rows))
        print(f"{r['count']} workflows")
    elif sub == "run":
        if r.get("auto"):
            _print_workflow_run_auto(r)
        else:
            w = r["workflow"]
            print(f"✔ 工作流已启动 (run {r['run']['run_id']})")
            print(f"  Task      {r['task_id']}")
            print(f"  Workflow  {w['id']} — {w['name']}")
            print(f"  Current   {r['current_step'] or '-'}")
    elif sub == "status":
        run = r["run"]
        print(f"{run['run_id']}  {run['workflow_id']} — {run['workflow_name']}  "
              f"任务 {r['task_id']}  状态: {run['status']}")
        for st in r["steps"]:
            print(f"  {st['symbol']} {st['step_id']:<16} {st['status']}")


def _print_workflow_run_auto(r: dict) -> None:
    """workflow run --auto 输出: Workflow/Step/Agent/Runtime/Result (phase4c2-status §3)。"""
    w = r["workflow"]
    if r["status"] == "COMPLETED":
        print(f"✔ 自动执行完成 (run {r['run_id']})")
    else:
        print(f"✘ 自动执行失败 (run {r['run_id'] or '-'})")
    print(f"  Task      {r['task_id']}")
    print(f"  Workflow  {w['id']} — {w['name'] or '-'}")
    print(f"  Status    {r['status']}")
    if r.get("error"):
        print(f"  error     {r['error']}")
    for st in r["steps"]:
        print(f"  Step      {st['step_id']:<16} {st['status']:<10} "
              f"Agent {st['agent_id'] or '-'}  Runtime {st['runtime_id'] or '-'}  "
              f"Result {st['result'] or '-'}  ({st['execution_id'] or '-'})")
    if r["events"]:
        print(f"  事件      {' → '.join(r['events'])}")


def _print_runtime(args: Any, r: dict) -> None:
    sub = args.runtime_command
    if sub == "catalog":
        _print_runtime_catalog(args.runtime_catalog_command, r)
        return
    if sub == "add":
        rt = r["runtime"]
        print(f"✔ Runtime {rt['id']} 已注册 (type: {rt['type']})")
        print(f"  name        {rt['name']}")
        print(f"  status      {rt['status']}")
        print(f"  description {rt['description'] or '-'}")
    elif sub == "list":
        rows = [[rt["id"], rt["name"], rt["type"], rt["status"]] for rt in r["runtimes"]]
        print(_render_table(["Runtime", "Name", "Type", "Status"], rows))
        print(f"{r['count']} runtimes")
    elif sub == "test":
        res = r["result"]
        print(f"Runtime {r['runtime']} smoke: {r['status']}  (execution {r['execution_id']})")
        if res.get("error"):
            print(f"  error    {res['error']}")
        else:
            stdout = (res.get("output") or {}).get("stdout", "")
            print(f"  stdout   {stdout.strip()[:200] or '(empty)'}")


def _print_runtime_catalog(sub: str, r: dict) -> None:
    if sub == "list":
        rows = [
            [d["id"], d["type"], ", ".join(d["capabilities"]) or "-",
             d["version"], d["status"]]
            for d in r["definitions"]
        ]
        print(_render_table(["Runtime", "Type", "Capabilities", "Version", "Status"], rows))
        print(f"{r['count']} definitions")
    elif sub == "show":
        d = r["definition"]
        print(f"{d['id']}  {d['name']}  [{d['type']}]  v{d['version']}  {d['status']}")
        print(f"  description   {d['description'] or '-'}")
        print(f"  capabilities  {', '.join(d['capabilities']) or '-'}")
        print(f"  tasks         {', '.join(d['supported_tasks']) or '-'}")
        if d.get("metadata"):
            print(f"  metadata      {json.dumps(d['metadata'], ensure_ascii=False)}")


def _print_execution(sub: str, r: dict) -> None:
    if sub == "list":
        rows = [
            [e["id"], e["task_id"], e["workflow_id"] or "-", e["step_id"] or "-",
             e["agent_id"] or "-", e["runtime_id"] or "-", e["status"]]
            for e in r["executions"]
        ]
        print(_render_table(["Execution", "Task", "Workflow", "Step", "Agent", "Runtime", "Status"], rows))
        print(f"{r['count']} executions")
    elif sub == "run":
        print(f"✔ 执行 {r['execution_id']} 完成 (runtime: {r['runtime'] or '-'}, status: {r['status']})")
        res = r["result"]
        if res is not None:
            print(f"  result    {res['status']}")
            if res.get("error"):
                print(f"  error     {res['error']}")
            elif res.get("output"):
                print(f"  output    {json.dumps(res['output'], ensure_ascii=False)}")
        wf = r["workflow"]
        if wf["step_completed"]:
            print("  workflow  step completed")
        if wf["workflow_failed"]:
            print("  workflow  run failed")
        if wf.get("error"):
            print(f"  workflow  linkage error: {wf['error']}")
        print(f"  事件      {' → '.join(r['events']) or '-'}")
    elif sub == "status":
        e = r["execution"]
        print(f"{e['id']}  状态: {e['status']}  runtime: {e['runtime_id'] or '-'}")
        print(f"  task      {e['task_id']}")
        print(f"  workflow  {e['workflow_id'] or '-'}  step {e['step_id'] or '-'}")
        print(f"  agent     {e['agent_id'] or '-'}")
        res = r["result"]
        if res is None:
            print("  result    (尚无结果)")
        else:
            print(f"  result    {res['status']}")
            if res.get("error"):
                print(f"  error     {res['error']}")
            elif res.get("output"):
                print(f"  output    {json.dumps(res['output'], ensure_ascii=False)}")


def _print_checkpoint(sub: str, r: dict) -> None:
    if sub == "create":
        c = r["checkpoint"]
        print(f"✔ Checkpoint {c['id']} 已创建 (event_seq: {c['event_seq']})")
        print(f"  task        {c['task_id']}")
        print(f"  workflow    {c['workflow_id'] or '-'}")
        print(f"  current     {c['current_step'] or '-'}")
        if c.get("workflow_state"):
            print(f"  run state   {c['workflow_state'].get('status', '-')}")
    elif sub == "list":
        rows = [
            [c["id"], c["task_id"], c["workflow_id"] or "-", str(c["event_seq"]),
             c["current_step"] or "-", c["created_at"]]
            for c in r["checkpoints"]
        ]
        print(_render_table(["Checkpoint", "Task", "Workflow", "EventSeq", "CurrentStep", "CreatedAt"], rows))
        print(f"{r['count']} checkpoints")


def _print_recover(r: dict) -> None:
    rec = r["recovery"]
    if rec["resume_ok"]:
        print(f"✔ 恢复完成 (task {rec['task_id']}) — 可继续")
    else:
        print(f"✘ 恢复被拒绝 (task {rec['task_id']}) — 不可继续")
    print(f"  Last Event  {rec['last_event']}")
    print(f"  State       {rec['state']}")
    print(f"  Resume      {rec['resume_ok']}")
    for action in rec["actions"]:
        print(f"  action      {action}")


def _print_dashboard(r: dict) -> None:
    from dashboard.models import FactorySnapshot
    from dashboard.renderer import DashboardRenderer

    snapshot = FactorySnapshot.model_validate(r["snapshot"])
    print(DashboardRenderer().render(snapshot, view=r.get("view") or "all"))


def _print_project(sub: str, r: dict) -> None:
    if sub == "list":
        rows = [[p["name"], p["language"], p["repository"] or "-",
                 ", ".join(p["tech_stack"]) or "-"] for p in r["projects"]]
        print(_render_table(["Project", "Language", "Repository", "Tech Stack"], rows))
        print(f"{r['count']} projects (examples: {r['examples_dir']})")
    elif sub == "show":
        p = r["project"]
        print(f"{p['name']}  {p['description'] or ''}")
        print(f"  language    {p['language']}")
        print(f"  repository  {p['repository'] or '-'}")
        print(f"  tech_stack  {', '.join(p['tech_stack']) or '-'}")
        print(f"  agents      {len(r['agents'])}")
        for a in r["agents"]:
            print(f"    {a['id']:<20} role={a['role']:<15} skills={', '.join(a['skills']) or '-'}")
        print(f"  skills      {len(r['skills'])}")
        for s in r["skills"]:
            print(f"    {s['id']:<20} category={s['category']:<12} "
                  f"{', '.join(s['capabilities']) or '-'}")
        print(f"  workflows   {len(r['workflows'])}")
        for w in r["workflows"]:
            steps = " → ".join(st["id"] for st in w["steps"])
            print(f"    {w['id']:<20} {w['name'] or '-'}  [{steps}]")


if __name__ == "__main__":
    sys.exit(main())
