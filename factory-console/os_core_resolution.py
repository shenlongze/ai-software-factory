"""factory-console/os_core_resolution.py — OS Core Service: Resolution (MU-CORE-08).

Resolution = 确定性解析服务: 根据工作需求解析"需要什么专业能力, 以及哪些合法的
ProfessionalRole / Workforce / Identity 能提供该能力"。

只解析, 不执行:
    不做 Plugin Closure / 不调用 Tool / 不运行 Agent / 不调 Model / 不创建 Execution/TaskNode。
    Resolution ≠ Execution ≠ Plugin ≠ Scheduler。

解析链:
    Work.required_capability_refs
      -> Capability SSOT (active)
      -> ProfessionalRole (status=active, capability_refs 命中)
      -> Workforce (status=active, capability_refs 命中, company scope 合法)
      -> Identity (active member)

SSOT: <root>/resolution/resolutions.json (RS-*; 一次解析事实, 不是 Capability 定义)。
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RESOLUTION_STATUSES: tuple[str, ...] = ("resolved", "unresolved")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: str | Path) -> Path:
    return Path(root) / "resolution" / "resolutions.json"


def _load(root: str | Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    items = data.get("resolutions") if isinstance(data, dict) else None
    return items if isinstance(items, dict) else {}


def _save(root: str | Path, data: dict[str, dict[str, Any]]) -> None:
    p = _file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"resolutions": data}, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def get_resolution(root: str | Path, resolution_id: str) -> dict[str, Any] | None:
    return _load(root).get(str(resolution_id))


def list_resolutions(root: str | Path, *, status: str = "") -> list[dict[str, Any]]:
    recs = list(_load(root).values())
    if status:
        recs = [r for r in recs if r.get("status") == str(status)]
    return sorted(recs, key=lambda r: r.get("created_at", ""))


# ---------------------------------------------------------------- 解析核心

def _company_of_work(root: str | Path, work: dict[str, Any]) -> tuple[str, str]:
    from .os_core_project import get_project

    project = get_project(root, work["project_id"])
    if project is None:
        raise ValueError(f"Project 不存在: {work['project_id']}")
    return str(project.get("company_id") or ""), str(project["id"])


def _company_eligible(company_id: str, workforce_company: str) -> bool:
    """Company isolation: 有 company 的 work 只匹配同 company 的 workforce;
    global(company="") 的 work 只匹配 global workforce。不发明跨公司规则。"""
    return (company_id or "") == (workforce_company or "")


def _resolve(root: str | Path, *, required_capability_refs: list[str],
             company_id: str = "", project_id: str = "", work_id: str = "",
             requested_professional_role_refs: list[str] | None = None,
             requested_workforce_refs: list[str] | None = None,
             requested_identity_refs: list[str] | None = None,
             constraints: dict[str, Any] | None = None) -> dict[str, Any]:
    from .os_core_capability import resolve_capability, validate_capability_ref
    from .os_core_identity import get_identity
    from .os_core_professional import list_professional_roles
    from .os_core_workforce import list_workforces

    requested_pr = {str(x) for x in (requested_professional_role_refs or [])}
    requested_wf = {str(x) for x in (requested_workforce_refs or [])}
    requested_idn = {str(x) for x in (requested_identity_refs or [])}

    matches: list[dict[str, Any]] = []
    unresolved: list[str] = []
    reasons: list[str] = []
    for ref in required_capability_refs:
        try:
            cap_id = validate_capability_ref(root, ref)          # active only; retired 拒绝
        except ValueError:
            unresolved.append(str(ref))
            reasons.append(f"capability 不可解析或已停用: {ref}")
            continue
        capability = resolve_capability(root, cap_id)

        prs = [p for p in list_professional_roles(root)
               if p.get("status") == "active" and cap_id in (p.get("capability_refs") or [])
               and (not requested_pr or p["professional_role_id"] in requested_pr)]
        prs = sorted(prs, key=lambda p: (p.get("created_at", ""), p["professional_role_id"]))

        wfs = [w for w in list_workforces(root, status="active")
               if cap_id in (w.get("capability_refs") or [])
               and _company_eligible(company_id, str(w.get("company_id") or ""))
               and (not requested_wf or w["workforce_id"] in requested_wf)]
        wfs = sorted(wfs, key=lambda w: (w.get("created_at", ""), w["workforce_id"]))

        if not wfs:
            unresolved.append(cap_id)
            reasons.append(f"{cap_id}: no eligible workforce")
            continue
        for wf in wfs:
            members = []
            for mid in wf.get("member_refs", []):
                ident = get_identity(root, mid)
                if ident and ident.get("status") == "active" and (
                        not requested_idn or ident["identity_id"] in requested_idn):
                    members.append(ident)
            members = sorted(members, key=lambda i: i["identity_id"])
            pr = prs[0] if prs else None
            matches.append({
                "capability_id": cap_id,
                "professional_role_id": pr["professional_role_id"] if pr else "",
                "workforce_id": wf["workforce_id"],
                "identity_id": members[0]["identity_id"] if members else "",
                "match_type": "deterministic",
                "reason": (
                    f"work requires {cap_id} ({capability['name']}); "
                    f"professional role {pr['professional_role_id'] if pr else '-'} provides it; "
                    f"workforce {wf['workforce_id']} provides it and is active"
                    + ("; same company" if company_id else "; global scope")),
            })

    status = "resolved" if (matches and not unresolved) else "unresolved"
    if not required_capability_refs:
        status = "unresolved"
        reasons.append("no required capability specified")
    rec = {
        "resolution_id": f"RS-{uuid.uuid4().hex[:10]}",
        "status": status,
        "request": {"company_id": company_id, "project_id": project_id, "work_id": work_id,
                    "required_capability_refs": [str(c) for c in required_capability_refs],
                    "requested_professional_role_refs": sorted(requested_pr),
                    "requested_workforce_refs": sorted(requested_wf),
                    "requested_identity_refs": sorted(requested_idn),
                    "constraints": constraints or {}},
        "matches": matches,
        "unresolved_capabilities": unresolved,
        "reason": "; ".join(reasons),
        "created_at": _now_iso(),
        "resolved_at": _now_iso(),
    }
    data = _load(root)
    data[rec["resolution_id"]] = rec
    _save(root, data)
    return rec


def resolve_work(root: str | Path, work_id: str, *,
                 requested_professional_role_refs: list[str] | None = None,
                 requested_workforce_refs: list[str] | None = None,
                 requested_identity_refs: list[str] | None = None,
                 constraints: dict[str, Any] | None = None) -> dict[str, Any]:
    """Work -> required capabilities -> PR/Workforce/Identity 解析。"""
    from .os_core_work import get_work

    work = get_work(root, work_id)
    if work is None:
        raise ValueError(f"Work 不存在: {work_id}")
    company_id, project_id = _company_of_work(root, work)
    return _resolve(root, required_capability_refs=list(work.get("required_capability_refs") or []),
                    company_id=company_id, project_id=project_id, work_id=work_id,
                    requested_professional_role_refs=requested_professional_role_refs,
                    requested_workforce_refs=requested_workforce_refs,
                    requested_identity_refs=requested_identity_refs,
                    constraints=constraints)


def resolve_capability(root: str | Path, capability_id: str, *, company_id: str = "",
                       project_id: str = "", work_id: str = "") -> dict[str, Any]:
    """单个 Capability 的解析 (供未来 Scheduler/Execution 调用)。"""
    return _resolve(root, required_capability_refs=[capability_id], company_id=company_id,
                    project_id=project_id, work_id=work_id)


__all__ = [
    "RESOLUTION_STATUSES",
    "get_resolution",
    "list_resolutions",
    "resolve_capability",
    "resolve_work",
]
