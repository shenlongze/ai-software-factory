"""tests/console/test_cli_services.py — S10-026 Task B: Runtime Manager (服务注册表)。

覆盖 (全 hermetic, tmp_path + 显式 config 注入隔离 — 不写真实 ~/.factory):
- 注册表: 内置 3 服务 (backend/frontend/runtime) 注册齐全; 注入假 ServiceDef
  自动被发现 (未来 vector-db/gateway 模式); 重复/空 id 注册 → ValueError
- factory service list: 三服务 + running/stopped 状态 + PID/URL 展示 (验收 A)
- factory start 无参数 = 全部内置服务 (backend+frontend), 行为兼容断言
  (验收 B): 幂等短路 / 端口预检 / 启动+健康检查顺序 / 就绪输出 / 打开浏览器
- factory start <service>: 只启动指定服务 (验收 C); 未知服务 → exit 2;
  前端启动失败 → 回滚已起后端
- factory stop: 经注册表停止 — 陈旧 pid 清理 / 已停止输出 (验收 C)
- factory status: 输出与旧版一致 (经注册表)
- 注册表可扩展 (验收 D): 假服务出现在 service list 与 `start <id>` 解析
- frontend 默认 dist 托管, --dev 保留 vite (验收 E)
- 不真正启动 uvicorn/vite (monkeypatch 全部进程启动原语; 真实启动只在冒烟手动)

装配: importlib + sys.path 挂仓库根 (factory-console 包名含连字符, 唯一导入
方式; 同 tests/console 既有模式)。basename 全仓库唯一。
"""

from __future__ import annotations

import base64
import importlib
import json
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # factory-console/ 的父目录 (含连字符包名)
    sys.path.insert(0, str(_ROOT))

_svc = importlib.import_module("factory-console.cli_services")
_cli = importlib.import_module("factory-console.cli_factory")
_cfg = importlib.import_module("factory-console.config")

BUILTIN_IDS = ["backend", "frontend", "runtime"]


def make_cli(tmp_path: Path):
    """hermetic FactoryCLI: config.json 指向 tmp data_dir, 零环境依赖。"""
    data_dir = tmp_path / ".factory"
    data_dir.mkdir()
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        json.dumps({"core": {"data_dir": str(data_dir)}}), encoding="utf-8"
    )
    config = _cfg.ConfigProvider(
        user_config_file=cfg_file, env_file=tmp_path / ".env", environ={}
    )
    root = tmp_path / "repo"
    root.mkdir()
    return _cli.FactoryCLI(config, root=root)


def patch_ports(monkeypatch, value: bool = False) -> None:
    """端口探测归零 (cli_factory 模块属性 — cli_services 经 _factory 同一引用)。"""
    monkeypatch.setattr(_cli, "_port_in_use", lambda port: value)


def patch_start_checks(monkeypatch) -> None:
    """start 前置检查全绿 + 端口空闲 (测试只关注注册表编排)。"""
    monkeypatch.setattr(_cli, "_env_problems", lambda: [])
    monkeypatch.setattr(_cli, "_dep_problems", lambda root: [])
    monkeypatch.setattr(_cli, "_config_hints", lambda config: [])
    patch_ports(monkeypatch, value=False)


def patch_procs(monkeypatch, cli) -> dict[str, list]:
    """进程启动/健康检查/浏览器全部打桩 (不真正起 uvicorn/vite)。"""
    calls: dict[str, list] = {"backend": [], "frontend": []}

    def fake_start_backend(port):
        calls["backend"].append(port)
        return True

    def fake_start_frontend(port, *, dev=False):
        calls["frontend"].append((port, dev))
        return True

    monkeypatch.setattr(cli, "_start_backend", fake_start_backend)
    monkeypatch.setattr(cli, "_start_frontend", fake_start_frontend)
    monkeypatch.setattr(cli, "_wait_backend", lambda port: True)
    monkeypatch.setattr(cli, "_wait_frontend", lambda port: True)
    monkeypatch.setattr(_cli, "_open_url", lambda url: calls.setdefault("open", []).append(url))
    return calls


def write_pid(cli, name: str, pid: int) -> None:
    (cli.data_dir / "run").mkdir(parents=True, exist_ok=True)
    (cli.data_dir / "run" / f"{name}.pid").write_text(f"{pid}\n", encoding="utf-8")


