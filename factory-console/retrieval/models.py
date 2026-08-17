"""factory-console/retrieval/models.py — Retrieval abstraction 数据模型 (S10-070 G5)。

统一检索模型: RetrievalRequest (请求契约) / RetrievalCandidate (候选结果) /
RetrievalScore (评分视图) / RetrievalSource (来源枚举) — 多来源 (经验/审计/
项目资产/知识库/外部 RAG) 编排的单一事实来源。

设计: docs/sprint10/S10-070-gap-design.md §三.5 (G5 Retrieval abstraction)
边界:
- 纯标准库 (dataclasses/enum), 零新依赖
- 确定性: 排序/去重键稳定 (source_type + source_id)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

__all__ = [
    "RetrievalSource",
    "RetrievalRequest",
    "RetrievalCandidate",
    "RetrievalScore",
]


class RetrievalSource(str, Enum):
    """检索来源枚举 (G5): 统一来源标识 — 注册/编排/去重基础。"""

    EXPERIENCE = "experience"      # 经验库 (memory/experience_store.json)
    AUDIT = "audit"                # 审计事件 (audit/audit_events.json)
    PROJECT = "project"            # 项目资产 (projects/<slug>/*)
    KNOWLEDGE = "knowledge"        # 知识库 (未来)
    EXTERNAL_RAG = "external_rag"  # 外部 RAG (未来)

    def __str__(self) -> str:  # pragma: no cover — 展示友好
        return self.value


@dataclass
class RetrievalRequest:
    """检索请求 (G5): 统一查询契约 — orchestrator 消费。

    query: 查询文本 (关键词/自然语言); source_type: 限定来源 (None = 全部);
    project_id: 项目过滤 (Audit/Project 检索用); top_k: 排序后截断数
    (<=0 → 不截断); max_tokens: Context Budget 上限 (<=0 → 无限制);
    filters: 扩展过滤 (type/event_type/agent_id 等, 各 Retriever 自行消费)。
    """

    query: str = ""
    source_type: Optional[RetrievalSource] = None
    project_id: str = ""
    top_k: int = 10
    max_tokens: int = 2048
    filters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """→ dict (调试/审计视图)。"""
        return {
            "query": self.query,
            "source_type": str(self.source_type) if self.source_type else None,
            "project_id": self.project_id,
            "top_k": self.top_k,
            "max_tokens": self.max_tokens,
            "filters": dict(self.filters),
        }


@dataclass
class RetrievalCandidate:
    """检索候选 (G5): 单条结果 — 统一结构 (content/source/score/metadata)。

    content: 文本内容 (进 LLM Context 的正文); source_type: 来源枚举;
    source_id: 来源内唯一 id (去重键); score: 0-1 相关度 (排序键);
    metadata: 扩展信息 (project/type/created_at/confidence 等)。
    """

    content: str
    source_type: RetrievalSource
    source_id: str
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def dedupe_key(self) -> tuple[str, str]:
        """去重键 (source_type + source_id) — orchestrator 去重基础。"""
        return (str(self.source_type), str(self.source_id))

    def to_dict(self) -> dict[str, Any]:
        """→ dict (审计/展示视图)。"""
        return {
            "content": self.content,
            "source_type": str(self.source_type),
            "source_id": self.source_id,
            "score": round(float(self.score), 4),
            "metadata": dict(self.metadata),
        }


@dataclass
class RetrievalScore:
    """评分视图 (G5): 候选 + 评分 + 排名 (排序后产物)。

    candidate: 候选; score: 排序评分 (归一 0-1); rank: 1-based 排名。
    """

    candidate: RetrievalCandidate
    score: float = 0.0
    rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        """→ dict (审计/展示视图)。"""
        return {
            "rank": self.rank,
            "score": round(float(self.score), 4),
            "candidate": self.candidate.to_dict(),
        }
