"""change/service.py — ChangeService: Commit 解析 / 路径分析 / L4 验证 / 分支绑定 /
Execution Git Snapshot 关联存储 (Phase 6D, ADR-0019)。

设计依据:
- phase6d-status.md: ChangeService (parse_commits/analyze/bind/validate) +
  Execution Git Snapshot (before_commit/after_commit/changed_files, 兼容)
- Git 只读铁律: 查询聚合只调 GitClient/GitService 读接口; 唯一的写路径是
  ChangeStore (JSON 关联存储, <root>/change/snapshots.json) — 不触碰仓库本身。
- 事件边界 (同 GitService 模式): 服务层经注入的 EventLogger 发 change.* /
  git.task.bound / git.commit.linked 审计事件; 收集器/CLI 读路径不发事件。

ChangeStore: ExecutionGitSnapshot 关联持久化 (追加式列表 + 原子写 tmp+os.replace,
同 GitChangeStore/既有 JSON store 模式)。损坏文件读 → [] (失败安全: 快照是
审计增强非核心状态, 不因损坏崩溃)。

Execution Git Snapshot 兼容 (ADR-0019 决策 3): 快照存于 change 侧 (ChangeStore),
ExecutionRequest/Result 模型零改动 (禁止改 runtime/execution) — 旧执行记录无
快照字段完全正常, snapshot_execution 只在执行完成 (CLI 装配钩子) 时关联写入。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from git.client import GitClient
from git.models import GitChange, GitCommit
from git.service import GitChangeStore, GitService
from tasks.store import TaskStore

from .analyzer import ChangeAnalyzer, l4_checks, l4_verdict
from .events import (
    record_change_analyzed,
    record_change_validation_completed,
    record_git_commit_linked,
    record_git_task_bound,
)
from .linker import CommitLinker, bind_branch
from .models import (
    ChangeAnalysis,
    ChangeContext,
    ChangeValidationResult,
    ExecutionGitSnapshot,
    GitBranchContext,
)


class ChangeStore:
    """ExecutionGitSnapshot 关联存储 (JSON 列表文件, 追加式; 失败安全读)。

    path 接受目录 (→ <dir>/snapshots.json) 或文件路径; 缺省 =
    ~/.factory/change/snapshots.json (与 CLI DEFAULT_ROOT 一致, 不依赖 cwd)。
    """

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            self.path = Path.home() / ".factory" / "change" / "snapshots.json"
        else:
            p = Path(path)
            self.path = p / "snapshots.json" if p.suffix != ".json" else p

    # ------------------------------------------------------------------ 读写

    def load(self) -> list[ExecutionGitSnapshot]:
        """全部快照 (按写入序); 文件缺失 → [], 损坏 → [] (失败安全)。"""
        if not self.path.is_file():
            return []
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        snapshots: list[ExecutionGitSnapshot] = []
        for item in data:
            if isinstance(item, dict):
                try:
                    snapshots.append(ExecutionGitSnapshot.model_validate(item))
                except (ValueError, TypeError):
                    continue  # 单条损坏跳过, 不拖垮整库 (失败安全)
        return snapshots

    def save(self, snapshot: ExecutionGitSnapshot) -> None:
        """追加一条快照并原子落盘 (tmp + os.replace)。"""
        records = [s.to_dict() for s in self.load()]
        records.append(snapshot.to_dict())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------ 查询

    def list(
        self,
        *,
        task_id: str | None = None,
        execution_id: str | None = None,
        project_id: str | None = None,
    ) -> list[ExecutionGitSnapshot]:
        """快照列表 (过滤可选); 无关联 → [] (旧执行记录兼容)。"""
        snapshots = self.load()
        if task_id is not None:
            snapshots = [s for s in snapshots if s.task_id == task_id]
        if execution_id is not None:
            snapshots = [s for s in snapshots if s.execution_id == execution_id]
        if project_id is not None:
            snapshots = [s for s in snapshots if s.project_id == project_id]
        return snapshots


def _merge_changes(*groups: list[GitChange]) -> list[GitChange]:
    """多来源 GitChange 合并: 按路径去重 (首见优先), 防行数重复求和。

    task↔git 绑定变更与实时工作区变更可能重叠 (绑定源自在同一工作区), 合并后
    每个路径只保留首个变更 — 行数对账不翻倍。
    """
    seen: set[str] = set()
    merged: list[GitChange] = []
    for group in groups:
        for change in group:
            path = change.files[0] if change.files else ""
            if path and path in seen:
                continue
            if path:
                seen.add(path)
            merged.append(change)
    return merged


class ChangeService:
    """Change Intelligence 服务: Commit 解析 / 分析 / L4 验证 / 分支绑定 / 快照关联。

    装配: client (GitClient) 或 git_service (GitService, 含 client + task 关联
    store) 二选一; task_store 用于 L4 任务标题装载 (缺省 None → 标题为空,
    path_match 规则 SKIP — 服务层纯 git 场景兼容); logger 注入发审计事件。
    """

    def __init__(
        self,
        *,
        client: GitClient | None = None,
        git_service: GitService | None = None,
        task_store: TaskStore | None = None,
        logger: Any | None = None,
        project_id: str | None = None,
        change_store: ChangeStore | None = None,
        git_changes_store: GitChangeStore | None = None,
    ) -> None:
        if git_service is not None:
            self._git = git_service
        else:
            self._git = GitService(
                client or GitClient("."),
                project_id=project_id,
                changes_store=git_changes_store or GitChangeStore(),
            )
        self._client: GitClient = self._git.client
        self._tasks = task_store
        self._logger = logger
        self._project_id = project_id or (self._git.client.repository or None)
        self._store = change_store or ChangeStore()
        self._linker = CommitLinker()

    @property
    def client(self) -> GitClient:
        return self._client

    @property
    def store(self) -> ChangeStore:
        return self._store

    # ------------------------------------------------------------------ Commit 解析 (三来源: message > execution > branch)

    def parse_commits(
        self,
        *,
        limit: int = 20,
        branch: str | None = None,
        execution_task_id: str | None = None,
    ) -> list[GitCommit]:
        """最近提交 + 任务关联解析 (CommitLinker), 命中发 git.commit.linked。

        失败安全: 非 git 目录/空仓库 → [] (client.log 失败安全); 事件只在
        解析命中 task_id 时发出 (未命中是常态 — 提交无任务 ID 不刷审计噪声)。
        """
        commits = self._client.log(limit=limit)
        if not commits:
            return []
        if branch is None:
            branch = self._client.current_branch()
        linked: list[GitCommit] = []
        for commit in self._linker.link_many(commits, branch=branch, execution_task_id=execution_task_id):
            if commit.task_id and self._logger is not None:
                record_git_commit_linked(
                    self._logger,
                    commit=commit,
                    task_id=commit.task_id,
                    branch=branch,
                )
            linked.append(commit)
        return linked

    # ------------------------------------------------------------------ 路径分析 (禁 LLM)

    def analyze(
        self,
        task_id: str,
        *,
        limit: int = 20,
        branch: str | None = None,
        execution_task_id: str | None = None,
    ) -> ChangeAnalysis:
        """任务变更分析: 解析提交 (回填 task_id) + 工作区变更路径/行数对账。

        files = task↔git 绑定变更 (get_changes 回填) ∪ 实时工作区变更
        (client.diff, 含未提交/未跟踪文件 — 分析必须反映"当前状态", 提交哈希
        另行记入 analysis.commits 作审计溯源)。
        事件: git.commit.linked (解析命中) + change.analyzed。
        失败安全: 非 git 目录 → 空分析 (不抛)。
        """
        commits = self.parse_commits(limit=limit, branch=branch, execution_task_id=execution_task_id)
        linked_hashes = [c.hash for c in commits if c.task_id == task_id]
        task_changes = self._git.get_changes(task_id=task_id)
        try:
            working_changes = self._client.diff()
        except Exception:  # 防御兜底: diff 失败不影响提交级分析
            working_changes = []
        analysis = ChangeAnalyzer().analyze(
            task_id,
            changes=_merge_changes(task_changes, working_changes),
            files=[],
            commits=linked_hashes,
        )
        if self._logger is not None:
            record_change_analyzed(self._logger, analysis=analysis)
        return analysis

    # ------------------------------------------------------------------ L4 Change Validation

    def change_context(self, task_id: str) -> ChangeContext:
        """L4 规则输入快照: 任务标题 + 仓库变更证据 (失败安全, 永不抛)。

        - 非 git 目录/查询失败 → is_repo=False + error (L4 全部 SKIP)。
        - commits = 已解析 task_id 的提交 (CommitLinker, message/branch 来源);
          files = 工作区变更路径 (全量, L4 path_match 对照)。
        """
        task_title = ""
        if self._tasks is not None:
            task = self._tasks.get(task_id)
            task_title = task.title if task is not None else ""
        status = self._client.status()
        if not status.is_repo:
            return ChangeContext(
                task_id=task_id, task_title=task_title,
                repository=status.repository, is_repo=False, error=status.error,
            )
        commits = self.parse_commits(limit=20)
        linked = [c for c in commits if c.task_id == task_id]
        changes = self._client.diff()
        files = sorted({f for c in changes for f in c.files})
        analysis = ChangeAnalyzer().analyze(task_id, changes=changes, files=files,
                                            commits=[c.hash for c in linked])
        return ChangeContext(
            task_id=task_id,
            task_title=task_title,
            repository=status.repository,
            is_repo=True,
            has_commits=bool(commits),  # 仓库存在提交 = 变更证据 (空仓库 → False → SKIP)
            commits=linked,
            files=analysis.files,
            insertions=analysis.insertions,
            deletions=analysis.deletions,
            affected_modules=analysis.affected_modules,
        )

    def validate(self, task_id: str) -> ChangeValidationResult:
        """L4 Change Validation: Task 描述 vs Git Change → PASS/FAIL/SKIP。

        无 git 关联 (非仓库/无证据) → SKIP (旧 Task 兼容, 不误报)。
        事件: change.validation.completed (result=判定)。失败安全: 内部异常 →
        ERROR 结果 (不抛, 同 ValidationEngine 规则兜底语义)。
        """
        try:
            ctx = self.change_context(task_id)
            checks = l4_checks(ctx)
            verdict = l4_verdict(checks)
            detail = "；".join(c.get("message", "") for c in checks if c.get("status") != "SKIP") or "无 git 关联"
            result = ChangeValidationResult(
                task_id=task_id, status=verdict, message=detail, checks=checks,
            )
        except Exception as exc:  # 失败安全: 内部错误 → ERROR 结果
            result = ChangeValidationResult(
                task_id=task_id, status="ERROR",
                message=f"{type(exc).__name__}: {exc}",
                checks=[{"id": "L4.change", "status": "ERROR", "message": str(exc)}],
            )
        if self._logger is not None:
            record_change_validation_completed(self._logger, result=result)
        return result

    # ------------------------------------------------------------------ 分支绑定

    def bind_branch(self, *, branch: str | None = None) -> GitBranchContext:
        """仓库分支的任务上下文 (branch → task_id 解析), 发 git.task.bound。

        失败安全: 非 git 目录/查询失败 → status=error (branch=None), 不抛。
        """
        context = bind_branch(self._client, branch=branch, project_id=self._project_id)
        if self._logger is not None:
            record_git_task_bound(self._logger, context=context)
        return context

    # ------------------------------------------------------------------ Execution Git Snapshot 关联

    def snapshot_execution(
        self,
        *,
        execution_id: str,
        task_id: str,
        before_commit: str | None = None,
        after_commit: str | None = None,
        changed_files: list[str] | None = None,
        repository: str = "",
    ) -> ExecutionGitSnapshot:
        """执行完成时的 Git 快照关联 (ChangeStore 持久化; runtime/ 零改动)。

        after_commit 缺省 = 当前 HEAD (执行后状态); changed_files 缺省 = 工作区
        变更路径 (任务接管变更的审计快照)。失败安全: 非 git 目录 → 快照照常
        记录 (commit=None, files=[]) — 关联记录"执行发生在无仓库环境"的事实。
        """
        if after_commit is None:
            try:
                after_commit = self._client.current_commit()
            except Exception:
                after_commit = None
        if changed_files is None:
            try:
                changed_files = sorted({f for c in self._client.diff() for f in c.files})
            except Exception:
                changed_files = []
        snapshot = ExecutionGitSnapshot(
            execution_id=execution_id,
            task_id=task_id,
            project_id=self._project_id,
            repository=repository or self._client.repository,
            before_commit=before_commit,
            after_commit=after_commit,
            changed_files=sorted(dict.fromkeys(changed_files)),
        )
        self._store.save(snapshot)
        return snapshot

    def snapshots(self, *, task_id: str | None = None) -> list[ExecutionGitSnapshot]:
        """已关联的执行快照 (ChangeStore 查询; 旧执行记录无快照 → 空)。"""
        return self._store.list(task_id=task_id, project_id=self._project_id)
