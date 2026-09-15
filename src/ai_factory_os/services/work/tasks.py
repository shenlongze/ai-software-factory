"""decomposition · 任务树读取与状态更新（搬迁自 factory_console.task_tree）。

数据: `<root>/ops/tasktree/trees.json` —— **本域自己的数据** ✓（原子写 os.replace）。

跨域依赖 —— 实体层（`get_entity` / `store_entity` / `bump_version`）经 `bind_lookups()`
**注入**，本域不 import `unified_contract`（按 SSoT R3/R5「服务域不许跨域直连」）。

未接线时的行为（诚实优先）:
  · `task_progress` / `tree_status` → 返回**结构完整 + `unwired` 标注**（不是假 0，也不是空页）
  · `update_task_status`         → **fail-closed 拒绝**（写操作绝不静默通过 ✗）

搬迁说明（刀2 第三域 · 续）:
  · 只搬 HTTP 面用到的: get_tree / task_progress / tree_status / update_task_status。
  · 老区的 `decompose` / `execute_subtask` / `execute_tree` / `materialize_tree` /
    `render_tasks_md` **未搬** —— HTTP 面不经过它们（POST /api/task-trees 已判 LEGACY+FROZEN，本刀删除）。
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

__all__ = ["get_tree", "task_progress", "tree_status", "update_task_status", "bind_lookups"]

#: 跨域（实体层）钩子 —— bootstrap 注入
GetEntity = Callable[[Path | str, str], dict[str, Any]]
StoreEntity = Callable[[Path | str, dict[str, Any]], Any]
BumpVersion = Callable[..., Any]
_hooks: dict[str, Any] = {}


class _NoLookup:
    """哨兵：该数据源未接线（≠ 数据为空）。"""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover
        return "<no-lookup>"


NO_LOOKUP = _NoLookup()


def bind_lookups(*, get_entity: GetEntity | None = None,
                 store_entity: StoreEntity | None = None,
                 bump_version: BumpVersion | None = None) -> None:
    """注入实体层能力（bootstrap 装配时调用；None 项保持不变）。"""
    for key, fn in (("get_entity", get_entity), ("store_entity", store_entity),
                    ("bump_version", bump_version)):
        if fn is not None:
            _hooks[key] = fn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "tasktree" / f"{name}.json"


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


def get_tree(root: Path | str, task_tree_id: str) -> dict[str, Any]:
    """任务树；不存在 → ValueError（与老区一致）。"""
    for t in _load(root, "trees"):
        if t.get("task_tree_id") == task_tree_id:
            return t
    raise ValueError(f"TaskTree 不存在: {task_tree_id}")


def _entity(root: Path | str, entity_id: str) -> Any:
    fn = _hooks.get("get_entity")
    return NO_LOOKUP if fn is None else fn(root, entity_id)


def task_progress(root: Path | str, task_tree_id: str) -> dict[str, Any]:
    """统一进度投影（completed/total/percentage；可重建，非第二事实源）。"""
    tree = get_tree(root, task_tree_id)
    ids = list(tree.get("subtasks") or [])
    subtasks = [_entity(root, tid) for tid in ids]
    if any(s is NO_LOOKUP for s in subtasks):
        return {"task_tree_id": task_tree_id, "total_units": 0, "completed_units": 0,
                "percentage": 0, "in_progress": [], "blocked": [],
                "unwired": ["entities"], "calculated_at": _now_iso()}
    total = len(subtasks)
    completed = sum(1 for t in subtasks if t.get("status") == "COMPLETED")
    active = [t for t in subtasks
              if t.get("status") in ("COMPLETED", "VALIDATED", "ACTIVE")]
    return {"task_tree_id": task_tree_id, "total_units": total,
            "completed_units": completed,
            "percentage": round(completed / total * 100) if total else 0,
            "source": "task_graph", "calculated_at": _now_iso(),
            "in_progress": [t["id"] for t in active if t.get("status") != "COMPLETED"],
            "blocked": [t["id"] for t in subtasks if t.get("status") == "BLOCKED"]}


def tree_status(root: Path | str, task_tree_id: str) -> dict[str, Any]:
    """Task Tree 状态（每任务 status + 依赖 + 进度）。"""
    tree = get_tree(root, task_tree_id)
    ids = [tree.get("root_task", "")] + list(tree.get("subtasks") or [])
    tasks = [_entity(root, tid) for tid in ids if tid]
    if any(t is NO_LOOKUP for t in tasks):
        return {"task_tree_id": task_tree_id, "title": tree.get("title", ""),
                "progress": task_progress(root, task_tree_id), "tasks": [],
                "unwired": ["entities"], "calculated_at": _now_iso()}
    return {"task_tree_id": task_tree_id, "title": tree.get("title", ""),
            "progress": task_progress(root, task_tree_id),
            "tasks": [{"id": t.get("id", ""), "title": t.get("title", ""),
                       "status": t.get("status"),
                       "depends_on": t.get("depends_on", []),
                       "production_run_id": t.get("production_run_id", "")} for t in tasks]}


def update_task_status(root: Path | str, task_id: str, *, status: str,
                       actor: str = "system") -> dict[str, Any]:
    """Task 状态更新（S43 lifecycle 语义；进度由 Projection 计算，非 UI 状态）。

    ★ 写操作: 实体层未接线 → 抛错拒绝（fail-closed，绝不静默通过）✓
    """
    get_e, store_e, bump = (_hooks.get("get_entity"), _hooks.get("store_entity"),
                            _hooks.get("bump_version"))
    if get_e is None or store_e is None or bump is None:
        raise RuntimeError(
            "实体层未接线（get_entity/store_entity/bump_version 未注入）—— 拒绝写操作")
    t = get_e(root, task_id)
    if t.get("type") != "task":
        raise ValueError(f"非 task 实体: {task_id}")
    t["status"] = status
    bump(t, actor=actor, note=f"status={status}")
    store_e(root, t)
    return t
