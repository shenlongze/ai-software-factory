"""factory-console/api/projects.py — GET /projects 路由函数 (只读)。

返回全部项目只读投影 (ProjectSummary): id/name/lifecycle stage/status/
last activity。无项目 → 空列表 (404 语义由 11B HTTP 层决定, 本层只读投影)。
"""

from __future__ import annotations

from typing import Any

from ..events import record_console_viewed
from ..models import ProjectSummary

#: API 路由标识 (事件 payload view 名, 11B FastAPI 薄层同用)
VIEW = "projects"


def list_projects(
    service: Any,
    *,
    logger: Any = None,
) -> list[ProjectSummary]:
    """GET /projects — 项目清单 (只读聚合 + console.viewed 审计)。"""
    projects = service.list_projects()
    if logger is not None:
        record_console_viewed(
            logger, view=VIEW, count=len(projects), extra={"projects": [p.id for p in projects]}
        )
    return projects


__all__ = ["VIEW", "list_projects"]
