"""tests/s8/test_s8_release_contract.py — CONTRACTS release 5 节 (Unit, S8-004)。

覆盖 (任务清单: release 契约 5 节必填 + validation_rules):
- CONTRACTS["release"] required_fields = 5 节 (build_result/version/
  package/release_notes/deployment)
- validation_rules: build_result dict 必含 status/command; package dict
  必含 name/type/files; version/release_notes/deployment 非空 str
- validate_artifact: 全字段 ok / 缺字段 missing / 规则失败 errors
- ArtifactRegistry: release 产物契约校验 → VALIDATED / INVALID (invalid_reason
  落库 + org.artifact.failed 事件)
- 与 exec 侧 _local_validate 双体系一致 (str strip 判空; build_result/package
  深度校验在 exec 侧 — org 只保结构)

依赖: 本目录 conftest (org_dir/project_store/wlife/event_store) + s8_helpers。
"""

from __future__ import annotations

from org.artifact import validate_artifact
from org.projects import ArtifactStatus

from s8_helpers import event_sequence, release_payload_ok

#: release 契约 5 节 (与 CONTRACTS release required_fields / DevOps prompt 同源)
RELEASE_FIELDS = (
    "build_result",
    "version",
    "package",
    "release_notes",
    "deployment",
)


class TestReleaseContractDeclared:
    def test_release_required_fields_5_sections(self):
        """release 契约 5 节必填 (S8-004 Release Agent 输出契约)。"""
        from org.artifact import CONTRACTS

        assert CONTRACTS["release"]["required_fields"] == RELEASE_FIELDS

    def test_release_validation_rules(self):
        """规则: build_result dict 必含 status/command; package dict 必含
        name/type/files; 其余非空 str。"""
        from org.artifact import CONTRACTS

        rules = CONTRACTS["release"]["validation_rules"]
        assert rules["build_result"] == {
            "type": "dict",
            "min_keys": 1,
            "required_keys": ["status", "command"],
        }
        assert rules["package"] == {
            "type": "dict",
            "min_keys": 1,
            "required_keys": ["name", "type", "files"],
        }
        assert rules["version"] == {"type": "str", "min_length": 1}
        assert rules["release_notes"] == {"type": "str", "min_length": 1}
        assert rules["deployment"] == {"type": "str", "min_length": 1}

    def test_release_contract_in_enum(self):
        """契约与枚举同源: CONTRACTS 键集合 == ArtifactType 值集合。"""
        from org.artifact import CONTRACTS
        from org.projects import ArtifactType

        assert set(CONTRACTS) == {t.value for t in ArtifactType}
        assert ArtifactType.RELEASE.value == "release"


class TestValidateRelease:
    def test_valid_payload_ok(self):
        result = validate_artifact("release", release_payload_ok())
        assert result.ok
        assert result.missing == []
        assert result.errors == []

    def test_all_missing(self):
        result = validate_artifact("release", {})
        assert not result.ok
        assert result.missing == list(RELEASE_FIELDS)

    def test_partial_missing(self):
        payload = release_payload_ok()
        del payload["deployment"]
        result = validate_artifact("release", payload)
        assert not result.ok
        assert result.missing == ["deployment"]

    def test_build_result_empty_dict_rule_fail(self):
        payload = release_payload_ok()
        payload["build_result"] = {}
        result = validate_artifact("release", payload)
        assert not result.ok
        assert any("build_result" in e for e in result.errors)

    def test_build_result_missing_keys_rule_fail(self):
        payload = release_payload_ok()
        payload["build_result"] = {"outcome": "ok"}
        result = validate_artifact("release", payload)
        assert not result.ok
        assert any("status" in e and "command" in e for e in result.errors)

    def test_package_missing_keys_rule_fail(self):
        payload = release_payload_ok()
        payload["package"] = {"id": "pkg-1"}
        result = validate_artifact("release", payload)
        assert not result.ok
        assert any("name" in e and "type" in e and "files" in e for e in result.errors)

    def test_package_empty_dict_rule_fail(self):
        payload = release_payload_ok()
        payload["package"] = {}
        result = validate_artifact("release", payload)
        assert not result.ok
        assert any("package" in e for e in result.errors)

    def test_str_sections_blank_is_empty(self):
        """str 非空语义: 纯空白视为空串 (strip 判空, 与 exec 侧同规则)。"""
        payload = release_payload_ok()
        payload["release_notes"] = "   "
        result = validate_artifact("release", payload)
        assert not result.ok
        assert any("release_notes" in e for e in result.errors)

    def test_version_wrong_type_rule_fail(self):
        payload = release_payload_ok()
        payload["version"] = 1.0
        result = validate_artifact("release", payload)
        assert not result.ok
        assert any("version" in e and "str" in e for e in result.errors)

    def test_unknown_extra_fields_ignored(self):
        """artifact_refs 等附加键不影响契约 (validate_artifact 只查契约字段)。"""
        payload = release_payload_ok()
        payload["artifact_refs"] = ["A-CODE", "A-TEST"]
        result = validate_artifact("release", payload)
        assert result.ok

    def test_type_case_insensitive(self):
        result = validate_artifact("RELEASE", release_payload_ok())
        assert result.ok
        assert result.type == "release"


