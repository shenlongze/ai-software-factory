"""tests/factory_runtime/test_frt_cli.py — factory-runtime CLI (退出码/--json/子命令)。

重点: init/start/stop/status/restart/logs 退出码 + --json 结构化输出 +
用法错误 SystemExit(2) + 健康失败 rc 1。
"""

from __future__ import annotations

import json
import os
import shlex
import stat
import sys
from pathlib import Path

import pytest


def _run(rt_pkg, argv: list[str]):
    """调 cli.main (返回 rc); capsys 由测试自行读取。"""
    return rt_pkg.cli.main(argv)


def test_init_creates_dirs(rt_pkg, cli_root):
    rc = _run(rt_pkg, ["--root", str(cli_root), "init"])
    assert rc == 0
    for name in rt_pkg.paths.SUBDIRS:
        assert (cli_root / name).is_dir()
    assert (cli_root / "config" / "runtime_state.json").exists()
    assert (cli_root / "config" / "runtime_token").exists()


def test_init_perms(rt_pkg, cli_root):
    if os.name != "posix":
        pytest.skip("POSIX only")
    _run(rt_pkg, ["--root", str(cli_root), "init"])
    assert stat.S_IMODE(cli_root.stat().st_mode) == 0o700
    assert stat.S_IMODE((cli_root / "config" / "runtime_token").stat().st_mode) == 0o600


