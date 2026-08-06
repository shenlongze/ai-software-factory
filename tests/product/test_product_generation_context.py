"""tests/product/test_product_generation_context.py — GeneratedArtifactContext + GenerationResult (Phase 9B, ADR-0027)。

覆盖: 上下文模型字段/默认值/to_dict, 校验 (source_artifact_id 非空 / confidence 0-1 /
generation_time UTC 格式), GenerationResult 序列化形状 (含 approval_request None 分支)。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from product.generation import GeneratedArtifactContext, GenerationResult, ProductGenerationError
from product.models import ApprovalRequest, Artifact


def _ctx(**kw) -> GeneratedArtifactContext:
    defaults = {"source_artifact_id": "ART-001"}
    defaults.update(kw)
    return GeneratedArtifactContext(**defaults)


class TestGeneratedArtifactContextDefaults:
    def test_minimal_construction(self):
        ctx = _ctx()
        assert ctx.source_artifact_id == "ART-001"
        assert ctx.agent_id is None
        assert ctx.provider_id is None
        assert ctx.task_requirement == {}
        assert ctx.confidence == 0.0
        assert ctx.source_events == []
        assert ctx.generation_time  # 默认 UTC 时间戳

    def test_to_dict_json_friendly(self):
        ctx = _ctx(provider_id="mock", confidence=0.5, source_events=["ev-1", "ev-2"])
        d = ctx.to_dict()
        assert d["source_artifact_id"] == "ART-001"
        assert d["provider_id"] == "mock"
        assert d["confidence"] == 0.5
        assert d["source_events"] == ["ev-1", "ev-2"]
        assert isinstance(d, dict)

    def test_task_requirement_roundtrip(self):
        req = {"task_type": "prd", "required_capabilities": ["generation"]}
        ctx = _ctx(task_requirement=req)
        assert ctx.task_requirement == req
        assert ctx.to_dict()["task_requirement"] == req

    def test_agent_and_provider_nullable(self):
        ctx = _ctx(agent_id="agent-1", provider_id="mock")
        assert ctx.agent_id == "agent-1"
        assert ctx.provider_id == "mock"


class TestGeneratedArtifactContextValidation:
    def test_source_artifact_id_whitespace_stripped(self):
        assert _ctx(source_artifact_id="  ART-001  ").source_artifact_id == "ART-001"

    def test_empty_source_artifact_id_rejected(self):
        with pytest.raises(ValidationError):
            _ctx(source_artifact_id="")
        with pytest.raises(ValidationError):
            _ctx(source_artifact_id="   ")

    def test_confidence_bounds_accepted(self):
        assert _ctx(confidence=0.0).confidence == 0.0
        assert _ctx(confidence=1.0).confidence == 1.0

    def test_confidence_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            _ctx(confidence=-0.1)
        with pytest.raises(ValidationError):
            _ctx(confidence=1.1)

    def test_generation_time_must_be_utc_timestamp(self):
        with pytest.raises(ValidationError):
            _ctx(generation_time="not-a-timestamp")
        with pytest.raises(ValidationError):
            _ctx(generation_time="2026-13-99")

    def test_generation_time_valid_iso_accepted(self):
        ctx = _ctx(generation_time="2026-08-06T12:00:00Z")
        assert ctx.generation_time == "2026-08-06T12:00:00Z"


class TestGenerationResult:
    def test_to_dict_without_approval(self):
        artifact = Artifact(id="ART-001", type="research")
        ctx = _ctx()
        result = GenerationResult(
            artifact=artifact, context=ctx, approval_request=None,
            provider_id="mock", recommendation=None,
        )
        d = result.to_dict()
        assert d["artifact"]["id"] == "ART-001"
        assert d["context"]["source_artifact_id"] == "ART-001"
        assert d["approval_request"] is None
        assert d["provider_id"] == "mock"
        assert d["recommendation"] is None

    def test_to_dict_with_approval(self):
        artifact = Artifact(id="ART-002", type="prd")
        ctx = _ctx(source_artifact_id="ART-002")
        approval = ApprovalRequest(id="APR-001", artifact_id="ART-002", gate="prd")
        result = GenerationResult(
            artifact=artifact, context=ctx, approval_request=approval,
            provider_id="mock", recommendation={"provider_id": "mock", "score": 0.9},
        )
        d = result.to_dict()
        assert d["approval_request"]["id"] == "APR-001"
        assert d["approval_request"]["status"] == "pending"
        assert d["recommendation"]["score"] == 0.9

    def test_generation_error_hierarchy(self):
        assert issubclass(ProductGenerationError, Exception)
