"""tests/recovery/test_event_replay.py — EventReplay 按 seq 回放测试 (纯内存, 无存储)。"""

from __future__ import annotations

from agents.models import AgentStatus
from assignment.models import AssignmentStatus
from events.models import Event, EventType
from recovery.replay import EventReplay
from runtime.models import ExecutionStatus
from workflows.models import StepStatus, WorkflowStatus


def ev(type_: EventType, seq: int, **payload) -> Event:
    """构造带 seq 锚点的事件 (回放顺序由 seq 决定)。"""
    return Event.create(type_, source="test", task_id="T-001", payload=payload).model_copy(
        update={"seq": seq}
    )


def wf_started(seq: int, *, run_id: str = "WR-001", workflow_id: str = "wf-a",
               step_ids: list[str] | None = None) -> Event:
    return ev(EventType.WORKFLOW_STARTED, seq,
              run_id=run_id, workflow_id=workflow_id, step_ids=step_ids or ["s1", "s2"])


def step_started(seq: int, step_id: str) -> Event:
    return ev(EventType.WORKFLOW_STEP_STARTED, seq, step_id=step_id)


def step_completed(seq: int, step_id: str) -> Event:
    return ev(EventType.WORKFLOW_STEP_COMPLETED, seq, step_id=step_id, result="OK")


def exec_ev(type_: EventType, seq: int, execution_id: str = "EX-001") -> Event:
    return ev(type_, seq, execution_id=execution_id)


def asg_ev(type_: EventType, seq: int, *, assignment_id: str = "ASG-001",
           agent_id: str = "A-001") -> Event:
    return ev(type_, seq, assignment_id=assignment_id, agent_id=agent_id)


class TestReplayBasics:
    def test_empty_events(self):
        state = EventReplay([]).state
        assert state.workflow_status is None
        assert state.run_id is None
        assert state.current_step is None
        assert state.steps == {}
        assert state.assignments == {}
        assert state.executions == {}
        assert state.agents == {}
        assert state.last_seq == 0
        assert state.state_label == "none"

    def test_replay_sorts_by_seq(self):
        events = [step_completed(5, "s1"), step_started(4, "s1"), wf_started(3)]
        state = EventReplay(events).state
        assert state.steps == {"s1": StepStatus.COMPLETED}

    def test_unknown_event_types_ignored(self):
        events = [
            ev(EventType.TASK_CREATED, 1),
            ev(EventType.RECOVERY_STARTED, 2),
            ev(EventType.SYSTEM_INIT, 3),
            wf_started(4),
        ]
        state = EventReplay(events).state
        assert state.workflow_status is WorkflowStatus.RUNNING  # 仅 workflow.* 生效
        assert state.last_seq == 4

    def test_last_seq_tracks_max(self):
        state = EventReplay([wf_started(3), step_started(8, "s1"), step_started(5, "s2")]).state
        assert state.last_seq == 8

    def test_feed_incremental(self):
        rp = EventReplay()
        rp.feed(wf_started(1))
        assert rp.state.workflow_status is WorkflowStatus.RUNNING
        rp.feed(step_started(2, "s1"))
        assert rp.state.steps == {"s1": StepStatus.RUNNING}
        assert rp.state.current_step == "s1"

    def test_replay_twice_idempotent(self):
        events = [wf_started(1), step_started(2, "s1")]
        first = EventReplay(events).state
        second = EventReplay(events).state
        assert first.steps == second.steps
        assert first.last_seq == second.last_seq


