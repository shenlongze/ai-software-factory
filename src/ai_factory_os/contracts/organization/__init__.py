"""organization — 公司 / 部门 / 角色 / 成员。零依赖。"""
from __future__ import annotations

from dataclasses import dataclass, field

MEMBER_STATES: tuple[str, ...] = ("active", "suspended", "retired")


@dataclass(frozen=True)
class Company:
    """一家公司 —— 资源的所有者，也是预算与授权的边界。"""

    id: str
    name: str
    owner_id: str = ""
    parent_id: str = ""
    status: str = "active"


@dataclass(frozen=True)
class Department:
    """部门（可嵌套）。"""

    id: str
    company_id: str
    name: str
    parent_id: str = ""


@dataclass(frozen=True)
class Role:
    """角色 = 能力集合 + 授权范围。

    角色不做事；它只声明「具备哪些能力」与「可触达哪些范围」。
    """

    id: str
    name: str
    capability_refs: tuple[str, ...] = ()
    authority: tuple[str, ...] = ()


@dataclass(frozen=True)
class Capacity:
    """成员的可调度容量 —— 同时能跑几个。"""

    max_concurrent: int = 1


@dataclass(frozen=True)
class Member:
    """成员 —— 一个身份（人/Agent）在组织内的任职。

    Member 是调度的**资源单位**：调度器分配工作时，分配到 Member。
    """

    id: str
    org_id: str
    identity_id: str
    name: str = ""
    role_ids: tuple[str, ...] = ()
    capacity: Capacity = field(default_factory=Capacity)
    status: str = "active"
