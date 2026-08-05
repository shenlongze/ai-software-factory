"""test_runtime_events.py — Event 集成: runtime.* / execution.* 事件 (一律经 EventLogger)。"""

from __future__ import annotations

from events.models import EventType
from runtime.models import RuntimeStatus

from runtime_helpers import make_runtime, make_task, make_workflow


class TestEventTypeMembers:
    def test_runtime_members_present(self):
        for name in ("RUNTIME_REGISTERED", "RUNTIME_REMOVED", "RUNTIME_VIEWED"):
            assert hasattr(EventType, name)
        assert EventType.RUNTIME_REGISTERED.value == "runtime.registered"
        assert EventType.RUNTIME_REMOVED.value == "runtime.removed"
        assert EventType.RUNTIME_VIEWED.value == "runtime.viewed"

    def test_execution_members_present(self):
        for name in (
            "EXECUTION_CREATED", "EXECUTION_STARTED",
            "EXECUTION_COMPLETED", "EXECUTION_FAILED", "EXECUTION_VIEWED",
        ):
            assert hasattr(EventType, name)
        assert EventType.EXECUTION_CREATED.value == "execution.created"
        assert EventType.EXECUTION_STARTED.value == "execution.started"
        assert EventType.EXECUTION_COMPLETED.value == "execution.completed"
        assert EventType.EXECUTION_FAILED.value == "execution.failed"
        assert EventType.EXECUTION_VIEWED.value == "execution.viewed"

    def test_event_create_accepts_new_type_string(self):
        """新枚举值可经 Event.create 字符串路径入库 (ADR-0001 扩展路径)。"""
        from events.models import Event

        ev = Event.create("runtime.registered", source="test")
        assert ev.type is EventType.RUNTIME_REGISTERED


class TestRuntimeEvents:
    def test_register_emits_runtime_registered(self, event_registry):
        rt, ev = event_registry.register(make_runtime("R-001"))
        assert ev is not None
        assert ev.type is EventType.RUNTIME_REGISTERED

    def test_registered_event_fields(self, event_registry, logger):
        event_registry.register(make_runtime("R-001", name="mock-rt", description="d"))
        evs = logger.store.query()
        assert len(evs) == 1
        ev = evs[0]
        assert ev.type is EventType.RUNTIME_REGISTERED
        assert ev.source == "runtime_registry"
        assert ev.stage == "available" and ev.result == "OK"
        assert ev.payload == {
            "name": "mock-rt", "type": "agent", "status": "AVAILABLE", "description": "d",
        }

    def test_register_disabled_stage(self, event_registry, logger):
        event_registry.register(make_runtime("R-001", status=RuntimeStatus.DISABLED))
        assert logger.store.query()[0].stage == "disabled"

    def test_remove_emits_runtime_removed(self, event_registry, logger):
        event_registry.register(make_runtime("R-001"))
        removed, ev = event_registry.remove("R-001")
        assert ev is not None and ev.type is EventType.RUNTIME_REMOVED
        assert removed.id == "R-001"
        types = [e.type.value for e in logger.store.query()]
        assert types == ["runtime.registered", "runtime.removed"]

    def test_no_logger_no_events(self, registry, logger):
        """registry 无 logger → 纯存储操作, 不发事件 (库/测试场景)。"""
        registry.register(make_runtime("R-001"))
        assert logger.store.query() == []


class TestExecutionEvents:
    def test_created_emitted_by_execute_step(self, event_engine, task_store, workflow_store):
        workflow_store.save_workflow(make_workflow("wf-test", steps=["s1", "s2"]))
        task_store.create(make_task("T-001", workflow="wf-test"))
        event_engine.start_workflow("T-001")
        req, ev = event_engine.execute_step("T-001", "s1")
        assert ev is not None and ev.type is EventType.EXECUTION_CREATED

    def test_created_event_fields(self, event_engine, task_store, workflow_store):
        workflow_store.save_workflow(make_workflow("wf-test", steps=["s1"]))
        task_store.create(make_task("T-001", workflow="wf-test"))
        event_engine.start_workflow("T-001")
        req, ev = event_engine.execute_step("T-001", "s1")
        assert ev.source == "workflow_engine"
        assert ev.stage == "pending" and ev.result == "OK"
        assert ev.payload["execution_id"] == req.id
        assert ev.payload["step_id"] == "s1"
        assert ev.payload["status"] == "PENDING"
        assert ev.payload["task_id"] == "T-001"
        assert ev.payload["workflow_id"] == "wf-test"

    def test_created_is_last_event(self, event_engine, task_store, workflow_store, logger):
        """事件序: workflow.started → workflow.step.started → execution.created。"""
        workflow_store.save_workflow(make_workflow("wf-test", steps=["s1"]))
        task_store.create(make_task("T-001", workflow="wf-test"))
        event_engine.start_workflow("T-001")
        event_engine.execute_step("T-001", "s1")
        types = [e.type.value for e in logger.store.query()]
        assert types == ["workflow.started", "workflow.step.started", "execution.created"]

    def test_lifecycle_events_recordable(self, logger):
        """started/completed/failed 事件模型就绪, 可经 EventLogger 记录
        (无具体 Runtime, 发射点落在 4B-2 派发层 — ADR-0006 决策 1)。"""
        logger.record(EventType.EXECUTION_STARTED, source="dispatcher", task_id="T-1",
                      stage="running", action="dispatch execution", result="OK",
                      payload={"execution_id": "EX-001", "runtime_id": "R-001"})
        logger.record(EventType.EXECUTION_COMPLETED, source="dispatcher", task_id="T-1",
                      stage="success", action="complete execution", result="OK",
                      payload={"execution_id": "EX-001"})
        logger.record(EventType.EXECUTION_FAILED, source="dispatcher", task_id="T-1",
                      stage="failed", action="fail execution", result="failed",
                      payload={"execution_id": "EX-001", "error": "boom"})
        types = [e.type.value for e in logger.store.query()]
        assert types == ["execution.started", "execution.completed", "execution.failed"]

    def test_lifecycle_events_roundtrip(self, logger):
        ev = logger.record(EventType.EXECUTION_STARTED, source="dispatcher", stage="running",
                           action="dispatch", payload={"execution_id": "EX-001"})
        stored = logger.store.query()[0]
        assert stored.payload == {"execution_id": "EX-001"}
        assert stored.seq == ev.seq
        assert stored.type is EventType.EXECUTION_STARTED

    def test_viewed_events_recordable(self, logger):
        """读命令事件 (ADR-0002 铁律): runtime.viewed / execution.viewed。"""
        logger.record(EventType.RUNTIME_VIEWED, source="cli", action="list runtimes",
                      result="OK", payload={"count": 0})
        logger.record(EventType.EXECUTION_VIEWED, source="cli", action="list executions",
                      result="OK", payload={"count": 0})
        types = [e.type.value for e in logger.store.query()]
        assert types == ["runtime.viewed", "execution.viewed"]
