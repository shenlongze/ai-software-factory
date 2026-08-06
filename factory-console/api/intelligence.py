"""factory-console/api/intelligence.py — GET /recommendations + GET /experience 路由函数。

- GET /recommendations: 推荐产物只读投影 (RecommendationSummary):
  candidate/score/factors/explanation — 只推荐不执行 (执行决策权在人,
  phase10a-plan §Q1 边界铁律)。
- GET /experience: 经验记录只读投影 (ExperienceSummary):
  provider/agent/skill/workflow/success rate/confidence (六域 subject 定位)。
两个视图都只读聚合 + console.viewed 审计 (ADR-0002)。
"""

from __future__ import annotations

from typing import Any

from ..events import record_console_viewed
from ..models import ExperienceSummary, RecommendationSummary

VIEW_RECOMMENDATIONS = "recommendations"
VIEW_EXPERIENCE = "experience"


def list_recommendations(
    service: Any,
    *,
    logger: Any = None,
    limit: int = 10,
) -> list[RecommendationSummary]:
    """GET /recommendations — 推荐清单 (只读 + console.viewed 审计)。"""
    recommendations = service.list_recommendations(limit=limit)
    if logger is not None:
        record_console_viewed(
            logger,
            view=VIEW_RECOMMENDATIONS,
            count=len(recommendations),
            extra={"limit": limit},
        )
    return recommendations


def list_experience(
    service: Any,
    *,
    logger: Any = None,
    limit: int = 10,
) -> list[ExperienceSummary]:
    """GET /experience — 经验清单 (只读 + console.viewed 审计)。"""
    experiences = service.list_experience(limit=limit)
    if logger is not None:
        record_console_viewed(
            logger,
            view=VIEW_EXPERIENCE,
            count=len(experiences),
            extra={"limit": limit},
        )
    return experiences


__all__ = ["VIEW_EXPERIENCE", "VIEW_RECOMMENDATIONS", "list_experience", "list_recommendations"]
