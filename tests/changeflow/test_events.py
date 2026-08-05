"""tests/changeflow/test_events.py — change.trigger.* / change.workflow.* 审计事件
(Phase 6E, ADR-0020)。

覆盖 5 事件: created / viewed / evaluated / workflow.started / workflow.completed
— EventType、payload 契约 (Dashboard Change Flow View 聚合依赖)、result 判定、
source 缺省、触发失败 error 载荷。
"""

from __future__ import annotations

from events.models import EventType

from changeflow.events import (
    record_change_trigger_created,
    record_change_trigger_evaluated,
    record_change_trigger_viewed,
    record_change_workflow_completed,
    record_change_workflow_started,
)

from changeflow_helpers import make_evaluation, make_rule_result, make_trigger


class TestTriggerCreated:
    def test_event_type_and_result(self, logger):
        ev = record_change_trigger_created(logger, trigger=make_trigger())
        assert ev.type == EventType.CHANGE_TRIGGER_CREATED
        assert ev.result == "OK"

    def test_source_default_changeflow(self, logger):
        ev = record_change_trigger_created(logger, trigger=make_trigger())
        assert ev.source == "changeflow"

    def test_payload_contract(self, logger):
        t = make_trigger(project_id="markpad", task_type="feature",
                         required_validation="PASS", target_workflow="release")
        ev = record_change_trigger_created(logger, trigger=t)
        p = ev.payload
        assert p["trigger_id"] == "TRIG-FEATURE-RELEASE"
        assert p["event_type"] == "workflow.completed"
        assert p["project_id"] == "markpad"
        assert p["task_type"] == "feature"
        assert p["required_validation"] == "PASS"
        assert p["target_workflow"] == "release"

    def test_project_id_none_in_event(self, logger):
        ev = record_change_trigger_created(logger, trigger=make_trigger())
        assert ev.project_id is None

    def test_custom_source(self, logger):
        ev = record_change_trigger_created(logger, trigger=make_trigger(),
                                           source="cli")
        assert ev.source == "cli"


class TestTriggerViewed:
    def test_event_type(self, logger):
        ev = record_change_trigger_viewed(logger, count=2)
        assert ev.type == EventType.CHANGE_TRIGGER_VIEWED
        assert ev.payload["count"] == 2

    def test_source_default_cli(self, logger):
        # 读命令审计 source 缺省 cli (与写路径 changeflow 区分)
        ev = record_change_trigger_viewed(logger, count=0)
        assert ev.source == "cli"

    def test_zero_count(self, logger):
        ev = record_change_trigger_viewed(logger, count=0)
        assert ev.payload["count"] == 0


class TestTriggerEvaluated:
    def test_event_type_and_result(self, logger):
        ev = record_change_trigger_evaluated(
            logger, evaluation=make_evaluation(status="PASS"))
        assert ev.type == EventType.CHANGE_TRIGGER_EVALUATED
        assert ev.result == "PASS"

    def test_task_id_on_event(self, logger):
        ev = record_change_trigger_evaluated(
            logger, evaluation=make_evaluation(task_id="MP-BUG-001"))
        assert ev.task_id == "MP-BUG-001"

    def test_payload_contract(self, logger):
        e = make_evaluation(
            status="PASS", triggered_workflow="release", run_id="WR-1",
            rules=[make_rule_result(rule_id="validation.l4", status="PASS")],
        )
        ev = record_change_trigger_evaluated(logger, evaluation=e)
        p = ev.payload
        assert p["task_id"] == "MP-BUG-001"
        assert p["trigger_id"] == "TRIG-FEATURE-RELEASE"
        assert p["status"] == "PASS"
        assert p["triggered_workflow"] == "release"
        assert p["run_id"] == "WR-1"
        assert p["error"] is None
        assert p["rules"][0]["rule_id"] == "validation.l4"
        assert p["rules"][0]["status"] == "PASS"

    def test_fail_evaluation_result(self, logger):
        ev = record_change_trigger_evaluated(
            logger, evaluation=make_evaluation(status="FAIL"))
        assert ev.result == "FAIL"

    def test_error_evaluation_carries_error(self, logger):
        e = make_evaluation(status="ERROR", trigger_id=None,
                            error="task not found: X")
        ev = record_change_trigger_evaluated(logger, evaluation=e)
        assert ev.result == "ERROR"
        assert ev.payload["error"] == "task not found: X"
        assert ev.payload["trigger_id"] is None

    def test_source_default_changeflow(self, logger):
        ev = record_change_trigger_evaluated(
            logger, evaluation=make_evaluation())
        assert ev.source == "changeflow"

    def test_skip_evaluation(self, logger):
        ev = record_change_trigger_evaluated(
            logger, evaluation=make_evaluation(status="SKIP"))
        assert ev.result == "SKIP"


