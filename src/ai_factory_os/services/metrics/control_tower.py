"""监控域 · Control Tower 实时投影（搬迁自 factory_console.control_tower）。

从真实 Entities / Events 投影（可重建，**非第二事实源**）：
  · Work 概览      — conversations / tasks / executions 状态分布
  · Workforce 状态  — RUNNING / WAITING / IDLE / BLOCKED / ERROR
  · Governance 待办 — PENDING approvals
  · 实时事件流      — 最近 audit events（correlation 可追溯）

数据来源（全是别的域的数据）经 `bind_lookups()` 注入 —— 按 SSoT R3/R5
「服务域不许跨域直连」，本域不 import 任何别的域，也不直接读别人的数据文件。
装配（把 entities / production_runs / approvals / audit_events 接上）是 bootstrap 的职责。

未注入时：返回**结构完整 + `unwired` 标注**（不是假 0，也不是空页）——
前端能区分「真的没有」与「还没接线」。

搬迁说明（刀2）：
  · 原 `_file`/`_load`（读 `<root>/ops/controltower/*.json`）是**死代码**，从未被调用，
    本域不搬（那正是"看着像 bug、其实是没用的路径"的来源）。
  · 原 `work_overview` 走的是 `unified_contract.entities()`（读 `ops/unified/entities.json`）✓
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

#: 跨域数据源钩子（bootstrap 注入）
Lookup = Callable[[Path | str], list[dict[str, Any]]]
_hooks: dict[str, Lookup] = {}


class _NoLookup:
    """哨兵：该数据源未接线（≠ 数据为空）。"""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover
        return "<no-lookup>"


NO_LOOKUP = _NoLookup()


def bind_lookups(*, entities: Lookup | None = None,
                 production_runs: Lookup | None = None,
                 approvals: Lookup | None = None,
                 audit_events: Lookup | None = None) -> None:
    """注入跨域数据源（bootstrap 装配时调用；None 项保持不变）。"""
    for key, fn in (("entities", entities), ("production_runs", production_runs),
                    ("approvals", approvals), ("audit_events", audit_events)):
        if fn is not None:
            _hooks[key] = fn


def _query(kind: str, root: Path | str) -> Any:
    fn = _hooks.get(kind)
    return NO_LOOKUP if fn is None else (fn(root) or [])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _unwired(*kinds: str) -> dict[str, Any]:
    """未接线标注（诚实：不想假装有数据，也不想给空页）。"""
    return {"unwired": list(kinds), "calculated_at": _now_iso()}


def work_overview(root: Path | str) -> dict[str, Any]:
    """Work 概览：conversations / tasks / executions 状态分布（真实投影）。"""
    all_entities = _query("entities", root)
    if all_entities is NO_LOOKUP:
        return {"conversations": 0, "tasks": 0, "executions": 0, **_unwired("entities")}
    runs = _query("production_runs", root)
    has_runs = runs is not NO_LOOKUP

    convs = [e for e in all_entities if e.get("type") == "conv"]
    tasks = [e for e in all_entities if e.get("type") == "task"]
    run_states: dict[str, int] = {}
    for r in (runs if has_runs else []):
        st = str(r.get("state", "UNKNOWN"))
        run_states[st] = run_states.get(st, 0) + 1

    out: dict[str, Any] = {
        "conversations": len(convs),
        "conversation_open": sum(1 for c in convs if c.get("status") == "OPEN"),
        "tasks": len(tasks),
        "task_states": {s: sum(1 for t in tasks if t.get("status") == s)
                        for s in sorted({str(t.get("status", "?")) for t in tasks})},
        "executions": len(runs) if has_runs else 0,
        "execution_states": run_states,
        "calculated_at": _now_iso(),
    }
    if not has_runs:
        out["unwired"] = ["production_runs"]
    return out


def workforce_status(root: Path | str) -> dict[str, Any]:
    """Workforce 状态：谁在干什么（从真实 task 投影）。"""
    all_entities = _query("entities", root)
    if all_entities is NO_LOOKUP:
        return {"running": 0, "waiting": 0, "blocked": 0, "error": 0,
                "idle": 0, "active_tasks": [], **_unwired("entities")}

    tasks = [e for e in all_entities if e.get("type") == "task"]
    by = {s: [t for t in tasks if t.get("status") == s]
          for s in ("RUNNING", "READY", "BLOCKED", "FAILED")}
    active = [t for t in tasks if t.get("status") in by]
    return {
        "running": len(by["RUNNING"]),
        "waiting": len(by["READY"]),
        "blocked": len(by["BLOCKED"]),
        "error": len(by["FAILED"]),
        "idle": max(0, len(tasks) - len(active)),
        "active_tasks": [{"id": t.get("id", ""), "title": t.get("title", ""),
                          "status": t.get("status"),
                          "production_run_id": t.get("production_run_id", "")}
                         for t in active[:10]],
        "calculated_at": _now_iso(),
    }


def governance_pending(root: Path | str) -> dict[str, Any]:
    """Governance 待办：PENDING approvals。"""
    approvals = _query("approvals", root)
    if approvals is NO_LOOKUP:
        return {"pending_approvals": 0, "items": [], **_unwired("approvals")}
    pending = [a for a in approvals if a.get("decision") == "PENDING"]
    return {"pending_approvals": len(pending),
            "items": [{"approval_id": a.get("approval_id"),
                       "subject_type": a.get("subject_type"),
                       "requested_by": a.get("requested_by"),
                       "requested_at": a.get("requested_at")} for a in pending[:10]],
            "calculated_at": _now_iso()}


def realtime_stream(root: Path | str, *, limit: int = 20) -> dict[str, Any]:
    """最近事件流（从真实 audit events 投影，correlation 可追溯）。"""
    events = _query("audit_events", root)
    if events is NO_LOOKUP:
        return {"events": [], "count": 0, **_unwired("audit_events")}
    events = sorted(events,
                    key=lambda e: str(e.get("timestamp") or e.get("created_at") or ""),
                    reverse=True)
    stream = [{"event_id": e.get("audit_id") or e.get("event_id"),
               "event_type": e.get("event_type"),
               "trace_id": e.get("trace_id", ""),
               "correlation_id": e.get("correlation_id", ""),
               "timestamp": e.get("timestamp") or e.get("created_at") or ""}
              for e in events[:limit]]
    return {"events": stream, "count": len(stream), "calculated_at": _now_iso()}


def control_tower(root: Path | str) -> dict[str, Any]:
    """Control Tower 总览（全投影合成，无伪数据）。"""
    return {"work": work_overview(root),
            "workforce": workforce_status(root),
            "governance": governance_pending(root),
            "realtime": realtime_stream(root),
            "calculated_at": _now_iso()}
