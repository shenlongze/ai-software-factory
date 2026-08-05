"""tests/change/test_change_failsafe.py — 失败安全与边界 (空仓库/非 git/损坏数据)。

Change Intelligence 铁律: 任何仓库查询失败都不得抛异常 — commits 空 /
分析空 / L4 SKIP / bind error / 快照照常记录 (ADR-0019 决策 8)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from git.client import GitClient

from change.service import ChangeService, ChangeStore


def _svc(repo, **kw):
    """ChangeService 装配: change_store 显式注入 tmp 下 (hermetic — 库缺省
    ChangeStore() 指向 ~/.factory/change/snapshots.json, 落真实用户数据)。"""
    kw.setdefault("change_store", ChangeStore(Path(repo).parent / "change"))
    return ChangeService(client=GitClient(repo), **kw)


class TestNonGitFailsafe:
    def test_parse_commits_empty(self, tmp_path):
        assert _svc(tmp_path / "nope").parse_commits() == []

    def test_analyze_empty(self, tmp_path):
        a = _svc(tmp_path / "nope").analyze("MP-BUG-001")
        assert a.files == []
        assert a.insertions == 0
        assert a.deletions == 0
        assert a.commits == []

    def test_validate_skip(self, tmp_path):
        assert _svc(tmp_path / "nope").validate("MP-BUG-001").status == "SKIP"

    def test_change_context_not_repo(self, tmp_path):
        ctx = _svc(tmp_path / "nope").change_context("MP-BUG-001")
        assert ctx.is_repo is False
        assert ctx.error  # 失败原因承载, 不抛

    def test_bind_branch_error_status(self, tmp_path):
        assert _svc(tmp_path / "nope").bind_branch().status == "error"

    def test_snapshot_recorded_without_repo(self, tmp_path):
        svc = _svc(tmp_path / "nope")
        snap = svc.snapshot_execution(execution_id="EX-1", task_id="T-001")
        assert snap.after_commit is None
        assert snap.changed_files == []
        assert svc.snapshots(task_id="T-001") == [snap]

    def test_validate_never_raises(self, tmp_path):
        for task_id in ("MP-BUG-001", "T-001", "", "!!!"):
            result = _svc(tmp_path / "nope").validate(task_id)
            assert result.status in ("PASS", "FAIL", "SKIP", "ERROR")


class TestEmptyRepoFailsafe:
    @pytest.fixture
    def empty_repo(self, tmp_path):
        from git_helpers import init_repo

        return init_repo(tmp_path / "empty")

    def test_parse_commits_empty_repo(self, empty_repo):
        assert _svc(empty_repo).parse_commits() == []

    def test_analyze_empty_repo(self, empty_repo):
        a = _svc(empty_repo).analyze("MP-BUG-001")
        assert a.commits == []
        assert a.files == []

    def test_validate_skip_empty_repo(self, empty_repo):
        # 空仓库 (无提交无变更) → 无证据 → SKIP (不误报)
        assert _svc(empty_repo).validate("MP-BUG-001").status == "SKIP"

    def test_change_context_is_repo_true(self, empty_repo):
        ctx = _svc(empty_repo).change_context("MP-BUG-001")
        assert ctx.is_repo is True
        assert ctx.commits == []
        assert ctx.files == []

    def test_snapshot_after_commit_none(self, empty_repo):
        snap = _svc(empty_repo).snapshot_execution(execution_id="EX-1",
                                                   task_id="MP-BUG-001")
        assert snap.after_commit is None  # 无 HEAD


class TestCorruptedStoreFailsafe:
    def test_corrupted_snapshots_file(self, tmp_path, logger):
        store = ChangeStore(tmp_path / "change")
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text("###garbage###", encoding="utf-8")
        svc = ChangeService(client=GitClient(tmp_path / "nope"), logger=logger,
                            change_store=store)
        # 损坏快照文件不影响 validate / snapshots 查询
        assert svc.validate("MP-BUG-001").status == "SKIP"
        assert svc.snapshots() == []

    def test_missing_change_dir(self, tmp_path):
        svc = _svc(tmp_path / "nope")
        assert svc.snapshots() == []
        assert svc.store.load() == []


class TestMissingTaskCompat:
    def test_validate_unknown_task_in_store(self, task_repo, change_dir, logger,
                                            tmp_path):
        from tasks.store import TaskStore

        svc = ChangeService(client=GitClient(task_repo), logger=logger,
                            task_store=TaskStore(tmp_path / "tasks"),
                            change_store=ChangeStore(change_dir))
        # TaskStore 无该任务 → 标题空 → path_match SKIP; commit_link 判定照常
        result = svc.validate("MP-BUG-001")
        assert result.status in ("PASS", "FAIL", "SKIP")

    def test_analyze_unknown_task(self, task_repo, change_dir, logger):
        svc = ChangeService(client=GitClient(task_repo), logger=logger,
                            change_store=ChangeStore(change_dir))
        a = svc.analyze("T-999")
        assert a.task_id == "T-999"  # 不抛, 空分析可查