class TestWorkflowStarted:
    def test_event_type(self, logger):
        ev = record_change_workflow_started(
            logger, task_id="MP-BUG-001", trigger=make_trigger(),
            workflow_id="release", run_id="WR-1")
        assert ev.type == EventType.CHANGE_WORKFLOW_STARTED
        assert ev.result == "OK"

    def test_payload_contract(self, logger):
        ev = record_change_workflow_started(
            logger, task_id="MP-BUG-001", trigger=make_trigger(),
            workflow_id="release", run_id="WR-1")
        p = ev.payload
        assert p["task_id"] == "MP-BUG-001"
        assert p["trigger_id"] == "TRIG-FEATURE-RELEASE"
        assert p["workflow_id"] == "release"
        assert p["run_id"] == "WR-1"

    def test_project_id_from_trigger(self, logger):
        ev = record_change_workflow_started(
            logger, task_id="MP-BUG-001",
            trigger=make_trigger(project_id="markpad"),
            workflow_id="release", run_id="WR-1")
        assert ev.project_id == "markpad"

    def test_stage_running(self, logger):
        ev = record_change_workflow_started(
            logger, task_id="T-1", trigger=make_trigger(),
            workflow_id="release", run_id="WR-1")
        assert ev.stage == "running"


class TestWorkflowCompleted:
    def test_event_type_completed(self, logger):
        ev = record_change_workflow_completed(
            logger, task_id="MP-BUG-001", trigger_id="TRIG-1",
            workflow_id="release", run_id="WR-1", result="COMPLETED")
        assert ev.type == EventType.CHANGE_WORKFLOW_COMPLETED
        assert ev.result == "COMPLETED"
        assert ev.stage == "completed"

    def test_failed_result_stage_failed(self, logger):
        ev = record_change_workflow_completed(
            logger, task_id="MP-BUG-001", trigger_id="TRIG-1",
            workflow_id="release", run_id="WR-1", result="FAILED")
        assert ev.result == "FAILED"
        assert ev.stage == "failed"

    def test_payload_contract(self, logger):
        ev = record_change_workflow_completed(
            logger, task_id="MP-BUG-001", trigger_id="TRIG-1",
            workflow_id="release", run_id="WR-1", result="COMPLETED",
            error=None)
        p = ev.payload
        assert p["task_id"] == "MP-BUG-001"
        assert p["trigger_id"] == "TRIG-1"
        assert p["workflow_id"] == "release"
        assert p["run_id"] == "WR-1"
        assert p["result"] == "COMPLETED"
        assert p["error"] is None

    def test_error_payload(self, logger):
        ev = record_change_workflow_completed(
            logger, task_id="T-1", trigger_id="TRIG-1",
            workflow_id="release", run_id="WR-1", result="FAILED",
            error="step failed")
        assert ev.payload["error"] == "step failed"


class TestEventOrdering:
    def test_full_trigger_chain_event_order(self, logger):
        """5 事件顺序: created → viewed → evaluated → workflow.started →
        workflow.completed (事件库按 seq 递增)。"""
        record_change_trigger_created(logger, trigger=make_trigger())
        record_change_trigger_viewed(logger, count=1)
        record_change_trigger_evaluated(
            logger, evaluation=make_evaluation(status="PASS"))
        record_change_workflow_started(
            logger, task_id="MP-BUG-001", trigger=make_trigger(),
            workflow_id="release", run_id="WR-1")
        record_change_workflow_completed(
            logger, task_id="MP-BUG-001", trigger_id="TRIG-FEATURE-RELEASE",
            workflow_id="release", run_id="WR-1", result="COMPLETED")

        events = logger.store.query()
        types = [e.type.value for e in events]
        assert types == [
            "change.trigger.created",
            "change.trigger.viewed",
            "change.trigger.evaluated",
            "change.workflow.started",
            "change.workflow.completed",
        ]
        seqs = [e.seq for e in events]
        assert seqs == sorted(seqs)  # 严格递增

    def test_evaluated_before_started_seq(self, logger):
        record_change_trigger_evaluated(
            logger, evaluation=make_evaluation(status="PASS"))
        record_change_workflow_started(
            logger, task_id="MP-BUG-001", trigger=make_trigger(),
            workflow_id="release", run_id="WR-1")
        events = logger.store.query()
        assert events[0].type == EventType.CHANGE_TRIGGER_EVALUATED
        assert events[1].type == EventType.CHANGE_WORKFLOW_STARTED
        assert events[1].seq > events[0].seq

    def test_completed_after_started(self, logger):
        record_change_workflow_started(
            logger, task_id="T-1", trigger=make_trigger(),
            workflow_id="release", run_id="WR-1")
        record_change_workflow_completed(
            logger, task_id="T-1", trigger_id="TRIG-1",
            workflow_id="release", run_id="WR-1", result="COMPLETED")
        events = logger.store.query()
        assert events[0].type == EventType.CHANGE_WORKFLOW_STARTED
        assert events[1].type == EventType.CHANGE_WORKFLOW_COMPLETED
