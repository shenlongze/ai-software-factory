"""test_validation_reports.py — ValidationReport 汇总 (层/总判定) + 输出格式测试。"""

from __future__ import annotations

from validation.models import ValidationResult, ValidationStatus
from validation.reports import ValidationReport, render_checks


def _res(level: str, rule: str, status: ValidationStatus) -> ValidationResult:
    return ValidationResult(
        id=f"{level}.{rule}", task_id="T-001", level=level,
        rule=rule, status=status, message="m",
    )


def _pass_report(**overrides: object) -> ValidationReport:
    """典型通过报告: L1 全 PASS, L2 PASS, L3 SKIP (Hook)。"""
    base: dict[str, object] = dict(
        task_id="T-001",
        results=[
            _res("L1", "task_exists", ValidationStatus.PASS),
            _res("L1", "task_data", ValidationStatus.PASS),
            _res("L1", "task_status", ValidationStatus.PASS),
            _res("L1", "task_files", ValidationStatus.PASS),
            _res("L2", "workflow", ValidationStatus.PASS),
            _res("L3", "artifact", ValidationStatus.SKIP),
        ],
    )
    base.update(overrides)
    return ValidationReport(**base)


class TestAggregation:
    def test_pass_with_skip_layers(self):
        """全 PASS + L3 SKIP → 总判定 PASS (SKIP 不阻止通过)。"""
        report = _pass_report()
        assert report.result is ValidationStatus.PASS
        assert report.passed

    def test_fail_beats_skip(self):
        report = ValidationReport(task_id="T-001", results=[
            _res("L1", "task_exists", ValidationStatus.FAIL),
            _res("L2", "workflow", ValidationStatus.SKIP),
            _res("L3", "artifact", ValidationStatus.SKIP),
        ])
        assert report.result is ValidationStatus.FAIL
        assert not report.passed

    def test_error_result(self):
        report = ValidationReport(task_id="T-001", results=[
            _res("L1", "task_exists", ValidationStatus.PASS),
            _res("L3", "artifact", ValidationStatus.ERROR),
        ])
        assert report.result is ValidationStatus.ERROR
        assert not report.passed

    def test_by_level_worst_non_skip(self):
        """层状态 = 层内非 SKIP 规则最差; 整层全 SKIP 显示 SKIP。"""
        report = ValidationReport(task_id="T-001", results=[
            _res("L1", "task_exists", ValidationStatus.PASS),
            _res("L1", "task_data", ValidationStatus.FAIL),
            _res("L2", "workflow", ValidationStatus.PASS),
            _res("L3", "artifact", ValidationStatus.SKIP),
        ])
        assert report.by_level == {"L1": ValidationStatus.FAIL,
                                   "L2": ValidationStatus.PASS,
                                   "L3": ValidationStatus.SKIP}

    def test_empty_results_passes(self):
        """无规则 → PASS (防御性默认)。"""
        report = ValidationReport(task_id="T-001", results=[])
        assert report.result is ValidationStatus.PASS
        assert report.by_level == {"L1": ValidationStatus.SKIP,
                                   "L2": ValidationStatus.SKIP,
                                   "L3": ValidationStatus.SKIP}

    def test_reason_maps_first_failure(self):
        report = ValidationReport(task_id="T-001", results=[
            _res("L1", "task_exists", ValidationStatus.FAIL),
            _res("L1", "task_files", ValidationStatus.FAIL),
        ])
        assert report.reason == "task_not_found"

    def test_reason_none_when_pass(self):
        assert _pass_report().reason is None

    def test_reason_status_mismatch(self):
        report = ValidationReport(task_id="T-001", results=[
            _res("L2", "expect_status", ValidationStatus.FAIL),
        ])
        assert report.reason == "status_mismatch"


class TestFormat:
    def test_to_text_exact_sample(self):
        """父任务样例输出逐字一致。"""
        assert _pass_report().to_text() == (
            "Validation Report\n"
            "Task: T-001\n"
            "L1 Factory    PASS\n"
            "L2 Workflow   PASS\n"
            "L3 Artifact   SKIP\n"
            "Result: PASS"
        )

    def test_to_text_fail(self):
        report = ValidationReport(task_id="T-001", results=[
            _res("L1", "task_exists", ValidationStatus.FAIL),
            _res("L2", "workflow", ValidationStatus.SKIP),
            _res("L3", "artifact", ValidationStatus.SKIP),
        ])
        text = report.to_text()
        assert "L1 Factory    FAIL" in text
        assert "L2 Workflow   SKIP" in text
        assert "Result: FAIL" in text

    def test_to_text_missing_task(self):
        report = ValidationReport(task_id="T-999", results=[
            _res("L1", "task_exists", ValidationStatus.FAIL),
            _res("L2", "workflow", ValidationStatus.SKIP),
            _res("L3", "artifact", ValidationStatus.SKIP),
        ])
        assert "Task: T-999" in report.to_text()
        assert "Result: FAIL" in report.to_text()

    def test_render_checks_shape(self):
        """checks 载荷: {id, name, status, detail} (Phase 2 契约)。"""
        checks = render_checks(_pass_report().results)
        assert len(checks) == 6
        assert checks[0] == {"id": "L1.task_exists", "name": "任务存在",
                             "status": "PASS", "detail": "m"}
        assert checks[-1]["id"] == "L3.artifact"
        assert checks[-1]["status"] == "SKIP"
