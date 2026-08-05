"""test_execution_service.py — ExecutionService: 组合根 (Dispatcher + Runner + Store) 编排与查询。"""

from __future__ import annotations

import pytest

from execution.dispatcher import ExecutionDispatcher
from execution.runner import ExecutionRunner
from runtime.adapter import RuntimeAdapter
from runtime.models import ExecutionRequest, ExecutionResult, ExecutionStatus

from runtime_helpers import make_request
from conftest import register_echo


class _FixedAdapter(RuntimeAdapter):
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(id="EXR-1", request_id=request.id, output={"svc": True})


class TestServiceRun:
    def test_run_delegates_to_runner(self, service, runtime_store):
        register_echo(service.dispatcher.registry)
        request = make_request("EX-001")
        runtime_store.save_execution(request)
        outcome = service.run("EX-001")
        assert outcome.request.status is ExecutionStatus.SUCCESS
        # Echo 语义 = 回显 input 到 output["echo"] (runtime/adapters/echo.py)
        assert outcome.result.output == {
            "echo": request.input, "execution_id": "EX-001", "runtime_id": "echo",
        }

    def test_run_failed_input(self, service, runtime_store):
        register_echo(service.dispatcher.registry)
        runtime_store.save_execution(make_request("EX-001", input={"fail": "x"}))
        assert service.run("EX-001").request.status is ExecutionStatus.FAILED

    def test_run_not_found(self, service):
        from execution.runner import ExecutionNotFoundError

        with pytest.raises(ExecutionNotFoundError, match="execution not found"):
            service.run("EX-999")


class TestServiceStatus:
    def test_status_before_run(self, service, runtime_store):
        register_echo(service.dispatcher.registry)
        runtime_store.save_execution(make_request("EX-001"))
        request, result = service.status("EX-001")
        assert request is not None and request.status is ExecutionStatus.PENDING
        assert result is None

    def test_status_after_run(self, service, runtime_store):
        register_echo(service.dispatcher.registry)
        runtime_store.save_execution(make_request("EX-001"))
        service.run("EX-001")
        request, result = service.status("EX-001")
        assert request.status is ExecutionStatus.SUCCESS
        assert result is not None and result.status is ExecutionStatus.SUCCESS

    def test_status_not_found(self, service):
        assert service.status("EX-999") == (None, None)

    def test_status_emits_no_events(self, event_service, runtime_store, logger):
        """status 是只读查询, 不发事件 (CLI 层另行发 execution.viewed)。"""
        register_echo(event_service.dispatcher.registry)
        runtime_store.save_execution(make_request("EX-001"))
        event_service.status("EX-001")
        assert logger.store.query() == []


class TestServiceAssembly:
    def test_properties(self, service, runtime_store, registry):
        assert service.store is runtime_store
        assert isinstance(service.dispatcher, ExecutionDispatcher)
        assert isinstance(service.runner, ExecutionRunner)
        assert service.dispatcher.registry is registry

    def test_register_adapter_passthrough(self, service, runtime_store):
        service.register_adapter("R-001", _FixedAdapter())
        assert isinstance(service.dispatcher.get_adapter("R-001"), _FixedAdapter)

    def test_builtin_adapters_wired(self, service):
        from runtime.adapters import EchoRuntimeAdapter

        assert isinstance(service.dispatcher.get_adapter("echo"), EchoRuntimeAdapter)

    def test_runner_workflow_engine_wired(self, service):
        from workflows.engine import WorkflowEngine

        assert isinstance(service.runner.workflow_engine, WorkflowEngine)
