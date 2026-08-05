"""tests/change/test_change_service.py — ChangeService 集成测试 (真实 git 仓库)。

覆盖: parse_commits (三来源 + 事件) / analyze (变更对账 + change.analyzed) /
change_context (任务标题装载 + 证据装配) / validate (L4 SKIP/PASS/FAIL/ERROR) /
bind_branch / snapshot_execution (Execution Git Snapshot 关联, 兼容旧记录)。
"""

from __future__ import annotations

import pytest

from events.models import EventType

from git.client import GitClient

from change.service import ChangeService, ChangeStore

from git_helpers import commit_all, write_file
from change_helpers import make_snapshot


def _add_task(store, task_id: str, title: str = "Fix login crash") -> None:
    from tasks.models import Task

    store.create(Task(id=task_id, title=title, project="markpad"))


class TestParseCommits:
    def test_task_ids_from_messages(self, task_repo, change_dir, logger):
        svc = ChangeService(client=GitClient(task_repo), logger=logger,
                            change_store=ChangeStore(change_dir))
        commits = svc.parse_commits(limit=10)
        assert len(commits) == 2
        by_msg = {c.message: c.task_id for c in commits}
        assert by_msg["MP-BUG-001: fix login crash"] == "MP-BUG-001"
        assert by_msg["MP-FEATURE-002: add settings page"] == "MP-FEATURE-002"

    def test_non_git_returns_empty(self, tmp_path, change_dir):
        svc = ChangeService(client=GitClient(tmp_path / "nope"),
                            change_store=ChangeStore(change_dir))
        assert svc.parse_commits() == []

    def test_linked_event_emitted(self, task_repo, change_dir, logger):
        svc = ChangeService(client=GitClient(task_repo), logger=logger,
                            change_store=ChangeStore(change_dir))
        svc.parse_commits(limit=10)
        types = [e.type for e in logger.store.query()]
        assert EventType.GIT_COMMIT_LINKED in types

    def test_no_event_without_task_ids(self, repo_path, change_dir, logger):
        svc = ChangeService(client=GitClient(repo_path), logger=logger,
                            change_store=ChangeStore(change_dir))
        svc.parse_commits(limit=10)
        types = [e.type for e in logger.store.query()]
        assert EventType.GIT_COMMIT_LINKED not in types

    def test_execution_task_fallback(self, repo_path, change_dir, logger):
        svc = ChangeService(client=GitClient(repo_path), logger=logger,
                            change_store=ChangeStore(change_dir))
        commits = svc.parse_commits(limit=10, execution_task_id="MP-TASK-014")
        assert all(c.task_id == "MP-TASK-014" for c in commits)


class TestAnalyze:
    def test_analysis_empty_on_non_git(self, tmp_path, change_dir, logger):
        svc = ChangeService(client=GitClient(tmp_path / "nope"), logger=logger,
                            change_store=ChangeStore(change_dir))
        a = svc.analyze("MP-BUG-001")
        assert a.files == []
        assert a.commits == []

    def test_analyze_records_commits(self, task_repo, change_dir, logger):
        svc = ChangeService(client=GitClient(task_repo), logger=logger,
                            change_store=ChangeStore(change_dir))
        a = svc.analyze("MP-BUG-001", limit=10)
        assert len(a.commits) == 1
        assert a.task_id == "MP-BUG-001"

    def test_change_analyzed_event(self, task_repo, change_dir, logger):
        svc = ChangeService(client=GitClient(task_repo), logger=logger,
                            change_store=ChangeStore(change_dir))
        svc.analyze("MP-BUG-001", limit=10)
        types = [e.type for e in logger.store.query()]
        assert EventType.CHANGE_ANALYZED in types

    def test_working_tree_changes_merged(self, task_repo, change_dir, logger):
        write_file(task_repo, "app/newfile.py", "x = 1\n")
        svc = ChangeService(client=GitClient(task_repo), logger=logger,
                            change_store=ChangeStore(change_dir))
        a = svc.analyze("MP-BUG-001", limit=10)
        assert any("newfile" in f for f in a.files)


class TestChangeContext:
    def test_non_repo_failsafe(self, tmp_path, change_dir, logger):
        svc = ChangeService(client=GitClient(tmp_path / "nope"), logger=logger,
                            change_store=ChangeStore(change_dir))
        ctx = svc.change_context("MP-BUG-001")
        assert ctx.is_repo is False
        assert ctx.error

    def test_task_title_loaded(self, task_repo, change_dir, logger, tmp_path):
        from tasks.store import TaskStore

        store = TaskStore(tmp_path / "tasks")
        _add_task(store, "MP-BUG-001", "修复登录崩溃")
        svc = ChangeService(client=GitClient(task_repo), logger=logger,
                            task_store=store, change_store=ChangeStore(change_dir))
        ctx = svc.change_context("MP-BUG-001")
        assert ctx.task_title == "修复登录崩溃"

    def test_commits_evidence(self, task_repo, change_dir, logger):
        svc = ChangeService(client=GitClient(task_repo), logger=logger,
                            change_store=ChangeStore(change_dir))
        ctx = svc.change_context("MP-BUG-001")
        assert ctx.is_repo is True
        assert [c.task_id for c in ctx.commits] == ["MP-BUG-001"]


