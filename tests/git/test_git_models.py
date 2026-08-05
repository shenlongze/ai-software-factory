"""tests/git/test_git_models.py — Git 模型 (GitContext/GitChange/GitCommit)。

覆盖: 字段默认值 / 校验 (状态归一化/计数非负/hash 必填) / to_dict JSON /
空仓库状态 / 旧 Task 兼容 (task_id=None)。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from git.models import DETECTED_STATUS, GitChange, GitCommit, GitContext


class TestGitContext:
    def test_defaults_fail_safe(self):
        ctx = GitContext()
        assert ctx.project_id is None
        assert ctx.repository == ""
        assert ctx.branch is None
        assert ctx.base_commit is None
        assert ctx.current_commit is None
        assert ctx.is_repo is False
        assert ctx.error is None
        assert ctx.changes == []

    def test_full_fields(self):
        ctx = GitContext(
            project_id="markpad", repository="/repo", branch="main",
            base_commit="abc", current_commit="abc", is_repo=True,
        )
        assert ctx.branch == "main"
        assert ctx.is_repo is True

    def test_empty_repo_state(self):
        """空仓库: is_repo=True 但无提交可指 (current_commit=None)。"""
        ctx = GitContext(repository="/repo", is_repo=True)
        assert ctx.is_repo is True
        assert ctx.current_commit is None
        assert ctx.error is None

    def test_error_carried(self):
        ctx = GitContext(repository="/nope", is_repo=False, error="not a git repository")
        assert ctx.error == "not a git repository"

    def test_to_dict_json(self):
        ctx = GitContext(repository="/repo", branch="main", is_repo=True)
        d = ctx.to_dict()
        assert d["repository"] == "/repo"
        assert d["branch"] == "main"
        assert d["is_repo"] is True
        assert d["changes"] == []


class TestGitChange:
    def test_defaults(self):
        c = GitChange(files=["a.py"])
        assert c.status == "modified"
        assert c.task_id is None
        assert c.project_id is None
        assert c.insertions == 0
        assert c.deletions == 0
        assert c.files == ["a.py"]
        assert c.commits == []
        assert c.id  # uuid 自动生成

    def test_status_normalized_lowercase(self):
        assert GitChange(files=["a"], status="MODIFIED").status == "modified"
        assert GitChange(files=["a"], status="Untracked").status == "untracked"
        assert GitChange(files=["a"], status="ADDED").status == "added"
        assert GitChange(files=["a"], status="DELETED").status == "deleted"
        assert GitChange(files=["a"], status="renamed").status == "renamed"
        assert GitChange(files=["a"], status="detected").status == DETECTED_STATUS

    def test_unknown_status_falls_back_modified(self):
        assert GitChange(files=["a"], status="weird").status == "modified"
        assert GitChange(files=["a"], status="").status == "modified"

    def test_counts_non_negative(self):
        assert GitChange(files=["a"], insertions=-3, deletions=-1).insertions == 0
        assert GitChange(files=["a"], insertions=-3, deletions=-1).deletions == 0

    def test_task_binding_fields(self):
        c = GitChange(
            task_id="T-001", project_id="markpad", repository="/repo",
            files=["a.py", "b.py"], insertions=5, deletions=2,
            commits=["abc123"],
        )
        assert c.task_id == "T-001"
        assert c.commits == ["abc123"]
        assert c.repository == "/repo"

    def test_old_task_compat_no_task(self):
        """旧 Task 兼容: 无 git 关联的变更 task_id=None。"""
        c = GitChange(files=["a.py"])
        assert c.task_id is None

    def test_to_dict_json(self):
        c = GitChange(task_id="T-001", files=["a.py"], insertions=1)
        d = c.to_dict()
        assert d["task_id"] == "T-001"
        assert d["files"] == ["a.py"]
        assert d["insertions"] == 1
        assert isinstance(d["created_at"], str)


class TestGitCommit:
    def test_required_fields(self):
        c = GitCommit(hash="abc123", message="feat: x")
        assert c.hash == "abc123"
        assert c.message == "feat: x"
        assert c.task_id is None
        assert c.branch is None
        assert c.author == ""

    def test_empty_hash_rejected(self):
        with pytest.raises(ValidationError):
            GitCommit(hash="")
        with pytest.raises(ValidationError):
            GitCommit(hash="   ")

    def test_binding_backfill(self):
        c = GitCommit(hash="abc", branch="main", task_id="T-001")
        assert c.branch == "main"
        assert c.task_id == "T-001"

    def test_created_at_default_utc(self):
        c = GitCommit(hash="abc")
        assert c.created_at.tzinfo is not None
        assert isinstance(c.created_at, datetime)

    def test_to_dict_json(self):
        c = GitCommit(hash="abc", message="m", author="t")
        d = c.to_dict()
        assert d["hash"] == "abc"
        assert d["author"] == "t"
        assert d["task_id"] is None
        assert isinstance(d["created_at"], str)

    def test_created_at_roundtrip(self):
        """带 created_at 的 round-trip: 逐字段比较 + 原时间戳 (skill 陷阱)。"""
        ts = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)
        c = GitCommit(hash="abc", message="m", created_at=ts)
        d = c.to_dict()
        back = GitCommit.model_validate(d)
        assert back.hash == c.hash
        assert back.message == c.message
        assert back.created_at == c.created_at
