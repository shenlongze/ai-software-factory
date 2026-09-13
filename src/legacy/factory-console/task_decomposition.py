"""factory-console/task_decomposition.py — Multi-level Task Tree 域 (S1 第 2 刀, canonical)。

把 approved PRD → 多级任务树 (Project → Domain → Leaf Task) 的 canonical 域。

边界 (AI Factory OS 收敛原则 / CT 断层 F2):
- 本域是**计划层组织结构** (Task Tree); 每叶 = 一个最小可执行工作单元,
  执行语义由 production_run 图编排 + node_runtime.execute_node_run 承担。
- 数据落盘 <root>/task_trees/{plan_id}.json (与 conversations/product_truth 分域,
  不写 legacy projects/<slug>/ 存储, 不造平行 Truth)。
- 驱动: 生产可接 LLM decomposer (注入协议, 失败/非法 → 确定性模板兜底 + degraded);
  测试/无注入 → 确定性结构模板 (可复现)。
- 叶节点携带 change_type(NEW_FILE/MODIFY) + expected_files + depends_on, 供
  执行层做 NO_OP/完成态判定 (防 2/7 复发: 重叠/已完成任务不得伪装成失败)。
"""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

#: 树节点 kind 白名单
NODE_KINDS = ("project", "domain", "module", "capability", "task")
#: 叶任务 change_type 白名单
CHANGE_TYPES = ("NEW_FILE", "MODIFY")
#: 模板功能域 (PRD functional_requirements 按语义归类; 未知 → 通用交付域)
_TEMPLATE_DOMAINS = ("setup", "feature", "constraint", "decision", "verify", "delivery")

_lock = threading.RLock()


# ------------------------------------------------------------------ 存储


def _tree_dir(root: str | Path) -> Path:
    return Path(root) / "task_trees"


def _tree_file(root: str | Path, plan_id: str) -> Path:
    return _tree_dir(root) / f"{plan_id}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_task_tree(root: str | Path, plan_id: str,
                   tree: dict[str, Any]) -> dict[str, Any]:
    """原子写 <root>/task_trees/{plan_id}.json。"""
    p = _tree_file(root, plan_id)
    with _lock:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(tree, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, p)
    return tree