class FakeVectorDB:
    """假服务 (未来 vector-db 模式): 只实现 ServiceDef 协议四件套。"""

    id = "vector-db"
    label = "向量库 (假服务, 测试注入)"

    def start(self, ctx):
        return _svc.ServiceHandle(id=self.id, ok=True, pid=1, port=8668)

    def stop(self, handle):
        return None

    def status(self, ctx):
        return _svc.ServiceStatus(self.id, _svc.STATE_STOPPED, "未运行")


# ------------------------------------------------------------------ 注册表 (验收 D)


class TestRegistry:
    def test_builtin_services_registered(self):
        """内置 3 服务注册齐全 (验收 A 服务清单)。"""
        assert [s.id for s in _svc.list_services()] == BUILTIN_IDS

    def test_register_fake_auto_discovered(self, tmp_path, capsys):
        """未来 vector-db/gateway: 实现协议 + register → service list 自动出现。"""
        cli = make_cli(tmp_path)
        _svc.register(FakeVectorDB())
        try:
            assert "vector-db" in [s.id for s in _svc.list_services()]
            args = _cli.build_parser().parse_args(["service", "list"])
            rc = cli.run(args)
            out = capsys.readouterr().out
            assert rc == 0
            assert "factory service list:" in out
            assert "vector-db" in out
        finally:
            del _svc._SERVICES["vector-db"]  # 清理, 不污染其他用例

    def test_register_duplicate_raises(self):
        with pytest.raises(ValueError):
            _svc.register(_svc.BackendService())

    def test_register_empty_id_raises(self):
        class NoId:
            id = ""
            label = "x"

            def start(self, ctx):
                return _svc.ServiceHandle(id="x", ok=True)

            def stop(self, handle):
                return None

            def status(self, ctx):
                return _svc.ServiceStatus("x", _svc.STATE_STOPPED)

        with pytest.raises(ValueError):
            _svc.register(NoId())


# ------------------------------------------------------------------ service list (验收 A)


class TestServiceList:
    def test_list_structure_three_services(self, tmp_path, capsys, monkeypatch):
        """空环境: 三服务齐全, 全部 stopped, 退出码 0 (列表展示)。"""
        cli = make_cli(tmp_path)
        patch_ports(monkeypatch, value=False)
        args = _cli.build_parser().parse_args(["service", "list"])
        rc = cli.run(args)
        out = capsys.readouterr().out
        assert rc == 0
        assert "factory service list:" in out
        assert out.count("stopped") == 3
        for sid in BUILTIN_IDS:
            assert sid in out

    def test_list_running_shows_pid_url(self, tmp_path, capsys, monkeypatch):
        """running 服务展示 (PID, url); 其余 stopped。"""
        cli = make_cli(tmp_path)
        patch_ports(monkeypatch, value=False)
        monkeypatch.setattr(_cli, "_pid_alive", lambda pid: True)
        write_pid(cli, "backend", 12345)
        args = _cli.build_parser().parse_args(["service", "list"])
        rc = cli.run(args)
        out = capsys.readouterr().out
        assert rc == 0
        assert "backend   running" in out
        assert "(PID 12345, http://127.0.0.1:8011)" in out
        assert "frontend  stopped" in out
        assert "runtime   stopped" in out


# ------------------------------------------------------------------ start 无参数 (验收 B)


