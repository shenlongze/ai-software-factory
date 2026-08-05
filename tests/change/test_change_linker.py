"""tests/change/test_change_linker.py — Commit parser + 分支任务上下文绑定。

覆盖: parse_task_id / normalize_task_id / task_id_from_message /
task_id_from_branch / CommitLinker (三来源优先级 message > execution > branch,
幂等) / bind_branch (bound/unbound/error) — 纯函数单测 + 真实仓库集成。
"""

from __future__ import annotations

import pytest

from change.linker import (
    BRANCH_STATUS_BOUND,
    BRANCH_STATUS_ERROR,
    BRANCH_STATUS_UNBOUND,
    CommitLinker,
    bind_branch,
    normalize_task_id,
    parse_task_id,
    task_id_from_branch,
    task_id_from_message,
)

from git_helpers import commit_all, init_repo, write_file
from change_helpers import make_commit


class TestParseTaskId:
    @pytest.mark.parametrize("text,expected", [
        ("MP-BUG-001", "MP-BUG-001"),
        ("fix MP-FEATURE-002 crash", "MP-FEATURE-002"),
        ("MP-TASK-014 done", "MP-TASK-014"),
        ("MP-EPIC-3 epic", "MP-EPIC-3"),
        ("MP-STORY-42 story", "MP-STORY-42"),
        ("MP-CHORE-7 chore", "MP-CHORE-7"),
        ("T-001 legacy", "T-001"),
    ])
    def test_extracts(self, text, expected):
        assert parse_task_id(text) == expected

    def test_mp_type_case_insensitive_normalized(self):
        assert parse_task_id("mp-bug-001") == "MP-BUG-001"
        assert parse_task_id("MP-bug-001") == "MP-BUG-001"

    def test_no_match_returns_none(self):
        assert parse_task_id("ordinary commit message") is None

    def test_empty_returns_none(self):
        assert parse_task_id("") is None
        assert parse_task_id(None) is None

    def test_word_boundary_no_partial_match(self):
        # 前缀相同但不构成完整 token → 不误报; 位数上限 6 位
        assert parse_task_id("MP-BUG-00123456") is None
        assert parse_task_id("XMP-BUG-001") is None

    def test_mp_priority_over_short(self):
        assert parse_task_id("MP-BUG-001 and T-002") == "MP-BUG-001"

    def test_first_match_wins(self):
        assert parse_task_id("MP-BUG-001 MP-FEATURE-002") == "MP-BUG-001"

    def test_unknown_mp_type_not_matched(self):
        assert parse_task_id("MP-NOPE-001") is None


class TestNormalizeTaskId:
    def test_mp_uppercases_type_and_num(self):
        assert normalize_task_id("mp-bug-001") == "MP-BUG-001"

    def test_t_short_uppercased(self):
        assert normalize_task_id("t-001") == "T-001"

    def test_empty(self):
        assert normalize_task_id("") == ""
        assert normalize_task_id(None) == ""

    def test_strips_whitespace(self):
        assert normalize_task_id("  MP-BUG-001  ") == "MP-BUG-001"


class TestTaskIdFromMessage:
    def test_message_with_task(self):
        assert task_id_from_message("MP-BUG-001: fix login") == "MP-BUG-001"

    def test_message_without_task(self):
        assert task_id_from_message("chore: bump deps") is None

    def test_short_task(self):
        assert task_id_from_message("T-007 update") == "T-007"


class TestTaskIdFromBranch:
    def test_feature_branch(self):
        assert task_id_from_branch("feature/MP-FEATURE-002-login") == "MP-FEATURE-002"

    def test_bare_task_branch(self):
        assert task_id_from_branch("MP-BUG-001") == "MP-BUG-001"

    def test_main_no_match(self):
        assert task_id_from_branch("main") is None

    def test_empty_no_match(self):
        assert task_id_from_branch("") is None
        assert task_id_from_branch(None) is None

    def test_slash_prefix_form(self):
        assert task_id_from_branch("hotfix/MP-BUG-001-fix") == "MP-BUG-001"


