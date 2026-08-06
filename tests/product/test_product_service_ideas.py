"""tests/product/test_product_service_ideas.py — ProductService: ProductIdea CRUD + Artifact 抽象 (Phase 9A, ADR-0026)。

覆盖: create_idea 落库 ProductIdea + 同步 product_idea Artifact (Idea 即 Artifact,
content.idea_id 锚点)、ID 递增 (PI-001/ART-001 → 002)、goals/context、list 排序、
get 未找到抛 ProductNotFoundError、create_artifact 任意类型 (AI Artifact Lineage:
provider/agent/source_events/confidence)、按类型过滤、get_artifact_by_idea。
"""

from __future__ import annotations

import pytest

from product.service import ProductError, ProductNotFoundError

from product_helpers import seed_artifact, seed_idea


class TestCreateIdea:
    def test_create_idea_returns_idea(self, service):
        idea = service.create_idea("AI 助手")
        assert idea.id == "PI-001"
        assert idea.title == "AI 助手"
        assert idea.status == "created"

    def test_create_idea_persists_idea(self, service):
        idea = service.create_idea("AI 助手", description="d", goals=["g1"], context={"k": "v"})
        got = service.get_idea(idea.id)
        assert got.description == "d"
        assert got.goals == ["g1"]
        assert got.context == {"k": "v"}

    def test_create_idea_syncs_product_idea_artifact(self, service):
        idea = service.create_idea("AI 助手")
        artifact = service.get_artifact_by_idea(idea.id)
        assert artifact is not None
        assert artifact.type == "product_idea"
        assert artifact.content["idea_id"] == idea.id
        assert artifact.content["title"] == "AI 助手"

    def test_idea_id_increments(self, service):
        assert service.create_idea("a").id == "PI-001"
        assert service.create_idea("b").id == "PI-002"
        assert service.create_idea("c").id == "PI-003"

    def test_artifact_id_increments_independent_of_idea(self, service):
        i1 = service.create_idea("a")  # ART-001
        assert i1.id == "PI-001"
        a = service.create_artifact("prd")
        assert a.id == "ART-002"  # product_idea Artifact 已占 ART-001

    def test_create_idea_defaults_empty(self, service):
        idea = service.create_idea("t")
        assert idea.goals == []
        assert idea.context == {}
        assert idea.description == ""

    def test_list_ideas_sorted(self, service):
        service.create_idea("b")
        service.create_idea("a")
        service.create_idea("c")
        assert [i.id for i in service.list_ideas()] == ["PI-001", "PI-002", "PI-003"]

    def test_get_idea_missing_raises(self, service):
        with pytest.raises(ProductNotFoundError):
            service.get_idea("PI-999")

    def test_get_idea_found(self, service):
        idea = service.create_idea("t")
        assert service.get_idea(idea.id).id == idea.id


class TestCreateArtifact:
    def test_create_artifact_arbitrary_type(self, service):
        a = service.create_artifact("research", {"notes": "x"})
        assert a.id == "ART-001"
        assert a.type == "research"
        assert a.content == {"notes": "x"}

    def test_create_artifact_lineage(self, service):
        a = service.create_artifact(
            "prd",
            provider_id="hermes",
            agent_id="ag-1",
            source_events=["ev-1", "ev-2"],
            confidence=0.9,
        )
        assert a.provider_id == "hermes"
        assert a.agent_id == "ag-1"
        assert a.source_events == ["ev-1", "ev-2"]
        assert a.confidence == 0.9

    def test_create_artifact_idea_anchor(self, service):
        idea = service.create_idea("t")
        a = service.create_artifact("prd", idea_id=idea.id)
        assert a.content["idea_id"] == idea.id

    def test_create_artifact_invalid_confidence_raises_validation_error(self, service):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            service.create_artifact("prd", confidence=1.5)

    def test_list_artifacts_filtered(self, service):
        service.create_artifact("prd")
        service.create_artifact("ui")
        service.create_artifact("prd")
        assert len(service.list_artifacts()) == 3
        assert [a.type for a in service.list_artifacts("prd")] == ["prd", "prd"]

    def test_get_artifact_missing_raises(self, service):
        with pytest.raises(ProductNotFoundError):
            service.get_artifact("ART-999")

    def test_get_artifact_by_idea_none_when_missing(self, service):
        assert service.get_artifact_by_idea("PI-999") is None


class TestLineageViaSeedHelpers:
    def test_seed_idea_helper(self, service):
        idea = seed_idea(service, title="AI 助手", goals=["g"])
        assert idea.goals == ["g"]

    def test_seed_artifact_helper(self, service, ):
        a = seed_artifact(service, "prd", idea_id="PI-001", confidence=0.6)
        assert a.type == "prd"
        assert a.content["idea_id"] == "PI-001"
        assert a.confidence == 0.6
