"""test_provider_declared_actual_8b3.py — Declared vs Actual 对比 (Phase 8B-3, ADR-0025)。

覆盖 providers/usage.py declared_vs_actual (Provider Intelligence Loop 可视化数据源):
- declared = 能力基线声明值 (ProviderCapabilityProfile matrix 平均质量分; 无 profile / 空矩阵 → None)
- actual = 实测聚合 (成功率先按 provider 合并多 (model, version) 桶; 时长按调用数加权;
  无 usage 记录 → None 字段)
- gap = declared - actual_success_rate (正 = 表现不及声明, 负 = 优于声明; 任一侧缺失 → None)
- 返回按 provider_id 排序的 JSON 友好条目
"""

from __future__ import annotations

from providers.capability import ProviderCapabilityProfile
from providers.usage import (
    ProviderUsage,
    declared_vs_actual,
    stats_from_usage,
)


def make_profile(
    provider_id: str,
    matrix: dict[str, float] | None = None,
) -> ProviderCapabilityProfile:
    return ProviderCapabilityProfile(
        provider_id=provider_id,
        matrix=matrix if matrix is not None else {"chat": 0.8, "code": 0.6, "reasoning": 1.0},
    )


def make_usage(
    provider_id: str = "openai",
    *,
    model: str | None = "gpt-4o",
    version: str | None = "1.0",
    latency_ms: int = 100,
    success: bool = True,
) -> ProviderUsage:
    return ProviderUsage(
        provider_id=provider_id, model=model, version=version,
        latency_ms=latency_ms, success=success,
        recorded_at="2026-08-06T10:00:00.000000Z",
    )


def _stats(records):
    return stats_from_usage(records)


# ------------------------------------------------------------------ 无声明 / 无实测


class TestDeclaredVsActualNoData:
    def test_empty_inputs_empty_output(self):
        assert declared_vs_actual(None, []) == []

    def test_empty_profiles_empty_stats(self):
        assert declared_vs_actual({}, []) == []

    def test_profile_without_usage_declared_only(self):
        profiles = {"openai": make_profile("openai")}
        entries = declared_vs_actual(profiles, [])
        assert len(entries) == 1
        e = entries[0]
        assert e["provider_id"] == "openai"
        assert e["declared_score"] == round((0.8 + 0.6 + 1.0) / 3, 4)  # 0.8
        assert e["actual_success_rate"] is None
        assert e["actual_avg_duration_ms"] is None
        assert e["actual_execution_count"] == 0
        assert e["gap"] is None  # actual 缺失 → gap None

    def test_usage_without_profile_actual_only(self):
        records = [
            make_usage(provider_id="openai", success=True),
            make_usage(provider_id="openai", success=True),
            make_usage(provider_id="openai", success=False),
        ]
        entries = declared_vs_actual(None, _stats(records))
        assert len(entries) == 1
        e = entries[0]
        assert e["declared_score"] is None  # 无声明不臆造
        assert e["actual_success_rate"] == round(2 / 3, 4)
        assert e["actual_execution_count"] == 3
        assert e["gap"] is None  # declared 缺失 → gap None


# ------------------------------------------------------------------ 完整对比


