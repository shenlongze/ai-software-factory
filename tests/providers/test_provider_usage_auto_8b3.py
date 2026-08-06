"""test_provider_usage_auto_8b3.py — Provider Usage 自动记录 (Phase 8B-3, ADR-0025)。

覆盖 providers/integration.py ProviderCarrierAdapter usage 自动记录:
- 成功/失败/委托异常路径: 执行后落库 usage.json + provider.usage.recorded 事件
- 关联字段: execution_id/task_id/provider_id/model/estimated_cost/latency_ms/success
- opt-in 缺省关: 无 usage_store → 零落库零 usage 事件 (8B-1 单元语义保持)
- 落库失败安全: record 抛异常 → 跳过 BOTH 落库与事件, 执行结果不受影响
- cost_model 估算 estimated_cost (非真实计费); wrap_adapters_with_provider
  批量注入 usage_store + cost_models
"""

from __future__ import annotations

from pathlib import Path

import pytest

from events.models import EventType
from runtime.models import ExecutionRequest, ExecutionResult, ExecutionStatus

from providers.costs import ProviderCostModel
from providers.integration import (
    ProviderCarrierAdapter,
    ProviderContext,
    wrap_adapters_with_provider,
)
from providers.usage import ProviderUsage, UsageStore

from providers_helpers import make_definition  # noqa: F401

# ------------------------------------------------------------------ 数据构造


def _request(**overrides) -> ExecutionRequest:
    data = dict(id="EX-001", task_id="T-001", input={"prompt": "hi"})
    data.update(overrides)
    return ExecutionRequest(**data)


class _FakeDelegate:
    """可控委托: 记录收到请求, 按设定返回结果或抛异常。"""

    def __init__(self, result: ExecutionResult | None = None, exc: Exception | None = None):
        self.result = result or ExecutionResult(
            id="EXR-001", request_id="EX-001", status=ExecutionStatus.SUCCESS,
            output={"echo": "ok"},
        )
        self.exc = exc
        self.seen: list[ExecutionRequest] = []

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.seen.append(request)
        if self.exc is not None:
            raise self.exc
        return self.result


def _token_cost_model(provider_id: str = "openai") -> ProviderCostModel:
    return ProviderCostModel(
        provider_id=provider_id, mode="token",
        pricing={"input": 10.0, "output": 20.0}, currency="USD",
    )


def _types(logger) -> list[str]:
    return [e.type.value for e in logger.store.query()]


class TestUsageRecordedOnSuccess:
    def test_success_run_persists_record(self, providers_dir: Path, logger):
        store = UsageStore(providers_dir)
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes"),
            logger=logger, usage_store=store,
        )
        adapter.execute(_request())
        records = store.list()
        assert len(records) == 1
        assert records[0].provider_id == "hermes"
        assert records[0].success is True

    def test_record_association_fields(self, providers_dir: Path, logger):
        store = UsageStore(providers_dir)
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes", model="m1"),
            logger=logger, usage_store=store,
        )
        adapter.execute(_request(id="EX-777", task_id="T-042"))
        usage = store.list()[0]
        assert usage.execution_id == "EX-777"
        assert usage.task_id == "T-042"
        assert usage.model == "m1"

    def test_record_latency_and_cost_defaults(self, providers_dir: Path, logger):
        store = UsageStore(providers_dir)
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes"),
            logger=logger, usage_store=store,
        )
        adapter.execute(_request())
        usage = store.list()[0]
        assert usage.latency_ms >= 0
        assert usage.estimated_cost == 0.0  # 无成本模型 → 0.0 (不臆造定价)

    def test_record_has_uuid_id(self, providers_dir: Path, logger):
        store = UsageStore(providers_dir)
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes"),
            logger=logger, usage_store=store,
        )
        adapter.execute(_request())
        usage = store.list()[0]
        assert len(usage.id) == 32
        assert all(c in "0123456789abcdef" for c in usage.id)

    def test_usage_json_file_location(self, providers_dir: Path, logger):
        store = UsageStore(providers_dir)
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes"),
            logger=logger, usage_store=store,
        )
        adapter.execute(_request())
        assert (providers_dir / "usage.json").exists()
        assert store.count() == 1

    def test_usage_recorded_event_after_completed(self, providers_dir: Path, logger):
        store = UsageStore(providers_dir)
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes"),
            logger=logger, usage_store=store,
        )
        adapter.execute(_request())
        assert _types(logger) == [
            "provider.selected", "provider.execution.started",
            "provider.execution.completed", "provider.usage.recorded",
        ]

    def test_usage_recorded_payload(self, providers_dir: Path, logger):
        store = UsageStore(providers_dir)
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes"),
            logger=logger, usage_store=store,
        )
        adapter.execute(_request(id="EX-9", task_id="T-9"))
        ev = logger.store.query()[-1]
        assert ev.type is EventType.PROVIDER_USAGE_RECORDED
        assert ev.payload["provider_id"] == "hermes"
        assert ev.payload["execution_id"] == "EX-9"
        assert ev.payload["task_id"] == "T-9"
        assert ev.payload["success"] is True
        assert ev.payload["estimated_cost"] == 0.0

    def test_multiple_runs_accumulate_records(self, providers_dir: Path, logger):
        store = UsageStore(providers_dir)
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes"),
            logger=logger, usage_store=store,
        )
        for i in range(3):
            adapter.execute(_request(id=f"EX-{i}"))
        assert store.count() == 3
        assert len([e for e in logger.store.query()
                    if e.type is EventType.PROVIDER_USAGE_RECORDED]) == 3


