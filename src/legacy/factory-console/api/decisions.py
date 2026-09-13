"""factory-console/api/decisions.py — GET /decisions/{id} 路由函数 (只读)。

返回单决策只读投影 (DecisionSummary): options/recommendation/score/
reasoning/evidence/risk。不存在 → None (11B 映射 404)。决策状态流转
(accept/reject 回写) 由既有 DecisionIntelligence 负责, Console 只读。
"""

from __future__ import annotations

from typing import Any

from ..events import record_console_viewed
from ..models import DecisionSummary

VIEW = "decisions"


def get_decision(
    service: Any,
    decision_id: str,
    *,
    logger: Any = None,
) -> DecisionSummary | None:
    """GET /decisions/{id} — 决策详情 (只读 + console.viewed 审计)。"""
    summary = service.get_decision(decision_id)
    if logger is not None:
        record_console_viewed(
            logger,
            view=VIEW,
            count=1 if summary is not None else 0,
            extra={"decision_id": decision_id},
        )
    return summary


__all__ = ["VIEW", "get_decision"]