class TestReplayWorkflow:
    def test_workflow_started_sets_running(self):
        state = EventReplay([wf_started(1)]).state
        assert state.workflow_status is WorkflowStatus.RUNNING
        assert state.run_id == "WR-001"
        assert state.workflow_id == "wf-a"
        assert state.step_order == ["s1", "s2"]

    def test_step_started_sets_running_and_current(self):
        state = EventReplay([wf_started(1), step_started(2, "s2")]).state
        assert state.steps == {"s2": StepStatus.RUNNING}
        assert state.current_step == "s2"

    def test_step_completed_advances_current_step(self):
        state = EventReplay([
            wf_started(1), step_started(2, "s1"), step_completed(3, "s1"),
        ]).state
        assert state.steps == {"s1": StepStatus.COMPLETED}
        assert state.current_step == "s2"  # 下一个未完成步骤

    def test_all_steps_completed_derives_completed(self):
        state = EventReplay([
            wf_started(1),
            step_started(2, "s1"), step_completed(3, "s1"),
            step_started(4, "s2"), step_completed(5, "s2"),
        ]).state
        assert state.workflow_status is WorkflowStatus.COMPLETED  # 事件缺失兜底
        assert state.current_step is None

    def test_workflow_completed_event(self):
        state = EventReplay([wf_started(1), ev(EventType.WORKFLOW_COMPLETED, 2)]).state
        assert state.workflow_status is WorkflowStatus.COMPLETED

    def test_workflow_failed_event(self):
        state = EventReplay([wf_started(1), ev(EventType.WORKFLOW_FAILED, 2, error="boom")]).state
        assert state.workflow_status is WorkflowStatus.FAILED

    def test_step_order_fallback_without_workflow_started(self):
        # 无 workflow.started (run 早于本阶段): 步骤按首次出现顺序追加
        state = EventReplay([step_started(1, "s2"), step_started(2, "s1")]).state
        assert state.step_order == ["s2", "s1"]

    def test_workflow_id_from_payload_optional(self):
        state = EventReplay([ev(EventType.WORKFLOW_STARTED, 1, run_id="WR-001")]).state
        assert state.run_id == "WR-001"
        assert state.workflow_id is None


class TestReplayExecution:
    def test_execution_lifecycle(self):
        state = EventReplay([
            exec_ev(EventType.EXECUTION_CREATED, 1),
            exec_ev(EventType.EXECUTION_STARTED, 2),
            exec_ev(EventType.EXECUTION_COMPLETED, 3),
        ]).state
        assert state.executions == {"EX-001": ExecutionStatus.SUCCESS}

    def test_execution_created_pending(self):
        state = EventReplay([exec_ev(EventType.EXECUTION_CREATED, 1)]).state
        assert state.executions == {"EX-001": ExecutionStatus.PENDING}

    def test_execution_started_running(self):
        state = EventReplay([exec_ev(EventType.EXECUTION_STARTED, 1)]).state
        assert state.executions == {"EX-001": ExecutionStatus.RUNNING}

    def test_execution_failed_terminal(self):
        state = EventReplay([
            exec_ev(EventType.EXECUTION_CREATED, 1),
            exec_ev(EventType.EXECUTION_FAILED, 2),
        ]).state
        assert state.executions == {"EX-001": ExecutionStatus.FAILED}

    def test_multiple_executions_independent(self):
        state = EventReplay([
            exec_ev(EventType.EXECUTION_CREATED, 1, "EX-001"),
            exec_ev(EventType.EXECUTION_CREATED, 2, "EX-002"),
            exec_ev(EventType.EXECUTION_COMPLETED, 3, "EX-001"),
        ]).state
        assert state.executions == {
            "EX-001": ExecutionStatus.SUCCESS,
            "EX-002": ExecutionStatus.PENDING,
        }