class TestStartAll:
    def test_start_all_starts_backend_and_frontend(self, tmp_path, capsys, monkeypatch):
        """`factory start` 无参数 → backend+frontend 都启动 + 健康检查 + 浏览器。"""
        cli = make_cli(tmp_path)
        patch_start_checks(monkeypatch)
        calls = patch_procs(monkeypatch, cli)
        args = _cli.build_parser().parse_args(["start"])
        rc = cli.run(args)
        out = capsys.readouterr().out
        assert rc == 0
        assert calls["backend"] == [8011]
        assert calls["frontend"] == [(5180, False)]
        assert "✓ 已就绪: http://127.0.0.1:5180/#/workspace" in out
        assert "后端 API: http://127.0.0.1:8011/api/projects" in out
        assert calls["open"] == ["http://127.0.0.1:5180/#/workspace"]

    def test_start_all_no_browser(self, tmp_path, capsys, monkeypatch):
        """--no-browser: 不打开浏览器 (其余照常)。"""
        cli = make_cli(tmp_path)
        patch_start_checks(monkeypatch)
        calls = patch_procs(monkeypatch, cli)
        args = _cli.build_parser().parse_args(["start", "--no-browser"])
        rc = cli.run(args)
        assert rc == 0
        assert "open" not in calls

    def test_start_all_idempotent(self, tmp_path, capsys, monkeypatch):
        """幂等: 前后端均已运行 → 提示不重复起, 零启动调用。"""
        cli = make_cli(tmp_path)
        patch_start_checks(monkeypatch)
        calls = patch_procs(monkeypatch, cli)
        monkeypatch.setattr(_cli, "_pid_alive", lambda pid: True)
        write_pid(cli, "backend", 1111)
        write_pid(cli, "frontend", 2222)
        args = _cli.build_parser().parse_args(["start"])
        rc = cli.run(args)
        out = capsys.readouterr().out
        assert rc == 0
        assert "已在运行: http://127.0.0.1:5180/#/workspace" in out
        assert calls["backend"] == [] and calls["frontend"] == []

    def test_start_port_precheck_busy(self, tmp_path, capsys, monkeypatch):
        """端口预检: 后端端口被占 → 明确提示, 不启动任何服务。"""
        cli = make_cli(tmp_path)
        patch_start_checks(monkeypatch)
        calls = patch_procs(monkeypatch, cli)
        monkeypatch.setattr(_cli, "_port_in_use", lambda port: True)  # 预检用
        args = _cli.build_parser().parse_args(["start"])
        rc = cli.run(args)
        err = capsys.readouterr().err
        assert rc == 1
        assert "端口已被占用: 后端端口 8011" in err
        assert calls["backend"] == [] and calls["frontend"] == []

    def test_start_backend_wait_fail(self, tmp_path, capsys, monkeypatch):
        """后端健康检查失败 → 日志尾部 + 清理 pid, 不回滚 stop。"""
        cli = make_cli(tmp_path)
        patch_start_checks(monkeypatch)
        calls = patch_procs(monkeypatch, cli)
        monkeypatch.setattr(cli, "_wait_backend", lambda port: False)
        monkeypatch.setattr(cli, "_show_log_tail", lambda path, lines=30: None)
        stopped = []
        monkeypatch.setattr(cli, "stop", lambda: stopped.append("stop") or 0)
        args = _cli.build_parser().parse_args(["start"])
        rc = cli.run(args)
        err = capsys.readouterr().err
        assert rc == 1
        assert "后端启动失败 (健康检查超时" in err
        assert calls["frontend"] == []  # 前端未被启动
        assert stopped == []  # 后端失败 → 只清理 pid, 不调 stop

    def test_start_frontend_fail_rolls_back(self, tmp_path, capsys, monkeypatch):
        """前端启动失败 → 回滚已起后端 (stop 调用)。"""
        cli = make_cli(tmp_path)
        patch_start_checks(monkeypatch)
        calls = patch_procs(monkeypatch, cli)
        calls["frontend"] = []

        def fake_start_frontend(port, *, dev=False):
            calls["frontend"].append((port, dev))
            return False

        monkeypatch.setattr(cli, "_start_frontend", fake_start_frontend)
        stopped = []
        monkeypatch.setattr(cli, "stop", lambda: stopped.append("stop") or 0)
        args = _cli.build_parser().parse_args(["start"])
        rc = cli.run(args)
        assert rc == 1
        assert calls["backend"] == [8011]
        assert calls["frontend"] == [(5180, False)]
        assert stopped == ["stop"]  # 回滚


# ------------------------------------------------------------------ start 单服务 (验收 C)


