"""tests/intelligence/test_intelligence_decision.py — DecisionIntelligence 引擎
(Phase 10A-2, ADR-0031): Context→Analysis→Options→Evaluation→Recommendation→
Risk→Decision Artifact。

覆盖 (任务要求 ≥80 中的引擎部分):
- DecisionContext 校验/默认值/approval 绑定点
- Option evaluation + Score calculation (四因素加权归一 + 中性分 + 权重归一)
- Reason generation (逐条解释, 可审计)
- Evidence chain (禁无证据 — context/option 双层)
- Confidence (分数差距/证据覆盖/因素完整度 + 分析先验)
- Risk detection (R1 决策类型 / R2 选项风险 / R3 约束关键词 / R4 竞争激烈 /
  R5 低置信度; requires_approval 派生)
- Approval binding (9c ApprovalGate 复用 — duck-typed 公共接口)
- Event sequence (4 链序: analysis.started → completed → option.evaluated×N →
  decision.created)
- Store persistence (decide 落库可见)

本文件 basename 全仓库唯一 (test_intelligence_* 前缀, conftest 注释约定)。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from intelligence.decision import (
    DEFAULT_FACTOR_WEIGHTS,
    LOW_CONFIDENCE_THRESHOLD,
    NEUTRAL_FACTOR,
    DecisionIntelligence,
    DecisionIntelligenceError,
    NoEvidenceError,
    compute_confidence,
    normalize_weights,
    score_option,
)
from intelligence.models import (
    ApprovalBinding,
    Decision,
    DecisionContext,
    DecisionOption,
    DecisionStatus,
    RiskAssessment,
    RiskLevel,
)

from intelligence_helpers import make_evidence

# ---------------------------------------------------------------- 工厂 helper


def _option(
    oid: str,
    *,
    factors: dict[str, float] | None = None,
    score: float = 0.0,
    risks: list[str] | None = None,
    evidence: list | None = None,
) -> DecisionOption:
    return DecisionOption(
        id=oid,
        name=oid.upper(),
        score=score,
        factors=factors or {},
        risks=risks or [],
        evidence=evidence or [],
    )


def _ctx(**kw) -> DecisionContext:
    """决策上下文工厂 (固定确定性输入)。"""
    base = dict(
        subject="task-1",
        decision_type="general",
        objective="choose the best option",
        constraints=[],
        available_options=[
            _option("a", factors={"capability": 0.9, "cost": 0.7, "performance": 0.8, "experience": 0.6}),
            _option("b", factors={"capability": 0.5, "cost": 0.9, "performance": 0.6, "experience": 0.7}),
        ],
        evidence_sources=[make_evidence()],
    )
    base.update(kw)
    return DecisionContext(**base)


def _engine(**kw) -> DecisionIntelligence:
    return DecisionIntelligence(**kw)


# ---------------------------------------------------------- 四因素评分 (Score)


class TestNormalizeWeights:
    def test_default_weights_normalized(self):
        w = normalize_weights(DEFAULT_FACTOR_WEIGHTS)
        assert sum(w.values()) == pytest.approx(1.0)
        assert w["capability"] == pytest.approx(0.40)

    def test_partial_weights_fill_zero_then_normalize(self):
        w = normalize_weights({"capability": 0.4, "cost": 0.4})
        assert w == pytest.approx(
            {"capability": 0.5, "cost": 0.5, "performance": 0.0, "experience": 0.0}
        )

    def test_unknown_factor_key_raises(self):
        with pytest.raises(ValueError, match="unknown factor"):
            normalize_weights({"capability": 1.0, "magic": 1.0})

    def test_negative_weight_raises(self):
        with pytest.raises(ValueError, match=">= 0"):
            normalize_weights({"capability": -0.1})

    def test_zero_sum_raises(self):
        with pytest.raises(ValueError, match="sum to > 0"):
            normalize_weights({"capability": 0.0, "cost": 0.0})


class TestScoreOption:
    def test_four_factor_weighted_sum(self):
        """0.9×0.40 + 0.7×0.25 + 0.8×0.20 + 0.6×0.15 = 0.785 → 0.785。"""
        opt = _option("a", factors={"capability": 0.9, "cost": 0.7, "performance": 0.8, "experience": 0.6})
        scored = score_option(opt)
        assert scored.score == pytest.approx(0.785, abs=1e-3)
        assert scored.score == 0.785  # round(…, 3) 精确

    def test_missing_factor_uses_neutral(self):
        """capability 1.0 其余缺失 → 中性分 0.5: 0.4 + 0.125+0.1+0.075 = 0.7。"""
        opt = _option("a", factors={"capability": 1.0})
        assert score_option(opt).score == pytest.approx(0.7, abs=1e-3)

    def test_custom_weights_override(self):
        opt = _option("a", factors={"capability": 1.0, "cost": 0.0, "performance": 0.0, "experience": 0.0})
        scored = score_option(opt, weights={"capability": 1.0})
        assert scored.score == pytest.approx(1.0, abs=1e-3)

    def test_score_clamped_to_unit_interval(self):
        opt = _option("a", factors={"capability": 1.0, "cost": 1.0, "performance": 1.0, "experience": 1.0})
        assert score_option(opt).score == 1.0

    def test_no_factors_uses_context_score(self):
        opt = _option("a", score=0.62)
        scored = score_option(opt)
        assert scored.score == 0.62
        assert any("未做规则加权" in line for line in scored.reasoning)

    def test_model_copy_semantics(self):
        opt = _option("a", factors={"capability": 0.9, "cost": 0.7, "performance": 0.8, "experience": 0.6})
        scored = score_option(opt)
        assert scored is not opt
        assert opt.score == 0.0  # 原对象不更新 (model_copy 语义)


class TestReasonGeneration:
    def test_reasoning_has_per_factor_lines(self):
        opt = _option("a", factors={"capability": 0.9, "cost": 0.7, "performance": 0.8, "experience": 0.6})
        scored = score_option(opt)
        assert len(scored.reasoning) == 6  # 4 因素 + 最高贡献 + 公式
        assert any(line.startswith("capability ") for line in scored.reasoning)
        assert any(line.startswith("cost ") for line in scored.reasoning)

    def test_reasoning_identifies_top_contributor(self):
        """capability 贡献最大 (0.9×0.4=0.36 > cost 0.175)。"""
        opt = _option("a", factors={"capability": 0.9, "cost": 0.7, "performance": 0.8, "experience": 0.6})
        scored = score_option(opt)
        top = [line for line in scored.reasoning if line.startswith("最高贡献因素")][0]
        assert "capability" in top

    def test_reasoning_includes_formula(self):
        opt = _option("a", factors={"capability": 0.9, "cost": 0.7, "performance": 0.8, "experience": 0.6})
        scored = score_option(opt)
        assert any("综合评分" in line and "0.785" in line for line in scored.reasoning)

    def test_reasoning_weight_lines_show_contribution(self):
        opt = _option("a", factors={"capability": 0.9, "cost": 0.7, "performance": 0.8, "experience": 0.6})
        scored = score_option(opt)
        cap = [line for line in scored.reasoning if line.startswith("capability ")][0]
        assert "0.360" in cap  # 0.9×0.40 贡献


# ---------------------------------------------------------------- Confidence


class TestComputeConfidence:
    def test_empty_options_zero(self):
        assert compute_confidence([]) == 0.0

    def test_spread_drives_confidence(self):
        opts = [
            _option("a", score=0.9, evidence=[make_evidence()]),
            _option("b", score=0.3, evidence=[make_evidence()]),
        ]
        # spread=0.6 coverage=1.0 completeness=0 → 0.5×0.6+0.3×1.0+0 = 0.6
        assert compute_confidence(opts) == pytest.approx(0.6)

    def test_single_option_uses_own_score_as_spread(self):
        opt = [_option("a", score=0.8, evidence=[make_evidence()])]
        # spread=0.8 coverage=1.0 completeness=0 → 0.5×0.8+0.3 = 0.7
        assert compute_confidence(opt) == pytest.approx(0.7)

    def test_evidence_coverage_component(self):
        opts = [
            _option("a", score=0.9, evidence=[make_evidence()]),
            _option("b", score=0.5),  # 无证据
        ]
        # spread=0.4 coverage=0.5 completeness=0 → 0.2+0.15 = 0.35
        assert compute_confidence(opts) == pytest.approx(0.35)

    def test_factor_completeness_component(self):
        opts = [
            _option("a", score=0.9, factors={"capability": 0.9, "cost": 0.7, "performance": 0.8, "experience": 0.6},
                    evidence=[make_evidence()]),
            _option("b", score=0.6, evidence=[make_evidence()]),
        ]
        # spread=0.3 coverage=1.0 completeness=(4+0)/8=0.5
        # → 0.5×0.3 + 0.3×1.0 + 0.2×0.5 = 0.15+0.3+0.1 = 0.55
        assert compute_confidence(opts) == pytest.approx(0.55)

    def test_analysis_prior_mixed_in(self):
        from intelligence.models import DecisionAnalysis

        opts = [
            _option("a", score=0.9, evidence=[make_evidence()]),
            _option("b", score=0.3, evidence=[make_evidence()]),
        ]
        analysis = DecisionAnalysis(confidence=1.0, evidence=[make_evidence()])
        # 0.8×0.6 + 0.2×1.0 = 0.68
        assert compute_confidence(opts, analysis) == pytest.approx(0.68)

    def test_never_exceeds_one(self):
        opts = [_option("a", score=1.0, evidence=[make_evidence()])]
        assert compute_confidence(opts) <= 1.0


# ---------------------------------------------------------------- Analysis


class TestAnalyze:
    def test_no_evidence_raises(self, logger):
        engine = _engine(logger=logger)
        with pytest.raises(NoEvidenceError, match="evidence"):
            engine.analyze(_ctx(evidence_sources=[]))

    def test_observations_include_context(self):
        engine = _engine()
        analysis = engine.analyze(_ctx(constraints=["must be cheap"]))
        text = "\n".join(analysis.observations)
        assert "决策类型: general" in text
        assert "目标: choose the best option" in text
        assert "约束: must be cheap" in text
        assert "候选选项: 2" in text

    def test_factor_aggregate_is_option_mean(self):
        """capability 均值 = (0.9+0.5)/2 = 0.7。"""
        engine = _engine()
        analysis = engine.analyze(_ctx())
        assert analysis.factors["capability"] == pytest.approx(0.7)
        assert analysis.factors["cost"] == pytest.approx(0.8)

    def test_no_options_uses_neutral_factors(self):
        engine = _engine()
        analysis = engine.analyze(_ctx(available_options=[]))
        assert all(v == NEUTRAL_FACTOR for v in analysis.factors.values())

    def test_analysis_confidence_scales_with_evidence(self):
        engine = _engine()
        a1 = engine.analyze(_ctx(evidence_sources=[make_evidence()]))
        a4 = engine.analyze(
            _ctx(evidence_sources=[make_evidence(f"e{i}") for i in range(4)])
        )
        assert a1.confidence == pytest.approx(0.55)  # 0.4 + 0.15×1
        assert a4.confidence == 1.0  # 0.4 + 0.15×4 = 1.0 (封顶)

    def test_analysis_emits_started_then_completed(self, logger, event_store):
        engine = _engine(logger=logger)
        engine.analyze(_ctx())
        types = [e.type.value for e in event_store.query()]
        assert types == [
            "intelligence.decision.analysis.started",
            "intelligence.decision.analysis.completed",
        ]


# ------------------------------------------------------------- Evaluation


class TestEvaluateOptions:
    def test_no_options_raises(self):
        engine = _engine()
        with pytest.raises(DecisionIntelligenceError, match="no available options"):
            engine.evaluate_options(_ctx(available_options=[]))

    def test_scores_filled_for_all_options(self):
        engine = _engine()
        scored = engine.evaluate_options(_ctx())
        assert len(scored) == 2
        assert all(o.score > 0 for o in scored)
        assert all(o.reasoning for o in scored)

    def test_option_inherits_context_evidence_by_default(self):
        engine = _engine()
        scored = engine.evaluate_options(_ctx())
        assert all(o.evidence for o in scored)
        assert scored[0].evidence[0].lineage_ref() == "event:evt-1"

    def test_inherit_disabled_without_option_evidence_raises(self):
        engine = _engine(inherit_context_evidence=False)
        with pytest.raises(NoEvidenceError, match="no evidence"):
            engine.evaluate_options(_ctx())

    def test_own_evidence_overrides_inheritance(self):
        own = make_evidence(source_id="opt-ev", source_type="artifact")
        engine = _engine(inherit_context_evidence=False)
        ctx = _ctx(available_options=[_option("a", factors={"capability": 0.9, "cost": 0.7, "performance": 0.8, "experience": 0.6}, evidence=[own])])
        scored = engine.evaluate_options(ctx)
        assert scored[0].evidence[0].lineage_ref() == "artifact:opt-ev"

    def test_option_evaluated_event_per_option(self, logger, event_store):
        engine = _engine(logger=logger)
        engine.evaluate_options(_ctx())
        ev = [e for e in event_store.query() if e.type.value == "intelligence.decision.option.evaluated"]
        assert len(ev) == 2
        assert {e.payload["option_id"] for e in ev} == {"a", "b"}
        assert all(e.payload["score"] > 0 for e in ev)

    def test_evaluated_event_payload_shape(self, logger, event_store):
        engine = _engine(logger=logger)
        engine.evaluate_options(_ctx())
        ev = [e for e in event_store.query() if e.type.value == "intelligence.decision.option.evaluated"][0]
        assert ev.payload["subject_id"] == "task-1"
        assert "reasoning_count" in ev.payload
        assert "evidence_count" in ev.payload


# ---------------------------------------------------------- Recommendation


class TestRecommend:
    def test_top_score_recommended_with_alternatives(self):
        engine = _engine()
        ctx = _ctx()
        analysis = engine.analyze(ctx)
        options = engine.evaluate_options(ctx, analysis)
        rec, alts = engine.recommend(ctx, analysis, options)
        assert rec == "a"  # alpha 0.785 > beta
        assert alts == ["b"]

    def test_tie_prefers_context_order(self):
        engine = _engine()
        ctx = _ctx(
            available_options=[
                _option("x", score=0.5, evidence=[make_evidence()]),
                _option("y", score=0.5, evidence=[make_evidence()]),
            ]
        )
        analysis = engine.analyze(ctx)
        options = engine.evaluate_options(ctx, analysis)
        rec, alts = engine.recommend(ctx, analysis, options)
        assert rec == "x"  # 稳定排序: 同分取 context 顺序先者

    def test_no_options_raises(self):
        engine = _engine()
        from intelligence.models import DecisionAnalysis

        with pytest.raises(DecisionIntelligenceError, match="no options evaluated"):
            engine.recommend(_ctx(), DecisionAnalysis(), [])


# ------------------------------------------------------------- Risk 检测


class TestAssessRisk:
    def test_high_risk_decision_type(self):
        """R1: provider_selection 属高风险类 → high + requires_approval。"""
        engine = _engine()
        ctx = _ctx(decision_type="provider_selection")
        risk = engine.assess_risk(ctx, engine.analyze(ctx), [], "a")
        assert risk.risk_level == RiskLevel.HIGH.value
        assert risk.requires_approval is True
        assert any("provider_selection" in t for t in risk.rules_triggered)

    def test_low_risk_general_type(self):
        """general 类型 + 明确分差 + 足量证据 → low, 无审批需求。"""
        engine = _engine()
        ctx = _ctx(
            decision_type="general",
            available_options=[
                _option("a", score=0.9, evidence=[make_evidence()]),
                _option("b", score=0.3, evidence=[make_evidence()]),
            ],
        )
        analysis = engine.analyze(ctx)
        options = engine.evaluate_options(ctx, analysis)
        risk = engine.assess_risk(ctx, analysis, options, "a")
        assert risk.risk_level == RiskLevel.LOW.value
        assert risk.requires_approval is False

    def test_option_risk_keyword_triggers_high(self):
        """R2: 选项 risks 文本含 cost increase → high。"""
        engine = _engine()
        ctx = _ctx(
            decision_type="general",
            available_options=[_option("a", risks=["cost increase risk"], evidence=[make_evidence()])],
        )
        risk = engine.assess_risk(ctx, engine.analyze(ctx), [ctx.available_options[0]], "a")
        assert risk.risk_level == RiskLevel.HIGH.value
        assert any("option:a" in t for t in risk.rules_triggered)

    def test_constraint_keyword_triggers_high(self):
        """R3: 约束文本含 migration → high。"""
        engine = _engine()
        ctx = _ctx(decision_type="general", constraints=["no migration allowed"])
        risk = engine.assess_risk(ctx, engine.analyze(ctx), [], "a")
        assert risk.risk_level == RiskLevel.HIGH.value

    def test_close_competition_medium(self):
        """R4: top−runner-up < 0.1 → medium (需人工确认); 置信度足 → 不强制审批。

        选项用四因素 (completeness=1.0) + 证据 (coverage=1.0):
        confidence = 0.5×0.096 + 0.3×1.0 + 0.2×1.0 = 0.548 ≥ 0.5 → 不触发 R5。
        """
        engine = _engine()
        ctx = _ctx(
            decision_type="general",
            available_options=[
                _option("a", factors={"capability": 0.74, "cost": 0.6, "performance": 0.6, "experience": 0.6},
                        evidence=[make_evidence()]),
                _option("b", factors={"capability": 0.5, "cost": 0.6, "performance": 0.6, "experience": 0.6},
                        evidence=[make_evidence()]),
            ],
        )
        analysis = engine.analyze(ctx)
        options = engine.evaluate_options(ctx, analysis)
        assert options[0].score - options[1].score == pytest.approx(0.096, abs=1e-3)
        risk = engine.assess_risk(ctx, analysis, options, "a")
        assert risk.risk_level == RiskLevel.MEDIUM.value
        assert risk.requires_approval is False  # medium 不强制审批
        assert any("分差小" in r for r in risk.reasons)

    def test_low_confidence_medium_and_requires_approval(self):
        """R5: 置信度 < 0.5 → medium + requires_approval (需人工确认)。"""
        engine = _engine()
        ctx = _ctx(
            decision_type="general",
            available_options=[_option("a", score=0.3, evidence=[make_evidence()])],
        )
        analysis = engine.analyze(ctx)
        options = engine.evaluate_options(ctx, analysis)
        risk = engine.assess_risk(ctx, analysis, options, "a")
        assert risk.risk_level == RiskLevel.MEDIUM.value
        assert risk.requires_approval is True  # 低置信度 → 需人工

    def test_risk_reasons_populated(self):
        engine = _engine()
        ctx = _ctx(decision_type="provider_selection")
        analysis = engine.analyze(ctx)
        options = engine.evaluate_options(ctx, analysis)
        risk = engine.assess_risk(ctx, analysis, options, "a")
        assert isinstance(risk, RiskAssessment)
        assert risk.reasons
        assert any("高风险" in r for r in risk.reasons)

    def test_gap_at_or_above_threshold_is_low(self):
        """R4 边界: gap ≥ 0.1 (严格小于才 medium) → low。

        0.72 − 0.52 = 0.2 > 0.1; confidence = 0.5×0.2+0.3×1.0+0.2×1.0 = 0.6 ≥ 0.5。
        """
        engine = _engine()
        ctx = _ctx(
            decision_type="general",
            available_options=[
                _option("a", factors={"capability": 0.9, "cost": 0.6, "performance": 0.6, "experience": 0.6},
                        evidence=[make_evidence()]),
                _option("b", factors={"capability": 0.4, "cost": 0.6, "performance": 0.6, "experience": 0.6},
                        evidence=[make_evidence()]),
            ],
        )
        analysis = engine.analyze(ctx)
        options = engine.evaluate_options(ctx, analysis)
        risk = engine.assess_risk(ctx, analysis, options, "a")
        assert risk.risk_level == RiskLevel.LOW.value


# ----------------------------------------------------------- Decision 构建


class TestBuildDecision:
    def test_evidence_deduped_by_lineage(self):
        engine = _engine()
        shared = make_evidence()
        ctx = _ctx(
            available_options=[
                _option("a", factors={"capability": 0.9, "cost": 0.7, "performance": 0.8, "experience": 0.6},
                        evidence=[shared]),
            ]
        )
        analysis = engine.analyze(ctx)
        options = engine.evaluate_options(ctx, analysis)
        rec, alts = engine.recommend(ctx, analysis, options)
        risk = engine.assess_risk(ctx, analysis, options, rec)
        d = engine.build_decision(ctx, analysis, options, rec, alts, risk)
        refs = [e.lineage_ref() for e in d.evidence]
        assert refs.count("event:evt-1") == 1  # context ∪ 选项去重

    def test_risk_numeric_mapping(self):
        engine = _engine()
        ctx = _ctx(decision_type="provider_selection")
        analysis = engine.analyze(ctx)
        risk = engine.assess_risk(ctx, analysis, [], "a")
        d = engine.build_decision(ctx, analysis, [], "a", [], risk)
        assert d.risk == pytest.approx(0.8)  # high → 0.8
        assert d.risk_level == "high"

    def test_status_recommended(self):
        engine = _engine()
        ctx = _ctx()
        analysis = engine.analyze(ctx)
        options = engine.evaluate_options(ctx, analysis)
        rec, alts = engine.recommend(ctx, analysis, options)
        risk = engine.assess_risk(ctx, analysis, options, rec)
        d = engine.build_decision(ctx, analysis, options, rec, alts, risk)
        assert d.status == DecisionStatus.RECOMMENDED
        assert d.recommendation == "a"
        assert d.analysis is not None  # 分析快照入 Decision (全链可审计)

    def test_decision_carries_options_full_chain(self):
        engine = _engine()
        ctx = _ctx()
        analysis = engine.analyze(ctx)
        options = engine.evaluate_options(ctx, analysis)
        rec, alts = engine.recommend(ctx, analysis, options)
        risk = engine.assess_risk(ctx, analysis, options, rec)
        d = engine.build_decision(ctx, analysis, options, rec, alts, risk)
        assert len(d.options) == 2
        assert all(o["score"] > 0 and o["reasoning"] for o in d.options)


# ------------------------------------------------------ Approval 绑定 (9c 复用)


class _FakeApprovalService:
    """9c ApprovalGate 公共接口替身 (request_approval 签名同 ProductService)。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.request_id = "APR-TEST-001"

    def request_approval(self, artifact_id, gate_id=None, *, by, note):
        self.calls.append(
            dict(artifact_id=artifact_id, gate_id=gate_id, by=by, note=note)
        )
        return SimpleNamespace(id=self.request_id)


