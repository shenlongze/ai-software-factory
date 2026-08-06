"""tests/product/test_product_generator.py — ProductGenerator 生成编排 (Phase 9B, ADR-0027)。

覆盖: research/prd/ui 编排 (Artifact 产出 + Lineage + context), 自动审批联动
(PRD/UI mandatory → pending; research → 无), 失败路径 (无效类型 / idea 不存在 /
无 Provider 智能 / 无能力匹配 / 无 Adapter 实现 / adapter 失败 / adapter 意外异常),
Provider 选择 (显式 --provider 覆盖经 explicit 层 / TaskRequirement 能力映射 /
min_quality/budget 传递), 重生成版本递增, usage 失败安全, experience 记录接口。

Mock 装配见 product_helpers (MockSelector/MockAdapter/MockUsageStore/make_generator)。
"""

from __future__ import annotations

import pytest

from providers.models import ProviderRequest
from providers.selector import Recommendation

from product.generation import (
    GENERATION_TYPES,
    ProductGenerationError,
    ProductGenerationNoProviderError,
    ProductGenerator,
    adapter_call,
)
from product.models import ApprovalStatus
from product.service import ProductNotFoundError

from product_helpers import (
    MockAdapter,
    MockSelector,
    MockUsageStore,
    make_generator,
    seed_idea,
)


def _seed(generator, title: str = "AI 助手") -> str:
    """创建 idea, 返回 idea_id。"""
    return generator.service.create_idea(title).id


class TestResearchGeneration:
    def test_research_generates_artifact_with_lineage(self, product_dir):
        gen = make_generator(product_dir)
        idea_id = _seed(gen)
        result = gen.generate(idea_id, "research")
        artifact = result.artifact
        assert artifact.type == "research"
        assert artifact.status == "completed"
        assert artifact.provider_id == "mock"
        assert artifact.agent_id is None
        assert artifact.version == 1
        assert artifact.content["content"] == "mock generated content"
        assert artifact.content["model"] == "mock-model"
        assert artifact.content["idea_id"] == idea_id

    def test_research_context_embedded_in_artifact(self, product_dir):
        gen = make_generator(product_dir)
        idea_id = _seed(gen)
        result = gen.generate(idea_id, "research", confidence=0.4)
        ctx = result.artifact.content["generation_context"]
        assert ctx["source_artifact_id"]  # 生成来源 (product_idea Artifact id)
        assert ctx["provider_id"] == "mock"
        assert ctx["confidence"] == 0.4
        assert ctx["task_requirement"]["task_type"] == "research"
        # 与 result.context 同源
        assert result.context.to_dict() == ctx

    def test_research_no_approval_request(self, product_dir):
        gen = make_generator(product_dir)
        idea_id = _seed(gen)
        result = gen.generate(idea_id, "research")
        assert result.approval_request is None
        assert gen.service.list_approvals() == []

    def test_research_result_shape(self, product_dir):
        gen = make_generator(product_dir)
        idea_id = _seed(gen)
        result = gen.generate(idea_id, "research")
        assert result.provider_id == "mock"
        assert result.recommendation["provider_id"] == "mock"
        assert result.recommendation["score"] == 0.9
        assert result.recommendation["estimated_cost"] == 0.01


class TestApprovalAutoRequest:
    def test_prd_auto_requests_approval(self, product_dir):
        gen = make_generator(product_dir)
        idea_id = _seed(gen)
        result = gen.generate(idea_id, "prd")
        approval = result.approval_request
        assert approval is not None
        assert approval.gate == "prd"
        assert approval.status == ApprovalStatus.PENDING.value
        assert approval.artifact_id == result.artifact.id
        assert approval.idea_id == idea_id

    def test_prd_approval_pending_in_service(self, product_dir):
        gen = make_generator(product_dir)
        idea_id = _seed(gen)
        gen.generate(idea_id, "prd")
        pending = gen.service.list_approvals(pending_only=True)
        assert len(pending) == 1
        assert pending[0].gate == "prd"

    def test_ui_auto_requests_approval(self, product_dir):
        gen = make_generator(product_dir)
        idea_id = _seed(gen)
        result = gen.generate(idea_id, "ui")
        assert result.approval_request is not None
        assert result.approval_request.gate == "ui"

    def test_prd_approval_workflow_pause_linkage(self, product_dir):
        """生成 → approval pending → 关联 workflow 进入 awaiting_approval (9a 联动)。"""
        gen = make_generator(product_dir)
        idea_id = _seed(gen)
        gen.service.start_workflow(idea_id)
        gen.generate(idea_id, "prd")
        wf = gen.service.workflow_status(idea_id)
        assert wf.status == "awaiting_approval"


