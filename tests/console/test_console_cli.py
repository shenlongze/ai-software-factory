"""tests/console/test_console_cli.py — factory console CLI (Phase 11A, ADR-0034)。

覆盖:
- console dashboard: 文本七域汇总输出 / --json 结构 / --limit 截断
- console approvals: 文本清单 / --json / --pending 只列待办
- 退出码: 正常 rc 0; 未知子命令 rc 2; factory-console 缺失响亮 rc 7
  (Removal Isolation — 删除 console 包不影响其余命令)
- 有数据工厂: 各域计数正确投影 (真实 store 种子)
- 只读铁律: 读命令不写任何数据文件 (事件库 factory.db 为唯一允许的写)

basename 全仓库唯一 (test_console_* 前缀)。
"""

from __future__ import annotations

import argparse
import importlib
import json

import pytest

from events.store import EventStore

from intelligence.store import DecisionStore

from product.store import ProductStore

from console_helpers import (
    make_artifact,
    make_decision,
    make_idea,
    make_request,
    make_usage,
)
from providers.usage import UsageStore


def _run(root, *argv) -> int:
    from cli.main import main

    return main(["--root", str(root), *argv])


def _seed_factory(root):
    """种子: 1 idea + 1 artifact + 2 requests (1 pending) + 1 decision + 1 usage。"""
    product = ProductStore(root / "product")
    product.save_idea(make_idea(idea_id="idea-1", project_id="demo"))
    product.save_artifact(make_artifact(artifact_id="art-1", idea_id="idea-1"))
    product.save_request(
        make_request(request_id="req-1", artifact_id="art-1", idea_id="idea-1", status="pending")
    )
    product.save_request(
        make_request(request_id="req-2", artifact_id="art-1", idea_id="idea-1", status="approved")
    )
    decisions = DecisionStore(root / "intelligence")
    decisions.save(make_decision())
    usage = UsageStore(root / "providers")
    usage.record(make_usage(provider_id="hermes", estimated_cost=0.01, success=True))
    return product, decisions, usage


# ------------------------------------------------------------------ dashboard


class TestDashboardText:
    def test_seven_domain_summary_output(self, tmp_path, capsys):
        rc = _run(tmp_path, "console", "dashboard")
        out = capsys.readouterr().out
        assert rc == 0
        assert "Human Console — Dashboard 七域汇总 (只读)" in out
        assert "项目" in out
        assert "待审批" in out
        assert "运行中 Agent" in out
        assert "最近决策" in out
        assert "成本" in out
        assert "经验" in out
        assert "最近活动" in out
        assert "console.dashboard.viewed seq=" in out

    def test_counts_reflect_seeded_data(self, tmp_path, capsys):
        _seed_factory(tmp_path)
        _run(tmp_path, "console", "dashboard")
        out = capsys.readouterr().out
        assert "待审批      1  (共 2)" in out
        assert "最近决策    1" in out
        assert "$0.010000  (1 calls)" in out
        assert "最近活动    0 条" in out


class TestDashboardJson:
    def test_json_structure(self, tmp_path, capsys):
        rc = _run(tmp_path, "console", "dashboard", "--json")
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["ok"] is True
        assert data["event"] == "console.dashboard.viewed"
        assert isinstance(data["event_seq"], int)
        d = data["dashboard"]
        # 七域全部出现 (SECTIONS 键序)
        assert list(d.keys()) == [
            "projects",
            "approvals",
            "agents",
            "decisions",
            "cost",
            "experience",
            "activity",
        ]
        assert isinstance(d["projects"], list)  # workspace 内置示例项目可能非空
        assert d["cost"]["calls"] == 0
        assert d["experience"]["total"] == 0
        assert d["activity"] == []

    def test_json_counts_with_data(self, tmp_path, capsys):
        _seed_factory(tmp_path)
        _run(tmp_path, "console", "dashboard", "--json")
        d = json.loads(capsys.readouterr().out)["dashboard"]
        assert len(d["approvals"]) == 2
        assert len(d["decisions"]) == 1
        assert d["cost"]["calls"] == 1
        assert d["cost"]["total_cost"] == 0.01

    def test_limit_truncates_decisions(self, tmp_path, capsys):
        decisions = DecisionStore(tmp_path / "intelligence")
        for i in range(5):
            decisions.save(
                make_decision(
                    decision_id=f"dec-{i}",
                    created_at=f"2026-01-0{i + 1}T00:00:00.000000Z",
                )
            )
        _run(tmp_path, "console", "dashboard", "--limit", "2", "--json")
        d = json.loads(capsys.readouterr().out)["dashboard"]
        assert len(d["decisions"]) == 2
        assert d["decisions"][0]["id"] == "dec-4"  # 最近优先