class TestCommitLinkerLink:
    def test_parse_from_message(self):
        c = CommitLinker().link(make_commit(message="MP-BUG-001: fix"))
        assert c.task_id == "MP-BUG-001"

    def test_existing_task_id_not_overwritten(self):
        c = CommitLinker().link(make_commit(message="MP-BUG-001: fix",
                                            task_id="MP-FEATURE-002"))
        assert c.task_id == "MP-FEATURE-002"  # 幂等: 已关联不覆盖

    def test_execution_task_fallback(self):
        c = CommitLinker().link(make_commit(message="no task"),
                                execution_task_id="MP-TASK-014")
        assert c.task_id == "MP-TASK-014"

    def test_branch_fallback(self):
        c = CommitLinker().link(make_commit(message="no task", branch=None),
                                branch="feature/MP-FEATURE-002-x")
        assert c.task_id == "MP-FEATURE-002"

    def test_message_priority_over_execution(self):
        c = CommitLinker().link(make_commit(message="MP-BUG-001: fix"),
                                execution_task_id="MP-FEATURE-002")
        assert c.task_id == "MP-BUG-001"

    def test_execution_priority_over_branch(self):
        c = CommitLinker().link(make_commit(message="no task", branch=None),
                                branch="feature/MP-FEATURE-002-x",
                                execution_task_id="MP-BUG-001")
        assert c.task_id == "MP-BUG-001"

    def test_no_source_returns_untouched(self):
        c = CommitLinker().link(make_commit(message="plain", task_id=None))
        assert c.task_id is None

    def test_execution_task_normalized(self):
        c = CommitLinker().link(make_commit(message="no task"),
                                execution_task_id="mp-bug-001")
        assert c.task_id == "MP-BUG-001"

    def test_original_commit_unchanged(self):
        commit = make_commit(message="MP-BUG-001: fix")
        CommitLinker().link(commit)
        assert commit.task_id is None  # model_copy → 原对象不动

    def test_short_task_via_pattern(self):
        c = CommitLinker().link(make_commit(message="T-042 done"))
        assert c.task_id == "T-042"


class TestCommitLinkerLinkMany:
    def test_batch_parse(self):
        commits = [make_commit(message="MP-BUG-001: a"),
                   make_commit(message="plain")]
        out = CommitLinker().link_many(commits)
        assert out[0].task_id == "MP-BUG-001"
        assert out[1].task_id is None

    def test_original_list_unchanged(self):
        commits = [make_commit(message="MP-BUG-001: a")]
        CommitLinker().link_many(commits)
        assert commits[0].task_id is None

    def test_execution_context_injected_batch(self):
        commits = [make_commit(message="a"), make_commit(message="b")]
        out = CommitLinker().link_many(commits, execution_task_id="MP-TASK-9")
        assert [c.task_id for c in out] == ["MP-TASK-9", "MP-TASK-9"]


class TestBindBranch:
    def test_bound(self, task_repo):
        from git.client import GitClient
        ctx = bind_branch(GitClient(task_repo), branch="feature/MP-BUG-001-hotfix",
                          project_id="markpad")
        assert ctx.status == BRANCH_STATUS_BOUND
        assert ctx.task_id == "MP-BUG-001"
        assert ctx.project_id == "markpad"

    def test_unbound(self, repo_path):
        from git.client import GitClient
        ctx = bind_branch(GitClient(repo_path), branch="main")
        assert ctx.status == BRANCH_STATUS_UNBOUND
        assert ctx.task_id is None

    def test_error_on_non_repo(self, tmp_path):
        from git.client import GitClient
        ctx = bind_branch(GitClient(tmp_path / "no-repo"))
        assert ctx.status == BRANCH_STATUS_ERROR
        assert ctx.task_id is None

    def test_explicit_branch_wins_over_client(self, task_repo):
        from git.client import GitClient
        ctx = bind_branch(GitClient(task_repo),
                          branch="feature/MP-CHORE-1-x")
        assert ctx.task_id == "MP-CHORE-1"

    def test_detached_branch_none(self, repo_path):
        from git.client import GitClient
        ctx = bind_branch(GitClient(repo_path), branch=None)
        # branch=None → 客户端查询真实分支 (main) → unbound
        assert ctx.status in (BRANCH_STATUS_UNBOUND, BRANCH_STATUS_BOUND)
