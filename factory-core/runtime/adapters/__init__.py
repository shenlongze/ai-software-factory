"""runtime/adapters — 内置 Runtime 适配器实现 (Phase 4B-2: 无真实 Runtime, 仅 mock)。

BUILTIN_ADAPTERS: {runtime_id: RuntimeAdapter} 内置实现映射 — 目前唯一内置为
EchoRuntimeAdapter (id="echo", type="mock"), 用于验证 dispatch/runner 执行链路。

边界 (ADR-0007 决策 3): 实现映射 (本包) 与身份注册 (RuntimeRegistry/runtimes.json)
解耦 — 内置 Adapter 只提供\"实现\", runtime 身份仍须经 `factory runtime add --id echo
--type mock` 显式注册, registry 是派发解析的唯一事实源。
"""

from __future__ import annotations

from .echo import EchoRuntimeAdapter

BUILTIN_ADAPTERS: dict[str, EchoRuntimeAdapter] = {"echo": EchoRuntimeAdapter()}

__all__ = ["EchoRuntimeAdapter", "BUILTIN_ADAPTERS"]
