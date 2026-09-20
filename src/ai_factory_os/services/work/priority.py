"""优先级（priority）—— 三个来源 + 人为最高（★ Founder 定: "ABC都要，支持人为干预"）。

【术语与取值原文来源】调度器契约 `contracts/scheduling.SortKey.priority`
  排序规则 `core/scheduler/rank.py` 原文: **先到期的先做 → 优先级 P0>P1>P2>P3 → 便宜的先做 → 声明序**。
  ⇒ 取值只有 P0/P1/P2/P3（值域外的写不进去, 不静默接受）。

【三个来源 —— 谁的优先级说了算（仲裁: 人工 > 产线声明 > 关键路径自动）】
  A. manual   —— 人手动改（页面点 / CLI --set）。★ 最高, 任何自动都不许覆盖它。
  B. declared —— 产线声明（LLM 在拆解/声明时给 + 理由）。
  C. keypath  —— 关键路径自动导出（链上 ⇒ 拖整棵树 ⇒ 最该先做）。

【★ 为什么必须分开记 source】"谁定的"决定它能不能被覆盖 ——
  只有记了 source, `--auto` 才不会把人手排的顺序冲掉（一数据一权威源 + 人为最高）。
"""

from __future__ import annotations

from typing import Any

VALID: tuple[str, ...] = ("P0", "P1", "P2", "P3")
SOURCE_RANK = {"manual": 0, "declared": 1, "keypath": 2}     # 数字小 = 更权威


def normalize(value: str) -> str:
    """值域校验 —— 非法值抛错（不静默接受: 静默接受 = 写进去一个排不了序的东西）。"""
    v = str(value or "").strip().upper()
    if v not in VALID:
        raise ValueError(f"优先级只能是 {'/'.join(VALID)} 之一, 收到: {value!r}")
    return v


def auto_from_keypath(nodes: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """B+C 里的【C: 关键路径自动导出】—— 纯函数, 不落盘。

    判据（写明, 不自称业务价值）:
      · 在关键路径上（推迟它 ⇒ 整棵完不成） ⇒ **P0**
      · 不在链上、但有人等它（下游 > 0 ⇒ 卡人） ⇒ **P1**
      · 其余（纯旁支） ⇒ **P2**
    """
    from ai_factory_os.services.work import keypath as _kp

    leaves = [str(n.get("id") or "") for n in nodes if n.get("kind") == "task"]
    graph = _kp.leaf_graph(nodes)
    kp = _kp.critical_path(nodes)
    on_chain = set(kp.get("critical_ids") or [])
    waiting = {k: 0 for k in leaves}
    for _k, deps in graph.items():
        for d in deps:
            if d in waiting:
                waiting[d] += 1
    out: dict[str, dict[str, str]] = {}
    for lid in leaves:
        if lid in on_chain:
            out[lid] = {"priority": "P0", "source": "keypath",
                        "reason": "在关键路径上（推迟它 = 拖整棵树）"}
        elif waiting.get(lid):
            out[lid] = {"priority": "P1", "source": "keypath",
                        "reason": f"不在关键路径上, 但有 {waiting[lid]} 个任务在等它"}
        else:
            out[lid] = {"priority": "P2", "source": "keypath",
                        "reason": "旁支（不影响关键路径）"}
    return out


def effective(nodes: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """★ 仲裁后的生效优先级 —— 人工 > 产线声明 > 关键路径自动。

    返回值: {叶 id: {priority, source, reason}}（只含叶任务）。
    """
    auto = auto_from_keypath(nodes)
    out: dict[str, dict[str, str]] = {}
    for n in nodes:
        if n.get("kind") != "task":
            continue
        nid = str(n.get("id") or "")
        stored = str(n.get("priority") or "").strip().upper()
        src = str(n.get("priority_source") or "").strip()
        if stored in VALID and src in SOURCE_RANK:
            out[nid] = {"priority": stored, "source": src,
                        "reason": str(n.get("priority_reason") or "")}
        else:
            out[nid] = auto.get(nid) or {"priority": "P2", "source": "keypath", "reason": ""}
    return out


def can_apply(node: dict[str, Any], new_source: str) -> bool:
    """自动来源想写某个节点时先问一句: 允许吗?

    ★ 仲裁规则（Founder: "ABC都要, 支持人为干预"）: **等级低的不能覆盖等级高的; 同级可以刷新自己**:
      · manual(0) 不许被 declared/keypath 覆盖 ✓（人工最高）
      · declared(1) 不许被 keypath 覆盖 ✓
      · keypath(2) 刷新 keypath ✓（树变了, 自动结论该重算 —— 否则永远冻在第一版）
    实测踩过: 写成"严格小于"⇒ 重跑 --auto 把同级也跳过 ⇒ 自动值永远不刷新。
    """
    cur = str(node.get("priority_source") or "").strip()
    if cur not in SOURCE_RANK:
        return True
    return SOURCE_RANK[new_source] <= SOURCE_RANK[cur]


def stored_stats(nodes: list[dict[str, Any]]) -> dict[str, int]:
    """落盘 vs 兜底 —— ★ 显示上必须分开: 没设置过时"生效分布"是自动兜底, 不是已排好。"""
    leaves = [n for n in nodes if n.get("kind") == "task"]
    stored = sum(1 for n in leaves if str(n.get("priority_source") or "") in SOURCE_RANK)
    return {"leaves": len(leaves), "stored": stored, "fallback": len(leaves) - stored}


def distribution(eff: dict[str, dict[str, str]]) -> dict[str, int]:
    """优先级分布（给视图/CLI 一句话说清"多少条最要紧"）。"""
    out = {p: 0 for p in VALID}
    for v in eff.values():
        out[v["priority"]] = out.get(v["priority"], 0) + 1
    return out
