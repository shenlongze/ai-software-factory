"""逐模块细拆（expand）—— 让任务树**真的长出子任务**。

【为什么需要它（实测教训）】
 现状: arch 产的 `task_breakdown` 是**平的**（13 个模块 × 1 个任务）⇒ 树只有
   project→domain→task 三层, **没有子任务/子子任务** ⇒ "拆解"这件事其实没发生。
 试过并【证伪】的路:
   · 在 architect prompt 里要求"复杂模块给 children" ⇒ 实测 0/11、0/14 都不拆
     （LLM 不自觉地拆细; 它在一次输出里优先写完骨架）
   · 一次性让 LLM 输出整棵多级树 ⇒ 单次输出上限 8192 tokens 必被截断
     （本仓踩过 25466 字符截断, 报错还误导成"字段缺失"）
 ⇒ 正解: **逐个模块单独拆** —— 每次只喂一个模块, 输出体量小（不截断）,
   模型精力集中在这一个模块上（拆得细）。这就是"分而治之"。

【与既有能力的关系】
 · `split_node`（手动拆）: 用户自己指定子任务标题 ⇒ 兜底
 · `expand_module`（本模块）: 让 LLM 给出子任务草案 ⇒ 生成, 用户再改（人机协作）
"""

from __future__ import annotations

import json
from typing import Any

_MIN_KIDS, _MAX_KIDS = 2, 8       #: 一个模块拆成几个子任务（下限/上限）
_MAX_TITLE = 60                   #: 子任务标题长度上限


def _prompt(module: str, desc: str, acceptance: str, caps: list[str]) -> str:
    return (
        "你是资深技术负责人。判断下面这项工作是【一件事】还是【多件事】。\n"
        "★ 判据（唯一标准）: 一个工程师**一次能做完**、且能被**独立验收** ⇒ 就是一件事。\n"
        f"· 是【多件事】⇒ 拆成 {_MIN_KIDS}-{_MAX_KIDS} 个子任务（每个仍要满足上述判据）;\n"
        "· 若它【已经是一件事】⇒ 只返回一个元素的数组（原文照抄标题即可）, 不要硬凑;\n"
        "· 每个任务必须能让别人【独立验收】（写明验收标准）;\n"
        f"· 任务名 ≤{_MAX_TITLE} 字, 用中文, 说清做什么;\n"
        "· 不要重复、不要\"其他\"、不要\"杂项\";\n"
        "· depends_on 写它依赖的【同批任务的编号】(从 1 开始; 无依赖则空数组);\n"
        '· 只输出 JSON 数组, 不要解释、不要 markdown。格式:\n'
        '[{"title":"建商品数据表","acceptance":"表建好且能插入一条商品","depends_on":[]}]\n'
        f"\n模块: {module}\n"
        f"模块说明: {desc or '（无）'}\n"
        f"已有验收要求: {acceptance or '（无）'}\n"
        f"需要的能力: {', '.join(caps) if caps else '（未指定）'}\n"
    )


def _parse(content: str) -> list[dict[str, Any]] | None:
    """解析 LLM 输出; 不合规 ⇒ None（不产半成品）。"""
    s = str(content or "").strip()
    if s.startswith("```"):
        s = "\n".join(ln for ln in s.splitlines() if not ln.strip().startswith("```")).strip()
    try:
        got = json.loads(s)
    except Exception:
        return None
    if not isinstance(got, list):
        return None
    out: list[dict[str, Any]] = []
    for it in got[:_MAX_KIDS]:
        if isinstance(it, str):                      # 容忍"只给标题字符串"的形态
            it = {"title": it}
        if not isinstance(it, dict):
            continue
        title = str(it.get("title") or "").strip()[:_MAX_TITLE]
        if not title:
            continue
        deps = it.get("depends_on") or []
        out.append({
            "title": title,
            "acceptance": str(it.get("acceptance") or "").strip()[:300],
            # ★ 依赖用【同批序号】表示（1-based）—— 由调用方翻译成真实 node id
            "depends_on_idx": [int(x) for x in deps if str(x).strip().isdigit()],
        })
    return out or None     # ★ 允许只返回 1 个（= "已经是一件事, 不该再拆"）


