"""tests/product/test_product_generation_events.py — 生成事件链序 + payload (Phase 9B, ADR-0027)。

覆盖: generation.started → provider.selected → provider.execution.started|completed
→ [usage.recorded] → approval.required → generation.completed 链序 (审批后统一
单一 completed 事件 — 双事件回归), failed 链 (generation.failed, 无 completed),
experience.recorded/viewed payload, Lineage source_events 锚定, logger=None 静默。
"""

from __future__ import annotations

import pytest

from events.models import EventType

from product.events import (
    record_experience_recorded,
    record_experience_viewed,
    record_generation_completed,
    record_generation_failed,
    record_generation_started,
)
from product.generation import ProductGenerationError, ProductGenerationNoProviderError
from product.models import ApprovalRequest, Artifact

from product_helpers import (
    MockAdapter,
    MockSelector,
    MockUsageStore,
    event_sequence,
    event_types_of,
    make_generator,
    payload_of,
    seed_idea,
)


class TestSuccessChain:
    def test_research_chain_order(self, product_dir, logger, event_store):
        gen = make_generator(product_dir, logger=logger)
        idea_id = seed_idea(gen.service).id
        gen.generate(idea_id, "research")
        seq = event_sequence(event_store)
        gen_events = [e for e in seq if e.startswith(("product.generation", "provider."))]
        assert gen_events == [
            "product.generation.started",
            "provider.selected",
            "provider.execution.started",
            "provider.execution.completed",
            "product.generation.completed",
        ]

    def test_prd_chain_approval_before_completed(self, product_dir, logger, event_store):
        """PRD: approval.required 在 generation.completed **之前** (审批后统一发出,
        单一 completed 事件携带 approval_request_id)。"""
        gen = make_generator(product_dir, logger=logger)
        idea_id = seed_idea(gen.service).id
        gen.generate(idea_id, "prd")
        seq = event_sequence(event_store)
        assert seq.index("approval.required") < seq.index("product.generation.completed")
        assert seq.index("product.generation.started") < seq.index("approval.required")

    def test_single_completed_event_regression(self, product_dir, logger, event_store):
        """双 completed 事件回归: PRD/UI 路径必须恰好一个 generation.completed。"""
        gen = make_generator(product_dir, logger=logger)
        idea_id = seed_idea(gen.service).id
        gen.generate(idea_id, "prd")
        gen.generate(idea_id, "ui")
        completed = [e for e in event_store.query()
                     if e.type == EventType.PRODUCT_GENERATION_COMPLETED]
        assert len(completed) == 2  # 每次生成恰好一个 (无重复)

    def test_usage_recorded_in_chain(self, product_dir, logger, event_store):
        gen = make_generator(product_dir, logger=logger, usage_store=MockUsageStore())
        idea_id = seed_idea(gen.service).id
        gen.generate(idea_id, "research")
        seq = event_sequence(event_store)
        assert "provider.usage.recorded" in seq
        assert seq.index("provider.execution.completed") < seq.index("provider.usage.recorded")
        assert seq.index("provider.usage.recorded") < seq.index("product.generation.completed")


