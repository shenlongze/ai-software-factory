"""llm.routing — 路由的【问】与【答】契约。零依赖。

RouteRequest 是**问**（这一次任务需要什么）；RouteDecision 是**答**
（用哪个 provider/model、按哪一层选的、为什么、降级路径）。

★ 核心只认这两个结构 —— 不认识 L1~L5 策略，也不 import 任何路由实现。
  智能路由因此是【可替换的决策器】: 换实现（或换成独立产品）核心零改动。
  RouteLayer 仅用于审计与解释（"按哪层选的"），不是策略本身的实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

#: 五层决策链的层标（与 LLM Router 既有自述一致；仅作标记，不含策略逻辑）。
ROUTE_LAYERS: tuple[str, ...] = (
    "L1-user-explicit",
    "L2-agent-policy",
    "L3-project-rule",
    "L4-system-recommend",
    "L5-fallback",
)


class RouteLayer(str, Enum):
    """决策来自哪一层 —— 审计与可解释的载体。"""

    USER_EXPLICIT = "L1-user-explicit"
    AGENT_POLICY = "L2-agent-policy"
    PROJECT_RULE = "L3-project-rule"
    SYSTEM_RECOMMEND = "L4-system-recommend"
    FALLBACK = "L5-fallback"


@dataclass(frozen=True)
class RouteRequest:
    """路由的问 —— 这一次任务需要什么。"""

    task_type: str = ""
    #: 必需能力（如 ("reasoning",) / ("tool_call",)）—— 决策器据此筛模型。
    required_capabilities: tuple[str, ...] = ()
    #: L1 用户显式指定（显式但不存在/禁用 → 决策器应响亮报错，不静默降级）。
    explicit_provider: str | None = None
    explicit_model: str | None = None
    project_id: str = ""
    agent_id: str = ""
    skill_id: str = ""
    #: 预估上下文长度（用于挑上下文窗口足够的模型）。
    context_tokens: int | None = None
    #: 剩余预算（USD）；决策器可选据此降级到更便宜的模型。
    budget_remaining_usd: float | None = None

    @property
    def is_explicit(self) -> bool:
        """是否用户显式指定（决定"失败应响亮还是可降级"）。"""
        return bool(self.explicit_provider or self.explicit_model)


@dataclass(frozen=True)
class RouteDecision:
    """路由的答 —— 用哪个、按哪层选的、为什么、降级路径。"""

    provider_id: str
    model_id: str | None
    layer: RouteLayer
    reason: str = ""
    #: 曾尝试但失败的 provider（降级链轨迹）—— 审计可查"为什么不是首选"。
    fallback_from: tuple[str, ...] = ()
    cost_estimate_usd: float | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def is_fallback(self) -> bool:
        """是否发生过降级（至少尝试过一个失败的候选）。"""
        return bool(self.fallback_from)
