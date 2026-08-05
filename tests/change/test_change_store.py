"""tests/change/test_change_store.py — ChangeStore (ExecutionGitSnapshot 关联存储)。

覆盖: 追加式 JSON 持久化 / 原子写 / 损坏文件失败安全 (→ []) / 过滤查询 /
旧执行记录 (无快照) 兼容 → 空列表。
"""

from __future__ import annotations

import json

from change.models import ExecutionGitSnapshot
from change.service import ChangeStore

from change_helpers import make_snapshot


class TestChangeStoreIO:
    def test_load_missing_file_empty(self, store):
        assert store.load() == []

    def test_save_load_roundtrip(self, store):
        snap = make_snapshot(execution_id="EX-001")
        store.save(snap)
        loaded = store.load()
        assert len(loaded) == 1
        assert loaded[0].execution_id == "EX-001"

    def test_append_multiple(self, store):
        store.save(make_snapshot(execution_id="EX-1"))
        store.save(make_snapshot(execution_id="EX-2"))
        assert [s.execution_id for s in store.load()] == ["EX-1", "EX-2"]

    def test_corrupted_file_failsafe(self, store):
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text("{not json", encoding="utf-8")
        assert store.load() == []

    def test_non_list_json_failsafe(self, store):
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text(json.dumps({"a": 1}), encoding="utf-8")
        assert store.load() == []

    def test_invalid_item_skipped(self, store):
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text(json.dumps([
            {"execution_id": "EX-OK", "task_id": "T-1"},
            {"execution_id": 42, "task_id": None, "nope": True},  # 校验失败
        ]), encoding="utf-8")
        loaded = store.load()
        assert [s.execution_id for s in loaded] == ["EX-OK"]

    def test_atomic_write_no_tmp_leftover(self, store):
        store.save(make_snapshot())
        assert not store.path.with_suffix(".json.tmp").exists()

    def test_dir_path_resolution(self, tmp_path):
        s = ChangeStore(tmp_path / "sub")
        assert s.path == tmp_path / "sub" / "snapshots.json"

    def test_file_path_resolution(self, tmp_path):
        s = ChangeStore(tmp_path / "custom.json")
        assert s.path == tmp_path / "custom.json"


class TestChangeStoreQuery:
    def test_filter_task_id(self, store):
        store.save(make_snapshot(execution_id="EX-1", task_id="MP-BUG-001"))
        store.save(make_snapshot(execution_id="EX-2", task_id="MP-FEATURE-002"))
        assert [s.execution_id for s in store.list(task_id="MP-BUG-001")] == ["EX-1"]

    def test_filter_execution_id(self, store):
        store.save(make_snapshot(execution_id="EX-1"))
        store.save(make_snapshot(execution_id="EX-2"))
        assert [s.execution_id for s in store.list(execution_id="EX-2")] == ["EX-2"]

    def test_filter_project_id(self, store):
        store.save(make_snapshot(execution_id="EX-1", project_id="markpad"))
        store.save(make_snapshot(execution_id="EX-2", project_id="other"))
        assert [s.execution_id for s in store.list(project_id="markpad")] == ["EX-1"]

    def test_no_match_empty(self, store):
        store.save(make_snapshot())
        assert store.list(task_id="T-999") == []

    def test_old_execution_no_snapshot_empty(self, store):
        # 旧执行记录 (ExecutionRequest 无快照字段) → 查询返回空, 不报错
        assert store.list() == []
        assert store.list(execution_id="EX-OLD") == []

    def test_combined_filters(self, store):
        snap = make_snapshot(execution_id="EX-1", task_id="MP-BUG-001",
                             project_id="markpad")
        store.save(snap)
        store.save(make_snapshot(execution_id="EX-2", task_id="MP-BUG-001",
                                 project_id="other"))
        out = store.list(task_id="MP-BUG-001", project_id="markpad")
        assert [s.execution_id for s in out] == ["EX-1"]

    def test_snapshot_order_preserved(self, store):
        store.save(make_snapshot(execution_id="EX-1"))
        store.save(make_snapshot(execution_id="EX-2"))
        store.save(make_snapshot(execution_id="EX-3"))
        assert [s.execution_id for s in store.load()] == ["EX-1", "EX-2", "EX-3"]

    def test_roundtrip_model_type(self, store):
        store.save(make_snapshot())
        loaded = store.load()
        assert isinstance(loaded[0], ExecutionGitSnapshot)
