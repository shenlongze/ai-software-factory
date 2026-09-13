"""governance — 门 / 预算 / 策略。零依赖。

门不是流程常量，而是能力的属性（见 ApprovalSpec）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class ApprovalMode(str, Enum):
    """需要审批的时机 —— 能力的属性，不是流程的常量。"""

    NONE = "none"
    BEFORE = "before"
    AFTER = "after"


class GateKind(str, Enum):
    BEFORE = "before"
    AFTER = "after"


class GateState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class BudgetScope(str, Enum):
    ORG = "org"
    ROLE = "role"
    MEMBER = "member"
    PROJECT = "project"


class BudgetPolicy(str, Enum):
    """超预算时的行为。"""

    BLOCK = "block"
    WARN = "warn"
    APPROVE = "approve"


class PolicyEffect(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


@dataclass(frozen=True)
class ApprovalSpec:
    """能力的审批声明 —— 门由它推导，不由内核写死。"""

    mode: ApprovalMode = ApprovalMode.NONE
    approver_role: str = ""


@dataclass(frozen=True)
class Gate:
    """一道门 —— 某个主体的待批/已批事项。"""

    id: str
    subject_ref: str
    kind: GateKind = GateKind.BEFORE
    approver_role: str = ""
    state: GateState = GateState.PENDING
    decided_by: str = ""
    decided_at: str = ""
    reason: str = ""


@dataclass(frozen=True)
class Budget:
    """预算 —— 某个范围内的额度。"""

    scope: str
    scope_ref: str
    limit: float = 0.0
    used: float = 0.0
    period: str = ""
    policy: BudgetPolicy = BudgetPolicy.BLOCK


@dataclass(frozen=True)
class Policy:
    """策略 —— 范围 + 规则 + 效果。"""

    id: str
    scope: str
    rule: str
    effect: PolicyEffect = PolicyEffect.ALLOW


class VerdictKind(str, Enum):
    """治理判定结论。"""

    ALLOW = "allow"
    DENY = "deny"
    APPROVAL = "approval"


@dataclass(frozen=True)
class Verdict:
    """治理判定结果 —— 某个动作是否被允许。

    meta 用「不可变的键值对元组」而非 dict，与契约层不可变约定一致。
    """

    allowed: bool = False
    kind: VerdictKind = VerdictKind.DENY
    reason: str = ""
    subject_ref: str = ""
    meta: tuple[tuple[str, str], ...] = ()


@runtime_checkable
class GovernanceGate(Protocol):
    """治理门契约：对某个动作做判定。"""

    def check(self, action: dict[str, Any]) -> Verdict:
        """判定动作是否被允许（allow / deny / 需审批）。"""
        ...
