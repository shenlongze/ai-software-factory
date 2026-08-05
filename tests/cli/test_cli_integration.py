"""test_integration.py — 端到端: 完整 CLI 工作流 + 全行为事件审计 + 持久化。"""

from __future__ import annotations

from pathlib import Path

from events.store import EventStore
from cli_helpers import event_types, open_events, run_cli, task_ids


class TestFullWorkflow:
    def test_init_create_flow_all_events(self, capsys, cli_root: Path):
        """init → create×2 → update → list → status → logs → status → validate。

        断言: 每个 CLI 行为都产生了正确 Event (可在 EventStore 查到), 且顺序完整。
        """
        assert run_cli(capsys, cli_root, "init")[0] == 0
        assert run_cli(capsys, cli_root, "task", "create", "--id", "T-001",
                       "--title", "实现撤销/重做", "--project", "markpad")[0] == 0
        assert run_cli(capsys, cli_root, "task", "create", "--id", "T-002",
                       "--title", "渲染引擎事件分发", "--project", "markpad")[0] == 0
        assert run_cli(capsys, cli_root, "task", "update", "T-001", "--status", "DEVELOPMENT")[0] == 0
        assert run_cli(capsys, cli_root, "task", "list", "--project", "markpad")[0] == 0
        assert run_cli(capsys, cli_root, "task", "status", "T-001")[0] == 0
        assert run_cli(capsys, cli_root, "event", "logs", "--limit", "10")[0] == 0
        assert run_cli(capsys, cli_root, "status")[0] == 0
        assert run_cli(capsys, cli_root, "validate", "T-001")[0] == 0

        with open_events(cli_root) as store:
            types = event_types(store)
            assert types == [
                "system.init",            # init
                "task.created",           # create T-001
                "task.created",           # create T-002
                "task.updated",           # update T-001 → DEVELOPMENT
                "task.viewed",            # list
                "task.viewed",            # status T-001
                "system.logs_viewed",     # event logs
                "system.status_viewed",   # status
                "validation.started",     # validate
                "validation.completed",   # validate
            ]
            assert store.count() == 10

        # 任务文件持久化
        assert task_ids(cli_root) == ["T-001", "T-002"]

    def test_events_survive_reopen(self, capsys, cli_root: Path):
        """事件库跨连接重开仍可查 (WAL 关闭后数据落盘)。"""
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "a")
        with open_events(cli_root) as store:
            assert store.count() == 1
        # 第二次独立连接
        with open_events(cli_root) as store2:
            assert store2.count() == 1
            assert store2.get(1).type.value == "task.created"

    def test_every_command_emits_event(self, capsys, cli_root: Path):
        """铁律: 每次命令调用至少新增一条事件。"""
        run_cli(capsys, cli_root, "init")
        with open_events(cli_root) as store:
            n0 = store.count()
        run_cli(capsys, cli_root, "status")
        with open_events(cli_root) as store:
            assert store.count() == n0 + 1
        run_cli(capsys, cli_root, "event", "logs")
        with open_events(cli_root) as store:
            assert store.count() == n0 + 2


class TestCleanRoot:
    def test_uninitialized_root_auto_creates(self, capsys, cli_root: Path):
        """不先 init 也能跑 (隐式 ensure_dirs), init 仅显式发 system.init。"""
        rc, _, _ = run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "a")
        assert rc == 0
        assert (cli_root / "tasks" / "T-001.json").exists()
        assert (cli_root / "factory.db").exists()
        with open_events(cli_root) as store:
            assert event_types(store) == ["task.created"]
