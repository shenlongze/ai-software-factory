"""factory-core/intelligence — Intelligence Layer (Phase 10A-1/10A-2/10A-3, ADR-0030/0031/0032)。

认知层: 模型 (Decision/DecisionOption/DecisionContext/DecisionAnalysis/
DecisionResult/RiskAssessment/Recommendation/ExperienceRecord/Evidence +
Candidate/CandidateEvaluation/RecommendationContext/RecommendationResult/
ReasoningItem) + 独立数据空间三 Store (decisions/recommendations/experiences,
原子写) + DecisionIntelligence 引擎 (10A-2: Context→Analysis→Options→
Evaluation→Recommendation→Risk→Decision Artifact, 规则评分四因素, 禁无证据,
9c Approval 复用) + RecommendationEngine 引擎 (10A-3: 多因素加权评分 +
Reasoning 解释 + Risk + Experience 集成冷启动中性 + Decision 集成) + 事件
(intelligence.*)。

边界铁律 (phase10a1-status.md / phase10a2-status.md / phase10a3-status.md):
- 只分析 + 推荐 + 解释, **不自动执行** (无 LLM/学习算法 — 10A-3 只评分推荐,
  10A-4 才做经验学习)。
- Core 零感知: 删除本包 Factory 照常运行; 本包零顶层 imports product/providers/
  runtime (store.py 零顶层 imports events, decision.py 经 duck-typed
  approval_service 复用 9c — Removal Isolation)。
- 事件经 EventLogger (唯一事实源); 智能输出全部支持 Evidence/Confidence/Lineage。
"""

from .decision import (
    CLOSE_COMPETITION_GAP,
    DEFAULT_FACTOR_WEIGHTS,
    FACTOR_KEYS,
    HIGH_RISK_DECISION_TYPES,
    HIGH_RISK_KEYWORDS,
    LOW_CONFIDENCE_THRESHOLD,
    NEUTRAL_FACTOR,
    RISK_LEVEL_TO_NUMERIC,
    DecisionIntelligence,
    DecisionIntelligenceError,
    NoEvidenceError,
    compute_confidence,
    decision_result,
    normalize_weights,
    score_option,
)
from .events import (
    record_decision_analysis_completed,
    record_decision_analysis_started,
    record_decision_created,
    record_decision_option_evaluated,
    record_experience_analyzed,
    record_experience_recorded,
    record_feedback_learned,
    record_intelligence_viewed,
    record_recommendation_candidate_evaluated,
    record_recommendation_completed,
    record_recommendation_created,
    record_recommendation_explained,
    record_recommendation_started,
    record_task_evaluated,
)
from .experience import (
    MAX_RECOMMENDED_PER_TYPE,
    RECOMMEND_THRESHOLD,
    ExperienceAnalyzer,
    aggregate_experience_factor,
    aggregate_records,
    matches_experience,
)
from .evaluate import TaskEvaluator
from .models import (
    DEFAULT_HALF_LIFE_DAYS,
    ApprovalBinding,
    Candidate,
    CandidateEvaluation,
    CandidateType,
    Decision,
    DecisionAnalysis,
    DecisionContext,
    DecisionOption,
    DecisionResult,
    DecisionStatus,
    Evidence,
    EvidenceSource,
    ExperienceAggregation,
    ExperienceAnalysis,
    ExperienceDomain,
    ExperienceRecord,
    ExperienceResult,
    Recommendation,
    RecommendationContext,
    RecommendationResult,
    ReasoningDirection,
    ReasoningItem,
    RiskAssessment,
    RiskLevel,
    TaskEvaluation,
    TaskRequirement,
    decay_freshness,
)
from .recommend import (
    CRITICAL_FACTOR_THRESHOLD,
    DEFAULT_WEIGHTS,
    LOW_FACTOR_THRESHOLD,
    NEGATIVE_THRESHOLD,
    POSITIVE_THRESHOLD,
    RECOMMEND_FACTOR_KEYS,
    NoCandidatesError,
    RecommendationEngine,
    RecommendationEngineError,
    assess_recommendation_risk,
    compute_recommendation_confidence,
    evaluate_factors,
    score_candidate,
)
from .store import (
    CorruptIntelligenceStoreError,
    DecisionStore,
    ExperienceStore,
    IntelligenceStoreError,
    RecommendationStore,
)

__all__ = [
    # models
    "Decision",
    "DecisionStatus",
    "DecisionContext",
    "DecisionOption",
    "DecisionAnalysis",
    "DecisionResult",
    "RiskAssessment",
    "RiskLevel",
    "ApprovalBinding",
    "Recommendation",
    "ExperienceRecord",
    "ExperienceDomain",
    "ExperienceResult",
    "Evidence",
    "EvidenceSource",
    "decay_freshness",
    "DEFAULT_HALF_LIFE_DAYS",
    # experience loop models (10A-4)
    "ExperienceAggregation",
    "ExperienceAnalysis",
    "TaskRequirement",
    "TaskEvaluation",
    # recommendation engine models (10A-3)
    "Candidate",
    "CandidateType",
    "CandidateEvaluation",
    "RecommendationContext",
    "RecommendationResult",
    "ReasoningItem",
    "ReasoningDirection",
    # decision engine (10A-2)
    "DecisionIntelligence",
    "DecisionIntelligenceError",
    "NoEvidenceError",
    "score_option",
    "compute_confidence",
    "decision_result",
    "normalize_weights",
    "FACTOR_KEYS",
    "DEFAULT_FACTOR_WEIGHTS",
    "NEUTRAL_FACTOR",
    "LOW_CONFIDENCE_THRESHOLD",
    "HIGH_RISK_DECISION_TYPES",
    "HIGH_RISK_KEYWORDS",
    "CLOSE_COMPETITION_GAP",
    "RISK_LEVEL_TO_NUMERIC",
    # recommendation engine (10A-3)
    "RecommendationEngine",
    "RecommendationEngineError",
    "NoCandidatesError",
    "score_candidate",
    "compute_recommendation_confidence",
    "assess_recommendation_risk",
    "evaluate_factors",
    "RECOMMEND_FACTOR_KEYS",
    "DEFAULT_WEIGHTS",
    "POSITIVE_THRESHOLD",
    "NEGATIVE_THRESHOLD",
    "LOW_FACTOR_THRESHOLD",
    "CRITICAL_FACTOR_THRESHOLD",
    # experience loop (10A-4)
    "ExperienceAnalyzer",
    "TaskEvaluator",
    "aggregate_experience_factor",
    "aggregate_records",
    "matches_experience",
    "RECOMMEND_THRESHOLD",
    "MAX_RECOMMENDED_PER_TYPE",
    # store
    "DecisionStore",
    "RecommendationStore",
    "ExperienceStore",
    "IntelligenceStoreError",
    "CorruptIntelligenceStoreError",
    # events
    "record_decision_created",
    "record_decision_analysis_started",
    "record_decision_analysis_completed",
    "record_decision_option_evaluated",
    "record_recommendation_created",
    "record_recommendation_started",
    "record_recommendation_completed",
    "record_recommendation_candidate_evaluated",
    "record_recommendation_explained",
    "record_experience_recorded",
    "record_experience_analyzed",
    "record_task_evaluated",
    "record_feedback_learned",
    "record_intelligence_viewed",
]
