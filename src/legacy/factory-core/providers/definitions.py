"""providers/definitions.py — 默认 Provider 定义 (hermes, 只描述不执行)。

设计依据:
- phase8a-status.md: 默认 hermes provider (Phase 8a 基础); phase8-plan.md §Q4:
  Hermes 双角色 — 既有 Runtime Adapter (执行, runtime/adapters/hermes.py) + 新
  Provider Adapter (智能, providers/adapters/hermes.py) 并存不替换。
- 边界 (同 runtimes/definitions.py ADR-0014 决策 3): 默认定义常驻代码层, 是
  Provider 目录的内建基线 (builtin baseline) — 读路径 (get/list/find_by_capability/
  default) 由 ProviderRegistry 合并, 永不自动写入 catalog.json; 持久化层只存
  用户注册/覆盖的定义。
- Phase 8B-2 (phase8b2-plan.md §7): 能力/成本模型基线同样常驻代码层 —
  DEFAULT_CAPABILITY_PROFILES (能力矩阵 + evidence 依据) / DEFAULT_COST_MODELS
  (定价估算, 非真实计费) 与定义基线一一对应 (hermes), CostAwareSelector 与
  CLI compare/recommend 读路径合并; 持久化覆盖 (capability.json/costs.json)
  留待后续阶段 (本阶段 KISS: 只读基线, 自定义 Provider 的能力/成本数据由
  调用方注入)。

与内置 Adapter 的关系: 定义 id 与 BUILTIN_PROVIDER_ADAPTERS 键一致 (hermes) —
Provider 命名空间独立于 Runtime 命名空间 (runtime 的 hermes 身份为 hermes-runtime)。
"""

from __future__ import annotations

from .capability import ProviderCapabilityProfile
from .costs import ProviderCostModel
from .models import ProviderDefinition, ProviderStatus

DEFAULT_PROVIDER_DEFINITIONS: list[ProviderDefinition] = [
    ProviderDefinition(
        id="hermes",
        name="Hermes Agent",
        type="agent",
        description="Hermes Agent — Nous Research 的通用 AI Agent (经 hermes CLI "
                    "-z one-shot 调用, Factory 默认智能来源)",
        capabilities=["chat", "generation", "code", "reasoning", "tool-use"],
        models=["hermes-default"],
        version="1.0.0",
        status=ProviderStatus.ACTIVE,
        config_schema={
            "command": {"type": "string", "default": "hermes",
                        "env": "FACTORY_PROVIDER_HERMES_CMD",
                        "description": "hermes CLI 命令 (可给绝对路径)"},
            "timeout_s": {"type": "number", "default": 300,
                          "env": "FACTORY_PROVIDER_HERMES_TIMEOUT",
                          "description": "一次 one-shot 调用超时秒数"},
            "mode": {"type": "string", "default": "cli -z",
                     "description": "调用方式: cli -z (subprocess) / api (预留)"},
        },
        metadata={
            "vendor": "Nous Research",
            "execution": "hermes -z (one-shot subprocess)",
            "builtin": True,
        },
    ),
]

DEFAULT_PROVIDER_IDS: tuple[str, ...] = tuple(d.id for d in DEFAULT_PROVIDER_DEFINITIONS)

#: 默认能力基线 (Phase 8B-2): provider_id → 能力矩阵质量分 + evidence 依据。
#: 质量分是估算基准 (非实测值), evidence 标注来源 — 自定义 Provider 的能力
#: 数据由调用方注入 CostAwareSelector (能力过滤不臆造无 evidence 的能力)。
DEFAULT_CAPABILITY_PROFILES: dict[str, ProviderCapabilityProfile] = {
    "hermes": ProviderCapabilityProfile(
        provider_id="hermes",
        matrix={
            "chat": 0.9,
            "generation": 0.8,
            "code": 0.8,
            "reasoning": 0.7,
            "analysis": 0.6,
            "tool-use": 0.7,
        },
        evidence=[
            "builtin baseline (phase8b2-plan.md §4): 默认定义能力标签的估算质量分",
            "measured: factory provider smoke (2026-08)",
        ],
    ),
}

#: 默认成本基线 (Phase 8B-2): provider_id → 定价估算模型。hermes 本地执行 →
#: free (免费, 非真实计费); 云 Provider 的成本数据由调用方注入。
DEFAULT_COST_MODELS: dict[str, ProviderCostModel] = {
    "hermes": ProviderCostModel(
        provider_id="hermes",
        mode="free",
        pricing={},
        currency="USD",
        free=True,
    ),
}


def default_provider_definitions() -> list[ProviderDefinition]:
    """默认定义深拷贝列表 (调用方可安全修改, 不影响模块常量)。"""
    return [d.model_copy(deep=True) for d in DEFAULT_PROVIDER_DEFINITIONS]


def default_provider_definition(provider_id: str) -> ProviderDefinition | None:
    """按 id 取默认定义 (未命中返回 None)。"""
    for d in DEFAULT_PROVIDER_DEFINITIONS:
        if d.id == provider_id:
            return d.model_copy(deep=True)
    return None
