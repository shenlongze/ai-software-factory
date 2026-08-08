"""tests/s8/test_s8_product_contract.py — CONTRACTS product 类型 (Unit, S8-001)。

覆盖 (任务清单: product 7 节必填 + validation_rules):
- ArtifactType.PRODUCT / IDEA 枚举成员 (宽容解析)
- CONTRACTS product: required_fields 7 节 (market_analysis/user_persona/
  user_journey/problem_statement/feature_list/mvp_scope/user_stories)
- validation_rules: str 节非空 / feature_list 是 list / mvp_scope dict 含
  in/out / user_stories 非空 list
- idea 契约 (PM 阶段输入, 自然语言)
- ArtifactRegistry: product 产物 create→generated→validate 全链
  (通过 → VALIDATED / 契约失败 → INVALID) + 类型查询过滤

依赖: 本目录 conftest (project_store + registry + logger)。
"""

from __future__ import annotations

import pytest

from org.artifact import CONTRACTS, ArtifactRegistry, validate_artifact
from org.projects import ArtifactStatus, ArtifactType, ProjectStore

from s8_helpers import product_payload_ok

#: product 契约 7 节 (任务清单: 7 节必填)
PRODUCT_FIELDS = (
    "market_analysis",
    "user_persona",
    "user_journey",
    "problem_statement",
    "feature_list",
    "mvp_scope",
    "user_stories",
)


class TestArtifactType:
    def test_product_member(self):
        assert ArtifactType.PRODUCT.value == "product"

    def test_idea_member(self):
        assert ArtifactType.IDEA.value == "idea"

    def test_parse_case_insensitive(self):
        assert ArtifactType.parse("PRODUCT") is ArtifactType.PRODUCT
        assert ArtifactType.parse("Product") is ArtifactType.PRODUCT
        assert ArtifactType.parse("IDEA") is ArtifactType.IDEA

    def test_unknown_still_raises(self):
        with pytest.raises(ValueError, match="invalid artifact type"):
            ArtifactType.parse("nope")


class TestProductContract:
    def test_contract_declared_7_fields(self):
        """product 契约: required_fields 7 节 (任务清单同序)。"""
        assert CONTRACTS["product"]["required_fields"] == PRODUCT_FIELDS
        assert len(PRODUCT_FIELDS) == 7

    def test_contract_rules_shape(self):
        """validation_rules: 结构规则 (str 非空 / list / dict 含 in-out)。"""
        rules = CONTRACTS["product"]["validation_rules"]
        assert rules["market_analysis"] == {"type": "str", "min_length": 1}
        assert rules["user_persona"] == {"type": "str", "min_length": 1}
        assert rules["user_journey"] == {"type": "str", "min_length": 1}
        assert rules["problem_statement"] == {"type": "str", "min_length": 1}
        assert rules["feature_list"] == {"type": "list", "min_items": 1}
        assert rules["mvp_scope"] == {
            "type": "dict", "min_keys": 1, "required_keys": ["in", "out"],
        }
        assert rules["user_stories"] == {"type": "list", "min_items": 1}

    def test_idea_contract_declared(self):
        """idea 契约: 自然语言想法 (PM 阶段输入)。"""
        assert CONTRACTS["idea"]["required_fields"] == ("idea",)
        assert CONTRACTS["idea"]["validation_rules"]["idea"] == {
            "type": "str", "min_length": 1,
        }

    def test_valid_product_payload(self):
        assert validate_artifact("product", product_payload_ok()).ok

    def test_missing_section(self):
        """缺任一节 → missing 响亮 (如缺 mvp_scope)。"""
        payload = product_payload_ok()
        del payload["mvp_scope"]
        result = validate_artifact("product", payload)
        assert not result.ok
        assert result.missing == ["mvp_scope"]

    def test_missing_most_sections(self):
        """只给一节 → 其余 6 节全部 missing (7 节必填)。"""
        result = validate_artifact("product", {"market_analysis": "m"})
        assert not result.ok
        assert result.missing == [
            "user_persona", "user_journey", "problem_statement",
            "feature_list", "mvp_scope", "user_stories",
        ]

    def test_empty_string_rule_fail(self):
        """str 节空串 → 规则失败 (非空约束)。"""
        payload = product_payload_ok()
        payload["problem_statement"] = "   "
        result = validate_artifact("product", payload)
        assert not result.ok
        assert result.errors == ["problem_statement: min length 1"]

    def test_feature_list_not_list(self):
        """feature_list 非 list → 规则失败 (类型约束)。"""
        payload = product_payload_ok()
        payload["feature_list"] = "不是列表"
        result = validate_artifact("product", payload)
        assert not result.ok
        assert result.errors == ["feature_list: expected list, got str"]

    def test_feature_list_empty(self):
        """feature_list 空 list → min_items 失败。"""
        payload = product_payload_ok()
        payload["feature_list"] = []
        result = validate_artifact("product", payload)
        assert not result.ok
        assert result.errors == ["feature_list: min items 1"]

    def test_mvp_scope_missing_out(self):
        """mvp_scope 缺 out 键 → required_keys 失败 (in/out 边界必含)。"""
        payload = product_payload_ok()
        payload["mvp_scope"] = {"in": ["a"]}
        result = validate_artifact("product", payload)
        assert not result.ok
        assert result.errors == ["mvp_scope: missing required keys: out"]

    def test_mvp_scope_missing_both(self):
        """mvp_scope 既缺 in 又缺 out → required_keys 列出全部缺失键。"""
        payload = product_payload_ok()
        payload["mvp_scope"] = {"notes": "x"}
        result = validate_artifact("product", payload)
        assert not result.ok
        assert "in" in result.errors[0] and "out" in result.errors[0]

    def test_user_stories_empty(self):
        """user_stories 空 list → min_items 失败。"""
        payload = product_payload_ok()
        payload["user_stories"] = []
        result = validate_artifact("product", payload)
        assert not result.ok
        assert result.errors == ["user_stories: min items 1"]

    def test_idea_valid(self):
        assert validate_artifact("idea", {"idea": "开发一个记账 Web App"}).ok

    def test_idea_empty_rejected(self):
        result = validate_artifact("idea", {"idea": ""})
        assert not result.ok
        assert result.errors == ["idea: min length 1"]


