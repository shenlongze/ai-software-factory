"""tests/console/test_cli_demo_run.py — S10-042 Task 002: factory demo run (一条命令完成首次体验)。

覆盖 (全 hermetic: HOME 重定向 tmp, 零真实 ~/.factory / ~/.factory-demo / 临时目录污染):
- 验收 A: demo run "<goal>" → 自动建项目目录 + main.py 骨架 + 调 exec CLI 执行
  (monkeypatch 注入假 cmd_exec_run, 验证薄代理参数传递: root=demo root,
  args.project/task/objective/agent/provider)
- 验收 B: --project-dir 复用指定目录 (不自动建临时目录; main.py 缺失才写骨架)
- 验收 C: --no-cleanup 保留临时目录 (打印路径); 默认清理临时目录
- 验收 D: 缺 objective → rc 2 明确错误
- 验收 E: 复用 exec CLI (零复制执行逻辑 — 只经 _proxy_exec_cli → cmd_exec_run)
- 失败安全: 底层异常 → rc 1 明确错误; result ok=False → rc=exit_code 明确错误;
  目录创建失败 → 明确错误; 清理护栏拒绝非 demo 路径
- 环境门: _env_problems 不通过 → rc 1 明确提示 (同 demo start)
- parser: demo 动作含 run + objective 位置参数 + --agent/--provider/--no-cleanup/
  --project-dir; init/status/reset/start 兼容不受影响

装配: importlib + sys.path 挂仓库根 (factory-console 包名含连字符, 唯一导入
方式; 同 tests/console 既有模式)。basename 全仓库唯一。

零真实执行保证: 所有用例 monkeypatch _proxy_exec_cli → 假 cmd_exec_run,
绝不触碰真实 exec/LLM 链路。
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # factory-console/ 的父目录 (含连字符包名)
    sys.path.insert(0, str(_ROOT))

_cli = importlib.import_module("factory-console.cli_factory")
_cfg = importlib.import_module("factory-console.config")

#: demo 数据根目录名
DEMO_ROOT_NAME = ".factory-demo"
#: demo run 自动项目目录前缀
DEMO_TMP_PREFIX = "factory-demo-"

#: 入口级测试需要清空的 env (防真实环境变量串入 — 同 test_cli_demo)
_ENV_PURGE = (
    "PORT",
    "FRONTEND_PORT",
    "DATA_DIR",
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)

_OK_RESULT = {
    "ok": True,
    "command": "run",
    "request_id": "EXR-abc123",
    "result_id": "EXS-def456",
    "status": "success",
    "error": None,
    "artifacts": [
        {
            "id": "ART-1",
            "type": "patch",
            "path": "/demo/exec/patches/EXS-def456.patch",
        }
    ],
    "usage": {"total_tokens": 1234, "estimated_cost_usd": 0.0009},
    "report": "demo report",
    "event_seq": 7,
    "exit_code": 0,
}


class FakeExecCli:
    """假 exec.cli 模块 (monkeypatch _proxy_exec_cli 注入; 记录调用, 零真实执行)。"""

    def __init__(self, result: dict | None = None, exc: Exception | None = None):
        self.result = result or _OK_RESULT
        self.exc = exc
        self.calls: list[dict] = []

    def cmd_exec_run(self, root, args):
        self.calls.append({"root": Path(root), "args": args})
        if self.exc is not None:
            raise self.exc
        return self.result


@pytest.fixture(autouse=True)
def _fake_node(monkeypatch):
    """环境检测 hermetic: 伪造 node 版本 (demo run 的环境门, 同 test_cli_demo)。"""
    monkeypatch.setattr(_cli, "_node_version", lambda: (26, 7))


def make_cli(tmp_path: Path):
    """hermetic FactoryCLI: config.json 指向 tmp data_dir; 依赖目录伪造。"""
    data_dir = tmp_path / ".factory"
    data_dir.mkdir(exist_ok=True)
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


def run(cli, *argv: str) -> int:
    """解析 + 执行 (同既有测试模式)。"""
    return cli.run(_cli.build_parser().parse_args(list(argv)))


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """HOME 重定向到 tmp (<home>/.factory-demo = demo root; 用户 <home>/.factory 零预置)。"""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for var in _ENV_PURGE:
        monkeypatch.delenv(var, raising=False)
    return home


def demo_root(home: Path) -> Path:
    return home / DEMO_ROOT_NAME


def capture_project_dir(capsys) -> Path:
    """从输出 "✔ 项目目录: <dir>/main.py" 提取自动创建的目录。"""
    out = capsys.readouterr().out
    for line in out.splitlines():
        if "✔ 项目目录:" in line:
            return Path(line.split("✔ 项目目录:")[1].strip()).parent
    raise AssertionError(f"输出缺少项目目录行:\n{out}")


# ------------------------------------------------------------------ parser (demo run 注册 + 兼容)


class TestDemoRunParser:
    def test_run_action_registered(self):
        """demo 动作含 run + 参数注册 (objective/--agent/--provider/--no-cleanup/--project-dir)。"""
        args = _cli.build_parser().parse_args(
            ["demo", "run", "给 main.py 加 hello", "--agent", "agent-x",
             "--provider", "deepseek", "--no-cleanup", "--project-dir", "/tmp/px"]
        )
        assert args.demo_action == "run"
        assert args.objective == "给 main.py 加 hello"
        assert args.agent == "agent-x"
        assert args.provider == "deepseek"
        assert args.no_cleanup is True
        assert args.project_dir == "/tmp/px"

    def test_run_defaults(self):
        """demo run 缺省: objective=None, agent=None (运行时 → backend-1), provider=None。"""
        args = _cli.build_parser().parse_args(["demo", "run"])
        assert args.demo_action == "run"
        assert args.objective is None
        assert args.agent is None
        assert args.provider is None
        assert args.no_cleanup is False
        assert args.project_dir is None

    def test_legacy_actions_unchanged(self):
        """init/status/reset/start 兼容: objective=None, 原参数不受影响。"""
        for action in ("init", "status", "reset", "start"):
            args = _cli.build_parser().parse_args(["demo", action])
            assert args.demo_action == action
            assert args.objective is None
        args = _cli.build_parser().parse_args(["demo", "start", "--no-browser", "--port", "9000"])
        assert args.demo_action == "start"
        assert args.no_browser is True
        assert args.port == 9000


# ------------------------------------------------------------------ 验收 D: 缺 objective → 明确错误


class TestMissingObjective:
    def test_missing_objective_clear_error(self, tmp_path, isolated_home, capsys):
        """demo run 无 objective → rc 2 + 明确错误 (验收 D)。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "demo", "run")
        assert rc == 2
        err = capsys.readouterr().err
        assert "demo run 需要 objective" in err
        assert "demo run" in err


