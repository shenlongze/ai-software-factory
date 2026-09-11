"""kernel/node/contracts.py — 执行节点契约（自治原语）。

只定义"做什么"，不含"怎么做"。禁止 import services/extensions。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class NodeSpec:
    """节点定义（输入）。"""

    node_id: str
    kind: str
    inputs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NodeResult:
    """节点执行结果（输出）：结果 + 证据引用。"""

    node_id: str
    ok: bool
    outputs: dict[str, Any]
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)


@runtime_checkable
class Node(Protocol):
    """执行节点契约：输入 node 定义 → 输出执行结果 + 证据。"""

    def execute(self, spec: NodeSpec) -> NodeResult:
        """执行节点，返回结果与证据引用。"""
        ...
