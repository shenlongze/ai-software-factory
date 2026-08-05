"""test_metrics.py — 指标聚合正确性 (phase1-plan §7.1 test_metrics 覆盖点 ①-⑤)。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from events.metrics import AgentMetrics, Metrics, compute_metrics, metrics_by_agent, metrics_by_day, metrics_by_session
from events.models import EventType
from helpers import ev

T0 = datetime(2026, 8, 5, 10, 0, 0, tzinfo=timezone.utc)


class TestCoreAggregation:
    def test_empty_stream_returns_zeros(self):
        """⑤ 空事件流返回零值不报错。"""
        m = compute_metrics([])
        assert m.task_count == 0
        assert m.success_count == 0 and m.fail_count == 0
        assert m.success_rate == 0.0
        assert m.avg_task_duration_s == 0.0
        assert m.avg_retry_count == 0.0
        assert m.tool_call_count == 0
        assert m.interrupted_count == 0
        assert m.event_count == 0

    def test_success_rate_with_failures(self):
        """① 成功率计算正确 (含失败任务): 2 done + 1 fail → 2/3。"""
        events = [
            ev(EventType.TASK_START, task_id="T-1"),
            ev(EventType.TASK_END, task_id="T-1", result="done", payload={"result": "done"}),
            ev(EventType.TASK_START, task_id="T-2"),
            ev(EventType.TASK_END, task_id="T-2", result="done", payload={"result": "done"}),
            ev(EventType.TASK_START, task_id="T-3"),
            ev(EventType.TASK_FAIL, task_id="T-3", result="failed"),
        ]
        m = compute_metrics(events)
        assert m.task_count == 3
        assert m.success_count == 2
        assert m.fail_count == 1
        assert m.success_rate == 2 / 3

    def test_task_duration_end_minus_start(self):
        """② 耗时 = end − start (取最后一次 start)。"""
        events = [
            ev(EventType.TASK_START, task_id="T-1", timestamp=T0),
            ev(EventType.TASK_END, task_id="T-1", result="done",
               payload={"result": "done"}, timestamp=T0 + timedelta(seconds=90)),
        ]
        m = compute_metrics(events)
        assert m.avg_task_duration_s == 90.0

    def test_retry_count_same_task_two_starts(self):
        """③ 重试计数正确: 同一任务 start 2 次 = 1 次重试。"""
        events = [
            ev(EventType.TASK_START, task_id="T-1", timestamp=T0),
            ev(EventType.TASK_START, task_id="T-1", timestamp=T0 + timedelta(seconds=10)),
            ev(EventType.TASK_END, task_id="T-1", result="done",
               payload={"result": "done"}, timestamp=T0 + timedelta(seconds=100)),
        ]
        m = compute_metrics(events)
        assert m.avg_retry_count == 1.0
        assert m.avg_task_duration_s == 90.0  # 耗时取最后一次 start

    def test_tool_call_count_and_per_task(self):
        events = [
            ev(EventType.TASK_START, task_id="T-1"),
            ev(EventType.TOOL_CALL, task_id="T-1"),
            ev(EventType.TOOL_CALL, task_id="T-1"),
            ev(EventType.TASK_END, task_id="T-1", result="done", payload={"result": "done"}),
            ev(EventType.TASK_START, task_id="T-2"),
            ev(EventType.TOOL_CALL, task_id="T-2"),
        ]
        m = compute_metrics(events)
        assert m.tool_call_count == 3
        assert m.avg_tool_calls_per_task == 1.5

    def test_interrupted_count_checkpoint_without_end(self):
        """中断: checkpoint 后无 task.end 的任务数。"""
        events = [
            ev(EventType.TASK_START, task_id="T-1"),
            ev(EventType.CHECKPOINT, task_id="T-1"),
            ev(EventType.TASK_END, task_id="T-1", result="done", payload={"result": "done"}),
            ev(EventType.TASK_START, task_id="T-2"),
            ev(EventType.CHECKPOINT, task_id="T-2"),   # 中断: 无 end
            ev(EventType.TASK_START, task_id="T-3"),
        ]
        m = compute_metrics(events)
        assert m.interrupted_count == 1

    def test_event_count(self):
        events = [ev(EventType.TASK_START, task_id="T-1"), ev(EventType.TOOL_CALL, task_id="T-1")]
        assert compute_metrics(events).event_count == 2

    def test_result_counts_distribution(self):
        """按 result 语义列计数 (validation 结果统计的承载口径)。"""
        events = [
            ev(EventType.TASK_START, task_id="T-1", result="OK"),
            ev(EventType.TOOL_CALL, task_id="T-1", result="OK"),
            ev(EventType.TOOL_CALL, task_id="T-1", result="ERROR"),
            ev(EventType.TASK_END, task_id="T-1", result="done", payload={"result": "done"}),
            ev(EventType.TASK_FAIL, task_id="T-2", result="failed"),
        ]
        m = compute_metrics(events)
        assert m.result_counts == {"OK": 2, "ERROR": 1, "done": 1, "failed": 1}


class TestGrouping:
    def test_metrics_by_day(self):
        """④ 按 day 分组正确。"""
        d1 = datetime(2026, 8, 5, 10, 0, 0, tzinfo=timezone.utc)
        d2 = datetime(2026, 8, 6, 10, 0, 0, tzinfo=timezone.utc)
        events = [
            ev(EventType.TASK_START, task_id="T-1", timestamp=d1),
            ev(EventType.TASK_END, task_id="T-1", result="done", payload={"result": "done"}, timestamp=d1),
            ev(EventType.TASK_START, task_id="T-2", timestamp=d2),
            ev(EventType.TASK_END, task_id="T-2", result="done", payload={"result": "done"}, timestamp=d2),
        ]
        by_day = metrics_by_day(events)
        assert sorted(by_day) == ["2026-08-05", "2026-08-06"]
        assert by_day["2026-08-05"].task_count == 1
        assert by_day["2026-08-06"].task_count == 1
        assert by_day["2026-08-06"].success_count == 1

    def test_metrics_by_session(self):
        """④ 按 session 分组正确 (组键 = payload.session_id)。"""
        events = [
            ev(EventType.TASK_START, task_id="T-1", payload={"session_id": "S-1"}),
            ev(EventType.TASK_END, task_id="T-1", result="done",
               payload={"session_id": "S-1", "result": "done"}),
            ev(EventType.TASK_START, task_id="T-2", payload={"session_id": "S-2"}),
            ev(EventType.TASK_FAIL, task_id="T-2", result="failed", payload={"session_id": "S-2"}),
        ]
        by_session = metrics_by_session(events)
        assert sorted(by_session) == ["S-1", "S-2"]
        assert by_session["S-1"].success_rate == 1.0
        assert by_session["S-2"].success_rate == 0.0
        assert by_session["S-2"].fail_count == 1

    def test_metrics_by_agent(self):
        """按 agent 分组: 执行次数 / 工具调用 / 成败。"""
        events = [
            ev(EventType.TASK_START, task_id="T-1", agent_id="A-1"),
            ev(EventType.TOOL_CALL, task_id="T-1", agent_id="A-1"),
            ev(EventType.TOOL_CALL, task_id="T-1", agent_id="A-1"),
            ev(EventType.TASK_END, task_id="T-1", result="done",
               agent_id="A-1", payload={"result": "done"}),
            ev(EventType.TASK_START, task_id="T-2", agent_id="A-2"),
            ev(EventType.TASK_FAIL, task_id="T-2", result="failed", agent_id="A-2"),
        ]
        by_agent = metrics_by_agent(events)
        assert set(by_agent) == {"A-1", "A-2"}
        a1: AgentMetrics = by_agent["A-1"]
        assert a1.event_count == 4
        assert a1.tool_call_count == 2
        assert a1.task_count == 1
        assert a1.success_count == 1 and a1.fail_count == 0
        assert by_agent["A-2"].fail_count == 1

    def test_project_filter(self):
        """按 project 过滤后再聚合。"""
        events = [
            ev(EventType.TASK_START, task_id="T-1", project_id="P-1"),
            ev(EventType.TASK_END, task_id="T-1", result="done",
               project_id="P-1", payload={"result": "done"}),
            ev(EventType.TASK_START, task_id="T-2", project_id="P-2"),
            ev(EventType.TASK_FAIL, task_id="T-2", result="failed", project_id="P-2"),
        ]
        m_p1 = compute_metrics(events, project_id="P-1")
        assert m_p1.task_count == 1
        assert m_p1.success_rate == 1.0
        by_agent = metrics_by_agent(events, project_id="P-2")
        assert set(by_agent) == set()  # 无 agent_id 事件 → 空


class TestMarkdown:
    def test_to_markdown(self):
        m = compute_metrics([ev(EventType.TASK_START, task_id="T-1")])
        md = m.to_markdown()
        assert "## Metrics (all)" in md
        assert "task_count: 1" in md
        assert "success_rate" in md
        assert isinstance(md, str)

    def test_metrics_serializable(self):
        """Metrics 是 Pydantic 模型, 可 JSON 序列化 (Phase 2 Dashboard 直接消费)。"""
        m = compute_metrics([ev(EventType.TASK_START, task_id="T-1")])
        assert Metrics.model_validate_json(m.model_dump_json()) == m
