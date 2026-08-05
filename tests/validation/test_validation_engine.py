"""test_validation_engine.py — ValidationEngine 流程 + Event 集成测试。

覆盖: validate 主流程 / 事件序列 (started→rule.*→completed / failed) /
L1 各异常 (缺失/损坏/非法状态/缺字段) / L2 不满足 / SKIP / expect-status / 规则异常兜底。
"""

from __future__ import annotations

import json

import pytest

from events.models import EventType
from tasks.models import TaskStatus
from validation.models import ValidationStatus

from validation_helpers import create_task, record_created, record_updated, write_raw_task


def _types(logger) -> list[EventType]:
    return [e.type for e in logger.store.query()]


class TestValidatePass:
    def test_validate_pass_report(self, engine, logger, task_store):
        create_task(task_store)
        record_created(logger)
        report = engine.validate("T-001")
        assert report.passed
        assert report.task_found
        assert report.result is ValidationStatus.PASS
        assert report.reason is None
        assert report.by_level == {"L1": ValidationStatus.PASS,
                                   "L2": ValidationStatus.PASS,
                                   "L3": ValidationStatus.SKIP}

    def test_validate_emits_full_event_sequence(self, engine, logger, task_store):
        """铁律事件流: created → started → rule.started/rule.completed(×6) → completed。"""
        create_task(task_store)
        record_created(logger)
        engine.validate("T-001")
        types = _types(logger)
        assert types[0] is EventType.TASK_CREATED
        assert types[1] is EventType.VALIDATION_STARTED
        assert EventType.VALIDATION_RULE_STARTED in types
        assert EventType.VALIDATION_RULE_COMPLETED in types
        assert types[-1] is EventType.VALIDATION_COMPLETED
        assert EventType.VALIDATION_FAILED not in types
        started = [t for t in types if t is EventType.VALIDATION_RULE_STARTED]
        completed = [t for t in types if t is EventType.VALIDATION_RULE_COMPLETED]
        assert len(started) == len(completed) == 6  # L1×4 + L2×1 + L3×1

    def test_started_event_payload(self, engine, logger, task_store):
        create_task(task_store)
        record_created(logger)
        engine.validate("T-001")
        started = logger.store.query(event_type=EventType.VALIDATION_STARTED)[0]
        assert started.result == "started"
        assert started.stage == "L2"
        assert started.task_id == "T-001"
        assert "L1.task_exists" in started.payload["checks"]

    def test_rule_events_carry_payload(self, engine, logger, task_store):
        create_task(task_store)
        record_created(logger)
        engine.validate("T-001")
        completed = logger.store.query(event_type=EventType.VALIDATION_RULE_COMPLETED)
        by_rule = {e.payload["rule"]: e for e in completed}
        assert by_rule["L1.task_exists"].result == "PASS"
        assert by_rule["L2.workflow"].payload["status"] == "PASS"
        assert by_rule["L3.artifact"].result == "SKIP"
        assert by_rule["L1.task_exists"].stage == "L1"

    def test_completed_event_payload_pass(self, engine, logger, task_store):
        create_task(task_store)
        record_created(logger)
        engine.validate("T-001")
        completed = logger.store.query(event_type=EventType.VALIDATION_COMPLETED)[0]
        assert completed.result == "PASS"
        assert completed.payload["level"] == "L2"
        assert completed.payload["reason"] is None
        assert len(completed.payload["checks"]) == 6
        assert completed.payload["checks"][0]["id"] == "L1.task_exists"
        assert completed.payload["checks"][0]["status"] == "PASS"

    def test_validate_level_marker(self, engine, logger, task_store):
        """--level 作为事件 stage 标记; 三层始终执行 (ADR-0003)。"""
        create_task(task_store)
        record_created(logger)
        report = engine.validate("T-001", level="L1")
        assert report.level == "L1"
        started = logger.store.query(event_type=EventType.VALIDATION_STARTED)[0]
        assert started.stage == "L1"
        # L3 规则仍然执行 (hook SKIP)
        assert report.by_level["L3"] is ValidationStatus.SKIP


class TestValidateMissingTask:
    def test_report_fail_task_not_found(self, engine, logger):
        report = engine.validate("T-999")
        assert not report.task_found
        assert report.result is ValidationStatus.FAIL
        assert report.reason == "task_not_found"
        assert report.by_level["L1"] is ValidationStatus.FAIL
        assert report.by_level["L2"] is ValidationStatus.SKIP

    def test_emits_failed_event(self, engine, logger):
        engine.validate("T-999")
        types = _types(logger)
        assert EventType.VALIDATION_FAILED in types
        # 顺序: completed 先落库, failed 追加收尾 (ADR-0003)
        assert types[-2] is EventType.VALIDATION_COMPLETED
        assert types[-1] is EventType.VALIDATION_FAILED
        failed = logger.store.query(event_type=EventType.VALIDATION_FAILED)[0]
        assert failed.result == "FAIL"
        assert failed.task_id == "T-999"
        assert failed.payload["reason"] == "task_not_found"
        assert failed.payload["failure_class"] == "task_not_found"
        completed = logger.store.query(event_type=EventType.VALIDATION_COMPLETED)[0]
        assert completed.result == "FAIL"


