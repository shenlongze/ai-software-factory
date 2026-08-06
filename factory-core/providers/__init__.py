"""factory-core/providers/ — LLM Provider Abstraction (Phase 8A, ADR-0022)。

智能来源层 (Extension, 与 runtime/ 执行机制平级分离, phase8-plan §Q1):
- models.py: ProviderDefinition + ProviderRequest/Response (统一 I/O, 不绑 OpenAI 格式)
- provider.py: ProviderAdapter 抽象接口 (generate/chat/stream)
- registry.py: ProviderRegistry (register/get/list/remove/find_by_capability/default)
- store.py: ProviderStore — catalog.json 原子写 (独立数据空间 .factory/providers/)
- definitions.py: 默认定义 (hermes, 内建基线)
- events.py: provider.* 事件辅助 (经 EventLogger; 8B-1 增 execution_id/source)
- config.py: runtime_preferences.provider 字段语义 (parse_runtime_preferences)
- selector.py: ProviderSelector — 四层优先级选择 (Phase 8B-1, Project > Agent >
  Runtime > Default, 无硬编码)
- integration.py: Provider × Execution 集成 (input 携带 provider_id + provider.*
  执行审计事件, ProviderCarrierAdapter 载波, Phase 8B-1)
- adapters/: BUILTIN_PROVIDER_ADAPTERS (hermes — 与 runtime/adapters 并存不替换)

冻结约束 (phase8a-status.md): Core 零修改 / Runtime 与 Provider 分离 / Hermes
双角色并存 / 删除 providers 不影响 Factory (独立数据空间 + 零 Core 依赖 —
CLI/dashboard 均延迟导入本包)。
"""

from __future__ import annotations

from .config import parse_runtime_preferences, preferred_provider, runtime_default_provider
from .integration import (
    ProviderCarrierAdapter,
    ProviderContext,
    carry_provider_input,
    provider_context_from_selection,
    wrap_adapters_with_provider,
)
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
from .selector import (
    RECOMMENDATION_SOURCE,
    SELECTION_SOURCES,
    CostAwareSelector,
    ProviderSelection,
    ProviderSelector,
    Recommendation,
)
from .store import CorruptProviderStoreError, ProviderStore, ProviderStoreError
from .capability import ProviderCapabilityProfile, find_best_for_task, rank_for_task
from .costs import (
    COST_MODES,
    ESTIMATED_DURATION_SECONDS,
    ESTIMATED_TOKENS,
    ProviderCostModel,
    estimate_call_cost,
)
from .usage import (
    PERIODS,
    ProviderPerformanceStats,
    ProviderUsage,
    UsageStore,
    filter_by_period,
    stats_from_usage,
)
from .models import TaskRequirement

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
    # --- Phase 8B-1 (ADR-0023): 选择 + 执行集成 ---
    "SELECTION_SOURCES",
    "ProviderSelection",
    "ProviderSelector",
    "ProviderContext",
    "ProviderCarrierAdapter",
    "carry_provider_input",
    "provider_context_from_selection",
    "wrap_adapters_with_provider",
    "parse_runtime_preferences",
    "preferred_provider",
    "runtime_default_provider",
    # --- Phase 8B-2 (ADR-0024): 能力 + 成本 + 使用层 ---
    "TaskRequirement",
    "ProviderCapabilityProfile",
    "find_best_for_task",
    "rank_for_task",
    "COST_MODES",
    "ESTIMATED_TOKENS",
    "ESTIMATED_DURATION_SECONDS",
    "ProviderCostModel",
    "estimate_call_cost",
    "PERIODS",
    "ProviderUsage",
    "ProviderPerformanceStats",
    "UsageStore",
    "filter_by_period",
    "stats_from_usage",
    "CostAwareSelector",
    "Recommendation",
    "RECOMMENDATION_SOURCE",
]
