"""services.work.decomposition — 任务拆解（产品环 ④→⑤ 的衔接层）。

★ 2026-09-15 新增。服务域 `work` · 域 `decomposition`（对齐 docs/design/domain-alignment.md:69）。

【为什么是"衔接"而不是"再拆一次"】
 环④ 架构设计产出的 Design Artifact 里，`task_breakdown` 已经是**模块级的任务种子**
 （LLM 在架构阶段拆过一层）。若在本环再跑一次 LLM 分解，同一需求会被拆两遍
 ⇒ 必然出现"架构说 11 个模块、任务树说 8 个"的不一致。
 所以本域做的是【把种子物化成多级树 + 补齐执行字段 + 加边界纪律】，不重跑 LLM。

【对齐 Founder 设计（原文出处）】
 · 每任务 = 做什么 / 改哪些文件 / 验收断言 / 依赖 / 归属
   （docs/sprint10/S10-088-hermes-next-sprint-prompt.md:41）
 · 节点模型 = Project → Domain → Leaf 多级 + change_type + expected_files + depends_on
   （task_decomposition 的 canonical 定义）
 · 「任务拆解自动生成」（docs/sprint7/sprint7-backlog.md:47）
 · 产出**候选** → **人工确认** → 才进执行（docs/archive/legacy-docs/lifecycle-model.md:88）
 · 「属于项目的文件必须在项目目录下」（Founder 铁律）

【★ 与历史 4 套的关系（docs/audits/2026-09-08-full-body-ct.md "家族 A"）】
  本模块是 canonical 的**新地基实现**，边界收紧为一句:
    · 它是【计划层组织结构】；执行语义由 production_run + node_runtime 承担（不越界）
    · 借 decomposer 的**边界纪律**（depth / leaves / cycle），但不搬它的旧存储
    · 不新造第 5 套存储 —— 沿用 canonical 的 `task_trees/{plan_id}.json`
      （且遵守项目文件在项目目录的铁律）

【存储】projects/<project_id>/tasks/{plan_id}.json 优先（项目内）
        回落 <root>/task_trees/{plan_id}.json（进度视图 progress_view 读这里）
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "decompose_from_design", "load_tree", "list_trees", "confirm_tree",
    "tree_summary", "tree_leaves", "topological_order",
    "parallel_groups", "file_conflicts",
    "DECOMPOSE_LIMITS",
]

_lock = threading.RLock()

#: 节点 kind 白名单（同 canonical）
NODE_KINDS = ("project", "domain", "module", "capability", "task")
#: 叶任务变更类型
CHANGE_TYPES = ("NEW_FILE", "MODIFY")

#: ★ 边界纪律（借老区 decomposer 的智慧: depth≤5 / tasks≤64 / 环检测）
DECOMPOSE_LIMITS = {
    "max_depth": 5,        # 树深上限
    "max_leaves": 64,      # 叶子数上限（超限 → 需求该重新审视, 不硬拆）
    "max_title": 200,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _tree_file(root: Path | str, plan_id: str, project_id: str = "") -> Path:
    """树文件: 优先项目目录（Founder 铁律）→ 回落全局 task_trees/。"""
    base = Path(root)
    if project_id:
        d = base / "projects" / project_id / "tasks"
        if d.parent.is_dir():          # 项目存在 ⇒ 放项目内
            return d / f"{plan_id}.json"
    return base / "task_trees" / f"{plan_id}.json"


def _read(root: Path | str, plan_id: str, project_id: str = "") -> dict[str, Any] | None:
    """读树: 指定项目 → 项目内; 否则【全局搜】（projects/*/tasks/ + task_trees/）。

    全局搜索是必要的 —— 调用方（如 `tasktree show PLAN-x`）通常只有 plan_id,
    而树按 Founder 铁律落在 projects/<P>/tasks/ 下。
    """
    base = Path(root)
    cands: list[Path] = []
    if project_id:
        cands.append(base / "projects" / project_id / "tasks" / f"{plan_id}.json")
    cands.append(base / "task_trees" / f"{plan_id}.json")
    pj = base / "projects"
    if pj.is_dir():
        cands += [d / "tasks" / f"{plan_id}.json" for d in pj.iterdir() if d.is_dir()]
    for p in cands:
        if not p.is_file():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 损坏 → 跳过（继续找下一个）
            continue
        if isinstance(d, dict) and d.get("plan_id") == plan_id:
            return d
    return None


def _save(root: Path | str, plan_id: str, tree: dict[str, Any], project_id: str = "") -> Path:
    p = _tree_file(root, plan_id, project_id)
    with _lock:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, p)
    return p


# ------------------------------------------------------------------ 角色/文件 推导

#: 模块名 → 承担角色（诚实规则, 不是猜测: 按【词边界】判定, 防 "ui" 命中 "rout/e" 之类子串）
_ROLE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(test|tests|testing|spec|verify|verification|check)\b"), "tester"),
    (re.compile(r"\b(ui|ux|render|rendering|view|views|template|style|frontend|wireframe)\b"), "ui_designer"),
    (re.compile(r"\b(doc|docs|readme|guide)\b"), "technical_writer"),
    (re.compile(r"\b(infra|deploy|docker|ci|build|scaffold|module)\b"), "devops"),
]
_DEFAULT_ROLE = "unassigned"   # ★ 不猜: 种子里没给就诚实留空


#: 落地型模块的特征词（脚手架 / 初始化 / 配置 —— 其余都依赖它们先就位）
_SETTLING_RE = re.compile(
    r"\b(scaffold|init|bootstrap|setup|config|skeleton|module|目录|骨架|初始化|脚手架)\b"
)


def _is_settling(module: str, text: str) -> bool:
    """是不是"落地型"模块（脚手架/初始化/配置）—— 它们是其它模块的先决。

    判据 = 词边界（不猜语义）。不是落地型 → 依赖已有落地域（若有）。
    """
    hay = re.sub(r"[-_/]", " ", f"{module} {text}").lower()
    return bool(_SETTLING_RE.search(hay))


def _role_hint(module: str, text: str) -> str:
    """角色**提示**（不是事实）—— 关键字推导不可靠（"render" 可能是 CLI 渲染而非 UI），
    所以只作 hint 供执行层参考；`required_role` 一律诚实留 `unassigned` 除非种子显式给。
    """
    hay = re.sub(r"[-_/]", " ", f"{module}").lower()      # 只看模块名, 不看描述（描述噪声大）
    for pat, role in _ROLE_RULES:
        if pat.search(hay):
            return role
    return ""


#: 文件扩展名白名单 —— ★ 按长度倒序拼进正则（防 .js 抢先匹配 .json）
_FILE_EXTS = ("json", "yaml", "yml", "toml", "tsx", "sql", "jsx", "go", "py", "ts", "js", "rs", "java", "kt", "md")
_FILE_RE = re.compile(r"[\w./-]+\.(?:" + "|".join(sorted(_FILE_EXTS, key=len, reverse=True)) + r")\b", re.I)


def _files_for(module: str, text: str, stack: str = "") -> list[str]:
    """推 expected_files: 从模块名与描述里抽路径样式的 token（诚实: 抽不到就留空）。"""
    found: list[str] = []
    for m in _FILE_RE.finditer(f"{module} {text}"):
        tok = m.group(0).lstrip(".") if m.group(0).startswith("./") else m.group(0)
        if tok not in found:
            found.append(tok)
    for m in re.finditer(r"\b(?:cmd|internal|src|app|lib|pkg|services?)/[\w./-]+", text):
        tok = m.group(0).rstrip(".,;")
        if tok not in found:
            found.append(tok)
    return found[:8]


# ------------------------------------------------------------------ 核心: 种子 → 多级树


class DecomposeLimitError(Exception):
    """超出拆解边界（depth/leaves）—— 响亮报错, 不静默硬拆。"""


def decompose_from_design(
    root: Path | str,
    *,
    project_id: str,
    design_metadata: dict[str, Any],
    plan_id: str = "",
    prd_ref: str = "",
    created_by: str = "decomposition",
) -> dict[str, Any]:
    """Design Artifact（含 task_breakdown 种子）→ 多级任务树（候选态）。

    种子形态（架构阶段产出）: [{"module": str, "task": str, "api_contract"?: str}, ...]

    产出结构（对齐 canonical, 并让 progress_view 可读）:
      {plan_id, project_id, status: "candidate", created_at, created_by, prd_ref,
       nodes: [{id, kind, title, parent_id, prd_ref, change_type, expected_files,
                depends_on, scope, required_role, acceptance}], limits: {...}}
    """
    seeds = design_metadata.get("task_breakdown") or []
    if not isinstance(seeds, list) or not seeds:
        raise ValueError("design 没有 task_breakdown 种子 —— 先跑 arch design（任务拆解需要架构产出作输入）")

    plan_id = plan_id or f"PLAN-{uuid.uuid4().hex[:10]}"
    tree_id = plan_id
    stack = str(design_metadata.get("technical_stack") or "")
    sysarch = design_metadata.get("system_architecture")
    stack_note = (json.dumps(sysarch, ensure_ascii=False)[:300] if sysarch else stack[:300])

    nodes: list[dict[str, Any]] = []

    def _node(kind: str, title: str, parent: str = "", **kw: Any) -> dict[str, Any]:
        return {
            "id": f"{tree_id}-{kind[:1]}-{uuid.uuid4().hex[:8]}",
            "kind": kind,
            "title": str(title)[: DECOMPOSE_LIMITS["max_title"]],
            "parent_id": parent,
            "prd_ref": prd_ref,
            "change_type": kw.get("change_type", "") if kw.get("change_type") in CHANGE_TYPES else "",
            "expected_files": list(kw.get("expected_files") or []),
            "depends_on": list(kw.get("depends_on") or []),
            "scope": str(kw.get("scope") or "")[:500],
            "required_role": kw.get("required_role") or _DEFAULT_ROLE,
            "role_hint": str(kw.get("role_hint") or ""),      # ★ 提示（非事实）
            "acceptance": str(kw.get("acceptance") or "")[:300],
        }

    # 根: 计划（Project 层）
    root_node = _node("project", f"计划 {plan_id}", scope=stack_note)
    nodes.append(root_node)

    # 中间层: 按种子出现顺序归组
    # ★ 2026-09-19 修（M3 并行调度）: 原实现把"种子出现顺序"当成"依赖顺序"，
    #   给每个叶子连了 prev_leaf_ids ⇒ 强制全串行（实测并行度=1 ✗）。
    #   顺序 ≠ 依赖 —— 依赖要按【真实先决关系】推导:
    #     · 每个叶子依赖【自己的 domain 节点】（层级归属, 不产生串行）
    #     · 跨 domain 只连【层次先决】: 落地型(脚手架/配置) → 其余; 底层域 → 上层域
    #     · 无真依赖 → **不连边** ⇒ 同层可并行 ✓
    #   （同层写同一文件的冲突不在依赖图里表达 —— 由 file_conflicts() 在执行前收缩边界）
    prev_leaf_ids: list[str] = []
    first_domain_ids: list[str] = []          # 最先落地的那些域（供跨域先决用）
    for idx, seed in enumerate(seeds, 1):
        if not isinstance(seed, dict):
            continue
        module = str(seed.get("module") or f"module-{idx}").strip()
        desc = str(seed.get("task") or "").strip()
        contract = str(seed.get("api_contract") or "").strip()

        dom = _node("domain", f"模块 {idx}: {module}", parent=root_node["id"], scope=desc[:300])
        # ★ 跨域先决: 仅当本模块属"落地/底层"之外, 且已有早于它的落地域时, 才连一条
        #   （不逐级链接 —— 那会退化成串行）
        dom["depends_on"] = list(first_domain_ids) if _is_settling(module, desc) is False else []
        if _is_settling(module, desc) and not first_domain_ids:
            first_domain_ids.append(dom["id"])
        nodes.append(dom)

        leaf = _node(
            "task", desc or module, parent=dom["id"],
            change_type="NEW_FILE",
            expected_files=_files_for(module, f"{desc} {contract}", stack),
            # 只依赖自己的域（层级归属）—— 不再链式依赖前一个叶
            depends_on=[dom["id"]],
            scope=contract[:300],
            required_role=_DEFAULT_ROLE,
            role_hint=_role_hint(module, desc),
            acceptance=contract or f"{module} 实现完成且可验证",
        )
        nodes.append(leaf)
        prev_leaf_ids.append(leaf["id"])

    leaves = [n for n in nodes if n["kind"] == "task"]
    # ── 边界纪律（超出 → 响亮拒绝, 不静默硬拆）
    if len(nodes) > DECOMPOSE_LIMITS["max_leaves"] * 3:
        raise DecomposeLimitError(
            f"节点数 {len(nodes)} 超出上限 —— 种子过大, 请先精简架构的 task_breakdown")
    if depth_of(nodes, root_node["id"]) > DECOMPOSE_LIMITS["max_depth"]:
        raise DecomposeLimitError(
            f"树深超过 {DECOMPOSE_LIMITS['max_depth']} —— 拆解层级过深")
    cycles = detect_cycles(nodes)
    if cycles:
        raise DecomposeLimitError(f"依赖存在环: {cycles[:3]}")

    tree = {
        "plan_id": plan_id,
        "project_id": project_id,
        "status": "candidate",            # ★ 候选 —— 需人工确认才进执行
        "created_at": _now_iso(),
        "created_by": created_by,
        "prd_ref": prd_ref,
        "design_ref": str(design_metadata.get("artifact_refs") or ""),
        "limits": dict(DECOMPOSE_LIMITS),
        "counts": {"nodes": len(nodes), "leaves": len(leaves)},
        "nodes": nodes,
    }
    tree["_saved_to"] = str(_save(root, plan_id, tree, project_id))
    return tree


def depth_of(nodes: list[dict[str, Any]], root_id: str) -> int:
    by_id = {n["id"]: n for n in nodes}
    best = 0
    for n in nodes:
        d = 0
        cur = n
        seen = set()
        while cur and cur.get("parent_id") and cur["parent_id"] in by_id and cur["id"] not in seen:
            seen.add(cur["id"])
            cur = by_id[cur["parent_id"]]
            d += 1
        best = max(best, d)
    return best


def detect_cycles(nodes: list[dict[str, Any]]) -> list[list[str]]:
    """依赖环检测（只报, 不改）。"""
    by_id = {n["id"]: n for n in nodes}
    cycles: list[list[str]] = []
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n["id"]: WHITE for n in nodes}

    def visit(nid: str, path: list[str]) -> None:
        if color.get(nid) == GRAY:
            cycles.append(path[path.index(nid):] + [nid] if nid in path else path + [nid])
            return
        if color.get(nid) == BLACK:
            return
        color[nid] = GRAY
        for dep in (by_id.get(nid, {}).get("depends_on") or []):
            if dep in by_id:
                visit(dep, path + [nid])
        color[nid] = BLACK

    for n in nodes:
        visit(n["id"], [])
    return cycles


# ------------------------------------------------------------------ 读取面


def parallel_groups(tree: dict[str, Any]) -> list[list[str]]:
    """按 DAG 拓扑分层 —— **同层可并行, 层间必须串行**（M3 并行调度的依据）。

    为什么必须有它（借鉴老区 task_decomposition.compute_parallel_groups 的设计洞察）:
        只把串行的 `for` 换成线程池 ⇒ 下游任务在上游产物还没写完时开跑
        ⇒ 从「确定性失败」变成「随机失败」（且难复现）
        ⇒ 先算出层级, 执行器才有**正确的并行边界**（只算不执行 ⇒ 零风险）。

    实现: Kahn 分层。
      · 无依赖的叶 → 第 0 层（可立即并行）
      · 某层全部完成后, 其下游才进下一层
      · 检测到环 → 环内整体放一层（**不阻塞 · 不静默丢弃**）
    返回: `[[本层 id...], ...]` 每层已排序（结果确定, 便于比对）。

    ⚠ 语义边界: 本函数只算"依赖允许的并行", **不含文件冲突** ——
      同层若两个任务写同一文件仍会互相踩。执行器必须同时用 `file_conflicts()` 收缩边界。
    """
    leaves = tree_leaves(tree)
    idset = {str(n.get("id") or "") for n in leaves if n.get("id")}
    deps: dict[str, set[str]] = {i: set() for i in idset}
    by_title = {str(n.get("title") or "").strip(): str(n.get("id") or "") for n in leaves}
    for n in leaves:
        tid = str(n.get("id") or "")
        if tid not in deps:
            continue
        for d in (n.get("depends_on") or []):
            k = str(d).strip()
            if k in idset:
                deps[tid].add(k)
            elif k in by_title and by_title[k] in idset:
                deps[tid].add(by_title[k])       # depends_on 写标题也认
    levels: list[list[str]] = []
    remaining = dict(deps)
    done: set[str] = set()
    while remaining:
        layer = [n for n, d in remaining.items() if d <= done]
        if not layer:                            # 环 → 剩余整体一层, 不阻塞
            layer = sorted(remaining)
        levels.append(sorted(layer))
        done |= set(layer)
        for n in layer:
            remaining.pop(n, None)
    return levels


def file_conflicts(tree: dict[str, Any]) -> list[dict[str, Any]]:
    """同层内写同一文件的冲突（并行安全边界）—— 返回 [{file, ids: [...]}]。

    为什么: `parallel_groups` 只保证依赖顺序, 不保证"不撞车" ——
      两个同层任务若 expected_files 有交集, 并行执行必然互相覆盖。
      ⇒ 执行器需按此把冲突任务**降级为串行**（或报给用户裁决）。
    只在**同一层**内检测（跨层有依赖约束, 不会同时跑）。
    """
    groups = parallel_groups(tree)
    leaves = {str(n.get("id") or ""): n for n in tree_leaves(tree)}
    out: list[dict[str, Any]] = []
    for layer in groups:
        owner: dict[str, list[str]] = {}
        for nid in layer:
            for f in (leaves.get(nid, {}).get("expected_files") or []):
                owner.setdefault(str(f), []).append(nid)
        for f, nids in sorted(owner.items()):
            if len(nids) > 1:
                out.append({"file": f, "ids": sorted(nids)})
    return out


def load_tree(root: Path | str, plan_id: str, project_id: str = "") -> dict[str, Any] | None:
    return _read(root, plan_id, project_id)


def list_trees(root: Path | str, project_id: str = "") -> list[dict[str, Any]]:
    """列出任务树（项目内 + 全局）。"""
    seen: dict[str, dict[str, Any]] = {}
    dirs = [Path(root) / "task_trees"]
    if project_id:
        dirs.insert(0, Path(root) / "projects" / project_id / "tasks")
    else:
        pj = Path(root) / "projects"
        if pj.is_dir():
            dirs += [d / "tasks" for d in pj.iterdir() if d.is_dir()]
    for d in dirs:
        if not d.is_dir():
            continue
        for f in d.glob("*.json"):
            try:
                x = json.loads(f.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if isinstance(x, dict) and x.get("plan_id"):
                seen.setdefault(str(x["plan_id"]), x)
    return sorted(seen.values(), key=lambda t: str(t.get("created_at") or ""), reverse=True)


def confirm_tree(root: Path | str, plan_id: str, project_id: str = "") -> dict[str, Any]:
    """人工确认 —— 候选 → 已确认（进入执行的前置门）。"""
    tree = _read(root, plan_id, project_id)
    if tree is None:
        raise FileNotFoundError(f"任务树不存在: {plan_id}")
    if tree.get("status") != "candidate":
        raise ValueError(f"只有候选态可确认; 当前: {tree.get('status')}")
    tree["status"] = "confirmed"
    tree["confirmed_at"] = _now_iso()
    tree.pop("_saved_to", None)
    tree["_saved_to"] = str(_save(root, plan_id, tree, tree.get("project_id", "") or project_id))
    return tree


def tree_leaves(tree: dict[str, Any]) -> list[dict[str, Any]]:
    return [n for n in (tree.get("nodes") or []) if n.get("kind") == "task"]


def topological_order(tree: dict[str, Any]) -> list[str]:
    """叶任务的拓扑序（依赖先）—— 执行层按它串行/并行。"""
    leaves = tree_leaves(tree)
    by_id = {n["id"]: n for n in leaves}
    out: list[str] = []
    seen: set[str] = set()

    def _visit(nid: str) -> None:
        if nid in seen or nid not in by_id:
            return
        seen.add(nid)
        for dep in (by_id[nid].get("depends_on") or []):
            _visit(dep)
        out.append(nid)

    for n in leaves:
        _visit(n["id"])
    return out


def tree_summary(tree: dict[str, Any] | None) -> dict[str, Any]:
    """进度投影（不开第二套事实 —— 从树本身算）。"""
    if not tree:
        return {"exists": False, "leaves": 0, "done": 0, "percent": 0.0}
    leaves = tree_leaves(tree)
    done = sum(1 for n in leaves if str(n.get("status") or "").upper() in ("DONE", "COMPLETED"))
    total = len(leaves)
    return {
        "exists": True,
        "plan_id": tree.get("plan_id"),
        "status": tree.get("status"),
        "kinds": {k: sum(1 for n in tree.get("nodes", []) if n.get("kind") == k) for k in NODE_KINDS},
        "leaves": total,
        "done": done,
        "percent": round(done / total * 100, 1) if total else 0.0,
        "roles": sorted({str(n.get("required_role") or "") for n in leaves}),
    }
