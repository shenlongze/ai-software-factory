"""runtime/registry.py — RuntimeRegistry: register/get/list/remove (AVAILABLE/DISABLED)。

设计依据:
- phase4b1-status.md: RuntimeRegistry (register/get/list/remove, 状态 AVAILABLE/DISABLED)。
- 参照 agents/registry.py 模式: 写方法返回 `(对象, Event | None)`; Event 经 EventLogger
  (不直接写 EventStore); logger 可缺省。存储先落地、事件后发。
- resolve_runtime_id: 派发辅助 — 显式 id (须已注册) → 首个 AVAILABLE → None
  (ADR-0006 决策 6: 辅助放注册表而非 Adapter, 因需访问注册状态)。
"""

from __future__ import annotations

from typing import Any

from events.logger import EventLogger
from events.models import Event, EventType

from .models import RuntimeInfo, RuntimeStatus
from .store import RuntimeStore


class RuntimeRegistryError(Exception):
    """RuntimeRegistry 基础异常。"""


class RuntimeExistsError(RuntimeRegistryError):
    """Runtime 已存在 (register 冲突)。"""


class RuntimeNotFoundError(RuntimeRegistryError):
    """Runtime 不存在。"""


class RuntimeRegistry:
    """Runtime 注册表: RuntimeStore 持久化 + 事件 (runtime.registered/removed/viewed)。"""

    SOURCE = "runtime_registry"  # event-model §2.1 source 取值

    def __init__(self, store: RuntimeStore, logger: EventLogger | None = None):
        self._store = store
        self._logger = logger

    @property
    def store(self) -> RuntimeStore:
        return self._store

    # ------------------------------------------------------------------ 写

    def register(self, runtime: RuntimeInfo) -> tuple[RuntimeInfo, Event | None]:
        """注册新 Runtime; id 冲突抛 RuntimeExistsError; 发 runtime.registered。"""
        if self.get(runtime.id) is not None:
            raise RuntimeExistsError(f"runtime already exists: {runtime.id}")
        self._store.save_runtime(runtime)
        ev = self._emit(
            EventType.RUNTIME_REGISTERED, runtime, "register runtime",
            {
                "name": runtime.name,
                "type": runtime.type,
                "status": runtime.status.value,
                "description": runtime.description,
            },
        )
        return runtime, ev

    def remove(self, runtime_id: str) -> tuple[RuntimeInfo, Event | None]:
        """移除 Runtime; 不存在抛 RuntimeNotFoundError; 发 runtime.removed。"""
        runtime = self.get(runtime_id)
        if runtime is None:
            raise RuntimeNotFoundError(f"runtime not found: {runtime_id}")
        self._store.remove_runtime(runtime_id)
        ev = self._emit(
            EventType.RUNTIME_REMOVED, runtime, "remove runtime",
            {
                "name": runtime.name,
                "type": runtime.type,
                "status": runtime.status.value,
            },
        )
        return runtime, ev

    def _emit(
        self, type_: EventType, runtime: RuntimeInfo, action: str, payload: dict[str, Any],
    ) -> Event | None:
        if self._logger is None:
            return None
        return self._logger.record(
            type_, source=self.SOURCE, stage=runtime.status.value.lower(),
            action=action, result="OK", payload=payload,
        )

    # ------------------------------------------------------------------ 读

    def get(self, runtime_id: str) -> RuntimeInfo | None:
        """按 id 取 Runtime; 不存在返回 None。"""
        return self._store.get_runtime(runtime_id)

    def list(self, *, status: RuntimeStatus | str | None = None) -> list[RuntimeInfo]:
        """全部 Runtime (按 id 排序), 可选按状态过滤。"""
        want = RuntimeStatus.parse(status) if isinstance(status, str) else status
        runtimes = [
            r for r in self._store.list_runtimes()
            if want is None or r.status is want
        ]
        return sorted(runtimes, key=lambda r: r.id)

    def count(self) -> int:
        return len(self._store.runtime_ids())

    def ids(self) -> list[str]:
        """现有 Runtime id 列表 (排序)。"""
        return self._store.runtime_ids()

    def next_id(self, prefix: str = "R-") -> str:
        """自动编号: 取现有最大数字后缀 +1 (如 R-001 → R-002)。"""
        return self._store.next_runtime_id(prefix)

    # ------------------------------------------------------------------ 派发辅助

    def resolve_runtime_id(self, runtime_id: str | None = None) -> str | None:
        """解析执行应使用的 runtime id: 显式 id (须已注册) → 首个 AVAILABLE → None。

        派发层 (Phase 4B-2) 启动执行前调用: 请求未指定 runtime 时自动选一个可用运行时;
        没有任何可用 Runtime 时返回 None (执行留在 PENDING, 等待后续注册/人工处理)。
        """
        if runtime_id is not None:
            if self.get(runtime_id) is None:
                raise RuntimeNotFoundError(f"runtime not found: {runtime_id}")
            return runtime_id
        for runtime in self.list(status=RuntimeStatus.AVAILABLE):
            return runtime.id
        return None
