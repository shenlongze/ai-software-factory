"""resource — 能力 / 实现绑定 / 解析。零依赖。

Capability 是**声明**，Implementation 是**怎么做**，Resolution 是**这一次谁来做**。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..governance import ApprovalSpec

CAPABILITY_STATES: tuple[str, ...] = ("active", "deprecated", "retired")
RESOLUTION_STATES: tuple[str, ...] = ("resolved", "unresolved")
MATCH_TYPES: tuple[str, ...] = ("deterministic", "preferred", "fallback")


class ProviderType(str, Enum):
    """实现提供者种类 —— 能力落在哪种实现上。"""

    AGENT = "agent"
    SKILL = "skill"
    TOOL = "tool"
    MCP = "mcp"
    HUMAN = "human"


@dataclass(frozen=True)
class CostSpec:
    """成本模型（估算值）。"""

    tokens: int = 0
    seconds: int = 0
    money: float = 0.0


@dataclass(frozen=True)
class Capability:
    """能力声明 —— 全系统最重要的契约。

    verify / effects / risk 三者必修：
        verify   没有它 → 无法验收，只能人肉看
        effects  没有它 → 无法治理，系统不知道自己会动什么
        risk     没有它 → 只能把审批门写死在代码里
    """

    id: str
    name: str
    version: str = "1"
    satisfies: str = ""
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = ()
    verify: str = ""
    effects: tuple[str, ...] = ()
    risk: str = "low"
    approval: ApprovalSpec = field(default_factory=ApprovalSpec)
    cost: CostSpec = field(default_factory=CostSpec)
    status: str = "active"


@dataclass(frozen=True)
class Implementation:
    """实现绑定 —— 某能力由哪种实现提供。一个能力可有多个实现。"""

    capability_id: str
    provider_type: ProviderType
    provider_ref: str
    version: str = "1"


@dataclass(frozen=True)
class Match:
    """一次匹配结果 —— 某个成员被判定可以满足某能力。"""

    capability_id: str
    member_id: str
    identity_id: str
    provider_type: ProviderType
    provider_ref: str = ""
    match_type: str = "deterministic"


@dataclass(frozen=True)
class Resolution:
    """解析结果 —— 「这一次由谁来做」的判定。"""

    id: str
    task_node_id: str
    required_capability_refs: tuple[str, ...] = ()
    matches: tuple[Match, ...] = ()
    status: str = "unresolved"
    unresolved_capabilities: tuple[str, ...] = ()
    reason: str = ""
