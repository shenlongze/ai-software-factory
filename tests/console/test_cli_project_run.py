"""tests/console/test_cli_project_run.py — S10-031: factory project/run 转正 (薄代理 org/exec CLI)。

覆盖 (全 hermetic, tmp_path 注入隔离 — 不读/写真实 ~/.factory):
- 验收 E: run 缺 --task / --project → 明确错误 (rc 2); project create 缺
  --repo-path → 明确错误 (rc 2)
- 验收 A: factory run --project <dir> --task <id> --agent backend-1 →
  薄代理 exec.cli.cmd_exec_run (monkeypatch 注入假 exec.cli 验证代理参数
  传递 + 1 个真跑冒烟: 真实 exec.cli 加载 + 诚实失败 provider not found)
- 验收 B: factory run-status --id <id> → 薄代理 exec.cli.cmd_exec_status
- 验收 C: factory project create --repo-path <dir> → 薄代理
  org.cli.cmd_project_register (monkeypatch + 1 个真跑冒烟: 真实注册 +
  project list 回读)
- 验收 D: factory project list → 只读 projects.json 输出 (有/无数据;
  缺失/损坏 → 空列表, 永不抛)
- 失败安全: 底层异常 / importlib 加载失败 → 清晰错误消息 (不吞不裸抛)
- 回归: project/run 已不在 STUB_COMMANDS; run-status 已注册为顶层子命令

装配: importlib + sys.path 挂仓库根 + factory-core (同 tests/console 既有
模式; factory-console 包名含连字符, 唯一导入方式)。basename 全仓库唯一。
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
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))

_cli = importlib.import_module("factory-console.cli_factory")
_cfg = importlib.import_module("factory-console.config")


def make_cli(tmp_path: Path, *, real_root: bool = False):
    """hermetic FactoryCLI: config.json 指向 tmp (data_dir 隔离), 零真实环境依赖。

    real_root=True → 不覆盖 root (self.root = 仓库根, 真跑冒烟用 —
    薄代理需定位 factory-exec/factory-org); 否则 root=tmp (monkeypatch 用例)。
    """
    data_dir = tmp_path / ".factory"
    data_dir.mkdir(exist_ok=True)
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        json.dumps({"core": {"data_dir": str(data_dir)}}), encoding="utf-8"
    )
    config = _cfg.ConfigProvider(
        user_config_file=cfg_file, env_file=tmp_path / ".env", environ={}
    )
    root = None if real_root else tmp_path
    return _cli.FactoryCLI(config, root=root)


def run(cli, *argv: str) -> int:
    """解析 + 执行 (同既有测试模式)。"""
    return cli.run(_cli.build_parser().parse_args(list(argv)))


# ------------------------------------------------------------------ 假代理 (monkeypatch 注入)


class FakeExecCli:
    """假 exec.cli — 记录代理调用 (验证参数传递) + 最小 _print_result。"""

    def __init__(self, result: dict | None = None, exc: Exception | None = None) -> None:
        self.calls: list[tuple] = []
        self.exc = exc
        self.result = result or {
            "ok": True,
            "command": "run",
            "request_id": "EXR-1",
            "result_id": "RES-1",
            "status": "success",
            "error": None,
            "artifacts": [],
            "usage": None,
            "report": "",
            "event_seq": 1,
            "exit_code": 0,
        }

    def cmd_exec_run(self, root, args):
        self.calls.append(("run", root, args))
        if self.exc is not None:
            raise self.exc
        return self.result

    def cmd_exec_status(self, root, args):
        self.calls.append(("status", root, args))
        return {
            "ok": True,
            "command": "status",
            "count": 1,
            "results": [{"id": "RES-1", "status": "success", "request_id": "EXR-1"}],
            "approval_count": 0,
            "event_seq": 1,
            "exit_code": 0,
        }

    def _print_result(self, args, result):
        if result.get("command") == "run":
            print("✔ 执行完成")
            print(f"  result_id   {result['result_id']}")
        elif result.get("command") == "status":
            print(f"执行结果 {result['count']} 条")


class FakeOrgCli:
    """假 org.cli — 记录代理调用 (验证参数传递) + 最小 _print_result。"""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def cmd_project_register(self, root, args):
        self.calls.append(("register", root, args))
        return {
            "ok": True,
            "project": {"id": "P-1", "name": "demo"},
            "analysis_ref": "",
            "baseline_ref": "",
            "snapshot_ref": "",
            "analysis": {},
            "baseline": {},
            "exit_code": 0,
        }

    def _print_result(self, args, result):
        print("✔ 项目注册成功")
        print(f"  id  {result['project']['id']}")


# ------------------------------------------------------------------ 验收 E: 参数缺失 → 明确错误


class TestRunRequiredArgs:
    def test_run_missing_task_and_objective(self, tmp_path, capsys):
        """验收 B (S10-042-003): 无 --task 且无 --objective → 明确错误 (rc 2)。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "run", "--project", str(tmp_path))
        err = capsys.readouterr().err
        assert rc == 2
        assert "--task 必填" in err and "--objective 必填" in err

    def test_run_missing_project(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        rc = run(cli, "run", "--task", "E2-001")
        err = capsys.readouterr().err
        assert rc == 2
        assert "--project 必填" in err

    def test_project_create_missing_repo_path(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        rc = run(cli, "project", "create")
        err = capsys.readouterr().err
        assert rc == 2
        assert "--repo-path 必填" in err

    def test_project_unknown_action(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        rc = run(cli, "project")  # 缺动作 → 明确错误 (非 stub 提示)
        err = capsys.readouterr().err
        assert rc == 2
        assert "需要子命令" in err
        assert "尚未实现" not in err


# ------------------------------------------------------------------ 验收 A: run → 代理 exec CLI


class TestRunProxy:
    def test_run_proxies_exec_cli_with_args(self, tmp_path, monkeypatch, capsys):
        """--project/--task/--agent 原样传给 cmd_exec_run (root=data_dir)。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli()
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        rc = run(
            cli, "run", "--project", str(repo_dir), "--task", "E2-001",
            "--agent", "backend-1",
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert "✔ 执行完成" in out and "RES-1" in out
        assert len(fake.calls) == 1
        kind, root, args = fake.calls[0]
        assert kind == "run"
        assert root == cli.data_dir  # 薄代理: root 即工厂数据根
        assert args.project == str(repo_dir)
        assert args.task == "E2-001"
        assert args.agent == "backend-1"

    def test_run_json_output(self, tmp_path, monkeypatch, capsys):
        """--json → 结构化 JSON (同 exec CLI 契约)。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli()
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        rc = run(cli, "run", "--project", str(tmp_path), "--task", "T-9", "--json")
        data = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert data["ok"] is True
        assert data["result_id"] == "RES-1"


# ------------------------------------------------------------ S10-042 Task 003: run --objective


class TestRunObjective:
    def test_run_objective_auto_generates_task(self, tmp_path, monkeypatch, capsys):
        """验收 A: run --project <dir> --objective <goal> → 调 exec CLI —
        task 自动生成 (非空, E2-OBJ-* 前缀), objective 透传。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli()
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        rc = run(
            cli, "run", "--project", str(repo_dir),
            "--objective", "给 main.py 加一个加法函数",
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert "✔ 执行完成" in out and "RES-1" in out
        assert len(fake.calls) == 1
        kind, root, args = fake.calls[0]
        assert kind == "run"
        assert root == cli.data_dir  # 薄代理: root 即工厂数据根
        assert args.task  # 自动生成非空
        assert args.task.startswith("E2-OBJ-")
        assert args.objective == "给 main.py 加一个加法函数"  # objective 透传

    def test_run_objective_json_output(self, tmp_path, monkeypatch, capsys):
        """--objective + --json → 结构化 JSON (task 自动生成不破坏 JSON 契约)。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli()
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        rc = run(cli, "run", "--project", str(repo_dir), "--objective", "加测试", "--json")
        data = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert data["ok"] is True
        assert data["result_id"] == "RES-1"
        assert fake.calls[0][2].task.startswith("E2-OBJ-")

    def test_run_objective_real_smoke_honest_failure(self, tmp_path, monkeypatch, capsys):
        """真实 exec.cli 链路: --objective 路径 → task 自动生成 + objective
        透传 → 真实 cmd_exec_run (provider bogus → 诚实失败 rc 1, 不发网络)。"""
        monkeypatch.setenv("HOME", str(tmp_path))  # 隔离 ~/.factory
        cli = make_cli(tmp_path, real_root=True)
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        rc = run(
            cli, "run", "--project", str(repo_dir),
            "--objective", "真实链路目标", "--provider", "bogus",
        )
        out = capsys.readouterr().out
        assert rc == 1
        # S10-044: 统一失败格式到 stdout (错误不再只进 stderr)
        assert "❌ Failed" in out
        assert "provider not found: bogus" in out
        assert "config check" in out

    def test_run_objective_with_explicit_task_still_works(self, tmp_path, monkeypatch, capsys):
        """验收 C: 旧用法 --task 仍工作 (task 优先, 不自动生成覆盖)。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli()
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        rc = run(
            cli, "run", "--project", str(repo_dir), "--task", "T-001",
            "--objective", "修复 bug",
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert "✔ 执行完成" in out
        assert len(fake.calls) == 1
        _, _, args = fake.calls[0]
        assert args.task == "T-001"  # task 优先, 原样透传
        assert args.objective == "修复 bug"  # objective 仍透传

    def test_run_status_proxies_exec_cli(self, tmp_path, monkeypatch, capsys):
        """验收 B: run-status --id → cmd_exec_status (root=data_dir, id 透传)。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli()
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        rc = run(cli, "run-status", "--id", "RES-1")
        out = capsys.readouterr().out
        assert rc == 0
        assert "执行结果 1 条" in out
        assert len(fake.calls) == 1
        kind, root, args = fake.calls[0]
        assert kind == "status"
        assert root == cli.data_dir
        assert args.id == "RES-1"

    def test_run_real_smoke_honest_failure(self, tmp_path, monkeypatch, capsys):
        """真跑冒烟: 真实 exec.cli 加载 (importlib + PYTHONPATH) + 诚实失败。

        --provider bogus → cmd_exec_run 返回 provider not found (rc 1,
        不发网络请求) — 证明代理链路真实可用, 不 mock。
        """
        monkeypatch.setenv("HOME", str(tmp_path))  # 隔离 ~/.factory
        cli = make_cli(tmp_path, real_root=True)
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        rc = run(
            cli, "run", "--project", str(repo_dir), "--task", "E2-001",
            "--agent", "backend-1", "--provider", "bogus",
        )
        out = capsys.readouterr().out
        assert rc == 1
        # S10-044: 统一失败格式到 stdout (错误不再只进 stderr)
        assert "❌ Failed" in out
        assert "provider not found: bogus" in out
        assert "config check" in out


# ------------------------------------------------------------------ 验收 C: project create → 代理 org CLI


class TestProjectCreateProxy:
    def test_project_create_proxies_org_cli(self, tmp_path, monkeypatch, capsys):
        """--repo-path 原样传给 cmd_project_register (root=data_dir)。"""
        cli = make_cli(tmp_path)
        fake = FakeOrgCli()
        monkeypatch.setattr(cli, "_proxy_org_cli", lambda: fake)
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        rc = run(cli, "project", "create", "--repo-path", str(repo_dir))
        out = capsys.readouterr().out
        assert rc == 0
        assert "✔ 项目注册成功" in out and "P-1" in out
        assert len(fake.calls) == 1
        kind, root, args = fake.calls[0]
        assert kind == "register"
        assert root == cli.data_dir
        assert args.repo_path == str(repo_dir)

    def test_project_create_json_output(self, tmp_path, monkeypatch, capsys):
        cli = make_cli(tmp_path)
        fake = FakeOrgCli()
        monkeypatch.setattr(cli, "_proxy_org_cli", lambda: fake)
        rc = run(cli, "project", "create", "--repo-path", str(tmp_path), "--json")
        data = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert data["ok"] is True
        assert data["project"]["id"] == "P-1"

    def test_project_create_real_smoke(self, tmp_path, monkeypatch, capsys):
        """真跑冒烟: 真实 org.cli 加载 + 真实注册 → projects.json 落盘 → list 回读。"""
        monkeypatch.setenv("HOME", str(tmp_path))  # 隔离 ~/.factory
        cli = make_cli(tmp_path, real_root=True)
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "main.py").write_text("print('hello')\n", encoding="utf-8")
        rc = run(cli, "project", "create", "--repo-path", str(repo_dir))
        out = capsys.readouterr().out
        assert rc == 0
        assert "✔ 项目注册成功" in out
        # 落盘: <data_dir>/org/projects.json (org store 格式 {"projects": {...}})
        projects_file = cli.data_dir / "org" / "projects.json"
        assert projects_file.is_file()
        raw = json.loads(projects_file.read_text(encoding="utf-8"))
        section = raw["projects"]
        assert len(section) == 1
        project = next(iter(section.values()))
        assert project["repo_path"] == str(repo_dir.resolve())
        # list 回读显示 id/name
        rc2 = run(cli, "project", "list")
        out2 = capsys.readouterr().out
        assert rc2 == 0
        pid = next(iter(section))
        assert f"项目清单 (1 个)" in out2
        assert pid in out2 and project["name"] in out2


# ------------------------------------------------------------------ 验收 D: project list → 只读 projects.json


class TestProjectList:
    def test_list_empty_when_missing(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        rc = run(cli, "project", "list")
        out = capsys.readouterr().out
        assert rc == 0
        assert "项目清单 (0 个)" in out

    def test_list_with_data(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        org_dir = cli.data_dir / "org"
        org_dir.mkdir(parents=True)
        (org_dir / "projects.json").write_text(
            json.dumps(
                {
                    "projects": {
                        "P-1": {"id": "P-1", "name": "alpha"},
                        "P-2": {"id": "P-2", "name": "beta"},
                    }
                }
            ),
            encoding="utf-8",
        )
        rc = run(cli, "project", "list")
        out = capsys.readouterr().out
        assert rc == 0
        assert "项目清单 (2 个)" in out
        assert "P-1  alpha" in out and "P-2  beta" in out

    def test_list_json_mode(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        org_dir = cli.data_dir / "org"
        org_dir.mkdir(parents=True)
        (org_dir / "projects.json").write_text(
            json.dumps({"projects": {"P-1": {"id": "P-1", "name": "alpha"}}}),
            encoding="utf-8",
        )
        rc = run(cli, "project", "list", "--json")
        data = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert data["ok"] is True and data["count"] == 1
        assert data["projects"][0] == {"id": "P-1", "name": "alpha"}

    def test_list_corrupt_file_empty(self, tmp_path, capsys):
        """损坏 projects.json → 空列表, rc 0 (只读失败安全, 永不抛)。"""
        cli = make_cli(tmp_path)
        org_dir = cli.data_dir / "org"
        org_dir.mkdir(parents=True)
        (org_dir / "projects.json").write_text("{corrupt", encoding="utf-8")
        rc = run(cli, "project", "list")
        out = capsys.readouterr().out
        assert rc == 0
        assert "项目清单 (0 个)" in out


# ------------------------------------------------------------------ 失败安全: 底层异常 → 清晰错误


class TestFailureSafety:
    def test_exec_cli_exception_clear_error(self, tmp_path, monkeypatch, capsys):
        cli = make_cli(tmp_path)

        def boom():
            raise RuntimeError("boom")

        monkeypatch.setattr(cli, "_proxy_exec_cli", boom)
        rc = run(cli, "run", "--project", str(tmp_path), "--task", "E2-001")
        err = capsys.readouterr().err
        assert rc == 1
        assert "exec CLI 执行失败" in err and "boom" in err

    def test_org_cli_exception_clear_error(self, tmp_path, monkeypatch, capsys):
        cli = make_cli(tmp_path)

        def boom():
            raise RuntimeError("org boom")

        monkeypatch.setattr(cli, "_proxy_org_cli", boom)
        rc = run(cli, "project", "create", "--repo-path", str(tmp_path))
        err = capsys.readouterr().err
        assert rc == 1
        assert "org CLI 注册失败" in err and "org boom" in err


# ------------------------------------------------------------------ 回归: 转正不破坏其余命令


class TestNoRegression:
    def test_project_run_no_longer_stubs(self):
        """S10-031: project/run 已从 STUB_COMMANDS 移除 (转正完成)。"""
        assert "project" not in _cli.STUB_COMMANDS
        assert "run" not in _cli.STUB_COMMANDS

    def test_run_status_registered_as_top_level(self):
        """run-status 已注册为顶层子命令 (验收 B 的 CLI 面)。"""
        parser = _cli.build_parser()
        for action in parser._actions:
            if getattr(action, "choices", None):
                choices = set(action.choices)
                assert {"project", "run", "run-status"} <= choices
                return
        pytest.fail("subparsers not found")

    def test_run_parser_flags_match_exec_cli(self):
        """run 参数与 exec CLI 对齐 (--project/--task/--agent/--provider/--json...)。"""
        ns = _cli.build_parser().parse_args(
            ["run", "--project", "/x", "--task", "T-1", "--agent", "a1",
             "--provider", "p1", "--objective", "o", "--requirement", "r",
             "--employee", "e1", "--test-cmd", "pytest", "--json"]
        )
        assert ns.command == "run"
        assert ns.project == "/x" and ns.task == "T-1"
        assert ns.agent == "a1" and ns.provider == "p1"
        assert ns.objective == "o" and ns.requirement == "r"
        assert ns.employee == "e1" and ns.test_cmd == "pytest"
        assert ns.json is True

    def test_existing_commands_unaffected(self, tmp_path, capsys):
        """新增 project/run/run-status 不破坏既有命令 (status rc 0)。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "status")
        assert rc == 0


# ------------------------------------------------------------------ S10-044 Task 001: run 失败统一输出 (❌ Failed + Reason + Solution 到 stdout)


class TestRunUnifiedFailure:
    """验收 D (S10-044 Task 001): run 执行失败 → 统一格式到 stdout (用户必见)。"""

    def test_run_failure_unified_format_stdout(self, tmp_path, monkeypatch, capsys):
        """ok=True 但 exit_code=1 (执行本身失败) → ❌ Failed + Reason + Solution 到 stdout。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli(
            result={
                "ok": True,
                "command": "run",
                "status": "failed",
                "error": "agent failed: boom",
                "exit_code": 1,
                "artifacts": [],
                "usage": None,
            }
        )
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        rc = run(cli, "run", "--project", str(repo_dir), "--task", "E2-001")
        out = capsys.readouterr().out
        assert rc == 1
        assert "❌ Failed" in out
        assert "Reason:" in out
        assert "Solution:" in out
        assert "agent failed: boom" in out
        assert "run-status" in out  # 通用 Solution (执行失败)

    def test_run_ok_false_unified_stdout(self, tmp_path, monkeypatch, capsys):
        """ok=False (provider not found) → 统一格式到 stdout + config check Solution。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli(
            result={
                "ok": False,
                "error": "provider not found: bogus (available: ['deepseek'])",
                "exit_code": 1,
            }
        )
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        rc = run(cli, "run", "--project", str(repo_dir), "--task", "E2-001")
        out = capsys.readouterr().out
        assert rc == 1
        assert "❌ Failed" in out
        assert "provider not found: bogus" in out
        assert "config check" in out  # provider not found → Solution 含 config check

    def test_run_exception_unified_stdout(self, tmp_path, monkeypatch, capsys):
        """底层异常 → 统一格式到 stdout (错误不再只进 stderr)。"""
        cli = make_cli(tmp_path)
        fake = FakeExecCli(exc=RuntimeError("boom"))
        monkeypatch.setattr(cli, "_proxy_exec_cli", lambda: fake)
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        rc = run(cli, "run", "--project", str(repo_dir), "--task", "E2-001")
        out = capsys.readouterr().out
        assert rc == 1
        assert "❌ Failed" in out
        assert "exec CLI 执行失败" in out
        assert "boom" in out

    def test_usage_error_stays_simple(self, tmp_path, capsys):
        """验收 E: 参数校验错误 (缺 --task) 仍简单 '错误: ...' (用法错误不统一)。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "run", "--project", str(tmp_path))
        err = capsys.readouterr().err
        assert rc == 2
        assert "错误: --task 必填" in err
        assert "❌ Failed" not in err
