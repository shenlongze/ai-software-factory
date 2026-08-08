"""tests/s7/test_s7_tester_role.py — Tester 角色 + bug_report 契约 (Unit, S7-004)。

覆盖 (任务清单: Tester execution_kind/prompt/bug_report CONTRACTS/Registry):
- roles.py: tester execution_kind planning→executable; prompt 含测试策略
  (运行测试/分析失败/生成 bug report); executable_role_ids 含 tester
- org_role_coverage: qa → execution_kind=executable (双体系统一)
- ArtifactType.BUG_REPORT 枚举成员 (宽容解析)
- CONTRACTS bug_report: 声明式 6 字段契约 + 校验通过/缺失/空值/严重级
- test 契约强化: results 必含 passed (S7-004)
- ArtifactRegistry: bug_report 产物 create→generated→validate 全链
  (通过 → VALIDATED / 契约失败 → INVALID) + 类型查询过滤

依赖: 本目录 conftest (project_store + registry + logger)。

"""

from __future__ import annotations

import pytest

from org.artifact import CONTRACTS, validate_artifact
from org.projects import ArtifactStatus, ArtifactType

import exec.roles as roles


def _bug_ok() -> dict:
    return {
        "location": "calc.py:6 (sub)",
        "repro": "运行 test_sub",
        "expected": "sub(5, 3) == 2",
        "actual": "sub(5, 3) == 8",
        "root_cause": "sub 误用加法",
        "severity": "high",
    }


class TestTesterRole:
    def test_tester_executable(self):
        """S7-004: Tester execution_kind planning → executable。"""
        tester = roles.require_role("tester")
        assert tester.execution_kind == "executable"
        assert tester.is_executable

    def test_tester_prompt_covers_test_strategy(self):
        """Tester prompt = 测试策略: 运行测试/分析失败/生成 bug report/修复任务。"""
        prompt = roles.require_role("tester").prompt_template
        assert "运行测试" in prompt
        assert "分析失败" in prompt
        assert "bug report" in prompt
        assert "修复任务" in prompt
        assert "unittest/pytest" in prompt

    def test_executable_role_ids_include_tester(self):
        """S8-003 扩展: architect + developer + product-manager + tester +
        ui-designer (按 role_id 排序)。"""
        assert roles.executable_role_ids() == [
            "architect", "developer", "product-manager", "tester", "ui-designer",
        ]

    def test_org_coverage_tester_executable(self):
        """双体系统一: org 模板 qa → exec tester (execution_kind=executable)。"""
        coverage = roles.org_role_coverage()
        assert coverage["qa"]["role_id"] == "tester"
        assert coverage["qa"]["resolved"] is True
        assert coverage["qa"]["execution_kind"] == "executable"

    def test_tester_capabilities_unchanged(self):
        assert set(roles.capabilities_for_role("tester")) == {"testing", "verification"}

    def test_resolve_tester_alias(self):
        assert roles.resolve_role("qa").role_id == "tester"


class TestArtifactType:
    def test_bug_report_member(self):
        assert ArtifactType.BUG_REPORT.value == "bug_report"

    def test_parse_case_insensitive(self):
        assert ArtifactType.parse("BUG_REPORT") is ArtifactType.BUG_REPORT

    def test_unknown_still_raises(self):
        with pytest.raises(ValueError, match="invalid artifact type"):
            ArtifactType.parse("nope")


class TestBugReportContract:
    def test_contract_declared(self):
        assert CONTRACTS["bug_report"]["required_fields"] == (
            "location", "repro", "expected", "actual", "root_cause", "severity",
        )

    def test_valid_payload(self):
        assert validate_artifact("bug_report", _bug_ok()).ok

    def test_missing_fields(self):
        result = validate_artifact("bug_report", {"location": "l"})
        assert not result.ok
        assert result.missing == ["repro", "expected", "actual", "root_cause", "severity"]

    def test_empty_string_rule_fail(self):
        result = validate_artifact(
            "bug_report", {**{k: "x" for k in _bug_ok()}, "root_cause": ""}
        )
        assert not result.ok
        assert any("root_cause" in e for e in result.errors)

    def test_severity_required(self):
        result = validate_artifact(
            "bug_report", {k: v for k, v in _bug_ok().items() if k != "severity"}
        )
        assert not result.ok
        assert result.missing == ["severity"]

    def test_type_case_insensitive(self):
        assert validate_artifact("BUG_REPORT", _bug_ok()).ok

    def test_none_payload_all_missing(self):
        result = validate_artifact("bug_report", None)
        assert result.missing == list(CONTRACTS["bug_report"]["required_fields"])


class TestTestContractStrengthened:
    def test_results_requires_passed_key(self):
        """S7-004 强化: test.results 必含 passed (确定性测试结果契约)。"""
        ok = validate_artifact("test", {"results": {"passed": True, "total": 2}, "bugs": []})
        assert ok.ok
        bad = validate_artifact("test", {"results": {"total": 2}, "bugs": []})
        assert not bad.ok
        assert any("passed" in e for e in bad.errors)


class TestRegistryBugReport:
    def test_bug_report_lifecycle_validated(self, registry, project_store):
        """bug_report 产物全链: create → generated → validate → VALIDATED。"""
        from org.projects import ProjectLifecycle

        ProjectLifecycle(project_store).create_project("P", project_id="P-1")
        ProjectLifecycle(project_store).create_stage("WF-1", "tester", stage_id="STG-1")
        artifact = registry.create("STG-1", "bug_report", project_id="P-1",
                                   metadata=_bug_ok(), artifact_id="A-BUG-1")
        registry.mark_generated("A-BUG-1")
        artifact, result = registry.validate("A-BUG-1")
        assert result.ok
        assert artifact.status is ArtifactStatus.VALIDATED

    def test_bug_report_contract_failure_invalid(self, registry, project_store):
        from org.projects import ProjectLifecycle

        ProjectLifecycle(project_store).create_project("P", project_id="P-1")
        ProjectLifecycle(project_store).create_stage("WF-1", "tester", stage_id="STG-1")
        registry.create("STG-1", "bug_report", project_id="P-1",
                        metadata={"location": "l"}, artifact_id="A-BUG-2")
        registry.mark_generated("A-BUG-2")
        artifact, result = registry.validate("A-BUG-2")
        assert not result.ok
        assert artifact.status is ArtifactStatus.INVALID

    def test_bug_report_type_query(self, registry, project_store):
        from org.projects import ProjectLifecycle

        ProjectLifecycle(project_store).create_project("P", project_id="P-1")
        ProjectLifecycle(project_store).create_stage("WF-1", "tester", stage_id="STG-1")
        registry.create("STG-1", "bug_report", project_id="P-1", metadata=_bug_ok(),
                        artifact_id="A-BUG-3")
        registry.mark_generated("A-BUG-3")
        registry.validate("A-BUG-3")
        found = registry.query(type_="bug_report")
        assert [a.id for a in found] == ["A-BUG-3"]
        assert registry.query(type_="bug_report", status="validated")[0].id == "A-BUG-3"
