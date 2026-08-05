"""test_store.py — TaskStore JSON 文件持久化 (create/get/list/update_status)。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tasks.models import TaskStatus
from tasks.store import TaskExistsError, TaskNotFoundError, TaskStore, TaskStoreError
from task_helpers import make_task


class TestCreateGet:
    def test_create_writes_file_and_roundtrips(self, store: TaskStore):
        t = make_task("T-001", title="impl", project="markpad", type="bug", owner="alice")
        store.create(t)
        path = store.dir / "T-001.json"
        assert path.exists()
        got = store.get("T-001")
        assert got is not None
        assert got.id == "T-001"
        assert got.title == "impl"
        assert got.project == "markpad"
        assert got.type == "bug"
        assert got.owner == "alice"
        assert got.status is TaskStatus.BACKLOG

    def test_create_duplicate_raises(self, store: TaskStore):
        store.create(make_task("T-001"))
        with pytest.raises(TaskExistsError):
            store.create(make_task("T-001", title="other"))

    def test_get_missing_returns_none(self, store: TaskStore):
        assert store.get("T-999") is None

    def test_file_content_is_json(self, store: TaskStore):
        store.create(make_task("T-001", project="markpad"))
        raw = json.loads((store.dir / "T-001.json").read_text(encoding="utf-8"))
        assert raw["id"] == "T-001"
        assert raw["status"] == "BACKLOG"
        assert raw["project"] == "markpad"


class TestList:
    def test_list_sorted_by_id(self, store: TaskStore):
        for tid in ("T-003", "T-001", "T-002"):
            store.create(make_task(tid))
        assert [t.id for t in store.list()] == ["T-001", "T-002", "T-003"]

    def test_list_filter_status(self, store: TaskStore):
        store.create(make_task("T-001"))
        store.create(make_task("T-002", status=TaskStatus.DEVELOPMENT))
        store.create(make_task("T-003", status=TaskStatus.DEVELOPMENT))
        dev = store.list(status="DEVELOPMENT")
        assert [t.id for t in dev] == ["T-002", "T-003"]
        assert store.list(status=TaskStatus.DONE) == []

    def test_list_filter_project(self, store: TaskStore):
        store.create(make_task("T-001", project="markpad"))
        store.create(make_task("T-002", project="other"))
        assert [t.id for t in store.list(project="markpad")] == ["T-001"]
        assert [t.id for t in store.list(project="nope")] == []

    def test_list_empty_dir(self, store: TaskStore):
        assert store.list() == []
        assert store.count() == 0

    def test_next_id_auto_increment(self, store: TaskStore):
        assert store.next_id() == "T-001"
        store.create(make_task("T-001"))
        store.create(make_task("T-007"))
        assert store.next_id() == "T-008"


class TestUpdateStatus:
    def test_update_status_changes_and_bumps_updated_at(self, store: TaskStore):
        t = store.create(make_task("T-001"))
        before = t.updated_at
        got = store.update_status("T-001", "TESTING")
        assert got.status is TaskStatus.TESTING
        assert got.updated_at >= before
        assert store.get("T-001").status is TaskStatus.TESTING

    def test_update_status_missing_raises(self, store: TaskStore):
        with pytest.raises(TaskNotFoundError):
            store.update_status("T-999", "DONE")

    def test_update_status_invalid_raises(self, store: TaskStore):
        store.create(make_task("T-001"))
        with pytest.raises(ValueError):
            store.update_status("T-001", "bogus")


class TestPersistence:
    def test_survives_store_reopen(self, tasks_dir: Path):
        """新实例重开同目录: 数据仍在 (跨进程持久化语义)。"""
        TaskStore(tasks_dir).create(make_task("T-001", project="markpad"))
        TaskStore(tasks_dir).create(make_task("T-002", title="second"))
        reopened = TaskStore(tasks_dir)
        assert reopened.count() == 2
        assert reopened.get("T-001").project == "markpad"
        assert reopened.get("T-002").title == "second"

    def test_corrupt_file_raises(self, tasks_dir: Path, store: TaskStore):
        store.create(make_task("T-001"))
        (tasks_dir / "T-001.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(TaskStoreError, match="corrupt task file"):
            store.get("T-001")
