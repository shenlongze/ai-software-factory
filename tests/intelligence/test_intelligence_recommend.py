"""tests/intelligence/test_intelligence_recommend.py — RecommendationEngine 引擎
(Phase 10A-3, ADR-0032): Context → Filter → Evaluation → Rank → Reasoning →
Risk → Recommendation Artifact (+ 可选 Decision Artifact / 9c Approval)。

覆盖 (任务要求 ≥80 中的引擎部分):
- Candidate model (四类型/中性缺省/None 归一/factors)
- Weight calculation (默认 0.35/0.30/0.20/0.15 / 自定义 / 归一化)
- Capability/Performance/Cost ranking (权重主导 + 排序)
- Experience influence (effective_score = score×confidence×freshness 聚合)
- Cold start (中性分不惩罚新候选; 无记录 → neutral 来源)
- Explanation generation (正向原因/负向因素/中性说明 结构化 ReasoningItem)
- Risk detection (R1 竞争激烈 / R2 明显短板 / R3 严重短板 / R4 冷启动提示 /
  R5 低置信度; requires_approval 派生 = high 或低置信度)
- Confidence (分数差距/经验覆盖/候选深度)
- Decision integration (→Decision Artifact →9c ApprovalGate 绑定, 复用 10A-2)
- Event sequence (recommendation.started → candidate.evaluated×N → explained
  → [created 落库时] → completed)
- Store persistence (落库 Recommendation Artifact 可见)

basename 全仓库唯一 (test_intelligence_* 前缀, conftest 注释约定)。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from intelligence.decision import (
    CLOSE_COMPETITION_GAP,
    LOW_CONFIDENCE_THRESHOLD,
    NEUTRAL_FACTOR,
)
from intelligence.models import (
    Candidate,
    CandidateEvaluation,
    CandidateType,
    Decision,
    DecisionStatus,
    Evidence,
    ExperienceRecord,
    ReasoningDirection,
    ReasoningItem,
    RecommendationContext,
    RecommendationResult,
    RiskAssessment,
    RiskLevel,
)
from intelligence.recommend import (
    CRITICAL_FACTOR_THRESHOLD,
    DEFAULT_WEIGHTS,
    LOW_FACTOR_THRESHOLD,
    NEGATIVE_THRESHOLD,
    POSITIVE_THRESHOLD,
    RECOMMEND_FACTOR_KEYS,
    NoCandidatesError,
    RecommendationEngine,
    RecommendationEngineError,
    assess_recommendation_risk,
    compute_recommendation_confidence,
    evaluate_factors,
    score_candidate,
)

from intelligence_helpers import (
    event_sequence,
    make_evidence,
    make_experience,
    payload_of,
    TS_LATE,
    TS_MID,
    TS_OLD,
)

# ---------------------------------------------------------------- 工厂 helper


def _candidate(
    cid: str,
    *,
    cap: float = 0.8,
    perf: float = 0.8,
    cost: float = 0.8,
    exp: float | None = None,
    ctype: str | CandidateType = "provider",
    description: str = "",
    evidence: list | None = None,
) -> Candidate:
    """候选工厂 (exp 缺省 None → 中性 0.5, 模拟冷启动)。"""
    kw: dict = {
        "id": cid,
        "type": ctype,
        "capability": cap,
        "performance": perf,
        "cost": cost,
        "description": description,
    }
    if exp is not None:
        kw["experience"] = exp
    if evidence is not None:
        kw["evidence"] = evidence
    return Candidate(**kw)


def _ctx(candidates: list[Candidate], **kw) -> RecommendationContext:
    """推荐上下文工厂 (固定确定性输入)。"""
    base: dict = {
        "task_type": "development",
        "required_capabilities": ["code", "reasoning"],
        "candidates": candidates,
    }
    base.update(kw)
    return RecommendationContext(**base)


def _engine(*args, **kw) -> RecommendationEngine:
    """引擎工厂 (支持位置参数 store, 同 10A-2 _engine 模式)。"""
    return RecommendationEngine(*args, **kw)


def _evaluation(
    cid: str,
    score: float,
    *,
    factors: dict[str, float] | None = None,
    experience_records: int = 0,
) -> CandidateEvaluation:
    """CandidateEvaluation 工厂 (风险/置信度单测直接构造)。"""
    return CandidateEvaluation(
        candidate_id=cid,
        candidate_type="provider",
        score=score,
        factors=factors or {"capability": score, "performance": score, "cost": score, "experience": 0.5},
        experience_records=experience_records,
    )


# ------------------------------------------------------------------ Candidate 模型


class TestCandidateModel:
    def test_default_type_provider(self):
        assert _candidate("a").type is CandidateType.PROVIDER

    def test_four_types_supported(self):
        for ctype, enum in (
            ("provider", CandidateType.PROVIDER),
            ("agent", CandidateType.AGENT),
            ("skill", CandidateType.SKILL),
            ("workflow", CandidateType.WORKFLOW),
        ):
            assert _candidate("a", ctype=ctype).type is enum

    def test_type_coerced_from_string(self):
        assert Candidate(**{"id": "a", "capability": 0.5, "performance": 0.5, "cost": 0.5, "type": "agent"}).type is CandidateType.AGENT

    def test_experience_defaults_neutral(self):
        assert _candidate("a").experience == NEUTRAL_FACTOR

    def test_evidence_none_defaults_empty(self):
        assert _candidate("a", evidence=None).evidence == []

    def test_evidence_coerced_from_dicts(self):
        c = Candidate(**{"id": "a", "capability": 0.5, "performance": 0.5, "cost": 0.5, "evidence": [{"source_type": "event", "source_id": "e1"}]})
        assert len(c.evidence) == 1
        assert isinstance(c.evidence[0], Evidence)

    def test_factors_keys_order(self):
        assert list(_candidate("a").factors().keys()) == list(RECOMMEND_FACTOR_KEYS)

    def test_factors_values(self):
        c = _candidate("a", cap=0.9, perf=0.8, cost=0.7, exp=0.6)
        assert c.factors() == {"capability": 0.9, "performance": 0.8, "cost": 0.7, "experience": 0.6}

    def test_out_of_range_rejected(self):
        with pytest.raises(Exception):
            _candidate("a", cap=1.5)

    def test_to_dict_json(self):
        d = _candidate("a").to_dict()
        assert d["id"] == "a"
        assert d["type"] == "provider"
        assert d["experience"] == 0.5


# ------------------------------------------------------------------ 权重 (Weight)


class TestWeights:
    def test_default_weights_sum_one(self):
        assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)

    def test_default_weights_values(self):
        assert DEFAULT_WEIGHTS["capability"] == pytest.approx(0.35)
        assert DEFAULT_WEIGHTS["performance"] == pytest.approx(0.30)
        assert DEFAULT_WEIGHTS["cost"] == pytest.approx(0.20)
        assert DEFAULT_WEIGHTS["experience"] == pytest.approx(0.15)

    def test_engine_weights_property(self):
        assert _engine().weights == pytest.approx(DEFAULT_WEIGHTS)

    def test_custom_weights_normalized(self):
        engine = _engine(weights={"capability": 1.0, "performance": 1.0})
        w = engine.weights
        assert w["capability"] == pytest.approx(0.5)
        assert w["performance"] == pytest.approx(0.5)
        assert w["cost"] == pytest.approx(0.0)
        assert w["experience"] == pytest.approx(0.0)

    def test_unknown_key_rejected(self):
        with pytest.raises(ValueError):
            _engine(weights={"capability": 1.0, "nonsense": 1.0})

    def test_zero_sum_rejected(self):
        with pytest.raises(ValueError):
            _engine(weights={"capability": 0.0})

    def test_negative_rejected(self):
        with pytest.raises(ValueError):
            _engine(weights={"capability": -0.1, "performance": 1.0})

    def test_weights_are_read_only_copy(self):
        engine = _engine()
        engine.weights["capability"] = 1.0
        assert engine.weights["capability"] == pytest.approx(0.35)


# ------------------------------------------------------------------ 四因素评分 (Score)


class TestScoreCalculation:
    def test_default_weights_score(self):
        ev = score_candidate(_candidate("a", cap=0.9, perf=0.8, cost=0.7, exp=0.6), [], DEFAULT_WEIGHTS)
        assert ev.score == pytest.approx(0.785)

    def test_components_per_factor(self):
        ev = score_candidate(_candidate("a", cap=0.9, perf=0.8, cost=0.7, exp=0.6), [], DEFAULT_WEIGHTS)
        assert ev.score_components["capability"] == pytest.approx(0.9 * 0.35)
        assert ev.score_components["performance"] == pytest.approx(0.8 * 0.30)
        assert ev.score_components["cost"] == pytest.approx(0.7 * 0.20)
        assert ev.score_components["experience"] == pytest.approx(0.6 * 0.15)

    def test_components_sum_equals_score(self):
        ev = score_candidate(_candidate("a", cap=0.9, perf=0.8, cost=0.7, exp=0.6), [], DEFAULT_WEIGHTS)
        assert sum(ev.score_components.values()) == pytest.approx(ev.score)

    def test_custom_weights_score(self):
        ev = score_candidate(
            _candidate("a", cap=0.9, perf=0.8, cost=0.7, exp=0.6),
            [],
            {"capability": 0.7, "performance": 0.3},
        )
        assert ev.score == pytest.approx(0.9 * 0.7 + 0.8 * 0.3)

    def test_capability_only_weight(self):
        ev = score_candidate(_candidate("a", cap=0.9), [], {"capability": 1.0})
        assert ev.score == pytest.approx(0.9)

    def test_perfect_candidate_scores_one(self):
        ev = score_candidate(_candidate("a", cap=1.0, perf=1.0, cost=1.0, exp=1.0), [], DEFAULT_WEIGHTS)
        assert ev.score == pytest.approx(1.0)

    def test_zero_candidate_scores_zero(self):
        ev = score_candidate(_candidate("a", cap=0.0, perf=0.0, cost=0.0, exp=0.0), [], DEFAULT_WEIGHTS)
        assert ev.score == pytest.approx(0.0)

    def test_score_rounded_three_dp(self):
        ev = score_candidate(_candidate("a", cap=0.999, perf=0.999, cost=0.999, exp=0.999), [], DEFAULT_WEIGHTS)
        assert ev.score == round(ev.score, 3)

    def test_factors_recorded_in_evaluation(self):
        ev = score_candidate(_candidate("a", cap=0.9, perf=0.8, cost=0.7, exp=0.6), [], DEFAULT_WEIGHTS)
        assert ev.factors == {"capability": 0.9, "performance": 0.8, "cost": 0.7, "experience": 0.6}

    def test_required_capabilities_in_reasoning(self):
        ev = score_candidate(_candidate("a"), [], DEFAULT_WEIGHTS, required_capabilities=["code"])
        assert any("任务要求能力: code" in r.text for r in ev.reasoning)


# ------------------------------------------------------------------ 排序 (Ranking)


class TestRanking:
    def _ranked(self, context: RecommendationContext) -> list[CandidateEvaluation]:
        engine = _engine()
        engine.recommend(context)
        return engine._last_candidates  # noqa: SLF001 — 排序断言走结果 evaluations

    def test_top_candidate_is_highest_score(self):
        result = _engine().recommend(_ctx([_candidate("a", cap=0.9), _candidate("b", cap=0.6)]))
        assert result.top_candidate_id == "a"

    def test_evaluations_sorted_desc(self):
        result = _engine().recommend(_ctx([_candidate("a", cap=0.6), _candidate("b", cap=0.9)]))
        scores = [e.score for e in result.evaluations]
        assert scores == sorted(scores, reverse=True)

    def test_result_score_matches_top_evaluation(self):
        result = _engine().recommend(_ctx([_candidate("a", cap=0.9), _candidate("b", cap=0.6)]))
        assert result.score == result.evaluations[0].score

    def test_capability_dominates_ranking(self):
        """能力权重最高 (0.35): 能力满分者即使性能/成本弱也胜 (专业的人做专业的事)。"""
        a = _candidate("a", cap=1.0, perf=0.6, cost=0.6)
        b = _candidate("b", cap=0.5, perf=0.9, cost=0.9)
        result = _engine().recommend(_ctx([a, b]))
        assert result.top_candidate_id == "a"

    def test_performance_beats_experience(self):
        """性能 (0.30) 权重高于经验 (0.15): 同能力/成本下性能高者胜。"""
        a = _candidate("a", cap=0.8, perf=0.95, cost=0.8, exp=0.2)
        b = _candidate("b", cap=0.8, perf=0.5, cost=0.8, exp=0.95)
        result = _engine().recommend(_ctx([a, b]))
        assert result.top_candidate_id == "a"

    def test_candidate_type_does_not_change_score(self):
        """四类型统一评分公式: 类型只是候选属性 (KISS)。"""
        ev_provider = score_candidate(_candidate("a", ctype="provider", cap=0.9), [], DEFAULT_WEIGHTS)
        ev_agent = score_candidate(_candidate("a", ctype="agent", cap=0.9), [], DEFAULT_WEIGHTS)
        assert ev_provider.score == ev_agent.score


# ------------------------------------------------------------------ 过滤 (Filter)


class TestFilter:
    def test_quality_target_filters_low_capability(self):
        result = _engine().recommend(_ctx(
            [_candidate("a", cap=0.9), _candidate("b", cap=0.5)],
            quality_target=0.8,
        ))
        assert result.top_candidate_id == "a"
        assert result.filtered_candidates == ["b"]
        assert len(result.evaluations) == 1

    def test_budget_filters_low_cost_benefit(self):
        result = _engine().recommend(_ctx(
            [_candidate("a", cap=0.9, cost=0.9), _candidate("b", cap=0.9, cost=0.5)],
            budget=0.7,
        ))
        assert result.top_candidate_id == "a"
        assert result.filtered_candidates == ["b"]

    def test_budget_none_no_filter(self):
        result = _engine().recommend(_ctx([_candidate("a", cap=0.9, cost=0.1)]))
        assert result.top_candidate_id == "a"
        assert result.filtered_candidates == []

    def test_quality_none_no_filter(self):
        result = _engine().recommend(_ctx([_candidate("a", cap=0.1)]))
        assert result.top_candidate_id == "a"

    def test_all_filtered_no_recommendation(self):
        """宁缺毋滥: 全部被过滤 → 无推荐 (top_candidate_id None + 高风险)。"""
        result = _engine().recommend(_ctx(
            [_candidate("a", cap=0.5), _candidate("b", cap=0.6)],
            quality_target=0.9,
        ))
        assert result.top_candidate_id is None
        assert result.risk_level == RiskLevel.HIGH.value
        assert result.requires_approval is True
        assert len(result.evaluations) == 0
        assert set(result.filtered_candidates) == {"a", "b"}

    def test_filtered_candidates_auditable(self):
        result = _engine().recommend(_ctx(
            [_candidate("a", cap=0.9), _candidate("b", cap=0.4), _candidate("c", cap=0.3)],
            quality_target=0.8,
        ))
        assert result.filtered_candidates == ["b", "c"]


# ------------------------------------------------------------------ 经验 (Experience)


class TestExperienceInfluence:
    def test_effective_score_product(self):
        """experience = score×confidence×freshness (Q3 影响链基础)。"""
        rec = make_experience(score=0.8, confidence=0.9, created_at=TS_LATE)
        assert rec.effective_score(TS_LATE) == pytest.approx(0.8 * 0.9 * 1.0)

    def test_freshness_decay_over_half_life(self):
        """60 天 / 30 天半衰期 → freshness 0.25 (历史经验不永久有效)。"""
        rec = make_experience(created_at=TS_OLD)
        assert rec.current_freshness(TS_LATE, half_life_days=30.0) == pytest.approx(0.25)

    def test_stale_record_lowers_experience_factor(self):
        ev = evaluate_factors(
            _candidate("a"), [make_experience(score=0.8, confidence=0.9, created_at=TS_OLD)],
            now=TS_LATE, half_life_days=30.0,
        )
        assert ev[0]["experience"] == pytest.approx(0.8 * 0.9 * 0.25)

    def test_fresh_record_full_effective(self):
        ev = evaluate_factors(
            _candidate("a"), [make_experience(score=0.8, confidence=0.9, created_at=TS_LATE)],
            now=TS_LATE, half_life_days=30.0,
        )
        assert ev[0]["experience"] == pytest.approx(0.8 * 0.9)

    def test_multiple_records_average(self):
        ev = evaluate_factors(
            _candidate("a"),
            [
                make_experience(score=0.9, confidence=1.0, created_at=TS_LATE),
                make_experience(score=0.5, confidence=1.0, created_at=TS_LATE),
            ],
            now=TS_LATE, half_life_days=30.0,
        )
        assert ev[0]["experience"] == pytest.approx(0.7)

    def test_source_records(self):
        recs = [make_experience(created_at=TS_LATE)]
        factors, count, source = evaluate_factors(_candidate("a"), recs, now=TS_LATE)
        assert count == 1
        assert source == "records"

    def test_source_declared(self):
        factors, count, source = evaluate_factors(_candidate("a", exp=0.7), [])
        assert count == 0
        assert source == "declared"
        assert factors["experience"] == pytest.approx(0.7)

    def test_source_neutral_when_declared_neutral(self):
        factors, count, source = evaluate_factors(_candidate("a", exp=0.5), [])
        assert source == "neutral"
        assert factors["experience"] == pytest.approx(NEUTRAL_FACTOR)

    def test_cold_start_neutral_default(self):
        """冷启动: 无历史记录 → 候选声明经验分, 缺省 0.5 中性 (不臆造经验)。"""
        ev = score_candidate(_candidate("a"), [], DEFAULT_WEIGHTS)
        assert ev.factors["experience"] == pytest.approx(NEUTRAL_FACTOR)
        assert ev.experience_records == 0
        assert ev.experience_source == "neutral"

    def test_cold_start_not_punished(self):
        """冷启动不惩罚: 无记录中性 0.5 > 旧失败经验的有效分。"""
        a = _candidate("a")  # 无记录 → 中性 0.5
        stale_failure = make_experience(score=0.2, confidence=0.5, created_at=TS_OLD, result="failure")
        b = _candidate("b")
        ev_a = evaluate_factors(a, [], now=TS_LATE, half_life_days=30.0)[0]
        ev_b = evaluate_factors(b, [stale_failure], now=TS_LATE, half_life_days=30.0)[0]
        assert ev_a["experience"] > ev_b["experience"]

    def test_historical_context_preferred_over_store(self):
        """historical_context 优先于 ExperienceStore (显式上下文是唯一事实源)。"""
        rec_in_ctx = make_experience(score=0.9, confidence=1.0, created_at=TS_LATE, subject_id="cand")
        rec_in_store = make_experience(score=0.1, confidence=1.0, created_at=TS_LATE, subject_id="cand")

        class FakeStore:
            def find(self, subject_id):
                return [rec_in_store]

        engine = _engine(experience_store=FakeStore(), now=lambda: TS_LATE)
        context = _ctx(
            [_candidate("cand")],
            historical_context={"cand": [rec_in_ctx]},
        )
        result = engine.recommend(context)
        assert result.evaluations[0].factors["experience"] == pytest.approx(0.9)

    def test_experience_store_fallback(self):
        """无 historical_context → ExperienceStore.find 兜底。"""
        rec = make_experience(score=0.8, confidence=0.9, created_at=TS_LATE, subject_id="cand")

        class FakeStore:
            def find(self, subject_id):
                assert subject_id == "cand"
                return [rec]

        engine = _engine(experience_store=FakeStore())
        result = engine.recommend(_ctx([_candidate("cand")]))
        assert result.evaluations[0].experience_source == "records"
        assert result.evaluations[0].experience_records == 1

    def test_mark_used_refreshes_freshness(self):
        """使用即刷新: mark_used 后 freshness 重置 1.0 (被验证的经验保持有效)。"""
        rec = make_experience(created_at=TS_OLD)
        used = rec.mark_used(now=TS_LATE)
        assert used.last_used == TS_LATE
        assert used.freshness == 1.0
        assert used.effective_score(TS_LATE) == pytest.approx(rec.score * rec.confidence)

    def test_experience_reasoning_mentions_records(self):
        ev = score_candidate(
            _candidate("a"),
            [make_experience(score=0.8, confidence=0.9, created_at=TS_LATE)],
            DEFAULT_WEIGHTS, now=TS_LATE,
        )
        text = " ".join(r.text for r in ev.reasoning)
        assert "历史经验 1 条" in text
        assert "成功率 100%" in text

    def test_cold_start_reasoning_text(self):
        ev = score_candidate(_candidate("a"), [], DEFAULT_WEIGHTS)
        text = " ".join(r.text for r in ev.reasoning)
        assert "冷启动" in text
        assert "中性分不惩罚" in text


# ------------------------------------------------------------------ 置信度 (Confidence)


class TestConfidence:
    def test_empty_evaluations_zero(self):
        assert compute_recommendation_confidence([]) == 0.0

    def test_single_candidate_spread_is_own_score(self):
        ev = [_evaluation("a", 0.8, experience_records=1)]
        assert compute_recommendation_confidence(ev) == pytest.approx(0.5 * 0.8 + 0.3 * 1.0 + 0.2 * 0.2)

    def test_spread_between_top_and_runner_up(self):
        evs = [
            _evaluation("a", 0.9, experience_records=1),
            _evaluation("b", 0.5, experience_records=1),
        ]
        assert compute_recommendation_confidence(evs) == pytest.approx(0.5 * 0.4 + 0.3 * 1.0 + 0.2 * 0.4)

    def test_experience_coverage_raises_confidence(self):
        evs_cold = [
            _evaluation("a", 0.9, experience_records=0),
            _evaluation("b", 0.5, experience_records=0),
        ]
        evs_warm = [
            _evaluation("a", 0.9, experience_records=1),
            _evaluation("b", 0.5, experience_records=1),
        ]
        assert compute_recommendation_confidence(evs_warm) > compute_recommendation_confidence(evs_cold)

    def test_depth_capped_at_five(self):
        evs = [_evaluation(f"c{i}", 0.9, experience_records=1) for i in range(8)]
        assert compute_recommendation_confidence(evs) == pytest.approx(
            0.5 * 0.0 + 0.3 * 1.0 + 0.2 * 1.0
        )

    def test_cold_start_lowers_confidence(self):
        """冷启动 → 低置信度 → 需人工确认 (§Q4 机制 5)。"""
        engine = _engine()
        result = engine.recommend(_ctx([_candidate("a", cap=0.9)]))
        assert result.confidence < LOW_CONFIDENCE_THRESHOLD
        assert result.requires_approval is True


# ------------------------------------------------------------------ 风险 (Risk)


class TestRisk:
    def test_no_evaluations_high(self):
        level, reasons, approval = assess_recommendation_risk([], 0.0, [], None)
        assert level == RiskLevel.HIGH.value
        assert approval is True

    def test_r1_close_competition_medium(self):
        evs = [_evaluation("a", 0.9, experience_records=1), _evaluation("b", 0.82, experience_records=1)]
        level, reasons, approval = assess_recommendation_risk(evs, 0.9, [], None)
        assert level == RiskLevel.MEDIUM.value
        assert any("竞争激烈" in r for r in reasons)

    def test_r1_not_triggered_when_gap_wide(self):
        evs = [_evaluation("a", 0.9, experience_records=1), _evaluation("b", 0.5, experience_records=1)]
        level, _, _ = assess_recommendation_risk(evs, 0.9, [], None)
        assert level == RiskLevel.LOW.value

    def test_r2_obvious_weakness_medium(self):
        evs = [_evaluation("a", 0.9, factors={"capability": 0.25, "performance": 0.9, "cost": 0.9, "experience": 0.5}, experience_records=1)]
        level, reasons, _ = assess_recommendation_risk(evs, 0.9, [], None)
        assert level == RiskLevel.MEDIUM.value
        assert any("明显短板" in r for r in reasons)

    def test_r3_critical_weakness_high(self):
        evs = [_evaluation("a", 0.9, factors={"capability": 0.15, "performance": 0.9, "cost": 0.9, "experience": 0.5}, experience_records=1)]
        level, reasons, approval = assess_recommendation_risk(evs, 0.9, [], None)
        assert level == RiskLevel.HIGH.value
        assert approval is True
        assert any("严重不足" in r for r in reasons)

    def test_r4_cold_start_hint_without_upgrade(self):
        """R4 冷启动: 提示人工确认但不升级等级 (无经验不惩罚, 经验非唯一依据)。"""
        evs = [_evaluation("a", 0.9, experience_records=0), _evaluation("b", 0.5, experience_records=1)]
        level, reasons, _ = assess_recommendation_risk(evs, 0.9, [], None)
        assert level == RiskLevel.LOW.value
        assert any("冷启动" in r for r in reasons)

    def test_r5_low_confidence_medium(self):
        evs = [_evaluation("a", 0.6, experience_records=0)]
        level, reasons, approval = assess_recommendation_risk(evs, 0.3, [], None)
        assert level == RiskLevel.MEDIUM.value
        assert approval is True
        assert any("置信度低" in r for r in reasons)

    def test_requires_approval_high(self):
        _, _, approval = assess_recommendation_risk(
            [_evaluation("a", 0.9, factors={"capability": 0.1, "performance": 0.9, "cost": 0.9, "experience": 0.5}, experience_records=1)],
            0.9, [], None,
        )
        assert approval is True

    def test_requires_approval_low_confidence(self):
        _, _, approval = assess_recommendation_risk(
            [_evaluation("a", 0.9, experience_records=1)],
            0.4, [], None,
        )
        assert approval is True

    def test_low_risk_no_approval(self):
        evs = [_evaluation("a", 0.9, experience_records=1), _evaluation("b", 0.5, experience_records=1)]
        level, reasons, approval = assess_recommendation_risk(evs, 0.9, [], None)
        assert level == RiskLevel.LOW.value
        assert approval is False
        assert any("未触发风险规则" in r for r in reasons)

    def test_filtered_candidates_reported_in_reasons(self):
        evs = [_evaluation("a", 0.9, experience_records=1)]
        _, reasons, _ = assess_recommendation_risk(evs, 0.9, ["weak-1", "weak-2"], None)
        assert any("2 个候选被过滤" in r for r in reasons)

    def test_risk_numeric_mapping_in_artifact(self):
        """RecommendationResult.to_artifact: risk 数值映射 (low 0.2/medium 0.5/high 0.8)。"""
        result = RecommendationResult(task_type="t", risk_level="high", risk_reasons=["x"], requires_approval=True)
        art = result.to_artifact()
        assert art.risk == 0.8
        result2 = RecommendationResult(task_type="t", risk_level="low")
        assert result2.to_artifact().risk == 0.2


# ------------------------------------------------------------------ 解释 (Explanation)


class TestExplanation:
    def test_positive_reasons(self):
        ev = score_candidate(_candidate("a", cap=0.9, perf=0.8), [], DEFAULT_WEIGHTS)
        positives = [r for r in ev.reasoning if r.direction is ReasoningDirection.POSITIVE]
        assert len(positives) >= 2
        assert all(r.text.startswith("+") for r in positives)

    def test_negative_reasons(self):
        ev = score_candidate(_candidate("a", cap=0.9, perf=0.2, cost=0.9), [], DEFAULT_WEIGHTS)
        negatives = [r for r in ev.reasoning if r.direction is ReasoningDirection.NEGATIVE]
        assert any(r.factor == "performance" for r in negatives)
        assert all(r.text.startswith("-") for r in negatives)

    def test_neutral_reasons_cold_start(self):
        ev = score_candidate(_candidate("a", cap=0.9, perf=0.5, cost=0.5), [], DEFAULT_WEIGHTS)
        neutrals = [r for r in ev.reasoning if r.direction is ReasoningDirection.NEUTRAL]
        assert any(r.factor == "experience" for r in neutrals)
        assert any(r.text.startswith("±") for r in neutrals)

    def test_reasoning_has_score_formula_item(self):
        ev = score_candidate(_candidate("a"), [], DEFAULT_WEIGHTS)
        assert any(r.factor == "score" for r in ev.reasoning)

    def test_reasoning_factor_count(self):
        """capability/performance/cost/experience + score 综合 = 5 条。"""
        ev = score_candidate(_candidate("a"), [], DEFAULT_WEIGHTS)
        assert len(ev.reasoning) == 5

    def test_reasoning_items_are_structured(self):
        ev = score_candidate(_candidate("a"), [], DEFAULT_WEIGHTS)
        for item in ev.reasoning:
            assert isinstance(item, ReasoningItem)
            assert item.factor
            assert item.direction in ReasoningDirection
            assert item.text

    def test_result_positive_reasons_helper(self):
        result = _engine().recommend(_ctx([_candidate("a", cap=0.9, perf=0.9, cost=0.9)]))
        positives = result.positive_reasons()
        assert len(positives) >= 3
        assert all(r.direction is ReasoningDirection.POSITIVE for r in positives)

    def test_result_negative_reasons_helper(self):
        result = _engine().recommend(_ctx([_candidate("a", cap=0.9, perf=0.2, cost=0.9)]))
        assert any(r.factor == "performance" for r in result.negative_reasons())

    def test_reasons_by_factor(self):
        result = _engine().recommend(_ctx([_candidate("a", cap=0.9)]))
        items = result.reasons_by_factor("capability")
        assert len(items) == 1
        assert items[0].factor == "capability"

    def test_result_reasoning_carried_from_top(self):
        result = _engine().recommend(_ctx([_candidate("a", cap=0.9)]))
        assert result.reasoning == result.evaluations[0].reasoning


# ------------------------------------------------------------------ 决策集成 (Decision Integration)


class _FakeApprovalService:
    """9c ApprovalGate duck-typed 公共接口 (request_approval → 带 .id 对象)。"""

    def __init__(self) -> None:
        self.requests: list[Any] = []

    def request_approval(self, artifact_id, gate_id=None, by=None, note=None):
        req = SimpleNamespace(
            id=f"ap-{len(self.requests) + 1}",
            artifact_id=artifact_id,
            gate_id=gate_id,
            by=by,
            note=note,
        )
        self.requests.append(req)
        return req


class TestDecisionIntegration:
    def _recommend_result(self, **engine_kw) -> tuple[RecommendationResult, RecommendationContext]:
        engine = _engine(**engine_kw)
        context = _ctx([_candidate("a", cap=0.9), _candidate("b", cap=0.6)])
        return engine.recommend(context), context

    def test_to_decision_options_snapshot(self):
        result, context = self._recommend_result()
        engine = _engine()
        decision = engine.to_decision(result, context)
        assert decision is not None
        assert len(decision.options) == 2
        ids = [o["id"] for o in decision.options]
        assert ids == ["a", "b"]

    def test_to_decision_recommendation_top(self):
        result, context = self._recommend_result()
        decision = _engine().to_decision(result, context)
        assert decision.recommendation == "a"

    def test_to_decision_derives_confidence_risk(self):
        result, context = self._recommend_result()
        decision = _engine().to_decision(result, context)
        assert decision.confidence == result.confidence
        assert decision.risk_level == result.risk_level
        assert decision.requires_approval == result.requires_approval
        assert decision.risk in (0.2, 0.5, 0.8)

    def test_to_decision_status_recommended(self):
        result, context = self._recommend_result()
        decision = _engine().to_decision(result, context)
        assert decision.status is DecisionStatus.RECOMMENDED
        assert decision.decision_type == "recommendation"

    def test_to_decision_evidence_from_top_candidate(self):
        """top 候选证据链随 Decision 产物 (证据可追溯, §Q4)。"""
        ev = make_evidence(source_id="evt-top")
        engine = _engine()
        context = _ctx(
            [_candidate("a", cap=0.9, evidence=[ev]), _candidate("b", cap=0.6)],
        )
        result = engine.recommend(context)
        decision = engine.to_decision(result, context)
        assert [e.source_id for e in decision.evidence] == ["evt-top"]

    def test_to_decision_none_without_top(self):
        """无推荐 (全部过滤) → None (宁缺毋滥, 无可决策对象)。"""
        result = _engine().recommend(_ctx(
            [_candidate("a", cap=0.4)], quality_target=0.9,
        ))
        assert result.top_candidate_id is None
        assert _engine().to_decision(result, _ctx([_candidate("a", cap=0.4)])) is None

    def test_to_decision_approval_binding_submits(self):
        """高风险推荐 + 装配 approval_service → 9c 审批请求提交 + id 回填。"""
        fake = _FakeApprovalService()
        engine = _engine(approval_service=fake)
        context = _ctx(
            [_candidate("a", cap=0.9, perf=0.1)],  # 明显短板 → high
            approval={"artifact_id": "ART-1", "gate": "prd", "by": "tester"},
        )
        result = engine.recommend(context)
        assert result.requires_approval is True
        decision = engine.to_decision(result, context)
        assert decision.approval_request_id == "ap-1"
        assert fake.requests[0].artifact_id == "ART-1"
        assert fake.requests[0].gate_id == "prd"

    def test_to_decision_no_binding_without_artifact(self):
        """高风险但无绑定点 → 不静默降级: requires_approval=true + 无请求 id。"""
        engine = _engine(approval_service=_FakeApprovalService())
        context = _ctx([_candidate("a", cap=0.9, perf=0.1)])
        result = engine.recommend(context)
        decision = engine.to_decision(result, context)
        assert decision.requires_approval is True
        assert decision.approval_request_id is None

    def test_to_decision_low_risk_no_approval_call(self):
        """低风险推荐 (经验覆盖 → 置信度足) → 不调 approval_service (零审批提交)。"""
        fake = _FakeApprovalService()
        engine = _engine(approval_service=fake, now=lambda: TS_LATE)
        rec = make_experience(score=0.9, confidence=1.0, created_at=TS_LATE)
        context = _ctx(
            [_candidate("a", cap=0.9, perf=0.9, cost=0.9), _candidate("b", cap=0.5, perf=0.5, cost=0.5)],
            historical_context={"a": [rec], "b": [rec]},
        )
        result = engine.recommend(context)
        assert result.requires_approval is False
        decision = engine.to_decision(result, context)
        assert decision.requires_approval is False
        assert fake.requests == []

    def test_to_decision_option_reasoning_flat_text(self):
        result, context = self._recommend_result()
        decision = _engine().to_decision(result, context)
        assert all(o["reasoning"] for o in decision.options)
        assert all(isinstance(r, str) for o in decision.options for r in o["reasoning"])

    def test_approval_service_error_raises(self):
        """审批服务抛错 → DecisionIntelligenceError 响亮 (不吞错, 装配方转 CLI rc 1)。"""
        from intelligence.decision import DecisionIntelligenceError

        class BrokenService:
            def request_approval(self, *args, **kwargs):
                raise RuntimeError("gate missing")

        engine = _engine(approval_service=BrokenService())
        context = _ctx(
            [_candidate("a", cap=0.9, perf=0.1)],
            approval={"artifact_id": "ART-1"},
        )
        result = engine.recommend(context)
        with pytest.raises(DecisionIntelligenceError) as exc_info:
            engine.to_decision(result, context)
        assert "approval binding failed" in str(exc_info.value)


# ------------------------------------------------------------------ 事件链 (Event Chain)


class TestEventChain:
    def test_no_store_chain(self, logger, event_store):
        engine = _engine(logger=logger)
        engine.recommend(_ctx([_candidate("a", cap=0.9), _candidate("b", cap=0.6)]))
        assert event_sequence(event_store) == [
            "intelligence.recommendation.started",
            "intelligence.recommendation.candidate.evaluated",
            "intelligence.recommendation.candidate.evaluated",
            "intelligence.recommendation.explained",
            "intelligence.recommendation.completed",
        ]

    def test_with_store_chain_includes_created(self, intelligence_dir, logger, event_store):
        from intelligence.store import RecommendationStore

        engine = _engine(RecommendationStore(intelligence_dir), logger=logger)
        engine.recommend(_ctx([_candidate("a", cap=0.9)]))
        assert event_sequence(event_store) == [
            "intelligence.recommendation.started",
            "intelligence.recommendation.candidate.evaluated",
            "intelligence.recommendation.explained",
            "intelligence.recommendation.created",
            "intelligence.recommendation.completed",
        ]

    def test_started_payload(self, logger, event_store):
        engine = _engine(logger=logger)
        engine.recommend(_ctx([_candidate("a", cap=0.9)], task_type="testing", required_capabilities=["code"]))
        payload = payload_of(event_store, "intelligence.recommendation.started")
        assert payload["task_type"] == "testing"
        assert payload["required_capabilities"] == ["code"]
        assert payload["candidate_count"] == 1

    def test_candidate_evaluated_payload(self, logger, event_store):
        engine = _engine(logger=logger)
        engine.recommend(_ctx([_candidate("a", cap=0.9)]))
        payload = payload_of(event_store, "intelligence.recommendation.candidate.evaluated")
        assert payload["candidate_id"] == "a"
        assert payload["score"] == pytest.approx(0.9 * 0.35 + 0.8 * 0.30 + 0.8 * 0.20 + 0.5 * 0.15)
        assert set(payload["factors"]) == set(RECOMMEND_FACTOR_KEYS)
        assert payload["experience_source"] == "neutral"

    def test_explained_payload_counts(self, logger, event_store):
        engine = _engine(logger=logger)
        engine.recommend(_ctx([_candidate("a", cap=0.9, perf=0.2)]))
        payload = payload_of(event_store, "intelligence.recommendation.explained")
        assert payload["top_candidate_id"] == "a"
        assert payload["positive_count"] >= 1
        assert payload["negative_count"] >= 1
        assert payload["reasoning_count"] == payload["positive_count"] + payload["negative_count"] + payload["neutral_count"]

    def test_completed_payload(self, logger, event_store):
        engine = _engine(logger=logger)
        result = engine.recommend(_ctx([_candidate("a", cap=0.9)]))
        payload = payload_of(event_store, "intelligence.recommendation.completed")
        assert payload["top_candidate_id"] == "a"
        assert payload["score"] == result.score
        assert payload["confidence"] == result.confidence
        assert payload["risk_level"] == result.risk_level
        assert payload["candidate_count"] == 1

    def test_logger_none_silent(self):
        result = _engine().recommend(_ctx([_candidate("a", cap=0.9)]))
        assert result.top_candidate_id == "a"

    def test_chain_all_filtered(self, logger, event_store):
        """全部被过滤: 链缩短为 started → completed (无候选可评/可解释)。"""
        engine = _engine(logger=logger)
        engine.recommend(_ctx([_candidate("a", cap=0.4)], quality_target=0.9))
        assert event_sequence(event_store) == [
            "intelligence.recommendation.started",
            "intelligence.recommendation.completed",
        ]

    def test_created_event_payload(self, intelligence_dir, logger, event_store):
        from intelligence.store import RecommendationStore

        engine = _engine(RecommendationStore(intelligence_dir), logger=logger)
        engine.recommend(_ctx([_candidate("a", cap=0.9, ctype="agent")]))
        payload = payload_of(event_store, "intelligence.recommendation.created")
        assert payload["target_type"] == "agent"
        assert payload["target_id"] == "a"
        assert payload["score"] > 0


# ------------------------------------------------------------------ Store 持久化 (Persistence)


class TestStorePersistence:
    def test_artifact_saved(self, intelligence_dir):
        from intelligence.store import RecommendationStore

        store = RecommendationStore(intelligence_dir)
        engine = _engine(store)
        result = engine.recommend(_ctx([_candidate("a", cap=0.9)]))
        assert store.count() == 1
        art = store.list_all()[0]
        assert art.target_id == "a"

    def test_artifact_fields(self, intelligence_dir):
        from intelligence.store import RecommendationStore

        store = RecommendationStore(intelligence_dir)
        engine = _engine(store)
        result = engine.recommend(_ctx([_candidate("a", cap=0.9, ctype="skill")]))
        art = store.list_all()[0]
        assert art.target_type == "skill"
        assert art.score == result.score
        assert art.reasoning  # 解释扁平化 (list[str])
        assert art.confidence == result.confidence
        assert art.risk in (0.2, 0.5, 0.8)

    def test_no_store_in_memory(self):
        """无 store → 不落库 (纯内存推荐)。"""
        engine = _engine()
        result = engine.recommend(_ctx([_candidate("a", cap=0.9)]))
        assert result.top_candidate_id == "a"


# ------------------------------------------------------------------ 无候选 (NoCandidates)


class TestNoCandidates:
    def test_empty_candidates_raises(self):
        with pytest.raises(NoCandidatesError):
            _engine().recommend(_ctx([]))

    def test_error_is_engine_error(self):
        assert issubclass(NoCandidatesError, RecommendationEngineError)
