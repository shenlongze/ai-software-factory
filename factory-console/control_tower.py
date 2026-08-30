"""factory-console/control_tower.py — K2 Control Tower 基础 (实时状态投影).

从真实 Entities/Events 投影 (可重建, 非第二事实源):
- Work 概览: conversations/tasks/executions 状态分布
- Workforce 状态: RUNNING/WAITING/IDLE/BLOCKED/ERROR (从真实 task/run 投影)
- Governance 待办: PENDING approvals (S17)
- 实时事件流: 最近 events (correlation 可追溯)

复用: S43 unified_contract entities + S17 governance + S3 production runs
禁止: 第二套状态系统 / 伪实时 (全从真实数据投影)
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .unified_contract import entities, get_entity


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "controltower" / f"{name}.json"


def _load(root: Path | str, name: str) -> list[dict[str, Any]]:
    try:
        d = json.loads(_file(root, name).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _runs(root: Path | str) -> list[dict[str, Any]]:
    """从真实 ProductionRun 投影 (复用 S3 list_production_runs, 非猜路径)。"""
    try:
        from .production_run import list_production_runs
        return list_production_runs(root)
    except Exception:  # noqa: BLE001
        return []


def work_overview(root: Path | str) -> dict[str, Any]:
    """Work 概览: conversations/tasks/executions 状态分布 (真实投影)。"""
    all_entities = entities(root)
    convs = [e for e in all_entities if e["type"] == "conv"]
    tasks = [e for e in all_entities if e["type"] == "task"]
    runs = _runs(root)
    run_states = {}
    for r in runs:
        st = r.get("state", "UNKNOWN")
        run_states[st] = run_states.get(st, 0) + 1
    return {"conversations": len(convs),
            "conversation_open": sum(1 for c in convs if c.get("status") == "OPEN"),
            "tasks": len(tasks),
            "task_states": {s: sum(1 for t in tasks if t.get("status") == s)
                            for s in sorted({t.get("status", "?") for t in tasks})},
            "executions": len(runs),
            "execution_states": run_states,
            "calculated_at": _now_iso()}


def workforce_status(root: Path | str) -> dict[str, Any]:
    """Workforce 状态: 谁在干什么 (从真实 task/run 投影)。"""
    all_entities = entities(root)
    tasks = [e for e in all_entities if e["type"] == "task"]
    active = [t for t in tasks if t.get("status") in ("RUNNING", "READY", "BLOCKED", "FAILED")]
    running = [t for t in tasks if t.get("status") == "RUNNING"]
    waiting = [t for t in tasks if t.get("status") == "READY"]
    blocked = [t for t in tasks if t.get("status") == "BLOCKED"]
    error = [t for t in tasks if t.get("status") == "FAILED"]
    return {"running": len(running), "waiting": len(waiting),
            "blocked": len(blocked), "error": len(error),
            "idle": max(0, len(tasks) - len(active)),
            "active_tasks": [{"id": t["id"], "title": t.get("title", ""),
                              "status": t.get("status"),
                              "production_run_id": t.get("production_run_id", "")}
                             for t in active[:10]],
            "calculated_at": _now_iso()}


def governance_pending(root: Path | str) -> dict[str, Any]:
    """Governance 待办: PENDING approvals (S17 真实数据)。"""
    try:
        d = json.loads((Path(root) / "ops" / "governance" / "approvals.json").read_text(encoding="utf-8"))
        approvals = d if isinstance(d, list) else []
    except (OSError, ValueError):
        approvals = []
    pending = [a for a in approvals if a.get("decision") == "PENDING"]
    return {"pending_approvals": len(pending),
            "items": [{"approval_id": a.get("approval_id"), "subject_type": a.get("subject_type"),
                       "requested_by": a.get("requested_by"), "requested_at": a.get("requested_at")}
                      for a in pending[:10]],
            "calculated_at": _now_iso()}


def realtime_stream(root: Path | str, *, limit: int = 20) -> dict[str, Any]:
    """最近事件流 (从真实 AuditEvent 投影, correlation 可追溯)。"""
    try:
        d = json.loads((Path(root) / "audit" / "audit_events.json").read_text(encoding="utf-8"))
        events = d if isinstance(d, list) else []
    except (OSError, ValueError):
        events = []
    events.sort(key=lambda e: e.get("timestamp", e.get("created_at", "")), reverse=True)
    stream = [{"event_id": e.get("audit_id") or e.get("event_id"),
               "event_type": e.get("event_type"),
               "trace_id": e.get("trace_id", ""),
               "correlation_id": e.get("correlation_id", ""),
               "timestamp": e.get("timestamp", e.get("created_at", ""))}
              for e in events[:limit]]
    return {"events": stream, "count": len(stream), "calculated_at": _now_iso()}


def control_tower(root: Path | str) -> dict[str, Any]:
    """Control Tower 总览 (全投影合成, 无伪数据)。"""
    return {"work": work_overview(root),
            "workforce": workforce_status(root),
            "governance": governance_pending(root),
            "realtime": realtime_stream(root),
            "calculated_at": _now_iso()}
