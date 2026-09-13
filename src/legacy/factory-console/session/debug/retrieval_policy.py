"""factory-console/session/debug/retrieval_policy.py — DebugRetrievalPolicy (S10-068 Part 2, G6)。

检索策略: 查询构建/来源选择/Top-K/重排/去重/Context Budget — 未来多 RAG 来源
扩展点 (select_sources 可扩展; 不引入 Vector DB)。

设计: docs/sprint10/S10-068-part2-design.md §5
复用 (只读): S10-067 ExperienceStore/ExperienceRetriever (Memory Top-K) +
本包 DebugExperienceRetriever 语义。

排序口径 (rank): 项目相关 > confidence > 新鲜 > 成功 > 已验证。
边界:
- 纯标准库, 零新依赖; 失败安全: 空库/空查询 → []; 单条损坏 → 跳过
- apply_budget → (selected, stats): stats 含 candidates_count/selected_count/
  discarded_count/estimated_tokens/max_tokens/latency
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

from ...memory.experience import (
    DEBUG_EXPERIENCE,
    FAILURE_PATTERN,
    SUCCESS_PATTERN,
)
from ...memory.experience_store import DEFAULT_WORKSPACE, ExperienceStore
from ...memory.retrieval import ExperienceRetriever
from .context_budget import ContextBudget

#: 检索经验类型 (调试经验 + 失败模式 + 成功模式 — Feedback Loop 闭环)
_RETRIEVE_TYPES: tuple[str, ...] = (
    DEBUG_EXPERIENCE,
    FAILURE_PATTERN,
    SUCCESS_PATTERN,
)

#: 来源标识 (select_sources 口径 — 未来多 RAG 扩展点)
SOURCE_DEBUG_EXPERIENCE = "debug_experience"
SOURCE_PROJECT_EXPERIENCE = "project_experience"
SOURCE_GLOBAL = "global"

#: 缺省 Top-K
DEFAULT_TOP_K = 3

#: 缺省 Context Budget (token)
DEFAULT_MAX_TOKENS = 2048


def _get(record: Any, key: str, default: Any = None) -> Any:
    """记录字段读取 (对象属性 / dict 键, 失败安全)。"""
    if isinstance(record, dict):
        return record.get(key, default)
    return getattr(record, key, default)


class DebugRetrievalPolicy:
    """检索策略 (G6): build_query/select_sources/retrieve/rank/deduplicate/apply_budget。

    retrieve(session, memory_store=None, top_k=3) -> list[ExperienceRecord]:
      查询面 = error_summary + task_id + project_id; 类型 = DEBUG_EXPERIENCE +
      FAILURE_PATTERN + SUCCESS_PATTERN; 项目过滤 (project_id 非空时);
      Top-K (confidence 降序) + 按 id 去重 (失败安全 → [])。
    apply_budget(candidates, max_tokens) -> (selected, stats):
      ContextBudget.fit 截断 + stats (审计口径)。
    """

    def __init__(self, workspace: Any = None) -> None:
        self.workspace = Path(workspace) if workspace is not None else DEFAULT_WORKSPACE
        self.budget = ContextBudget()

    # ------------------------------------------------------------ 查询/来源

    def build_query(self, session: Any) -> str:
        """查询面: error + task + project 特征 (空格连接, 空段跳过)。"""
        if isinstance(session, dict):
            parts = (
                str(session.get("error_summary") or ""),
                str(session.get("task_id") or ""),
                str(session.get("project_id") or ""),
            )
        else:
            parts = (
                str(getattr(session, "error_summary", "") or ""),
                str(getattr(session, "task_id", "") or ""),
                str(getattr(session, "project_id", "") or ""),
            )
        return " ".join(part for part in parts if part)

    def select_sources(self, session: Any) -> list[str]:
        """来源选择: debug_experience 优先 + project 经验 (项目非空时) + global。"""
        sources = [SOURCE_DEBUG_EXPERIENCE]
        project = (
            str(session.get("project_id") or "")
            if isinstance(session, dict)
            else str(getattr(session, "project_id", "") or "")
        )
        if project:
            sources.append(SOURCE_PROJECT_EXPERIENCE)
        sources.append(SOURCE_GLOBAL)
        return sources

    # ------------------------------------------------------------ 检索

    def retrieve(
        self,
        session: Any,
        memory_store: Any = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> list[Any]:
        """会话 → 相关历史经验 (Top-K, 去重, 失败安全 → [])。"""
        query = self.build_query(session)
        project = (
            str(session.get("project_id") or "")
            if isinstance(session, dict)
            else str(getattr(session, "project_id", "") or "")
        )
        k = max(0, int(top_k or 0))
        try:
            # S10-072 P0-C: 统一检索入口 (经 RetrievalOrchestrator, 失败 → 原逻辑)
            from ...retrieval.unified import retrieve_experience

            store = (
                memory_store
                if memory_store is not None
                else ExperienceStore.from_workspace(self.workspace)
            )
            hits, _stats = retrieve_experience(query, store=store, top_k=20, project=project)
            hits = [r for r in hits if r.type in _RETRIEVE_TYPES]
        except Exception:  # noqa: BLE001 — 失败安全: Memory 异常 → 空结果
            return []
        return self.deduplicate(self.rank(hits, session))[:k] if k else []

    # ------------------------------------------------------------ 重排/去重

    def rank(self, candidates: Any, session: Any = None) -> list[Any]:
        """重排: 项目相关 > confidence > 新鲜 > 成功 > 已验证 (降序)。"""
        project = (
            str(session.get("project_id") or "")
            if isinstance(session, dict)
            else str(getattr(session, "project_id", "") or "")
        )

        def key(record: Any) -> tuple[Any, ...]:
            project_bonus = 1 if (
                project and _get(record, "project", "") == project
            ) else 0
            return (
                project_bonus,
                float(_get(record, "confidence", 0.0) or 0.0),
                str(_get(record, "created_at", "") or ""),
                1 if _get(record, "success", False) else 0,
                1 if _get(record, "source", "") else 0,
            )

        return sorted(list(candidates or []), key=key, reverse=True)

    def deduplicate(self, candidates: Any) -> list[Any]:
        """去重: 同 id 保留最高 confidence (记录顺序稳定)。"""
        seen: dict[str, Any] = {}
        for record in list(candidates or []):
            record_id = str(_get(record, "id", "") or "")
            if not record_id:
                seen[f"__idx_{len(seen)}"] = record
                continue
            if record_id not in seen or _get(record, "confidence", 0.0) > _get(
                seen[record_id], "confidence", 0.0
            ):
                seen[record_id] = record
        return list(seen.values())

    # ------------------------------------------------------------ Context Budget

    def apply_budget(
        self,
        candidates: Any,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> tuple[list[Any], dict[str, Any]]:
        """Context Budget: 截断保 max_tokens → (selected, stats)。"""
        start = time.perf_counter()
        selected = self.budget.fit(candidates, max_tokens)
        latency = time.perf_counter() - start
        stats = self.budget.stats(
            candidates, selected, max_tokens=max_tokens, latency=latency
        )
        return selected, stats
