"""tests/git/test_git_failsafe.py — 失败安全专项 (Phase 6C 铁律: 永不抛未处理异常)。

覆盖: 非 git 目录 / git 命令不存在 (git_bin 注入坏路径) / 超时 (monkeypatch
subprocess.run 抛 TimeoutExpired) → 稳定错误摘要 (error 字段), 空列表返回,
不抛异常; GitChangeStore 损坏文件读 → 空列表 (单条损坏跳过)。

铁律断言: 所有场景不抛任何异常, 调用方照常拿到可渲染结果。
"""

from __future__ import annotations

import json
import subprocess

import pytest

from git.client import GitClient
from git.models import GitChange
from git.service import GitChangeStore, GitService


def _not_repo_dir(tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    return d


class TestNotARepository:
    def test_status_failsafe(self, tmp_path):
        ctx = GitClient(_not_repo_dir(tmp_path)).status()
        assert ctx.is_repo is False
        assert "not a git repository" in (ctx.error or "")
        assert ctx.branch is None
        assert ctx.current_commit is None

    def test_diff_empty(self, tmp_path):
        assert GitClient(_not_repo_dir(tmp_path)).diff() == []

    def test_log_empty(self, tmp_path):
        assert GitClient(_not_repo_dir(tmp_path)).log() == []

    def test_is_repo_false(self, tmp_path):
        assert GitClient(_not_repo_dir(tmp_path)).is_repo() is False

    def test_current_branch_none(self, tmp_path):
        assert GitClient(_not_repo_dir(tmp_path)).current_branch() is None

    def test_current_commit_none(self, tmp_path):
        assert GitClient(_not_repo_dir(tmp_path)).current_commit() is None

    def test_service_get_status_error(self, tmp_path, changes_dir):
        svc = GitService(
            GitClient(_not_repo_dir(tmp_path)), project_id="p", changes_store=GitChangeStore(changes_dir)
        )
        ctx = svc.get_status()
        assert ctx.is_repo is False
        assert ctx.project_id == "p"
        assert ctx.changes == []
        assert ctx.error

    def test_service_get_changes_empty(self, tmp_path, changes_dir):
        svc = GitService(GitClient(_not_repo_dir(tmp_path)), changes_store=GitChangeStore(changes_dir))
        assert svc.get_changes() == []

    def test_service_get_commits_empty(self, tmp_path, changes_dir):
        svc = GitService(GitClient(_not_repo_dir(tmp_path)), changes_store=GitChangeStore(changes_dir))
        assert svc.get_commits() == []

    def test_client_constructed_with_missing_dir(self, tmp_path):
        """目录不存在 (路径错误) → 同失败安全路径, 不抛。"""
        ctx = GitClient(tmp_path / "no-such-dir").status()
        assert ctx.is_repo is False
        assert ctx.error


class TestCommandMissing:
    def test_status_command_not_found(self, repo_path):
        c = GitClient(repo_path, git_bin="/nonexistent/git-xyz")
        ctx = c.status()
        assert ctx.is_repo is False
        assert "not found" in (ctx.error or "")

    def test_diff_empty(self, repo_path):
        assert GitClient(repo_path, git_bin="/nonexistent/git-xyz").diff() == []

    def test_log_empty(self, repo_path):
        assert GitClient(repo_path, git_bin="/nonexistent/git-xyz").log() == []

    def test_is_repo_false(self, repo_path):
        assert GitClient(repo_path, git_bin="/nonexistent/git-xyz").is_repo() is False

    def test_service_failsafe(self, repo_path, changes_dir):
        svc = GitService(
            GitClient(repo_path, git_bin="/nonexistent/git-xyz"), changes_store=GitChangeStore(changes_dir)
        )
        ctx = svc.get_status()
        assert ctx.is_repo is False
        assert "not found" in (ctx.error or "")
        assert svc.get_changes() == []
        assert svc.get_commits() == []


class TestTimeout:
    def _patch_run_timeout(self, monkeypatch):
        def boom(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="git", timeout=0.001)

        monkeypatch.setattr(subprocess, "run", boom)

    def test_status_timeout(self, repo_path, monkeypatch):
        self._patch_run_timeout(monkeypatch)
        ctx = GitClient(repo_path).status()
        assert ctx.is_repo is False
        assert "timed out" in (ctx.error or "")

    def test_diff_empty(self, repo_path, monkeypatch):
        self._patch_run_timeout(monkeypatch)
        assert GitClient(repo_path).diff() == []

    def test_log_empty(self, repo_path, monkeypatch):
        self._patch_run_timeout(monkeypatch)
        assert GitClient(repo_path).log() == []

    def test_is_repo_false(self, repo_path, monkeypatch):
        self._patch_run_timeout(monkeypatch)
        assert GitClient(repo_path).is_repo() is False

    def test_service_status_error(self, repo_path, changes_dir, monkeypatch):
        self._patch_run_timeout(monkeypatch)
        svc = GitService(GitClient(repo_path), changes_store=GitChangeStore(changes_dir))
        ctx = svc.get_status()
        assert ctx.is_repo is False
        assert "timed out" in (ctx.error or "")


class TestGitChangeStoreFailsafe:
    def test_load_missing_file_empty(self, store: GitChangeStore):
        assert store.load() == []

    def test_load_corrupt_json_empty(self, changes_dir, store: GitChangeStore):
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text("{not json!!", encoding="utf-8")
        assert store.load() == []

    def test_load_not_a_list_empty(self, changes_dir, store: GitChangeStore):
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text('{"task_id": "T-1"}', encoding="utf-8")
        assert store.load() == []

    def test_load_bad_item_skipped(self, changes_dir, store: GitChangeStore):
        """单条损坏跳过, 不拖垮整库 (失败安全)。"""
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text(
            json.dumps([{"task_id": "T-1", "files": ["a.py"]}, "junk", 42]),
            encoding="utf-8",
        )
        records = store.load()
        assert len(records) == 1
        assert records[0].task_id == "T-1"

    def test_save_after_corrupt_recovers(self, changes_dir, store: GitChangeStore):
        """损坏文件被下一次 save 原子覆盖恢复 (不抛错)。"""
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text("{broken", encoding="utf-8")
        store.save(GitChange(task_id="T-9", files=["x.py"]))
        records = store.load()
        assert len(records) == 1
        assert records[0].task_id == "T-9"
