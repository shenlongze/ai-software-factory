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

from .commands import CliError, cmd_event_logs, cmd_init, cmd_status, cmd_task_create, cmd_task_list, cmd_task_status, cmd_task_update, cmd_validate
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


if __name__ == "__main__":
    sys.exit(main())