# ------------------------------------------------------------------ approvals


class TestApprovalsText:
    def test_table_and_count_line(self, tmp_path, capsys):
        _seed_factory(tmp_path)
        rc = _run(tmp_path, "console", "approvals")
        out = capsys.readouterr().out
        assert rc == 0
        assert "Request" in out
        assert "req-1" in out
        assert "req-2" in out
        assert "2 approvals (pending: 1)" in out
        assert "console.viewed seq=" in out
        assert "view=approvals" in out

    def test_empty_factory_rc0(self, tmp_path, capsys):
        rc = _run(tmp_path, "console", "approvals")
        out = capsys.readouterr().out
        assert rc == 0
        assert "0 approvals (pending: 0)" in out


class TestApprovalsJson:
    def test_json_structure(self, tmp_path, capsys):
        _seed_factory(tmp_path)
        rc = _run(tmp_path, "console", "approvals", "--json")
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["ok"] is True
        assert data["count"] == 2
        assert data["pending"] == 1
        assert data["pending_only"] is False
        assert data["event"] == "console.viewed"
        assert [a["id"] for a in data["approvals"]] == ["req-1", "req-2"]
        a = data["approvals"][0]
        assert a["artifact_id"] == "art-1"
        assert a["gate"] == "prd"
        assert a["status"] == "pending"

    def test_pending_only_filters(self, tmp_path, capsys):
        _seed_factory(tmp_path)
        rc = _run(tmp_path, "console", "approvals", "--pending", "--json")
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["pending_only"] is True
        assert data["count"] == 1
        assert [a["id"] for a in data["approvals"]] == ["req-1"]


# ------------------------------------------------------------------ 退出码 / 缺失包


class TestExitCodes:
    def test_unknown_console_subcommand_rc2(self, tmp_path, capsys):
        """非法子命令 → argparse SystemExit(2) (入口契约, 同 recommend CLI 模式)。"""
        with pytest.raises(SystemExit) as exc:
            _run(tmp_path, "console", "bogus")
        assert exc.value.code == 2

    def test_console_missing_package_rc7(self, tmp_path, capsys, monkeypatch):
        """模拟删除 factory-console/ 包: dashboard 响亮 rc 7 (Removal Isolation)。"""
        orig = importlib.import_module

        def fake_import(name, package=None):
            if name == "factory-console" or name.startswith("factory-console"):
                raise ImportError(f"No module named {name!r} (simulated removal)")
            return orig(name, package)

        monkeypatch.setattr(importlib, "import_module", fake_import)
        rc = _run(tmp_path, "console", "dashboard")
        assert rc == 7
        err = capsys.readouterr().err
        assert "factory-console 未安装" in err

    def test_other_commands_unaffected_without_console(self, tmp_path, capsys, monkeypatch):
        """删除 console 包 → init/task 等其余命令零影响 (rc 0)。"""
        orig = importlib.import_module

        def fake_import(name, package=None):
            if name == "factory-console" or name.startswith("factory-console"):
                raise ImportError(f"No module named {name!r} (simulated removal)")
            return orig(name, package)

        monkeypatch.setattr(importlib, "import_module", fake_import)
        assert _run(tmp_path, "init") == 0
        assert _run(tmp_path, "task", "create", "--title", "t1", "--project", "demo") == 0

    def test_dashboard_rc0_on_empty_factory(self, tmp_path, capsys):
        """空工厂 (无任何数据): dashboard rc 0 + 事件照常写 (审计不因空失败)。"""
        assert _run(tmp_path, "console", "dashboard") == 0
        db = EventStore(tmp_path / "factory.db")
        try:
            assert [e.type.value for e in db.query()] == ["console.dashboard.viewed"]
        finally:
            db.close()


