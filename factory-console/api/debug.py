"""factory-console/api/debug.py — S10-068 Debug Intelligence API 路由函数。

纯函数路由 (无 Web 依赖, 同 memory.py 模式 — 未来 FastAPI 薄层做 HTTP 绑定):

- debug_analyze:   POST /api/debug/analyze   {error_message, task_id?, agent_id?,
                   context?, project?, previous_attempts?, workspace?} → DebugDecision
- debug_recommend: POST /api/debug/recommend {error_message, workspace?} → 策略推荐 (简版)
- debug_history:   GET  /api/debug/history   {workspace?, limit?} → [DebugCase 历史]
- debug_stats:     GET  /api/debug/stats     {workspace?} → 统计

错误语义 (失败安全铁律): 输入非法 (error_message 为空) / 引擎异常 →
{"ok": False, "error": str} — 绝不裸抛。

设计: docs/sprint10/S10-068-debug-intelligence-design.md §8
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..memory.experience_store import DEFAULT_WORKSPACE
from ..session.debug import DebugCase, DebugEngine
from ..session.debug.error_analysis import ErrorAnalyzer

__all__ = [
    "DebugAnalyzeRequest",
    "DebugHistoryRequest",
    "DebugRecommendRequest",
    "DebugResponse",
    "DebugStatsRequest",
    "debug_analyze",
    "debug_history",
    "debug_recommend",
    "debug_stats",
]


# ---------------------------------------------------------------- Schemas

class DebugAnalyzeRequest(BaseModel):
    """POST /api/debug/analyze 请求体: 错误信息 + 可选案件字段。"""

    error_message: str = ""
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    context: Optional[str] = None
    project: Optional[str] = None
    previous_attempts: int = 0
    workspace: Optional[str] = None


class DebugRecommendRequest(BaseModel):
    """POST /api/debug/recommend 请求体: 错误信息 (简版策略推荐)。"""

    error_message: str = ""
    workspace: Optional[str] = None


class DebugHistoryRequest(BaseModel):
    """GET /api/debug/history 请求体: workspace + limit。"""

    workspace: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=500)


class DebugStatsRequest(BaseModel):
    """GET /api/debug/stats 请求体: workspace。"""

    workspace: Optional[str] = None


class DebugResponse(BaseModel):
    """统一响应包装: ok + data (成功) / error (失败) — HTTP 层可映射。"""

    ok: bool = True
    data: Optional[Any] = None
    error: Optional[str] = None


# ---------------------------------------------------------------- 内部

def _to_response(data: Any, error: Optional[str] = None) -> dict[str, Any]:
    """响应模型 → dict (Pydantic v2 model_dump — HTTP 层直接序列化)。"""
    return DebugResponse(ok=error is None, data=data, error=error).model_dump()


def _workspace(workspace: Any = None) -> Path:
    """workspace → Path (None/空 → 默认工厂根 ~/.factory)。"""
    return Path(workspace) if workspace else DEFAULT_WORKSPACE


def _require_message(error_message: Any) -> str:
    """error_message 校验: 空 → ValueError (schema 校验语义)。"""
    message = str(error_message or "").strip()
    if not message:
        raise ValueError("error_message 不能为空")
    return message


# ---------------------------------------------------------------- 4 端点

def debug_analyze(
    error_message: str = "",
    task_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    context: Optional[str] = None,
    workspace: Any = None,
    project: Optional[str] = None,
    previous_attempts: int = 0,
) -> dict[str, Any]:
    """POST /api/debug/analyze — 完整调试分析 (DebugCase → DebugDecision)。

    {error_message, task_id?, agent_id?, context?, project?, previous_attempts?,
    workspace?} → {ok, data: DebugDecision.to_dict(), error}。
    """
    try:
        message = _require_message(error_message)
        engine = DebugEngine(_workspace(workspace))
        case = engine.analyzer.extract(
            message,
            task_id=task_id or "",
            agent_id=agent_id or "",
            context=context or "",
            project=project or "",
            previous_attempts=previous_attempts,
        )
        decision = engine.analyze(case)
        return _to_response(decision.to_dict())
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律: 异常 → 明确错误
        return _to_response(None, f"调试分析失败: {exc}")


def debug_recommend(error_message: str = "", workspace: Any = None) -> dict[str, Any]:
    """POST /api/debug/recommend — 策略推荐 (同 analyze 简版)。

    {error_message, workspace?} → {ok, data: {strategy, reason, confidence}, error}。
    """
    try:
        message = _require_message(error_message)
        engine = DebugEngine(_workspace(workspace))
        decision = engine.analyze(engine.analyzer.extract(message))
        return _to_response(
            {
                "strategy": decision.strategy.value
                if hasattr(decision.strategy, "value")
                else str(decision.strategy),
                "reason": decision.reason,
                "confidence": decision.confidence,
            }
        )
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return _to_response(None, f"策略推荐失败: {exc}")


def debug_history(workspace: Any = None, limit: int = 20) -> dict[str, Any]:
    """GET /api/debug/history — 调试案件历史 (最新在前)。

    {workspace?, limit?} → {ok, data: [entry], error} (entry 含 case/decision/outcome)。
    """
    try:
        engine = DebugEngine(_workspace(workspace))
        return _to_response(engine.history(_workspace(workspace), limit=limit))
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return _to_response(None, f"调试历史查询失败: {exc}")


def debug_stats(workspace: Any = None) -> dict[str, Any]:
    """GET /api/debug/stats — 调试统计 (按 error_type/strategy/outcome)。

    {workspace?} → {ok, data: {total_cases, by_error_type, by_strategy,
    by_outcome, file}, error}。
    """
    try:
        engine = DebugEngine(_workspace(workspace))
        return _to_response(engine.stats(_workspace(workspace)))
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律
        return _to_response(None, f"调试统计失败: {exc}")
