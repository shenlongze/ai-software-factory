"""factory-console/ops_projection.py — S22 Production Health Projection + Control Plane.

Health State 是 Projection (由 facts 计算, 可重建, 非第二事实源):
- facts: HealthCheck / Incident / Recovery / Release / Verification
- projection: project_health / release_health / history / comparison

原则:
- 不创建 operations_state.json 作为唯一真相
- 每次查询实时计算 (可重建)
- 允许解释: 为什么当前 HEALTHY/UNHEALTHY
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .health_service import (
    HR_HEALTHY, HR_DEGRADED, HR_UNHEALTHY, HR_UNKNOWN,
    INC_OPEN, INC_ACKNOWLEDGED, INC_RECOVERING, INC_RESOLVED, INC_FAILED,
    list_health_checks, list_incidents,
)
from .release_service import list_releases, get_release
from .ops_scheduler import list_schedules


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def release_health(root: Path | str, release_id: str) -> dict[str, Any]:
    """Release Health Projection (facts 计算)。"""
    rel = get_release(root, release_id)
    if rel is None:
        raise ValueError(f"Release 不存在: {release_id}")
    checks = list_health_checks(root, release_id=release_id)
    incidents = [i for i in list_incidents(root) if i.get("release_id") == release_id]
    latest = checks[-1] if checks else None
    state = latest["result"] if latest else (HR_UNKNOWN if not rel.get("state") else HR_UNKNOWN)
    # RECOVERING: 有 active incident 在 RECOVERING
    if any(i["status"] in (INC_RECOVERING,) for i in incidents):
        state = "RECOVERING"
    open_incidents = [i for i in incidents if i["status"] in (INC_OPEN, INC_ACKNOWLEDGED, INC_RECOVERING)]
    return {
        "project_id": rel.get("project_id") or "",
        "release_id": release_id,
        "release_state": rel.get("state"),
        "health_state": state,
        "last_check": latest.get("completed_at") if latest else None,
        "last_result": latest.get("result") if latest else None,
        "checks_count": len(checks),
        "open_incidents": len(open_incidents),
        "incident_ids": [i["incident_id"] for i in incidents[-5:]],
        "recovery_count": sum(1 for i in incidents if i["status"] == INC_RESOLVED),
        "rollback_id": incidents[-1].get("rollback_id", "") if incidents else "",
        "explain": _explain(release_id, rel, latest, open_incidents),
    }


def _explain(release_id: str, rel: dict[str, Any], latest: dict[str, Any] | None,
             open_incidents: list[dict[str, Any]]) -> str:
    if latest is None:
        return "无 health check 记录 (UNKNOWN)"
    if any(i["status"] == INC_RECOVERING for i in open_incidents):
        return f"recovering: incident {open_incidents[0]['incident_id']} rollback 进行中"
    if latest["result"] == HR_UNHEALTHY:
        failed = [c["check_type"] for c in latest.get("checks", []) if c["status"] == "FAILED"]
        return f"unhealthy: check {latest['health_check_id']} failed={failed}"
    if latest["result"] == HR_DEGRADED:
        return f"degraded: check {latest['health_check_id']} retryable failure"
    return f"healthy: check {latest['health_check_id']} all PASS"


def release_health_history(root: Path | str, release_id: str) -> list[dict[str, Any]]:
    """Health History (真实 persisted checks + incidents 时间线)。"""
    checks = list_health_checks(root, release_id=release_id)
    incidents = [i for i in list_incidents(root) if i.get("release_id") == release_id]
    timeline: list[dict[str, Any]] = []
    for c in checks:
        timeline.append({"at": c.get("completed_at", ""), "kind": "health_check",
                         "health_check_id": c["health_check_id"], "result": c["result"],
                         "failed_checks": [x["check_type"] for x in c.get("checks", []) if x["status"] == "FAILED"]})
    for i in incidents:
        timeline.append({"at": i.get("created_at", ""), "kind": "incident",
                         "incident_id": i["incident_id"], "status": i["status"],
                         "severity": i["severity"], "rollback_id": i.get("rollback_id", "")})
    timeline.sort(key=lambda x: x.get("at", ""))
    return timeline


def project_health(root: Path | str, project_id: str) -> dict[str, Any]:
    """Project Health Projection (Multi-Release)。"""
    rels = list_releases(root)
    rels = [r for r in rels if (r.get("project_id") or "") == project_id]
    release_views = [release_health(root, r["release_id"]) for r in rels]
    states = [v["health_state"] for v in release_views]
    if not states:
        return {"project_id": project_id, "health_state": HR_UNKNOWN,
                "releases": [], "explain": "无 release"}
    priority = [HR_UNHEALTHY, "RECOVERING", HR_DEGRADED, HR_HEALTHY, HR_UNKNOWN]
    proj_state = next((s for s in priority if s in states), HR_UNKNOWN)
    open_inc = sum(v["open_incidents"] for v in release_views)
    return {
        "project_id": project_id,
        "health_state": proj_state,
        "releases": release_views,
        "release_count": len(release_views),
        "open_incidents": open_inc,
        "explain": f"{proj_state}: {len(release_views)} releases, {open_inc} open incidents",
    }


def compare_releases(root: Path | str, release_a: str, release_b: str) -> dict[str, Any]:
    """Release 健康比较 (真实数据)。"""
    ha = release_health(root, release_a)
    hb = release_health(root, release_b)
    order = [HR_HEALTHY, HR_DEGRADED, "RECOVERING", HR_UNHEALTHY, HR_UNKNOWN]
    score = lambda s: order.index(s) if s in order else len(order)  # noqa: E731
    return {
        "release_a": ha, "release_b": hb,
        "more_healthy": release_a if score(ha["health_state"]) < score(hb["health_state"])
                        else release_b if score(hb["health_state"]) < score(ha["health_state"]) else "equal",
        "criteria": ["health_state", "checks_count", "open_incidents", "recovery_count"],
    }


def overview(root: Path | str) -> dict[str, Any]:
    """Control Plane Overview (全量聚合投影)。"""
    rels = list_releases(root)
    checks = list_health_checks(root)
    incidents = list_incidents(root)
    schedules = list_schedules(root)
    released = [r for r in rels if r["state"] == "RELEASED"]
    release_views = [release_health(root, r["release_id"]) for r in released]
    state_counts: dict[str, int] = {}
    for v in release_views:
        state_counts[v["health_state"]] = state_counts.get(v["health_state"], 0) + 1
    return {
        "projects": len({r.get("project_id") or "" for r in rels}),
        "releases_total": len(rels),
        "releases_active": len(released),
        "health_states": state_counts,
        "open_incidents": sum(1 for i in incidents if i["status"] in (INC_OPEN, INC_ACKNOWLEDGED, INC_RECOVERING)),
        "incidents_total": len(incidents),
        "schedules": len(schedules),
        "schedules_enabled": sum(1 for s in schedules if s.get("enabled")),
        "health_checks_total": len(checks),
        "recoveries": sum(1 for i in incidents if i["status"] == INC_RESOLVED),
        "rollbacks": sum(1 for i in incidents if i.get("rollback_id")),
        "generated_at": _now_iso(),
    }
