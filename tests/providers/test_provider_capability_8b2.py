"""test_provider_capability_8b2.py — ProviderCapabilityProfile 能力矩阵 + 任务匹配 (Phase 8B-2, ADR-0024)。

覆盖:
- 矩阵校验 (0-1 范围/非数值/缺失能力 quality=0.0)
- evidence 归一化 (None/去空白/去空串/保序去重)
- has 键存在语义 (min_quality=0.0 缺键不过 — 无证据不臆造)
- average_quality / max_tokens / context_window
- rank_for_task: required 过滤/质量分排序/空 required 矩阵平均/空矩阵=1.0/稳定排序
- find_best_for_task: 首个/无候选 None
- dict 输入归一 / TaskRequirement 校验
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from providers.capability import (
    ProviderCapabilityProfile,
    find_best_for_task,
    rank_for_task,
)
from providers.models import TaskRequirement

from providers_helpers import make_definition


def make_profile(
    provider_id: str = "openai",
    matrix: dict | None = None,
    *,
    max_tokens: int | None = None,
    context_window: int | None = None,
    evidence: list[str] | None = None,
) -> ProviderCapabilityProfile:
    return ProviderCapabilityProfile(
        provider_id=provider_id,
        matrix=matrix or {"chat": 0.9, "code": 0.8, "reasoning": 0.7},
        max_tokens=max_tokens,
        context_window=context_window,
        evidence=evidence,
    )


class TestProfileValidation:
    def test_basic_profile(self):
        p = make_profile("openai", {"chat": 0.9, "code": 0.8})
        assert p.provider_id == "openai"
        assert p.matrix == {"chat": 0.9, "code": 0.8}

    def test_defaults_empty(self):
        p = ProviderCapabilityProfile(provider_id="x")
        assert p.matrix == {}
        assert p.evidence == []
        assert p.max_tokens is None
        assert p.context_window is None

    def test_provider_id_sane(self):
        with pytest.raises(ValidationError):
            ProviderCapabilityProfile(provider_id="../evil")
        with pytest.raises(ValidationError):
            ProviderCapabilityProfile(provider_id="")

    def test_matrix_score_negative_rejected(self):
        with pytest.raises(ValidationError):
            make_profile("x", {"chat": -0.1})

    def test_matrix_score_over_one_rejected(self):
        with pytest.raises(ValidationError):
            make_profile("x", {"chat": 1.1})

    def test_matrix_score_one_allowed(self):
        p = make_profile("x", {"chat": 1.0})
        assert p.quality("chat") == 1.0

    def test_matrix_zero_allowed(self):
        p = make_profile("x", {"vision": 0.0})
        assert p.matrix["vision"] == 0.0

    def test_matrix_non_numeric_rejected(self):
        with pytest.raises(ValidationError):
            make_profile("x", {"chat": "high"})

    def test_evidence_normalized(self):
        p = make_profile("x", evidence=["  benchmark: X  ", "", "vendor docs", "vendor docs"])
        assert p.evidence == ["benchmark: X", "vendor docs"]

    def test_evidence_none_defaults_empty(self):
        p = make_profile("x", evidence=None)
        assert p.evidence == []

    def test_max_tokens_context_window(self):
        p = make_profile("x", max_tokens=8000, context_window=128000)
        assert p.max_tokens == 8000
        assert p.context_window == 128000


class TestQualityQueries:
    def test_quality_present(self):
        p = make_profile("openai", {"code": 0.8})
        assert p.quality("code") == 0.8

    def test_quality_missing_zero(self):
        """矩阵缺失能力 → 0.0 (无证据 = 无能力, 不臆造)。"""
        p = make_profile("openai", {"code": 0.8})
        assert p.quality("vision") == 0.0

    def test_quality_case_sensitive(self):
        p = make_profile("openai", {"code": 0.8})
        assert p.quality("CODE") == 0.0

    def test_has_present_above_threshold(self):
        p = make_profile("openai", {"code": 0.8})
        assert p.has("code", 0.5) is True

    def test_has_present_below_threshold(self):
        p = make_profile("openai", {"code": 0.8})
        assert p.has("code", 0.9) is False

    def test_has_missing_key_false_even_min_quality_zero(self):
        """★ 键存在语义: min_quality=0.0 是\"键存在即可\", 不是\"0 分也通过\"。"""
        p = make_profile("openai", {"code": 0.8})
        assert p.has("vision", 0.0) is False

    def test_has_zero_score_present(self):
        """键存在且 0 分: has(0.0) 通过 (有证据但质量 0), has(0.1) 不过。"""
        p = make_profile("openai", {"vision": 0.0})
        assert p.has("vision", 0.0) is True
        assert p.has("vision", 0.1) is False

    def test_average_quality(self):
        p = make_profile("openai", {"chat": 0.9, "code": 0.8, "reasoning": 0.7})
        assert p.average_quality(["chat", "code", "reasoning"]) == 0.8

    def test_average_quality_missing_counts_zero(self):
        p = make_profile("openai", {"chat": 0.9})
        assert p.average_quality(["chat", "vision"]) == 0.45

    def test_average_quality_empty_zero(self):
        p = make_profile("openai", {"chat": 0.9})
        assert p.average_quality([]) == 0.0

    def test_to_dict_json(self):
        p = make_profile("openai", {"chat": 0.9}, evidence=["bench: x"])
        d = p.to_dict()
        assert d["provider_id"] == "openai"
        assert d["matrix"] == {"chat": 0.9}
        assert d["evidence"] == ["bench: x"]


