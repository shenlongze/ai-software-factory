"""test_provider_integration_8b1.py — Provider × Execution 集成层 (Phase 8B-1, ADR-0023)。

覆盖 providers/integration.py:
- carry_provider_input: provider_id 注入 input (新实例, 原请求不变, 其他键保留)
- provider_context_from_selection: ProviderSelection → ProviderContext (model 取
  定义首个模型; 无选择 → None)
- ProviderCarrierAdapter: 事件序 selected → execution.started → completed|failed;
  payload 含 execution_id/source; 委托异常 → failed 后原样抛出; logger None → 零事件
- wrap_adapters_with_provider: 全量包装返回新映射 (不改传入映射, delegate/context 保留)
"""

from __future__ import annotations

import pytest

from events.models import EventType
from runtime.adapter import RuntimeAdapter
from runtime.models import ExecutionRequest, ExecutionResult, ExecutionStatus

from providers.integration import (
    ProviderCarrierAdapter,
    ProviderContext,
    carry_provider_input,
    provider_context_from_selection,
    wrap_adapters_with_provider,
)
from providers.models import ProviderDefinition
from providers.selector import ProviderSelection

from providers_helpers import make_definition


def _request(**overrides) -> ExecutionRequest:
    data = dict(id="EX-001", task_id="T-001", input={"prompt": "hi"})
    data.update(overrides)
    return ExecutionRequest(**data)


class _FakeDelegate(RuntimeAdapter):
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


def _selection(provider: ProviderDefinition | None = None, source: str = "project"):
    return ProviderSelection(
        provider_id=provider.id if provider is not None else "openai",
        provider=provider,
        source=source,
    )


class TestCarryProviderInput:
    def test_injects_provider_id(self):
        carried = carry_provider_input(_request(), "hermes")
        assert carried.input["provider_id"] == "hermes"

    def test_preserves_existing_keys(self):
        carried = carry_provider_input(_request(), "hermes")
        assert carried.input["prompt"] == "hi"

    def test_returns_new_instance(self):
        original = _request()
        carried = carry_provider_input(original, "hermes")
        assert carried is not original
        assert "provider_id" not in original.input  # 原请求不变

    def test_empty_input_gets_provider_id(self):
        carried = carry_provider_input(_request(input={}), "hermes")
        assert carried.input == {"provider_id": "hermes"}

    def test_preserves_request_identity_fields(self):
        carried = carry_provider_input(
            _request(task_id="T-009", runtime_id="echo"), "hermes",
        )
        assert carried.id == "EX-001"
        assert carried.task_id == "T-009"
        assert carried.runtime_id == "echo"
        assert carried.status is ExecutionStatus.PENDING

    def test_overwrites_previous_provider_id(self):
        carried = carry_provider_input(_request(input={"provider_id": "old"}), "new")
        assert carried.input["provider_id"] == "new"


class TestProviderContextFromSelection:
    def test_none_selection_returns_none(self):
        assert provider_context_from_selection(None) is None

    def test_model_taken_from_definition_first(self):
        definition = make_definition("openai", models=["gpt-4o", "gpt-4o-mini"])
        ctx = provider_context_from_selection(_selection(definition, source="project"))
        assert ctx.provider_id == "openai"
        assert ctx.model == "gpt-4o"

    def test_source_passthrough(self):
        ctx = provider_context_from_selection(_selection(None, source="explicit"))
        assert ctx.source == "explicit"

    def test_selection_without_definition_model_none(self):
        ctx = provider_context_from_selection(_selection(None, source="default"))
        assert ctx.model is None

    def test_definition_without_models_model_none(self):
        definition = ProviderDefinition(
            id="openai", name="Provider openai", type="cloud",
            capabilities=["chat"], models=[], version="1.0.0",
        )
        ctx = provider_context_from_selection(_selection(definition))
        assert ctx.model is None

    def test_provider_id_passthrough(self):
        ctx = provider_context_from_selection(_selection(None))
        assert ctx.provider_id == "openai"


class TestProviderContext:
    def test_default_source_is_project(self):
        assert ProviderContext(provider_id="hermes").source == "project"

    def test_default_model_none(self):
        assert ProviderContext(provider_id="hermes").model is None

    def test_to_dict(self):
        ctx = ProviderContext(provider_id="hermes", model="m1", source="explicit")
        assert ctx.to_dict() == {
            "provider_id": "hermes", "model": "m1", "source": "explicit",
        }

    def test_frozen(self):
        ctx = ProviderContext(provider_id="hermes")
        with pytest.raises(Exception):
            ctx.provider_id = "other"  # type: ignore[misc]


