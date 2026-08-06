"""test_provider_recommend_8b3.py — 推荐三分数权重 (Phase 8B-3, ADR-0025)。

覆盖 providers/selector.py CostAwareSelector Phase 8B-3 增量:
- Recommendation 三分数 (capability_score/cost_score/performance_score) 字段 + to_dict
- _cost_score: 无成本模型 → 0.0 (成本维度最劣, 与 8B-2 排序语义同向); free → 1.0;
  越贵越低 (线性衰减, 归一基准 _COST_SCORE_DECAY=0.01)
- performance_score: 注入 usage_stats → 实测性能分; 无 usage 数据 → 0.5 中性 (8B-2 兼容)
- score = 0.4*capability + 0.3*cost + 0.3*performance (综合推荐分)
- 排序: 成本升序 → 同成本性能分降序 → 同成本同性能综合分降序 (无 usage 时退化为 8B-2 序)
- reasons 含性能分标注 (实测 N 次执行 / 无 usage 数据, 中性)
"""

from __future__ import annotations

import pytest

from providers.capability import ProviderCapabilityProfile
from providers.costs import ProviderCostModel
from providers.models import ProviderDefinition, ProviderStatus, TaskRequirement
from providers.registry import ProviderRegistry
from providers.selector import CostAwareSelector, Recommendation
from providers.store import ProviderStore
from providers.usage import ProviderPerformanceStats, stats_by_provider

from providers_helpers import make_definition


def make_profile(provider_id: str, matrix: dict[str, float]) -> ProviderCapabilityProfile:
    return ProviderCapabilityProfile(provider_id=provider_id, matrix=matrix)


def make_cost(
    provider_id: str, mode: str = "token", pricing: dict | None = None,
    free: bool = False,
) -> ProviderCostModel:
    return ProviderCostModel(
        provider_id=provider_id, mode=mode,
        pricing=pricing or {"input": 10.0, "output": 20.0},
        currency="USD", free=free,
    )


def make_stats(
    provider_id: str, *, calls: int = 5, success_rate: float = 1.0,
    avg_duration_ms: float = 500.0, avg_cost: float = 0.0,
) -> ProviderPerformanceStats:
    return ProviderPerformanceStats(
        provider_id=provider_id, calls=calls, execution_count=calls,
        success_rate=success_rate, failure_rate=round(1.0 - success_rate, 4),
        avg_latency_ms=avg_duration_ms, avg_duration_ms=avg_duration_ms,
        avg_cost=avg_cost,
    )


@pytest.fixture
def registry_with(store: ProviderStore) -> ProviderRegistry:
    return ProviderRegistry(store)


# ------------------------------------------------------------------ Recommendation 模型


class TestRecommendationThreeScores:
    def test_defaults_zero(self):
        r = Recommendation(provider_id="openai", score=0.5, reasons=[])
        assert r.capability_score == 0.0
        assert r.cost_score == 0.0
        assert r.performance_score == 0.0

    def test_to_dict_contains_three_scores(self):
        r = Recommendation(
            provider_id="openai", score=0.8, reasons=["x"],
            capability_score=0.9, cost_score=0.7, performance_score=0.5,
        )
        d = r.to_dict()
        assert d["capability_score"] == 0.9
        assert d["cost_score"] == 0.7
        assert d["performance_score"] == 0.5

    def test_source_is_recommendation(self):
        r = Recommendation(provider_id="openai", score=0.5, reasons=[])
        assert r.source == "recommendation"


# ------------------------------------------------------------------ cost_score


class TestCostScore:
    def test_no_cost_model_zero(self):
        """无成本模型 → 0.0 — 成本信息缺失 = 成本维度最劣 (与 8B-2 排最后同向)。"""
        from providers.selector import _cost_score

        assert _cost_score(None, None) == 0.0

    def test_free_is_one(self):
        from providers.selector import _cost_score

        assert _cost_score(make_cost("x", free=True), 0.0) == 1.0

    def test_zero_cost_is_one(self):
        from providers.selector import _cost_score

        assert _cost_score(make_cost("x"), 0.0) == 1.0

    def test_linear_decay_expensive_lower(self):
        from providers.selector import _cost_score

        cheap = _cost_score(make_cost("x"), 0.001)
        pricey = _cost_score(make_cost("x"), 0.009)
        assert cheap > pricey
        assert 0.0 < cheap <= 1.0
        assert 0.0 < pricey < 1.0

    def test_decay_floor_at_baseline(self):
        """cost >= _COST_SCORE_DECAY (0.01) → 成本分归零。"""
        from providers.selector import _cost_score

        assert _cost_score(make_cost("x"), 0.01) == 0.0
        assert _cost_score(make_cost("x"), 0.5) == 0.0

    def test_formula_exact(self):
        from providers.selector import _cost_score

        assert _cost_score(make_cost("x"), 0.002) == round(1.0 - 0.002 / 0.01, 4) == 0.8

    def test_free_beats_paid(self):
        from providers.selector import _cost_score

        assert _cost_score(make_cost("x", free=True), 0.0) > _cost_score(make_cost("x"), 0.001)


