"""factory-console/api/workflows.py — GET /workflows 路由函数 (S9-002 只读)。"""

from __future__ import annotations

from typing import Any

from ..events import record_console_viewed
from ..models import WorkflowDetail, WorkflowSummary

#: API 路由标识 (事件 payload view 名, 11B FastAPI 薄层同用)
VIEW = "workflows"


def list_workflows(
    service: Any,
    *,
    logger: Any = None,
    project_id: str | None = None,
) -> list[WorkflowSummary]:
    """GET /workflows — 组织级 Workflow 运行清单 (阶段链进度聚合 + 审计)。

    无 org 数据空间 → 空列表 (失败安全, 同其余域); logger 存在时发
    console.viewed (view="workflows") 只读审计。
    """
    workflows = service.list_workflows(project_id=project_id)
    if logger is not None:
        record_console_viewed(
            logger,
            view=VIEW,
            count=len(workflows),
            project_id=project_id,
            extra={"workflows": [w.id for w in workflows]},
        )
    return workflows


def get_workflow(
    service: Any,
    workflow_id: str,
    *,
    logger: Any = None,
) -> WorkflowDetail | None:
    """GET /workflows/{id} — 单 Workflow 8 阶段链全视图 (404 语义由调用方定)。

    无 org/不存在 → None (11B HTTP 层映射 404); logger 存在时发
    console.viewed (view="workflow_detail") 只读审计。
    """
    detail = service.get_workflow(workflow_id)
    if logger is not None:
        record_console_viewed(
            logger,
            view="workflow_detail",
            count=1 if detail is not None else 0,
            project_id=detail.project_id if detail else None,
            extra={"workflow_id": workflow_id},
        )
    return detail


__all__ = ["VIEW", "get_workflow", "list_workflows"]
