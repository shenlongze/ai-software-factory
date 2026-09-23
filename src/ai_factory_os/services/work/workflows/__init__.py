"""workflows — Workflow Engine (Phase 4A: 定义 + 运行状态机 + JSON 持久化)。

对外出口: Workflow / WorkflowStep / WorkflowRun / WorkflowStatus / StepStatus /
WorkflowStore / WorkflowEngine / 内置定义 BUILTIN_WORKFLOWS。
"""

import importlib
from .types import StepState, StepStatus, Workflow, WorkflowRun, WorkflowStatus, WorkflowStep
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
    """惰性暴露 engine / store 的公开名字（打破导入环 ✓）。

    ★ 2026-09-20 修: 原来**只查 engine.__dict__** ⇒ `__all__` 里承诺的
    WorkflowStoreError / CorruptWorkflowStoreError（它们住在 store.py）**永远拿不到**
    （`from ...workflows import *` 会直接 ImportError）—— 清 lint 债时用导入冒烟查出来的。
    """
    if name in _LAZY_EXPORTS:
        for mod_name in (".engine", ".store"):
            try:
                mod = importlib.import_module(mod_name, __name__)
            except Exception:  # noqa: BLE001 — 某一侧导入失败不影响另一侧
                continue
            value = getattr(mod, name, None)
            if value is not None:
                globals()[name] = value
                return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
from .definitions import BUILTIN_WORKFLOWS, get_builtin, list_builtins  # noqa: E402 — 必须在这之后: 先建 __getattr__ 惰性出口, 否则与 engine 形成导入环（见上注释）

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
