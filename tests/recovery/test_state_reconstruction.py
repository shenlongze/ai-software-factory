"""tests/recovery/test_state_reconstruction.py — 四域状态重建测试 (事件链 → 状态)。

覆盖 phase4c3-status.md 的 State Reconstruction: Workflow/Step/Assignment/Execution
从事件链重建; 中断现场与终态现场均验证。
"""

from __future__ import annotations

from agents.models import AgentStatus
from agents.registry import AgentRegistry
from assignment.allocator import AgentAllocator
from assignment.models import AssignmentStatus
from events.models import Event, EventType
from recovery.replay import EventReplay
from runtime.models import ExecutionStatus
from workflows.engine import WorkflowEngine
from workflows.models import StepStatus, WorkflowStatus

from recovery_helpers import make_agent, make_task, make_workflow


def ev(type_: EventType, seq: int, **payload) -> Event:
    return Event.create(type_, source="test", task_id="T-001", payload=payload).model_copy(
        update={"seq": seq}
    )


class TestWorkflowReconstruction:
    def test_mid_step1_running(self):
        """中断于第一步: workflow RUNNING, step1 RUNNING, current_step=s1。"""
        events = [
            ev(EventType.WORKFLOW_STARTED, 1, run_id="WR-001", workflow_id="wf-a",
               step_ids=["s1", "s2"]),
            ev(EventType.WORKFLOW_STEP_STARTED, 2, step_id="s1"),
        ]
        s = EventReplay(events).state
        assert s.workflow_status is WorkflowStatus.RUNNING
        assert s.steps == {"s1": StepStatus.RUNNING}
        assert s.current_step == "s1"

    def test_full_completed_workflow(self):
        events = [
            ev(EventType.WORKFLOW_STARTED, 1, run_id="WR-001", workflow_id="wf-a",
               step_ids=["s1", "s2"]),
            ev(EventType.WORKFLOW_STEP_STARTED, 2, step_id="s1"),
            ev(EventType.WORKFLOW_STEP_COMPLETED, 3, step_id="s1", result="OK"),
            ev(EventType.WORKFLOW_STEP_STARTED, 4, step_id="s2"),
            ev(EventType.WORKFLOW_STEP_COMPLETED, 5, step_id="s2", result="OK"),
            ev(EventType.WORKFLOW_COMPLETED, 6, run_id="WR-001"),
        ]
        s = EventReplay(events).state
        assert s.workflow_status is WorkflowStatus.COMPLETED
        assert s.steps == {"s1": StepStatus.COMPLETED, "s2": StepStatus.COMPLETED}

    def test_failed_workflow(self):
        events = [
            ev(EventType.WORKFLOW_STARTED, 1, run_id="WR-001", workflow_id="wf-a",
               step_ids=["s1"]),
            ev(EventType.WORKFLOW_STEP_STARTED, 2, step_id="s1"),
            ev(EventType.WORKFLOW_STEP_COMPLETED, 3, step_id="s1", result="FAIL"),
            ev(EventType.WORKFLOW_FAILED, 4, run_id="WR-001", error="step s1 failed"),
        ]
        s = EventReplay(events).state
        assert s.workflow_status is WorkflowStatus.FAILED
        assert s.steps == {"s1": StepStatus.COMPLETED}


class TestExecutionReconstruction:
    def test_execution_states_all(self):
        events = [
            ev(EventType.EXECUTION_CREATED, 1, execution_id="EX-001"),
            ev(EventType.EXECUTION_STARTED, 2, execution_id="EX-001"),
            ev(EventType.EXECUTION_COMPLETED, 3, execution_id="EX-001", status="SUCCESS"),
        ]
        s = EventReplay(events).state
        assert s.executions == {"EX-001": ExecutionStatus.SUCCESS}

    def test_execution_stuck_running(self):
        """中断现场: execution 停在 RUNNING (无终态事件)。"""
        events = [
            ev(EventType.EXECUTION_CREATED, 1, execution_id="EX-001"),
            ev(EventType.EXECUTION_STARTED, 2, execution_id="EX-001"),
        ]
        s = EventReplay(events).state
        assert s.executions == {"EX-001": ExecutionStatus.RUNNING}


class TestAssignmentReconstruction:
    def test_assignment_with_agent_release(self):
        events = [
            ev(EventType.ASSIGNMENT_CREATED, 1, assignment_id="ASG-001", agent_id="A-001"),
            ev(EventType.ASSIGNMENT_STARTED, 2, assignment_id="ASG-001", agent_id="A-001"),
            ev(EventType.AGENT_RELEASED, 3, assignment_id="ASG-001", agent_id="A-001"),
        ]
        s = EventReplay(events).state
        assert s.assignments == {"ASG-001": AssignmentStatus.RELEASED}
        assert s.agents == {"A-001": AgentStatus.AVAILABLE}

    def test_agent_stuck_working(self):
        """中断现场: agent 停在 WORKING (assignment WORKING 无终态)。"""
        events = [
            ev(EventType.ASSIGNMENT_CREATED, 1, assignment_id="ASG-001", agent_id="A-001"),
            ev(EventType.ASSIGNMENT_STARTED, 2, assignment_id="ASG-001", agent_id="A-001"),
        ]
        s = EventReplay(events).state
        assert s.agents == {"A-001": AgentStatus.WORKING}
        assert s.assignments == {"ASG-001": AssignmentStatus.WORKING}


