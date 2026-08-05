"""tests/workflows/test_workflow_engine.py — WorkflowEngine 状态机与全流程。

覆盖: create/start/start_step/complete_step/fail_workflow; 非法转换拒绝; 顺序强制;
FAILED 终态; Task.workflow 关联; 事件序列。
"""

from __future__ import annotations

import pytest

from tasks.store import TaskStore
from workflows.engine import (
    StepNotReadyError,
    StepNotFoundError,
    WorkflowAlreadyStartedError,
    WorkflowEngine,
    WorkflowExistsError,
    WorkflowNotFoundError,
    WorkflowRunNotFoundError,
    WorkflowStateError,
)
from workflows.models import StepStatus, WorkflowStatus
from workflows.store import WorkflowStore

from workflow_helpers import FEATURE_STEP_IDS, make_step, make_task, make_workflow


def _seed(engine: WorkflowEngine, wf_id: str = "feature-delivery") -> None:
    """注册默认工作流定义 (engine 构造不自动注册, 显式 seed)。"""
    engine.create_workflow(make_workflow(wf_id))


def _start(engine: WorkflowEngine, task_id: str = "T-001", wf_id: str = "feature-delivery"):
    engine.task_store.create(make_task(task_id, workflow=wf_id))
    return engine.start_workflow(task_id)


class TestCreateWorkflow:
    def test_create_registers(self, engine: WorkflowEngine):
        wf, ev = engine.create_workflow(make_workflow("wf-1"))
        assert wf.id == "wf-1"
        assert ev is None  # 无 logger
        assert engine.get_workflow("wf-1") is not None
        assert engine.list_workflows()[0].id == "wf-1"

    def test_create_duplicate_raises(self, engine: WorkflowEngine):
        engine.create_workflow(make_workflow("wf-1"))
        with pytest.raises(WorkflowExistsError, match="wf-1"):
            engine.create_workflow(make_workflow("wf-1"))

    def test_create_persists(self, engine: WorkflowEngine, workflow_store: WorkflowStore):
        engine.create_workflow(make_workflow("wf-1"))
        fresh = WorkflowEngine(workflow_store, task_store=TaskStore(workflow_store.dir.parent / "tasks"))
        assert fresh.get_workflow("wf-1") is not None


class TestStartWorkflow:
    def test_start_marks_running_and_current(self, engine: WorkflowEngine):
        _seed(engine)
        run, ev = _start(engine)
        assert run.status is WorkflowStatus.RUNNING
        assert run.current_step == "architecture"
        assert run.run_id == "WR-001"
        assert ev is None
        # 设计语义: run 后第一步自动 RUNNING, 其余 PENDING
        assert run.step_states[0].status is StepStatus.RUNNING
        assert all(st.status is StepStatus.PENDING for st in run.step_states[1:])

    def test_start_auto_starts_first_step(self, engine: WorkflowEngine):
        """run 启动后第一步即 RUNNING (无需显式 start_step), current_step 指向第一步。"""
        _seed(engine)
        run, _ = _start(engine)
        assert run.step_state("architecture").status is StepStatus.RUNNING
        assert run.current_step == "architecture"

    def test_start_task_not_found(self, engine: WorkflowEngine):
        _seed(engine)
        with pytest.raises(WorkflowRunNotFoundError, match="task not found"):
            engine.start_workflow("T-999")

    def test_start_workflow_not_registered(self, engine: WorkflowEngine):
        engine.task_store.create(make_task("T-001", workflow="ghost-wf"))
        with pytest.raises(WorkflowNotFoundError, match="ghost-wf"):
            engine.start_workflow("T-001")

    def test_start_task_without_workflow(self, engine: WorkflowEngine):
        engine.task_store.create(make_task("T-001", workflow=None))
        with pytest.raises(WorkflowNotFoundError, match="no workflow"):
            engine.start_workflow("T-001")

    def test_start_already_started(self, engine: WorkflowEngine):
        _seed(engine)
        _start(engine)
        with pytest.raises(WorkflowAlreadyStartedError, match="already has"):
            engine.start_workflow("T-001")

    def test_uses_task_workflow_field(self, engine: WorkflowEngine):
        """Task.workflow 字段 → 关联定义 (自定义 workflow id)。"""
        engine.create_workflow(make_workflow("custom-wf"))
        run, _ = _start(engine, wf_id="custom-wf")
        assert run.workflow_id == "custom-wf"
        assert run.workflow_name == "custom-wf 测试"


