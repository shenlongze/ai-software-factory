"""tests/change/test_change_cli.py — factory change 子命令 CLI 测试 (真实 git 仓库)。

覆盖: change commits / analyze / validate 的文本与 --json 输出、退出码
(0 PASS/SKIP / 3 FAIL / 1 ERROR / 2 用法)、审计事件 (git.commit.viewed /
change.analyzed / change.validation.completed)、--repo 显式路径、失败安全。
"""

from __future__ import annotations

import json

import pytest

from cli.main import main

from git_helpers import commit_all, write_file
from cli_helpers import event_types


class TestChangeCommits:
    def test_commits_show_linked_tasks(self, capsys, task_cli_root):
        rc = main(["--root", str(task_cli_root), "change", "commits"])
        out, _ = capsys.readouterr()
        assert rc == 0
        assert "MP-BUG-001" in out  # task 列
        assert "fix login crash" in out

    def test_commits_non_git_empty(self, capsys, cli_root):
        rc = main(["--root", str(cli_root), "change", "commits"])
        out, _ = capsys.readouterr()
        assert rc == 0
        assert "0 commits" in out

    def test_commits_json_shape(self, capsys, task_cli_root):
        rc = main(["--root", str(task_cli_root), "--json", "change", "commits"])
        out, _ = capsys.readouterr()
        assert rc == 0
        data = json.loads(out)
        assert data["count"] >= 1
        assert data["commits"][0]["task_id"] == "MP-BUG-001"

    def test_commits_limit(self, capsys, task_cli_root):
        main(["--root", str(task_cli_root), "change", "commits", "--limit", "1"])
        out, _ = capsys.readouterr()
        assert "1 commits" in out

    def test_commits_audit_event(self, capsys, task_cli_root):
        main(["--root", str(task_cli_root), "change", "commits"])
        capsys.readouterr()
        from cli_helpers import open_events

        store = open_events(task_cli_root)
        try:
            assert "git.commit.viewed" in event_types(store)
        finally:
            store.close()

    def test_commits_explicit_repo(self, capsys, cli_root, task_repo):
        rc = main(["--root", str(cli_root), "change", "commits",
                   "--repo", str(task_repo)])
        out, _ = capsys.readouterr()
        assert rc == 0
        assert "MP-BUG-001" in out


class TestChangeAnalyze:
    def test_analyze_output(self, capsys, task_cli_root):
        rc = main(["--root", str(task_cli_root), "change", "analyze", "MP-BUG-001"])
        out, _ = capsys.readouterr()
        assert rc == 0
        assert "变更分析 MP-BUG-001" in out
        assert "commit 关联: 1" in out

    def test_analyze_json(self, capsys, task_cli_root):
        rc = main(["--root", str(task_cli_root), "--json", "change", "analyze",
                   "MP-BUG-001"])
        out, _ = capsys.readouterr()
        assert rc == 0
        data = json.loads(out)
        assert data["task_id"] == "MP-BUG-001"
        assert data["analysis"]["commits"]

    def test_analyze_non_git_empty(self, capsys, cli_root):
        rc = main(["--root", str(cli_root), "change", "analyze", "MP-BUG-001"])
        out, _ = capsys.readouterr()
        assert rc == 0
        assert "commit 关联: 0" in out

    def test_analyze_event_emitted(self, capsys, task_cli_root):
        main(["--root", str(task_cli_root), "change", "analyze", "MP-BUG-001"])
        capsys.readouterr()
        from cli_helpers import open_events

        store = open_events(task_cli_root)
        try:
            assert "change.analyzed" in event_types(store)
        finally:
            store.close()

    def test_analyze_working_tree_files(self, capsys, task_cli_root):
        write_file(task_cli_root, "wip.py", "y = 2\n")
        rc = main(["--root", str(task_cli_root), "change", "analyze", "MP-BUG-001"])
        out, _ = capsys.readouterr()
        assert rc == 0
        assert "wip.py" in out


class TestChangeValidate:
    def test_validate_skip_non_git(self, capsys, cli_root):
        rc = main(["--root", str(cli_root), "change", "validate", "MP-BUG-001"])
        out, _ = capsys.readouterr()
        assert rc == 0  # SKIP 非失败
        assert "SKIP" in out

    def test_validate_pass_linked(self, capsys, task_cli_root):
        rc = main(["--root", str(task_cli_root), "change", "validate", "MP-BUG-001"])
        out, _ = capsys.readouterr()
        assert rc == 0
        assert "PASS" in out
        assert "L4.commit_link" in out

    def test_validate_fail_exit_3(self, capsys, task_cli_root):
        write_file(task_cli_root, "unrelated.py", "x = 1\n")
        rc = main(["--root", str(task_cli_root), "change", "validate", "MP-TASK-099"])
        out, err = capsys.readouterr()
        assert rc == 3
        assert "FAIL" in out

    def test_validate_error_exit_1(self, capsys, task_cli_root, monkeypatch):
        def _boom(self):
            raise RuntimeError("git exploded")

        monkeypatch.setattr("git.client.GitClient.status", _boom)
        rc = main(["--root", str(task_cli_root), "change", "validate", "MP-BUG-001"])
        out, err = capsys.readouterr()
        assert rc == 1
        assert "ERROR" in out

    def test_validate_json_result(self, capsys, task_cli_root):
        rc = main(["--root", str(task_cli_root), "--json", "change", "validate",
                   "MP-BUG-001"])
        out, _ = capsys.readouterr()
        assert rc == 0
        data = json.loads(out)
        assert data["result"]["status"] == "PASS"
        assert data["result"]["checks"]

    def test_validate_event_emitted(self, capsys, task_cli_root):
        main(["--root", str(task_cli_root), "change", "validate", "MP-BUG-001"])
        capsys.readouterr()
        from cli_helpers import open_events

        store = open_events(task_cli_root)
        try:
            types = event_types(store)
            assert "change.validation.completed" in types
            assert "git.commit.linked" in types
        finally:
            store.close()

    def test_validate_task_title_from_store(self, capsys, task_cli_root):
        from tasks.models import Task
        from tasks.store import TaskStore

        TaskStore(task_cli_root / "tasks").create(
            Task(id="MP-BUG-001", title="Fix login crash", project="default"))
        rc = main(["--root", str(task_cli_root), "change", "validate", "MP-BUG-001"])
        out, _ = capsys.readouterr()
        assert rc == 0
        assert "PASS" in out


class TestChangeUsage:
    def test_unknown_change_command_exit_2(self, capsys, cli_root):
        # argparse 对未知子命令抛 SystemExit(2) (发生在 main 返回前, 同
        # tests/recovery / tests/runtime 用法错误模式)
        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "change", "frobnicate"])
        out, err = capsys.readouterr()
        assert exc.value.code == 2
        assert "invalid choice" in err or "unknown change command" in err

    def test_change_requires_subcommand(self, cli_root):
        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "change"])
        assert exc.value.code == 2

    def test_analyze_requires_task_id(self, cli_root):
        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "change", "analyze"])
        assert exc.value.code == 2
