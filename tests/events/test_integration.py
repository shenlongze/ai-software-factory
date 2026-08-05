"""test_integration.py — 完整链路 (phase1-plan §9 验收清单对应的端到端场景)。"""

from __future__ import annotations

import sqlite3

import pytest
from pydantic import ValidationError

from events.logger import EventLogger
from events.metrics import compute_metrics, metrics_by_session
from events.models import EventType
from events.store import EventStore


class TestFullPipeline:
    def test_create_write_query_metrics(self, db_path):
        """完整链路: 创建→写→查→指标。"""
        with EventStore(db_path) as store:
            logger = EventLogger(store)

            logger.task_start("T-1", title="impl logger", role="backend", project_id="P-factory")
            logger.tool_call("T-1", tool="pytest", arg_summary="-q", result_summary="42 passed",
                             duration_s=2.0, project_id="P-factory")
            logger.checkpoint("T-1", description="mid", artifacts=["models.py"], project_id="P-factory")
            logger.task_end("T-1", result="done", duration_s=60.0, project_id="P-factory")
            logger.task_start("T-2", title="impl store", role="backend", project_id="P-factory")
            logger.task_fail("T-2", stage="build", error="sqlite mismatch", project_id="P-factory")

            # 查询
            assert store.count() == 6
            assert len(store.by_project("P-factory")) == 6
            assert len(store.by_task("T-1")) == 4
            assert len(store.by_type(EventType.TASK_FAIL)) == 1

            # 指标
            m = compute_metrics(store.query(), project_id="P-factory")
            assert m.task_count == 2
            assert m.success_count == 1
            assert m.fail_count == 1
            assert m.success_rate == 0.5
            assert m.tool_call_count == 1
            assert m.interrupted_count == 0
            # 便捷方法的 duration_s 落在 payload, 事件链可回读
            assert store.by_task("T-1")[3].payload["duration_s"] == 60.0

            # 持久化
            store.close()
        with EventStore(db_path) as reopened:
            assert reopened.count() == 6
            assert reopened.by_task("T-1")[-1].result == "done"


class TestFailureRecovery:
    def test_failed_task_replay_chain(self, store: EventStore):
        """验收项: 失败任务按 task_id 回放出失败前的完整事件链 (证据可追溯)。"""
        logger = EventLogger(store)
        logger.task_start("T-fail", title="risky", role="frontend")
        logger.tool_call("T-fail", tool="patch", arg_summary="ui.py", result_summary="ok", duration_s=0.3)
        logger.checkpoint("T-fail", description="before-verify", artifacts=["ui.py"])
        logger.task_fail("T-fail", stage="verify", error="L2 check failed", evidence="ref://artifacts/T-fail/val.log")

        chain = store.by_task("T-fail")
        assert [e.type.value for e in chain] == ["task.start", "tool.call", "checkpoint", "task.fail"]
        # 断点恢复锚点: checkpoint 在 fail 之前, 可从其 seq 续跑
        cp = chain[2]
        tail = store.by_task("T-fail", since_seq=cp.seq)
        assert [e.type.value for e in tail] == ["task.fail"]
        assert tail[0].evidence == "ref://artifacts/T-fail/val.log"

    def test_error_corrected_by_new_event(self, store: EventStore):
        """append-only 纠错模式: 写错不发 UPDATE, 补发新事件纠正。"""
        logger = EventLogger(store)
        logger.task_start("T-1", title="a", role="b")
        logger.task_fail("T-1", stage="build", error="flaky env")
        logger.task_start("T-1", title="a", role="b")          # 重试
        logger.task_end("T-1", result="done", duration_s=5.0)  # 新事件纠正

        chain = store.by_task("T-1")
        assert [e.type.value for e in chain] == ["task.start", "task.fail", "task.start", "task.end"]
        # plan 口径: fail_count = task.fail 事件数, 计入分母
        m = compute_metrics(store.query())
        assert m.success_rate == 0.5
        assert m.avg_retry_count == 1.0


