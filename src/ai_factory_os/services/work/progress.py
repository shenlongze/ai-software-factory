"""开发任务进度（progress）—— 让【监控/看板/状态】看得见【执行】。

【全链路实跑查出的最严重一处（卡点 1）】
  执行走的是**任务树**（`tasktree` 的叶任务, 也是页面上的待办清单）;
  而 `metrics` / `kanban` / `task list` / `status` 读的是**任务域**（tasks/*.json + backlog + assignments）。
  两者是两套账本 ⇒ 工厂干着活、代码在提交, 看板上却永远显示 0。

【修法（一数据一权威源）】
  · 权威源 = 任务树（它才是执行的真实账本: 叶状态就是执行回写的状态）
  · 本模块把它投影成"任务行 / 进度汇总", 供监控类读侧合并使用 —— **不做双写**（双写就是两套账本的病根）
  · 任务域那份照旧服务"工厂自己的流程任务", 但监控必须**两份都报**, 且标明来源
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

#: 叶状态 ⇒ 看板/任务行的状态词（看板列: todo/ready/in_progress/review/blocked/failed/done/cancelled）
_STATUS_MAP = {
    "": "todo",
    "pending": "todo",
    "todo": "todo",
    "ready": "ready",
    "claimed": "in_progress",
    "in_progress": "in_progress",
    "review": "review",
    "blocked": "blocked",
    "failed": "failed",
    "completed": "done",
    "done": "done",
    "cancelled": "cancelled",
}


def leaf_rows(root: Path | str, *, plan_id: str = "") -> list[dict[str, Any]]:
    """任务树的叶 ⇒ 任务行（与 `_task_rows` 同形状: id/title/status/project/role/agent）。

    ★ 这是"开发任务"的唯一权威来源（执行回写的就是叶状态）。
    """
    from ai_factory_os.services.work import decomposition as D

    rows: list[dict[str, Any]] = []
    for meta in D.list_trees(root):
        pid = str(meta.get("plan_id") or "")
        if plan_id and pid != plan_id:
            continue
        tree = D.load_tree(root, pid)
        if not tree:
            continue
        proj = str(tree.get("project_id") or "")
        for n in tree.get("nodes") or []:
            if n.get("kind") != "task":
                continue
            raw = str(n.get("status") or "").strip().lower()
            caps = [str(c) for c in (n.get("required_capabilities") or [])]
            rows.append({
                "id": str(n.get("id") or ""),
                "title": str(n.get("display_name") or n.get("title") or ""),
                "status": _STATUS_MAP.get(raw, raw or "todo"),
                "raw_status": raw or "pending",
                "project": proj,
                "plan_id": pid,
                "role": str(n.get("required_role") or "") if n.get("required_role") not in (None, "unassigned") else (caps[0] if caps else ""),
                "agent": str(n.get("claimed_by") or n.get("assignee") or ""),
                "source": "tasktree",
            })
    return rows


def summary(root: Path | str, *, project_id: str = "", plan_id: str = "") -> dict[str, Any]:
    """开发任务汇总（全树/单项目/单计划）—— 给 metrics/status 用的同一份口径。"""
    rows = [r for r in leaf_rows(root, plan_id=plan_id)
            if not project_id or r["project"] == project_id]
    by_status: dict[str, int] = {}
    by_project: dict[str, dict[str, int]] = {}
    for r in rows:
        by_status[r["raw_status"]] = by_status.get(r["raw_status"], 0) + 1
        p = by_project.setdefault(r["project"], {"leaves": 0, "done": 0})
        p["leaves"] += 1
        if r["raw_status"] == "completed":
            p["done"] += 1
    done = sum(1 for r in rows if r["raw_status"] == "completed")
    return {
        "plans": len({r["plan_id"] for r in rows}),
        "projects": sorted(by_project),
        "leaves": len(rows),
        "done": done,
        "percent": (done * 100 // len(rows)) if rows else 0,
        "by_status": by_status,
        "by_project": by_project,
        "source": "tasktree（任务树 = 执行的真实账本）",
    }
