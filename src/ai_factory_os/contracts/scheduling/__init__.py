"""scheduling — 调度决策 / 排序键 / 就绪条件。零依赖。

调度器只回答一个问题：**现在，下一个该是谁。**
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DecisionKind(str, Enum):
    """就绪判定的五种结果。"""

    READY = "ready"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    UNRESOLVED = "unresolved"


# 就绪七条件（全部满足才 READY）
READY_CONDITIONS: tuple[str, ...] = (
    "status_actionable",          # 节点状态可调
    "dependencies_satisfied",     # 前驱均有 accepted Outcome
    "no_active_execution",        # 无活跃执行（幂等）
    "capability_available",       # 解析成功且有匹配
    "capacity_available",         # 成员有空闲容量
    "budget_available",           # 预算够
    "deadline_feasible",          # 未过期
)

# 排序键顺序：先到期的先做 → 优先级 → 便宜的先做 → 声明序
SORT_ORDER: tuple[str, ...] = ("deadline", "priority", "cost_estimate", "sequence")

PREEMPTION_POLICIES: tuple[str, ...] = ("none", "preempt")


@dataclass(frozen=True)
class SortKey:
    """排序键 —— 稳定、全序、可解释。"""

    deadline: str = ""
    priority: str = "P2"
    cost_estimate: float = 0.0
    sequence: int = 0


@dataclass(frozen=True)
class Decision:
    """一次就绪判定 —— 确定性、无副作用、可解释。"""

    task_node_id: str
    kind: DecisionKind = DecisionKind.BLOCKED
    reasons: tuple[str, ...] = ()
    failed_conditions: tuple[str, ...] = ()
    resolution_id: str = ""
    member_id: str = ""
    identity_id: str = ""


@dataclass(frozen=True)
class TickResult:
    """一次 tick 的结果。"""

    scheduled: tuple[str, ...] = ()
    decisions: tuple[Decision, ...] = ()
    deferred: tuple[str, ...] = ()