def _low_risk_ctx() -> DecisionContext:
    return _ctx(decision_type="general")


class TestBindApproval:
    def test_no_approval_needed_returns_unchanged(self):
        engine = _engine(approval_service=_FakeApprovalService())
        d = Decision(subject_id="t1")
        out = engine.bind_approval(d, _low_risk_ctx(), RiskAssessment())
        assert out is d
        assert out.approval_request_id is None

    def test_high_risk_without_service_marks_only(self):
        """装配缺失 → 不静默降级: requires_approval=true + approval_request_id=None。"""
        engine = _engine(approval_service=None)
        d = Decision(subject_id="t1", requires_approval=True)
        risk = RiskAssessment(risk_level="high", requires_approval=True)
        ctx = _ctx(decision_type="provider_selection")
        out = engine.bind_approval(d, ctx, risk)
        assert out.requires_approval is True
        assert out.approval_request_id is None

    def test_high_risk_without_binding_marks_only(self):
        engine = _engine(approval_service=_FakeApprovalService())
        d = Decision(subject_id="t1", requires_approval=True)
        risk = RiskAssessment(risk_level="high", requires_approval=True)
        ctx = _ctx(decision_type="provider_selection", approval=None)
        out = engine.bind_approval(d, ctx, risk)
        assert out.approval_request_id is None

    def test_binding_success_calls_9c_gate(self):
        svc = _FakeApprovalService()
        engine = _engine(approval_service=svc)
        d = Decision(subject_id="t1", requires_approval=True)
        risk = RiskAssessment(risk_level="high", requires_approval=True)
        ctx = _ctx(
            decision_type="provider_selection",
            approval=ApprovalBinding(artifact_id="ART-1", gate="prd", by="cli"),
        )
        out = engine.bind_approval(d, ctx, risk)
        assert svc.calls == [
            dict(artifact_id="ART-1", gate_id="prd", by="cli",
                 note=f"intelligence decision {d.id}")
        ]
        assert out.approval_request_id == "APR-TEST-001"
        assert out is not d  # model_copy 语义

    def test_binding_error_surfaced(self):
        class _Boom:
            def request_approval(self, *a, **kw):
                raise RuntimeError("gate missing")

        engine = _engine(approval_service=_Boom())
        d = Decision(subject_id="t1", requires_approval=True)
        risk = RiskAssessment(risk_level="high", requires_approval=True)
        ctx = _ctx(
            decision_type="provider_selection",
            approval=ApprovalBinding(artifact_id="ART-1"),
        )
        with pytest.raises(DecisionIntelligenceError, match="approval binding failed"):
            engine.bind_approval(d, ctx, risk)

    def test_binding_note_uses_context_note(self):
        svc = _FakeApprovalService()
        engine = _engine(approval_service=svc)
        d = Decision(subject_id="t1", requires_approval=True)
        risk = RiskAssessment(risk_level="high", requires_approval=True)
        ctx = _ctx(
            decision_type="provider_selection",
            approval=ApprovalBinding(artifact_id="ART-1", note="manual note"),
        )
        out = engine.bind_approval(d, ctx, risk)
        assert svc.calls[0]["note"] == "manual note"


