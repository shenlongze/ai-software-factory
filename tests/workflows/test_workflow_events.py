"""tests/workflows/test_workflow_events.py — Event 集成: 六事件 + payload 字段契约。

每个操作经 EventLogger 产生事件; payload 必须含 workflow_id/task_id/step_id/result (phase4a §3)。
"""

from __future__ import annotations

from events.logger import EventLogger
from events.models import EventType
from workflows.engine import WorkflowEngine

from workflow_helpers import FEATURE_STEP_IDS, make_task, make_workflow


def _seed_and_start(engine: WorkflowEngine, logger: EventLogger, task_id: str = "T-001"):
    engine.create_workflow(make_workflow("feature-delivery"))
    engine.task_store.create(make_task(task_id, workflow="feature-delivery"))
    return engine.start_workflow(task_id)


def _types(logger: EventLogger) -> list[str]:
    return [e.type.value for e in logger.store.query()]


class TestCreatedEvent:
    def test_created_payload(self, event_engine: WorkflowEngine, logger: EventLogger):
        wf, ev = event_engine.create_workflow(make_workflow("feature-delivery"))
        assert ev is not None
        assert ev.type is EventType.WORKFLOW_CREATED
        assert ev.source == "workflow_engine"
        assert ev.stage == "created"
        assert ev.result == "OK"
        assert ev.task_id is None  # 定义层无任务维度
        assert ev.payload["workflow_id"] == "feature-delivery"
        assert ev.payload["name"] == "feature-delivery 测试"
        assert ev.payload["steps"] == FEATURE_STEP_IDS

    def test_created_event_count(self, event_engine: WorkflowEngine, logger: EventLogger):
        event_engine.create_workflow(make_workflow("wf-1"))
        event_engine.create_workflow(make_workflow("wf-2"))
        events = logger.store.query()
        assert [e.type for e in events] == [EventType.WORKFLOW_CREATED] * 2


class TestStartedEvent:
    def test_started_payload(self, event_engine: WorkflowEngine, logger: EventLogger):
        run, ev = _seed_and_start(event_engine, logger)
        assert ev is not None
        assert ev.type is EventType.WORKFLOW_STARTED
        assert ev.stage == "running"
        assert ev.result == "OK"
        assert ev.task_id == "T-001"  # 顶层任务维度
        assert ev.payload["workflow_id"] == "feature-delivery"
        assert ev.payload["task_id"] == "T-001"
        assert ev.payload["run_id"] == run.run_id
        assert ev.payload["step_ids"] == FEATURE_STEP_IDS

    def test_start_emits_first_step_started(self, event_engine: WorkflowEngine, logger: EventLogger):
        """run 启动自动发第一步 step.started (事件序: started → step.started)。"""
        _seed_and_start(event_engine, logger)
        types = [e.type.value for e in logger.store.query()]
        assert types[-2:] == ["workflow.started", "workflow.step.started"]
        step_evs = [e for e in logger.store.query() if e.type.value == "workflow.step.started"]
        assert len(step_evs) == 1
        assert step_evs[0].payload["step_id"] == "architecture"
        assert step_evs[0].payload["step_name"] == "architecture"


class TestStepEvents:
    def test_step_started_payload(self, event_engine: WorkflowEngine, logger: EventLogger):
        _seed_and_start(event_engine, logger)
        event_engine.complete_step("T-001", "architecture")  # 第一步已自动 RUNNING
        run, ev = event_engine.start_step("T-001", "development")
        assert ev is not None
        assert ev.type is EventType.WORKFLOW_STEP_STARTED
        assert ev.task_id == "T-001"
        assert ev.payload["workflow_id"] == "feature-delivery"
        assert ev.payload["task_id"] == "T-001"
        assert ev.payload["run_id"] == run.run_id
        assert ev.payload["step_id"] == "development"
        assert ev.payload["step_name"] == "development"

    def test_step_completed_payload(self, event_engine: WorkflowEngine, logger: EventLogger):
        _seed_and_start(event_engine, logger)
        run, ev = event_engine.complete_step("T-001", "architecture", result="OK", evidence="ref://report")
        assert ev is not None
        assert ev.type is EventType.WORKFLOW_STEP_COMPLETED
        assert ev.result == "OK"
        assert ev.payload["step_id"] == "architecture"
        assert ev.payload["result"] == "OK"
        assert ev.payload["evidence"] == "ref://report"
        assert ev.payload["run_id"] == run.run_id


