"""tests/factory_runtime/test_frt_logging.py — 日志模块 (三文件/轮转/事件)。

重点: runtime.log/core.log/console.log 三文件 / 事件记录 / 轮转 (Rotating +
子进程预轮转) / 单例重置。
"""

from __future__ import annotations

from logging.handlers import RotatingFileHandler
from pathlib import Path


def test_setup_creates_runtime_log(rt_pkg, frt_root):
    logger = rt_pkg.logging.setup_runtime_logger(frt_root)
    assert logger is not None
    assert (frt_root / "logs" / "runtime.log").exists()


def test_three_files_created(rt_pkg, frt_root):
    rt_pkg.logging.setup_runtime_logger(frt_root)
    rt_pkg.logging.open_child_log(frt_root, rt_pkg.logging.CORE_LOG)
    rt_pkg.logging.open_child_log(frt_root, rt_pkg.logging.CONSOLE_LOG)
    d = frt_root / "logs"
    assert (d / "runtime.log").exists()
    assert (d / "core.log").exists()
    assert (d / "console.log").exists()


def test_logs_dir_created(rt_pkg, frt_root):
    rt_pkg.logging.setup_runtime_logger(frt_root)
    assert (frt_root / "logs").is_dir()


def test_log_event_recorded(rt_pkg, frt_root):
    logger = rt_pkg.logging.setup_runtime_logger(frt_root)
    rt_pkg.logging.log_event(logger, "started")
    text = (frt_root / "logs" / "runtime.log").read_text()
    assert "started" in text


def test_log_event_with_detail(rt_pkg, frt_root):
    logger = rt_pkg.logging.setup_runtime_logger(frt_root)
    rt_pkg.logging.log_event(logger, "restart", "core exited code=1")
    text = (frt_root / "logs" / "runtime.log").read_text()
    assert "restart — core exited code=1" in text


def test_log_event_markers(rt_pkg, frt_root):
    """事件可定位: 启动失败/子进程退出/health timeout/restart 各有标记。"""
    logger = rt_pkg.logging.setup_runtime_logger(frt_root)
    for event in ("startup failed", "child exited", "health timeout", "restart"):
        rt_pkg.logging.log_event(logger, event)
    text = (frt_root / "logs" / "runtime.log").read_text()
    for event in ("startup failed", "child exited", "health timeout", "restart"):
        assert event in text


def test_runtime_rotation(rt_pkg, frt_root):
    logger = rt_pkg.logging.setup_runtime_logger(frt_root, max_bytes=300, backup_count=2)
    for _ in range(20):
        logger.info("x" * 100)
    d = frt_root / "logs"
    assert (d / "runtime.log.1").exists()


def test_child_log_prerotation(rt_pkg, frt_root):
    path = frt_root / "logs" / "core.log"
    path.parent.mkdir(parents=True)
    path.write_text("y" * 2000)
    result = rt_pkg.logging.open_child_log(frt_root, "core.log", max_bytes=1000)
    assert result == path
    assert (frt_root / "logs" / "core.log.1").exists()


def test_open_child_log_creates_file(rt_pkg, frt_root):
    path = rt_pkg.logging.open_child_log(frt_root, "console.log")
    assert path == frt_root / "logs" / "console.log"
    assert path.parent.is_dir()


def test_logger_propagate_false(rt_pkg, frt_root):
    logger = rt_pkg.logging.setup_runtime_logger(frt_root)
    assert logger.propagate is False


def test_reset_removes_handlers(rt_pkg, frt_root):
    logger = rt_pkg.logging.setup_runtime_logger(frt_root)
    assert any(
        isinstance(h, RotatingFileHandler)
        and h.baseFilename == str(frt_root / "logs" / "runtime.log")
        for h in logger.handlers
    )
    rt_pkg.logging.reset_runtime_logger()
    assert not any(isinstance(h, RotatingFileHandler) for h in logger.handlers)


def test_reset_allows_new_root(rt_pkg, frt_root, tmp_path):
    rt_pkg.logging.setup_runtime_logger(frt_root)
    rt_pkg.logging.reset_runtime_logger()
    root2 = tmp_path / "root2"
    logger2 = rt_pkg.logging.setup_runtime_logger(root2)
    rt_pkg.logging.log_event(logger2, "started")
    assert (root2 / "logs" / "runtime.log").exists()
    assert (frt_root / "logs" / "runtime.log").exists()  # 旧文件不动


def test_default_constants(rt_pkg):
    assert rt_pkg.logging.DEFAULT_MAX_BYTES == 1_000_000
    assert rt_pkg.logging.DEFAULT_BACKUP_COUNT == 3
    assert rt_pkg.logging.LOG_RELPATH == Path("logs")


def test_singleton_same_logger(rt_pkg, frt_root):
    a = rt_pkg.logging.setup_runtime_logger(frt_root)
    b = rt_pkg.logging.setup_runtime_logger(frt_root)
    assert a is b
