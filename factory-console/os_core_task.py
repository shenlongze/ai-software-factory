"""factory-console/os_core_task.py — OS Core: Task (MU-CORE-09).

Task = Work/Workstream 下可管理、可追踪的工作单元 (定义"要完成什么")。

语义: Work ≠ Task ≠ TaskNode ≠ Execution；Sprint 不是 Task 的父级真相。
SSOT: <root>/task/tasks.json (T-*, single writer + 原子写)。
范围外: TaskNode 见 os_core_task_node; Execution 见 os_core_execution; Verification/Evidence/Outcome 后续 MU。
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TASK_STATES: tuple[str, ...] = ("todo", "ready", "in_progress", "blocked",
                                "completed", "cancelled")
TASK_PRIORITIES: tuple[str, ...] = ("P0", "P1", "P2", "P3")
TASK_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "todo": ("ready", "in_progress", "cancelled"),
    "ready": ("in_progress", "blocked", "cancelled"),
    "in_progress": ("blocked", "completed", "cancelled"),
    "blocked": ("in_progress", "cancelled"),
    "completed": (),
    "cancelled": (),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: str | Path) -> Path:
    return Path(root) / "task" / "tasks.json"


def _load(root: str | Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    items = data.get("tasks") if isinstance(data, dict) else None
    return items if isinstance(items, dict) else {}


def _save(root: str | Path, data: dict[str, dict[str, Any]]) -> None:
    p = _file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"tasks": data}, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


# ---------------------------------------------------------------- CRUD

def create_task(root: str | Path, *, work_id: str, name: str, workstream_id: str = "",
                description: str = "", priority: str = "P2", owner_identity_id: str = "",
                status: str = "todo", task_id: str | None = None) -> dict[str, Any]:
    from .os_core_identity import get_identity
    from .os_core_work import get_work, list_workstreams

    if status not in TASK_STATES:
        raise ValueError(f"未知 status: {status} (可选: {TASK_STATES})")
    if priority not in TASK_PRIORITIES:
        raise ValueError(f"未知 priority: {priority} (可选: {TASK_PRIORITIES})")
    if get_work(root, work_id) is None:
        raise ValueError(f"Work 不存在: {work_id}")
    workstream_id = str(workstream_id or "")
    if workstream_id:
        owned = {s["workstream_id"] for s in list_workstreams(root, work_id=work_id)}
        if workstream_id not in owned:
            raise ValueError(f"Workstream {workstream_id} 不属于 Work {work_id}")
    owner_identity_id = str(owner_identity_id or "")
    if owner_identity_id and get_identity(root, owner_identity_id) is None:
        raise ValueError(f"Identity 不存在: {owner_identity_id}")
    data = _load(root)
    tid = task_id or f"T-{uuid.uuid4().hex[:10]}"
    if tid in data:
        raise ValueError(f"Task 已存在: {tid}")
    now = _now_iso()
    rec = {"task_id": tid, "work_id": str(work_id), "workstream_id": workstream_id,
           "name": name, "description": description, "priority": priority,
           "status": status, "owner_identity_id": owner_identity_id,
           "created_at": now, "updated_at": now}
    data[tid] = rec
    _save(root, data)
    return rec


def get_task(root: str | Path, task_id: str) -> dict[str, Any] | None:
    return _load(root).get(str(task_id))


def list_tasks(root: str | Path, *, work_id: str = "", workstream_id: str = "",
               status: str = "") -> list[dict[str, Any]]:
    recs = list(_load(root).values())
    if work_id:
        recs = [r for r in recs if r["work_id"] == str(work_id)]
    if workstream_id:
        recs = [r for r in recs if r["workstream_id"] == str(workstream_id)]
    if status:
        recs = [r for r in recs if r["status"] == str(status)]
    return sorted(recs, key=lambda r: (r.get("created_at", ""), r["task_id"]))


def update_task(root: str | Path, task_id: str, *, name: str | None = None,
                description: str | None = None, priority: str | None = None,
                owner_identity_id: str | None = None,
                workstream_id: str | None = None) -> dict[str, Any]:
    from .os_core_identity import get_identity
    from .os_core_work import list_workstreams

    data = _load(root)
    rec = data.get(str(task_id))
    if rec is None:
        raise ValueError(f"Task 不存在: {task_id}")
    if name is not None:
        rec["name"] = name
    if description is not None:
        rec["description"] = description
    if priority is not None:
        if priority not in TASK_PRIORITIES:
            raise ValueError(f"未知 priority: {priority}")
        rec["priority"] = priority
    if owner_identity_id is not None:
        if owner_identity_id and get_identity(root, owner_identity_id) is None:
            raise ValueError(f"Identity 不存在: {owner_identity_id}")
        rec["owner_identity_id"] = str(owner_identity_id)
    if workstream_id is not None:
        if workstream_id:
            owned = {s["workstream_id"] for s in list_workstreams(root, work_id=rec["work_id"])}
            if workstream_id not in owned:
                raise ValueError(f"Workstream {workstream_id} 不属于 Work {rec['work_id']}")
        rec["workstream_id"] = str(workstream_id)
    rec["updated_at"] = _now_iso()
    _save(root, data)
    return rec


def set_task_status(root: str | Path, task_id: str, target: str) -> dict[str, Any]:
    if target not in TASK_STATES:
        raise ValueError(f"未知状态: {target}")
    data = _load(root)
    rec = data.get(str(task_id))
    if rec is None:
        raise ValueError(f"Task 不存在: {task_id}")
    current = rec["status"]
    if target == current:
        return rec
    if target not in TASK_TRANSITIONS.get(current, ()):
        raise ValueError(f"非法状态迁移: {current} → {target}")
    rec["status"] = target
    rec["updated_at"] = _now_iso()
    _save(root, data)
    return rec


def resolve_task(root: str | Path, task_id: str) -> dict[str, Any]:
    """Task -> Work -> Project 引用解析。"""
    from .os_core_project import get_project
    from .os_core_work import get_work

    rec = get_task(root, task_id)
    if rec is None:
        raise ValueError(f"Task 不存在: {task_id}")
    work = get_work(root, rec["work_id"])
    if work is None:
        raise ValueError(f"Work 不存在: {rec['work_id']}")
    project = get_project(root, work["project_id"])
    if project is None:
        raise ValueError(f"Project 不存在: {work['project_id']}")
    return {"task": rec, "work": work, "project": project}


__all__ = ["TASK_PRIORITIES", "TASK_STATES", "create_task", "get_task", "list_tasks",
           "resolve_task", "set_task_status", "update_task"]