class TestCarrierAdapterSuccess:
    def test_event_order_selected_started_completed(self, logger):
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes"), logger=logger,
        )
        adapter.execute(_request())
        types = [e.type.value for e in logger.store.query()]
        assert types == [
            "provider.selected", "provider.execution.started", "provider.execution.completed",
        ]

    def test_delegate_receives_carried_input(self):
        delegate = _FakeDelegate()
        adapter = ProviderCarrierAdapter(
            delegate, ProviderContext(provider_id="hermes"), logger=None,
        )
        adapter.execute(_request(input={"prompt": "hi"}))
        assert delegate.seen[0].input["provider_id"] == "hermes"
        assert delegate.seen[0].input["prompt"] == "hi"

    def test_result_passthrough(self):
        delegate = _FakeDelegate()
        adapter = ProviderCarrierAdapter(
            delegate, ProviderContext(provider_id="hermes"), logger=None,
        )
        result = adapter.execute(_request())
        assert result is delegate.result
        assert result.status is ExecutionStatus.SUCCESS

    def test_selected_payload_execution_id(self, logger):
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes"), logger=logger,
        )
        adapter.execute(_request(id="EX-777"))
        ev = logger.store.query()[0]
        assert ev.type is EventType.PROVIDER_SELECTED
        assert ev.payload["execution_id"] == "EX-777"
        assert ev.payload["provider_id"] == "hermes"

    def test_selected_payload_source_from_context(self, logger):
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes", source="project"),
            logger=logger,
        )
        adapter.execute(_request())
        ev = logger.store.query()[0]
        assert ev.payload["source"] == "project"

    def test_events_source_is_cli(self, logger):
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes"), logger=logger,
        )
        adapter.execute(_request())
        assert all(e.source == "cli" for e in logger.store.query())

    def test_model_in_selected_payload(self, logger):
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes", model="m1"), logger=logger,
        )
        adapter.execute(_request())
        assert logger.store.query()[0].payload["model"] == "m1"

    def test_all_events_carry_execution_id(self, logger):
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes"), logger=logger,
        )
        adapter.execute(_request(id="EX-555"))
        for ev in logger.store.query():
            assert ev.payload["execution_id"] == "EX-555"

    def test_completed_event_result_ok(self, logger):
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes"), logger=logger,
        )
        adapter.execute(_request())
        assert logger.store.query()[-1].result == "OK"


class TestCarrierAdapterFailure:
    def test_failed_result_event_order(self, logger):
        delegate = _FakeDelegate(result=ExecutionResult(
            id="EXR-1", request_id="EX-001", status=ExecutionStatus.FAILED, error="boom",
        ))
        adapter = ProviderCarrierAdapter(
            delegate, ProviderContext(provider_id="hermes"), logger=logger,
        )
        result = adapter.execute(_request())
        assert result.status is ExecutionStatus.FAILED
        types = [e.type.value for e in logger.store.query()]
        assert types == [
            "provider.selected", "provider.execution.started", "provider.execution.failed",
        ]

    def test_failed_payload_error_from_result(self, logger):
        delegate = _FakeDelegate(result=ExecutionResult(
            id="EXR-1", request_id="EX-001", status=ExecutionStatus.FAILED, error="boom",
        ))
        adapter = ProviderCarrierAdapter(
            delegate, ProviderContext(provider_id="hermes"), logger=logger,
        )
        adapter.execute(_request())
        ev = logger.store.query()[-1]
        assert ev.type is EventType.PROVIDER_EXECUTION_FAILED
        assert ev.payload["error"] == "boom"
        assert ev.payload["execution_id"] == "EX-001"

    def test_failed_payload_fallback_error(self, logger):
        """FAILED 结果无 error → 载波用稳定兜底文案。"""
        delegate = _FakeDelegate(result=ExecutionResult(
            id="EXR-1", request_id="EX-001", status=ExecutionStatus.FAILED,
        ))
        adapter = ProviderCarrierAdapter(
            delegate, ProviderContext(provider_id="hermes"), logger=logger,
        )
        adapter.execute(_request())
        assert "provider execution failed" in logger.store.query()[-1].payload["error"]

    def test_delegate_exception_reraised(self):
        delegate = _FakeDelegate(exc=RuntimeError("kaboom"))
        adapter = ProviderCarrierAdapter(
            delegate, ProviderContext(provider_id="hermes"), logger=None,
        )
        with pytest.raises(RuntimeError, match="kaboom"):
            adapter.execute(_request())

    def test_delegate_exception_emits_failed_then_reraise(self, logger):
        delegate = _FakeDelegate(exc=ValueError("bad input"))
        adapter = ProviderCarrierAdapter(
            delegate, ProviderContext(provider_id="hermes"), logger=logger,
        )
        with pytest.raises(ValueError):
            adapter.execute(_request())
        types = [e.type.value for e in logger.store.query()]
        assert types == [
            "provider.selected", "provider.execution.started", "provider.execution.failed",
        ]
        ev = logger.store.query()[-1]
        assert "ValueError" in ev.payload["error"]
        assert ev.payload["execution_id"] == "EX-001"