def _make_selector(store, *, profiles=None, costs=None, usage=None):
    """模块级 CostAwareSelector 构造 (profiles/costs/usage 可缺省)。"""
    return CostAwareSelector(
        ProviderRegistry(store),
        capability_profiles=profiles or {},
        cost_models=costs or {},
        usage_stats=usage or {},
    )


# ------------------------------------------------------------------ 三分数加权推荐


class TestRecommendationWeights:
    def test_score_weighted_formula(self, store):
        store.save_definition(make_definition("alpha", capabilities=["chat"]))
        profiles = {"alpha": make_profile("alpha", {"chat": 0.8})}
        costs = {"alpha": make_cost("alpha", free=True)}
        usage = {"alpha": make_stats("alpha", success_rate=0.9)}
        r = _make_selector(store, profiles=profiles, costs=costs, usage=usage).recommend(
            TaskRequirement(task_type="feature", required_capabilities=["chat"]),
        )
        # capability 0.8 (0.4) + cost 1.0 (0.3) + performance 0.9 实测 (0.3)
        assert r.capability_score == 0.8
        assert r.cost_score == 1.0
        assert r.performance_score > 0.5  # 有实测数据 → 非中性
        assert r.score == round(0.4 * 0.8 + 0.3 * 1.0 + 0.3 * r.performance_score, 4)

    def test_no_usage_neutral_performance(self, store):
        """无 usage_stats → performance_score 0.5 中性 (8B-2 兼容)。"""
        store.save_definition(make_definition("alpha", capabilities=["chat"]))
        profiles = {"alpha": make_profile("alpha", {"chat": 0.8})}
        costs = {"alpha": make_cost("alpha", free=True)}
        r = _make_selector(store, profiles=profiles, costs=costs).recommend(
            TaskRequirement(task_type="feature", required_capabilities=["chat"]),
        )
        assert r.performance_score == 0.5
        assert r.score == round(0.4 * 0.8 + 0.3 * 1.0 + 0.3 * 0.5, 4)

    def test_performance_reflects_usage_stats(self, store):
        """注入 usage_stats → performance_score = 实测性能分 (非 0.5)。"""
        store.save_definition(make_definition("alpha", capabilities=["chat"]))
        profiles = {"alpha": make_profile("alpha", {"chat": 0.8})}
        usage = {"alpha": make_stats("alpha", calls=10, success_rate=1.0, avg_duration_ms=100.0)}
        r = _make_selector(store, profiles=profiles, usage=usage).recommend(
            TaskRequirement(task_type="feature", required_capabilities=["chat"]),
        )
        from providers.usage import performance_score_from_stats

        assert r.performance_score == performance_score_from_stats(usage["alpha"])
        assert r.performance_score > 0.5

    def test_bad_performance_lowers_score(self, store):
        """同能力同成本下: 实测差 (全失败) → 综合分低于无数据中性。"""
        store.save_definition(make_definition("alpha", capabilities=["chat"]))
        profiles = {"alpha": make_profile("alpha", {"chat": 0.8})}
        costs = {"alpha": make_cost("alpha", free=True)}
        bad = _make_selector(
            store, profiles=profiles, costs=costs,
            usage={"alpha": make_stats("alpha", success_rate=0.0)},
        ).recommend(TaskRequirement(task_type="feature", required_capabilities=["chat"]))
        neutral = _make_selector(
            store, profiles=profiles, costs=costs,
        ).recommend(TaskRequirement(task_type="feature", required_capabilities=["chat"]))
        assert bad.score < neutral.score

    def test_good_performance_raises_score(self, store):
        store.save_definition(make_definition("alpha", capabilities=["chat"]))
        profiles = {"alpha": make_profile("alpha", {"chat": 0.8})}
        costs = {"alpha": make_cost("alpha", free=True)}
        good = _make_selector(
            store, profiles=profiles, costs=costs,
            usage={"alpha": make_stats("alpha", success_rate=1.0, avg_duration_ms=1.0)},
        ).recommend(TaskRequirement(task_type="feature", required_capabilities=["chat"]))
        neutral = _make_selector(
            store, profiles=profiles, costs=costs,
        ).recommend(TaskRequirement(task_type="feature", required_capabilities=["chat"]))
        assert good.score > neutral.score

    def test_reasons_mention_measured_executions(self, store):
        store.save_definition(make_definition("alpha", capabilities=["chat"]))
        profiles = {"alpha": make_profile("alpha", {"chat": 0.8})}
        usage = {"alpha": make_stats("alpha", calls=7)}
        r = _make_selector(store, profiles=profiles, usage=usage).recommend(
            TaskRequirement(task_type="feature", required_capabilities=["chat"]),
        )
        assert any("实测 7 次执行" in reason for reason in r.reasons)

    def test_reasons_mention_neutral_when_no_usage(self, store):
        store.save_definition(make_definition("alpha", capabilities=["chat"]))
        profiles = {"alpha": make_profile("alpha", {"chat": 0.8})}
        r = _make_selector(store, profiles=profiles).recommend(
            TaskRequirement(task_type="feature", required_capabilities=["chat"]),
        )
        assert any("无 usage 数据, 中性" in reason for reason in r.reasons)

    def test_reasons_include_performance_score(self, store):
        store.save_definition(make_definition("alpha", capabilities=["chat"]))
        profiles = {"alpha": make_profile("alpha", {"chat": 0.8})}
        r = _make_selector(store, profiles=profiles).recommend(
            TaskRequirement(task_type="feature", required_capabilities=["chat"]),
        )
        assert any("性能分: 0.50" in reason for reason in r.reasons)

    def test_candidate_capability_score_required_average(self, store):
        """required 多能力 → capability_score = 平均质量分。"""
        store.save_definition(make_definition("alpha", capabilities=["chat"]))
        profiles = {"alpha": make_profile("alpha", {"chat": 0.8, "code": 0.6})}
        r = _make_selector(store, profiles=profiles).recommend(
            TaskRequirement(task_type="feature", required_capabilities=["chat", "code"]),
        )
        assert r.capability_score == 0.7

    def test_selector_exposes_usage_stats(self, store):
        sel = CostAwareSelector(ProviderRegistry(store), usage_stats={"a": make_stats("a")})
        assert "a" in sel.usage_stats


