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
    "parallel_groups", "file_conflicts", "claim_leaf", "release_leaf", "CLAIMABLE",
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


#: CAS 认领的进程内互斥（保证"读-判-写"三步原子）。
#: ⚠ 跨进程不在当前形态内 —— 与 services/work/store.py 的约定一致（单 CLI 进程）。
_CLAIM_LOCK = threading.Lock()


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
    """读树: 指定项目 → 项目内; 否则【全局搜】（task_trees/ + projects/*/tasks/）。

    全局搜索是必要的 —— 调用方（如 `tasktree show PLAN-x`）通常只有 plan_id,
    而树可以落在两处**合法**位置: 有项目的落 `projects/<P>/tasks/`（Founder 铁律）,
    无项目的落 `task_trees/`（实测真数据: 6 棵树其中 4 棵 project_id 为空 ⇒ 该回落是合法场景）。

    ★ R27（同一数据的读写路径必须一致）: **同一个 plan 只应存在一处**。
      多处同时存在 ⇒ 响亮报错（`TreeDuplicatedError`），**绝不静默取一份** ——
      否则就会出现"回写写 A 处、驱动读 B 处 ⇒ 回写看不见 ⇒ 无限重建执行"
      （实测: run --plan 空转 50 轮）。报错信息里给出全部路径与修法。
    """
    base = Path(root)
    cands: list[Path] = []
    if project_id:
        cands.append(base / "projects" / project_id / "tasks" / f"{plan_id}.json")
    cands.append(base / "task_trees" / f"{plan_id}.json")
    pj = base / "projects"
    if pj.is_dir():
        cands += [d / "tasks" / f"{plan_id}.json" for d in pj.iterdir() if d.is_dir()]

    found: list[tuple[Path, dict[str, Any]]] = []
    seen: set[str] = set()
    for p in cands:
        if not p.is_file() or str(p) in seen:
            continue
        seen.add(str(p))
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 损坏 → 跳过（继续找下一个）
            continue
        if isinstance(d, dict) and d.get("plan_id") == plan_id:
            found.append((p, d))

    if len(found) > 1:
        where = "\n".join(f"  · {p}" for p, _ in found)
        raise TreeDuplicatedError(
            f"同一个 plan 存在多处树文件（plan_id={plan_id}）—— 违反 R27"
            f"（同一数据的读写路径必须一致）:\n{where}\n"
            f"修法: 只保留**权威位置**那一份（有项目的在 projects/<P>/tasks/;"
            f" 无项目的在 task_trees/），删除其余副本后重试。"
        )
    return found[0][1] if found else None


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


