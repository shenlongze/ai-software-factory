"""test_execution_dispatcher.py — ExecutionDispatcher: runtime 解析 → Adapter → execute。"""

from __future__ import annotations

import pytest

from execution.dispatcher import (
    ExecutionDispatchError,
    ExecutionDispatcher,
    NoAvailableRuntimeError,
    RuntimeAdapterNotFoundError,
)
from runtime.adapter import RuntimeAdapter
from runtime.models import ExecutionRequest, ExecutionResult, ExecutionStatus, RuntimeStatus

from runtime_helpers import make_request, make_runtime


class _FixedAdapter(RuntimeAdapter):
    """测试 stub: 固定返回 SUCCESS 结果 (可选绑定其他请求模拟契约违反)。"""

    def __init__(self, request_id: str | None = None):
        self._request_id = request_id
        self.calls: list[ExecutionRequest] = []

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.calls.append(request)
        return ExecutionResult(
            id="EXR-1", request_id=self._request_id or request.id,
            output={"adapter": "fixed"},
        )


class _BoomAdapter(RuntimeAdapter):
    """执行时抛异常的 Adapter (Runner 防御路径用)。"""

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        raise RuntimeError("adapter exploded")


class TestResolveRuntimeId:
    def test_explicit_id(self, registry):
        registry.register(make_runtime("R-001"))
        d = ExecutionDispatcher(registry)
        assert d.resolve_runtime_id(make_request(runtime_id="R-001")) == "R-001"

    def test_explicit_unregistered_raises(self, registry):
        from runtime.registry import RuntimeNotFoundError

        d = ExecutionDispatcher(registry)
        with pytest.raises(RuntimeNotFoundError, match="runtime not found: R-999"):
            d.resolve_runtime_id(make_request(runtime_id="R-999"))

    def test_auto_picks_first_available(self, registry):
        registry.register(make_runtime("R-002"))
        registry.register(make_runtime("R-001"))
        d = ExecutionDispatcher(registry)
        # AVAILABLE 列表按 id 排序 → R-001
        assert d.resolve_runtime_id(make_request()) == "R-001"

    def test_auto_none_without_runtime(self, registry):
        d = ExecutionDispatcher(registry)
        with pytest.raises(NoAvailableRuntimeError):
            d.resolve_runtime_id(make_request())

    def test_auto_skips_disabled(self, registry):
        registry.register(make_runtime("R-001", status=RuntimeStatus.DISABLED))
        d = ExecutionDispatcher(registry)
        with pytest.raises(NoAvailableRuntimeError):
            d.resolve_runtime_id(make_request())

    def test_request_runtime_id_prefers_explicit(self, registry):
        registry.register(make_runtime("R-001"))
        registry.register(make_runtime("R-002"))
        d = ExecutionDispatcher(registry)
        assert d.resolve_runtime_id(make_request(runtime_id="R-002")) == "R-002"


class TestAdapterLookup:
    def test_adapters_empty_by_default(self, registry):
        assert ExecutionDispatcher(registry).adapters == {}

    def test_get_adapter_unknown(self, registry):
        d = ExecutionDispatcher(registry)
        assert d.get_adapter("nope") is None

    def test_register_and_get(self, registry):
        d = ExecutionDispatcher(registry, adapters={"echo": _FixedAdapter()})
        assert isinstance(d.get_adapter("echo"), _FixedAdapter)

    def test_register_overrides(self, registry):
        d = ExecutionDispatcher(registry)
        d.register_adapter("echo", _FixedAdapter())
        d.register_adapter("echo", _FixedAdapter())
        assert len(d.adapters) == 1

    def test_adapters_property_is_copy(self, registry):
        d = ExecutionDispatcher(registry, adapters={"echo": _FixedAdapter()})
        d.adapters["echo"] = _BoomAdapter()  # 外部修改副本不影响内部
        assert isinstance(d.get_adapter("echo"), _FixedAdapter)

    def test_registry_property(self, registry):
        d = ExecutionDispatcher(registry)
        assert d.registry is registry


class TestDispatch:
    def test_dispatch_calls_adapter_and_returns_result(self, registry):
        registry.register(make_runtime("R-001"))
        adapter = _FixedAdapter()
        d = ExecutionDispatcher(registry, adapters={"R-001": adapter})
        req = make_request()
        result = d.dispatch(req)
        assert result.status is ExecutionStatus.SUCCESS
        assert result.request_id == req.id
        assert adapter.calls == [req]

    def test_dispatch_auto_resolve(self, registry):
        registry.register(make_runtime("echo", type="mock"))
        d = ExecutionDispatcher(registry, adapters={"echo": _FixedAdapter()})
        result = d.dispatch(make_request())
        assert result.request_id == "EX-001"

    def test_dispatch_missing_adapter_raises(self, registry):
        """身份已注册但无实现 → RuntimeAdapterNotFoundError (配置缺口显式报错)。"""
        registry.register(make_runtime("R-001"))
        d = ExecutionDispatcher(registry)
        with pytest.raises(RuntimeAdapterNotFoundError, match="R-001"):
            d.dispatch(make_request())

    def test_dispatch_no_available_runtime_raises(self, registry):
        d = ExecutionDispatcher(registry, adapters={"echo": _FixedAdapter()})
        with pytest.raises(NoAvailableRuntimeError):
            d.dispatch(make_request())

    def test_dispatch_validates_request_binding(self, registry):
        """契约: 结果必须绑定本请求; 错绑 → ExecutionDispatchError。"""
        registry.register(make_runtime("R-001"))
        d = ExecutionDispatcher(registry, adapters={"R-001": _FixedAdapter(request_id="EX-999")})
        with pytest.raises(ExecutionDispatchError, match="EX-999"):
            d.dispatch(make_request("EX-001"))

    def test_dispatch_adapter_exception_propagates(self, registry):
        """Adapter 内部异常由 Runner 处置 — Dispatcher 原样透传。"""
        registry.register(make_runtime("R-001"))
        d = ExecutionDispatcher(registry, adapters={"R-001": _BoomAdapter()})
        with pytest.raises(RuntimeError, match="adapter exploded"):
            d.dispatch(make_request())
