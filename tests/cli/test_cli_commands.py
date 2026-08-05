"""test_commands.py — CLI 各命令行为 + Event 集成断言 (phase2 核心要求)。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from events.models import EventType
from events.store import EventStore
from cli_helpers import event_types, open_events, run_cli, task_ids


class TestInit:
    def test_init_creates_skeleton_and_event(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(capsys, cli_root, "init")
        assert rc == 0
        for d in ("tasks", "agents", "workflows", "events"):
            assert (cli_root / d).is_dir()
        assert (cli_root / "factory.db").exists()
        with open_events(cli_root) as store:
            assert event_types(store) == ["system.init"]
            ev = store.get(1)
            assert ev.type is EventType.SYSTEM_INIT
            assert ev.source == "cli"
            assert ev.payload["root"] == str(cli_root)

    def test_init_idempotent(self, capsys, cli_root: Path):
        rc1, _, _ = run_cli(capsys, cli_root, "init")
        rc2, _, _ = run_cli(capsys, cli_root, "init")
        assert rc1 == rc2 == 0
        with open_events(cli_root) as store:
            assert store.count() == 2  # 每次 init 一条 system.init

    def test_init_json(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(capsys, cli_root, "init", "--json")
        assert rc == 0
        d = json.loads(out)
        assert d["ok"] is True
        assert "tasks" in d["dirs"]


class TestTaskCreate:
    def test_create_writes_task_and_event(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(
            capsys, cli_root, "task", "create", "--id", "T-001",
            "--title", "实现撤销/重做", "--project", "markpad", "--type", "feature",
        )
        assert rc == 0
        assert "T-001" in out
        assert task_ids(cli_root) == ["T-001"]
        with open_events(cli_root) as store:
            types = event_types(store)
            assert types == ["task.created"]
            ev = store.get(1)
            assert ev.type is EventType.TASK_CREATED
            assert ev.task_id == "T-001"
            assert ev.project_id == "markpad"
            assert ev.stage == "backlog"
            assert ev.payload["title"] == "实现撤销/重做"

    def test_create_auto_id(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "task", "create", "--title", "first")
        rc, out, _ = run_cli(capsys, cli_root, "task", "create", "--title", "second")
        assert rc == 0
        assert task_ids(cli_root) == ["T-001", "T-002"]

    def test_create_duplicate_exit_1(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "a")
        rc, _, err = run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "b")
        assert rc == 1
        assert "already exists" in err

    def test_create_missing_title_exit_2(self, capsys, cli_root: Path):
        with pytest.raises(SystemExit) as exc:
            run_cli(capsys, cli_root, "task", "create", "--id", "T-001")
        assert exc.value.code == 2


class TestTaskList:
    def test_list_filters_and_event(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "a", "--project", "p1")
        run_cli(capsys, cli_root, "task", "create", "--id", "T-002", "--title", "b", "--project", "p2")
        run_cli(capsys, cli_root, "task", "update", "T-002", "--status", "DEVELOPMENT")

        rc, out, _ = run_cli(capsys, cli_root, "task", "list", "--status", "DEVELOPMENT")
        assert rc == 0
        assert "T-002" in out and "T-001" not in out
        assert "1 tasks" in out

        rc2, out2, _ = run_cli(capsys, cli_root, "task", "list", "--project", "p1")
        assert rc2 == 0
        assert "T-001" in out2 and "T-002" not in out2

        with open_events(cli_root) as store:
            viewed = [e for e in store.query(event_type=EventType.TASK_VIEWED) if e.action == "list tasks"]
            assert len(viewed) == 2
            assert viewed[0].payload["count"] == 1
            assert viewed[0].payload["status"] == "DEVELOPMENT"

    def test_list_invalid_status_exit_2(self, capsys, cli_root: Path):
        rc, _, err = run_cli(capsys, cli_root, "task", "list", "--status", "BOGUS")
        assert rc == 2
        assert "invalid task status" in err

    def test_list_json(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "a")
        rc, out, _ = run_cli(capsys, cli_root, "task", "list", "--json")
        assert rc == 0
        d = json.loads(out)
        assert d["count"] == 1
        assert d["tasks"][0]["id"] == "T-001"
        assert d["tasks"][0]["status"] == "BACKLOG"


class TestTaskStatus:
    def test_status_detail_with_timeline(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "a")
        rc, out, _ = run_cli(capsys, cli_root, "task", "status", "T-001")
        assert rc == 0
        assert "T-001" in out and "BACKLOG" in out
        assert "时间线" in out and "task.created" in out
        with open_events(cli_root) as store:
            viewed = [e for e in store.query(event_type=EventType.TASK_VIEWED) if e.action == "show task"]
            assert len(viewed) == 1
            assert viewed[0].task_id == "T-001"

    def test_status_missing_exit_7(self, capsys, cli_root: Path):
        rc, _, err = run_cli(capsys, cli_root, "task", "status", "T-999")
        assert rc == 7
        assert "task not found" in err

    def test_status_json(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "a")
        rc, out, _ = run_cli(capsys, cli_root, "task", "status", "T-001", "--json")
        assert rc == 0
        d = json.loads(out)
        assert d["task"]["id"] == "T-001"
        assert isinstance(d["timeline"], list)


class TestTaskUpdate:
    def test_update_status_event(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "a")
        rc, out, _ = run_cli(capsys, cli_root, "task", "update", "T-001", "--status", "development")
        assert rc == 0
        assert "DEVELOPMENT" in out
        with open_events(cli_root) as store:
            ev = [e for e in store.query(event_type=EventType.TASK_UPDATED)][0]
            assert ev.task_id == "T-001"
            assert ev.payload == {"from": "BACKLOG", "to": "DEVELOPMENT"}
            assert ev.stage == "development"

    def test_update_missing_exit_7(self, capsys, cli_root: Path):
        rc, _, err = run_cli(capsys, cli_root, "task", "update", "T-999", "--status", "DONE")
        assert rc == 7

    def test_update_invalid_status_exit_2(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "a")
        rc, _, _ = run_cli(capsys, cli_root, "task", "update", "T-001", "--status", "nope")
        assert rc == 2


class TestEventLogs:
    def test_logs_desc_order_limit(self, capsys, cli_root: Path):
        for i in range(3):
            run_cli(capsys, cli_root, "task", "create", "--id", f"T-00{i + 1}", "--title", f"t{i}")
        rc, out, _ = run_cli(capsys, cli_root, "event", "logs", "--limit", "2")
        assert rc == 0
        assert "2 events" in out
        # 倒序: 最新两条是 task.created #3 和 #2 (system.logs_viewed 在查询之后写入, 不在结果内)
        with open_events(cli_root) as store:
            assert event_types(store)[-1] == "system.logs_viewed"
            tail = store.query()[-3:-1]  # 结果内两条 (排除刚写入的 logs_viewed)
            assert [e.type.value for e in tail] == ["task.created", "task.created"]

    def test_logs_filter_task(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "a", "--project", "p1")
        run_cli(capsys, cli_root, "task", "create", "--id", "T-002", "--title", "b", "--project", "p2")
        rc, out, _ = run_cli(capsys, cli_root, "event", "logs", "--task", "T-001")
        assert rc == 0
        assert "T-001" in out and "T-002" not in out
        rc2, out2, _ = run_cli(capsys, cli_root, "event", "logs", "--project", "p2")
        assert rc2 == 0
        assert "T-002" in out2 and "T-001" not in out2

    def test_logs_json(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "init")
        rc, out, _ = run_cli(capsys, cli_root, "event", "logs", "--json")
        assert rc == 0
        d = json.loads(out)
        assert d["count"] == 1
        assert d["events"][0]["type"] == "system.init"


class TestStatus:
    def test_status_counts(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "a", "--project", "markpad")
        run_cli(capsys, cli_root, "task", "create", "--id", "T-002", "--title", "b", "--project", "markpad")
        run_cli(capsys, cli_root, "task", "update", "T-002", "--status", "TESTING")
        rc, out, _ = run_cli(capsys, cli_root, "status")
        assert rc == 0
        assert "markpad" in out
        assert "tasks" in out
        with open_events(cli_root) as store:
            statuses = [e for e in store.query(event_type=EventType.SYSTEM_STATUS_VIEWED)]
            assert len(statuses) == 1
            p = statuses[0].payload
            assert p["projects"] == ["markpad"]
            assert p["tasks_total"] == 2
            assert p["tasks_by_status"] == {"BACKLOG": 1, "TESTING": 1}
            assert p["events_total"] == 3  # 两条 created + 一条 updated; 快照不含 status_viewed 自身

    def test_status_json(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(capsys, cli_root, "status", "--json")
        assert rc == 0
        d = json.loads(out)
        assert d["tasks_count"] == 0
        assert d["events_count"] == 0


class TestValidate:
    def _seed(self, capsys, cli_root: Path, status: str = "BACKLOG") -> None:
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "a")
        if status != "BACKLOG":
            run_cli(capsys, cli_root, "task", "update", "T-001", "--status", status)

    def test_validate_pass_exit_0(self, capsys, cli_root: Path):
        self._seed(capsys, cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "validate", "T-001")
        assert rc == 0
        assert "验证通过" in out
        with open_events(cli_root) as store:
            types = event_types(store)
            # Phase 3A 事件流 (ADR-0003): started → rule.started/rule.completed(×规则) → completed
            assert types[1] == "validation.started"            # started 紧随 task.created
            assert types[-1] == "validation.completed"         # completed 收尾
            assert "validation.rule.started" in types          # 每条规则成对事件
            assert "validation.rule.completed" in types
            assert "validation.failed" not in types            # 通过时不发 failed
            completed = store.query(event_type=EventType.VALIDATION_COMPLETED)[0]
            assert completed.result == "PASS"
            assert completed.payload["level"] == "L2"
            assert completed.payload["checks"][0]["status"] == "PASS"

    def test_validate_expect_status_mismatch_exit_3(self, capsys, cli_root: Path):
        self._seed(capsys, cli_root, status="DEVELOPMENT")
        rc, out, _ = run_cli(capsys, cli_root, "validate", "T-001", "--expect-status", "TESTING")
        assert rc == 3
        assert "验证失败" in out
        with open_events(cli_root) as store:
            completed = store.query(event_type=EventType.VALIDATION_COMPLETED)[0]
            assert completed.result == "FAIL"
            assert completed.payload["reason"] == "status_mismatch"

    def test_validate_missing_task_exit_7(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(capsys, cli_root, "validate", "T-999")
        assert rc == 7
        with open_events(cli_root) as store:
            completed = store.query(event_type=EventType.VALIDATION_COMPLETED)[0]
            assert completed.result == "FAIL"
            assert completed.payload["reason"] == "task_not_found"

    def test_validate_bad_expect_status_exit_2(self, capsys, cli_root: Path):
        self._seed(capsys, cli_root)
        rc, _, _ = run_cli(capsys, cli_root, "validate", "T-001", "--expect-status", "nope")
        assert rc == 2

    def test_validate_json(self, capsys, cli_root: Path):
        self._seed(capsys, cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "validate", "T-001", "--json")
        assert rc == 0
        d = json.loads(out)
        assert d["ok"] is True
        assert d["exit_code"] == 0
