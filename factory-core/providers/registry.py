"""providers/registry.py — ProviderRegistry: 能力目录 + 默认选择 (register/get/list/...)。

设计依据:
- phase8-plan.md §Q5/Q7: ProviderRegistry = Provider Catalog (定义) 读路径 +
  默认 Provider 持久化; 选择优先级 (显式项目配置 > Agent 要求 > Runtime 能力 >
  Registry 默认) 由 Phase 8c 实现, 本阶段只提供 default/resolve 基础。
- 参照 runtimes/catalog.py (RuntimeCatalog) 模式: 写方法返回 `(对象, Event | None)`;
  Event 经 events.py 辅助 (EventLogger, 不直接写 EventStore); logger 可缺省;
  存储先落地、事件后发。
- 合并视图 (同 ADR-0014 决策 3): 默认定义 (definitions.py) 是内建基线, 与已持久化
  定义合并成"目录视图" — get/list/find_by_capability/count/ids 都看合并视图;
  已持久化定义按 id 覆盖默认值。写路径 (register/remove) 只作用于持久化层:
  - register: id 在合并视图中已存在 (默认 id 保留 + 持久化重复) → ProviderExistsError;
    默认 id 不可覆盖注册 (内建定义只读)。
  - remove: 只删除持久化记录; 内建默认定义不可移除 (抛 ProviderRegistryError)。
- default (Phase 8a): set_default 持久化默认 id (provider.selected stage=default);
  default() 返回默认定义 (默认引用已移除 → 自动失效返回 None, 不抛错);
  resolve() 解析执行应使用的 provider id: 显式 id (须已注册) → 默认 → None
  (Phase 8c 扩展: capability/配置优先级)。
"""

from __future__ import annotations

from typing import Any

from events.models import Event

from .definitions import DEFAULT_PROVIDER_DEFINITIONS
from .events import (
    record_provider_registered,
    record_provider_removed,
    record_provider_selected,
)
from .models import ProviderDefinition, ProviderStatus
from .store import ProviderStore


class ProviderRegistryError(Exception):
    """ProviderRegistry 基础异常。"""


class ProviderExistsError(ProviderRegistryError):
    """Provider 已存在 (register 冲突, 含默认定义 id 保留)。"""


class ProviderNotFoundError(ProviderRegistryError):
    """Provider 不存在 (remove/set_default/resolve 未命中)。"""


class ProviderRegistry:
    """Provider 能力目录 + 默认选择: ProviderStore 持久化 + 默认定义基线 + 事件。"""

    SOURCE = "provider_registry"  # event-model §2.1 source 取值

    def __init__(self, store: ProviderStore, logger: Any | None = None):
        self._store = store
        self._logger = logger

    @property
    def store(self) -> ProviderStore:
        return self._store

    # ------------------------------------------------------------------ 合并视图

    def _merged(self) -> dict[str, ProviderDefinition]:
        """目录视图: 默认定义基线 + 已持久化定义 (持久化按 id 覆盖)。"""
        merged = {d.id: d for d in DEFAULT_PROVIDER_DEFINITIONS}
        for d in self._store.list_definitions():
            merged[d.id] = d
        return merged

    # ------------------------------------------------------------------ 写

    def register(self, definition: ProviderDefinition) -> tuple[ProviderDefinition, Event | None]:
        """注册新定义; id 冲突 (含默认定义保留) 抛 ProviderExistsError;
        发 provider.registered。"""
        if self.get(definition.id) is not None:
            raise ProviderExistsError(
                f"provider already exists: {definition.id}"
            )
        self._store.save_definition(definition)
        ev = record_provider_registered(self._logger, definition=definition)
        return definition, ev

    def remove(self, provider_id: str) -> tuple[ProviderDefinition, Event | None]:
        """移除已持久化定义; 未命中抛 ProviderNotFoundError; 内建默认定义
        不可移除 (抛 ProviderRegistryError); 发 provider.removed。"""
        definition = self.get(provider_id)
        if definition is None:
            raise ProviderNotFoundError(f"provider not found: {provider_id}")
        if not self._store.remove_definition(provider_id):
            raise ProviderRegistryError(
                f"cannot remove builtin provider definition: {provider_id} "
                f"(default definitions are read-only)"
            )
        ev = record_provider_removed(self._logger, definition=definition)
        return definition, ev

    def set_default(self, provider_id: str) -> tuple[ProviderDefinition, Event | None]:
        """持久化默认 Provider; 未注册抛 ProviderNotFoundError; 发
        provider.selected (stage=default)。"""
        definition = self.get(provider_id)
        if definition is None:
            raise ProviderNotFoundError(f"provider not found: {provider_id}")
        self._store.save_default(provider_id)
        ev = record_provider_selected(
            self._logger, provider_id=provider_id,
            model=(definition.models[0] if definition.models else None),
            default=True, stage="default", action="set default provider",
        )
        return definition, ev

    # ------------------------------------------------------------------ 读

    def get(self, provider_id: str) -> ProviderDefinition | None:
        """按 id 取定义 (合并视图); 不存在返回 None。"""
        return self._merged().get(provider_id)

    def list(
        self,
        *,
        type: str | None = None,
        status: ProviderStatus | str | None = None,
    ) -> list[ProviderDefinition]:
        """全部定义 (合并视图, 按 id 排序), 可选按 type/status 过滤。"""
        want = ProviderStatus.parse(status) if isinstance(status, str) else status
        definitions = [
            d for d in self._merged().values()
            if (type is None or d.type == type)
            and (want is None or d.status is want)
        ]
        return sorted(definitions, key=lambda d: d.id)

    def find_by_capability(self, capability: str) -> list[ProviderDefinition]:
        """按能力标签检索 (大小写不敏感, 子串不含); 按 id 排序。"""
        want = capability.strip().lower()
        if not want:
            return []
        return sorted(
            (
                d for d in self._merged().values()
                if any(c.lower() == want for c in d.capabilities)
            ),
            key=lambda d: d.id,
        )

    def count(self) -> int:
        """目录视图定义总数。"""
        return len(self._merged())

    def ids(self) -> list[str]:
        """目录视图定义 id 列表 (排序)。"""
        return sorted(self._merged())

    # ------------------------------------------------------------------ 默认选择

    def default(self) -> ProviderDefinition | None:
        """默认 Provider 定义; 未设置/默认引用已移除 → None (自动失效, 不抛错)。"""
        provider_id = self._store.get_default()
        if provider_id is None:
            return None
        return self.get(provider_id)

    def resolve(self, provider_id: str | None = None) -> str | None:
        """解析执行应使用的 provider id: 显式 id (须已注册) → 默认 → None。

        派发层 (Phase 8c) 启动 Provider 调用前调用; 请求未指定 provider 时返回
        默认 id; 未设置默认 → None (调用方自行兜底, 同 resolve_runtime_id 语义)。
        """
        if provider_id is not None:
            if self.get(provider_id) is None:
                raise ProviderNotFoundError(f"provider not found: {provider_id}")
            return provider_id
        default = self.default()
        return default.id if default is not None else None
