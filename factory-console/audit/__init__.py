"""factory-console/audit/ — Audit Intelligence (S10-069)。

统一审计模型 + 存储 + 查询 + 决策链重建 + 结构化"为什么" + Context Budget
+ 防篡改 — Product→Plan→Task→Agent→Debug→Memory→Cost→Review→Delivery
全生命周期可审计、可解释、可导出。

设计: docs/sprint10/S10-069-audit-design.md
组件:
- AuditEvent / EVENT_TYPES / redact — 统一事件模型 + 30+ 事件类型 + 脱敏
- AuditStore / AuditStoreProtocol — append/get/query/get_chain/export/stats/verify
- AuditQuery — 10 类筛选 (project/task/agent/trace/type/actor/decision/status/risk/time)
- AuditDecisionChain — get_chain(trace_id) 重建决策链
- AuditExplain — why_created/why_agent/why_stopped/why_debug/why_cost/who_approved
- AuditContextBudget — Context 保护 (fit/stats)
- AuditIntegrity — event_hash + previous_event_hash (tamper-evident)
"""

from __future__ import annotations

from .audit_chain import AuditDecisionChain
from .audit_context import AuditContextBudget
from .audit_event import (
    ACTOR_TYPES,
    EVENT_TYPES,
    AuditEvent,
    canonical_json,
    redact,
)
from .audit_explain import AuditExplain
from .audit_integrity import AuditIntegrity
from .audit_query import AuditQuery
from .audit_store import (
    AUDIT_FILE_NAME,
    DEFAULT_AUDIT_FILE,
    AuditStore,
    AuditStoreProtocol,
)

__all__ = [
    "ACTOR_TYPES",
    "AUDIT_FILE_NAME",
    "AuditContextBudget",
    "AuditDecisionChain",
    "AuditEvent",
    "AuditExplain",
    "AuditIntegrity",
    "AuditQuery",
    "AuditStore",
    "AuditStoreProtocol",
    "DEFAULT_AUDIT_FILE",
    "EVENT_TYPES",
    "canonical_json",
    "redact",
]