class TestStartStep:
    def test_start_first_step(self, engine: WorkflowEngine):
        """单步工作流: run 后唯一一步自动 RUNNING, complete_step 直接收尾。"""
        engine.create_workflow(make_workflow("single", steps=[make_step("solo", 1)]))
        engine.task_store.create(make_task("T-001", workflow="single"))
        run, _ = engine.start_workflow("T-001")
        assert run.step_state("solo").status is StepStatus.RUNNING
        run, _ = engine.complete_step("T-001", "solo")
        assert run.status is WorkflowStatus.COMPLETED

    def test_start_step_advances_in_order(self, engine: WorkflowEngine):
        _seed(engine)
        _start(engine)
        engine.complete_step("T-001", "architecture")
        run, _ = engine.start_step("T-001", "development")
        assert run.step_state("development").status is StepStatus.RUNNING
        assert run.current_step == "development"

    def test_skip_step_rejected(self, engine: WorkflowEngine):
        """只能按 order 顺序: 跳过未完成步骤 → 拒绝。"""
        _seed(engine)
        _start(engine)
        with pytest.raises(StepNotReadyError, match="not the current step"):
            engine.start_step("T-001", "development")

    def test_start_completed_step_rejected(self, engine: WorkflowEngine):
        _seed(engine)
        _start(engine)
        engine.complete_step("T-001", "architecture")
        with pytest.raises(StepNotReadyError, match="not the current step|not running"):
            engine.start_step("T-001", "architecture")

    def test_start_already_running_step_rejected(self, engine: WorkflowEngine):
        """run 后第一步已自动 RUNNING: 重复 start_step (重复启动) → 拒绝。"""
        _seed(engine)
        _start(engine)
        with pytest.raises(WorkflowStateError, match="invalid step transition"):
            engine.start_step("T-001", "architecture")

    def test_start_unknown_step(self, engine: WorkflowEngine):
        _seed(engine)
        _start(engine)
        with pytest.raises(StepNotFoundError, match="not in workflow"):
            engine.start_step("T-001", "nope")

    def test_start_step_no_run(self, engine: WorkflowEngine):
        _seed(engine)
        engine.task_store.create(make_task("T-001"))
        with pytest.raises(WorkflowRunNotFoundError, match="no workflow run"):
            engine.start_step("T-001", "architecture")


class TestCompleteStep:
    def test_complete_advances_current(self, engine: WorkflowEngine):
        _seed(engine)
        _start(engine)
        run, _ = engine.complete_step("T-001", "architecture")
        assert run.step_state("architecture").status is StepStatus.COMPLETED
        assert run.step_state("architecture").result == "OK"
        assert run.current_step == "development"
        assert run.status is WorkflowStatus.RUNNING

    def test_complete_all_steps_completes_run(self, engine: WorkflowEngine):
        _seed(engine)
        _start(engine)
        run, _ = engine.complete_step("T-001", FEATURE_STEP_IDS[0])  # 第一步已自动 RUNNING
        for step_id in FEATURE_STEP_IDS[1:]:
            engine.start_step("T-001", step_id)
            run, _ = engine.complete_step("T-001", step_id)
        assert run is not None
        assert run.status is WorkflowStatus.COMPLETED
        assert run.current_step is None
        assert run.all_steps_completed()

    def test_complete_not_running_step_rejected(self, engine: WorkflowEngine):
        _seed(engine)
        _start(engine)
        with pytest.raises(StepNotReadyError, match="not running"):
            engine.complete_step("T-001", "development")  # PENDING 步骤未启动

    def test_complete_unknown_step(self, engine: WorkflowEngine):
        _seed(engine)
        _start(engine)
        with pytest.raises(StepNotFoundError, match="not in workflow"):
            engine.complete_step("T-001", "nope")

    def test_complete_after_finished_rejected(self, engine: WorkflowEngine):
        """COMPLETED 终态: run 完成后任何步骤操作拒绝。"""
        _seed(engine)
        _start(engine)
        engine.complete_step("T-001", FEATURE_STEP_IDS[0])
        for step_id in FEATURE_STEP_IDS[1:]:
            engine.start_step("T-001", step_id)
            engine.complete_step("T-001", step_id)
        with pytest.raises(WorkflowStateError, match="not running"):
            engine.start_step("T-001", "architecture")