class TreeDuplicatedError(Exception):
    """同一个 plan 存在**多处**树文件（违反 R27: 同一数据的读写路径必须一致）。

    为什么响亮报错而不是"取一份": 实测过后果 —— 回写写 A 处、驱动读 B 处 ⇒
    回写"看不见" ⇒ 每轮 tick 又建新执行 ⇒ **空转 50 轮 / 52 个执行**。
    静默取一份只会把这种 bug 藏起来。
    """


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
            # ★ 2026-09-19 加（M3 调度前置）: 该叶【需要什么能力】——
            #   由架构阶段给（与 depends_on 同理: 依赖/能力都是架构设计的产物）。
            #   消费方: bootstrap/scheduler_wiring.OrgResource（按能力命中选人）→ core/scheduler.evaluate
            "required_capabilities": [str(c) for c in (kw.get("required_capabilities") or []) if str(c).strip()],
            "role_hint": str(kw.get("role_hint") or ""),      # ★ 提示（非事实）
            "acceptance": str(kw.get("acceptance") or "")[:300],
        }

    # 根: 计划（Project 层）
    root_node = _node("project", f"计划 {plan_id}", scope=stack_note)
    nodes.append(root_node)

    # 中间层: 按种子出现顺序归组
    # ★ 2026-09-19 修（M3 并行调度 · Founder 裁决方案 A）:
    #   依赖由【架构阶段给】—— 种子里带 depends_on（模块名数组）。
    #   之前的两种写法都错（实测暴露）:
    #     · 链式依赖 prev_leaf  ⇒ 并行度 1（全串行）
    #     · "落地型→其余"启发式 ⇒ 并行度 11（全并行）
    #   现在: 种子给什么就是什么; **没给就不连边**（不猜 —— 不猜是纪律, 不是懒惰）。
    #   跨域先决的落点: 叶依赖【自己的 domain 节点】= 层级归属; 域间由种子 depends_on 表达。
    #
    # ★★ 2026-09-19 增（Founder 指出"任务→子任务→子子任务"的递归分解丢失了）:
    #   本函数现在支持**种子嵌套** —— 种子的 `children` 会被递归物化:
    #     有 children ⇒ kind=domain（容器）; 无 children ⇒ kind=task（叶子, 可执行）。
    #   ⇒ 树深由【需求复杂度】决定, 不再固定 3 层。
    #   依据: 老区曾实现过（ee84bc18 "递归分解（不限层数）", Founder 要求"层数不限,
    #     只在确有必要时继续往下拆 —— 不要把每层都硬拆平"），绞杀老区时随 104,618 行一起丢失。
    #   ★ 向后兼容: 种子无 children 时行为与旧版**完全一致**（每 seed = 1 domain + 1 leaf）。
    seed_order: dict[str, str] = {}          # 模块名 → domain 节点 id
    for idx, seed in enumerate(seeds, 1):
        if isinstance(seed, dict):
            mod = str(seed.get("module") or f"module-{idx}").strip()
            seed_order[mod] = ""                 # 先占位, 下面填 id

    def _seed_node(seed: dict[str, Any], parent_id: str, idx: int,
                   *, depth: int = 0) -> None:
        """物化一个种子（含其 children 递归）。有 children ⇒ domain; 无 ⇒ task。"""
        module = str(seed.get("module") or seed.get("task") or f"module-{idx}").strip()
        desc = str(seed.get("task") or "").strip()
        contract = str(seed.get("api_contract") or "").strip()
        children = seed.get("children")
        has_kids = isinstance(children, list) and bool(children)

        if has_kids:
            # 容器层（模块/阶段）—— 不再产叶, 叶在 children 里
            dom = _node("domain", f"模块 {idx}: {module}", parent=parent_id,
                        scope=(desc or contract)[:300])
            seed_deps = [str(d).strip() for d in (seed.get("depends_on") or []) if str(d).strip()]
            dom["depends_on"] = [i for i in (seed_order.get(d, "") for d in seed_deps) if i]
            nodes.append(dom)
            seed_order[module] = dom["id"]
            for j, kid in enumerate(children or [], 1):
                if isinstance(kid, dict) and depth + 1 <= DECOMPOSE_LIMITS["max_depth"]:
                    _seed_node(kid, dom["id"], j, depth=depth + 1)
            return

        # 叶子任务（可执行）—— 与旧版行为一致
        deps = [parent_id]
        seed_deps = [str(d).strip() for d in (seed.get("depends_on") or []) if str(d).strip()]
        deps += [i for i in (seed_order.get(d, "") for d in seed_deps) if i]
        leaf = _node(
            "task", desc or module, parent=parent_id,
            change_type=str(seed.get("change_type") or "NEW_FILE"),
            expected_files=_files_for(module, f"{desc} {contract}", stack),
            depends_on=deps,
            scope=contract[:300],
            required_role=_DEFAULT_ROLE,
            role_hint=_role_hint(module, desc),
            required_capabilities=[
                str(c).strip() for c in (seed.get("required_capabilities") or []) if str(c).strip()
            ],
            acceptance=str(seed.get("acceptance") or contract or f"{module} 实现完成且可验证"),
        )
        nodes.append(leaf)

    for idx, seed in enumerate(seeds, 1):
        if not isinstance(seed, dict):
            continue
        module = str(seed.get("module") or f"module-{idx}").strip()
        desc = str(seed.get("task") or "").strip()
        contract = str(seed.get("api_contract") or "").strip()
        seed_deps = [str(d).strip() for d in (seed.get("depends_on") or []) if str(d).strip()]
        children = seed.get("children")
        has_kids = isinstance(children, list) and bool(children)

        if has_kids:
            _seed_node(seed, root_node["id"], idx)
            continue

        dom = _node("domain", f"模块 {idx}: {module}", parent=root_node["id"], scope=desc[:300])
        # 域间依赖: 映射到那些被依赖模块的 domain 节点（此时已生成的在 seed_order 里）
        dom["depends_on"] = [i for i in (seed_order.get(d, "") for d in seed_deps) if i]
        nodes.append(dom)
        seed_order[module] = dom["id"]           # 登记本模块 → 供后续模块引用

        leaf = _node(
            "task", desc or module, parent=dom["id"],
            change_type="NEW_FILE",
            expected_files=_files_for(module, f"{desc} {contract}", stack),
            # 叶只依赖自己的域（层级归属）—— 模块间的先决在 domain 层表达
            depends_on=[dom["id"]],
            scope=contract[:300],
            required_role=_DEFAULT_ROLE,
            role_hint=_role_hint(module, desc),
            # 架构种子给的必需能力（角色名）—— 不给就空（调度器会诚实报 UNRESOLVED, 不瞎派）
            required_capabilities=[
                str(c).strip() for c in (seed.get("required_capabilities") or []) if str(c).strip()
            ],
            acceptance=contract or f"{module} 实现完成且可验证",
        )
        nodes.append(leaf)

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


