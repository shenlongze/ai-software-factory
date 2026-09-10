"""factory-console/os_core_task_node.py — OS Core: TaskNode (MU-CORE-09).

TaskNode = Task 内最小、可独立执行与验证的工作节点 (任务执行树中的语义节点)。

语义: Task ≠ TaskNode ≠ Execution ≠ NodeRun。TaskNode 可在无 Execution 时存在;
一个 TaskNode 可有多次 Execution。parent_node_id 只能指向同一 Task 下的 TaskNode。

SSOT: <root>/task/task_nodes.json (TN-*, single writer + 原子写)。
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

NODE_STATES: tuple[str, ...] = ("pending", "ready", "blocked", "running",
                                "completed", "failed", "cancelled")
NODE_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "pending": ("ready", "blocked", "running", "cancelled"),
    "ready": ("running", "blocked", "cancelled"),
    "blocked": ("ready", "running", "cancelled"),
    "running": ("completed", "failed", "cancelled"),
    "completed": (),
    "failed": (),
    "cancelled": (),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: str | Path) -> Path:
    return Path(root) / "task" / "task_nodes.json"


def _load(root: str | Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    items = data.get("task_nodes") if isinstance(data, dict) else None
    return items if isinstance(items, dict) else {}


def _save(root: str | Path, data: dict[str, dict[str, Any]]) -> None:
    p = _file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"task_nodes": data}, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def create_task_node(root: str | Path, *, task_id: str, name: str, parent_node_id: str = "",
                     description: str = "", node_type: str = "", sequence: int = 0,
                     required_capability_refs: list[str] | None = None,
                     depends_on: list[str] | None = None,
                     status: str = "pending",
                     task_node_id: str | None = None) -> dict[str, Any]:
    from .os_core_capability import validate_capability_ref
    from .os_core_task import get_task

    if status not in NODE_STATES:
        raise ValueError(f"未知 status: {status} (可选: {NODE_STATES})")
    if get_task(root, task_id) is None:
        raise ValueError(f"Task 不存在: {task_id}")
    parent_node_id = str(parent_node_id or "")
    if parent_node_id:
        parent = get_task_node(root, parent_node_id)
        if parent is None:
            raise ValueError(f"父 TaskNode 不存在: {parent_node_id}")
        if parent["task_id"] != str(task_id):
            raise ValueError(f"父 TaskNode {parent_node_id} 不属于 Task {task_id}")
    caps = [validate_capability_ref(root, c) for c in (required_capability_refs or [])]
    data = _load(root)
    nid = task_node_id or f"TN-{uuid.uuid4().hex[:10]}"
    deps = _validate_depends_on(data, str(task_id), nid, depends_on or [])
    if nid in data:
        raise ValueError(f"TaskNode 已存在: {nid}")
    now = _now_iso()
    rec = {"task_node_id": nid, "task_id": str(task_id), "parent_node_id": parent_node_id,
           "name": name, "description": description, "node_type": node_type,
           "status": status, "sequence": int(sequence),
           "required_capability_refs": caps, "depends_on": deps,
           "created_at": now, "updated_at": now}
    data[nid] = rec
    _save(root, data)
    return rec


def _validate_depends_on(data: dict[str, dict[str, Any]], task_id: str, node_id: str,
                         depends_on: list[str]) -> list[str]:
    """依赖只能指向**同一 Task** 的 TaskNode; 禁止自依赖/环。"""
    deps: list[str] = []
    for dep in depends_on:
        dep = str(dep)
        if dep == node_id:
            raise ValueError(f"TaskNode 不能依赖自身: {dep}")
        target = data.get(dep)
        if target is None:
            raise ValueError(f"依赖的 TaskNode 不存在: {dep}")
        if target["task_id"] != str(task_id):
            raise ValueError(f"依赖 {dep} 不属于 Task {task_id}")
        if dep in deps:
            continue
        deps.append(dep)
    # 环检测: 从每个 dep 出发能否回到 node_id
    def _reaches(target: str, seen: set[str]) -> bool:
        if target == node_id:
            return True
        if target in seen:
            return False
        seen.add(target)
        rec = data.get(target) or {}
        return any(_reaches(str(d), seen) for d in rec.get("depends_on", []))
    for dep in deps:
        if _reaches(dep, set()):
            raise ValueError(f"检测到依赖环: {node_id} -> {dep}")
    return deps


def get_task_node(root: str | Path, task_node_id: str) -> dict[str, Any] | None:
    return _load(root).get(str(task_node_id))


def list_task_nodes(root: str | Path, *, task_id: str = "", parent_node_id: str = "",
                    status: str = "") -> list[dict[str, Any]]:
    recs = list(_load(root).values())
    if task_id:
        recs = [r for r in recs if r["task_id"] == str(task_id)]
    if parent_node_id:
        recs = [r for r in recs if r["parent_node_id"] == str(parent_node_id)]
    if status:
        recs = [r for r in recs if r["status"] == str(status)]
    return sorted(recs, key=lambda r: (r.get("sequence", 0), r.get("created_at", ""),
                                       r["task_node_id"]))


def task_node_tree(root: str | Path, task_id: str) -> list[dict[str, Any]]:
    """Task 下的 TaskNode 树 (parent_node_id -> children)。"""
    nodes = list_task_nodes(root, task_id=task_id)
    by_id = {n["task_node_id"]: {**n, "children": []} for n in nodes}

    def _attach(node: dict[str, Any]) -> dict[str, Any]:
        for child in nodes:
            if child["parent_node_id"] == node["task_node_id"]:
                node["children"].append(_attach(by_id[child["task_node_id"]]))
        return node

    return [_attach(by_id[n["task_node_id"]]) for n in nodes if not n["parent_node_id"]]


def update_task_node(root: str | Path, task_node_id: str, *, name: str | None = None,
                     description: str | None = None, node_type: str | None = None,
                     sequence: int | None = None,
                     required_capability_refs: list[str] | None = None,
                     depends_on: list[str] | None = None) -> dict[str, Any]:
    from .os_core_capability import validate_capability_ref

    data = _load(root)
    rec = data.get(str(task_node_id))
    if rec is None:
        raise ValueError(f"TaskNode 不存在: {task_node_id}")
    if name is not None:
        rec["name"] = name
    if description is not None:
        rec["description"] = description
    if node_type is not None:
        rec["node_type"] = node_type
    if sequence is not None:
        rec["sequence"] = int(sequence)
    if required_capability_refs is not None:
        rec["required_capability_refs"] = [validate_capability_ref(root, c)
                                           for c in required_capability_refs]
    if depends_on is not None:
        rec["depends_on"] = _validate_depends_on(data, rec["task_id"],
                                                 rec["task_node_id"], depends_on)
    rec["updated_at"] = _now_iso()
    _save(root, data)
    return rec


def set_task_node_status(root: str | Path, task_node_id: str, target: str) -> dict[str, Any]:
    if target not in NODE_STATES:
        raise ValueError(f"未知状态: {target}")
    data = _load(root)
    rec = data.get(str(task_node_id))
    if rec is None:
        raise ValueError(f"TaskNode 不存在: {task_node_id}")
    current = rec["status"]
    if target == current:
        return rec
    if target not in NODE_TRANSITIONS.get(current, ()):
        raise ValueError(f"非法状态迁移: {current} → {target}")
    rec["status"] = target
    rec["updated_at"] = _now_iso()
    _save(root, data)
    return rec


def resolve_task_node(root: str | Path, task_node_id: str) -> dict[str, Any]:
    """TaskNode -> Task -> Work -> Project 引用解析。"""
    from .os_core_task import resolve_task

    rec = get_task_node(root, task_node_id)
    if rec is None:
        raise ValueError(f"TaskNode 不存在: {task_node_id}")
    chain = resolve_task(root, rec["task_id"])
    return {"task_node": rec, **chain}


__all__ = ["NODE_STATES", "create_task_node", "get_task_node", "list_task_nodes",
           "resolve_task_node", "set_task_node_status", "task_node_tree", "update_task_node"]
