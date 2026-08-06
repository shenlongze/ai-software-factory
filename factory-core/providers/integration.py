"""providers/integration.py — Provider × Execution 集成层 (Phase 8B-1/8B-3)。

设计依据:
- phase8b1-status.md §3/§4: 选择结果经 ExecutionRequest.input dict 携带
  provider_id (input 是 dict, 调用方构造, 不改模型 — HermesRuntimeAdapter 忽略
  未知键, 兼容); Orchestration 集成 = 装配时经 context 传递 (Phase 6E executor
  注入模式, 不破坏 workflow run --auto 既有行为)。
- ProviderCarrierAdapter = CLI 装配点的"执行上下文载波" (Executor 注入, 参照
  ADR-0020 决策 1 模式): 包装真实 RuntimeAdapter, 在派发时 (1) 把已选
  provider_id 注入 request.input (delegate 可见), (2) 经 EventLogger 发
  provider.* 执行审计事件 (selected → execution.started → completed|failed →
  usage.recorded)。委托 adapter 原样执行 — Runtime/Provider 边界保持,
  不复制任何执行逻辑。
- 事件序 (每次 execute): provider.selected (payload 含 execution_id/source) →
  provider.execution.started → (delegate) → provider.execution.completed|failed
  → provider.usage.recorded (终态后, Phase 8B-3, ADR-0025)。provider.selected
  由载波在每个 execution 派发点发出 (execution_id 恒可得), CLI 与 --auto 两
  路径统一, 无双发风险。
- Phase 8B-3 usage 自动记录 (ADR-0025, docs/provider-intelligence-model.md):
  执行计时 (time.monotonic) → ProviderUsage 构造 (execution_id/task_id/
  provider_id/model/estimated_cost/latency_ms/success) → UsageStore.record
  (持久化, 独立数据空间 usage.json) → provider.usage.recorded 事件。estimated_
  cost 由 CostModel 估算 (非真实计费); 失败调用也记录 (success=False + error,
  成功率聚合数据基础)。载波 usage 记录 = 构造参数缺省关 (opt-in): 无
  usage_store → 零落库零 usage 事件 (8B-1 单元语义保持, 破坏面隔离在 CLI
  装配点); 落库失败 → 跳过 BOTH 落库与事件 (事件是唯一事实源, 落库失败即
  事实未发生, 不撒谎)。无 logger → 零事件但照常落库 (若装配 store)。
- 兼容性: 无 provider 选择 → 不构造载波 → 旧链路零变化 (无 provider 事件、
  input 零注入)。usage 无真实计量时不传 (payload 省略键, 同 Phase 8A 契约)。
- 边界: 本模块只做"上下文传递 + 审计 + 使用记录", 不实现任何 Provider 智能
  调用 (OpenAI/Claude Adapter 不在本阶段范围, phase8b1-status.md 冻结约束)。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping

from runtime.adapter import RuntimeAdapter
from runtime.models import ExecutionRequest, ExecutionResult, ExecutionStatus

from .costs import ProviderCostModel, estimate_call_cost
from .events import (
    record_provider_execution_completed,
    record_provider_execution_failed,
    record_provider_execution_started,
    record_provider_selected,
    record_provider_usage,
)
from .selector import ProviderSelection
from .usage import ProviderUsage, UsageStore


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
    """RuntimeAdapter 载波: 派发时注入 provider_id + 发 provider.* 执行审计事件
    + usage 自动记录 (Phase 8B-3, ADR-0025)。

    仅作执行上下文传递 (Executor 注入模式, Phase 6E): 不实现 Provider 智能调用,
    委托真实 adapter 原样执行; 事件经 EventLogger (source 缺省 "cli" — 由 CLI
    装配点构造, 与 cmd_provider_test 的 source 约定一致)。

    Args:
        delegate: 被包装的真实 RuntimeAdapter (如 hermes-runtime/echo)。
        context: 已完成的 Provider 选择 (provider_id/model/source)。
        logger: EventLogger | None (None → 零事件, 仅 input 注入 + 落库)。
        usage_store: UsageStore | None — usage 自动记录落库 (独立数据空间
            usage.json); None → 零落库零 usage 事件 (构造参数缺省关 opt-in,
            8B-1 单元语义保持 — 只有 CLI 装配点传 usage_store 才记录)。
        cost_model: ProviderCostModel | None — estimated_cost 估算 (非真实
            计费); None → estimated_cost=0.0 (无成本模型不臆造定价)。
    """

    def __init__(
        self,
        delegate: RuntimeAdapter,
        context: ProviderContext,
        logger: Any | None = None,
        usage_store: UsageStore | None = None,
        cost_model: ProviderCostModel | None = None,
    ):
        self._delegate = delegate
        self._context = context
        self._logger = logger
        self._usage_store = usage_store
        self._cost_model = cost_model

    @property
    def delegate(self) -> RuntimeAdapter:
        return self._delegate

    @property
    def context(self) -> ProviderContext:
        return self._context

    @property
    def usage_store(self) -> UsageStore | None:
        return self._usage_store

    @property
    def cost_model(self) -> ProviderCostModel | None:
        return self._cost_model

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """执行: 注入 provider_id → 审计事件 → 委托执行 → 终态审计 → usage 记录。

        事件序: provider.selected (execution_id/source) → provider.execution.started
        → (delegate) → provider.execution.completed|failed → provider.usage.recorded
        (终态后, Phase 8B-3 — usage 记录是执行经验闭环的数据基础)。
        委托异常 → provider.execution.failed + usage (success=False) 后原样抛出
        (Runner 防御兜底转 FAILED)。
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
        started = time.monotonic()
        try:
            result = self._delegate.execute(request)
        except Exception as exc:  # 委托异常 → 审计失败 + usage 后原样抛出 (不吞异常)
            error = f"{type(exc).__name__}: {exc}"
            record_provider_execution_failed(
                self._logger, provider_id=provider_id, model=model,
                error=error, execution_id=execution_id, source="cli",
            )
            self._record_usage(request, success=False, error=error, started=started)
            raise
        elapsed_ms = _elapsed_ms(started)
        if result.status is ExecutionStatus.SUCCESS:
            record_provider_execution_completed(
                self._logger, provider_id=provider_id, model=model,
                execution_id=execution_id, source="cli",
            )
            self._record_usage(request, success=True, error=None, started=started)
        else:
            error = result.error or f"provider execution failed: {execution_id}"
            record_provider_execution_failed(
                self._logger, provider_id=provider_id, model=model,
                error=error, execution_id=execution_id, source="cli",
            )
            self._record_usage(request, success=False, error=error, started=started)
        return result

    # ------------------------------------------------------------------ usage 自动记录 (Phase 8B-3)

    def _record_usage(
        self,
        request: ExecutionRequest,
        *,
        success: bool,
        error: str | None,
        started: float,
    ) -> ProviderUsage | None:
        """执行后构造 ProviderUsage → UsageStore.record → provider.usage.recorded。

        - 载波 usage 记录 = 构造参数缺省关 (opt-in): 无 usage_store → None
          (零落库零事件 — 8B-1 单元测试保持绿, 破坏面隔离在 CLI 装配点)。
        - 关联字段: execution_id/task_id 取自 ExecutionRequest (执行经验追溯);
          provider_id/model 取自选择上下文; latency_ms = 委托执行计时;
          estimated_cost = CostModel 估算 (非真实计费, 无模型 → 0.0)。
        - 失败也记录 (success=False + error) — 成功率聚合的数据基础。
        - 落库失败安全: usage_store.record 抛异常 → 跳过 BOTH 落库与事件
          (事件是唯一事实源: 落库失败即事实未发生, 不发\"声称已落库\"的假
          事件), 返回 None — 执行结果原样返回, 集成层永不因 usage 失败
          破坏 run 链路。
        - 无 logger → 零事件 (record_* 辅助对 None logger 返回 None)。
        """
        if self._usage_store is None:
            return None  # opt-in 缺省关: 无 usage_store → 零落库零 usage 事件
        usage = ProviderUsage(
            provider_id=self._context.provider_id,
            model=self._context.model,
            execution_id=request.id,
            task_id=request.task_id,
            estimated_cost=(
                estimate_call_cost(self._cost_model) or 0.0
                if self._cost_model is not None else 0.0
            ),
            latency_ms=_elapsed_ms(started),
            success=success,
            error=error,
        )
        try:
            self._usage_store.record(usage)
        except Exception:
            return None  # 落库失败 → 跳过 BOTH 落库与事件 (不撒谎, 不破坏链路)
        record_provider_usage(self._logger, usage=usage, source="cli")
        return usage


def _elapsed_ms(started: float) -> int:
    """委托执行时长 ms (time.monotonic 计时, 非负)。"""
    return max(0, int((time.monotonic() - started) * 1000))


def wrap_adapters_with_provider(
    adapters: Mapping[str, RuntimeAdapter],
    context: ProviderContext,
    logger: Any | None = None,
    usage_store: UsageStore | None = None,
    cost_models: Mapping[str, ProviderCostModel] | None = None,
) -> dict[str, RuntimeAdapter]:
    """包装全部内置 RuntimeAdapter 为 ProviderCarrierAdapter (装配点批量注入)。

    返回新 dict (不改传入映射); 无 provider 选择时调用方不应调用本函数
    (直接传 None → 旧链路, 零 provider 事件)。
    Phase 8B-3 (ADR-0025): usage_store 装配时每次执行自动落库 usage 记录;
    cost_models 提供 provider_id → 成本模型 (estimated_cost 估算, 非真实计费)。
    """
    cost_models = dict(cost_models or {})
    return {
        runtime_id: ProviderCarrierAdapter(
            adapter, context, logger=logger,
            usage_store=usage_store,
            cost_model=cost_models.get(context.provider_id),
        )
        for runtime_id, adapter in dict(adapters).items()
    }
