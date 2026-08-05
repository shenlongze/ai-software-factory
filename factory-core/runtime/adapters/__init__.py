"""runtime/adapters — 内置 Runtime 适配器实现 (Phase 4B-2+: echo mock + hermes 真实 Agent)。

BUILTIN_ADAPTERS: {runtime_id: RuntimeAdapter} 内置实现映射:
- echo (id="echo", type="mock"): EchoRuntimeAdapter — 测试用 mock, 验证 dispatch/runner 链路。
- hermes-runtime (id="hermes-runtime", type="agent"): HermesRuntimeAdapter — 真实 Agent
  Runtime, subprocess 调 hermes CLI (Phase 4C-1)。

边界 (ADR-0007 决策 3): 实现映射 (本包) 与身份注册 (RuntimeRegistry/runtimes.json)
解耦 — 内置 Adapter 只提供"实现", runtime 身份仍须经 `factory runtime add --id <id>
--type <type>` 显式注册, registry 是派发解析的唯一事实源。
"""

from __future__ import annotations

from runtime.adapter import RuntimeAdapter

from .echo import EchoRuntimeAdapter
from .hermes import HermesRuntimeAdapter

BUILTIN_ADAPTERS: dict[str, RuntimeAdapter] = {
    EchoRuntimeAdapter.RUNTIME_ID: EchoRuntimeAdapter(),
    HermesRuntimeAdapter.RUNTIME_ID: HermesRuntimeAdapter(),
}

__all__ = ["EchoRuntimeAdapter", "HermesRuntimeAdapter", "BUILTIN_ADAPTERS"]