class TestCompletedEvent:
    def test_completed_payload(self, event_engine: WorkflowEngine, logger: EventLogger):
        _seed_and_start(event_engine, logger)
        ev = None
        ev = event_engine.complete_step("T-001", FEATURE_STEP_IDS[0])[1]  # 第一步已自动 RUNNING
        for step_id in FEATURE_STEP_IDS[1:]:
            event_engine.start_step("T-001", step_id)
            ev = event_engine.complete_step("T-001", step_id)[1]
        assert ev is not None
        assert ev.type is EventType.WORKFLOW_COMPLETED
        assert ev.stage == "completed"
        assert ev.result == "OK"
        assert ev.task_id == "T-001"
        assert ev.payload["workflow_id"] == "feature-delivery"
        assert ev.payload["task_id"] == "T-001"
        assert ev.payload["run_id"] is not None


class TestFailedEvent:
    def test_failed_payload(self, event_engine: WorkflowEngine, logger: EventLogger):
        _seed_and_start(event_engine, logger)
        run, ev = event_engine.fail_workflow("T-001", "agent crashed")
        assert ev is not None
        assert ev.type is EventType.WORKFLOW_FAILED
        assert ev.stage == "failed"
        assert ev.result == "failed"
        assert ev.task_id == "T-001"
        assert ev.payload["workflow_id"] == "feature-delivery"
        assert ev.payload["task_id"] == "T-001"
        assert ev.payload["run_id"] == run.run_id
        assert ev.payload["error"] == "agent crashed"

    def test_step_fail_emits_failed(self, event_engine: WorkflowEngine, logger: EventLogger):
        _seed_and_start(event_engine, logger)
        _, ev = event_engine.complete_step("T-001", "architecture", result="FAIL")
        assert ev is not None
        assert ev.type is EventType.WORKFLOW_FAILED


class TestEventSequence:
    def test_full_lifecycle_sequence(self, event_engine: WorkflowEngine, logger: EventLogger):
        """六事件时序: created → started → step.started → step.completed ×4 → completed。"""
        event_engine.create_workflow(make_workflow("feature-delivery"))
        event_engine.task_store.create(make_task("T-001"))
        event_engine.start_workflow("T-001")
        event_engine.complete_step("T-001", FEATURE_STEP_IDS[0])  # 第一步 step.started 已由 run 发
        for step_id in FEATURE_STEP_IDS[1:]:
            event_engine.start_step("T-001", step_id)
            event_engine.complete_step("T-001", step_id)
        assert _types(logger) == [
            "workflow.created",
            "workflow.started",
            "workflow.step.started", "workflow.step.completed",
            "workflow.step.started", "workflow.step.completed",
            "workflow.step.started", "workflow.step.completed",
            "workflow.step.started", "workflow.step.completed",
            "workflow.completed",
        ]

    def test_failure_sequence(self, event_engine: WorkflowEngine, logger: EventLogger):
        """失败路径: created → started → step.started → step.completed(FAIL) → failed。"""
        _seed_and_start(event_engine, logger)
        event_engine.complete_step("T-001", "architecture", result="FAIL")
        assert _types(logger) == [
            "workflow.created",
            "workflow.started",
            "workflow.step.started",
            "workflow.step.completed",
            "workflow.failed",
        ]

    def test_no_logger_no_events(self, engine: WorkflowEngine, db_path):
        """无 logger: 操作不产生事件 (engine 纯存储模式, 事件由上层显式传入 logger)。"""
        from events.store import EventStore
        engine.create_workflow(make_workflow("feature-delivery"))
        engine.task_store.create(make_task("T-001"))
        engine.start_workflow("T-001")
        engine.complete_step("T-001", "architecture")  # 第一步已自动 RUNNING
        store = EventStore(db_path)
        try:
            assert store.count() == 0
        finally:
            store.close()


class TestEventTypeEnum:
    def test_workflow_members_present(self):
        """六事件 + viewed (ADR-0005: 读命令事件) 均为枚举成员。"""
        for name in (
            "WORKFLOW_CREATED", "WORKFLOW_STARTED", "WORKFLOW_STEP_STARTED",
            "WORKFLOW_STEP_COMPLETED", "WORKFLOW_COMPLETED", "WORKFLOW_FAILED",
            "WORKFLOW_VIEWED",
        ):
            assert hasattr(EventType, name)
        assert EventType.WORKFLOW_CREATED.value == "workflow.created"
        assert EventType.WORKFLOW_VIEWED.value == "workflow.viewed"
