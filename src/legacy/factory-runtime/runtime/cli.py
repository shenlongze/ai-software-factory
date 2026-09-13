"""runtime/cli.py — factory-runtime CLI (start/stop/status/restart/logs/init)。

独立包入口 (console script: factory-runtime = "runtime.cli:main"):
- 轻量/延迟 import: 无 Core 依赖; RuntimeManager 在命令分发时才装配。
- 退出码: 0 成功 / 1 运行时错误 (RuntimeError) / 2 用法 (argparse SystemExit)。

命令:
  init     初始化数据目录 (7 子目录 + token + 状态文件)
  start    启动 Console 常驻服务 (managed service; 健康通过报 ready;
           --port/--factory-cmd/--console-cmd 可注入)
  stop     Console graceful 停止 (幂等)
  restart  stop + start
  status   状态 (state 文件 + Console service health + Core command availability; --json)
  logs     查看 logs/runtime.log|core.log|console.log 尾部 (--lines N)

bundle 内部路由 (仅 PyInstaller frozen, 15A-3c-2):
  argv[0] == "__core"     → 转发 factory-core CLI (bundle 已收集, 延迟 import)
  argv[0] == "__console"  → 转发 uvicorn + fastapi_adapter (同 uvicorn 参数形态)
  RuntimeManager 在 frozen 下 spawn [sys.executable, "__core"|"__console", …],
  sys.executable = bundle 路径 (runtime/bundle.py 生成 argv)。非 frozen 下
  本路由不激活 — 原 factory CLI / uvicorn 子进程逻辑保持。
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

    cmd_start = sub.add_parser("start", help="启动 Console 常驻服务 (Core 命令执行器)")
    cmd_start.add_argument("--port", type=int, default=0, help="Console 端口 (0 = 动态分配)")
    cmd_start.add_argument("--factory-cmd", default=None, help="Core 命令 (命令执行/可用性检查; 默认: factory)")
    cmd_start.add_argument("--console-cmd", default=None, help="Console 启动命令 (支持 {port})")
    cmd_start.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help="JSON 输出"
    )

    sub.add_parser("stop", help="停止 (Console graceful)")
    cmd_restart = sub.add_parser("restart", help="stop + start")
    cmd_restart.add_argument("--port", type=int, default=0, help="Console 端口 (0 = 动态分配)")
    cmd_restart.add_argument("--factory-cmd", default=None, help="Core 命令 (命令执行/可用性检查; 默认: factory)")
    cmd_restart.add_argument("--console-cmd", default=None, help="Console 启动命令 (支持 {port})")
    cmd_restart.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help="JSON 输出"
    )

    cmd_status = sub.add_parser("status", help="查看状态 (runtime + console service + core command)")
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
    """CLI 入口 (console script 直接以返回值作进程退出码)。

    bundle 内部路由优先: frozen + argv[0] == __core/__console → 转发
    Core/Console (15A-3c-2); 否则标准 factory-runtime CLI 分发。
    """
    argv_list = list(sys.argv[1:] if argv is None else argv)
    routed = _bundle_route(argv_list)
    if routed is not None:
        return routed
    args = build_parser().parse_args(argv_list)
    try:
        return _dispatch(args)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


def _bundle_route(argv: list[str]) -> int | None:
    """bundle 内部子命令路由: __core/__console → 退出码; 否则 None。

    仅 frozen 激活 (非 frozen 下 argv[0] 是普通 runtime 命令, 不拦截);
    返回 None 表示继续走标准 CLI 分发。
    """
    if not argv or not getattr(sys, "frozen", False):
        return None
    marker = argv[0]
    if marker == "__core":
        return _run_core(argv[1:])
    if marker == "__console":
        return _run_console(argv[1:])
    return None


def _run_core(core_argv: list[str]) -> int:
    """转发 factory-core CLI (bundle 已收集; 延迟 import 保 Removal Isolation)。

    失败安全: 收集缺失 → 用户语言错误 + 退出码 1 (Desktop 可展示)。
    """
    try:
        from cli.main import main as _core_main  # type: ignore[import-not-found]
    except Exception as exc:
        print(f"error: factory-core 不可用: {exc}", file=sys.stderr)
        return 1
    return _core_main(core_argv)


def _run_console(console_argv: list[str]) -> int:
    """转发 uvicorn + factory-console fastapi_adapter (bundle 已收集)。

    参数与 uvicorn CLI 同构 (--host/--port; 其余忽略); 阻塞直到退出 —
    与 uvicorn 子进程语义一致 (RuntimeManager SIGTERM 停止)。
    """
    parser = argparse.ArgumentParser(prog="factory-runtime-bundle __console")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址 (默认回环)")
    parser.add_argument("--port", type=int, default=8011, help="监听端口")
    ns, _ = parser.parse_known_args(console_argv)
    try:
        from fastapi_adapter import create_app  # type: ignore[import-not-found]
    except Exception as exc:
        print(f"error: factory-console 不可用: {exc}", file=sys.stderr)
        return 1
    try:
        import uvicorn
    except Exception as exc:
        print(f"error: uvicorn 不可用: {exc}", file=sys.stderr)
        return 1
    uvicorn.run(create_app(), host=ns.host, port=ns.port)
    return 0


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
    print(f"core:      {'available' if status['core_alive'] else 'unavailable'} (command)")
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
