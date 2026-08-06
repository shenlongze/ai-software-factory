"""tests/intelligence/test_intelligence_experience.py — 经验 freshness/decay (Phase 10A-1)。

覆盖: 五域经验记录的 freshness 指数衰减 (半衰期)、effective_score =
performance × confidence × freshness、mark_used (usage_count/last_used/新鲜度
刷新)、衰减锚点 = last_used、store 持久化后衰减语义不变。
"""

from __future__ import annotations

import pytest

from intelligence.models import DEFAULT_HALF_LIFE_DAYS, ExperienceRecord

from intelligence_helpers import (
    TS_LATE,
    TS_MID,
    TS_OLD,
    assert_experience_equal,
    make_experience,
)

#: 30 天半衰期 (秒)
_HALF_LIFE_S = DEFAULT_HALF_LIFE_DAYS * 86400.0


class TestFreshnessDecay:
    def test_fresh_at_creation(self):
        """同一时刻: age=0 → freshness=1.0 (刚记录时最新鲜)。"""
        e = make_experience(created_at=TS_OLD)
        assert e.current_freshness(now=TS_OLD) == 1.0

    def test_freshness_after_one_half_life(self):
        e = make_experience(created_at=TS_OLD)
        # TS_OLD + 30 天 = 2026-01-31T00:00:00.000000Z
        assert e.current_freshness(now="2026-01-31T00:00:00.000000Z") == pytest.approx(0.5)

    def test_freshness_after_two_half_lives(self):
        e = make_experience(created_at=TS_OLD)
        # TS_OLD + 60 天 = 2026-03-02 (TS_LATE)
        assert e.current_freshness(now=TS_LATE) == pytest.approx(0.25)

    def test_freshness_monotonic_decreasing(self):
        e = make_experience(created_at=TS_OLD)
        f1 = e.current_freshness(now="2026-01-10T00:00:00.000000Z")
        f2 = e.current_freshness(now="2026-02-10T00:00:00.000000Z")
        f3 = e.current_freshness(now="2026-03-10T00:00:00.000000Z")
        assert f1 > f2 > f3
        assert f3 > 0.0  # 历史经验不永久有效, 但永不为负

    def test_custom_half_life(self):
        e = make_experience(created_at=TS_OLD)
        # 自定义半衰期 10 天: TS_OLD + 10 天 → 0.5
        assert e.current_freshness(now="2026-01-11T00:00:00.000000Z", half_life_days=10) == pytest.approx(0.5)

    def test_default_half_life_constant(self):
        assert DEFAULT_HALF_LIFE_DAYS == 30.0


class TestEffectiveScore:
    def test_formula_score_times_confidence_times_freshness(self):
        e = make_experience(score=0.8, confidence=0.9, created_at=TS_OLD)
        # 同一时刻: freshness=1.0 → 0.8 × 0.9 × 1.0
        assert e.effective_score(now=TS_OLD) == pytest.approx(0.72)

    def test_effective_score_decays_with_age(self):
        fresh = make_experience(exp_id="e-fresh", score=0.9, confidence=1.0, created_at=TS_OLD)
        old = make_experience(exp_id="e-old", score=0.9, confidence=1.0, created_at=TS_OLD)
        fresh_s = fresh.effective_score(now="2026-01-05T00:00:00.000000Z")
        old_s = old.effective_score(now="2026-02-15T00:00:00.000000Z")
        assert fresh_s > old_s  # 同样的表现, 越久远越不有效

    def test_failure_sample_effective_score_low(self):
        e = make_experience(result="failure", score=0.1, confidence=1.0, created_at=TS_OLD)
        assert e.effective_score(now=TS_OLD) == pytest.approx(0.1)

    def test_effective_score_never_exceeds_performance(self):
        """score × confidence × freshness ≤ score (衰减不放大历史经验)。"""
        e = make_experience(score=0.6, confidence=1.0, created_at=TS_OLD)
        assert e.effective_score(now=TS_LATE) <= 0.6


class TestMarkUsed:
    def test_mark_used_increments_count_and_sets_last_used(self):
        e = make_experience()
        used = e.mark_used(now=TS_MID)
        assert used.usage_count == 1
        assert used.last_used == TS_MID
        assert used.freshness == 1.0  # 使用即刷新新鲜度
        # 原对象不变 (model_copy 新实例语义)
        assert e.usage_count == 0
        assert e.last_used is None

    def test_multiple_uses_increment(self):
        e = make_experience()
        e = e.mark_used(now="2026-01-02T00:00:00.000000Z")
        e = e.mark_used(now="2026-01-03T00:00:00.000000Z")
        assert e.usage_count == 2
        assert e.last_used == "2026-01-03T00:00:00.000000Z"

    def test_mark_used_default_now(self):
        e = make_experience()
        used = e.mark_used()
        assert used.last_used is not None
        assert used.last_used != TS_OLD

    def test_decay_anchor_is_last_used_after_use(self):
        """衰减锚点 = last_used (被反复验证的经验保持有效)。"""
        e = make_experience(created_at=TS_OLD).mark_used(now="2026-01-10T00:00:00.000000Z")
        # 锚点 2026-01-10, now 2026-01-15 → age 5 天
        assert e.current_freshness(now="2026-01-15T00:00:00.000000Z") == pytest.approx(
            0.5 ** (5.0 / 30.0)
        )

    def test_usage_refreshes_freshness_vs_never_used(self):
        """同年龄: 使用过的经验 (锚点=last_used) 比从未使用的更新鲜。"""
        unused = make_experience(created_at=TS_OLD)
        used = make_experience(exp_id="e2", created_at=TS_OLD).mark_used(now=TS_MID)
        now = "2026-01-20T00:00:00.000000Z"
        assert used.current_freshness(now=now) > unused.current_freshness(now=now)


class TestExperienceStoreIntegration:
    def test_mark_used_persisted_via_store(self, experience_store):
        e = make_experience().mark_used(now=TS_MID)
        experience_store.save(e)
        got = experience_store.get(e.id)
        assert got.usage_count == 1
        assert got.last_used == TS_MID
        assert got.freshness == 1.0

    def test_freshness_decay_after_store_roundtrip(self, experience_store):
        e = make_experience(created_at=TS_OLD)
        experience_store.save(e)
        got = experience_store.get(e.id)
        assert got.current_freshness(now="2026-01-31T00:00:00.000000Z") == pytest.approx(0.5)
        assert got.effective_score(now="2026-01-31T00:00:00.000000Z") == pytest.approx(
            e.score * e.confidence * 0.5
        )

    def test_effective_score_unchanged_by_model_copy_persistence(self, experience_store):
        e = make_experience(score=0.5, confidence=0.5, created_at=TS_OLD)
        experience_store.save(e)
        got = experience_store.get(e.id)
        assert got.effective_score(now=TS_OLD) == pytest.approx(0.25)

    def test_roundtrip_equality_fieldwise(self, experience_store):
        e = make_experience(usage_count=3, last_used=TS_MID, freshness=0.4)
        experience_store.save(e)
        assert_experience_equal(experience_store.get(e.id), e)

    def test_experience_is_immutable_record_kind(self):
        """经验记录 = 事实快照: 结果/评分不可事后改写 (学习算法只读经验, 10A-4)。"""
        e = make_experience()
        assert isinstance(e, ExperienceRecord)
        assert e.result.value in {"success", "failure"}
