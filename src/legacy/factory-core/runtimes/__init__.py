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
from .models import CatalogStatus, RuntimeDefinition
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
