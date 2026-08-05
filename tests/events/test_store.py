"""test_store.py — SQLite append-only 存储 (phase1-plan §7.1 test_store 覆盖点 ①-⑧)。"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from events.models import EventType
from events.store import EventStore
from helpers import ev


class TestAppend:
    def test_append_assigns_monotonic_seq(self, store: EventStore):
        """① append 后 seq 单调递增 (1,2,3...)。"""
        e1 = store.append(ev(EventType.TASK_START, task_id="T-1"))
        e2 = store.append(ev(EventType.TOOL_CALL, task_id="T-1"))
        e3 = store.append(ev(EventType.TASK_END, task_id="T-1", result="done"))
        assert [e1.seq, e2.seq, e3.seq] == [1, 2, 3]

    def test_append_backfills_seq_via_copy(self, store: EventStore):
        """append 返回回填 seq 的新实例, 原事件 seq 仍为 0。"""
        original = ev(EventType.TASK_START, task_id="T-1")
        stored = store.append(original)
        assert stored.seq == 1
        assert original.seq == 0

    def test_duplicate_event_id_rejected(self, store: EventStore):
        """③ 重复 event_id 拒绝 (UNIQUE)。"""
        e1 = store.append(ev(EventType.TASK_START, task_id="T-1"))
        with pytest.raises(sqlite3.IntegrityError):
            store.append(e1)  # 同一 event_id 再次追加

    def test_append_invalid_payload_rejected_before_db(self, store: EventStore):
        """非 JSON payload 在模型层拒绝, 不落库。"""
        with pytest.raises(ValidationError):
            store.append(ev(EventType.TOOL_CALL, payload={"bad": datetime.now(timezone.utc)}))
        assert store.count() == 0

    def test_append_with_none_optional_fields(self, store: EventStore):
        """agent_id/task_id 为 None 时正常写入。"""
        e = store.append(ev(EventType.SESSION_CLOSE))
        assert e.task_id is None and e.agent_id is None
        assert store.count() == 1


class TestAppendOnly:
    def test_store_has_no_update_delete_methods(self, store: EventStore):
        """应用层第一道闸: 无 update/delete 方法。"""
        assert not hasattr(store, "update")
        assert not hasattr(store, "delete")

    def test_update_rejected_by_trigger(self, store: EventStore):
        """② UPDATE 被触发器物理拒绝。"""
        store.append(ev(EventType.TASK_START, task_id="T-1"))
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store._conn.execute("UPDATE events SET source='hacked' WHERE seq=1")

    def test_delete_rejected_by_trigger(self, store: EventStore):
        """② DELETE 被触发器物理拒绝。"""
        store.append(ev(EventType.TASK_START, task_id="T-1"))
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store._conn.execute("DELETE FROM events WHERE seq=1")

    def test_append_only_across_new_connection(self, db_path):
        """触发器跨连接仍生效 (数据库层保证, 与连接无关)。"""
        s1 = EventStore(db_path)
        s1.append(ev(EventType.TASK_START, task_id="T-1"))
        s1.close()
        s2 = EventStore(db_path)
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            s2._conn.execute("DELETE FROM events WHERE seq=1")
        s2.close()


class TestQuery:
    def test_by_task_ordered_replay(self, store: EventStore):
        """④ 按 task_id 回放顺序正确 (seq 升序) + since_seq 锚点。"""
        store.append(ev(EventType.TASK_START, task_id="T-1"))
        store.append(ev(EventType.TOOL_CALL, task_id="T-1"))
        store.append(ev(EventType.CHECKPOINT, task_id="T-1"))
        store.append(ev(EventType.TASK_END, task_id="T-1", result="done"))
        store.append(ev(EventType.TASK_START, task_id="T-2"))

        chain = store.by_task("T-1")
        assert [e.type.value for e in chain] == ["task.start", "tool.call", "checkpoint", "task.end"]
        assert [e.seq for e in chain] == [1, 2, 3, 4]

        resumed = store.by_task("T-1", since_seq=2)
        assert [e.type.value for e in resumed] == ["checkpoint", "task.end"]

    def test_by_agent(self, store: EventStore):
        store.append(ev(EventType.TOOL_CALL, task_id="T-1", agent_id="A-1"))
        store.append(ev(EventType.TOOL_CALL, task_id="T-1", agent_id="A-2"))
        store.append(ev(EventType.TOOL_CALL, task_id="T-2", agent_id="A-1"))
        got = store.by_agent("A-1")
        assert len(got) == 2
        assert all(e.agent_id == "A-1" for e in got)

    def test_by_project(self, store: EventStore):
        store.append(ev(EventType.TASK_START, task_id="T-1", project_id="P-1"))
        store.append(ev(EventType.TASK_START, task_id="T-2", project_id="P-2"))
        store.append(ev(EventType.TASK_START, task_id="T-3", project_id="P-1"))
        got = store.by_project("P-1")
        assert [e.task_id for e in got] == ["T-1", "T-3"]

    def test_query_by_type(self, store: EventStore):
        for _ in range(3):
            store.append(ev(EventType.TOOL_CALL, task_id="T-1"))
        store.append(ev(EventType.CHECKPOINT, task_id="T-1"))
        fails = store.by_type(EventType.TOOL_CALL)
        assert len(fails) == 3
        assert all(e.type is EventType.TOOL_CALL for e in fails)

    def test_query_by_type_string_accepts_str(self, store: EventStore):
        store.append(ev(EventType.TASK_FAIL, task_id="T-1"))
        assert len(store.by_type("task.fail")) == 1

    def test_query_time_range(self, store: EventStore):
        """⑤ 时间范围过滤 (含边界)。"""
        t0 = datetime(2026, 8, 5, 0, 0, 0, tzinfo=timezone.utc)
        store.append(ev(EventType.TASK_START, task_id="T-1", timestamp=t0))
        store.append(ev(EventType.TOOL_CALL, task_id="T-1", timestamp=t0 + timedelta(minutes=10)))
        store.append(ev(EventType.TASK_END, task_id="T-1", result="done", timestamp=t0 + timedelta(minutes=30)))

        mid = store.query(after=t0 + timedelta(minutes=5), before=t0 + timedelta(minutes=20))
        assert [e.type.value for e in mid] == ["tool.call"]
        assert len(store.query(after=t0, before=t0 + timedelta(minutes=30))) == 3  # 含边界 (t0 与 t0+30 均命中)

    def test_query_limit_offset(self, store: EventStore):
        """limit/offset 分页 (CLI/Dashboard 预留)。"""
        for i in range(5):
            store.append(ev(EventType.TOOL_CALL, task_id=f"T-{i}"))
        page = store.query(limit=2, offset=1)
        assert [e.seq for e in page] == [2, 3]
        assert [e.seq for e in store.query(offset=3)] == [4, 5]

    def test_query_combined_filters(self, store: EventStore):
        """project + task + agent + type + result 组合过滤。"""
        store.append(ev(EventType.TOOL_CALL, project_id="P-1", task_id="T-1", agent_id="A-1", result="OK"))
        store.append(ev(EventType.TOOL_CALL, project_id="P-1", task_id="T-1", agent_id="A-1", result="ERROR"))
        store.append(ev(EventType.TOOL_CALL, project_id="P-1", task_id="T-1", agent_id="A-2", result="OK"))
        store.append(ev(EventType.CHECKPOINT, project_id="P-1", task_id="T-1", agent_id="A-1", result="OK"))

        got = store.query(project_id="P-1", task_id="T-1", agent_id="A-1",
                          event_type=EventType.TOOL_CALL, result="OK")
        assert len(got) == 1
        assert got[0].seq == 1

    def test_since_incremental_replay(self, store: EventStore):
        """⑥ since(seq) 增量回放 (订阅者用)。"""
        for i in range(4):
            store.append(ev(EventType.TOOL_CALL, task_id="T-1"))
        tail = store.since(2)
        assert [e.seq for e in tail] == [3, 4]

    def test_recent_returns_desc(self, store: EventStore):
        for i in range(3):
            store.append(ev(EventType.TOOL_CALL, task_id="T-1"))
        recent = store.recent(limit=2)
        assert [e.seq for e in recent] == [3, 2]

    def test_get_and_get_by_id(self, store: EventStore):
        e = store.append(ev(EventType.TASK_START, task_id="T-1"))
        assert store.get(1).event_id == e.event_id
        assert store.get_by_id(e.event_id).seq == 1
        assert store.get(999) is None
        assert store.get_by_id("missing") is None

    def test_count_and_count_by_type(self, store: EventStore):
        store.append(ev(EventType.TASK_START, task_id="T-1"))
        store.append(ev(EventType.TOOL_CALL, task_id="T-1"))
        store.append(ev(EventType.TOOL_CALL, task_id="T-1"))
        store.append(ev(EventType.CHECKPOINT, task_id="T-1"))
        assert store.count() == 4
        assert store.count_by_type() == {"tool.call": 2, "task.start": 1, "checkpoint": 1}

    def test_query_events_iterable_cli_preview(self, store: EventStore):
        """CLI 预留: query_events() 返回可迭代, 支持 limit/offset 与过滤。"""
        for i in range(5):
            store.append(ev(EventType.TOOL_CALL, task_id=f"T-{i}"))
        stream = store.query_events(limit=2, offset=1)
        assert iter(stream) is stream  # 可迭代对象
        got = list(stream)
        assert [e.seq for e in got] == [2, 3]
        assert [e.seq for e in store.query_events(task_id="T-0")] == [1]


class TestPersistenceAndMode:
    def test_wal_mode_enabled(self, store: EventStore):
        """⑦ WAL 模式生效。"""
        mode = store._conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_persistence_across_reopen(self, db_path):
        """⑧ 库文件真实落盘、重开可读 (持久化)。"""
        s1 = EventStore(db_path)
        e = s1.append(ev(EventType.CHECKPOINT, task_id="T-1", payload={"artifacts": ["a.py"]}))
        s1.close()

        assert db_path.exists()
        s2 = EventStore(db_path)
        assert s2.count() == 1
        got = s2.get_by_id(e.event_id)
        assert got.payload == {"artifacts": ["a.py"]}
        assert got.timestamp == e.timestamp
        s2.close()

    def test_wal_sidecar_files_created(self, db_path):
        """WAL 模式下产生 -wal 侧文件 (读写并发友好的证据, 连接存活期间存在)。"""
        s = EventStore(db_path)
        s.append(ev(EventType.TASK_START, task_id="T-1"))
        wal = db_path.with_name(db_path.name + "-wal")
        assert wal.exists()  # close() 时会 checkpoint 并回收 wal 文件
        s.close()