# ------------------------------------------------------------------ 三分数排序


class TestRecommendationSorting:
    def _setup(self, store, specs):
        """specs: [(id, cost, perf, cap)] → 注册 + 数据注入。"""
        profiles, costs, usage = {}, {}, {}
        for pid, cost, perf, cap in specs:
            store.save_definition(make_definition(pid, capabilities=["chat"]))
            profiles[pid] = make_profile(pid, {"chat": cap})
            costs[pid] = make_cost(pid, free=(cost == 0.0))
            if cost is None:
                costs.pop(pid)  # 无成本模型 → 排最后
            usage[pid] = make_stats(pid, success_rate=perf)
        return CostAwareSelector(
            ProviderRegistry(store), profiles, costs, usage,
        )

    def test_cheapest_first(self, store):
        """成本升序: free 优先。"""
        sel = self._setup(store, [
            ("paid", 0.005, 1.0, 0.9),
            ("free", 0.0, 0.5, 0.8),
        ])
        r = sel.recommend(TaskRequirement(task_type="feature", required_capabilities=["chat"]))
        assert r.provider_id == "free"

    def test_no_cost_model_last(self, store):
        sel = self._setup(store, [
            ("no-cost", None, 1.0, 0.9),
            ("paid", 0.001, 0.5, 0.5),
        ])
        r = sel.recommend(TaskRequirement(task_type="feature", required_capabilities=["chat"]))
        assert r.provider_id == "paid"

    def test_same_cost_prefers_higher_performance(self, store):
        """同成本 → 实测性能分降序 (三分数排序的 8B-3 增量)。"""
        sel = self._setup(store, [
            ("slow", 0.0, 0.3, 0.9),
            ("fast", 0.0, 0.9, 0.9),
        ])
        r = sel.recommend(TaskRequirement(task_type="feature", required_capabilities=["chat"]))
        assert r.provider_id == "fast"

    def test_same_cost_same_perf_falls_back_to_score(self, store):
        """同成本同性能 → 综合分降序 (无 usage 时退化为能力序)。"""
        sel = self._setup(store, [
            ("weak", 0.0, 0.5, 0.5),
            ("strong", 0.0, 0.5, 0.9),
        ])
        r = sel.recommend(TaskRequirement(task_type="feature", required_capabilities=["chat"]))
        assert r.provider_id == "strong"

    def test_config_preferred_still_wins(self, store):
        """配置优先层 (8B-1 链) 在 8B-3 保持: 配置选中且过能力过滤 → 直接推荐。"""
        store.save_definition(make_definition("configured", capabilities=["chat"]))
        store.save_definition(make_definition("cheap", capabilities=["chat"]))
        sel = CostAwareSelector(
            ProviderRegistry(store),
            capability_profiles={
                "configured": make_profile("configured", {"chat": 0.7}),
                "cheap": make_profile("cheap", {"chat": 0.9}),
            },
            cost_models={
                "configured": make_cost("configured", free=True),
                "cheap": make_cost("cheap", free=True),
            },
        )
        r = sel.recommend(
            TaskRequirement(task_type="feature", required_capabilities=["chat"]),
            preferences={"feature": {"provider": "configured"}},
        )
        assert r.provider_id == "configured"
        assert any("配置优先" in reason for reason in r.reasons)

    def test_recommendation_to_dict_full(self, store):
        store.save_definition(make_definition("alpha", capabilities=["chat"]))
        profiles = {"alpha": make_profile("alpha", {"chat": 0.8})}
        r = _make_selector(store, profiles=profiles).recommend(
            TaskRequirement(task_type="feature", required_capabilities=["chat"]),
        )
        d = r.to_dict()
        assert d["score"] == r.score
        assert d["capability_score"] == 0.8
        assert d["cost_score"] == 0.0  # 无成本模型 → 0.0
        assert d["performance_score"] == 0.5


