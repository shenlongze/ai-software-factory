"""tests/exec/test_exec_store.py — 执行数据空间持久化 (原子写/损坏响亮失败)。

覆盖: 四子库 CRUD roundtrip / 按 id 排序 / 计数 / 缺失 None / 损坏 JSON 与
模型校验失败 → CorruptExecStoreError / 首次写自动建目录 / 删除幂等。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from exec.models import ApprovalRecord, Artifact, ArtifactType, ExecutionRequest, ExecutionResult
from exec.store import CorruptExecStoreError, ExecStore


def _mk_request(req_id: str = "EXR-1") -> ExecutionRequest:
    return ExecutionRequest(id=req_id, objective="fix bug")


def _mk_result(result_id: str = "EXS-1", request_id: str = "EXR-1") -> ExecutionResult:
    return ExecutionResult(id=result_id, request_id=request_id)


class TestRequests:
    def test_save_get_roundtrip(self, exec_store: ExecStore):
        exec_store.save_request(_mk_request())
        got = exec_store.get_request("EXR-1")
        assert got is not None
        assert got.id == "EXR-1"
        assert got.objective == "fix bug"

    def test_get_missing_none(self, exec_store: ExecStore):
        assert exec_store.get_request("EXR-nope") is None

    def test_list_sorted_by_id(self, exec_store: ExecStore):
        exec_store.save_request(_mk_request("EXR-b"))
        exec_store.save_request(_mk_request("EXR-a"))
        ids = [r.id for r in exec_store.list_requests()]
        assert ids == ["EXR-a", "EXR-b"]

    def test_count(self, exec_store: ExecStore):
        assert exec_store.count_requests() == 0
        exec_store.save_request(_mk_request())
        assert exec_store.count_requests() == 1

    def test_dir_created_on_first_write(self, exec_dir: Path):
        store = ExecStore(exec_dir)
        assert not exec_dir.exists()
        store.save_request(_mk_request())
        assert exec_dir.exists()
        assert (exec_dir / "requests.json").exists()


class TestResults:
    def test_save_get_roundtrip(self, exec_store: ExecStore):
        exec_store.save_result(_mk_result())
        got = exec_store.get_result("EXS-1")
        assert got is not None
        assert got.request_id == "EXR-1"

    def test_get_result_by_request(self, exec_store: ExecStore):
        exec_store.save_result(_mk_result())
        got = exec_store.get_result_by_request("EXR-1")
        assert got is not None and got.id == "EXS-1"

    def test_get_result_by_request_missing(self, exec_store: ExecStore):
        assert exec_store.get_result_by_request("EXR-nope") is None

    def test_list_results(self, exec_store: ExecStore):
        exec_store.save_result(_mk_result("EXS-1"))
        exec_store.save_result(_mk_result("EXS-2"))
        assert len(exec_store.list_results()) == 2
        assert exec_store.count_results() == 2


class TestArtifacts:
    def test_save_get_roundtrip(self, exec_store: ExecStore):
        a = Artifact(id="ART-1", type=ArtifactType.PATCH, task_id="T-1")
        exec_store.save_artifact(a)
        got = exec_store.get_artifact("ART-1")
        assert got is not None
        assert got.type is ArtifactType.PATCH
        assert got.task_id == "T-1"

    def test_artifact_roundtrip_preserves_event_refs(self, exec_store: ExecStore):
        a = Artifact(id="ART-1", type=ArtifactType.REPORT, event_refs=["3", "4"])
        exec_store.save_artifact(a)
        got = exec_store.get_artifact("ART-1")
        assert got is not None
        assert got.event_refs == ["3", "4"]

    def test_count_artifacts(self, exec_store: ExecStore):
        exec_store.save_artifact(Artifact(id="ART-1", type=ArtifactType.PATCH))
        assert exec_store.count_artifacts() == 1


class TestApprovals:
    def test_save_get_roundtrip(self, exec_store: ExecStore):
        a = ApprovalRecord(id="APR-1", request_id="EXR-1")
        exec_store.save_approval(a)
        got = exec_store.get_approval("APR-1")
        assert got is not None
        assert got.request_id == "EXR-1"
        assert got.decision.value == "pending"

    def test_list_approvals(self, exec_store: ExecStore):
        exec_store.save_approval(ApprovalRecord(id="APR-1", request_id="EXR-1"))
        exec_store.save_approval(ApprovalRecord(id="APR-2", request_id="EXR-2"))
        assert [a.id for a in exec_store.list_approvals()] == ["APR-1", "APR-2"]

    def test_delete_idempotent(self, exec_store: ExecStore):
        a = ApprovalRecord(id="APR-1", request_id="EXR-1")
        exec_store.save_approval(a)
        assert exec_store.get_approval("APR-1") is not None
        assert exec_store._approvals.delete("APR-1") is True
        assert exec_store._approvals.delete("APR-1") is False
        assert exec_store.get_approval("APR-1") is None


class TestCorruption:
    """损坏文件测试: mkdir 局部化 (本类 autouse fixture) — 不破坏"首次写建目录"逆断言。"""

    @pytest.fixture(autouse=True)
    def _precreate(self, exec_dir: Path):
        exec_dir.mkdir(parents=True, exist_ok=True)

    def test_corrupt_json_loud(self, exec_store: ExecStore, exec_dir: Path):
        (exec_dir / "requests.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(CorruptExecStoreError):
            exec_store.list_requests()

    def test_missing_section_loud(self, exec_store: ExecStore, exec_dir: Path):
        (exec_dir / "requests.json").write_text(json.dumps({"other": {}}), encoding="utf-8")
        with pytest.raises(CorruptExecStoreError):
            exec_store.get_request("EXR-1")

    def test_model_validation_failure_loud(self, exec_store: ExecStore, exec_dir: Path):
        (exec_dir / "requests.json").write_text(
            json.dumps({"requests": {"EXR-1": {"id": 123, "bogus": True}}}),
            encoding="utf-8",
        )
        with pytest.raises(CorruptExecStoreError):
            exec_store.get_request("EXR-1")

    def test_corrupt_does_not_silently_rebuild(self, exec_store: ExecStore, exec_dir: Path):
        """损坏库上 save 响亮抛错 (先读后写), 不静默覆盖重建 (store 契约)。"""
        (exec_dir / "results.json").write_text("{broken", encoding="utf-8")
        with pytest.raises(CorruptExecStoreError):
            exec_store.save_result(_mk_result())


class TestPatchesDir:
    def test_patches_dir_property(self, exec_store: ExecStore):
        assert exec_store.patches_dir.name == "patches"
        assert exec_store.patches_dir.parent == exec_store.dir
