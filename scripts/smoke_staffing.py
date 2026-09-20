"""派工（谁做）冒烟 —— 判据 + ★ 决定性一条: 声明后调度器必须判 READY。

【为什么有它】Founder "接下来应该是执行了吧" ⇒ 实跑 `run --plan`: 创建执行 0 个。
  根因: 全树 required_capabilities 全空 ⇒ 调度器 `unresolved: 未声明 required_capability_refs`
  ⇒ 一个叶也派不出去。本冒烟守的就是"声明之后能不能派出去"这条链。

【★ 两处必须机器守（都踩过）】
  ① 匹配规则: 调度器拿节点 `required_capabilities` 与**成员角色**求交集（`OrgResource.resolution_for`
     里写的是 `{m.role_ids}`）—— 注释说 "skill 命中", 与代码不符 ⇒ 值必须是【真实角色名】。
  ② 级联: 调度器读的是**叶自己**的字段 ⇒ 声明在模块上不会继承, 必须级联写到子叶
     （否则"模块有角色、叶还是空"⇒ 依旧 unresolved）。

跑法: `.venv/bin/python scripts/smoke_staffing.py` · 加 `--root ~/.factory` 扫真根
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
    return {
        "plan_id": "PLAN-st", "project_id": "P1", "status": "confirmed",
        "nodes": [
            {"id": "p", "kind": "project", "parent_id": "", "title": "项目"},
            {"id": "M1", "kind": "domain", "parent_id": "p", "title": "模块一", "depends_on": []},
            {"id": "a1", "kind": "task", "parent_id": "M1", "title": "a1",
             "depends_on": ["M1"], "status": "pending"},
            {"id": "a2", "kind": "task", "parent_id": "M1", "title": "a2",
             "depends_on": ["M1", "a1"], "status": "pending"},
        ],
    }


def _write_tree(root: Path, tree: dict) -> None:
    d = root / "projects" / tree["project_id"] / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{tree['plan_id']}.json").write_text(
        json.dumps(tree, ensure_ascii=False, indent=1), encoding="utf-8")


def _write_fleet(root: Path, roles: list[str]) -> None:
    """造一份**真成员文件**（与调度器读的同一路径）—— 角色清单只有这一处来源。"""
    d = root / "agents"
    d.mkdir(parents=True, exist_ok=True)
    rows = [{"id": f"agent-{i}", "name": f"员工{i}", "role": r, "status": "AVAILABLE",
             "skills": ["general"]} for i, r in enumerate(roles, 1)]
    (d / "agents.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def _decide(root: Path) -> dict[str, str]:
    """跑真调度器一次 ⇒ {叶 id: kind}（不看文档, 看它实际判什么）。"""
    from ai_factory_os.bootstrap.scheduler_wiring import wire_scheduler
    from ai_factory_os.core.scheduler.loop import tick

    ports = wire_scheduler(root, plan_id="PLAN-st", project_id="P1")
    return {str(d.task_node_id): str(d.kind.value) for d in tick(ports).decisions}


def _check(root: Path) -> list[str]:
    from ai_factory_os.services.work import decomposition as D
    from ai_factory_os.services.work import staffing as ST

    bad: list[str] = []
    tree = _fixture_tree()
    _write_tree(root, tree)
    _write_fleet(root, ["developer", "tester", "architect"])

    # ① 角色清单来自真成员文件（不是常量表）
    cat = ST.role_catalog(root)
    if cat != {"developer": 1, "tester": 1, "architect": 1}:
        bad.append(f"角色清单不对: {cat}")

    # ② 值域: 清单外的丢弃 + 计数; 大小写不敏感; role 兜底填 caps
    role, caps, dropped = ST.parse_staffing("Developer", ["DEVELOPER", "白造的角色"], cat)
    if role != "developer" or caps != ["developer"] or dropped != ["白造的角色"]:
        bad.append(f"parse_staffing 不对: role={role} caps={caps} dropped={dropped}")
    role2, caps2, _ = ST.parse_staffing("tester", [], cat)
    if role2 != "tester" or caps2 != ["tester"]:
        bad.append(f"role 未兜底填 capabilities（会仍然 unresolved）: {role2}/{caps2}")

    # ③ ★ 声明前: 调度器必须判 unresolved（这就是"一个叶也派不出去"的原因）
    before = _decide(root)
    if "unresolved" not in set(before.values()):
        bad.append(f"未声明时调度器竟然不是 unresolved: {before}")

    # ④ ★★ 级联: 声明在【模块】上, 子叶也必须拿到（调度器读叶自己的字段）
    D.set_node_staffing(root, "PLAN-st", node_id="M1", role="developer",
                        capabilities=["developer"], project_id="P1")
    t2 = D.load_tree(root, "PLAN-st", "P1")
    if t2 is None:
        return bad + ["读不到刚落盘的树（落盘路径坏了）—— 响亮失败, 不静默"]
    for n in t2["nodes"]:
        if n.get("kind") == "task" and n.get("required_capabilities") != ["developer"]:
            bad.append(f"级联失败: 叶 {n.get('id')} 没拿到 required_capabilities")

    # ⑤ ★★★ 决定性: 声明后调度器必须判 READY（且匹配到成员）
    from ai_factory_os.bootstrap.scheduler_wiring import wire_scheduler
    from ai_factory_os.core.scheduler.loop import tick

    ports = wire_scheduler(root, plan_id="PLAN-st", project_id="P1")
    dec = {str(d.task_node_id): d for d in tick(ports).decisions}
    a1 = dec.get("a1")
    if a1 is None or str(a1.kind.value) != "ready":
        bad.append(f"声明后根叶仍不是 READY: {a1.kind.value if a1 else '缺决策'}"
                   f"（failed={a1.failed_conditions if a1 else '-'}）")
    elif not a1.member_id:
        bad.append("READY 但没匹配到成员（member_id 空）")
    # 下游叶仍应被前驱挡住（不许因为能派就跳过依赖）
    a2 = dec.get("a2")
    if a2 is not None and str(a2.kind.value) != "blocked":
        bad.append(f"下游叶 a2 不应 READY（依赖未满足）: {a2.kind.value}")
    return bad


def test_staffing_unblocks_dispatch(tmp_path: Path) -> None:
    """派工: 角色清单来自真成员文件 · 值域 · 级联到叶 · ★ 声明后调度器判 READY。"""
    assert _check(tmp_path) == []


def main() -> int:
    ap = argparse.ArgumentParser(description="派工判据冒烟")
    ap.add_argument("--root", default="", help="额外扫描的真实数据根")
    args = ap.parse_args()

    results: list[tuple[str, bool, str]] = []
    with tempfile.TemporaryDirectory() as td:
        bad = _check(Path(td))
    results.append(("角色清单·值域·级联·声明后判 READY", not bad, "；".join(bad)))

    if args.root:
        from ai_factory_os.services.work import staffing as ST

        rroot = Path(args.root).expanduser()
        cat = ST.role_catalog(rroot)
        results.append((f"真根角色清单可读（{len(cat)} 个角色）", bool(cat),
                        "" if cat else "读不到成员文件 —— 调度器将无法解析成员"))

    width = max(len(n) for n, _, _ in results)
    fails = 0
    for label, ok, detail in results:
        print(f"   [{'PASS' if ok else 'FAIL'}] {label.ljust(width)}" + (f"   ← {detail}" if detail else ""))
        fails += 0 if ok else 1
    print(f"\n{len(results) - fails}/{len(results)} 通过")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
