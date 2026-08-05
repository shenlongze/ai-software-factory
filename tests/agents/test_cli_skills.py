"""tests/agents/test_cli_skills.py — CLI: factory skill add/list (+ skill.* 事件集成)。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli_helpers import event_types, open_events, run_cli
from cli.main import main
from events.models import EventType


class TestSkillAdd:
    def test_add_creates_skill_and_event(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(
            capsys, cli_root, "skill", "add", "--id", "flutter",
            "--category", "frontend", "--capabilities", "widget,dart", "--version", "2.0.0",
        )
        assert rc == 0
        assert "flutter" in out
        assert "2.0.0" in out
        with open_events(cli_root) as store:
            assert event_types(store) == ["skill.registered"]
            ev = store.get(1)
            assert ev.type is EventType.SKILL_REGISTERED
            assert ev.source == "skill_registry"
            assert ev.stage == "frontend"
            assert ev.payload["version"] == "2.0.0"
            assert ev.payload["capabilities"] == ["widget", "dart"]

    def test_add_defaults(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(capsys, cli_root, "skill", "add", "--id", "backend")
        assert rc == 0
        with open_events(cli_root) as store:
            ev = store.get(1)
            assert ev.payload["category"] == "general"
            assert ev.payload["version"] == "1.0.0"

    def test_add_with_name_and_description(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(
            capsys, cli_root, "skill", "add", "--id", "flutter", "--category", "frontend",
            "--name", "Flutter UI", "--description", "跨平台 UI", "--json",
        )
        assert rc == 0
        d = json.loads(out)
        assert d["skill"]["name"] == "Flutter UI"
        assert d["skill"]["description"] == "跨平台 UI"

    def test_add_duplicate_exit_1(self, capsys, cli_root: Path):
        args = ("skill", "add", "--id", "flutter")
        rc1, _, _ = run_cli(capsys, cli_root, *args)
        rc2, _, err = run_cli(capsys, cli_root, *args)
        assert rc1 == 0
        assert rc2 == 1
        assert "already exists" in err

    def test_add_missing_id_usage_exit_2(self, capsys, cli_root: Path):
        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "skill", "add"])
        assert exc.value.code == 2  # 缺 --id → argparse 用法错误

    def test_add_json(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(capsys, cli_root, "skill", "add", "--id", "backend", "--json")
        assert rc == 0
        d = json.loads(out)
        assert d["ok"] is True
        assert d["skill"]["version"] == "1.0.0"
        assert d["event_seq"] >= 1


class TestSkillList:
    def test_list_empty(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(capsys, cli_root, "skill", "list")
        assert rc == 0
        assert "0 skills" in out
        with open_events(cli_root) as store:
            assert event_types(store) == ["skill.viewed"]

    def test_list_shows_skills(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "skill", "add", "--id", "flutter", "--category", "frontend")
        run_cli(capsys, cli_root, "skill", "add", "--id", "backend", "--category", "backend")
        rc, out, _ = run_cli(capsys, cli_root, "skill", "list")
        assert rc == 0
        assert "flutter" in out
        assert "backend" in out
        assert "frontend" in out
        assert "2 skills" in out

    def test_list_filter_category(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "skill", "add", "--id", "flutter", "--category", "frontend")
        run_cli(capsys, cli_root, "skill", "add", "--id", "backend", "--category", "backend")
        rc, out, _ = run_cli(capsys, cli_root, "skill", "list", "--category", "frontend")
        assert rc == 0
        assert "flutter" in out
        assert "backend" not in out
        assert "1 skills" in out

    def test_list_json(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "skill", "add", "--id", "flutter", "--category", "frontend")
        rc, out, _ = run_cli(capsys, cli_root, "skill", "list", "--json")
        assert rc == 0
        d = json.loads(out)
        assert d["count"] == 1
        assert d["skills"][0]["id"] == "flutter"
        assert d["event_seq"] >= 2

    def test_list_emits_viewed_event(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "skill", "add", "--id", "flutter")
        run_cli(capsys, cli_root, "skill", "list")
        with open_events(cli_root) as store:
            assert event_types(store) == ["skill.registered", "skill.viewed"]


class TestSkillPersistence:
    def test_skills_persist_across_commands(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "skill", "add", "--id", "flutter", "--category", "frontend")
        assert (cli_root / "skills" / "skills.json").exists()
        rc, out, _ = run_cli(capsys, cli_root, "skill", "list")
        assert rc == 0
        assert "1 skills" in out
