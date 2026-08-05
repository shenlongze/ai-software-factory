"""change/linker.py — Commit parser + 分支任务上下文绑定 (Phase 6D, ADR-0019)。

设计依据:
- phase6d-status.md: Commit message parser (MP-BUG-001 → GitCommit.task_id;
  branch/message/execution context 三来源) + GitBranchContext (branch/task_id/
  project_id/status/created_at) + git.task.bound / git.commit.linked 事件
- Git 只读铁律: 本模块只解析/关联 (纯函数 + 只读 client 查询), 零仓库写命令。

任务 ID 语法 (Task.id 约定, 大小写不敏感归一):
- MP-XXX-NNN: MP-BUG-001 / MP-FEATURE-002 / MP-TASK-014 (产品前缀-类型-序号)
- T-NNN: T-001 (Phase 1-3 遗留编号)
归一化: MP-bug-001 → MP-BUG-001 (类型段大写); T-001 原样。

三来源优先级 (ADR-0019 决策 1): commit message > execution context (显式
注入的执行任务) > branch name (分支命名约定 feature/MP-FEATURE-002-x)。
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from git.client import GitClient
from git.models import GitCommit

from .models import GitBranchContext

# 任务 ID 类型段 (MP-<TYPE>-<NUM> 的 TYPE 词汇)
_TASK_TYPES = ("BUG", "FEATURE", "TASK", "EPIC", "STORY", "CHORE")

# 主模式: MP-BUG-001 (类型段大小写不敏感, 归一大写); 次模式: T-001 (原样大写)
_TASK_ID_RE = re.compile(
    rf"\b(MP-(?:{'|'.join(_TASK_TYPES)})-\d{{1,6}})\b",
    re.IGNORECASE,
)
_TASK_ID_RE_SHORT = re.compile(r"\b(T-\d{1,6})\b")

# 分支名中的任务段 (feature/MP-FEATURE-002-login → MP-FEATURE-002)
_BRANCH_TASK_RE = re.compile(
    rf"(?:^|[/_-])(MP-(?:{'|'.join(_TASK_TYPES)})-\d{{1,6}})(?:[/_-]|$)",
    re.IGNORECASE,
)

# 解析结果为空时的判定: 分支存在但无任务匹配 → unbound
BRANCH_STATUS_BOUND = "bound"
BRANCH_STATUS_UNBOUND = "unbound"
BRANCH_STATUS_ERROR = "error"


def normalize_task_id(value: str) -> str:
    """归一化任务 ID: 去空白, MP-XXX 类型段大写 (T-001 原样)。"""
    v = (value or "").strip()
    if not v:
        return ""
    if v.upper().startswith("MP-"):
        head, sep, tail = v.partition("-")
        if sep and tail:
            return f"{head.upper()}-{tail.upper()}"
        return v.upper()
    return v.upper()


def parse_task_id(text: str) -> str | None:
    """从任意文本提取任务 ID (message/branch/描述通用; 首个匹配, 大小写归一)。

    优先级: MP-XXX-NNN (类型段受控词汇) > T-NNN (短编号)。无匹配 → None。
    """
    if not text:
        return None
    m = _TASK_ID_RE.search(text)
    if m:
        return normalize_task_id(m.group(1))
    m = _TASK_ID_RE_SHORT.search(text)
    if m:
        return normalize_task_id(m.group(1))
    return None


def task_id_from_message(message: str) -> str | None:
    """commit message → task_id (来源 1: message, 最高优先级)。"""
    return parse_task_id(message)


def task_id_from_branch(branch: str | None) -> str | None:
    """分支名 → task_id (来源 3: branch; feature/MP-FEATURE-002-login 形态)。"""
    if not branch:
        return None
    m = _BRANCH_TASK_RE.search(branch)
    if m:
        return normalize_task_id(m.group(1))
    # 兜底: 整体就是任务 ID 的分支名 (如 'MP-BUG-001')
    return parse_task_id(branch) if _TASK_ID_RE.match(branch.strip()) or _TASK_ID_RE_SHORT.match(branch.strip()) else None


class CommitLinker:
    """Commit → task_id 关联器 (三来源: message > execution > branch)。

    - link(): 单条提交解析; 已带 task_id 的提交 (绑定回填) 不被覆盖。
    - link_many(): 批量 (log 列表), 同一分支/执行上下文统一注入。
    纯函数, 不发事件 (事件由 ChangeService 统一经 EventLogger 发出)。
    """

    def __init__(self, patterns: Iterable[re.Pattern] | None = None) -> None:
        self._patterns = list(patterns) if patterns is not None else [_TASK_ID_RE, _TASK_ID_RE_SHORT]

    def link(
        self,
        commit: GitCommit,
        *,
        branch: str | None = None,
        execution_task_id: str | None = None,
    ) -> GitCommit:
        """解析单条提交的任务关联 (已有 task_id 不覆盖, 幂等)。"""
        if commit.task_id:
            return commit
        task_id = task_id_from_message(commit.message)
        if not task_id and execution_task_id:
            task_id = normalize_task_id(execution_task_id)
        if not task_id:
            task_id = task_id_from_branch(branch or commit.branch)
        if task_id:
            return commit.model_copy(update={"task_id": task_id})
        return commit

    def link_many(
        self,
        commits: list[GitCommit],
        *,
        branch: str | None = None,
        execution_task_id: str | None = None,
    ) -> list[GitCommit]:
        """批量解析 (返回新列表, 原列表不动)。"""
        return [self.link(c, branch=branch, execution_task_id=execution_task_id) for c in commits]


def bind_branch(
    client: GitClient,
    *,
    branch: str | None = None,
    project_id: str | None = None,
) -> GitBranchContext:
    """仓库分支的任务上下文投影 (branch → task_id 解析)。

    - bound: 解析出 task_id (分支命名含任务 ID)。
    - unbound: 分支存在但无任务匹配 (含分支为 None — detached/非 git)。
    - error: 非 git 目录/查询失败 (失败安全: 不抛异常)。
    只读: 仅调 client.current_branch() (subprocess 读命令, 失败安全)。
    """
    if branch is None:
        try:
            if not client.is_repo():
                return GitBranchContext(branch=None, task_id=None, project_id=project_id, status=BRANCH_STATUS_ERROR)
            branch = client.current_branch()
        except Exception:  # 防御兜底: 任何 client 异常 → error 状态
            return GitBranchContext(branch=None, task_id=None, project_id=project_id, status=BRANCH_STATUS_ERROR)
    task_id = task_id_from_branch(branch) if branch else None
    return GitBranchContext(
        branch=branch,
        task_id=task_id,
        project_id=project_id,
        status=BRANCH_STATUS_BOUND if task_id else BRANCH_STATUS_UNBOUND,
    )


def is_repo_reachable(client: GitClient) -> bool:
    """仓库是否可达 (is_repo 失败安全)。"""
    try:
        return bool(client.is_repo())
    except Exception:
        return False
