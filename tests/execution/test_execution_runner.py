"""test_execution_runner.py — ExecutionRunner 生命周期与事件序 (PENDING→started→execute→SUCCESS/FAILED→completed/failed)。

事件序契约 (phase4b2-status + ADR-0007 决策 1): 成功 [execution.started, execution.completed];
失败 [execution.started, execution.failed]; 无可用 Runtime → 保持 PENDING 且零事件。
"""

from __future__ import annotations

import pytest

from events.models import EventType
from execution.dispatcher import (
    ExecutionDispatcher,
    NoAvailableRuntimeError,
)
from execution.runner import ExecutionNotFoundError, ExecutionRunner, ExecutionStateError
from runtime.adapter import RuntimeAdapter
from runtime.models import ExecutionRequest, ExecutionResult, ExecutionStatus

from runtime_helpers import make_request, make_runtime
from conftest import register_echo


class _BoomAdapter(RuntimeAdapter):
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        raise RuntimeError("adapter exploded")


class _MisbindAdapter(RuntimeAdapter):
    """返回绑定到其他请求的结果 (契约违反 → Runner 转 FAILED)。"""

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(id="EXR-X", request_id="EX-999")


class _LifecycleProbe(RuntimeAdapter):
    """记录收到请求时的状态 (验证 adapter 收到的是 RUNNING 请求)。"""

    def __init__(self):
        self.seen: list[ExecutionStatus] = []

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.seen.append(request.status)
        return ExecutionResult(id="EXR-1", request_id=request.id)


class TestRunLifecycle:
    def test_success_lifecycle(self, runner, runtime_store):
        """终态: 请求 SUCCESS + 结果落库 (results 以 request_id 为键)。"""
        register_echo(runner.dispatcher.registry)
        req = make_request("EX-001")
        runtime_store.save_execution(req)
        outcome = runner.run("EX-001")
        assert outcome.request.status is ExecutionStatus.SUCCESS
        assert outcome.result is not None
        assert outcome.result.status is ExecutionStatus.SUCCESS
        assert runtime_store.get_execution("EX-001").status is ExecutionStatus.SUCCESS
        assert runtime_store.get_result("EX-001").request_id == "EX-001"

    def test_run_fills_runtime_id(self, runner, runtime_store):
        register_echo(runner.dispatcher.registry)
        runtime_store.save_execution(make_request("EX-001"))
        outcome = runner.run("EX-001")
        assert outcome.request.runtime_id == "echo"

    def test_result_id_derived(self, runner, runtime_store):
        register_echo(runner.dispatcher.registry)
        runtime_store.save_execution(make_request("EX-001"))
        assert runner.run("EX-001").result.id == "EXR-EX-001"

    def test_adapter_sees_running_request(self, runner, runtime_store):
        """adapter.execute 收到的请求状态为 RUNNING (派发中)。"""
        probe = _LifecycleProbe()
        runner.dispatcher.register_adapter("echo", probe)
        register_echo(runner.dispatcher.registry)
        runtime_store.save_execution(make_request("EX-001"))
        runner.run("EX-001")
        assert probe.seen == [ExecutionStatus.RUNNING]

    def test_outcome_events_success(self, event_runner, runtime_store, logger):
        register_echo(event_runner.dispatcher.registry)
        runtime_store.save_execution(make_request("EX-001"))
        outcome = event_runner.run("EX-001")
        assert [e.type for e in outcome.events] == [
            EventType.EXECUTION_STARTED, EventType.EXECUTION_COMPLETED,
        ]
        types = [e.type.value for e in logger.store.query()]
        assert types == ["execution.started", "execution.completed"]


class TestRunFailures:
    def test_failed_input(self, runner, runtime_store):
        register_echo(runner.dispatcher.registry)
        runtime_store.save_execution(make_request("EX-001", input={"fail": "boom"}))
        outcome = runner.run("EX-001")
        assert outcome.request.status is ExecutionStatus.FAILED
        assert outcome.result.status is ExecutionStatus.FAILED
        assert outcome.result.error == "boom"

    def test_failed_events_order(self, event_runner, runtime_store, logger):
        register_echo(event_runner.dispatcher.registry)
        runtime_store.save_execution(make_request("EX-001", input={"fail": "boom"}))
        outcome = event_runner.run("EX-001")
        assert [e.type.value for e in outcome.events] == [
            "execution.started", "execution.failed",
        ]
        assert [e.type.value for e in logger.store.query()] == [
            "execution.started", "execution.failed",
        ]

    def test_adapter_exception_becomes_failed(self, runner, runtime_store):
        runner.dispatcher.register_adapter("echo", _BoomAdapter())
        register_echo(runner.dispatcher.registry)
        runtime_store.save_execution(make_request("EX-001"))
        outcome = runner.run("EX-001")
        assert outcome.request.status is ExecutionStatus.FAILED
        assert outcome.result.status is ExecutionStatus.FAILED
        assert "RuntimeError" in outcome.result.error
        assert "adapter exploded" in outcome.result.error

    def test_adapter_exception_emits_failed(self, event_runner, runtime_store, logger):
        event_runner.dispatcher.register_adapter("echo", _BoomAdapter())
        register_echo(event_runner.dispatcher.registry)
        runtime_store.save_execution(make_request("EX-001"))
        event_runner.run("EX-001")
        assert [e.type.value for e in logger.store.query()] == [
            "execution.started", "execution.failed",
        ]

    def test_contract_violation_becomes_failed(self, runner, runtime_store):
        """结果错绑 (request_id 不匹配) → Runner 转 FAILED, 生命周期不中断。"""
        runner.dispatcher.register_adapter("echo", _MisbindAdapter())
        register_echo(runner.dispatcher.registry)
        runtime_store.save_execution(make_request("EX-001"))
        outcome = runner.run("EX-001")
        assert outcome.request.status is ExecutionStatus.FAILED
        assert "ExecutionDispatchError" in outcome.result.error


