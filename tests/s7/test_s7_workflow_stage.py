"""tests/s7/test_s7_workflow_stage.py — Stage 状态机全转换表 (Unit, S7-003)。

覆盖 (合法 + 非法, 逐条覆盖 STAGE_TRANSITIONS):
- 合法: pending→ready / ready→running / running→completed / running→failed
  (reason) / blocked→ready (条件满足恢复) / blocked→pending (重置) /
  failed→ready (重试) / failed→pending (重置)
- 非法: pending→running / pending→completed / pending→failed /
  ready→completed / completed 终态任何转换 → WorkflowStateError
- 幂等: 同状态不重复转换 (不发事件); 事件只发 ready/running/completed
  (blocked/failed/pending 无独立事件, 与 org/events.py 契约一致)

依赖: 本目录 conftest (project_store + logger + event_store)。
"""

from __future__ import annotations

import pytest

from org.projects import StageStatus
from org.workflow import WorkflowLifecycle, WorkflowStateError

from s7_helpers import event_sequence


@pytest.fixture
def wlife(project_store, logger) -> WorkflowLifecycle:
    return WorkflowLifecycle(project_store, logger=logger)


@pytest.fixture
def sid(wlife) -> str:
    from org.projects import ProjectLifecycle

    ProjectLifecycle(wlife.store).create_project("Build App", project_id="P-1")
    wlife.create_workflow("P-1", "Ship v1", workflow_id="WF-1")
    return wlife.create_stage("WF-1", "developer", stage_id="STG-1").id


def _go(wlife, sid: str, *statuses: StageStatus) -> None:
    """链式合法转换 (自 PENDING 起)。"""
    for status in statuses:
        wlife.transition_stage(sid, status)


class TestLegalTransitions:
    def test_pending_to_ready(self, wlife, sid):
        stage = wlife.transition_stage(sid, StageStatus.READY)
        assert stage.status is StageStatus.READY

    def test_ready_to_running(self, wlife, sid):
        _go(wlife, sid, StageStatus.READY, StageStatus.RUNNING)
        assert wlife.get_stage(sid).status is StageStatus.RUNNING

    def test_running_to_completed(self, wlife, sid):
        _go(wlife, sid, StageStatus.READY, StageStatus.RUNNING, StageStatus.COMPLETED)
        assert wlife.get_stage(sid).status is StageStatus.COMPLETED

    def test_running_to_failed_with_reason(self, wlife, sid):
        _go(wlife, sid, StageStatus.READY, StageStatus.RUNNING)
        stage = wlife.transition_stage(sid, StageStatus.FAILED, reason="test failed")
        assert stage.status is StageStatus.FAILED
        assert stage.artifact_ref == ""  # 失败不带产物 (审计经 workflow.failed)

    def test_blocked_to_ready(self, wlife, sid):
        _go(wlife, sid, StageStatus.BLOCKED, StageStatus.READY)
        assert wlife.get_stage(sid).status is StageStatus.READY

    def test_blocked_to_pending_reset(self, wlife, sid):
        _go(wlife, sid, StageStatus.BLOCKED, StageStatus.PENDING)
        assert wlife.get_stage(sid).status is StageStatus.PENDING

    def test_failed_to_ready_retry(self, wlife, sid):
        _go(wlife, sid, StageStatus.READY, StageStatus.RUNNING, StageStatus.FAILED)
        stage = wlife.transition_stage(sid, StageStatus.READY)  # 条件满足重试
        assert stage.status is StageStatus.READY

    def test_failed_to_pending_reset(self, wlife, sid):
        _go(wlife, sid, StageStatus.READY, StageStatus.RUNNING, StageStatus.FAILED)
        stage = wlife.transition_stage(sid, StageStatus.PENDING)
        assert stage.status is StageStatus.PENDING

    def test_string_status_parsed(self, wlife, sid):
        stage = wlife.transition_stage(sid, "ready")
        assert stage.status is StageStatus.READY


