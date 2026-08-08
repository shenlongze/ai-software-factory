"""tests/s9/test_s9_approval_events.py — org.approval.* 事件契约。

覆盖 (S9-001 任务清单: events):
- EventType +3: org.approval.created/approved/rejected (ADR-0001 扩展路径)
- created payload: gate_id/stage_id/workflow_id/project_id/status/
  requested_at (source=org — Runner 自动建门)
- approved payload: + reviewer/comment/approved_at (source=cli — 人工决定)
- rejected payload: + reviewer/comment/rejected_at (result=FAIL)
- workflow 联动事件: approve → started (from_status=paused); reject →
  started + failed (failed_reason 审计)
- logger=None 全静默 (同既有 org 模式)

依赖: 本目录 conftest + s9_helpers。
"""

from __future__ import annotations

import pytest

from events.models import EventType

from org.workflow import WorkflowLifecycle, WorkflowStatus

from s9_helpers import build_approval_workflow, event_sequence, payload_of


@pytest.fixture
def gate_workflow(wlife: WorkflowLifecycle, project_id: str):
    return build_approval_workflow(wlife, project_id)


def _complete_first_stage(wlife, workflow_id: str):
    wlife.activate(workflow_id)  # 门语义在运行中 workflow 上 (ACTIVE→PAUSED)
    pm = wlife.list_stages(workflow_id)[0]
    wlife.transition_stage(pm.id, "ready")
    wlife.transition_stage(pm.id, "running")
    wlife.transition_stage(pm.id, "completed")
    return pm


class TestEventTypes:
    def test_approval_event_types_registered(self) -> None:
        assert EventType.ORG_APPROVAL_CREATED.value == "org.approval.created"
        assert EventType.ORG_APPROVAL_APPROVED.value == "org.approval.approved"
        assert EventType.ORG_APPROVAL_REJECTED.value == "org.approval.rejected"

    def test_enum_incremental_extension(self) -> None:
        """纯增量: 既有 org.workflow.* 值零改动 (ADR-0001 决策 1 路径)。"""
        assert EventType.ORG_WORKFLOW_COMPLETED.value == "org.workflow.completed"
        assert EventType.ORG_ARTIFACT_VALIDATED.value == "org.artifact.validated"


class TestCreatedEvent:
    def test_payload_contract(self, wlife, event_store, gate_workflow, project_id) -> None:
        pm = _complete_first_stage(wlife, gate_workflow.id)
        gate = wlife.request_approval(pm.id)
        payload = payload_of(event_store, "org.approval.created")
        assert payload["gate_id"] == gate.id
        assert payload["stage_id"] == pm.id
        assert payload["workflow_id"] == gate_workflow.id
        assert payload["project_id"] == project_id
        assert payload["status"] == "pending"
        assert payload["requested_at"] == gate.requested_at.isoformat()
        event = [e for e in event_store.query() if e.type.value == "org.approval.created"][0]
        assert event.source == "org"  # Runner 自动建门
        assert event.result == "OK"

    def test_created_follows_stage_completed(self, wlife, event_store, gate_workflow) -> None:
        pm = _complete_first_stage(wlife, gate_workflow.id)
        wlife.request_approval(pm.id)
        seq = event_sequence(event_store)
        assert seq.index("org.workflow.stage_completed") < seq.index("org.approval.created")
        # 暂停不独立发事件 (恢复路径已由 started 覆盖 — S7 先例)
        assert "org.workflow.paused" not in seq


class TestApprovedEvent:
    def test_payload_contract(self, wlife, event_store, gate_workflow) -> None:
        pm = _complete_first_stage(wlife, gate_workflow.id)
        gate = wlife.request_approval(pm.id)
        wlife.approve_approval(gate.id, reviewer="alice", comment="MVP ok")
        payload = payload_of(event_store, "org.approval.approved")
        assert payload["gate_id"] == gate.id
        assert payload["status"] == "approved"
        assert payload["reviewer"] == "alice"
        assert payload["comment"] == "MVP ok"
        assert payload["approved_at"] != ""
        event = [e for e in event_store.query() if e.type.value == "org.approval.approved"][0]
        assert event.source == "cli"  # 人工决定必须审计 (ADR-0002)

    def test_approve_resumes_with_started_event(self, wlife, event_store, gate_workflow) -> None:
        pm = _complete_first_stage(wlife, gate_workflow.id)
        gate = wlife.request_approval(pm.id)
        wlife.approve_approval(gate.id, reviewer="alice")
        started = [e for e in event_store.query() if e.type.value == "org.workflow.started"]
        # 恢复 (PAUSED→ACTIVE) 的 started 是最后一个 (首个为 activate 启动)
        assert started[-1].payload.get("from_status") == "paused"
        seq = event_sequence(event_store)
        resume_idx = max(i for i, t in enumerate(seq) if t == "org.workflow.started")
        assert seq.index("org.approval.approved") < resume_idx


class TestRejectedEvent:
    def test_payload_contract(self, wlife, event_store, gate_workflow) -> None:
        pm = _complete_first_stage(wlife, gate_workflow.id)
        gate = wlife.request_approval(pm.id)
        wlife.reject_approval(gate.id, reviewer="bob", comment="scope too big")
        payload = payload_of(event_store, "org.approval.rejected")
        assert payload["gate_id"] == gate.id
        assert payload["status"] == "rejected"
        assert payload["reviewer"] == "bob"
        assert payload["comment"] == "scope too big"
        assert payload["rejected_at"] != ""
        event = [e for e in event_store.query() if e.type.value == "org.approval.rejected"][0]
        assert event.source == "cli"
        assert event.result == "FAIL"

    def test_reject_fails_workflow_with_reason(self, wlife, event_store, gate_workflow) -> None:
        pm = _complete_first_stage(wlife, gate_workflow.id)
        gate = wlife.request_approval(pm.id)
        wlife.reject_approval(gate.id, reviewer="bob", comment="scope too big")
        failed = [e for e in event_store.query() if e.type.value == "org.workflow.failed"][0]
        assert failed.payload.get("stage_id") == pm.id
        assert "scope too big" in failed.payload.get("reason", "")
        seq = event_sequence(event_store)
        assert seq.index("org.approval.rejected") < seq.index("org.workflow.failed")


class TestSilentLogger:
    def test_logger_none_records_nothing(
        self, no_logger_wlife: WorkflowLifecycle, project_id, db_path
    ) -> None:
        wf = build_approval_workflow(no_logger_wlife, project_id)
        pm = no_logger_wlife.list_stages(wf.id)[0]
        gate = no_logger_wlife.request_approval(pm.id)
        no_logger_wlife.approve_approval(gate.id, reviewer="alice")
        assert not db_path.exists()  # 零事件 = 零事件库副作用
