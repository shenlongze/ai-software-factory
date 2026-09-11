"""kernel/scheduler/contracts.py — 调度契约（从"要做什么"到"现在执行谁"）。

只定义"做什么"，不含"怎么做"。禁止 import services/extensions。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ExecutionUnit:
    """一个待执行单元（调度输出）。"""

    unit_id: str
    node_ref: str
    inputs: dict[str, Any]


@runtime_checkable
class Scheduler(Protocol):
    """调度器契约：只读事实状态 → 返回下一个该执行谁。"""

    def next(self, state: dict[str, Any]) -> ExecutionUnit | None:
        """给定事实状态，返回下一个就绪的执行单元（无 → None）。"""
        ...
