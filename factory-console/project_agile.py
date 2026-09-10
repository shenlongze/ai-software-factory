"""factory-console/project_agile.py — 项目级敏捷管理域 (S1 第 6 刀, canonical)。

把 Golden Path 认知链 (PRD/Plan/执行) 挂到真实项目:
```
Project (P-*)  ← conversation.project_id 锚点
  └─ Backlog: [PRD 条目] (approve_prd 自动入, 幂等)
  └─ Sprints: [Sprint]  (planned → active → review → closed)
       ├─ prd_ids + plan_ids (approved Plan 绑 active sprint)
       └─ 叶统计 (COMPLETED/FAILED/BLOCKED 回写)
```

边界:
- 数据 <root>/project_agile/{pid}.json (project_os 的 entity 系统保留 legacy, 不混写)
- project_id 复用 project_os P-* (可经 project_os.get_project 反查标题)
- conversation 未 attach 项目 → 行为不变 (单会话 golden path 兼容)
- Sprint 状态机: planned → active → review → closed; 未完成叶在 closed 时回 backlog
"""
from __future__ import annotations
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

#: Sprint 状态机
SPRINT_STATES = ("planned", "active", "review", "closed")
_SPRINT_NEXT = {
    "planned": "active",
    "active": "review",
    "review": "closed",
}


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _agile_file(root: Path | str, project_id: str) -> Path:
    return Path(root) / "project_agile" / f"{project_id}.json"


def _load(root: Path | str, project_id: str) -> dict[str, Any]:
    p = _agile_file(root, project_id)
    if not p.is_file():
        return {"project_id": project_id, "backlog": [], "sprints": []}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {
            "project_id": project_id, "backlog": [], "sprints": []}
    except (OSError, ValueError):
        return {"project_id": project_id, "backlog": [], "sprints": []}


