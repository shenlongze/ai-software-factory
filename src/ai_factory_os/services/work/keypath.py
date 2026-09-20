"""关键路径（Critical Path）—— 从树的依赖图算"最长链"，并标注 ✓汇聚点 ▲。

【术语与判据的原文来源（★ 禁自造, 都是老能力恢复）】
  CHANGELOG v1.1.12「M3b 关键路径标注 (M3-2, S10-090)」原文:
    · 关键路径 = **最长链**: 依赖图 → 拓扑序 → `dist[task] = max(dist[dep]) + est`
      → 最长链回溯 → `estimated_duration`
    · merge point = **入度 ≥ 2** 的节点（只标注, 不调度）
    · CRITICAL 落盘 —— `plan.json.tasks[].critical: bool`（关键路径上 = True）
    · ★ 失败安全铁律: **成环 ⇒ 拒绝产出关键路径**（诚实不伪造）; 不产半成品
  老实现 `session/critical_path.py` 在区域清理中被删（CHANGELOG 已无对应代码）⇒ 本模块按原文恢复判据。

【★ 一份判据, 两处用（禁止各写一套）】
  · 调度器（`bootstrap/scheduler_wiring.py`）要"叶的可调度依赖" ==> `schedulable_deps()`
  · 关键路径要"叶依赖图" ==> `leaf_graph()`
  两处同源 —— 依赖摊平规则只有这一份实现。

【★ 为什么是"跳数"不是"工时"】树里没有 estimated_duration 字段（现状, 实测 273 节点无此字段）
  ⇒ 按原文 `dist[dep] + est` 取 est=1 ⇒ 退化成"最长依赖链（跳数）"。
  这一点必须在输出里写明（`basis`），不许冒充工时关键路径。
"""

from __future__ import annotations

from typing import Any

_MAX_UP = 16                      #: 上溯深度上限（与老实现一致, 防坏数据无限上溯）


def schedulable_deps(nodes: list[dict[str, Any]], leaf_id: str) -> list[str]:
    """把一个叶的 depends_on 解析成【其它叶的 id】—— 摊掉 domain/project 层。

    规则（与执行面一致, 唯一实现）:
      · 取"本叶 + 其全部祖先"声明的 depends_on;
      · 指向 domain/project ⇒ 摊成该节点下的**全部叶**; 指向叶 ⇒ 原样;
      · ★ 指向【自己或自己的祖先】的那条是**归属**（不是可调度先决）⇒ 必须跳过。
        不跳过 ⇒ 摊成"自己的全部兄弟" ⇒ 同域内两两互相依赖 = 环 ⇒ 全树永远不 READY。
        （2026-09-20 实跑执行暴露的硬伤: 真树摊平后 185 条边 → 9158 条 · 13 个环 · 199/199 卡死。）
    """
    by_id = {str(n.get("id") or ""): n for n in nodes}

    def leaves_under(nid: str) -> list[str]:
        out: list[str] = []
        for n in nodes:
            cur = str(n.get("id") or "")
            for _ in range(_MAX_UP):
                if cur == nid:
                    if n.get("kind") == "task":
                        out.append(str(n.get("id") or ""))
                    break
                par = str((by_id.get(cur) or {}).get("parent_id") or "")
                if not par or par == cur:
                    break
                cur = par
        return out

    chain: list[str] = []
    cur = leaf_id
    for _ in range(_MAX_UP):                       # 叶 → domain → project
        chain.append(cur)
        par = str((by_id.get(cur) or {}).get("parent_id") or "")
        if not par or par == cur:
            break
        cur = par
    chain_set = set(chain)

    deps: list[str] = []
    for cid in chain:
        for d in ((by_id.get(cid) or {}).get("depends_on") or []):
            d = str(d).strip()
            if d in chain_set:                     # ★ 归属不是先决
                continue
            for t in leaves_under(d):
                if t and t != leaf_id and t not in chain_set and t not in deps:
                    deps.append(t)
    return sorted(deps)


