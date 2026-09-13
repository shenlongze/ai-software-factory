"""factory-console/session/context_ledger.py — ContextLedger (S10-070 G4 统一预算)。

统一 Context Budget 总约束: 各模块 (system/task/project/memory/audit/debug/
retrieval) 独立估算 context token 的现状 → 组合可无限叠加 (G4)。ContextLedger
提供单一总账: MAX_CONTEXT_TOKENS 总预算 + 按来源 allocate/add_source +
check (总预算约束) + stats (审计口径)。

- allocate(source, tokens) -> bool: 总预算内分配 (超出 → False, 不记账)
- add_source(name, tokens) -> int: 无条件记账 (返回新 total — 统计/审计用)
- total() / remaining() / over_budget(): 总账视图
- check(total_tokens) -> (ok, reason): 总预算约束检查 (集中校验点)
- stats() -> {sources, total, max, remaining, over}: 审计/展示口径
- estimate_tokens(text) -> int: 复用各模块启发式 (len/4 — 同
  session/debug/context_budget.ContextBudget 口径, 中文/英文混合近似)

边界:
- 纯标准库, 零新依赖; estimate_tokens 为启发式 (非精确 tokenizer)
- 失败安全: 非法输入 (负数/非数字) → 归一为 0, 不抛
- 不修改任何现有 budget 模块 (session/debug/context_budget.py 等) — 独立新账本

设计: docs/sprint10/S10-070-gap-design.md §三.4 (G4 Context Budget 统一)
"""

from __future__ import annotations

from typing import Any, Optional

__all__ = ["ContextLedger", "estimate_tokens"]

#: 启发式: 每 token 约 4 字符 (中文/英文混合近似; 无 tokenizer 依赖 —
#: 同 session/debug/context_budget._CHARS_PER_TOKEN 口径)
_CHARS_PER_TOKEN = 4.0

#: 总预算缺省 (G4: 系统/任务/项目/记忆/审计/调试/检索组合的 LLM Context 上限)
DEFAULT_MAX_CONTEXT_TOKENS = 12000


def estimate_tokens(text: Any) -> int:
    """文本 token 估算 (启发式 len/4; 空 → 0; 非空至少 1)。"""
    content = str(text or "")
    if not content.strip():
        return 0
    return max(1, int(len(content) / _CHARS_PER_TOKEN))


class ContextLedger:
    """统一 Context 总账 (G4): MAX_CONTEXT_TOKENS 总预算 + 来源分配。

    allocate(source, tokens): 预算内分配 → True 并记账; 超出 → False
      (不记账, 调用方降级 — 总预算铁律);
    add_source(name, tokens): 无条件记账 (统计视图; 返回新 total);
    check(total_tokens): 集中校验 — (True, reason) / (False, 超预算原因);
    stats(): {sources: {name: tokens}, total, max, remaining, over}。
    """

    MAX_CONTEXT_TOKENS = DEFAULT_MAX_CONTEXT_TOKENS

    def __init__(self, max_tokens: Optional[int] = None) -> None:
        """max_tokens 缺省 → MAX_CONTEXT_TOKENS (12000); <=0 → 无预算限制。"""
        self._max: int = int(max_tokens) if max_tokens is not None else self.MAX_CONTEXT_TOKENS
        self._sources: dict[str, int] = {}

    # ------------------------------------------------------------ 分配

    def allocate(self, source: str, tokens: Any) -> bool:
        """预算内分配 (G4/验收 E): 总预算内 → 记账 + True; 超出 → False。

        source 非空字符串 (空 → False, 不记账); tokens 归一 (负数/非数字 → 0);
        预算已满 (remaining <= 0) 且本次 > 0 → False (总预算铁律)。
        """
        name = str(source or "")
        if not name:
            return False
        try:
            amount = max(0, int(float(tokens or 0)))
        except (TypeError, ValueError):  # noqa: BLE001 — 失败安全
            amount = 0
        if amount == 0:
            self._sources[name] = self._sources.get(name, 0)
            return True
        if self._max > 0 and self.total() + amount > self._max:
            return False
        self._sources[name] = self._sources.get(name, 0) + amount
        return True

    def add_source(self, name: str, tokens: Any) -> int:
        """无条件记账 (统计/审计视图; 不校验预算 — 调用方自行决定语义)。

        返回新 total。name 空 → 忽略 (不记账, 返回当前 total)。
        """
        label = str(name or "")
        if not label:
            return self.total()
        try:
            amount = max(0, int(float(tokens or 0)))
        except (TypeError, ValueError):  # noqa: BLE001 — 失败安全
            amount = 0
        self._sources[label] = self._sources.get(label, 0) + amount
        return self.total()

    # ------------------------------------------------------------ 总账

    def total(self) -> int:
        """已分配 token 总量 (全部来源合计)。"""
        return sum(self._sources.values())

    def remaining(self) -> int:
        """剩余预算 (max <= 0 → 无限制, 返回极大值语义: max 原值)。"""
        if self._max <= 0:
            return self._max
        return max(0, self._max - self.total())

    def over_budget(self) -> bool:
        """是否超出总预算 (max <= 0 → 永不超)。"""
        if self._max <= 0:
            return False
        return self.total() > self._max

    def check(self, total_tokens: Any) -> tuple[bool, str]:
        """总预算约束检查 (G4/验收 E): (ok, reason) 二元组。

        total_tokens: 待检查的累计 token (任意来源组合 — 集中校验点);
        max <= 0 → 无限制 → (True, "no limit"); 超出 → (False, 超了多少)。
        """
        try:
            amount = max(0, int(float(total_tokens or 0)))
        except (TypeError, ValueError):  # noqa: BLE001 — 失败安全
            amount = 0
        if self._max <= 0:
            return True, f"no limit (max={self._max})"
        if amount <= self._max:
            return True, f"within budget ({amount}/{self._max})"
        return False, f"over budget by {amount - self._max} tokens ({amount}/{self._max})"

    # ------------------------------------------------------------ 统计

    def stats(self) -> dict[str, Any]:
        """统计 (验收 E): {sources, total, max, remaining, over} — 审计口径。"""
        return {
            "sources": dict(sorted(self._sources.items())),
            "total": self.total(),
            "max": self._max,
            "remaining": self.remaining(),
            "over": self.over_budget(),
        }

    # ------------------------------------------------------------ 工具

    def estimate_tokens(self, text: Any) -> int:
        """实例级 token 估算 (委托模块级 estimate_tokens — 复用各模块模式)。"""
        return estimate_tokens(text)