class TestThreeSessions:
    def test_three_sessions_metrics_comparison(self, db_path):
        """验收项: 连续 3 个会话的指标 (成功率/耗时/重试) 可对比。"""
        with EventStore(db_path) as store:
            logger = EventLogger(store)
            # S-1: 一次成功
            logger.record(EventType.TASK_START, source="orchestrator", task_id="T-1",
                          stage="running", result="OK", payload={"session_id": "S-1"})
            logger.record(EventType.TASK_END, source="orchestrator", task_id="T-1",
                          stage="done", result="done", payload={"session_id": "S-1", "result": "done"})
            # S-2: 一次失败
            logger.record(EventType.TASK_START, source="orchestrator", task_id="T-2",
                          stage="running", result="OK", payload={"session_id": "S-2"})
            logger.record(EventType.TASK_FAIL, source="orchestrator", task_id="T-2",
                          stage="failed", result="failed", payload={"session_id": "S-2"})
            # S-3: 一次重试后成功
            logger.record(EventType.TASK_START, source="orchestrator", task_id="T-3",
                          stage="running", result="OK", payload={"session_id": "S-3"})
            logger.record(EventType.TASK_START, source="orchestrator", task_id="T-3",
                          stage="running", result="OK", payload={"session_id": "S-3"})
            logger.record(EventType.TASK_END, source="orchestrator", task_id="T-3",
                          stage="done", result="done", payload={"session_id": "S-3", "result": "done"})

            by_session = metrics_by_session(store.query())
            assert sorted(by_session) == ["S-1", "S-2", "S-3"]
            assert by_session["S-1"].success_rate == 1.0
            assert by_session["S-2"].success_rate == 0.0
            assert by_session["S-3"].success_rate == 1.0
            assert by_session["S-3"].avg_retry_count == 1.0


class TestAppendOnlyEndToEnd:
    def test_append_only_enforced_everywhere(self, store: EventStore):
        """端到端 append-only: 应用层无入口 + 数据库层触发器。"""
        logger = EventLogger(store)
        logger.task_start("T-1", title="a", role="b")
        logger.tool_call("T-1", tool="x", arg_summary="a", result_summary="r", duration_s=0.1)

        assert not hasattr(logger, "update") and not hasattr(store, "update")
        assert not hasattr(logger, "delete") and not hasattr(store, "delete")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store._conn.execute("UPDATE events SET source='x' WHERE seq=1")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store._conn.execute("DELETE FROM events WHERE seq=2")

    def test_invalid_event_rejected_end_to_end(self, store: EventStore):
        """非法事件 (未知类型/非 JSON payload) 端到端拒绝, 库不受污染。"""
        logger = EventLogger(store)
        with pytest.raises(ValidationError):
            logger.record("bogus.type", source="cli")
        with pytest.raises(ValidationError):
            logger.record(EventType.TOOL_CALL, source="cli", task_id="T-1",
                          payload={"bad": {1, 2}})  # set 非 JSON
        assert store.count() == 0


class TestCliPreview:
    def test_query_events_stream_with_filters(self, store: EventStore):
        """CLI 预留接口 (factory logs/status): 可迭代 + 过滤 + limit/offset。"""
        logger = EventLogger(store)
        for i in range(5):
            logger.tool_call(f"T-{i}", tool="x", arg_summary="a", result_summary="r", duration_s=0.1)
        logger.checkpoint("T-0", description="cp")

        stream = store.query_events(event_type=EventType.TOOL_CALL, limit=2, offset=3)
        got = list(stream)
        assert [e.seq for e in got] == [4, 5]
        assert [e.seq for e in store.query_events(limit=2)] == [1, 2]
        assert [e.type for e in store.query_events()] == [EventType.TOOL_CALL] * 5 + [EventType.CHECKPOINT]
