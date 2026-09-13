"""factory-console/retrieval/orchestrator.py — 统一检索编排器 (S10-070)。

多来源注册 → 并发/顺序检索 → 去重 → 排序 → Top-K → Context Budget。
避免每个 Agent 各查一遍 RAG (设计 §9)。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .models import RetrievalCandidate, RetrievalRequest, RetrievalSource
from .retriever import Retriever


def _estimate_tokens(text: str) -> int:
    """粗估 token (中文 1 字 ≈ 1 token, 英文 1 词 ≈ 1 token)。"""
    return max(1, len(str(text or "")) // 2)


class RetrievalOrchestrator:
    """统一检索编排: 注册 → 检索 → 去重 → 排序 → Top-K → Budget。"""

    def __init__(self, max_context_tokens: int = 12000) -> None:
        self._retrievers: Dict[RetrievalSource, Retriever] = {}
        self.max_context_tokens = max_context_tokens

    def register(self, source_type: RetrievalSource, retriever: Retriever) -> None:
        """注册来源 (ExternalRAGRetriever 未来同接口)。"""
        self._retrievers[source_type] = retriever

    def registered_sources(self) -> List[str]:
        return [s.value for s in self._retrievers]

    def retrieve(self, request: RetrievalRequest) -> tuple[List[RetrievalCandidate], Dict[str, Any]]:
        """多来源 → 去重 → 排序 → Top-K → Budget → (candidates, stats)。"""
        start = _now()
        all_candidates: List[RetrievalCandidate] = []
        if request.source_type is not None:
            sources = [request.source_type]
        else:
            sources = [s for s in self._retrievers]
        for source_type in sources:
            retriever = self._retrievers.get(source_type)
            if retriever is None:
                continue
            try:
                hits = retriever.retrieve(request)
                all_candidates.extend(hits)
            except Exception:  # noqa: BLE001 — 单来源失败不阻断
                continue

        # 去重 (source_type + source_id)
        seen: set = set()
        unique: List[RetrievalCandidate] = []
        for c in all_candidates:
            key = (c.source_type.value, c.source_id)
            if key in seen:
                continue
            seen.add(key)
            unique.append(c)

        # 排序 (score 降序; 同分: experience > audit > project)
        order = {RetrievalSource.EXPERIENCE: 0, RetrievalSource.AUDIT: 1,
                 RetrievalSource.PROJECT: 2, RetrievalSource.KNOWLEDGE: 3,
                 RetrievalSource.EXTERNAL_RAG: 4}
        unique.sort(key=lambda c: (-c.score, order.get(c.source_type, 9)))

        # Top-K
        k = max(0, request.top_k or 5)
        top = unique[:k]

        # Context Budget
        selected: List[RetrievalCandidate] = []
        total_tokens = 0
        budget = request.max_tokens or self.max_context_tokens
        discarded = 0
        for c in top:
            t = _estimate_tokens(c.content)
            if total_tokens + t > budget:
                discarded += 1
                continue
            selected.append(c)
            total_tokens += t

        stats = {
            "candidates_count": len(unique),
            "selected_count": len(selected),
            "discarded_count": discarded + max(0, len(unique) - k),
            "estimated_tokens": total_tokens,
            "max_tokens": budget,
            "latency": _elapsed(start),
        }
        return selected, stats


def _now() -> float:
    import time
    return time.monotonic()


def _elapsed(start: float) -> float:
    import time
    return round(time.monotonic() - start, 4)
