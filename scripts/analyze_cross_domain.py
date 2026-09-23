"""跨域依赖分析 → 报告（R3 断环方案的判据）。

★ Founder 点单：出「谁依赖谁 · 有没有环 · 每环怎么断」的图。**只读分析, 不动代码** ✗。

数据来源：`scripts/check_architecture.py` 的 `modules()` + `_layer_edges()` ——
复用守卫**同一份**模块/边（不另取参照 ✓）。

产出：`docs/reports/2026-09-22-跨域依赖与断环方案.md`（含 mermaid 图 + 环清单 + 断法选项）
用法：`.venv/bin/python scripts/analyze_cross_domain.py`
"""
from __future__ import annotations

import importlib
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "reports" / "2026-09-22-跨域依赖与断环方案.md"

TYPE_HINT = ("Status", "Type", "Spec", "Config", "Error", "Request", "Response", "Result",
             "Enum", "Protocol", "Snapshot", "Record", "Definition", "Info", "State")


def _load_checker():
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.path.insert(0, str(ROOT / "src"))
    return importlib.import_module("check_architecture")


def _is_typeish(edge: str) -> bool:
    """边字符串形如 `path:line → 目标模块` —— 只看**目标模块**那段 ✓。"""
    target = edge.split("→")[-1].strip()
    low = target.lower()
    if any(h in target for h in TYPE_HINT) or any(k in low for k in (".types", "contracts", ".enums")):
        return True
    return False


