"""test_runtime_adapter.py — RuntimeAdapter 抽象接口契约 (无具体 Runtime 实现)。"""

from __future__ import annotations

import inspect

import pytest

from runtime.adapter import RuntimeAdapter
from runtime.models import ExecutionRequest, ExecutionResult

from runtime_helpers import make_request


class _EchoAdapter(RuntimeAdapter):
    """测试实现: 原样回显输入为 SUCCESS 结果 (验证子类实现契约)。"""

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(id="EXR-1", request_id=request.id, output={"echo": request.input})


class _SuperAdapter(RuntimeAdapter):
    """测试实现: 显式调 super().execute (验证抽象方法占位行为)。"""

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        return super().execute(request)


class TestAdapterContract:
    def test_is_abc(self):
        assert inspect.isabstract(RuntimeAdapter)

    def test_execute_is_abstract(self):
        assert "execute" in RuntimeAdapter.__abstractmethods__

    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            RuntimeAdapter()

    def test_subclass_without_execute_not_instantiable(self):
        class NoExecute(RuntimeAdapter):
            pass

        with pytest.raises(TypeError):
            NoExecute()

    def test_subclass_with_execute_instantiable(self):
        assert isinstance(_EchoAdapter(), RuntimeAdapter)

    def test_execute_returns_result(self):
        """契约: execute(request) -> ExecutionResult, 结果关联 request_id。"""
        req = ExecutionRequest(id="EX-001", task_id="T-1", input={"prompt": "hi"})
        res = _EchoAdapter().execute(req)
        assert isinstance(res, ExecutionResult)
        assert res.request_id == req.id
        assert res.status.value == "SUCCESS"
        assert res.output == {"echo": {"prompt": "hi"}}

    def test_execute_with_workflow_bound_request(self):
        req = make_request()
        res = _EchoAdapter().execute(req)
        assert res.request_id == req.id
        assert res.status.value == "SUCCESS"

    def test_base_execute_raises_not_implemented(self):
        """抽象方法占位: 子类调 super().execute 抛 NotImplementedError。"""
        with pytest.raises(NotImplementedError):
            _SuperAdapter().execute(make_request())

    def test_adapter_decoupled_from_registry(self):
        """Adapter 与注册表/存储解耦: 接口模块不 import 注册表/存储/事件 (只依赖模型)。"""
        mod = inspect.getmodule(RuntimeAdapter)
        assert mod is not None
        src = inspect.getsource(mod)
        assert "from .registry" not in src
        assert "from .store" not in src
        assert "EventLogger" not in src
        assert "from .models import" in src  # 唯一依赖: 模型契约
