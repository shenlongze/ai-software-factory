"""factory-console/task_tree.py — K2 Task Tree (Real Complex Work 最小实现).

多任务分解 + 依赖 + 进度投影 (Task 是 What, Node 是 How):
- TaskTree: 从 Conversation Requirement 分解为 task 树 (确定性规则)
- Task 层级: parent_id/children (S43 task_ 实体扩展)
- 依赖: depends_on (串行/并行)
- Progress: completed_units/total_units/percentage (统一 Projection, 非 UI 状态)

复用: S43 unified_contract + S30 workforce + S3 production + K1 conversation_os
禁止: 第二套 Task 模型 / 第二套进度 / fake 分解
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
)
from .conversation_os import extract_requirement


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


#: 确定性任务分解模板 (按领域)
DECOMPOSE_TEMPLATES: dict[str, list[str]] = {
    "app": ["需求分析", "技术架构", "后端实现", "前端实现", "测试验证", "发布准备"],
    "backend": ["接口设计", "数据库设计", "核心实现", "测试验证"],
    "default": ["分析", "设计", "实现", "验证", "交付"],
}


def decompose(root: Path | str, *, title: str, description: str = "",
              domain: str = "default",
              source_conv_id: str = "", source_req_id: str = "") -> dict[str, Any]:
    """确定性任务分解: 需求 → task 树 (S43 task_ 实体, parent/children 层级)。"""
    # 1. Requirement 实体 (若未建)
    req = None
    if source_conv_id:
        req = extract_requirement(root, source_conv_id, title=title,
                                  description=description)
    elif source_req_id:
        req = get_entity(root, source_req_id)

    # 2. 根 Task
    root_task = create_entity("task", created_by="system",
                              parent_id=req["id"] if req else "")
    root_task["title"] = title
    root_task["status"] = "READY"
    root_task["domain"] = domain
    store_entity(root, root_task)

    # 3. 子任务 (模板分解)
    subtasks = []
    for i, step in enumerate(DECOMPOSE_TEMPLATES.get(domain, DECOMPOSE_TEMPLATES["default"])):
        t = create_entity("task", created_by="system", parent_id=root_task["id"])
        t["title"] = f"{title} · {step}"
        t["status"] = "DRAFT"
        t["order"] = i
        t["depends_on"] = [subtasks[-1]["id"]] if subtasks else []  # 串行依赖
        store_entity(root, t)
        subtasks.append(t)

    root_task["children"] = [t["id"] for t in subtasks]
    bump_version(root_task, actor="system", note="decomposed")
    store_entity(root, root_task)

    tree = {"task_tree_id": root_task["id"], "title": title, "domain": domain,
            "root_task": root_task["id"], "subtasks": [t["id"] for t in subtasks],
            "requirement_id": req["id"] if req else "",
            "count": len(subtasks)}
    _save(root, "trees", _load(root, "trees") + [tree])
    return tree


def task_trees(root: Path | str) -> list[dict[str, Any]]:
    return _load(root, "trees")


def get_tree(root: Path | str, task_tree_id: str) -> dict[str, Any]:
    for t in _load(root, "trees"):
        if t["task_tree_id"] == task_tree_id:
            return t
    raise ValueError(f"TaskTree 不存在: {task_tree_id}")


def update_task_status(root: Path | str, task_id: str, *, status: str,
                       actor: str = "system") -> dict[str, Any]:
    """Task 状态更新 (S43 lifecycle 语义; 进度由 Projection 计算, 非 UI 状态)。"""
    t = get_entity(root, task_id)
    if t["type"] != "task":
        raise ValueError(f"非 task 实体: {task_id}")
    t["status"] = status
    bump_version(t, actor=actor, note=f"status={status}")
    store_entity(root, t)
    return t


def task_progress(root: Path | str, task_tree_id: str) -> dict[str, Any]:
    """统一进度投影 (completed_units/total_units/percentage; 可重建, 非第二事实源)。"""
    tree = get_tree(root, task_tree_id)
    subtasks = [get_entity(root, tid) for tid in tree["subtasks"]]
    total = len(subtasks)
    done = [t for t in subtasks if t.get("status") in ("COMPLETED", "VALIDATED", "ACTIVE")]
    completed = sum(1 for t in subtasks if t.get("status") == "COMPLETED")
    percentage = round(completed / total * 100) if total else 0
    return {"task_tree_id": task_tree_id, "total_units": total,
            "completed_units": completed, "percentage": percentage,
            "source": "task_graph", "calculated_at": _now_iso(),
            "in_progress": [t["id"] for t in done if t.get("status") != "COMPLETED"],
            "blocked": [t["id"] for t in subtasks if t.get("status") == "BLOCKED"]}


def tree_status(root: Path | str, task_tree_id: str) -> dict[str, Any]:
    """Task Tree 状态 (每任务 status + 依赖 + 进度)。"""
    tree = get_tree(root, task_tree_id)
    tasks = [get_entity(root, tid) for tid in [tree["root_task"]] + tree["subtasks"]]
    return {"task_tree_id": task_tree_id, "title": tree["title"],
            "progress": task_progress(root, task_tree_id),
            "tasks": [{"id": t["id"], "title": t.get("title", ""), "status": t.get("status"),
                       "depends_on": t.get("depends_on", []),
                       "production_run_id": t.get("production_run_id", "")} for t in tasks]}


def execute_subtask(root: Path | str, task_id: str, *,
                    executor_factory, artifact_root: Path | str,
                    nodes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """子任务 → 真实 production_run 执行 (Task 是 What, Node 是 How)。

    每个子任务独立 NodeRun (Node 独立性保持), 产生 Evidence。
    """
    from .production_run import register_workflow, create_production_run, execute_production_run

    t = get_entity(root, task_id)
    if t["type"] != "task":
        raise ValueError(f"非 task 实体: {task_id}")
    node_specs = nodes or [{"node_id": "exec", "name": "执行", "type": "engineering",
                            "executor_name": "agent"}]
    wf_id = f"task-{task_id[-8:]}"
    try:
        register_workflow(root, workflow_id=wf_id, name=wf_id, nodes=node_specs)
    except Exception:  # noqa: BLE001
        pass
    run = create_production_run(root, wf_id)
    t["production_run_id"] = run["run_id"]
    t["status"] = "RUNNING"
    bump_version(t, actor="system", note="run created")
    store_entity(root, t)
    result = execute_production_run(root, run["run_id"], executor_factory=executor_factory,
                                    artifact_root=str(artifact_root))
    result_state = result.get("state", "UNKNOWN")
    t = get_entity(root, task_id)
    t["status"] = "COMPLETED" if result_state == "COMPLETED" else "FAILED"
    t["run_state"] = result_state
    bump_version(t, actor="system", note=f"run {result_state}")
    store_entity(root, t)
    return {"task_id": task_id, "production_run_id": run["run_id"],
            "state": result_state, "task_status": t["status"]}


def execute_tree(root: Path | str, task_tree_id: str, *,
                 executor_factory, artifact_root: Path | str,
                 nodes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Task Tree 串行执行 (依赖顺序, 每个子任务真实执行; 失败停止)。"""
    tree = get_tree(root, task_tree_id)
    results = []
    for tid in tree["subtasks"]:
        r = execute_subtask(root, tid, executor_factory=executor_factory,
                            artifact_root=artifact_root, nodes=nodes)
        results.append(r)
        if r["state"] != "COMPLETED":
            break  # 串行依赖: 失败停止
    return {"task_tree_id": task_tree_id, "results": results,
            "progress": task_progress(root, task_tree_id),
            "summary": f"{len([r for r in results if r['state'] == 'COMPLETED'])}/{len(tree['subtasks'])} 子任务完成"}
