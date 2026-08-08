"""tests/s8/test_s8_uxui_contract.py — CONTRACTS ux_ui 类型 (Unit, S8-002)。

覆盖 (任务清单: ux_ui 7 节必填 + validation_rules 结构校验):
- ArtifactType.UX_UI 枚举成员 (宽容解析)
- CONTRACTS ux_ui: required_fields 7 节 (information_architecture/user_flow/
  wireframe/screen_specifications/component_definition/design_tokens/prototype)
- validation_rules 结构校验: wireframe dict 必含 screens / screen_specifications
  list / design_tokens dict / 其余节非空 (str/list/dict 规则)
- ArtifactRegistry: ux_ui 产物 create→generated→validate 全链
  (通过 → VALIDATED / 契约失败 → INVALID) + 类型查询过滤

依赖: 本目录 conftest (project_store + registry + logger)。
"""

from __future__ import annotations

import pytest

from org.artifact import CONTRACTS, ArtifactRegistry, validate_artifact
from org.projects import ArtifactStatus, ArtifactType, ProjectStore

from s8_helpers import uxui_payload_ok

#: ux_ui 契约 7 节 (任务清单: 7 节必填)
UXUI_FIELDS = (
    "information_architecture",
    "user_flow",
    "wireframe",
    "screen_specifications",
    "component_definition",
    "design_tokens",
    "prototype",
)


class TestArtifactType:
    def test_ux_ui_member(self):
        assert ArtifactType.UX_UI.value == "ux_ui"

    def test_parse_case_insensitive(self):
        assert ArtifactType.parse("UX_UI") is ArtifactType.UX_UI
        assert ArtifactType.parse("Ux_Ui") is ArtifactType.UX_UI

    def test_unknown_still_raises(self):
        with pytest.raises(ValueError, match="invalid artifact type"):
            ArtifactType.parse("nope")


class TestUxUiContract:
    def test_contract_declared_7_fields(self):
        """ux_ui 契约: required_fields 7 节 (任务清单同序)。"""
        assert CONTRACTS["ux_ui"]["required_fields"] == UXUI_FIELDS
        assert len(UXUI_FIELDS) == 7

    def test_contract_rules_shape(self):
        """validation_rules: 结构校验 (wireframe 含 screens / screen_specs
        list / design_tokens dict / 其余非空)。"""
        rules = CONTRACTS["ux_ui"]["validation_rules"]
        assert rules["information_architecture"] == {"type": "dict", "min_keys": 1}
        assert rules["user_flow"] == {"type": "list", "min_items": 1}
        assert rules["wireframe"] == {
            "type": "dict", "min_keys": 1, "required_keys": ["screens"],
        }
        assert rules["screen_specifications"] == {"type": "list", "min_items": 1}
        assert rules["component_definition"] == {"type": "list", "min_items": 1}
        assert rules["design_tokens"] == {"type": "dict", "min_keys": 1}
        assert rules["prototype"] == {"type": "str", "min_length": 1}

    def test_valid_uxui_payload(self):
        assert validate_artifact("ux_ui", uxui_payload_ok()).ok

    def test_missing_section(self):
        """缺任一节 → missing 响亮 (如缺 wireframe)。"""
        payload = uxui_payload_ok()
        del payload["wireframe"]
        result = validate_artifact("ux_ui", payload)
        assert not result.ok
        assert result.missing == ["wireframe"]

    def test_missing_most_sections(self):
        """只给一节 → 其余 6 节全部 missing (7 节必填)。"""
        result = validate_artifact("ux_ui", {"prototype": "p"})
        assert not result.ok
        assert result.missing == [
            "information_architecture", "user_flow", "wireframe",
            "screen_specifications", "component_definition", "design_tokens",
        ]

    def test_wireframe_missing_screens(self):
        """wireframe 缺 screens 键 → required_keys 失败 (结构校验)。"""
        payload = uxui_payload_ok()
        payload["wireframe"] = {"notes": "无 screens"}
        result = validate_artifact("ux_ui", payload)
        assert not result.ok
        assert result.errors == ["wireframe: missing required keys: screens"]

    def test_wireframe_not_dict(self):
        """wireframe 非 dict → 类型约束失败。"""
        payload = uxui_payload_ok()
        payload["wireframe"] = "纯文字线框"
        result = validate_artifact("ux_ui", payload)
        assert not result.ok
        assert result.errors == ["wireframe: expected dict, got str"]

    def test_information_architecture_empty(self):
        """information_architecture 空 dict → min_keys 失败。"""
        payload = uxui_payload_ok()
        payload["information_architecture"] = {}
        result = validate_artifact("ux_ui", payload)
        assert not result.ok
        assert result.errors == ["information_architecture: min keys 1"]

    def test_information_architecture_not_dict(self):
        payload = uxui_payload_ok()
        payload["information_architecture"] = ["screens"]
        result = validate_artifact("ux_ui", payload)
        assert not result.ok
        assert result.errors == [
            "information_architecture: expected dict, got list",
        ]

    def test_user_flow_empty(self):
        """user_flow 空 list → min_items 失败。"""
        payload = uxui_payload_ok()
        payload["user_flow"] = []
        result = validate_artifact("ux_ui", payload)
        assert not result.ok
        assert result.errors == ["user_flow: min items 1"]

    def test_screen_specifications_empty(self):
        """screen_specifications 空 list → min_items 失败 (结构校验)。"""
        payload = uxui_payload_ok()
        payload["screen_specifications"] = []
        result = validate_artifact("ux_ui", payload)
        assert not result.ok
        assert result.errors == ["screen_specifications: min items 1"]

    def test_screen_specifications_not_list(self):
        payload = uxui_payload_ok()
        payload["screen_specifications"] = "规格说明"
        result = validate_artifact("ux_ui", payload)
        assert not result.ok
        assert result.errors == ["screen_specifications: expected list, got str"]

    def test_component_definition_empty(self):
        payload = uxui_payload_ok()
        payload["component_definition"] = []
        result = validate_artifact("ux_ui", payload)
        assert not result.ok
        assert result.errors == ["component_definition: min items 1"]

    def test_design_tokens_empty(self):
        """design_tokens 空 dict → min_keys 失败 (结构校验)。"""
        payload = uxui_payload_ok()
        payload["design_tokens"] = {}
        result = validate_artifact("ux_ui", payload)
        assert not result.ok
        assert result.errors == ["design_tokens: min keys 1"]

    def test_design_tokens_not_dict(self):
        payload = uxui_payload_ok()
        payload["design_tokens"] = ["colors"]
        result = validate_artifact("ux_ui", payload)
        assert not result.ok
        assert result.errors == ["design_tokens: expected dict, got list"]

    def test_prototype_empty(self):
        """prototype 纯空白 → min_length 失败 (str 非空按 strip 判定)。"""
        payload = uxui_payload_ok()
        payload["prototype"] = "   "
        result = validate_artifact("ux_ui", payload)
        assert not result.ok
        assert result.errors == ["prototype: min length 1"]

    def test_prototype_not_str(self):
        payload = uxui_payload_ok()
        payload["prototype"] = ["点击交互"]
        result = validate_artifact("ux_ui", payload)
        assert not result.ok
        assert result.errors == ["prototype: expected str, got list"]