class TestUsageRecordedOnFailure:
    def test_failed_result_records_success_false(self, providers_dir: Path, logger):
        store = UsageStore(providers_dir)
        delegate = _FakeDelegate(result=ExecutionResult(
            id="EXR-1", request_id="EX-001", status=ExecutionStatus.FAILED, error="boom",
        ))
        adapter = ProviderCarrierAdapter(
            delegate, ProviderContext(provider_id="hermes"),
            logger=logger, usage_store=store,
        )
        adapter.execute(_request())
        usage = store.list()[0]
        assert usage.success is False
        assert usage.error == "boom"

    def test_failed_result_usage_event_after_failed(self, providers_dir: Path, logger):
        store = UsageStore(providers_dir)
        delegate = _FakeDelegate(result=ExecutionResult(
            id="EXR-1", request_id="EX-001", status=ExecutionStatus.FAILED, error="boom",
        ))
        adapter = ProviderCarrierAdapter(
            delegate, ProviderContext(provider_id="hermes"),
            logger=logger, usage_store=store,
        )
        adapter.execute(_request())
        assert _types(logger) == [
            "provider.selected", "provider.execution.started",
            "provider.execution.failed", "provider.usage.recorded",
        ]
        assert logger.store.query()[-1].payload["success"] is False

    def test_delegate_exception_records_then_reraise(self, providers_dir: Path, logger):
        store = UsageStore(providers_dir)
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(exc=ValueError("bad")), ProviderContext(provider_id="hermes"),
            logger=logger, usage_store=store,
        )
        with pytest.raises(ValueError):
            adapter.execute(_request())
        usage = store.list()[0]
        assert usage.success is False
        assert "ValueError" in usage.error
        assert _types(logger)[-1] == "provider.usage.recorded"


class TestUsageOptInDefaultOff:
    def test_no_store_no_usage_event_success(self, logger):
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes"), logger=logger,
        )
        adapter.execute(_request())
        assert _types(logger) == [
            "provider.selected", "provider.execution.started",
            "provider.execution.completed",
        ]

    def test_no_store_no_usage_event_failed(self, logger):
        delegate = _FakeDelegate(result=ExecutionResult(
            id="EXR-1", request_id="EX-001", status=ExecutionStatus.FAILED, error="x",
        ))
        adapter = ProviderCarrierAdapter(
            delegate, ProviderContext(provider_id="hermes"), logger=logger,
        )
        adapter.execute(_request())
        assert _types(logger) == [
            "provider.selected", "provider.execution.started",
            "provider.execution.failed",
        ]

    def test_no_store_no_usage_file_created(self, providers_dir: Path, logger):
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes"), logger=logger,
        )
        adapter.execute(_request())
        assert not (providers_dir / "usage.json").exists()


