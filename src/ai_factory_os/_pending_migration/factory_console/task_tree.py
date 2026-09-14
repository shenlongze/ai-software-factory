"""src/legacy/factory-console/task_tree.py — K2 Task Tree (Real Complex Work 最小实现).

⚠️ FROZEN / LEGACY (S1 第 2 刀, 2026-09-08):
- 任务组织层 canonical = task_decomposition (多级树域, task_trees/{plan_id}.json)。
- 本模块保留供既有调用方 (conv_*/project_os 旧链) 兼容; 不扩展、不接新流量。
- 新 Golden Path 一律走 golden_path.generate_plan → task_decomposition。

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .unified_contract import (
    create_entity, store_entity, get_entity, bump_version,
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
    # 默认 node: node_id 带 role 段 (x-<role>) 使真实 executor factory 可路由
    node_specs = nodes or [{"node_id": "dev-software_developer", "name": "执行",
                            "type": "engineering", "executor_name": "software_developer"}]
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


def materialize_tree(root: Path | str, tree: dict[str, Any], *,
                     title: str = "", domain: str = "llm") -> dict[str, Any]:
    """把 LLM 分解出的【树 dict】物化成 task 实体（方案 A）。

    为什么: LLM 分解器产出的是 nodes/leaves 结构（用于 PLAN），
    而 CLI/编排/证据链都按 task 实体（parent_id/children）走 →
    必须在同一处把它落成实体，否则两套模型永远对不上。

    返回与 decompose() 同构的 tree 记录（task_tree_id/title/subtasks/count），
    因此 tasktree list/status/progress 无需改动即可看到它 ✓
    """
    nodes = tree.get("nodes") or []
    if not nodes:
        raise ValueError("materialize_tree: 空树（LLM 未产出节点）")
    root_title = (title or tree.get("goal") or "任务")[:120]
    root_task = create_entity("task", created_by="system")
    root_task["title"] = root_title
    root_task["status"] = "READY"
    root_task["domain"] = domain
    store_entity(root, root_task)

    # nodes 由 _build_nested_nodes 按【父先于子】顺序产出 → 单趟即可映射
    id_map: dict[str, str] = {}
    subtasks: list[str] = []
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        kind = str(n.get("kind") or "task")
        if kind == "project":
            continue
        parent_src = str(n.get("parent_id") or "")
        parent_id = id_map.get(parent_src, root_task["id"])
        e = create_entity("task", created_by="system", parent_id=parent_id)
        e["title"] = str(n.get("title") or "任务")[:200]
        e["status"] = "DRAFT"
        if n.get("change_type"):
            e["change_type"] = n["change_type"]
        if n.get("expected_files"):
            e["expected_files"] = list(n["expected_files"])
        e["tree_kind"] = kind
        if n.get("required_skill"):
            e["required_skill"] = str(n["required_skill"])[:60]
        if n.get("required_role"):
            e["required_role"] = str(n["required_role"])[:40]
        store_entity(root, e)
        id_map[str(n.get("id") or "")] = e["id"]
        pairs.append((e, n))
        if kind == "task":
            subtasks.append(e["id"])

    # ★ 依赖映射: 树节点 id → 实体 id（两套 id 空间不同，必须翻译）
    for ent, node in pairs:
        deps = [id_map[d] for d in (node.get("depends_on") or []) if d in id_map]
        deps = [d for d in deps if d != ent["id"]]
        if deps:
            ent["depends_on"] = deps
            store_entity(root, ent)
    root_task["children"] = list(subtasks)
    store_entity(root, root_task)
    record = {"task_tree_id": root_task["id"], "title": root_title, "domain": domain,
              "root_task": root_task["id"], "subtasks": subtasks,
              "count": len(subtasks), "source": "llm_tree",
              "tree_id": tree.get("tree_id", ""),
              "truncated": bool(tree.get("truncated"))}
    _save(root, "trees", _load(root, "trees") + [record])
    return record