def _req(**kwargs) -> TaskRequirement:
    return TaskRequirement(**kwargs)


class TestTaskRequirement:
    def test_defaults(self):
        r = TaskRequirement()
        assert r.task_type == "development"
        assert r.required_capabilities == []
        assert r.min_quality == 0.0
        assert r.budget is None

    def test_task_type_empty_rejected(self):
        with pytest.raises(ValidationError):
            TaskRequirement(task_type="  ")

    def test_capabilities_normalized(self):
        r = TaskRequirement(required_capabilities=[" code ", "", "code", "reasoning"])
        assert r.required_capabilities == ["code", "reasoning"]

    def test_min_quality_range(self):
        with pytest.raises(ValidationError):
            TaskRequirement(min_quality=-0.1)
        with pytest.raises(ValidationError):
            TaskRequirement(min_quality=1.1)

    def test_budget_nonnegative(self):
        with pytest.raises(ValidationError):
            TaskRequirement(budget=-1.0)

    def test_to_dict(self):
        d = _req(task_type="testing", required_capabilities=["code"], budget=1.0).to_dict()
        assert d["task_type"] == "testing"
        assert d["budget"] == 1.0

    def test_dict_validation_raises(self):
        """非法 dict 输入 (如负 min_quality) → ValidationError (不静默吞)。"""
        with pytest.raises(ValidationError):
            TaskRequirement.model_validate({"min_quality": -2.0})


