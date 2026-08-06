"""tests/factory_runtime/test_frt_watchdog.py — watchdog (managed services 崩溃恢复)。

架构裁决 B (Core Command Model):
- watchdog 只 watch managed services (当前 Console); Core 退出是预期,
  不重启, 不报警为 crash。
- 未来 Agent Worker/Scheduler 经 manager.managed_services 注册 → 自动覆盖。

重点: console 崩溃 → 自动重启 (restart_count/事件) / 超限 → failed /
Core 命令退出不触发重启 / stop 后不再重启 / 重启计数随新 start 重置。
"""

from __future__ import annotations

import time

import pytest

from frt_helpers import wait_until


def _fast(**overrides) -> dict:
    kw = {
        "health_timeout": 8.0,
        "health_interval": 0.1,
        "terminate_timeout": 1.0,
        "watchdog_interval": 0.2,
    }
    kw.update(overrides)
    return kw


def test_core_command_exit_does_not_trigger_watchdog(
    manager_factory, frt_root, fake_core_cmd, fake_console_cmd
):
    """Core 退出是预期: watchdog 只 watch managed services (Console), Core 不重启。"""
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    wd = mgr._watchdog
    result = mgr.run_command(["status"])  # Core 命令执行后退出 (正常完成)
    assert result.returncode == 0
    time.sleep(0.8)  # 给 watchdog 若干轮 — 若误 watch Core 必然触发重启
    assert wd.restart_count == 0
    assert mgr.status()["status"] == "ready"


def test_watchdog_polls_managed_services_list(rt_pkg):
    """_check_once 只轮询 manager.managed_services (duck-typed manager 验证)。"""

    class FakeManager:
        managed_services = ["svc_a"]

        def status(self):
            return {"status": "ready"}

        def service_proc(self, name):
            assert name == "svc_a"
            return None  # 无进程 → 跳过, 零重启

    wd = rt_pkg.watchdog.Watchdog(FakeManager())
    wd._check_once()
    assert wd.restart_count == 0


def test_watchdog_ignores_core_without_managed_proc(rt_pkg, manager_factory, frt_root, monkeypatch):
    """Core 无进程可 watch (非 managed service) → 零重启。"""
    mgr = manager_factory(frt_root)
    monkeypatch.setattr(mgr, "status", lambda: {"status": "ready"})
    wd = rt_pkg.watchdog.Watchdog(mgr)
    wd._check_once()
    assert wd.restart_count == 0


def test_console_crash_restart(manager_factory, frt_root, fake_core_cmd, fake_console_crash_cmd):
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
    assert mgr.status()["status"] == "ready"
    assert mgr.status()["console_alive"] is True


def test_console_crash_once_restart_records_event(
    manager_factory, frt_root, fake_core_cmd, fake_console_crash_once_cmd
):
    """console crash-once → watchdog 重启 1 次 → 常驻; 事件记录 (name/exit_code)。"""
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_crash_once_cmd, **_fast()
    )
    mgr.start()
    assert wait_until(lambda: mgr._watchdog is not None and mgr._watchdog.restart_count >= 1, timeout=12)
    record = mgr._watchdog.restarts[-1]
    assert record["name"] == "console"
    assert record["exit_code"] == 2
    assert record["at"]
    assert mgr.status()["status"] == "ready"
    # 事件记录 (可定位)
    log_text = (frt_root / "logs" / "runtime.log").read_text()
    assert "restart" in log_text and "console" in log_text


def test_restart_limit_exceeded_failed(manager_factory, frt_root, fake_core_cmd, fake_console_crash_cmd):
    mgr = manager_factory(
        frt_root,
        factory_cmd=fake_core_cmd,
        console_cmd=fake_console_crash_cmd,
        **_fast(max_restarts=2),
    )
    mgr.start()
    assert wait_until(lambda: mgr.status()["status"] == "failed", timeout=20)
    assert mgr._watchdog.restart_count == 3  # 2 次重启后第 3 次退出超限
    log_text = (frt_root / "logs" / "runtime.log").read_text()
    assert "watchdog limit reached" in log_text


def test_watchdog_stops_on_stop(manager_factory, frt_root, fake_core_cmd, fake_console_cmd):
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_cmd, **_fast()
    )
    mgr.start()
    wd = mgr._watchdog
    thread = wd._thread
    assert thread is not None and thread.is_alive()
    mgr.stop()
    assert wd._thread is None or not wd._thread.is_alive()


def test_watchdog_no_restart_after_stop(manager_factory, frt_root, fake_core_cmd, fake_console_crash_cmd):
    mgr = manager_factory(
        frt_root,
        factory_cmd=fake_core_cmd,
        console_cmd=fake_console_crash_cmd,
        **_fast(max_restarts=2),
    )
    mgr.start()
    wd = mgr._watchdog
    mgr.stop()
    count = wd.restart_count
    time.sleep(0.8)  # 若线程仍活, crash_loop 必然触发重启
    assert wd.restart_count == count
    assert mgr.status()["status"] == "stopped"


def test_restart_count_reset_on_new_start(
    manager_factory, frt_root, fake_core_cmd, fake_console_crash_once_cmd
):
    mgr = manager_factory(
        frt_root, factory_cmd=fake_core_cmd, console_cmd=fake_console_crash_once_cmd, **_fast()
    )
    mgr.start()
    assert wait_until(lambda: mgr._watchdog.restart_count >= 1, timeout=12)
    st = mgr.restart()
    assert st["status"] == "ready"
    assert mgr._watchdog.restart_count == 0  # 新 Watchdog 实例


def test_watchdog_start_idempotent(rt_pkg, manager_factory, frt_root):
    mgr = manager_factory(frt_root)
    wd = rt_pkg.watchdog.Watchdog(mgr)
    wd.start()
    thread = wd._thread
    wd.start()  # 二次 start 不新起线程
    assert wd._thread is thread
    wd.stop()


def test_watchdog_stop_before_start_noop(rt_pkg, manager_factory, frt_root):
    mgr = manager_factory(frt_root)
    wd = rt_pkg.watchdog.Watchdog(mgr)
    wd.stop()  # 未 start → 零异常
    assert wd._thread is None


def test_watchdog_check_once_skips_when_not_running(rt_pkg, manager_factory, frt_root):
    mgr = manager_factory(frt_root)
    wd = rt_pkg.watchdog.Watchdog(mgr)
    wd._check_once()  # status idle → 不触发任何重启
    assert wd.restart_count == 0


def test_max_restarts_configurable(rt_pkg, manager_factory, frt_root):
    mgr = manager_factory(frt_root)
    wd = rt_pkg.watchdog.Watchdog(mgr, max_restarts=5)
    assert wd.max_restarts == 5


def test_restart_process_unknown_name(rt_pkg, manager_factory, frt_root):
    mgr = manager_factory(frt_root)
    with pytest.raises(ValueError, match="unknown managed service"):
        mgr.restart_process("bogus")


def test_service_proc_unknown_name(rt_pkg, manager_factory, frt_root):
    mgr = manager_factory(frt_root)
    with pytest.raises(ValueError, match="unknown managed service"):
        mgr.service_proc("bogus")


def test_watchdog_survives_restart_exception(rt_pkg, manager_factory, frt_root):
    """watchdog 轮询中异常不崩溃 (失败安全: _run 捕获后继续/退出)。"""
    mgr = manager_factory(frt_root)
    wd = rt_pkg.watchdog.Watchdog(mgr)
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        wd._stop_event.set()  # 单轮即退出
        raise OSError("boom")

    wd._check_once = boom
    wd._run()
    assert calls["n"] == 1
    assert wd.restart_count == 0
