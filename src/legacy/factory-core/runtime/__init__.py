"""runtime — Runtime Adapter 接口层 (Phase 4B-1: 抽象接口 + 注册表 + JSON 持久化)。

对外出口: ExecutionRequest / ExecutionResult / ExecutionStatus / RuntimeInfo /
RuntimeStatus / RuntimeAdapter / RuntimeRegistry / RuntimeStore (+ 异常)。
本阶段无具体 Runtime 实现 (Hermes/mock 等落地于 Phase 4B-2+)。
"""

from .adapter import RuntimeAdapter
from .models import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    RuntimeInfo,
    RuntimeStatus,
)
from .registry import (
    RuntimeExistsError,
    RuntimeNotFoundError,
    RuntimeRegistry,
    RuntimeRegistryError,
)
from .store import CorruptRuntimeStoreError, RuntimeStore, RuntimeStoreError

__all__ = [
    "ExecutionRequest",
    "ExecutionResult",
    "ExecutionStatus",
    "RuntimeInfo",
    "RuntimeStatus",
    "RuntimeAdapter",
    "RuntimeRegistry",
    "RuntimeRegistryError",
    "RuntimeExistsError",
    "RuntimeNotFoundError",
    "RuntimeStore",
    "RuntimeStoreError",
    "CorruptRuntimeStoreError",
]
