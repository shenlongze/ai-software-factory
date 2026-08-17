"""factory-console/retrieval/retriever.py — 统一检索器抽象 (S10-070)。

Retriever Protocol + 具体实现: ExperienceRetriever (Memory) /
AuditRetriever (Audit) / ProjectRetriever (项目资产)。
ExternalRAGRetriever 未来扩展点 (RetrievalSource.EXTERNAL_RAG)。
"""

from __future__ import annotations

from typing import Any, List, Optional, Protocol, runtime_checkable

from .models import RetrievalCandidate, RetrievalRequest, RetrievalSource


@runtime_checkable
class Retriever(Protocol):
    """检索器协议: retrieve(request) -> list[RetrievalCandidate]。"""

    def retrieve(self, request: RetrievalRequest) -> List[RetrievalCandidate]:
        ...


def _match(query: str, text: str) -> bool:
    """宽松关键词匹配 (query 任一 token ∈ text)。"""
    q = str(query or "").strip()
    if not q:
        return True
    tokens = [t for t in q.replace("，", " ").replace(",", " ").split() if t]
    if not tokens:
        return True
    return any(t in str(text or "") for t in tokens)


class ExperienceRetriever:
    """S10-067 Memory → RetrievalCandidate (DEBUG/FAILURE/SUCCESS 经验)。"""

    source_type = RetrievalSource.EXPERIENCE

    def __init__(self, memory_store: Any = None) -> None:
        self.memory_store = memory_store

    def retrieve(self, request: RetrievalRequest) -> List[RetrievalCandidate]:
        try:
            if self.memory_store is None:
                return []
            records = self.memory_store.records() if hasattr(self.memory_store, "records") else []
        except Exception:  # noqa: BLE001 — 失败安全
            return []
        candidates: List[RetrievalCandidate] = []
        for rec in records:
            problem = getattr(rec, "problem", "") or rec.get("problem", "") if isinstance(rec, dict) else getattr(rec, "problem", "")
            if not _match(request.query, problem):
                continue
            if request.project_id and getattr(rec, "project", "") and \
                    getattr(rec, "project", "") != request.project_id:
                if not isinstance(rec, dict) or rec.get("project") != request.project_id:
                    continue
            confidence = getattr(rec, "confidence", 0.0) if not isinstance(rec, dict) else rec.get("confidence", 0.0)
            candidates.append(RetrievalCandidate(
                content=str(problem),
                source_type=self.source_type,
                source_id=getattr(rec, "id", "") if not isinstance(rec, dict) else rec.get("id", ""),
                score=float(confidence),
                metadata={"type": getattr(rec, "type", "") if not isinstance(rec, dict) else rec.get("type", "")},
            ))
        return candidates


class AuditRetriever:
    """S10-069 Audit → RetrievalCandidate (审计事件摘要)。"""

    source_type = RetrievalSource.AUDIT

    def __init__(self, audit_store: Any = None) -> None:
        self.audit_store = audit_store

    def retrieve(self, request: RetrievalRequest) -> List[RetrievalCandidate]:
        try:
            if self.audit_store is None:
                return []
            events = self.audit_store.query() if hasattr(self.audit_store, "query") else []
        except Exception:  # noqa: BLE001 — 失败安全
            return []
        candidates: List[RetrievalCandidate] = []
        for ev in events:
            text = f"{getattr(ev, 'event_type', '')} {getattr(ev, 'decision_reason', '')}"
            if not _match(request.query, text):
                continue
            candidates.append(RetrievalCandidate(
                content=text.strip(),
                source_type=self.source_type,
                source_id=getattr(ev, "audit_id", ""),
                score=1.0,
                metadata={"event_type": getattr(ev, "event_type", "")},
            ))
        return candidates


class ProjectRetriever:
    """项目资产 → RetrievalCandidate (product.json 摘要)。"""

    source_type = RetrievalSource.PROJECT

    def __init__(self, workspace: Any = None) -> None:
        self.workspace = workspace

    def retrieve(self, request: RetrievalRequest) -> List[RetrievalCandidate]:
        if self.workspace is None:
            return []
        import json
        from pathlib import Path
        projects_dir = Path(self.workspace) / "projects"
        if not projects_dir.is_dir():
            return []
        candidates: List[RetrievalCandidate] = []
        try:
            for pd in sorted(projects_dir.iterdir()):
                if not pd.is_dir():
                    continue
                if request.project_id and pd.name != request.project_id:
                    continue
                pf = pd / "product.json"
                if not pf.is_file():
                    continue
                data = json.loads(pf.read_text(encoding="utf-8"))
                name = str(data.get("name", "") or pd.name)
                problem = str(data.get("problem", "") or "")
                if not _match(request.query, name + " " + problem):
                    continue
                candidates.append(RetrievalCandidate(
                    content=f"{name}: {problem[:80]}",
                    source_type=self.source_type,
                    source_id=pd.name,
                    score=0.5,
                    metadata={"project": pd.name},
                ))
        except Exception:  # noqa: BLE001 — 失败安全
            return []
        return candidates
