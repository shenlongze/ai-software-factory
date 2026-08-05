"""test_runtime_store.py — RuntimeStore: JSON 读写 / 原子写 / 损坏检测 (workflows/store.py 模式)。"""

from __future__ import annotations

import json

import pytest

from runtime.models import ExecutionRequest, ExecutionResult, ExecutionStatus, RuntimeInfo
from runtime.store import CorruptRuntimeStoreError, RuntimeStore

from runtime_helpers import make_request, make_result, make_runtime


class TestRead:
    def test_empty_store(self, runtime_store):
        assert runtime_store.list_runtimes() == []
        assert runtime_store.list_executions() == []
        assert runtime_store.list_results() == []
        assert runtime_store.get_runtime("R-1") is None

    def test_no_file_created_on_read(self, runtime_store, runtimes_dir):
        runtime_store.list_runtimes()
        assert not (runtimes_dir / "runtimes.json").exists()

    def test_save_get_runtime(self, runtime_store):
        rt = make_runtime("R-001")
        runtime_store.save_runtime(rt)
        got = runtime_store.get_runtime("R-001")
        assert isinstance(got, RuntimeInfo)
        assert got.id == rt.id and got.name == rt.name and got.type == rt.type
        assert got.description == rt.description
        assert got.status is rt.status
        assert got.created_at == rt.created_at  # 时间戳 roundtrip 保留

    def test_save_get_execution(self, runtime_store):
        req = make_request("EX-001")
        runtime_store.save_execution(req)
        got = runtime_store.get_execution("EX-001")
        assert isinstance(got, ExecutionRequest)
        assert got.id == req.id and got.task_id == req.task_id
        assert got.workflow_id == req.workflow_id and got.step_id == req.step_id
        assert got.status is req.status and got.input == req.input
        assert got.created_at == req.created_at

    def test_save_get_result_by_request_id(self, runtime_store):
        """results 以 request_id 为键 (ADR-0006 决策 3)。"""
        res = make_result()
        runtime_store.save_result(res)
        got = runtime_store.get_result("EX-001")
        assert isinstance(got, ExecutionResult)
        assert got.id == res.id and got.request_id == res.request_id
        assert got.status is res.status and got.output == res.output and got.error == res.error

    def test_list_sorted(self, runtime_store):
        runtime_store.save_runtime(make_runtime("R-002"))
        runtime_store.save_runtime(make_runtime("R-001"))
        runtime_store.save_execution(make_request("EX-002"))
        runtime_store.save_execution(make_request("EX-001"))
        assert [r.id for r in runtime_store.list_runtimes()] == ["R-001", "R-002"]
        assert [e.id for e in runtime_store.list_executions()] == ["EX-001", "EX-002"]

    def test_list_executions_filter_task(self, runtime_store):
        runtime_store.save_execution(make_request("EX-001", task_id="T-1"))
        runtime_store.save_execution(make_request("EX-002", task_id="T-2"))
        assert [e.id for e in runtime_store.list_executions(task_id="T-2")] == ["EX-002"]

    def test_remove_runtime(self, runtime_store):
        runtime_store.save_runtime(make_runtime("R-001"))
        assert runtime_store.remove_runtime("R-001") is True
        assert runtime_store.remove_runtime("R-001") is False
        assert runtime_store.list_runtimes() == []

    def test_reload_persists(self, runtime_store, runtimes_dir):
        """落盘 → 新 store 实例读回 (JSON 持久化闭环)。"""
        rt, req, res = make_runtime("R-001"), make_request("EX-001"), make_result()
        runtime_store.save_runtime(rt)
        runtime_store.save_execution(req)
        runtime_store.save_result(res)
        fresh = RuntimeStore(runtimes_dir)
        got_rt = fresh.get_runtime("R-001")
        got_req = fresh.get_execution("EX-001")
        got_res = fresh.get_result("EX-001")
        assert got_rt.created_at == rt.created_at and got_rt.status is rt.status
        assert got_req.created_at == req.created_at and got_req.status is req.status
        assert got_req.workflow_id == req.workflow_id and got_req.step_id == req.step_id
        assert got_res.request_id == res.request_id and got_res.output == res.output