class TestReplayAssignment:
    def test_assignment_created_sets_agent_working(self):
        state = EventReplay([asg_ev(EventType.ASSIGNMENT_CREATED, 1)]).state
        assert state.assignments == {"ASG-001": AssignmentStatus.ASSIGNED}
        assert state.agents == {"A-001": AgentStatus.WORKING}

    def test_assignment_started_working(self):
        state = EventReplay([asg_ev(EventType.ASSIGNMENT_STARTED, 1)]).state
        assert state.assignments == {"ASG-001": AssignmentStatus.WORKING}

    def test_assignment_completed_releases_agent(self):
        state = EventReplay([
            asg_ev(EventType.ASSIGNMENT_CREATED, 1),
            asg_ev(EventType.ASSIGNMENT_COMPLETED, 2),
        ]).state
        assert state.assignments == {"ASG-001": AssignmentStatus.COMPLETED}
        assert state.agents == {"A-001": AgentStatus.AVAILABLE}

    def test_assignment_failed_releases_agent(self):
        state = EventReplay([
            asg_ev(EventType.ASSIGNMENT_CREATED, 1),
            asg_ev(EventType.ASSIGNMENT_FAILED, 2),
        ]).state
        assert state.assignments == {"ASG-001": AssignmentStatus.FAILED}
        assert state.agents == {"A-001": AgentStatus.AVAILABLE}

    def test_agent_released_marks_released_and_available(self):
        state = EventReplay([
            asg_ev(EventType.ASSIGNMENT_CREATED, 1),
            asg_ev(EventType.AGENT_RELEASED, 2),
        ]).state
        assert state.assignments == {"ASG-001": AssignmentStatus.RELEASED}
        assert state.agents == {"A-001": AgentStatus.AVAILABLE}

    def test_assignment_completed_after_released_keeps_terminal(self):
        # 终态不回头: released 后 completed 事件不再改状态 (回放幂等)
        state = EventReplay([
            asg_ev(EventType.ASSIGNMENT_CREATED, 1),
            asg_ev(EventType.AGENT_RELEASED, 2),
            asg_ev(EventType.ASSIGNMENT_COMPLETED, 3),
        ]).state
        assert state.assignments == {"ASG-001": AssignmentStatus.RELEASED}


class TestReplayFullChain:
    def test_interleaved_full_chain(self):
        """完整自动执行链路 (交错事件序) → 四域状态全部重建正确。"""
        events = [
            wf_started(1, step_ids=["s1", "s2"]),
            step_started(2, "s1"),
            exec_ev(EventType.EXECUTION_CREATED, 3),
            asg_ev(EventType.ASSIGNMENT_CREATED, 4),
            asg_ev(EventType.ASSIGNMENT_STARTED, 5),
            exec_ev(EventType.EXECUTION_STARTED, 6),
            exec_ev(EventType.EXECUTION_COMPLETED, 7),
            step_completed(8, "s1"),
            asg_ev(EventType.ASSIGNMENT_COMPLETED, 9),
            step_started(10, "s2"),
        ]
        state = EventReplay(events).state
        assert state.workflow_status is WorkflowStatus.RUNNING
        assert state.current_step == "s2"
        assert state.steps == {"s1": StepStatus.COMPLETED, "s2": StepStatus.RUNNING}
        assert state.executions == {"EX-001": ExecutionStatus.SUCCESS}
        assert state.assignments == {"ASG-001": AssignmentStatus.COMPLETED}
        assert state.agents == {"A-001": AgentStatus.AVAILABLE}
        assert state.last_seq == 10

    def test_interrupted_dispatch_chain(self):
        """中断现场: execution RUNNING + assignment WORKING + agent WORKING。"""
        events = [
            wf_started(1, step_ids=["s1"]),
            step_started(2, "s1"),
            exec_ev(EventType.EXECUTION_CREATED, 3),
            asg_ev(EventType.ASSIGNMENT_CREATED, 4),
            asg_ev(EventType.ASSIGNMENT_STARTED, 5),
            exec_ev(EventType.EXECUTION_STARTED, 6),  # 中断: 无 completed/failed
        ]
        state = EventReplay(events).state
        assert state.workflow_status is WorkflowStatus.RUNNING
        assert state.executions == {"EX-001": ExecutionStatus.RUNNING}
        assert state.assignments == {"ASG-001": AssignmentStatus.WORKING}
        assert state.agents == {"A-001": AgentStatus.WORKING}
