"""tests/intelligence/test_intelligence_experience_loop.py — ExperienceAnalyzer
经验闭环 (Phase 10A-4, ADR-0033): 只读聚合 + 正负经验 + Feedback Loop 记录。

覆盖 (任务要求 ≥100 中的分析器/聚合/事件部分):
- ExperienceRecord 增强字段 (subject_type/task_type/capability/quality_score/
  cost/duration/evidence)
- aggregate_records 聚合 (统计 + 正负聚合有效分 + 推理)
- Freshness 半衰期在聚合层生效 (旧记录有效分衰减)
- Positive-Negative feedback (成功提高/失败降低; 全失败 → 0.0)
- negative_signal 派生属性 (单一事实源, 不落库)
- Feedback Loop 入口 record_experience (落库 + feedback.learned 事件)
- analyze (experience.analyzed 事件 + 载荷)
- 事件序列 (feedback.learned → experience.analyzed → task.evaluated)
- Store isolation (数据空间独立; 无 store → 空分析不臆造)
- Failure cases (非法 domain/result/score 拒绝)

basename 全仓库唯一 (test_intelligence_* 前缀, conftest 注释约定)。
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from intelligence.experience import (
    MAX_RECOMMENDED_PER_TYPE,
    RECOMMEND_THRESHOLD,
    ExperienceAnalyzer,
    aggregate_experience_factor,
    aggregate_records,
    matches_experience,
)
from intelligence.models import (
    DEFAULT_HALF_LIFE_DAYS,
    ExperienceAggregation,
    ExperienceDomain,
    ExperienceRecord,
    ExperienceResult,
)

from intelligence_helpers import (
    event_types_of,
    make_evidence,
    make_experience,
    payload_of,
    TS_LATE,
    TS_MID,
    TS_OLD,
)


def _analyzer(store=None, logger=None, *, now=None, half_life_days=30.0):
    return ExperienceAnalyzer(store, logger, now=now, half_life_days=half_life_days)


def _rec_ok(**kw):
    """成功经验工厂 (agent 域, 带增强字段)。"""
    base = dict(
        domain="agent",
        subject_id="coder-1",
        subject_type="agent",
        task_type="development",
        capability=["code"],
        score=0.9,
        confidence=1.0,
        quality_score=0.8,
        cost=0.7,
        duration=120.0,
        evidence=[make_evidence()],
        created_at=TS_LATE,
    )
    base.update(kw)
    return make_experience(**base)


def _rec_fail(**kw):
    base = dict(
        domain="provider",
        subject_id="hermes",
        subject_type="provider",
        task_type="development",
        capability=["code"],
        result="failure",
        score=0.3,
        confidence=0.8,
        created_at=TS_LATE,
    )
    base.update(kw)
    return make_experience(**base)


# ------------------------------------------------------- 增强字段 (模型层)


class TestExperienceEnhancedFields:
    def test_full_fields_recorded(self):
        ev = make_evidence(source_id="evt-exec-1")
        e = ExperienceRecord(
            domain="agent",
            subject_id="coder-1",
            subject_type="agent",
            task_type="development",
            capability=["code", "reasoning"],
            result="success",
            score=0.9,
            quality_score=0.85,
            cost=0.7,
            duration=123.4,
            confidence=0.95,
            evidence=[ev],
        )
        assert e.subject_type == "agent"
        assert e.task_type == "development"
        assert e.capability == ["code", "reasoning"]
        assert e.quality_score == 0.85
        assert e.cost == 0.7
        assert e.duration == 123.4
        assert e.evidence[0].lineage_ref() == "event:evt-exec-1"

    def test_subject_type_derived_from_domain(self):
        e = make_experience(domain="skill", subject_id="python")
        assert e.subject_type == "skill"

    def test_enhanced_fields_defaults(self):
        e = make_experience()
        assert e.task_type == ""
        assert e.capability == []
        assert e.quality_score is None
        assert e.cost is None
        assert e.duration is None
        assert e.evidence == []

    def test_none_capability_coerced_empty(self):
        e = make_experience(capability=None)
        assert e.capability == []

    def test_string_capability_split_comma_not_chars(self):
        """10A-4 单字符 bug 回归: 字符串 capability 按逗号分隔, 不拆成单字符。"""
        e = make_experience(capability="code")
        assert e.capability == ["code"]
        e2 = make_experience(capability="code,reasoning")
        assert e2.capability == ["code", "reasoning"]

    def test_string_capability_empty_segments_filtered(self):
        e = make_experience(capability=" code ,, reasoning ,")
        assert e.capability == ["code", "reasoning"]

    def test_quality_cost_range_validated(self):
        with pytest.raises(ValidationError):
            make_experience(quality_score=1.1)
        with pytest.raises(ValidationError):
            make_experience(cost=-0.1)
        with pytest.raises(ValidationError):
            make_experience(duration=-1.0)

    def test_evidence_coerced_from_dicts(self):
        e = make_experience(evidence=[{"source_type": "event", "source_id": "evt-9"}])
        assert e.evidence[0].lineage_ref() == "event:evt-9"

    def test_to_dict_includes_enhanced_fields(self):
        data = _rec_ok().to_dict()
        assert json.loads(json.dumps(data)) == data
        assert data["subject_type"] == "agent"
        assert data["task_type"] == "development"
        assert data["capability"] == ["code"]
        assert data["quality_score"] == 0.8
        assert data["duration"] == 120.0
        assert data["cost"] == 0.7

    def test_negative_signal_not_in_to_dict(self):
        """negative_signal 是派生属性 (单一事实源), 不落库不序列化。"""
        data = _rec_fail().to_dict()
        assert "negative_signal" not in data
        assert data["result"] == "failure"


# ------------------------------------------------------- matches_experience


class TestMatchesExperience:
    def test_no_filters_matches_all(self):
        assert matches_experience(_rec_ok())

    def test_task_type_equal(self):
        assert matches_experience(_rec_ok(), task_type="development")
        assert not matches_experience(_rec_ok(), task_type="testing")

    def test_capability_intersection(self):
        assert matches_experience(_rec_ok(), capability=["code"])
        assert matches_experience(_rec_ok(), capability=["reasoning", "code"])
        assert not matches_experience(_rec_ok(), capability=["design"])

    def test_capability_string_query_split_comma_not_chars(self):
        """10A-4 单字符 bug 回归: 查询侧字符串 capability 同样按逗号分隔。"""
        assert matches_experience(_rec_ok(), capability="code")
        assert matches_experience(_rec_ok(), capability="reasoning,code")
        assert not matches_experience(_rec_ok(), capability="design")
        assert not matches_experience(_rec_ok(), capability="c")  # 单字符不再命中 "code"

    def test_capability_no_declared_not_match(self):
        e = make_experience(capability=[])
        assert not matches_experience(e, capability=["code"])

    def test_task_and_capability_combined(self):
        assert matches_experience(_rec_ok(), task_type="development", capability=["code"])
        assert not matches_experience(_rec_ok(), task_type="testing", capability=["code"])


# ------------------------------------------------------- 正负聚合 (纯函数)


class TestAggregatePositiveNegative:
    def test_no_records_zero(self):
        assert aggregate_experience_factor([]) == 0.0

    def test_single_success_is_effective_score(self):
        e = _rec_ok(score=0.9, confidence=1.0, created_at=TS_LATE)
        assert aggregate_experience_factor([e], now=TS_LATE) == pytest.approx(0.9)

    def test_all_success_equals_mean_effective(self):
        a = _rec_ok(score=0.9, confidence=1.0, created_at=TS_LATE)
        b = _rec_ok(score=0.7, confidence=1.0, created_at=TS_LATE, exp_id="exp-2")
        assert aggregate_experience_factor([a, b], now=TS_LATE) == pytest.approx(0.8)

    def test_failure_subtracts(self):
        ok = _rec_ok(score=0.9, confidence=1.0, created_at=TS_LATE)
        fail = _rec_fail(score=0.5, confidence=1.0, created_at=TS_LATE)
        # (0.9 - 0.5) / 2 = 0.2 — 失败经验降低未来评分
        assert aggregate_experience_factor([ok, fail], now=TS_LATE) == pytest.approx(0.2)

    def test_all_failure_zero(self):
        f1 = _rec_fail(score=0.5, created_at=TS_LATE)
        f2 = _rec_fail(score=0.4, created_at=TS_LATE, exp_id="exp-3")
        assert aggregate_experience_factor([f1, f2], now=TS_LATE) == 0.0

    def test_failure_dominant_clamped_zero(self):
        ok = _rec_ok(score=0.3, confidence=1.0, created_at=TS_LATE)
        fail = _rec_fail(score=0.8, confidence=1.0, created_at=TS_LATE)
        # (0.3 - 0.8) / 2 < 0 → clamp01 → 0.0
        assert aggregate_experience_factor([ok, fail], now=TS_LATE) == 0.0

    def test_success_raises_above_cold_start_neutral(self):
        ok = _rec_ok(score=0.95, confidence=1.0, created_at=TS_LATE)
        assert aggregate_experience_factor([ok], now=TS_LATE) > RECOMMEND_THRESHOLD

    def test_decay_applies_to_aggregate(self):
        fresh = _rec_ok(score=0.9, confidence=1.0, created_at=TS_LATE)
        stale = _rec_ok(score=0.9, confidence=1.0, created_at=TS_OLD, exp_id="exp-4")
        fresh_v = aggregate_experience_factor([fresh], now=TS_LATE)
        stale_v = aggregate_experience_factor([stale], now=TS_LATE)
        assert stale_v < fresh_v  # 旧记录半衰期衰减, 历史经验不永久有效

    def test_custom_half_life(self):
        stale = _rec_ok(score=0.9, confidence=1.0, created_at=TS_OLD)
        long_hl = aggregate_experience_factor([stale], now=TS_LATE, half_life_days=3650.0)
        short_hl = aggregate_experience_factor([stale], now=TS_LATE, half_life_days=1.0)
        assert long_hl > short_hl


# ------------------------------------------------------- aggregate_records


class TestAggregateRecords:
    def test_empty_cold_start(self):
        agg = aggregate_records([], subject_id="x", subject_type="agent")
        assert agg.record_count == 0
        assert agg.success_rate == 0.0
        assert agg.effective_score == 0.0
        assert agg.reasoning == ["无历史经验记录 (冷启动)"]

    def test_stats_computed(self):
        a = _rec_ok(score=0.8, confidence=0.9, created_at=TS_LATE)
        b = _rec_ok(score=0.6, confidence=0.7, created_at=TS_LATE, exp_id="exp-5")
        agg = aggregate_records([a, b], now=TS_LATE)
        assert agg.record_count == 2
        assert agg.success_count == 2
        assert agg.failure_count == 0
        assert agg.success_rate == 1.0
        assert agg.avg_score == pytest.approx(0.7)
        assert agg.avg_confidence == pytest.approx(0.8)
        assert agg.avg_freshness == pytest.approx(1.0)
        # effective = mean(score×confidence×freshness) = (0.72 + 0.42)/2 = 0.57
        assert agg.effective_score == pytest.approx(0.57)

    def test_failure_counts(self):
        ok = _rec_ok(created_at=TS_LATE)
        fail = _rec_fail(created_at=TS_LATE)
        agg = aggregate_records([ok, fail], now=TS_LATE)
        assert agg.success_count == 1
        assert agg.failure_count == 1
        assert agg.success_rate == 0.5

    def test_avg_cost_only_when_present(self):
        a = _rec_ok(cost=0.6, created_at=TS_LATE)
        b = _rec_ok(cost=None, created_at=TS_LATE, exp_id="exp-6")
        agg = aggregate_records([a, b], now=TS_LATE)
        assert agg.avg_cost == pytest.approx(0.6)  # None 成本不参与平均

    def test_avg_cost_none_when_no_cost(self):
        agg = aggregate_records([_rec_ok(cost=None)], now=TS_LATE)
        assert agg.avg_cost is None

    def test_dimensions_propagated(self):
        agg = aggregate_records(
            [_rec_ok()],
            subject_id="coder-1",
            subject_type="agent",
            task_type="development",
            capability=["code"],
            now=TS_LATE,
        )
        assert agg.subject_id == "coder-1"
        assert agg.subject_type == "agent"
        assert agg.task_type == "development"
        assert agg.capability == ["code"]

    def test_reasoning_explains_positive_negative(self):
        ok = _rec_ok(created_at=TS_LATE)
        fail = _rec_fail(created_at=TS_LATE)
        agg = aggregate_records([ok, fail], now=TS_LATE)
        text = "\n".join(agg.reasoning)
        assert "2 条" in text
        assert "成功 1 / 失败 1" in text
        assert "50%" in text
        assert "失败为负信号扣分" in text


# ------------------------------------------------------- negative_signal


class TestNegativeSignal:
    def test_failure_is_negative(self):
        assert _rec_fail().negative_signal is True

    def test_success_is_not_negative(self):
        assert _rec_ok().negative_signal is False

    def test_derived_from_result_never_diverges(self):
        e = make_experience(result="failure")
        assert e.negative_signal == (e.result is ExperienceResult.FAILURE)

    def test_failure_sample_recorded_like_success(self, experience_store):
        """反事实记录: 失败样本同样落库 (防\"只记成功\"自我循环偏差)。"""
        an = _analyzer(experience_store)
        rec = an.record_experience(
            subject_type="provider", subject_id="hermes",
            result="failure", score=0.2,
        )
        assert experience_store.get(rec.id).result == ExperienceResult.FAILURE
        assert experience_store.get(rec.id).negative_signal is True


# ------------------------------------------------------- records 查询


class TestAnalyzerRecords:
    def test_no_store_returns_empty(self):
        assert _analyzer(None).records() == []

    def test_fresh_store_cold_start(self, experience_store):
        assert _analyzer(experience_store).records() == []

    def test_returns_all(self, experience_store):
        an = _analyzer(experience_store)
        an.record_experience(subject_type="agent", subject_id="a-1", task_type="development", score=0.8)
        an.record_experience(subject_type="provider", subject_id="p-1", task_type="testing", score=0.6)
        assert len(an.records()) == 2

    def test_filter_subject_type(self, experience_store):
        an = _analyzer(experience_store)
        an.record_experience(subject_type="agent", subject_id="a-1", task_type="development", score=0.8)
        an.record_experience(subject_type="provider", subject_id="p-1", task_type="development", score=0.6)
        recs = an.records(subject_type="agent")
        assert [r.subject_id for r in recs] == ["a-1"]

    def test_filter_subject_id(self, experience_store):
        an = _analyzer(experience_store)
        an.record_experience(subject_type="agent", subject_id="a-1", task_type="development", score=0.8)
        an.record_experience(subject_type="agent", subject_id="a-2", task_type="development", score=0.6)
        recs = an.records(subject_id="a-2")
        assert [r.subject_id for r in recs] == ["a-2"]

    def test_filter_task_type(self, experience_store):
        an = _analyzer(experience_store)
        an.record_experience(subject_type="agent", subject_id="a-1", task_type="development", score=0.8)
        an.record_experience(subject_type="agent", subject_id="a-2", task_type="testing", score=0.6)
        recs = an.records(task_type="development")
        assert [r.subject_id for r in recs] == ["a-1"]

    def test_filter_capability_intersection(self, experience_store):
        an = _analyzer(experience_store)
        an.record_experience(subject_type="agent", subject_id="a-1", task_type="development",
                             capability=["code"], score=0.8)
        an.record_experience(subject_type="agent", subject_id="a-2", task_type="development",
                             capability=["design"], score=0.6)
        recs = an.records(capability=["code", "reasoning"])
        assert [r.subject_id for r in recs] == ["a-1"]

    def test_combined_filters(self, experience_store):
        an = _analyzer(experience_store)
        an.record_experience(subject_type="agent", subject_id="a-1", task_type="development",
                             capability=["code"], score=0.8)
        an.record_experience(subject_type="agent", subject_id="a-2", task_type="development",
                             capability=["code"], score=0.6)
        an.record_experience(subject_type="provider", subject_id="p-1", task_type="development",
                             capability=["code"], score=0.6)
        recs = an.records(subject_type="agent", task_type="development", capability=["code"])
        # list_all 按 id (uuid4) 排序, 非插入序 — 断言集合相等, 不依赖记录顺序
        assert sorted(r.subject_id for r in recs) == ["a-1", "a-2"]


# ------------------------------------------------------- record_experience


class TestRecordExperience:
    def test_saves_to_store(self, experience_store):
        an = _analyzer(experience_store)
        rec = an.record_experience(
            subject_type="agent", subject_id="coder-1",
            task_type="development", capability=["code"],
            score=0.9, confidence=0.95,
        )
        assert experience_store.count() == 1
        assert experience_store.get(rec.id).subject_id == "coder-1"

    def test_string_capability_saved_as_list(self, experience_store):
        """10A-4 单字符 bug 回归: record_experience 收字符串 capability →
        落库为逗号分隔清单 (不拆成单字符)。"""
        an = _analyzer(experience_store)
        rec = an.record_experience(
            subject_type="agent", subject_id="coder-1",
            task_type="development", capability="code,reasoning",
            score=0.9,
        )
        assert rec.capability == ["code", "reasoning"]
        assert experience_store.get(rec.id).capability == ["code", "reasoning"]

    def test_returns_record_with_full_fields(self):
        rec = _analyzer(None).record_experience(
            subject_type="skill", subject_id="python",
            task_type="development", capability=["code"],
            result="success", score=0.85, quality_score=0.9, cost=0.8,
            duration=60.0, confidence=0.9,
            evidence=[make_evidence()],
        )
        assert rec.subject_type == "skill"
        assert rec.task_type == "development"
        assert rec.capability == ["code"]
        assert rec.quality_score == 0.9
        assert rec.cost == 0.8
        assert rec.duration == 60.0
        assert len(rec.evidence) == 1

    def test_defaults(self):
        rec = _analyzer(None).record_experience(subject_type="provider", subject_id="x", score=0.7)
        assert rec.result == ExperienceResult.SUCCESS
        assert rec.confidence == 0.5
        assert rec.task_type == ""
        assert rec.capability == []

    def test_without_store_pure_memory(self):
        rec = _analyzer(None).record_experience(subject_type="agent", subject_id="a-1", score=0.7)
        assert rec.subject_id == "a-1"  # 仍返回记录 (纯内存模式, 不落库)

    def test_created_at_injectable(self):
        rec = _analyzer(None).record_experience(
            subject_type="agent", subject_id="a-1", score=0.7, created_at=TS_OLD
        )
        assert rec.created_at == TS_OLD

    def test_negative_records_also_saved(self, experience_store):
        an = _analyzer(experience_store)
        rec = an.record_experience(
            subject_type="provider", subject_id="hermes",
            result="failure", score=0.2, task_type="development", capability=["code"],
        )
        assert experience_store.get(rec.id).negative_signal is True

    def test_failure_case_invalid_domain(self):
        # record_experience 先做枚举转换 (ExperienceDomain("memory") → ValueError;
        # pydantic ValidationError 亦为 ValueError 子类, 统一用 ValueError 捕获)
        with pytest.raises(ValueError):
            _analyzer(None).record_experience(subject_type="memory", subject_id="x", score=0.5)

    def test_failure_case_invalid_result(self):
        with pytest.raises(ValueError):
            _analyzer(None).record_experience(
                subject_type="agent", subject_id="x", result="partial", score=0.5
            )

    def test_failure_case_score_out_of_range(self):
        with pytest.raises(ValidationError):
            _analyzer(None).record_experience(subject_type="agent", subject_id="x", score=1.5)


# ------------------------------------------------------- analyze


class TestAnalyze:
    def test_cold_start_analysis(self, logger):
        an = _analyzer(None, logger)
        analysis = an.analyze(subject_id="coder-1", subject_type="agent")
        assert analysis.subject_id == "coder-1"
        assert analysis.subject_type == "agent"
        assert analysis.aggregation.record_count == 0
        assert analysis.aggregation.reasoning == ["无历史经验记录 (冷启动)"]

    def test_analyze_aggregates_records(self, experience_store, logger):
        an = _analyzer(experience_store, logger)
        an.record_experience(subject_type="agent", subject_id="coder-1",
                             task_type="development", capability=["code"],
                             score=0.9, confidence=1.0)
        analysis = an.analyze(subject_id="coder-1", subject_type="agent",
                              task_type="development", capability=["code"])
        assert analysis.aggregation.record_count == 1
        assert analysis.aggregation.success_rate == 1.0
        assert analysis.aggregation.effective_score > RECOMMEND_THRESHOLD

    def test_analyze_filters_by_task_type(self, experience_store, logger):
        an = _analyzer(experience_store, logger)
        an.record_experience(subject_type="agent", subject_id="coder-1",
                             task_type="development", score=0.9)
        an.record_experience(subject_type="agent", subject_id="coder-1",
                             task_type="testing", score=0.8, created_at=TS_LATE)
        analysis = an.analyze(subject_id="coder-1", task_type="testing")
        assert analysis.aggregation.record_count == 1

    def test_analyze_read_only_no_side_effect(self, experience_store, logger):
        an = _analyzer(experience_store, logger)
        an.record_experience(subject_type="agent", subject_id="a-1", task_type="development", score=0.9)
        before = experience_store.count()
        an.analyze(subject_id="a-1", subject_type="agent")
        assert experience_store.count() == before  # 只读分析零写入

    def test_analyze_reasoning_readable(self, experience_store, logger):
        an = _analyzer(experience_store, logger)
        an.record_experience(subject_type="provider", subject_id="p-1",
                             task_type="development", result="failure", score=0.2)
        analysis = an.analyze(subject_id="p-1", subject_type="provider",
                              task_type="development")
        assert analysis.aggregation.failure_count == 1
        assert analysis.aggregation.effective_score == 0.0


# ------------------------------------------------------- 事件


class TestExperienceEvents:
    def test_record_fires_feedback_learned(self, logger):
        an = _analyzer(None, logger)
        rec = an.record_experience(
            subject_type="agent", subject_id="coder-1",
            task_type="development", capability=["code"],
            result="failure", score=0.2,
        )
        types = event_types_of(logger.store)
        assert "intelligence.feedback.learned" in types
        payload = payload_of(logger.store, "intelligence.feedback.learned")
        assert payload["experience_id"] == rec.id
        assert payload["negative_signal"] is True
        assert payload["task_type"] == "development"
        assert payload["capability"] == ["code"]

    def test_analyze_fires_experience_analyzed(self, experience_store, logger):
        an = _analyzer(experience_store, logger)
        an.record_experience(subject_type="agent", subject_id="coder-1",
                             task_type="development", score=0.9)
        analysis = an.analyze(subject_id="coder-1", subject_type="agent",
                              task_type="development")
        payload = payload_of(logger.store, "intelligence.experience.analyzed")
        assert payload["subject_id"] == "coder-1"
        assert payload["record_count"] == 1
        assert payload["success_rate"] == 1.0
        assert payload["effective_score"] == analysis.aggregation.effective_score

    def test_events_silent_without_logger(self, experience_store):
        an = _analyzer(experience_store, None)
        an.record_experience(subject_type="agent", subject_id="a-1", score=0.7)
        analysis = an.analyze(subject_id="a-1")
        assert analysis.aggregation.record_count == 1  # 无 logger 不崩, 事件静默

    def test_analyze_and_record_sequence(self, logger):
        """事件链: record (feedback.learned) → analyze (experience.analyzed)。"""
        an = _analyzer(None, logger)
        an.record_experience(subject_type="agent", subject_id="a-1", score=0.7)
        an.analyze(subject_id="a-1", subject_type="agent")
        types = event_types_of(logger.store)
        assert types.index("intelligence.feedback.learned") < types.index(
            "intelligence.experience.analyzed"
        )

    def test_task_evaluated_after_analyze_chain(self, experience_store, logger):
        """闭环链: 记录 → 分析 → 任务评估 (analyzed → task.evaluated)。"""
        from intelligence.evaluate import TaskEvaluator

        from intelligence.models import TaskRequirement

        an = _analyzer(experience_store, logger)
        an.record_experience(subject_type="agent", subject_id="a-1",
                             task_type="development", capability=["code"], score=0.9)
        an.analyze(subject_id="a-1", subject_type="agent", task_type="development")
        TaskEvaluator(experience_store, logger).evaluate(
            TaskRequirement(task_type="development", required_capabilities=["code"])
        )
        types = event_types_of(logger.store)
        assert types.index("intelligence.experience.analyzed") < types.index(
            "intelligence.task.evaluated"
        )


# ------------------------------------------------------- Store isolation


class TestExperienceStoreIsolation:
    def test_data_space_separate_files(self, tmp_path):
        from intelligence.store import DecisionStore, ExperienceStore, RecommendationStore

        idir = tmp_path / "factory" / "intelligence"
        ExperienceStore(idir).save(make_experience())
        DecisionStore(idir).save(_dummy_decision())
        RecommendationStore(idir).save(_dummy_recommendation())
        assert sorted(p.name for p in idir.iterdir()) == [
            "decisions.json",
            "experiences.json",
            "recommendations.json",
        ]

    def test_experience_removal_does_not_affect_core(self, tmp_path):
        from events.models import Event

        from events.store import EventStore

        from intelligence.store import ExperienceStore

        idir = tmp_path / "factory" / "intelligence"
        ExperienceStore(idir).save(make_experience())
        db = tmp_path / "factory" / "events.db"
        store = EventStore(db)
        store.append(Event.create("task.start", source="test"))
        store.close()
        import shutil

        shutil.rmtree(idir)
        reopened = EventStore(db)
        assert reopened.count() == 1
        reopened.close()

    def test_analyzer_no_store_does_not_create_dir(self, tmp_path):
        an = _analyzer(None)
        an.analyze(subject_id="x")
        an.records()
        assert not (tmp_path / "factory" / "intelligence").exists()


def _dummy_decision():
    from intelligence_helpers import make_decision

    return make_decision()


def _dummy_recommendation():
    from intelligence_helpers import make_recommendation

    return make_recommendation()
