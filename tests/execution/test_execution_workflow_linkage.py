"""test_execution_workflow_linkage.py — ExecutionRunner × WorkflowEngine 联动。

契约 (phase4b2-status §Workflow 联动):
- 成功 → complete_step (workflow.step.completed; 全步完成则 workflow.completed)
- 失败 → fail_workflow (workflow.failed, 当前 RUNNING 步骤同步 FAILED)
- 未绑定 workflow / 无引擎 → 不联动; 联动异常 best-effort 记录 workflow_error
  (不影响执行终态落盘, ADR-0007 决策 4)。
"""

from __future__ import annotations

import pytest

from execution.runner import ExecutionRunner
from runtime.models import ExecutionStatus
from workflows.engine import WorkflowEngine
from workflows.models import StepStatus, WorkflowStatus

from runtime_helpers import make_task, make_workflow
from conftest import register_echo


def _seed(engine, task_store, workflow_store, *, task_id="T-001", steps=("s1", "s2"), **task_overrides):
    """workflow 定义 + 任务 + run 启动 (第一步自动 RUNNING), 返回 (task_id, 第一步)。"""
    workflow_store.save_workflow(make_workflow("wf-test", steps=list(steps)))
    task_store.create(make_task(task_id, workflow="wf-test", **task_overrides))
    engine.start_workflow(task_id)
    return task_id, steps[0]


def _pending_execution(runtime_store, *, task_id="T-001", step_id="s1", input=None):
    """直接落一条 PENDING 执行请求 (绑定工作流步骤)。"""
    from runtime_helpers import make_request

    req = make_request("EX-001", task_id=task_id, workflow_id="wf-test", step_id=step_id,
                       input=input if input is not None else {})
    runtime_store.save_execution(req)
    return req


class TestSuccessLinkage:
    def test_success_completes_step(self, event_service, runtime_store, task_store, workflow_store):
        register_echo(event_service.dispatcher.registry)
        task_id, s1 = _seed(event_service.runner.workflow_engine, task_store, workflow_store)
        _pending_execution(runtime_store, task_id=task_id, step_id=s1)
        event_service.run("EX-001")
        run = event_service.runner.workflow_engine.status(task_id)
        assert run.step_state(s1).status is StepStatus.COMPLETED
        assert run.status is WorkflowStatus.RUNNING  # s2 未执行, run 继续

    def test_success_single_step_completes_workflow(self, event_service, runtime_store, task_store, workflow_store):
        register_echo(event_service.dispatcher.registry)
        task_id, s1 = _seed(event_service.runner.workflow_engine, task_store, workflow_store, steps=("s1",))
        _pending_execution(runtime_store, task_id=task_id, step_id=s1)
        outcome = event_service.run("EX-001")
        run = event_service.runner.workflow_engine.status(task_id)
        assert run.status is WorkflowStatus.COMPLETED
        assert outcome.workflow_step_completed is True
        assert outcome.workflow_failed is False

    def test_evidence_links_execution(self, event_service, runtime_store, task_store, workflow_store):
        register_echo(event_service.dispatcher.registry)
        task_id, s1 = _seed(event_service.runner.workflow_engine, task_store, workflow_store)
        _pending_execution(runtime_store, task_id=task_id, step_id=s1)
        event_service.run("EX-001")
        step = event_service.runner.workflow_engine.status(task_id).step_state(s1)
        assert step.evidence == "execution EX-001"

    def test_events_order_with_linkage(self, event_service, runtime_store, task_store, workflow_store, logger):
        register_echo(event_service.dispatcher.registry)
        task_id, s1 = _seed(event_service.runner.workflow_engine, task_store, workflow_store, steps=("s1",))
        _pending_execution(runtime_store, task_id=task_id, step_id=s1)
        event_service.run("EX-001")
        types = [e.type.value for e in logger.store.query()]
        assert types == [
            "workflow.started", "workflow.step.started",
            "execution.started", "execution.completed",
            "workflow.step.completed", "workflow.completed",
        ]


class TestFailureLinkage:
    def test_failure_fails_workflow(self, event_service, runtime_store, task_store, workflow_store):
        register_echo(event_service.dispatcher.registry)
        task_id, s1 = _seed(event_service.runner.workflow_engine, task_store, workflow_store)
        _pending_execution(runtime_store, task_id=task_id, step_id=s1, input={"fail": "boom"})
        outcome = event_service.run("EX-001")
        run = event_service.runner.workflow_engine.status(task_id)
        assert run.status is WorkflowStatus.FAILED
        assert outcome.workflow_failed is True
        assert outcome.workflow_step_completed is False

    def test_failure_marks_running_step_failed(self, event_service, runtime_store, task_store, workflow_store):
        register_echo(event_service.dispatcher.registry)
        task_id, s1 = _seed(event_service.runner.workflow_engine, task_store, workflow_store)
        _pending_execution(runtime_store, task_id=task_id, step_id=s1, input={"fail": "boom"})
        event_service.run("EX-001")
        step = event_service.runner.workflow_engine.status(task_id).step_state(s1)
        assert step.status is StepStatus.FAILED

    def test_failure_error_message_propagates(self, event_service, runtime_store, task_store, workflow_store):
        register_echo(event_service.dispatcher.registry)
        task_id, s1 = _seed(event_service.runner.workflow_engine, task_store, workflow_store)
        _pending_execution(runtime_store, task_id=task_id, step_id=s1, input={"fail": "boom"})
        event_service.run("EX-001")
        run = event_service.runner.workflow_engine.status(task_id)
        assert "boom" in run.error

    def test_failed_events_order_with_linkage(self, event_service, runtime_store, task_store, workflow_store, logger):
        register_echo(event_service.dispatcher.registry)
        task_id, s1 = _seed(event_service.runner.workflow_engine, task_store, workflow_store)
        _pending_execution(runtime_store, task_id=task_id, step_id=s1, input={"fail": "boom"})
        event_service.run("EX-001")
        types = [e.type.value for e in logger.store.query()]
        assert types == [
            "workflow.started", "workflow.step.started",
            "execution.started", "execution.failed",
            "workflow.failed",
        ]


