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

复用: S43 unified_contract + S30 workforce + S3 production（K1 conversation_os 已于 2026-09-15 退休删除 ✓）
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
    create_entity, create_requirement, store_entity, get_entity, bump_version,
)


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
    """确定性【模板】分解: 需求 → task 树 (S43 task_ 实体)。

    ★ 生产路径【不】经过这里 —— 一律走 LLM 分解器
      (task_decomposition.build_llm_decomposer: 真实需求分析 + 不限层数
       + 任务带 required_role/required_skill + 依赖 DAG)。
    本函数用固定模板 (DECOMPOSE_TEMPLATES) 产出稳定结果。
    原用途是 golden_suite 回归断言 —— 该套件已随 conversation_os 于 2026-09-15 退休 ✓；
    现仅供 API 的模板路径 (POST /api/task-trees/decompose) 兜底 ✓（要确定性、不调 LLM）。
    """
    # 1. Requirement 实体 (若未建) —— 走实体域 ✓（不再经已退休的 conversation_os ✓）
    req = None
    if source_conv_id:
        req = create_requirement(root, title=title, description=description,
                                 source_conv_id=source_conv_id)
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
                     title: str = "", domain: str = "llm",
                     docs_dir: str | Path | None = None,
                     project_id: str = "") -> dict[str, Any]:
    """把 LLM 分解出的【树 dict】物化成 task 实体（方案 A）。

    为什么: LLM 分解器产出的是 nodes/leaves 结构（用于 PLAN），
    而 CLI/编排/证据链都按 task 实体（parent_id/children）走 →
    必须在同一处把它落成实体，否则两套模型永远对不上。

    ★ project_id（2026-09-15 加）:
        此前建 task 时**不传 project_id** ⇒ 实体没有项目归属 ⇒
        `factory progress`（按项目聚合）看不见计划环, 而任务级视图 (os_core_work
        按 `r["project_id"] == project_id` 过滤) 也筛不到。
        与会话/PRD 同一病因: **数据在, 关联缺**。此处补上归属 ✓
        （只写字段, 不改存储位置 —— 全局实体库 + project_id 过滤是既有读法。）

    返回与 decompose() 同构的 tree 记录（task_tree_id/title/subtasks/count），
    因此 tasktree list/status/progress 无需改动即可看到它 ✓
    """
    nodes = tree.get("nodes") or []
    if not nodes:
        raise ValueError("materialize_tree: 空树（LLM 未产出节点）")
    root_title = (title or tree.get("goal") or "任务")[:120]
    root_task = create_entity("task", created_by="system", project_id=project_id)
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
        e = create_entity("task", created_by="system", parent_id=parent_id,
                          project_id=project_id)
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
    # ★ 明文规格产物: 任务清单 tasks.md（人可读/可评审/可 diff ✓ 审批门的对象 ✓）
    try:
        # ★ docs_dir: 让清单落进【项目目录】(Founder: 产出文档该有归宿 ✓)；
        #   未指定则维持原行为（数据根 task_trees/）✓
        md_dir = Path(docs_dir) if docs_dir else (Path(root) / "task_trees")
        md_dir.mkdir(parents=True, exist_ok=True)
        md_path = md_dir / f"{root_task['id']}.md"
        md_path.write_text(render_tasks_md(root, tree), encoding="utf-8")
        record["tasks_md"] = str(md_path)
    except Exception as exc:  # noqa: BLE001 — 渲染失败不影响物化（但要可见）
        import sys as _sys
        print(f"[task_tree] tasks.md 渲染失败: {exc}", file=_sys.stderr)

    return record


def render_tasks_md(root: Path | str, tree: dict[str, Any]) -> str:
    """把任务树渲染成【明文任务清单 tasks.md】（人可读、可评审、可 diff）。

    为什么（Founder 问"该具备它们的哪些能力"→ 判 T2 应该有）:
      我们的治理承诺是"可审计、可人审"，但产物只有 JSON/实体 ✗ ——
      明文 markdown 才能评审/diff/给人看，也是审批门的对象 ✓
      （对标 github/spec-kit 136k★ 的核心做法: spec.md / plan.md / tasks.md）
    """
    from datetime import datetime, timezone

    nodes = [n for n in (tree.get("nodes") or []) if isinstance(n, dict)]
    leaves = [n for n in nodes if n.get("kind") == "task"]
    by_id = {str(n.get("id")): n for n in nodes}
    title = str(tree.get("goal") or tree.get("title") or "任务清单")

    def label(nid: str) -> str:
        n = by_id.get(nid) or {}
        return str(n.get("title") or nid)[:60]

    # 角色/技能分布（一眼看出"要哪些能力"—— 编排的输入摘要）
    roles: dict[str, int] = {}
    skills: dict[str, int] = {}
    for n in leaves:
        r = str(n.get("required_role") or "").strip()
        if r:
            roles[r] = roles.get(r, 0) + 1
        for sk in str(n.get("required_skill") or "").split("、"):
            sk = sk.strip()
            if sk:
                skills[sk] = skills.get(sk, 0) + 1

    lines = [
        f"# 任务清单 · {title}",
        "",
        f"> 来源: {tree.get('decomposer', 'llm')} · tree_id `{tree.get('tree_id', '')}`"
        f" · 生成 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
    ]
    flags = []
    if tree.get("truncated"):
        flags.append("发生过截断/断环")
    if tree.get("degraded"):
        flags.append("LLM 降级")
    if flags:
        lines.append(f"> ⚠ {' / '.join(flags)}")
    lines += [
        "",
        "## 概览",
        f"- 节点 {len(nodes)} 个（叶子任务 {len(leaves)} 个）"
        f" · 依赖边 {sum(len(n.get('depends_on') or []) for n in leaves)} 条",
        f"- 角色需求: {' · '.join(f'{k}×{v}' for k, v in sorted(roles.items())) or '（未标注）'}",
        f"- 技能需求: {' · '.join(f'{k}×{v}' for k, v in sorted(skills.items())[:12]) or '（未标注）'}",
        "",
        "## 任务（叶子 = 可执行单元）",
    ]
    for i, n in enumerate(leaves, 1):
        role = str(n.get("required_role") or "").strip()
        skill = str(n.get("required_skill") or "").strip()
        meta = " · ".join(x for x in (f"role={role}" if role else "",
                                      f"skill={skill}" if skill else "") if x)
        lines.append(f"- [ ] **T{i}** {str(n.get('title') or '')[:120]}"
                     + (f"  `{meta}`" if meta else ""))
        deps = [label(d) for d in (n.get("depends_on") or [])]
        lines.append(f"      - 依赖: {'、'.join(deps) if deps else '无（可立即开始）'}")
        if n.get("expected_files"):
            lines.append("      - 产出: " + "、".join(
                f"`{x}`" for x in list(n["expected_files"])[:8]))
        if n.get("change_type"):
            lines.append(f"      - 变更类型: {n['change_type']}")

    lines += ["", "## 层级结构"]
    tops = [n for n in nodes if not n.get("parent_id")]
    for top in tops:
        _walk(top, nodes, lines, 0)
    return "\n".join(lines) + "\n"


def _walk(node: dict[str, Any], nodes: list[dict[str, Any]], out: list[str],
          depth: int) -> None:
    """递归渲染层级（缩进树）。"""
    mark = "▸" if node.get("kind") == "domain" else "•"
    out.append("  " * depth + f"{mark} {str(node.get('title') or '')[:100]}")
    kids = [n for n in nodes if n.get("parent_id") == node.get("id")]
    for k in kids:
        _walk(k, nodes, out, depth + 1)
