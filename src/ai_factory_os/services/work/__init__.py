"""services.work — 项目 / 工作 / 工作流 / 任务 / 任务节点。

拥有契约：contracts/work.py
调度器经 core.scheduler.ports.WorkPort 读取节点、依赖、时限、优先级。
不负责：调度决策（core/scheduler）、执行（services/execution）。
"""

# ── 原 factory-core/tasks/__init__.py（刀38 迁入）──
# tasks — Task 领域 (Phase 2: Pydantic Task + JSON 文件 TaskStore + 五状态)。

from .types import Task, TaskStatus
from .store import TaskExistsError, TaskNotFoundError, TaskStore, TaskStoreError

__all__ = [
    "Task",
    "TaskStatus",
    "TaskStore",
    "TaskStoreError",
    "TaskExistsError",
    "TaskNotFoundError",
]
