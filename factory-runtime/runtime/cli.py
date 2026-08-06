"""runtime/cli.py — factory-runtime CLI (start/stop/status/restart/logs/init)。

独立包入口 (console script: factory-runtime = "runtime.cli:main"):
- 轻量/延迟 import: 无 Core 依赖; RuntimeManager 在命令分发时才装配。
- 退出码: 0 成功 / 1 运行时错误 (RuntimeError) / 2 用法 (argparse SystemExit)。

命令:
  init     初始化数据目录 (7 子目录 + token + 状态文件)
  start    启动 Core + Console (健康通过报 ready; --port/--factory-cmd/--console-cmd 可注入)
  stop     逆序 graceful 停止 (幂等)
  restart  stop + start
  status   状态 (state 文件 + 活进程; --json)
  logs     查看 logs/runtime.log|core.log|console.log 尾部 (--lines N)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .errors import RuntimeError
from .logging import CONSOLE_LOG, CORE_LOG, RUNTIME_LOG, logs_dir
from .paths import SUBDIRS, default_data_dir, ensure_data_root
from .state import RuntimeState, save_state

_LOG_FILES = (RUNTIME_LOG, CORE_LOG, CONSOLE_LOG)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="factory-runtime",
        description="AI Software Factory Product Runtime (Phase 15A-1)",
    )
    parser.add_argument(
        "--root",
        default=str(default_data_dir()),
        help="runtime 数据根 (默认: 平台规范目录)",
    )
    parser.add_argument("--json", action="store_true", help="JSON 结构化输出")
    sub = parser.add_subparsers(dest="command", required=True)

    cmd_init = sub.add_parser("init", help="初始化数据目录 (7 子目录 + token + 状态文件)")
    cmd_init.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help="JSON 输出"
    )

    cmd_start = sub.add_parser("start", help="启动 Core + Console")
    cmd_start.add_argument("--port", type=int, default=0, help="Console 端口 (0 = 动态分配)")
    cmd_start.add_argument("--factory-cmd", default=None, help="Core 启动命令 (默认: factory)")
    cmd_start.add_argument("--console-cmd", default=None, help="Console 启动命令 (支持 {port})")
    cmd_start.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help="JSON 输出"
    )

    sub.add_parser("stop", help="停止 (Console → Core 逆序 graceful)")
    cmd_restart = sub.add_parser("restart", help="stop + start")
    cmd_restart.add_argument("--port", type=int, default=0, help="Console 端口 (0 = 动态分配)")
    cmd_restart.add_argument("--factory-cmd", default=None, help="Core 启动命令 (默认: factory)")
    cmd_restart.add_argument("--console-cmd", default=None, help="Console 启动命令 (支持 {port})")
    cmd_restart.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help="JSON 输出"
    )

    cmd_status = sub.add_parser("status", help="查看状态")
    cmd_status.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help="JSON 输出"
    )

    cmd_logs = sub.add_parser("logs", help="查看日志尾部")
    cmd_logs.add_argument("--lines", type=int, default=50, help="每个文件行数 (默认 50)")
    cmd_logs.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help="JSON 输出"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 入口 (console script 直接以返回值作进程退出码)。"""
    args = build_parser().parse_args(argv)
    try:
        return _dispatch(args)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


def _dispatch(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser()
    use_json = bool(args.json)
    command = args.command

    if command == "init":
        ensure_data_root(root)
        from .manager import RuntimeManager  # 延迟 (token 写入复用)

        mgr = RuntimeManager(root)
        mgr._write_token()  # noqa: SLF001 — init 预生成 token (600)
        save_state(RuntimeState(status="idle", version=__version__), root)
        if use_json:
            print(json.dumps({"root": str(root), "status": "idle", "subdirs": list(SUBDIRS)}))
        else:
            print(f"initialized: {root}")
            print(f"subdirs: {', '.join(SUBDIRS)}")
            print("status: idle")
        return 0

    if command in ("start", "stop", "restart", "status"):
        from .manager import RuntimeManager

        kwargs = {}
        if command in ("start", "restart"):
            if args.port:
                kwargs["console_port"] = args.port
            if args.factory_cmd:
                kwargs["factory_cmd"] = args.factory_cmd
            if args.console_cmd:
                kwargs["console_cmd"] = args.console_cmd
        mgr = RuntimeManager(root, **kwargs)
        if command == "start":
            status = mgr.start()
        elif command == "stop":
            status = mgr.stop()
        elif command == "restart":
            status = mgr.restart()
        else:
            status = mgr.status()
        _print_status(status, use_json)
        return 0

    if command == "logs":
        return _cmd_logs(root, args.lines, use_json)

    return 2  # 不可达 (argparse required=True)


def _print_status(status: dict, use_json: bool) -> None:
    if use_json:
        print(json.dumps(status, ensure_ascii=False))
        return
    print(f"status:    {status['status']}")
    print(f"pid:       {status['pid']}")
    print(f"port:      {status['port']}")
    print(f"version:   {status['version']}")
    print(f"started:   {status['started_at']}")
    print(f"stopped:   {status['stopped_at']}")
    print(f"core:      {'alive' if status['core_alive'] else 'down'}")
    print(f"console:   {'alive' if status['console_alive'] else 'down'}")


def _cmd_logs(root: Path, lines: int, use_json: bool) -> int:
    d = logs_dir(root)
    files: dict[str, list[str]] = {}
    for name in _LOG_FILES:
        path = d / name
        if not path.exists():
            files[name] = []
            continue
        with open(path, encoding="utf-8", errors="replace") as fh:
            tail = fh.readlines()[-lines:]
        files[name] = [line.rstrip("\n") for line in tail]
    if use_json:
        print(json.dumps({"root": str(root), "files": files}, ensure_ascii=False))
        return 0
    for name in _LOG_FILES:
        print(f"== {name} ==")
        for line in files[name]:
            print(line)
    return 0


if __name__ == "__main__":  # pragma: no cover — python -m runtime.cli 入口
    sys.exit(main())
