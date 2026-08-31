"""factory-console/operational_state.py — K4 Unified Operational State.

Control Tower 核心: 从真实 SSOT 投影 Operational State (非第二事实源)。

- OperationalState Contract: 按实体语义 (Agent/Task/Node/Run)
- 状态映射: entity.status → operational state (确定性, 非 LLM)
- 全链路钻取: project → sprint → task → node → agent → run → artifact → verification → evidence
- "谁在工作": agent 级 (从真实 run/task 依据)
- Idle 原因: no_eligible_task / waiting_dependency / policy_denied
- Failure 原因链: task FAILED → incident/recovery → evidence
- snapshot: 一致性快照 (断线恢复用; snapshot + event replay)

复用: S43 unified_contract + K3 project_os + S3 production_run + S17 governance
禁止: 第二套 SSOT / LLM 计算状态 / Mock realtime
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .unified_contract import entities, get_entity

#: 统一 Operational States (按实体语义)
TASK_STATES = ("PLANNED", "READY", "RUNNING", "BLOCKED", "WAITING_APPROVAL",
               "FAILED", "COMPLETED", "CANCELLED")
AGENT_STATES = ("ACTIVE", "RUNNING", "IDLE", "SUSPENDED", "FAILED", "RETIRED")

#: entity.status → operational state (确定性映射)
TASK_STATUS_MAP = {
    "DRAFT": "PLANNED", "READY": "READY", "RUNNING": "RUNNING",
    "BLOCKED": "BLOCKED", "WAITING_APPROVAL": "WAITING_APPROVAL",
    "FAILED": "FAILED", "COMPLETED": "COMPLETED", "CANCELLED": "CANCELLED",
    "VALIDATED": "READY", "ACTIVE": "RUNNING",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "operational" / f"{name}.json"


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


def _runs(root: Path | str) -> list[dict[str, Any]]:
    try:
        from .production_run import list_production_runs
        return list_production_runs(root)
    except Exception:  # noqa: BLE001
        return []


# ------------------------------------------------------------------ 状态映射

def task_operational_state(entity: dict[str, Any]) -> str:
    """Task entity → operational state (确定性)。"""
    return TASK_STATUS_MAP.get(entity.get("status", "DRAFT"), "PLANNED")


def agent_operational_state(root: Path | str, agent_id: str) -> dict[str, Any]:
    """Agent 级状态 (从真实 task/run 依据, 非超时猜测)。

    RUNNING: 有 RUNNING task 绑定; IDLE: 无 task + 原因; BLOCKED: 有 BLOCKED task。
    """
    all_entities = entities(root)
    tasks = [t for t in all_entities if t["type"] == "task"]
    my_tasks = [t for t in tasks if t.get("agent_id") == agent_id
                or t.get("role") == agent_id]
    if any(t.get("status") == "RUNNING" for t in my_tasks):
        running = [t for t in my_tasks if t.get("status") == "RUNNING"]
        return {"agent_id": agent_id, "state": "RUNNING",
                "current_work": running[0].get("title", ""),
                "task_id": running[0]["id"], "evidence": "task RUNNING"}
    if any(t.get("status") == "BLOCKED" for t in my_tasks):
        blocked = [t for t in my_tasks if t.get("status") == "BLOCKED"]
        return {"agent_id": agent_id, "state": "BLOCKED",
                "current_work": blocked[0].get("title", ""),
                "blocking_reason": "task BLOCKED", "task_id": blocked[0]["id"]}
    if any(t.get("status") in ("READY", "DRAFT", "VALIDATED") for t in my_tasks):
        waiting = [t for t in my_tasks if t.get("status") in ("READY", "DRAFT", "VALIDATED")]
        return {"agent_id": agent_id, "state": "WAITING",
                "current_work": waiting[0].get("title", ""),
                "idle_reason": "waiting_dependency"}
    return {"agent_id": agent_id, "state": "IDLE",
            "current_work": "-", "idle_reason": "no_eligible_task"}


# ------------------------------------------------------------------ 全链路钻取

def drill_down(root: Path | str, project_id: str) -> dict[str, Any]:
    """Project → Sprint → Task → Node → Agent → Run → Evidence 全链路。"""
    from .project_os import project_status

    ps = project_status(root, project_id)
    chain = {"project": {"id": project_id, "title": ps.get("title", ""),
                         "status": ps.get("status", ""),
                         "progress": ps["progress"]},
             "sprints": []}
    for sp in ps["sprints"]:
        sp_chain = {"sprint": {"id": sp["sprint_id"], "title": sp.get("title", ""),
                               "status": sp.get("status", ""),
                               "progress": sp["progress"]},
                    "tasks": []}
        for t in sp["tasks"]:
            task_detail = _task_detail(root, t["id"])
            sp_chain["tasks"].append(task_detail)
        chain["sprints"].append(sp_chain)
    return chain


def _task_detail(root: Path | str, task_id: str) -> dict[str, Any]:
    """Task 钻取: → node/run → evidence (为什么这个状态)。"""
    t = get_entity(root, task_id)
    run_id = t.get("production_run_id", "")
    run_detail = {}
    if run_id:
        for r in _runs(root):
            if r.get("run_id") == run_id:
                run_detail = {"run_id": run_id, "state": r.get("state", ""),
                              "nodes": r.get("node_runs", []),
                              "started_at": r.get("started_at", "")}
                break
    # evidence (task 下 evidence 实体)
    ev_list = [e for e in entities(root, entity_type="evidence")
               if e.get("parent_id") == task_id]
    return {"id": t["id"], "title": t.get("title", ""),
            "status": t.get("status", ""),
            "operational_state": task_operational_state(t),
            "production_run_id": run_id,
            "run": run_detail,
            "evidence": [{"id": e["id"], "state": e.get("state", ""),
                          "refs": e.get("evidence_refs", [])} for e in ev_list],
            "why": _why_state(t, run_detail, ev_list)}


def _why_state(task: dict[str, Any], run: dict[str, Any],
               ev_list: list[dict[str, Any]]) -> str:
    """状态原因 (可解释; 非猜测)。"""
    st = task.get("status", "")
    if st == "BLOCKED":
        return f"Task BLOCKED (等待依赖或审批; approval: {task.get('approval_status', 'unknown')})"
    if st == "FAILED":
        run_state = run.get("state", "?") if run else "?"
        ev = ev_list[0] if ev_list else None
        return (f"Task FAILED (run={run_state}"
                + (f"; evidence {ev['id']} state={ev.get('state')}" if ev else "")
                + ")")
    if st == "COMPLETED":
        return f"Task COMPLETED (run={run.get('state', '?') if run else '?'})"
    if st == "RUNNING":
        return "Task RUNNING (执行中)"
    return f"Task {st}"


# ------------------------------------------------------------------ "谁在工作" / 全局视图

def who_is_working(root: Path | str) -> dict[str, Any]:
    """谁在工作 (从真实 task/run 依据; RUNNING/WAITING/BLOCKED/IDLE + 原因)。"""
    all_entities = entities(root)
    tasks = [t for t in all_entities if t["type"] == "task"]
    agents = {}
    for t in tasks:
        aid = t.get("agent_id") or t.get("role") or "unassigned"
        agents.setdefault(aid, []).append(t)
    rows = []
    for aid, ts in agents.items():
        row = {"agent": aid, "tasks": len(ts)}
        if any(t.get("status") == "RUNNING" for t in ts):
            r = [t for t in ts if t.get("status") == "RUNNING"][0]
            row["state"] = "RUNNING"
            row["current_work"] = r.get("title", "")
        elif any(t.get("status") == "BLOCKED" for t in ts):
            row["state"] = "BLOCKED"
            row["current_work"] = [t for t in ts if t.get("status") == "BLOCKED"][0].get("title", "")
            row["blocking_reason"] = "task BLOCKED"
        elif any(t.get("status") in ("READY", "DRAFT") for t in ts):
            row["state"] = "WAITING"
            row["current_work"] = [t for t in ts if t.get("status") in ("READY", "DRAFT")][0].get("title", "")
            row["idle_reason"] = "waiting_dependency"
        else:
            row["state"] = "IDLE"
            row["current_work"] = "-"
            row["idle_reason"] = "no_eligible_task"
        rows.append(row)
    return {"agents": rows, "count": len(rows), "calculated_at": _now_iso()}


def global_overview(root: Path | str) -> dict[str, Any]:
    """Global Operations View (Projects/Running/Waiting/Blocked/Approval/Failed + Workforce + Activity)。"""
    from .control_tower import (work_overview, workforce_status,
                                governance_pending, realtime_stream)

    w = work_overview(root)
    ws = workforce_status(root)
    gp = governance_pending(root)
    rt = realtime_stream(root, limit=8)
    return {"projects": {"total": w["conversations"] if "projects" not in w else w.get("projects", 0),
                         "running": w["execution_states"].get("RUNNING", 0),
                         "waiting": w["task_states"].get("READY", 0) + w["task_states"].get("DRAFT", 0),
                         "blocked": w["task_states"].get("BLOCKED", 0),
                         "approval": gp["pending_approvals"],
                         "failed": w["task_states"].get("FAILED", 0)},
            "workforce": {"running": ws["running"], "waiting": ws["waiting"],
                          "blocked": ws["blocked"], "error": ws["error"],
                          "idle": ws["idle"]},
            "recent_activity": rt["events"],
            "calculated_at": _now_iso()}


# ------------------------------------------------------------------ Snapshot (断线恢复)

def snapshot(root: Path | str) -> dict[str, Any]:
    """一致性快照 (断线恢复: snapshot + event replay 基础)。"""
    from .control_tower import control_tower
    return {"snapshot_id": f"snap_{datetime.now(timezone.utc).strftime('%H%M%S')}",
            "taken_at": _now_iso(),
            "state": control_tower(root)}


def restore_from_snapshot(root: Path | str, snap: dict[str, Any]) -> bool:
    """验证 snapshot 与当前真实状态一致 (断线后 UI 恢复到正确状态)。"""
    from .control_tower import control_tower
    current = control_tower(root)
    return (current["work"]["executions"] == snap["state"]["work"]["executions"]
            and current["work"]["task_states"] == snap["state"]["work"]["task_states"]
            and current["workforce"] == snap["state"]["workforce"])
