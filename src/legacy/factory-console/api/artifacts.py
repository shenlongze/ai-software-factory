"""factory-console/api/artifacts.py — GET /artifacts 路由函数 (S9-002 只读)。"""

from __future__ import annotations

from typing import Any

from ..events import record_console_viewed
from ..models import ArtifactContent, ArtifactDetail, ArtifactSummary

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


def get_artifact(
    service: Any,
    artifact_id: str,
    *,
    logger: Any = None,
) -> ArtifactDetail | None:
    """GET /artifacts/{id} — 单产物详情 (S9-003 Review 数据源)。

    返回 ArtifactDetail (metadata 契约载荷 + review 审批门状态); 无 org /
    产物不存在 → None (HTTP 层映射 404)。logger 存在时发 console.viewed
    (view="artifact_detail") 只读审计。
    """
    detail = service.get_artifact(artifact_id)
    if logger is not None and detail is not None:
        record_console_viewed(
            logger,
            view="artifact_detail",
            count=1,
            extra={
                "artifact_id": artifact_id,
                "type": detail.type,
                "review_status": detail.review.status if detail.review else None,
            },
        )
    return detail


def get_artifact_content(
    service: Any,
    artifact_id: str,
    *,
    logger: Any = None,
) -> ArtifactContent | None:
    """GET /artifacts/{id}/content — 产物渲染内容 (S10-005 Artifact Center)。

    返回 ArtifactContent (location 文件文本; 缺失 → content None — 失败安全);
    无 org / 产物不存在 → None (HTTP 层映射 404)。logger 存在时发
    console.viewed (view="artifact_content") 只读审计。
    """
    content = service.get_artifact_content(artifact_id)
    if logger is not None and content is not None:
        record_console_viewed(
            logger,
            view="artifact_content",
            count=1,
            extra={"artifact_id": artifact_id, "type": content.type},
        )
    return content


__all__ = ["VIEW", "get_artifact", "get_artifact_content", "list_artifacts"]