def test_init_json(rt_pkg, cli_root, capsys):
    rc = _run(rt_pkg, ["--root", str(cli_root), "init", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "idle"
    assert out["root"] == str(cli_root)
    assert "config" in out["subdirs"]


def test_start_stop_roundtrip(rt_pkg, cli_root, fake_core_cmd, fake_console_cmd, capsys):
    factory_cmd = shlex.join(fake_core_cmd)
    console_cmd = shlex.join(fake_console_cmd)
    rc = _run(
        rt_pkg,
        ["--root", str(cli_root), "start", "--factory-cmd", factory_cmd, "--console-cmd", console_cmd],
    )
    assert rc == 0
    assert "status:    ready" in capsys.readouterr().out

    rc = _run(rt_pkg, ["--root", str(cli_root), "status", "--json"])
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "ready"
    assert status["core_alive"] is True
    assert status["console_alive"] is True

    rc = _run(rt_pkg, ["--root", str(cli_root), "stop"])
    assert rc == 0
    assert "status:    stopped" in capsys.readouterr().out


def test_start_failure_rc1(rt_pkg, cli_root, fake_core_cmd, fake_console_slow_cmd, capsys):
    factory_cmd = shlex.join(fake_core_cmd)
    console_cmd = shlex.join(fake_console_slow_cmd)
    rc = _run(
        rt_pkg,
        ["--root", str(cli_root), "start", "--factory-cmd", factory_cmd, "--console-cmd", console_cmd],
    )
    assert rc == 1
    assert "health timeout" in capsys.readouterr().err


def test_status_before_start(rt_pkg, cli_root, capsys):
    rc = _run(rt_pkg, ["--root", str(cli_root), "status", "--json"])
    assert rc == 0
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "idle"


def test_stop_when_not_running_rc0(rt_pkg, cli_root, capsys):
    rc = _run(rt_pkg, ["--root", str(cli_root), "stop"])
    assert rc == 0
    assert "not running" not in capsys.readouterr().out  # 文本模式正常输出状态


def test_restart_rc0(rt_pkg, cli_root, fake_core_cmd, fake_console_cmd, capsys):
    factory_cmd = shlex.join(fake_core_cmd)
    console_cmd = shlex.join(fake_console_cmd)
    assert _run(rt_pkg, ["--root", str(cli_root), "start", "--factory-cmd", factory_cmd, "--console-cmd", console_cmd]) == 0
    capsys.readouterr()
    rc = _run(
        rt_pkg,
        ["--root", str(cli_root), "restart", "--factory-cmd", factory_cmd, "--console-cmd", console_cmd],
    )
    assert rc == 0
    assert "status:    ready" in capsys.readouterr().out
    _run(rt_pkg, ["--root", str(cli_root), "stop"])
    capsys.readouterr()


def test_cli_stop_kills_orphaned_children(rt_pkg, cli_root, fake_core_cmd, fake_console_cmd, capsys):
    """CLI start 后管理器进程已退出 → stop 经 pid 文件跨进程终止子进程。"""
    factory_cmd = shlex.join(fake_core_cmd)
    console_cmd = shlex.join(fake_console_cmd)
    assert _run(
        rt_pkg,
        ["--root", str(cli_root), "start", "--factory-cmd", factory_cmd, "--console-cmd", console_cmd],
    ) == 0
    capsys.readouterr()
    core_pid = int((cli_root / "config" / "core.pid").read_text().strip())
    console_pid = int((cli_root / "config" / "console.pid").read_text().strip())
    from frt_helpers import pid_alive

    assert pid_alive(core_pid) and pid_alive(console_pid)
    rc = _run(rt_pkg, ["--root", str(cli_root), "stop"])
    assert rc == 0
    assert not pid_alive(core_pid)
    assert not pid_alive(console_pid)
    assert not (cli_root / "config" / "core.pid").exists()
    assert not (cli_root / "config" / "console.pid").exists()


def test_logs_command(rt_pkg, cli_root, fake_core_cmd, fake_console_cmd, capsys):
    factory_cmd = shlex.join(fake_core_cmd)
    console_cmd = shlex.join(fake_console_cmd)
    assert _run(rt_pkg, ["--root", str(cli_root), "start", "--factory-cmd", factory_cmd, "--console-cmd", console_cmd]) == 0
    capsys.readouterr()
    rc = _run(rt_pkg, ["--root", str(cli_root), "logs", "--lines", "20"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "== runtime.log ==" in out
    assert "== core.log ==" in out
    assert "== console.log ==" in out
    assert "started" in out
    _run(rt_pkg, ["--root", str(cli_root), "stop"])
    capsys.readouterr()


def test_logs_json(rt_pkg, cli_root, fake_core_cmd, fake_console_cmd, capsys):
    factory_cmd = shlex.join(fake_core_cmd)
    console_cmd = shlex.join(fake_console_cmd)
    assert _run(rt_pkg, ["--root", str(cli_root), "start", "--factory-cmd", factory_cmd, "--console-cmd", console_cmd]) == 0
    capsys.readouterr()
    rc = _run(rt_pkg, ["--root", str(cli_root), "logs", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert set(data["files"].keys()) == {"runtime.log", "core.log", "console.log"}
    _run(rt_pkg, ["--root", str(cli_root), "stop"])
    capsys.readouterr()


def test_unknown_command_exit_2(rt_pkg, cli_root):
    with pytest.raises(SystemExit) as exc:
        _run(rt_pkg, ["--root", str(cli_root), "bogus"])
    assert exc.value.code == 2


def test_missing_command_exit_2(rt_pkg, cli_root):
    with pytest.raises(SystemExit) as exc:
        _run(rt_pkg, ["--root", str(cli_root)])
    assert exc.value.code == 2


def test_help_exit_0(rt_pkg, capsys):
    with pytest.raises(SystemExit) as exc:
        _run(rt_pkg, ["--help"])
    assert exc.value.code == 0
    assert "usage" in capsys.readouterr().out


def test_start_json_output(rt_pkg, cli_root, fake_core_cmd, fake_console_cmd, capsys):
    factory_cmd = shlex.join(fake_core_cmd)
    console_cmd = shlex.join(fake_console_cmd)
    rc = _run(
        rt_pkg,
        ["--root", str(cli_root), "start", "--json", "--factory-cmd", factory_cmd, "--console-cmd", console_cmd],
    )
    status = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert status["status"] == "ready"
    _run(rt_pkg, ["--root", str(cli_root), "stop"])
    capsys.readouterr()


def test_global_json_flag_position(rt_pkg, cli_root, capsys):
    """全局 --json 放在子命令前也生效 (argparse SUPPRESS 不覆盖)。"""
    rc = _run(rt_pkg, ["--root", str(cli_root), "--json", "status"])
    status = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert status["status"] == "idle"


def test_init_twice_idempotent(rt_pkg, cli_root):
    assert _run(rt_pkg, ["--root", str(cli_root), "init"]) == 0
    assert _run(rt_pkg, ["--root", str(cli_root), "init"]) == 0


def test_token_not_in_status_output(rt_pkg, cli_root, fake_core_cmd, fake_console_cmd, capsys):
    """状态输出不含 token (secret 脱敏, 设计 §5)。"""
    factory_cmd = shlex.join(fake_core_cmd)
    console_cmd = shlex.join(fake_console_cmd)
    _run(rt_pkg, ["--root", str(cli_root), "start", "--factory-cmd", factory_cmd, "--console-cmd", console_cmd])
    capsys.readouterr()
    _run(rt_pkg, ["--root", str(cli_root), "status", "--json"])
    out = capsys.readouterr().out
    token = (cli_root / "config" / "runtime_token").read_text().strip()
    assert token not in out
    _run(rt_pkg, ["--root", str(cli_root), "stop"])
    capsys.readouterr()


def test_python_m_entrypoint(cli_root):
    """python -m runtime.cli 入口可用 (__main__ 块) — 冒烟同形态。"""
    import os
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root / "factory-runtime")
    result = subprocess.run(
        [sys.executable, "-m", "runtime.cli", "--root", str(cli_root), "init"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo_root),
    )
    assert result.returncode == 0, result.stderr
    assert "initialized" in result.stdout
