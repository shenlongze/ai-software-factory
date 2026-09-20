"""链路接缝 冒烟 —— 环与环之间"接得上吗"。

【为什么有它】全链路实跑（docs/实跑-全链路-20260920.md）暴露一类问题:
  每环单独看都"有入口、能跑", 但**环与环之间的接缝**断了 —— 而且断了不报错, 只是"取不到东西"。
  第一个接缝: 会话事实 → 想法文本（`product develop` 自动取想法）: 键路径写错 ⇒ 永远取不到。

【判据】接缝必须: ①认现网形态 ②兼容旧形态 ③跳过被推翻的 ④缺了要**响亮报错**（不静默）
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))


def _conv(facts: dict | list, *, shape: str) -> dict:
    """造一个会话文件内容: shape=nested(现网) / legacy(旧) 。"""
    if shape == "nested":
        return {"id": "conv-x", "project_id": "P-x", "understanding": {"version": 1, "facts": facts}}
    return {"id": "conv-x", "project_id": "P-x", "facts": facts}


def _write(root: Path, conv: dict) -> None:
    d = root / "projects" / "P-x" / "conversations"
    d.mkdir(parents=True, exist_ok=True)
    (d / "conv-x.json").write_text(json.dumps(conv, ensure_ascii=False), encoding="utf-8")


def _check(root: Path) -> list[str]:
    from apps.cli.commands import CliError
    from apps.cli.main import FactoryContext, _prod_idea_text

    bad: list[str] = []
    ctx = FactoryContext(root=root)
    idea = {"id": "f1", "type": "IDEA", "content": "给自由职业者的记账开票小程序", "status": "PROPOSED"}
    req = {"id": "f2", "type": "REQUIREMENT", "content": "记收支流水", "status": "PROPOSED"}

    # ① 现网形态（understanding.facts 是 dict）—— ★ 这就是实跑踩到的那个
    _write(root, _conv({"f1": idea, "f2": req}, shape="nested"))
    got = _prod_idea_text(ctx, "P-x", None)
    if got != idea["content"]:
        bad.append(f"现网形态取不到想法: {got!r}")

    # ② 兼容旧形态（顶层 facts 是 list）
    _write(root, _conv([idea, req], shape="legacy"))
    got = _prod_idea_text(ctx, "P-x", None)
    if got != idea["content"]:
        bad.append(f"旧形态取不到想法: {got!r}")

    # ③ 被推翻的（SUPERSEDED）不能当依据; 只在有活动想法时才取
    dead = dict(idea, id="f0", content="【被推翻的旧想法】", status="SUPERSEDED")
    _write(root, _conv({"f0": dead, "f1": idea}, shape="nested"))
    got = _prod_idea_text(ctx, "P-x", None)
    if got != idea["content"]:
        bad.append(f"把被推翻的想法当依据了: {got!r}")
    _write(root, _conv({"f0": dead}, shape="nested"))
    try:
        _prod_idea_text(ctx, "P-x", None)
        bad.append("只有被推翻的想法时竟然没报错（静默）")
    except CliError:
        pass

    # ④ 没有任何想法 ⇒ 响亮报错（不许静默返回空串）
    _write(root, _conv({}, shape="nested"))
    try:
        empty = _prod_idea_text(ctx, "P-x", None)
        bad.append(f"无想法竟返回 {empty!r}（应报错）")
    except CliError:
        pass

    # ⑤ 显式 --idea 最优先（不需要会话）
    if _prod_idea_text(ctx, "P-x", "手写的想法") != "手写的想法":
        bad.append("--idea 没能优先")
    return bad


def _check_views_see_tree(root: Path) -> list[str]:
    """★ 监控必须看得见执行（卡点 1）: 任务树里有叶 ⇒ status/metrics/kanban 必须报出来。

    实测踩到: 执行走【任务树】, 而 status/task list/kanban/metrics 读【任务域】⇒ 显示 0。
    这里直接问那几个命令的**返回值**（不看文案）, 断言数字与树一致。
    """
    from apps.cli.commands import cmd_metrics, cmd_status
    from apps.cli.main import FactoryContext, _task_rows
    from ai_factory_os.services.work import progress as P

    bad: list[str] = []
    tree = {
        "plan_id": "PLAN-v", "project_id": "P-v", "status": "confirmed",
        "nodes": [
            {"id": "p", "kind": "project", "parent_id": "", "title": "项目"},
            {"id": "M", "kind": "domain", "parent_id": "p", "title": "模块"},
            {"id": "L1", "kind": "task", "parent_id": "M", "title": "做完了的叶", "status": "completed"},
            {"id": "L2", "kind": "task", "parent_id": "M", "title": "没做的叶", "status": "pending"},
        ],
    }
    d = root / "projects" / "P-v" / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    (d / "PLAN-v.json").write_text(json.dumps(tree, ensure_ascii=False), encoding="utf-8")
    ctx = FactoryContext(root=root)

    # ① 投影本身
    sm = P.summary(root)
    if (sm["leaves"], sm["done"], sm["projects"]) != (2, 1, ["P-v"]):
        bad.append(f"progress.summary 不对: {sm}")

    # ② status 必须报出开发任务与项目
    st = cmd_status(ctx)
    if st.get("projects") != ["P-v"]:
        bad.append(f"status 看不到项目: {st.get('projects')}")
    if (st.get("dev_tasks") or {}).get("leaves") != 2:
        bad.append(f"status 看不到开发任务: {(st.get('dev_tasks') or {}).get('leaves')}")

    # ③ metrics 必须带 tasks_tree
    mt = cmd_metrics(ctx, _ns_metrics())
    if (mt.get("tasks_tree") or {}).get("leaves") != 2:
        bad.append(f"metrics 看不到开发任务: {(mt.get('tasks_tree') or {}).get('leaves')}")

    # ④ kanban/task list 的那份任务行必须含叶（且状态已映射到看板词）
    ids = {str(r.get("id")) for r in _task_rows(root)}
    if not {"L1", "L2"} <= ids:
        bad.append(f"任务行里没有树上的叶: {sorted(ids)[:5]}")
    st_map = {str(r.get("id")): str(r.get("status")) for r in _task_rows(root)}
    if st_map.get("L1") != "done" or st_map.get("L2") != "todo":
        bad.append(f"叶状态没映射到看板词: L1={st_map.get('L1')} L2={st_map.get('L2')}")
    return bad


def _ns_metrics():
    from types import SimpleNamespace
    return SimpleNamespace(workspace=False, project=None, metrics_command="", json=False)


def test_monitoring_sees_execution(tmp_path: Path) -> None:
    """监控看得见执行: 任务树的叶必须出现在 status / metrics / kanban(任务行) 里。"""
    assert _check_views_see_tree(tmp_path) == []


def _check_state_semantics(root: Path) -> list[str]:
    """★ 执行状态语义（卡点 3）: 环境性失败要能重试但不能空转 · 完成必须留产出证据。

    实测踩过的两种病:
      · 一律 cancelled ⇒ 缺 runtime / provider 抖一下, 任务**永久终止、不可重试**
      · 一律 pending   ⇒ 归还后被再调度 ⇒ 打满 max_ticks + 每轮新建执行（cr-4: 13 叶 50 个执行）
    """
    from ai_factory_os.bootstrap.scheduler_pump import _MAX_RETRY, _on_failure
    from ai_factory_os.services.work import decomposition as D
    from ai_factory_os.services.work import progress as P

    bad: list[str] = []
    # ① 重试决策: 未到上限 ⇒ 交回 pending; 到上限 ⇒ 终止（防空转）
    for tries in range(_MAX_RETRY):
        st, _n = _on_failure(tries)
        if st != "pending":
            bad.append(f"第 {tries} 次失败应回 pending 重试, 实得 {st}")
    st, note = _on_failure(_MAX_RETRY)
    if st != "cancelled" or not note:
        bad.append(f"到上限({_MAX_RETRY})应终止并写明原因, 实得 {st} / {note!r}")

    # ② 树: 交回重试 ⇒ retry_count+1 + 写明原因; 终态 ⇒ 清掉计数
    tree = {"plan_id": "PLAN-s", "project_id": "P-s", "status": "confirmed",
            "nodes": [{"id": "p", "kind": "project", "parent_id": "", "title": "项目"},
                      {"id": "M", "kind": "domain", "parent_id": "p", "title": "模块"},
                      {"id": "L1", "kind": "task", "parent_id": "M", "title": "叶", "status": "claimed"}]}
    d = root / "projects" / "P-s" / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    (d / "PLAN-s.json").write_text(json.dumps(tree, ensure_ascii=False), encoding="utf-8")
    D.release_leaf(root, "PLAN-s", "L1", status="pending", project_id="P-s", note="第 1 次失败 ⇒ 交回")
    leaf = D.get_leaf(root, "PLAN-s", "L1", project_id="P-s") or {}
    if leaf.get("retry_count") != 1 or not leaf.get("status_note"):
        bad.append(f"交回重试没记计数/原因: retry_count={leaf.get('retry_count')} note={leaf.get('status_note')!r}")
    if leaf.get("status") != "pending" or leaf.get("claimed_by"):
        bad.append(f"交回后状态/认领没清: {leaf.get('status')} claimed_by={leaf.get('claimed_by')}")

    # ③ 产出证据: 无改动 ⇒ verify_needed（待核）; 有改动 ⇒ 干净完成
    D.set_node_evidence(root, "PLAN-s", "L1", evidence="no-change", verify_needed=True, project_id="P-s")
    if (P.summary(root).get("verify_needed") or 0) != 1:
        bad.append("无产出证据的完成没被标进 verify_needed（进度会把它当'真做完了'）")
    D.set_node_evidence(root, "PLAN-s", "L1", evidence="repo-changed", verify_needed=False, project_id="P-s")
    if (P.summary(root).get("verify_needed") or 0) != 0:
        bad.append("有产出证据后 verify_needed 没清掉")

    # ④ 终态要把重试计数清掉（否则下次改任务会带着旧计数）
    D.release_leaf(root, "PLAN-s", "L1", status="completed", project_id="P-s")
    leaf2 = D.get_leaf(root, "PLAN-s", "L1", project_id="P-s") or {}
    if leaf2.get("retry_count") is not None:
        bad.append(f"终态没清 retry_count: {leaf2.get('retry_count')}")
    return bad


def test_execution_state_semantics(tmp_path: Path) -> None:
    """执行状态语义: 失败可重试(带上限) · 完成留证据(无证据 ⇒ 待核) · 终态清计数。"""
    assert _check_state_semantics(tmp_path) == []


def test_conv_facts_reach_product_develop(tmp_path: Path) -> None:
    """接缝: 会话事实 → 想法文本（两种存法 + 跳过被推翻 + 缺了报错 + --idea 优先）。"""
    assert _check(tmp_path) == []


def main() -> int:
    results: list[tuple[str, bool, str]] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        bad1 = _check(root)
        bad2 = _check_views_see_tree(root)
        bad3 = _check_state_semantics(root)
    results.append(("会话事实 → 想法文本", not bad1, "；".join(bad1)))
    results.append(("监控看得见执行（树 → status/metrics/看板）", not bad2, "；".join(bad2)))
    results.append(("执行状态语义（可重试 / 完成留证据）", not bad3, "；".join(bad3)))
    width = max(len(n) for n, _, _ in results)
    fails = 0
    for label, ok, detail in results:
        print(f"   [{'PASS' if ok else 'FAIL'}] {label.ljust(width)}" + (f"   ← {detail}" if detail else ""))
        fails += 0 if ok else 1
    print(f"\n{len(results) - fails}/{len(results)} 通过")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
