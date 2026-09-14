"""services.execution — 执行实例 / 结果。

拥有契约：contracts/execution.py
调度器经 core.scheduler.ports.ExecutionPort 查活跃执行、创建实例。
关键语义：执行成功 ≠ 业务完成；完成由 Outcome.accepted 定义。
不负责：真正干活（plugins）、验收判定标准（能力声明的 verify）。
"""

# ── 原 factory-core/runtimes/__init__.py（刀43 迁入）──
"""runtimes — Runtime 能力目录层 (Phase 5A.1: 描述 Catalog ≠ 实例 Registry ≠ 执行器 Runtime)。

对外出口: RuntimeDefinition / CatalogStatus / RuntimeCatalog / CatalogStore /
RuntimeCatalogError 系列异常 / 默认定义 (DEFAULT_DEFINITIONS + default_definitions)。
只描述能力, 不参与派发与执行 (ADR-0014)。
"""

from .catalog import (
    RuntimeCatalog,
    RuntimeCatalogError,
    RuntimeDefinitionExistsError,
    RuntimeDefinitionNotFoundError,
)
from .definitions import DEFAULT_DEFINITIONS, default_definition, default_definitions
from .runtime_types import CatalogStatus, RuntimeDefinition
from .store import CatalogStore, CatalogStoreError, CorruptCatalogStoreError

__all__ = [
    "RuntimeDefinition",
    "CatalogStatus",
    "RuntimeCatalog",
    "RuntimeCatalogError",
    "RuntimeDefinitionExistsError",
    "RuntimeDefinitionNotFoundError",
    "CatalogStore",
    "CatalogStoreError",
    "CorruptCatalogStoreError",
    "DEFAULT_DEFINITIONS",
    "default_definitions",
    "default_definition",
]

# ── 原 factory-core/execution/__init__.py（刀48 迁入）──
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