def expand_module(          # noqa: N802 — 名字保留（对外已用）
    module_title: str,
    *,
    desc: str = "",
    acceptance: str = "",
    caps: list[str] | None = None,
    provider: Any,
) -> list[dict[str, Any]]:
    """让 LLM 把一个模块拆成子任务草案。失败 ⇒ 抛错（不产半成品）。"""
    from ai_factory_os.infrastructure.llm.provider import ProviderRequest

    ctx = _prompt(module_title, desc, acceptance, list(caps or []))
    resp = provider.generate(ProviderRequest(task_context=ctx, max_tokens=2048))
    if not getattr(resp, "ok", False) or not (resp.content or "").strip():
        raise ValueError(f"细拆失败: {getattr(resp, 'error', '') or '空响应'}")
    kids = _parse(resp.content)
    if not kids:
        raise ValueError("细拆输出不合规（不是 JSON 数组）—— 不产半成品; 可重试")
    return kids


from pathlib import Path  # noqa: E402 — 局部补（本函数签名用）


def expand_to_minimal(
    root: Path | str,
    plan_id: str,
    project_id: str = "",
    *,
    provider: Any,
    max_rounds: int = 6,
    max_leaves: int = 400,
) -> dict[str, Any]:
    """★ 递归拆解到【最小单位】（Founder 定: "我们采取的是递归的方式, 拆到最小单位, 最小实现"）。

    与"让模型一次吐细"的区别（我先前方向错了）: 拆解是**递归过程** ——
      架构给的是【模块级种子】⇒ 拆解环**反复**把"还不是最小单位"的节点拆开,
      直到每个叶都能一句话写出验收（= 到最小实现）为止。

    停止判据（唯一）: `granularity.reasons_for(叶)` 为空 —— **不是**"层数用完"。
    纪律: 轮次/叶数到上限 ⇒ 停下并**响亮报 remaining**（不静默放弃, 不假装拆完）;
          单个节点细拆失败 ⇒ 记 errors 继续下一个（不因一个节点毁掉整轮）。
    返回: {"rounds", "split", "remaining", "errors", "leaves", "stopped_because"}
    """
    from ai_factory_os.services.work import decomposition as D
    from ai_factory_os.services.work import granularity as G

    out: dict[str, Any] = {"rounds": 0, "split": [], "remaining": [], "errors": [],
                           "leaves": 0, "stopped_because": ""}
    tree = D.load_tree(root, plan_id, project_id) or {}

    for rnd in range(1, max_rounds + 1):
        nodes = tree.get("nodes") or []
        leaves = [n for n in nodes if n.get("kind") == "task"]
        todo = [n for n in leaves if G.reasons_for(n)]
        if not todo:
            out["stopped_because"] = "全部叶已到最小单位"
            break
        out["rounds"] = rnd
        progressed = False
        for node in todo:
            if len([n for n in (tree.get("nodes") or []) if n.get("kind") == "task"]) >= max_leaves:
                out["stopped_because"] = f"叶数到上限（{max_leaves}）⇒ 停止递归"
                break
            nid = str(node.get("id") or "")
            try:
                kids = expand_module(
                    str(node.get("display_name") or node.get("title") or ""),
                    desc=str(node.get("scope") or ""),
                    acceptance=str(node.get("acceptance") or ""),
                    caps=list(node.get("required_capabilities") or []),
                    provider=provider,
                )
            except Exception as exc:  # noqa: BLE001 — 单节点失败不毁整轮
                out["errors"].append(f"{nid}: 细拆失败 {type(exc).__name__}: {str(exc)[:60]}")
                continue
            if len(kids) < 2:
                # LLM 判"已是一件事" ⇒ 这节点到底（但它没过粒度判据 ⇒ 收尾时进 remaining, 响亮）
                continue
            res = D.expand_domain(root, plan_id, node_id=nid, kids=kids, project_id=project_id)
            tree = res.get("tree") or tree
            out["split"].append({"node": nid, "kids": [str(k.get("title") or "")[:40] for k in kids]})
            progressed = True
        if not progressed:
            out["stopped_because"] = out["stopped_because"] or "本轮没有节点可再拆（LLM 判定已是最小）"
            break
    else:
        out["stopped_because"] = f"轮次到上限（{max_rounds}）⇒ 停止递归"

    final = D.load_tree(root, plan_id, project_id) or tree
    fnodes = final.get("nodes") or []
    out["leaves"] = len([n for n in fnodes if n.get("kind") == "task"])
    out["remaining"] = [
        {"id": str(n.get("id") or ""), "title": str(n.get("display_name") or n.get("title") or "")[:60],
         "reasons": G.reasons_for(n)}
        for n in fnodes if n.get("kind") == "task" and G.reasons_for(n)
    ]
    return out
