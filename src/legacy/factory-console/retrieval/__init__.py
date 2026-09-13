"""factory-console/retrieval/ — 统一检索抽象 (S10-070)。

多 RAG / 多 Memory 来源统一入口:
  RetrievalRequest → RetrievalOrchestrator (注册/去重/排序/Top-K/Budget)
  → [RetrievalCandidate] + stats

来源: EXPERIENCE (Memory) / AUDIT (审计) / PROJECT (项目) /
       KNOWLEDGE (知识库) / EXTERNAL_RAG (未来扩展)。
"""

from __future__ import annotations

from .models import (
    RetrievalCandidate,
    RetrievalRequest,
    RetrievalScore,
    RetrievalSource,
)
from .external_source import (
    MockExternalSource,
    clear_external_sources,
    configured_external_sources,
    get_external_sources,
    register_external_source,
)
from .knowledge_store import (
    IngestResult,
    KnowledgeHit,
    KnowledgeStore,
    rag_query,
)
from .orchestrator import RetrievalOrchestrator
from .retriever import (
    AuditRetriever,
    ExperienceRetriever,
    ProjectRetriever,
    Retriever,
)

__all__ = [
    "RetrievalCandidate",
    "RetrievalRequest",
    "RetrievalScore",
    "RetrievalSource",
    "RetrievalOrchestrator",
    "Retriever",
    "ExperienceRetriever",
    "AuditRetriever",
    "ProjectRetriever",
    "KnowledgeStore",
    "KnowledgeHit",
    "IngestResult",
    "rag_query",
    "MockExternalSource",
    "register_external_source",
    "get_external_sources",
    "clear_external_sources",
    "configured_external_sources",
]