# ------------------------------------------------------------------ 只读铁律 (CLI 层)


class TestCliReadOnly:
    def test_read_commands_write_no_domain_files(self, tmp_path, capsys):
        """console dashboard/approvals 前后, 除 factory.db 外数据空间零变化。"""
        _seed_factory(tmp_path)

        def domain_snapshot(root):
            """排除 *.db (事件库/审计库为唯一允许的写, sqlite 二进制)。"""
            out = {}
            for path in sorted(root.rglob("*")):
                if path.is_file() and path.suffix != ".db":
                    out[str(path.relative_to(root))] = path.read_text(encoding="utf-8")
            return out

        before = domain_snapshot(tmp_path)
        _run(tmp_path, "console", "dashboard")
        _run(tmp_path, "console", "approvals", "--pending")
        after = domain_snapshot(tmp_path)
        assert after == before


# ======================================================================
# S10-007 阶段二 — bin/factory CLI MVP (start/stop/status)
# 覆盖: argparse 子命令结构 / 环境依赖配置检查 / pid 文件路径 / 幂等 /
#       端口占用提示 / 健康检查轮询 / 启动失败日志尾部 / stop 清理 / status
# 铁律: 不真起服务 (subprocess/urllib/端口 全部 monkeypatch 或纯函数)。
# 连字符包名 (factory-console.cli_factory) 无法用 import 语句, 统一经
# importlib 加载; conftest 已把仓库根挂 sys.path。
# ======================================================================


def _factory_cli_mod():
    """factory-console.cli_factory 模块 (连字符包, importlib 唯一加载方式)。"""
    return importlib.import_module("factory-console.cli_factory")


def _make_cli(tmp_path, **environ):
    """隔离 ConfigProvider (注入 environ) + 假 root 的 FactoryCLI 实例。"""
    mod = _factory_cli_mod()
    cfg = mod.ConfigProvider(
        environ={"DATA_DIR": str(tmp_path / "data"), **environ},
        env_file=tmp_path / "env",
        user_config_file=tmp_path / "cfg.json",
    )
    return mod.FactoryCLI(cfg, root=tmp_path)


def _parse(mod, *argv):
    """build_parser().parse_args → Namespace (测试 argparse 结构)。"""
    return mod.build_parser().parse_args(list(argv))


