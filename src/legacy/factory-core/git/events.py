"""git/events.py — git.* 审计事件辅助 (经 EventLogger, Phase 6C, ADR-0018)。

设计依据:
- phase6c-status.md: git.status.viewed / git.change.detected / git.commit.viewed
- ADR-0002: 所有 CLI 行为必须产生 Event (读命令也发审计事件);
  事件类型扩展 = 加 EventType 枚举成员即可 (ADR-0001 决策 1, 不改表结构)。

边界: 本模块只发 git.* 事件, 不触碰任何业务状态 (Git 只读 + 审计);
source 缺省 "git" (服务层), CLI 命令层直接经 logger.record 用 source="cli"
(同既有命令模式), payload 含仓库/计数等审计信息。
"""

from __future__ import annotations

from typing import Any

from events.models import Event, EventType

from .models import GitChange, GitCommit, GitContext


def record_git_status_viewed(
    logger: Any,
    *,
    status: GitContext,
    project_id: str | None = None,
    source: str = "git",
) -> Event:
    """仓库状态被查看 (只读审计)。失败安全: 非 git 仓库 result=ERROR + error 摘要。"""
    return logger.record(
        EventType.GIT_STATUS_VIEWED,
        source=source,
        project_id=project_id,
        stage="viewed",
        action="view git status",
        result="OK" if status.is_repo else "ERROR",
        payload={
            "repository": status.repository,
            "branch": status.branch,
            "current_commit": status.current_commit,
            "changes": len(status.changes),
            "is_repo": status.is_repo,
            "error": status.error,
        },
    )


def record_git_change_detected(
    logger: Any,
    *,
    change: GitChange,
    project_id: str | None = None,
    task_id: str | None = None,
    source: str = "git",
) -> Event:
    """工作区变更被检测/关联 (bind_task_change 审计; CLI diff 复用)。"""
    return logger.record(
        EventType.GIT_CHANGE_DETECTED,
        source=source,
        project_id=project_id,
        task_id=task_id,
        stage="detected",
        action="detect git change",
        result="OK",
        payload={
            "change_id": change.id,
            "repository": change.repository,
            "files": change.files,
            "commits": change.commits,
            "insertions": change.insertions,
            "deletions": change.deletions,
            "status": change.status,
        },
    )


def record_git_commit_viewed(
    logger: Any,
    *,
    commits: list[GitCommit],
    project_id: str | None = None,
    repository: str = "",
    limit: int = 20,
    source: str = "git",
) -> Event:
    """提交历史被查看 (只读审计)。"""
    return logger.record(
        EventType.GIT_COMMIT_VIEWED,
        source=source,
        project_id=project_id,
        stage="viewed",
        action="view git commits",
        result="OK",
        payload={
            "repository": repository,
            "count": len(commits),
            "limit": limit,
            "hashes": [c.hash for c in commits[:20]],
        },
    )
