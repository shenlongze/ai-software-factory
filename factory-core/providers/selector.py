"""providers/selector.py — ProviderSelector: 四层优先级选择 (Phase 8B-1, ADR-0023)。

设计依据:
- phase8-plan.md §Q5: 选择优先级 1. 显式项目配置 (project.yaml
  runtime_preferences.<task_type>.provider) > 2. Agent 要求 (Agent.runtime_preferences,
  角色级) > 3. Runtime 能力 (Runtime 声明的默认 provider) > 4. 默认 provider
  (ProviderRegistry.default)。配置驱动, 无硬编码选择逻辑 — 本模块是纯决策引擎,
  每一层都是调用方注入的数据 (dict/id), 不自己读任何存储。
- phase8b1-status.md: resolve(project_prefs, agent_prefs, runtime_default,
  registry_default) → ProviderSelection | None; 每层缺失 → 降级下一层; 全部缺失
  → None; 显式覆盖 (CLI --provider) 优先于项目配置。
- 边界: 选择只产出 provider id + 来源; 是否真去调用 Provider (adapter.generate)
  由上层 (Execution 集成层) 决定 — 本阶段仅选择 + 审计 (provider.selected),
  不实现 OpenAI/Claude Adapter (phase8b1-status.md 冻结约束)。

层级语义:
- explicit (CLI --provider 显式覆盖): 用户明确指定 — 未注册/禁用 → 抛
  ProviderNotFoundError (配置缺口显式暴露, 同 cmd_provider_test 契约), 不静默降级。
- project / agent / runtime / default: 配置层 — 条目缺失、id 为空、未注册或
  DISABLED (models.py: DISABLED 不参与选择/执行) 均视为"该层缺失" → 降级下一层。

ProviderSelection.source 取值: explicit | project | agent | runtime | default
(provider.selected 事件 payload 的 source 字段, phase8b1-status.md §3)。

注册表装配 (可选): ProviderSelector(registry) 时对配置层做存在性/状态校验
(未注册/禁用 → 降级); 不装配注册表时只做 id 链决策 (provider 定义由调用方
自行解析) — 纯函数语义, 便于无存储单测。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import preferred_provider
from .models import ProviderDefinition, ProviderStatus
from .registry import ProviderNotFoundError, ProviderRegistry

#: provider.selected 事件 payload 的 source 取值 (优先级链层名)
SELECTION_SOURCES: tuple[str, ...] = ("explicit", "project", "agent", "runtime", "default")


@dataclass(frozen=True)
class ProviderSelection:
    """一次选择结果: provider id + 定义 (注册表装配时回填) + 来源层。"""

    provider_id: str
    provider: ProviderDefinition | None = None
    source: str = "project"  # explicit|project|agent|runtime|default

    def to_dict(self) -> dict[str, Any]:
        return {"provider_id": self.provider_id, "source": self.source}


class ProviderSelector:
    """Provider 选择器: 四层优先级链 (Project > Agent > Runtime > Default), 无硬编码。

    用法 (CLI 集成层, 延迟导入 — Removal Isolation):
        selector = ProviderSelector(provider_registry)
        selection = selector.resolve(
            task_type=task.type,
            explicit=args.provider,            # CLI --provider 显式覆盖
            project_prefs=project_prefs,       # project.yaml runtime_preferences
            agent_prefs=agent_prefs,           # Agent 角色级偏好 (未来字段)
            runtime_default=runtime_default,   # Runtime 目录定义声明的默认 provider
            registry_default=registry_default, # ProviderRegistry.default().id
        )
    """

    def __init__(self, registry: ProviderRegistry | None = None):
        self._registry = registry

    @property
    def registry(self) -> ProviderRegistry | None:
        return self._registry

    # ------------------------------------------------------------------ 选择

    def resolve(
        self,
        *,
        task_type: str,
        explicit: str | None = None,
        project_prefs: dict[str, Any] | None = None,
        agent_prefs: dict[str, Any] | None = None,
        runtime_default: str | None = None,
        registry_default: str | None = None,
    ) -> ProviderSelection | None:
        """按优先级链选择 provider; 全部缺失 → None。

        层级: explicit (CLI --provider) > project (runtime_preferences.\
        <task_type>.provider) > agent (角色级偏好同构) > runtime (Runtime 声明
        默认) > default (ProviderRegistry 默认)。每层缺失 (条目/空 id/未注册/
        DISABLED) → 降级下一层; 显式层未注册/禁用 → ProviderNotFoundError。
        """
        # 层 0: 显式覆盖 (CLI --provider) — 用户意图, 不静默降级
        if explicit is not None and str(explicit).strip():
            provider_id = str(explicit).strip()
            definition = self._resolve_definition(provider_id)
            if self._registry is not None and definition is None:
                raise ProviderNotFoundError(
                    f"provider not found or disabled: {provider_id}"
                )
            return ProviderSelection(
                provider_id=provider_id, provider=definition, source="explicit",
            )
        # 层 1: 显式项目配置 (project.yaml runtime_preferences.<task_type>.provider)
        selection = self._config_layer(
            preferred_provider(project_prefs, task_type), "project",
        )
        if selection is not None:
            return selection
        # 层 2: Agent 要求 (Agent.runtime_preferences, 角色级; 与项目层同构解析)
        selection = self._config_layer(
            preferred_provider(agent_prefs, task_type), "agent",
        )
        if selection is not None:
            return selection
        # 层 3: Runtime 能力 (Runtime 目录定义声明的默认 provider)
        selection = self._config_layer(runtime_default, "runtime")
        if selection is not None:
            return selection
        # 层 4: 默认 provider (ProviderRegistry.default)
        return self._config_layer(registry_default, "default")

    # ------------------------------------------------------------------ 内部

    def _config_layer(self, provider_id: str | None, source: str) -> ProviderSelection | None:
        """配置层选择: 条目缺失/空 id/未注册/禁用 → None (降级下一层)。"""
        if provider_id is None or not str(provider_id).strip():
            return None
        provider_id = str(provider_id).strip()
        definition = self._resolve_definition(provider_id)
        if self._registry is not None and definition is None:
            return None  # 已装配注册表: 未注册/禁用 = 该层缺失
        return ProviderSelection(
            provider_id=provider_id, provider=definition, source=source,
        )

    def _resolve_definition(self, provider_id: str) -> ProviderDefinition | None:
        """按 id 解析定义 (注册表装配时); 未装配 → None (不校验, 调用方自行解析)。

        DISABLED 不参与选择/执行 (models.py ProviderStatus 契约) — 返回 None
        由 _config_layer 降级 / resolve 显式层抛错。
        """
        if self._registry is None:
            return None
        definition = self._registry.get(provider_id)
        if definition is None or definition.status is not ProviderStatus.ACTIVE:
            return None
        return definition