class TestFactoryCliArgparse:
    """子命令注册: start/stop/status/doctor/service + 命令组骨架
    (agent/skill/task/router/rag/audit) + 预留 init/config/project/run。"""

    def test_all_subcommands_registered(self):
        mod = _factory_cli_mod()
        parser = mod.build_parser()
        sub_actions = {
            a.dest: a
            for a in parser._actions
            if isinstance(a, argparse._SubParsersAction)  # noqa: SLF001
        }
        choices = set(sub_actions["command"].choices)
        assert choices == {
            "start",
            "stop",
            "status",
            "doctor",
            "service",  # S10-026 P3: 服务注册表 (cli_services)
            "agent",  # S10-026 Task C: 命令组骨架 (只读展示)
            "skill",
            "task",
            "router",
            "rag",
            "audit",
            "init",
            "config",
            "demo",  # S10-026 Task F: 隔离 Demo Workspace (~/.factory-demo)
            "project",  # S10-031: 转正 (create 代理 org CLI / list 只读)
            "exec",  # S10-083: 执行历史 (真实时间线)
            "run",  # S10-031: 转正 (薄代理 exec CLI cmd_exec_run)
            "run-status",  # S10-031: 转正 (薄代理 exec CLI cmd_exec_status)
            "repo",  # M1: 存量仓库模式 (理解→计划→改→测→修)
            "tools",  # M1: 工具发现 (AI CLI + MCP server, 增强层)
            "evidence",  # M1a: 证据包 (diff+test+决策, 可审计)
            "workload",  # M1b: 积压清道夫 (backlog/status)
            "approval",  # M1b: 审批门 (list/decide, 复用 ApprovalGate)
            "create",  # S10-1xx: 统一创建入口 (company/department/project, §1.4.5)
            "llm",  # v1.1.30: LLM 清单 (资源域)
            "todo",  # v1.1.30: 主线任务清单 (数据域)
            "help",  # v1.1.31: 命令总览 (按域分类)
            "update",  # v1.1.43: 整体/模块更新 (系统域)
            "mcp",  # v1.1.85 (S10-116 A-3): MCP 管理 (list/connect/remove)
            "eval",  # v1.1.95 (S10-121 K-5): 七维评测 + 发布门 (只读; --gate patch|minor|major)
            "artifacts",  # v1.1.109 (C-1): 产出物契约 (list/validate — 全部项目)
        }

    def test_start_flags_parsed(self):
        mod = _factory_cli_mod()
        ns = _parse(mod, "start", "--no-browser", "--port", "9000", "--frontend-port", "6000")
        assert ns.command == "start"
        assert ns.no_browser is True
        assert ns.port == 9000
        assert ns.frontend_port == 6000

    def test_legacy_stub_commands_now_implemented(self, capsys):
        """S10-031: project/run 不再返回 stub 提示 (参数缺失 → 明确错误 rc 2)。

        config 已于 S10-026 Task D 转正, init 已于 S10-026 Task E 转正,
        project/run/run-status 已于 S10-031 转正 (薄代理 org/exec CLI) —
        代理/查询/列表行为见 tests/console/test_cli_project_run.py。
        """
        mod = _factory_cli_mod()
        rc = mod.main(["run"])  # 缺 --task → 明确错误
        out, err = capsys.readouterr()
        assert rc == 2
        assert "--task 必填" in err
        assert "尚未实现" not in out + err
        rc = mod.main(["project"])  # 缺动作 → 明确错误
        out, err = capsys.readouterr()
        assert rc == 2
        assert "需要子命令" in err
        assert "尚未实现" not in out + err