class TestFailurePaths:
    def test_step_result_fail_fails_run(self, engine: WorkflowEngine):
        _seed(engine)
        _start(engine)
        run, _ = engine.complete_step("T-001", "architecture", result="FAIL")
        assert run.status is WorkflowStatus.FAILED
        assert run.step_state("architecture").status is StepStatus.FAILED
        assert run.error is not None and "FAIL" in run.error

    def test_fail_workflow_terminal(self, engine: WorkflowEngine):
        _seed(engine)
        _start(engine)
        run, _ = engine.fail_workflow("T-001", "agent crashed")
        assert run.status is WorkflowStatus.FAILED
        assert run.error == "agent crashed"
        assert run.step_state("architecture").status is StepStatus.FAILED  # RUNNING 步骤同步

    def test_fail_workflow_before_start(self, engine: WorkflowEngine):
        """CREATED → FAILED 合法 (未启动即废弃)。"""
        _seed(engine)
        run, _ = _start(engine)
        run, _ = engine.fail_workflow("T-001", "cancelled")
        assert run.status is WorkflowStatus.FAILED

    def test_fail_workflow_completed_rejected(self, engine: WorkflowEngine):
        """COMPLETED 终态: 不能再失败。"""
        _seed(engine)
        _start(engine)
        engine.complete_step("T-001", FEATURE_STEP_IDS[0])
        for step_id in FEATURE_STEP_IDS[1:]:
            engine.start_step("T-001", step_id)
            engine.complete_step("T-001", step_id)
        with pytest.raises(WorkflowStateError, match="terminal state"):
            engine.fail_workflow("T-001", "too late")

    def test_fail_workflow_again_rejected(self, engine: WorkflowEngine):
        """FAILED 终态: 不能二次失败。"""
        _seed(engine)
        _start(engine)
        engine.fail_workflow("T-001", "first")
        with pytest.raises(WorkflowStateError, match="terminal state"):
            engine.fail_workflow("T-001", "second")

    def test_fail_workflow_no_run(self, engine: WorkflowEngine):
        _seed(engine)
        engine.task_store.create(make_task("T-001"))
        with pytest.raises(WorkflowRunNotFoundError, match="no workflow run"):
            engine.fail_workflow("T-001", "x")

    def test_steps_after_failed_run_rejected(self, engine: WorkflowEngine):
        """FAILED 终态: run 失败后步骤操作拒绝。"""
        _seed(engine)
        _start(engine)
        engine.fail_workflow("T-001", "boom")
        with pytest.raises(WorkflowStateError, match="not running"):
            engine.start_step("T-001", "architecture")


class TestStatus:
    def test_status_returns_run(self, engine: WorkflowEngine):
        _seed(engine)
        _start(engine)
        run = engine.status("T-001")
        assert run is not None and run.status is WorkflowStatus.RUNNING

    def test_status_no_run_returns_none(self, engine: WorkflowEngine):
        engine.task_store.create(make_task("T-001"))
        assert engine.status("T-001") is None


class TestStateMachineTable:
    """转换表合法性 (公开校验入口 is_valid_*_transition)。"""

    def test_run_created_to_completed_rejected(self):
        assert not WorkflowEngine.is_valid_run_transition(WorkflowStatus.CREATED, WorkflowStatus.COMPLETED)

    def test_run_valid_path(self):
        assert WorkflowEngine.is_valid_run_transition(WorkflowStatus.CREATED, WorkflowStatus.RUNNING)
        assert WorkflowEngine.is_valid_run_transition(WorkflowStatus.RUNNING, WorkflowStatus.COMPLETED)

    def test_run_failed_terminal(self):
        assert not WorkflowEngine.is_valid_run_transition(WorkflowStatus.FAILED, WorkflowStatus.RUNNING)
        assert not WorkflowEngine.is_valid_run_transition(WorkflowStatus.FAILED, WorkflowStatus.COMPLETED)
        assert not WorkflowEngine.is_valid_run_transition(WorkflowStatus.COMPLETED, WorkflowStatus.FAILED)

    def test_step_transitions(self):
        assert WorkflowEngine.is_valid_step_transition(StepStatus.PENDING, StepStatus.RUNNING)
        assert WorkflowEngine.is_valid_step_transition(StepStatus.RUNNING, StepStatus.COMPLETED)
        assert not WorkflowEngine.is_valid_step_transition(StepStatus.PENDING, StepStatus.COMPLETED)  # 跳过 RUNNING
        assert not WorkflowEngine.is_valid_step_transition(StepStatus.COMPLETED, StepStatus.RUNNING)
        assert not WorkflowEngine.is_valid_step_transition(StepStatus.FAILED, StepStatus.RUNNING)
