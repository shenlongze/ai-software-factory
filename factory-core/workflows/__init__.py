"""workflows — Workflow Engine (Phase 4A: 定义 + 运行状态机 + JSON 持久化)。

对外出口: Workflow / WorkflowStep / WorkflowRun / WorkflowStatus / StepStatus /
WorkflowStore / WorkflowEngine / 内置定义 BUILTIN_WORKFLOWS。
"""

from .definitions import BUILTIN_WORKFLOWS, get_builtin, list_builtins
from .engine import (
    StepNotReadyError,
    StepNotFoundError,
    WorkflowAlreadyStartedError,
    WorkflowEngine,
    WorkflowEngineError,
    WorkflowExistsError,
    WorkflowNotFoundError,
    WorkflowRunNotFoundError,
    WorkflowStateError,
)
from .models import StepState, StepStatus, Workflow, WorkflowRun, WorkflowStatus, WorkflowStep
from .store import CorruptWorkflowStoreError, WorkflowStore, WorkflowStoreError

__all__ = [
    "Workflow",
    "WorkflowStep",
    "WorkflowStatus",
    "StepStatus",
    "StepState",
    "WorkflowRun",
    "WorkflowStore",
    "WorkflowStoreError",
    "CorruptWorkflowStoreError",
    "WorkflowEngine",
    "WorkflowEngineError",
    "WorkflowStateError",
    "WorkflowExistsError",
    "WorkflowNotFoundError",
    "WorkflowRunNotFoundError",
    "WorkflowAlreadyStartedError",
    "StepNotFoundError",
    "StepNotReadyError",
    "BUILTIN_WORKFLOWS",
    "get_builtin",
    "list_builtins",
]
