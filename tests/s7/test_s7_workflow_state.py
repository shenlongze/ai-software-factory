"""tests/s7/test_s7_workflow_state.py — Workflow 状态机全转换表 (Unit, S7-003)。

覆盖 (合法 + 非法, 逐条覆盖 WORKFLOW_TRANSITIONS):
- 合法: draft→active / active→paused / paused→active (恢复) / active→completed
  / active→failed (reason) / failed→paused (失败重试前置)
- 非法: draft→completed / draft→paused / paused→completed / failed→active
  / completed 终态任何转换 → WorkflowStateError
- 幂等: 同状态不重复转换 (不发事件)
- 审计: started_at / completed_at / failed_reason 随转换落库

依赖: 本目录 conftest (project_store + logger + event_store)。
"""

from __future__ import annotations

import pytest

from org.lifecycle import NotFoundError
from org.workflow import (
    WorkflowLifecycle,
    WorkflowStateError,
    WorkflowStatus,
)

from s7_helpers import event_sequence


@pytest.fixture
def wlife(project_store, logger) -> WorkflowLifecycle:
    return WorkflowLifecycle(project_store, logger=logger)


@pytest.fixture
def wfid(wlife) -> str:
    from org.projects import ProjectLifecycle

    ProjectLifecycle(wlife.store).create_project("Build App", project_id="P-1")
    return wlife.create_workflow("P-1", "Ship v1", workflow_id="WF-1").id


class TestLegalTransitions:
    def test_draft_to_active(self, wlife, wfid):
        wf = wlife.activate(wfid)
        assert wf.status is WorkflowStatus.ACTIVE
        assert wf.started_at is not None
        assert wlife.get_workflow(wfid).status is WorkflowStatus.ACTIVE

    def test_active_to_paused(self, wlife, wfid):
        wlife.activate(wfid)
        wf = wlife.pause(wfid)
        assert wf.status is WorkflowStatus.PAUSED

    def test_paused_to_active_resume(self, wlife, wfid):
        wlife.activate(wfid)
        wlife.pause(wfid)
        wf = wlife.activate(wfid)  # 恢复
        assert wf.status is WorkflowStatus.ACTIVE
        # started_at 保留首次启动时间 (不覆盖)
        assert wf.started_at is not None

    def test_active_to_completed(self, wlife, wfid):
        wlife.activate(wfid)
        wf = wlife.transition_workflow(wfid, WorkflowStatus.COMPLETED)
        assert wf.status is WorkflowStatus.COMPLETED
        assert wf.completed_at is not None

    def test_active_to_failed_with_reason(self, wlife, wfid):
        wlife.activate(wfid)
        wf = wlife.transition_workflow(
            wfid, WorkflowStatus.FAILED, reason="executor boom"
        )
        assert wf.status is WorkflowStatus.FAILED
        assert wf.failed_reason == "executor boom"

    def test_failed_to_paused_retry_path(self, wlife, wfid):
        wlife.activate(wfid)
        wlife.transition_workflow(wfid, WorkflowStatus.FAILED, reason="boom")
        wf = wlife.pause(wfid)  # 人工介入后失败重试前置
        assert wf.status is WorkflowStatus.PAUSED
        assert wlife.activate(wfid).status is WorkflowStatus.ACTIVE  # 重试

    def test_string_status_parsed(self, wlife, wfid):
        wf = wlife.transition_workflow(wfid, "active")
        assert wf.status is WorkflowStatus.ACTIVE


class TestIllegalTransitions:
    def test_draft_to_completed_rejected(self, wlife, wfid):
        with pytest.raises(WorkflowStateError, match="invalid workflow transition"):
            wlife.transition_workflow(wfid, WorkflowStatus.COMPLETED)

    def test_draft_to_paused_rejected(self, wlife, wfid):
        with pytest.raises(WorkflowStateError, match="invalid workflow transition"):
            wlife.transition_workflow(wfid, WorkflowStatus.PAUSED)

    def test_draft_to_failed_rejected(self, wlife, wfid):
        with pytest.raises(WorkflowStateError):
            wlife.transition_workflow(wfid, WorkflowStatus.FAILED)

    def test_paused_to_completed_rejected(self, wlife, wfid):
        wlife.activate(wfid)
        wlife.pause(wfid)
        with pytest.raises(WorkflowStateError, match="invalid workflow transition"):
            wlife.transition_workflow(wfid, WorkflowStatus.COMPLETED)

    def test_failed_to_active_rejected(self, wlife, wfid):
        """失败不可直接恢复 — 须先 pause (failed → paused → active)。"""
        wlife.activate(wfid)
        wlife.transition_workflow(wfid, WorkflowStatus.FAILED)
        with pytest.raises(WorkflowStateError):
            wlife.activate(wfid)

    def test_completed_terminal_rejects_all(self, wlife, wfid):
        wlife.activate(wfid)
        wlife.transition_workflow(wfid, WorkflowStatus.COMPLETED)
        for target in (WorkflowStatus.ACTIVE, WorkflowStatus.PAUSED,
                       WorkflowStatus.FAILED):
            with pytest.raises(WorkflowStateError):
                wlife.transition_workflow(wfid, target)

    def test_error_message_lists_allowed(self, wlife, wfid):
        with pytest.raises(WorkflowStateError) as exc:
            wlife.transition_workflow(wfid, WorkflowStatus.PAUSED)
        assert "draft → paused" in str(exc.value)
        assert "active" in str(exc.value)  # allowed from draft: active


class TestIdempotency:
    def test_same_status_no_event(self, wlife, wfid, event_store):
        """同状态幂等: 不重复转换, 不发事件。"""
        before = len(event_store.query())
        wf = wlife.transition_workflow(wfid, WorkflowStatus.DRAFT)
        assert wf.status is WorkflowStatus.DRAFT
        assert len(event_store.query()) == before

    def test_activate_twice_second_noop(self, wlife, wfid, event_store):
        wlife.activate(wfid)
        seq_after_first = event_sequence(event_store)
        assert "org.workflow.started" in seq_after_first
        n_started = seq_after_first.count("org.workflow.started")
        wlife.activate(wfid)  # active → active 幂等
        seq_after_second = event_sequence(event_store)
        assert seq_after_second.count("org.workflow.started") == n_started


class TestAudit:
    def test_transition_updates_updated_at(self, wlife, wfid):
        before = wlife.get_workflow(wfid).updated_at
        wlife.activate(wfid)
        assert wlife.get_workflow(wfid).updated_at >= before

    def test_pause_transition_no_event(self, wlife, wfid, event_store):
        """active→paused 不独立发事件 (恢复路径由 started 覆盖)。"""
        wlife.activate(wfid)
        wlife.pause(wfid)
        seq = event_sequence(event_store)
        assert seq.count("org.workflow.started") == 1  # 暂停不发第二条 started

    def test_transition_missing_workflow(self, wlife):
        with pytest.raises(NotFoundError):
            wlife.transition_workflow("WF-999", WorkflowStatus.ACTIVE)