# ------------------------------------------------------------ decide 全链


class TestDecideChain:
    def test_event_chain_order(self, logger, event_store):
        """4 链序: started → completed → option.evaluated×2 → decision.created (链终)。"""
        engine = _engine(logger=logger)
        engine.decide(_ctx())
        types = [e.type.value for e in event_store.query()]
        assert types == [
            "intelligence.decision.analysis.started",
            "intelligence.decision.analysis.completed",
            "intelligence.decision.option.evaluated",
            "intelligence.decision.option.evaluated",
            "intelligence.decision.created",
        ]

    def test_created_event_last_with_full_payload(self, logger, event_store):
        engine = _engine(logger=logger)
        engine.decide(_ctx())
        created = [e for e in event_store.query() if e.type.value == "intelligence.decision.created"]
        assert len(created) == 1
        p = created[0].payload
        assert p["decision_type"] == "general"
        assert p["subject_id"] == "task-1"
        assert p["recommendation"] == "a"
        assert p["evidence_count"] >= 1
        assert p["risk_level"] in ("low", "medium", "high")
        assert "approval_request_id" in p

    def test_decide_persists_to_store(self, decision_store, logger):
        engine = _engine(decision_store=decision_store, logger=logger)
        d = engine.decide(_ctx())
        loaded = decision_store.get(d.id)
        assert loaded is not None
        assert loaded.recommendation == "a"
        assert loaded.status == DecisionStatus.RECOMMENDED
        assert decision_store.count() == 1

    def test_decide_with_approval_binding(self, decision_store, logger):
        svc = _FakeApprovalService()
        engine = _engine(decision_store=decision_store, logger=logger, approval_service=svc)
        ctx = _ctx(
            decision_type="provider_selection",  # R1 高风险
            approval=ApprovalBinding(artifact_id="ART-1", gate="prd"),
        )
        d = engine.decide(ctx)
        assert d.requires_approval is True
        assert d.approval_request_id == "APR-TEST-001"
        assert svc.calls  # 9c 审批服务被调用
        # 落库版本同样带审批绑定 (引擎落库的是返回值)
        assert decision_store.get(d.id).approval_request_id == "APR-TEST-001"

    def test_low_risk_decision_skips_approval(self, decision_store, logger):
        svc = _FakeApprovalService()
        engine = _engine(decision_store=decision_store, logger=logger, approval_service=svc)
        d = engine.decide(_low_risk_ctx())
        assert d.requires_approval is False
        assert d.approval_request_id is None
        assert svc.calls == []

    def test_result_derivation(self):
        engine = _engine()
        d = engine.decide(_ctx())
        res = engine.result(d)
        assert res.decision_id == d.id
        assert res.recommendation == "a"
        assert res.alternatives == ["b"]
        assert res.confidence == d.confidence
        assert res.risk_level == d.risk_level
        assert res.requires_approval == d.requires_approval

    def test_no_evidence_decision_rejected(self):
        """禁无证据: 全链入口无证据 → NoEvidenceError, 零事件。"""
        engine = _engine()
        with pytest.raises(NoEvidenceError):
            engine.decide(_ctx(evidence_sources=[]))

    def test_no_evidence_no_events_emitted(self, logger, event_store):
        engine = _engine(logger=logger)
        with pytest.raises(NoEvidenceError):
            engine.decide(_ctx(evidence_sources=[]))
        assert event_store.query() == []