class TestRankForTask:
    def test_rank_orders_by_score_desc(self):
        profiles = [
            make_profile("a", {"code": 0.5}),
            make_profile("b", {"code": 0.9}),
            make_profile("c", {"code": 0.7}),
        ]
        ranked = rank_for_task(_req(required_capabilities=["code"]), profiles)
        assert [p.provider_id for p, _ in ranked] == ["b", "c", "a"]
        assert ranked[0][1] == 0.9

    def test_rank_filters_missing_capability(self):
        """缺能力证据 → 过滤 (无证据不推荐)。"""
        profiles = [
            make_profile("a", {"code": 0.8}),
            make_profile("b", {"chat": 0.9}),  # 无 code 证据
        ]
        ranked = rank_for_task(_req(required_capabilities=["code"]), profiles)
        assert [p.provider_id for p, _ in ranked] == ["a"]

    def test_rank_filters_below_min_quality(self):
        profiles = [make_profile("a", {"code": 0.4}), make_profile("b", {"code": 0.8})]
        ranked = rank_for_task(
            _req(required_capabilities=["code"], min_quality=0.6), profiles,
        )
        assert [p.provider_id for p, _ in ranked] == ["b"]

    def test_rank_min_quality_zero_requires_key(self):
        """min_quality=0.0 仍需键存在 — vision=0.0 无能力不过。"""
        profiles = [
            make_profile("a", {"code": 0.8}),
            make_profile("b", {"vision": 0.0}),  # 有键但 0 分
            make_profile("c", {"chat": 0.9}),  # 无 vision 键
        ]
        ranked = rank_for_task(
            _req(required_capabilities=["vision"], min_quality=0.0), profiles,
        )
        assert [p.provider_id for p, _ in ranked] == ["b"]

    def test_rank_no_required_uses_matrix_average(self):
        profiles = [
            make_profile("a", {"chat": 0.9, "code": 0.8}),
            make_profile("b", {"chat": 0.5, "code": 0.5}),
        ]
        ranked = rank_for_task(_req(required_capabilities=[]), profiles)
        assert [p.provider_id for p, _ in ranked] == ["a", "b"]
        assert ranked[0][1] == 0.85
        assert ranked[1][1] == 0.5

    def test_rank_no_required_empty_matrix_score_one(self):
        """无能力要求 + 无矩阵 → 完全匹配 (1.0)。"""
        profiles = [ProviderCapabilityProfile(provider_id="x")]
        ranked = rank_for_task(_req(), profiles)
        assert ranked[0][1] == 1.0

    def test_rank_stable_same_score(self):
        """同分保输入序 (稳定排序)。"""
        profiles = [
            make_profile("a", {"code": 0.8}),
            make_profile("b", {"code": 0.8}),
            make_profile("c", {"code": 0.8}),
        ]
        ranked = rank_for_task(_req(required_capabilities=["code"]), profiles)
        assert [p.provider_id for p, _ in ranked] == ["a", "b", "c"]

    def test_rank_dict_input(self):
        profiles_dict = {"a": make_profile("a", {"code": 0.9}), "b": make_profile("b", {"code": 0.5})}
        ranked = rank_for_task(_req(required_capabilities=["code"]), profiles_dict)
        assert [p.provider_id for p, _ in ranked] == ["a", "b"]

    def test_rank_dict_requirement_input(self):
        profiles = [make_profile("a", {"code": 0.8})]
        ranked = rank_for_task({"required_capabilities": ["code"]}, profiles)
        assert ranked[0][0].provider_id == "a"

    def test_rank_none_profiles_empty(self):
        assert rank_for_task(_req(), None) == []

    def test_rank_multi_capability_average_score(self):
        profiles = [make_profile("a", {"code": 0.8, "reasoning": 0.6})]
        ranked = rank_for_task(
            _req(required_capabilities=["code", "reasoning"]), profiles,
        )
        assert ranked[0][1] == 0.7

    def test_rank_multi_capability_any_missing_filters(self):
        profiles = [
            make_profile("a", {"code": 0.8, "reasoning": 0.6}),
            make_profile("b", {"code": 0.9}),  # 缺 reasoning
        ]
        ranked = rank_for_task(
            _req(required_capabilities=["code", "reasoning"]), profiles,
        )
        assert [p.provider_id for p, _ in ranked] == ["a"]


class TestFindBestForTask:
    def test_best_hit(self):
        profiles = [make_profile("a", {"code": 0.5}), make_profile("b", {"code": 0.9})]
        best, score = find_best_for_task(_req(required_capabilities=["code"]), profiles)
        assert best.provider_id == "b"
        assert score == 0.9

    def test_best_none_when_no_candidate(self):
        profiles = [make_profile("a", {"chat": 0.9})]
        assert find_best_for_task(_req(required_capabilities=["code"]), profiles) is None

    def test_best_none_when_empty(self):
        assert find_best_for_task(_req(), []) is None


class TestProfileIndependence:
    def test_make_definition_unrelated(self):
        """能力层与 ProviderDefinition 定义层独立 (helper 冒烟)。"""
        d = make_definition("openai")
        assert d.id == "openai"
        assert "chat" in d.capabilities
