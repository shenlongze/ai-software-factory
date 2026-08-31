"""factory-console/project_os.py — K3 Real Project Operating Loop.

Project 持续运营: 普通用户通过 Conversation 创建/跟踪/推进真实 Project。

- Project Entity (S43 project_ 前缀): 从 Requirement 创建, 绑定 conv
- Sprint Entity (S43 sprint_ 前缀): project 下创建, 绑定 tasks
- Project→Sprint→Task 层级 (parent_id, 可追溯)
- Execution 回写: task status → sprint/project 状态投影 (实时计算, 非第二 SSOT)
- Requirement v2: 新 req 版本 → 识别受影响 task → replan (新 task)
- Approval gate: 高风险 task 执行前 request_approval → 用户批准 → 继续
- project_status: 从真实 task/run/evidence 投影 (Project/Sprint/Task 各层)

复用: S43 unified_contract + K1 conversation_os + K2 task_tree + S17 governance
禁止: 第二套 SSOT / 第二套 Task/Project 模型 / Fake Evidence / LLM 决定 lifecycle
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .unified_contract import (
    new_id, create_entity, store_entity, get_entity, entities, bump_version,
    lifecycle_transition, trace_lineage,
)
from .conversation_os import extract_requirement
from .task_tree import decompose, update_task_status, task_progress


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "project" / f"{name}.json"


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


# ------------------------------------------------------------------ Project

def create_project(root: Path | str, *, title: str, description: str = "",
                   source_conv_id: str = "", source_req_id: str = "",
                   created_by: str = "human") -> dict[str, Any]:
    """从 Requirement 创建 Project (S43 project_ 前缀, 绑定 conv/req)。"""
    req_id = ""
    if source_conv_id:
        req = extract_requirement(root, source_conv_id, title=title,
                                  description=description)
        req_id = req["id"]
    elif source_req_id:
        req_id = source_req_id
    proj = create_entity("project", created_by=created_by,
                         parent_id=req_id or "", project_id="")
    proj["title"] = title
    proj["description"] = description
    proj["source_conversation_id"] = source_conv_id
    proj["source_requirement_id"] = req_id
    proj["status"] = "ACTIVE"
    proj["sprints"] = []
    store_entity(root, proj)
    # 绑定 conv → project
    if source_conv_id:
        try:
            conv = get_entity(root, source_conv_id)
            conv["project_id"] = proj["id"]
            bump_version(conv, actor="system", note="project bound")
            store_entity(root, conv)
        except Exception:  # noqa: BLE001
            pass
    return proj


def projects(root: Path | str) -> list[dict[str, Any]]:
    return [e for e in entities(root, entity_type="project")]


def get_project(root: Path | str, project_id: str) -> dict[str, Any]:
    return get_entity(root, project_id)


# ------------------------------------------------------------------ Sprint

def create_sprint(root: Path | str, project_id: str, *, title: str,
                  goal: str = "") -> dict[str, Any]:
    """Project 下创建 Sprint (S43 sprint_ 前缀, parent=project)。"""
    proj = get_project(root, project_id)
    sp = create_entity("sprint", created_by="system", parent_id=project_id,
                       project_id=project_id)
    sp["title"] = title
    sp["goal"] = goal
    sp["status"] = "ACTIVE"
    sp["tasks"] = []
    store_entity(root, sp)
    proj["sprints"] = proj.get("sprints", []) + [sp["id"]]
    bump_version(proj, actor="system", note="sprint created")
    store_entity(root, proj)
    return sp


def sprints(root: Path | str, project_id: str = "") -> list[dict[str, Any]]:
    all_s = [e for e in entities(root, entity_type="sprint")]
    if project_id:
        all_s = [s for s in all_s if s.get("project_id") == project_id]
    return all_s


def get_sprint(root: Path | str, sprint_id: str) -> dict[str, Any]:
    return get_entity(root, sprint_id)


def add_task_to_sprint(root: Path | str, sprint_id: str, task_id: str) -> dict[str, Any]:
    """Task 加入 Sprint (sprint.tasks + task.project_id 绑定)。"""
    sp = get_sprint(root, sprint_id)
    task = get_entity(root, task_id)
    sp["tasks"] = sp.get("tasks", []) + [task_id]
    bump_version(sp, actor="system", note="task added")
    store_entity(root, sp)
    task["sprint_id"] = sprint_id
    bump_version(task, actor="system", note="sprint bound")
    store_entity(root, task)
    return sp


# ------------------------------------------------------------------ 状态投影 (实时计算, 非第二 SSOT)

def _task_state(root: Path | str, task_id: str) -> dict[str, Any]:
    t = get_entity(root, task_id)
    return {"id": t["id"], "title": t.get("title", ""), "status": t.get("status", "DRAFT"),
            "production_run_id": t.get("production_run_id", ""),
            "updated_at": t.get("updated_at", "")}


def sprint_status(root: Path | str, sprint_id: str) -> dict[str, Any]:
    """Sprint 状态投影 (从真实 task 实时计算)。"""
    sp = get_sprint(root, sprint_id)
    tasks = [_task_state(root, tid) for tid in sp.get("tasks", [])]
    completed = sum(1 for t in tasks if t["status"] == "COMPLETED")
    failed = sum(1 for t in tasks if t["status"] == "FAILED")
    running = sum(1 for t in tasks if t["status"] == "RUNNING")
    blocked = sum(1 for t in tasks if t["status"] == "BLOCKED")
    return {"sprint_id": sprint_id, "title": sp.get("title", ""),
            "status": sp.get("status", ""), "tasks": tasks,
            "progress": {"completed": completed, "failed": failed,
                         "running": running, "blocked": blocked,
                         "total": len(tasks),
                         "percentage": round(completed / len(tasks) * 100) if tasks else 0},
            "calculated_at": _now_iso()}


def project_status(root: Path | str, project_id: str) -> dict[str, Any]:
    """Project 状态投影 (Project→Sprint→Task 全层, 实时计算)。"""
    proj = get_project(root, project_id)
    sprint_statuses = [sprint_status(root, sid) for sid in proj.get("sprints", [])]
    all_tasks = [t for s in sprint_statuses for t in s["tasks"]]
    completed = sum(1 for t in all_tasks if t["status"] == "COMPLETED")
    failed = sum(1 for t in all_tasks if t["status"] == "FAILED")
    running = sum(1 for t in all_tasks if t["status"] == "RUNNING")
    blocked = sum(1 for t in all_tasks if t["status"] == "BLOCKED")
    waiting = sum(1 for t in all_tasks if t["status"] in ("DRAFT", "READY"))
    return {"project_id": project_id, "title": proj.get("title", ""),
            "status": proj.get("status", ""),
            "source_conversation_id": proj.get("source_conversation_id", ""),
            "sprints": sprint_statuses,
            "progress": {"completed": completed, "failed": failed,
                         "running": running, "blocked": blocked,
                         "waiting": waiting, "total": len(all_tasks),
                         "percentage": round(completed / len(all_tasks) * 100) if all_tasks else 0},
            "calculated_at": _now_iso()}


# ------------------------------------------------------------------ Requirement v2 → Replan

def update_requirement(root: Path | str, req_id: str, *, new_title: str,
                       new_description: str = "") -> dict[str, Any]:
    """Requirement 新版本 (不可覆盖历史; 新 req 实体, 关联旧版本)。"""
    old = get_entity(root, req_id)
    req = create_entity("req", created_by="human", parent_id=old.get("parent_id", ""),
                        project_id=old.get("project_id", ""))
    req["title"] = new_title
    req["description"] = new_description
    req["acceptance_criteria"] = old.get("acceptance_criteria", "")
    req["source_conversation_id"] = old.get("source_conversation_id", "")
    req["status"] = "VALIDATED"
    req["supersedes"] = req_id
    req["version"] = old.get("version", 1) + 1
    store_entity(root, req)
    return req


def replan(root: Path | str, project_id: str, *, new_req_id: str,
           new_task_title: str) -> dict[str, Any]:
    """Requirement 变更 → 受影响 Task 识别 + 新 Task (Replan)。"""
    proj = get_project(root, project_id)
    affected = []
    for sid in proj.get("sprints", []):
        sp = get_sprint(root, sid)
        for tid in sp.get("tasks", []):
            t = get_entity(root, tid)
            # 未完成 task 视为受影响 (可重计划)
            if t.get("status") not in ("COMPLETED",):
                affected.append(t["id"])
    # 新 task (parent=project, 关联新 req)
    task = create_entity("task", created_by="system", parent_id=project_id,
                         project_id=project_id)
    task["title"] = new_task_title
    task["status"] = "READY"
    task["requirement_id"] = new_req_id
    store_entity(root, task)
    return {"project_id": project_id, "new_task_id": task["id"],
            "affected_tasks": affected, "replanned_at": _now_iso()}


# ------------------------------------------------------------------ Approval gate

def approve_task_execution(root: Path | str, task_id: str, *,
                           risk: str = "HIGH") -> dict[str, Any]:
    """高风险 task 执行前 Approval gate (S17 governance; 不批准 → 不执行)。"""
    from .governance_service import request_approval, decide_approval
    task = get_entity(root, task_id)
    appr = request_approval(root, production_run_id="", artifact_ids=[],
                            requested_by="project_os",
                            policy_id="production_apply",
                            subject_type="task", subject_id=task_id)
    return {"approval_id": appr.get("approval_id", ""), "status": "PENDING",
            "task_id": task_id, "risk": risk}


def decide_task_approval(root: Path | str, approval_id: str, *,
                         decision: str, decided_by: str = "human") -> dict[str, Any]:
    """用户批准/拒绝 (APPROVED → 可执行; REJECTED → 不执行)。"""
    from .governance_service import decide_approval
    # 统一 decision 值域: approve→APPROVED, reject→REJECTED
    norm = {"approve": "APPROVED", "approved": "APPROVED", "reject": "REJECTED",
            "rejected": "REJECTED"}.get(str(decision).lower(), decision)
    return decide_approval(root, approval_id, decision=norm, decided_by=decided_by)


def task_approval_status(root: Path | str, task_id: str) -> str:
    """Task 的 Approval 状态 (从真实 governance 数据)。"""
    try:
        d = json.loads((Path(root) / "governance" / "approvals.json").read_text(encoding="utf-8"))
        approvals = d if isinstance(d, list) else []
    except (OSError, ValueError):
        approvals = []
    for a in approvals:
        if a.get("subject_id") == task_id:
            return a.get("decision", "PENDING")
    return "NO_APPROVAL_REQUIRED"
