"""test_provider_performance_8b3.py — 性能聚合增强 + stats_by_provider + 性能分 (Phase 8B-3, ADR-0025)。

覆盖 providers/usage.py Phase 8B-3 增量 (8B-2 stats_from_usage 基础保持, 本文件只测新增):
- ProviderPerformanceStats 8B-3 增强字段: failure_rate / execution_count / avg_duration_ms /
  avg_cost (兼容别名: execution_count == calls, avg_duration_ms == avg_latency_ms)
- stats_from_usage 输出增强列口径: failure_rate = 1 - success_rate; execution_count = 调用数;
  avg_duration_ms = 平均执行时长 (= avg_latency_ms); avg_cost = total_cost / calls (0 调用 → 0.0)
- stats_by_provider: 按 provider 合并多 (model, version) 桶 → 单一统计 (成功率先合并再除,
  时长按调用数加权, 空记录 → {}, period 过滤)
- performance_score_from_stats: 无数据 0.5 中性 / 有数据 0.6*成功率 + 0.4*时长归一
  (duration_score = clamp(1 - avg_duration_ms/60_000, 0, 1))
"""

from __future__ import annotations

from datetime import datetime, timezone

from events.models import format_timestamp
from providers.usage import (
    ProviderPerformanceStats,
    ProviderUsage,
    performance_score_from_stats,
    stats_by_provider,
    stats_from_usage,
)


def make_usage(
    provider_id: str = "openai",
    *,
    model: str | None = "gpt-4o",
    version: str | None = "1.0",
    latency_ms: int = 100,
    estimated_cost: float = 0.01,
    success: bool = True,
    prompt_tokens: int = 10,
    completion_tokens: int = 20,
    recorded_at: str | None = None,
) -> ProviderUsage:
    return ProviderUsage(
        provider_id=provider_id,
        model=model,
        version=version,
        latency_ms=latency_ms,
        estimated_cost=estimated_cost,
        success=success,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        recorded_at=recorded_at or format_timestamp(datetime.now(timezone.utc)),
    )


# ------------------------------------------------------------------ 8B-3 增强字段模型


class TestPerformanceStatsEnhancedFields:
    def test_enhanced_defaults(self):
        s = ProviderPerformanceStats(provider_id="openai")
        assert s.failure_rate == 0.0
        assert s.execution_count == 0
        assert s.avg_duration_ms == 0.0
        assert s.avg_cost == 0.0

    def test_enhanced_fields_in_to_dict(self):
        d = ProviderPerformanceStats(provider_id="openai").to_dict()
        for key in (
            "failure_rate", "execution_count", "avg_duration_ms", "avg_cost",
        ):
            assert key in d

    def test_compat_aliases_same_default(self):
        """8B-2 字段 (calls/avg_latency_ms) 与 8B-3 别名 (execution_count/avg_duration_ms) 同值。"""
        s = ProviderPerformanceStats(provider_id="openai", calls=3, avg_latency_ms=12.5)
        assert s.execution_count == s.calls == 3
        assert s.avg_duration_ms == s.avg_latency_ms == 12.5


# ------------------------------------------------------------------ stats_from_usage 增强列


class TestStatsFromUsageEnhancedColumns:
    def test_failure_rate_complement_of_success(self):
        records = [
            make_usage(success=True),
            make_usage(success=True),
            make_usage(success=False),
        ]
        s = stats_from_usage(records)[0]
        assert s.failure_rate == round(1.0 - s.success_rate, 4) == round(1 / 3, 4)

    def test_execution_count_equals_calls(self):
        records = [make_usage() for _ in range(4)]
        s = stats_from_usage(records)[0]
        assert s.execution_count == 4
        assert s.calls == 4

    def test_avg_duration_ms_alias_avg_latency(self):
        records = [make_usage(latency_ms=100), make_usage(latency_ms=300)]
        s = stats_from_usage(records)[0]
        assert s.avg_duration_ms == 200.0
        assert s.avg_latency_ms == 200.0

    def test_avg_cost_total_over_calls(self):
        records = [
            make_usage(estimated_cost=0.1),
            make_usage(estimated_cost=0.2),
            make_usage(estimated_cost=0.3),
        ]
        s = stats_from_usage(records)[0]
        assert s.avg_cost == 0.2
        assert s.total_cost == 0.6

    def test_avg_cost_zero_calls_zero(self):
        assert ProviderPerformanceStats(provider_id="x").avg_cost == 0.0

    def test_all_failed_failure_rate_one(self):
        records = [make_usage(success=False), make_usage(success=False)]
        s = stats_from_usage(records)[0]
        assert s.success_rate == 0.0
        assert s.failure_rate == 1.0

    def test_all_success_failure_rate_zero(self):
        s = stats_from_usage([make_usage(success=True)])[0]
        assert s.success_rate == 1.0
        assert s.failure_rate == 0.0

    def test_mixed_failure_rate_rounding(self):
        records = [
            make_usage(success=True),
            make_usage(success=True),
            make_usage(success=True),
            make_usage(success=False),
        ]
        s = stats_from_usage(records)[0]
        assert s.success_rate == 0.75
        assert s.failure_rate == 0.25

    def test_enhanced_columns_in_json_dict(self):
        s = stats_from_usage([make_usage()])[0].to_dict()
        assert s["execution_count"] == 1
        assert s["failure_rate"] == 0.0
        assert s["avg_duration_ms"] == 100.0
        assert s["avg_cost"] == 0.01

    def test_zero_call_group_never_emitted(self):
        """stats_from_usage 只输出有记录的组 — 无记录 → [] (0 调用组不臆造)。"""
        assert stats_from_usage([]) == []


