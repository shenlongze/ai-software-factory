"""services/resource/rules.py — 统一实体/数据的**规则与构造**（S43 实体契约的实现面之一）。

★ 2026-09-22（R9 结构债）: 原先放在 `contracts/entity/contract.py` 里 —— 但那些函数带控制流,
  契约层只许放数据（R9）。这里**原样搬过来, 行为一字未改** ✗（Founder: 不新增功能 ⇒ 只搬不改 ✓）:
  new_id · validate_entity_id · validate_entity · check_version · bump_version · lifecycle_transition ·
  create_entity · make_command/response/event/error/page/realtime_event · relation_children/parents
  数据常量仍以 `contracts/entity/contract.py` 为**单一事实源** ✓
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ai_factory_os.contracts.entity.contract import (
    ENTITY_FIELDS,
    ENTITY_RELATIONS,
    ERROR_CODES,
    ID_PREFIXES,
    LIFECYCLE_STATES,
    LIFECYCLE_TRANSITIONS,
)


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