class TestValidationFailures:
    def test_unknown_artifact_type(self, product_dir):
        gen = make_generator(product_dir)
        idea_id = _seed(gen)
        with pytest.raises(ProductGenerationError, match="unsupported artifact type"):
            gen.generate(idea_id, "architecture")
        with pytest.raises(ProductGenerationError, match="research, prd, ui"):
            gen.generate(idea_id, "bogus")

    def test_idea_not_found(self, product_dir):
        gen = make_generator(product_dir)
        with pytest.raises(ProductNotFoundError, match="idea not found"):
            gen.generate("PI-999", "research")

    def test_selector_not_configured_no_provider_error(self, product_dir):
        gen = make_generator(product_dir, selector=None)
        idea_id = _seed(gen)
        with pytest.raises(ProductGenerationNoProviderError, match="CostAwareSelector"):
            gen.generate(idea_id, "research")

    def test_no_capability_match_no_provider_error(self, product_dir):
        gen = make_generator(product_dir, selector=MockSelector(recommendation=None))
        idea_id = _seed(gen)
        with pytest.raises(ProductGenerationNoProviderError, match="no provider available"):
            gen.generate(idea_id, "research")

    def test_selector_raise_wrapped(self, product_dir):
        from providers.registry import ProviderNotFoundError

        gen = make_generator(product_dir, selector=MockSelector(exc=ProviderNotFoundError("x")))
        idea_id = _seed(gen)
        with pytest.raises(ProductGenerationError, match="provider selection failed"):
            gen.generate(idea_id, "research")

    def test_no_adapter_implementation(self, product_dir):
        """推荐了 provider 但无实现映射 (注册但未实现 → 明确配置缺口错误)。"""
        gen = make_generator(product_dir, adapters={})
        idea_id = _seed(gen)
        with pytest.raises(ProductGenerationError, match="no adapter implementation"):
            gen.generate(idea_id, "research")

    def test_adapter_error_response(self, product_dir):
        gen = make_generator(
            product_dir,
            adapters={"mock": MockAdapter(error="boom: model unavailable")},
        )
        idea_id = _seed(gen)
        with pytest.raises(ProductGenerationError, match="generation failed: boom"):
            gen.generate(idea_id, "research")

    def test_adapter_error_records_failed_artifact(self, product_dir):
        gen = make_generator(
            product_dir,
            adapters={"mock": MockAdapter(error="boom")},
        )
        idea_id = _seed(gen)
        with pytest.raises(ProductGenerationError):
            gen.generate(idea_id, "research")
        failed = [a for a in gen.service.list_artifacts("research") if a.status == "failed"]
        assert len(failed) == 1
        assert failed[0].provider_id == "mock"  # 失败 Artifact 仍带 Lineage (可追溯)

    def test_adapter_unexpected_exception_defensive(self, product_dir):
        gen = make_generator(
            product_dir,
            adapters={"mock": MockAdapter(raise_exc=RuntimeError("adapter bug"))},
        )
        idea_id = _seed(gen)
        with pytest.raises(ProductGenerationError, match="generation raised: adapter bug"):
            gen.generate(idea_id, "research")

    def test_unsupported_type_does_not_call_selector(self, product_dir):
        selector = MockSelector()
        gen = make_generator(product_dir, selector=selector)
        idea_id = _seed(gen)
        with pytest.raises(ProductGenerationError):
            gen.generate(idea_id, "bogus")
        assert selector.calls == []