class TestCarrierAdapterNoLogger:
    def test_no_events_when_logger_none(self, logger):
        """logger=None → 零事件 (不写事件库)。"""
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes"), logger=None,
        )
        adapter.execute(_request())
        assert logger.store.count() == 0

    def test_input_injection_without_logger(self):
        delegate = _FakeDelegate()
        adapter = ProviderCarrierAdapter(
            delegate, ProviderContext(provider_id="hermes"), logger=None,
        )
        adapter.execute(_request())
        assert delegate.seen[0].input["provider_id"] == "hermes"

    def test_execute_works_without_logger(self):
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes"), logger=None,
        )
        result = adapter.execute(_request())
        assert result.status is ExecutionStatus.SUCCESS


class TestCarrierAdapterAccessors:
    def test_delegate_property(self):
        delegate = _FakeDelegate()
        adapter = ProviderCarrierAdapter(
            delegate, ProviderContext(provider_id="hermes"), logger=None,
        )
        assert adapter.delegate is delegate

    def test_context_property(self):
        ctx = ProviderContext(provider_id="hermes")
        adapter = ProviderCarrierAdapter(_FakeDelegate(), ctx, logger=None)
        assert adapter.context is ctx

    def test_selected_action_names_execution(self, logger):
        adapter = ProviderCarrierAdapter(
            _FakeDelegate(), ProviderContext(provider_id="hermes"), logger=logger,
        )
        adapter.execute(_request(id="EX-321"))
        assert "EX-321" in logger.store.query()[0].action


class TestWrapAdaptersWithProvider:
    def _builtins(self):
        from runtime.adapters import BUILTIN_ADAPTERS

        return dict(BUILTIN_ADAPTERS)

    def test_wraps_every_adapter(self):
        adapters = self._builtins()
        wrapped = wrap_adapters_with_provider(
            adapters, ProviderContext(provider_id="hermes"), logger=None,
        )
        assert set(wrapped) == set(adapters)
        assert all(
            isinstance(a, ProviderCarrierAdapter) for a in wrapped.values()
        )

    def test_returns_new_dict_original_unchanged(self):
        adapters = self._builtins()
        wrapped = wrap_adapters_with_provider(
            adapters, ProviderContext(provider_id="hermes"), logger=None,
        )
        assert wrapped is not adapters
        assert all(
            not isinstance(a, ProviderCarrierAdapter) for a in adapters.values()
        )

    def test_delegates_preserved(self):
        adapters = self._builtins()
        wrapped = wrap_adapters_with_provider(
            adapters, ProviderContext(provider_id="hermes"), logger=None,
        )
        for runtime_id, adapter in wrapped.items():
            assert adapter.delegate is adapters[runtime_id]

    def test_context_shared(self):
        ctx = ProviderContext(provider_id="hermes", source="project")
        wrapped = wrap_adapters_with_provider(
            self._builtins(), ctx, logger=None,
        )
        assert all(a.context is ctx for a in wrapped.values())

    def test_empty_mapping(self):
        assert wrap_adapters_with_provider({}, ProviderContext(provider_id="hermes")) == {}

    def test_wrapped_adapter_executes_with_injection(self):
        """载波包装后真实执行: echo 委托可见 provider_id 注入。"""
        from runtime.adapters import BUILTIN_ADAPTERS

        wrapped = wrap_adapters_with_provider(
            BUILTIN_ADAPTERS, ProviderContext(provider_id="hermes"), logger=None,
        )
        result = wrapped["echo"].execute(_request(input={"prompt": "hi"}))
        assert result.status is ExecutionStatus.SUCCESS
        assert result.output["echo"]["provider_id"] == "hermes"