class TestStartSingle:
    def test_start_backend_only(self, tmp_path, capsys, monkeypatch):
        """`factory start backend` 只启动后端; 前端不启动; 不开浏览器。"""
        cli = make_cli(tmp_path)
        patch_start_checks(monkeypatch)
        calls = patch_procs(monkeypatch, cli)
        args = _cli.build_parser().parse_args(["start", "backend"])
        rc = cli.run(args)
        out = capsys.readouterr().out
        assert rc == 0
        assert calls["backend"] == [8011]
        assert calls["frontend"] == []
        assert "✓ backend 已就绪" in out
        assert "open" not in calls  # 前端未运行 → 不打开浏览器

    def test_start_backend_idempotent(self, tmp_path, capsys, monkeypatch):
        """单服务幂等: 后端已运行 → 提示不重复起。"""
        cli = make_cli(tmp_path)
        patch_start_checks(monkeypatch)
        calls = patch_procs(monkeypatch, cli)
        monkeypatch.setattr(_cli, "_pid_alive", lambda pid: True)
        write_pid(cli, "backend", 1234)
        args = _cli.build_parser().parse_args(["start", "backend"])
        rc = cli.run(args)
        out = capsys.readouterr().out
        assert rc == 0
        assert "已在运行: backend (PID 1234)" in out
        assert calls["backend"] == []

    def test_start_unknown_service_rc2(self, tmp_path, capsys, monkeypatch):
        """服务不存在 → exit 2 + 可用列表 (验收: 服务不存在 → 2)。"""
        cli = make_cli(tmp_path)
        patch_start_checks(monkeypatch)
        args = _cli.build_parser().parse_args(["start", "bogus"])
        rc = cli.run(args)
        err = capsys.readouterr().err
        assert rc == 2
        assert "未知服务: bogus" in err
        assert "backend, frontend, runtime" in err

    def test_start_runtime_placeholder(self, tmp_path, capsys, monkeypatch):
        """`factory start runtime`: 占位提示, 不失败 (rc 0)。"""
        cli = make_cli(tmp_path)
        patch_start_checks(monkeypatch)
        args = _cli.build_parser().parse_args(["start", "runtime"])
        rc = cli.run(args)
        out = capsys.readouterr().out
        assert rc == 0
        assert "runtime" in out
        assert "按需调度" in out

    def test_start_fake_service_cli(self, tmp_path, capsys, monkeypatch):
        """注册表可扩展 (验收 D): 假服务经 CLI `start vector-db` 可启动。"""
        cli = make_cli(tmp_path)
        patch_start_checks(monkeypatch)
        _svc.register(FakeVectorDB())
        try:
            args = _cli.build_parser().parse_args(["start", "vector-db"])
            rc = cli.run(args)
            out = capsys.readouterr().out
            assert rc == 0
            assert "vector-db 已就绪" in out
        finally:
            del _svc._SERVICES["vector-db"]


# ------------------------------------------------------------------ stop (验收 C)


class TestStop:
    def test_stop_nothing_running(self, tmp_path, capsys, monkeypatch):
        cli = make_cli(tmp_path)
        patch_ports(monkeypatch, value=False)
        args = _cli.build_parser().parse_args(["stop"])
        rc = cli.run(args)
        out = capsys.readouterr().out
        assert rc == 0
        assert "未发现运行中的服务" in out

    def test_stop_stale_pid_cleaned(self, tmp_path, monkeypatch):
        """陈旧 pid (进程已死) → 不误杀, 清理 pid 文件。"""
        cli = make_cli(tmp_path)
        patch_ports(monkeypatch, value=False)
        write_pid(cli, "backend", 999999)  # 超过 macOS pid_max, 必然不存在
        write_pid(cli, "frontend", 999999)
        args = _cli.build_parser().parse_args(["stop"])
        rc = cli.run(args)
        assert rc == 0
        assert not (cli.data_dir / "run" / "backend.pid").exists()
        assert not (cli.data_dir / "run" / "frontend.pid").exists()

    def test_stop_killed_output(self, tmp_path, capsys, monkeypatch):
        """经注册表停止: 输出 `已停止: 后端 (PID x), 前端 (PID x)`。"""
        cli = make_cli(tmp_path)
        patch_ports(monkeypatch, value=False)
        monkeypatch.setattr(cli, "_stop_one", lambda pid_file, port: 4242)
        args = _cli.build_parser().parse_args(["stop"])
        rc = cli.run(args)
        out = capsys.readouterr().out
        assert rc == 0
        assert "已停止: 后端 (PID 4242), 前端 (PID 4242)" in out


# ------------------------------------------------------------------ status (经注册表, 输出不变)


class TestStatus:
    def test_status_output_via_registry(self, tmp_path, capsys, monkeypatch):
        """status 输出与旧版一致 (数据目录/LLM/后端/前端), rc 0。"""
        cli = make_cli(tmp_path)
        patch_ports(monkeypatch, value=False)
        args = _cli.build_parser().parse_args(["status"])
        rc = cli.run(args)
        out = capsys.readouterr().out
        assert rc == 0
        assert "数据目录" in out
        assert "LLM:" in out
        assert "后端: 未运行 — 端口 8011 空闲" in out
        assert "前端: 未运行 — 端口 5180 空闲" in out