class TestValidateL1Failures:
    def test_corrupt_file(self, engine, logger, task_store):
        write_raw_task(task_store.dir, "T-001", "{broken json")
        report = engine.validate("T-001")
        assert report.task_found                      # 文件存在 → 非"未找到"
        assert report.result is ValidationStatus.FAIL
        assert report.reason == "task_data_invalid"
        l1 = {r.rule: r.status for r in report.results if r.level == "L1"}
        assert l1["task_exists"] is ValidationStatus.PASS
        assert l1["task_data"] is ValidationStatus.FAIL

    def test_invalid_status_field(self, engine, logger, task_store):
        write_raw_task(task_store.dir, "T-001",
                       json.dumps({"id": "T-001", "title": "x", "project": "p", "status": "BOGUS"}))
        report = engine.validate("T-001")
        assert report.result is ValidationStatus.FAIL
        # 数据规则最先失败 (父任务 ①②③④ 顺序); 状态规则同样给出具体诊断
        assert report.reason == "task_data_invalid"
        l1 = {r.rule: r.status for r in report.results if r.level == "L1"}
        assert l1["task_data"] is ValidationStatus.FAIL
        assert l1["task_status"] is ValidationStatus.FAIL

    def test_incomplete_file(self, engine, logger, task_store):
        write_raw_task(task_store.dir, "T-001", json.dumps({"id": "T-001"}))
        report = engine.validate("T-001")
        assert report.result is ValidationStatus.FAIL
        assert report.reason == "task_data_invalid"
        l1 = {r.rule: r.status for r in report.results if r.level == "L1"}
        assert l1["task_data"] is ValidationStatus.FAIL
        assert l1["task_files"] is ValidationStatus.FAIL

    def test_empty_title_only_files_fails(self, engine, logger, task_store):
        """title 为空串: 模型可接受 (无校验器) → 仅 task_files FAIL, reason 精确。"""
        write_raw_task(task_store.dir, "T-001",
                       json.dumps({"id": "T-001", "title": "", "project": "p",
                                   "status": "BACKLOG"}))
        report = engine.validate("T-001")
        assert report.result is ValidationStatus.FAIL
        assert report.reason == "task_files_incomplete"
        l1 = {r.rule: r.status for r in report.results if r.level == "L1"}
        assert l1["task_data"] is ValidationStatus.PASS
        assert l1["task_files"] is ValidationStatus.FAIL


class TestValidateL2:
    def test_workflow_mismatch_fails(self, engine, logger, task_store):
        """状态 DEVELOPMENT 但事件历史停在 BACKLOG → workflow_mismatch。"""
        create_task(task_store)
        record_created(logger)
        task_store.update_status("T-001", TaskStatus.DEVELOPMENT)
        report = engine.validate("T-001")
        assert report.result is ValidationStatus.FAIL
        assert report.reason == "workflow_mismatch"
        assert report.by_level["L2"] is ValidationStatus.FAIL

    def test_no_workflow_skips_l2(self, engine, logger, task_store):
        create_task(task_store, workflow=None)
        record_created(logger)
        report = engine.validate("T-001")
        assert report.passed
        assert report.by_level["L2"] is ValidationStatus.SKIP

    def test_history_consistent_passes(self, engine, logger, task_store):
        create_task(task_store)
        record_created(logger)
        record_updated(logger, to="TESTING")
        task_store.update_status("T-001", TaskStatus.TESTING)
        report = engine.validate("T-001")
        assert report.passed
        assert report.by_level["L2"] is ValidationStatus.PASS


class TestExpectStatus:
    def test_mismatch_fails(self, engine, logger, task_store):
        create_task(task_store)
        record_created(logger)
        report = engine.validate("T-001", expect_status=TaskStatus.DONE)
        assert report.result is ValidationStatus.FAIL
        assert report.reason == "status_mismatch"
        assert report.by_level["L2"] is ValidationStatus.FAIL

    def test_match_passes(self, engine, logger, task_store):
        create_task(task_store)
        record_created(logger)
        report = engine.validate("T-001", expect_status=TaskStatus.BACKLOG)
        assert report.passed
        assert report.reason is None


class TestRuleErrorHandling:
    def test_rule_exception_becomes_error(self, engine, logger, task_store, monkeypatch):
        """规则抛异常 → ERROR 兜底, 不中断其他规则 (report 含完整结果)。"""
        create_task(task_store)
        record_created(logger)

        def boom(task_id: str) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr("validation.engine.rules.rule_artifact", boom)
        report = engine.validate("T-001")
        artifact = [r for r in report.results if r.rule == "artifact"][0]
        assert artifact.status is ValidationStatus.ERROR
        assert "boom" in artifact.message
        # L1/L2 不受影响
        assert report.by_level["L1"] is ValidationStatus.PASS
        # 总判定 ERROR (非 FAIL) → 不发 validation.failed
        assert report.result is ValidationStatus.ERROR
        completed = logger.store.query(event_type=EventType.VALIDATION_COMPLETED)[0]
        assert completed.result == "ERROR"
        assert not logger.store.query(event_type=EventType.VALIDATION_FAILED)
