"""test_logger.py — EventLogger 高层 API (phase1-plan §7.1 test_logger 覆盖点 ①-④)。"""

from __future__ import annotations

import threading

import pytest
from pydantic import ValidationError

from events.logger import EventLogger
from events.models import EventType
from events.store import EventStore
from helpers import ev


class TestRecord:
    def test_record_basic(self, store: EventStore):
        logger = EventLogger(store)
        e = logger.record(EventType.TOOL_CALL, source="agent", task_id="T-1",
                          stage="running", action="run", result="OK", payload={"tool": "pytest"})
        assert e.seq == 1
        got = store.get(1)
        assert got.type is EventType.TOOL_CALL
        assert got.payload == {"tool": "pytest"}

    def test_record_rejects_unknown_type(self, store: EventStore):
        logger = EventLogger(store)
        with pytest.raises(ValidationError, match="not.a.type"):
            logger.record("not.a.type", source="agent")


class TestSixConvenienceMethods:
    def test_six_event_types_roundtrip(self, store: EventStore):
        """① 六类便捷方法端到端写入并回读。"""
        logger = EventLogger(store)
        logger.task_start("T-1", title="impl", role="backend")
        logger.task_end("T-1", result="done", duration_s=12.5, artifact="ref://a")
        logger.task_fail("T-2", stage="build", error="compile error", evidence="ref://e")
        logger.tool_call("T-1", tool="pytest", arg_summary="tests", result_summary="42 passed", duration_s=3.1)
        logger.checkpoint("T-1", description="save state", artifacts=["a.py"])
        logger.session_close("S-1")

        assert store.count() == 6
        types = [e.type for e in store.query()]
        assert types == [
            EventType.TASK_START, EventType.TASK_END, EventType.TASK_FAIL,
            EventType.TOOL_CALL, EventType.CHECKPOINT, EventType.SESSION_CLOSE,
        ]
        # 便捷方法自动填充语义列与载荷
        by_id = {e.type: e for e in store.query()}
        assert by_id[EventType.TASK_START].payload == {"title": "impl", "role": "backend"}
        assert by_id[EventType.TASK_END].result == "done"
        assert by_id[EventType.TASK_END].payload["duration_s"] == 12.5
        assert by_id[EventType.TASK_FAIL].payload["error"] == "compile error"
        assert by_id[EventType.CHECKPOINT].payload["artifacts"] == ["a.py"]
        assert by_id[EventType.SESSION_CLOSE].payload["session_id"] == "S-1"

    def test_task_chain_start_tool_checkpoint_end(self, store: EventStore):
        """② 同一 task_id 的 start→tool.call→checkpoint→end 事件链完整、顺序正确。"""
        logger = EventLogger(store)
        logger.task_start("T-1", title="impl", role="backend")
        logger.tool_call("T-1", tool="patch", arg_summary="a.py", result_summary="ok", duration_s=0.5)
        logger.checkpoint("T-1", description="mid-state", artifacts=["a.py"])
        logger.task_end("T-1", result="done", duration_s=30.0)

        chain = store.by_task("T-1")
        assert [e.type.value for e in chain] == ["task.start", "tool.call", "checkpoint", "task.end"]
        assert [e.seq for e in chain] == [1, 2, 3, 4]

    def test_optional_fields_none(self, store: EventStore):
        """④ 字段可空性: agent_id/task_id 为 None 时正常。"""
        logger = EventLogger(store)
        e = logger.session_close("S-1")  # 无 task_id / agent_id
        assert e.task_id is None and e.agent_id is None
        assert store.by_task("missing") == []


class TestConcurrency:
    def test_multithreaded_append_no_loss(self, store: EventStore):
        """③ 多线程并发写 100 条无丢失、seq 无重复。"""
        logger = EventLogger(store)
        n_threads, per_thread = 8, 25

        def worker(tid: int):
            for i in range(per_thread):
                logger.tool_call(f"T-{tid}-{i}", tool="x", arg_summary="a", result_summary="r", duration_s=0.1)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert store.count() == n_threads * per_thread
        seqs = [e.seq for e in store.query()]
        assert seqs == list(range(1, n_threads * per_thread + 1))  # 无重复、无空洞

    def test_concurrent_same_task_chain_keeps_order(self, store: EventStore):
        """并发下同一任务的 seq 仍单调且不互相覆盖。"""
        logger = EventLogger(store)
        barrier = threading.Barrier(2)

        def worker(agent: str):
            barrier.wait()
            for i in range(20):
                logger.tool_call("T-shared", tool="x", agent_id=agent,
                                 arg_summary="a", result_summary="r", duration_s=0.1)

        threads = [threading.Thread(target=worker, args=(a,)) for a in ("A-1", "A-2")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        chain = store.by_task("T-shared")
        assert len(chain) == 40
        assert [e.seq for e in chain] == list(range(1, 41))
