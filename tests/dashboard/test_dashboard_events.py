"""tests/dashboard/test_dashboard_events.py — dashboard.viewed 事件集成测试。"""

from __future__ import annotations

import json

from events.logger import EventLogger
from events.models import Event, EventType


class TestDashboardViewedEventType:
    def test_event_type_value(self):
        """枚举扩展: dashboard.viewed (ADR-0012, 不改表结构)。"""
        assert EventType.DASHBOARD_VIEWED.value == "dashboard.viewed"

    def test_event_type_in_enum(self):
        assert EventType("dashboard.viewed") is EventType.DASHBOARD_VIEWED

    def test_event_type_coerce_from_string(self):
        ev = Event.create("dashboard.viewed", source="test")
        assert ev.type is EventType.DASHBOARD_VIEWED


class TestDashboardViewedRecording:
    def test_record_dashboard_viewed(self, logger: EventLogger):
        ev = logger.record(
            EventType.DASHBOARD_VIEWED, source="cli", stage="viewed",
            action="view dashboard", result="OK",
            payload={"view": "all", "tasks_total": 3},
        )
        assert ev.type is EventType.DASHBOARD_VIEWED
        assert ev.result == "OK"
        assert ev.seq > 0

    def test_record_with_project_id(self, logger: EventLogger):
        ev = logger.record(
            EventType.DASHBOARD_VIEWED, source="cli", project_id="P-001",
            action="view dashboard", result="OK",
        )
        assert ev.project_id == "P-001"

    def test_event_retrievable_from_store(self, logger: EventLogger):
        logger.record(EventType.DASHBOARD_VIEWED, source="cli", action="view dashboard",
                      result="OK", payload={"view": "tasks"})
        events = logger.store.query(event_type=EventType.DASHBOARD_VIEWED)
        assert len(events) == 1
        assert events[0].payload["view"] == "tasks"

    def test_event_json_dump(self, logger: EventLogger):
        ev = logger.record(EventType.DASHBOARD_VIEWED, source="cli", action="view dashboard",
                           result="OK", payload={"view": "all", "tasks_total": 1})
        data = ev.model_dump(mode="json")
        assert data["type"] == "dashboard.viewed"
        json.dumps(data)  # JSON 友好

    def test_dashboard_viewed_append_only(self, logger: EventLogger):
        """dashboard.viewed 经 EventStore 落库, append-only 语义 (事件库只增)。"""
        before = logger.store.count()
        logger.record(EventType.DASHBOARD_VIEWED, source="cli", action="view dashboard",
                      result="OK")
        assert logger.store.count() == before + 1
        # 读接口可查回 (dashboard 查询记录事件, 事件自身可被审计)
        assert logger.store.recent(1)[0].type is EventType.DASHBOARD_VIEWED


class TestDashboardViewedPayload:
    def test_payload_counts(self, logger: EventLogger):
        ev = logger.record(
            EventType.DASHBOARD_VIEWED, source="cli", action="view dashboard", result="OK",
            payload={
                "view": "all", "tasks_total": 2, "agents_total": 1,
                "executions_total": 3, "execution_success": 2, "execution_failed": 1,
                "checkpoints_total": 0, "events_total": 10,
            },
        )
        assert ev.payload["tasks_total"] == 2
        assert ev.payload["execution_success"] == 2
        assert ev.payload["execution_failed"] == 1

    def test_payload_json_safe(self, logger: EventLogger):
        ev = logger.record(EventType.DASHBOARD_VIEWED, source="cli", action="view dashboard",
                           result="OK", payload={"view": "all"})
        row = ev.to_row()
        assert json.loads(row[-1]) == {"view": "all"}