class TestProviderSelection:
    def test_explicit_provider_passed_to_selector(self, product_dir):
        selector = MockSelector()
        gen = make_generator(product_dir, selector=selector)
        idea_id = _seed(gen)
        gen.generate(idea_id, "prd", provider_id="hermes")
        assert selector.calls[-1]["explicit"] == "hermes"

    def test_explicit_provider_overrides_recommendation(self, product_dir):
        """显式 --provider 覆盖: 结果 provider_id 用显式值, 且调用了 selector。"""
        selector = MockSelector(provider_id="auto")
        gen = make_generator(
            product_dir, selector=selector,
            adapters={"auto": MockAdapter(provider_id="auto"), "mock": MockAdapter()},
        )
        idea_id = _seed(gen)
        result = gen.generate(idea_id, "research", provider_id="auto")
        assert result.provider_id == "auto"
        assert selector.calls[-1]["explicit"] == "auto"

    def test_research_requirement_capabilities(self, product_dir):
        selector = MockSelector()
        gen = make_generator(product_dir, selector=selector)
        idea_id = _seed(gen)
        gen.generate(idea_id, "research")
        call = selector.calls[-1]
        assert call["task_type"] == "research"
        assert call["required_capabilities"] == GENERATION_TYPES["research"]["capabilities"]

    def test_prd_requirement_capabilities(self, product_dir):
        selector = MockSelector()
        gen = make_generator(product_dir, selector=selector)
        idea_id = _seed(gen)
        gen.generate(idea_id, "prd")
        call = selector.calls[-1]
        assert call["task_type"] == "prd"
        assert call["required_capabilities"] == ["generation", "reasoning"]

    def test_ui_requirement_capabilities(self, product_dir):
        selector = MockSelector()
        gen = make_generator(product_dir, selector=selector)
        idea_id = _seed(gen)
        gen.generate(idea_id, "ui")
        call = selector.calls[-1]
        assert call["task_type"] == "ui"
        assert call["required_capabilities"] == ["generation"]

    def test_min_quality_and_budget_forwarded(self, product_dir):
        selector = MockSelector()
        gen = make_generator(product_dir, selector=selector)
        idea_id = _seed(gen)
        gen.generate(idea_id, "research", min_quality=0.6, budget=0.5)
        call = selector.calls[-1]
        assert call["min_quality"] == 0.6
        assert call["budget"] == 0.5

    def test_generation_types_gate_mapping(self):
        """门映射: research 无默认门 / prd/ui mandatory — 领域知识, 非 Provider 硬编码。"""
        assert GENERATION_TYPES["research"]["gate"] is None
        assert GENERATION_TYPES["prd"]["gate"] == "prd"
        assert GENERATION_TYPES["ui"]["gate"] == "ui"

    def test_prompt_contains_idea_context(self, product_dir):
        adapter = MockAdapter()
        gen = make_generator(product_dir, adapters={"mock": adapter})
        idea_id = gen.service.create_idea("My Product", description="desc", goals=["g1"]).id
        gen.generate(idea_id, "research")
        request: ProviderRequest = adapter.requests[-1]
        assert "My Product" in request.prompt
        assert "desc" in request.prompt
        assert "g1" in request.prompt
        assert request.metadata["artifact_type"] == "research"
        assert request.metadata["idea_id"] == idea_id
        assert request.metadata["generation"] == "product-generator"


class TestVersionAndLineage:
    def test_regeneration_increments_version(self, product_dir):
        gen = make_generator(product_dir)
        idea_id = _seed(gen)
        v1 = gen.generate(idea_id, "prd").artifact
        v2 = gen.generate(idea_id, "prd").artifact
        assert v1.version == 1
        assert v2.version == 2

    def test_version_independent_across_types(self, product_dir):
        gen = make_generator(product_dir)
        idea_id = _seed(gen)
        r = gen.generate(idea_id, "research").artifact
        p = gen.generate(idea_id, "prd").artifact
        assert r.version == 1
        assert p.version == 1

    def test_version_independent_across_ideas(self, product_dir):
        gen = make_generator(product_dir)
        a = _seed(gen, "A")
        b = _seed(gen, "B")
        assert gen.generate(a, "prd").artifact.version == 1
        assert gen.generate(b, "prd").artifact.version == 1

    def test_confidence_and_created_by_passthrough(self, product_dir):
        gen = make_generator(product_dir)
        idea_id = _seed(gen)
        result = gen.generate(idea_id, "prd", confidence=0.8, created_by="pipeline")
        assert result.artifact.confidence == 0.8
        assert result.artifact.created_by == "pipeline"
        assert result.context.confidence == 0.8
        assert result.approval_request.by == "pipeline"

    def test_agent_id_lineage(self, product_dir):
        gen = make_generator(product_dir, agent_id="agent-9")
        idea_id = _seed(gen)
        result = gen.generate(idea_id, "research")
        assert result.artifact.agent_id == "agent-9"
        assert result.context.agent_id == "agent-9"


