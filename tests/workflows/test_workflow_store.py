"""tests/workflows/test_workflow_store.py — WorkflowStore JSON 持久化。

覆盖: 读写往返 / 排序 / upsert / 删除 / run 关联 / 损坏文件 (JSON/结构/校验) / 原子写。
"""

from __future__ import annotations

import json

import pytest

from workflows.models import Workflow, WorkflowRun, WorkflowStatus, WorkflowStep
from workflows.store import CorruptWorkflowStoreError, WorkflowStore

from workflow_helpers import make_workflow


def _make_run(store: WorkflowStore, task_id: str = "T-001", wf_id: str = "wf-test") -> WorkflowRun:
    wf = store.get_workflow(wf_id) or make_workflow(wf_id)
    store.save_workflow(wf)
    run = WorkflowRun.from_workflow(run_id=store.next_run_id(), workflow=wf, task_id=task_id)
    run.status = WorkflowStatus.RUNNING
    store.save_run(run)
    return run


class TestWorkflowCrud:
    def test_save_and_get(self, workflow_store: WorkflowStore):
        wf = make_workflow("wf-1")
        workflow_store.save_workflow(wf)
        got = workflow_store.get_workflow("wf-1")
        assert got is not None
        assert got == wf
        assert got.step_ids() == ["architecture", "development", "testing", "validation"]

    def test_get_missing_returns_none(self, workflow_store: WorkflowStore):
        assert workflow_store.get_workflow("nope") is None

    def test_list_sorted_by_id(self, workflow_store: WorkflowStore):
        for wid in ("wf-b", "wf-a", "wf-c"):
            workflow_store.save_workflow(make_workflow(wid))
        assert [w.id for w in workflow_store.list_workflows()] == ["wf-a", "wf-b", "wf-c"]

    def test_save_overwrite_upsert(self, workflow_store: WorkflowStore):
        single = Workflow(id="wf-1", name="单步", steps=[WorkflowStep(id="a", name="a", order=1)])
        workflow_store.save_workflow(single)
        wf = make_workflow("wf-1")  # 同名覆盖
        workflow_store.save_workflow(wf)
        assert workflow_store.get_workflow("wf-1").step_ids() == wf.step_ids()

    def test_remove_workflow(self, workflow_store: WorkflowStore):
        workflow_store.save_workflow(make_workflow("wf-1"))
        assert workflow_store.remove_workflow("wf-1") is True
        assert workflow_store.get_workflow("wf-1") is None
        assert workflow_store.remove_workflow("wf-1") is False

    def test_empty_store_list(self, workflow_store: WorkflowStore):
        assert workflow_store.list_workflows() == []
        assert workflow_store.list_runs() == []
        assert workflow_store.next_run_id() == "WR-001"


class TestRunCrud:
    def test_save_and_get_run(self, workflow_store: WorkflowStore):
        run = _make_run(workflow_store)
        got = workflow_store.get_run(run.run_id)
        assert got is not None
        assert got.run_id == run.run_id
        assert got.task_id == "T-001"
        assert got.status is WorkflowStatus.RUNNING

    def test_get_run_by_task(self, workflow_store: WorkflowStore):
        run = _make_run(workflow_store, task_id="T-007")
        assert workflow_store.get_run_by_task("T-007").run_id == run.run_id
        assert workflow_store.get_run_by_task("T-999") is None

    def test_run_ids_sequential(self, workflow_store: WorkflowStore):
        r1 = _make_run(workflow_store, task_id="T-001")
        r2 = _make_run(workflow_store, task_id="T-002")
        assert r1.run_id == "WR-001"
        assert r2.run_id == "WR-002"
        assert workflow_store.next_run_id() == "WR-003"

    def test_list_runs_sorted(self, workflow_store: WorkflowStore):
        _make_run(workflow_store, task_id="T-002")
        _make_run(workflow_store, task_id="T-001")
        assert [r.run_id for r in workflow_store.list_runs()] == ["WR-001", "WR-002"]

    def test_persists_across_instances(self, workflow_store: WorkflowStore):
        """新 store 实例重读 (模拟重启): 定义与运行实例都在。"""
        _make_run(workflow_store, task_id="T-001")
        fresh = WorkflowStore(workflow_store.dir)
        assert fresh.get_workflow("wf-test") is not None
        assert fresh.get_run_by_task("T-001") is not None
        assert fresh.next_run_id() == "WR-002"

    def test_remove_workflow_keeps_runs(self, workflow_store: WorkflowStore):
        """定义可删, 运行实例快照不受影响 (run 冗余 workflow_id/name)。"""
        _make_run(workflow_store, task_id="T-001")
        workflow_store.remove_workflow("wf-test")
        run = workflow_store.get_run_by_task("T-001")
        assert run is not None
        assert run.workflow_id == "wf-test"
        assert run.workflow_name == "wf-test 测试"


class TestCorruption:
    def test_corrupt_json_raises(self, workflow_store: WorkflowStore, tmp_path):
        workflow_store.path.parent.mkdir(parents=True, exist_ok=True)
        workflow_store.path.write_text("{not json!!", encoding="utf-8")
        with pytest.raises(CorruptWorkflowStoreError, match="corrupt"):
            workflow_store.list_workflows()

    def test_non_object_root_raises(self, workflow_store: WorkflowStore):
        workflow_store.path.parent.mkdir(parents=True, exist_ok=True)
        workflow_store.path.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(CorruptWorkflowStoreError, match="expected JSON object"):
            workflow_store.list_workflows()

    def test_missing_section_raises(self, workflow_store: WorkflowStore):
        workflow_store.path.parent.mkdir(parents=True, exist_ok=True)
        workflow_store.path.write_text(json.dumps({"workflows": {}}), encoding="utf-8")
        with pytest.raises(CorruptWorkflowStoreError, match="runs"):
            workflow_store.list_workflows()

    def test_model_validation_failure_raises(self, workflow_store: WorkflowStore):
        workflow_store.path.parent.mkdir(parents=True, exist_ok=True)
        workflow_store.path.write_text(
            json.dumps({"workflows": {"wf": {"id": "wf", "name": "x", "steps": []}}, "runs": {}}),
            encoding="utf-8",
        )
        with pytest.raises(CorruptWorkflowStoreError, match="at least one step"):
            workflow_store.list_workflows()

    def test_atomic_write_leaves_no_tmp(self, workflow_store: WorkflowStore):
        workflow_store.save_workflow(make_workflow("wf-1"))
        leftovers = [p.name for p in workflow_store.dir.glob("*.tmp")]
        assert leftovers == []
        assert workflow_store.path.exists()
