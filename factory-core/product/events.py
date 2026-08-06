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
    status: str | None = None,
    artifact_id: str | None = None,
    source: str = "cli",
) -> Event | None:
    """审批清单被查看 (CLI 读命令审计, ADR-0002; source 缺省 cli)。

    Phase 9c: --status 过滤 (approval list) / approval history 复用本事件
    (payload 携带 status 与 artifact_id 上下文)。
    """
    if logger is None:
        return None
    payload: dict[str, Any] = {"count": count, "pending_only": pending_only}
    if status is not None:
        payload["status"] = status
    if artifact_id is not None:
        payload["artifact_id"] = artifact_id
    return logger.record(
        EventType.APPROVAL_VIEWED,
        source=source,
        stage="viewed",
        action="view approvals",
        result="OK",
        payload=payload,
    )


def _record_approval_lifecycle(
    logger: Any,
    type_: EventType,
    *,
    request: Any,
    gate: Any = None,
    artifact: Any = None,
    source: str = "product",
    action: str,
) -> Event | None:
    """approval.created / approval.pending 共用 (请求生命周期事件)。

    payload 与 approval.required 同构 (request_id/artifact_id/gate/status/
    idea_id/artifact_version + artifact_type/required/source_events) — 事件
    唯一事实源: 队列/历史/审计从事件 payload 即可重建上下文。
    """
    if logger is None:
        return None
    payload: dict[str, Any] = {
        "request_id": request.id,
        "artifact_id": request.artifact_id,
        "gate": request.gate,
        "status": request.status,
        "idea_id": request.idea_id,
        "artifact_version": getattr(request, "artifact_version", None),
    }
    if gate is not None:
        payload["artifact_type"] = gate.artifact_type
        payload["required"] = gate.required
    if artifact is not None:
        payload["artifact_type"] = payload.get("artifact_type") or artifact.type
        payload["source_events"] = artifact.source_events  # Lineage 摘要
    return logger.record(
        type_,
        source=source,
        stage=request.status,
        action=action,
        result="OK",
        payload=payload,
    )


def record_approval_created(
    logger: Any,
    *,
    request: Any,
    gate: Any = None,
    artifact: Any = None,
    source: str = "product",
) -> Event | None:
    """审批请求创建 (approval.created; request 落库后发出, 状态机起点)。"""
    return _record_approval_lifecycle(
        logger, EventType.APPROVAL_CREATED,
        request=request, gate=gate, artifact=artifact, source=source,
        action="create approval request",
    )


def record_approval_pending(
    logger: Any,
    *,
    request: Any,
    gate: Any = None,
    artifact: Any = None,
    source: str = "product",
) -> Event | None:
    """请求进入待审队列 (approval.pending; 等待人工决定, workflow → paused)。"""
    return _record_approval_lifecycle(
        logger, EventType.APPROVAL_PENDING,
        request=request, gate=gate, artifact=artifact, source=source,
        action="queue approval request",
    )


def _record_approval_decision_9c(
    logger: Any,
    type_: EventType,
    *,
    request: Any,
    decision: Any,
    artifact: Any = None,
    source: str = "product",
    action: str,
) -> Event | None:
    """approval.approved/rejected/changes_requested/delegated 共用 (终态决定)。"""
    if logger is None:
        return None
    return logger.record(
        type_,
        source=source,
        stage=request.status,
        action=action,
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
            "artifact_version": getattr(request, "artifact_version", None),
        },
    )


def record_approval_approved(
    logger: Any,
    *,
    request: Any,
    decision: Any,
    artifact: Any = None,
    source: str = "product",
) -> Event | None:
    """审批通过 (approval.approved; 终态, 产生 Product Decision Artifact)。"""
    return _record_approval_decision_9c(
        logger, EventType.APPROVAL_APPROVED,
        request=request, decision=decision, artifact=artifact, source=source,
        action="approve artifact",
    )