# ------------------------------------------------------------------ stats_by_provider (8B-3 新增)


class TestStatsByProvider:
    def test_empty_records_empty_dict(self):
        assert stats_by_provider([]) == {}

    def test_single_bucket_passthrough(self):
        records = [make_usage(latency_ms=100, estimated_cost=0.5, success=True)]
        out = stats_by_provider(records)
        assert set(out) == {"openai"}
        s = out["openai"]
        assert s.calls == 1
        assert s.success_rate == 1.0
        assert s.avg_duration_ms == 100.0
        assert s.total_cost == 0.5
        assert s.avg_cost == 0.5

    def test_merges_model_buckets(self):
        """多 (model, version) 桶 → 跨桶合并 (成功率先合并再除)。"""
        records = [
            make_usage(model="gpt-4o", version="1.0", success=True),
            make_usage(model="gpt-4o-mini", version="1.0", success=True),
            make_usage(model="gpt-4o-mini", version="1.0", success=False),
        ]
        out = stats_by_provider(records)
        assert len(out) == 1  # 只按 provider 合并
        s = out["openai"]
        assert s.calls == 3
        assert s.success_rate == round(2 / 3, 4)
        assert s.failure_rate == round(1 / 3, 4)
        assert s.execution_count == 3
        assert s.model is None  # 合并后无单模型维度
        assert s.version is None

    def test_avg_duration_weighted_by_calls(self):
        """桶合并时长按调用数加权: (100*1 + 300*3) / 4 = 250。"""
        records = [
            make_usage(model="a", latency_ms=100),
            make_usage(model="b", latency_ms=300),
            make_usage(model="b", latency_ms=300),
            make_usage(model="b", latency_ms=300),
        ]
        s = stats_by_provider(records)["openai"]
        assert s.avg_duration_ms == 250.0
        assert s.avg_latency_ms == 250.0

    def test_cost_accumulates_across_buckets(self):
        records = [
            make_usage(model="a", estimated_cost=0.1),
            make_usage(model="b", estimated_cost=0.2),
            make_usage(model="b", estimated_cost=0.3),
        ]
        s = stats_by_provider(records)["openai"]
        assert s.total_cost == 0.6
        assert s.avg_cost == 0.2

    def test_total_tokens_summed(self):
        records = [
            make_usage(prompt_tokens=10, completion_tokens=20),
            make_usage(prompt_tokens=30, completion_tokens=40),
        ]
        s = stats_by_provider(records)["openai"]
        assert s.total_tokens == 100

    def test_multiple_providers_separate(self):
        records = [
            make_usage(provider_id="openai", success=True),
            make_usage(provider_id="claude", success=False),
            make_usage(provider_id="openai", success=True),
        ]
        out = stats_by_provider(records)
        assert set(out) == {"claude", "openai"}
        assert out["openai"].calls == 2
        assert out["openai"].success_rate == 1.0
        assert out["claude"].calls == 1
        assert out["claude"].success_rate == 0.0

    def test_sorted_by_provider_id(self):
        records = [
            make_usage(provider_id="zeta"),
            make_usage(provider_id="alpha"),
            make_usage(provider_id="mike"),
        ]
        assert list(stats_by_provider(records)) == ["alpha", "mike", "zeta"]

    def test_period_filter_day(self):
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        records = [
            make_usage(provider_id="openai", recorded_at=today),
            make_usage(provider_id="openai", recorded_at="2020-01-01T00:00:00.000000Z"),
        ]
        out = stats_by_provider(records, period="day")
        assert out["openai"].calls == 1

    def test_period_field_reflected(self):
        s = stats_by_provider([make_usage()], period="week")["openai"]
        assert s.period == "week"

    def test_failure_rate_zero_calls_default(self):
        """无记录 provider 不进 dict — 不臆造 0 调用统计。"""
        assert "openai" not in stats_by_provider([])


# ------------------------------------------------------------------ performance_score_from_stats (8B-3 新增)