#: 叶的可认领状态（CAS 的前提）——pending 才可被认领
CLAIMABLE = ("pending", "candidate")


def claim_leaf(
    root: Path | str,
    plan_id: str,
    node_id: str,
    member_id: str,
    *,
    project_id: str = "",
) -> dict[str, Any]:
    """★ CAS 认领一个叶 —— 「两个 agent 永不会拿同一张卡」（吸收自 amux）。

    为什么必须有它（并行正确性的硬保证）:
        调度器判定 READY 后到真正开始干活之间有时间窗 —— 若两个驱动/两轮 tick
        同时看见了同一个叶, 单靠"判定时是 pending"不足以防双领（判定与写入之间可穿插）。
        CAS = **写入时再校验一次状态**, 只有把 pending 改成 claimed 的那一方赢。

    实现（单进程本地形态, 与 services/work/store.py 的约定一致: 不做跨进程文件锁）:
        threading.Lock 保证本进程内"读-判-写"三步原子; 写入用 D._save（原子替换）。
        ⚠ 跨进程并发不在当前形态内（同 store.py 自述）。未授予跨进程语义, 不假装有。

    返回: {"ok": bool, "reason": str, "node": {...} | None}
      ok=True  ⇒ 认领成功（status 已置 claimed, 记 claimed_by / claimed_at）
      ok=False ⇒ 已被人领 / 状态不可领 / 找不到（reason 说明, 调用方换下一个叶）
    """
    with _CLAIM_LOCK:
        tree = _read(root, plan_id, project_id)
        if tree is None:
            return {"ok": False, "reason": f"任务树不存在: {plan_id}", "node": None}
        node = next((n for n in (tree.get("nodes") or [])
                     if str(n.get("id") or "") == node_id), None)
        if node is None:
            return {"ok": False, "reason": f"叶不存在: {node_id}", "node": None}
        cur = str(node.get("status") or "pending").lower()
        if cur not in CLAIMABLE:
            return {"ok": False, "reason": f"已被认领或不可领（status={cur}）", "node": node}
        # ── CAS 提交点: 检查通过后立刻写（锁内, 中间无让出）
        node["status"] = "claimed"
        node["claimed_by"] = str(member_id)
        node["claimed_at"] = _now_iso()
        _save(root, plan_id, tree, project_id)
        return {"ok": True, "reason": "", "node": node}