class TestUsageRecording:
    def test_usage_recorded_on_success(self, product_dir):
        usage = MockUsageStore()
        gen = make_generator(product_dir, usage_store=usage)
        idea_id = _seed(gen)
        gen.generate(idea_id, "research")
        assert len(usage.records) == 1
        record = usage.records[0]
        assert record.provider_id == "mock"
        assert record.success is True
        assert record.prompt_tokens == 10
        assert record.completion_tokens == 5
        assert record.estimated_cost == 0.01

    def test_usage_recorded_on_adapter_failure(self, product_dir):
        usage = MockUsageStore()
        gen = make_generator(
            product_dir,
            adapters={"mock": MockAdapter(error="boom")},
            usage_store=usage,
        )
        idea_id = _seed(gen)
        with pytest.raises(ProductGenerationError):
            gen.generate(idea_id, "research")
        assert len(usage.records) == 1
        assert usage.records[0].success is False
        assert "boom" in usage.records[0].error

    def test_usage_store_failure_is_fail_safe(self, product_dir):
        """usage 落库失败绝不破坏生成链路 (8B-3 语义: 审计增强数据)。"""
        gen = make_generator(product_dir, usage_store=MockUsageStore(fail=True))
        idea_id = _seed(gen)
        result = gen.generate(idea_id, "research")
        assert result.artifact.status == "completed"


class TestExperienceInterface:
    def test_record_experience_derives_lineage(self, product_dir, tmp_path):
        from product.experience import ExperienceStore

        exp_store = ExperienceStore(tmp_path / "exp")
        gen = make_generator(product_dir, experience_store=exp_store)
        idea_id = _seed(gen)
        artifact = gen.generate(idea_id, "prd", confidence=0.7).artifact
        experience = gen.record_experience(
            artifact.id, rating=5, comment="很棒", approved=True, by="reviewer",
        )
        assert experience.artifact_type == "prd"
        assert experience.provider_id == "mock"
        assert experience.confidence == 0.7
        assert experience.rating == 5
        assert experience.approved is True
        assert experience.human_feedback == "很棒"
        assert exp_store.count() == 1

    def test_record_experience_missing_artifact(self, product_dir, tmp_path):
        from product.experience import ExperienceStore

        gen = make_generator(product_dir, experience_store=ExperienceStore(tmp_path / "exp"))
        with pytest.raises(ProductNotFoundError, match="artifact not found"):
            gen.record_experience("ART-999")

    def test_record_experience_without_store(self, product_dir):
        gen = make_generator(product_dir, experience_store=None)
        idea_id = _seed(gen)
        artifact = gen.generate(idea_id, "research").artifact
        with pytest.raises(ProductGenerationError, match="experience store not configured"):
            gen.record_experience(artifact.id)

    def test_list_experiences_without_store_empty(self, product_dir):
        gen = make_generator(product_dir, experience_store=None)
        assert gen.list_experiences() == []

    def test_list_experiences_filter(self, product_dir, tmp_path):
        from product.experience import ExperienceStore

        exp_store = ExperienceStore(tmp_path / "exp")
        gen = make_generator(product_dir, experience_store=exp_store)
        idea_id = _seed(gen)
        a1 = gen.generate(idea_id, "prd").artifact
        a2 = gen.generate(idea_id, "research").artifact
        gen.record_experience(a1.id, rating=4)
        gen.record_experience(a2.id, rating=3)
        assert len(gen.list_experiences()) == 2
        prd_only = gen.list_experiences(artifact_type="prd")
        assert len(prd_only) == 1
        assert prd_only[0].artifact_type == "prd"


class TestAdapterCall:
    def test_adapter_call_dispatches(self):
        adapter = MockAdapter()
        request = ProviderRequest(prompt="hi")
        response = adapter_call({"mock": adapter}, "mock", request)
        assert response.content == "mock generated content"
        assert adapter.requests == [request]

    def test_adapter_call_missing_implementation(self):
        request = ProviderRequest(prompt="hi")
        with pytest.raises(ProductGenerationError, match="no adapter implementation"):
            adapter_call({}, "hermes", request)

    def test_adapters_property_returns_copy(self, product_dir):
        gen = make_generator(product_dir, adapters={"mock": MockAdapter()})
        gen.adapters["intruder"] = MockAdapter()
        assert "intruder" not in gen._adapters

    def test_selector_property_none_when_unconfigured(self, product_dir):
        gen = make_generator(product_dir, selector=None)
        assert gen.selector is None


class TestGeneratorConstruction:
    def test_minimal_construction(self, product_dir):
        gen = ProductGenerator(make_generator(product_dir).service)
        assert gen.service is not None
        assert gen.selector is None
        assert gen.adapters == {}
        assert gen._logger is None
