"""git/models.py — Git 集成层领域模型 (Pydantic v2, Phase 6C, ADR-0018)。

设计依据:
- phase6c-status.md: GitContext (project_id/repository/branch/base_commit/current_commit)
  + GitChange (task_id/project_id/files/insertions/deletions/status)
  + GitCommit (hash/message/branch/task_id/created_at)
- 风格同 tasks/models.py / workspace/models.py: Pydantic v2 + to_dict()
  (model_dump(mode="json")) + 时间戳统一 UTC 带时区。

失败安全语义: GitContext.error 承载查询失败信息 (非 git 目录/命令缺失/空仓库),
所有字段可空 — 上层 (GitService/CLI/Dashboard) 永不因 git 查询失败而抛错。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

# 变更状态归一化集合 (git status porcelain XY 码 → 五类, 见 client._normalize_status)
CHANGE_STATUSES = frozenset({"untracked", "added", "modified", "deleted", "renamed"})

# GitChange.status 缺省 (bind_task_change 的绑定状态)
DETECTED_STATUS = "detected"


class GitContext(BaseModel):
    """一次仓库状态查询的只读上下文 (失败安全: is_repo=False + error 承载原因)。

    base_commit = 变更比较基准 (通常 = HEAD); current_commit 为当前 HEAD。
    空仓库 (init 后无提交): is_repo=True, current_commit=None — 无提交可指。
    changes = 工作区变更明细 (GitClient.diff 结果, 由 GitService.get_status 填充)。
    """

    project_id: str | None = None
    repository: str = ""
    branch: str | None = None
    base_commit: str | None = None
    current_commit: str | None = None
    is_repo: bool = False
    changes: list["GitChange"] = Field(default_factory=list)
    error: str | None = None  # 查询失败原因 (非 git 目录 / 命令缺失 / ...)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class GitChange(BaseModel):
    """一条工作区变更 (客户端逐文件粒度) 或一次 task↔git 关联 (多文件绑定)。

    客户端 diff/status 解析: files=[单路径] + insertions/deletions (numstat 合并);
    bind_task_change 绑定: files=[多路径] + task_id + status="detected" + commits
    (关联提交哈希) — 持久化于 GitChangeStore (<root>/git/changes.json)。
    """

    id: str = Field(default_factory=lambda: uuid4().hex)  # 绑定记录主键 (持久化)
    project_id: str | None = None
    task_id: str | None = None  # 无 git 关联 (旧 Task) → None, 兼容
    repository: str = ""
    files: list[str] = Field(default_factory=list)
    insertions: int = 0
    deletions: int = 0
    status: str = "modified"  # untracked/added/modified/deleted/renamed/detected
    commits: list[str] = Field(default_factory=list)  # 关联提交哈希 (bind 时回填)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("status")
    @classmethod
    def _status_clean(cls, v: str) -> str:
        v = (v or "modified").strip().lower()
        return v if v in CHANGE_STATUSES or v == DETECTED_STATUS else "modified"

    @field_validator("insertions", "deletions")
    @classmethod
    def _counts_non_negative(cls, v: int) -> int:
        return max(0, v)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class GitCommit(BaseModel):
    """一条提交记录 (git log 解析, 只读)。task_id 为绑定回填 (Task↔git 关联)。"""

    hash: str
    message: str = ""
    branch: str | None = None  # 查询时所在分支 (log 上下文)
    task_id: str | None = None  # 关联任务 (bind 回填, 无 → None 兼容旧 Task)
    author: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("hash")
    @classmethod
    def _hash_sane(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("commit hash must not be empty")
        return v

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
