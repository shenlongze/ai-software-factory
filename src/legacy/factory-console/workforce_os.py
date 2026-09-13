"""factory-console/workforce_os.py — S30 Workforce Intelligence & Organization Foundation.

把 S16 Multi-Agent Workforce 升级为 Workforce OS:
- Organization → Department → Workforce → AgentProfile (层级 + lineage)
- Workforce Lifecycle (DRAFT→ACTIVE→SUSPENDED→RETIRED, append-only + audit)
- Performance Profile (从 Production Evidence 投影, 不造数据)
- 确定性 Agent Selection (capability match → permission → policy, 非 LLM)

边界:
- Production Core = SSOT (Workforce 只投影/编排, 不改 Production Truth)
- 复用 S16 ROLE_CAPABILITIES/PERMISSION_MATRIX + S17 governance + AgentRegistry
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .workforce import ROLE_CAPABILITIES, PERMISSION_MATRIX, list_agents

#: Lifecycle 状态机
WFL_STATES = ("DRAFT", "ACTIVE", "SUSPENDED", "RETIRED")
WFL_TRANSITIONS = {
    "DRAFT": ("ACTIVE", "RETIRED"),
    "ACTIVE": ("SUSPENDED", "RETIRED"),
    "SUSPENDED": ("ACTIVE", "RETIRED"),
    "RETIRED": (),
}

#: 每个角色默认 skill/tool/model binding (确定性, 非 prompt)
ROLE_BINDINGS: dict[str, dict[str, Any]] = {
    "product_manager": {"skills": ["requirement_analysis"], "tools": ["llm"], "model": "default"},
    "market_analyst": {"skills": ["market_research"], "tools": ["llm"], "model": "default"},
    "ux_designer": {"skills": ["ui_design"], "tools": ["llm"], "model": "default"},
    "software_architect": {"skills": ["system_design"], "tools": ["llm"], "model": "default"},
    "software_developer": {"skills": ["coding"], "tools": ["llm", "codex"], "model": "default"},
    "qa_engineer": {"skills": ["testing"], "tools": ["llm", "pytest"], "model": "default"},
    "release_engineer": {"skills": ["release"], "tools": ["llm"], "model": "default"},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "workforce_os" / f"{name}.json"


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


def _audit(root: Path | str, event_type: str, payload: dict[str, Any]) -> None:
    try:
        from .audit.audit_event import AuditEvent
        from .audit.audit_store import AuditStore

        store = AuditStore(workspace=None, file=str(Path(root) / "audit" / "audit_events.json"))
        ev = AuditEvent.create(
            event_type,
            trace_id=payload.get("entity_id") or "",
            actor_type="system", actor_id="workforce_os",
            action=f"workforce_os.{event_type.lower()}",
            source="workforce_os", decision="allow",
            decision_reason=payload.get("note") or "",
            evidence=[payload], result={"ok": True}, metadata={"workforce_os": payload},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


def _next_state(current: str, target: str) -> str:
    if target not in WFL_STATES:
        raise ValueError(f"未知状态: {target}")
    if target == current:
        return target
    if target not in WFL_TRANSITIONS.get(current, ()):
        raise ValueError(f"非法状态迁移: {current} → {target}")
    return target


# ------------------------------------------------------------------ Organization

def create_organization(root: Path | str, *, name: str = "AI Factory",
                        created_by: str = "system") -> dict[str, Any]:
    """MU-CORE-01: 委托 OS Core Boundary 创建 Company (org SSOT)。

    本函数不再持有 Organization Truth (不落 ops/workforce_os/organizations.json);
    返回兼容形状 (org_id=company id), 供既有 Web/CLI 消费者平滑迁移。
    """
    from .os_core_company_organization import create_company

    company = create_company(root, name=name)
    org = {"org_id": company["id"], "name": company.get("name", name),
           "departments": [], "created_at": company.get("created_at")}
    _audit(root, "WORKFORCE_ORGANIZATION_CREATED",
           {"entity_id": org["org_id"], "name": name, "ssot": "org"})
    return org


def list_organizations(root: Path | str) -> list[dict[str, Any]]:
    """MU-CORE-01: 从 org SSOT 投影 (只读视图), 不再读第二组织真相。"""
    from .os_core_company_organization import list_companies, list_departments

    out: list[dict[str, Any]] = []
    for c in list_companies(root):
        depts = [d["id"] for d in list_departments(root, company_id=c["id"])]
        out.append({"org_id": c["id"], "name": c.get("name", ""),
                    "departments": depts, "created_at": c.get("created_at")})
    return out


def create_department(root: Path | str, *, org_id: str, name: str) -> dict[str, Any]:
    """MU-CORE-01: 委托 OS Core Boundary 创建 Department (org SSOT)。"""
    from .os_core_company_organization import create_department as _create_dept
    from .os_core_company_organization import get_company

    if get_company(root, org_id) is None:
        raise ValueError(f"Organization 不存在: {org_id}")
    dept = _create_dept(root, company_id=org_id, name=name)
    compat = {"dept_id": dept["id"], "org_id": org_id, "name": dept.get("name", name),
              "workforces": [], "created_at": dept.get("created_at")}
    _audit(root, "WORKFORCE_DEPARTMENT_CREATED",
           {"entity_id": compat["dept_id"], "name": name, "ssot": "org"})
    return compat


# ------------------------------------------------------------------ Workforce

def _compat_workforce(root: Path | str, rec: dict[str, Any]) -> dict[str, Any]:
    """Workforce SSOT 记录 -> 旧 compat 形状。

    MU-CORE-04: Workforce 事实 = os_core_workforce SSOT; 本函数只投影兼容形状。
    `agents` 由成员 Identity 的 profile_ref(agent:*) 投影到 AgentProfile store
    (AgentProfile 是 profile, 不是 Workforce/Identity 主体)。
    """
    agent_ids: set[str] = set()
    try:
        from .os_core_identity import get_identity

        for mid in rec.get("member_refs", []):
            ident = get_identity(root, mid) or {}
            ref = str(ident.get("profile_ref") or "")
            if ref.startswith("agent:"):
                agent_ids.add(ref.split(":", 1)[1])
    except Exception:  # noqa: BLE001 — 投影失败不阻断 compat
        pass
    agents = [p for p in _load(root, "agent_profiles") if p.get("agent_id") in agent_ids]
    return {"workforce_id": rec["workforce_id"], "dept_id": rec.get("scope_id", ""),
            "name": rec["name"], "status": str(rec["status"]).upper(),
            "roles": list(rec.get("legacy_role_refs") or []), "agents": agents,
            "history": list(rec.get("history") or []),
            "created_at": rec.get("created_at"), "updated_at": rec.get("updated_at"),
            "company_id": rec.get("company_id", ""),
            "member_refs": list(rec.get("member_refs") or []),
            "professional_role_refs": list(rec.get("professional_role_refs") or []),
            "capability_refs": list(rec.get("capability_refs") or [])}


def create_workforce(root: Path | str, *, dept_id: str = "", name: str = "production",
                     roles: list[str] | None = None,
                     created_by: str = "system") -> dict[str, Any]:
    """MU-CORE-04: Workforce 实体写入 OS Workforce SSOT (旧 workforce store 不再写入)。"""
    from .os_core_company_organization import get_department
    from .os_core_workforce import create_workforce as _create

    roles = roles or list(ROLE_CAPABILITIES.keys())
    company_id, scope_type, scope_id = "", "global", ""
    if dept_id:
        dept = get_department(root, dept_id)
        if dept is None:
            raise ValueError(f"Department 不存在: {dept_id}")
        company_id, scope_type, scope_id = dept.get("company_id", ""), "department", dept_id
    rec = _create(root, name=name, company_id=company_id, scope_type=scope_type,
                  scope_id=scope_id, legacy_role_refs=roles)
    _audit(root, "WORKFORCE_CREATED", {"entity_id": rec["workforce_id"], "name": name,
                                       "ssot": "os_workforce"})
    return _compat_workforce(root, rec)


def workforce_status(root: Path | str, workforce_id: str, *, target: str,
                     actor: str = "system") -> dict[str, Any]:
    """Lifecycle 迁移 (委托 OS Workforce SSOT; append-only + 非法迁移拒绝)。"""
    from .os_core_workforce import set_workforce_status as _set

    rec = _set(root, workforce_id, str(target).lower())
    _audit(root, "WORKFORCE_STATUS_CHANGED",
           {"entity_id": workforce_id, "to": rec["status"], "ssot": "os_workforce"})
    return _compat_workforce(root, rec)


def attach_agent(root: Path | str, *, workforce_id: str, role: str,
                 agent_id: str = "") -> dict[str, Any]:
    """Attach AgentProfile 到 Workforce: profile 存 AgentProfile; 成员引用 Agent Identity。"""
    from .os_core_identity import project_agent
    from .os_core_workforce import add_member, get_workforce as _get

    rec = _get(root, workforce_id)
    if rec is None:
        raise ValueError(f"Workforce 不存在: {workforce_id}")
    if rec["status"] != "draft":
        raise ValueError(f"Workforce 非 DRAFT 状态 ({str(rec['status']).upper()}) — 不可 attach")
    if role not in ROLE_CAPABILITIES:
        raise ValueError(f"未知角色: {role}")
    profile = _get_or_create_agent_profile(root, role, agent_id)
    ident = project_agent(root, profile["agent_id"], display_name=profile.get("agent_id", ""))
    add_member(root, workforce_id, ident["identity_id"])
    return profile


def get_workforce(root: Path | str, workforce_id: str) -> dict[str, Any]:
    from .os_core_workforce import get_workforce as _get

    rec = _get(root, workforce_id)
    if rec is None:
        raise ValueError(f"Workforce 不存在: {workforce_id}")
    return _compat_workforce(root, rec)


def list_workforces(root: Path | str) -> list[dict[str, Any]]:
    from .os_core_workforce import list_workforces as _list

    return [_compat_workforce(root, r) for r in _list(root)]


# ------------------------------------------------------------------ AgentProfile

def _get_or_create_agent_profile(root: Path | str, role: str, agent_id: str = "") -> dict[str, Any]:
    """从 AgentRegistry 或创建 AgentProfile (确定性强绑定)。"""
    for p in _load(root, "agent_profiles"):
        if p["role"] == role and (not agent_id or p["agent_id"] == agent_id):
            return p
    # 从 S16 AgentRegistry 找真实 agent (若存在)
    reg_agent_id = agent_id
    if not reg_agent_id:
        for a in list_agents(root):
            if a.get("role") == role:
                reg_agent_id = a.get("agent_id") or a.get("id", "")
                break
    bind = ROLE_BINDINGS.get(role, {"skills": [], "tools": [], "model": "default"})
    profile = {
        "agent_id": reg_agent_id or f"agt-os-{uuid.uuid4().hex[:8]}",
        "role": role,
        "capabilities": ROLE_CAPABILITIES.get(role, []),
        "skills": bind.get("skills", []),
        "tools": bind.get("tools", []),
        "model": bind.get("model", "default"),
        "provider": "deepseek",
        "policies": [f"permission:{role}"],
        "status": "ACTIVE",
        "created_at": _now_iso(),
    }
    _save(root, "agent_profiles", _load(root, "agent_profiles") + [profile])
    return profile


def list_agent_profiles(root: Path | str) -> list[dict[str, Any]]:
    return _load(root, "agent_profiles")


def capabilities_list(root: Path | str) -> list[dict[str, str]]:
    """Capability 确定性 Contract 列表 (从 ROLE_CAPABILITIES 反查)。"""
    out = []
    for role, caps in ROLE_CAPABILITIES.items():
        for cap in caps:
            out.append({"capability": cap, "role": role,
                        "permitted": next((a for a, rs in PERMISSION_MATRIX.items() if role in rs), "")})
    return out


# ------------------------------------------------------------------ Performance Profile (从 Evidence 投影)

def agent_performance(root: Path | str, agent_id: str) -> dict[str, Any]:
    """Performance 从真实 Production Evidence 投影 (不造数据)。"""
    # 收集该 agent 相关的 production runs (通过 task → production_run 关联)
    tasks = _load_tasks_by_agent(root, agent_id)
    runs = []
    from .production_run import get_production_run
    for t in tasks:
        pr_id = t.get("production_run_id", "")
        if pr_id:
            run = get_production_run(root, pr_id)
            if run is not None:
                runs.append(run)
    if not runs:
        return {"agent_id": agent_id, "sample_count": 0, "evidence_refs": [],
                "explain": "无 Production Evidence (无 runs)"}
    n = len(runs)
    completed = sum(1 for r in runs if r.get("state") == "COMPLETED")
    failed = sum(1 for r in runs if r.get("state") == "FAILED")
    # verification pass rate (从 run artifacts 投影)
    ver_pass = 0
    from .artifact_lifecycle import get_artifact
    for r in runs:
        for aid in r.get("artifacts", []) or []:
            art = get_artifact(root, aid)
            if art is not None and art.get("verification", {}).get("result") == "PASS":
                ver_pass += 1
    # evaluation score (从 run evaluation 投影)
    scores = []
    from .production_evaluation import get_evaluation
    for r in runs:
        ev = get_evaluation(root, r.get("run_id", ""))
        if ev is not None and ev.get("overall_score") is not None:
            scores.append(ev["overall_score"])
    perf = {
        "agent_id": agent_id,
        "sample_count": n,
        "success_rate": round(completed / n, 3),
        "failure_rate": round(failed / n, 3),
        "verification_pass_rate": round(ver_pass / max(1, n), 3),
        "evaluation_score": round(sum(scores) / len(scores), 1) if scores else None,
        "evidence_refs": [r.get("run_id", "") for r in runs],
        "explain": f"从 {n} 个真实 ProductionRun 投影",
    }
    return perf


def _load_tasks_by_agent(root: Path | str, agent_id: str) -> list[dict[str, Any]]:
    """该 agent 的 tasks (通过 task.agent_id 或 role 匹配)。"""
    profile = None
    for p in _load(root, "agent_profiles"):
        if p["agent_id"] == agent_id:
            profile = p
            break
    tasks = []
    try:
        from .workforce import _load_tasks
        for t in _load_tasks(root):
            if t.get("agent_id") == agent_id or (profile and t.get("role") == profile["role"]):
                tasks.append(t)
    except Exception:  # noqa: BLE001
        pass
    return tasks


# ------------------------------------------------------------------ 确定性 Agent Selection

def select_agent_deterministic(root: Path | str, *, required_capability: str,
                               workforce_id: str = "") -> dict[str, Any]:
    """确定性 Selection: capability match → permission → policy (非 LLM)。

    Task → RequiredCapability → 候选 agents → 校验权限 → 返回首个 ACTIVE。
    """
    # 1. capability match (从 ROLE_CAPABILITIES)
    candidates = []
    for role, caps in ROLE_CAPABILITIES.items():
        if required_capability in caps:
            candidates.append(role)
    if not candidates:
        return {"selected": False, "reason": f"无角色具备 capability: {required_capability}"}
    # 2. permission check (action 必须允许该 role)
    permitted = [r for r in candidates
                 if any(required_capability == a or required_capability in PERMISSION_MATRIX.get(a, [])
                        for a in PERMISSION_MATRIX if r in PERMISSION_MATRIX[a])]
    pool = permitted or candidates
    # 3. 从 AgentRegistry 找真实 agent
    for role in pool:
        for a in list_agents(root):
            if a.get("role") == role:
                return {"selected": True, "agent_id": a.get("agent_id") or a.get("id", ""),
                        "role": role, "capability": required_capability,
                        "reason": "capability match + permission + agent 可用"}
    # 4. 无注册 agent → AgentProfile 兜底
    for role in pool:
        profile = _get_or_create_agent_profile(root, role)
        return {"selected": True, "agent_id": profile["agent_id"], "role": role,
                "capability": required_capability,
                "reason": "capability match (AgentProfile 兜底)"}
    return {"selected": False, "reason": "无可用 agent"}


# ------------------------------------------------------------------ Lineage

def workforce_os_lineage(root: Path | str, agent_id: str = "",
                         workforce_id: str = "") -> dict[str, Any]:
    """全链 lineage: org → dept → workforce → agent → tasks → runs。"""
    from .os_core_company_organization import list_companies, list_departments

    orgs = [{"org_id": c["id"], "name": c.get("name", ""),
             "departments": [d["id"] for d in list_departments(root, company_id=c["id"])],
             "created_at": c.get("created_at")} for c in list_companies(root)]
    depts = [{"dept_id": d["id"], "org_id": d["company_id"], "name": d.get("name", ""),
              "created_at": d.get("created_at")} for d in list_departments(root)]
    out = {"organizations": orgs, "departments": depts, "workforces": []}
    for w in list_workforces(root):
        if workforce_id and w["workforce_id"] != workforce_id:
            continue
        w_agents = [a for a in w["agents"] if not agent_id or a["agent_id"] == agent_id]
        out["workforces"].append({"workforce_id": w["workforce_id"], "name": w["name"],
                                  "status": w["status"], "agents": w_agents,
                                  "history": w["history"]})
    return out
