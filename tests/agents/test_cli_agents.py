"""tests/agents/test_cli_agents.py — CLI: factory agent add/list (+ agent.* 事件集成)。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli_helpers import event_types, open_events, run_cli
from cli.main import main
from events.models import EventType


class TestAgentAdd:
    def test_add_creates_agent_and_event(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(
            capsys, cli_root, "agent", "add", "--id", "A-001",
            "--role", "backend-developer", "--skills", "backend,flutter",
        )
        assert rc == 0
        assert "A-001" in out
        with open_events(cli_root) as store:
            assert event_types(store) == ["agent.registered"]
            ev = store.get(1)
            assert ev.type is EventType.AGENT_REGISTERED
            assert ev.agent_id == "A-001"
            assert ev.source == "agent_registry"
            assert ev.stage == "available"
            assert ev.payload["skills"] == ["backend", "flutter"]
            assert ev.payload["role"] == "backend-developer"

    def test_add_with_name_and_description(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(
            capsys, cli_root, "agent", "add", "--id", "A-002", "--role", "test-engineer",
            "--skills", "testing", "--name", "Tester", "--description", "负责测试",
        )
        assert rc == 0
        assert "Tester" in out
        with open_events(cli_root) as store:
            ev = store.get(1)
            assert ev.payload["name"] == "Tester"
            assert ev.payload["description"] == "负责测试"

    def test_add_duplicate_exit_1(self, capsys, cli_root: Path):
        args = ("agent", "add", "--id", "A-001", "--role", "r", "--skills", "s")
        rc1, _, _ = run_cli(capsys, cli_root, *args)
        rc2, _, err = run_cli(capsys, cli_root, *args)
        assert rc1 == 0
        assert rc2 == 1  # 已存在 → 一般错误
        assert "already exists" in err

    def test_add_missing_role_usage_exit_2(self, capsys, cli_root: Path):
        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "agent", "add", "--id", "A-001"])
        assert exc.value.code == 2  # 缺 --role → argparse 用法错误

    def test_add_json(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(
            capsys, cli_root, "agent", "add", "--id", "A-001",
            "--role", "backend-developer", "--skills", "backend", "--json",
        )
        assert rc == 0
        d = json.loads(out)
        assert d["ok"] is True
        assert d["agent"]["id"] == "A-001"
        assert d["agent"]["status"] == "AVAILABLE"
        assert d["event_seq"] >= 1

    def test_add_skills_csv_trimmed(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(
            capsys, cli_root, "agent", "add", "--id", "A-001",
            "--role", "r", "--skills", " backend , flutter , ", "--json",
        )
        assert rc == 0
        d = json.loads(out)
        assert d["agent"]["skills"] == ["backend", "flutter"]


class TestAgentList:
    def test_list_empty(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(capsys, cli_root, "agent", "list")
        assert rc == 0
        assert "0 agents" in out
        with open_events(cli_root) as store:
            assert event_types(store) == ["agent.viewed"]

    def test_list_shows_agents(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "agent", "add", "--id", "A-001", "--role", "backend-developer", "--skills", "backend")
        run_cli(capsys, cli_root, "agent", "add", "--id", "A-002", "--role", "test-engineer", "--skills", "testing")
        rc, out, _ = run_cli(capsys, cli_root, "agent", "list")
        assert rc == 0
        assert "A-001" in out
        assert "A-002" in out
        assert "backend-developer" in out
        assert "test-engineer" in out
        assert "2 agents" in out

    def test_list_filter_status(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "agent", "add", "--id", "A-001", "--role", "r", "--skills", "s")
        rc, out, _ = run_cli(capsys, cli_root, "agent", "list", "--status", "WORKING")
        assert rc == 0
        assert "0 agents" in out

    def test_list_filter_status_invalid_exit_2(self, capsys, cli_root: Path):
        rc, _, err = run_cli(capsys, cli_root, "agent", "list", "--status", "bogus")
        assert rc == 2
        assert "invalid agent status" in err

    def test_list_filter_skill_find_by_skill(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "agent", "add", "--id", "A-001", "--role", "r", "--skills", "backend")
        run_cli(capsys, cli_root, "agent", "add", "--id", "A-002", "--role", "r", "--skills", "flutter")
        rc, out, _ = run_cli(capsys, cli_root, "agent", "list", "--skill", "flutter")
        assert rc == 0
        assert "A-002" in out
        assert "A-001" not in out

    def test_list_json(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "agent", "add", "--id", "A-001", "--role", "r", "--skills", "s")
        rc, out, _ = run_cli(capsys, cli_root, "agent", "list", "--json")
        assert rc == 0
        d = json.loads(out)
        assert d["count"] == 1
        assert d["agents"][0]["id"] == "A-001"
        assert d["event_seq"] >= 2

    def test_list_emits_viewed_event(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "agent", "add", "--id", "A-001", "--role", "r", "--skills", "s")
        run_cli(capsys, cli_root, "agent", "list")
        with open_events(cli_root) as store:
            assert event_types(store) == ["agent.registered", "agent.viewed"]


class TestAgentPersistence:
    def test_agents_persist_across_commands(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "agent", "add", "--id", "A-001", "--role", "backend-developer", "--skills", "backend")
        assert (cli_root / "agents" / "agents.json").exists()
        rc, out, _ = run_cli(capsys, cli_root, "agent", "list")
        assert rc == 0
        assert "1 agents" in out

    def test_agent_list_before_any_add_is_empty(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(capsys, cli_root, "agent", "list")
        assert rc == 0
        assert "0 agents" in out
