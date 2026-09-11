"""kernel/governance/contracts.py — 治理契约（审批/预算/审计统一挂点）。

只定义"做什么"，不含"怎么做"。禁止 import services/extensions。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class Decision:
    """治理判定结果。"""

    allowed: bool
    verdict: str  # allow | deny | approval
    reason: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class GovernanceGate(Protocol):
    """治理 Gate 契约：check(action) → allow/deny/approval。"""

    def check(self, action: dict[str, Any]) -> Decision:
        """对某动作做治理判定（含审批/预算/审计挂点）。"""
        ...
