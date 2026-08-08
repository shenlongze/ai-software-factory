"""tests/s9/test_s9_approval_store.py — ApprovalGateStore 持久化。

覆盖 (S9-001 任务清单: persistence):
- save/get/list_all/count/delete (upsert 语义, id 排序)
- approvals.json 文件位置 + section 结构 (与 org 其他 store 同模式)
- 原子写 (临时文件 + os.replace) 不残留 tmp 文件
- 损坏失败安全: JSON 损坏/缺 section/坏记录 → CorruptOrgStoreError 响亮
  拒绝 (绝不静默返回空 — 审计数据铁律)
- 跨实例持久化 (新 store 实例读回已存门)

依赖: 本目录 conftest。
"""

from __future__ import annotations

import json

import pytest

from org.approval import (
    ApprovalGate,
    ApprovalGateStore,
    ApprovalStatus,
    transition_approval,
)
from org.store import CorruptOrgStoreError


def _gate(gate_id: str = "AG-1", stage_id: str = "STG-1", workflow_id: str = "WF-1") -> ApprovalGate:
    return ApprovalGate(id=gate_id, stage_id=stage_id, workflow_id=workflow_id)


class TestStoreCrud:
    def test_save_get_roundtrip(self, approval_store: ApprovalGateStore) -> None:
        approval_store.save(_gate())
        got = approval_store.get("AG-1")
        assert got is not None
        assert got.id == "AG-1"
        assert got.status == ApprovalStatus.PENDING
        assert got.stage_id == "STG-1"
        assert got.workflow_id == "WF-1"

    def test_get_missing_returns_none(self, approval_store: ApprovalGateStore) -> None:
        assert approval_store.get("AG-NOPE") is None

    def test_upsert_same_id_overwrites(self, approval_store: ApprovalGateStore) -> None:
        approval_store.save(_gate())
        updated = transition_approval(
            approval_store.get("AG-1"),  # type: ignore[arg-type]
            ApprovalStatus.APPROVED,
            reviewer="alice",
            comment="ok",
        )
        approval_store.save(updated)
        got = approval_store.get("AG-1")
        assert got is not None and got.status == ApprovalStatus.APPROVED
        assert got.reviewer == "alice"
        assert approval_store.count() == 1

    def test_list_all_sorted_and_count(self, approval_store: ApprovalGateStore) -> None:
        approval_store.save(_gate("AG-3", stage_id="STG-3"))
        approval_store.save(_gate("AG-1", stage_id="STG-1"))
        approval_store.save(_gate("AG-2", stage_id="STG-2"))
        ids = [g.id for g in approval_store.list_all()]
        assert ids == ["AG-1", "AG-2", "AG-3"]
        assert approval_store.count() == 3

    def test_delete_and_delete_missing(self, approval_store: ApprovalGateStore) -> None:
        approval_store.save(_gate())
        assert approval_store.delete("AG-1") is True
        assert approval_store.get("AG-1") is None
        assert approval_store.delete("AG-1") is False  # 幂等


class TestStoreFile:
    def test_file_location_and_section(self, org_dir, approval_store: ApprovalGateStore) -> None:
        approval_store.save(_gate())
        path = org_dir / "approvals.json"
        assert path.exists()
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert set(raw.keys()) == {"approvals"}
        assert "AG-1" in raw["approvals"]

    def test_persistence_across_instances(self, org_dir) -> None:
        ApprovalGateStore(org_dir).save(_gate("AG-1"))
        second = ApprovalGateStore(org_dir)
        got = second.get("AG-1")
        assert got is not None and got.stage_id == "STG-1"

    def test_missing_file_is_empty_store(self, approval_store: ApprovalGateStore) -> None:
        assert approval_store.list_all() == []
        assert approval_store.count() == 0

    def test_no_tmp_residue_after_atomic_write(self, org_dir, approval_store: ApprovalGateStore) -> None:
        approval_store.save(_gate())
        leftovers = [p for p in org_dir.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == []


class TestStoreCorruption:
    def test_corrupt_json_raises(self, org_dir) -> None:
        path = org_dir / "approvals.json"
        org_dir.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(CorruptOrgStoreError, match="corrupt org store"):
            ApprovalGateStore(org_dir).list_all()

    def test_missing_section_raises(self, org_dir) -> None:
        path = org_dir / "approvals.json"
        org_dir.mkdir(parents=True, exist_ok=True)
        path.write_text('{"other": {}}', encoding="utf-8")
        with pytest.raises(CorruptOrgStoreError, match="missing or invalid section"):
            ApprovalGateStore(org_dir).list_all()

    def test_invalid_record_raises(self, org_dir) -> None:
        path = org_dir / "approvals.json"
        org_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '{"approvals": {"AG-1": {"id": "AG-1", "status": "maybe"}}}',
            encoding="utf-8",
        )
        with pytest.raises(CorruptOrgStoreError, match="corrupt org store"):
            ApprovalGateStore(org_dir).list_all()
