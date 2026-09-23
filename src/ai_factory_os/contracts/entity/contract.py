"""contracts/entity — 统一实体/数据契约（S43 Unified Entity/Data Contract 的**契约面**）。

2026-09-15 自 _pending_migration/factory_console/unified_contract.py **拆出**:
  · 契约面（本文件）: ID 前缀表 / 实体字段 / 生命周期状态与转移 / 实体关系 / 错误码
  ★ 2026-09-22（R9 结构债）: 本文件只留**数据**（前缀表/字段/生命周期/关系/错误码）;
    原先那些带控制流的纯函数（new_id · create_entity · validate_entity · check_version ·
    bump_version · lifecycle_transition · make_* · relation_*）已**外移**到
    `services/resource/rules.py` —— 契约层不许含控制流（R9）, 也不许反向依赖 services。
  · 实现面（读写盘）: → infrastructure/storage/entity_store.py

13 实体统一关系:
 Conversation→Requirement→Analysis→Decision→Project→Sprint→Task→Node→Run→Artifact→Evidence→Incident→Approval
"""

from __future__ import annotations


#: 统一 ID 前缀 (禁止各系统自建 ID)
ID_PREFIXES = {
    "org": "org", "dept": "dept", "workforce": "workforce", "agent": "agent",
    "plugin": "plugin", "skill": "skill", "tool": "tool",
    "conv": "conv", "msg": "msg", "req": "req", "analysis": "analysis", "decision": "decision",
    "project": "project", "sprint": "sprint", "task": "task", "node": "node", "run": "run",
    "artifact": "artifact", "evidence": "evidence", "incident": "incident", "approval": "approval",
    "cmd": "cmd", "evt": "evt", "corr": "corr", "snap": "snap",
}

#: Universal Entity 基础字段
ENTITY_FIELDS = ("id", "type", "version", "status", "created_at", "updated_at",
                 "created_by", "owner", "parent_id", "project_id", "lineage",
                 "policy", "permissions", "metadata")

#: 统一 Lifecycle
LIFECYCLE_STATES = ("CREATED", "VALIDATED", "ACTIVE", "SUSPENDED", "BLOCKED",
                    "COMPLETED", "RETIRED")
LIFECYCLE_TRANSITIONS = {
    "CREATED": ("VALIDATED", "RETIRED"),
    "VALIDATED": ("ACTIVE", "SUSPENDED", "BLOCKED", "RETIRED"),
    "ACTIVE": ("SUSPENDED", "BLOCKED", "COMPLETED", "RETIRED"),
    "SUSPENDED": ("ACTIVE", "BLOCKED", "COMPLETED", "RETIRED"),
    "BLOCKED": ("ACTIVE", "SUSPENDED", "RETIRED"),
    "COMPLETED": ("RETIRED",),
    "RETIRED": (),
}

#: 13 实体统一关系 (parent → children)
ENTITY_RELATIONS = {
    "conv": ("msg", "req"),
    "req": ("analysis", "decision"),
    "analysis": ("decision",),
    "decision": ("project", "task"),
    "project": ("sprint", "task", "artifact", "evidence"),
    "sprint": ("task",),
    "task": ("node", "artifact", "evidence"),
    "node": ("run", "artifact", "evidence"),
    "run": ("artifact", "evidence"),
    "artifact": ("evidence",),
    "incident": ("evidence", "approval"),
    "approval": (),
}

#: 统一 Error codes
ERROR_CODES = {
    "VERSION_CONFLICT": "entity version conflict (optimistic concurrency)",
    "INVALID_STATE": "invalid state transition",
    "NOT_FOUND": "entity not found",
    "PERMISSION_DENIED": "permission denied",
    "VALIDATION_ERROR": "validation failed",
    "UNKNOWN_ERROR": "unknown error",
}
