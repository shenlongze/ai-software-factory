"""factory-console/api/lifecycle.py — GET /projects/{id}/lifecycle 路由函数 (只读)。

返回单项目生命周期只读快照 (LifecycleSummary): current stage/completed
stages/pending approval/next actions。无生命周期 → None (11B 映射 404)。
"""

from __future__ import annotations

from typing import Any

from ..events import record_console_viewed
from ..models import LifecycleSummary

VIEW = "lifecycle"


def get_project_lifecycle(
    service: Any,
    project_id: str,
    *,
    logger: Any = None,
) -> LifecycleSummary | None:
    """GET /projects/{id}/lifecycle — 生命周期快照 (只读 + console.viewed 审计)。"""
    summary = service.project_lifecycle(project_id)
    if logger is not None:
        record_console_viewed(
            logger,
            view=VIEW,
            count=1 if summary is not None else 0,
            project_id=project_id,
            extra={"lifecycle_status": summary.status if summary is not None else None},
        )
    return summary


__all__ = ["VIEW", "get_project_lifecycle"]
