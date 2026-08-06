"""factory-core/providers/ — LLM Provider Abstraction (Phase 8A, ADR-0022)。

智能来源层 (Extension, 与 runtime/ 执行机制平级分离, phase8-plan §Q1):
- models.py: ProviderDefinition + ProviderRequest/Response (统一 I/O, 不绑 OpenAI 格式)
- provider.py: ProviderAdapter 抽象接口 (generate/chat/stream)
- registry.py: ProviderRegistry (register/get/list/remove/find_by_capability/default)
- store.py: ProviderStore — catalog.json 原子写 (独立数据空间 .factory/providers/)
- definitions.py: 默认定义 (hermes, 内建基线)
- events.py: provider.* 事件辅助 (经 EventLogger)
- config.py: runtime_preferences.provider 字段语义 (Phase 8c 实现选择)
- adapters/: BUILTIN_PROVIDER_ADAPTERS (hermes — 与 runtime/adapters 并存不替换)

冻结约束 (phase8a-status.md): Core 零修改 / Runtime 与 Provider 分离 / Hermes
双角色并存 / 删除 providers 不影响 Factory (独立数据空间 + 零 Core 依赖 —
CLI/dashboard 均延迟导入本包)。
"""

from __future__ import annotations

from .models import (
    ProviderDefinition,
    ProviderRequest,
    ProviderResponse,
    ProviderStatus,
)
from .provider import ProviderAdapter
from .registry import (
    ProviderExistsError,
    ProviderNotFoundError,
    ProviderRegistry,
    ProviderRegistryError,
)
from .store import CorruptProviderStoreError, ProviderStore, ProviderStoreError

__all__ = [
    "ProviderAdapter",
    "ProviderDefinition",
    "ProviderRequest",
    "ProviderResponse",
    "ProviderStatus",
    "ProviderRegistry",
    "ProviderRegistryError",
    "ProviderExistsError",
    "ProviderNotFoundError",
    "ProviderStore",
    "ProviderStoreError",
    "CorruptProviderStoreError",
]
