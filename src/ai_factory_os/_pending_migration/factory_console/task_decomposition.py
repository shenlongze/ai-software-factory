"""src/legacy/factory-console/task_decomposition.py — Multi-level Task Tree 域 (S1 第 2 刀, canonical)。

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
    """任务树文件路径: 优先【项目目录】(projects/<P>/tasks/) ✓ → 回落全局 task_trees/ ✓。

    ★ Founder 铁律: 属于项目的文件必须在项目目录下 ✓。
    读优先 + 写回落: 新树的写入方不知道项目 ✗ → 由调用方在生成计划后搬迁 ✓
    （与会话同一模式: move_tree_to_project ✓）。
    """
    base = Path(root)
    for f in base.glob(f"projects/*/tasks/{plan_id}.json"):
        if f.is_file():
            return f
    return _tree_dir(root) / f"{plan_id}.json"


def move_tree_to_project(root: str | Path, plan_id: str,
                         project_id: str) -> bool:
    """把任务树文件搬进 projects/<P-id>/tasks/（幂等 + 原子 + 失败安全 ✓）。"""
    if not project_id:
        return False
    src = _tree_dir(root) / f"{plan_id}.json"
    dst = Path(root) / "projects" / project_id / "tasks" / f"{plan_id}.json"
    if not src.is_file() or dst.exists():
        return False
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        import os as _os
        _os.replace(src, dst)
        # 同名 .md（清单）一并跟着走 ✓
        src_md = src.with_suffix(".md")
        if src_md.is_file():
            _os.replace(src_md, dst.with_suffix(".md"))
        return True
    except OSError as exc:
        import sys as _s
        print(f"[project] 任务树迁移失败: {exc}", file=_s.stderr)
        return False


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
            "你是 AI Factory OS 的任务分解器。\n"
            "步骤: ① 先做真实需求分析（要交付什么、有哪些模块与依赖）\n"
            "      ② 再按【阶段 → 模块 → 任务 → 子任务】逐级拆分\n"
            "      ③ 只在确有必要时继续往下拆（不要把每层都硬拆平）\n"
            "层数不限，按需求实际复杂度决定。只输出 JSON:\n"
            '{"nodes":[{"title":"...","kind":"domain|task",'
            '"change_type":"NEW_FILE|MODIFY","expected_files":[...],'
            '"required_role":"前端|后端|测试|架构或空",'
            '"required_skill":"具体技能点或空",'
            '"depends_on":["必须先完成的其它任务的 title"],'
            '"children":[{与父节点同构, 可再嵌 children, 不限层数}]}]}  '
            '"（也可写成 {"nodes":[{...}]} 一行，但必须闭合完整）\\n'
            "（children 可递归嵌套；无 children 的节点即叶子任务）\n\n"
            f"产品: {goal}\n功能需求: {feats}"
        )
        # ★ 重试（实测: 单次约 1/3 成功率 —— LLM 返回非法 JSON 很常见 ✗，
        #   不重试就等于"分解能力只有三分之一可用"✗）
        tree = None
        attempts = _DECOMPOSE_ATTEMPTS
        for attempt in range(1, attempts + 1):
            raw = None
            try:
                raw = llm_fn(prompt)
            except Exception:  # noqa: BLE001
                raw = None
            tree = _parse_llm_tree(raw, prd)
            if tree is not None:
                tree["attempts"] = attempt
                break
        if tree is None:
            # ★ 不再回落模板（Founder: 分解一律走 LLM，宁可不拆也不假装拆）
            return {
                "prd_id": prd.get("id", ""), "plan_id": prd.get("plan_id", ""),
                "goal": str(goal)[:200], "tree_id": "", "nodes": [], "leaves": [],
                "edges": [], "critical_path": [], "parallel_groups": [],
                "degraded": True, "decomposer": "llm-failed",
                "attempts": attempts,
                "error": f"LLM 分解失败（重试 {attempts} 次仍未得到合法 JSON；未回落模板）",
            }
        tree["decomposer"] = "llm"
        tree["degraded"] = False
        return tree

    return _decompose


#: 递归分解护栏（Founder 要求"层数不限"，但 LLM 输出必须有界 ——
#: 无界递归会拖垮执行；深度/节点数异常往往就是模型跑偏的信号）。
#: LLM 分解重试次数（实测单次成功率低 —— 非法 JSON 很常见）
_DECOMPOSE_ATTEMPTS = 3

MAX_TREE_DEPTH = 32
MAX_TREE_NODES = 500
_TRUNCATED = [False]


def _break_cycles(nodes: list[dict[str, Any]]) -> int:
    """断掉依赖环（DFS 找回边），返回断开的边数。

    LLM 给出的 depends_on 可能成环（A→B→A）→ 编排会死锁 ✗。
    这里做最小处理: 后访问到的回边直接摘除，并在结果里标 truncated（诚实告知）。
    """
    by_id = {n["id"]: n for n in nodes if n.get("id")}
    state: dict[str, int] = {}          # 0=未访问 1=在栈 2=完成
    broken = 0

    def _dfs(nid: str) -> None:
        nonlocal broken
        state[nid] = 1
        node = by_id.get(nid)
        for dep in list((node or {}).get("depends_on", [])):
            st = state.get(dep, 0)
            if st == 1:                 # 回边 → 断
                (node or {})["depends_on"] = [d for d in node["depends_on"] if d != dep]
                broken += 1
            elif st == 0 and dep in by_id:
                _dfs(dep)
        state[nid] = 2

    for nid in list(by_id):
        if state.get(nid, 0) == 0:
            _dfs(nid)
    return broken


def _build_nested_nodes(items: list[Any], *, tree_id: str, prd_ref: str,
                        parent_id: str, depth: int) -> list[dict[str, Any]]:
    """把 LLM 的嵌套 nodes 递归物化为 tree 节点（parent_id/children 层级）。

    护栏: 深度超 MAX_TREE_DEPTH 或节点数超 MAX_TREE_NODES → 截断并置 _TRUNCATED。
    有 children 的节点 = domain（容器）；无 = task（叶子，可执行）。
    """
    out: list[dict[str, Any]] = []
    if depth > MAX_TREE_DEPTH:
        _TRUNCATED[0] = True
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        if len(out) >= MAX_TREE_NODES:
            _TRUNCATED[0] = True
            break
        title = str(it.get("title") or "").strip()[:200]
        if not title:
            continue
        children = it.get("children") or []
        has_kids = isinstance(children, list) and bool(children)
        ct = str(it.get("change_type") or "")
        ct = ct if ct in CHANGE_TYPES else ("MODIFY" if has_kids else "NEW_FILE")
        exp = [str(x) for x in (it.get("expected_files") or [])][:20]
        kind = "domain" if has_kids else "task"
        node = _new_node(tree_id, kind=kind, title=title, parent_id=parent_id,
                         prd_ref=prd_ref,
                         change_type=ct if kind == "task" else "",
                         expected_files=exp if kind == "task" else [],
                         scope=str(it.get("kind") or "feature"))
        node["has_children"] = has_kids
        # ★ 刀A: 任务带【能力需求】+【依赖声明】—— 编排（能力解析与调度）的输入
        node["required_skill"] = str(it.get("required_skill") or "").strip()[:60]
        node["required_role"] = str(it.get("required_role") or "").strip()[:40]
        node["depends_on_titles"] = [str(x) for x in (it.get("depends_on") or [])][:20]
        out.append(node)
        if has_kids:
            out.extend(_build_nested_nodes(children, tree_id=tree_id, prd_ref=prd_ref,
                                           parent_id=node["id"], depth=depth + 1))
    return out


def _parse_llm_tree(raw: str | None, prd: dict[str, Any]) -> dict[str, Any] | None:
    """解析 LLM JSON; 非法 → None (调用方兜底)。"""
    if not raw:
        return None
    try:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        data = json.loads(m.group(0))
        # ★ 两种 schema 都接受（新: nodes 递归嵌套 / 旧: domains+tasks 两层）
        node_list_pre = data.get("nodes")
        has_nodes = isinstance(node_list_pre, list) and bool(node_list_pre)
        domains = data.get("domains")
        if not has_nodes and (not isinstance(domains, list) or not domains):
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

        # ★ 新 schema（递归嵌套）: {"nodes":[{title,kind,change_type,expected_files,children:[…]}]}
        #   支持任意层数（Founder: 层数不限）。护栏见 MAX_TREE_DEPTH / MAX_TREE_NODES。
        node_list = data.get("nodes")
        if isinstance(node_list, list) and node_list:
            built = _build_nested_nodes(node_list, tree_id=tree_id,
                                        prd_ref=prd.get("id", ""),
                                        parent_id=project["id"], depth=0)
            if not built:
                return None
            nodes.extend(built)
            # 叶子按【结构】判定（不是按 has_children 标记）:
            # 截断后纯链式树每个节点都"有 children"却全被砍掉 →
            # 按标记判定会得出"零叶子"✗ 而误判为 LLM 失败
            child_ids = {n["parent_id"] for n in built if n.get("parent_id")}
            leaves.extend([n["id"] for n in built if n["id"] not in child_ids])
            for n in nodes:
                n.pop("has_children", None)
            # ★ 依赖解析: LLM 用 title 表达依赖 → 映射为 id
            #   校验: 指向不存在的 → 丢弃；指向自己 → 丢弃；成环 → 断环（诚实标注）
            _tmap = {n["title"]: n["id"] for n in nodes}
            for n in nodes:
                deps: list[str] = []
                for ttl in n.pop("depends_on_titles", []):
                    did = _tmap.get(str(ttl).strip())
                    if did and did != n["id"] and did not in deps:
                        deps.append(did)
                if deps:
                    n["depends_on"] = deps
            _broken = _break_cycles(nodes)
            if _broken:
                _TRUNCATED[0] = True
            if not leaves:
                return None
            vleaf = _new_node(tree_id, kind="task", title="验证与交付",
                              parent_id=project["id"], prd_ref=prd.get("id", ""),
                              change_type="MODIFY", expected_files=[],
                              depends_on=list(leaves), scope="verify")
            nodes.append(vleaf)
            leaves.append(vleaf["id"])
            edges = [{"from": n["parent_id"], "to": n["id"]}
                     for n in nodes if n.get("parent_id")]
            return {
                "plan_id": prd.get("plan_id", ""), "prd_id": prd.get("id", ""),
                "goal": goal, "tree_id": tree_id, "nodes": nodes,
                "leaves": leaves, "edges": edges,
                "critical_path": [n["id"] for n in nodes if n["kind"] == "task"],
                "parallel_groups": [], "degraded": False,
                "truncated": _TRUNCATED[0],
            }
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
