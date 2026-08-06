"""runtime/logging.py — 日志管理 (三文件 + 轮转 + 事件记录)。

文件 (phase15-runtime-design.md §3 日志查看):
    <data_root>/logs/runtime.log    runtime 自身事件 (可定位)
    <data_root>/logs/core.log       Core 子进程输出 (stdout+stderr)
    <data_root>/logs/console.log    Console 子进程输出

事件 (runtime.log, 供测试/运维定位):
    start / started / stopping / stopped / failed /
    core started / console started / child exited /
    health timeout / startup failed / restart / restart failed /
    watchdog limit reached / stop (not running)

轮转: runtime.log 用 RotatingFileHandler (maxBytes + backupCount);
core/console 子进程日志在 spawn 前预轮转 (超限 → .1, 丢弃最旧) —
子进程 stdout 是继承的文件描述符, 无法由父进程按行轮转。
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_RELPATH = Path("logs")
RUNTIME_LOG = "runtime.log"
CORE_LOG = "core.log"
CONSOLE_LOG = "console.log"

#: 单文件轮转阈值 (字节) / 保留备份数
DEFAULT_MAX_BYTES = 1_000_000
DEFAULT_BACKUP_COUNT = 3

#: 进程级单例 (每进程一个 runtime logger; 测试经 reset_runtime_logger 重置)
_runtime_logger: logging.Logger | None = None
_runtime_handler: RotatingFileHandler | None = None


def logs_dir(data_root: str | Path) -> Path:
    """日志目录 (<data_root>/logs)。"""
    return Path(data_root) / LOG_RELPATH


def setup_runtime_logger(
    data_root: str | Path,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> logging.Logger:
    """装配 runtime.log (RotatingFileHandler, 单例)。"""
    global _runtime_logger, _runtime_handler
    if _runtime_logger is not None:
        return _runtime_logger
    d = logs_dir(data_root)
    d.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("factory.runtime")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        d / RUNTIME_LOG,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False  # 不泄漏到根 logger
    _runtime_logger = logger
    _runtime_handler = handler
    return logger


def reset_runtime_logger() -> None:
    """关闭并清空单例 (测试隔离用)。"""
    global _runtime_logger, _runtime_handler
    if _runtime_logger is not None and _runtime_handler is not None:
        try:
            _runtime_handler.close()
            _runtime_logger.removeHandler(_runtime_handler)
        except (OSError, ValueError):
            pass
    _runtime_logger = None
    _runtime_handler = None


def log_event(logger: logging.Logger, event: str, detail: str = "") -> None:
    """记录可定位事件: `event — detail` (detail 可空)。"""
    message = event if not detail else f"{event} — {detail}"
    logger.info(message)


def open_child_log(
    data_root: str | Path,
    name: str,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> Path:
    """子进程日志文件路径: 超限先预轮转 (path → path.1), 返回文件路径。

    调用方以 append 模式打开并传给 Popen stdout/stderr。
    """
    d = logs_dir(data_root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / name
    try:
        if path.exists() and path.stat().st_size >= max_bytes:
            backup = path.with_suffix(path.suffix + ".1")
            if backup.exists():
                backup.unlink()
            path.rename(backup)
    except OSError:
        pass
    # 保证文件存在 (三文件契约: 启动前即就位)
    try:
        path.touch(exist_ok=True)
    except OSError:
        pass
    return path
