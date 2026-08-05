"""runtimes/catalog.py — RuntimeCatalog: 能力目录 (register/get/list/remove/find_by_capability)。

设计依据:
- phase5a1-status.md: RuntimeCatalog CRUD + 默认定义 hermes/echo/mock (只描述不执行);
  事件 runtime.catalog.registered/removed/viewed (ADR-0014 决策 1)。
- 参照 runtime/registry.py 模式: 写方法返回 `(对象, Event | None)`; Event 经
  EventLogger (不直接写 EventStore); logger 可缺省; 存储先落地、事件后发。
- 三层边界 (ADR-0014 决策 2): Catalog=能力描述 (本类) / Registry=实例可用状态
  (RuntimeRegistry) / Runtime=执行器 (RuntimeAdapter) — 本类不触碰派发与执行。

读路径合并 (ADR-0014 决策 3): 默认定义 (definitions.py) 是内建基线, 与已持久化
定义合并成"目录视图" — get/list/find_by_capability/count/ids 都看合并视图;
已持久化定义按 id 覆盖默认值。写路径 (register/remove) 只作用于持久化层:
- register: id 在合并视图中已存在 (默认 id 保留 + 持久化重复) → RuntimeDefinitionExistsError;
  默认 id 不可覆盖注册 (内建定义只读, 见 ADR-0014 决策 4)。
- remove: 只删除持久化记录; 内建默认定义不可移除 (抛 RuntimeCatalogError)。
"""

from __future__ import annotations

from typing import Any

from events.logger import EventLogger
from events.models import Event, EventType

from .definitions import DEFAULT_DEFINITIONS
from .models import CatalogStatus, RuntimeDefinition
from .store import CatalogStore


class RuntimeCatalogError(Exception):
    """RuntimeCatalog 基础异常。"""


class RuntimeDefinitionExistsError(RuntimeCatalogError):
    """定义已存在 (register 冲突, 含默认定义 id 保留)。"""


class RuntimeDefinitionNotFoundError(RuntimeCatalogError):
    """定义不存在 (remove 未命中)。"""


class RuntimeCatalog:
    """Runtime 能力目录: CatalogStore 持久化 + 默认定义基线 + 事件 (runtime.catalog.*)。"""

    SOURCE = "runtime_catalog"  # event-model §2.1 source 取值

    def __init__(self, store: CatalogStore, logger: EventLogger | None = None):
        self._store = store
        self._logger = logger

    @property
    def store(self) -> CatalogStore:
        return self._store

    # ------------------------------------------------------------------ 合并视图

    def _merged(self) -> dict[str, RuntimeDefinition]:
        """目录视图: 默认定义基线 + 已持久化定义 (持久化按 id 覆盖)。"""
        merged = {d.id: d for d in DEFAULT_DEFINITIONS}
        for d in self._store.list_definitions():
            merged[d.id] = d
        return merged

    # ------------------------------------------------------------------ 写

    def register(self, definition: RuntimeDefinition) -> tuple[RuntimeDefinition, Event | None]:
        """注册新定义; id 冲突 (含默认定义保留) 抛 RuntimeDefinitionExistsError;
        发 runtime.catalog.registered。"""
        if self.get(definition.id) is not None:
            raise RuntimeDefinitionExistsError(
                f"runtime definition already exists: {definition.id}"
            )
        self._store.save_definition(definition)
        ev = self._emit(
            EventType.RUNTIME_CATALOG_REGISTERED, definition, "register runtime definition",
            {
                "name": definition.name,
                "type": definition.type,
                "version": definition.version,
                "status": definition.status.value,
                "capabilities": definition.capabilities,
                "description": definition.description,
            },
        )
        return definition, ev

    def remove(self, definition_id: str) -> tuple[RuntimeDefinition, Event | None]:
        """移除已持久化定义; 未命中抛 RuntimeDefinitionNotFoundError; 内建默认定义
        不可移除 (抛 RuntimeCatalogError); 发 runtime.catalog.removed。"""
        definition = self.get(definition_id)
        if definition is None:
            raise RuntimeDefinitionNotFoundError(
                f"runtime definition not found: {definition_id}"
            )
        if not self._store.remove_definition(definition_id):
            raise RuntimeCatalogError(
                f"cannot remove builtin runtime definition: {definition_id} "
                f"(default definitions are read-only)"
            )
        ev = self._emit(
            EventType.RUNTIME_CATALOG_REMOVED, definition, "remove runtime definition",
            {
                "name": definition.name,
                "type": definition.type,
                "version": definition.version,
                "status": definition.status.value,
            },
        )
        return definition, ev

    def _emit(
        self, type_: EventType, definition: RuntimeDefinition, action: str,
        payload: dict[str, Any],
    ) -> Event | None:
        if self._logger is None:
            return None
        return self._logger.record(
            type_, source=self.SOURCE, stage=definition.status.value.lower(),
            action=action, result="OK", payload=payload,
        )

    # ------------------------------------------------------------------ 读

    def get(self, definition_id: str) -> RuntimeDefinition | None:
        """按 id 取定义 (合并视图); 不存在返回 None。"""
        return self._merged().get(definition_id)

    def list(
        self,
        *,
        type: str | None = None,
        status: CatalogStatus | str | None = None,
    ) -> list[RuntimeDefinition]:
        """全部定义 (合并视图, 按 id 排序), 可选按 type/status 过滤。"""
        want = CatalogStatus.parse(status) if isinstance(status, str) else status
        definitions = [
            d for d in self._merged().values()
            if (type is None or d.type == type)
            and (want is None or d.status is want)
        ]
        return sorted(definitions, key=lambda d: d.id)

    def find_by_capability(self, capability: str) -> list[RuntimeDefinition]:
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