class TestFactoryCliEnvironment:
    """环境/依赖/配置检查 (start 前三步, 不真起服务)。"""

    def test_python_too_old_hint(self, tmp_path, monkeypatch, capsys):
        mod = _factory_cli_mod()
        monkeypatch.setattr(mod, "MIN_PYTHON", (3, 99, 0))  # 运行时 3.x < 99 → 触发
        cli = _make_cli(tmp_path)
        assert cli.start(no_browser=True) == 1
        assert "Python 版本过低" in capsys.readouterr().err

    def test_node_missing_hint(self, tmp_path, monkeypatch, capsys):
        mod = _factory_cli_mod()
        monkeypatch.setattr(mod, "_node_version", lambda: None)
        cli = _make_cli(tmp_path)
        assert cli.start(no_browser=True) == 1
        assert "请安装" in capsys.readouterr().err

    def test_node_too_old_hint(self, tmp_path, monkeypatch, capsys):
        mod = _factory_cli_mod()
        monkeypatch.setattr(mod, "_node_version", lambda: (16, 5))
        cli = _make_cli(tmp_path)
        assert cli.start(no_browser=True) == 1
        assert "版本过低" in capsys.readouterr().err

    def test_deps_node_modules_missing_hint(self, tmp_path, monkeypatch, capsys):
        mod = _factory_cli_mod()
        # 假 root: 源码仓库 (有 pyproject.toml) 但无 .venv 无 node_modules → 依赖检查给出 install 指引
        fake_root = tmp_path / "fake"
        fake_root.mkdir(exist_ok=True)
        (fake_root / "pyproject.toml").write_text("", encoding="utf-8")
        (fake_root / "factory-console" / "web" / "frontend").mkdir(parents=True)
        problems = mod._dep_problems(fake_root)
        text = "\n".join(problems)
        assert "python3 -m venv .venv" in text
        assert "npm install" in text
        # 走 start 流程 → rc 1 + 依赖提示
        cli = _make_cli(tmp_path, DATA_DIR=str(tmp_path / "data"))
        cli.root = fake_root
        assert cli.start(no_browser=True) == 1
        assert "npm install" in capsys.readouterr().err

    def test_llm_key_missing_hint_but_continues(self, tmp_path, monkeypatch, capsys):
        """配置检查: key 缺失 → 提示 .env.example, 但不阻断 (继续启动)。"""
        mod = _factory_cli_mod()
        cli = _make_cli(tmp_path)
        assert mod._config_hints(cli.config)  # 无 key → 有提示
        # happy path: 全部启动步骤 mock 成功
        monkeypatch.setattr(mod, "_env_problems", lambda: [])
        monkeypatch.setattr(mod, "_dep_problems", lambda root: [])
        monkeypatch.setattr(mod, "_port_in_use", lambda port, host="127.0.0.1": False)
        monkeypatch.setattr(cli, "_backend_running", lambda: False)
        monkeypatch.setattr(cli, "_frontend_running", lambda: False)
        monkeypatch.setattr(cli, "_start_backend", lambda port: True)
        monkeypatch.setattr(cli, "_wait_backend", lambda port: True)
        monkeypatch.setattr(cli, "_start_frontend", lambda port: True)
        monkeypatch.setattr(cli, "_wait_frontend", lambda port: True)
        assert cli.start(no_browser=True) == 0
        out = capsys.readouterr().out
        assert "LLM API key 未配置" in out
        assert ".env.example" in out
        assert "已就绪" in out


