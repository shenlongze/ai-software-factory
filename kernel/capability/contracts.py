"""kernel/capability/contracts.py — 能力契约（注册与解析 / 找谁做）。

只定义"做什么"，不含"怎么做"。禁止 import services/extensions 具体实现。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class Capability:
    """一项能力（抽象"谁能做"）。"""

    capability_id: str
    name: str
    kind: str = ""  # agent | skill | tool | mcp | model | factory


@dataclass(frozen=True)
class Binding:
    """能力 → 扩展实现的绑定（解析结果）。"""

    capability_id: str
    extension_ref: str
    params: dict[str, Any]


@runtime_checkable
class CapabilityRegistry(Protocol):
    """能力注册表契约：一切插件的统一注册表。"""

    def register(self, capability: Capability, binding: Binding) -> None:
        """注册能力与其实现绑定。"""
        ...

    def resolve(self, requirement: str) -> Binding | None:
        """按需求解析出应使用的扩展绑定。"""
        ...
