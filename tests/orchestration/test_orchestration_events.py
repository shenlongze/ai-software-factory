"""test_orchestration_events.py — orchestration.* 事件: EventType 扩展 + emit 辅助。

覆盖: 枚举成员/取值 / source / stage / result / payload / logger 缺省返回 None /
经 EventLogger 落库 (seq 回填) / 与 workflow.* 底层事件并存 (事件序)。
"""

from __future__ import annotations

import pytest

from events.logger import EventLogger
from events.models import EventType
from orchestration import events as orch_events


class TestEventTypeExtension:
    def test_members_exist(self):
        """EventType 含五个 orchestration.* 成员 (ADR-0010 增量扩展)。"""
        assert EventType.ORCHESTRATION_STARTED == "orchestration.started"
        assert EventType.ORCHESTRATION_STEP_STARTED == "orchestration.step.started"
        assert EventType.ORCHESTRATION_STEP_COMPLETED == "orchestration.step.completed"
        assert EventType.ORCHESTRATION_COMPLETED == "orchestration.completed"
        assert EventType.ORCHESTRATION_FAILED == "orchestration.failed"

    def test_values_are_strings(self):
        for member in (
            EventType.ORCHESTRATION_STARTED, EventType.ORCHESTRATION_STEP_STARTED,
            EventType.ORCHESTRATION_STEP_COMPLETED, EventType.ORCHESTRATION_COMPLETED,
            EventType.ORCHESTRATION_FAILED,
        ):
            assert isinstance(member.value, str)

    def test_coercion_from_string(self):
        """Event.create 字符串 type 经 validator 宽容转换 (ADR-0001 扩展路径)。"""
        from events.models import Event
        ev = Event.create("orchestration.started", source="x")
        assert ev.type is EventType.ORCHESTRATION_STARTED

    def test_legacy_events_unchanged(self):
        """既有事件不回归 (908 基线语义)。"""
        assert EventType.WORKFLOW_STARTED == "workflow.started"
        assert EventType.EXECUTION_COMPLETED == "execution.completed"
        assert EventType.ASSIGNMENT_CREATED == "agent.assignment.created"


class TestSource:
    def test_source_constant(self):
        assert orch_events.SOURCE == "orchestration_engine"

    def test_all_events_use_orchestration_source(self, logger: EventLogger):
        orch_events.emit_started(logger, task_id="T-001")
        orch_events.emit_step_started(logger, task_id="T-001", workflow_id="wf",
                                      run_id="WR-001", step_id="dev")
        orch_events.emit_step_completed(logger, task_id="T-001", workflow_id="wf",
                                        run_id="WR-001", step_id="dev")
        orch_events.emit_completed(logger, task_id="T-001", workflow_id="wf",
                                   run_id="WR-001", steps=[])
        orch_events.emit_failed(logger, task_id="T-001", workflow_id="wf",
                                run_id="WR-001", error="boom")
        events = logger.store.query()
        assert len(events) == 5
        assert all(e.source == "orchestration_engine" for e in events)


class TestEmitStarted:
    def test_payload(self, logger: EventLogger):
        ev = orch_events.emit_started(logger, task_id="T-001")
        assert ev is not None
        assert ev.type is EventType.ORCHESTRATION_STARTED
        assert ev.task_id == "T-001"
        assert ev.stage == "running"
        assert ev.result == "OK"
        assert ev.payload == {"task_id": "T-001"}

    def test_seq_assigned(self, logger: EventLogger):
        ev = orch_events.emit_started(logger, task_id="T-001")
        assert ev is not None and ev.seq > 0
        stored = logger.store.query(task_id="T-001")
        assert stored[-1].event_id == ev.event_id

    def test_no_logger_returns_none(self):
        assert orch_events.emit_started(None, task_id="T-001") is None


class TestEmitStepStarted:
    def test_payload(self, logger: EventLogger):
        ev = orch_events.emit_step_started(
            logger, task_id="T-001", workflow_id="wf", run_id="WR-001",
            step_id="dev", step_name="编码", agent_id="A-001",
        )
        assert ev is not None
        assert ev.type is EventType.ORCHESTRATION_STEP_STARTED
        assert ev.task_id == "T-001"
        assert ev.agent_id == "A-001"
        assert ev.stage == "running" and ev.result == "OK"
        assert ev.payload["workflow_id"] == "wf"
        assert ev.payload["run_id"] == "WR-001"
        assert ev.payload["step_id"] == "dev"
        assert ev.payload["step_name"] == "编码"
        assert ev.payload["agent_id"] == "A-001"

    def test_agent_optional(self, logger: EventLogger):
        ev = orch_events.emit_step_started(
            logger, task_id="T-001", workflow_id="wf", run_id="WR-001", step_id="dev",
        )
        assert ev is not None and ev.agent_id is None

    def test_no_logger_returns_none(self):
        assert orch_events.emit_step_started(
            None, task_id="T-001", workflow_id="wf", run_id="WR-001", step_id="dev",
        ) is None