def record_approval_rejected(
    logger: Any,
    *,
    request: Any,
    decision: Any,
    artifact: Any = None,
    source: str = "product",
) -> Event | None:
    """审批拒绝 (approval.rejected; 终态, 回退重生成 — 9a denied 语义映射)。"""
    return _record_approval_decision_9c(
        logger, EventType.APPROVAL_REJECTED,
        request=request, decision=decision, artifact=artifact, source=source,
        action="reject artifact",
    )


def record_approval_changes_requested(
    logger: Any,
    *,
    request: Any,
    decision: Any,
    artifact: Any = None,
    source: str = "product",
) -> Event | None:
    """要求修改 (approval.changes_requested; 终态, 修改后重新审批)。"""
    return _record_approval_decision_9c(
        logger, EventType.APPROVAL_CHANGES_REQUESTED,
        request=request, decision=decision, artifact=artifact, source=source,
        action="request artifact changes",
    )


def record_approval_delegated(
    logger: Any,
    *,
    request: Any,
    decision: Any,
    artifact: Any = None,
    source: str = "product",
) -> Event | None:
    """审批转派 (approval.delegated; 终态, 待被转派人决定 — 通用决策系统: 审批
    可委托给其他决策人, 被转派人经新请求重新决定)。"""
    return _record_approval_decision_9c(
        logger, EventType.APPROVAL_DELEGATED,
        request=request, decision=decision, artifact=artifact, source=source,
        action="delegate approval",
    )


