"""用户视图 —— 任务树的**两个投影**（Founder 定的设计）。

Founder 原话:
  "两层是两种呈现, 服务两种理解, 但说的一定是同一件事"
    · 功能链路图（看关系）: 这个需求包含什么、怎么串起来
    · 层级待办清单（看进度）: 要做哪些活、谁做、做到哪了

★ 为什么这层要独立（不在 CLI 里）:
  同一个视图要同时给 **CLI** 和 **API** 用 —— 若各写一份就是 R25（一能力两套实现）。
  ⇒ 视图的**数据构造**归服务层; CLI 负责排版, API 负责序列化。

★ 数据源只有一份: 任务树（`decomposition`）。两个投影都**只读它**, 不加第二套数据。
"""

from __future__ import annotations

from typing import Any

#: 能力名 → 人话（用户视图里不出现 developer/architect 这种词）
_CAP_WORDS: dict[str, str] = {
    "developer": "开发", "architect": "架构", "tester": "测试", "devops": "部署",
    "reviewer": "评审", "security": "安全", "ux_ui": "设计", "pm": "产品",
}

_DONE = ("completed", "done", "accepted")
_RUNNING = ("claimed", "running", "in_progress")
_DEAD = ("cancelled", "failed", "rejected")


def cap_word(cap: Any) -> str:
    """能力名 → 人话（认不出就原样, 不瞎译）。"""
    s = str(cap or "").strip()
    return _CAP_WORDS.get(s, s)


def display_name(title: str) -> str:
    """把专业 title 【规则派生】成人话名（不调 LLM —— 快、稳、免费）。

    规则: 去掉 "模块 N: " 前缀 → 取第一个分句（括号优先）→ 限 24 字。
    ★ 这是**派生**: 节点有 `display_name` 字段时优先用字段（见 `node_name`）;
      字段由 `tasktree translate`（LLM 翻译）或用户 `tasktree edit` 写入。
    """
    s = str(title or "").strip()
    if s.startswith("模块"):
        i = s.find(":")
        j = s.find("：")
        cut = min([x for x in (i, j) if x >= 0], default=-1)
        if cut > 0:
            s = s[cut + 1:].strip()
    # ★ 括号优先: "初始化 monorepo（consumer、admin…" ⇒ "初始化 monorepo"
    for sep in ("（", "(", "，", "、", "；", ";", ",", "。"):
        if sep in s:
            s = s.split(sep)[0]
            break
    return s[:24] + ("…" if len(s) > 24 else "")


def node_name(node: dict[str, Any]) -> str:
    """节点的显示名 —— ★ 优先 `display_name` 字段（用户改过/翻译过的）, 否则规则派生。

    ★ 为什么必须有: 若只派生不读字段, 用户 `tasktree edit --display-name` 改的值
    **根本不显示**（实测踩到 ⇒ 用户以为改了其实没用）。
    """
    got = str(node.get("display_name") or "").strip()
    return got or display_name(node.get("title"))


def todo_mark(status: Any) -> str:
    """状态 → 人话标记。"""
    st = str(getattr(status, "value", status) or "").strip().lower()
    if st in _DONE:
        return "done"
    if st in _RUNNING:
        return "doing"
    if st in _DEAD:
        return "dead"
    return "todo"


#: 标记 → 符号/文字（CLI 用符号; Web 可换图标 —— 数据里给的是语义值）
MARK_SYMBOL: dict[str, str] = {"todo": "☐", "doing": "🚧", "done": "✅", "dead": "⛔"}


def node_progress(node: dict[str, Any], by_parent: dict[str, list]) -> tuple[int, int]:
    """★ 完成度（**派生值, 不落字段**）—— Founder 设计:
    "节点完成度 = 已完成子节点数 / 总子节点数"（叶子 DONE ⇒ 100%）。

    为什么是派生而非字段: 它完全由子节点 status 决定 ⇒ 存字段会出现"存的值 ≠ 算的值"。
    """
    kids = [k for k in by_parent.get(str(node.get("id") or ""), [])
            if k.get("kind") in ("domain", "task")]
    if not kids:
        st = str(node.get("status") or "").lower()
        return (1, 1) if st in _DONE else (0, 1)
    d = tt = 0
    for k in kids:
        kd, kt = node_progress(k, by_parent)
        d += kd
        tt += kt
    return (d, tt)


