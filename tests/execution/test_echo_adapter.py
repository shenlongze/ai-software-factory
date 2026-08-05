"""test_echo_adapter.py — EchoRuntimeAdapter: 内置 mock runtime 行为 (echo SUCCESS / fail 分支)。"""

from __future__ import annotations

from runtime.adapter import RuntimeAdapter
from runtime.adapters import BUILTIN_ADAPTERS, EchoRuntimeAdapter
from runtime.models import ExecutionRequest, ExecutionResult, ExecutionStatus

from runtime_helpers import make_request


class TestEchoBasics:
    def test_is_runtime_adapter(self):
        """契约: 实现 RuntimeAdapter 抽象接口 (仅依赖 models, 无 registry/store 引用)。"""
        assert issubclass(EchoRuntimeAdapter, RuntimeAdapter)
        assert isinstance(EchoRuntimeAdapter(), RuntimeAdapter)

    def test_runtime_meta(self):
        assert EchoRuntimeAdapter.RUNTIME_ID == "echo"
        assert EchoRuntimeAdapter.TYPE == "mock"
        assert EchoRuntimeAdapter.FAIL_KEY == "fail"

    def test_registered_as_builtin(self):
        """内置注册: BUILTIN_ADAPTERS["echo"] 为 EchoRuntimeAdapter 实例。"""
        assert "echo" in BUILTIN_ADAPTERS
        assert isinstance(BUILTIN_ADAPTERS["echo"], EchoRuntimeAdapter)
        assert EchoRuntimeAdapter.RUNTIME_ID in BUILTIN_ADAPTERS

    def test_returns_execution_result(self):
        result = EchoRuntimeAdapter().execute(make_request())
        assert isinstance(result, ExecutionResult)
        assert result.status is ExecutionStatus.SUCCESS

    def test_result_binds_request(self):
        """契约: result.request_id 必须等于请求 id (派发层校验依赖此绑定)。"""
        result = EchoRuntimeAdapter().execute(make_request("EX-007"))
        assert result.request_id == "EX-007"

    def test_result_id_derived_from_execution(self):
        result = EchoRuntimeAdapter().execute(make_request("EX-007"))
        assert result.id == "EXR-EX-007"


class TestEchoSuccess:
    def test_echoes_input(self):
        result = EchoRuntimeAdapter().execute(make_request(input={"prompt": "hi"}))
        assert result.output["echo"] == {"prompt": "hi"}

    def test_empty_input_echo(self):
        result = EchoRuntimeAdapter().execute(make_request(input={}))
        assert result.output["echo"] == {}

    def test_output_marks_execution_and_runtime(self):
        result = EchoRuntimeAdapter().execute(make_request("EX-009"))
        assert result.output["execution_id"] == "EX-009"
        assert result.output["runtime_id"] == "echo"

    def test_no_error_on_success(self):
        result = EchoRuntimeAdapter().execute(make_request())
        assert result.error is None


class TestEchoFailBranch:
    """特殊分支 (phase4b2-status: 按 input 特殊值返回 FAILED 供测试)。"""

    def test_fail_key_returns_failed(self):
        result = EchoRuntimeAdapter().execute(make_request(input={"fail": "boom"}))
        assert result.status is ExecutionStatus.FAILED

    def test_fail_key_error_message(self):
        result = EchoRuntimeAdapter().execute(make_request(input={"fail": "boom"}))
        assert result.error == "boom"

    def test_fail_key_still_binds_request(self):
        result = EchoRuntimeAdapter().execute(make_request("EX-010", input={"fail": "x"}))
        assert result.request_id == "EX-010"
        assert result.id == "EXR-EX-010"

    def test_falsy_fail_value_is_success(self):
        """{"fail": ""} 非真值 → 不触发 FAILED 分支。"""
        result = EchoRuntimeAdapter().execute(make_request(input={"fail": ""}))
        assert result.status is ExecutionStatus.SUCCESS

    def test_other_input_ignores_fail(self):
        result = EchoRuntimeAdapter().execute(
            make_request(input={"prompt": "p", "fail": 0})
        )
        assert result.status is ExecutionStatus.SUCCESS
        assert result.output["echo"] == {"prompt": "p", "fail": 0}