def leaf_graph(nodes: list[dict[str, Any]]) -> dict[str, list[str]]:
    """叶依赖图（调度器看到的那张图）—— {叶 id: [它依赖的叶, ...]}。"""
    leaves = [str(n.get("id") or "") for n in nodes if n.get("kind") == "task"]
    leaf_set = set(leaves)
    return {lid: [d for d in schedulable_deps(nodes, lid) if d in leaf_set] for lid in leaves}


def _cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """Tarjan 强连通分量 —— 返回 >1 的分量（= 环）。"""
    import sys

    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on: set[str] = set()
    stack: list[str] = []
    counter = [0]
    out: list[list[str]] = []

    def strong(v: str) -> None:
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in graph.get(v, []):
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            out.append(comp)

    sys.setrecursionlimit(20000)
    for v in graph:
        if v not in index:
            strong(v)
    return [c for c in out if len(c) > 1]


def module_chain(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """★ 模块级关键路径 —— 图上画得出来的是【模块链】。

    判据（写明依据, 不冒充工时）: 在【模块依赖图】上取加权最长链,
      权重 = 该模块下的叶数（工作量代理 —— 树里没有工时字段）。
    ⇒ 用途: 功能链路图上高亮"整体由这条链决定"（人读的是模块, 不是 199 个叶）。
    """
    by_id = {str(n.get("id") or ""): n for n in nodes}
    doms = [n for n in nodes if n.get("kind") == "domain"]
    dom_ids = {str(n.get("id") or "") for n in doms}
    tops = [n for n in doms if str(n.get("parent_id") or "") not in dom_ids] or list(doms)

    def leaves_under(nid: str) -> list[str]:
        out: list[str] = []
        for n in nodes:
            cur = str(n.get("id") or "")
            for _ in range(_MAX_UP):
                if cur == nid:
                    if n.get("kind") == "task":
                        out.append(str(n.get("id") or ""))
                    break
                par = str((by_id.get(cur) or {}).get("parent_id") or "")
                if not par or par == cur:
                    break
                cur = par
        return out

    weight = {str(n.get("id") or ""): len(leaves_under(str(n.get("id") or ""))) for n in tops}
    graph: dict[str, list[str]] = {}
    for n in tops:
        nid = str(n.get("id") or "")
        graph[nid] = [str(d) for d in (n.get("depends_on") or [])
                      if str(d) in weight and str(d) != nid]
    out: dict[str, Any] = {"available": False, "reason": "", "chain": [], "total": 0,
                           "basis": "模块依赖链 × 叶数（工作量代理；非工时）"}
    if not graph:
        out["reason"] = "没有模块"
        return out
    if _cycles(graph):
        out["reason"] = "模块依赖成环 ⇒ 拒绝产出关键路径（诚实不伪造）"
        return out
    dist: dict[str, int] = {}
    rdeps: dict[str, list[str]] = {k: [] for k in graph}
    for k, deps in graph.items():
        for d in deps:
            rdeps.setdefault(d, []).append(k)
    deg = {k: len(v) for k, v in graph.items()}
    ready = sorted([k for k, v in deg.items() if v == 0])
    seen = 0
    while ready:
        k = ready.pop(0)
        seen += 1
        dist[k] = weight.get(k, 1) + max((dist.get(d, 0) for d in graph.get(k, [])), default=0)
        for nxt in rdeps.get(k, []):
            deg[nxt] -= 1
            if deg[nxt] == 0:
                ready.append(nxt)
    if seen != len(graph):
        out["reason"] = "模块图排序未覆盖全部模块（坏数据）"
        return out
    end = max(dist, key=lambda k: dist[k])
    chain: list[str] = []
    cur = end
    while cur:
        chain.append(cur)
        nxt = max((d for d in graph.get(cur, [])), key=lambda d: dist.get(d, 0), default="")
        if not nxt or dist.get(nxt, 0) >= dist.get(cur, 0):
            break
        cur = nxt
    chain.reverse()
    out.update({
        "available": True,
        "chain": [{"id": k, "name": str((by_id.get(k) or {}).get("display_name")
                                        or (by_id.get(k) or {}).get("title") or k),
                   "leaves": weight.get(k, 0)} for k in chain],
        "critical_ids": chain,
        "total": sum(weight.get(k, 0) for k in chain),
    })
    return out


def critical_path(nodes: list[dict[str, Any]], name_of: dict[str, str] | None = None,
                  module_of: dict[str, str] | None = None) -> dict[str, Any]:
    """★ 关键路径: 依赖图上的【最长链】+ 汇聚点（入度 ≥ 2）。

    成环 ⇒ `available=False` 并给出环成员（★ 诚实不伪造 —— 原文铁律）。
    `name_of` / `module_of`: 可选, 给结果带上人话名与所属模块（视图直接用）。
    """
    graph = leaf_graph(nodes)
    name_of = name_of or {}
    module_of = module_of or {}
    out: dict[str, Any] = {
        "available": False, "reason": "", "basis": "依赖跳数（树里没有工时字段，非工时关键路径）",
        "chain": [], "critical_ids": [], "merges": [], "total": 0,
    }
    if not graph:
        out["reason"] = "没有叶任务（空树）"
        return out
    cyc = _cycles(graph)
    if cyc:
        out["reason"] = f"依赖成环 ⇒ 拒绝产出关键路径（诚实不伪造）: {len(cyc)} 个环, 例 {cyc[0][:3]}"
        return out

    # 拓扑序 + dist（est=1 ⇒ 最长跳数链）
    dist: dict[str, int] = {}
    order: list[str] = []
    deg = {k: len(v) for k, v in graph.items()}      # 依赖数（前驱个数）
    ready = sorted([k for k, v in deg.items() if v == 0])
    # 反向邻接（谁依赖我）
    rdeps: dict[str, list[str]] = {k: [] for k in graph}
    for k, deps in graph.items():
        for d in deps:
            rdeps.setdefault(d, []).append(k)
    while ready:
        k = ready.pop(0)
        order.append(k)
        dist[k] = max((dist.get(d, 0) + 1 for d in graph.get(k, [])), default=1)
        for nxt in rdeps.get(k, []):
            deg[nxt] -= 1
            if deg[nxt] == 0:
                ready.append(nxt)
    if len(order) != len(graph):                     # 兜底（该分支不该到: 前面已拒绝环）
        out["reason"] = "拓扑排序未覆盖全部叶（存在环或坏数据）"
        return out

    end = max(dist, key=lambda k: dist[k]) if dist else ""
    chain: list[str] = []
    cur = end
    while cur:                                       # 回溯最长链
        chain.append(cur)
        nxt = max((d for d in graph.get(cur, [])), key=lambda d: dist.get(d, 0), default="")
        if not nxt or dist.get(nxt, 0) >= dist.get(cur, 0):
            break
        cur = nxt
    chain.reverse()
    # ★ 两个口径必须分开命名（★ 踩过: 把"入度"和"卡住多少下游"混成一个数 ⇒ 断言对不上）
    #   · 汇聚点 (原文 M3b 术语): 入度 ≥ 2 = 有多少条链汇到它 = len(依赖数)
    #   · 谁最卡人 (对人最有用): 出度 = 有多少任务在等它 = len(下游数)
    #   实测: 摊平图上两条口径都 ≥2 满天飞（前驱 174/199）⇒ 都要写明口径 + 只取 top N。
    merges = [{"id": k, "name": name_of.get(k, k), "in_degree": len(graph.get(k, []))} for k in graph]
    blockers = sorted(
        [{"id": k, "name": name_of.get(k, k), "waiting": len(rdeps.get(k, []))} for k in graph],
        key=lambda m: -m["waiting"])[:10]
    n_merge = sum(1 for m in merges if m["in_degree"] >= 2)
    out.update({
        "available": True,
        "chain": [{"id": k, "name": name_of.get(k, k), "module": module_of.get(k, "")} for k in chain],
        "critical_ids": chain,
        "merges": sorted(merges, key=lambda m: -m["in_degree"])[:10],
        "merges_note": (f"汇聚点(入度≥2) {n_merge} / {len(graph)} 个"
                        "（跨模块摊平后几乎人人 ≥2 ⇒ 只取前 10）"),
        "blockers": blockers,
        "blockers_note": "谁最卡人 = 有多少任务在等它（出度, top 10）",
        "total": len(chain),
    })
    return out
