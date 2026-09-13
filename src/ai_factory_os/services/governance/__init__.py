"""services.governance — 治理域（审批 / 预算 / 策略）。

拥有契约：`contracts/governance`。不负责：调度决策（core/scheduler）、执行本身（services/execution）。

沿革：factory-exec/exec/approval.py → services/approval_runtime/ → 此处（刀20 重写替换）。
对外一律从这里取，不再从旧路径。
"""
from __future__ import annotations

from .rules import classify_risk, normalize_decision
from .service import ApprovalDecideError, ApprovalGate, ApprovalRuntimeError, decide
from .store import ApprovalRecord, ApprovalStore, ApprovalStoreError

__all__ = [
    "ApprovalDecideError",
    "ApprovalGate",
    "ApprovalRecord",
    "ApprovalRuntimeError",
    "ApprovalStore",
    "ApprovalStoreError",
    "classify_risk",
    "decide",
    "normalize_decision",
]
