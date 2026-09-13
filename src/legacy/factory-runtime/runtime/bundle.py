"""runtime/bundle.py — PyInstaller frozen bundle 感知 (Phase 15A-3c-2)。

设计依据: phase15-runtime-design.md §2/§3 (PyInstaller 捆绑分发) +
15A-3c-2 任务书 (bundle 内 RuntimeManager spawn 子进程用
[sys.executable, "__core"|"__console", ...] — frozen 下 sys.executable
= bundle 可执行文件路径)。

本模块只做两件事 (KISS, 零业务逻辑):
1. `is_frozen()` — 运行时环境探测 (PyInstaller frozen / 普通 venv)。
2. spawn argv 工厂 — Core/Console 子进程命令:
   - frozen:  [sys.executable, "__core"] /
              [sys.executable, "__console", "--host", …, "--port", …]
     (__core/__console 由 runtime/cli.py main() 内部路由, 见该模块)
   - 非 frozen: 返回 None → RuntimeManager 走原有 subprocess 逻辑
     (factory CLI / uvicorn 模板), 零行为变化。

禁止: 本模块不 import factory-core / factory-console 任何内部 —
仅字符串拼接; 路由逻辑在 cli.py, 收集逻辑在 bundle spec (hidden imports)。
"""

from __future__ import annotations

import sys

#: bundle 内部子命令标记 (argv[0] 位置, 经 runtime.cli.main 路由)
CORE_MARKER = "__core"
CONSOLE_MARKER = "__console"


def is_frozen() -> bool:
    """PyInstaller frozen 环境探测 (sys.frozen 存在且为真)。"""
    return bool(getattr(sys, "frozen", False))


def core_spawn_argv() -> list[str] | None:
    """Core 子进程 spawn argv: frozen → [sys.executable, "__core"]; 否则 None。"""
    if is_frozen():
        return [sys.executable, CORE_MARKER]
    return None


def console_spawn_argv(port: int) -> list[str] | None:
    """Console 子进程 spawn argv: frozen → bundle __console 路由; 否则 None。

    __console 路由参数与 uvicorn CLI 同构 (--host/--port), 见 cli.py。
    """
    if is_frozen():
        return [sys.executable, CONSOLE_MARKER, "--host", "127.0.0.1", "--port", str(port)]
    return None


def is_bundle_marker(argv0: str) -> bool:
    """argv[0] 是否为 bundle 内部子命令标记 (路由判定用)。"""
    return argv0 in (CORE_MARKER, CONSOLE_MARKER)
