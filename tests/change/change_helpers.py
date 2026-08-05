"""tests/change/change_helpers.py — Change Intelligence 测试数据构造 (纯函数)。

唯一 basename 规则 (backend-developer skill): helper 模块命名 change_helpers,
避免与 tests/cli/helpers.py、tests/dashboard/dashboard_helpers.py 等非包目录
共存时同名模块互相遮蔽。
"""

from __future__ import annotations

from git.models import GitChange, GitCommit

from change.models import (
    ChangeAnalysis,
    ChangeContext,
    ChangeValidationResult,
    ExecutionGitSnapshot,
    GitBranchContext,
)


def make_commit(
    hash_: str = "abc123",
    message: str = "MP-BUG-001: fix crash",
    branch: str | None = "main",
    task_id: str | None = None,
    **kw,
) -> GitCommit:
    return GitCommit(hash=hash_, message=message, branch=branch,
                     task_id=task_id, **kw)


def make_change(
    path: str = "app/auth.py",
    insertions: int = 5,
    deletions: int = 1,
    status: str = "modified",
    task_id: str | None = None,
    **kw,
) -> GitChange:
    return GitChange(files=[path], insertions=insertions, deletions=deletions,
                     status=status, task_id=task_id, **kw)


def make_analysis(
    task_id: str = "MP-BUG-001",
    files: list[str] | None = None,
    insertions: int = 3,
    deletions: int = 1,
    modules: list[str] | None = None,
    commits: list[str] | None = None,
) -> ChangeAnalysis:
    return ChangeAnalysis(
        task_id=task_id,
        files=files or [],
        insertions=insertions,
        deletions=deletions,
        affected_modules=modules or [],
        commits=commits or [],
    )


def make_change_context(
    task_id: str = "MP-BUG-001",
    task_title: str = "Fix login crash",
    is_repo: bool = True,
    commits: list[GitCommit] | None = None,
    files: list[str] | None = None,
    modules: list[str] | None = None,
    error: str | None = None,
) -> ChangeContext:
    commits = commits or []
    return ChangeContext(
        task_id=task_id,
        task_title=task_title,
        is_repo=is_repo,
        has_commits=bool(commits),  # 提供 commits = 仓库存在提交 (L4 证据判定)
        commits=commits,
        files=files or [],
        affected_modules=modules or [],
        error=error,
    )


def make_validation(
    task_id: str = "MP-BUG-001",
    status: str = "PASS",
    message: str = "2 个提交关联任务 MP-BUG-001",
    checks: list[dict] | None = None,
) -> ChangeValidationResult:
    return ChangeValidationResult(task_id=task_id, status=status,
                                  message=message, checks=checks or [])


def make_snapshot(
    execution_id: str = "EX-001",
    task_id: str = "MP-BUG-001",
    project_id: str = "markpad",
    before_commit: str | None = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    after_commit: str | None = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    changed_files: list[str] | None = None,
) -> ExecutionGitSnapshot:
    return ExecutionGitSnapshot(
        execution_id=execution_id,
        task_id=task_id,
        project_id=project_id,
        repository="/repo/markpad",
        before_commit=before_commit,
        after_commit=after_commit,
        changed_files=changed_files or [],
    )