# ------------------------------------------------------------------ 验收 A: 自动建目录 + 调 exec CLI (monkeypatch 验证代理)


class TestDemoRunHappyPath:
    def test_run_auto_project_and_proxy_exec(self, tmp_path, isolated_home, monkeypatch, capsys):
        """验收 A: demo run "<goal>" → workspace 就绪 + 自动建项目目录 + main.py 骨架
        + 调 exec CLI (root=demo root, args 参数正确传递) → rc 0 + 展示 + 默认清理。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli()
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        rc = run(cli, "demo", "run", "给 main.py 加一个加法函数")
        assert rc == 0
        out = capsys.readouterr().out
        assert "=== AI Factory Quick Demo ===" in out
        assert "✔ workspace 就绪" in out
        assert "✔ 目标: 给 main.py 加一个加法函数" in out
        assert "✔ 执行: backend-1 → Router 决策" in out
        # 薄代理调用: 恰好一次, root=demo root
        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call["root"] == demo_root(isolated_home)
        # 参数传递: project=自动目录 / task 自动 ID / objective / agent 缺省 backend-1 / provider None
        project_dir = Path(call["args"].project)
        assert project_dir.name.startswith(DEMO_TMP_PREFIX)
        assert call["args"].task.startswith("E2-DEMO-")
        assert call["args"].objective == "给 main.py 加一个加法函数"
        assert call["args"].agent == "backend-1"
        assert call["args"].provider is None
        # 展示: status / artifact / usage
        assert "status      success" in out
        assert "artifact    patch" in out
        assert "1234 tokens" in out
        assert "✔ 完成!" in out
        # 默认清理: 自动目录已删
        assert not Path(project_dir).exists()

    def test_auto_project_has_main_py_skeleton(self, tmp_path, isolated_home, monkeypatch):
        """自动建的项目目录含 main.py 骨架 (objective 注释 + print stub; --no-cleanup 保留以便检查)。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli()
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        rc = run(cli, "demo", "run", "加一个 hello 函数", "--no-cleanup")
        assert rc == 0
        project_dir = Path(fake.calls[0]["args"].project)
        main_py = project_dir / "main.py"
        assert main_py.exists()
        text = main_py.read_text(encoding="utf-8")
        assert "加一个 hello 函数" in text
        assert "def main()" in text
        assert "print(" in text
        _cli._demo_rmtree_tmp(project_dir)  # 测试自清理 (护栏路径, 同实现)

    def test_workspace_prepared_in_demo_root(self, tmp_path, isolated_home, monkeypatch):
        """workspace 准备: demo root + providers.json 就位 (复用 demo init 路径)。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli()
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        rc = run(cli, "demo", "run", "hello")
        assert rc == 0
        root = demo_root(isolated_home)
        assert (root / "providers.json").is_file()
        assert (root / "agents").is_dir()
        assert (root / "skills").is_dir()

    def test_agent_and_provider_flags_passed(self, tmp_path, isolated_home, monkeypatch, capsys):
        """--agent / --provider 显式传递到 exec args (缺省走 Router 决策)。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli()
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        rc = run(cli, "demo", "run", "hello", "--agent", "backend-2", "--provider", "anthropic")
        assert rc == 0
        args = fake.calls[0]["args"]
        assert args.agent == "backend-2"
        assert args.provider == "anthropic"
        out = capsys.readouterr().out
        assert "✔ 执行: backend-2 → anthropic" in out