def release_leaf(
    root: Path | str,
    plan_id: str,
    node_id: str,
    *,
    project_id: str = "",
    status: str = "pending",
) -> bool:
    """归还/推进一个已被认领的叶（执行完 → completed；失败 → 交回 pending 供重认）。"""
    with _CLAIM_LOCK:
        tree = _read(root, plan_id, project_id)
        if tree is None:
            return False
        for n in tree.get("nodes") or []:
            if str(n.get("id") or "") == node_id:
                n["status"] = status
                n.pop("claimed_by", None)
                n.pop("claimed_at", None)
                _save(root, plan_id, tree, project_id)
                return True
        return False


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
    # ★ 2026-09-19: 依赖可能挂在 domain 节点上（架构给的模块级先决）——
    #   叶要**继承其祖先域的依赖**（域 A 依赖域 B ⇒ A 的叶依赖 B 的叶）。
    #   不继承的话叶之间无边 ⇒ 全部挤在第 0 层（实测暴露的坑）。
    nodes_all = list(tree.get("nodes") or [])
    by_id_all = {str(n.get("id") or ""): n for n in nodes_all}
    leaf_of: dict[str, list[str]] = {}          # 节点 id → 该子树下的叶 id
    for lf in leaves:
        cur = str(lf.get("id") or "")
        for _ in range(16):                     # 上溯到根（深度上限兜底）
            leaf_of.setdefault(cur, []).append(str(lf.get("id") or ""))
            par = str((by_id_all.get(cur) or {}).get("parent_id") or "")
            if not par or par == cur:
                break
            cur = par
    for n in nodes_all:                          # 把每个节点的 depends_on 摊到它的叶
        nid = str(n.get("id") or "")
        for d in (n.get("depends_on") or []):
            d = str(d).strip()
            for a in leaf_of.get(nid, []):       # 本节点的叶
                for b in leaf_of.get(d, []):     # 被依赖节点的叶
                    if a in deps and b in idset and a != b:
                        deps[a].add(b)
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


def edit_node(
    root: Path | str,
    plan_id: str,
    *,
    node_id: str,
    project_id: str = "",
    title: str | None = None,
    acceptance: str | None = None,
    display_name: str | None = None,
    depends_on: list[str] | None = None,
    drop: bool = False,
) -> dict[str, Any]:
    """★ 逐节点编辑 —— Founder: "每一个子节点, 用户都有可能做修改"。

    与 `confirm_tree` 的分工（都作用于同一份树文件 —— 一数据一权威源）:
      · confirm_tree: 整树确认（候选 → 已确认）
      · edit_node:    改某个节点（改完回到候选态, ★ 需重新确认才进执行）

    ★ 为什么要回到候选态: 用户改完 ⇒ 与"刚才确认过的那棵树"不再是同一棵 ⇒
      必须重新走过确认门（否则"确认"这个门就形同虚设）。

    支持: 改 title / acceptance / display_name / 依赖 · 删除节点（drop, 连其子树）
    边界: 找不到节点 ⇒ 响亮报错（不静默）; display_name 为空 ⇒ 置空（回落派生）。
    """
    tree = _read(root, plan_id, project_id)
    if tree is None:
        raise FileNotFoundError(f"任务树不存在: {plan_id}")
    nodes: list[dict[str, Any]] = tree.get("nodes") or []
    target = None
    for n in nodes:
        nid = str(n.get("id") or "")
        # 支持【完整 id】或【短 id】（用户视图里显示的是短 id, 便于输入）
        if nid == node_id or nid.endswith(node_id):
            target = n
            break
    if target is None:
        raise ValueError(f"找不到节点: {node_id}（用 `tasktree show/todo` 看可用的 id）")

    if drop:
        # 删节点 + 其整棵子树（不留孤儿节点）
        doomed = {str(target.get("id") or "")}
        changed = True
        while changed:
            changed = False
            for n in nodes:
                p = str(n.get("parent_id") or "")
                if p in doomed and str(n.get("id") or "") not in doomed:
                    doomed.add(str(n.get("id") or ""))
                    changed = True
        kept = [n for n in nodes if str(n.get("id") or "") not in doomed]
        # 依赖里指向被删节点的引用也要清掉（否则留下悬空依赖 ⇒ 调度器判"前驱未验收"永不执行）
        for n in kept:
            deps = [str(x) for x in (n.get("depends_on") or []) if str(x) not in doomed]
            n["depends_on"] = deps
        tree["nodes"] = kept
        action = f"删除节点及其子树（{len(doomed)} 个）"
    else:
        if title is not None:
            target["title"] = str(title)[:500]
        if acceptance is not None:
            target["acceptance"] = str(acceptance)[:300]
        if display_name is not None:
            target["display_name"] = str(display_name)[:60]
        if depends_on is not None:
            target["depends_on"] = [str(x) for x in depends_on]
        action = "更新节点"

    tree["status"] = "candidate"                 # ★ 改完回到候选态, 需重新确认
    tree["edited_at"] = _now_iso()
    tree.pop("_saved_to", None)
    tree["_saved_to"] = str(_save(root, plan_id, tree, tree.get("project_id", "") or project_id))
    return {"tree": tree, "node": target, "action": action, "status": tree["status"]}


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
