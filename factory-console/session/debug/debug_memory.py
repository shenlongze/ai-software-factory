"""factory-console/session/debug/debug_memory.py — DebugExperienceRetriever (S10-068 G5)。

历史经验检索: DebugCase → Memory Top-K (S10-067 ExperienceRetriever 复用)。

设计: docs/sprint10/S10-068-debug-intelligence-design.md §5
复用: factory-console/memory/retrieval.py ExperienceRetriever.search +
      factory-console/memory/experience.py (DEBUG_EXPERIENCE/FAILURE_PATTERN)
边界:
- 纯标准库; 只读复用 Memory (不修改 S10-067)
- 接口预留: retrieve 签名不变, 未来 embedding/hybrid 换实现 (不引入 Vector DB)
- 失败安全: 空库/空查询 → [] (不抛); 单条损坏 → 跳过
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ...memory.experience import (
    DEBUG_EXPERIENCE,
    FAILURE_PATTERN,
    SUCCESS_PATTERN,
)
from ...memory.experience_store import DEFAULT_WORKSPACE, ExperienceStore
from ...memory.retrieval import ExperienceRetriever
from . import DebugCase

#: 检索类型 (调试经验 + 失败模式 + 成功模式 — Feedback Loop 闭环:
#: 成功修复沉淀的 SUCCESS_PATTERN 也必须可被检索, 才能命中 FIX_CODE 先例)
_RETRIEVE_TYPES: tuple[str, ...] = (
    DEBUG_EXPERIENCE,
    FAILURE_PATTERN,
    SUCCESS_PATTERN,
)

#: 缺省 Top-K
DEFAULT_TOP_K = 3


class DebugExperienceRetriever:
    """调试经验检索器 (G5): Top-K 检索 + 排序 + 去重。

    retrieve(debug_case, *, top_k=3, memory_store=None) -> list[ExperienceRecord]:
      1) 查询面: error_message + task_id + context (关键词检索);
      2) 类型: DEBUG_EXPERIENCE + FAILURE_PATTERN (分别检索后合并);
      3) 项目过滤: debug_case.project (非空时);
      4) Top-K 排序: confidence 降序 (同 confidence → created_at 降序) + 按 id 去重。
    """

    def __init__(self, workspace: Any = None) -> None:
        self.workspace = Path(workspace) if workspace is not None else DEFAULT_WORKSPACE

    def retrieve(
        self,
        debug_case: Any,
        *,
        top_k: int = DEFAULT_TOP_K,
        memory_store: Any = None,
    ) -> list[Any]:
        """DebugCase → 相关历史经验 (Top-K, confidence 降序, 去重)。

        memory_store: ExperienceStore 实例 (缺省 → workspace 装配); 检索失败
        (库损坏等) → 空结果, 不抛 — 失败安全 (调试流程不被 Memory 阻断)。
        """
        case = debug_case if isinstance(debug_case, DebugCase) else DebugCase.from_dict(debug_case)
        k = max(0, int(top_k or 0))
        try:
            store = (
                memory_store
                if memory_store is not None
                else ExperienceStore.from_workspace(self.workspace)
            )
            retriever = ExperienceRetriever(store)
            query = " ".join(
                part
                for part in (case.error_message, case.task_id, case.context)
                if part
            )
            hits: list[Any] = []
            for record_type in _RETRIEVE_TYPES:
                hits.extend(
                    retriever.search(
                        query=query,
                        type=record_type,
                        project=case.project or None,
                    )
                )
        except Exception:  # noqa: BLE001 — 失败安全: Memory 异常 → 空结果
            return []

        # 去重 (同 id 保留最高 confidence) + Top-K 排序 (confidence/created_at 降序)
        seen: dict[str, Any] = {}
        for record in hits:
            record_id = getattr(record, "id", None) or ""
            if record_id not in seen or record.confidence > seen[record_id].confidence:
                seen[record_id] = record
        ranked = sorted(
            seen.values(),
            key=lambda r: (r.confidence, r.created_at),
            reverse=True,
        )
        return ranked[:k] if k else []
