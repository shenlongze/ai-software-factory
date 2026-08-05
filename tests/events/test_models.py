"""test_models.py — Event 模型校验 (phase1-plan §7.1: ①-⑤ 覆盖点)。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from events.models import Event, EventType, format_timestamp, parse_timestamp


class TestEventType:
    def test_six_event_type_members(self):
        """六类最小事件齐全 (Phase 1, ADR-0001); ADR-0002 增量扩展类别前缀存在。"""
        values = [t.value for t in EventType]
        # Phase 1 六类最小事件 (event-model.md §3 最小集) 全部保留
        for v in ("task.start", "task.end", "task.fail", "tool.call", "checkpoint", "session.close"):
            assert v in values
        # ADR-0002 Phase 2 扩展: 类别前缀各至少 1 个 (task./tool./system./validation.)
        for prefix in ("task.", "tool.", "system.", "validation."):
            assert any(v.startswith(prefix) for v in values), f"缺少 {prefix!r} 前缀事件"
        # 增量扩展后成员数 > 最小六类
        assert len(values) > 6

    def test_event_type_is_str_enum(self):
        """str 枚举: 值可直接存 SQLite type 列。"""
        assert EventType.TASK_START == "task.start"
        assert isinstance(EventType.TASK_START, str)


class TestEventConstruction:
    def test_construct_with_defaults(self):
        """① 合法事件构造成功; ④ 默认值: event_id/timestamp 自动生成, seq=0, payload={}。"""
        e = Event(type=EventType.TASK_START, source="cli")
        assert e.seq == 0
        assert len(e.event_id) == 32  # uuid4().hex
        assert e.timestamp.tzinfo is not None
        assert e.payload == {}
        assert e.task_id is None and e.agent_id is None

    def test_create_factory_generates_id_and_timestamp(self):
        """factory 方法: 生成 uuid event_id + UTC 时间戳, 语义列可填。"""
        e = Event.create(
            EventType.TASK_END, source="orchestrator", task_id="T-1",
            stage="done", action="finish", result="done", payload={"duration_s": 3.2},
        )
        assert len(e.event_id) == 32
        assert e.timestamp.tzinfo is not None
        assert e.type is EventType.TASK_END
        assert e.stage == "done" and e.result == "done"
        assert e.payload == {"duration_s": 3.2}

    def test_create_accepts_type_string(self):
        """type 传字符串 (如未来扩类) 自动转为枚举。"""
        e = Event.create("task.start", source="cli", task_id="T-1")
        assert e.type is EventType.TASK_START

    def test_required_fields_missing_rejected(self):
        """缺必填 type/source 拒绝。"""
        with pytest.raises(ValidationError):
            Event(source="cli")
        with pytest.raises(ValidationError):
            Event(type=EventType.TASK_START)

    def test_invalid_type_rejected(self):
        """② 非法 type 拒绝。"""
        with pytest.raises(ValidationError):
            Event(type="bogus.event", source="cli")

    def test_payload_json_safe_rejected(self):
        """③ 非 JSON payload (set) 拒绝入库。"""
        with pytest.raises(ValidationError):
            Event(type=EventType.TOOL_CALL, source="cli", payload={"bad": {1, 2}})

    def test_payload_datetime_rejected(self):
        """非 JSON payload (datetime) 拒绝。"""
        with pytest.raises(ValidationError):
            Event(type=EventType.TOOL_CALL, source="cli", payload={"when": datetime.now(timezone.utc)})

    def test_payload_nested_dict_ok(self):
        """JSON 友好嵌套 payload 接受。"""
        e = Event(type=EventType.CHECKPOINT, source="cli", payload={"files": {"a.py": "hash1"}})
        assert e.payload["files"]["a.py"] == "hash1"


class TestImmutability:
    def test_event_is_frozen(self):
        """不可变: 字段赋值被拒绝。"""
        e = Event(type=EventType.TASK_START, source="cli")
        with pytest.raises(ValidationError):
            e.event_id = "hacked"

    def test_seq_backfill_via_model_copy(self):
        """不可变模型下 seq 回填用 model_copy(update=...), 原实例不变。"""
        e = Event(type=EventType.TASK_START, source="cli")
        backfilled = e.model_copy(update={"seq": 42})
        assert backfilled.seq == 42
        assert e.seq == 0


class TestSerialization:
    def test_json_roundtrip(self):
        """model_dump_json → model_validate_json 往返一致。"""
        e = Event.create(
            EventType.TOOL_CALL, source="agent", task_id="T-1", agent_id="A-1",
            stage="running", action="run tests", result="OK",
            payload={"tool": "pytest", "duration_s": 1.5},
        )
        restored = Event.model_validate_json(e.model_dump_json())
        assert restored == e
        assert restored.type is EventType.TOOL_CALL

    def test_to_row_serialization(self):
        """⑤ to_row() 序列化正确: 时间统一格式, payload 为 JSON 字符串。"""
        e = Event.create(
            EventType.TASK_FAIL, source="cli", task_id="T-1",
            result="failed", payload={"error": "boom", "stage": "build"},
        )
        row = e.to_row()
        assert row[0] == e.event_id
        assert row[1] == format_timestamp(e.timestamp)
        assert row[2] == "task.fail"
        assert json.loads(row[11]) == {"error": "boom", "stage": "build"}

    def test_from_row_roundtrip(self):
        """to_row → from_row 往返一致 (含 seq 回填与语义列)。"""
        e = Event.create(
            EventType.CHECKPOINT, source="agent", project_id="P-1", task_id="T-1",
            stage="checkpoint", action="save state", result="OK",
            evidence="ref://artifacts/T-1/chk-1", payload={"artifacts": ["a.py"]},
        )
        row = e.to_row()
        restored = Event.from_row(dict(zip(
            ["event_id", "timestamp", "type", "source", "project_id", "task_id", "agent_id",
             "stage", "action", "result", "evidence", "payload"],
            row,
        )) | {"seq": 7})
        assert restored == e.model_copy(update={"seq": 7})

    def test_timestamp_format_fixed(self):
        """时间存储格式固定 (字符串排序 == 时间排序)。"""
        ts = datetime(2026, 8, 5, 10, 32, 10, 123456, tzinfo=timezone.utc)
        s = format_timestamp(ts)
        assert s == "2026-08-05T10:32:10.123456Z"
        assert parse_timestamp(s) == ts
