"""factory-console/os_core_work.py — OS Core: Work / Workstream (MU-CORE-06).

语义 (Constitution v2 Art.14/15):
    Project ≠ Work ≠ Workstream ≠ Task ≠ TaskNode ≠ Execution
    Sprint/Backlog/PRD 是 Factory/Agile 视图, 不是 Work。
    conversation_id / session_id / task_id / node_run_id / sprint_id 绝不作 work_id。

- Work = Project 下具有独立业务/工作目标、生命周期与可追踪结果的工作单元。
- Workstream = Work 内用于组织/分流/协同/专业工作域的结构 (属于 Work)。

SSOT: <root>/work/work.json {works, workstreams} (single writer + 原子写 + stable ID W-*/WS-*)。
范围外 (后续 MU): Task / TaskNode / Execution / Capability / Plugin / Resolution / Resource /
Governance / Approval / HITL / DB 迁移。
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORK_STATES: tuple[str, ...] = ("draft", "active", "on_hold", "completed", "archived")
WORK_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "draft": ("active", "archived"),
    "active": ("on_hold", "completed", "archived"),
    "on_hold": ("active", "completed", "archived"),
    "completed": ("archived",),
    "archived": (),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: str | Path) -> Path:
    return Path(root) / "work" / "work.json"


def _load(root: str | Path) -> dict[str, dict[str, dict[str, Any]]]:
    try:
        data = json.loads(_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"works": {}, "workstreams": {}}
    works = data.get("works") if isinstance(data, dict) else None
    streams = data.get("workstreams") if isinstance(data, dict) else None
    return {"works": works if isinstance(works, dict) else {},
            "workstreams": streams if isinstance(streams, dict) else {}}


def _save(root: str | Path, data: dict[str, dict[str, dict[str, Any]]]) -> None:
    p = _file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def _require_project(root: str | Path, project_id: str) -> dict[str, Any]:
    from .os_core_project import get_project

    project = get_project(root, project_id)
    if project is None:
        raise ValueError(f"Project 不存在: {project_id}")
    return project


# ---------------------------------------------------------------- Work

def create_work(root: str | Path, *, project_id: str, name: str, description: str = "",
                work_type: str = "", owner_identity_id: str = "",
                status: str = "draft", work_id: str | None = None) -> dict[str, Any]:
    """创建 Work (Project 下一层; project 必须存在于 MU-CORE-05 SSOT)。"""
    if status not in WORK_STATES:
        raise ValueError(f"未知 status: {status} (可选: {WORK_STATES})")
    project = _require_project(root, project_id)
    owner_identity_id = str(owner_identity_id or "")
    if owner_identity_id:
        from .os_core_identity import get_identity

        if get_identity(root, owner_identity_id) is None:
            raise ValueError(f"Identity 不存在: {owner_identity_id}")
    data = _load(root)
    wid = work_id or f"W-{uuid.uuid4().hex[:10]}"
    if wid in data["works"]:
        raise ValueError(f"Work 已存在: {wid}")
    now = _now_iso()
    rec = {"work_id": wid, "project_id": str(project["id"]), "name": name,
           "description": description, "work_type": work_type, "status": status,
           "owner_identity_id": owner_identity_id,
           "created_at": now, "updated_at": now}
    data["works"][wid] = rec
    _save(root, data)
    return rec


def get_work(root: str | Path, work_id: str) -> dict[str, Any] | None:
    return _load(root)["works"].get(str(work_id))


def list_works(root: str | Path, *, project_id: str = "", status: str = "") -> list[dict[str, Any]]:
    recs = list(_load(root)["works"].values())
    if project_id:
        recs = [r for r in recs if r["project_id"] == str(project_id)]
    if status:
        recs = [r for r in recs if r["status"] == str(status)]
    return sorted(recs, key=lambda r: r.get("created_at", ""))


def update_work(root: str | Path, work_id: str, *, name: str | None = None,
                description: str | None = None, work_type: str | None = None,
                owner_identity_id: str | None = None) -> dict[str, Any]:
    data = _load(root)
    rec = data["works"].get(str(work_id))
    if rec is None:
        raise ValueError(f"Work 不存在: {work_id}")
    if name is not None:
        rec["name"] = name
    if description is not None:
        rec["description"] = description
    if work_type is not None:
        rec["work_type"] = work_type
    if owner_identity_id is not None:
        if owner_identity_id:
            from .os_core_identity import get_identity

            if get_identity(root, owner_identity_id) is None:
                raise ValueError(f"Identity 不存在: {owner_identity_id}")
        rec["owner_identity_id"] = str(owner_identity_id)
    rec["updated_at"] = _now_iso()
    _save(root, data)
    return rec


def set_work_status(root: str | Path, work_id: str, target: str) -> dict[str, Any]:
    if target not in WORK_STATES:
        raise ValueError(f"未知状态: {target}")
    data = _load(root)
    rec = data["works"].get(str(work_id))
    if rec is None:
        raise ValueError(f"Work 不存在: {work_id}")
    current = rec["status"]
    if target == current:
        return rec
    if target not in WORK_TRANSITIONS.get(current, ()):
        raise ValueError(f"非法状态迁移: {current} → {target}")
    rec["status"] = target
    rec["updated_at"] = _now_iso()
    _save(root, data)
    return rec


def resolve_work(root: str | Path, work_id: str) -> dict[str, Any]:
    """解析 Work -> Project (引用解析, 不复制 Project 数据)。"""
    rec = get_work(root, work_id)
    if rec is None:
        raise ValueError(f"Work 不存在: {work_id}")
    return {"work": rec, "project": _require_project(root, rec["project_id"])}


# ---------------------------------------------------------------- Workstream (属于 Work)

def create_workstream(root: str | Path, *, work_id: str, name: str, description: str = "",
                      status: str = "draft", workstream_id: str | None = None) -> dict[str, Any]:
    if status not in WORK_STATES:
        raise ValueError(f"未知 status: {status} (可选: {WORK_STATES})")
    if get_work(root, work_id) is None:
        raise ValueError(f"Work 不存在: {work_id}")
    data = _load(root)
    sid = workstream_id or f"WS-{uuid.uuid4().hex[:10]}"
    if sid in data["workstreams"]:
        raise ValueError(f"Workstream 已存在: {sid}")
    now = _now_iso()
    rec = {"workstream_id": sid, "work_id": str(work_id), "name": name,
           "description": description, "status": status,
           "created_at": now, "updated_at": now}
    data["workstreams"][sid] = rec
    _save(root, data)
    return rec


def get_workstream(root: str | Path, workstream_id: str) -> dict[str, Any] | None:
    return _load(root)["workstreams"].get(str(workstream_id))


def list_workstreams(root: str | Path, *, work_id: str = "",
                     status: str = "") -> list[dict[str, Any]]:
    recs = list(_load(root)["workstreams"].values())
    if work_id:
        recs = [r for r in recs if r["work_id"] == str(work_id)]
    if status:
        recs = [r for r in recs if r["status"] == str(status)]
    return sorted(recs, key=lambda r: r.get("created_at", ""))


def update_workstream(root: str | Path, workstream_id: str, *, name: str | None = None,
                      description: str | None = None) -> dict[str, Any]:
    data = _load(root)
    rec = data["workstreams"].get(str(workstream_id))
    if rec is None:
        raise ValueError(f"Workstream 不存在: {workstream_id}")
    if name is not None:
        rec["name"] = name
    if description is not None:
        rec["description"] = description
    rec["updated_at"] = _now_iso()
    _save(root, data)
    return rec


def set_workstream_status(root: str | Path, workstream_id: str, target: str) -> dict[str, Any]:
    if target not in WORK_STATES:
        raise ValueError(f"未知状态: {target}")
    data = _load(root)
    rec = data["workstreams"].get(str(workstream_id))
    if rec is None:
        raise ValueError(f"Workstream 不存在: {workstream_id}")
    current = rec["status"]
    if target == current:
        return rec
    if target not in WORK_TRANSITIONS.get(current, ()):
        raise ValueError(f"非法状态迁移: {current} → {target}")
    rec["status"] = target
    rec["updated_at"] = _now_iso()
    _save(root, data)
    return rec


def resolve_workstream(root: str | Path, workstream_id: str) -> dict[str, Any]:
    """解析 Workstream -> Work -> Project (引用解析)。"""
    rec = get_workstream(root, workstream_id)
    if rec is None:
        raise ValueError(f"Workstream 不存在: {workstream_id}")
    return {"workstream": rec, "work": get_work(root, rec["work_id"]),
            "project": _require_project(root, (get_work(root, rec["work_id"]) or {})["project_id"])}


__all__ = [
    "WORK_STATES",
    "WORK_TRANSITIONS",
    "create_work",
    "create_workstream",
    "get_work",
    "get_workstream",
    "list_works",
    "list_workstreams",
    "resolve_work",
    "resolve_workstream",
    "set_work_status",
    "set_workstream_status",
    "update_work",
    "update_workstream",
]