class TestProductRegistry:
    def _seed_stage(self, registry: ArtifactRegistry) -> None:
        """最小 stage 种子 (产物关联校验前置; stage 必须存在)。"""
        from org.projects import ProjectLifecycle

        plife = ProjectLifecycle(registry.store)
        plife.create_project("Build App", project_id="P-8")
        plife.create_stage("WF-8", "product-manager", stage_id="STG-8")

    def test_registry_product_validated(self, project_store: ProjectStore, logger):
        """product 产物全链: create → generated → validate → VALIDATED。"""
        registry = ArtifactRegistry(project_store, logger=logger)
        self._seed_stage(registry)
        artifact = registry.create(
            "STG-8", "product", project_id="P-8",
            producer_role="product-manager", metadata=product_payload_ok(),
            artifact_id="A-PROD-1",
        )
        registry.mark_generated(artifact.id)
        updated, result = registry.validate(artifact.id)
        assert result.ok
        assert updated.status is ArtifactStatus.VALIDATED

    def test_registry_product_invalid(self, project_store: ProjectStore, logger):
        """契约失败 → 产物 INVALID (invalid_reason 落库审计)。"""
        registry = ArtifactRegistry(project_store, logger=logger)
        self._seed_stage(registry)
        bad = product_payload_ok()
        del bad["feature_list"]
        artifact = registry.create(
            "STG-8", "product", project_id="P-8",
            producer_role="product-manager", metadata=bad,
            artifact_id="A-PROD-2",
        )
        registry.mark_generated(artifact.id)
        updated, result = registry.validate(artifact.id)
        assert not result.ok
        assert updated.status is ArtifactStatus.INVALID
        assert "feature_list" in updated.invalid_reason

    def test_registry_product_query_filter(self, project_store: ProjectStore, logger):
        """类型查询: product 产物按 type 过滤 (组合查询)。"""
        registry = ArtifactRegistry(project_store, logger=logger)
        self._seed_stage(registry)
        registry.create(
            "STG-8", "product", project_id="P-8",
            producer_role="product-manager", metadata=product_payload_ok(),
            artifact_id="A-PROD-3",
        )
        registry.create(
            "STG-8", "idea", project_id="P-8", metadata={"idea": "记账 App"},
            artifact_id="A-IDEA-3",
        )
        products = registry.query(type_="product")
        ideas = registry.query(type_="idea")
        assert [a.id for a in products] == ["A-PROD-3"]
        assert [a.id for a in ideas] == ["A-IDEA-3"]

    def test_registry_idea_validated(self, project_store: ProjectStore, logger):
        """idea 产物全链 → VALIDATED (PM 阶段输入可经 Registry 校验)。"""
        registry = ArtifactRegistry(project_store, logger=logger)
        self._seed_stage(registry)
        artifact = registry.create(
            "STG-8", "idea", project_id="P-8", metadata={"idea": "记账 Web App"},
            artifact_id="A-IDEA-1",
        )
        registry.mark_generated(artifact.id)
        updated, result = registry.validate(artifact.id)
        assert result.ok
        assert updated.status is ArtifactStatus.VALIDATED
