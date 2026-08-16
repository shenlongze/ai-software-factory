"""S10-066 — Product Intelligence API 测试套件。

覆盖: 3 端点路由函数 (intelligence/analyze + market-analysis + persona)
+ request/response schema + error handling + 注册。
装配: 禁真实网络。
"""

from __future__ import annotations

import pytest

from importlib import import_module

API = import_module("factory-console.api.product_intelligence")
API_INIT = import_module("factory-console.api")


def _intent():
    return {"name": "台球计分", "problem": "台球计分麻烦",
            "user": "台球爱好者", "platform": "mobile",
            "core_features": ["计分", "排行榜"]}


class TestAnalyzeEndpoint:
    def test_ok(self):
        res = API.product_intelligence_analyze(_intent())
        assert res.get("ok") is True
        assert "data" in res

    def test_data_has_industry(self):
        res = API.product_intelligence_analyze(_intent())
        assert "industry" in res["data"]["industry_analysis"]

    def test_data_has_mvp(self):
        res = API.product_intelligence_analyze(_intent())
        assert "mvp" in res["data"]["mvp_plan"]

    def test_data_has_value(self):
        res = API.product_intelligence_analyze(_intent())
        assert "score" in res["data"]["product_value_score"]

    def test_data_has_market(self):
        res = API.product_intelligence_analyze(_intent())
        assert "market_size" in res["data"]["market_analysis"]

    def test_data_has_personas(self):
        res = API.product_intelligence_analyze(_intent())
        assert isinstance(res["data"]["user_personas"], list)

    def test_data_has_competitors(self):
        res = API.product_intelligence_analyze(_intent())
        assert "competitors" in res["data"]["competitor_analysis"]

    def test_data_has_conflicts(self):
        res = API.product_intelligence_analyze(_intent())
        assert isinstance(res["data"]["requirement_conflicts"], list)

    def test_data_has_business(self):
        res = API.product_intelligence_analyze(_intent())
        assert "revenue_models" in res["data"]["business_analysis"]

    def test_none_input_fail_safe(self):
        """None 输入 → 失败安全 (engine 兜底, 不裸抛)。"""
        res = API.product_intelligence_analyze(None)
        assert "data" in res  # 兜底报告


class TestMarketEndpoint:
    def test_ok(self):
        res = API.product_market_analysis(_intent())
        assert res.get("ok") is True

    def test_market_size(self):
        res = API.product_market_analysis(_intent())
        assert res["data"]["market_size"]

    def test_user_trends(self):
        res = API.product_market_analysis(_intent())
        assert isinstance(res["data"]["user_trends"], list)

    def test_opportunity(self):
        res = API.product_market_analysis(_intent())
        assert res["data"]["opportunity_window"]

    def test_none_fail_safe(self):
        res = API.product_market_analysis(None)
        assert "data" in res


class TestPersonaEndpoint:
    def test_ok(self):
        res = API.product_persona(_intent())
        assert res.get("ok") is True

    def test_personas(self):
        res = API.product_persona(_intent())
        assert len(res["data"]) >= 1

    def test_persona_fields(self):
        res = API.product_persona(_intent())
        p = res["data"][0]
        assert p["name"] and p["description"]

    def test_none_fail_safe(self):
        res = API.product_persona(None)
        assert "data" in res


class TestRegistration:
    def test_registered(self):
        assert hasattr(API_INIT, "product_intelligence_analyze") or \
            "product_intelligence_analyze" in getattr(API_INIT, "__all__", [])

    def test_market_registered(self):
        assert hasattr(API_INIT, "product_market_analysis") or \
            "product_market_analysis" in getattr(API_INIT, "__all__", [])

    def test_persona_registered(self):
        assert hasattr(API_INIT, "product_persona") or \
            "product_persona" in getattr(API_INIT, "__all__", [])
