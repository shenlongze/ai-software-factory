"""factory-console/os_core_workforce.py — OS Core Boundary: Workforce (MU-CORE-04).

Workforce = 为完成某类专业工作而组织起来的一组可治理主体及其专业角色/能力引用/范围/生命周期。
**Workforce ≠ Agent List**；成员引用 Identity (MU-CORE-02)，专业角色引用 ProfessionalRole (MU-CORE-03)。

关系:
    Company -> Identity -> Role Assignment -> ProfessionalRole -> Workforce -> Capability(contract)
    Workforce.member_refs            : [identity_id]        (Identity SSOT 解析)
    Workforce.professional_role_refs : [professional_role_id] (Professional SSOT 解析)
    Workforce.capability_refs        : [str]                (仅契约, 不实现 Capability)
    Workforce.scope                  : global | department (证据: workforce_os 用 dept_id)

SSOT: <root>/workforce/workforces.json (single writer + 原子写 + stable ID)。
范围外 (后续 MU): Capability 实现 / Plugin / Project / Work / Resolution / Resource / Governance 全链。
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORKFORCE_STATES: tuple[str, ...] = ("draft", "active", "suspended", "retired")
WORKFORCE_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "draft": ("active", "retired"),
    "active": ("suspended", "retired"),
    "suspended": ("active", "retired"),
    "retired": (),
}
SCOPE_TYPES: tuple[str, ...] = ("global", "department")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: str | Path) -> Path:
    return Path(root) / "workforce" / "workforces.json"


def _load(root: str | Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    items = data.get("workforces") if isinstance(data, dict) else None
    return items if isinstance(items, dict) else {}


def _save(root: str | Path, data: dict[str, dict[str, Any]]) -> None:
    p = _file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"workforces": data}, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def _require_identity(root: str | Path, identity_id: str) -> None:
    from .os_core_identity import get_identity

    if get_identity(root, identity_id) is None:
        raise ValueError(f"Identity 不存在: {identity_id}")


def _require_professional_role(root: str | Path, professional_role_id: str) -> None:
    from .os_core_professional import get_professional_role

    if get_professional_role(root, professional_role_id) is None:
        raise ValueError(f"Professional Role 不存在: {professional_role_id}")


# ---------------------------------------------------------------- CRUD / lifecycle

def create_workforce(root: str | Path, *, name: str, company_id: str = "",
                     scope_type: str = "global", scope_id: str = "",
                     description: str = "",
                     professional_role_refs: list[str] | None = None,
                     capability_refs: list[str] | None = None,
                     governance_refs: list[str] | None = None,
                     legacy_role_refs: list[str] | None = None,
                     status: str = "draft",
                     workforce_id: str | None = None) -> dict[str, Any]:
    """创建 Workforce (OS Core SSOT)。

    - company_id 若提供必须存在 (MU-CORE-01 边界);
    - scope_type=department 时 scope_id 必须是存在的 Department (经 org SSOT);
    - professional_role_refs 必须存在于 Professional SSOT;
    - capability_refs 仅契约 (不实现 Capability);
    - legacy_role_refs 为兼容字段 (旧 role 词汇, 待后续 MU 收敛, 不参与 OS 语义)。
    """
    if status not in WORKFORCE_STATES:
        raise ValueError(f"未知 status: {status} (可选: {WORKFORCE_STATES})")
    if scope_type not in SCOPE_TYPES:
        raise ValueError(f"未知 scope_type: {scope_type} (可选: {SCOPE_TYPES})")
    company_id = str(company_id or "")
    if company_id:
        from .os_core_company_organization import get_company

        if get_company(root, company_id) is None:
            raise ValueError(f"Company 不存在: {company_id}")
    scope_id = str(scope_id or "")
    if scope_type == "department":
        if not scope_id:
            raise ValueError("scope_type=department 必须提供 scope_id")
        from .os_core_company_organization import get_department

        dept = get_department(root, scope_id)
        if dept is None:
            raise ValueError(f"Department 不存在: {scope_id}")
        if company_id and dept.get("company_id") != company_id:
            raise ValueError(
                f"Department {scope_id} 属于 {dept.get('company_id')}, 不是 {company_id}")
    elif scope_id:
        raise ValueError("scope_type=global 不接受 scope_id")

    from .os_core_capability import validate_capability_ref

    pr_refs = list(professional_role_refs or [])
    for prid in pr_refs:
        _require_professional_role(root, prid)
    data = _load(root)
    wid = workforce_id or f"WF-{uuid.uuid4().hex[:10]}"
    if wid in data:
        raise ValueError(f"Workforce 已存在: {wid}")
    for rec in data.values():
        if (rec["name"] == name and rec.get("company_id", "") == company_id
                and rec.get("scope_type") == scope_type
                and rec.get("scope_id", "") == scope_id
                and rec["status"] != "retired"):
            raise ValueError(f"Workforce 名称已存在: {name}")
    now = _now_iso()
    rec = {"workforce_id": wid, "name": name, "description": description,
           "company_id": company_id, "scope_type": scope_type, "scope_id": scope_id,
           "status": status, "member_refs": [], "professional_role_refs": pr_refs,
           "capability_refs": [validate_capability_ref(root, c)
                               for c in (capability_refs or [])],
           "governance_refs": [str(g) for g in (governance_refs or [])],
           "legacy_role_refs": [str(r) for r in (legacy_role_refs or [])],
           "history": [{"from": "", "to": status, "at": now, "note": "created"}],
           "created_at": now, "updated_at": now}
    data[wid] = rec
    _save(root, data)
    return rec


def get_workforce(root: str | Path, workforce_id: str) -> dict[str, Any] | None:
    return _load(root).get(str(workforce_id))


def list_workforces(root: str | Path, *, company_id: str = "",
                    status: str = "") -> list[dict[str, Any]]:
    recs = list(_load(root).values())
    if company_id:
        recs = [r for r in recs if r.get("company_id", "") == str(company_id)]
    if status:
        recs = [r for r in recs if r["status"] == str(status)]
    return sorted(recs, key=lambda r: r.get("created_at", ""))


def update_workforce(root: str | Path, workforce_id: str, *, name: str | None = None,
                     description: str | None = None,
                     professional_role_refs: list[str] | None = None,
                     capability_refs: list[str] | None = None,
                     governance_refs: list[str] | None = None) -> dict[str, Any]:
    data = _load(root)
    rec = data.get(str(workforce_id))
    if rec is None:
        raise ValueError(f"Workforce 不存在: {workforce_id}")
    if name is not None:
        rec["name"] = name
    if description is not None:
        rec["description"] = description
    if professional_role_refs is not None:
        for prid in professional_role_refs:
            _require_professional_role(root, prid)
        rec["professional_role_refs"] = list(professional_role_refs)
    if capability_refs is not None:
        from .os_core_capability import validate_capability_ref

        rec["capability_refs"] = [validate_capability_ref(root, c) for c in capability_refs]
    if governance_refs is not None:
        rec["governance_refs"] = [str(g) for g in governance_refs]
    rec["updated_at"] = _now_iso()
    _save(root, data)
    return rec


def set_workforce_status(root: str | Path, workforce_id: str, target: str) -> dict[str, Any]:
    if target not in WORKFORCE_STATES:
        raise ValueError(f"未知状态: {target}")
    data = _load(root)
    rec = data.get(str(workforce_id))
    if rec is None:
        raise ValueError(f"Workforce 不存在: {workforce_id}")
    current = rec["status"]
    if target == current:
        return rec
    if target not in WORKFORCE_TRANSITIONS.get(current, ()):
        raise ValueError(f"非法状态迁移: {current} → {target}")
    rec["history"].append({"from": current, "to": target, "at": _now_iso(),
                           "note": "status change"})
    rec["status"] = target
    rec["updated_at"] = _now_iso()
    _save(root, data)
    return rec


# ---------------------------------------------------------------- membership / roles

def add_member(root: str | Path, workforce_id: str, identity_id: str,
               *, professional_role_ref: str = "") -> dict[str, Any]:
    """加入成员 (引用 Identity, 不创建主体)。"""
    _require_identity(root, identity_id)
    if professional_role_ref:
        _require_professional_role(root, professional_role_ref)
    data = _load(root)
    rec = data.get(str(workforce_id))
    if rec is None:
        raise ValueError(f"Workforce 不存在: {workforce_id}")
    if str(identity_id) not in rec["member_refs"]:
        rec["member_refs"].append(str(identity_id))
    if professional_role_ref and professional_role_ref not in rec["professional_role_refs"]:
        rec["professional_role_refs"].append(professional_role_ref)
    rec["updated_at"] = _now_iso()
    _save(root, data)
    return rec


def remove_member(root: str | Path, workforce_id: str, identity_id: str) -> dict[str, Any]:
    data = _load(root)
    rec = data.get(str(workforce_id))
    if rec is None:
        raise ValueError(f"Workforce 不存在: {workforce_id}")
    rec["member_refs"] = [m for m in rec["member_refs"] if m != str(identity_id)]
    rec["updated_at"] = _now_iso()
    _save(root, data)
    return rec


def assign_professional_role(root: str | Path, workforce_id: str,
                             professional_role_id: str) -> dict[str, Any]:
    _require_professional_role(root, professional_role_id)
    data = _load(root)
    rec = data.get(str(workforce_id))
    if rec is None:
        raise ValueError(f"Workforce 不存在: {workforce_id}")
    if professional_role_id not in rec["professional_role_refs"]:
        rec["professional_role_refs"].append(professional_role_id)
    rec["updated_at"] = _now_iso()
    _save(root, data)
    return rec


# ---------------------------------------------------------------- resolve

def resolve_workforce(root: str | Path, workforce_id: str) -> dict[str, Any]:
    """解析 Workforce -> 成员 Identity / Professional Role (引用解析, 不复制数据)。"""
    from .os_core_identity import get_identity
    from .os_core_professional import get_professional_role

    rec = get_workforce(root, workforce_id)
    if rec is None:
        raise ValueError(f"Workforce 不存在: {workforce_id}")
    members = [ident for m in rec["member_refs"]
               if (ident := get_identity(root, m)) is not None]
    roles = [r for p in rec["professional_role_refs"]
             if (r := get_professional_role(root, p)) is not None]
    return {"workforce": rec, "members": members, "professional_roles": roles}


def resolve_workforce_capabilities(root: str | Path, workforce_id: str) -> dict[str, Any]:
    """Workforce -> capability_refs -> Capability SSOT 解析 (MU-CORE-07)。"""
    from .os_core_capability import resolve_capability

    rec = get_workforce(root, workforce_id)
    if rec is None:
        raise ValueError(f"Workforce 不存在: {workforce_id}")
    caps = [resolve_capability(root, c) for c in rec.get("capability_refs", [])]
    return {"workforce": rec, "capabilities": caps}


__all__ = [
    "SCOPE_TYPES",
    "WORKFORCE_STATES",
    "WORKFORCE_TRANSITIONS",
    "add_member",
    "assign_professional_role",
    "create_workforce",
    "get_workforce",
    "list_workforces",
    "remove_member",
    "resolve_workforce_capabilities",
    "resolve_workforce",
    "set_workforce_status",
    "update_workforce",
]
