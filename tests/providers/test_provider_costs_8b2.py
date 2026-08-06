"""test_provider_costs_8b2.py — ProviderCostModel 成本估算 (Phase 8B-2, ADR-0024)。

覆盖:
- 四模式 (token/request/time/free) 估算值与校验
- token 模式: dict/int/缺省三种输入形态 + 缺定价键 ValueError
- request 模式: 单价 × 次数 (缺省 1)
- time 模式: duration_seconds 必填 (缺省 ValueError) + 按小时换算
- free: 恒 0.0 (free 标记 + mode=free 双路径)
- pricing 非负校验 / mode 枚举校验
- estimate_call_cost 多模式归一 (None 兜底 / 60s 基准 / 定价键缺失 → None)
- describe 人类可读
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from providers.costs import (
    COST_MODES,
    ESTIMATED_DURATION_SECONDS,
    ESTIMATED_TOKENS,
    ProviderCostModel,
    estimate_call_cost,
)


def make_cost(
    provider_id: str = "openai",
    mode: str = "token",
    pricing: dict | None = None,
    *,
    currency: str = "USD",
    free: bool = False,
) -> ProviderCostModel:
    return ProviderCostModel(
        provider_id=provider_id,
        mode=mode,
        pricing=pricing or {},
        currency=currency,
        free=free,
    )


class TestCostModelValidation:
    def test_default_mode_free(self):
        c = ProviderCostModel(provider_id="x")
        assert c.mode == "free"
        assert c.free is False
        assert c.currency == "USD"

    def test_mode_case_insensitive(self):
        c = make_cost("x", mode="TOKEN")
        assert c.mode == "token"

    def test_invalid_mode_rejected(self):
        with pytest.raises(ValidationError):
            make_cost("x", mode="per-token")

    def test_cost_modes_enum(self):
        assert COST_MODES == ("token", "request", "time", "free")

    def test_pricing_negative_rejected(self):
        with pytest.raises(ValidationError):
            make_cost("x", mode="request", pricing={"request": -0.1})

    def test_pricing_non_numeric_rejected(self):
        with pytest.raises(ValidationError):
            make_cost("x", mode="request", pricing={"request": "cheap"})

    def test_provider_id_sane(self):
        with pytest.raises(ValidationError):
            ProviderCostModel(provider_id="a/b", mode="free")

    def test_to_dict(self):
        c = make_cost("openai", mode="token", pricing={"input": 3.0, "output": 15.0})
        d = c.to_dict()
        assert d["mode"] == "token"
        assert d["pricing"] == {"input": 3.0, "output": 15.0}


class TestTokenMode:
    def test_estimate_explicit_tokens(self):
        c = make_cost("openai", mode="token", pricing={"input": 3.0, "output": 15.0})
        # 1000 in @ $3/1K + 2000 out @ $15/1K = 3 + 30 = 33
        assert c.estimate_cost({"input": 1000, "output": 2000}) == 33.0

    def test_estimate_int_tokens_means_output_only(self):
        c = make_cost("openai", mode="token", pricing={"input": 3.0, "output": 15.0})
        assert c.estimate_cost(1000) == 15.0  # 0 in + 1000 out

    def test_estimate_default_baseline(self):
        """缺省用模块基准 ESTIMATED_TOKENS = {input: 1000, output: 500}。"""
        c = make_cost("openai", mode="token", pricing={"input": 3.0, "output": 15.0})
        expected = 1000 * 3.0 / 1000 + 500 * 15.0 / 1000  # 3 + 7.5 = 10.5
        assert c.estimate_cost() == expected
        assert ESTIMATED_TOKENS == {"input": 1000, "output": 500}

    def test_missing_pricing_keys_raise(self):
        c = make_cost("openai", mode="token", pricing={"input": 3.0})
        with pytest.raises(ValueError):
            c.estimate_cost()
        c2 = make_cost("openai", mode="token", pricing={"output": 3.0})
        with pytest.raises(ValueError):
            c2.estimate_cost()

    def test_zero_tokens_zero_cost(self):
        c = make_cost("openai", mode="token", pricing={"input": 3.0, "output": 15.0})
        assert c.estimate_cost({"input": 0, "output": 0}) == 0.0


class TestRequestMode:
    def test_single_request(self):
        c = make_cost("openai", mode="request", pricing={"request": 0.01})
        assert c.estimate_cost() == 0.01

    def test_multiple_requests(self):
        c = make_cost("openai", mode="request", pricing={"request": 0.01})
        assert c.estimate_cost(requests=10) == 0.1

    def test_missing_pricing_raise(self):
        c = make_cost("openai", mode="request", pricing={})
        with pytest.raises(ValueError):
            c.estimate_cost()


class TestTimeMode:
    def test_duration_required(self):
        c = make_cost("openai", mode="time", pricing={"per_hour": 1.2})
        with pytest.raises(ValueError):
            c.estimate_cost()

    def test_hourly_estimate(self):
        c = make_cost("openai", mode="time", pricing={"per_hour": 1.2})
        # 30 分钟 = 0.6
        assert c.estimate_cost(duration_seconds=1800) == 0.6

    def test_one_hour_estimate(self):
        c = make_cost("openai", mode="time", pricing={"per_hour": 1.2})
        assert c.estimate_cost(duration_seconds=3600) == 1.2

    def test_missing_pricing_raise(self):
        c = make_cost("openai", mode="time", pricing={})
        with pytest.raises(ValueError):
            c.estimate_cost(duration_seconds=60)


class TestFreeMode:
    def test_mode_free_zero(self):
        c = make_cost("openai", mode="free", pricing={})
        assert c.estimate_cost() == 0.0
        assert c.estimate_cost({"input": 9999, "output": 9999}) == 0.0

    def test_free_flag_zero_even_with_pricing(self):
        """free=True 时即使带 pricing 也恒 0 (本地模型免费)。"""
        c = make_cost(
            "local", mode="token",
            pricing={"input": 3.0, "output": 15.0}, free=True,
        )
        assert c.estimate_cost({"input": 1000, "output": 2000}) == 0.0


class TestEstimateCallCost:
    def test_none_model_returns_none(self):
        """无成本模型 → None (排序排最后, 不臆造 0)。"""
        assert estimate_call_cost(None) is None

    def test_free_zero(self):
        c = make_cost("hermes", mode="free")
        assert estimate_call_cost(c) == 0.0

    def test_token_default_baseline(self):
        c = make_cost("openai", mode="token", pricing={"input": 3.0, "output": 15.0})
        expected = 1000 * 3.0 / 1000 + 500 * 15.0 / 1000
        assert estimate_call_cost(c) == expected

    def test_token_custom_tokens(self):
        c = make_cost("openai", mode="token", pricing={"input": 3.0, "output": 15.0})
        assert estimate_call_cost(c, tokens={"input": 0, "output": 1000}) == 15.0

    def test_request_one_call(self):
        c = make_cost("openai", mode="request", pricing={"request": 0.05})
        assert estimate_call_cost(c) == 0.05

    def test_time_uses_60s_baseline(self):
        c = make_cost("openai", mode="time", pricing={"per_hour": 36.0})
        # 60s = 1/60 小时 × $36 = $0.6
        assert estimate_call_cost(c) == 0.6
        assert ESTIMATED_DURATION_SECONDS == 60

    def test_time_custom_duration(self):
        c = make_cost("openai", mode="time", pricing={"per_hour": 36.0})
        assert estimate_call_cost(c, duration_seconds=3600) == 36.0

    def test_missing_pricing_key_fail_safe_none(self):
        """定价键缺失 → ValueError → 兜底 None (失败安全, 不抛)。"""
        c = make_cost("openai", mode="token", pricing={"input": 3.0})
        assert estimate_call_cost(c) is None


class TestDescribe:
    def test_describe_free(self):
        c = make_cost("hermes", mode="free")
        assert c.describe() == "free"

    def test_describe_token(self):
        c = make_cost("openai", mode="token", pricing={"input": 3.0, "output": 15.0})
        assert "token" in c.describe()
        assert "3.0/1K in" in c.describe()
        assert "15.0/1K out" in c.describe()

    def test_describe_request(self):
        c = make_cost("openai", mode="request", pricing={"request": 0.01})
        assert "request" in c.describe()
        assert "0.01/call" in c.describe()

    def test_describe_time(self):
        c = make_cost("openai", mode="time", pricing={"per_hour": 1.2})
        assert "time" in c.describe()
        assert "1.2/hour" in c.describe()
