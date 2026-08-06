"""providers/integration.py — Provider × Execution 集成层 (Phase 8B-1, ADR-0023)。

设计依据:
- phase8b1-status.md §3/§4: 选择结果经 ExecutionRequest.input dict 携带
  provider_id (input 是 dict, 调用方构造, 不改模型 — HermesRuntimeAdapter 忽略
  未知键, 兼容); Orchestration 集成 = 装配时经 context 传递 (Phase 6E executor
  注入模式, 不破坏 workflow run --auto 既有行为)。
- ProviderCarrierAdapter = CLI 装配点的"执行上下文载波" (Executor 注入, 参照
  ADR-0020 决策 1 模式): 包装真实 RuntimeAdapter, 在派发时 (1) 把已选
  provider_id 注入 request.input (delegate 可见), (2) 经 EventLogger 发
  provider.* 执行审计事件 (selected → execution.started → completed|failed)。
  委托 adapter 原样执行 — Runtime/Provider 边界保持, 不复制任何执行逻辑。
- 事件序 (每次 execute): provider.selected (payload 含 execution_id/source) →
  provider.execution.started → (delegate) → provider.execution.completed|failed。
  provider.selected 由载波在每个 execution 派发点发出 (execution_id 恒可得),
  CLI 与 --auto 两路径统一, 无双发风险。
- 兼容性: 无 provider 选择 → 不构造载波 → 旧链路零变化 (无 provider 事件、
  input 零注入)。usage 无真实计量时不传 (payload 省略键, 同 Phase 8A 契约)。
- 边界: 本模块只做"上下文传递 + 审计", 不实现任何 Provider 智能调用
  (OpenAI/Claude Adapter 不在本阶段范围, phase8b1-status.md 冻结约束)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from runtime.adapter import RuntimeAdapter
from runtime.models import ExecutionRequest, ExecutionResult, ExecutionStatus

from .events import (
    record_provider_execution_completed,
    record_provider_execution_failed,
    record_provider_execution_started,
    record_provider_selected,
)
from .selector import ProviderSelection


@dataclass(frozen=True)
class ProviderContext:
    """一次已完成的 Provider 选择 (集成层上下文, 经 CLI 装配点传递)。"""

    provider_id: str
    model: str | None = None
    source: str = "project"  # explicit|project|agent|runtime|default

    def to_dict(self) -> dict[str, Any]:
        return {"provider_id": self.provider_id, "model": self.model, "source": self.source}


def provider_context_from_selection(
    selection: ProviderSelection | None,
) -> ProviderContext | None:
    """ProviderSelection → ProviderContext (model 取定义首个模型; 无选择 → None)。"""
    if selection is None:
        return None
    model = None
    if selection.provider is not None and selection.provider.models:
        model = selection.provider.models[0]
    return ProviderContext(
        provider_id=selection.provider_id, model=model, source=selection.source,
    )


def carry_provider_input(request: ExecutionRequest, provider_id: str) -> ExecutionRequest:
    """把 provider_id 注入 ExecutionRequest.input (不改模型, 新实例)。

    input 是 dict, 调用方构造 — 携带未知键对 Runtime Adapter 透明
    (HermesRuntimeAdapter 忽略未知键, phase8b1-status.md §3 兼容约束)。
    """
    return request.model_copy(update={"input": {**request.input, "provider_id": provider_id}})


class ProviderCarrierAdapter(RuntimeAdapter):
    """RuntimeAdapter 载波: 派发时注入 provider_id + 发 provider.* 执行审计事件。

    仅作执行上下文传递 (Executor 注入模式, Phase 6E): 不实现 Provider 智能调用,
    委托真实 adapter 原样执行; 事件经 EventLogger (source 缺省 "cli" — 由 CLI
    装配点构造, 与 cmd_provider_test 的 source 约定一致)。

    Args:
        delegate: 被包装的真实 RuntimeAdapter (如 hermes-runtime/echo)。
        context: 已完成的 Provider 选择 (provider_id/model/source)。
        logger: EventLogger | None (None → 零事件, 仅 input 注入)。
    """

    def __init__(
        self,
        delegate: RuntimeAdapter,
        context: ProviderContext,
        logger: Any | None = None,
    ):
        self._delegate = delegate
        self._context = context
        self._logger = logger

    @property
    def delegate(self) -> RuntimeAdapter:
        return self._delegate

    @property
    def context(self) -> ProviderContext:
        return self._context

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """执行: 注入 provider_id → 审计事件 → 委托执行 → 终态审计事件。

        事件序: provider.selected (execution_id/source) → provider.execution.started
        → (delegate) → provider.execution.completed|failed (execution_id)。
        委托异常 → provider.execution.failed 后原样抛出 (Runner 防御兜底转 FAILED)。
        """
        request = carry_provider_input(request, self._context.provider_id)
        provider_id = self._context.provider_id
        model = self._context.model
        execution_id = request.id
        record_provider_selected(
            self._logger, provider_id=provider_id, model=model,
            execution_id=execution_id, selection_source=self._context.source,
            source="cli", stage="selected",
            action=f"select provider for execution {execution_id}",
        )
        record_provider_execution_started(
            self._logger, provider_id=provider_id, model=model,
            execution_id=execution_id, source="cli",
        )
        try:
            result = self._delegate.execute(request)
        except Exception as exc:  # 委托异常 → 审计失败后原样抛出 (不吞异常)
            record_provider_execution_failed(
                self._logger, provider_id=provider_id, model=model,
                error=f"{type(exc).__name__}: {exc}",
                execution_id=execution_id, source="cli",
            )
            raise
        if result.status is ExecutionStatus.SUCCESS:
            record_provider_execution_completed(
                self._logger, provider_id=provider_id, model=model,
                execution_id=execution_id, source="cli",
            )
        else:
            record_provider_execution_failed(
                self._logger, provider_id=provider_id, model=model,
                error=result.error or f"provider execution failed: {execution_id}",
                execution_id=execution_id, source="cli",
            )
        return result


def wrap_adapters_with_provider(
    adapters: Mapping[str, RuntimeAdapter],
    context: ProviderContext,
    logger: Any | None = None,
) -> dict[str, RuntimeAdapter]:
    """包装全部内置 RuntimeAdapter 为 ProviderCarrierAdapter (装配点批量注入)。

    返回新 dict (不改传入映射); 无 provider 选择时调用方不应调用本函数
    (直接传 None → 旧链路, 零 provider 事件)。
    """
    return {
        runtime_id: ProviderCarrierAdapter(adapter, context, logger=logger)
        for runtime_id, adapter in dict(adapters).items()
    }