class TestValidate:
    def test_skip_non_repo(self, tmp_path, change_dir, logger):
        svc = ChangeService(client=GitClient(tmp_path / "nope"), logger=logger,
                            change_store=ChangeStore(change_dir))
        result = svc.validate("MP-BUG-001")
        assert result.status == "SKIP"
        assert result.task_id == "MP-BUG-001"

    def test_pass_linked_commit(self, task_repo, change_dir, logger):
        svc = ChangeService(client=GitClient(task_repo), logger=logger,
                            change_store=ChangeStore(change_dir))
        assert svc.validate("MP-BUG-001").status == "PASS"

    def test_fail_unrelated_task(self, task_repo, change_dir, logger):
        svc = ChangeService(client=GitClient(task_repo), logger=logger,
                            change_store=ChangeStore(change_dir))
        # 制造工作区变更证据 (未提交文件); 仓库提交只关联 MP-BUG-001 /
        # MP-FEATURE-002 → 无关任务有证据但无关联 → FAIL
        write_file(task_repo, "unrelated.py", "x = 1\n")
        result = svc.validate("MP-TASK-099")
        assert result.status == "FAIL"

    def test_validation_event_emitted(self, task_repo, change_dir, logger):
        svc = ChangeService(client=GitClient(task_repo), logger=logger,
                            change_store=ChangeStore(change_dir))
        svc.validate("MP-BUG-001")
        types = [e.type for e in logger.store.query()]
        assert EventType.CHANGE_VALIDATION_COMPLETED in types

    def test_validation_event_payload_status(self, task_repo, change_dir, logger):
        svc = ChangeService(client=GitClient(task_repo), logger=logger,
                            change_store=ChangeStore(change_dir))
        svc.validate("MP-BUG-001")
        ev = [e for e in logger.store.query()
              if e.type == EventType.CHANGE_VALIDATION_COMPLETED][-1]
        assert ev.result == "PASS"

    def test_error_failsafe_on_internal_exception(self, tmp_path, change_dir, logger):
        class _BoomClient(GitClient):
            def status(self):
                raise RuntimeError("boom")

        svc = ChangeService(client=_BoomClient(tmp_path / "x"), logger=logger,
                            change_store=ChangeStore(change_dir))
        result = svc.validate("MP-BUG-001")
        assert result.status == "ERROR"
        assert "boom" in result.message

    def test_validate_never_raises(self, task_repo, change_dir, logger):
        svc = ChangeService(client=GitClient(task_repo), logger=logger,
                            change_store=ChangeStore(change_dir))
        for task_id in ("MP-BUG-001", "MP-FEATURE-002", "T-001", ""):
            result = svc.validate(task_id)
            assert result.status in ("PASS", "FAIL", "SKIP", "ERROR")


class TestBindBranch:
    def test_bound_event(self, task_repo, change_dir, logger):
        svc = ChangeService(client=GitClient(task_repo), logger=logger,
                            change_store=ChangeStore(change_dir))
        ctx = svc.bind_branch(branch="feature/MP-BUG-001-x")
        assert ctx.task_id == "MP-BUG-001"
        types = [e.type for e in logger.store.query()]
        assert EventType.GIT_TASK_BOUND in types

    def test_error_status_non_repo(self, tmp_path, change_dir, logger):
        svc = ChangeService(client=GitClient(tmp_path / "nope"), logger=logger,
                            change_store=ChangeStore(change_dir))
        ctx = svc.bind_branch()
        assert ctx.status == "error"


class TestSnapshotExecution:
    def test_snapshot_saved_and_queryable(self, task_repo, change_dir, logger):
        svc = ChangeService(client=GitClient(task_repo), logger=logger,
                            change_store=ChangeStore(change_dir),
                            project_id="markpad")
        snap = svc.snapshot_execution(execution_id="EX-001", task_id="MP-BUG-001")
        assert snap.after_commit  # 缺省 = 当前 HEAD
        assert svc.snapshots(task_id="MP-BUG-001") == [snap]

    def test_snapshot_non_git_recorded(self, tmp_path, change_dir, logger):
        svc = ChangeService(client=GitClient(tmp_path / "nope"), logger=logger,
                            change_store=ChangeStore(change_dir))
        snap = svc.snapshot_execution(execution_id="EX-1", task_id="T-001")
        assert snap.after_commit is None
        assert snap.changed_files == []

    def test_snapshot_changed_files_default_from_diff(self, task_repo, change_dir,
                                                      logger):
        write_file(task_repo, "wip.py", "y = 2\n")
        svc = ChangeService(client=GitClient(task_repo), logger=logger,
                            change_store=ChangeStore(change_dir))
        snap = svc.snapshot_execution(execution_id="EX-2", task_id="MP-BUG-001")
        assert "wip.py" in snap.changed_files

    def test_snapshots_empty_for_old_executions(self, task_repo, change_dir, logger):
        svc = ChangeService(client=GitClient(task_repo), logger=logger,
                            change_store=ChangeStore(change_dir))
        assert svc.snapshots(task_id="T-999") == []

    def test_snapshot_project_id(self, task_repo, change_dir, logger):
        svc = ChangeService(client=GitClient(task_repo), logger=logger,
                            change_store=ChangeStore(change_dir),
                            project_id="markpad")
        snap = svc.snapshot_execution(execution_id="EX-3", task_id="MP-BUG-001")
        assert snap.project_id == "markpad"
