"""执行面端到端冒烟 —— 调度器【摊平依赖】的判据（不动 LLM, 确定性）。

【为什么有它（2026-09-20 实跑执行暴露的硬伤）】
  Founder 问"接下来应该是执行了吧" ⇒ 我实跑 `factory run --plan … --limit 1`:
    `轮次 1 · 创建执行 0 个 · 停止原因: 无可推进执行（就绪叶为空）: blocked`
  查根因: 调度器看到的依赖图是【摊平后】的（叶继承其祖先域的依赖, 域依赖摊成该域全部叶）。
  `scheduler_wiring._schedulable_deps` 没把"叶 → 自己的域/祖先"这条当**归属**跳过 ⇒
  每个叶被摊成"依赖自己全部兄弟" ⇒ 同域内两两互相依赖 = 环 ⇒ 永不 READY。
  实测真树: 原始 185 条叶→叶边 → 摊平后 **9158** 条 · **13 个环**（每模块一个） · 199/199 全 BLOCKED。

  ★ 教训: 树上的依赖图看着是 DAG（我此前只查了树里的边）。
    **调度器不读树里的边, 读的是摊平后的边** —— 判"能不能执行"必须查摊平后的图。

跑法: `.venv/bin/python scripts/smoke_exec_dispatch.py`
      `.venv/bin/python scripts/smoke_exec_dispatch.py --root ~/.factory`   # 扫真实数据根
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))


def _node(nid: str, kind: str, parent: str, title: str, *, deps: list[str] | None = None,
          caps: list[str] | None = None) -> dict:
    return {"id": nid, "kind": kind, "parent_id": parent, "title": title,
            "display_name": title, "depends_on": list(deps or []), "scope": "",
            "acceptance": "", "expected_files": [], "required_role": "unassigned",
            "required_capabilities": list(caps or []), "status": "pending"}


def _write(root: Path, tree: dict) -> None:
    d = root / "projects" / tree["project_id"] / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{tree['plan_id']}.json").write_text(
        json.dumps(tree, ensure_ascii=False, indent=1), encoding="utf-8")


def _fixture() -> dict:
    """两模块四叶: M2 依赖 M1; 每个叶都带"指向自己域"的归属依赖（正是会造环的那种树）。"""
    return {
        "plan_id": "PLAN-exec", "project_id": "P1", "status": "confirmed",
        "nodes": [
            _node("p", "project", "", "小项目"),
            _node("M1", "domain", "p", "模块一"),
            _node("a1", "task", "M1", "任务 a1", deps=["M1"]),
            _node("a2", "task", "M1", "任务 a2", deps=["M1", "a1"]),
            _node("M2", "domain", "p", "模块二", deps=["M1"]),
            _node("b1", "task", "M2", "任务 b1", deps=["M2"]),
            _node("b2", "task", "M2", "任务 b2", deps=["M2", "b1"]),
        ],
    }


def _cycles(adj: dict[str, list[str]]) -> list[list[str]]:
    """Tarjan 强连通分量 —— 返回 >1 的分量（= 环）。"""
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
        for w in adj.get(v, []):
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
    for v in adj:
        if v not in index:
            strong(v)
    return [c for c in out if len(c) > 1]


def _schedulable(root: Path, plan_id: str, project_id: str) -> dict[str, list[str]]:
    """调度器真正看到的叶→叶依赖图（走真适配器, 不重写规则）。"""
    from ai_factory_os.bootstrap.scheduler_wiring import wire_scheduler

    ports = wire_scheduler(root, plan_id=plan_id, project_id=project_id)
    nodes = ports.work.list_nodes(task_id=plan_id)
    leaf_set = {str(n.id) for n in nodes}
    # ★ 走 WorkPort 的公开方法拿叶（用私有缓存 = 会在端口重写时静默失联）
    return {str(n.id): [d for d in (n.depends_on or ()) if d in leaf_set] for n in nodes}


def _check(root: Path, plan_id: str, project_id: str, *, label: str,
           fixture: bool = False) -> list[str]:
    """判据（任何树）: 摊平后无环 · 无自依赖。fixture 再加两条语义断言。

    ★ 通用判据只放"任何树都成立"的; fixture 专用断言（根叶零依赖 / 跨域摊成叶）
      必须用 fixture 自己的 id —— 套到真树上是误报（踩过）。
    """
    bad: list[str] = []
    adj = _schedulable(root, plan_id, project_id)
    if not adj:
        return [f"{label}: 摊平后一个叶都没有（读取路径坏了?）"]
    if fixture:
        # ① 归属（指向自己/祖先的 depends_on）不许变成依赖 ⇒ 根叶必须【零依赖】
        if adj.get("a1"):
            bad.append(f"{label}: 根叶 a1 的依赖不为空 = {adj['a1']}（归属被当成依赖 ⇒ 会依赖兄弟）")
        # ② 跨域依赖: M2 的叶必须依赖 M1 的全部叶
        if sorted(adj.get("b1", [])) != ["a1", "a2"]:
            bad.append(f"{label}: M2 的叶未继承 M1 的叶: {adj.get('b1')}")
    # ③ 摊平后无环（★ 就是这个 bug: 13 个环把整棵树卡死）
    cyc = _cycles(adj)
    if cyc:
        bad.append(f"{label}: 摊平后出现 {len(cyc)} 个环, 例: {cyc[0][:4]}")
    # ④ 不许依赖自己
    selfdep = [k for k, v in adj.items() if k in v]
    if selfdep:
        bad.append(f"{label}: 出现自依赖: {selfdep}")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description="执行面冒烟: 调度器摊平依赖的判据")
    ap.add_argument("--root", default="", help="额外扫描的真实数据根（诊断用）")
    args = ap.parse_args()

    import tempfile

    results: list[tuple[str, bool, str]] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        tree = _fixture()
        _write(root, tree)
        bad = _check(root, tree["plan_id"], tree["project_id"], label="两模块四叶", fixture=True)
        results.append(("归属不算依赖 · 跨域摊成叶 · 摊平无环", not bad, "；".join(bad)))

    if args.root:
        rroot = Path(args.root).expanduser()
        for tf in sorted(rroot.glob("projects/*/tasks/PLAN-*.json")):
            try:
                t = json.loads(tf.read_text(encoding="utf-8"))
                pid = str(t.get("project_id") or tf.parents[1].name)
                bad2 = _check(rroot, str(t.get("plan_id") or tf.stem), pid, label=tf.stem)
            except Exception as exc:  # noqa: BLE001 — 单棵树坏了不掩盖其它
                bad2 = [f"{tf.stem}: 读取/解析失败: {type(exc).__name__}: {exc}"]
            results.append((f"{tf.stem} 摊平依赖无环", not bad2, "；".join(bad2)))

    width = max(len(n) for n, _, _ in results)
    fails = 0
    for name, ok, detail in results:
        print(f"   [{'PASS' if ok else 'FAIL'}] {name.ljust(width)}" + (f"   ← {detail}" if detail else ""))
        fails += 0 if ok else 1
    print(f"\n{len(results) - fails}/{len(results)} 通过")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