def record_approval_resumed(
    logger: Any,
    *,
    workflow: Any,
    reason: str = "manual",
    source: str = "product",
) -> Event | None:
    """工作流恢复 (approval.resumed; paused → running — 终态决定自动恢复或
    CLI workflow resume 手动恢复, reason: approved/rejected/changes_requested/manual)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.APPROVAL_RESUMED,
        source=source,
        stage=workflow.status,
        action="resume product workflow",
        result="OK",
        payload={
            "workflow_id": workflow.id,
            "idea_id": workflow.idea_id,
            "current_stage": workflow.current_stage,
            "status": workflow.status,
            "reason": reason,
        },
    )


def record_approval_experience_recorded(
    logger: Any,
    *,
    experience: Any,
    by: str = "cli",
    source: str = "product",
) -> Event | None:
    """审批经验记录落盘 (ProductGenerator.record_approval_experience;
    product.approval_experience.recorded)。

    payload: experience_id/artifact_type/provider_id/agent_id/confidence/decision/
    human_comment/improvement_signal/by — Provider/Agent 优化数据接口 (只记录
    不消费, 同 product.experience.recorded 语义)。
    """
    if logger is None:
        return None
    return logger.record(
        EventType.PRODUCT_APPROVAL_EXPERIENCE_RECORDED,
        source=source,
        stage="recorded",
        action="record approval experience",
        result="OK",
        payload={
            "experience_id": experience.id,
            "artifact_type": experience.artifact_type,
            "provider_id": experience.provider_id,
            "agent_id": experience.agent_id,
            "confidence": experience.confidence,
            "decision": experience.decision,
            "human_comment": experience.human_comment,
            "improvement_signal": experience.improvement_signal,
            "by": by,
        },
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


def record_generation_started(
    logger: Any,
    *,
    artifact_type: str,
    source_artifact_id: str,
    idea_id: str | None = None,
    provider_id: str | None = None,
    task_requirement: dict[str, Any] | None = None,
    source: str = "product",
) -> Event | None:
    """生成开始 (ProductGenerator.generate 选定 Provider 后; product.generation.started)。

    payload: artifact_type/source_artifact_id/idea_id/provider_id/task_requirement
    — 与 GeneratedArtifactContext.task_requirement 同源 (审计: 什么需求经什么
    选择逻辑选了哪个 Provider)。result=OK (开始不是终态)。
    """
    if logger is None:
        return None
    return logger.record(
        EventType.PRODUCT_GENERATION_STARTED,
        source=source,
        stage="running",
        action="generate product artifact",
        result="OK",
        payload={
            "artifact_type": artifact_type,
            "source_artifact_id": source_artifact_id,
            "idea_id": idea_id,
            "provider_id": provider_id,
            "task_requirement": dict(task_requirement or {}),
        },
    )


def record_generation_completed(
    logger: Any,
    *,
    artifact: Any,
    context: Any = None,
    provider_id: str | None = None,
    approval_request: Any = None,
    source: str = "product",
) -> Event | None:
    """生成完成 (Artifact 产出 + Lineage 记录; product.generation.completed)。

    payload: artifact_id/artifact_type/provider_id/confidence/source_events
    (Lineage 摘要) + approval_request_id (PRD/UI mandatory 自动审批锚点,
    生成后等待人工批准)。result=OK。
    """
    if logger is None:
        return None
    payload: dict[str, Any] = {
        "artifact_id": artifact.id,
        "artifact_type": artifact.type,
        "provider_id": provider_id or artifact.provider_id,
        "confidence": artifact.confidence,
        "source_events": artifact.source_events,
        "idea_id": (
            artifact.content.get("idea_id")
            if isinstance(artifact.content, dict) else None
        ),
    }
    if context is not None:
        payload["generation_time"] = getattr(context, "generation_time", None)
    if approval_request is not None:
        payload["approval_request_id"] = approval_request.id
        payload["approval_status"] = approval_request.status
    return logger.record(
        EventType.PRODUCT_GENERATION_COMPLETED,
        source=source,
        stage=artifact.status,
        action="generate product artifact",
        result="OK",
        payload=payload,
    )


def record_generation_failed(
    logger: Any,
    *,
    artifact_type: str,
    source_artifact_id: str,
    error: str,
    idea_id: str | None = None,
    provider_id: str | None = None,
    source: str = "product",
) -> Event | None:
    """生成失败 (无 Provider/无 Adapter/生成失败; product.generation.failed)。

    payload: artifact_type/source_artifact_id/idea_id/provider_id/error —
    明确错误不静默 (CLI 退出码 1 + 事件审计双通道)。result=ERROR。
    """
    if logger is None:
        return None
    return logger.record(
        EventType.PRODUCT_GENERATION_FAILED,
        source=source,
        stage="failed",
        action="generate product artifact",
        result="ERROR",
        payload={
            "artifact_type": artifact_type,
            "source_artifact_id": source_artifact_id,
            "idea_id": idea_id,
            "provider_id": provider_id,
            "error": error,
        },
    )


def record_experience_recorded(
    logger: Any,
    *,
    experience: Any,
    by: str = "cli",
    source: str = "product",
) -> Event | None:
    """人工经验记录落盘 (ProductGenerator.record_experience; product.experience.recorded)。

    payload: experience_id/artifact_type/provider_id/approved/confidence/rating/
    human_feedback/by — 经验数据接口只记录不消费 (Provider 自动优化预留)。
    """
    if logger is None:
        return None
    return logger.record(
        EventType.PRODUCT_EXPERIENCE_RECORDED,
        source=source,
        stage="recorded",
        action="record generation experience",
        result="OK",
        payload={
            "experience_id": experience.id,
            "artifact_type": experience.artifact_type,
            "provider_id": experience.provider_id,
            "approved": experience.approved,
            "confidence": experience.confidence,
            "rating": experience.rating,
            "human_feedback": experience.human_feedback,
            "by": by,
        },
    )


def record_experience_viewed(
    logger: Any,
    *,
    count: int,
    artifact_type: str | None = None,
    source: str = "cli",
) -> Event | None:
    """经验清单被查看 (CLI 读命令审计, ADR-0002; source 缺省 cli)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.PRODUCT_EXPERIENCE_VIEWED,
        source=source,
        stage="viewed",
        action="view generation experiences",
        result="OK",
        payload={"count": count, "artifact_type": artifact_type},
    )
