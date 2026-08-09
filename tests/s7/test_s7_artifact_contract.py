"""tests/s7/test_s7_artifact_contract.py — S7-002 类型契约 (Unit, ADR-0039)。

覆盖 (任务清单: prd/design/code/test/bug_report/release 声明式 required+validation):
- CONTRACTS 声明式覆盖全部 5 类型 (required_fields + validation_rules)
- validate_artifact: 缺失字段 → missing; 规则失败 (类型错/空值/空容器)
  → errors; 通过 → ok=True; 类型大小写不敏感; None 载荷 → 全缺失;
  未知类型 → ValueError
- ValidationResult 形状 (to_dict 可审计)
- 契约可扩展 (CONTRACTS 为普通 dict, 增条目即扩展 — 声明式)

依赖: 本目录 conftest (sys.path 挂 factory-org)。
"""

from __future__ import annotations

import pytest

from org.artifact import CONTRACTS, ValidationResult, validate_artifact
from org.projects import ArtifactType


def _prd_ok() -> dict:
    return {"problem": "p", "user": "u", "features": ["f1", "f2"]}


class TestContractsDeclared:
    def test_all_types_covered(self):
        """全部类型契约 (S7-002 六类型 + S8-001 扩展 idea/product + S8-002
        扩展 ux_ui + S9-004 扩展 project_analysis/baseline)。"""
        assert sorted(CONTRACTS) == [
            "baseline", "bug_report", "code", "design", "idea", "prd",
            "product", "project_analysis", "release", "test", "ux_ui",
        ]
        for contract in CONTRACTS.values():
            assert "required_fields" in contract
            assert "validation_rules" in contract

    def test_prd_contract_shape(self):
        assert CONTRACTS["prd"]["required_fields"] == ("problem", "user", "features")

    def test_design_contract_shape(self):
        """S8-003: design 契约强化为 7 节 (Architect Agent 输出; 旧
        architecture/api/database 3 节契约废弃)。"""
        assert CONTRACTS["design"]["required_fields"] == (
            "system_architecture", "technical_stack", "database_design",
            "api_design", "frontend_architecture", "backend_architecture",
            "task_breakdown",
        )

    def test_code_contract_shape(self):
        assert CONTRACTS["code"]["required_fields"] == ("files", "changes")

    def test_test_contract_shape(self):
        assert CONTRACTS["test"]["required_fields"] == ("results", "bugs")
        # S7-004 强化: results 必含 passed 键 (确定性测试结果契约)
        assert CONTRACTS["test"]["validation_rules"]["results"]["required_keys"] == ["passed"]

    def test_bug_report_contract_shape(self):
        assert CONTRACTS["bug_report"]["required_fields"] == (
            "location", "repro", "expected", "actual", "root_cause", "severity",
        )

    def test_release_contract_shape(self):
        """S8-004: release 契约强化为 5 节 (Release Agent 输出; 旧
        version/notes/artifact_ref 3 字段契约废弃)。"""
        assert CONTRACTS["release"]["required_fields"] == (
            "build_result", "version", "package", "release_notes", "deployment",
        )
        # S8-004 强化: build_result 必含 status/command; package 必含
        # name/type/files (构建结果/发布包清单结构化契约)
        assert CONTRACTS["release"]["validation_rules"]["build_result"][
            "required_keys"
        ] == ["status", "command"]
        assert CONTRACTS["release"]["validation_rules"]["package"][
            "required_keys"
        ] == ["name", "type", "files"]

    def test_contract_is_extensible_dict(self):
        """契约声明式: 普通 dict, 新增类型 = 枚举 + 本表加条目。"""
        assert isinstance(CONTRACTS, dict)
        assert set(CONTRACTS) == {t.value for t in ArtifactType}  # 与枚举同源


class TestValidatePrd:
    def test_valid_payload(self):
        result = validate_artifact("prd", _prd_ok())
        assert result.ok
        assert result.missing == []
        assert result.errors == []

    def test_all_missing(self):
        result = validate_artifact("prd", {})
        assert not result.ok
        assert result.missing == ["problem", "user", "features"]

    def test_partial_missing(self):
        result = validate_artifact("prd", {"problem": "p"})
        assert not result.ok
        assert result.missing == ["user", "features"]

    def test_features_empty_list_rule_fail(self):
        result = validate_artifact(
            "prd", {"problem": "p", "user": "u", "features": []}
        )
        assert not result.ok
        assert result.missing == []
        assert any("features" in e for e in result.errors)

    def test_features_wrong_type_rule_fail(self):
        result = validate_artifact(
            "prd", {"problem": "p", "user": "u", "features": "f1"}
        )
        assert not result.ok
        assert any("features" in e and "list" in e for e in result.errors)

    def test_problem_empty_string_rule_fail(self):
        result = validate_artifact(
            "prd", {"problem": "", "user": "u", "features": ["f1"]}
        )
        assert not result.ok
        assert any("problem" in e for e in result.errors)