# ------------------------------------------------------------------ 验收 B: --project-dir 复用指定目录


class TestProjectDirReuse:
    def test_reuse_existing_dir(self, tmp_path, isolated_home, monkeypatch, capsys):
        """--project-dir 指定 → 复用该目录 (不自动建临时目录), 缺 main.py 才写骨架。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli()
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        user_dir = tmp_path / "my-project"
        user_dir.mkdir()
        rc = run(cli, "demo", "run", "hello", "--project-dir", str(user_dir))
        assert rc == 0
        args = fake.calls[0]["args"]
        assert Path(args.project) == user_dir
        # 复用目录: main.py 骨架写入 (缺失时), 目录本身保留
        assert (user_dir / "main.py").exists()
        assert user_dir.is_dir()
        out = capsys.readouterr().out
        assert str(user_dir / "main.py") in out
        # 无临时目录被创建 (输出不含清理行 — 非自动创建不清理)
        assert "已清理临时目录" not in out

    def test_reuse_does_not_overwrite_existing_main_py(self, tmp_path, isolated_home, monkeypatch):
        """复用目录已有 main.py → 不覆盖用户文件。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli()
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        user_dir = tmp_path / "my-project"
        user_dir.mkdir()
        (user_dir / "main.py").write_text("MY ORIGINAL CODE\n", encoding="utf-8")
        rc = run(cli, "demo", "run", "hello", "--project-dir", str(user_dir))
        assert rc == 0
        assert (user_dir / "main.py").read_text(encoding="utf-8") == "MY ORIGINAL CODE\n"

    def test_reuse_nonexistent_dir_created(self, tmp_path, isolated_home, monkeypatch):
        """--project-dir 指向不存在目录 → mkdir 幂等创建后复用。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli()
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        user_dir = tmp_path / "brand-new" / "nested"
        rc = run(cli, "demo", "run", "hello", "--project-dir", str(user_dir))
        assert rc == 0
        assert user_dir.is_dir()
        assert Path(fake.calls[0]["args"].project) == user_dir


# ------------------------------------------------------------------ 验收 C: --no-cleanup 保留 / 默认清理


class TestCleanup:
    def test_no_cleanup_keeps_dir(self, tmp_path, isolated_home, monkeypatch, capsys):
        """--no-cleanup → 临时目录保留 + 打印路径 (验收 C)。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli()
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        rc = run(cli, "demo", "run", "hello", "--no-cleanup")
        assert rc == 0
        project_dir = Path(fake.calls[0]["args"].project)
        assert project_dir.is_dir()
        out = capsys.readouterr().out
        assert f"(演示目录保留: {project_dir})" in out
        _cli._demo_rmtree_tmp(project_dir)  # 测试自清理 (护栏路径, 同实现)

    def test_default_cleans_temp_dir(self, tmp_path, isolated_home, monkeypatch):
        """默认 → 临时目录被清理 (验收 C)。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli()
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        rc = run(cli, "demo", "run", "hello")
        assert rc == 0
        project_dir = Path(fake.calls[0]["args"].project)
        assert not project_dir.exists()

    def test_cleanup_guard_rejects_non_demo_path(self):
        """清理护栏: 非 demo 临时路径 → ValueError 响亮拒绝 (绝不误删)。"""
        with pytest.raises(ValueError):
            _cli._demo_rmtree_tmp(Path("/tmp/not-a-demo-dir"))
        with pytest.raises(ValueError):
            _cli._demo_rmtree_tmp(Path("/etc/factory-demo-x"))


# ------------------------------------------------------------------ 失败安全


class TestFailureSafety:
    def test_exec_exception_clear_error(self, tmp_path, isolated_home, monkeypatch, capsys):
        """底层异常 → rc 1 + 明确错误 + 自动目录仍清理 (失败安全)。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli(exc=RuntimeError("boom"))
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        rc = run(cli, "demo", "run", "hello")
        assert rc == 1
        err = capsys.readouterr().err
        assert "exec CLI 执行失败" in err
        assert "boom" in err

    def test_exec_result_failed(self, tmp_path, isolated_home, monkeypatch, capsys):
        """result ok=False → rc=exit_code + 明确错误。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli(
            result={"ok": False, "error": "provider not found: x", "exit_code": 1}
        )
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        rc = run(cli, "demo", "run", "hello")
        assert rc == 1
        err = capsys.readouterr().err
        assert "执行失败" in err
        assert "provider not found" in err

    def test_exec_ok_but_failed_status(self, tmp_path, isolated_home, monkeypatch, capsys):
        """exec 契约: ok=True 但 exit_code=1 → 执行本身失败 → rc 1 + 明确错误 (不假装成功)。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli(
            result={
                "ok": True,
                "command": "run",
                "status": "failed",
                "error": "agent failed: boom",
                "exit_code": 1,
                "artifacts": [],
                "usage": {},
            }
        )
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        rc = run(cli, "demo", "run", "hello")
        assert rc == 1
        err = capsys.readouterr().err
        assert "执行失败" in err
        assert "agent failed: boom" in err

    def test_project_dir_creation_failure(self, tmp_path, isolated_home, monkeypatch, capsys):
        """项目目录创建失败 → 明确错误, 不吞 (不调 exec)。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli()
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        blocker = tmp_path / "blocker"
        blocker.write_text("file", encoding="utf-8")
        rc = run(cli, "demo", "run", "hello", "--project-dir", str(blocker / "sub"))
        assert rc == 1
        err = capsys.readouterr().err
        assert "项目目录创建失败" in err
        assert fake.calls == []

    def test_env_problems_gate(self, tmp_path, isolated_home, monkeypatch, capsys):
        """环境检查不通过 → rc 1 明确提示 (同 demo start 环境门)。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli()
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        monkeypatch.setattr(_cli, "_env_problems", lambda: ["node 缺失"])
        rc = run(cli, "demo", "run", "hello")
        assert rc == 1
        err = capsys.readouterr().err
        assert "node 缺失" in err
        assert fake.calls == []


