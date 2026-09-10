"""factory-console/os_core_identity.py — OS Core Boundary: Identity (MU-CORE-02).

Identity = Human | Agent 的统一 OS Core 主体原语。

- Identity 是 Execution actor / Approval actor / Governance subject / Workforce member /
  Audit subject / Evidence attribution subject。
- Identity ≠ Role ≠ Employee ≠ AgentEntity ≠ Workforce ≠ Capability ≠ Plugin。
- Employee / AgentEntity 是 Identity 的 profile 来源 (projection), 不各自充当平台主体。

Company Boundary (证据决定, 见 MU-CORE-02 报告):
- Human Identity: 公司内主体 -> company_id 必填 (Employee.company_id 为证)。
- Agent Identity: 当前 agents/agent_entity 均无 company 绑定 -> company_id 可空 (= 全局/跨公司);
  跨公司归属由后续 Role/Workforce assignment/scope 表达 (本 MU 只保留契约, 不实现 scope)。

范围: 只建立 Identity 主体层 + Employee/AgentEntity projection + actor 引用解析。
不含 Role / Professional / Workforce / Project / Work / Capability / Plugin / FactorySpec。

API:
    create_identity / get_identity / list_identities / resolve_identity
    ensure_identity (按 profile_ref 幂等)
    project_employee / project_agent
    resolve_actor_identity (actor 字符串 -> identity_id; resolve-only, 不创建)

存储: <root>/identity/identities.json
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

IDENTITY_TYPES: tuple[str, ...] = ("human", "agent")
IDENTITY_STATUSES: tuple[str, ...] = ("active", "retired")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ORG_SRC = _REPO_ROOT / "factory-org"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_identity_id() -> str:
    return f"I-{uuid.uuid4().hex[:10]}"


def _file(root: str | Path) -> Path:
    return Path(root) / "identity" / "identities.json"


def _load(root: str | Path) -> dict[str, dict[str, Any]]:
    p = _file(root)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    ids = data.get("identities") if isinstance(data, dict) else None
    return ids if isinstance(ids, dict) else {}


def _save(root: str | Path, data: dict[str, dict[str, Any]]) -> None:
    p = _file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"identities": data}, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def _org_store(root: str | Path) -> Any:
    try:
        from org import store as org_store
    except ModuleNotFoundError:  # 源码态
        src = str(_ORG_SRC)
        if src not in sys.path:
            sys.path.insert(0, src)
        from org import store as org_store
    return org_store.OrgStore(Path(root) / "org")


# ---------------------------------------------------------------- 主体 CRUD

def create_identity(root: str | Path, *, identity_type: str, company_id: str = "",
                    profile_ref: str = "", display_name: str = "",
                    identity_id: str | None = None,
                    status: str = "active") -> dict[str, Any]:
    """新建 Identity 主体 (identity_type=human|agent)。"""
    if identity_type not in IDENTITY_TYPES:
        raise ValueError(f"未知 identity_type: {identity_type} (可选: {IDENTITY_TYPES})")
    if status not in IDENTITY_STATUSES:
        raise ValueError(f"未知 status: {status} (可选: {IDENTITY_STATUSES})")
    data = _load(root)
    iid = identity_id or new_identity_id()
    if iid in data:
        raise ValueError(f"Identity 已存在: {iid}")
    if profile_ref:
        for rec in data.values():
            if rec.get("profile_ref") == profile_ref:
                raise ValueError(f"profile_ref 已被占用: {profile_ref} -> {rec['identity_id']}")
    rec = {"identity_id": iid, "identity_type": identity_type,
           "company_id": str(company_id or ""), "profile_ref": str(profile_ref or ""),
           "display_name": str(display_name or ""), "status": status,
           "created_at": _now_iso(), "updated_at": _now_iso()}
    data[iid] = rec
    _save(root, data)
    return rec


def get_identity(root: str | Path, identity_id: str) -> dict[str, Any] | None:
    return _load(root).get(str(identity_id))


def list_identities(root: str | Path, *, identity_type: str = "",
                    company_id: str = "") -> list[dict[str, Any]]:
    recs = list(_load(root).values())
    if identity_type:
        recs = [r for r in recs if r.get("identity_type") == identity_type]
    if company_id:
        recs = [r for r in recs if r.get("company_id") == str(company_id)]
    return sorted(recs, key=lambda r: r.get("created_at", ""))


def resolve_identity(root: str | Path, ref: str) -> dict[str, Any] | None:
    """按 identity_id 或 profile_ref 解析。"""
    ref = str(ref or "")
    if not ref:
        return None
    data = _load(root)
    if ref in data:
        return data[ref]
    for rec in data.values():
        if rec.get("profile_ref") == ref:
            return rec
    return None


def ensure_identity(root: str | Path, *, identity_type: str, profile_ref: str,
                    company_id: str = "", display_name: str = "") -> dict[str, Any]:
    """按 profile_ref 幂等投影 (已存在 -> 原样返回; 公司冲突 -> ValueError)。"""
    existing = resolve_identity(root, profile_ref)
    if existing is not None:
        if existing.get("identity_type") != identity_type:
            raise ValueError(
                f"profile_ref {profile_ref} 已属于 {existing.get('identity_type')}, "
                f"不能投影为 {identity_type}")
        old_company = str(existing.get("company_id") or "")
        new_company = str(company_id or "")
        if old_company and new_company and old_company != new_company:
            raise ValueError(
                f"Identity {existing['identity_id']} 属于公司 {old_company}, "
                f"不能投影到公司 {new_company} (公司隔离)")
        return existing
    return create_identity(root, identity_type=identity_type, company_id=company_id,
                           profile_ref=profile_ref, display_name=display_name)


# ---------------------------------------------------------------- 投影 (Employee / AgentEntity)

def project_employee(root: str | Path, employee_id: str) -> dict[str, Any]:
    """Employee -> Human Identity 投影 (Employee.company_id 为 Human 的公司边界)。"""
    emp = _org_store(root).get_employee(str(employee_id))
    if emp is None:
        raise ValueError(f"Employee 不存在: {employee_id}")
    return ensure_identity(root, identity_type="human",
                           profile_ref=f"employee:{emp.id}",
                           company_id=emp.company_id, display_name=emp.name)


def project_agent(root: str | Path, agent_id: str, *, agents_file: Any = None,
                  company_id: str = "", display_name: str = "") -> dict[str, Any]:
    """AgentEntity/AgentRegistry -> Agent Identity 投影 (读侧; 不改 AgentEntity)。

    Agent 当前无 company 绑定 -> company_id 默认可空 (全局/跨公司);
    跨公司 scope 由后续 Role/Workforce assignment 表达。
    """
    name = display_name or str(agent_id)
    try:
        from .session.agent_registry import AgentRegistry

        entity = AgentRegistry(agents_file=Path(agents_file) if agents_file else None).get(str(agent_id))
        if entity is not None and not display_name:
            name = getattr(entity, "name", None) or getattr(entity, "role", None) or name
    except Exception:  # noqa: BLE001 — registry 不可读时仍按 id 投影 (诚实: profile_ref only)
        pass
    return ensure_identity(root, identity_type="agent",
                           profile_ref=f"agent:{agent_id}",
                           company_id=company_id, display_name=name)


# ---------------------------------------------------------------- actor 引用 (Execution/Approval/Audit)

def resolve_actor_identity(root: str | Path, actor: str) -> str:
    """actor 字符串 -> identity_id (resolve-only; 未登记 -> 空字符串, 不创建、不阻断)。

    匹配顺序: identity_id -> profile_ref(employee:/agent:/裸 id) -> display_name。
    """
    actor = str(actor or "")
    if not actor:
        return ""
    data = _load(root)
    if actor in data:
        return actor
    candidates = (f"employee:{actor}", f"agent:{actor}")
    for rec in data.values():
        if rec.get("profile_ref") in candidates or rec.get("profile_ref") == actor:
            return str(rec["identity_id"])
    for rec in data.values():
        if rec.get("display_name") == actor:
            return str(rec["identity_id"])
    return ""


__all__ = [
    "IDENTITY_TYPES",
    "create_identity",
    "ensure_identity",
    "get_identity",
    "list_identities",
    "new_identity_id",
    "project_agent",
    "project_employee",
    "resolve_actor_identity",
    "resolve_identity",
]
