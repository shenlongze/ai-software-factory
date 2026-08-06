"""tests/factory_runtime/test_frt_manager.py — RuntimeManager 生命周期。

架构裁决 B (Core Command Model):
- start: init datadir → Console (managed service) 常驻 → 健康等待 → ready
- Core 非 daemon: 命令执行器 (run_command / 可用性检查), 退出是预期
- Core 命令失败 ≠ Runtime 崩溃 (start 只依赖 Console service)
- status = runtime 状态 + console service health + core command availability

重点: start 成功 (ready/port/pid) / stop 成功 / restart / 健康失败 (timeout →
failed) / 强杀 / token (600, 日志脱敏) / 状态文件 / 跨进程 pid 文件。
"""

from __future__ import annotations

import os
import stat
import sys
import time
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
    # Console service 存活 = healthy (唯一常驻验证点)
    assert st["console_alive"] is True
    assert st["console_healthy"] is True
    # Core = 命令可用性 (fake core --help → 0); 非 daemon → 无退出码
    assert st["core_alive"] is True
    assert st["core_available"] is True
    assert st["core_exit_code"] is None
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
    console_pid = mgr.console_proc.pid
    st = mgr.stop()
    assert st["status"] == "stopped"
    assert mgr.console_proc is None
    assert mgr.core_proc is None  # Core 非 daemon, 恒 None
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
    first_console_pid = mgr.console_proc.pid
    st = mgr.restart()
    assert st["status"] == "ready"
    assert mgr.console_proc is not None
    assert mgr.console_proc.pid != first_console_pid


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
    assert mgr.console_proc is None  # 子进程已清理
    log_text = (frt_root / "logs" / "runtime.log").read_text()
    assert "health timeout" in log_text


def test_start_ignores_core_command_failure(
    rt_pkg, manager_factory, frt_root, fake_core_fail_cmd, fake_console_cmd
):
    """Core 命令不可用 ≠ 启动失败: start 只依赖 Console managed service。"""
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_fail_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    st = mgr.start()
    assert st["status"] == "ready"
    assert st["core_alive"] is False  # 命令不可用不影响 runtime
    assert st["core_available"] is False
    assert st["console_alive"] is True
    assert st["console_healthy"] is True


def test_stop_force_kill(manager_factory, frt_root, fake_core_cmd, fake_console_ignore_term_cmd):
    mgr = manager_factory(
        frt_root,
        factory_cmd=fake_core_cmd,
        console_cmd=fake_console_ignore_term_cmd,
        **_fast({"terminate_timeout": 0.3}),
    )
    mgr.start()
    console_pid = mgr.console_proc.pid
    mgr.stop()  # SIGTERM 被忽略 → 超时 → SIGKILL
    assert not pid_alive(console_pid)
    assert mgr.console_proc is None


def test_status_before_start(manager_factory, frt_root, fake_core_cmd):
    mgr = manager_factory(frt_root, factory_cmd=fake_core_cmd)
    st = mgr.status()
    assert st["status"] == "idle"
    assert st["core_alive"] is True  # Core 命令可用性独立于 runtime 状态
    assert st["console_alive"] is False
    assert st["console_healthy"] is False
    assert st["core_exit_code"] is None


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
    st = mgr.start()  # 常驻脚本无 --help → 可用性 False, 但 start 只依赖 Console
    assert st["status"] == "ready"
    assert st["console_alive"] is True


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
    console_pid = int((frt_root / "config" / "console.pid").read_text().strip())
    assert console_pid == mgr.console_proc.pid
    assert pid_alive(console_pid)
    # Core 非 daemon → 无 core.pid
    assert not (frt_root / "config" / "core.pid").exists()


