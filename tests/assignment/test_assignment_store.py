"""tests/assignment/test_assignment_store.py — AssignmentStore JSON 持久化 (读写/原子写/损坏)。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from assignment.models import AssignmentStatus
from assignment.store import AssignmentStore, CorruptAssignmentStoreError

from assignment_helpers import make_assignment


class TestReadWrite:
    def test_save_load_roundtrip(self, assignment_store: AssignmentStore):
        a = make_assignment()
        assignment_store.save(a)
        assert assignment_store.load("ASG-001") == a

    def test_load_missing_returns_none(self, assignment_store: AssignmentStore):
        assert assignment_store.load("ASG-999") is None

    def test_load_all_empty(self, assignment_store: AssignmentStore):
        assert assignment_store.load_all() == {}

    def test_upsert_overwrites(self, assignment_store: AssignmentStore):
        assignment_store.save(make_assignment(status=AssignmentStatus.ASSIGNED))
        assignment_store.save(make_assignment(status=AssignmentStatus.WORKING))
        loaded = assignment_store.load("ASG-001")
        assert loaded is not None
        assert loaded.status is AssignmentStatus.WORKING

    def test_remove_existing(self, assignment_store: AssignmentStore):
        assignment_store.save(make_assignment())
        assert assignment_store.remove("ASG-001") is True
        assert assignment_store.load("ASG-001") is None

    def test_remove_missing_false(self, assignment_store: AssignmentStore):
        assert assignment_store.remove("ASG-999") is False

    def test_file_at_expected_path(self, assignment_store: AssignmentStore, assignments_dir: Path):
        assignment_store.save(make_assignment())
        assert (assignments_dir / "assignments.json").exists()

    def test_json_sorted_by_id(self, assignment_store: AssignmentStore):
        assignment_store.save(make_assignment("ASG-002"))
        assignment_store.save(make_assignment("ASG-001"))
        raw = json.loads(assignment_store.path.read_text(encoding="utf-8"))
        assert list(raw.keys()) == ["ASG-001", "ASG-002"]

    def test_no_tmp_file_left_after_write(self, assignment_store: AssignmentStore):
        assignment_store.save(make_assignment())
        leftovers = [p for p in assignment_store.dir.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == []

    def test_persistence_across_instances(self, assignments_dir: Path):
        AssignmentStore(assignments_dir).save(make_assignment("ASG-001"))
        fresh = AssignmentStore(assignments_dir)
        assert fresh.load("ASG-001") is not None


class TestCorruption:
    def test_corrupt_json_raises(self, assignment_store: AssignmentStore, assignments_dir: Path):
        assignments_dir.mkdir(parents=True, exist_ok=True)
        (assignments_dir / "assignments.json").write_text("{ not json", encoding="utf-8")
        with pytest.raises(CorruptAssignmentStoreError):
            assignment_store.load_all()

    def test_non_object_json_raises(self, assignment_store: AssignmentStore, assignments_dir: Path):
        assignments_dir.mkdir(parents=True, exist_ok=True)
        (assignments_dir / "assignments.json").write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(CorruptAssignmentStoreError):
            assignment_store.load("ASG-001")

    def test_corrupt_model_raises(self, assignment_store: AssignmentStore, assignments_dir: Path):
        assignments_dir.mkdir(parents=True, exist_ok=True)
        (assignments_dir / "assignments.json").write_text(
            json.dumps({"ASG-001": {"id": "ASG-001", "agent_id": "A-001",
                                    "task_id": "T-001", "status": "bogus"}}),
            encoding="utf-8",
        )
        with pytest.raises(CorruptAssignmentStoreError):
            assignment_store.load("ASG-001")


class TestList:
    def test_list_all_sorted(self, assignment_store: AssignmentStore):
        assignment_store.save(make_assignment("ASG-002", task_id="T-002"))
        assignment_store.save(make_assignment("ASG-001", task_id="T-001"))
        ids = [a.id for a in assignment_store.list()]
        assert ids == ["ASG-001", "ASG-002"]

    def test_list_filter_task(self, assignment_store: AssignmentStore):
        assignment_store.save(make_assignment("ASG-001", task_id="T-001"))
        assignment_store.save(make_assignment("ASG-002", task_id="T-002"))
        assert [a.id for a in assignment_store.list(task_id="T-002")] == ["ASG-002"]

    def test_list_filter_agent(self, assignment_store: AssignmentStore):
        assignment_store.save(make_assignment("ASG-001", agent_id="A-001"))
        assignment_store.save(make_assignment("ASG-002", agent_id="A-002"))
        assert [a.id for a in assignment_store.list(agent_id="A-002")] == ["ASG-002"]

    def test_list_filter_status(self, assignment_store: AssignmentStore):
        assignment_store.save(make_assignment("ASG-001", status=AssignmentStatus.ASSIGNED))
        assignment_store.save(make_assignment("ASG-002", status=AssignmentStatus.RELEASED))
        assert [a.id for a in assignment_store.list(status=AssignmentStatus.RELEASED)] == ["ASG-002"]
        # 字符串状态宽容解析
        assert [a.id for a in assignment_store.list(status="released")] == ["ASG-002"]


class TestNextId:
    def test_next_id_starts_at_001(self, assignment_store: AssignmentStore):
        assert assignment_store.next_id() == "ASG-001"

    def test_next_id_increments(self, assignment_store: AssignmentStore):
        assignment_store.save(make_assignment("ASG-001"))
        assignment_store.save(make_assignment("ASG-002"))
        assert assignment_store.next_id() == "ASG-003"

    def test_next_id_ignores_non_matching_prefix(self, assignment_store: AssignmentStore):
        assignment_store.save(make_assignment("X-100"))
        assert assignment_store.next_id() == "ASG-001"
