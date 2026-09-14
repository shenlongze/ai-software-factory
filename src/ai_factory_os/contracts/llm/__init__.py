"""llm — Provider/模型配置 与 路由决策的契约。零依赖。

三件事分清楚（这是"智能路由以后能独立成产品"的边界）:

  ProviderConfig  声明【有哪些 provider、启停、模型清单、key 引用】—— 属核心
  ModelSpec       单个模型【的规格（能力/成本/上下文）】—— 属核心
  RouteRequest / RouteDecision  路由的【问】与【答】—— 契约属核心，
                                决策器实现属插件层（可替换、可独立售卖）

核心只认识上面这些结构；不认识 L1~L5 策略，也不 import 任何路由实现。
"""

from __future__ import annotations

from .provider import (
    API_KEY_REF_PREFIX,
    PROVIDER_STATUSES,
    ModelSpec,
    ProviderConfig,
    ProviderStatus,
)
from .routing import ROUTE_LAYERS, RouteDecision, RouteLayer, RouteRequest

__all__ = [
    "API_KEY_REF_PREFIX",
    "PROVIDER_STATUSES",
    "ModelSpec",
    "ProviderConfig",
    "ProviderStatus",
    "ROUTE_LAYERS",
    "RouteDecision",
    "RouteLayer",
    "RouteRequest",
]
