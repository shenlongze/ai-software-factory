"""git/service.py — GitService: 只读查询聚合 + task↔git 关联 (Phase 6C, ADR-0018)。

设计依据:
- phase6c-status.md: get_status()/get_changes()/get_commits()/bind_task_change()
  (task ↔ git change 关联); 旧 Task 兼容 (无 git 关联的 Task 正常)
- 工程规则: Git 只读 + 审计 — get_status/get_changes/get_commits 只调
  GitClient 读接口 (subprocess git 读命令); bind_task_change 是唯一的写路径
  (GitChangeStore JSON 追加 + git.change.detected 审计事件), 不触碰仓库本身。

只读铁律: 查询聚合 = 纯函数组合, 无副作用; 审计事件经 EventLogger 发出
(依赖注入 logger, 与 CLI 命令层装配一致 — 收集器/服务不发全局事件)。

GitChangeStore: task↔git 关联的 JSON 持久化 (<root>/git/changes.json, 追加式
列表 + 原子写 tmp+os.replace, 同既有 JSON store 模式)。损坏文件读 → 空列表
(失败安全, 关联是审计增强非核心状态, 不因损坏崩溃)。

Task↔git 关联兼容: Task 模型不加字段 (禁止改 tasks/), 关联存在 git 侧 —
GitChange.task_id 引用 Task.id; 无关联的旧 Task 完全正常 (get_changes/get_commits
的 task_id 恒为 None, 绑定查询返回空)。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .client import GitClient
from .events import record_git_change_detected
from .models import GitChange, GitCommit, GitContext

class GitTaskNotFoundError(Exception):
    """bind_task_change 引用不存在的任务 (仅装配 task_store 时校验)。"""


class GitChangeStore:
    """task↔git 关联持久化 (JSON 列表文件, 追加式; 失败安全读)。

    path 接受目录 (→ <dir>/changes.json) 或文件路径; 缺省 = ~/.factory/git/
    changes.json (与 CLI DEFAULT_ROOT 一致, 不依赖 cwd)。
    """

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            self.path = Path.home() / ".factory" / "git" / "changes.json"
        else:
            p = Path(path)
            self.path = p / "changes.json" if p.suffix != ".json" else p

    # ------------------------------------------------------------------ 读写

    def load(self) -> list[GitChange]:
        """全部绑定记录 (按写入序); 文件缺失 → [], 损坏 → [] (失败安全)。"""
        if not self.path.is_file():
            return []
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        changes: list[GitChange] = []
        for item in data:
            if isinstance(item, dict):
                try:
                    changes.append(GitChange.model_validate(item))
                except (ValueError, TypeError):
                    continue  # 单条损坏跳过, 不拖垮整库 (失败安全)
        return changes

    def save(self, change: GitChange) -> None:
        """追加一条绑定并原子落盘 (tmp + os.replace)。"""
        records = [c.to_dict() for c in self.load()]
        records.append(change.to_dict())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------ 查询

    def list(self, *, task_id: str | None = None, project_id: str | None = None) -> list[GitChange]:
        """绑定记录 (按任务过滤可选); 无关联 → [] (旧 Task 兼容)。"""
        changes = self.load()
        if task_id is not None:
            changes = [c for c in changes if c.task_id == task_id]
        if project_id is not None:
            changes = [c for c in changes if c.project_id == project_id]
        return changes

    def task_by_path(self) -> dict[str, str]:
        """path → task_id 映射 (最近绑定优先; 无关联路径不出现)。"""
        mapping: dict[str, str] = {}
        for c in self.load():
            if c.task_id:
                for p in c.files:
                    mapping[p] = c.task_id
        return mapping

    def task_by_commit(self) -> dict[str, str]:
        """commit hash → task_id 映射 (最近绑定优先)。"""
        mapping: dict[str, str] = {}
        for c in self.load():
            if c.task_id:
                for h in c.commits:
                    mapping[h] = c.task_id
        return mapping


class GitService:
    """单仓库 Git 只读服务 (失败安全) + task↔git 关联 (审计)。"""

    def __init__(
        self,
        client: GitClient,
        *,
        project_id: str | None = None,
        task_store: Any | None = None,   # TaskStore (可选: bind 存在性校验)
        logger: Any | None = None,       # EventLogger (可选: git.* 审计事件)
        changes_store: GitChangeStore | None = None,
    ) -> None:
        self._client = client
        self._project_id = project_id
        self._task_store = task_store
        self._logger = logger
        self._store = changes_store or GitChangeStore()

    @property
    def client(self) -> GitClient:
        return self._client

    # ------------------------------------------------------------------ 只读查询

    def get_status(self) -> GitContext:
        """仓库状态: 上下文 (branch/current_commit) + 工作区变更列表。

        失败安全: 非 git 目录 → is_repo=False + error, changes 空 — 不抛异常。
        """
        ctx = self._client.status()
        ctx.project_id = self._project_id
        if ctx.is_repo:
            ctx.changes = self._client.diff()
        return ctx

    def get_changes(self, *, task_id: str | None = None) -> list[GitChange]:
        """工作区变更列表 (逐文件), 合并 task↔git 关联 (task_id 回填)。

        旧 Task 兼容: 无关联的路径 task_id=None (绑定查询 task_id 过滤在
        GitChangeStore.list, 此处为实时变更 + 关联投影)。
        """
        changes = self._client.diff()
        if not changes:
            return []
        bound = self._store.task_by_path()
        for c in changes:
            path = c.files[0] if c.files else ""
            c.task_id = bound.get(path)
            c.project_id = self._project_id
        if task_id is not None:
            changes = [c for c in changes if c.task_id == task_id]
        return changes

    def get_commits(self, *, limit: int = 20, task_id: str | None = None) -> list[GitCommit]:
        """最近提交 (倒序), 回填 branch + task↔git 关联 (hash → task_id)。"""
        commits = self._client.log(limit=limit)
        if not commits:
            return []
        branch = self._client.current_branch()
        bound = self._store.task_by_commit()
        for c in commits:
            c.branch = branch
            c.task_id = bound.get(c.hash)
        if task_id is not None:
            commits = [c for c in commits if c.task_id == task_id]
        return commits

    # ------------------------------------------------------------------ task↔git 关联 (唯一写路径 + 审计)

    def bind_task_change(
        self,
        task_id: str,
        *,
        files: list[str] | None = None,
        commits: list[str] | None = None,
        status: str = "detected",
    ) -> GitChange:
        """把任务与 git 变更关联: 持久化 GitChange + 发 git.change.detected。

        - task_store 装配时校验任务存在 (GitTaskNotFoundError);
          未装配 task_store 时跳过校验 (纯服务场景, 旧 Task 兼容)。
        - files 缺省 = 当前全部工作区变更路径 (任务接管所有未提交变更);
          insertions/deletions 从实时 diff 对账 (文件级求和)。
        - commits 记录关联的提交哈希 (审计溯源); 全部幂等 (同任务重复
          绑定追加记录, 查询取最近关联 — 审计语义)。
        """
        if self._task_store is not None and self._task_store.get(task_id) is None:
            raise GitTaskNotFoundError(f"task not found: {task_id}")
        live = {c.files[0]: c for c in self._client.diff() if c.files}
        if files is None:
            files = sorted(live)
        files = sorted(dict.fromkeys(f for f in files if f))
        insertions = sum(live[f].insertions for f in files if f in live)
        deletions = sum(live[f].deletions for f in files if f in live)
        change = GitChange(
            task_id=task_id,
            project_id=self._project_id,
            repository=self._client.repository,
            files=files,
            insertions=insertions,
            deletions=deletions,
            status=status or "detected",
            commits=list(dict.fromkeys(commits or [])),
        )
        self._store.save(change)
        if self._logger is not None:
            record_git_change_detected(
                self._logger,
                project_id=self._project_id,
                task_id=task_id,
                change=change,
            )
        return change

    def bound_changes(self, task_id: str | None = None) -> list[GitChange]:
        """已绑定的关联记录 (GitChangeStore 持久化, 非实时变更)。"""
        return self._store.list(task_id=task_id, project_id=self._project_id)