def load_task_tree(root: str | Path, plan_id: str) -> dict[str, Any] | None:
    """读树; 不存在 → None (不抛)。"""
    p = _tree_file(root, plan_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ------------------------------------------------------------------ 结构


def _new_node(tree_id: str, *, kind: str, title: str, parent_id: str = "",
              prd_ref: str = "", change_type: str = "",
              expected_files: list[str] | None = None,
              depends_on: list[str] | None = None,
              scope: str = "") -> dict[str, Any]:
    node = {
        "id": f"{tree_id}-{kind[:1]}-{uuid.uuid4().hex[:8]}",
        "kind": kind,
        "title": str(title)[:200],
        "parent_id": parent_id,
        "prd_ref": prd_ref,
        "change_type": change_type if change_type in CHANGE_TYPES else "",
        "expected_files": list(expected_files or []),
        "depends_on": list(depends_on or []),
        "scope": str(scope)[:500],
    }
    return node


# ------------------------------------------------------------------ 确定性模板

_FEATURE_LABEL = re.compile(r"实现功能:\s*(.*)|\b(.+)")


def _template_decompose(prd: dict[str, Any]) -> dict[str, Any]:
    """确定性多级模板: Project → 功能/交付域 → 叶 (每功能条款一叶)。

    空功能条款 → 从 goal 兜底 ≥1 叶 (诚实, 不产空树)。
    """
    tree_id = uuid.uuid4().hex[:6]
    content = prd.get("content", {}) or {}
    if not isinstance(content, dict):
        content = {}
    overview = content.get("overview", {}) or {}
    goal = str(overview.get("problem") or overview.get("name")
               or prd.get("goal") or "构建目标产品")[:120]
    title = str(overview.get("name") or goal)[:120]

    nodes: list[dict[str, Any]] = []
    leaves: list[str] = []

    project = _new_node(tree_id, kind="project", title=title or goal,
                        prd_ref=prd.get("id", ""), scope="project")
    nodes.append(project)

    # 功能域
    feats = content.get("functional_requirements", []) or []
    if feats:
        fdom = _new_node(tree_id, kind="domain",
                         title="功能实现",
                         parent_id=project["id"],
                         prd_ref=prd.get("id", ""),
                         scope="functional")
        nodes.append(fdom)
        for i, raw in enumerate(feats):
            text = re.sub(r"^实现功能:\s*", "", str(raw)).strip() or f"功能 {i + 1}"
            leaf = _new_node(tree_id, kind="task",
                             title=f"实现功能: {text}",
                             parent_id=fdom["id"],
                             prd_ref=prd.get("id", ""),
                             change_type="NEW_FILE",
                             expected_files=[],
                             depends_on=[],
                             scope="feature")
            nodes.append(leaf)
            leaves.append(leaf["id"])
    else:
        # 空功能条款 → goal 兜底
        fdom = _new_node(tree_id, kind="domain", title="交付",
                         parent_id=project["id"],
                         prd_ref=prd.get("id", ""), scope="delivery")
        nodes.append(fdom)
        leaf = _new_node(tree_id, kind="task", title=f"实现: {goal}",
                         parent_id=fdom["id"],
                         prd_ref=prd.get("id", ""),
                         change_type="NEW_FILE", expected_files=[],
                         scope="goal-fallback")
        nodes.append(leaf)
        leaves.append(leaf["id"])

    # 验证交付域 (depends_on 全部功能叶)
    vdom = _new_node(tree_id, kind="domain", title="验证与交付",
                     parent_id=project["id"],
                     prd_ref=prd.get("id", ""), scope="verify")
    nodes.append(vdom)
    vleaf = _new_node(tree_id, kind="task", title="验证与交付",
                      parent_id=vdom["id"],
                      prd_ref=prd.get("id", ""),
                      change_type="MODIFY",
                      expected_files=[],
                      depends_on=list(leaves),
                      scope="verify")
    nodes.append(vleaf)
    leaves.append(vleaf["id"])

    edges = [{"from": n["parent_id"], "to": n["id"]} for n in nodes
             if n.get("parent_id")]
    return {
        "plan_id": prd.get("plan_id", ""),
        "prd_id": prd.get("id", ""),
        "goal": goal,
        "tree_id": tree_id,
        "nodes": nodes,
        "leaves": leaves,
        "edges": edges,
        "critical_path": [n["id"] for n in nodes if n["kind"] == "task"],
        "parallel_groups": [],
        "degraded": False,
        "decomposer": "template",
        "created_at": _now_iso(),
    }


# ------------------------------------------------------------------ LLM 注入


def build_llm_decomposer(
    llm_fn: Callable[[str], str | None] | None = None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """LLM decomposer 工厂: 注入 console_sessions.llm_raw (或测试 llm_fn)。

    失败/非法 → 模板兜底 + degraded=True (诚实降级, 不伪造 LLM 结果)。
    """
    if llm_fn is None:
        from factory_console.console_sessions import llm_raw as _raw
        llm_fn = _raw

    def _decompose(prd: dict[str, Any]) -> dict[str, Any]:
        content = prd.get("content", {}) or {}
        overview = content.get("overview", {}) if isinstance(content, dict) else {}
        goal = str(overview.get("problem")
                   or prd.get("goal") or "")[:300]
        feats = (content.get("functional_requirements", [])
                 if isinstance(content, dict) else []) or []
        prompt = (
            "你是 AI Factory OS 的任务分解器。把下面产品拆成多级任务树"
            " (Project→Domain→Leaf)。只输出 JSON:\n"
            '{"domains":[{"title":"...","tasks":[{"title":"...",'
            '"change_type":"NEW_FILE|MODIFY","expected_files":[...]}]}]}\n\n'
            f"产品: {goal}\n功能需求: {feats}"
        )
        raw = None
        try:
            raw = llm_fn(prompt)
        except Exception:  # noqa: BLE001
            raw = None
        tree = _parse_llm_tree(raw, prd)
        if tree is None:
            base = _template_decompose(prd)
            base["degraded"] = True
            base["decomposer"] = "template-after-llm-failure"
            return base
        tree["decomposer"] = "llm"
        tree["degraded"] = False
        return tree

    return _decompose


def _parse_llm_tree(raw: str | None, prd: dict[str, Any]) -> dict[str, Any] | None:
    """解析 LLM JSON; 非法 → None (调用方兜底)。"""
    if not raw:
        return None
    try:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        data = json.loads(m.group(0))
        domains = data.get("domains")
        if not isinstance(domains, list) or not domains:
            return None
        tree_id = uuid.uuid4().hex[:6]
        content = prd.get("content", {}) or {}
        overview = content.get("overview", {}) if isinstance(content, dict) else {}
        goal = str(overview.get("problem")
                   or prd.get("goal") or "构建目标产品")[:120]
        nodes: list[dict[str, Any]] = []
        leaves: list[str] = []
        project = _new_node(tree_id, kind="project",
                            title=str(overview.get("name") or goal)[:120],
                            prd_ref=prd.get("id", ""), scope="project")
        nodes.append(project)
        for d in domains:
            dtitle = str(d.get("title") or "交付域")[:120]
            dom = _new_node(tree_id, kind="domain", title=dtitle,
                            parent_id=project["id"],
                            prd_ref=prd.get("id", ""),
                            scope="domain")
            nodes.append(dom)
            tasks = d.get("tasks") or []
            if not tasks:
                tasks = [{"title": f"实现: {dtitle}"}]
            for t in tasks:
                ct = str(t.get("change_type") or "NEW_FILE")
                ct = ct if ct in CHANGE_TYPES else "NEW_FILE"
                exp = [str(x) for x in (t.get("expected_files") or [])][:20]
                leaf = _new_node(tree_id, kind="task",
                                 title=str(t.get("title") or "任务")[:200],
                                 parent_id=dom["id"],
                                 prd_ref=prd.get("id", ""),
                                 change_type=ct, expected_files=exp,
                                 scope="feature")
                nodes.append(leaf)
                leaves.append(leaf["id"])
        # 验证交付叶 (depends_on 全部功能叶) — 与模板同构
        vdom = _new_node(tree_id, kind="domain", title="验证与交付",
                         parent_id=project["id"],
                         prd_ref=prd.get("id", ""), scope="verify")
        nodes.append(vdom)
        vleaf = _new_node(tree_id, kind="task", title="验证与交付",
                          parent_id=vdom["id"], prd_ref=prd.get("id", ""),
                          change_type="MODIFY", expected_files=[],
                          depends_on=list(leaves), scope="verify")
        nodes.append(vleaf)
        leaves.append(vleaf["id"])
        edges = [{"from": n["parent_id"], "to": n["id"]} for n in nodes
                 if n.get("parent_id")]
        return {
            "plan_id": prd.get("plan_id", ""), "prd_id": prd.get("id", ""),
            "goal": goal, "tree_id": tree_id, "nodes": nodes,
            "leaves": leaves, "edges": edges,
            "critical_path": [n["id"] for n in nodes if n["kind"] == "task"],
            "parallel_groups": [], "degraded": False,
            "created_at": _now_iso(),
        }
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


# ------------------------------------------------------------------ decompose_prd (公开入口)


def decompose_prd(
    prd: dict[str, Any],
    *,
    interpreter: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """PRD → 多级树。interpreter 注入 (LLM) → 模板兜底 (degraded 诚实)。"""
    if interpreter is not None:
        try:
            tree = interpreter(prd)
            if tree and isinstance(tree, dict) and tree.get("nodes"):
                return tree
        except Exception:  # noqa: BLE001 — 任何失败 → 模板兜底
            pass
    tree = _template_decompose(prd)
    tree["degraded"] = bool(interpreter is not None)
    return tree


# ------------------------------------------------------------------ 查询/导出


def tree_leaves(tree: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(n) for n in (tree.get("nodes") or []) if n.get("kind") == "task"]


def tree_summary(tree: dict[str, Any] | None) -> dict[str, Any]:
    if tree is None:
        return {"exists": False}
    leaves = tree_leaves(tree)
    return {
        "exists": True,
        "plan_id": tree.get("plan_id", ""),
        "goal": tree.get("goal", ""),
        "depth": 3 if any(n.get("kind") == "domain" for n in tree.get("nodes", [])) else 2,
        "node_count": len(tree.get("nodes", [])),
        "leaf_count": len(leaves),
        "domains": sorted({str(n.get("title"))[:60] for n in tree.get("nodes", [])
                           if n.get("kind") == "domain"}),
        "leaves": [
            {"id": n["id"], "title": n["title"], "change_type": n.get("change_type", ""),
             "expected_files": n.get("expected_files", []),
             "depends_on": n.get("depends_on", [])}
            for n in leaves
        ],
        "critical_path": tree.get("critical_path", []),
        "parallel_groups": tree.get("parallel_groups", []),
        "degraded": bool(tree.get("degraded")),
        "decomposer": tree.get("decomposer", ""),
    }


def tree_to_plan(tree: dict[str, Any]) -> tuple[list[dict[str, Any]],
                                                list[str]]:
    """叶摘要 (供 PLAN.tasks) + 拓扑序 (order, 依赖先)。

    拓扑: DFS post-order (depends_on 先于依赖者)。
    """
    leaves = tree_leaves(tree)
    by_id = {n["id"]: n for n in leaves}
    visited: set[str] = set()
    order: list[str] = []

    def _visit(node_id: str) -> None:
        if node_id in visited:
            return
        visited.add(node_id)
        node = by_id.get(node_id)
        for dep in (node or {}).get("depends_on", []):
            if dep in by_id:
                _visit(dep)
        order.append(node_id)

    for n in leaves:
        _visit(n["id"])

    summaries = []
    for lid in order:
        n = by_id[lid]
        summaries.append({
            "id": lid,
            "title": n["title"],
            "kind": n["kind"],
            "change_type": n.get("change_type", ""),
            "expected_files": n.get("expected_files", []),
            "depends_on": n.get("depends_on", []),
            "prd_ref": n.get("prd_ref", ""),
        })
    return summaries, order


__all__ = [
    "NODE_KINDS", "CHANGE_TYPES",
    "save_task_tree", "load_task_tree",
    "build_llm_decomposer", "decompose_prd",
    "tree_leaves", "tree_summary", "tree_to_plan",
]
