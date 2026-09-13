"""execution — 执行 / 结果。零依赖。

关键语义：**执行成功 ≠ 业务完成**。
完成由 Outcome.accepted 定义，不由 Execution.status 定义。
"""
from __future__ import annotations

from dataclasses import dataclass

EXECUTION_STATES: tuple[str, ...] = ("queued", "running", "done", "failed", "preempted", "cancelled")
OUTCOME_STATES: tuple[str, ...] = ("pending", "accepted", "rejected")


@dataclass(frozen=True)
class Execution:
    """一次执行实例 —— 某任务节点的一次尝试。"""

    id: str
    task_node_id: str
    resolution_id: str = ""
    actor_identity_id: str = ""
    member_id: str = ""
    status: str = "queued"
    started_at: str = ""
    ended_at: str = ""
    cost_actual: float = 0.0


@dataclass(frozen=True)
class Outcome:
    """执行结果 —— 验收的产物。

    只有 accepted 会向上传播，解锁后继节点。
    """

    id: str
    execution_id: str
    status: str = "pending"
    verifier_id: str = ""
    verified_at: str = ""
    evidence_refs: tuple[str, ...] = ()
    reason: str = ""