class TestDeclaredVsActualFull:
    def test_declared_is_matrix_average(self):
        profiles = {"openai": make_profile("openai", {"a": 1.0, "b": 0.5})}
        e = declared_vs_actual(profiles, [])[0]
        assert e["declared_score"] == 0.75

    def test_gap_positive_underperforms(self):
        """declared 0.8 > actual 0.5 → gap +0.3 (表现不及声明)。"""
        profiles = {"openai": make_profile("openai", {"chat": 0.8, "code": 0.8})}
        records = [
            make_usage(success=True),
            make_usage(success=False),
        ]
        e = declared_vs_actual(profiles, _stats(records))[0]
        assert e["declared_score"] == 0.8
        assert e["actual_success_rate"] == 0.5
        assert e["gap"] == 0.3

    def test_gap_negative_outperforms(self):
        """declared 0.5 < actual 1.0 → gap -0.5 (优于声明)。"""
        profiles = {"openai": make_profile("openai", {"a": 0.5})}
        records = [make_usage(success=True)]
        e = declared_vs_actual(profiles, _stats(records))[0]
        assert e["gap"] == -0.5

    def test_gap_zero_when_matches(self):
        profiles = {"openai": make_profile("openai", {"a": 1.0})}
        records = [make_usage(success=True)]
        e = declared_vs_actual(profiles, _stats(records))[0]
        assert e["gap"] == 0.0

    def test_actual_duration_weighted_across_buckets(self):
        """时长按调用数加权: (100*1 + 300*3)/4 = 250。"""
        profiles = {"openai": make_profile("openai", {"a": 1.0})}
        records = [
            make_usage(model="a", latency_ms=100),
            make_usage(model="b", latency_ms=300),
            make_usage(model="b", latency_ms=300),
            make_usage(model="b", latency_ms=300),
        ]
        e = declared_vs_actual(profiles, _stats(records))[0]
        assert e["actual_avg_duration_ms"] == 250.0

    def test_actual_success_merged_across_buckets(self):
        """成功率先合并再除: 桶1 (1/1) + 桶2 (1/3) → 2/4 = 0.5。"""
        profiles = {"openai": make_profile("openai", {"a": 1.0})}
        records = [
            make_usage(model="a", success=True),
            make_usage(model="b", success=True),
            make_usage(model="b", success=False),
            make_usage(model="b", success=False),
        ]
        e = declared_vs_actual(profiles, _stats(records))[0]
        assert e["actual_success_rate"] == 0.5
        assert e["actual_execution_count"] == 4

    def test_entries_sorted_by_provider_id(self):
        profiles = {
            "zeta": make_profile("zeta", {"a": 1.0}),
            "alpha": make_profile("alpha", {"a": 1.0}),
        }
        ids = [e["provider_id"] for e in declared_vs_actual(profiles, [])]
        assert ids == ["alpha", "zeta"]

    def test_union_of_profile_and_usage_providers(self):
        """providers = profiles ∪ usage 中出现者 (两侧都列出)。"""
        profiles = {"openai": make_profile("openai", {"a": 1.0})}
        records = [make_usage(provider_id="claude", success=True)]
        entries = declared_vs_actual(profiles, _stats(records))
        assert [e["provider_id"] for e in entries] == ["claude", "openai"]
        by_id = {e["provider_id"]: e for e in entries}
        assert by_id["claude"]["declared_score"] is None
        assert by_id["openai"]["actual_success_rate"] is None

    def test_profile_dict_value_can_be_any_object_with_matrix(self):
        """profiles 值对象只要有 .matrix 即可 (鸭子类型, 与模型解耦)。"""

        class _Fake:
            matrix = {"a": 0.9}

        entries = declared_vs_actual({"openai": _Fake()}, [])
        assert entries[0]["declared_score"] == 0.9


# ------------------------------------------------------------------ 边界


class TestDeclaredVsActualEdges:
    def test_empty_matrix_declared_none(self):
        profiles = {"openai": make_profile("openai", {})}
        e = declared_vs_actual(profiles, [])[0]
        assert e["declared_score"] is None
        assert e["gap"] is None

    def test_all_failed_actual_rate_zero(self):
        profiles = {"openai": make_profile("openai", {"a": 1.0})}
        records = [make_usage(success=False), make_usage(success=False)]
        e = declared_vs_actual(profiles, _stats(records))[0]
        assert e["actual_success_rate"] == 0.0
        assert e["gap"] == 1.0

    def test_zero_length_matrix_never_divide_by_zero(self):
        profiles = {"openai": make_profile("openai", {})}
        entries = declared_vs_actual(profiles, [])
        assert entries[0]["declared_score"] is None  # 空矩阵不除零

    def test_entry_keys_json_friendly(self):
        e = declared_vs_actual({}, _stats([make_usage(success=True)]))[0]
        assert set(e) == {
            "provider_id", "declared_score", "actual_success_rate",
            "actual_avg_duration_ms", "actual_execution_count", "gap",
        }
        # JSON 友好: 全部基础类型
        import json

        json.dumps(e)

    def test_rounding_consistency(self):
        """declared/actual/gap 均 round 4 位。"""
        profiles = {"openai": make_profile("openai", {"a": 0.77777})}
        records = [make_usage(success=True) for _ in range(3)] + [make_usage(success=False)]
        e = declared_vs_actual(profiles, _stats(records))[0]
        for key in ("declared_score", "actual_success_rate", "gap"):
            assert round(e[key], 4) == e[key]
