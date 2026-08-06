"""factory-core/product/events.py — product.*/idea.*/approval.* 事件辅助 (经 EventLogger)。

设计依据:
- phase9-plan.md §3 (Event Namespace): idea.created/updated / approval.required/
  granted/denied / product.workflow.started — 全部经 EventLogger (唯一事实源)。
- phase9a-status.md §Event 集成: EventType 枚举扩展 (events/models.py) +
  本模块辅助函数; logger 为 None 时全部静默 (同 understanding/events.py 模式)。
- ADR-0002: 所有 CLI 行为必须产生 Event — 读命令审计 (idea.viewed /
  product.workflow.status_viewed / approval.viewed) 由 CLI 命令层发出
  (source="cli"); 写路径事件由服务层发出 (source="product")。
- AI Artifact Lineage: approval.required 的 payload 携带 artifact_id/type/
  source_events 摘要, 后续 Product Decision Artifact 的 source_events 引用
  对应事件 event_id (经 return 值回填, 见 service.decide_approval)。

payload 契约 (与 CLI --json 出口一致, Dashboard Product View 事件聚合同源)。
"""

from __future__ import annotations

from typing import Any

from events.models import Event, EventType


def record_idea_created(
    logger: Any,
    *,
    idea: Any,
    artifact: Any = None,
    source: str = "product",
) -> Event | None:
    """想法创建 (ProductService.create_idea; 同步落 product_idea Artifact)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.IDEA_CREATED,
        source=source,
        stage=idea.status,
        action="create product idea",
        result="OK",
        payload={
            "idea_id": idea.id,
            "title": idea.title,
            "artifact_id": artifact.id if artifact is not None else None,
            "goals": idea.goals,
        },
    )


def record_idea_viewed(
    logger: Any,
    *,
    count: int,
    idea_id: str | None = None,
    source: str = "cli",
) -> Event | None:
    """想法列表/详情被查看 (CLI 读命令审计, ADR-0002; source 缺省 cli)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.IDEA_VIEWED,
        source=source,
        stage="viewed",
        action="view product ideas",
        result="OK",
        payload={"count": count, "idea_id": idea_id},
    )


def record_idea_updated(
    logger: Any,
    *,
    idea: Any,
    source: str = "product",
) -> Event | None:
    """想法更新 (status 流转等; 9a 骨架仅预留辅助, service 暂不调用)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.IDEA_UPDATED,
        source=source,
        stage=idea.status,
        action="update product idea",
        result="OK",
        payload={"idea_id": idea.id, "title": idea.title, "status": idea.status},
    )


def record_approval_required(
    logger: Any,
    *,
    request: Any,
    gate: Any = None,
    artifact: Any = None,
    source: str = "product",
) -> Event | None:
    """审批请求创建 (approval.required; 任何 Artifact 可申请 — 门不绑定类型)。"""
    if logger is None:
        return None
    payload: dict[str, Any] = {
        "request_id": request.id,
        "artifact_id": request.artifact_id,
        "gate": request.gate,
        "status": request.status,
        "idea_id": request.idea_id,
    }
    if gate is not None:
        payload["artifact_type"] = gate.artifact_type
        payload["required"] = gate.required
    if artifact is not None:
        payload["artifact_type"] = payload.get("artifact_type") or artifact.type
        payload["source_events"] = artifact.source_events  # Lineage 摘要
    return logger.record(
        EventType.APPROVAL_REQUIRED,
        source=source,
        stage=request.status,
        action="request approval",
        result="OK",
        payload=payload,
    )


def _record_approval_decision(
    logger: Any,
    type_: EventType,
    *,
    request: Any,
    decision: Any,
    artifact: Any = None,
    source: str,
) -> Event | None:
    """approval.granted / approval.denied 共用 (终态决定, 不可逆)。"""
    if logger is None:
        return None
    return logger.record(
        type_,
        source=source,
        stage=request.status,
        action="approve artifact" if decision.decision == "approved" else "deny artifact",
        result=decision.decision.upper(),
        payload={
            "request_id": request.id,
            "artifact_id": request.artifact_id,
            "gate": request.gate,
            "decision": decision.decision,
            "decided_by": decision.decided_by,
            "comment": decision.comment,
            "idea_id": request.idea_id,
            "artifact_type": artifact.type if artifact is not None else None,
        },
    )


def record_approval_granted(
    logger: Any,
    *,
    request: Any,
    decision: Any,
    artifact: Any = None,
    source: str = "product",
) -> Event | None:
    """审批通过 (approval.granted; Product Decision Artifact 的 source_events 锚点)。"""
    return _record_approval_decision(
        logger, EventType.APPROVAL_GRANTED,
        request=request, decision=decision, artifact=artifact, source=source,
    )


def record_approval_denied(
    logger: Any,
    *,
    request: Any,
    decision: Any,
    artifact: Any = None,
    source: str = "product",
) -> Event | None:
    """审批拒绝 (approval.denied; 回退重生成, 记录 comment)。"""
    return _record_approval_decision(
        logger, EventType.APPROVAL_DENIED,
        request=request, decision=decision, artifact=artifact, source=source,
    )


def record_approval_viewed(
    logger: Any,
    *,
    count: int,
    pending_only: bool = False,
    source: str = "cli",
) -> Event | None:
    """审批清单被查看 (CLI 读命令审计, ADR-0002; source 缺省 cli)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.APPROVAL_VIEWED,
        source=source,
        stage="viewed",
        action="view approvals",
        result="OK",
        payload={"count": count, "pending_only": pending_only},
    )


def record_workflow_started(
    logger: Any,
    *,
    workflow: Any,
    source: str = "product",
) -> Event | None:
    """产品工作流启动 (product.workflow.started; 骨架阶段链)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.PRODUCT_WORKFLOW_STARTED,
        source=source,
        stage=workflow.status,
        action="start product workflow",
        result="OK",
        payload={
            "workflow_id": workflow.id,
            "idea_id": workflow.idea_id,
            "stages": workflow.stages,
            "current_stage": workflow.current_stage,
        },
    )


def record_workflow_status_viewed(
    logger: Any,
    *,
    workflow: Any,
    source: str = "cli",
) -> Event | None:
    """产品工作流状态被查看 (CLI 读命令审计, ADR-0002; source 缺省 cli)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.PRODUCT_WORKFLOW_STATUS_VIEWED,
        source=source,
        stage=workflow.status,
        action="view product workflow status",
        result="OK",
        payload={
            "workflow_id": workflow.id,
            "idea_id": workflow.idea_id,
            "current_stage": workflow.current_stage,
            "status": workflow.status,
            "product_decision": workflow.product_decision,
        },
    )
