"""factory-console/os_core_role.py — OS Core Boundary: Role Definition + Role Assignment (MU-CORE-03).

语义分离 (Constitution v2 Art.09/42):
- **Role Definition** = "这个角色是什么" (职责/能力/执行语义)。SSOT = `exec/roles.py`
  ROLE_REGISTRY (S7-001 事实源; org.Role.role_ref 亦指向它)。本模块只提供只读 boundary,
  不新建第二份定义。
- **Role Assignment** = "哪个 Identity 在哪个 Scope 承担这个 Role"。SSOT = 本模块
  `<root>/role/assignments.json` (新域)。

Scope 证据 (不臆造): org.Role 是 company-scoped (org.Role.company_id);
Agent Identity 当前无公司绑定 (MU-CORE-02 证据) -> 因此本 MU 只支持:
    scope_type ∈ {global, company}
Project / Work scope 待对应 MU 有证据后再扩展, 本 MU 不写入 schema。

范围: Root/RoleAssignment 之外 (Capability/Workforce/Project/Work/Plugin/Resolution) 不在本 MU。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCOPE_TYPES: tuple[str, ...] = ("global", "company")
ASSIGNMENT_STATUSES: tuple[str, ...] = ("active", "revoked")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_EXEC_SRC = _REPO_ROOT / "factory-exec"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _exec_roles() -> Any:
    """导入 exec/roles.py (源码态挂 factory-exec 到 sys.path; 安装态直接 import)。"""
    try:
        from exec import roles as exec_roles
    except ModuleNotFoundError:
        src = str(_EXEC_SRC)
        if src not in sys.path:
            sys.path.insert(0, src)
        from exec import roles as exec_roles
    return exec_roles


# ================================================================ Role Definition (只读 boundary)

def list_role_definitions() -> list[dict[str, Any]]:
    """Role Definition 清单 (来自 exec/roles.py SSOT)。"""
    roles = _exec_roles()
    out = []
    for d in roles.list_role_dicts():
        out.append({**d, "description": "", "status": "active", "source": "exec/roles.py"})
    return out


def get_role_definition(role_id: str) -> dict[str, Any] | None:
    roles = _exec_roles()
    for d in roles.list_role_dicts():
        if d["role_id"] == str(role_id):
            return {**d, "description": "", "status": "active", "source": "exec/roles.py"}
    return None


def resolve_role_definition(ref: str) -> dict[str, Any]:
    """按 role_id / 显示名 / 别名解析 (单一注册表入口); 未解析 -> ValueError。"""
    roles = _exec_roles()
    try:
        d = roles.resolve_role(ref)
    except roles.RoleError as exc:
        raise ValueError(str(exc)) from exc
    return {"role_id": d.role_id, "name": d.name, "capabilities": list(d.capabilities),
            "workflow_stages": list(d.workflow_stages), "execution_kind": d.execution_kind,
            "description": "", "status": "active", "source": "exec/roles.py"}


# ================================================================ Role Assignment (新 SSOT)

def _file(root: str | Path) -> Path:
    return Path(root) / "role" / "assignments.json"


def _load(root: str | Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    items = data.get("assignments") if isinstance(data, dict) else None
    return items if isinstance(items, dict) else {}


def _save(root: str | Path, data: dict[str, dict[str, Any]]) -> None:
    p = _file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"assignments": data}, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def create_role_assignment(root: str | Path, *, identity_id: str, role_id: str,
                           scope_type: str = "global", scope_id: str = "",
                           status: str = "active",
                           assignment_id: str | None = None) -> dict[str, Any]:
    """新建 Role Assignment: 哪个 Identity 在哪个 Scope 承担哪个 Role。

    - identity_id 必须存在于 Identity SSOT (MU-CORE-02)。
    - role_id 必须能解析到 Role Definition (exec/roles.py SSOT)。
    - scope_type='company' 时 scope_id 必须是存在的 Company (MU-CORE-01 边界)。
    """
    from .os_core_identity import get_identity

    if scope_type not in SCOPE_TYPES:
        raise ValueError(f"未知 scope_type: {scope_type} (可选: {SCOPE_TYPES})")
    if status not in ASSIGNMENT_STATUSES:
        raise ValueError(f"未知 status: {status} (可选: {ASSIGNMENT_STATUSES})")
    if get_identity(root, str(identity_id)) is None:
        raise ValueError(f"Identity 不存在: {identity_id}")
    definition = resolve_role_definition(role_id)
    canonical_role = definition["role_id"]
    scope_id = str(scope_id or "")
    if scope_type == "company":
        if not scope_id:
            raise ValueError("scope_type=company 必须提供 scope_id")
        from .os_core_company_organization import get_company

        if get_company(root, scope_id) is None:
            raise ValueError(f"Company 不存在: {scope_id}")
    elif scope_id:
        raise ValueError("scope_type=global 不接受 scope_id")

    data = _load(root)
    for rec in data.values():
        if (rec["identity_id"] == str(identity_id) and rec["role_id"] == canonical_role
                and rec["scope_type"] == scope_type and rec.get("scope_id", "") == scope_id
                and rec["status"] == "active"):
            raise ValueError(
                f"Role Assignment 已存在: {rec['assignment_id']} "
                f"({identity_id} -> {canonical_role} @ {scope_type}:{scope_id or '-'})")
    aid = assignment_id or f"RA-{uuid.uuid4().hex[:10]}"
    if aid in data:
        raise ValueError(f"Role Assignment 已存在: {aid}")
    rec = {"assignment_id": aid, "identity_id": str(identity_id),
           "role_id": canonical_role, "scope_type": scope_type, "scope_id": scope_id,
           "status": status, "created_at": _now_iso(), "updated_at": _now_iso()}
    data[aid] = rec
    _save(root, data)
    return rec


def get_role_assignment(root: str | Path, assignment_id: str) -> dict[str, Any] | None:
    return _load(root).get(str(assignment_id))


def list_role_assignments(root: str | Path, *, identity_id: str = "",
                          role_id: str = "", scope_type: str = "",
                          scope_id: str = "", status: str = "") -> list[dict[str, Any]]:
    recs = list(_load(root).values())
    if identity_id:
        recs = [r for r in recs if r["identity_id"] == str(identity_id)]
    if role_id:
        recs = [r for r in recs if r["role_id"] == str(role_id)]
    if scope_type:
        recs = [r for r in recs if r["scope_type"] == str(scope_type)]
    if scope_id:
        recs = [r for r in recs if r.get("scope_id", "") == str(scope_id)]
    if status:
        recs = [r for r in recs if r["status"] == str(status)]
    return sorted(recs, key=lambda r: r.get("created_at", ""))


def set_role_assignment_status(root: str | Path, assignment_id: str, status: str) -> dict[str, Any]:
    if status not in ASSIGNMENT_STATUSES:
        raise ValueError(f"未知 status: {status} (可选: {ASSIGNMENT_STATUSES})")
    data = _load(root)
    rec = data.get(str(assignment_id))
    if rec is None:
        raise ValueError(f"Role Assignment 不存在: {assignment_id}")
    rec["status"] = status
    rec["updated_at"] = _now_iso()
    _save(root, data)
    return rec


def resolve_identity_roles(root: str | Path, identity_id: str) -> list[dict[str, Any]]:
    """Identity -> Role Assignment -> Role Definition 解析链 (active only)。"""
    out = []
    for a in list_role_assignments(root, identity_id=identity_id, status="active"):
        definition = get_role_definition(a["role_id"]) or resolve_role_definition(a["role_id"])
        out.append({"assignment": a, "role": definition})
    return out


__all__ = [
    "SCOPE_TYPES",
    "create_role_assignment",
    "get_role_assignment",
    "get_role_definition",
    "list_role_assignments",
    "list_role_definitions",
    "resolve_identity_roles",
    "resolve_role_definition",
    "set_role_assignment_status",
]