class TestPerformanceScore:
    def test_none_stats_neutral(self):
        """无统计 → 0.5 中性 (8B-2 兼容: 无 usage 数据不臆造性能)。"""
        assert performance_score_from_stats(None) == 0.5

    def test_zero_execution_neutral(self):
        s = ProviderPerformanceStats(provider_id="openai", calls=0, execution_count=0)
        assert performance_score_from_stats(s) == 0.5

    def test_perfect_fast_execution_high(self):
        """全成功 + 近零时长 → 接近满分。"""
        s = ProviderPerformanceStats(
            provider_id="openai", calls=5, execution_count=5,
            success_rate=1.0, avg_duration_ms=1.0,
        )
        assert performance_score_from_stats(s) == 1.0  # round(0.6+0.4*0.99998) = 1.0

    def test_all_failed_fast_execution_low(self):
        """全失败 → 性能分很低 (0.6*0 + 0.4*~1)。"""
        s = ProviderPerformanceStats(
            provider_id="openai", calls=3, execution_count=3,
            success_rate=0.0, avg_duration_ms=100.0,
        )
        score = performance_score_from_stats(s)
        assert 0.3 < score < 0.5  # 失败拖低, 但仍有时长正分

    def test_formula_weights_exact(self):
        """score = 0.6*success_rate + 0.4*duration_score (duration = 1 - avg/60_000)。"""
        s = ProviderPerformanceStats(
            provider_id="openai", calls=2, execution_count=2,
            success_rate=0.5, avg_duration_ms=30_000.0,
        )
        assert performance_score_from_stats(s) == round(0.6 * 0.5 + 0.4 * 0.5, 4) == 0.5

    def test_duration_score_floors_at_zero_60s(self):
        """avg_duration_ms >= 60_000 → duration_score = 0 (时长维度最劣)。"""
        s = ProviderPerformanceStats(
            provider_id="openai", calls=1, execution_count=1,
            success_rate=1.0, avg_duration_ms=60_000.0,
        )
        assert performance_score_from_stats(s) == round(0.6 * 1.0 + 0.4 * 0.0, 4) == 0.6

    def test_duration_score_above_60s_also_zero(self):
        s = ProviderPerformanceStats(
            provider_id="openai", calls=1, execution_count=1,
            success_rate=1.0, avg_duration_ms=120_000.0,
        )
        assert performance_score_from_stats(s) == 0.6

    def test_success_rate_dominates(self):
        """同时长下成功率更高 → 性能分更高。"""
        fast_ok = ProviderPerformanceStats(
            provider_id="a", calls=1, execution_count=1,
            success_rate=0.9, avg_duration_ms=1_000.0,
        )
        fast_bad = ProviderPerformanceStats(
            provider_id="b", calls=1, execution_count=1,
            success_rate=0.5, avg_duration_ms=1_000.0,
        )
        assert performance_score_from_stats(fast_ok) > performance_score_from_stats(fast_bad)

    def test_duration_matters_under_same_success(self):
        """同成功率下更快 → 性能分更高。"""
        quick = ProviderPerformanceStats(
            provider_id="a", calls=1, execution_count=1,
            success_rate=0.8, avg_duration_ms=100.0,
        )
        slow = ProviderPerformanceStats(
            provider_id="b", calls=1, execution_count=1,
            success_rate=0.8, avg_duration_ms=30_000.0,
        )
        assert performance_score_from_stats(quick) > performance_score_from_stats(slow)

    def test_score_bounded_01(self):
        for avg in (0.0, 1_000.0, 59_999.0, 120_000.0):
            for rate in (0.0, 0.25, 0.5, 1.0):
                s = ProviderPerformanceStats(
                    provider_id="x", calls=1, execution_count=1,
                    success_rate=rate, avg_duration_ms=avg,
                )
                assert 0.0 <= performance_score_from_stats(s) <= 1.0

    def test_rounding_four_digits(self):
        s = ProviderPerformanceStats(
            provider_id="x", calls=1, execution_count=1,
            success_rate=0.3333, avg_duration_ms=12_345.0,
        )
        score = performance_score_from_stats(s)
        assert round(score, 4) == score

    def test_stats_from_usage_feeds_score(self):
        """链: usage 记录 → stats → 性能分 (有数据时非中性)。"""
        records = [make_usage(success=True, latency_ms=500)]
        stats = stats_by_provider(records)
        score = performance_score_from_stats(stats["openai"])
        assert score > 0.5  # 有实测成功数据 → 高于无数据中性 0.5

    def test_stats_by_provider_feeds_selector_stats(self):
        """stats_by_provider 输出可直接作为 CostAwareSelector usage_stats 注入源。"""
        records = [make_usage(provider_id="hermes")]
        stats = stats_by_provider(records)
        assert "hermes" in stats
        assert stats["hermes"].execution_count == 1