def test_stop_removes_pid_files(manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    mgr.stop()
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
    assert st["console_alive"] is True
    assert st["console_healthy"] is True
    assert st["core_available"] is True
    other.stop()  # 跨进程 stop 经 pid 文件终止子进程
    assert not (frt_root / "config" / "console.pid").exists()
    assert not pid_alive(mgr.console_proc.pid)


# ---------------------------------------------------------------- Core 命令模型 (裁决 B)

def test_managed_services_console_only(manager_factory, frt_root):
    """managed_services 注册点: 当前 Console 唯一 (未来 Agent Worker/Scheduler 扩展)。"""
    mgr = manager_factory(frt_root)
    assert mgr.managed_services == ["console"]


def test_core_proc_never_spawned(manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    """Core 非 daemon: start 后 core_proc 恒 None, 只有 console 常驻。"""
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    assert mgr.core_proc is None
    assert mgr.console_proc is not None


def test_core_command_execution_success(manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    """Core 命令执行成功 (command executor): returncode 0 + stdout。"""
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    result = mgr.run_command(["echo", "hello-core"])
    assert result.returncode == 0
    assert "hello-core" in result.stdout
    assert mgr.status()["status"] == "ready"


def test_core_command_exit_expected_not_crash(manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    """Core 命令执行后退出是预期 (非 crash): 不触发 watchdog 重启, runtime 保持 ready。"""
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    result = mgr.run_command(["status"])
    assert result.returncode == 0
    wd = mgr._watchdog
    time.sleep(0.8)  # 若 watchdog 误把 Core 退出当 crash → 会尝试重启
    assert wd.restart_count == 0
    assert mgr.status()["status"] == "ready"
    assert mgr.status()["console_alive"] is True


def test_core_command_failure_not_runtime_crash(manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    """Core 命令失败 (rc 2) ≠ Runtime 崩溃: status 保持 ready, watchdog 零重启。"""
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    result = mgr.run_command(["fail"])
    assert result.returncode == 2
    assert "failure" in result.stderr
    st = mgr.status()
    assert st["status"] == "ready"
    assert st["console_alive"] is True
    assert mgr._watchdog.restart_count == 0


def test_core_command_missing_raises(rt_pkg, manager_factory, frt_root, fake_console_cmd):
    """spawn 级错误 (命令不存在) → RuntimeError (配置缺口响亮暴露)。"""
    mgr = manager_factory(
        frt_root, factory_cmd=["definitely-not-a-real-factory-bin"], console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    with pytest.raises(rt_pkg.RuntimeError, match="not found"):
        mgr.run_command(["status"])


def test_core_available_true(manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    """Core 命令可用性 = CommandHealth (fake core --help → 0)。"""
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    st = mgr.status()
    assert st["core_available"] is True
    assert st["core_alive"] is True
    assert st["command_health"]["name"] == "core"
    assert st["command_health"]["available"] is True
    assert mgr.check_core_available() is True


def test_core_available_false_when_command_missing(manager_factory, frt_root, fake_console_cmd):
    """命令缺失 → CommandHealth available False; runtime 仍 ready (失败安全)。"""
    mgr = manager_factory(
        frt_root, factory_cmd=["no-such-factory-bin"], console_cmd=fake_console_cmd, **_fast()
    )
    st = mgr.start()
    assert st["status"] == "ready"
    assert st["core_available"] is False
    assert st["core_alive"] is False
    assert st["command_health"]["available"] is False
    assert mgr.check_core_available() is False


def test_console_service_healthy(rt_pkg, manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    """Console service alive = healthy (ServiceHealth)。"""
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    h = rt_pkg.health.service_health("console", mgr.console_proc)
    assert h.name == "console"
    assert h.alive is True
    assert h.checked_at
    st = mgr.status()
    assert st["console_healthy"] is True
    assert st["service_health"]["name"] == "console"
    assert st["service_health"]["alive"] is True


def test_console_service_down_when_stopped(manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    """stop 后 Console service down (ServiceHealth alive False)。"""
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    mgr.stop()
    st = mgr.status()
    assert st["console_alive"] is False
    assert st["console_healthy"] is False
    assert st["service_health"]["alive"] is False


def test_console_crash_restart_keeps_ready(manager_factory, frt_root, fake_core_cmd, fake_console_crash_cmd):
    """managed service (Console) 崩溃 → watchdog 重启 → 保持 ready。"""
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_crash_cmd, **_fast()
    )
    mgr.start()
    first_pid = mgr.console_proc.pid

    def restarted():
        wd = mgr._watchdog
        return (
            wd is not None
            and wd.restart_count >= 1
            and mgr.console_proc is not None
            and mgr.console_proc.pid != first_pid
        )

    assert wait_until(restarted, timeout=12)
    st = mgr.status()
    assert st["status"] == "ready"
    assert st["console_alive"] is True