# ------------------------------------------------------------------ frontend dist / --dev (验收 E)


class FakePopen:
    """subprocess.Popen 桩: 记录 cmd, 提供 pid (绝不真正拉起进程)。"""

    last_cmd: list[str] = []

    def __init__(self, cmd, **kwargs):
        FakePopen.last_cmd = list(cmd)
        self.pid = 4242


class TestFrontendMode:
    def test_default_dist_hosting(self, tmp_path, capsys, monkeypatch):
        """默认 (无 --dev): dist 存在 → uvicorn + create_app(static_dir=dist)。"""
        cli = make_cli(tmp_path)
        (cli.data_dir / "run").mkdir(parents=True, exist_ok=True)
        dist = cli.root / "factory-console" / "web" / "frontend" / "dist"
        dist.mkdir(parents=True)
        (dist / "index.html").write_text("<html></html>", encoding="utf-8")
        monkeypatch.setattr(_cli.subprocess, "Popen", FakePopen)
        assert cli._start_frontend(5180) is True
        cmd = FakePopen.last_cmd
        assert cmd[0].endswith("python") and "-c" in cmd
        payload = cmd[2]
        m = re.search(r"base64\.b64decode\('([^']+)'\)", payload)
        assert m, "bootstrap 应经 base64 传入"
        decoded = base64.b64decode(m.group(1)).decode("utf-8")
        assert "static_dir" in decoded and str(dist) in decoded
        assert _read_pid_file(cli, "frontend") == 4242  # pid 文件 (stop 兼容)

    def test_dev_flag_keeps_vite(self, tmp_path, monkeypatch):
        """--dev: 走 vite (npm run dev -- --strictPort)。"""
        cli = make_cli(tmp_path)
        (cli.data_dir / "run").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(_cli.subprocess, "Popen", FakePopen)
        assert cli._start_frontend(5180, dev=True) is True
        cmd = FakePopen.last_cmd
        assert cmd[0].endswith("npm")
        assert "run" in cmd and "--strictPort" in cmd and "--host" in cmd

    def test_dist_missing_falls_back_vite(self, tmp_path, capsys, monkeypatch):
        """dist 缺失 → 回退 vite dev + 提示 (未构建也能启动)。"""
        cli = make_cli(tmp_path)
        (cli.data_dir / "run").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(_cli.subprocess, "Popen", FakePopen)
        assert cli._start_frontend(5180) is True
        out = capsys.readouterr().out
        assert "回退 vite dev 模式" in out
        cmd = FakePopen.last_cmd
        assert "--strictPort" in cmd


def _read_pid_file(cli, name: str) -> int | None:
    path = cli.data_dir / "run" / f"{name}.pid"
    return int(path.read_text(encoding="utf-8").strip()) if path.exists() else None


# ------------------------------------------------------------------ argparse 集成


class TestParser:
    def test_service_subcommand(self):
        args = _cli.build_parser().parse_args(["service", "list"])
        assert args.command == "service"
        assert args.service_action == "list"

    def test_service_unknown_action_rejected(self):
        with pytest.raises(SystemExit):
            _cli.build_parser().parse_args(["service", "bogus"])

    def test_start_positional_services(self):
        assert _cli.build_parser().parse_args(["start"]).services == []
        assert _cli.build_parser().parse_args(["start", "backend"]).services == ["backend"]
        assert _cli.build_parser().parse_args(
            ["start", "backend", "frontend"]
        ).services == ["backend", "frontend"]
        assert _cli.build_parser().parse_args(["start", "--dev"]).dev is True
        assert _cli.build_parser().parse_args(["start", "backend", "--no-browser"]).no_browser is True

    def test_existing_commands_unaffected(self, tmp_path, capsys, monkeypatch):
        """既有命令零回归: stop/status/doctor 照常 (注册表注册不破坏)。"""
        cli = make_cli(tmp_path)
        patch_ports(monkeypatch, value=False)
        for argv in (["status"], ["stop"]):
            args = _cli.build_parser().parse_args(argv)
            rc = cli.run(args)
            assert rc == 0, f"command {argv} regressed"