class TestRegistryRelease:
    def test_release_validated_via_registry(self, wlife, project_id):
        """Registry 校验: 合法 release 5 节载荷 → VALIDATED。"""
        wlife.create_workflow(project_id, "wf", workflow_id="WF-RC")
        stage = wlife.create_stage("WF-RC", "devops", stage_id="STG-RC")
        artifact = wlife.registry.create(
            stage.id,
            "release",
            project_id="P-8",
            producer_role="devops",
            metadata=release_payload_ok(),
            artifact_id="A-RC-OK",
        )
        wlife.registry.mark_generated(artifact.id)
        artifact, result = wlife.registry.validate(artifact.id)
        assert artifact.status is ArtifactStatus.VALIDATED
        assert result.ok

    def test_release_invalid_contract_persisted(self, wlife, project_id, event_store):
        """Registry 校验: 缺节 → INVALID (invalid_reason 落库 + artifact.failed 事件)。"""
        wlife.create_workflow(project_id, "wf", workflow_id="WF-RC2")
        stage = wlife.create_stage("WF-RC2", "devops", stage_id="STG-RC2")
        artifact = wlife.registry.create(
            stage.id,
            "release",
            project_id="P-8",
            producer_role="devops",
            metadata={"version": "只有一节"},
            artifact_id="A-RC-BAD",
        )
        wlife.registry.mark_generated(artifact.id)
        artifact, result = wlife.registry.validate(artifact.id)
        assert artifact.status is ArtifactStatus.INVALID
        assert not result.ok
        assert "build_result" in artifact.invalid_reason
        assert "package" in artifact.invalid_reason
        assert "org.artifact.failed" in event_sequence(event_store)

    def test_release_artifact_refs_passthrough(self, wlife, project_id):
        """artifact_refs 强引用随 metadata 落库 (发布产物溯源输入产物 id)。"""
        wlife.create_workflow(project_id, "wf", workflow_id="WF-RC3")
        stage = wlife.create_stage("WF-RC3", "devops", stage_id="STG-RC3")
        payload = release_payload_ok()
        payload["artifact_refs"] = ["A-CODE-1", "A-TEST-1"]
        artifact = wlife.registry.create(
            stage.id,
            "release",
            project_id="P-8",
            producer_role="devops",
            metadata=payload,
            artifact_id="A-RC-REFS",
        )
        assert artifact.metadata["artifact_refs"] == ["A-CODE-1", "A-TEST-1"]
        wlife.registry.mark_generated(artifact.id)
        artifact, result = wlife.registry.validate(artifact.id)
        assert artifact.status is ArtifactStatus.VALIDATED
        assert result.ok  # artifact_refs 附加键不破坏契约


class TestReleaseConsumptionPrep:
    def test_payload_build_result_structure(self):
        """build_result 必含 status/command (构建成败/命令 — 审计可复现)。"""
        build = release_payload_ok()["build_result"]
        assert {"status", "command"} <= set(build)
        assert build["status"] and build["command"]

    def test_payload_package_structure(self):
        """package 必含 name/type/files (发布包清单 — 部署消费)。"""
        pkg = release_payload_ok()["package"]
        assert {"name", "type", "files"} <= set(pkg)
        assert pkg["name"] and pkg["type"]
        assert isinstance(pkg["files"], list) and pkg["files"]

    def test_payload_fixed_sections_unchanged_by_others(self):
        """code/test payload 不受 release 契约影响 (各自独立, 回归)。"""
        from s8_helpers import code_payload_ok, qa_payload_ok

        assert validate_artifact("code", code_payload_ok()).ok
        assert validate_artifact("test", qa_payload_ok()).ok