class TestPayloadContracts:
    def test_generation_started_payload(self, product_dir, logger, event_store):
        gen = make_generator(product_dir, logger=logger)
        idea_id = seed_idea(gen.service).id
        gen.generate(idea_id, "prd", provider_id="mock")
        payload = payload_of(event_store, "product.generation.started")
        assert payload["artifact_type"] == "prd"
        assert payload["idea_id"] == idea_id
        assert payload["provider_id"] == "mock"
        assert payload["task_requirement"]["task_type"] == "prd"
        assert payload["source_artifact_id"]

    def test_provider_selected_payload(self, product_dir, logger, event_store):
        gen = make_generator(product_dir, logger=logger)
        idea_id = seed_idea(gen.service).id
        gen.generate(idea_id, "research")
        payload = payload_of(event_store, "provider.selected")
        assert payload["provider_id"] == "mock"
        assert payload["source"] == "recommendation"

    def test_provider_execution_completed_payload(self, product_dir, logger, event_store):
        gen = make_generator(product_dir, logger=logger)
        idea_id = seed_idea(gen.service).id
        gen.generate(idea_id, "research")
        payload = payload_of(event_store, "provider.execution.completed")
        assert payload["provider_id"] == "mock"
        assert payload["model"] == "mock-model"

    def test_generation_completed_payload(self, product_dir, logger, event_store):
        gen = make_generator(product_dir, logger=logger)
        idea_id = seed_idea(gen.service).id
        result = gen.generate(idea_id, "prd", confidence=0.5)
        payload = payload_of(event_store, "product.generation.completed")
        assert payload["artifact_id"] == result.artifact.id
        assert payload["artifact_type"] == "prd"
        assert payload["provider_id"] == "mock"
        assert payload["confidence"] == 0.5
        assert payload["idea_id"] == idea_id
        assert payload["source_events"] == result.artifact.source_events

    def test_prd_completed_payload_has_approval_anchor(self, product_dir, logger, event_store):
        gen = make_generator(product_dir, logger=logger)
        idea_id = seed_idea(gen.service).id
        result = gen.generate(idea_id, "prd")
        payload = payload_of(event_store, "product.generation.completed")
        assert payload["approval_request_id"] == result.approval_request.id
        assert payload["approval_status"] == "pending"

    def test_research_completed_payload_no_approval_anchor(self, product_dir, logger, event_store):
        gen = make_generator(product_dir, logger=logger)
        idea_id = seed_idea(gen.service).id
        gen.generate(idea_id, "research")
        payload = payload_of(event_store, "product.generation.completed")
        assert "approval_request_id" not in payload

    def test_source_events_lineage_anchors(self, product_dir, logger, event_store):
        """Artifact.source_events = [generation.started, provider.execution.completed] 锚点。"""
        gen = make_generator(product_dir, logger=logger)
        idea_id = seed_idea(gen.service).id
        result = gen.generate(idea_id, "research")
        ids = result.artifact.source_events
        assert len(ids) == 2
        by_id = {e.event_id: e for e in event_store.query()}
        assert by_id[ids[0]].type == EventType.PRODUCT_GENERATION_STARTED
        assert by_id[ids[1]].type == EventType.PROVIDER_EXECUTION_COMPLETED


class TestFailureChain:
    def test_adapter_failure_emits_failed(self, product_dir, logger, event_store):
        gen = make_generator(
            product_dir, logger=logger,
            adapters={"mock": MockAdapter(error="boom")},
        )
        idea_id = seed_idea(gen.service).id
        with pytest.raises(ProductGenerationError):
            gen.generate(idea_id, "research")
        failed = payload_of(event_store, "product.generation.failed")
        assert failed["artifact_type"] == "research"
        assert failed["idea_id"] == idea_id
        assert "boom" in failed["error"]
        assert "product.generation.completed" not in event_types_of(event_store)

    def test_adapter_failure_emits_execution_failed(self, product_dir, logger, event_store):
        gen = make_generator(
            product_dir, logger=logger,
            adapters={"mock": MockAdapter(error="boom")},
        )
        idea_id = seed_idea(gen.service).id
        with pytest.raises(ProductGenerationError):
            gen.generate(idea_id, "research")
        payload = payload_of(event_store, "provider.execution.failed")
        assert payload["provider_id"] == "mock"
        assert payload["error"] == "boom"

    def test_no_provider_emits_failed_no_started(self, product_dir, logger, event_store):
        gen = make_generator(product_dir, logger=logger, selector=None)
        idea_id = seed_idea(gen.service).id
        with __import__("pytest").raises(ProductGenerationNoProviderError):
            gen.generate(idea_id, "research")
        payload = payload_of(event_store, "product.generation.failed")
        assert "CostAwareSelector" in payload["error"]
        assert "product.generation.started" not in event_types_of(event_store)

    def test_failed_event_is_ERROR_result(self, product_dir, logger, event_store):
        gen = make_generator(
            product_dir, logger=logger,
            adapters={"mock": MockAdapter(error="boom")},
        )
        idea_id = seed_idea(gen.service).id
        with __import__("pytest").raises(ProductGenerationError):
            gen.generate(idea_id, "research")
        events = [e for e in event_store.query()
                  if e.type == EventType.PRODUCT_GENERATION_FAILED]
        assert events[-1].result == "ERROR"


