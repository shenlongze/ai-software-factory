"""factory-console/os_core_professional.py — OS Core: Professional Domain / Professional Role (MU-CORE-03).

语义 (Constitution v2 Art.36/42):
- Professional Domain = 专业领域 (如 Software Engineering / Finance / Marketing);
  不是 Industry, 不是 Capability。
- Professional Role = 专业领域中的具体专业角色 (如 Backend Engineer / Product Manager);
  不是 Role Definition 的别名, 不是 Agent, 不是 Workforce。
- 契约: `ProfessionalRole -> capability_refs` 仅作为 Capability 引用**契约**(字符串);
  本 MU **不实现** Capability Registry / Plugin Kernel (后续 MU)。

关系:
    Role Definition (exec/roles.py)  <--role_ref(contract)--  ProfessionalRole
    ProfessionalDomain --1:N--> ProfessionalRole

存储: <root>/professional/{domains,roles}.json
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROFESSIONAL_STATUSES: tuple[str, ...] = ("active", "archived")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _path(root: str | Path, name: str) -> Path:
    return Path(root) / "professional" / f"{name}.json"


def _load(root: str | Path, name: str) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_path(root, name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    items = data.get(name) if isinstance(data, dict) else None
    return items if isinstance(items, dict) else {}


def _save(root: str | Path, name: str, data: dict[str, dict[str, Any]]) -> None:
    p = _path(root, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({name: data}, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


# ---------------------------------------------------------------- Professional Domain

def create_professional_domain(root: str | Path, *, name: str, description: str = "",
                               domain_id: str | None = None,
                               status: str = "active") -> dict[str, Any]:
    if status not in PROFESSIONAL_STATUSES:
        raise ValueError(f"未知 status: {status}")
    data = _load(root, "domains")
    did = domain_id or f"PD-{uuid.uuid4().hex[:10]}"
    if did in data:
        raise ValueError(f"Professional Domain 已存在: {did}")
    for rec in data.values():
        if rec["name"] == name:
            raise ValueError(f"Professional Domain 名称已存在: {name} -> {rec['domain_id']}")
    rec = {"domain_id": did, "name": name, "description": description,
           "status": status, "created_at": _now_iso(), "updated_at": _now_iso()}
    data[did] = rec
    _save(root, "domains", data)
    return rec


def get_professional_domain(root: str | Path, domain_id: str) -> dict[str, Any] | None:
    return _load(root, "domains").get(str(domain_id))


def list_professional_domains(root: str | Path) -> list[dict[str, Any]]:
    return sorted(_load(root, "domains").values(), key=lambda r: r.get("created_at", ""))


# ---------------------------------------------------------------- Professional Role

def create_professional_role(root: str | Path, *, professional_domain_id: str, name: str,
                             role_ref: str = "", capability_refs: list[str] | None = None,
                             description: str = "", role_id: str | None = None,
                             status: str = "active") -> dict[str, Any]:
    """Professional Role (专业角色)。

    - professional_domain_id 必须存在;
    - role_ref 若提供, 必须能解析到 Role Definition SSOT (exec/roles.py) -> 存 canonical role_id;
    - capability_refs 仅存**契约引用** (不实现 Capability)。
    """
    if status not in PROFESSIONAL_STATUSES:
        raise ValueError(f"未知 status: {status}")
    if get_professional_domain(root, professional_domain_id) is None:
        raise ValueError(f"Professional Domain 不存在: {professional_domain_id}")
    canonical_ref = ""
    if role_ref:
        from .os_core_role import resolve_role_definition

        canonical_ref = resolve_role_definition(role_ref)["role_id"]
    data = _load(root, "roles")
    rid = role_id or f"PR-{uuid.uuid4().hex[:10]}"
    if rid in data:
        raise ValueError(f"Professional Role 已存在: {rid}")
    for rec in data.values():
        if rec["professional_domain_id"] == str(professional_domain_id) and rec["name"] == name:
            raise ValueError(f"Professional Role 名称已存在: {name} @ {professional_domain_id}")
    rec = {"professional_role_id": rid,
           "professional_domain_id": str(professional_domain_id),
           "name": name, "description": description,
           "role_ref": canonical_ref,
           "capability_refs": [str(c) for c in (capability_refs or [])],
           "status": status, "created_at": _now_iso(), "updated_at": _now_iso()}
    data[rid] = rec
    _save(root, "roles", data)
    return rec


def get_professional_role(root: str | Path, professional_role_id: str) -> dict[str, Any] | None:
    return _load(root, "roles").get(str(professional_role_id))


def list_professional_roles(root: str | Path, *,
                            professional_domain_id: str = "") -> list[dict[str, Any]]:
    recs = list(_load(root, "roles").values())
    if professional_domain_id:
        recs = [r for r in recs if r["professional_domain_id"] == str(professional_domain_id)]
    return sorted(recs, key=lambda r: r.get("created_at", ""))


def resolve_professional_role(root: str | Path, ref: str) -> dict[str, Any] | None:
    """按 professional_role_id 或同 domain 内 name 解析。"""
    ref = str(ref or "")
    data = _load(root, "roles")
    if ref in data:
        return data[ref]
    for rec in data.values():
        if rec.get("name") == ref:
            return rec
    return None


__all__ = [
    "PROFESSIONAL_STATUSES",
    "create_professional_domain",
    "create_professional_role",
    "get_professional_domain",
    "get_professional_role",
    "list_professional_domains",
    "list_professional_roles",
    "resolve_professional_role",
]
