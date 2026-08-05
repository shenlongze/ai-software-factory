"""tests/change/test_change_models.py — Change Intelligence 领域模型 (Pydantic v2)。

覆盖: GitBranchContext / ChangeAnalysis / ChangeValidationResult / ChangeContext /
ExecutionGitSnapshot — 默认值、校验器、to_dict JSON 序列化 (模式同 tests/git/
test_git_models.py)。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from change.models import (
    CHANGE_STATUSES,
    ChangeAnalysis,
    ChangeContext,
    ChangeValidationResult,
    ExecutionGitSnapshot,
    GitBranchContext,
)

from change_helpers import (
    make_analysis,
    make_change_context,
    make_commit,
    make_snapshot,
    make_validation,
)


class TestGitBranchContext:
    def test_default_unbound(self):
        ctx = GitBranchContext()
        assert ctx.status == "unbound"
        assert ctx.branch is None
        assert ctx.task_id is None

    def test_bound_fields(self):
        ctx = GitBranchContext(branch="feature/MP-FEATURE-002-login",
                               task_id="MP-FEATURE-002", project_id="markpad",
                               status="bound")
        assert ctx.branch == "feature/MP-FEATURE-002-login"
        assert ctx.task_id == "MP-FEATURE-002"
        assert ctx.project_id == "markpad"
        assert ctx.status == "bound"

    def test_status_validator_invalid_falls_back_unbound(self):
        assert GitBranchContext(status="weird").status == "unbound"

    def test_status_validator_case_insensitive(self):
        assert GitBranchContext(status="BOUND").status == "bound"

    def test_status_none_rejected_by_pydantic(self):
        # status 为强类型 str (Pydantic v2) — None 直接校验失败
        with pytest.raises(ValidationError):
            GitBranchContext(status=None)

    def test_to_dict_json_serializable(self):
        d = GitBranchContext(branch="main", status="unbound").to_dict()
        assert d["branch"] == "main"
        assert d["status"] == "unbound"
        assert isinstance(d["created_at"], str)  # mode="json" → ISO 字符串


class TestChangeAnalysis:
    def test_defaults_empty(self):
        a = ChangeAnalysis(task_id="MP-BUG-001")
        assert a.files == []
        assert a.insertions == 0
        assert a.deletions == 0
        assert a.affected_modules == []
        assert a.commits == []

    def test_counts_non_negative_validator(self):
        a = ChangeAnalysis(task_id="T-001", insertions=-5, deletions=-2)
        assert a.insertions == 0
        assert a.deletions == 0

    def test_to_dict(self):
        d = make_analysis(files=["a.py"], modules=["a"], commits=["h1"]).to_dict()
        assert d["task_id"] == "MP-BUG-001"
        assert d["files"] == ["a.py"]
        assert d["commits"] == ["h1"]

    def test_created_at_utc_aware(self):
        a = ChangeAnalysis(task_id="T-001")
        assert a.created_at.tzinfo is not None


class TestChangeValidationResult:
    def test_default_skip(self):
        r = ChangeValidationResult(task_id="MP-BUG-001")
        assert r.status == "SKIP"
        assert r.id == "L4.change"

    def test_status_coerce_lowercase(self):
        assert ChangeValidationResult(task_id="T-001", status="pass").status == "PASS"

    def test_status_invalid_falls_back_skip(self):
        assert ChangeValidationResult(task_id="T-001", status="nope").status == "SKIP"

    def test_passed_property(self):
        assert make_validation(status="PASS").passed
        assert not make_validation(status="FAIL").passed
        assert not make_validation(status="SKIP").passed

    def test_change_statuses_enum(self):
        assert CHANGE_STATUSES == {"PASS", "FAIL", "SKIP", "ERROR"}

    def test_to_dict_contains_checks(self):
        r = make_validation(checks=[{"id": "L4.commit_link", "status": "PASS"}])
        d = r.to_dict()
        assert d["status"] == "PASS"
        assert d["checks"][0]["id"] == "L4.commit_link"


class TestChangeContext:
    def test_default_not_repo(self):
        ctx = ChangeContext(task_id="MP-BUG-001")
        assert ctx.is_repo is False
        assert ctx.commits == []
        assert ctx.files == []

    def test_with_evidence(self):
        ctx = make_change_context(commits=[make_commit(task_id="MP-BUG-001")],
                                  files=["app/auth.py"], modules=["app.auth"])
        assert len(ctx.commits) == 1
        assert ctx.files == ["app/auth.py"]
        assert ctx.affected_modules == ["app.auth"]

    def test_error_fail_safe(self):
        ctx = make_change_context(is_repo=False, error="not a git repository")
        assert ctx.error == "not a git repository"

    def test_task_title_passthrough(self):
        ctx = make_change_context(task_title="登录页修复")
        assert ctx.task_title == "登录页修复"


class TestExecutionGitSnapshot:
    def test_defaults(self):
        s = ExecutionGitSnapshot(execution_id="EX-001", task_id="T-001")
        assert s.before_commit is None
        assert s.after_commit is None
        assert s.changed_files == []
        assert s.id  # uuid 自动生成

    def test_full_fields(self):
        s = make_snapshot(changed_files=["a.py", "b.py"])
        assert s.execution_id == "EX-001"
        assert s.task_id == "MP-BUG-001"
        assert s.project_id == "markpad"
        assert s.before_commit.startswith("a" * 12)
        assert s.changed_files == ["a.py", "b.py"]

    def test_to_dict(self):
        d = make_snapshot(execution_id="EX-9").to_dict()
        assert d["execution_id"] == "EX-9"
        assert d["task_id"] == "MP-BUG-001"
        assert isinstance(d["created_at"], str)

    def test_model_validate_roundtrip(self):
        s = make_snapshot()
        s2 = ExecutionGitSnapshot.model_validate(s.to_dict())
        assert s2.execution_id == s.execution_id
        assert s2.changed_files == s.changed_files

    def test_uuid_unique(self):
        assert make_snapshot().id != make_snapshot().id
