"""providers/costs.py — ProviderCostModel: 成本估算模型 (Phase 8B-2, 非真实计费)。

设计依据:
- phase8b2-plan.md §3: ProviderCostModel (mode: token/request/time/free,
  评审调整 2) — 多模式定价估算, 明确非真实计费 (§8 非目标: 不实现真实
  计费/支付; 估算只做选择依据与审计展示)。
- estimate_cost: 按模式估算一次调用成本 (纯函数语义, 无存储依赖):
  - token:   pricing {input: $/1K, output: $/1K} → input*in/1000 + output*out/1000
  - request: pricing {request: $/次} → 单价 × 请求次数 (缺省 1)
  - time:    pricing {per_hour: $/小时} → 单价 × 时长 (duration_seconds 必填)
  - free:    免费 (本地模型, 恒 0.0)
- estimate_call_cost: 统一"一次调用"估算基准 (token/request/time 模式归一,
  CostAwareSelector 成本排序与 CLI compare 共用; time 模式按 60s 基准) —
  基准常量即文档 (估算模型, 非真实计费), 与 usage 记录的实测值互不覆盖。

pricing 契约 (JSON 友好, 值须非负):
- token:   {"input": 3.0, "output": 15.0}   (per 1K tokens, USD)
- request: {"request": 0.01}                 (per call)
- time:    {"per_hour": 1.2}                 (per hour)
- free:    {}                                (pricing 可空)
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from .models import _id_sane

#: 成本模式枚举值 (评审调整 2): token / request / time / free
COST_MODES: tuple[str, ...] = ("token", "request", "time", "free")

#: 一次调用的估算 token 基准 (估算模型, 非真实计费; CostAwareSelector 与
#: CLI compare 共用 — 无 usage 实测数据时的排序基准)
ESTIMATED_TOKENS: dict[str, int] = {"input": 1000, "output": 500}

#: time 模式一次调用的估算时长基准 (秒)
ESTIMATED_DURATION_SECONDS: int = 60


class ProviderCostModel(BaseModel):
    """一个 Provider 的定价估算模型 (多模式, 非真实计费)。

    - mode: token | request | time | free (评审调整 2)。
    - pricing: 按模式的单价表 (见模块 docstring 契约; free 可空)。
    - free: 免费标记 (本地模型 — estimate_cost 恒 0.0, 成本排序优先)。
    """

    provider_id: str
    mode: str = "free"
    pricing: dict[str, float] = Field(default_factory=dict)
    currency: str = "USD"
    free: bool = False

    @field_validator("provider_id")
    @classmethod
    def _cost_id_sane(cls, v: str) -> str:
        return _id_sane(v)

    @field_validator("mode", mode="before")
    @classmethod
    def _mode_normalized(cls, v: Any) -> str:
        mode = str(v).strip().lower()
        if mode not in COST_MODES:
            raise ValueError(f"invalid cost mode: {v!r} (expected one of: {', '.join(COST_MODES)})")
        return mode

    @field_validator("pricing")
    @classmethod
    def _pricing_nonnegative(cls, v: dict[str, float]) -> dict[str, float]:
        bad = {k: val for k, val in v.items() if not isinstance(val, (int, float))}
        if bad:
            raise ValueError(f"pricing values must be numeric: {sorted(bad)}")
        out: dict[str, float] = {}
        for k, val in v.items():
            price = float(val)
            if price < 0.0:
                raise ValueError(f"pricing value must be non-negative: {k}={price}")
            out[k] = price
        return out

    # ------------------------------------------------------------------ 估算

    def estimate_cost(
        self,
        tokens: int | dict[str, int] | None = None,
        *,
        duration_seconds: float | None = None,
        requests: int | None = None,
    ) -> float:
        """按模式估算一次调用成本 (USD, 非真实计费)。

        Args:
            tokens: token 模式输入 — dict {input, output} 或 int (视为仅 output,
                即 {input: 0, output: n}); 缺省用模块基准 ESTIMATED_TOKENS。
            duration_seconds: time 模式必填 (秒); 缺省抛 ValueError。
            requests: request 模式调用次数 (缺省 1)。

        Raises:
            ValueError: time 模式缺 duration_seconds / token 模式定价键缺失。
        """
        if self.free or self.mode == "free":
            return 0.0
        if self.mode == "token":
            t = self._coerce_tokens(tokens)
            price_in = self.pricing.get("input")
            price_out = self.pricing.get("output")
            if price_in is None or price_out is None:
                raise ValueError(
                    f"token cost model requires pricing 'input' and 'output': {self.pricing}"
                )
            return round(t["input"] * price_in / 1000.0 + t["output"] * price_out / 1000.0, 8)
        if self.mode == "request":
            price = self.pricing.get("request")
            if price is None:
                raise ValueError(
                    f"request cost model requires pricing 'request': {self.pricing}"
                )
            return round(price * (requests if requests is not None else 1), 8)
        if self.mode == "time":
            if duration_seconds is None:
                raise ValueError("time cost model requires duration_seconds")
            price = self.pricing.get("per_hour")
            if price is None:
                raise ValueError(
                    f"time cost model requires pricing 'per_hour': {self.pricing}"
                )
            return round(price * float(duration_seconds) / 3600.0, 8)
        raise ValueError(f"unsupported cost mode: {self.mode}")  # pragma: no cover

    def _coerce_tokens(self, tokens: int | dict[str, int] | None) -> dict[str, int]:
        if tokens is None:
            return dict(ESTIMATED_TOKENS)
        if isinstance(tokens, dict):
            return {
                "input": int(tokens.get("input", 0)),
                "output": int(tokens.get("output", 0)),
            }
        return {"input": 0, "output": int(tokens)}

    def describe(self) -> str:
        """人类可读定价描述 (CLI compare 展示, 非真实计费)。"""
        if self.free or self.mode == "free":
            return "free"
        if self.mode == "token":
            return (
                f"token ({self.pricing.get('input', 0)}/1K in, "
                f"{self.pricing.get('output', 0)}/1K out {self.currency})"
            )
        if self.mode == "request":
            return f"request ({self.pricing.get('request', 0)}/call {self.currency})"
        if self.mode == "time":
            return f"time ({self.pricing.get('per_hour', 0)}/hour {self.currency})"
        return self.mode  # pragma: no cover

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def estimate_call_cost(
    cost_model: ProviderCostModel | None,
    *,
    tokens: dict[str, int] | None = None,
    duration_seconds: float | None = None,
) -> float | None:
    """统一"一次调用"估算成本 (多模式归一, 供成本排序/对比)。

    - 无 cost_model → None (无法估算 — 排序时排最后, 不臆造 0)。
    - token 模式按 tokens 基准 (缺省 ESTIMATED_TOKENS);
    - request 模式按 1 次; time 模式按 duration_seconds (缺省
      ESTIMATED_DURATION_SECONDS)。
    - free → 0.0。
    """
    if cost_model is None:
        return None
    try:
        if cost_model.mode == "time":
            return cost_model.estimate_cost(
                duration_seconds=(
                    duration_seconds if duration_seconds is not None
                    else ESTIMATED_DURATION_SECONDS
                ),
            )
        if cost_model.mode == "token":
            return cost_model.estimate_cost(tokens or ESTIMATED_TOKENS)
        return cost_model.estimate_cost()
    except ValueError:
        return None  # 定价键缺失 → 无法估算 (失败安全)
