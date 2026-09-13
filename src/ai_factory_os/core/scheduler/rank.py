"""scheduler.rank — 排序：先到期的先做 → 优先级 → 便宜的先做 → 声明序。

稳定、全序、可解释。
"""
from __future__ import annotations

from collections.abc import Iterable

from ai_factory_os.contracts.scheduling import SortKey

_PRIORITY = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
_NO_DEADLINE = "9999-12-31T23:59:59Z"


def sort_key(key: SortKey) -> tuple[str, int, float, int]:
    """调度次序的键 —— 无时限视为最晚。"""
    return (key.deadline or _NO_DEADLINE,
            _PRIORITY.get(key.priority, len(_PRIORITY)),
            key.cost_estimate,
            key.sequence)


def order(pairs: Iterable[tuple[SortKey, str]]) -> list[str]:
    """按调度次序排列，返回 payload（此处为 task_node_id）。"""
    return [payload for _, payload in sorted(pairs, key=lambda kv: sort_key(kv[0]))]
