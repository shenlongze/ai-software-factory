"""git — Git Integration Layer (Phase 6C, ADR-0018)。

Task 与 Git 变更的可追踪关系 (Git 只读 + 审计):
- models: GitContext/GitChange/GitCommit (Pydantic v2)
- client: GitClient (subprocess 只读 git, 失败安全返回)
- service: GitService (get_status/get_changes/get_commits/bind_task_change)
- events: git.* 审计事件辅助 (经 EventLogger)

工程规则: 零仓库写命令 (无 push/merge/rebase), 无 Workflow/Execution 依赖,
旧 Task (无 git 关联) 完全兼容。
"""

from .client import GitClient
from .models import GitChange, GitCommit, GitContext
from .service import GitChangeStore, GitService, GitTaskNotFoundError

__all__ = [
    "GitClient",
    "GitChange",
    "GitChangeStore",
    "GitCommit",
    "GitContext",
    "GitService",
    "GitTaskNotFoundError",
]
