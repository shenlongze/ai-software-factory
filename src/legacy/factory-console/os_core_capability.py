"""factory-console/os_core_capability.py — OS Core: Capability (MU-CORE-07).

Capability = Professional Role 可被授权/解析/组合/执行/验证的专业能力契约（"能做什么"）。

语义边界 (Architecture Freeze):
    Capability ≠ Agent ≠ Skill ≠ Tool ≠ Plugin ≠ Model ≠ Professional Role ≠ Industry ≠ Factory
    Industry → FactorySpec → Factory 是另一条轴, Industry 不得作为 Capability 身份。

SSOT: <root>/capability/capabilities.json (single writer + 原子写 + stable ID CAP-*)。
范围外 (后续 MU): Resolution / Plugin Closure / Execution / Task / Agent registry 重写。
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CAPABILITY_STATES: tuple[str, ...] = ("active", "deprecated", "retired")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: str | Path) -> Path:
    return Path(root) / "capability" / "capabilities.json"


def _load(root: str | Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    items = data.get("capabilities") if isinstance(data, dict) else None
    return items if isinstance(items, dict) else {}


def _save(root: str | Path, data: dict[str, dict[str, Any]]) -> None:
    p = _file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"capabilities": data}, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


# ---------------------------------------------------------------- CRUD

def create_capability(root: str | Path, *, name: str, description: str = "",
                      category: str = "", status: str = "active",
                      capability_id: str | None = None) -> dict[str, Any]:
    """创建 Capability 定义 (不含 agent/model/plugin/tool 字段 — Capability 不负责执行)。"""
    if status not in CAPABILITY_STATES:
        raise ValueError(f"未知 status: {status} (可选: {CAPABILITY_STATES})")
    data = _load(root)
    cid = capability_id or f"CAP-{uuid.uuid4().hex[:10]}"
    if cid in data:
        raise ValueError(f"Capability 已存在: {cid}")
    for rec in data.values():
        if rec["name"] == name:
            raise ValueError(f"Capability 名称已存在: {name} -> {rec['capability_id']}")
    now = _now_iso()
    rec = {"capability_id": cid, "name": name, "description": description,
           "category": category, "status": status,
           "created_at": now, "updated_at": now}
    data[cid] = rec
    _save(root, data)
    return rec


def get_capability(root: str | Path, capability_id: str) -> dict[str, Any] | None:
    return _load(root).get(str(capability_id))


def list_capabilities(root: str | Path, *, category: str = "",
                      status: str = "") -> list[dict[str, Any]]:
    recs = list(_load(root).values())
    if category:
        recs = [r for r in recs if r["category"] == str(category)]
    if status:
        recs = [r for r in recs if r["status"] == str(status)]
    return sorted(recs, key=lambda r: r.get("created_at", ""))


def update_capability(root: str | Path, capability_id: str, *, name: str | None = None,
                      description: str | None = None, category: str | None = None) -> dict[str, Any]:
    data = _load(root)
    rec = data.get(str(capability_id))
    if rec is None:
        raise ValueError(f"Capability 不存在: {capability_id}")
    if name is not None:
        rec["name"] = name
    if description is not None:
        rec["description"] = description
    if category is not None:
        rec["category"] = category
    rec["updated_at"] = _now_iso()
    _save(root, data)
    return rec


def set_capability_status(root: str | Path, capability_id: str, status: str) -> dict[str, Any]:
    if status not in CAPABILITY_STATES:
        raise ValueError(f"未知 status: {status} (可选: {CAPABILITY_STATES})")
    data = _load(root)
    rec = data.get(str(capability_id))
    if rec is None:
        raise ValueError(f"Capability 不存在: {capability_id}")
    rec["status"] = status
    rec["updated_at"] = _now_iso()
    _save(root, data)
    return rec


# ---------------------------------------------------------------- resolve / validate

def resolve_capability(root: str | Path, ref: str) -> dict[str, Any]:
    """按 capability_id 或 name 解析; 未解析 -> ValueError。"""
    ref = str(ref or "")
    data = _load(root)
    if ref in data:
        return data[ref]
    for rec in data.values():
        if rec["name"] == ref:
            return rec
    raise ValueError(f"Capability 不存在: {ref}")


def validate_capability_ref(root: str | Path, ref: str) -> str:
    """校验引用并返回 canonical capability_id (无效 -> ValueError, 不静默)。"""
    rec = resolve_capability(root, ref)
    if rec["status"] == "retired":
        raise ValueError(f"Capability 已退役: {ref}")
    return str(rec["capability_id"])


__all__ = [
    "CAPABILITY_STATES",
    "create_capability",
    "get_capability",
    "list_capabilities",
    "resolve_capability",
    "set_capability_status",
    "update_capability",
    "validate_capability_ref",
]
