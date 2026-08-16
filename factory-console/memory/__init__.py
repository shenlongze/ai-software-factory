"""factory-console/memory/ — Memory Learning & Experience Intelligence (S10-067)。

完整学习循环: Execution → Observation → Learning → Pattern Extraction →
Future Recommendation。

组件 (GAP G1-G8):
- experience.py        — ExperienceRecord 模型 + 6 类型 (G1)
- experience_store.py  — 持久化 experience_store.json (G2)
- extraction.py        — 自动提取 (execution_records/repair/replanning/gap/
  validation → 经验) (G3)
- learning_engine.py   — PatternLearner (模式 + confidence) + LearningEngine
  (学习循环) (G4/G6)
- retrieval.py         — ExperienceRetriever (关键词检索 + 相似项目) (G5)
- recommendation.py    — Recommender (planning/debug 提醒 — 影响未来) (G7)
- learning_trace.py    — LearningTrace (learning_trace.json 审计) (G8)

设计: docs/sprint10/S10-067-memory-learning-design.md
边界: 纯标准库, 零新依赖; 失败安全 (缺失/损坏 → 空, 不抛); 关键词+规则
检索 (不引入向量数据库/embedding — GAP 五不该)。
"""

from .experience import (
    AGENT_EXPERIENCE,
    DEBUG_EXPERIENCE,
    FAILURE_PATTERN,
    PLANNING_EXPERIENCE,
    SUCCESS_PATTERN,
    TYPES,
    USER_FEEDBACK,
    ExperienceRecord,
    ensure_type,
    make_record_id,
)
from .experience_store import (
    DEFAULT_WORKSPACE,
    EXPERIENCE_STORE_FILE_NAME,
    ExperienceStore,
    experience_store_file,
    memory_dir,
)
from .extraction import ExperienceExtractor
from .learning_engine import (
    AgentProfile,
    LearningEngine,
    LearningResult,
    Pattern,
    PatternLearner,
)
from .learning_trace import LEARNING_TRACE_FILE_NAME, LearningTrace
from .recommendation import Recommender
from .retrieval import ExperienceRetriever

__all__ = [
    "AGENT_EXPERIENCE",
    "AgentProfile",
    "DEBUG_EXPERIENCE",
    "DEFAULT_WORKSPACE",
    "EXPERIENCE_STORE_FILE_NAME",
    "ExperienceExtractor",
    "ExperienceRecord",
    "ExperienceRetriever",
    "ExperienceStore",
    "FAILURE_PATTERN",
    "LEARNING_TRACE_FILE_NAME",
    "LearningEngine",
    "LearningResult",
    "LearningTrace",
    "PLANNING_EXPERIENCE",
    "Pattern",
    "PatternLearner",
    "Recommender",
    "SUCCESS_PATTERN",
    "TYPES",
    "USER_FEEDBACK",
    "ensure_type",
    "experience_store_file",
    "make_record_id",
    "memory_dir",
]