class TestIllegalTransitions:
    def test_pending_to_running_rejected(self, wlife, sid):
        with pytest.raises(WorkflowStateError, match="invalid stage transition"):
            wlife.transition_stage(sid, StageStatus.RUNNING)

    def test_pending_to_completed_rejected(self, wlife, sid):
        with pytest.raises(WorkflowStateError):
            wlife.transition_stage(sid, StageStatus.COMPLETED)

    def test_pending_to_failed_rejected(self, wlife, sid):
        with pytest.raises(WorkflowStateError):
            wlife.transition_stage(sid, StageStatus.FAILED)

    def test_ready_to_completed_rejected(self, wlife, sid):
        """ready 不可直接 completed — 须经 running (受控主链)。"""
        wlife.transition_stage(sid, StageStatus.READY)
        with pytest.raises(WorkflowStateError):
            wlife.transition_stage(sid, StageStatus.COMPLETED)

    def test_running_to_pending_rejected(self, wlife, sid):
        _go(wlife, sid, StageStatus.READY, StageStatus.RUNNING)
        with pytest.raises(WorkflowStateError):
            wlife.transition_stage(sid, StageStatus.PENDING)

    def test_completed_terminal_rejects_all(self, wlife, sid):
        _go(wlife, sid, StageStatus.READY, StageStatus.RUNNING, StageStatus.COMPLETED)
        for target in (StageStatus.READY, StageStatus.RUNNING,
                       StageStatus.PENDING, StageStatus.BLOCKED, StageStatus.FAILED):
            with pytest.raises(WorkflowStateError):
                wlife.transition_stage(sid, target)

    def test_error_message_lists_allowed(self, wlife, sid):
        with pytest.raises(WorkflowStateError) as exc:
            wlife.transition_stage(sid, StageStatus.RUNNING)
        assert "pending → running" in str(exc.value)
        assert "ready" in str(exc.value)  # allowed from pending


class TestIdempotencyAndEvents:
    def test_same_status_idempotent_no_event(self, wlife, sid, event_store):
        before = len(event_store.query())
        stage = wlife.transition_stage(sid, StageStatus.PENDING)
        assert stage.status is StageStatus.PENDING
        assert len(event_store.query()) == before

    def test_ready_emits_stage_ready(self, wlife, sid, event_store):
        wlife.transition_stage(sid, StageStatus.READY)
        seq = event_sequence(event_store)
        assert seq.count("org.workflow.stage_ready") == 1

    def test_running_emits_stage_started(self, wlife, sid, event_store):
        _go(wlife, sid, StageStatus.READY, StageStatus.RUNNING)
        seq = event_sequence(event_store)
        assert seq.count("org.workflow.stage_started") == 1

    def test_completed_emits_stage_completed(self, wlife, sid, event_store):
        _go(wlife, sid, StageStatus.READY, StageStatus.RUNNING, StageStatus.COMPLETED)
        seq = event_sequence(event_store)
        assert seq.count("org.workflow.stage_completed") == 1

    def test_blocked_emits_no_event(self, wlife, sid, event_store):
        """blocked 为评估瞬态: 不独立发事件 (解除回 ready 时发 stage_ready)。"""
        wlife.transition_stage(sid, StageStatus.BLOCKED)
        seq = event_sequence(event_store)
        assert "org.workflow.stage_ready" not in seq
        assert "org.workflow.stage_started" not in seq
        assert "org.workflow.stage_completed" not in seq

    def test_failed_stage_emits_no_stage_event(self, wlife, sid, event_store):
        """failed 随 workflow.failed 审计 (stage 级无独立 failed 事件)。"""
        _go(wlife, sid, StageStatus.READY, StageStatus.RUNNING, StageStatus.FAILED)
        seq = event_sequence(event_store)
        assert seq.count("org.workflow.stage_completed") == 0

    def test_transition_missing_stage(self, wlife):
        from org.lifecycle import NotFoundError

        with pytest.raises(NotFoundError, match="stage not found"):
            wlife.transition_stage("STG-999", StageStatus.READY)