class TestExperienceEvents:
    def test_experience_recorded_payload(self, product_dir, logger, event_store, tmp_path):
        from product.experience import ExperienceStore

        exp_store = ExperienceStore(tmp_path / "exp")
        gen = make_generator(product_dir, logger=logger, experience_store=exp_store)
        idea_id = seed_idea(gen.service).id
        artifact = gen.generate(idea_id, "prd").artifact
        gen.record_experience(
            artifact.id, rating=4, comment="ok", approved=True, by="tester",
        )
        payload = payload_of(event_store, "product.experience.recorded")
        assert payload["artifact_type"] == "prd"
        assert payload["provider_id"] == "mock"
        assert payload["approved"] is True
        assert payload["rating"] == 4
        assert payload["human_feedback"] == "ok"
        assert payload["by"] == "tester"
        assert payload["experience_id"]
        events = [e for e in event_store.query()
                  if e.type == EventType.PRODUCT_EXPERIENCE_RECORDED]
        assert events[-1].source == "product"

    def test_experience_viewed_event(self, logger):
        ev = record_experience_viewed(logger, count=2, artifact_type="prd")
        assert ev.type == EventType.PRODUCT_EXPERIENCE_VIEWED
        assert ev.source == "cli"
        assert ev.payload == {"count": 2, "artifact_type": "prd"}


class TestGenerationEventHelpers:
    def _sample_context(self):
        from product.generation import GeneratedArtifactContext

        return GeneratedArtifactContext(source_artifact_id="ART-001", provider_id="mock")

    def test_generation_started_helper(self, logger):
        ev = record_generation_started(
            logger, artifact_type="prd", source_artifact_id="ART-001",
            idea_id="PI-001", provider_id="mock",
            task_requirement={"task_type": "prd"},
        )
        assert ev.type == EventType.PRODUCT_GENERATION_STARTED
        assert ev.result == "OK"
        assert ev.payload["task_requirement"] == {"task_type": "prd"}

    def test_generation_completed_helper(self, logger):
        artifact = Artifact(id="ART-002", type="prd",
                            content={"idea_id": "PI-001"}, source_events=["ev-1"])
        approval = ApprovalRequest(id="APR-001", artifact_id="ART-002", gate="prd")
        ev = record_generation_completed(
            logger, artifact=artifact, context=self._sample_context(),
            provider_id="mock", approval_request=approval,
        )
        assert ev.type == EventType.PRODUCT_GENERATION_COMPLETED
        assert ev.payload["artifact_id"] == "ART-002"
        assert ev.payload["approval_request_id"] == "APR-001"
        assert ev.payload["idea_id"] == "PI-001"

    def test_generation_failed_helper(self, logger):
        ev = record_generation_failed(
            logger, artifact_type="prd", source_artifact_id="ART-001",
            error="no provider", idea_id="PI-001",
        )
        assert ev.type == EventType.PRODUCT_GENERATION_FAILED
        assert ev.result == "ERROR"
        assert ev.payload["error"] == "no provider"

    def test_experience_recorded_helper(self, logger):
        from product.experience import GenerationExperience

        exp = GenerationExperience(artifact_type="prd", provider_id="mock", rating=3)
        ev = record_experience_recorded(logger, experience=exp, by="cli")
        assert ev.type == EventType.PRODUCT_EXPERIENCE_RECORDED
        assert ev.payload["rating"] == 3
        assert ev.payload["by"] == "cli"

    def test_helpers_silent_without_logger(self):
        from product.experience import GenerationExperience

        exp = GenerationExperience(artifact_type="prd")
        assert record_generation_started(
            None, artifact_type="prd", source_artifact_id="ART-001") is None
        assert record_generation_completed(None, artifact=Artifact(id="A", type="prd")) is None
        assert record_generation_failed(
            None, artifact_type="prd", source_artifact_id="ART-001", error="e") is None
        assert record_experience_recorded(None, experience=exp) is None
        assert record_experience_viewed(None, count=1) is None
