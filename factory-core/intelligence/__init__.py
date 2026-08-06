"""factory-core/intelligence — Intelligence Layer 基础 (Phase 10A-1, ADR-0030)。

认知层基础: 模型 (Decision/Recommendation/ExperienceRecord/Evidence) + 独立
数据空间三 Store (decisions/recommendations/experiences, 原子写) + 4 事件。

边界铁律 (phase10a1-status.md):
- 只分析 + 推荐 + 解释, **不自动执行** (无引擎/LLM/学习算法, 属 10A-2~4)。
- Core 零感知: 删除本包 Factory 照常运行; 本包零顶层 imports product/providers/
  runtime (store.py 零顶层 imports events, Removal Isolation)。
- 事件经 EventLogger (唯一事实源); 智能输出全部支持 Evidence/Confidence/Lineage。
"""

from .events import (
    record_decision_created,
    record_experience_recorded,
    record_intelligence_viewed,
    record_recommendation_created,
)
from .models import (
    DEFAULT_HALF_LIFE_DAYS,
    Decision,
    DecisionStatus,
    Evidence,
    EvidenceSource,
    ExperienceDomain,
    ExperienceRecord,
    ExperienceResult,
    Recommendation,
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
    "Recommendation",
    "ExperienceRecord",
    "ExperienceDomain",
    "ExperienceResult",
    "Evidence",
    "EvidenceSource",
    "decay_freshness",
    "DEFAULT_HALF_LIFE_DAYS",
    # store
    "DecisionStore",
    "RecommendationStore",
    "ExperienceStore",
    "IntelligenceStoreError",
    "CorruptIntelligenceStoreError",
    # events
    "record_decision_created",
    "record_recommendation_created",
    "record_experience_recorded",
    "record_intelligence_viewed",
]
