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
