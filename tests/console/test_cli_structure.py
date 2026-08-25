"""tests/console/test_cli_structure.py — S10-026 Task C: Factory CLI 命令组骨架。

覆盖 (全 hermetic, tmp_path + 显式 config 注入隔离 — 不读/写真实 ~/.factory):
- 验收 A: agent/skill/task/router/rag/audit 六子命令注册齐全; 每个 --help 退出 0
  且含 usage + 子命令说明 (help 完整)
- 验收 B: factory agent 只读列出现有 agents (agents.json: id/name/role/skills)
- 验收 C: factory task 只读列出 tasks (tasks/*.json: id/title/status)
- 验收 D: factory audit 只读查询事件库 (events.db 最近事件 + 按类型计数)
- 验收 E: factory rag query/index/sources (S10-123 K-6 转正)
- 验收 F: factory router 骨架展示五层链 + 当前决策 (无 provider → 未命中提示)
- 验收 G: 无数据时空列表不报错 (rc 0 + 空列表提示); 损坏数据失败安全
- 验收 H: 既有命令零影响 (status/stop 照常 rc 0); skill 兼容单文件/目录两形态

装配: importlib + sys.path 挂仓库根 (factory-console 包名含连字符, 唯一导入
方式; 同 tests/console 既有模式)。basename 全仓库唯一。

只读保证: 所有被测命令只读数据文件; 测试自身用 tmp_path 造数据, 不触碰
真实 ~/.factory。
"""

from __future__ import annotations

import importlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # factory-console/ 的父目录 (含连字符包名)
    sys.path.insert(0, str(_ROOT))

_cli = importlib.import_module("factory-console.cli_factory")
_cfg = importlib.import_module("factory-console.config")

GROUP_COMMANDS = ["agent", "skill", "task", "router", "rag", "audit"]


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


def subcommand_names(parser) -> set[str]:
    """已注册子命令名集合 (argparse subparsers choices)。"""
    for action in parser._actions:
        if getattr(action, "choices", None):
            return set(action.choices)
    return set()


# ------------------------------------------------------------------ 验收 A: 命令存在 + --help 完整


class TestCommandRegistration:
    def test_six_group_commands_registered(self):
        """六子命令注册齐全 (agent/skill/task/router/rag/audit)。"""
        names = subcommand_names(_cli.build_parser())
        for cmd in GROUP_COMMANDS:
            assert cmd in names, f"缺少子命令 {cmd}"

    def test_help_exits_zero_with_usage(self, capsys):
        """每个子命令 --help → SystemExit(0) + usage + 说明 (验收 A help 完整)。"""
        parser = _cli.build_parser()
        for cmd in GROUP_COMMANDS:
            with pytest.raises(SystemExit) as exc:
                parser.parse_args([cmd, "--help"])
            assert exc.value.code == 0, f"{cmd} --help 应退出 0"
            out = capsys.readouterr().out
            assert "usage:" in out, f"{cmd} --help 缺 usage"
            assert cmd in out, f"{cmd} --help 缺命令名"

    def test_audit_limit_flag(self):
        """audit --limit 参数解析 (默认 10)。"""
        args = _cli.build_parser().parse_args(["audit"])
        assert args.limit == 10
        args = _cli.build_parser().parse_args(["audit", "--limit", "3"])
        assert args.limit == 3


# ------------------------------------------------------------------ 数据装配 helpers


def seed_agents(data_dir: Path) -> None:
    """agents/agents.json (dict 按 id 索引形态, 同真实存储)。"""
    agents_dir = data_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "agents.json").write_text(
        json.dumps(
            {
                "backend-1": {
                    "id": "backend-1",
                    "name": "backend-1",
                    "role": "backend-developer",
                    "skills": ["development", "python"],
                },
                "flutter-dev": {
                    "id": "flutter-dev",
                    "name": "Flutter Dev",
                    "role": "developer",
                    "skills": ["flutter", "dart"],
                },
            }
        ),
        encoding="utf-8",
    )


def seed_tasks(data_dir: Path) -> None:
    """tasks/*.json (每文件一条任务, 同真实存储)。"""
    tasks_dir = data_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / "T-001.json").write_text(
        json.dumps(
            {
                "id": "T-001",
                "title": "Fix markdown parser",
                "project": "markpad",
                "status": "BACKLOG",
            }
        ),
        encoding="utf-8",
    )
    (tasks_dir / "T-002.json").write_text(
        json.dumps(
            {
                "id": "T-002",
                "title": "Add export",
                "project": "markpad",
                "status": "IN_PROGRESS",
            }
        ),
        encoding="utf-8",
    )


