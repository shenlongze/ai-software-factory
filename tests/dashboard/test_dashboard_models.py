"""tests/dashboard/test_dashboard_models.py — FactorySnapshot 领域模型测试。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from dashboard.models import (
    AgentSnapshot,
    CheckpointSnapshot,
    ExecutionSnapshot,
    FactorySnapshot,
    MetricsSnapshot,
    TaskSnapshot,
    ValidationSummary,
    WorkflowSnapshot,
)


class TestFactorySnapshot:
    def test_empty_defaults(self):
        """空快照: 全字段默认值, 不抛错 (空工厂语义)。"""
        s = FactorySnapshot()
        assert s.tasks.total == 0
        assert s.agents.total == 0
        assert s.workflows.definitions == 0
        assert s.workflows.runs_total == 0
        assert s.executions.total == 0
        assert s.checkpoints.total == 0
        assert s.metrics.event_count == 0
        assert s.recent_events == []
        assert s.project_id is None
        assert s.tasks.by_status == {}
        assert s.agents.by_status == {}

    def test_generated_at_is_utc(self):
        s = FactorySnapshot()
        assert s.generated_at.tzinfo is not None
        assert s.generated_at.utcoffset() == timezone.utc.utcoffset(None)

    def test_created_with_values(self):
        s = FactorySnapshot(
            project_id="P-001",
            tasks=TaskSnapshot(total=3, by_status={"DONE": 1}, active=2, done=1),
            agents=AgentSnapshot(total=2, by_status={"AVAILABLE": 2}),
            recent_events=[{"seq": 1, "type": "task.created"}],
        )
        assert s.project_id == "P-001"
        assert s.tasks.total == 3
        assert s.tasks.active == 2
        assert s.agents.total == 2
        assert s.recent_events == [{"seq": 1, "type": "task.created"}]

    def test_to_dict_roundtrip(self):
        s = FactorySnapshot(
            project_id="P-001",
            tasks=TaskSnapshot(total=1, by_status={"BACKLOG": 1}, items=[{"id": "T-001"}]),
        )
        data = s.to_dict()
        assert data["project_id"] == "P-001"
        assert data["tasks"]["total"] == 1
        assert data["tasks"]["items"] == [{"id": "T-001"}]
        restored = FactorySnapshot.model_validate(data)
        assert restored.to_dict() == data

    def test_to_dict_json_dumpable(self):
        """--json 出口: model_dump(mode=json) 必须可 json.dumps (无 datetime/枚举残留)。"""
        s = FactorySnapshot(
            tasks=TaskSnapshot(total=1, items=[{"id": "T-001", "created_at": "2026-08-06T00:00:00Z"}]),
            recent_events=[{"seq": 1, "type": "task.created"}],
        )
        payload = json.dumps(s.to_dict(), ensure_ascii=False)
        assert '"T-001"' in payload
        assert '"total": 1' in payload

    def test_project_id_default_none(self):
        assert FactorySnapshot().project_id is None


class TestSubSnapshots:
    def test_task_snapshot_defaults(self):
        t = TaskSnapshot()
        assert (t.total, t.active, t.done) == (0, 0, 0)
        assert t.by_status == {}
        assert t.by_project == {}
        assert t.items == []

    def test_task_snapshot_counts(self):
        t = TaskSnapshot(total=5, by_status={"DONE": 2, "BACKLOG": 3}, active=3, done=2)
        assert t.to_dict()["total"] == 5
        assert t.by_status["DONE"] == 2

    def test_agent_snapshot(self):
        a = AgentSnapshot(total=2, by_status={"AVAILABLE": 1, "WORKING": 1},
                          working=1, available=1, by_role={"dev": 2})
        d = a.to_dict()
        assert d["working"] == 1 and d["available"] == 1
        assert d["by_role"] == {"dev": 2}

    def test_workflow_snapshot(self):
        w = WorkflowSnapshot(definitions=3, runs_total=2,
                             runs_by_status={"RUNNING": 1, "COMPLETED": 1})
        assert w.to_dict()["definitions"] == 3
        assert w.runs_by_status["RUNNING"] == 1

    def test_execution_snapshot_success_rate(self):
        x = ExecutionSnapshot(total=10, success=9, failed=1, success_rate=0.9,
                              by_status={"SUCCESS": 9, "FAILED": 1})
        assert x.to_dict()["success_rate"] == 0.9
        assert x.success == 9

    def test_checkpoint_snapshot(self):
        c = CheckpointSnapshot(total=1, tasks=["T-001"], items=[{"id": "CKPT-T-001"}])
        assert c.tasks == ["T-001"]
        assert c.to_dict()["total"] == 1

    def test_validation_summary(self):
        v = ValidationSummary(total=4, pass_count=2, fail_count=1, skip_count=1,
                              error_count=0, runs=1, failed_runs=0)
        d = v.to_dict()
        assert d["pass_count"] == 2 and d["fail_count"] == 1

    def test_metrics_snapshot(self):
        m = MetricsSnapshot(
            event_count=10,
            event_type_counts={"task.created": 5},
            validation=ValidationSummary(pass_count=2),
            recovery_started=1, recovery_completed=1, recovery_failed=0,
        )
        d = m.to_dict()
        assert d["event_count"] == 10
        assert d["recovery_started"] == 1
        assert d["validation"]["pass_count"] == 2

    def test_snapshot_nested_serialization(self):
        """嵌套子模型序列化为 dict (非 Pydantic 对象残留)。"""
        s = FactorySnapshot(metrics=MetricsSnapshot(validation=ValidationSummary(pass_count=3)))
        d = s.to_dict()
        assert isinstance(d["metrics"], dict)
        assert d["metrics"]["validation"]["pass_count"] == 3
