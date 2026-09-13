"""execution/dispatcher.py — ExecutionDispatcher: runtime 解析 → Adapter → execute()。

设计依据:
- phase4b2-status.md: ExecutionDispatcher — resolve runtime_id (RuntimeRegistry) →
  找到 RuntimeAdapter → 调 execute()。
- 职责边界 (ADR-0007 决策 1): Dispatcher 只负责\"派发\" (解析 runtime + 调 Adapter),
  不做生命周期/持久化/事件 — 那些归 ExecutionRunner。无可用 Runtime / 无 Adapter /
  契约违反都在此层以异常表达, 由 Runner 或 CLI 决定处置。
- 解析语义复用 RuntimeRegistry.resolve_runtime_id (ADR-0006 决策 6): 显式 id
  (须已注册, 否则 RuntimeNotFoundError) → 首个 AVAILABLE → None。
  无可用 Runtime → NoAvailableRuntimeError (执行留在 PENDING, 等待注册/人工处理)。
- 实现映射与身份注册解耦: RuntimeInfo 在 registry, Adapter 实现在本类 adapters 映射
  (register_adapter); dispatch 时按解析出的 runtime_id 找实现, 找不到即配置缺口
  → RuntimeAdapterNotFoundError (注册了身份但没装实现)。
- 结果契约校验: Adapter 返回的 ExecutionResult.request_id 必须等于请求 id
  (results 节以 request_id 为键, 错绑会导致结果无法关联), 违反抛 ExecutionDispatchError。
"""

from __future__ import annotations

from typing import Mapping

from runtime.adapter import RuntimeAdapter
from runtime.models import ExecutionRequest, ExecutionResult
from runtime.registry import RuntimeRegistry


class ExecutionDispatcherError(Exception):
    """ExecutionDispatcher 基础异常。"""


class NoAvailableRuntimeError(ExecutionDispatcherError):
    """无可用 Runtime: 请求未显式指定且 AVAILABLE 列表为空。"""


class RuntimeAdapterNotFoundError(ExecutionDispatcherError):
    """解析到 runtime 但无对应 Adapter 实现 (身份已注册, 实现缺失)。"""


class ExecutionDispatchError(ExecutionDispatcherError):
    """派发契约违反 (如 Adapter 返回结果未绑定本请求)。"""


class ExecutionDispatcher:
    """执行派发器: RuntimeRegistry 解析 runtime_id → 找 Adapter → 调 execute()。"""

    def __init__(
        self,
        registry: RuntimeRegistry,
        adapters: Mapping[str, RuntimeAdapter] | None = None,
    ):
        self._registry = registry
        self._adapters = dict(adapters or {})

    @property
    def registry(self) -> RuntimeRegistry:
        return self._registry

    @property
    def adapters(self) -> dict[str, RuntimeAdapter]:
        """已登记 Adapter 实现映射 (副本, 只读语义)。"""
        return dict(self._adapters)

    def register_adapter(self, runtime_id: str, adapter: RuntimeAdapter) -> None:
        """登记 runtime_id → Adapter 实现 (幂等覆盖; 不要求 registry 已有身份)。"""
        self._adapters[runtime_id] = adapter

    def get_adapter(self, runtime_id: str) -> RuntimeAdapter | None:
        """按 runtime_id 取 Adapter; 未登记返回 None。"""
        return self._adapters.get(runtime_id)

    def resolve_runtime_id(self, request: ExecutionRequest) -> str:
        """解析本次执行应使用的 runtime id: 显式 id → 首个 AVAILABLE → 报错。

        直接委托 RuntimeRegistry.resolve_runtime_id (ADR-0006 决策 6): 显式 id
        须已注册 (未注册抛 RuntimeNotFoundError); 为空时自动选首个 AVAILABLE;
        两者都拿不到 → NoAvailableRuntimeError (执行留在 PENDING)。
        """
        runtime_id = self._registry.resolve_runtime_id(request.runtime_id)
        if runtime_id is None:
            raise NoAvailableRuntimeError(
                f"no available runtime for execution {request.id}; "
                f"register a runtime first (factory runtime add)"
            )
        return runtime_id

    def dispatch(self, request: ExecutionRequest) -> ExecutionResult:
        """解析 runtime_id → 找 Adapter → execute() → 校验结果绑定。

        Raises:
            RuntimeNotFoundError: 显式 runtime_id 未注册
            NoAvailableRuntimeError: 无可用 Runtime
            RuntimeAdapterNotFoundError: 解析到 runtime 但无实现
            ExecutionDispatchError: Adapter 返回结果未绑定本请求 (契约违反)
        """
        runtime_id = self.resolve_runtime_id(request)
        adapter = self.get_adapter(runtime_id)
        if adapter is None:
            raise RuntimeAdapterNotFoundError(
                f"no adapter implementation for runtime: {runtime_id} "
                f"(execution {request.id})"
            )
        result = adapter.execute(request)
        if result.request_id != request.id:
            raise ExecutionDispatchError(
                f"adapter {runtime_id} returned result for request "
                f"{result.request_id!r}, expected {request.id!r}"
            )
        return result
