"""providers/adapters — 内置 Provider 适配器实现 (Phase 8A: hermes 真实 Agent)。

BUILTIN_PROVIDER_ADAPTERS: {provider_id: ProviderAdapter} 内置实现映射:
- hermes (id="hermes", type="agent"): HermesProviderAdapter — 真实 Agent 智能来源,
  subprocess 调 hermes CLI (Phase 8A)。

边界 (同 ADR-0007 决策 3 模式): 实现映射 (本包) 与能力目录 (ProviderRegistry/
catalog.json) 解耦 — 内置 Adapter 只提供"实现", Provider 定义由目录合并视图
(默认定义基线 + 持久化定义) 提供。命名空间独立于 runtime/adapters
(HermesRuntimeAdapter id="hermes-runtime") — 执行机制与智能来源并存 (phase8-plan §Q4)。

HermesProviderAdapter 实例化成本为零 (无连接/无密钥), 模块级单例安全 (同 runtime
BUILTIN_ADAPTERS 模式)。
"""

from __future__ import annotations

from providers.provider import ProviderAdapter

from .hermes import HermesProviderAdapter

BUILTIN_PROVIDER_ADAPTERS: dict[str, ProviderAdapter] = {
    HermesProviderAdapter.PROVIDER_ID: HermesProviderAdapter(),
}

__all__ = ["HermesProviderAdapter", "BUILTIN_PROVIDER_ADAPTERS"]