def _index(tree: dict[str, Any]) -> dict[str, list]:
    out: dict[str, list] = {}
    for n in tree.get("nodes") or []:
        out.setdefault(str(n.get("parent_id") or ""), []).append(n)
    return out


def _sources_of(eff: dict[str, dict[str, str]]) -> dict[str, int]:
    """优先级来源分布（人工/产线声明/关键路径）—— 视图必须能说清"这优先级是谁定的"。"""
    out: dict[str, int] = {}
    for v in eff.values():
        k = str(v.get("source") or "")
        out[k] = out.get(k, 0) + 1
    return out


def build_todo(tree: dict[str, Any]) -> dict[str, Any]:
    """★ 投影 A: 层级待办清单（看进度）—— 数据形态。

    返回 {title, status, done, total, percent, lines:[{depth, mark, name,
          who, done, total, id}]}。CLI 拿来排版; API 直接序列化给 Web。
    """
    by_parent = _index(tree)
    leaves = [n for n in (tree.get("nodes") or []) if n.get("kind") == "task"]
    done = sum(1 for n in leaves if str(n.get("status") or "").lower() in _DONE)
    total = len(leaves)
    lines: list[dict[str, Any]] = []

    # ★ 关键路径（Founder: "待办清单中没有关键路径的说明, 需要如何判断"）——
    #   判据原文见服务层 keypath.py（= 老能力 M3b 的恢复, 非自造）。
    from ai_factory_os.services.work import keypath as _kp

    _nodes = list(tree.get("nodes") or [])
    _names = {str(n.get("id") or ""): node_name(n) for n in _nodes}
    _domname = {str(n.get("id") or ""): node_name(n) for n in _nodes if n.get("kind") == "domain"}
    _leafmod = {str(n.get("id") or ""): _domname.get(str(n.get("parent_id") or ""), "")
                for n in _nodes if n.get("kind") == "task"}
    kp = _kp.critical_path(_nodes, _names, _leafmod)
    crit_ids = set(kp.get("critical_ids") or [])

    # ★ 优先级（ABC 三来源 + 人为最高）—— 判据见 services/work/priority.py
    from ai_factory_os.services.work import priority as _pri

    eff = _pri.effective(_nodes)

    def _walk(parent: str, depth: int) -> None:
        for n in by_parent.get(parent, []):
            if n.get("kind") == "project":
                _walk(str(n.get("id") or ""), depth)
                continue
            who = str(n.get("assignee") or "").strip()
            d_, t_ = node_progress(n, by_parent)
            if not who and n.get("kind") == "task":
                caps = n.get("required_capabilities") or []
                who = f"待派（需要: {cap_word(caps[0])}）" if caps else "待派"
            lines.append({
                "id": str(n.get("id") or ""),
                "depth": depth,
                "mark": todo_mark(n.get("status")),
                "name": node_name(n),
                "who": who,
                "done": d_,
                "total": t_,
                "kind": str(n.get("kind") or ""),
                # ★ 在关键路径上（这条决定整体完工 —— 推迟它就会拖整棵树）
                "critical": str(n.get("id") or "") in crit_ids,
                # ★ 优先级（叶: 仲裁后生效值; 模块: 自己声明的值, 供清单展示）
                "priority": (eff.get(str(n.get("id") or "")) or {}).get("priority")
                            or str(n.get("priority") or ""),
                "priority_source": (eff.get(str(n.get("id") or "")) or {}).get("source")
                                   or str(n.get("priority_source") or ""),
                "priority_reason": (eff.get(str(n.get("id") or "")) or {}).get("reason")
                                   or str(n.get("priority_reason") or ""),
            })
            _walk(str(n.get("id") or ""), depth + 1)

    _walk("", 0)
    return {
        "plan_id": str(tree.get("plan_id") or ""),
        "status": str(tree.get("status") or ""),
        "done": done,
        "total": total,
        "percent": (done * 100 // total) if total else 0,
        "lines": lines,
        # ★ 关键路径说明（怎么判、依据什么、哪些在链上、谁最卡人）
        "critical_path": {
            "available": kp.get("available"),
            "reason": kp.get("reason") or "",
            "total": kp.get("total") or 0,
            "basis": kp.get("basis") or "",
            "note": kp.get("merges_note") or "",
            "blockers": kp.get("blockers") or [],
            "blockers_note": kp.get("blockers_note") or "",
            "chain_head": (kp.get("chain") or [])[:3],
        },
        # ★ 优先级（分布 + 落盘情况 —— 让人一眼看出"哪些最要紧"和"谁定的"）
        #   ★ 口径与上面 lines 完全一致（列表显示什么, 汇总就算什么）——
        #     踩过: 汇总只统计叶任务 ⇒ 只有模块的树显示全 0, 与列表自相矛盾。
        "priority": {
            "distribution": {p: sum(1 for ln in lines if ln.get("priority") == p)
                             for p in _pri.VALID},
            "sources": _sources_of({ln["id"]: {"source": ln.get("priority_source") or ""}
                                    for ln in lines if ln.get("priority")}),
            "stored": _pri.stored_stats(_nodes),
        },
    }


def build_flow(tree: dict[str, Any]) -> dict[str, Any]:
    """★ 投影 B: 功能链路图（看关系）—— 数据形态。

    ★ 生成规则出自设计原文（docs/design/requirement-flow-and-user-view.md §6）:
       · 节点 = kind=domain 的节点 → 显示 display_name
       · 边   = depends_on（读成"前置关系"）
       · 分层 = parent_id（可折叠）—— 模块 → 子模块
       · 主次 = 被依赖次数（被依赖多 ⇒ 核心）

    ★ 为什么必须按 parent_id 分层（Founder 实测: "功能链路图有问题, 一直在堆砌, 看不懂"）:
       递归拆解产出的是 domain → domain → task 的嵌套（实测 13 个业务模块
       ⇒ 细拆成 73 个 domain）。若把这 73 个 domain 全拍平再按 depends_on 分层,
       会一次性倒出 73 个节点 + 72 条边 —— 用户看到的就是"堆砌"。
       ⇒ 默认只出【顶层模块】（父节点不是 domain 的那些）, 子模块放在 children 里,
         由使用方按需展开（这就是设计里"可折叠"的落地）。

    返回 {
      plan_id, modules(顶层模块数), domains(全部 domain 数),
      root:    [模块节点（含 children 递归; 每个带 level=第几批）]
      batches: [{level, nodes:[模块节点]}]  ← ★ 先后: 只对顶层模块分层
      edges:   [{from, to}]  ← ★ 边（前置 → 后续）, 渲染方据此画线
      external_deps: [{from, to_name}]  ← 依赖指向子模块的（不静默丢, 提示展开看）
    }
    模块节点 = {id, name, status, level, depended_by, core, deps:[前置名], kids, children:[...]}。
    """
    nodes = tree.get("nodes") or []
    doms = [n for n in nodes if n.get("kind") == "domain"]
    by_id = {str(n.get("id") or ""): n for n in nodes}
    dom_ids = {str(n.get("id") or "") for n in doms}

    # ★ 设计 §6 的"分层": parent_id → 子模块（同一份数据, 换一种看法, 不是第二份数据）
    kids_dom: dict[str, list[dict[str, Any]]] = {}
    for n in doms:
        kids_dom.setdefault(str(n.get("parent_id") or ""), []).append(n)

    # 顶层模块 = 父节点不是 domain 的（挂在 project 下 / 无父）
    top = [n for n in doms if str(n.get("parent_id") or "") not in dom_ids]
    if not top:                      # 兜底: 全嵌套(无顶层) ⇒ 取无父的那些, 仍无则全给(不退化成空视图)
        top = [n for n in doms if not str(n.get("parent_id") or "")] or list(doms)

    # 边 = depends_on（只认 domain → domain 的边; 自依赖丢弃）
    deps_of: dict[str, list[str]] = {}
    dep_count: dict[str, int] = {}
    for n in doms:
        nid = str(n.get("id") or "")
        ds = [str(x) for x in (n.get("depends_on") or [])
              if str(x) in dom_ids and str(x) != nid]
        deps_of[nid] = ds
        for d in ds:
            dep_count[d] = dep_count.get(d, 0) + 1
    core_max = max(dep_count.values(), default=0)

    # ★ 模块级关键路径（Founder: "待办清单/链路图里没有关键路径的说明, 需要如何判断"）
    #   判据 = 老能力 M3b（CHANGELOG v1.1.12）: 最长链; 权重用叶数当工作量代理（树里没工时字段）。
    from ai_factory_os.services.work import keypath as _kp

    mc = _kp.module_chain(nodes)
    crit_mods = set(mc.get("critical_ids") or [])
    crit_pairs = [(str(mc["critical_ids"][i]), str(mc["critical_ids"][i + 1]))
                  for i in range(len(mc.get("critical_ids") or []) - 1)]

    def _mk(n: dict[str, Any], seen: tuple[str, ...] = ()) -> dict[str, Any]:
        nid = str(n.get("id") or "")
        # 兜底: parent_id 成环 ⇒ 不再下钻（不递归爆栈; 不静默丢节点, 照样输出本节点）
        kids = [] if nid in seen else [_mk(k, seen + (nid,)) for k in kids_dom.get(nid, [])]
        return {
            "id": nid,
            "name": node_name(n),
            "status": todo_mark(n.get("status")),
            "depended_by": dep_count.get(nid, 0),
            "core": bool(core_max and dep_count.get(nid, 0) == core_max),
            # ★ 在【模块级关键路径】上（整体完工由这条链决定 —— 判定依据见 keypath.module_chain）
            "critical": nid in crit_mods,
            "deps": [node_name(by_id[d]) for d in deps_of.get(nid, []) if d in by_id],
            "kids": len(kids),
            "children": kids,
        }

    roots = [_mk(n) for n in top]
    by_top = {m["id"]: m for m in roots}

    # ★ 先后只对【顶层模块】分层 —— 把 60 个子模块也算进去会把层数从 6 拉到 12, 那也是"堆砌"。
    top_set = set(by_top)
    tdep = {t: [d for d in deps_of.get(t, []) if d in top_set] for t in top_set}
    batches: list[list[str]] = []
    done_set: set[str] = set()
    remaining = list(top_set)
    while remaining:
        ready = sorted(x for x in remaining if all(d in done_set for d in tdep.get(x, [])))
        if not ready:                      # 有环 ⇒ 整批放一层（不阻塞 · 不静默丢弃）
            batches.append(sorted(remaining))
            break
        batches.append(ready)
        done_set.update(ready)
        remaining = [x for x in remaining if x not in done_set]

    # ★ 图要画线: 必须给【id】和【方向】—— 名字会重名; 且 depends_on 的语义是
    #   "我依赖谁", 所以边要从【前置】指向【后续】(上面先做 ⇒ 箭头朝下)。
    top_level = {x: i for i, layer in enumerate(batches, 1) for x in layer}
    edges = [{"from": d, "to": t}
             for t in sorted(top_set) for d in tdep.get(t, [])]
    # 依赖指向子模块/非顶层的: 不静默丢 —— 单列出来, 渲染方提示"展开模块看"
    external = [{"from": by_top[x]["name"], "to_name": node_name(by_id[d])}
                for x in sorted(top_set) for d in deps_of.get(x, []) if d not in top_set]
    for m in roots:
        m["level"] = top_level.get(m["id"], 0)

    return {
        "plan_id": str(tree.get("plan_id") or ""),
        "modules": len(roots),
        "domains": len(doms),
        "root": roots,
        "batches": [
            {"level": i, "nodes": [by_top[x] for x in layer if x in by_top]}
            for i, layer in enumerate(batches, 1)
        ],
        "edges": edges,
        "external_deps": external,
        # ★ 关键路径（模块级）: 渲染方据此把这条链【高亮成一条链】—— 关系类内容要能被看见
        "critical_path": {
            "available": mc.get("available"),
            "reason": mc.get("reason") or "",
            "basis": mc.get("basis") or "",
            "modules": mc.get("chain") or [],
            "total_leaves": mc.get("total") or 0,
            "edges": [{"from": a, "to": b} for a, b in crit_pairs],
        },
    }
