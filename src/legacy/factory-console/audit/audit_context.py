"""factory-console/audit/audit_context.py — AuditContextBudget (S10-069 G10)。

Context Budget: 审计查询结果不无限膨胀 LLM Context — 估算 token + fit
(Top-K + 截断保 max_tokens) + stats (candidates/selected/discarded/
estimated_tokens/max_tokens/latency — 审计口径)。

设计: docs/sprint10/S10-069-audit-design.md §7 (复用 debug/context_budget 模式)
边界:
- 纯标准库; 估算启发式 (len/4 — 中文/英文混合近似), 非精确 tokenizer
- fit 失败安全: 空输入 → ([], stats); max_tokens<=0 → 全部候选 (无预算限制)
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from .audit_event import AuditEvent

#: 启发式: 每 token 约 4 字符 (中文/英文混合近似; 无 tokenizer 依赖)
_CHARS_PER_TOKEN = 4.0


def _event_text(item: Any) -> str:
    """事件/记录 → 估算文本 (AuditEvent/dict json / 其余 str)。"""
    if isinstance(item, AuditEvent):
        return json.dumps(item.to_dict(redact_sensitive=False), ensure_ascii=False)
    if isinstance(item, dict):
        return json.dumps(item, ensure_ascii=False)
    return str(item)


class AuditContextBudget:
    """Token 预算 (G10): estimate_tokens / fit / stats。

    fit(events, max_tokens) -> (selected, stats): 按给定顺序贪心选取, 累计
    估算 token 不超过 max_tokens (至少保留 1 条 — 审计结果不为空);
    max_tokens<=0 → 全部返回 (无预算限制)。返回二元组 (设计 §7 口径)。
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

    def fit(
        self, events: Any, max_tokens: int = 2048
    ) -> tuple[list[Any], dict[str, Any]]:
        """Top-K + 截断: 累计估算 token <= max_tokens (至少保留 1 条)。

        返回 (selected, stats) — 设计 §7: 调用方拿 selected 进 LLM Context,
        stats 进审计记录。单条超预算 → 仍保留 (至少 1 条, 结果不为空)。
        """
        started = time.monotonic()
        items = list(events or [])
        limit = int(max_tokens or 0)
        if limit <= 0:
            selected: list[Any] = list(items)
        else:
            selected = []
            total = 0
            for item in items:
                tokens = self.estimate_tokens(_event_text(item))
                if selected and total + tokens > limit:
                    break
                selected.append(item)
                total += tokens
        latency = round(time.monotonic() - started, 4)
        stats = self.stats(
            items, selected, max_tokens=max_tokens, latency=latency
        )
        return selected, stats

    def stats(
        self,
        candidates: Any,
        selected: Any,
        *,
        max_tokens: int = 0,
        latency: Optional[float] = None,
    ) -> dict[str, Any]:
        """统计 (审计口径): candidates/selected/discarded/tokens/max/latency。"""
        cands = list(candidates or [])
        picked = list(selected or [])
        selected_ids = {
            (getattr(r, "audit_id", None) or (r.get("audit_id") if isinstance(r, dict) else None))
            for r in picked
        }
        discarded = [
            r for r in cands
            if (getattr(r, "audit_id", None) or (r.get("audit_id") if isinstance(r, dict) else None))
            not in selected_ids
        ]
        return {
            "candidates_count": len(cands),
            "selected_count": len(picked),
            "discarded_count": len(discarded),
            "estimated_tokens": sum(
                self.estimate_tokens(_event_text(r)) for r in picked
            ),
            "max_tokens": int(max_tokens or 0),
            "latency": float(latency) if latency is not None else 0.0,
        }
