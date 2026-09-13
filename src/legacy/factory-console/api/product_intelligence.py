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
- product_mvp: POST /api/product/mvp (S10-070 G1 补齐)
    request: {product_intent, workspace?} → {ok, data: MvpPlan, error}
- product_value: POST /api/product/value (S10-070 G1 补齐)
    request: {product_intent, workspace?} → {ok, data: ProductValueScore, error}

错误语义 (失败安全铁律): 输入非法 (product_intent 非 dict/字段类型错误) /
引擎异常 → {"ok": False, "error": str} — 绝不裸抛。分析一律 deterministic
(禁真实网络/LLM 调用 — GAP 五不该: 不抓取真实市场数据)。

S10-070: workspace 可选参数 — product_intent 为空时从
workspace/projects/<slug>/product.json 定位最新产品意图 (同 CLI
_product_intent_from_context 口径; 失败安全: 找不到 → 空意图 → 引擎兜底)。

设计: docs/sprint10/S10-066-product-intelligence-design.md §3
     + docs/sprint10/S10-070-gap-design.md §三.1 (G1 API 补齐)
"""

from __future__ import annotations

import json
from pathlib import Path
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
    "product_mvp",
    "product_value",
]


class ProductIntelligenceRequest(BaseModel):
    """POST /api/product/* 请求体: 产品意图 (ProductIntent 字段, 设计 §2.1)。

    product_intent: name/problem/user/platform/core_features/status/raw/
    session_id — 缺省字段由 ProductIntent.from_dict 兜底 (失败安全)。
    workspace: 可选 (S10-070) — product_intent 为空时的产品意图兜底来源。
    """

    product_intent: dict[str, Any] = Field(default_factory=dict)
    workspace: Optional[str] = None


class ProductIntelligenceResponse(BaseModel):
    """统一响应包装: ok + data (成功) / error (失败) — HTTP 层可映射。"""

    ok: bool = True
    data: Optional[Any] = None
    error: Optional[str] = None


def _to_response(data: Any, error: Optional[str] = None) -> dict[str, Any]:
    """响应模型 → dict (Pydantic v2 model_dump — HTTP 层直接序列化)。"""
    return ProductIntelligenceResponse(ok=error is None, data=data, error=error).model_dump()


def _intent_from_workspace(workspace: Optional[str]) -> dict[str, Any]:
    """workspace → 最新产品意图 (projects/<slug>/product.json 兜底, 失败安全)。

    workspace 缺失/无项目/损坏 → {} (调用方走引擎兜底)。S10-070: CLI 与 API
    同一产品定位口径 (projects/*/product.json 最新一个)。
    """
    if not workspace:
        return {}
    projects_dir = Path(workspace) / "projects"
    if not projects_dir.is_dir():
        return {}
    matches = sorted(projects_dir.glob("*/product.json"))
    if not matches:
        return {}
    latest = max(matches, key=lambda p: p.stat().st_mtime)
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 — 失败安全: 损坏 → 空意图
        return {}


def _intent_dict(
    product_intent: Optional[dict[str, Any]],
    workspace: Optional[str] = None,
) -> dict[str, Any]:
    """请求意图归一: product_intent 非空优先; 否则 workspace 兜底; 再否则 {}。"""
    if isinstance(product_intent, dict) and product_intent:
        return product_intent
    return _intent_from_workspace(workspace)


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


def product_mvp(
    product_intent: Optional[dict[str, Any]] = None,
    workspace: Optional[str] = None,
) -> dict[str, Any]:
    """POST /api/product/mvp — MVP 规划 (G6 单模块, S10-070 G1 补齐)。

    {product_intent, workspace?} → {ok, data: MvpPlan.to_dict(), error}。
    workspace: product_intent 为空时从 workspace 定位最新产品意图 (兜底)。
    非法输入/引擎异常 → {"ok": False, "error": str} (不裸抛)。
    """
    try:
        request = ProductIntelligenceRequest(
            product_intent=product_intent or {},
            workspace=workspace,
        )
        intent = ProductIntent.from_dict(
            _intent_dict(request.product_intent, request.workspace)
        )
        mvp = ProductIntelligenceEngine().plan_mvp(intent)
        return _to_response(mvp.to_dict())
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return _to_response(None, f"MVP 规划失败: {exc}")


def product_value(
    product_intent: Optional[dict[str, Any]] = None,
    workspace: Optional[str] = None,
) -> dict[str, Any]:
    """POST /api/product/value — 产品价值评分 (G5 单模块, S10-070 G1 补齐)。

    {product_intent, workspace?} → {ok, data: ProductValueScore.to_dict(), error}。
    workspace: product_intent 为空时从 workspace 定位最新产品意图 (兜底)。
    非法输入/引擎异常 → {"ok": False, "error": str} (不裸抛)。
    """
    try:
        request = ProductIntelligenceRequest(
            product_intent=product_intent or {},
            workspace=workspace,
        )
        intent = ProductIntent.from_dict(
            _intent_dict(request.product_intent, request.workspace)
        )
        score = ProductIntelligenceEngine().score_value(intent)
        return _to_response(score.to_dict())
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return _to_response(None, f"价值评分失败: {exc}")