def seed_events_db(data_dir: Path, n: int = 5) -> Path:
    """events.db (events 表, 同 factory-core/events/store.py schema 子集)。"""
    db_path = data_dir / "events.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE events ("
            " seq INTEGER PRIMARY KEY AUTOINCREMENT,"
            " event_id TEXT NOT NULL UNIQUE,"
            " timestamp TEXT NOT NULL,"
            " type TEXT NOT NULL,"
            " source TEXT NOT NULL,"
            " project_id TEXT, task_id TEXT, agent_id TEXT,"
            " stage TEXT, action TEXT, result TEXT, evidence TEXT,"
            " payload TEXT NOT NULL)"
        )
        for i in range(n):
            typ = "task.started" if i % 2 == 0 else "task.completed"
            conn.execute(
                "INSERT INTO events (event_id, timestamp, type, source,"
                " project_id, task_id, payload) VALUES (?,?,?,?,?,?,?)",
                (
                    f"evt-{i}",
                    f"2026-08-14T00:00:{i:02d}Z",
                    typ,
                    "exec",
                    "markpad",
                    f"T-00{i + 1}",
                    "{}",
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return db_path


# ------------------------------------------------------------------ 验收 B: agent 只读展示


class TestAgent:
    def test_list_agents_readonly(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        seed_agents(cli.data_dir)
        args = _cli.build_parser().parse_args(["agent"])
        rc = cli.run(args)
        out = capsys.readouterr().out
        assert rc == 0
        assert "Agent 管理" in out
        assert "backend-1" in out and "backend-developer" in out
        assert "Flutter Dev" in out and "flutter, dart" in out
        assert "共 2 个 agent" in out

    def test_agents_missing_no_data(self, tmp_path, capsys):
        """无 agents.json → 空列表提示, rc 0 不报错 (验收 G)。"""
        cli = make_cli(tmp_path)
        rc = cli.run(_cli.build_parser().parse_args(["agent"]))
        out = capsys.readouterr().out
        assert rc == 0
        assert "无 agents 数据" in out

    def test_agents_corrupt_failsafe(self, tmp_path, capsys):
        """损坏 agents.json → 失败安全空列表 (验收 G)。"""
        cli = make_cli(tmp_path)
        agents_dir = cli.data_dir / "agents"
        agents_dir.mkdir()
        (agents_dir / "agents.json").write_text("{corrupt", encoding="utf-8")
        rc = cli.run(_cli.build_parser().parse_args(["agent"]))
        assert rc == 0
        assert "无 agents 数据" in capsys.readouterr().out


# ------------------------------------------------------------------ 验收 C: task 只读展示


class TestTask:
    def test_list_tasks_readonly(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        seed_tasks(cli.data_dir)
        rc = cli.run(_cli.build_parser().parse_args(["task"]))
        out = capsys.readouterr().out
        assert rc == 0
        assert "Task 管理" in out
        assert "T-001" in out and "Fix markdown parser" in out and "BACKLOG" in out
        assert "T-002" in out and "IN_PROGRESS" in out
        assert "共 2 个 task" in out

    def test_tasks_missing_no_data(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        rc = cli.run(_cli.build_parser().parse_args(["task"]))
        assert rc == 0
        assert "无 tasks 数据" in capsys.readouterr().out


# ------------------------------------------------------------------ 验收 D: audit 只读查询


class TestAudit:
    def test_events_recent_and_counts(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        seed_events_db(cli.data_dir, n=5)
        rc = cli.run(_cli.build_parser().parse_args(["audit"]))
        out = capsys.readouterr().out
        assert rc == 0
        assert "审计查询" in out
        assert "按类型计数" in out
        assert "task.started: 3" in out and "task.completed: 2" in out
        assert "最近 5 条事件" in out
        assert "#5" in out and "task.completed" in out
        assert "T-005" in out  # 作用域列 (task_id)

    def test_audit_limit(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        seed_events_db(cli.data_dir, n=5)
        rc = cli.run(_cli.build_parser().parse_args(["audit", "--limit", "2"]))
        out = capsys.readouterr().out
        assert rc == 0
        assert "最近 2 条事件" in out
        assert "#5" in out
        assert "#3" not in out

    def test_audit_no_db(self, tmp_path, capsys):
        """无事件库 → 提示, rc 0 (验收 G)。"""
        cli = make_cli(tmp_path)
        rc = cli.run(_cli.build_parser().parse_args(["audit"]))
        assert rc == 0
        assert "未找到事件库" in capsys.readouterr().out

    def test_audit_empty_db(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        seed_events_db(cli.data_dir, n=0)
        rc = cli.run(_cli.build_parser().parse_args(["audit"]))
        assert rc == 0
        assert "无事件数据" in capsys.readouterr().out

    def test_audit_factory_db_fallback(self, tmp_path, capsys):
        """events.db 缺失 → 兜底 factory.db (含 events 表)。"""
        cli = make_cli(tmp_path)
        seed_events_db(cli.data_dir, n=3)
        (cli.data_dir / "events.db").rename(cli.data_dir / "factory.db")
        rc = cli.run(_cli.build_parser().parse_args(["audit"]))
        out = capsys.readouterr().out
        assert rc == 0
        assert "factory.db" in out and "按类型计数" in out

    def test_audit_readonly_no_side_effect(self, tmp_path, capsys):
        """audit 只读: 查询后 events 表行数不变 (绝不写库)。"""
        cli = make_cli(tmp_path)
        seed_events_db(cli.data_dir, n=4)
        rc = cli.run(_cli.build_parser().parse_args(["audit"]))
        assert rc == 0
        capsys.readouterr()
        conn = sqlite3.connect(cli.data_dir / "events.db")
        try:
            assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 4
        finally:
            conn.close()


# ------------------------------------------------------------------ 验收 E: rag 子命令 (S10-123 K-6 转正)


class TestRag:
    def test_rag_subcommands_registered(self):
        """rag query/index/sources 子命令注册齐全。"""
        args = _cli.build_parser().parse_args(["rag", "query", "demo", "如何部署", "--top-k", "3"])
        assert args.command == "rag"
        assert args.rag_action == "query"
        assert args.project == "demo" and args.question == "如何部署" and args.top_k == 3
        args = _cli.build_parser().parse_args(["rag", "index", "demo", "--incremental"])
        assert args.rag_action == "index" and args.project == "demo" and args.incremental is True
        args = _cli.build_parser().parse_args(["rag", "sources"])
        assert args.rag_action == "sources"

    def test_rag_sources_no_registry_empty_not_crash(self, tmp_path, capsys):
        """rag sources 未配置/未注册 → rc 0 + 空不崩 (接口就绪状态)。"""
        cli = make_cli(tmp_path)
        rc = cli.run(_cli.build_parser().parse_args(["rag", "sources"]))
        out = capsys.readouterr().out
        assert rc == 0
        assert "外部知识源" in out
        assert "未配置" in out or "无已注册" in out


# ------------------------------------------------------------------ 验收 F: router 骨架


class TestRouter:
    def test_router_skeleton_no_provider(self, tmp_path, capsys):
        """无 providers.json → 五层链展示 + 当前决策未命中, rc 0。"""
        cli = make_cli(tmp_path)
        rc = cli.run(_cli.build_parser().parse_args(["router"]))
        out = capsys.readouterr().out
        assert rc == 0
        assert "LLM Router 状态" in out
        for layer in ("L1", "L2", "L3", "L4", "L5"):
            assert layer in out
        assert "当前决策" in out
        assert "未命中" in out

    def test_router_skeleton_with_provider(self, tmp_path, capsys, monkeypatch):
        """providers.json + enabled provider + key → 决策可命中 (L5 fallback)。"""
        cli = make_cli(tmp_path)
        (cli.data_dir / "providers.json").write_text(
            json.dumps(
                {
                    "providers": {
                        "deepseek": {
                            "id": "deepseek",
                            "enabled": True,
                            "api_key_ref": "env:DEEPSEEK_API_KEY",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        rc = cli.run(_cli.build_parser().parse_args(["router"]))
        out = capsys.readouterr().out
        assert rc == 0
        assert "L5 兜底: 可用" in out
        assert "当前决策: deepseek" in out


# ------------------------------------------------------------------ 验收 G/H: skill + 既有命令零影响


class TestSkill:
    def test_skill_single_file_registry(self, tmp_path, capsys):
        """skills/skills.json (单文件注册表, dict 形态)。"""
        cli = make_cli(tmp_path)
        skills_dir = cli.data_dir / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "skills.json").write_text(
            json.dumps(
                {
                    "flutter": {
                        "id": "flutter",
                        "name": "flutter",
                        "category": "framework",
                        "version": "1.0.0",
                    }
                }
            ),
            encoding="utf-8",
        )
        rc = cli.run(_cli.build_parser().parse_args(["skill"]))
        out = capsys.readouterr().out
        assert rc == 0
        assert "flutter" in out and "framework" in out and "v1.0.0" in out
        assert "共 1 个 skill" in out

    def test_skill_dir_form_fallback(self, tmp_path, capsys):
        """skills/*.json 目录形态兜底兼容 (exec skill 注册表)。"""
        cli = make_cli(tmp_path)
        skills_dir = cli.data_dir / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "dev.json").write_text(
            json.dumps({"id": "dev", "name": "dev", "category": "dev", "version": "0.1"})
            ,
            encoding="utf-8",
        )
        rc = cli.run(_cli.build_parser().parse_args(["skill"]))
        out = capsys.readouterr().out
        assert rc == 0
        assert "dev" in out and "共 1 个 skill" in out

    def test_skill_missing_no_data(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        rc = cli.run(_cli.build_parser().parse_args(["skill"]))
        assert rc == 0
        assert "无 skills 数据" in capsys.readouterr().out


class TestNoRegression:
    def test_existing_commands_unaffected(self, tmp_path, capsys):
        """新增命令不破坏既有命令 (验收 H): status/stop 照常 rc 0。"""
        cli = make_cli(tmp_path)
        for argv in (["status"], ["stop"]):
            rc = cli.run(_cli.build_parser().parse_args(list(argv)))
            assert rc == 0, f"command {argv} regressed"

    def test_stub_commands_still_present(self):
        """预留 stub (init/config/project/run) 不受影响。"""
        parser = _cli.build_parser()
        for name in _cli.STUB_COMMANDS:
            args = parser.parse_args([name])
            assert args.command == name