class TestEmitStepCompleted:
    def test_payload(self, logger: EventLogger):
        ev = orch_events.emit_step_completed(
            logger, task_id="T-001", workflow_id="wf", run_id="WR-001",
            step_id="dev", step_name="编码", agent_id="A-001",
            execution_id="EX-001", result="OK",
        )
        assert ev is not None
        assert ev.type is EventType.ORCHESTRATION_STEP_COMPLETED
        assert ev.stage == "running" and ev.result == "OK"
        assert ev.payload["execution_id"] == "EX-001"
        assert ev.payload["result"] == "OK"

    def test_no_logger_returns_none(self):
        assert orch_events.emit_step_completed(
            None, task_id="T-001", workflow_id="wf", run_id="WR-001", step_id="dev",
        ) is None


class TestEmitCompleted:
    def test_payload_with_steps(self, logger: EventLogger):
        steps = [{"step_id": "dev", "status": "COMPLETED"}]
        ev = orch_events.emit_completed(
            logger, task_id="T-001", workflow_id="wf", run_id="WR-001", steps=steps,
        )
        assert ev is not None
        assert ev.type is EventType.ORCHESTRATION_COMPLETED
        assert ev.stage == "completed" and ev.result == "OK"
        assert ev.payload["steps"] == steps
        assert ev.payload["workflow_id"] == "wf" and ev.payload["run_id"] == "WR-001"

    def test_no_logger_returns_none(self):
        assert orch_events.emit_completed(
            None, task_id="T-001", workflow_id="wf", run_id="WR-001", steps=[],
        ) is None


class TestEmitFailed:
    def test_payload(self, logger: EventLogger):
        ev = orch_events.emit_failed(
            logger, task_id="T-001", workflow_id="wf", run_id="WR-001", error="boom",
        )
        assert ev is not None
        assert ev.type is EventType.ORCHESTRATION_FAILED
        assert ev.stage == "failed" and ev.result == "failed"
        assert ev.payload["error"] == "boom"

    def test_workflow_optional(self, logger: EventLogger):
        """前置错误 (任务不存在等) 时 workflow_id/run_id 可为 None。"""
        ev = orch_events.emit_failed(logger, task_id="T-999", error="task not found: T-999")
        assert ev is not None
        assert ev.payload["workflow_id"] is None
        assert ev.payload["run_id"] is None

    def test_no_logger_returns_none(self):
        assert orch_events.emit_failed(None, task_id="T-001", error="boom") is None


class TestSequence:
    def test_success_sequence_order(self, logger: EventLogger):
        """成功事件序: started → step.started → step.completed → completed。"""
        orch_events.emit_started(logger, task_id="T-001")
        orch_events.emit_step_started(logger, task_id="T-001", workflow_id="wf",
                                      run_id="WR-001", step_id="dev")
        orch_events.emit_step_completed(logger, task_id="T-001", workflow_id="wf",
                                        run_id="WR-001", step_id="dev")
        orch_events.emit_completed(logger, task_id="T-001", workflow_id="wf",
                                   run_id="WR-001", steps=[])
        types = [e.type.value for e in logger.store.query()]
        assert types == [
            "orchestration.started", "orchestration.step.started",
            "orchestration.step.completed", "orchestration.completed",
        ]

    def test_failure_sequence_order(self, logger: EventLogger):
        """失败事件序: started → step.started → failed (无 step.completed/completed)。"""
        orch_events.emit_started(logger, task_id="T-001")
        orch_events.emit_step_started(logger, task_id="T-001", workflow_id="wf",
                                      run_id="WR-001", step_id="dev")
        orch_events.emit_failed(logger, task_id="T-001", workflow_id="wf",
                                run_id="WR-001", error="boom")
        types = [e.type.value for e in logger.store.query()]
        assert types == [
            "orchestration.started", "orchestration.step.started",
            "orchestration.failed",
        ]

    def test_mixed_with_workflow_events(self, logger: EventLogger):
        """orchestration.* 与 workflow.* 经同一 EventStore 按 seq 严格排序。"""
        logger.record(EventType.WORKFLOW_STARTED, source="workflow_engine",
                      task_id="T-001", stage="running", action="start workflow")
        orch_events.emit_started(logger, task_id="T-001")
        logger.record(EventType.WORKFLOW_COMPLETED, source="workflow_engine",
                      task_id="T-001", stage="completed", action="complete workflow")
        types = [e.type.value for e in logger.store.query()]
        assert types == [
            "workflow.started", "orchestration.started", "workflow.completed",
        ]
