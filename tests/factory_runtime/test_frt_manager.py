"""tests/factory_runtime/test_frt_manager.py — RuntimeManager 生命周期。

重点: start 成功 (ready/port/pid) / stop 成功 / restart / 健康失败 (timeout →
failed) / 启动期 Core 退出 / 强杀 / token (600, 日志脱敏) / 状态文件。
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from frt_helpers import pid_alive, wait_until


def _fast(mgr_kwargs: dict | None = None) -> dict:
    """测试用快参数 (健康等待/终止超时收紧, 避免慢启动)。"""
    kw = {
        "health_timeout": 8.0,
        "health_interval": 0.1,
        "terminate_timeout": 1.0,
        "watchdog_interval": 0.2,
    }
    if mgr_kwargs:
        kw.update(mgr_kwargs)
    return kw


def test_start_ready_state(rt_pkg, manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    st = mgr.start()
    assert st["status"] == "ready"
    assert st["port"] and st["port"] > 0
    assert st["pid"] == os.getpid()
    assert st["core_alive"] is True
    assert st["console_alive"] is True
    state = rt_pkg.state.load_state(frt_root)
    assert state.status == "ready"
    assert state.version == "0.1.0"
    assert state.port == st["port"]


def test_start_creates_dirs_and_files(rt_pkg, manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    assert (frt_root / "config" / "runtime_state.json").exists()
    assert (frt_root / "logs" / "runtime.log").exists()
    assert (frt_root / "logs" / "core.log").exists()
    assert (frt_root / "logs" / "console.log").exists()


def test_start_writes_token_file_600(manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    token_path = frt_root / "config" / "runtime_token"
    assert token_path.exists()
    token = token_path.read_text().strip()
    assert len(token) >= 64  # secrets.token_hex(32)
    if os.name == "posix":
        assert stat.S_IMODE(token_path.stat().st_mode) == 0o600


def test_start_token_masked_in_log(manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    token = (frt_root / "config" / "runtime_token").read_text().strip()
    log_text = (frt_root / "logs" / "runtime.log").read_text()
    assert token not in log_text  # 脱敏: 完整 token 绝不入日志
    assert token[:8] in log_text  # 掩码前缀 (可定位)


def test_start_dynamic_port(manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    st = mgr.start()
    assert st["port"] != 0
    assert mgr.console_port == st["port"]


def test_start_fixed_port(rt_pkg, manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    port = rt_pkg.manager._pick_free_port()
    mgr = manager_factory(
        frt_root,
        factory_cmd=fake_core_cmd,
        console_cmd=fake_console_cmd,
        console_port=port,
        **_fast(),
    )
    st = mgr.start()
    assert st["port"] == port


def test_start_already_running_raises(rt_pkg, manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    with pytest.raises(rt_pkg.RuntimeError, match="already running"):
        mgr.start()


def test_stop_success(manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    core_pid = mgr.core_proc.pid
    console_pid = mgr.console_proc.pid
    st = mgr.stop()
    assert st["status"] == "stopped"
    assert mgr.core_proc is None and mgr.console_proc is None
    assert not pid_alive(core_pid)
    assert not pid_alive(console_pid)


def test_stop_idempotent(rt_pkg, manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    mgr.stop()
    st = mgr.stop()  # 二次 stop 零异常
    assert st["status"] == "stopped"


def test_restart(manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    first_core_pid = mgr.core_proc.pid
    st = mgr.restart()
    assert st["status"] == "ready"
    assert mgr.core_proc is not None
    assert mgr.core_proc.pid != first_core_pid


def test_start_health_timeout_failed(rt_pkg, manager_factory, frt_root, fake_core_cmd, fake_console_slow_cmd):
    mgr = manager_factory(
        frt_root,
        factory_cmd=fake_core_cmd,
        console_cmd=fake_console_slow_cmd,
        **_fast({"health_timeout": 1.0, "terminate_timeout": 0.5}),
    )
    with pytest.raises(rt_pkg.RuntimeError, match="health timeout"):
        mgr.start()
    state = rt_pkg.state.load_state(frt_root)
    assert state.status == "failed"
    assert mgr.core_proc is None  # 子进程已清理
    log_text = (frt_root / "logs" / "runtime.log").read_text()
    assert "health timeout" in log_text


def test_start_core_exit_during_startup_failed(
    rt_pkg, manager_factory, frt_root, fake_core_exit_now, fake_console_cmd
):
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_exit_now, console_cmd=fake_console_cmd, **_fast()
    )
    with pytest.raises(rt_pkg.RuntimeError, match="startup failed"):
        mgr.start()
    state = rt_pkg.state.load_state(frt_root)
    assert state.status == "failed"
    log_text = (frt_root / "logs" / "runtime.log").read_text()
    assert "startup failed" in log_text


def test_stop_force_kill(manager_factory, frt_root, fake_core_ignore_term, fake_console_cmd):
    mgr = manager_factory(
        frt_root,
        factory_cmd=fake_core_ignore_term,
        console_cmd=fake_console_cmd,
        **_fast({"terminate_timeout": 0.3}),
    )
    mgr.start()
    core_pid = mgr.core_proc.pid
    mgr.stop()  # SIGTERM 被忽略 → 超时 → SIGKILL
    assert not pid_alive(core_pid)
    assert mgr.core_proc is None


def test_status_before_start(manager_factory, frt_root):
    mgr = manager_factory(frt_root)
    st = mgr.status()
    assert st["status"] == "idle"
    assert st["core_alive"] is False
    assert st["console_alive"] is False


def test_start_stale_ready_state_dead_pid(rt_pkg, manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    """状态文件残留 ready + pid 已死 → start 应继续 (跨进程崩溃恢复)。"""
    stale = rt_pkg.state.RuntimeState(pid=999999, port=1, status="ready", version="0.1.0")
    rt_pkg.state.save_state(stale, frt_root)
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    st = mgr.start()
    assert st["status"] == "ready"


def test_factory_cmd_str_shlex(manager_factory, frt_root, fake_core_cmd, fake_console_cmd, tmp_path):
    """factory_cmd 支持 str 形态 (shlex.split)。"""
    script = tmp_path / "fake_core.py"
    script.write_text("import time\ntime.sleep(600)")
    mgr = manager_factory(
        frt_root,
        factory_cmd=f"{sys.executable} {script}",
        console_cmd=fake_console_cmd,
        **_fast(),
    )
    st = mgr.start()
    assert st["status"] == "ready"


def test_console_cmd_placeholder(rt_pkg, manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    """console_cmd 的 {port} 占位符被替换为实际端口。"""
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    st = mgr.start()
    assert st["port"] == mgr.console_port
    # 新 console 进程确实在监听该端口 (health 已隐含, 再显式确认)
    assert (
        rt_pkg.health.check_console(f"http://127.0.0.1:{st['port']}", timeout=2.0) is True
    )


def test_stop_after_failed_start(rt_pkg, manager_factory, frt_root, fake_core_cmd, fake_console_slow_cmd):
    mgr = manager_factory(
        frt_root,
        factory_cmd=fake_core_cmd,
        console_cmd=fake_console_slow_cmd,
        **_fast({"health_timeout": 0.8, "terminate_timeout": 0.5}),
    )
    with pytest.raises(rt_pkg.RuntimeError):
        mgr.start()
    st = mgr.stop()  # failed 态 stop 不抛
    assert st["status"] == "stopped"


def test_version_in_state(rt_pkg, manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    assert rt_pkg.state.load_state(frt_root).version == rt_pkg.__version__


def test_watchdog_attached_after_start(manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    assert mgr._watchdog is not None
    assert mgr._watchdog.max_restarts == 3
    mgr.stop()
    assert mgr._watchdog is None


def test_pid_files_written_on_start(manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    core_pid = int((frt_root / "config" / "core.pid").read_text().strip())
    console_pid = int((frt_root / "config" / "console.pid").read_text().strip())
    assert core_pid == mgr.core_proc.pid
    assert console_pid == mgr.console_proc.pid
    assert pid_alive(core_pid) and pid_alive(console_pid)


def test_stop_removes_pid_files(manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    mgr.stop()
    assert not (frt_root / "config" / "core.pid").exists()
    assert not (frt_root / "config" / "console.pid").exists()


def test_status_cross_process_via_pid_files(
    rt_pkg, manager_factory, frt_root, fake_core_cmd, fake_console_cmd
):
    """跨进程视角: 新实例无 proc 引用 → status/stop 经 pid 文件生效。"""
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    other = rt_pkg.manager.RuntimeManager(frt_root)  # 模拟新进程
    st = other.status()
    assert st["status"] == "ready"
    assert st["core_alive"] is True
    assert st["console_alive"] is True
    other.stop()  # 跨进程 stop 经 pid 文件终止子进程
    assert not (frt_root / "config" / "core.pid").exists()
    assert not pid_alive(mgr.core_proc.pid)
