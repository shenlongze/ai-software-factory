"""tests/runtimes/test_catalog_events.py — Event 集成: runtime.catalog.* 事件。

覆盖: EventType 成员 / register→registered / remove→removed / 载荷字段 /
无 logger 零事件 / viewed 由读命令层经 CLI 发出 (test_cli_catalog.py 覆盖)。
"""

from __future__ import annotations

from events.models import Event, EventType

from catalog_helpers import make_definition


class TestEventTypeMembers:
    def test_members_present(self):
        for name in ("RUNTIME_CATALOG_REGISTERED", "RUNTIME_CATALOG_REMOVED", "RUNTIME_CATALOG_VIEWED"):
            assert hasattr(EventType, name)
        assert EventType.RUNTIME_CATALOG_REGISTERED.value == "runtime.catalog.registered"
        assert EventType.RUNTIME_CATALOG_REMOVED.value == "runtime.catalog.removed"
        assert EventType.RUNTIME_CATALOG_VIEWED.value == "runtime.catalog.viewed"

    def test_event_create_accepts_new_type_string(self):
        """新枚举值可经 Event.create 字符串路径入库 (ADR-0001 扩展路径)。"""
        ev = Event.create("runtime.catalog.registered", source="test")
        assert ev.type is EventType.RUNTIME_CATALOG_REGISTERED


class TestCatalogEvents:
    def test_register_emits_registered(self, event_catalog):
        d, ev = event_catalog.register(make_definition())
        assert ev is not None
        assert ev.type is EventType.RUNTIME_CATALOG_REGISTERED

    def test_registered_event_fields(self, event_catalog, logger):
        event_catalog.register(make_definition("custom-rt", version="1.2.0"))
        evs = logger.store.query()
        assert len(evs) == 1
        ev = evs[0]
        assert ev.type is EventType.RUNTIME_CATALOG_REGISTERED
        assert ev.source == "runtime_catalog"
        assert ev.stage == "active" and ev.result == "OK"
        assert ev.payload == {
            "name": "runtime custom-rt",
            "type": "agent",
            "version": "1.2.0",
            "status": "ACTIVE",
            "capabilities": ["code-generation", "testing"],
            "description": "默认测试定义",
        }

    def test_remove_emits_removed(self, event_catalog, logger):
        event_catalog.register(make_definition("custom-rt"))
        removed, ev = event_catalog.remove("custom-rt")
        assert ev is not None and ev.type is EventType.RUNTIME_CATALOG_REMOVED
        assert removed.id == "custom-rt"
        types = [e.type.value for e in logger.store.query()]
        assert types == ["runtime.catalog.registered", "runtime.catalog.removed"]

    def test_no_logger_no_events(self, catalog, logger):
        """catalog 无 logger → 纯存储操作, 不发事件 (库/测试场景)。"""
        catalog.register(make_definition("custom-rt"))
        catalog.remove("custom-rt")
        assert logger.store.query() == []

    def test_builtin_rejected_emits_nothing(self, event_catalog, logger):
        """内建定义移除被拒 — 不产生任何事件。"""
        from runtimes.catalog import RuntimeCatalogError

        try:
            event_catalog.remove("hermes")
        except RuntimeCatalogError:
            pass
        assert logger.store.query() == []

    def test_viewed_recorded_via_logger(self, logger):
        """viewed 事件经 EventLogger 直接记录 (CLI 读命令层路径, 同 runtime.viewed)。"""
        ev = logger.record(
            EventType.RUNTIME_CATALOG_VIEWED, source="cli",
            action="list runtime catalog", result="OK",
            payload={"count": 3, "type": None},
        )
        assert ev.type is EventType.RUNTIME_CATALOG_VIEWED
        assert ev.payload["count"] == 3
