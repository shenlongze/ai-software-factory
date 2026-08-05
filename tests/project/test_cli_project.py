"""test_cli_project.py — factory project list / show: 输出 / --json / 退出码 / 事件审计。

CLI 的 project 命令默认读取仓库根 examples/ (真实 markpad 配置) — 确定性输出;
事件断言走 cli_helpers (ADR-0002: 每个 CLI 行为必须产生 Event)。
"""

from __future__ import annotations

import json
from pathlib import Path

from cli_helpers import event_types, open_events, run_cli


class TestProjectList:
    def test_list_output(self, capsys, cli_root: Path):
        rc, out, err = run_cli(capsys, cli_root, "project", "list")
        assert rc == 0, err
        assert "markpad" in out
        assert "dart" in out
        assert "/Users/Shared/work/markpad" in out
        assert "1 projects" in out

    def test_list_json(self, capsys, cli_root: Path):
        rc, out, err = run_cli(capsys, cli_root, "--json", "project", "list")
        assert rc == 0, err
        data = json.loads(out)
        assert data["ok"] is True
        assert data["count"] == 1
        p = data["projects"][0]
        assert p["name"] == "markpad"
        assert p["language"] == "dart"
        assert p["tech_stack"] == ["flutter", "dart"]

    def test_list_emits_viewed_event(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(capsys, cli_root, "project", "list")
        assert rc == 0
        with open_events(cli_root) as store:
            assert event_types(store) == ["project.viewed"]


class TestProjectShow:
    def test_show_output(self, capsys, cli_root: Path):
        rc, out, err = run_cli(capsys, cli_root, "project", "show", "markpad")
        assert rc == 0, err
        assert "markpad" in out
        assert "language    dart" in out
        for agent in ("architect", "flutter-developer", "tester"):
            assert agent in out
        for skill in ("flutter", "dart", "testing", "architecture"):
            assert skill in out
        for wf in ("feature", "bug-fix", "release"):
            assert wf in out
        assert "reproduce → diagnose → fix → verify" in out

    def test_show_json(self, capsys, cli_root: Path):
        rc, out, err = run_cli(capsys, cli_root, "--json", "project", "show", "markpad")
        assert rc == 0, err
        data = json.loads(out)
        assert data["project"]["name"] == "markpad"
        assert len(data["agents"]) == 3
        assert len(data["skills"]) == 4
        assert len(data["workflows"]) == 3
        wf_ids = [w["id"] for w in data["workflows"]]
        assert wf_ids == ["bug-fix", "feature", "release"]
        feature = next(w for w in data["workflows"] if w["id"] == "feature")
        assert feature["steps"][1]["required_role"] == "developer"
        assert feature["steps"][1]["required_skill"] == "flutter"

    def test_show_not_found_exit_7(self, capsys, cli_root: Path):
        rc, out, err = run_cli(capsys, cli_root, "project", "show", "nope")
        assert rc == 7
        assert "project not found: nope" in err

    def test_show_emits_viewed_event_with_project_id(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "project", "show", "markpad")
        with open_events(cli_root) as store:
            events = store.query()
            assert [e.type.value for e in events] == ["project.viewed"]
            assert events[0].project_id == "markpad"
            assert events[0].payload["language"] == "dart"
            assert events[0].payload["agents"] == 3


class TestUsageErrors:
    def test_unknown_project_subcommand(self, capsys, cli_root: Path):
        import pytest
        from cli.main import main

        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "project", "bogus"])
        assert exc.value.code == 2

    def test_missing_name_usage_error(self, capsys, cli_root: Path):
        import pytest
        from cli.main import main

        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "project", "show"])
        assert exc.value.code == 2

    def test_every_project_command_emits_event(self, capsys, cli_root: Path):
        """铁律: 每次 project 命令调用至少新增一条事件。"""
        run_cli(capsys, cli_root, "project", "list")
        with open_events(cli_root) as store:
            n0 = store.count()
        run_cli(capsys, cli_root, "project", "show", "markpad")
        with open_events(cli_root) as store:
            assert store.count() == n0 + 1
