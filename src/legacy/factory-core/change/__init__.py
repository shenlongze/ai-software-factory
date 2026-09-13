"""change — Change Intelligence Layer (Phase 6D, ADR-0019)。

Task→Execution→Git Change→Commit→Validation 自动关联 (Git 只读 + 审计):
- models: GitBranchContext/ChangeAnalysis/ChangeContext/ChangeValidationResult/
  ExecutionGitSnapshot (Pydantic v2)
- linker: Commit parser (MP-BUG-001/MP-FEATURE-002/T-NNN → GitCommit.task_id;
  message > execution context > branch 三来源) + 分支任务上下文绑定
- analyzer: ChangeAnalyzer 路径分析 (Files/Insertions/Deletions/Affected modules,
  禁 LLM — 确定性规则) + L4 判定纯函数 (l4_checks/l4_verdict)
- service: ChangeService (parse_commits/analyze/validate/bind/snapshot_execution)
  + ChangeStore (ExecutionGitSnapshot 关联存储)
- events: git.task.bound / git.commit.linked / change.analyzed /
  change.validation.completed 审计事件辅助

工程规则: 零仓库写命令 (Git 只读铁律), runtime/execution 模型零改动 (快照
关联存储), 旧 Task (无 git 关联) 完全兼容 (L4 SKIP)。
"""

from .analyzer import ChangeAnalyzer, affected_modules, l4_checks, l4_verdict
from .linker import (
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
from .models import (
    CHANGE_STATUSES,
    ChangeAnalysis,
    ChangeContext,
    ChangeValidationResult,
    ExecutionGitSnapshot,
    GitBranchContext,
)
from .service import ChangeService, ChangeStore

__all__ = [
    # models
    "GitBranchContext",
    "ChangeAnalysis",
    "ChangeContext",
    "ChangeValidationResult",
    "ExecutionGitSnapshot",
    "CHANGE_STATUSES",
    # linker
    "CommitLinker",
    "bind_branch",
    "normalize_task_id",
    "parse_task_id",
    "task_id_from_branch",
    "task_id_from_message",
    "BRANCH_STATUS_BOUND",
    "BRANCH_STATUS_UNBOUND",
    "BRANCH_STATUS_ERROR",
    # analyzer
    "ChangeAnalyzer",
    "affected_modules",
    "l4_checks",
    "l4_verdict",
    # service
    "ChangeService",
    "ChangeStore",
]
