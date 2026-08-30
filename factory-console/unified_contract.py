"""factory-console/unified_contract.py — S43 Unified Entity/Data Contract (Master Plan S42).

冻结统一数据与接口基础:
- ID Contract: 统一前缀 (org_/dept_/workforce_/agent_/plugin_/conv_/msg_/req_/analysis_/
  decision_/project_/sprint_/task_/node_/run_/artifact_/evidence_/incident_/approval_)
- Universal Entity Contract: id/type/version/status/created_at/updated_at/created_by/
  owner/parent_id/project_id/lineage/policy/permissions/metadata
- Version Contract: entity_version + optimistic concurrency (VERSION_CONFLICT)
- Lifecycle Engine: Created→Validated→Active→Suspended/Blocked→Completed/Retired
  (domain lifecycle 扩展; Command→Policy→Validation→Transition→Event→Projection)
- Command Contract: request_id/entity_id/version/command/actor/timestamp/policy_context
- Event Contract: actor/actor_type/action/entity/before/after/reason/policy/decision/
  timestamp/correlation_id/causation_id
- Error Contract / Pagination Contract / Realtime Event Contract
- 13 实体统一关系: Conversation→Requirement→Analysis→Decision→Project→Sprint→Task→Node→Run→Artifact→Evidence→Incident→Approval

复用: audit_event.py (correlation_id)
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(entity_type: str) -> str:
    """统一 ID 生成 (禁止自建 ID)。"""
    prefix = ID_PREFIXES.get(entity_type)
    if prefix is None:
        raise ValueError(f"未知 entity_type: {entity_type} (合法: {sorted(ID_PREFIXES)})")
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def validate_entity_id(entity_id: str, entity_type: str | None = None) -> bool:
    """ID Contract 校验 (前缀必须匹配类型)。"""
    prefix = entity_id.split("_", 1)[0]
    if prefix not in ID_PREFIXES.values():
        return False
    if entity_type and ID_PREFIXES.get(entity_type) != prefix:
        return False
    return len(entity_id) > len(prefix) + 1


# ------------------------------------------------------------------ Universal Entity

def create_entity(entity_type: str, *, created_by: str = "system", owner: str = "",
                  parent_id: str = "", project_id: str = "",
                  policy: str = "", permissions: list[str] | None = None,
                  metadata: dict[str, Any] | None = None,
                  entity_id: str | None = None) -> dict[str, Any]:
    """创建 Universal Entity (统一字段, 禁重复定义基础字段)。"""
    now = _now_iso()
    return {"id": entity_id or new_id(entity_type), "type": entity_type,
            "version": 1, "status": "CREATED",
            "created_at": now, "updated_at": now,
            "created_by": created_by, "owner": owner,
            "parent_id": parent_id, "project_id": project_id,
            "lineage": [], "policy": policy,
            "permissions": permissions or [], "metadata": metadata or {}}


def validate_entity(entity: dict[str, Any]) -> dict[str, Any]:
    """Entity Contract 校验 (所有生产实体必须通过)。"""
    missing = [f for f in ENTITY_FIELDS if f not in entity]
    if missing:
        raise ValueError(f"Entity 缺基础字段: {missing}")
    if not validate_entity_id(entity["id"], entity["type"]):
        raise ValueError(f"非法 entity_id: {entity['id']} (type={entity['type']})")
    if not isinstance(entity["version"], int) or entity["version"] < 1:
        raise ValueError(f"非法 version: {entity['version']}")
    return {"valid": True, "entity_type": entity["type"], "entity_id": entity["id"]}


# ------------------------------------------------------------------ Version Contract (optimistic concurrency)

def check_version(entity: dict[str, Any], expected_version: int | None = None) -> None:
    """乐观并发: 基于旧版本修改 → VERSION_CONFLICT (非静默覆盖)。"""
    if expected_version is not None and entity["version"] != expected_version:
        raise ConcurrencyError(
            f"VERSION_CONFLICT: entity {entity['id']} 当前 v{entity['version']}, "
            f"期望 v{expected_version} (基于旧版本修改被拒绝)")


def bump_version(entity: dict[str, Any], *, actor: str = "system",
                 note: str = "") -> dict[str, Any]:
    """版本递增 + lineage (每次修改产生新版本, 历史可追溯)。"""
    entity["version"] += 1
    entity["updated_at"] = _now_iso()
    entity["lineage"] = entity.get("lineage", []) + [
        {"version": entity["version"], "actor": actor, "at": _now_iso(), "note": note}]
    return entity


class ConcurrencyError(Exception):
    """乐观并发冲突 (VERSION_CONFLICT)。"""


# ------------------------------------------------------------------ Lifecycle Engine

def lifecycle_transition(entity: dict[str, Any], *, target: str,
                         actor: str = "system", note: str = "") -> dict[str, Any]:
    """统一 Lifecycle: Command→Validation→Transition→Event (禁 UI 直接改 status)。"""
    if target not in LIFECYCLE_STATES:
        raise ValueError(f"未知 lifecycle 状态: {target}")
    current = entity["status"]
    if target not in LIFECYCLE_TRANSITIONS.get(current, ()) and target != current:
        raise ValueError(f"INVALID_STATE: 非法状态迁移 {current} → {target}")
    entity["status"] = target
    entity["updated_at"] = _now_iso()
    entity["lifecycle_history"] = entity.get("lifecycle_history", []) + [
        {"from": current, "to": target, "at": _now_iso(), "actor": actor, "note": note}]
    return entity


# ------------------------------------------------------------------ Command / Event / Error / Pagination / Realtime

def make_command(*, command: str, entity_id: str, actor: str = "human",
                 policy_context: dict[str, Any] | None = None,
                 expected_version: int | None = None) -> dict[str, Any]:
    """统一 Command Contract。"""
    return {"request_id": f"cmd_{uuid.uuid4().hex[:12]}", "entity_id": entity_id,
            "version": expected_version, "command": command, "actor": actor,
            "timestamp": _now_iso(), "policy_context": policy_context or {}}


def make_response(*, success: bool, data: Any = None, entity_version: int | None = None,
                  event_ids: list[str] | None = None, warnings: list[str] | None = None,
                  errors: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """统一 Response Contract。"""
    return {"success": success, "data": data, "entity_version": entity_version,
            "event_ids": event_ids or [], "warnings": warnings or [],
            "errors": errors or []}


def make_event(*, event_type: str, entity: dict[str, Any], action: str,
               actor: str = "system", actor_type: str = "system",
               before: Any = None, after: Any = None, reason: str = "",
               policy: str = "", decision: str = "allow",
               correlation_id: str = "", causation_id: str = "") -> dict[str, Any]:
    """统一 Event Contract (correlation/causation 可追溯)。"""
    return {"event_id": f"evt_{uuid.uuid4().hex[:12]}", "event_type": event_type,
            "entity_type": entity.get("type"), "entity_id": entity.get("id"),
            "entity_version": entity.get("version"), "action": action,
            "actor": actor, "actor_type": actor_type,
            "before": before, "after": after, "reason": reason,
            "policy": policy, "decision": decision,
            "timestamp": _now_iso(),
            "correlation_id": correlation_id or f"corr_{uuid.uuid4().hex[:12]}",
            "causation_id": causation_id}


def make_error(*, code: str, message: str = "", entity_id: str = "",
               request_id: str = "") -> dict[str, Any]:
    """统一 Error Contract。"""
    if code not in ERROR_CODES:
        code = "UNKNOWN_ERROR"
    return {"code": code, "message": message or ERROR_CODES[code],
            "entity_id": entity_id, "request_id": request_id}


def make_page(*, items: list[Any], page: int = 1, page_size: int = 20,
              total: int | None = None) -> dict[str, Any]:
    """统一 Pagination Contract。"""
    total_n = total if total is not None else len(items)
    return {"items": items, "page": page, "page_size": page_size,
            "total": total_n,
            "pages": max(1, (total_n + page_size - 1) // page_size)}


def make_realtime_event(*, event_type: str, entity_type: str, entity_id: str,
                        version: int, payload: Any = None,
                        correlation_id: str = "") -> dict[str, Any]:
    """统一 Realtime Event Contract (REST/WebSocket/SSE 共用)。"""
    return {"event_id": f"evt_{uuid.uuid4().hex[:12]}", "type": event_type,
            "entity": entity_type, "entity_id": entity_id, "version": version,
            "payload": payload, "timestamp": _now_iso(),
            "correlation_id": correlation_id or f"corr_{uuid.uuid4().hex[:12]}"}


# ------------------------------------------------------------------ 13 实体关系

def relation_children(entity_type: str) -> list[str]:
    """实体统一关系 (parent → children)。"""
    return list(ENTITY_RELATIONS.get(entity_type, ()))


def relation_parents(entity_type: str) -> list[str]:
    """反向关系 (child → parents, 可追溯链)。"""
    return [k for k, v in ENTITY_RELATIONS.items() if entity_type in v]


# ------------------------------------------------------------------ 持久化 (ops/unified/)

def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "unified" / f"{name}.json"


def _load(root: Path | str, name: str) -> list[dict[str, Any]]:
    try:
        d = json.loads(_file(root, name).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(root: Path | str, name: str, data: list[dict[str, Any]]) -> None:
    p = _file(root, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def store_entity(root: Path | str, entity: dict[str, Any]) -> dict[str, Any]:
    """持久化 Entity (统一 Store, 单一事实源)。"""
    validate_entity(entity)
    data = _load(root, "entities")
    data = [e for e in data if e["id"] != entity["id"]]
    data.append(entity)
    _save(root, "entities", data)
    return entity


def get_entity(root: Path | str, entity_id: str) -> dict[str, Any]:
    for e in _load(root, "entities"):
        if e["id"] == entity_id:
            return e
    raise ValueError(f"NOT_FOUND: entity {entity_id}")


def entities(root: Path | str, *, entity_type: str = "") -> list[dict[str, Any]]:
    data = _load(root, "entities")
    if entity_type:
        data = [e for e in data if e["type"] == entity_type]
    return data


def trace_lineage(root: Path | str, entity_id: str) -> list[dict[str, Any]]:
    """Lineage 追溯: 沿 parent_id 向上 (为什么创建这个实体)。"""
    chain = []
    current = entity_id
    seen = set()
    while current and current not in seen:
        seen.add(current)
        try:
            e = get_entity(root, current)
        except ValueError:
            break
        chain.append({"id": e["id"], "type": e["type"], "version": e["version"],
                      "status": e["status"]})
        current = e.get("parent_id", "")
    return chain
