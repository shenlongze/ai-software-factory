"""factory-console/session/debug/context_budget.py — ContextBudget (S10-068 Part 2, G7)。

Context Budget: 不让 Memory 检索结果全量进 LLM — estimate_tokens 估算 +
fit (Top-K + 截断保 max_tokens) + stats (审计口径)。

设计: docs/sprint10/S10-068-part2-design.md §6
边界:
- 纯标准库, 零模块依赖; 估算启发式 (len/4 — 中文/英文混合近似), 非精确 tokenizer
- fit 失败安全: 空输入 → []; max_tokens<=0 → 全部候选 (无预算限制)
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

#: 启发式: 每 token 约 4 字符 (中文/英文混合近似; 无 tokenizer 依赖)
_CHARS_PER_TOKEN = 4.0


def _record_text(record: Any) -> str:
    """记录 → 估算文本 (对象 to_dict / dict json / 字符串原样)。"""
    if hasattr(record, "to_dict"):
        return json.dumps(record.to_dict(), ensure_ascii=False)
    if isinstance(record, dict):
        return json.dumps(record, ensure_ascii=False)
    return str(record)


class ContextBudget:
    """Token 预算 (G7): estimate_tokens / fit / stats。

    estimate_tokens(text) -> int: 字符数/4 估算 (空 → 0, 非空至少 1);
    fit(records, max_tokens) -> list: 按给定顺序贪心选取, 累计估算 token
      不超过 max_tokens (至少保留 1 条 — 保证检索结果不为空);
    stats(candidates, selected, *, max_tokens, latency) -> dict:
      {candidates_count, selected_count, discarded_count, estimated_tokens,
       max_tokens, latency} — 审计/展示口径。
    """

    def estimate_tokens(self, text: Any) -> int:
        """文本 token 估算 (启发式 len/4; 空 → 0; 非空至少 1)。"""
        content = str(text or "")
        if not content.strip():
            return 0
        return max(1, int(len(content) / _CHARS_PER_TOKEN))

    def fit(self, records: Any, max_tokens: int = 2048) -> list[Any]:
        """Top-K + 截断: 累计估算 token <= max_tokens (至少保留 1 条)。

        records: 候选记录列表 (对象/dict/str 均可); max_tokens<=0 → 全部返回
        (无预算限制); 单条超预算 → 仍保留 (至少 1 条, 检索结果不为空)。
        """
        items = list(records or [])
        limit = int(max_tokens or 0)
        if limit <= 0:
            return items
        selected: list[Any] = []
        total = 0
        for item in items:
            tokens = self.estimate_tokens(_record_text(item))
            if selected and total + tokens > limit:
                break
            selected.append(item)
            total += tokens
        return selected

    def stats(
        self,
        candidates: Any,
        selected: Any,
        *,
        max_tokens: int = 0,
        latency: Optional[float] = None,
    ) -> dict[str, Any]:
        """统计 (审计口径): candidates/selected/discarded/tokens/max_tokens/latency。"""
        cands = list(candidates or [])
        picked = list(selected or [])
        selected_ids = {
            (getattr(r, "id", None) or (r.get("id") if isinstance(r, dict) else None))
            for r in picked
        }
        discarded = [
            r for r in cands
            if (getattr(r, "id", None) or (r.get("id") if isinstance(r, dict) else None))
            not in selected_ids
        ]
        return {
            "candidates_count": len(cands),
            "selected_count": len(picked),
            "discarded_count": len(discarded),
            "estimated_tokens": sum(
                self.estimate_tokens(_record_text(r)) for r in picked
            ),
            "max_tokens": int(max_tokens or 0),
            "latency": float(latency) if latency is not None else 0.0,
        }
