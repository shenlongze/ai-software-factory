"""scheduler.ports — 调度器对外的全部依赖，一律以 Protocol 注入。

调度器**不** import services / plugins / infrastructure。
它只声明"我需要能问世界这些问题"，由 bootstrap 在装配时把真实实现接上。
→ 换个治理/资源实现，调度器一行不动。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable

from ai_factory_os.contracts.execution import Execution
from ai_factory_os.contracts.governance import GateKind
from ai_factory_os.contracts.organization import Member
from ai_factory_os.contracts.resource import Capability, Resolution
from ai_factory_os.contracts.work import TaskNode


@runtime_checkable
class ClockPort(Protocol):
    """时间 —— 注入以便判定可复现。"""

    def now_iso(self) -> str: ...


@runtime_checkable
class WorkPort(Protocol):
    """工作世界：节点、依赖、验收、时限。"""

    def get_node(self, node_id: str) -> TaskNode | None: ...

    def list_nodes(self, task_id: str = "") -> Sequence[TaskNode]: ...

    def has_accepted_outcome(self, node_id: str) -> bool: ...

    def deadline_of(self, node_id: str) -> str: ...

    def priority_of(self, node_id: str) -> str: ...


@runtime_checkable
class ResourcePort(Protocol):
    """资源世界：解析结果、成员与能力声明。"""

    def resolution_for(self, node_id: str) -> Resolution | None: ...

    def member(self, member_id: str) -> Member | None: ...

    def capability(self, capability_id: str) -> Capability | None: ...


@runtime_checkable
class LoadPort(Protocol):
    """余量：容量与预算 —— 世界还剩多少空间。"""

    def active_count(self, member_id: str) -> int: ...

    def remaining_budget(self, scope_ref: str) -> float: ...


@runtime_checkable
class GatePort(Protocol):
    """门：某主体是否已获批。"""

    def is_approved(self, subject_ref: str, kind: GateKind = GateKind.BEFORE) -> bool: ...


@runtime_checkable
class ExecutionPort(Protocol):
    """执行：查活跃、创建实例。"""

    def active_for(self, node_id: str) -> Execution | None: ...

    def create(self, node_id: str, *, resolution_id: str,
               member_id: str, identity_id: str) -> Execution: ...


@dataclass(frozen=True)
class Ports:
    """调度器的全部外部依赖 —— 唯一注入点。"""

    clock: ClockPort
    work: WorkPort
    resource: ResourcePort
    load: LoadPort
    gate: GatePort
    execution: ExecutionPort
