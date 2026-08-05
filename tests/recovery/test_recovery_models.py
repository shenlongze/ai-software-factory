"""tests/recovery/test_recovery_models.py — Checkpoint / RecoveryResult 模型测试。"""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from recovery.models import Checkpoint, RecoveryResult


# ------------------------------------------------------------------ Checkpoint

class TestCheckpointModel:
    def test_defaults(self):
        cp = Checkpoint(id="CKPT-T-001", task_id="T-001")
        assert cp.event_seq == 0
        assert cp.workflow_id is None
        assert cp.workflow_state is None
        assert cp.current_step is None
        assert cp.agents == {}
        assert cp.executions == {}
        assert isinstance(cp.created_at, datetime)

    def test_full_fields(self):
        cp = Checkpoint(
            id="CKPT-T-001", task_id="T-001", workflow_id="wf-a", event_seq=42,
            workflow_state={"run_id": "WR-001", "status": "RUNNING"},
            current_step="s1", agents={"A-001": "WORKING"}, executions={"EX-001": "RUNNING"},
        )
        assert cp.workflow_id == "wf-a"
        assert cp.event_seq == 42
        assert cp.current_step == "s1"
        assert cp.agents == {"A-001": "WORKING"}
        assert cp.executions == {"EX-001": "RUNNING"}

    def test_serialization_roundtrip(self):
        cp = Checkpoint(
            id="CKPT-T-001", task_id="T-001", workflow_id="wf-a", event_seq=7,
            workflow_state={"run_id": "WR-001", "status": "RUNNING", "step_states": []},
            current_step="s1", agents={"A-001": "AVAILABLE"}, executions={},
        )
        raw = cp.model_dump(mode="json")
        got = Checkpoint.model_validate(raw)
        assert got.id == cp.id
        assert got.task_id == cp.task_id
        assert got.workflow_id == cp.workflow_id
        assert got.event_seq == cp.event_seq
        assert got.workflow_state == cp.workflow_state
        assert got.current_step == cp.current_step
        assert got.agents == cp.agents
        assert got.executions == cp.executions
        assert got.created_at == cp.created_at  # 同对象落盘读回, 时间戳保留

    def test_to_dict_json_friendly(self):
        cp = Checkpoint(id="CKPT-T-001", task_id="T-001")
        d = cp.to_dict()
        assert d["id"] == "CKPT-T-001"
        assert d["task_id"] == "T-001"
        assert isinstance(d["created_at"], str)  # ISO 字符串 (JSON 友好)

    def test_id_rejects_path_separator(self):
        with pytest.raises(ValidationError):
            Checkpoint(id="CKPT-a/b", task_id="T-001")

    def test_task_id_rejects_relative_path(self):
        with pytest.raises(ValidationError):
            Checkpoint(id="CKPT-T-001", task_id="../evil")

    def test_event_seq_negative_rejected(self):
        with pytest.raises(ValidationError):
            Checkpoint(id="CKPT-T-001", task_id="T-001", event_seq=-1)

    def test_event_seq_zero_allowed(self):
        assert Checkpoint(id="CKPT-T-001", task_id="T-001", event_seq=0).event_seq == 0


# ------------------------------------------------------------------ RecoveryResult

class TestRecoveryResultModel:
    def test_defaults(self):
        r = RecoveryResult(task_id="T-001")
        assert r.last_event == 0
        assert r.state == "none"
        assert r.resume_ok is False
        assert r.actions == []
        assert r.workflow is None
        assert r.assignments == []
        assert r.executions == []
        assert r.agents == {}

    def test_full_fields(self):
        r = RecoveryResult(
            task_id="T-001", last_event=12, state="RUNNING", resume_ok=True,
            actions=["continue step s1"], workflow={"run_id": "WR-001"},
            assignments=[{"id": "ASG-001"}], executions=[{"id": "EX-001"}],
            agents={"A-001": "AVAILABLE"},
        )
        assert r.resume_ok is True
        assert r.actions == ["continue step s1"]
        assert r.workflow == {"run_id": "WR-001"}

    def test_serialization_roundtrip(self):
        r = RecoveryResult(
            task_id="T-001", last_event=3, state="COMPLETED", resume_ok=False,
            actions=["reject recovery: workflow already COMPLETED"],
        )
        got = RecoveryResult.model_validate(r.model_dump(mode="json"))
        assert got.model_dump() == r.model_dump()

    def test_to_dict_json_friendly(self):
        r = RecoveryResult(task_id="T-001", resume_ok=True, actions=["a"])
        d = r.to_dict()
        assert d["resume_ok"] is True
        assert d["actions"] == ["a"]
        assert d["state"] == "none"
