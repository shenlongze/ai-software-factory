"""workflows — Workflow Engine (Phase 4A: 定义 + 运行状态机 + JSON 持久化)。

对外出口: Workflow / WorkflowStep / WorkflowRun / WorkflowStatus / StepStatus /
WorkflowStore / WorkflowEngine / 内置定义 BUILTIN_WORKFLOWS。
"""

from .models import StepState, StepStatus, Workflow, WorkflowRun, WorkflowStatus, WorkflowStep
# ★ engine 改为惰性重导出（PEP 562）:
#   workflows/__init__ → engine → ...services.work.store → 回到 workflows
#   的导入环: 急切导入时 workflows 尚未绑定 engine 名 → ImportError ✗
#   惰性化后，只有真正访问这些名字时才导入 engine ✓

_LAZY_EXPORTS = frozenset({   # engine + store: 两端都惰性 → 环不可能形成
    "StepNotReadyError",
    "StepNotFoundError",
    "WorkflowAlreadyStartedError",
    "WorkflowEngine",
    "WorkflowEngineError",
    "WorkflowExistsError",
    "WorkflowNotFoundError",
    "WorkflowRunNotFoundError",
    "WorkflowStateError",
    "CorruptWorkflowStoreError",
    "WorkflowStore",
    "WorkflowStoreError",
})


def __getattr__(name: str):
    """惰性暴露 engine 的公开名字（打破导入环 ✓）。"""
    if name in _LAZY_EXPORTS:
        from .engine import __dict__ as _ed
        value = _ed.get(name)
        if value is not None:
            globals()[name] = value
            return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
from .definitions import BUILTIN_WORKFLOWS, get_builtin, list_builtins

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
