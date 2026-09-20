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
    }


def build_flow(tree: dict[str, Any]) -> dict[str, Any]:
    """★ 投影 B: 功能链路图（看关系）—— 数据形态。

    分层用【domain 子图】做 Kahn 拓扑（★ 不用 `parallel_groups`: 那个按叶分层,
    而用户要看的是"模块级"先后）。有环 ⇒ 整批放一层（不阻塞 · 不静默丢弃）。
    返回 {plan_id, domains, layers:[{level, nodes:[{id,name,deps_on_count}]}], deps:[...]}。
    """
    nodes = tree.get("nodes") or []
    doms = [n for n in nodes if n.get("kind") == "domain"]
    names = {str(n.get("id") or ""): n for n in doms}
    dset = set(names)
    ddeps = {str(n.get("id") or ""): [str(x) for x in (n.get("depends_on") or []) if str(x) in dset]
             for n in doms}
    # 被依赖次数（主次: 被依赖多 ⇒ 更基础）
    dep_count: dict[str, int] = {}
    for nid, ds in ddeps.items():
        for d in ds:
            dep_count[d] = dep_count.get(d, 0) + 1

    layers: list[list[str]] = []
    done: set[str] = set()
    remaining = list(names)
    while remaining:
        ready = sorted(x for x in remaining if all(d in done for d in ddeps.get(x, [])))
        if not ready:
            layers.append(sorted(remaining))
            break
        layers.append(ready)
        done.update(ready)
        remaining = [x for x in remaining if x not in done]

    return {
        "plan_id": str(tree.get("plan_id") or ""),
        "domains": len(doms),
        "layers": [
            {"level": i, "nodes": [
                {"id": nid, "name": node_name(names[nid]),
                 "depended_by": dep_count.get(nid, 0),
                 "status": todo_mark(names[nid].get("status"))}
                for nid in layer]}
            for i, layer in enumerate(layers, 1)
        ],
        "deps": [
            {"name": node_name(names[nid]),
             "on": [node_name(names[d]) for d in ds if d in names]}
            for nid, ds in ddeps.items() if ds
        ],
    }
