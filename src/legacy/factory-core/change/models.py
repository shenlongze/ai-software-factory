"""change/models.py — Change Intelligence Layer 领域模型 (Pydantic v2, Phase 6D, ADR-0019)。

设计依据:
- phase6d-status.md: GitBranchContext (branch/task_id/project_id/status/created_at)
  + ChangeAnalysis (task_id/files/insertions/deletions/affected_modules)
  + ChangeValidationResult (task_id/status/message)
- 风格同 git/models.py / tasks/models.py: Pydantic v2 + to_dict()
  (model_dump(mode="json")) + 时间戳统一 UTC 带时区。

语义:
- GitBranchContext: 仓库当前分支的"任务上下文"投影 — 从分支名解析 task_id
  (linker.bind_branch), status 为任务在仓库侧的状态 (bound/unbound/error)。
- ChangeContext: L4 Change Validation 的只读输入快照 (任务在仓库中的变更证据),
  由 ChangeService 装配 (commits 已解析 task_id, files 为关联文件路径)。
- ExecutionGitSnapshot: Execution ↔ Git 快照关联 (before_commit/after_commit/
  changed_files) — 采用"关联"而非扩展 ExecutionRequest/Result 模型:
  旧执行记录 (无快照字段) 天然兼容, runtime/ 模型零改动 (ADR-0019 决策 3)。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

from git.models import GitCommit

# 分支任务上下文状态 (linker.bind_branch 判定)
_BRANCH_STATUSES = frozenset({"bound", "unbound", "error"})

# ChangeValidationResult.status 枚举值 (L4 判定; 与 validation.ValidationStatus 对齐)
CHANGE_STATUSES = frozenset({"PASS", "FAIL", "SKIP", "ERROR"})


class GitBranchContext(BaseModel):
    """仓库分支的"任务上下文"投影 (分支名 → task_id 解析结果)。

    - branch: 分支名 (如 feature/MP-FEATURE-002-login; 非 git 仓库 → None)。
    - task_id: 从分支名解析出的任务 (MP-XXX-NNN / T-NNN), 无匹配 → None。
    - status: bound (解析出 task_id) / unbound (分支存在但无任务匹配) /
      error (非 git 仓库或查询失败)。
    """

    branch: str | None = None
    task_id: str | None = None
    project_id: str | None = None
    status: str = "unbound"  # bound/unbound/error
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("status")
    @classmethod
    def _status_clean(cls, v: str) -> str:
        v = (v or "unbound").strip().lower()
        return v if v in _BRANCH_STATUSES else "unbound"

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ChangeAnalysis(BaseModel):
    """一次任务的变更分析结果 (ChangeAnalyzer 路径分析, 禁 LLM — ADR-0019 决策 2)。

    - files: 关联文件路径 (排序去重)。
    - insertions/deletions: 行数对账 (绑定变更 + 实时 diff 求和)。
    - affected_modules: 路径分段推断的模块列表 (目录分段/模块推断, 确定性规则)。
    - commits: 关联提交哈希 (commit message 解析 / 绑定回填)。
    """

    task_id: str
    files: list[str] = Field(default_factory=list)
    insertions: int = 0
    deletions: int = 0
    affected_modules: list[str] = Field(default_factory=list)
    commits: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("insertions", "deletions")
    @classmethod
    def _counts_non_negative(cls, v: int) -> int:
        return max(0, v)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ChangeValidationResult(BaseModel):
    """L4 Change Validation 判定结果 (CLI change validate / change.validation.completed 载荷)。

    - task_id: 被验证任务。
    - status: PASS (变更与任务一致) / FAIL (变更证据与任务不符) /
      SKIP (无 git 关联 / 无证据 — 旧 Task 兼容) / ERROR (规则内部错误)。
    - message: 人类可读证据摘要。
    """

    id: str = "L4.change"  # 规则 id 前缀 (与 validation 规则集命名一致)
    task_id: str
    status: str = "SKIP"
    message: str = ""
    checks: list[dict[str, Any]] = Field(default_factory=list)  # 逐规则 [{id,status,message}]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> str:
        v = str(v or "SKIP").strip().upper()
        return v if v in CHANGE_STATUSES else "SKIP"

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ChangeContext(BaseModel):
    """L4 规则输入快照: 任务在仓库中的变更证据 (ChangeService.change_context 装配)。

    - task_id: 被验证任务; task_title: 任务标题 (L4 路径匹配的对照文本)。
    - commits: 关联提交 (task_id 已解析); files: 关联文件路径;
      insertions/deletions: 行数对账; affected_modules: 模块推断。
    - is_repo=False (非 git 仓库/查询失败) → L4 规则全部 SKIP (无 git 关联)。
    """

    task_id: str
    task_title: str = ""
    repository: str = ""
    is_repo: bool = False
    has_commits: bool = False  # 仓库存在提交 (变更证据; 空仓库/非 git → False)
    commits: list[GitCommit] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    insertions: int = 0
    deletions: int = 0
    affected_modules: list[str] = Field(default_factory=list)
    error: str | None = None  # 仓库查询失败原因 (失败安全)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ExecutionGitSnapshot(BaseModel):
    """Execution ↔ Git 快照关联 (Execution 完成时记录, 兼容旧数据)。

    - execution_id: 关联执行请求 (RuntimeStore 主键)。
    - before_commit: 执行前 HEAD; after_commit: 执行后 HEAD;
      changed_files: 执行完成时工作区变更路径 (任务接管变更的审计快照)。
    - 关联存储 (ChangeStore JSON, 原子写) — 不改 ExecutionRequest/Result 模型,
      旧执行记录无快照字段完全正常 (ADR-0019 决策 3)。
    """

    id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex)
    execution_id: str
    task_id: str | None = None
    project_id: str | None = None
    repository: str = ""
    before_commit: str | None = None
    after_commit: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
