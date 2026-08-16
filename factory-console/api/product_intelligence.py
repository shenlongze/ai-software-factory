"""factory-console/api/product_intelligence.py — S10-066 产品智能 API 路由函数。

纯函数路由 (无 Web 依赖, 同 agent_executor.py 模式 — 未来 FastAPI 薄层做
HTTP 绑定):

- product_intelligence_analyze: POST /api/product/intelligence/analyze
    request: {product_intent: {name/problem/user/platform/core_features/...}}
    response: ProductIntelligenceResponse {ok, data: 8 模块报告, error}
- product_market_analysis: POST /api/product/market-analysis
    response: {ok, data: MarketAnalysis, error}
- product_persona: POST /api/product/persona
    response: {ok, data: [UserPersona], error}

错误语义 (失败安全铁律): 输入非法 (product_intent 非 dict/字段类型错误) /
引擎异常 → {"ok": False, "error": str} — 绝不裸抛。分析一律 deterministic
(禁真实网络/LLM 调用 — GAP 五不该: 不抓取真实市场数据)。

设计: docs/sprint10/S10-066-product-intelligence-design.md §3
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from ..session.product import ProductIntent
from ..session.product_intelligence import ProductIntelligenceEngine

__all__ = [
    "ProductIntelligenceRequest",
    "ProductIntelligenceResponse",
    "product_intelligence_analyze",
    "product_market_analysis",
    "product_persona",
]


class ProductIntelligenceRequest(BaseModel):
    """POST /api/product/* 请求体: 产品意图 (ProductIntent 字段, 设计 §2.1)。

    product_intent: name/problem/user/platform/core_features/status/raw/
    session_id — 缺省字段由 ProductIntent.from_dict 兜底 (失败安全)。
    """

    product_intent: dict[str, Any] = Field(default_factory=dict)


class ProductIntelligenceResponse(BaseModel):
    """统一响应包装: ok + data (成功) / error (失败) — HTTP 层可映射。"""

    ok: bool = True
    data: Optional[Any] = None
    error: Optional[str] = None


def _to_response(data: Any, error: Optional[str] = None) -> dict[str, Any]:
    """响应模型 → dict (Pydantic v2 model_dump — HTTP 层直接序列化)。"""
    return ProductIntelligenceResponse(ok=error is None, data=data, error=error).model_dump()


def product_intelligence_analyze(product_intent: dict[str, Any]) -> dict[str, Any]:
    """POST /api/product/intelligence/analyze — 完整产品智能分析 (8 模块)。

    {product_intent} → {ok, data: ProductIntelligenceReport.to_dict(), error}。
    异常 (非法输入/引擎失败) → {"ok": False, "error": str} (不裸抛)。
    """
    try:
        request = ProductIntelligenceRequest(product_intent=product_intent or {})
        intent = ProductIntent.from_dict(request.product_intent)
        report = ProductIntelligenceEngine().analyze(intent)
        return _to_response(report.to_dict())
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律: 异常 → 明确错误
        return _to_response(None, f"产品智能分析失败: {exc}")


def product_market_analysis(product_intent: dict[str, Any]) -> dict[str, Any]:
    """POST /api/product/market-analysis — 市场分析 (G8 单模块)。

    {product_intent} → {ok, data: MarketAnalysis.to_dict(), error}。
    """
    try:
        request = ProductIntelligenceRequest(product_intent=product_intent or {})
        intent = ProductIntent.from_dict(request.product_intent)
        market = ProductIntelligenceEngine().analyze_market(intent)
        return _to_response(market.to_dict())
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return _to_response(None, f"市场分析失败: {exc}")


def product_persona(product_intent: dict[str, Any]) -> dict[str, Any]:
    """POST /api/product/persona — 用户画像 (G3 单模块)。

    {product_intent} → {ok, data: [UserPersona.to_dict()], error}。
    """
    try:
        request = ProductIntelligenceRequest(product_intent=product_intent or {})
        intent = ProductIntent.from_dict(request.product_intent)
        personas = ProductIntelligenceEngine().analyze_persona(intent)
        return _to_response([p.to_dict() for p in personas])
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return _to_response(None, f"用户画像分析失败: {exc}")