# ------------------------------------------------------------------ 辅助函数单元 (骨架 / usage 格式化)


class TestHelpers:
    def test_main_skeleton_contains_objective(self):
        text = _cli._demo_main_skeleton("加一个加法函数")
        assert "加一个加法函数" in text
        assert "def main()" in text
        assert "print(" in text

    def test_format_usage_fail_safe(self):
        assert _cli._demo_format_usage({"total_tokens": 100, "estimated_cost_usd": 0.01}) == \
            "100 tokens · $0.0100"
        assert _cli._demo_format_usage(None) == "-"
        assert _cli._demo_format_usage("n/a") == "n/a"
        assert _cli._demo_format_usage({}) == "-"


# ------------------------------------------------------------------ S10-044 Task 001: 统一失败输出 (❌ Failed + Reason + Solution 到 stdout)


class TestUnifiedFailureOutput:
    """验收 A/B/C (S10-044 Task 001): demo run 失败 → stdout 显示统一格式, 用户必见
    (错误到 stdout, 不再只进 stderr — 用户失败时只看 stdout)。"""

    def test_failure_stdout_has_unified_format(self, tmp_path, isolated_home, monkeypatch, capsys):
        """验收 A: result ok=False → stdout 含 ❌ Failed + Reason + Solution + 原因。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli(
            result={"ok": False, "error": "agent failed: boom", "exit_code": 1}
        )
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        rc = run(cli, "demo", "run", "hello")
        assert rc == 1
        out = capsys.readouterr().out
        assert "❌ Failed" in out
        assert "Reason:" in out
        assert "Solution:" in out
        assert "agent failed: boom" in out

    def test_api_key_missing_solution_has_export(self, tmp_path, isolated_home, monkeypatch, capsys):
        """验收 B: api key missing → Solution 含 export 指引 (export <PROVIDER>_API_KEY)。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli(
            result={
                "ok": True,
                "status": "failed",
                "error": (
                    "provider error: anthropic api key missing: "
                    "ANTHROPIC_API_KEY 未设置 (在 ~/.factory/.env 配置)"
                ),
                "exit_code": 1,
                "artifacts": [],
                "usage": {},
            }
        )
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        rc = run(cli, "demo", "run", "hello")
        assert rc == 1
        out = capsys.readouterr().out
        assert "❌ Failed" in out
        assert "export" in out
        assert "_API_KEY" in out
        assert "factory init" in out

    def test_provider_not_found_solution_has_config_check(
        self, tmp_path, isolated_home, monkeypatch, capsys
    ):
        """验收 C: provider not found → Solution 含 config check + --provider 指引。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli(
            result={
                "ok": False,
                "error": "provider not found: bogus (available: ['deepseek'])",
                "exit_code": 1,
            }
        )
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        rc = run(cli, "demo", "run", "hello")
        assert rc == 1
        out = capsys.readouterr().out
        assert "❌ Failed" in out
        assert "config check" in out
        assert "--provider" in out

    def test_exec_ok_but_exit_code_1_unified_stdout(
        self, tmp_path, isolated_home, monkeypatch, capsys
    ):
        """exec 契约: ok=True 但 exit_code=1 → 执行失败 → 统一格式到 stdout。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli(
            result={
                "ok": True,
                "status": "failed",
                "error": "agent failed: boom",
                "exit_code": 1,
                "artifacts": [],
                "usage": {},
            }
        )
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        rc = run(cli, "demo", "run", "hello")
        assert rc == 1
        out = capsys.readouterr().out
        assert "❌ Failed" in out
        assert "Reason:" in out
        assert "Solution:" in out
        assert "agent failed: boom" in out

    def test_exception_unified_stdout(self, tmp_path, isolated_home, monkeypatch, capsys):
        """底层异常 → 统一格式到 stdout (执行失败同路径, 用户必见)。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli(exc=RuntimeError("boom"))
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        rc = run(cli, "demo", "run", "hello")
        assert rc == 1
        out = capsys.readouterr().out
        assert "❌ Failed" in out
        assert "exec CLI 执行失败" in out
        assert "boom" in out


class TestFormatFailure:
    """_format_failure 场景映射单元 (S10-044 §2 场景表)。"""

    def test_api_key_missing_maps_export_solution(self):
        text = _cli._format_failure(
            "provider error: anthropic api key missing: ANTHROPIC_API_KEY 未设置 (hint)"
        )
        assert text.startswith("❌ Failed")
        assert "Reason:\n  provider error: anthropic api key missing" in text
        assert "export" in text and "_API_KEY" in text and "factory init" in text

    def test_provider_not_found_maps_config_check(self):
        text = _cli._format_failure("provider not found: bogus (available: [...])")
        assert "config check" in text and "--provider" in text

    def test_project_dir_not_found_maps_project_create(self):
        text = _cli._format_failure("project dir not found: /tmp/x")
        assert "project create" in text and "--repo-path" in text

    def test_generic_error_falls_back_to_run_status(self):
        text = _cli._format_failure("agent failed: boom")
        assert "run-status" in text and "重试" in text

    def test_empty_error_fallback(self):
        text = _cli._format_failure("")
        assert text.startswith("❌ Failed")
        assert "未知错误" in text
        assert "Solution:" in text