class TestUxUiRegistry:
    def _seed_stage(self, registry: ArtifactRegistry) -> None:
        """最小 stage 种子 (产物关联校验前置; stage 必须存在)。"""
        from org.projects import ProjectLifecycle

        plife = ProjectLifecycle(registry.store)
        plife.create_project("Build App", project_id="P-8")
        plife.create_stage("WF-8", "ui-designer", stage_id="STG-8")

    def test_registry_uxui_validated(self, project_store: ProjectStore, logger):
        """ux_ui 产物全链: create → generated → validate → VALIDATED。"""
        registry = ArtifactRegistry(project_store, logger=logger)
        self._seed_stage(registry)
        artifact = registry.create(
            "STG-8", "ux_ui", project_id="P-8",
            producer_role="ui-designer", metadata=uxui_payload_ok(),
            artifact_id="A-UXUI-1",
        )
        registry.mark_generated(artifact.id)
        updated, result = registry.validate(artifact.id)
        assert result.ok
        assert updated.status is ArtifactStatus.VALIDATED

    def test_registry_uxui_invalid(self, project_store: ProjectStore, logger):
        """契约失败 → 产物 INVALID (invalid_reason 落库审计)。"""
        registry = ArtifactRegistry(project_store, logger=logger)
        self._seed_stage(registry)
        bad = uxui_payload_ok()
        del bad["screen_specifications"]
        artifact = registry.create(
            "STG-8", "ux_ui", project_id="P-8",
            producer_role="ui-designer", metadata=bad,
            artifact_id="A-UXUI-2",
        )
        registry.mark_generated(artifact.id)
        updated, result = registry.validate(artifact.id)
        assert not result.ok
        assert updated.status is ArtifactStatus.INVALID
        assert "screen_specifications" in updated.invalid_reason

    def test_registry_uxui_query_filter(self, project_store: ProjectStore, logger):
        """类型查询: ux_ui 产物按 type 过滤 (组合查询)。"""
        registry = ArtifactRegistry(project_store, logger=logger)
        self._seed_stage(registry)
        registry.create(
            "STG-8", "ux_ui", project_id="P-8",
            producer_role="ui-designer", metadata=uxui_payload_ok(),
            artifact_id="A-UXUI-3",
        )
        registry.create(
            "STG-8", "product", project_id="P-8",
            producer_role="product-manager", metadata={"market_analysis": "x"},
            artifact_id="A-PROD-3",
        )
        uxuis = registry.query(type_="ux_ui")
        products = registry.query(type_="product")
        assert [a.id for a in uxuis] == ["A-UXUI-3"]
        assert [a.id for a in products] == ["A-PROD-3"]
