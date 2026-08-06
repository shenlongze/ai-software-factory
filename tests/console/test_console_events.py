"""tests/console/test_console_events.py — console.* 3 事件链序与 payload 契约 (Phase 11A, ADR-0034)。

覆盖 (factory-console/events.py):
- EventType 枚举已含 console.viewed / console.approval.opened /
  console.dashboard.viewed (events/models.py 纯增量扩展, ADR-0001 路径)
- console.viewed: {view, count, project_id?, extra 合并} — 通用视图审计
- console.approval.opened: {approval_id, artifact_id, gate, status} —
  审批详情只读打开 (非决定: 不携带 approve/reject 指令)
- console.dashboard.viewed: 七域计数 {projects, pending_approvals,
  running_agents, decisions, total_cost, experiences, events}
- source == "console"; stage/action/result 语义列
- logger=None → 静默返回 None (同 product/intelligence 事件辅助模式)
- 链序: 三事件按调用序落库 (append-only, seq 单调)
- CLI 集成: factory console dashboard → console.dashboard.viewed;
  factory console approvals → console.viewed (view=approvals)

basename 全仓库唯一 (test_console_* 前缀)。
"""

from __future__ import annotations

import json

from events.models import EventType
from events.store import EventStore

from console_helpers import event_sequence, payload_of

console_events = __import__("importlib").import_module("factory-console.events")
SOURCE = console_events.SOURCE


def _run_cli(root, *argv) -> int:
    from cli.main import main

    return main(["--root", str(root), *argv])


# ------------------------------------------------------------------ 枚举扩展


class TestEventTypeExtension:
    def test_console_event_types_registered(self):
        """EventType 枚举纯增量含 console.* 三值 (ADR-0034, ADR-0001 路径)。"""
        values = {t.value for t in EventType}
        assert "console.viewed" in values
        assert "console.approval.opened" in values
        assert "console.dashboard.viewed" in values

    def test_source_constant(self):
        assert SOURCE == "console"


# ------------------------------------------------------------------ console.viewed


class TestConsoleViewed:
    def test_payload_contract(self, event_logger, event_store):
        ev = console_events.record_console_viewed(
            event_logger, view="projects", count=3,
            extra={"projects": ["demo", "other"]},
        )
        assert ev is not None
        assert ev.type is EventType.CONSOLE_VIEWED
        assert ev.source == "console"
        assert ev.stage == "viewed"
        assert ev.action == "view console projects"
        assert ev.result == "OK"
        assert ev.payload == {"view": "projects", "count": 3, "projects": ["demo", "other"]}

    def test_project_id_in_payload_and_column(self, event_logger, event_store):
        ev = console_events.record_console_viewed(
            event_logger, view="lifecycle", count=1, project_id="demo",
        )
        assert ev.project_id == "demo"
        assert ev.payload["project_id"] == "demo"

    def test_no_extra_payload_minimal(self, event_logger, event_store):
        ev = console_events.record_console_viewed(event_logger, view="approvals", count=0)
        assert ev.payload == {"view": "approvals", "count": 0}

    def test_none_logger_silent(self, event_store):
        """logger=None → 静默返回 None, 不写事件 (辅助函数失败安全)。"""
        assert console_events.record_console_viewed(None, view="x", count=0) is None
        assert console_events.record_console_approval_opened(
            None, approval_id="r", artifact_id="a", gate="g", status="pending",
        ) is None
        assert console_events.record_console_dashboard_viewed(
            None, projects=0, pending_approvals=0, running_agents=0,
            decisions=0, total_cost=0.0, experiences=0, events=0,
        ) is None
        assert event_store.query() == []


# ------------------------------------------------------------------ console.approval.opened


