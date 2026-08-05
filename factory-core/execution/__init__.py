"""execution — 执行派发层 (Phase 4B-2): Dispatcher / Runner / Service。

对外出口:
- ExecutionDispatcher (resolve runtime_id → Adapter → execute, 含 NoAvailableRuntimeError /
  RuntimeAdapterNotFoundError / ExecutionDispatchError)
- ExecutionRunner (生命周期 PENDING→started→execute→SUCCESS/FAILED→completed/failed,
  含 ExecutionNotFoundError / ExecutionStateError / ExecutionRunOutcome)
- ExecutionService (组合根: 统一编排与查询)

内置 Runtime 实现 (EchoRuntimeAdapter, id="echo", type="mock") 在 runtime.adapters,
身份注册经 RuntimeRegistry (ADR-0007 决策 3)。
"""

from __future__ import annotations

from .dispatcher import (
    ExecutionDispatchError,
    ExecutionDispatcher,
    ExecutionDispatcherError,
    NoAvailableRuntimeError,
    RuntimeAdapterNotFoundError,
)
from .runner import (
    ExecutionNotFoundError,
    ExecutionRunner,
    ExecutionRunnerError,
    ExecutionRunOutcome,
    ExecutionStateError,
)
from .service import ExecutionService

__all__ = [
    "ExecutionDispatcher",
    "ExecutionDispatcherError",
    "NoAvailableRuntimeError",
    "RuntimeAdapterNotFoundError",
    "ExecutionDispatchError",
    "ExecutionRunner",
    "ExecutionRunnerError",
    "ExecutionNotFoundError",
    "ExecutionStateError",
    "ExecutionRunOutcome",
    "ExecutionService",
]