# ------------------------------------------------------------------ 端到端: usage → stats → recommend 三分数


class TestUsageToRecommendChain:
    def test_usage_records_feed_recommendation(self, store):
        """冒烟链: usage 记录 → stats_by_provider → CostAwareSelector usage_stats。"""
        from providers.usage import ProviderUsage, UsageStore

        usage_store = UsageStore(store.dir)
        usage_store.record(ProviderUsage(
            provider_id="alpha", model="m", latency_ms=200, success=True,
        ))
        usage_store.record(ProviderUsage(
            provider_id="alpha", model="m", latency_ms=300, success=True,
        ))
        usage_store.record(ProviderUsage(
            provider_id="alpha", model="m", latency_ms=400, success=False,
        ))
        store.save_definition(make_definition("alpha", capabilities=["chat"]))
        stats = stats_by_provider(usage_store.list())
        assert stats["alpha"].calls == 3
        assert stats["alpha"].success_rate == round(2 / 3, 4)
        sel = _make_selector(
            store,
            profiles={"alpha": make_profile("alpha", {"chat": 0.8})},
            costs={"alpha": make_cost("alpha", free=True)},
            usage=stats,
        )
        r = sel.recommend(TaskRequirement(task_type="feature", required_capabilities=["chat"]))
        assert r.provider_id == "alpha"
        from providers.usage import performance_score_from_stats

        assert r.performance_score == performance_score_from_stats(stats["alpha"])
        assert r.score == round(0.4 * 0.8 + 0.3 * 1.0 + 0.3 * r.performance_score, 4)

    def test_recommendation_provider_definition_attached(self, store):
        store.save_definition(make_definition("alpha", capabilities=["chat"]))
        profiles = {"alpha": make_profile("alpha", {"chat": 0.8})}
        r = _make_selector(store, profiles=profiles).recommend(
            TaskRequirement(task_type="feature", required_capabilities=["chat"]),
        )
        assert r.provider is not None
        assert r.provider.id == "alpha"
        assert r.to_dict()["provider"]["id"] == "alpha"

    def test_no_candidate_returns_none(self, store):
        """无 profile 候选 → None (无能力证据不推荐)。"""
        store.save_definition(make_definition("alpha", capabilities=["chat"]))
        r = _make_selector(store).recommend(
            TaskRequirement(task_type="feature", required_capabilities=["chat"]),
        )
        assert r is None