class TestConsoleApprovalOpened:
    def test_payload_contract(self, event_logger, event_store):
        ev = console_events.record_console_approval_opened(
            event_logger,
            approval_id="req-1", artifact_id="art-1", gate="prd",
            status="pending", project_id="demo",
        )
        assert ev is not None
        assert ev.type is EventType.CONSOLE_APPROVAL_OPENED
        assert ev.source == "console"
        assert ev.stage == "opened"
        assert ev.action == "open approval detail"
        assert ev.result == "OK"
        assert ev.project_id == "demo"
        assert ev.payload == {
            "approval_id": "req-1",
            "artifact_id": "art-1",
            "gate": "prd",
            "status": "pending",
        }
        # 只读打开: payload 不携带任何 approve/reject/changes_requested 指令
        assert not any(
            k in ev.payload for k in ("decision", "action_taken", "approved")
        )


# ------------------------------------------------------------------ console.dashboard.viewed


class TestConsoleDashboardViewed:
    def test_seven_domain_payload(self, event_logger, event_store):
        ev = console_events.record_console_dashboard_viewed(
            event_logger,
            projects=1, pending_approvals=2, running_agents=1,
            decisions=3, total_cost=0.25, experiences=4, events=5,
        )
        assert ev is not None
        assert ev.type is EventType.CONSOLE_DASHBOARD_VIEWED
        assert ev.source == "console"
        assert ev.stage == "viewed"
        assert ev.action == "view console dashboard"
        assert ev.result == "OK"
        assert ev.payload == {
            "projects": 1,
            "pending_approvals": 2,
            "running_agents": 1,
            "decisions": 3,
            "total_cost": 0.25,
            "experiences": 4,
            "events": 5,
        }

    def test_total_cost_rounded(self, event_logger, event_store):
        ev = console_events.record_console_dashboard_viewed(
            event_logger,
            projects=0, pending_approvals=0, running_agents=0,
            decisions=0, total_cost=0.123456789, experiences=0, events=0,
        )
        assert ev.payload["total_cost"] == 0.123457  # round(…, 6)


# ------------------------------------------------------------------ 链序


class TestEventChainOrder:
    def test_three_events_in_call_order(self, event_logger, event_store):
        """三事件按调用序落库 (append-only, seq 单调递增)。"""
        console_events.record_console_dashboard_viewed(
            event_logger,
            projects=0, pending_approvals=0, running_agents=0,
            decisions=0, total_cost=0.0, experiences=0, events=0,
        )
        console_events.record_console_approval_opened(
            event_logger, approval_id="req-1", artifact_id="art-1",
            gate="prd", status="pending",
        )
        console_events.record_console_viewed(
            event_logger, view="providers", count=1,
        )
        assert event_sequence(event_store) == [
            "console.dashboard.viewed",
            "console.approval.opened",
            "console.viewed",
        ]

    def test_cli_dashboard_event_chain(self, tmp_path, capsys):
        """CLI 集成: dashboard 写 console.dashboard.viewed (七域计数 payload)。"""
        rc = _run_cli(tmp_path, "console", "dashboard", "--json")
        assert rc == 0
        db = EventStore(tmp_path / "factory.db")
        try:
            assert event_sequence(db) == ["console.dashboard.viewed"]
            payload = payload_of(db, "console.dashboard.viewed")
        finally:
            db.close()
        for key in ("projects", "pending_approvals", "running_agents",
                    "decisions", "total_cost", "experiences", "events"):
            assert key in payload

    def test_cli_approvals_event_chain(self, tmp_path, capsys):
        """CLI 集成: approvals 写 console.viewed (view=approvals, count)。"""
        rc = _run_cli(tmp_path, "console", "approvals", "--json")
        assert rc == 0
        db = EventStore(tmp_path / "factory.db")
        try:
            assert event_sequence(db) == ["console.viewed"]
            payload = payload_of(db, "console.viewed")
        finally:
            db.close()
        assert payload["view"] == "approvals"
        assert payload["count"] == 0
        assert payload["pending"] == 0
        assert payload["pending_only"] is False

    def test_cli_dashboard_json_reports_event_seq(self, tmp_path, capsys):
        """--json 输出携带 event 名与 event_seq (审计锚点可查)。"""
        rc = _run_cli(tmp_path, "console", "dashboard", "--json")
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["event"] == "console.dashboard.viewed"
        assert isinstance(data["event_seq"], int)
