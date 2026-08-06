"""factory-core/intelligence — Intelligence Layer (Phase 10A-1/10A-2, ADR-0030/0031)。

认知层: 模型 (Decision/DecisionOption/DecisionContext/DecisionAnalysis/
DecisionResult/RiskAssessment/Recommendation/ExperienceRecord/Evidence) +
独立数据空间三 Store (decisions/recommendations/experiences, 原子写) +
DecisionIntelligence 引擎 (10A-2: Context→Analysis→Options→Evaluation→
Recommendation→Risk→Decision Artifact, 规则评分四因素, 禁无证据, 9c Approval
复用) + 事件 (intelligence.*)。

边界铁律 (phase10a1-status.md / phase10a2-status.md):
- 只分析 + 推荐 + 解释, **不自动执行** (无 LLM/学习算法 — 10A-3/10A-4)。
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
    record_experience_recorded,
    record_intelligence_viewed,
    record_recommendation_created,
)
from .models import (
    DEFAULT_HALF_LIFE_DAYS,
    ApprovalBinding,
    Decision,
    DecisionAnalysis,
    DecisionContext,
    DecisionOption,
    DecisionResult,
    DecisionStatus,
    Evidence,
    EvidenceSource,
    ExperienceDomain,
    ExperienceRecord,
    ExperienceResult,
    Recommendation,
    RiskAssessment,
    RiskLevel,
    decay_freshness,
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
    "record_experience_recorded",
    "record_intelligence_viewed",
]
