"""factory-console/api/artifacts.py — GET /artifacts 路由函数 (S9-002 只读)。"""

from __future__ import annotations

from typing import Any

from ..events import record_console_viewed
from ..models import ArtifactSummary

#: API 路由标识 (事件 payload view 名, 11B FastAPI 薄层同用)
VIEW = "artifacts"


def list_artifacts(
    service: Any,
    *,
    logger: Any = None,
    project_id: str | None = None,
    workflow_id: str | None = None,
    type: str | None = None,
) -> list[ArtifactSummary]:
    """GET /artifacts — org Artifact 清单 (project/workflow/type 过滤 + 审计)。

    无 org 数据空间 → 空列表 (失败安全); logger 存在时发 console.viewed
    (view="artifacts") 只读审计。
    """
    artifacts = service.list_artifacts(
        project_id=project_id, workflow_id=workflow_id, type=type
    )
    if logger is not None:
        record_console_viewed(
            logger,
            view=VIEW,
            count=len(artifacts),
            project_id=project_id,
            extra={"workflow_id": workflow_id, "type": type},
        )
    return artifacts


__all__ = ["VIEW", "list_artifacts"]