class TestWrite:
    def test_upsert_execution_status(self, runtime_store):
        """状态推进 = upsert (PENDING → RUNNING), 不产生重复记录。"""
        req = make_request("EX-001")
        runtime_store.save_execution(req)
        req.status = ExecutionStatus.RUNNING
        runtime_store.save_execution(req)
        got = runtime_store.get_execution("EX-001")
        assert got.status is ExecutionStatus.RUNNING
        assert runtime_store.execution_ids() == ["EX-001"]

    def test_result_upsert_by_request_id(self, runtime_store):
        """同 request_id 多次落结果 → 幂等覆盖, 至多一条 (完成语义可重入)。"""
        runtime_store.save_result(make_result("EXR-1", request_id="EX-001"))
        runtime_store.save_result(make_result("EXR-2", request_id="EX-001"))
        assert runtime_store.get_result("EX-001").id == "EXR-2"
        assert len(runtime_store.list_results()) == 1

    def test_write_creates_dir(self, runtime_store, runtimes_dir):
        """首次写自动建目录 (context.py 骨架未含 runtimes/, ADR-0006 决策 5)。"""
        assert not runtimes_dir.exists()
        runtime_store.save_runtime(make_runtime("R-001"))
        assert runtimes_dir.exists()
        assert (runtimes_dir / "runtimes.json").exists()

    def test_atomic_write_no_temp_left(self, runtime_store, runtimes_dir):
        runtime_store.save_runtime(make_runtime("R-001"))
        assert list(runtimes_dir.glob(".*.tmp")) == []

    def test_file_format_sections(self, runtime_store, runtimes_dir):
        runtime_store.save_runtime(make_runtime("R-001"))
        raw = json.loads((runtimes_dir / "runtimes.json").read_text(encoding="utf-8"))
        assert set(raw) == {"runtimes", "executions", "results"}

    def test_sorted_write(self, runtime_store, runtimes_dir):
        """按 id 排序写入 (人工审计与 git 差异友好, agents/store.py 同款)。"""
        runtime_store.save_runtime(make_runtime("R-002"))
        runtime_store.save_runtime(make_runtime("R-001"))
        raw = json.loads((runtimes_dir / "runtimes.json").read_text(encoding="utf-8"))
        assert list(raw["runtimes"]) == ["R-001", "R-002"]


class TestIds:
    def test_next_runtime_id(self, runtime_store):
        assert runtime_store.next_runtime_id() == "R-001"
        runtime_store.save_runtime(make_runtime("R-007"))
        assert runtime_store.next_runtime_id() == "R-008"

    def test_next_execution_id(self, runtime_store):
        assert runtime_store.next_execution_id() == "EX-001"
        runtime_store.save_execution(make_request("EX-003"))
        assert runtime_store.next_execution_id() == "EX-004"


class TestCorrupt:
    """损坏文件绝不静默返回空 (workflows/store.py 同款纪律)。"""

    @staticmethod
    def _write(runtimes_dir, content: str) -> None:
        runtimes_dir.mkdir(parents=True, exist_ok=True)
        (runtimes_dir / "runtimes.json").write_text(content, encoding="utf-8")

    def test_invalid_json_raises(self, runtime_store, runtimes_dir):
        self._write(runtimes_dir, "{not json")
        with pytest.raises(CorruptRuntimeStoreError):
            runtime_store.list_runtimes()

    def test_non_object_root_raises(self, runtime_store, runtimes_dir):
        self._write(runtimes_dir, "[]")
        with pytest.raises(CorruptRuntimeStoreError):
            runtime_store.list_runtimes()

    def test_missing_section_raises(self, runtime_store, runtimes_dir):
        self._write(runtimes_dir, '{"runtimes": {}}')
        with pytest.raises(CorruptRuntimeStoreError):
            runtime_store.list_executions()

    def test_bad_model_data_raises(self, runtime_store, runtimes_dir):
        """结构合法但模型校验失败 (缺 name) → CorruptRuntimeStoreError。"""
        self._write(
            runtimes_dir,
            json.dumps({"runtimes": {"R-001": {"id": "R-001"}}, "executions": {}, "results": {}}),
        )
        with pytest.raises(CorruptRuntimeStoreError):
            runtime_store.list_runtimes()

    def test_corrupt_error_message_contains_path(self, runtime_store, runtimes_dir):
        self._write(runtimes_dir, "x")
        with pytest.raises(CorruptRuntimeStoreError, match="runtimes.json"):
            runtime_store.list_runtimes()

    def test_corrupt_affects_all_reads(self, runtime_store, runtimes_dir):
        """任一读入口遇损坏都报错 (不只 list_runtimes)。"""
        self._write(runtimes_dir, "{broken")
        with pytest.raises(CorruptRuntimeStoreError):
            runtime_store.get_execution("EX-001")
        with pytest.raises(CorruptRuntimeStoreError):
            runtime_store.list_results()
