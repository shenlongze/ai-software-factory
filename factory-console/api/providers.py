"""factory-console/api/providers.py — GET /providers 路由函数 (只读)。

返回 Provider 目录只读投影 (ProviderSummary): capability/cost/performance/
experience — 能力来自 catalog 定义, cost/performance/experience 来自 usage
统计 + 经验记录聚合 (无数据 → None, 冷启动不臆造)。
"""

from __future__ import annotations

from typing import Any

from ..events import record_console_viewed
from ..models import ProviderSummary

VIEW = "providers"


def list_providers(
    service: Any,
    *,
    logger: Any = None,
) -> list[ProviderSummary]:
    """GET /providers — Provider 目录 (只读聚合 + console.viewed 审计)。"""
    providers = service.list_providers()
    if logger is not None:
        record_console_viewed(
            logger,
            view=VIEW,
            count=len(providers),
            extra={"providers": [p.id for p in providers]},
        )
    return providers


__all__ = ["VIEW", "list_providers"]
