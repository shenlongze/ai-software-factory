"""tests/recovery/test_checkpoint_store.py — CheckpointStore 持久化测试。"""

from __future__ import annotations

import json

import pytest

from recovery.checkpoint import CheckpointStore, CorruptCheckpointError
from recovery.models import Checkpoint


def make_checkpoint(task_id: str = "T-001", *, event_seq: int = 0) -> Checkpoint:
    return Checkpoint(
        id=f"CKPT-{task_id}", task_id=task_id, workflow_id="wf-a",
        event_seq=event_seq, workflow_state={"run_id": "WR-001", "status": "RUNNING"},
        current_step="s1", agents={"A-001": "WORKING"}, executions={"EX-001": "RUNNING"},
    )


class TestCheckpointStoreRead:
    def test_load_missing_returns_none(self, checkpoint_store: CheckpointStore):
        assert checkpoint_store.load("T-999") is None

    def test_load_missing_empty_dir_returns_none(self, tmp_path):
        store = CheckpointStore(tmp_path / "does-not-exist")
        assert store.load("T-001") is None

    def test_list_empty_dir(self, tmp_path):
        store = CheckpointStore(tmp_path / "checkpoints")
        assert store.list() == []

    def test_corrupt_json_raises(self, checkpoint_store: CheckpointStore):
        path = checkpoint_store.path_for("T-001")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(CorruptCheckpointError):
            checkpoint_store.load("T-001")

    def test_model_validation_failure_raises(self, checkpoint_store: CheckpointStore):
        path = checkpoint_store.path_for("T-001")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"id": "CKPT-T-001"}), encoding="utf-8")  # 缺 task_id
        with pytest.raises(CorruptCheckpointError):
            checkpoint_store.load("T-001")

    def test_corrupt_list_raises(self, checkpoint_store: CheckpointStore):
        path = checkpoint_store.path_for("T-001")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]", encoding="utf-8")  # 非对象 → 校验失败
        with pytest.raises(CorruptCheckpointError):
            checkpoint_store.list()

    def test_path_for_rejects_path_traversal(self, checkpoint_store: CheckpointStore):
        with pytest.raises(ValueError):
            checkpoint_store.path_for("../evil")
        with pytest.raises(ValueError):
            checkpoint_store.path_for("a/b")

    def test_path_for_blank_rejected(self, checkpoint_store: CheckpointStore):
        with pytest.raises(ValueError):
            checkpoint_store.path_for("")


class TestCheckpointStoreWrite:
    def test_save_and_load_roundtrip(self, checkpoint_store: CheckpointStore):
        cp = make_checkpoint("T-001", event_seq=5)
        checkpoint_store.save(cp)
        got = checkpoint_store.load("T-001")
        assert got is not None
        assert got.id == cp.id
        assert got.task_id == cp.task_id
        assert got.workflow_id == cp.workflow_id
        assert got.event_seq == 5
        assert got.workflow_state == cp.workflow_state
        assert got.current_step == cp.current_step
        assert got.agents == cp.agents
        assert got.executions == cp.executions
        assert got.created_at == cp.created_at  # 同对象落盘读回, 时间戳保留

    def test_save_creates_dir_automatically(self, tmp_path):
        store = CheckpointStore(tmp_path / "a" / "b" / "checkpoints")
        store.save(make_checkpoint("T-001"))
        assert store.load("T-001") is not None  # 目录由首次原子写自动创建

    def test_save_overwrites_same_task(self, checkpoint_store: CheckpointStore):
        checkpoint_store.save(make_checkpoint("T-001", event_seq=3))
        checkpoint_store.save(make_checkpoint("T-001", event_seq=9))
        assert checkpoint_store.load("T-001").event_seq == 9

    def test_task_isolation(self, checkpoint_store: CheckpointStore):
        checkpoint_store.save(make_checkpoint("T-001"))
        checkpoint_store.save(make_checkpoint("T-002"))
        assert checkpoint_store.load("T-001").task_id == "T-001"
        assert checkpoint_store.load("T-002").task_id == "T-002"
        checkpoint_store.remove("T-001")
        assert checkpoint_store.load("T-001") is None
        assert checkpoint_store.load("T-002") is not None

    def test_list_sorted_by_task_id(self, checkpoint_store: CheckpointStore):
        checkpoint_store.save(make_checkpoint("T-002", event_seq=2))
        checkpoint_store.save(make_checkpoint("T-001", event_seq=1))
        checkpoint_store.save(make_checkpoint("T-003", event_seq=3))
        ids = [c.task_id for c in checkpoint_store.list()]
        assert ids == ["T-001", "T-002", "T-003"]

    def test_list_returns_all_fields(self, checkpoint_store: CheckpointStore):
        checkpoint_store.save(make_checkpoint("T-001"))
        items = checkpoint_store.list()
        assert len(items) == 1
        assert items[0].executions == {"EX-001": "RUNNING"}

    def test_remove_existing_returns_true(self, checkpoint_store: CheckpointStore):
        checkpoint_store.save(make_checkpoint("T-001"))
        assert checkpoint_store.remove("T-001") is True
        assert checkpoint_store.load("T-001") is None

    def test_remove_missing_returns_false(self, checkpoint_store: CheckpointStore):
        assert checkpoint_store.remove("T-999") is False

    def test_atomic_write_leaves_no_tmp(self, checkpoint_store: CheckpointStore):
        checkpoint_store.save(make_checkpoint("T-001"))
        leftovers = list(checkpoint_store.dir.glob("*.tmp"))
        assert leftovers == []

    def test_file_name_is_task_id(self, checkpoint_store: CheckpointStore):
        checkpoint_store.save(make_checkpoint("T-001"))
        assert (checkpoint_store.dir / "T-001.json").exists()
        assert not (checkpoint_store.dir / "CKPT-T-001.json").exists()