class TestValidateOtherTypes:
    def test_design_valid(self):
        payload = {
            "system_architecture": "a",
            "technical_stack": {"lang": "python"},
            "database_design": {"table": "tx"},
            "api_design": {"endpoints": [{"method": "GET", "path": "/x"}]},
            "frontend_architecture": "f",
            "backend_architecture": "b",
            "task_breakdown": [{"module": "m", "task": "t"}],
        }
        assert validate_artifact("design", payload).ok

    def test_design_missing_task_breakdown(self):
        result = validate_artifact(
            "design",
            {
                "system_architecture": "a",
                "technical_stack": {"lang": "python"},
                "database_design": {"table": "tx"},
                "api_design": {"endpoints": [{"method": "GET", "path": "/x"}]},
                "frontend_architecture": "f",
                "backend_architecture": "b",
            },
        )
        assert not result.ok
        assert result.missing == ["task_breakdown"]

    def test_design_api_missing_endpoints_rule_fail(self):
        """S8-003: api_design dict 必含 endpoints (API 约定, Developer 消费)。"""
        payload = {
            "system_architecture": "a",
            "technical_stack": {"lang": "python"},
            "database_design": {"table": "tx"},
            "api_design": {"base_url": "/api"},
            "frontend_architecture": "f",
            "backend_architecture": "b",
            "task_breakdown": [{"module": "m", "task": "t"}],
        }
        result = validate_artifact("design", payload)
        assert not result.ok
        assert any("endpoints" in e for e in result.errors)

    def test_design_task_breakdown_empty_rule_fail(self):
        payload = {
            "system_architecture": "a",
            "technical_stack": {"lang": "python"},
            "database_design": {"table": "tx"},
            "api_design": {"endpoints": [{"method": "GET", "path": "/x"}]},
            "frontend_architecture": "f",
            "backend_architecture": "b",
            "task_breakdown": [],
        }
        result = validate_artifact("design", payload)
        assert not result.ok
        assert any("task_breakdown" in e for e in result.errors)

    def test_code_valid(self):
        payload = {"files": ["a.py", "b.py"], "changes": "add feature"}
        assert validate_artifact("code", payload).ok

    def test_code_missing_files(self):
        result = validate_artifact("code", {"changes": "x"})
        assert not result.ok
        assert result.missing == ["files"]

    def test_code_files_empty_rule_fail(self):
        result = validate_artifact("code", {"files": [], "changes": "x"})
        assert not result.ok
        assert any("files" in e for e in result.errors)

    def test_test_valid(self):
        payload = {"results": {"passed": 3, "failed": 1}, "bugs": ["b1"]}
        assert validate_artifact("test", payload).ok

    def test_test_results_missing_passed_rule_fail(self):
        """S7-004 强化: results 缺 passed 键 → 规则失败 (确定性契约)。"""
        result = validate_artifact("test", {"results": {"total": 3}, "bugs": []})
        assert not result.ok
        assert any("passed" in e for e in result.errors)

    def test_test_results_empty_dict_rule_fail(self):
        result = validate_artifact("test", {"results": {}, "bugs": []})
        assert not result.ok
        assert any("results" in e for e in result.errors)

    def test_test_bugs_missing(self):
        result = validate_artifact("test", {"results": {"passed": 1}})
        assert not result.ok
        assert result.missing == ["bugs"]

    def test_release_valid(self):
        payload = {
            "build_result": {"status": "success", "command": "python -m build"},
            "version": "1.0.0",
            "package": {"name": "app", "type": "tar.gz", "files": ["dist/app.tar.gz"]},
            "release_notes": "首个正式版本",
            "deployment": "解压发布包并启动服务",
        }
        assert validate_artifact("release", payload).ok

    def test_release_missing_deployment(self):
        result = validate_artifact(
            "release",
            {
                "build_result": {"status": "success", "command": "python -m build"},
                "version": "1.0.0",
                "package": {"name": "app", "type": "tar.gz", "files": ["dist/app.tar.gz"]},
                "release_notes": "首个正式版本",
            },
        )
        assert not result.ok
        assert result.missing == ["deployment"]

    def test_release_build_result_missing_keys_rule_fail(self):
        """S8-004 强化: build_result 缺 status/command → 规则失败。"""
        result = validate_artifact(
            "release",
            {
                "build_result": {"outcome": "ok"},
                "version": "1.0.0",
                "package": {"name": "app", "type": "tar.gz", "files": ["dist/app.tar.gz"]},
                "release_notes": "首个正式版本",
                "deployment": "解压发布包并启动服务",
            },
        )
        assert not result.ok
        assert any("status" in e and "command" in e for e in result.errors)


class TestValidateEdgeCases:
    def test_type_case_insensitive(self):
        result = validate_artifact("PRD", _prd_ok())
        assert result.ok
        assert result.type == "prd"

    def test_none_payload_all_missing(self):
        result = validate_artifact("release", None)
        assert not result.ok
        assert result.missing == [
            "build_result", "version", "package", "release_notes", "deployment",
        ]

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="invalid artifact type"):
            validate_artifact("bogus", {})

    def test_result_type_resolved(self):
        result = validate_artifact(ArtifactType.DESIGN, {"architecture": "a", "api": "b", "database": "c"})
        assert result.type == "design"

    def test_result_to_dict_shape(self):
        result = validate_artifact("prd", {})
        d = result.to_dict()
        assert d == {
            "type": "prd",
            "ok": False,
            "missing": ["problem", "user", "features"],
            "errors": [],
        }

    def test_result_is_dataclass(self):
        assert isinstance(validate_artifact("prd", _prd_ok()), ValidationResult)
