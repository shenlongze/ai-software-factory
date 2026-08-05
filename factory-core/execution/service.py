"""execution/service.py — ExecutionService: 派发 + 执行 + 查询的统一入口 (薄门面)。

设计依据:
- phase4b2-status.md: ExecutionService (可选: 包装 dispatcher+runner+persistence 的统一入口)。
- KISS: 门面只做装配与委托 — Dispatcher (解析+调 Adapter) + Runner (生命周期+联动)
  + RuntimeStore (持久化) 的组合根; 业务逻辑全部留在下层, 本类不重复实现。
- status() 为只读查询 (不发事件; CLI 层另行发 execution.viewed, ADR-0002 铁律)。
"""

from __future__ import annotations

from typing import Mapping

from events.logger import EventLogger
from runtime.adapter import RuntimeAdapter
from runtime.models import ExecutionRequest, ExecutionResult
from runtime.registry import RuntimeRegistry
from runtime.store import RuntimeStore
from workflows.engine import WorkflowEngine

from .dispatcher import ExecutionDispatcher
from .runner import ExecutionRunOutcome, ExecutionRunner


class ExecutionService:
    """统一编排入口: Dispatcher + Runner + Store 的组合根。

    典型装配 (CLI): ExecutionService(store, RuntimeRegistry(store, logger),
    adapters=BUILTIN_ADAPTERS, logger=logger, workflow_engine=engine)。
    """

    def __init__(
        self,
        store: RuntimeStore,
        registry: RuntimeRegistry,
        adapters: Mapping[str, RuntimeAdapter] | None = None,
        logger: EventLogger | None = None,
        workflow_engine: WorkflowEngine | None = None,
    ):
        self._store = store
        self._dispatcher = ExecutionDispatcher(registry, adapters=adapters)
        self._runner = ExecutionRunner(
            store, self._dispatcher, logger=logger, workflow_engine=workflow_engine,
        )

    @property
    def store(self) -> RuntimeStore:
        return self._store

    @property
    def dispatcher(self) -> ExecutionDispatcher:
        return self._dispatcher

    @property
    def runner(self) -> ExecutionRunner:
        return self._runner

    # ------------------------------------------------------------------ 执行

    def run(self, execution_id: str) -> ExecutionRunOutcome:
        """执行一次 PENDING 执行请求 (委托 Runner 全生命周期)。"""
        return self._runner.run(execution_id)

    # ------------------------------------------------------------------ 查询

    def status(
        self, execution_id: str,
    ) -> tuple[ExecutionRequest | None, ExecutionResult | None]:
        """执行状态查询: (请求, 结果 | None); 请求不存在返回 (None, None)。

        只读, 不发事件 (CLI 层另行发 execution.viewed, ADR-0002 铁律)。
        """
        request = self._store.get_execution(execution_id)
        if request is None:
            return None, None
        return request, self._store.get_result(execution_id)

    # ------------------------------------------------------------------ 装配

    def register_adapter(self, runtime_id: str, adapter: RuntimeAdapter) -> None:
        """登记 runtime_id → Adapter 实现 (透传 Dispatcher)。"""
        self._dispatcher.register_adapter(runtime_id, adapter)
