"""factory-console/retrieval/unified.py — 生产统一检索助手 (S10-072 P0-A/B/C)。

所有生产检索入口经 RetrievalOrchestrator (统一 Policy/Dedup/Rank/Top-K/Budget),
并保持 ExperienceRecord 语义 (兼容现有调用方)。

用法:
    from ...retrieval.unified import retrieve_experience
    records = retrieve_experience(query, store=store, top_k=3, project="demo")
"""

from __future__ import annotations

from typing import Any, List, Optional

from .models import RetrievalRequest, RetrievalSource
from .orchestrator import RetrievalOrchestrator
from .retriever import ExperienceRetriever as OrchestratedExperienceRetriever


def retrieve_experience(
    query: str,
    store: Any = None,
    *,
    top_k: int = 5,
    project: Optional[str] = None,
    max_tokens: int = 8000,
    record_type: Optional[str] = None,
    extra_sources: Optional[list] = None,
    records: Optional[list] = None,
) -> tuple[List[Any], dict]:
    """统一经验检索入口 (S10-072): 经 RetrievalOrchestrator → ExperienceRecord。

    - 替代各生产入口直接调 ExperienceRetriever.search
    - store 或 records 至少其一 (records 优先 — 内存记录场景)
    - 返回 (records, stats): records 保持 ExperienceRecord 语义 (兼容调用方)
    - stats: candidates/selected/discarded/estimated_tokens/max_tokens/latency
    - 失败安全: Orchestrator 异常 → 空结果 (不阻断业务)
    """
    try:
        orch = RetrievalOrchestrator()
        orch.register(RetrievalSource.EXPERIENCE,
                      OrchestratedExperienceRetriever(memory_store=store, records=records))
        for src, retriever in (extra_sources or []):
            orch.register(src, retriever)
        request = RetrievalRequest(
            query=str(query or ""),
            project_id=project or None,
            top_k=max(0, int(top_k)),
            max_tokens=int(max_tokens),
        )
        candidates, stats = orch.retrieve(request)
        # RetrievalCandidate → ExperienceRecord (原记录优先: store.get 或 records 匹配)
        result_records: List[Any] = []
        _recs_by_id = {getattr(r, "id", ""): r for r in (records or [])}
        for c in candidates:
            rec = None
            if store is not None and hasattr(store, "get") and c.source_id:
                try:
                    rec = store.get(c.source_id)
                except Exception:  # noqa: BLE001
                    rec = None
            if rec is None and c.source_id in _recs_by_id:
                rec = _recs_by_id[c.source_id]
            if rec is not None:
                result_records.append(rec)
            else:
                from ..memory.experience import ExperienceRecord

                result_records.append(ExperienceRecord(
                    id=c.source_id,
                    type=str(c.metadata.get("type", "DEBUG_EXPERIENCE")),
                    problem=c.content,
                    confidence=c.score,
                    success=bool(c.metadata.get("success", True)),
                    source="retrieval_orchestrator",
                    project=project or "",
                ))
        # 可选类型过滤 (兼容旧调用方 record_type 语义)
        if record_type:
            result_records = [r for r in result_records if getattr(r, "type", "") == record_type]
        return result_records, stats
    except Exception:  # noqa: BLE001 — 失败安全
        return [], {"candidates_count": 0, "selected_count": 0, "discarded_count": 0,
                    "estimated_tokens": 0, "max_tokens": max_tokens, "latency": 0.0}
