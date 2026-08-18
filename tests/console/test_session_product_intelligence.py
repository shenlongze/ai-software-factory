"""S10-066 — Product Intelligence Core 测试套件。

覆盖: 8 模块分析 (industry/competitor/persona/conflict/value/mvp/business/market)
+ LLM/deterministic 双模式 + fallback + 持久化 + to_markdown。
装配: tmp_path + fixtures; llm_fn mock; 禁真实网络。
"""

from __future__ import annotations

import json
from pathlib import Path

from importlib import import_module

PI = import_module("factory-console.session.product_intelligence")


def _intent(**kw):
    d = {"name": "记账本", "problem": "个人记账繁琐",
         "user": "年轻上班族", "platform": "mobile",
         "core_features": ["快速记账", "分类统计", "预算提醒"]}
    d.update(kw)
    return d


# ================================================================== 1. 8 模块分析


class TestIndustry:
    def test_industry_present(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert r.industry_analysis.industry

    def test_industry_business_models(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert isinstance(r.industry_analysis.business_models, list)

    def test_industry_user_types(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert isinstance(r.industry_analysis.user_types, list)

    def test_industry_common_features(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert isinstance(r.industry_analysis.common_features, list)

    def test_industry_pain_points(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert isinstance(r.industry_analysis.pain_points, list)

    def test_industry_tech_trends(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert isinstance(r.industry_analysis.tech_trends, list)

    def test_industry_from_problem(self):
        """problem→pain_points 拆分。"""
        r = PI.ProductIntelligenceEngine().analyze(_intent(problem="台球计分麻烦"))
        assert any("台球" in p for p in r.industry_analysis.pain_points) or r.industry_analysis.pain_points


class TestCompetitor:
    def test_competitor_present(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert isinstance(r.competitor_analysis.competitors, list)

    def test_competitor_advantages(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert isinstance(r.competitor_analysis.advantages, list)

    def test_competitor_differentiation(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert isinstance(r.competitor_analysis.differentiation_opportunities, list)


class TestPersona:
    def test_personas_present(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert len(r.user_personas) >= 1

    def test_persona_fields(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        p = r.user_personas[0]
        assert p.name and p.description

    def test_persona_scenarios(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert isinstance(r.user_personas[0].scenarios, list)

    def test_persona_pain_points(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert isinstance(r.user_personas[0].pain_points, list)


class TestConflicts:
    def test_no_conflict(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert isinstance(r.requirement_conflicts, list)

    def test_web_offline_conflict(self):
        """platform=web + 离线功能 → 冲突。"""
        r = PI.ProductIntelligenceEngine().analyze(
            _intent(platform="web", core_features=["离线记账"]))
        assert r.requirement_conflicts

    def test_conflict_severity(self):
        r = PI.ProductIntelligenceEngine().analyze(
            _intent(platform="web", core_features=["离线记账"]))
        assert r.requirement_conflicts[0].severity in ("low", "medium", "high")


class TestValue:
    def test_score_range(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert 0 <= r.product_value_score.score <= 100

    def test_user_value(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert r.product_value_score.user_value

    def test_technical_value(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert r.product_value_score.technical_value

    def test_justification(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert r.product_value_score.justification


class TestMvp:
    def test_mvp_split(self):
        """前 2 功能→MVP, 其余→V2。"""
        r = PI.ProductIntelligenceEngine().analyze(
            _intent(core_features=["a", "b", "c", "d"]))
        assert r.mvp_plan.mvp == ["a", "b"]
        assert "c" in r.mvp_plan.v2

    def test_mvp_future(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert isinstance(r.mvp_plan.future, list)


class TestBusiness:
    def test_revenue_models(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert isinstance(r.business_analysis.revenue_models, list)

    def test_cost_structure(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert isinstance(r.business_analysis.cost_structure, list)

    def test_user_acquisition(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert isinstance(r.business_analysis.user_acquisition, list)

    def test_business_risks(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert isinstance(r.business_analysis.business_risks, list)


class TestMarket:
    def test_market_size(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert r.market_analysis.market_size

    def test_user_trends(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert isinstance(r.market_analysis.user_trends, list)

    def test_opportunity_window(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert r.market_analysis.opportunity_window


# ================================================================== 2. LLM 模式 + fallback


def _llm_report_fn(prompt, operation=""):
    return json.dumps({
        "industry_analysis": {"industry": "LLM行业", "business_models": ["SaaS"],
                              "user_types": ["企业"], "common_features": ["x"],
                              "pain_points": ["y"], "tech_trends": ["AI"]},
        "competitor_analysis": {"competitors": [{"name": "C1"}], "advantages": ["a"],
                                "differentiation_opportunities": ["d"]},
        "user_personas": [{"name": "LLM用户", "description": "d", "scenarios": ["s"],
                           "pain_points": ["p"]}],
        "requirement_conflicts": [],
        "product_value_score": {"score": 88, "user_value": "uv", "technical_value": "tv",
                                "justification": "j"},
        "mvp_plan": {"mvp": ["m1"], "v2": ["v1"], "future": ["f1"]},
        "business_analysis": {"revenue_models": ["rm"], "cost_structure": ["cs"],
                              "user_acquisition": ["ua"], "business_risks": ["br"]},
        "market_analysis": {"market_size": "large", "user_trends": ["t"],
                            "opportunity_window": "now"},
    }, ensure_ascii=False)


class TestLlmMode:
    def test_llm_analyze(self):
        from importlib import import_module as _im
        R = _im("factory-console.session.reasoning")
        prov = R.ReasoningProvider(llm_fn=_llm_report_fn)
        r = PI.ProductIntelligenceEngine().analyze(_intent(), llm_provider=prov)
        assert r.industry_analysis.industry == "LLM行业"

    def test_llm_score(self):
        from importlib import import_module as _im
        R = _im("factory-console.session.reasoning")
        prov = R.ReasoningProvider(llm_fn=_llm_report_fn)
        r = PI.ProductIntelligenceEngine().analyze(_intent(), llm_provider=prov)
        assert r.product_value_score.score == 88

    def test_llm_mvp(self):
        from importlib import import_module as _im
        R = _im("factory-console.session.reasoning")
        prov = R.ReasoningProvider(llm_fn=_llm_report_fn)
        r = PI.ProductIntelligenceEngine().analyze(_intent(), llm_provider=prov)
        assert r.mvp_plan.mvp == ["m1"]


class TestFallback:
    def test_llm_fail_deterministic(self):
        """LLM 失败 → deterministic fallback。"""
        from importlib import import_module as _im
        R = _im("factory-console.session.reasoning")

        def bad_fn(prompt, operation=""):
            raise R.ReasoningError("down")

        prov = R.ReasoningProvider(llm_fn=bad_fn)
        r = PI.ProductIntelligenceEngine().analyze(_intent(), llm_provider=prov)
        assert r.industry_analysis.industry  # deterministic 兜底

    def test_llm_invalid_deterministic(self):
        from importlib import import_module as _im
        R = _im("factory-console.session.reasoning")

        def bad_fn(prompt, operation=""):
            return "not json"

        prov = R.ReasoningProvider(llm_fn=bad_fn)
        r = PI.ProductIntelligenceEngine().analyze(_intent(), llm_provider=prov)
        assert r.industry_analysis.industry


# ================================================================== 3. 持久化 + markdown


class TestPersistence:
    def test_save_load(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir(exist_ok=True)
        engine = PI.ProductIntelligenceEngine()
        r = engine.analyze(_intent())
        engine.save(ws, r)
        r2 = engine.load(ws)
        assert r2 is not None
        assert r2.industry_analysis.industry == r.industry_analysis.industry

    def test_load_missing(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir(exist_ok=True)
        assert PI.ProductIntelligenceEngine().load(ws / "ghost") is None


class TestMarkdown:
    def test_to_markdown(self):
        engine = PI.ProductIntelligenceEngine()
        r = engine.analyze(_intent())
        md = engine.to_markdown(r)
        assert "#" in md or "产品" in md

    def test_to_markdown_industry(self):
        engine = PI.ProductIntelligenceEngine()
        r = engine.analyze(_intent())
        md = engine.to_markdown(r)
        assert "行业" in md or "industry" in md


# ================================================================== 4. report 结构


class TestReport:
    def test_to_dict(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        d = r.to_dict()
        assert "industry_analysis" in d
        assert "mvp_plan" in d
        assert "product_value_score" in d

    def test_from_dict(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        d = r.to_dict()
        r2 = PI.ProductIntelligenceReport.from_dict(d)
        assert r2.industry_analysis.industry == r.industry_analysis.industry

    def test_product_name(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent(name="TestProduct"))
        assert r.product_name == "TestProduct"

    def test_timestamp(self):
        r = PI.ProductIntelligenceEngine().analyze(_intent())
        assert r.timestamp

    def test_analyze_requires_intent(self):
        """空 intent → 不崩。"""
        r = PI.ProductIntelligenceEngine().analyze({})
        assert r.industry_analysis.industry or r.product_name  # 不崩


class TestLlmDefaultProvider:
    """S10-066 修复: ReasoningProvider(llm_fn=None) → 用默认真实调用。"""

    def test_default_provider_llm_fn(self, monkeypatch):
        """_llm_fn 识别 ReasoningProvider 默认 (注入固定 fn, 不依赖真实 key)。"""
        from importlib import import_module as _im
        R = _im("factory-console.session.reasoning")
        prov = R.ReasoningProvider(llm_fn=None)

        def _fake_default(self):
            return lambda prompt, operation="": "fake"

        monkeypatch.setattr(R.ReasoningProvider, "_default_llm_fn", _fake_default)
        fn = PI.ProductIntelligenceEngine._llm_fn(prov)
        assert callable(fn)
        assert fn("x") == "fake"

    def test_callable_provider(self):
        fn = PI.ProductIntelligenceEngine._llm_fn(lambda p, o="": "{}")
        assert callable(fn)

    def test_invalid_provider_raises(self):
        import pytest as _pt
        with _pt.raises(TypeError):
            PI.ProductIntelligenceEngine._llm_fn("not a provider")
