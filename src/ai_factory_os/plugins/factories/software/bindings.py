"""每个能力落在哪种实现上 —— 纯数据。

同一能力可有多个绑定；bindings.py 只声明，选谁由 services/resource 的解析决定。
"""
from __future__ import annotations

from ai_factory_os.contracts.resource import Implementation, ProviderType

BINDINGS: tuple[Implementation, ...] = (
    Implementation("CAP-UNDERSTAND", ProviderType.AGENT, "agent/understander"),
    Implementation("CAP-DRAFT-PRD", ProviderType.AGENT, "agent/planner"),
    Implementation("CAP-CONFIRM-PRD", ProviderType.HUMAN, "human/product-owner"),
    Implementation("CAP-DRAFT-PLAN", ProviderType.AGENT, "agent/planner"),
    Implementation("CAP-CONFIRM-PLAN", ProviderType.HUMAN, "human/product-owner"),
    Implementation("CAP-EXECUTE", ProviderType.AGENT, "agent/engineer"),
    Implementation("CAP-EXECUTE", ProviderType.SKILL, "skill/code-edit"),
    Implementation("CAP-VERIFY", ProviderType.TOOL, "tool/test-runner"),
    Implementation("CAP-REPAIR", ProviderType.AGENT, "agent/engineer"),
    Implementation("CAP-DELIVER", ProviderType.AGENT, "agent/releaser"),
    Implementation("CAP-DELIVER", ProviderType.HUMAN, "human/product-owner"),
)
