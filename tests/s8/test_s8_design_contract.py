"""tests/s8/test_s8_design_contract.py — CONTRACTS design 7 节 (Unit, S8-003)。

覆盖 (任务清单: design 契约 7 节必填 + validation_rules):
- CONTRACTS["design"] required_fields = 7 节 (system_architecture/
  technical_stack/database_design/api_design/frontend_architecture/
  backend_architecture/task_breakdown)
- validation_rules: task_breakdown list (min_items 1); api_design dict 必含
  endpoints (required_keys); 其余非空 (str min_length 1 / dict min_keys 1)
- validate_artifact: 全字段 ok / 缺字段 missing / 规则失败 errors
- ArtifactRegistry: design 产物契约校验 → VALIDATED / INVALID (invalid_reason
  落库 + org.artifact.failed 事件)
- 与 exec 侧 _local_validate 双体系一致 (str strip 判空; endpoints 深度
  校验在 exec 侧 — org 只保结构)

依赖: 本目录 conftest (org_dir/project_store/wlife/event_store) + s8_helpers。
"""

from __future__ import annotations

from org.artifact import validate_artifact
from org.projects import ArtifactStatus

from s8_helpers import (
    design_payload_ok,
    event_sequence,
    product_payload_ok,
    uxui_payload_ok,
)

#: design 契约 7 节 (与 CONTRACTS design required_fields 同源)
DESIGN_FIELDS = (
    "system_architecture",
    "technical_stack",
    "database_design",
    "api_design",
    "frontend_architecture",
    "backend_architecture",
    "task_breakdown",
)


class TestDesignContractDeclared:
    def test_design_required_fields_7_sections(self):
        """design 契约 7 节必填 (S8-003 Architect Agent 输出契约)。"""
        from org.artifact import CONTRACTS

        assert CONTRACTS["design"]["required_fields"] == DESIGN_FIELDS

    def test_design_validation_rules(self):
        """规则: task_breakdown list; api_design dict 必含 endpoints; 其余非空。"""
        from org.artifact import CONTRACTS

        rules = CONTRACTS["design"]["validation_rules"]
        assert rules["task_breakdown"] == {"type": "list", "min_items": 1}
        assert rules["api_design"] == {
            "type": "dict",
            "min_keys": 1,
            "required_keys": ["endpoints"],
        }
        assert rules["system_architecture"] == {"type": "str", "min_length": 1}
        assert rules["technical_stack"] == {"type": "dict", "min_keys": 1}
        assert rules["database_design"] == {"type": "dict", "min_keys": 1}
        assert rules["frontend_architecture"] == {"type": "str", "min_length": 1}
        assert rules["backend_architecture"] == {"type": "str", "min_length": 1}

    def test_design_contract_in_enum(self):
        """契约与枚举同源: CONTRACTS 键集合 == ArtifactType 值集合。"""
        from org.artifact import CONTRACTS
        from org.projects import ArtifactType

        assert set(CONTRACTS) == {t.value for t in ArtifactType}
        assert ArtifactType.DESIGN.value == "design"


class TestValidateDesign:
    def test_valid_payload_ok(self):
        result = validate_artifact("design", design_payload_ok())
        assert result.ok
        assert result.missing == []
        assert result.errors == []

    def test_all_missing(self):
        result = validate_artifact("design", {})
        assert not result.ok
        assert result.missing == list(DESIGN_FIELDS)

    def test_partial_missing(self):
        payload = design_payload_ok()
        del payload["task_breakdown"]
        result = validate_artifact("design", payload)
        assert not result.ok
        assert result.missing == ["task_breakdown"]

    def test_task_breakdown_empty_rule_fail(self):
        payload = design_payload_ok(task_count=0)
        result = validate_artifact("design", payload)
        assert not result.ok
        assert any("task_breakdown" in e for e in result.errors)

    def test_task_breakdown_wrong_type_rule_fail(self):
        payload = design_payload_ok()
        payload["task_breakdown"] = "not-a-list"
        result = validate_artifact("design", payload)
        assert not result.ok
        assert any("task_breakdown" in e and "list" in e for e in result.errors)

    def test_api_design_missing_endpoints_rule_fail(self):
        payload = design_payload_ok()
        payload["api_design"] = {"base_url": "/api"}
        result = validate_artifact("design", payload)
        assert not result.ok
        assert any("endpoints" in e for e in result.errors)

    def test_api_design_empty_dict_rule_fail(self):
        payload = design_payload_ok()
        payload["api_design"] = {}
        result = validate_artifact("design", payload)
        assert not result.ok
        assert any("api_design" in e for e in result.errors)

    def test_str_sections_blank_is_empty(self):
        """str 非空语义: 纯空白视为空串 (strip 判空, 与 exec 侧同规则)。"""
        payload = design_payload_ok()
        payload["system_architecture"] = "   "
        result = validate_artifact("design", payload)
        assert not result.ok
        assert any("system_architecture" in e for e in result.errors)

    def test_technical_stack_empty_dict_rule_fail(self):
        payload = design_payload_ok()
        payload["technical_stack"] = {}
        result = validate_artifact("design", payload)
        assert not result.ok
        assert any("technical_stack" in e for e in result.errors)

    def test_database_design_wrong_type_rule_fail(self):
        payload = design_payload_ok()
        payload["database_design"] = "no-db"
        result = validate_artifact("design", payload)
        assert not result.ok
        assert any("database_design" in e and "dict" in e for e in result.errors)

    def test_unknown_extra_fields_ignored(self):
        """artifact_refs 等附加键不影响契约 (validate_artifact 只查契约字段)。"""
        payload = design_payload_ok()
        payload["artifact_refs"] = ["A-PROD", "A-UXUI"]
        result = validate_artifact("design", payload)
        assert result.ok

    def test_type_case_insensitive(self):
        result = validate_artifact("DESIGN", design_payload_ok())
        assert result.ok
        assert result.type == "design"


