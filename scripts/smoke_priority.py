"""优先级 冒烟 —— 判据（ABC 三来源 + 人为最高）+ 落到调度器的证明。

【Founder 定】"ABC都要，支持人为干预" ⇒ 三个来源 + 仲裁规则必须机器守:
  A 人工(manual) > B 产线声明(declared) > C 关键路径自动(keypath)
  同级可刷新自己（否则自动结论永远冻在第一版 —— 实测踩过）
  取值只有 P0..P3（调度器 rank.py 原文: 先到期 → 优先级 → 便宜的先做 → 声明序）

【为什么必须有它】"设置了但没生效"是这类功能的典型死法 —— 所以最后一条断言
  直接问【调度器端口】: `ports.work.priority_of(叶)` 必须等于刚落盘的值。
（不是只看树上写了字段就算数。）

跑法: `.venv/bin/python scripts/smoke_priority.py` · 加 `--root ~/.factory` 扫真树
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))


def _fixture_tree() -> dict:
    """a1→a2 是关键链; c1 是旁支（没人等它）; b1 有人等（做 b1 挡着 b2）。"""
    return {
        "plan_id": "PLAN-pri", "project_id": "P1", "status": "confirmed",
        "nodes": [
            {"id": "p", "kind": "project", "parent_id": "", "title": "项目"},
            {"id": "M1", "kind": "domain", "parent_id": "p", "title": "模块一"},
            {"id": "a1", "kind": "task", "parent_id": "M1", "title": "a1", "depends_on": ["M1"]},
            {"id": "a2", "kind": "task", "parent_id": "M1", "title": "a2", "depends_on": ["M1", "a1"]},
            {"id": "M2", "kind": "domain", "parent_id": "p", "title": "模块二"},
            {"id": "c1", "kind": "task", "parent_id": "M2", "title": "旁支 c1", "depends_on": ["M2"]},
        ],
    }


def _write(root: Path, tree: dict) -> None:
    d = root / "projects" / tree["project_id"] / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{tree['plan_id']}.json").write_text(
        json.dumps(tree, ensure_ascii=False, indent=1), encoding="utf-8")


def _check(root: Path) -> list[str]:
    from ai_factory_os.services.work import decomposition as D
    from ai_factory_os.services.work import priority as P

    bad: list[str] = []
    tree = _fixture_tree()
    _write(root, tree)
    nodes = tree["nodes"]

    # ① 自动导出: 关键路径 P0 · 有人等它 P1 · 旁支 P2
    auto = P.auto_from_keypath(nodes)
    if auto["a1"]["priority"] != "P0" or auto["a2"]["priority"] != "P0":
        bad.append(f"关键路径应 P0: {auto['a1']['priority']}/{auto['a2']['priority']}")
    if auto["c1"]["priority"] != "P2":
        bad.append(f"旁支应 P2: {auto['c1']['priority']}（理由: {auto['c1']['reason']}）")
    if auto["a1"]["source"] != "keypath":
        bad.append("自动导出的来源应记 keypath")

    # ② 未落盘 ⇒ 兜底（显示上必须能区分, 别让人以为已排好）
    st = P.stored_stats(nodes)
    if st != {"leaves": 3, "stored": 0, "fallback": 3}:
        bad.append(f"落盘/兜底统计不对: {st}")

    # ③ 值域: 非法值必须抛（静默接受 = 写进一个排不了序的东西）
    try:
        P.normalize("P9")
        bad.append("P9 没被拒（值域守卫失效）")
    except ValueError:
        pass

    # ④ 仲裁: 人工挡自动 · 声明挡自动 · 同级可刷新 · 无来源可写
    m = {"priority_source": "manual"}
    d_ = {"priority_source": "declared"}
    k = {"priority_source": "keypath"}
    cases = [("人工挡 keypath", P.can_apply(m, "keypath"), False),
             ("人工挡 declared", P.can_apply(m, "declared"), False),
             ("声明挡 keypath", P.can_apply(d_, "keypath"), False),
             ("keypath 可刷新 keypath", P.can_apply(k, "keypath"), True),
             ("无来源可写", P.can_apply({}, "keypath"), True)]
    for label, got, want in cases:
        if got != want:
            bad.append(f"仲裁[{label}]: 期望 {want}, 实得 {got}")

    # ⑤ 落盘 + 回候选态
    D.set_node_priority(root, "PLAN-pri", node_id="a1", priority="P0", source="keypath",
                        project_id="P1")
    D.set_node_priority(root, "PLAN-pri", node_id="c1", priority="P1", source="manual",
                        reason="业务要求先做", project_id="P1")
    t2 = D.load_tree(root, "PLAN-pri", "P1")
    if t2 is None:
        return bad + ["读不到刚落盘的树（fixture 或落盘路径坏了）—— 响亮失败, 不静默"]
    a1 = next(n for n in t2["nodes"] if n["id"] == "a1")
    c1 = next(n for n in t2["nodes"] if n["id"] == "c1")
    if a1.get("priority") != "P0" or a1.get("priority_source") != "keypath":
        bad.append(f"落盘不对: {a1.get('priority')}/{a1.get('priority_source')}")
    if c1.get("priority_reason") != "业务要求先做":
        bad.append("人工理由没落盘")
    if t2.get("status") != "candidate":
        bad.append("改完没回候选态（与 edit_node 纪律不一致）")

    # ⑥ 非法值在落盘入口也要拒
    try:
        D.set_node_priority(root, "PLAN-pri", node_id="a2", priority="P9", source="manual",
                            project_id="P1")
        bad.append("落盘入口没拒非法值")
    except ValueError:
        pass

    # ⑦ ★ 真正生效: 调度器端口必须读到刚写进去的值（"设置了没生效"是这类功能的典型死法）
    from ai_factory_os.bootstrap.scheduler_wiring import wire_scheduler

    ports = wire_scheduler(root, plan_id="PLAN-pri", project_id="P1")
    got_a1 = str(ports.work.priority_of("a1"))
    got_c1 = str(ports.work.priority_of("c1"))
    if got_a1 != "P0":
        bad.append(f"调度器没读到 a1 的优先级: {got_a1!r}")
    if got_c1 != "P1":
        bad.append(f"调度器没读到 c1 的优先级: {got_c1!r}")

    # ⑧ 排序: P0 必须排在 P1 前面（用调度器的排序契约, 不另写一套）
    from ai_factory_os.contracts.scheduling import SortKey
    from ai_factory_os.core.scheduler import rank

    ordered = rank.order([(SortKey(priority="P1"), "c1"), (SortKey(priority="P0"), "a1")])
    if ordered != ["a1", "c1"]:
        bad.append(f"排序不对（P0 应在 P1 前）: {ordered}")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description="优先级判据冒烟")
    ap.add_argument("--root", default="", help="额外扫描的真实数据根")
    args = ap.parse_args()

    results: list[tuple[str, bool, str]] = []
    with tempfile.TemporaryDirectory() as td:
        bad = _check(Path(td))
    results.append(("ABC 三来源 · 人工最高 · 值域 · 落到调度器", not bad, "；".join(bad)))

    if args.root:
        from ai_factory_os.services.work import priority as P

        rroot = Path(args.root).expanduser()
        for pf in sorted(rroot.glob("projects/*/tasks/PLAN-*.json")):
            bad2: list[str] = []
            t = json.loads(pf.read_text(encoding="utf-8"))
            for n in t.get("nodes") or []:
                pv = str(n.get("priority") or "").strip()
                if pv and pv not in P.VALID:
                    bad2.append(f"{pf.stem}: 非法优先级 {pv!r} @ {str(n.get('id'))[-8:]}")
                src = str(n.get("priority_source") or "").strip()
                if src and src not in P.SOURCE_RANK:
                    bad2.append(f"{pf.stem}: 非法来源 {src!r} @ {str(n.get('id'))[-8:]}")
            results.append((f"{pf.stem} 优先级值域/来源合法", not bad2, "；".join(bad2)))

    width = max(len(n) for n, _, _ in results)
    fails = 0
    for label, ok, detail in results:
        print(f"   [{'PASS' if ok else 'FAIL'}] {label.ljust(width)}" + (f"   ← {detail}" if detail else ""))
        fails += 0 if ok else 1
    print(f"\n{len(results) - fails}/{len(results)} 通过")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
