"""change/events.py — change.* / git.task.bound / git.commit.linked 审计事件辅助
(经 EventLogger, Phase 6D, ADR-0019)。

设计依据:
- phase6d-status.md: git.task.bound / git.commit.linked / change.analyzed /
  change.validation.completed 事件
- ADR-0002: 所有 CLI 行为必须产生 Event; 事件类型扩展 = 加 EventType 枚举成员
  (ADR-0001 决策 1, 不改表结构)。
- Git 只读铁律: 本模块只发审计事件, 不触碰任何业务状态/仓库写操作;
  source 缺省 "change" (服务层), CLI 命令层直接经 logger.record 用 source="cli"
  (同既有命令模式, ADR-0018)。

payload 契约 (Dashboard Change View 事件聚合依赖, 与 CLI --json 出口一致):
- git.task.bound: branch/task_id/status/project_id
- git.commit.linked: hash/message/task_id/branch
- change.analyzed: task_id/files/insertions/deletions/affected_modules/commits
- change.validation.completed: task_id/status/message/checks
"""

from __future__ import annotations

from typing import Any

from events.models import Event, EventType

from .models import ChangeAnalysis, ChangeContext, ChangeValidationResult, GitBranchContext


def record_git_task_bound(
    logger: Any,
    *,
    context: GitBranchContext,
    source: str = "change",
) -> Event:
    """Task↔git 分支上下文绑定判定 (linker.bind_branch / change analyze 装配)。"""
    return logger.record(
        EventType.GIT_TASK_BOUND,
        source=source,
        project_id=context.project_id,
        task_id=context.task_id,
        stage=context.status,
        action="bind git branch context",
        result="OK" if context.status == "bound" else ("ERROR" if context.status == "error" else "SKIP"),
        payload={
            "branch": context.branch,
            "task_id": context.task_id,
            "status": context.status,
            "project_id": context.project_id,
        },
    )


def record_git_commit_linked(
    logger: Any,
    *,
    commit: Any,
    task_id: str,
    branch: str | None = None,
    source: str = "change",
) -> Event:
    """commit → task_id 关联 (CommitLinker 解析命中; 未命中不发, 减少噪声)。"""
    return logger.record(
        EventType.GIT_COMMIT_LINKED,
        source=source,
        task_id=task_id,
        stage="linked",
        action="link commit to task",
        result="OK",
        payload={
            "hash": getattr(commit, "hash", ""),
            "message": getattr(commit, "message", ""),
            "task_id": task_id,
            "branch": branch,
        },
    )


def record_change_analyzed(
    logger: Any,
    *,
    analysis: ChangeAnalysis,
    source: str = "change",
) -> Event:
    """变更路径分析完成 (ChangeAnalyzer.analyze 装配)。"""
    return logger.record(
        EventType.CHANGE_ANALYZED,
        source=source,
        task_id=analysis.task_id,
        stage="analyzed",
        action="analyze task changes",
        result="OK",
        payload={
            "task_id": analysis.task_id,
            "files": analysis.files,
            "insertions": analysis.insertions,
            "deletions": analysis.deletions,
            "affected_modules": analysis.affected_modules,
            "commits": analysis.commits,
        },
    )


def record_change_validation_completed(
    logger: Any,
    *,
    result: ChangeValidationResult,
    source: str = "change",
) -> Event:
    """L4 Change Validation 判定完成 (result=PASS/FAIL/SKIP/ERROR)。"""
    return logger.record(
        EventType.CHANGE_VALIDATION_COMPLETED,
        source=source,
        task_id=result.task_id,
        stage="validated",
        action="validate change evidence",
        result=result.status,
        payload={
            "task_id": result.task_id,
            "status": result.status,
            "message": result.message,
            "checks": result.checks,
        },
    )
