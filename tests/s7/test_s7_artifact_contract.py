"""tests/s7/test_s7_artifact_contract.py — S7-002 类型契约 (Unit, ADR-0039)。

覆盖 (任务清单: prd/design/code/test/release 声明式 required+validation):
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
    def test_all_five_types_covered(self):
        assert sorted(CONTRACTS) == ["code", "design", "prd", "release", "test"]
        for contract in CONTRACTS.values():
            assert "required_fields" in contract
            assert "validation_rules" in contract

    def test_prd_contract_shape(self):
        assert CONTRACTS["prd"]["required_fields"] == ("problem", "user", "features")

    def test_design_contract_shape(self):
        assert CONTRACTS["design"]["required_fields"] == (
            "architecture", "api", "database",
        )

    def test_code_contract_shape(self):
        assert CONTRACTS["code"]["required_fields"] == ("files", "changes")

    def test_test_contract_shape(self):
        assert CONTRACTS["test"]["required_fields"] == ("results", "bugs")

    def test_release_contract_shape(self):
        assert CONTRACTS["release"]["required_fields"] == (
            "version", "notes", "artifact_ref",
        )

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
        payload = {"architecture": "a", "api": "b", "database": "c"}
        assert validate_artifact("design", payload).ok

    def test_design_missing_database(self):
        result = validate_artifact("design", {"architecture": "a", "api": "b"})
        assert not result.ok
        assert result.missing == ["database"]

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

    def test_test_results_empty_dict_rule_fail(self):
        result = validate_artifact("test", {"results": {}, "bugs": []})
        assert not result.ok
        assert any("results" in e for e in result.errors)

    def test_test_bugs_missing(self):
        result = validate_artifact("test", {"results": {"passed": 1}})
        assert not result.ok
        assert result.missing == ["bugs"]

    def test_release_valid(self):
        payload = {"version": "1.0.0", "notes": "n", "artifact_ref": "A-2"}
        assert validate_artifact("release", payload).ok

    def test_release_missing_notes(self):
        result = validate_artifact("release", {"version": "1.0.0", "artifact_ref": "A-2"})
        assert not result.ok
        assert result.missing == ["notes"]


class TestValidateEdgeCases:
    def test_type_case_insensitive(self):
        result = validate_artifact("PRD", _prd_ok())
        assert result.ok
        assert result.type == "prd"

    def test_none_payload_all_missing(self):
        result = validate_artifact("release", None)
        assert not result.ok
        assert result.missing == ["version", "notes", "artifact_ref"]

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
