"""llm.provider — Provider 与模型的配置契约。零依赖。

ProviderConfig 是**声明**（有哪些 provider、启停、模型清单、key 引用）；
ModelSpec 是**单个模型的规格**（能力/上下文/成本）。

本契约只描述"配置长什么样"，不描述"怎么连"——
连接实现属 infrastructure/llm；本契约不得 import 任何实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

#: api_key_ref 只接受该前缀 —— 【明文 key 不入配置】（与既有校验同口径）。
API_KEY_REF_PREFIX = "env:"

PROVIDER_STATUSES: tuple[str, ...] = ("enabled", "disabled")


class ProviderStatus(str, Enum):
    """Provider 启停状态。第一个 enabled 且 key 可解析者胜出（v1 选择语义）。"""

    ENABLED = "enabled"
    DISABLED = "disabled"


@dataclass(frozen=True)
class ModelSpec:
    """单个模型的规格（能力/上下文/成本）—— 路由决策的依据。"""

    id: str
    provider_id: str
    display: str = ""
    context_window: int | None = None
    #: 能力标签: chat / reasoning / embedding / tool_call / vision …
    capabilities: tuple[str, ...] = ()
    input_rate_per_1k: float | None = None
    output_rate_per_1k: float | None = None

    def supports(self, capability: str) -> bool:
        """是否具备某项能力（大小写不敏感）。空 capabilities = 不声明 → 视为不支持。"""
        target = capability.strip().lower()
        return any(c.strip().lower() == target for c in self.capabilities)

    def estimate_cost_usd(self, input_tokens: int, output_tokens: int) -> float | None:
        """按 1k 单价估算成本；缺单价 → None（诚实: 不臆造）。"""
        if self.input_rate_per_1k is None or self.output_rate_per_1k is None:
            return None
        return (
            input_tokens / 1000.0 * self.input_rate_per_1k
            + output_tokens / 1000.0 * self.output_rate_per_1k
        )


@dataclass(frozen=True)
class ProviderConfig:
    """Provider 配置声明 —— 与 providers.json 的条目同构。"""

    id: str
    enabled: bool = True
    models: tuple[str, ...] = ()
    base_url: str = ""
    #: 只允许 "env:VAR" 形式的引用（明文 key 不入配置）。
    api_key_ref: str = ""
    display: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> ProviderStatus:
        return ProviderStatus.ENABLED if self.enabled else ProviderStatus.DISABLED

    def key_ref_is_valid(self) -> bool:
        """api_key_ref 合法: 空(本地模型如 ollama 可无 key) 或 env: 引用。"""
        return (not self.api_key_ref) or self.api_key_ref.startswith(API_KEY_REF_PREFIX)

    def key_env_var(self) -> str:
        """从 api_key_ref 取出环境变量名；非 env: 引用 → ""。"""
        if not self.api_key_ref.startswith(API_KEY_REF_PREFIX):
            return ""
        return self.api_key_ref[len(API_KEY_REF_PREFIX):]

    def is_usable(self, key_resolved: bool = True) -> bool:
        """可用性: enabled + key 引用合法 + （需要 key 时）key 可解析。

        本地 provider（无 api_key_ref）不要求 key —— 由调用方以 key_resolved=True 传入。
        """
        return self.enabled and self.key_ref_is_valid() and key_resolved
