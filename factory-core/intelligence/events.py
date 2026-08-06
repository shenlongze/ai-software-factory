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


def record_recommendation_started(
    logger: Any,
    *,
    context: Any,
    source: str = "intelligence",
) -> Event | None:
    """推荐开始 (intelligence.recommendation.started; 推荐链第 1 事件)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.INTELLIGENCE_RECOMMENDATION_STARTED,
        source=source,
        stage="recommending",
        action="start recommendation",
        result="OK",
        payload={
            "task_type": context.task_type,
            "required_capabilities": list(context.required_capabilities),
            "candidate_count": len(context.candidates),
            "budget": context.budget,
            "quality_target": context.quality_target,
            "constraint_count": len(context.constraints),
        },
    )


def record_recommendation_candidate_evaluated(
    logger: Any,
    *,
    evaluation: Any,
    context: Any,
    source: str = "intelligence",
) -> Event | None:
    """候选评分完成 (intelligence.recommendation.candidate.evaluated; 每候选一条)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.INTELLIGENCE_RECOMMENDATION_CANDIDATE_EVALUATED,
        source=source,
        stage="evaluating",
        action="evaluate recommendation candidate",
        result="OK",
        payload={
            "task_type": context.task_type,
            "candidate_id": evaluation.candidate_id,
            "candidate_type": evaluation.candidate_type,
            "score": evaluation.score,
            "factors": evaluation.factors,
            "experience_records": evaluation.experience_records,
            "experience_source": evaluation.experience_source,
        },
    )


def record_recommendation_explained(
    logger: Any,
    *,
    result: Any,
    source: str = "intelligence",
) -> Event | None:
    """推荐解释生成 (intelligence.recommendation.explained; 载荷含分项计数)。"""
    if logger is None:
        return None
    positives = sum(1 for r in result.reasoning if r.direction.value == "positive")
    negatives = sum(1 for r in result.reasoning if r.direction.value == "negative")
    neutrals = sum(1 for r in result.reasoning if r.direction.value == "neutral")
    return logger.record(
        EventType.INTELLIGENCE_RECOMMENDATION_EXPLAINED,
        source=source,
        stage="explained",
        action="explain recommendation",
        result="OK",
        payload={
            "top_candidate_id": result.top_candidate_id,
            "score": result.score,
            "reasoning_count": len(result.reasoning),
            "positive_count": positives,
            "negative_count": negatives,
            "neutral_count": neutrals,
            "risk_reason_count": len(result.risk_reasons),
        },
    )


def record_recommendation_completed(
    logger: Any,
    *,
    result: Any,
    decision_id: str | None = None,
    source: str = "intelligence",
) -> Event | None:
    """推荐完成 (intelligence.recommendation.completed; 链终事件)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.INTELLIGENCE_RECOMMENDATION_COMPLETED,
        source=source,
        stage="recommended",
        action="complete recommendation",
        result="OK",
        payload={
            "recommendation_id": result.id,
            "top_candidate_id": result.top_candidate_id,
            "score": result.score,
            "confidence": result.confidence,
            "risk_level": result.risk_level,
            "requires_approval": result.requires_approval,
            "candidate_count": len(result.evaluations),
            "filtered_count": len(result.filtered_candidates),
            "decision_id": decision_id,
        },
    )


# ------------------------------------------------------------------ 10A-4 Experience Loop 事件 (ADR-0033)


def record_experience_analyzed(
    logger: Any,
    *,
    analysis: Any,
    source: str = "intelligence",
) -> Event | None:
    """经验分析完成 (intelligence.experience.analyzed; ExperienceAnalyzer 只读聚合)。

    载荷含 subject 维度 + 聚合统计 (record_count/success_rate/effective_score)
    — 事件唯一事实源: 从 payload 可重建单主体经验分析结果的关键字段。
    """
    if logger is None:
        return None
    agg = analysis.aggregation
    return logger.record(
        EventType.INTELLIGENCE_EXPERIENCE_ANALYZED,
        source=source,
        stage="analyzed",
        action="analyze intelligence experience",
        result="OK",
        payload={
            "subject_id": analysis.subject_id,
            "subject_type": analysis.subject_type,
            "task_type": analysis.task_type,
            "capability": list(analysis.capability),
            "record_count": agg.record_count,
            "success_count": agg.success_count,
            "failure_count": agg.failure_count,
            "success_rate": agg.success_rate,
            "effective_score": agg.effective_score,
        },
    )


def record_task_evaluated(
    logger: Any,
    *,
    evaluation: Any,
    source: str = "intelligence",
) -> Event | None:
    """任务评估完成 (intelligence.task.evaluated; TaskEvaluator 推荐执行资源)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.INTELLIGENCE_TASK_EVALUATED,
        source=source,
        stage="evaluated",
        action="evaluate task",
        result="OK",
        payload={
            "task_type": evaluation.task_type,
            "required_capabilities": list(evaluation.required_capabilities),
            "recommended_agent_count": len(evaluation.recommended_agents),
            "recommended_provider_count": len(evaluation.recommended_providers),
            "recommended_skill_count": len(evaluation.recommended_skills),
            "confidence": evaluation.confidence,
            "risk_count": len(evaluation.risks),
        },
    )


def record_feedback_learned(
    logger: Any,
    *,
    experience: Any,
    source: str = "intelligence",
) -> Event | None:
    """反馈闭环 (intelligence.feedback.learned; 执行结果 → 经验记录落库)。

    Feedback Loop 链终事件: Task→Recommendation→Execution→Result→Experience
    (经验是未来推荐的依据; 只记录不执行, 不修改任何权重/配置 — 经验分析
    非自我修改)。
    """
    if logger is None:
        return None
    return logger.record(
        EventType.INTELLIGENCE_FEEDBACK_LEARNED,
        source=source,
        stage="learned",
        action="learn from execution feedback",
        result=experience.result.value.upper(),
        payload={
            "experience_id": experience.id,
            "domain": experience.domain.value,
            "subject_type": experience.subject_type,
            "subject_id": experience.subject_id,
            "task_type": experience.task_type,
            "capability": list(experience.capability),
            "result": experience.result.value,
            "score": experience.score,
            "confidence": experience.confidence,
            "negative_signal": experience.negative_signal,
        },
    )