class TestFactoryCliLifecycle:
    """pid 路径 / 幂等 / 端口占用 / 健康检查 / 失败日志 / stop / status。"""

    def test_pid_file_paths(self, tmp_path):
        cli = _make_cli(tmp_path)
        assert cli.backend_pid == tmp_path / "data" / "run" / "backend.pid"
        assert cli.frontend_pid == tmp_path / "data" / "run" / "frontend.pid"

    def test_start_idempotent_when_already_running(self, tmp_path, monkeypatch, capsys):
        mod = _factory_cli_mod()
        cli = _make_cli(tmp_path)
        monkeypatch.setattr(mod, "_env_problems", lambda: [])
        monkeypatch.setattr(mod, "_dep_problems", lambda root: [])
        monkeypatch.setattr(cli, "_backend_running", lambda: True)
        monkeypatch.setattr(cli, "_frontend_running", lambda: True)
        started = []

        def fake_start_backend(port):
            started.append(port)
            return True

        monkeypatch.setattr(cli, "_start_backend", fake_start_backend)
        assert cli.start(no_browser=True) == 0
        assert "已在运行" in capsys.readouterr().out
        assert started == []  # 不重复启动

    def test_port_in_use_hint(self, tmp_path, monkeypatch, capsys):
        mod = _factory_cli_mod()
        cli = _make_cli(tmp_path)
        monkeypatch.setattr(mod, "_env_problems", lambda: [])
        monkeypatch.setattr(mod, "_dep_problems", lambda root: [])
        monkeypatch.setattr(mod, "_port_in_use", lambda port, host="127.0.0.1": True)
        monkeypatch.setattr(cli, "_backend_running", lambda: False)
        monkeypatch.setattr(cli, "_frontend_running", lambda: False)
        assert cli.start(no_browser=True) == 1
        out = capsys.readouterr().err
        assert "端口已被占用" in out
        assert "FRONTEND_PORT" in out  # 修改配置指引

    def test_wait_http_polls_until_200(self, tmp_path, monkeypatch):
        mod = _factory_cli_mod()
        cli = _make_cli(tmp_path)
        seq = iter([0, 0, 200])

        def fake_status(url, timeout=2.0):
            return next(seq)

        monkeypatch.setattr(mod, "_http_status", fake_status)
        assert cli._wait_http("http://127.0.0.1:8011/api/projects", timeout=5.0) is True

    def test_wait_http_timeout_returns_false(self, tmp_path, monkeypatch):
        mod = _factory_cli_mod()
        cli = _make_cli(tmp_path)
        monkeypatch.setattr(mod, "_http_status", lambda url, timeout=2.0: 0)
        assert cli._wait_http("http://127.0.0.1:8011/api/projects", timeout=0.3) is False

    def test_backend_failure_shows_log_tail(self, tmp_path, monkeypatch, capsys):
        mod = _factory_cli_mod()
        cli = _make_cli(tmp_path)
        cli.run_dir.mkdir(parents=True)
        cli.backend_log.write_text("line1\nline2\nBOOM: port busy\n", encoding="utf-8")
        monkeypatch.setattr(mod, "_env_problems", lambda: [])
        monkeypatch.setattr(mod, "_dep_problems", lambda root: [])
        monkeypatch.setattr(mod, "_port_in_use", lambda port, host="127.0.0.1": False)
        monkeypatch.setattr(cli, "_backend_running", lambda: False)
        monkeypatch.setattr(cli, "_frontend_running", lambda: False)
        monkeypatch.setattr(cli, "_start_backend", lambda port: True)
        monkeypatch.setattr(cli, "_wait_backend", lambda port: False)
        assert cli.start(no_browser=True) == 1
        err = capsys.readouterr().err
        assert "日志尾部" in err
        assert "BOOM: port busy" in err  # 日志尾部透出真实失败行
        assert "后端启动失败" in err

    def test_stop_kills_pids_and_cleans_files(self, tmp_path, monkeypatch, capsys):
        mod = _factory_cli_mod()
        cli = _make_cli(tmp_path)
        cli.run_dir.mkdir(parents=True)
        cli.backend_pid.write_text("4242\n", encoding="utf-8")
        cli.frontend_pid.write_text("5151\n", encoding="utf-8")
        killed = []

        monkeypatch.setattr(mod, "_pid_alive", lambda pid: True)
        monkeypatch.setattr(mod, "_kill_pid", lambda pid, grace=2.0: killed.append(pid))
        monkeypatch.setattr(cli, "_kill_group", lambda pid: killed.append(("group", pid)))
        monkeypatch.setattr(mod, "_port_in_use", lambda port, host="127.0.0.1": False)
        assert cli.stop() == 0
        out = capsys.readouterr().out
        assert "已停止: 后端 (PID 4242), 前端 (PID 5151)" in out
        assert not cli.backend_pid.exists()
        assert not cli.frontend_pid.exists()
        assert ("group", 4242) in killed

    def test_status_shows_llm_data_dir_ports(self, tmp_path, monkeypatch, capsys):
        mod = _factory_cli_mod()
        cli = _make_cli(tmp_path, LLM_PROVIDER="deepseek", LLM_MODEL="test-model")
        monkeypatch.setattr(mod, "_pid_alive", lambda pid: False)
        monkeypatch.setattr(mod, "_port_in_use", lambda port, host="127.0.0.1": False)
        assert cli.status() == 0
        out = capsys.readouterr().out
        assert f"数据目录: {tmp_path / 'data'}" in out
        assert "provider=deepseek" in out
        assert "model=test-model" in out
        assert "api_key=未配置" in out  # 不打印 key 明文
        assert "后端: 未运行" in out
        assert "前端: 未运行" in out
        assert "未配置" not in out.replace("api_key=未配置", "")
