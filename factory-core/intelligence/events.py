"""factory-core/intelligence/events.py — intelligence.* 事件辅助 (经 EventLogger)。

设计依据:
- phase10a1-status.md §范围 (4 事件): intelligence.decision.created /
  intelligence.recommendation.created / intelligence.experience.recorded /
  intelligence.viewed — 全部经 EventLogger (唯一事实源, phase10a-plan §4)。
- ADR-0001 决策 1 扩展路径: EventType 枚举加成员即可 (events/models.py 已扩展);
  logger 为 None 时全部静默 (同 understanding/events.py 模式)。
- ADR-0002: 所有 CLI 行为必须产生 Event — viewed 为读命令审计 (source="cli",
  本阶段无 CLI, 辅助函数为 10A-5 CLI 预留; 写路径事件 source="intelligence")。
- 只记录不执行: 事件只审计落库事实, 不触发任何执行/选择 (10A-2~4 引擎另实现)。

payload 契约 (事件唯一事实源: 从事件 payload 可重建落库对象的关键字段)。
"""

from __future__ import annotations

from typing import Any

from events.models import Event, EventType


def record_decision_created(
    logger: Any,
    *,
    decision: Any,
    source: str = "intelligence",
) -> Event | None:
    """Decision 落库 (intelligence.decision.created; AI 推荐产物, ≠ approval.*)。

    10A-2 扩展: payload 追加 risk_level/requires_approval (决策链终事件 —
    事件唯一事实源: 从 payload 可重建风险等级与审批需求)。
    """
    if logger is None:
        return None
    return logger.record(
        EventType.INTELLIGENCE_DECISION_CREATED,
        source=source,
        stage=decision.status.value,
        action="create intelligence decision",
        result="OK",
        payload={
            "decision_id": decision.id,
            "decision_type": decision.decision_type,
            "subject_id": decision.subject_id,
            "recommendation": decision.recommendation,
            "confidence": decision.confidence,
            "risk": decision.risk,
            "risk_level": decision.risk_level,
            "requires_approval": decision.requires_approval,
            "evidence_count": len(decision.evidence),
            "approval_request_id": decision.approval_request_id,
        },
    )


def record_decision_analysis_started(
    logger: Any,
    *,
    context: Any,
    source: str = "intelligence",
) -> Event | None:
    """决策分析开始 (intelligence.decision.analysis.started; 决策链第 1 事件)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.INTELLIGENCE_DECISION_ANALYSIS_STARTED,
        source=source,
        stage="analysis",
        action="start decision analysis",
        result="OK",
        payload={
            "subject_id": context.subject,
            "decision_type": context.decision_type,
            "option_count": len(context.available_options),
            "evidence_count": len(context.evidence_sources),
        },
    )


def record_decision_analysis_completed(
    logger: Any,
    *,
    analysis: Any,
    context: Any,
    source: str = "intelligence",
) -> Event | None:
    """决策分析完成 (intelligence.decision.analysis.completed; 载荷含因素/观察/置信度)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.INTELLIGENCE_DECISION_ANALYSIS_COMPLETED,
        source=source,
        stage="analysis",
        action="complete decision analysis",
        result="OK",
        payload={
            "subject_id": context.subject,
            "decision_type": context.decision_type,
            "factors": analysis.factors,
            "observations_count": len(analysis.observations),
            "confidence": analysis.confidence,
            "evidence_count": len(analysis.evidence),
        },
    )


def record_decision_option_evaluated(
    logger: Any,
    *,
    option: Any,
    context: Any,
    source: str = "intelligence",
) -> Event | None:
    """选项规则评分完成 (intelligence.decision.option.evaluated; 每选项一条)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.INTELLIGENCE_DECISION_OPTION_EVALUATED,
        source=source,
        stage="evaluation",
        action="evaluate decision option",
        result="OK",
        payload={
            "subject_id": context.subject,
            "option_id": option.id,
            "name": option.name,
            "score": option.score,
            "factors": option.factors,
            "reasoning_count": len(option.reasoning),
            "evidence_count": len(option.evidence),
        },
    )


def record_recommendation_created(
    logger: Any,
    *,
    recommendation: Any,
    source: str = "intelligence",
) -> Event | None:
    """Recommendation 落库 (intelligence.recommendation.created; 推荐+解释, 不自动执行)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.INTELLIGENCE_RECOMMENDATION_CREATED,
        source=source,
        stage="recommended",
        action="create intelligence recommendation",
        result="OK",
        payload={
            "recommendation_id": recommendation.id,
            "target_type": recommendation.target_type,
            "target_id": recommendation.target_id,
            "score": recommendation.score,
            "confidence": recommendation.confidence,
            "risk": recommendation.risk,
            "reasoning_count": len(recommendation.reasoning),
            "evidence_count": len(recommendation.evidence),
        },
    )


def record_experience_recorded(
    logger: Any,
    *,
    experience: Any,
    source: str = "intelligence",
) -> Event | None:
    """经验记录落库 (intelligence.experience.recorded; 只记录不消费, 学习算法属 10A-4)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.INTELLIGENCE_EXPERIENCE_RECORDED,
        source=source,
        stage="recorded",
        action="record intelligence experience",
        result=experience.result.value.upper(),
        payload={
            "experience_id": experience.id,
            "domain": experience.domain.value,
            "subject_id": experience.subject_id,
            "result": experience.result.value,
            "score": experience.score,
            "confidence": experience.confidence,
        },
    )


def record_intelligence_viewed(
    logger: Any,
    *,
    view: str,
    count: int,
    source: str = "cli",
) -> Event | None:
    """Intelligence 数据被查看 (intelligence.viewed; 读命令审计, ADR-0002; source 缺省 cli)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.INTELLIGENCE_VIEWED,
        source=source,
        stage="viewed",
        action="view intelligence data",
        result="OK",
        payload={"view": view, "count": count},
    )