class TestStoreBackedReplay:
    def test_from_store_replays_task_chain(self, event_store, logger,
                                          workflow_store, task_store):
        """真实引擎事件链 (经 EventStore) → EventReplay.from_store 重建一致。"""
        wf = make_workflow("wf-a", steps=["s1", "s2"])
        workflow_store.save_workflow(wf)
        task_store.create(make_task("T-001", workflow="wf-a"))
        engine = WorkflowEngine(workflow_store, task_store=task_store, logger=logger)
        engine.start_workflow("T-001")  # 发 workflow.started + step.started

        state = EventReplay.from_store(logger.store, "T-001").state
        assert state.workflow_status is WorkflowStatus.RUNNING
        assert state.steps == {"s1": StepStatus.RUNNING}
        assert state.current_step == "s1"
        assert state.last_seq > 0

    def test_from_store_isolates_by_task(self, event_store, logger,
                                         workflow_store, task_store):
        """多任务事件共存时按 task 过滤 (by_task), 回放互不污染。"""
        wf = make_workflow("wf-a", steps=["s1"])
        workflow_store.save_workflow(wf)
        for tid in ("T-001", "T-002"):
            task_store.create(make_task(tid, workflow="wf-a"))
        engine = WorkflowEngine(workflow_store, task_store=task_store, logger=logger)
        engine.start_workflow("T-001")
        engine.start_workflow("T-002")

        s1 = EventReplay.from_store(logger.store, "T-001").state
        s2 = EventReplay.from_store(logger.store, "T-002").state
        assert s1.workflow_status is WorkflowStatus.RUNNING
        assert s2.workflow_status is WorkflowStatus.RUNNING
        assert s1.run_id != s2.run_id

    def test_recovery_events_do_not_disturb_replay(self, event_store, logger,
                                                   workflow_store, task_store):
        """recovery.* 事件混入链中不影响重建 (未知类型忽略)。"""
        wf = make_workflow("wf-a", steps=["s1"])
        workflow_store.save_workflow(wf)
        task_store.create(make_task("T-001", workflow="wf-a"))
        engine = WorkflowEngine(workflow_store, task_store=task_store, logger=logger)
        engine.start_workflow("T-001")
        logger.record(EventType.RECOVERY_STARTED, source="recovery_service",
                      task_id="T-001", action="start recovery", result="OK")
        logger.record(EventType.RECOVERY_COMPLETED, source="recovery_service",
                      task_id="T-001", action="complete recovery", result="OK")

        state = EventReplay.from_store(logger.store, "T-001").state
        assert state.workflow_status is WorkflowStatus.RUNNING
        assert state.steps == {"s1": StepStatus.RUNNING}


class TestFullPipelineReconstruction:
    def test_auto_pipeline_midway_state(self, logger, workflow_store, task_store,
                                        agent_store, assignment_store, runtime_store):
        """自动执行链路中断于第 2 步执行中 → 重建全部四域状态。"""
        agent_registry = AgentRegistry(agent_store, logger=logger)
        agent_registry.register(make_agent("A-001", role="backend-developer"))
        wf = make_workflow("wf-a", steps=["s1", "s2"])
        workflow_store.save_workflow(wf)
        task_store.create(make_task("T-001", workflow="wf-a"))
        engine = WorkflowEngine(workflow_store, task_store=task_store, logger=logger,
                                runtime_store=runtime_store, agent_registry=agent_registry)
        engine.start_workflow("T-001")  # step1 RUNNING
        engine.complete_step("T-001", "s1", result="OK")  # step1 COMPLETED, step2 当前
        engine.start_step("T-001", "s2")  # step2 RUNNING
        request, _ = engine.execute_step("T-001", "s2")  # execution.created (PENDING)
        allocator = AgentAllocator(assignment_store, agent_registry, logger=logger)
        asg, _ = allocator.assign(
            "T-001", agent_id="A-001", workflow_id="wf-a", workflow_step_id="s2",
            execution_id=request.id,
        )
        allocator.start(asg.id)  # WORKING
        logger.record(EventType.EXECUTION_STARTED, source="execution_runner",
                      task_id="T-001", payload={"execution_id": request.id,
                                                "workflow_id": "wf-a", "step_id": "s2"})

        state = EventReplay.from_store(logger.store, "T-001").state
        assert state.workflow_status is WorkflowStatus.RUNNING
        assert state.steps == {"s1": StepStatus.COMPLETED, "s2": StepStatus.RUNNING}
        assert state.current_step == "s2"
        assert state.executions == {request.id: ExecutionStatus.RUNNING}
        assert state.assignments == {asg.id: AssignmentStatus.WORKING}
        assert state.agents == {"A-001": AgentStatus.WORKING}
        assert state.last_seq == logger.store.count()  # 任务链即全部事件
