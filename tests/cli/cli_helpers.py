"""tests/cli/helpers.py — CLI 测试 helper: 跑 main + 打开事件库断言。"""

from __future__ import annotations

from pathlib import Path

from cli.main import main
from events.store import EventStore


def run_cli(capsys, root: Path, *argv: str) -> tuple[int, str, str]:
    """执行 CLI (root 固定注入), 返回 (退出码, stdout, stderr)。"""
    rc = main(["--root", str(root), *argv])
    out, err = capsys.readouterr()
    return rc, out, err


def open_events(root: Path) -> EventStore:
    """以只读断言打开 CLI 写出的事件库 (调用方负责 close)。"""
    return EventStore(root / "factory.db")


def event_types(store: EventStore) -> list[str]:
    return [e.type.value for e in store.query()]


def task_ids(root: Path) -> list[str]:
    from tasks.store import TaskStore

    return [t.id for t in TaskStore(root / "tasks").list()]