class TestRunPreconditions:
    def test_not_found_raises(self, runner):
        with pytest.raises(ExecutionNotFoundError, match="EX-999"):
            runner.run("EX-999")

    def test_running_rejected(self, runner, runtime_store):
        runtime_store.save_execution(make_request("EX-001", status=ExecutionStatus.RUNNING))
        with pytest.raises(ExecutionStateError, match="RUNNING"):
            runner.run("EX-001")

    def test_completed_rejected(self, runner, runtime_store):
        runtime_store.save_execution(make_request("EX-001", status=ExecutionStatus.SUCCESS))
        with pytest.raises(ExecutionStateError, match="SUCCESS"):
            runner.run("EX-001")

    def test_failed_rejected(self, runner, runtime_store):
        runtime_store.save_execution(make_request("EX-001", status=ExecutionStatus.FAILED))
        with pytest.raises(ExecutionStateError, match="FAILED"):
            runner.run("EX-001")

    def test_no_available_runtime_keeps_pending(self, event_runner, runtime_store, logger):
        """无可用 Runtime: 保持 PENDING, 零事件, 无结果 (ADR-0007 决策 4)。"""
        runtime_store.save_execution(make_request("EX-001"))
        with pytest.raises(NoAvailableRuntimeError):
            event_runner.run("EX-001")
        assert runtime_store.get_execution("EX-001").status is ExecutionStatus.PENDING
        assert runtime_store.list_results() == []
        assert logger.store.query() == []

    def test_explicit_unregistered_runtime_raises(self, runner, runtime_store):
        from runtime.registry import RuntimeNotFoundError

        runtime_store.save_execution(make_request("EX-001", runtime_id="R-999"))
        with pytest.raises(RuntimeNotFoundError):
            runner.run("EX-001")
        assert runtime_store.get_execution("EX-001").status is ExecutionStatus.PENDING


class TestRunEventPayloads:
    def _run_echo(self, runner, runtime_store, **overrides):
        register_echo(runner.dispatcher.registry)
        runtime_store.save_execution(
            make_request("EX-001", task_id="T-001", workflow_id="wf-test", step_id="s1", **overrides)
        )
        return runner.run("EX-001")

    def test_started_event_fields(self, event_runner, runtime_store, logger):
        self._run_echo(event_runner, runtime_store)
        started = logger.store.query()[0]
        assert started.type is EventType.EXECUTION_STARTED
        assert started.source == "execution_runner"
        assert started.stage == "running" and started.result == "OK"
        assert started.task_id == "T-001"
        assert started.payload == {
            "execution_id": "EX-001", "workflow_id": "wf-test", "task_id": "T-001",
            "step_id": "s1", "agent_id": None, "runtime_id": "echo", "status": "RUNNING",
        }

    def test_completed_event_fields(self, event_runner, runtime_store, logger):
        self._run_echo(event_runner, runtime_store)
        done = logger.store.query()[1]
        assert done.type is EventType.EXECUTION_COMPLETED
        assert done.stage == "success" and done.result == "OK"
        assert done.payload["status"] == "SUCCESS"
        assert done.payload["result_id"] == "EXR-EX-001"
        assert done.payload["runtime_id"] == "echo"

    def test_failed_event_fields(self, event_runner, runtime_store, logger):
        self._run_echo(event_runner, runtime_store, input={"fail": "boom"})
        failed = logger.store.query()[1]
        assert failed.type is EventType.EXECUTION_FAILED
        assert failed.stage == "failed" and failed.result == "failed"
        assert failed.payload["status"] == "FAILED"
        assert failed.payload["error"] == "boom"
        assert failed.payload["result_id"] == "EXR-EX-001"

    def test_no_logger_no_events(self, runner, runtime_store, logger):
        """runner 无 logger → 纯存储执行, 事件库零写入。"""
        register_echo(runner.dispatcher.registry)
        runtime_store.save_execution(make_request("EX-001"))
        outcome = runner.run("EX-001")
        assert outcome.events == []
        assert logger.store.query() == []


class TestRunProperties:
    def test_properties(self, runner, runtime_store, echo_dispatcher):
        assert runner.store is runtime_store
        assert runner.dispatcher is echo_dispatcher
        assert runner.workflow_engine is None

    def test_result_and_request_persisted_together(self, runner, runtime_store):
        register_echo(runner.dispatcher.registry)
        runtime_store.save_execution(make_request("EX-001", input={"fail": "nope"}))
        runner.run("EX-001")
        stored_req = runtime_store.get_execution("EX-001")
        stored_res = runtime_store.get_result("EX-001")
        assert stored_req.status is ExecutionStatus.FAILED
        assert stored_res.error == "nope"