def _save(root: Path | str, data: dict[str, Any]) -> None:
    p = _agile_file(root, data["project_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


# ------------------------------------------------------------------ A. 项目锚点

def attach_project(root: Path | str, conversation_id: str,
                   project_id: str) -> dict[str, Any]:
    """conversation 关联项目 (conversation 元数据 project_id)。"""
    from factory_console import product_understanding as pu
    doc = pu._load_conv(root, conversation_id)
    if doc is None:
        raise ValueError(f"conversation 不存在: {conversation_id}")
    doc["project_id"] = project_id
    doc["updated_at"] = _now_iso()
    pu._save_conv(root, conversation_id, doc)
    return {"conversation_id": conversation_id, "project_id": project_id}


def get_project_by_conversation(root: Path | str,
                                conversation_id: str) -> dict[str, Any] | None:
    """按 conversation 反查项目 (无关联 → None)。"""
    from factory_console import product_understanding as pu
    doc = pu._load_conv(root, conversation_id)
    if doc is None:
        return None
    pid = doc.get("project_id")
    if not pid:
        return None
    # project_os P-* 实体反查
    try:
        from factory_console.project_os import get_project
        proj = get_project(root, pid)
        return {"project_id": pid, "title": proj.get("title", ""),
                "description": proj.get("description", "")}
    except Exception:  # noqa: BLE001 — 实体缺失 → 仍返回 id 级关联
        return {"project_id": pid, "title": "", "description": ""}


def conversation_project_id(root: Path | str, conversation_id: str) -> str:
    """conversation 关联的 project_id (无 → "")。"""
    from factory_console import product_understanding as pu
    doc = pu._load_conv(root, conversation_id)
    return str((doc or {}).get("project_id") or "")


# ------------------------------------------------------------------ B. Backlog

def add_prd_to_backlog(root: Path | str, project_id: str, prd_id: str,
                       conversation_id: str) -> dict[str, Any]:
    """已确认 PRD 进项目 backlog (幂等: 同 prd_id 不重复)。"""
    data = _load(root, project_id)
    for item in data["backlog"]:
        if item.get("prd_id") == prd_id:
            return {"project_id": project_id, "prd_id": prd_id, "added": False,
                    "reason": "already_in_backlog"}
    data["backlog"].append({
        "prd_id": prd_id, "conversation_id": conversation_id,
        "status": "pending", "added_at": _now_iso(), "sprint_id": None,
    })
    _save(root, data)
    return {"project_id": project_id, "prd_id": prd_id, "added": True}


def list_backlog(root: Path | str, project_id: str) -> list[dict[str, Any]]:
    """Backlog 待办 (pending 且未进 active/review sprint)。"""
    data = _load(root, project_id)
    active_sprint_prds = set()
    for sp in data["sprints"]:
        if sp.get("status") in ("active", "review"):
            active_sprint_prds.update(sp.get("prd_ids") or [])
    return [b for b in data["backlog"]
            if b.get("status") == "pending"
            and b.get("prd_id") not in active_sprint_prds]


def list_all_backlog(root: Path | str, project_id: str) -> list[dict[str, Any]]:
    """Backlog 全量 (含已进 sprint 的, 视图用)。"""
    return _load(root, project_id)["backlog"]


# ------------------------------------------------------------------ C. Sprint 生命周期

def create_sprint(root: Path | str, project_id: str, *, title: str,
                  prd_ids: list[str] | None = None,
                  pull_from_backlog: bool = True) -> dict[str, Any]:
    """创建 Sprint (planned): 从 backlog 拉指定或全部待办 PRD。

    prd_ids=None + pull_from_backlog=True → 拉当前 backlog 全部 pending。
    prd_ids=[] → 空 sprint (手动后续加)。
    """
    data = _load(root, project_id)
    backlog = list_backlog(root, project_id)
    if prd_ids is None and pull_from_backlog:
        prd_ids = [b["prd_id"] for b in backlog]
    prd_ids = list(dict.fromkeys(prd_ids or []))  # 去重保序
    # 标记 backlog 项为 in-sprint
    for b in data["backlog"]:
        if b.get("prd_id") in prd_ids:
            b["status"] = "in_sprint"
    sprint = {
        "sprint_id": f"SPRINT-{uuid.uuid4().hex[:8]}",
        "project_id": project_id,
        "title": title,
        "status": "planned",
        "prd_ids": prd_ids,
        "plan_ids": [],
        "stats": {"total_leaves": 0, "completed": 0, "failed": 0,
                  "blocked": 0, "not_attempted": 0},
        "created_at": _now_iso(),
        "started_at": None, "closed_at": None,
    }
    data["sprints"].append(sprint)
    _save(root, data)
    return sprint


def get_sprint(root: Path | str, project_id: str,
               sprint_id: str) -> dict[str, Any] | None:
    data = _load(root, project_id)
    return next((s for s in data["sprints"]
                 if s.get("sprint_id") == sprint_id), None)


def get_active_sprint(root: Path | str, project_id: str) -> dict[str, Any] | None:
    data = _load(root, project_id)
    return next((s for s in data["sprints"]
                 if s.get("status") in ("active", "review")), None)


def _transition(root: Path | str, project_id: str, sprint_id: str,
                to_state: str) -> dict[str, Any]:
    if to_state not in SPRINT_STATES:
        raise ValueError(f"非法 sprint 状态: {to_state}")
    data = _load(root, project_id)
    sp = next((s for s in data["sprints"]
               if s.get("sprint_id") == sprint_id), None)
    if sp is None:
        raise ValueError(f"sprint 不存在: {sprint_id}")
    if to_state == "active":
        if sp["status"] != "planned":
            raise ValueError(
                f"sprint {sprint_id} 当前 {sp['status']} — 仅 planned 可 start")
        sp["started_at"] = _now_iso()
    elif to_state == "review":
        if sp["status"] != "active":
            raise ValueError(
                f"sprint {sprint_id} 当前 {sp['status']} — 仅 active 可 review")
    elif to_state == "closed":
        if sp["status"] != "review":
            raise ValueError(
                f"sprint {sprint_id} 当前 {sp['status']} — 仅 review 可 close")
        sp["closed_at"] = _now_iso()
        _return_unfinished_to_backlog(data, sp)
    sp["status"] = to_state
    sp["updated_at"] = _now_iso()
    _save(root, data)
    return sp


def _return_unfinished_to_backlog(data: dict[str, Any],
                                  sp: dict[str, Any]) -> None:
    """closed 时未完成 PRD (FAILED/BLOCKED/未做) 回 backlog。"""
    stats = sp.get("stats") or {}
    # 有 FAILED/BLOCKED/未完成叶的 PRD 视为未完成
    done_prds = set()
    per_prd = (sp.get("per_prd_stats") or {})
    for prd_id, s in per_prd.items():
        if s.get("failed", 0) == 0 and s.get("blocked", 0) == 0 \
                and s.get("not_attempted", 0) == 0 and s.get("completed", 0) > 0:
            done_prds.add(prd_id)
    for b in data["backlog"]:
        if b.get("prd_id") in sp.get("prd_ids", []) \
                and b.get("status") == "in_sprint" \
                and b.get("prd_id") not in done_prds:
            b["status"] = "pending"
            b["sprint_id"] = None
            b["returned_at"] = _now_iso()
    # 完成项标记 closed
    for b in data["backlog"]:
        if b.get("prd_id") in done_prds:
            b["status"] = "closed"
            b["sprint_id"] = sp.get("sprint_id")
    stats["unfinished_returned"] = len(
        [b for b in data["backlog"]
         if b.get("returned_at") and b.get("sprint_id") == sp.get("sprint_id")])
    sp["stats"] = stats


def start_sprint(root: Path | str, project_id: str,
                 sprint_id: str) -> dict[str, Any]:
    return _transition(root, project_id, sprint_id, "active")


def mark_review(root: Path | str, project_id: str,
                sprint_id: str) -> dict[str, Any]:
    return _transition(root, project_id, sprint_id, "review")


def close_sprint(root: Path | str, project_id: str,
                 sprint_id: str) -> dict[str, Any]:
    return _transition(root, project_id, sprint_id, "closed")


# ------------------------------------------------------------------ D. Golden Path 挂接

def bind_plan_to_sprint(root: Path | str, project_id: str, plan_id: str,
                        prd_id: str) -> dict[str, Any] | None:
    """approved Plan 绑当前 active sprint (无 active → None)。"""
    sp = get_active_sprint(root, project_id)
    if sp is None:
        return None
    if plan_id not in sp["plan_ids"]:
        sp["plan_ids"].append(plan_id)
    data = _load(root, project_id)
    for s in data["sprints"]:
        if s["sprint_id"] == sp["sprint_id"]:
            if plan_id not in s["plan_ids"]:
                s["plan_ids"].append(plan_id)
            s.setdefault("prd_plan_map", {})[prd_id] = plan_id
    _save(root, data)
    return get_sprint(root, project_id, sp["sprint_id"])


def update_sprint_leaf_stats(root: Path | str, project_id: str, plan_id: str,
                             prd_id: str, *,
                             executed: list[dict[str, Any]]) -> dict[str, Any] | None:
    """execute_approved 结果回写 sprint 叶统计 (按叶状态计数)。"""
    data = _load(root, project_id)
    sp = next((s for s in data["sprints"]
               if plan_id in (s.get("plan_ids") or [])), None)
    if sp is None:
        return None
    from collections import Counter
    c = Counter(e.get("result", {}).get("state", "NOT_ATTEMPTED")
                for e in executed)
    sp["stats"] = {
        "total_leaves": len(executed),
        "completed": c.get("COMPLETED", 0),
        "failed": c.get("FAILED", 0),
        "blocked": c.get("BLOCKED", 0),
        "not_attempted": c.get("NOT_ATTEMPTED", 0),
    }
    per = sp.setdefault("per_prd_stats", {})
    per[prd_id] = dict(sp["stats"])
    sp["updated_at"] = _now_iso()
    _save(root, data)
    return sp


# ------------------------------------------------------------------ E. 视图 (只读)

def project_agile_view(root: Path | str, project_id: str) -> dict[str, Any]:
    """项目敏捷视图: backlog / sprints / active。"""
    data = _load(root, project_id)
    return {
        "project_id": project_id,
        "backlog": list_backlog(root, project_id),
        "backlog_count": len(list_backlog(root, project_id)),
        "sprints": data["sprints"],
        "active_sprint": get_active_sprint(root, project_id),
    }