class TestRegistryDesign:
    def test_design_validated_via_registry(self, wlife, project_id):
        """Registry 校验: 合法 design 7 节载荷 → VALIDATED。"""
        wlife.create_workflow(project_id, "wf", workflow_id="WF-DC")
        stage = wlife.create_stage("WF-DC", "architect", stage_id="STG-DC")
        artifact = wlife.registry.create(
            stage.id,
            "design",
            project_id="P-8",
            producer_role="architect",
            metadata=design_payload_ok(),
            artifact_id="A-DC-OK",
        )
        wlife.registry.mark_generated(artifact.id)
        artifact, result = wlife.registry.validate(artifact.id)
        assert artifact.status is ArtifactStatus.VALIDATED
        assert result.ok

    def test_design_invalid_contract_persisted(self, wlife, project_id, event_store):
        """Registry 校验: 缺节 → INVALID (invalid_reason 落库 + artifact.failed 事件)。"""
        wlife.create_workflow(project_id, "wf", workflow_id="WF-DC2")
        stage = wlife.create_stage("WF-DC2", "architect", stage_id="STG-DC2")
        artifact = wlife.registry.create(
            stage.id,
            "design",
            project_id="P-8",
            producer_role="architect",
            metadata={"system_architecture": "只有一节"},
            artifact_id="A-DC-BAD",
        )
        wlife.registry.mark_generated(artifact.id)
        artifact, result = wlife.registry.validate(artifact.id)
        assert artifact.status is ArtifactStatus.INVALID
        assert not result.ok
        assert "task_breakdown" in artifact.invalid_reason
        assert "technical_stack" in artifact.invalid_reason
        assert "org.artifact.failed" in event_sequence(event_store)

    def test_design_artifact_refs_passthrough(self, wlife, project_id):
        """artifact_refs 强引用随 metadata 落库 (设计产物溯源输入产物 id)。"""
        wlife.create_workflow(project_id, "wf", workflow_id="WF-DC3")
        stage = wlife.create_stage("WF-DC3", "architect", stage_id="STG-DC3")
        payload = design_payload_ok()
        payload["artifact_refs"] = ["A-PROD-1", "A-UXUI-1"]
        artifact = wlife.registry.create(
            stage.id,
            "design",
            project_id="P-8",
            producer_role="architect",
            metadata=payload,
            artifact_id="A-DC-REFS",
        )
        assert artifact.metadata["artifact_refs"] == ["A-PROD-1", "A-UXUI-1"]
        wlife.registry.mark_generated(artifact.id)
        artifact, result = wlife.registry.validate(artifact.id)
        assert artifact.status is ArtifactStatus.VALIDATED
        assert result.ok  # artifact_refs 附加键不破坏契约


class TestDesignConsumptionPrep:
    def test_payload_endpoints_structure(self):
        """api_design.endpoints 每项含 method/path/contract (API 约定 —
        Developer 消费)。"""
        for ep in design_payload_ok()["api_design"]["endpoints"]:
            assert {"method", "path", "contract"} <= set(ep)
            assert ep["method"] and ep["path"]

    def test_payload_task_breakdown_developer_fields(self):
        """task_breakdown 每项含 module/task/api_contract/ui_guidance —
        S8-005 Developer 消费 (任务拆分/API 约定/UI 实现指导)。"""
        for task in design_payload_ok()["task_breakdown"]:
            assert {"module", "task", "api_contract", "ui_guidance"} <= set(task)
            assert task["module"] and task["task"]
            assert task["api_contract"] and task["ui_guidance"]

    def test_payload_fixed_sections_unchanged_by_others(self):
        """product/ux_ui payload 不受 design 契约影响 (各自独立, 回归)。"""
        assert validate_artifact("product", product_payload_ok()).ok
        assert validate_artifact("ux_ui", uxui_payload_ok()).ok