class TestLinkageBoundaries:
    def test_no_workflow_binding_no_linkage(self, event_service, runtime_store, task_store, workflow_store):
        """请求不绑定 workflow/step → 不触碰工作流 (独立执行)。"""
        register_echo(event_service.dispatcher.registry)
        task_id, s1 = _seed(event_service.runner.workflow_engine, task_store, workflow_store)
        from runtime_helpers import make_request

        standalone = make_request("EX-001", task_id=task_id, workflow_id=None, step_id=None)
        runtime_store.save_execution(standalone)
        outcome = event_service.run("EX-001")
        assert outcome.workflow_step_completed is False
        assert outcome.workflow_failed is False
        assert event_service.runner.workflow_engine.status(task_id).step_state(s1).status is StepStatus.RUNNING

    def test_no_engine_no_linkage(self, runner, runtime_store, task_store, workflow_store):
        """runner 未装配 workflow_engine → 只执行, 不联动。"""
        engine = WorkflowEngine(workflow_store, task_store=task_store)
        task_id, s1 = _seed(engine, task_store, workflow_store)
        register_echo(runner.dispatcher.registry)
        _pending_execution(runtime_store, task_id=task_id, step_id=s1)
        outcome = runner.run("EX-001")
        assert outcome.request.status is ExecutionStatus.SUCCESS
        assert outcome.workflow_step_completed is False
        assert engine.status(task_id).step_state(s1).status is StepStatus.RUNNING

    def test_linkage_error_on_terminal_run(self, event_service, runtime_store, task_store, workflow_store):
        """联动前置不满足 (run 已终态) → workflow_error 记录, 执行终态不受影响。"""
        register_echo(event_service.dispatcher.registry)
        task_id, s1 = _seed(event_service.runner.workflow_engine, task_store, workflow_store, steps=("s1",))
        event_service.runner.workflow_engine.complete_step(task_id, s1)  # run → COMPLETED
        _pending_execution(runtime_store, task_id=task_id, step_id=s1)
        outcome = event_service.run("EX-001")
        assert outcome.request.status is ExecutionStatus.SUCCESS
        assert outcome.workflow_step_completed is False
        assert outcome.workflow_error is not None
        assert "not running" in outcome.workflow_error

    def test_linkage_error_on_pending_step(self, event_service, runtime_store, task_store, workflow_store):
        """步骤未启动 (PENDING, 手工构造 run) → complete_step 拒绝 → workflow_error。"""
        from runtime_helpers import make_workflow as _mw
        from workflows.models import WorkflowRun

        register_echo(event_service.dispatcher.registry)
        engine = event_service.runner.workflow_engine
        workflow_store.save_workflow(_mw("wf-test", steps=["s1"]))
        task_store.create(make_task("T-001", workflow="wf-test"))
        run = WorkflowRun.from_workflow(
            run_id="WR-001", workflow=workflow_store.get_workflow("wf-test"), task_id="T-001",
        )
        run.status = WorkflowStatus.RUNNING  # 第一步保持 PENDING (未启动)
        workflow_store.save_run(run)
        _pending_execution(runtime_store, task_id="T-001", step_id="s1")
        outcome = event_service.run("EX-001")
        assert outcome.request.status is ExecutionStatus.SUCCESS
        assert outcome.workflow_step_completed is False
        assert "not running" in outcome.workflow_error

    def test_linkage_error_failure_path(self, event_service, runtime_store, task_store, workflow_store):
        """失败联动前置不满足 (run 已 COMPLETED) → workflow_error, 执行仍 FAILED 落盘。"""
        register_echo(event_service.dispatcher.registry)
        task_id, s1 = _seed(event_service.runner.workflow_engine, task_store, workflow_store, steps=("s1",))
        event_service.runner.workflow_engine.complete_step(task_id, s1)
        _pending_execution(runtime_store, task_id=task_id, step_id=s1, input={"fail": "boom"})
        outcome = event_service.run("EX-001")
        assert outcome.request.status is ExecutionStatus.FAILED
        assert outcome.workflow_failed is False
        assert outcome.workflow_error is not None

    def test_runner_property_engine(self, service):
        assert isinstance(service.runner.workflow_engine, WorkflowEngine)
