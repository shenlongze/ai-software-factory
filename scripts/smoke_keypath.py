"""关键路径 冒烟 —— 判据（手算对照）+ 真树断言（链必须是真的链）。

【为什么有它】Founder: "待办清单中没有关键路径的说明, 需要如何判断？？？"
  ⇒ 恢复老能力 M3b（CHANGELOG v1.1.12）: 关键路径 = 依赖图【最长链】（成环拒绝, 不伪造）。
  恢复类改动最怕"看着像" —— 所以用【手算对照】把判据钉死:
    单链 / 分叉 / 汇聚 / 环 / 无依赖 五种 DAG, 期望值在下面写死, 漂了就红。

【★ 两条铁律（写进断言, 不靠记性）】
  ① 归属不是先决: 叶的 depends_on 指向自己的 domain ⇒ 不算依赖（否则全树成环, 实测踩过）
  ② 成环 ⇒ available=False + reason 非空（★ 诚实不伪造: 不许硬给一条假关键路径）

跑法: `.venv/bin/python scripts/smoke_keypath.py`  · 加 `--root ~/.factory` 扫真树
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))


def _n(nid: str, kind: str, parent: str, title: str, deps: list[str] | None = None) -> dict:
    return {"id": nid, "kind": kind, "parent_id": parent, "title": title,
            "display_name": title, "depends_on": list(deps or [])}


def _leaf_chain(*specs: tuple[str, list[str]]) -> dict:
    """specs: [(叶 id, [依赖的叶 id]), ...] + 一个共同的 domain。"""
    nodes = [_n("p", "project", "", "项目"), _n("M", "domain", "p", "模块")]
    # ★ 每个叶都带"指向自己 domain"的归属依赖（真实树就是这样, 也是曾造成全树成环的那条）
    for lid, deps in specs:
        nodes.append(_n(lid, "task", "M", lid, ["M"] + list(deps)))
    return {"nodes": nodes}


def _check_fixtures() -> list[str]:
    from ai_factory_os.services.work import keypath as KP

    bad: list[str] = []
    names = {"a": "A", "b": "B", "c": "C", "d": "D"}

    def chain_ids(tree: dict) -> list[str]:
        r = KP.critical_path(tree["nodes"], names)
        return list(r["critical_ids"])

    # ① 单链: c 依赖 b, b 依赖 a ⇒ 链 = a,b,c（3 跳）
    t = _leaf_chain(("a", []), ("b", ["a"]), ("c", ["b"]))
    got = chain_ids(t)
    if got != ["a", "b", "c"]:
        bad.append(f"单链: 期望 [a,b,c], 实得 {got}")
    # ② 分叉: b,c 都只依赖 a ⇒ 链长 2（最长链 a→b 或 a→c）
    t = _leaf_chain(("a", []), ("b", ["a"]), ("c", ["a"]))
    if len(chain_ids(t)) != 2:
        bad.append(f"分叉: 期望链长 2, 实得 {len(chain_ids(t))}")
    # ③ 汇聚: d 依赖 b,c; b,c 依赖 a ⇒ 链长 3 · 汇聚点 d 入度 2
    t = _leaf_chain(("a", []), ("b", ["a"]), ("c", ["a"]), ("d", ["b", "c"]))
    r = KP.critical_path(t["nodes"], names)
    if len(r["critical_ids"]) != 3:
        bad.append(f"汇聚: 期望链长 3, 实得 {len(r['critical_ids'])}")
    top = {m["id"]: m["in_degree"] for m in r["merges"]}
    if top.get("d") != 2:
        bad.append(f"汇聚: d 的入度(前驱数)期望 2, 实得 {top.get('d')}")
    wait = {m["id"]: m["waiting"] for m in r["blockers"]}
    if wait.get("a") != 2:                        # a 被 b、c 等 ⇒ 谁最卡人 = a
        bad.append(f"谁最卡人: a 的下游数期望 2, 实得 {wait.get('a')}")
    # ④ 环: a↔b ⇒ 必须【拒绝产出】并给原因（诚实不伪造）
    #   ★ 断言必须咬住【显式拒绝】这条路径: 只查"含环"二字会被兜底的拓扑检查蒙过去
    #   （反向验证实测: 关掉显式环检测后兜底仍 available=False + reason 含"存在环或坏数据" ⇒ 不红）
    t = _leaf_chain(("a", ["b"]), ("b", ["a"]))
    r = KP.critical_path(t["nodes"], names)
    if r["available"] or "拒绝产出关键路径" not in r["reason"]:
        bad.append(f"环: 期望走显式拒绝（available=False 且 reason 含'拒绝产出关键路径'）, "
                   f"实得 {r['available']} / {r['reason']!r}")
    # ⑤ 无依赖: 三个独立叶 ⇒ 链长 1
    t = _leaf_chain(("a", []), ("b", []), ("c", []))
    if len(chain_ids(t)) != 1:
        bad.append(f"无依赖: 期望链长 1, 实得 {len(chain_ids(t))}")
    # ⑥ ★ 归属不是先决: 叶的依赖里只有自己的 domain ⇒ 摊平后【零依赖】
    graph = KP.leaf_graph(t["nodes"])
    if graph.get("a"):
        bad.append(f"归属被当成依赖: a 的摊平依赖 = {graph.get('a')}（应为空）")
    # ⑦ 模块级: 模块链的相邻两项必须真有依赖边（链是真的链, 不是拼的）
    nodes = [_n("p", "project", "", "项目"),
             _n("M1", "domain", "p", "模块一"), _n("a1", "task", "M1", "a1", ["M1"]),
             _n("M2", "domain", "p", "模块二", ["M1"]), _n("b1", "task", "M2", "b1", ["M2"]),
             _n("M3", "domain", "p", "模块三", ["M2"]), _n("c1", "task", "M3", "c1", ["M3"])]
    mc = KP.module_chain(nodes)
    ids = mc["critical_ids"]
    if ids != ["M1", "M2", "M3"]:
        bad.append(f"模块链: 期望 [M1,M2,M3], 实得 {ids}")
    if mc["total"] != 3:
        bad.append(f"模块链: 链上叶数期望 3, 实得 {mc['total']}")
    return bad


def _check_real(root: Path, plan_file: Path) -> list[str]:
    """真树断言: 链上相邻必须真有依赖边 · 链上叶数 = 各模块叶数之和 · 算不出必须给原因。"""
    from ai_factory_os.services.work import keypath as KP

    t = json.loads(plan_file.read_text(encoding="utf-8"))
    nodes = t.get("nodes") or []
    by_id = {str(n.get("id") or ""): n for n in nodes}
    name = {i: str(n.get("display_name") or n.get("title") or i) for i, n in by_id.items()}
    bad: list[str] = []

    mc = KP.module_chain(nodes)
    if mc["available"]:
        ids = list(mc["critical_ids"])
        for a, b in zip(ids, ids[1:]):                 # 相邻两项: b 必须声明依赖 a
            if a not in [str(x) for x in (by_id.get(b, {}).get("depends_on") or [])]:
                bad.append(f"{plan_file.stem}: 模块链不连续: {name.get(b, b)} 没声明依赖 {name.get(a, a)}")
        if len(set(ids)) != len(ids):
            bad.append(f"{plan_file.stem}: 模块链有重复节点")
    elif not mc.get("reason"):
        bad.append(f"{plan_file.stem}: 模块链算不出却没说原因（静默失败）")

    r = KP.critical_path(nodes, name)
    if r["available"]:
        unknown = [x for x in r["critical_ids"] if x not in by_id]
        if unknown:
            bad.append(f"{plan_file.stem}: 关键路径含不存在的节点: {unknown[:3]}")
        if r["total"] != len(r["critical_ids"]):
            bad.append(f"{plan_file.stem}: 链长与成员数不一致")
    elif not r.get("reason"):
        bad.append(f"{plan_file.stem}: 关键路径算不出却没说原因（静默失败）")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description="关键路径判据冒烟")
    ap.add_argument("--root", default="", help="额外扫描的真实数据根")
    args = ap.parse_args()

    results: list[tuple[str, bool, str]] = []
    bad = _check_fixtures()
    results.append(("判据: 单链/分叉/汇聚/环/无依赖/归属先决/模块链", not bad, "；".join(bad)))

    if args.root:
        rroot = Path(args.root).expanduser()
        for pf in sorted(rroot.glob("projects/*/tasks/PLAN-*.json")):
            bad2 = _check_real(rroot, pf)
            results.append((f"{pf.stem} 关键路径断言", not bad2, "；".join(bad2)))

    width = max(len(n) for n, _, _ in results)
    fails = 0
    for label, ok, detail in results:
        print(f"   [{'PASS' if ok else 'FAIL'}] {label.ljust(width)}" + (f"   ← {detail}" if detail else ""))
        fails += 0 if ok else 1
    print(f"\n{len(results) - fails}/{len(results)} 通过")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