def main() -> int:
    ca = _load_checker()
    mods = ca.modules()
    edges = ca._layer_edges(mods)

    # domain → domain 边（只看 services 内部跨域, 即 R3 口径 ✓）
    pair: dict[tuple[str, str], list[str]] = defaultdict(list)
    for m, tl, t, ln in edges:
        if m.layer != "services" or tl != "services":
            continue
        td = ca.target_domain(t)
        if td in (None, m.domain):
            continue
        pair[(m.domain or "?", td)].append(f"{m.rel}:{ln} → {t}")

    # 强连通（找环）—— 简单实现: 对每个域做 DFS 看能否回到自己
    nodes = sorted({a for a, _ in pair} | {b for _, b in pair})
    adj: dict[str, set[str]] = defaultdict(set)
    for a, b in pair:
        adj[a].add(b)

    def _reach(start: str) -> set[str]:
        seen: set[str] = set()
        stack = [start]
        while stack:
            cur = stack.pop()
            for nxt in adj.get(cur, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    # 真环 = 强连通分量（Tarjan, 迭代实现; 分量内 ≥2 个域就是环 ✓）
    import sys as _s

    _s.setrecursionlimit(10000)
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on: dict[str, bool] = {}
    stack: list[str] = []
    sccs: list[list[str]] = []
    counter = [0]

    def _tarjan(v: str) -> None:
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on[v] = True
        for w in adj.get(v, ()):
            if w not in index:
                _tarjan(w)
                low[v] = min(low[v], low[w])
            elif on.get(w):
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on[w] = False
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                sccs.append(sorted(comp))

    for n in nodes:
        if n not in index:
            _tarjan(n)
    cycles = [tuple(a) for a in sccs]                 # 分量（≥2 域）
    direct = [(a, b) for (a, b), _ in pair.items() if (b, a) in pair]

    # 报告
    lines: list[str] = []
    lines.append("# 跨域依赖与断环方案（R3）\n")
    lines.append("> 只读分析，**没有动任何代码** ✗。数据来自架构守卫 `scripts/check_architecture.py` 的")
    lines.append("> `modules()` + `_layer_edges()`（**同一份**模块与边，不另取参照 ✓）。")
    lines.append("> 这份文件由 `scripts/analyze_cross_domain.py` 生成，可重跑 ✓。\n")
    lines.append(f"## 一、总览\n\n- 跨域依赖边：**{sum(len(v) for v in pair.values())}** 条"
                 f"（R3 报的就是这些）\n- 涉及域：**{len(nodes)}** 个\n"
                 f"- **成环的域对：{len(cycles)} 对**（A→B 且 B→A）\n")

    lines.append("## 二、域间依赖图（mermaid）\n\n```mermaid\ngraph LR")
    for (a, b), lst in sorted(pair.items(), key=lambda kv: -len(kv[1])):
        lines.append(f'  {a}["{a}"] -->|{len(lst)}| {b}["{b}"]')
    lines.append("```\n")

    lines.append("## 三、边数排行（谁依赖别人最多）\n")
    lines.append("| 从 | 到 | 边数 | 其中「像契约」的 | 例子（前 2 条） |")
    lines.append("|---|---|---|---|---|")
    for (a, b), lst in sorted(pair.items(), key=lambda kv: -len(kv[1])):
        typeish = sum(1 for x in lst if _is_typeish(x))
        ex = " · ".join(f"`{x.split(' → ')[1]}`" for x in lst[:2])
        lines.append(f"| {a} | {b} | {len(lst)} | {typeish} | {ex} |")

    lines.append("\n## 四、成环情况（要断的）\n")
    lines.append(f"- **真环（强连通分量, 绕得回来）：{len(cycles)} 个**")
    for comp in cycles:
        lines.append(f"  - {', '.join(comp)}")
    lines.append(f"- **直接双向（A⇄B 两边都有边）：{len(direct)} 对** —— 这种最好断 ✓\n")
    for comp in cycles:
        for i, a in enumerate(comp):
            for b in comp[i + 1:]:
                ab, ba = pair.get((a, b), []), pair.get((b, a), [])
                if not ab or not ba:
                    continue          # 间接环: 反向要经中间域 ⇒ 单列一行说明 ✓
                lines.append(f"### {a} ⇄ {b}（{len(ab)} + {len(ba)} 条）\n")
                lines.append(f"- `{a} → {b}`：{len(ab)} 条，其中像契约的 {sum(1 for x in ab if _is_typeish(x))} 条")
                lines.append(f"- `{b} → {a}`：{len(ba)} 条，其中像契约的 {sum(1 for x in ba if _is_typeish(x))} 条")
                lines.append(f"- 例子：`{ab[0]}` ／ `{ba[0]}`\n")

    lines.append("## 五、断法（三选一, 按代价从低到高）\n")
    lines.append("| 断法 | 适用 | 代价 | 风险 |")
    lines.append("|---|---|---|---|")
    lines.append("| **搬类型**：把纯类型/枚举/契约搬到 `contracts/<域>/` | 边是「像契约」的那类（本报告第 3 列） | 低（同 R4/R9 的做法 ✓） | 低（保留再导出或改调用方 ✓） |")
    lines.append("| **注入**：调用方把需要的行为作为参数传进来 | 边是「要执行/查询」的那类 | 中（改函数签名 + 调用点） | 中（要跑全链回归 ✓） |")
    lines.append("| **改归属**：把模块搬到真正该在的域 | 两边互相纠缠、搬类型也断不干净 | 高 | 高（动 import 图） |")

    lines.append("\n## 六、建议顺序（我的判断, 供你裁决）\n")
    lines.append("1. 先做**不成环**的跨域边：把其中「像契约」的搬进 `contracts/` ⇒ 边数大降、风险最低")
    lines.append("2. 再针对**成环**的（上面第三节）逐对处理：先把两个方向里「像契约」的一半搬走，")
    lines.append("   环往往自己就断了 ✓；剩下的真行为依赖再谈注入")
    lines.append("3. 一次只动一对域，每步全量 `pytest` + 架构守卫复核（同 R9/R10 的做法 ✓）\n")
    lines.append("> 每步都要能回答：「这条边断了以后，行为一字未变吗？」 ✗ 变了就不是重构, 是改功能。")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  已生成 {OUT.relative_to(ROOT)}")
    print(f"  跨域边 {sum(len(v) for v in pair.values())} 条 · 涉及域 {len(nodes)} 个 · 成环域对 {len(cycles)} 对")
    top = Counter({f"{a}→{b}": len(v) for (a, b), v in pair.items()}).most_common(5)
    for k, v in top:
        print(f"    {k:34s} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