# ------------------------------------------------------- DecisionContext 校验


class TestDecisionContextValidation:
    def test_defaults(self):
        ctx = DecisionContext(subject="t1", evidence_sources=[make_evidence()])
        assert ctx.decision_type == "general"
        assert ctx.constraints == []
        assert ctx.available_options == []
        assert ctx.approval is None

    def test_none_lists_default_empty(self):
        ctx = DecisionContext(
            subject="t1",
            evidence_sources=[make_evidence()],
            available_options=None,
            constraints=None,
        )
        assert ctx.available_options == []
        assert ctx.constraints == []

    def test_option_dicts_coerced(self):
        ctx = DecisionContext(
            subject="t1",
            evidence_sources=[make_evidence()],
            available_options=[{"id": "a", "name": "A"}],
        )
        assert isinstance(ctx.available_options[0], DecisionOption)
        assert ctx.available_options[0].name == "A"

    def test_evidence_dicts_coerced(self):
        ctx = DecisionContext(
            subject="t1",
            evidence_sources=[{"source_type": "event", "source_id": "e1"}],
        )
        assert ctx.evidence_sources[0].lineage_ref() == "event:e1"

    def test_approval_binding_dict_coerced(self):
        ctx = DecisionContext(
            subject="t1",
            evidence_sources=[make_evidence()],
            approval={"artifact_id": "ART-9", "gate": "prd"},
        )
        assert isinstance(ctx.approval, ApprovalBinding)
        assert ctx.approval.gate == "prd"
        assert ctx.approval.by == "intelligence"  # 缺省申请人

    def test_option_factor_out_of_range_rejected(self):
        with pytest.raises(Exception):
            _option("a", factors={"capability": 1.5})


class TestEngineAssembly:
    def test_store_none_is_memory_only(self, logger):
        """无 store → 不持久化, 事件照发。"""
        engine = _engine(decision_store=None, logger=logger)
        d = engine.decide(_ctx())
        assert d.id  # 正常产出

    def test_custom_factor_weights_normalized_at_build(self):
        engine = _engine(factor_weights={"capability": 1.0})
        assert engine._weights["capability"] == 1.0
        assert engine._weights["cost"] == 0.0

    def test_unknown_weight_key_raises_at_build(self):
        with pytest.raises(ValueError, match="unknown factor"):
            _engine(factor_weights={"capability": 1.0, "nope": 0.5})

    def test_injectable_now_clock(self):
        engine = _engine(now=lambda: "2026-08-06T00:00:00.000000Z")
        assert engine._now() == "2026-08-06T00:00:00.000000Z"