class TestUsageCostModel:
    def test_estimated_cost_from_token_model(self, providers_dir: Path, logger):
        store = UsageStore(providers_dir)
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="openai"),
            logger=logger, usage_store=store, cost_model=_token_cost_model(),
        )
        adapter.execute(_request())
        # ESTIMATED_TOKENS 1000 in / 500 out @ $10/$20 per 1K = 10 + 10 = 20.0
        assert store.list()[0].estimated_cost == 20.0

    def test_estimated_cost_zero_for_free_model(self, providers_dir: Path, logger):
        store = UsageStore(providers_dir)
        free = ProviderCostModel(provider_id="hermes", mode="free", pricing={}, free=True)
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes"),
            logger=logger, usage_store=store, cost_model=free,
        )
        adapter.execute(_request())
        assert store.list()[0].estimated_cost == 0.0


class TestUsageFailSafe:
    def test_record_exception_skips_both_store_and_event(self, providers_dir: Path, logger):
        store = UsageStore(providers_dir)
        original_record = store.record

        def boom(usage: ProviderUsage):
            raise RuntimeError("disk full")

        store.record = boom  # type: ignore[method-assign]
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes"),
            logger=logger, usage_store=store,
        )
        result = adapter.execute(_request())  # 不抛, 链路不破坏
        assert result.status is ExecutionStatus.SUCCESS
        # 不发"声称已落库"的假事件: usage.recorded 缺失
        assert _types(logger) == [
            "provider.selected", "provider.execution.started",
            "provider.execution.completed",
        ]
        store.record = original_record  # type: ignore[method-assign]
        assert store.count() == 0  # 落库确实没发生

    def test_record_exception_failure_path_still_returns(self, providers_dir: Path, logger):
        store = UsageStore(providers_dir)

        def boom(usage: ProviderUsage):
            raise RuntimeError("disk full")

        store.record = boom  # type: ignore[method-assign]
        delegate = _FakeDelegate(result=ExecutionResult(
            id="EXR-1", request_id="EX-001", status=ExecutionStatus.FAILED, error="x",
        ))
        adapter = ProviderCarrierAdapter(
            delegate, ProviderContext(provider_id="hermes"),
            logger=logger, usage_store=store,
        )
        result = adapter.execute(_request())
        assert result.status is ExecutionStatus.FAILED
        assert _types(logger)[-1] == "provider.execution.failed"


class TestWrapWithUsage:
    def test_wrap_injects_store_and_cost_models(self, providers_dir: Path, logger):
        store = UsageStore(providers_dir)
        adapters = {
            "echo": _FakeDelegate(),
            "mock": _FakeDelegate(),
        }
        wrapped = wrap_adapters_with_provider(
            adapters, ProviderContext(provider_id="openai"), logger=logger,
            usage_store=store,
            cost_models={"openai": _token_cost_model()},
        )
        wrapped["echo"].execute(_request())
        wrapped["mock"].execute(_request())
        assert store.count() == 2
        assert all(u.provider_id == "openai" for u in store.list())
        assert all(u.estimated_cost == 20.0 for u in store.list())

    def test_wrap_without_cost_models_cost_zero(self, providers_dir: Path, logger):
        store = UsageStore(providers_dir)
        wrapped = wrap_adapters_with_provider(
            {"echo": _FakeDelegate()}, ProviderContext(provider_id="hermes"),
            logger=logger, usage_store=store,
        )
        wrapped["echo"].execute(_request())
        assert store.list()[0].estimated_cost == 0.0

    def test_wrap_returns_new_mapping(self, providers_dir: Path, logger):
        store = UsageStore(providers_dir)
        adapters = {"echo": _FakeDelegate()}
        wrapped = wrap_adapters_with_provider(
            adapters, ProviderContext(provider_id="hermes"),
            logger=logger, usage_store=store,
        )
        assert wrapped is not adapters
        assert wrapped["echo"] is not adapters["echo"]
        assert wrapped["echo"].delegate is adapters["echo"]  # 载波保留原委托

    def test_wrap_preserves_runtime_ids(self, providers_dir: Path, logger):
        store = UsageStore(providers_dir)
        wrapped = wrap_adapters_with_provider(
            {"echo": _FakeDelegate(), "mock": _FakeDelegate()},
            ProviderContext(provider_id="hermes"), logger=logger, usage_store=store,
        )
        assert set(wrapped) == {"echo", "mock"}
