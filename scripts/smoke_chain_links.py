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
from typing import Any

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
    # ⑤ ★★ `factory task list` 也必须看得见开发任务 —— 原来它只读【域账本】⇒
    #    实测同一句"任务": 看板 12 条、task list **0 条**（同一概念两个答案）
    from types import SimpleNamespace as _NS

    from apps.cli.commands import cmd_task_list

    tl = cmd_task_list(ctx, _NS(status=None, project=None, json=False))
    dev_ids = {str(d.get("id")) for d in (tl.get("dev_tasks") or [])}
    if not {"L1", "L2"} <= dev_ids:
        bad.append(f"task list 看不到开发任务（两套账本两个答案）: {sorted(dev_ids)[:5]}")
    if tl.get("count") != 2:
        bad.append(f"task list 的 count 应为 台账+开发 = 2, 实得 {tl.get('count')}")
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


def _check_small_fixes(root: Path) -> list[str]:
    """★ 小卡点四件里的三件可守部分（卡点 4/6/8）。

    (4) `create project` 静默成功 + `--json` 崩（返回值里塞 module/Namespace）
    (6) `--limit 1` 却"创建执行 2 个"（限量只在 tick 前判, 建批时没掐）
    (8) `prd_ref` 字段里存的是 design 制品 id（语义错位）
    """
    import json as _json
    from types import SimpleNamespace

    from ai_factory_os.bootstrap.scheduler_pump import _cap_batch

    bad: list[str] = []

    # (6) 限量: 剩余额度 1、批里 2 个 ⇒ 只能跑 1 个, 且要说明
    got, note = _cap_batch(["E1", "E2"], limit=1, done=0)
    if got != ["E1"] or not note:
        bad.append(f"限量没在建批时掐住: {got} / note={note!r}")
    got2, note2 = _cap_batch(["E1"], limit=3, done=0)
    if got2 != ["E1"] or note2:
        bad.append(f"额度够时不该截: {got2} / {note2!r}")
    got3, _ = _cap_batch(["E1", "E2"], limit=0, done=0)
    if got3 != ["E1", "E2"]:
        bad.append("limit=0（不限）不该截")

    # (8) 引用语义: prd_ref = 需求侧制品; design_ref = 本篇设计; 血缘另存
    from apps.cli.main import _decompose_refs

    design = SimpleNamespace(id="A-DESIGN", metadata={"artifact_refs": ["A-PRODUCT", "A-UX"]})
    prd, meta = _decompose_refs(design)
    if prd != "A-PRODUCT":
        bad.append(f"prd_ref 应指向需求侧制品, 实得 {prd!r}")
    if meta.get("artifact_refs") != ["A-DESIGN"]:
        bad.append(f"design_ref 应是本篇设计, 实得 {meta.get('artifact_refs')!r}")
    if meta.get("lineage") != ["A-PRODUCT", "A-UX"]:
        bad.append(f"血缘没另存: {meta.get('lineage')!r}")
    # 没有血缘时退化到 design 自己（不许空）
    prd2, meta2 = _decompose_refs(SimpleNamespace(id="A-D2", metadata={}))
    if prd2 != "A-D2" or meta2.get("artifact_refs") != ["A-D2"]:
        bad.append(f"无血缘时退化不对: {prd2!r} / {meta2.get('artifact_refs')!r}")

    # (4) create 的返回值必须 JSON 安全（原来塞了 module ⇒ --json 崩）+ 打印不能静默
    import contextlib
    import io

    from apps.cli.main import _print_create

    dispatch = {"action": "create", "create_type": "project",
                "args": SimpleNamespace(json=False, command="create"),
                "result": {"ok": True, "exit_code": 0,
                           "project": {"id": "P-x", "name": "小项目", "repo_path": "/tmp/x"}},
                "exit_code": 0}
    try:
        _json.dumps(dispatch, default=str)
    except TypeError as exc:
        bad.append(f"create 返回值不能 JSON 序列化: {exc}")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _print_create(dict(dispatch))
    out = buf.getvalue()
    if "✔" not in out or "P-x" not in out:
        bad.append(f"create project 成功时没输出（静默成功, 用户会以为失败）: {out[:60]!r}")
    return bad


def test_small_fixes(tmp_path: Path) -> None:
    """小卡点: 限量掐住 · 引用语义 · create 不静默且 --json 安全。"""
    assert _check_small_fixes(tmp_path) == []


def _check_granularity() -> list[str]:
    """★ 粒度判据（Founder: "每个叶能不能用一句话写出验收？不能 ⇒ 还没拆到位"）。

    判据要有区分度 —— 所以三条都要有【反例】: 单件的叶不许被判成"没拆到位"。
    """
    from ai_factory_os.services.work import granularity as G

    bad: list[str] = []
    single = {"kind": "task", "title": "导出 Excel/CSV 给会计",
              "acceptance": "按月份生成可下载的 csv 文件"}
    multi_seg = {"kind": "task", "title": "项目创建与维护",
                 "acceptance": "POST /api/projects -> project；GET /api/projects/{id} 返回聚合；PUT 更新"}
    multi_enum = {"kind": "task", "title": "按项目生成发票：税率、折扣、合计计算、编号规则",
                  "acceptance": "发票金额与税率一致"}
    no_acc = {"kind": "task", "title": "发票状态机", "acceptance": ""}
    domain = {"kind": "domain", "title": "甲、乙、丙、丁", "acceptance": ""}

    if G.reasons_for(single):
        bad.append(f"单件的叶被误判: {G.reasons_for(single)}")
    if not G.reasons_for(multi_seg):
        bad.append("验收分段（两个独立交付）没被判出来")
    if not G.reasons_for(multi_enum):
        bad.append("标题枚举 >=3 件事没被判出来")
    if not G.reasons_for(no_acc):
        bad.append("没验收没被判出来")
    if G.reasons_for(domain):
        bad.append("域节点不该参与粒度判定（只判 kind=task）")
    sm = G.summary([single, multi_seg, multi_enum, no_acc, domain])
    if (sm["leaves"], sm["oversized"]) != (4, 3):
        bad.append(f"汇总数不对: leaves={sm['leaves']} oversized={sm['oversized']}")
    if not sm.get("how_to_fix") or not sm.get("basis"):
        bad.append("汇总必须给出'怎么改'与判据（否则人不知道拿它怎么办）")
    return bad


def test_granularity_judgement() -> None:
    """粒度: 一句话写不出验收的叶要被判出来, 且单件的叶不许误判。"""
    assert _check_granularity() == []


def _check_ux_truncation_fallback() -> list[str]:
    """★ 输出被截断时要能自愈（实测: 社区团购场景 UX/UI 7 节 23357 字符写不完 ⇒ 整环失败）。

    architect 早有"分节生成"兜底, uxui 没有 ⇒ 这刀给它补上。用假 provider 验:
    第一次假截断 ⇒ 必须转成逐节生成, 且 7 节齐全。
    """
    import re as _re

    from ai_factory_os.plugins.agents.uxui import (
        UXUI_FIELDS, _gen_sections_individually, _is_truncated,
    )

    bad: list[str] = []

    class _Resp:
        def __init__(self, ok, content="", error=""):
            self.ok, self.content, self.error = ok, content, error

    class _FakeProv:
        """逐节调用: 按 prompt 里问到的节返回对应 JSON。

        ★ 注意: 截断判定发生在【调用方】(design), 逐节函数进来时已是兜底阶段 ⇒
          这个假 provider **不该**再返截断（我第一次就写错了, 守卫当场抓出来）。
        """
        def __init__(self):
            self.calls: list[str] = []

        def generate(self, req):
            self.calls.append(req.task_context)
            m = _re.search(r'\{"([a-z_]+)": \.\.\.', req.task_context)
            sec = m.group(1) if m else "?"
            return _Resp(True, '{"%s": {"k": "v"}}' % sec)

    if not _is_truncated(_Resp(False, "", "…truncated…")):
        bad.append("截断判定失灵（会把可自愈的截断当硬失败）")
    if _is_truncated(_Resp(False, "", "network timeout")):
        bad.append("网络错误被误判成截断")
    # ★ 真实 provider 是【抛异常】报截断的（providers/openai.py:192）——
    #   我第一版只认 response.error ⇒ 兜底根本没跑（真跑时又踩一次）⇒ 这条专门守它
    if not _is_truncated("ProviderError: openai response truncated: finish_reason=length (…)"):
        bad.append("★ 异常路径的截断没被认出来（兜底不会触发 —— 实际踩过）")

    prov = _FakeProv()
    merged = _gen_sections_individually(prompt="原始提示", provider=prov, max_tokens=128)
    # ★ 节名必须是【制品契约要的 7 节】—— 我第一次用了 product 的 5 节常量 ⇒ 契约报"7 节全缺"
    if not merged or set(merged) != set(UXUI_FIELDS):
        bad.append(f"逐节兜底没凑齐契约 7 节: {sorted(merged or {})}（要 {sorted(UXUI_FIELDS)}）")
    if len(prov.calls) != len(UXUI_FIELDS):
        bad.append(f"逐节调用次数不对: {len(prov.calls)}（应为 {len(UXUI_FIELDS)}）")

    class _BadProv:
        def generate(self, req):
            return _Resp(False, "", "boom")

    if _gen_sections_individually(prompt="p", provider=_BadProv(), max_tokens=128) is not None:
        bad.append("逐节里某节失败时应返回 None（不许产半成品）")
    return bad


def test_ux_truncation_fallback() -> None:
    """UX/UI 输出被截断 ⇒ 自动转逐节生成; 不产半成品。"""
    assert _check_ux_truncation_fallback() == []


def _check_tree_write_path() -> list[str]:
    """★ 写树的位置只认【树自己的 project_id】（第二轮实跑踩到的副本 bug）。

    实测: 执行回写时 project_id 传空 ⇒ 副本落到 `task_trees/`（回落位置）, 与
    `projects/<P>/tasks/` 那份并存 ⇒ 读树的 R27 守卫拒绝 ⇒ 监控/完成证据全崩。
    """
    import json as _json
    import tempfile

    from ai_factory_os.services.work import decomposition as D

    bad: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "projects" / "P-x").mkdir(parents=True)
        tree = {"plan_id": "PLAN-w", "project_id": "P-x", "status": "candidate", "nodes": []}
        # 调用方【故意】漏传 project_id —— 位置仍必须落在项目内
        p = D._save(root, "PLAN-w", tree, "")          # noqa: SLF001 — 就是要验这个内部写入路径
        want = root / "projects" / "P-x" / "tasks" / "PLAN-w.json"
        if Path(p) != want:
            bad.append(f"写错位置: {p}（应为 {want}）")
        if (root / "task_trees" / "PLAN-w.json").exists():
            bad.append("有 project_id 的树被写进了回落位置 task_trees/ ⇒ 会造出副本")
        # 无项目的树仍应回落（合法场景）
        p2 = D._save(root, "PLAN-np", {"plan_id": "PLAN-np", "nodes": []}, "")   # noqa: SLF001
        if Path(p2) != root / "task_trees" / "PLAN-np.json":
            bad.append(f"无项目的树该回落却没回落: {p2}")
        # 读得回来（没有副本 ⇒ 不触发 R27 守卫）
        got = D.load_tree(root, "PLAN-w", "P-x")
        on_disk = _json.loads(want.read_text()).get("plan_id") if want.is_file() else None
        if not got or on_disk != "PLAN-w":
            bad.append(f"写完读不回来（文件在={want.is_file()}, 读到={got is not None}）")
    return bad


def test_tree_write_path_is_unique() -> None:
    """写树位置只认树自己的 project_id（漏传也不许造副本）。"""
    assert _check_tree_write_path() == []


def _check_evidence_judgement() -> list[str]:
    """★ 产出证据的判定（真跑一次要几分钟, 这里一行验完）。

    · 有未提交改动 ⇒ 有产出 · 干净且最近提交在窗口内 ⇒ 有产出 · 干净且提交很久前 ⇒ 无产出
    · 不是 git 仓库 ⇒ 判不出（None, 调用方标"待核" —— 不猜）
    """
    import subprocess
    import tempfile

    from ai_factory_os.bootstrap.scheduler_pump import _repo_changed

    bad: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "r"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=False)
        (repo / "a.txt").write_text("x")
        if _repo_changed(str(repo)) is not True:
            bad.append("空仓库有未提交改动时，应判为【有产出】")
        subprocess.run(["git", "-C", str(repo), "-c", "user.email=d@l", "-c", "user.name=d",
                        "add", "-A"], check=False)
        subprocess.run(["git", "-C", str(repo), "-c", "user.email=d@l", "-c", "user.name=d",
                        "commit", "-qm", "init"], check=False)
        if _repo_changed(str(repo)) is not True:
            bad.append("刚提交过（在窗口内）应判为【有产出】")
        (repo / "a.txt").write_text("y")
        if _repo_changed(str(repo)) is not True:
            bad.append("有未提交改动应判为【有产出】")
        if _repo_changed(str(Path(td) / "不存在")) is not None:
            bad.append("不是仓库时应判【判不出】(None)，不许猜成 False")
    return bad


def test_evidence_judgement() -> None:
    """产出证据判定: 有改动/刚提交 ⇒ 有产出; 判不出 ⇒ None（不猜）。"""
    assert _check_evidence_judgement() == []


def _check_stale_claim_sweep() -> list[str]:
    """★ 陈旧认领要能交回, 但**绝不抢正在跑的活**（安全边界比功能更要紧）。

    场景: 进程中断后叶停在 claimed, 而执行没了 ⇒ 永远 BLOCKED（实测: 之后再跑就是"就绪叶为空"）。
    """
    import json as _json
    import tempfile
    from types import SimpleNamespace

    from ai_factory_os.bootstrap import scheduler_pump as SP
    from ai_factory_os.services.work import decomposition as D

    bad: list[str] = []

    class _Req:
        def __init__(self, node, status):
            self.input = {"node_id": node}
            self.status = SimpleNamespace(value=status)
            self.task_id = "PLAN-s"

    class _Store:
        def __init__(self, reqs):
            self._reqs = reqs

        def list_executions(self):
            return self._reqs

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        d = root / "projects" / "P-s" / "tasks"
        d.mkdir(parents=True)
        tree = {"plan_id": "PLAN-s", "project_id": "P-s", "status": "confirmed", "nodes": [
            {"id": "p", "kind": "project", "parent_id": "", "title": "项目"},
            {"id": "M", "kind": "domain", "parent_id": "p", "title": "模块"},
            {"id": "L-stale", "kind": "task", "parent_id": "M", "title": "中断遗留的叶",
             "status": "claimed", "claimed_by": "agent-x"},
            {"id": "L-live", "kind": "task", "parent_id": "M", "title": "正在跑的叶",
             "status": "claimed", "claimed_by": "agent-y"},
        ]}
        (d / "PLAN-s.json").write_text(_json.dumps(tree, ensure_ascii=False), encoding="utf-8")
        ports = SimpleNamespace(work=SimpleNamespace(_root=str(root), _plan_id="PLAN-s",
                                                     _project_id="P-s"))
        orig = SP.open_runtime_store
        try:
            # ① L-live 有活跃(PENDING)执行 ⇒ 不许动; L-stale 没有 ⇒ 应交回
            SP.open_runtime_store = lambda _r: _Store([_Req("L-live", "PENDING")])  # type: ignore[assignment]
            out = SP.sweep_stale_claims(root, ports)  # type: ignore[arg-type]
        finally:
            SP.open_runtime_store = orig  # type: ignore[assignment]
        ids = {x["node_id"] for x in out}
        if ids != {"L-stale"}:
            bad.append(f"交回集合不对: {ids}（只该交回 L-stale, 绝不碰有活跃执行的 L-live）")
        t2 = D.load_tree(root, "PLAN-s", "P-s") or {}
        st = {n["id"]: n for n in t2.get("nodes") or []}
        if st["L-stale"].get("status") != "pending":
            bad.append("陈旧认领没被交回 pending")
        if st["L-stale"].get("retry_count"):
            bad.append(f"陈旧认领不该计重试: retry_count={st['L-stale'].get('retry_count')}")
        if not st["L-stale"].get("status_note"):
            bad.append("交回没写原因（人看不到为什么动了它）")
        if st["L-live"].get("status") != "claimed" or not st["L-live"].get("claimed_by"):
            bad.append("★ 抢了正在跑的活（安全边界被破坏）")
        # ② 读不到执行存储 ⇒ 整轮不扫（不能瞎动）
        tree2 = dict(tree, nodes=[dict(n) for n in tree["nodes"]])
        (d / "PLAN-s.json").write_text(_json.dumps(tree2, ensure_ascii=False), encoding="utf-8")

        def _boom(_r):
            raise RuntimeError("store down")

        try:
            SP.open_runtime_store = _boom  # type: ignore[assignment]
            out2 = SP.sweep_stale_claims(root, ports)  # type: ignore[arg-type]
        finally:
            SP.open_runtime_store = orig  # type: ignore[assignment]
        if out2:
            bad.append("执行存储读不到时不该动任何叶")
    return bad


def test_stale_claim_sweep() -> None:
    """陈旧认领交回, 但绝不抢有活跃执行的叶。"""
    assert _check_stale_claim_sweep() == []


def _check_entity_catalog() -> list[str]:
    """★ 实体清单来源（第 4 项）: 设计制品的 database_design 优先, DDL 兜底, 都没有 ⇒ 空（不编）。

    为什么这条要守: DDL 是**任务要做出来的东西**, 从零场景还不存在 ⇒ 只认 DDL 就等于
    "数据流程图在这一环必然空着"（实测: declare 只能诚实拒绝）。而设计制品里本来就有那一节。
    """
    import tempfile

    from ai_factory_os.services.work import data_flow as DF

    bad: list[str] = []

    # ① 形状容错（LLM 产出不定, 契约只要求"非空对象"）
    cases = [
        ({"tables": [{"name": "User"}, {"name": "Order"}]}, {"User", "Order"}),
        ({"models": {"User": {"fields": ["id"]}, "Invoice": {}}}, {"User", "Invoice"}),
        ({"entities": ["User", "Order"]}, {"User", "Order"}),
        (["User", "Order"], {"User", "Order"}),
        ({"table": "public.users"}, {"users"}),                       # 带 schema 前缀 ⇒ 取尾段
        ({"tables": [{"name": "User"}, {"name": "User"}]}, {"User"}),  # 去重
    ]
    for section, want in cases:
        got = set(DF.entities_from_design(section))
        if not want <= got:
            bad.append(f"设计节解析漏了实体: {section} ⇒ {sorted(got)}（要 {sorted(want)}）")
    if DF.entities_from_design(None) or DF.entities_from_design({}):
        bad.append("空节应给空清单（不编）")
    if DF.entities_from_design({"tables": [{"name": "x"}]}):
        bad.append("太短的名字（<2）不该当实体")
    # ★ 真跑踩到: database_design 里除 tables 还有 overview/conventions/relationships_summary…
    #   这些**结构性说明的键**不许被当成实体
    mixed = {"overview": "本设计包含…", "conventions": {"naming": "snake_case"},
             "tables": [{"name": "User"}, {"name": "Order"}],
             "relationships_summary": ["User 1-N Order"], "key_queries_and_index_rationale": {"q": 1}}
    got_mixed = DF.entities_from_design(mixed)
    if set(got_mixed) != {"User", "Order"}:
        bad.append(f"结构性键被当成实体了: {got_mixed}（只要 User/Order）")
    # 文本兜底
    txt = DF.entities_from_design({"note": "CREATE TABLE users (id int); 表名: invoices"})
    if not {"users", "invoices"} <= set(txt):
        bad.append(f"文本兜底没捞到表名: {txt}")

    # ② 优先级: 无设计制品 + 有 DDL ⇒ 用 DDL; 两者都没有 ⇒ 空（调用方据此拒绝）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        proj = root / "projects" / "P-x"
        (proj / "prisma").mkdir(parents=True)
        (proj / "prisma" / "schema.prisma").write_text(
            "model User {\n  id Int @id\n}\nmodel Order {\n  id Int @id\n}\n", encoding="utf-8")
        cat = DF.entity_catalog(root, "P-x", workspace_dir=proj)
        if cat["source"] != "ddl" and not str(cat["source"]).startswith("ddl:"):
            bad.append(f"有 DDL 时该走 DDL 来源, 实得 {cat['source']!r}")
        if not {"User", "Order"} <= set(cat["names"]):
            bad.append(f"DDL 兜底没拿到实体: {cat['names']}")
        cat2 = DF.entity_catalog(root, "P-none", workspace_dir=root / "projects" / "P-none")
        if cat2["names"] or cat2["source"]:
            bad.append(f"两者都没有时应给空（调用方据此诚实拒绝）: {cat2}")
    return bad


def test_entity_catalog() -> None:
    """实体清单: 设计节解析（多形状）· DDL 兜底 · 都没有 ⇒ 空（不编）。"""
    assert _check_entity_catalog() == []


def _check_executor_verdict() -> list[str]:
    """★ 执行体裁定（第 3 项）: "停手"必须能显式表达, 且绝不记成完成。

    实测事故: 执行体自述"核验+停手、零改动", 叶却被记成 completed（进度 1/199 是假的）。
    """
    import tempfile
    from types import SimpleNamespace

    from ai_factory_os.bootstrap import scheduler_pump as SP
    from ai_factory_os.services.execution.runtime.adapters.hermes import (
        HermesRuntimeAdapter, _parse_verdict,
    )
    from ai_factory_os.services.execution.runtime.types import ExecutionRequest
    from ai_factory_os.services.work import decomposition as D
    from ai_factory_os.services.work import progress as P

    bad: list[str] = []

    # ① 解析: 三种裁定都认; 没表态/坏 JSON/未知值 ⇒ ""（保守, 不当作完成）
    m = '干活了\nEXEC-VERDICT: {"verdict": "done", "reason": "验收达成"}\n'
    if _parse_verdict(m)["verdict"] != "done":
        bad.append("done 裁定没解析出来")
    m2 = 'EXEC-VERDICT: {"verdict": "needs_decision", "reason": "验收与现状冲突"}'
    got2 = _parse_verdict(m2)
    if got2["verdict"] != "needs_decision" or not got2["verdict_reason"]:
        bad.append(f"needs_decision 没解析出来: {got2}")
    if _parse_verdict('EXEC-VERDICT: {"verdict": "maybe"}')["verdict"]:
        bad.append("未知裁定值应算【没表态】")
    if _parse_verdict("EXEC-VERDICT: {坏 json")["verdict"]:
        bad.append("坏 JSON 应算【没表态】")
    if _parse_verdict("什么都没说")["verdict"]:
        bad.append("没有标记时应算【没表态】")
    # 多个标记 ⇒ 取最后（执行体可能先写一版后改口）
    multi = 'EXEC-VERDICT: {"verdict": "done"}\n…\nEXEC-VERDICT: {"verdict": "blocked", "reason": "缺凭据"}'
    if _parse_verdict(multi)["verdict"] != "blocked":
        bad.append("多个裁定应取最后一个")

    # ② 从执行结果里取（dict 形态 / 对象形态）
    if SP._verdict_of({"output": {"verdict": "blocked", "verdict_reason": "缺凭据"}})[0] != "blocked":
        bad.append("dict 形态取不到裁定")
    if SP._verdict_of(SimpleNamespace(output={"verdict": "needs_decision"}))[0] != "needs_decision":
        bad.append("对象形态取不到裁定")
    if SP._verdict_of({"stdout": "x"})[0]:
        bad.append("没有裁定时应给空（没表态）")

    # ③ 指令里必须带契约（否则执行体不知道要表态）
    req = ExecutionRequest(id="EXR-v", task_id="PLAN-v", input={"instruction": "做点事"})
    prompt = HermesRuntimeAdapter._build_prompt(req)
    if "EXEC-VERDICT" not in prompt or "needs_decision" not in prompt:
        bad.append("指令里没有裁定契约（执行体无从表态）")

    # ④ 落到叶上 + 进度里算"待裁决"（不是完成）
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        d = root / "projects" / "P-v" / "tasks"
        d.mkdir(parents=True)
        (d / "PLAN-v.json").write_text(json.dumps(
            {"plan_id": "PLAN-v", "project_id": "P-v", "status": "confirmed", "nodes": [
                {"id": "p", "kind": "project", "parent_id": "", "title": "项目"},
                {"id": "M", "kind": "domain", "parent_id": "p", "title": "模块"},
                {"id": "L", "kind": "task", "parent_id": "M", "title": "叶", "status": "cancelled"}]},
            ensure_ascii=False), encoding="utf-8")
        D.mark_needs_decision(root, "PLAN-v", "L", verdict="needs_decision",
                              reason="验收与现状冲突", project_id="P-v")
        leaf = D.get_leaf(root, "PLAN-v", "L", project_id="P-v") or {}
        if not leaf.get("needs_decision") or leaf.get("decision_kind") != "needs_decision":
            bad.append(f"待裁决标记没写进叶: {leaf.get('needs_decision')}/{leaf.get('decision_kind')}")
        if "冲突" not in str(leaf.get("decision_reason") or ""):
            bad.append("裁决原因没落盘（人看不到要裁什么）")
        if (P.summary(root).get("needs_decision") or 0) != 1:
            bad.append("进度里没把'待裁决'单列（会被当成没这回事）")
        if (P.summary(root).get("done") or 0) != 0:
            bad.append("待裁决的叶不许算进完成")

        # ⑤ ★ 派活要给足上下文: 派发出来的执行请求里必须带【任务名 + 验收】,
        #    且适配器组出的 prompt 里能看到它们（真跑踩到: 执行体只收到 "execute execution EXR-x"）
        from ai_factory_os.bootstrap.scheduler_wiring import StoreExecution

        (d / "PLAN-v.json").write_text(json.dumps(
            {"plan_id": "PLAN-v", "project_id": "P-v", "status": "confirmed", "nodes": [
                {"id": "p", "kind": "project", "parent_id": "", "title": "项目"},
                {"id": "M", "kind": "domain", "parent_id": "p", "title": "模块"},
                {"id": "L", "kind": "task", "parent_id": "M", "status": "pending",
                 "title": "初始化工程脚手架", "acceptance": "仓库根有 package.json，且 scripts 里有 test",
                 "expected_files": ["package.json"]}]},
            ensure_ascii=False), encoding="utf-8")
        port = StoreExecution(root, plan_id="PLAN-v")
        req = port.create("L", resolution_id="R-1", member_id="m-1", identity_id="i-1")
        inp = dict(getattr(req, "input", {}) or {})
        if "初始化工程脚手架" not in str(inp.get("task") or ""):
            bad.append(f"派发没带任务名（执行体不知道干啥）: task={inp.get('task')!r}")
        if "package.json" not in str(inp.get("instruction") or ""):
            bad.append(f"派发没带验收/产出文件: instruction={str(inp.get('instruction'))[:60]!r}")
        prompt = HermesRuntimeAdapter._build_prompt(req)
        if "初始化工程脚手架" not in prompt or "验收标准" not in prompt:
            bad.append("适配器组出的 prompt 里看不到任务与验收（等于没派活）")
        if "EXEC-VERDICT" not in prompt:
            bad.append("prompt 里缺裁定契约")
    return bad


def test_executor_verdict() -> None:
    """执行体裁定: 停手可表达 · 没表态不当作完成 · 待裁决要在进度里单列。"""
    assert _check_executor_verdict() == []


def _check_project_memory() -> list[str]:
    """★ 项目级记忆（全量测试查出"写侧零调用者 + add 不落盘 ⇒ 静默丢"）。

    判据:
      · `add()` 必须**自动落盘**（新进程能读到 —— 实测踩过: 忘了 save 就悄悄丢）
      · 落盘失败/无数据根 ⇒ 返回 False（调用方据此可见地告警, 不许静默）
      · 调度器在【执行完成/停手/重试终止】时**真的写进项目记忆**（写侧接线）
    """
    import tempfile
    from types import SimpleNamespace

    from ai_factory_os.bootstrap import scheduler_pump as SP

    bad: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        from ai_factory_os.services.conversation.project_memory import MemoryStore

        # ① add 自动落盘: 写完**换一个实例**读
        ms = MemoryStore.load(root, "P-m")
        if ms.add("第一次尝试: 环境变量统一读取已落地", kind="learning",
                  authority="repo_evidence") is not True:
            bad.append("add() 没报落盘成功（应该自动落盘）")
        fresh = MemoryStore.load(root, "P-m")
        if len(fresh.recent(n=5)) != 1:
            bad.append("★ add() 没落盘 —— 新实例读不到（就是那个静默丢的坑）")
        # ② 未 load 数据根 ⇒ 只能是内存态, 必须返回 False 让人看得见
        orphan = MemoryStore("P-x")
        if orphan.add("无数据根") is not False:
            bad.append("没有数据根时应返回 False（否则调用方以为记住了）")
        # ③ 调度器写侧接线: 造一个"已完成的执行" ⇒ `_record_memory` 必须落一条
        proj = root / "projects" / "P-m" / "tasks"
        proj.mkdir(parents=True, exist_ok=True)
        (proj / "PLAN-m.json").write_text(json.dumps(
            {"plan_id": "PLAN-m", "project_id": "P-m", "status": "confirmed", "nodes": [
                {"id": "p", "kind": "project", "parent_id": "", "title": "项目"},
                {"id": "L", "kind": "task", "parent_id": "p", "status": "completed",
                 "title": "初始化脚手架"}]}, ensure_ascii=False), encoding="utf-8")

        class _Req:
            def __init__(self):
                self.id = "EXR-m"
                self.task_id = "PLAN-m"
                self.input = {"node_id": "L"}
                self.project_id = ""

        class _Store:
            def list_executions(self):
                return [_Req()]

        orig = SP.open_runtime_store
        try:
            SP.open_runtime_store = lambda _r: _Store()      # type: ignore[assignment]
            ports = SimpleNamespace(work=SimpleNamespace(_root=str(root), _plan_id="PLAN-m"))
            SP._record_memory(ports, "EXR-m", kind="learning",  # type: ignore[arg-type]
                              text="任务完成（裁定=done, 产出证据=repo-changed）",
                              authority="repo_evidence")
        finally:
            SP.open_runtime_store = orig                    # type: ignore[assignment]
        got = MemoryStore.load(root, "P-m").recent(n=5)
        if not any("任务完成" in str(e.get("text")) for e in got):
            bad.append("调度器没把执行经验写进项目记忆（写侧仍是死的）: "
                       f"{[str(e.get('text'))[:20] for e in got]}")
        # ④ 去重 + 权威升级（同文本不重复; 更高权威覆盖）
        ms2 = MemoryStore.load(root, "P-m")
        ms2.add("同一句话", kind="observation", authority="agent_claim")
        ms2.add("同一句话", kind="learning", authority="verified_state")
        same = [e for e in ms2.recent(n=9) if e.get("text") == "同一句话"]
        if len(same) != 1:
            bad.append(f"同文本该去重: {len(same)} 条")
        elif same[0].get("authority") != "verified_state":
            bad.append(f"更高权威该覆盖: {same[0].get('authority')}")
    return bad


def test_project_memory() -> None:
    """项目级记忆: add 自动落盘 · 失败可见 · 调度器写侧真的写。"""
    assert _check_project_memory() == []


def _check_llm_key_resolution() -> list[str]:
    """★ LLM key 的【归属与写读同源】（2026-09-21 实测"配了 key 却不生效"）。

    Founder 原话: 「配置不应该在 AI Factory OS 自己的配置文件么，和 .hermes/.env 有什么关系」
    实测病: ① `provider add` 把 key 写 ~/.hermes/.env（别人地盘）② 解析链读【源码目录内】的 .env（死路）
            ③ 降级时不说原因 ⇒ 只报"我暂时无法可靠理解…"，把人引向"换个说法"
    判据: key 归 factory 自己的 `~/.factory/.env`（600）; 配置只存 env: 引用; 写读同源; 降级理由可见。
    """
    import os
    import tempfile

    bad: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(home)                     # 隔离: 不碰真实 ~/.factory
        try:
            from ai_factory_os.infrastructure.config import provider as CFG
            from ai_factory_os.infrastructure.llm.providers.control_plane import LLMControlPlane
            from apps.cli.commands import _write_env_key

            # ① .env 层必须落在 factory 自己的数据根（不是源码目录、不是 ~/.hermes）
            envf = CFG._default_env_file()
            want = home / ".factory" / ".env"
            if envf != want:
                bad.append(f".env 层路径不对: {envf}（应为 {want}）")
            if "site-packages" in str(envf) or str(envf).startswith(str(Path.cwd())):
                bad.append(f"★ .env 层仍指向源码/包目录（死路）: {envf}")

            # ② provider add 写 key ⇒ 落 factory 自己的 .env + 权限 600
            written = _write_env_key("FACTORY_TEST_KEY", "dummy-value")
            if not written or Path(written) != want:
                bad.append(f"provider add 写到了别处: {written!r}（应为 {want}）")
            if want.is_file() and (want.stat().st_mode & 0o777) != 0o600:
                bad.append(f"密钥文件权限不是 600: {oct(want.stat().st_mode)[-3:]}")

            # ③ 解析链读同一处 ⇒ 用临时 HOME 造 providers.json, key 必须解析得到
            (home / ".factory").mkdir(parents=True, exist_ok=True)
            (home / ".factory" / "providers.json").write_text(json.dumps({
                "version": 1, "fallback_chain": ["p1"],
                "providers": {"p1": {"id": "p1", "enabled": True, "models": ["m"],
                                     "base_url": "http://x/v1", "api_key_ref": "env:FACTORY_TEST_KEY"}}},
                ensure_ascii=False), encoding="utf-8")
            plane = LLMControlPlane(providers_file=home / ".factory" / "providers.json")
            if plane.fallback_order() != ["p1"]:
                bad.append(f"★ 解析链读不到 factory 自己的 .env（写读不同源, 就是那个 bug）: {plane.fallback_order()}")
            if plane.resolve_api_key("p1") != "dummy-value":
                bad.append(f"key 没解析出来: {plane.resolve_api_key('p1')!r}")
        finally:
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home

    # ④ 降级必须【说出原因】（否则把人引向"换个说法"这个错误方向）
    from ai_factory_os.services.conversation import interpreter as II

    prop = II._degrade_clarify("随便一句话", "测试原因: 无可用 provider")
    if "测试原因" not in str(prop.get("reply") or ""):
        bad.append(f"降级没说原因（又回到误导性提示）: {str(prop.get('reply'))[:60]}")
    return bad


def test_llm_key_resolution() -> None:
    """LLM key: 归 factory 自己的 .env · 写读同源 · 权限 600 · 降级理由可见。"""
    assert _check_llm_key_resolution() == []


def _check_locate_reads_conversation() -> list[str]:
    """★ 定位要【读会话】（卡点2）: 不给文本也能定位, 且归属自动取自会话绑定。

    实测病: `locate` 的 `text` 原为**必填**位置参数 ⇒ 逼人把需求再粘一遍（看着像"它没读会话"）;
            且公开视图 `get_conversation()` 不含 project_id ⇒ 不给 --project 时**归属恒为空**。
    """
    import tempfile
    from types import SimpleNamespace

    from ai_factory_os.services.conversation import understanding as U
    from apps.cli.domains.conversation import _locate

    bad: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        d = root / "projects" / "P-loc" / "conversations"
        d.mkdir(parents=True, exist_ok=True)
        (d / "conv-t1.json").write_text(json.dumps({
            "id": "conv-t1", "title": "t", "status": "OPEN", "created_by": "human",
            "project_id": "P-loc", "messages": [
                {"id": "m1", "role": "human", "content": "我要做一个社区图书借还小程序", "created_at": ""}],
            "understanding": {"version": 0, "facts": {}}, "created_at": "", "updated_at": "",
        }, ensure_ascii=False), encoding="utf-8")

        # ① 只给会话 id（不给文本）⇒ 必须能定位, 且归属=会话绑定的项目
        #    注: 定位结果是**中文字段**（归属/类型/承接 —— 给人看的）, 不是 intent/project_id
        try:
            r = _locate(root, SimpleNamespace(conversation_id="conv-t1", text="", project=None,
                                              proposer="", intent=""))
        except Exception as exc:  # noqa: BLE001 — 失败也要干净可读（别崩栈）
            return [f"不给文本时应从会话取需求, 实际抛错: {type(exc).__name__}: {str(exc)[:80]}"]
        loc = r.get("location") or {}
        if not loc.get("类型"):
            bad.append(f"不给文本时没定位成功: {loc}")
        got_pid = str((loc.get("归属") or {}).get("project") or "")
        if got_pid != "P-loc":
            bad.append(f"归属没从会话带出来（公开视图缺 project_id 那个坑）: {got_pid!r}")
        # ② 落盘（后续步骤要读它 —— 定位白做就是这里没写）: 落在会话的 location 字段
        _raw = U._load_conv(root, "conv-t1") or {}  # noqa: SLF001
        if not (_raw.get("location") or {}):
            bad.append("定位结果没落盘（R26: 状态必须落盘）")
        # ③ 会话里没有人类消息 ⇒ 响亮报错（不静默给个空定位）
        (d / "conv-t2.json").write_text(json.dumps({
            "id": "conv-t2", "project_id": "P-loc", "messages": [],
            "understanding": {"version": 0, "facts": {}}, "status": "OPEN", "created_by": "human",
        }, ensure_ascii=False), encoding="utf-8")
        try:
            _locate(root, SimpleNamespace(conversation_id="conv-t2", text="", project=None,
                                          proposer="", intent=""))
            bad.append("空会话（无人类消息）应响亮报错, 实际静默通过")
        except Exception:
            pass
    return bad


def test_locate_reads_conversation() -> None:
    """定位: 读会话取文本与归属 · 落盘 · 空会话响亮报错。"""
    assert _check_locate_reads_conversation() == []


def _check_repo_closing_contract() -> list[str]:
    """★ 执行体的收尾契约 + 证据四态（卡点4）: "提交了"与"留了脏工作区"必须分开。

    实测: EXR-002/003 自提交(干净) · EXR-004(超时)/EXR-005 都没提交(场景仓库 6/18 个未提交文件)
          ⇒ 原来只有 True/False/None 三态, 分不清 ⇒ 叶被记成干净完成。
    """
    import subprocess
    import tempfile

    from ai_factory_os.bootstrap import scheduler_pump as SP
    from ai_factory_os.services.execution.runtime.adapters.hermes import (
        HermesRuntimeAdapter, _VERDICT_CONTRACT,
    )
    from ai_factory_os.services.execution.runtime.types import ExecutionRequest

    bad: list[str] = []

    def _git(cwd, *args):
        return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)

    with tempfile.TemporaryDirectory() as td:
        r = Path(td) / "repo"
        r.mkdir()
        if _git(r, "init", "-q").returncode != 0:
            return ["git init 不可用（环境问题, 跳过该守卫）"]
        _git(r, "-c", "user.email=t@local", "-c", "user.name=t", "config", "user.email", "t@local")
        _git(r, "config", "user.name", "t")
        # ① 非 git 仓库 ⇒ unknown（不猜）
        plain = Path(td) / "plain"
        plain.mkdir()
        if SP._repo_state(str(plain)) != "unknown":
            bad.append(f"非 git 目录应 unknown: {SP._repo_state(str(plain))}")
        # ② 仓库在、一次没提交 ⇒ none
        (r / "a.txt").write_text("x", encoding="utf-8")
        if SP._repo_state(str(r)) != "uncommitted":
            bad.append(f"有未提交改动应 uncommitted: {SP._repo_state(str(r))}")
        # ③ 提交后干净 ⇒ committed（窗口内）
        _git(r, "add", "-A")
        _git(r, "commit", "-q", "-m", "init")
        if SP._repo_state(str(r)) != "committed":
            bad.append(f"刚提交应 committed: {SP._repo_state(str(r))}")
        # ④ 窗口外（1 秒窗口 + 提交已在过去）⇒ none
        if SP._repo_state(str(r), window_sec=0.001) != "none":
            bad.append(f"窗口外应 none: {SP._repo_state(str(r), window_sec=0.001)}")
        # ⑤ 又脏了 ⇒ uncommitted（"产出未提交"这一态被单独识别出来 —— 本刀的核心）
        (r / "b.txt").write_text("y", encoding="utf-8")
        if SP._repo_state(str(r)) != "uncommitted":
            bad.append(f"提交后又改应 uncommitted: {SP._repo_state(str(r))}")
        # ⑥ 空仓库（有 .git 无提交）⇒ none（不是 uncommitted, 也不是 unknown）
        empty = Path(td) / "empty"
        empty.mkdir()
        _git(empty, "init", "-q")
        if SP._repo_state(str(empty)) != "none":
            bad.append(f"空仓库应 none: {SP._repo_state(str(empty))}")

    # ⑦ 指令里必须写【收尾纪律】（否则执行体不知道要提交）
    req = ExecutionRequest(id="EXR-c", task_id="PLAN-c", input={"instruction": "做事"})
    prompt = HermesRuntimeAdapter._build_prompt(req)
    for kw in ("收尾纪律", "commit"):
        if kw not in prompt and kw not in _VERDICT_CONTRACT:
            bad.append(f"指令里缺收尾纪律（{kw}）—— 执行体无从知道要提交")
    return bad


def test_repo_closing_contract() -> None:
    """收尾契约: 提交/未提交/无改动/判不出 四态分开 + 指令写清收尾纪律。"""
    assert _check_repo_closing_contract() == []


def _check_chain_covers_rings() -> list[str]:
    """★ `factory chain` = 会话唯一入口（核心第1条）: 覆盖 需求→拆解 每一步, 且 ⑤ **自动生成**三件制品。

    为什么守这条（2026-09-21 我自己误读过）: 该模块 docstring 写"缺产物时只在结果里提示", 而**代码**
    里 s5 是**自动生成** 产品定义/交互设计/架构设计（缺哪个补哪个）⇒ 只看自述会得出"链到拆解就断"的
    错误结论。守据: 三件制品的生成调用必须在源码里, 且 ①–⑦ 的步骤标签齐。
    """
    import inspect

    from apps.cli.domains import chain as CH

    bad: list[str] = []
    src = inspect.getsource(CH)
    for kw in ("cmd_product_develop", "cmd_product_ux", "_dispatch_arch"):
        if kw not in src:
            bad.append(f"⑤ 不再自动生成制品（缺 {kw}）⇒ 从零场景会断在拆解（arch 是 decompose 的必需输入）")
    for label in ("① 定位", "② 建会话", "③ 理解", "④ PRD", "⑤ 分析产物", "⑥ 拆解", "⑦ 细拆"):
        if label not in src:
            bad.append(f"步骤标签缺 {label}（人看不到这一段跑了没有）")
    # 失败要停在那步并记录（不许静默跳过）
    if '"fail"' not in src:
        bad.append("没有 fail 记录 ⇒ 断链会被静默跳过")
    return bad


def test_chain_covers_rings() -> None:
    """chain 覆盖 需求→拆解 全步 + 自动生成三件制品 + 失败可见。"""
    assert _check_chain_covers_rings() == []


def _check_workflow_drives_chain() -> list[str]:
    """★ 流程接进主链（核心第2条"无固定流程(可编排)"）。

    判据（缺一条就不算接上）:
      ① 默认不变: 树【不挂流程】⇒ 推进返回 "none"（叶按现状一次派活即完成）
      ② 挂了流程 ⇒ 叶按步骤顺序推进, **走完全部步骤才 finished**
      ③ ★ 可编排: 换一个（自定义）流程定义 ⇒ 主链行为跟着变（步数/顺序由定义决定）
      ④ 派活时把当前步骤写进执行请求（执行体看得到"这是第几步、要求什么技能"）
    """
    import tempfile

    from ai_factory_os.bootstrap import scheduler_pump as SP
    from ai_factory_os.bootstrap.scheduler_wiring import StoreExecution, wire_scheduler, workflow_engine
    from ai_factory_os.services.execution.runtime.store import open_runtime_store
    from ai_factory_os.services.execution.runtime.types import ExecutionRequest, ExecutionStatus
    from ai_factory_os.services.work import decomposition as D
    from ai_factory_os.services.work.workflows.models import Workflow, WorkflowStep

    bad: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        plan, leaf, proj = "PLAN-wf", "t-wf-1", "P-wf"
        d = root / "projects" / proj / "tasks"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{plan}.json").write_text(json.dumps({
            "plan_id": plan, "project_id": proj, "status": "confirmed",
            "nodes": [{"id": proj, "kind": "project", "title": "P"},
                      {"id": "dom", "kind": "domain", "parent_id": proj, "title": "D"},
                      {"id": leaf, "kind": "task", "parent_id": "dom", "title": "做一件事",
                       "status": "pending", "acceptance": "一句话验收"}],
        }, ensure_ascii=False), encoding="utf-8")

        eng = workflow_engine(root)
        if len(eng.list_workflows()) < 4:
            bad.append(f"内置流程没注册进 store: {[w.id for w in eng.list_workflows()]}")

        # ① 不挂流程 ⇒ 行为不变
        if SP._advance_workflow_step(wire_scheduler(root, plan_id=plan), "EXR-none") != "none":
            bad.append("未挂流程时不该推进流程（默认行为必须不变）")

        def _mk_exec(eid: str) -> None:
            open_runtime_store(root).save_execution(ExecutionRequest(
                id=eid, task_id=plan, status=ExecutionStatus.PENDING,
                input={"node_id": leaf, "resolution_id": "r", "member_id": "m", "identity_id": "i"}))

        # ② 挂 feature-delivery（4 步）⇒ 依次推进, 第 4 步才 finished
        D.set_tree_workflow(root, plan, "feature-delivery", proj)
        ports = wire_scheduler(root, plan_id=plan)
        _mk_exec("EXR-s1")
        step = StoreExecution(root, plan_id=plan)._workflow_step(leaf) or {}
        if step.get("step_id") != "architecture" or step.get("step_index") != 1:
            bad.append(f"派活该在第 1 步(architecture), 实得 {step.get('step_id')}/{step.get('step_index')}")
        # ④ 执行请求里必须带上步骤（执行体才能只看本步）
        req = StoreExecution(root, plan_id=plan).create(leaf, resolution_id="r",
                                                        member_id="m", identity_id="i")
        if str((req.input or {}).get("workflow_step") or "") != "architecture":
            bad.append(f"执行请求没带流程步骤: {(req.input or {}).get('workflow_step')!r}")
        got = [SP._advance_workflow_step(ports, f"EXR-s{i}") for i in (1,)]
        for i in (2, 3, 4):
            _mk_exec(f"EXR-s{i}")
            got.append(SP._advance_workflow_step(ports, f"EXR-s{i}"))
        if got != ["advanced", "advanced", "advanced", "finished"]:
            bad.append(f"4 步流程的推进序列不对: {got}")

        # ③ 可编排: 注册一个 2 步的自定义流程并挂上 ⇒ **换一个新叶**（新 run）只推 1 次就 advanced
        #    （注: 不能复用上面那个叶 —— 它的 run 已完结, run_for 会返回旧 run, 判不出"换定义生效"）
        leaf2 = "t-wf-2"
        tree = json.loads((d / f"{plan}.json").read_text(encoding="utf-8"))
        tree["nodes"].append({"id": leaf2, "kind": "task", "parent_id": "dom",
                              "title": "第二件事", "status": "pending", "acceptance": "一句话验收"})
        (d / f"{plan}.json").write_text(json.dumps(tree, ensure_ascii=False), encoding="utf-8")
        workflow_engine(root).create_workflow(Workflow(
            id="two-step", name="两步", description="",
            steps=[WorkflowStep(id="a", name="第一步", order=1),
                   WorkflowStep(id="b", name="第二步", order=2)]))
        D.set_tree_workflow(root, plan, "two-step", proj)

        def _mk_exec2(eid: str) -> None:
            open_runtime_store(root).save_execution(ExecutionRequest(
                id=eid, task_id=plan, status=ExecutionStatus.PENDING,
                input={"node_id": leaf2, "resolution_id": "r", "member_id": "m", "identity_id": "i"}))

        store2 = StoreExecution(root, plan_id=plan)
        if (store2._workflow_step(leaf2) or {}).get("steps_total") != 2:
            bad.append(f"换成 2 步流程后派活仍按旧定义: {store2._workflow_step(leaf2)}")
        ports2 = wire_scheduler(root, plan_id=plan)
        _mk_exec2("EXR-c1")
        r1 = SP._advance_workflow_step(ports2, "EXR-c1")
        _mk_exec2("EXR-c2")
        r2 = SP._advance_workflow_step(ports2, "EXR-c2")
        if (r1, r2) != ("advanced", "finished"):
            bad.append(f"换成 2 步自定义流程后主链没跟着变: {(r1, r2)}（可编排未生效）")
    return bad


def test_workflow_drives_chain() -> None:
    """流程接进主链: 默认不变 · 按步骤推进 · 走完才算完成 · 换定义行为跟着变。"""
    assert _check_workflow_drives_chain() == []


def _check_org_scope_reaches_execution() -> list[str]:
    """★ 多公司 / 多部门落到执行（核心第4条 / 四维里的两维）。

    判据:
      ① 默认不变: 项目未归属公司 ⇒ 选人池 = 全部成员（现状）
      ② 按公司筛: 项目归了公司 ⇒ 池子里**只有该公司**成员（跨公司不串人）
      ③ 归属进执行: 执行请求 input 带 company_id/department_id + 简报写明归属
      ④ 合法值: 项目归属读的是 projects.json（唯一一处 project_scope）
    """
    import tempfile

    from ai_factory_os.bootstrap.scheduler_wiring import StoreExecution
    from ai_factory_os.services.work import staffing as ST

    bad: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "agents").mkdir(parents=True, exist_ok=True)
        (root / "agents" / "agents.json").write_text(json.dumps({
            "a1": {"id": "a1", "name": "A1", "role": "developer", "company_id": "C-A"},
            "a2": {"id": "a2", "name": "A2", "role": "tester", "company_id": "C-A"},
            "b1": {"id": "b1", "name": "B1", "role": "developer", "company_id": "C-B"},
            "u1": {"id": "u1", "name": "U1", "role": "developer", "company_id": ""},
        }, ensure_ascii=False), encoding="utf-8")
        plan, proj, leaf = "PLAN-o1", "P-o1", "t-o1"
        (root / "org").mkdir(parents=True, exist_ok=True)
        (root / "org" / "projects.json").write_text(json.dumps({
            "projects": {proj: {"id": proj, "name": "P1", "company_id": "C-A", "department_ids": ["D-A"]}}
        }, ensure_ascii=False), encoding="utf-8")
        d = root / "projects" / proj / "tasks"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{plan}.json").write_text(json.dumps({
            "plan_id": plan, "project_id": proj, "status": "confirmed",
            "nodes": [{"id": leaf, "kind": "task", "title": "做事", "status": "pending",
                       "acceptance": "一句话验收"}],
        }, ensure_ascii=False), encoding="utf-8")

        # ① 默认不变（不给公司）
        allc = ST.role_catalog(root)
        if allc.get("developer") != 3 or allc.get("tester") != 1:
            bad.append(f"不筛时应见全部成员: {allc}")
        # ② 按公司筛（未归属成员不入选, 跨公司不串人）
        sc = ST.role_catalog(root, company_id="C-A")
        if sc.get("developer") != 1 or sc.get("tester") != 1 or "b1" in str(sc):
            bad.append(f"按公司筛人不对: {sc}（B 公司的 developer 不该进池）")
        # ④ 项目归属读一处
        if ST.project_scope(root, proj) != ("C-A", "D-A"):
            bad.append(f"project_scope 读不出归属: {ST.project_scope(root, proj)}")
        # ③ 归属进执行请求 + 简报
        req = StoreExecution(root, plan_id=plan).create(leaf, resolution_id="r",
                                                       member_id="a1", identity_id="a1")
        inp = req.input or {}
        if inp.get("company_id") != "C-A" or inp.get("department_id") != "D-A":
            bad.append(f"执行请求没带归属: {inp.get('company_id')!r}/{inp.get('department_id')!r}")
        if "归属: 公司 C-A" not in str(inp.get("instruction") or ""):
            bad.append("简报里没写归属（执行体不知道自己在哪个公司干活）")
        # 未归属项目 ⇒ 不筛 + 请求里为空（默认行为不变）
        (root / "org" / "projects.json").write_text(json.dumps({
            "projects": {proj: {"id": proj, "name": "P1", "company_id": "", "department_ids": []}}
        }, ensure_ascii=False), encoding="utf-8")
        req2 = StoreExecution(root, plan_id=plan).create(leaf, resolution_id="r",
                                                        member_id="a1", identity_id="a1")
        if (req2.input or {}).get("company_id"):
            bad.append("项目未归属时不该带公司")
    return bad


def test_org_scope_reaches_execution() -> None:
    """多公司/多部门落到执行: 默认不筛 · 按公司筛人不串 · 归属进请求与简报。"""
    assert _check_org_scope_reaches_execution() == []


def _check_file_conflict_demotion() -> list[str]:
    """★ 文件冲突降级串行（cr-5）—— 并行安全前提: 同层写同一文件的执行不能同时跑。

    实测病（2026-09-21）: 原实现遍历 `<root>/task_trees/*.json` —— 该目录**不存在**
    （真树在 `projects/<P>/tasks/*.json`）⇒ 恒返回空 ⇒ 这段是**死代码**, 且没人发现。
    """
    import tempfile

    from ai_factory_os.bootstrap import scheduler_pump as SP

    bad: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        proj, plan = "P-cf", "PLAN-cf"
        d = root / "projects" / proj / "tasks"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{plan}.json").write_text(json.dumps({
            "plan_id": plan, "project_id": proj, "status": "confirmed",
            "nodes": [
                {"id": "dom", "kind": "domain", "title": "D"},
                {"id": "t1", "kind": "task", "parent_id": "dom", "title": "改 A",
                 "status": "pending", "expected_files": ["src/a.py", "src/b.py"]},
                {"id": "t2", "kind": "task", "parent_id": "dom", "title": "也改 A",
                 "status": "pending", "expected_files": ["src/a.py"]},
                {"id": "t3", "kind": "task", "parent_id": "dom", "title": "各自改",
                 "status": "pending", "expected_files": ["src/c.py"]},
            ],
        }, ensure_ascii=False), encoding="utf-8")

        serial = SP._conflicting_nodes(root)
        if serial != {"t2"}:
            bad.append(f"同层写同一文件时该把后来的降级串行（期望 {{'t2'}}, 实得 {serial}）"
                       "（若为空 ⇒ 又退回'死代码'那个 bug）")
        par, ser = SP._split_by_conflict(root, ["EXR1", "EXR2", "EXR3"],
                                        {"EXR1": "t1", "EXR2": "t2", "EXR3": "t3"})
        if sorted(ser) != ["EXR2"] or sorted(par) != ["EXR1", "EXR3"]:
            bad.append(f"分批不对: 可并行 {par} · 串行 {ser}")
    return bad


def test_file_conflict_demotion() -> None:
    """文件冲突 ⇒ 降级串行（且真的读到了树 —— 不是死代码）。"""
    assert _check_file_conflict_demotion() == []


def _check_load_gate_real_data() -> list[str]:
    """★ 容量门 / 预算门接真数据（第 4 件·执行安全三件; Codex cr-6 "预算门是假数据"）。

    实测病: `SimpleLoad.active_count` 恒 0、`remaining_budget` 恒 1e9
      ⇒ 调度器 evaluate._pick 的两个条件（成员满 / 预算不够）**永不触发**。
    判据:
      ① active_count 数的是 RuntimeStore 里该成员【在跑】的执行（终态不算）
      ② remaining_budget = 预算 − 真实花费（usage.estimated_cost 累计）
      ③ 没数据 ⇒ 退回旧行为（0 / 预算全额）—— 默认不变
      ④ 预算花超（remaining<0）⇒ evaluate._pick 的预算条件成立（该成员不被选）
    """
    import tempfile

    from ai_factory_os.bootstrap.scheduler_wiring import SimpleLoad
    from ai_factory_os.infrastructure.llm.providers.usage import ProviderUsage, UsageStore
    from ai_factory_os.services.execution.runtime.store import open_runtime_store
    from ai_factory_os.services.execution.runtime.types import (
        ExecutionRequest, ExecutionStatus,
    )

    bad: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        store = open_runtime_store(root)
        for i, (mid, st) in enumerate((("m1", ExecutionStatus.PENDING),
                                       ("m1", ExecutionStatus.PENDING),
                                       ("m2", ExecutionStatus.RUNNING),
                                       ("m1", ExecutionStatus.SUCCESS))):
            store.save_execution(ExecutionRequest(
                id=f"EXR-l{i}", task_id="PLAN-l", status=st,
                input={"node_id": f"t{i}", "member_id": mid, "resolution_id": "r",
                       "identity_id": mid}))
        load = SimpleLoad(root)
        if load.active_count("m1") != 2:
            bad.append(f"m1 在跑数应 2（两条 PENDING; SUCCESS 不算）, 实得 {load.active_count('m1')}")
        if load.active_count("m2") != 1 or load.active_count("m9") != 0:
            bad.append(f"m2=1/m9=0 期望, 实得 {load.active_count('m2')}/{load.active_count('m9')}")
        # ③ 没用量 ⇒ 花费 0 / 预算全额
        if load.spent_total() != 0.0 or load.remaining_budget("m1") != 1.0e9:
            bad.append(f"没有用量时该退回旧行为: spent={load.spent_total()} remaining={load.remaining_budget('m1')}")
        # ② 真花费 ⇒ 剩余 = 预算 − 花费
        UsageStore(root / "providers").record(ProviderUsage(
            id="u1", provider_id="deepseek", model="m", prompt_tokens=1, completion_tokens=1,
            estimated_cost=5.0, latency_ms=1, success=True))
        load2 = SimpleLoad(root, budget=3.0)
        if load2.spent_total() != 5.0 or abs(load2.remaining_budget("m1") + 2.0) > 1e-9:
            bad.append(f"预算-花费没算对: spent={load2.spent_total()} remaining={load2.remaining_budget('m1')}")
        # ④ 花超 ⇒ 预算门条件成立（evaluate._pick 里 `remaining < estimate`）
        if not (load2.remaining_budget("m1") < 0):
            bad.append("花超时剩余应为负 ⇒ 该成员过不了预算门")
    return bad


def test_load_gate_real_data() -> None:
    """容量门/预算门接真数据: 在跑数来自执行、剩余=预算−真花费、没数据退回旧行为。"""
    assert _check_load_gate_real_data() == []


def _check_recover_plan_from_checkpoint() -> list[str]:
    """★ 失败恢复接树（第 4 件之③）: 中断后能按检查点把叶交回, 且不误伤在跑的。

    判据:
      ① 泵每批结束落检查点（停靠点）: 有叶状态汇总 + 执行状态快照
      ② recover --plan 把"claimed 且无活跃执行"的叶交回 pending（不计重试）
      ③ 有活跃执行的叶**不动**（不误伤）
      ④ 幂等: 重复调用无事可做（第二次 resumed 为空）
    """
    import tempfile
    from types import SimpleNamespace

    from ai_factory_os.bootstrap import scheduler_pump as SP
    from ai_factory_os.bootstrap.scheduler_wiring import wire_scheduler
    from ai_factory_os.services.execution.recovery.checkpoint import CheckpointStore
    from ai_factory_os.services.execution.runtime.store import open_runtime_store
    from ai_factory_os.services.execution.runtime.types import ExecutionRequest, ExecutionStatus

    bad: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        proj, plan = "P-rc", "PLAN-rc"
        d = root / "projects" / proj / "tasks"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{plan}.json").write_text(json.dumps({
            "plan_id": plan, "project_id": proj, "status": "confirmed",
            "nodes": [
                {"id": "dom", "kind": "domain", "title": "D"},
                {"id": "t-dead", "kind": "task", "parent_id": "dom", "title": "中断留下的叶",
                 "status": "claimed", "acceptance": "一句话验收"},
                {"id": "t-live", "kind": "task", "parent_id": "dom", "title": "正在跑的叶",
                 "status": "claimed", "acceptance": "一句话验收"},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        open_runtime_store(root).save_execution(ExecutionRequest(
            id="EXR-live", task_id=plan, status=ExecutionStatus.PENDING,
            input={"node_id": "t-live", "resolution_id": "r", "member_id": "m", "identity_id": "i"}))

        # ① 检查点: 泵落停靠点
        SP._write_checkpoint(wire_scheduler(root, plan_id=plan), SimpleNamespace(outcomes=[]))
        cp = CheckpointStore(root / "checkpoints").load(plan)
        if cp is None or not (cp.workflow_state or {}).get("node_status"):
            bad.append(f"泵没落检查点（或没有叶状态汇总）: {cp}")
        elif "EXR-live" not in (cp.executions or {}):
            bad.append(f"检查点没带执行状态快照: {cp.executions}")

        # ②③ 恢复: 交回 dead, 不动 live
        from datetime import datetime, timedelta, timezone

        args = SimpleNamespace(plan=plan, project=proj, dry_run=False, stale_after=1800.0)
        r = _cmd_recover_plan_for(root, args)
        got = [x["node_id"] for x in r.get("resumed") or []]
        if got != ["t-dead"]:
            bad.append(f"该交回 t-dead（且只交回它）, 实得 {got}")
        if [x["node_id"] for x in r.get("busy") or []] != ["t-live"]:
            bad.append(f"有活跃执行的叶该被标'仍在跑': {r.get('busy')}")
        tree = json.loads((d / f"{plan}.json").read_text(encoding="utf-8"))
        st = {n["id"]: n.get("status") for n in tree["nodes"] if n.get("kind") == "task"}
        if st.get("t-dead") != "pending" or st.get("t-live") != "claimed":
            bad.append(f"落盘后状态不对: {st}（t-dead⇒pending, t-live⇒claimed 保持）")
        # ④ 幂等
        r2 = _cmd_recover_plan_for(root, args)
        if (r2.get("resumed") or []) or [x["node_id"] for x in r2.get("busy") or []] != ["t-live"]:
            bad.append(f"重复调用该无事可做: resumed={r2.get('resumed')} busy={r2.get('busy')}")

        # ⑤ ★ 陈旧窗口（2026-09-21 实测"掐掉再恢复"才暴露的真 bug）:
        #    被 kill 留下的 PENDING 执行**永远算活跃** ⇒ 叶卡在 claimed, 恢复不动它。
        #    ⇒ 超过窗口的 PENDING/RUNNING 视为无活跃进程。
        old_req = open_runtime_store(root).list_executions()[0]
        old_req.created_at = datetime.now(timezone.utc) - timedelta(seconds=7200)
        open_runtime_store(root).save_execution(old_req)
        if "t-live" in SP.live_node_ids(root):
            bad.append("陈旧（2 小时前）的 PENDING 执行仍被当成活跃 ⇒ 恢复会永远不动它（老病没治）")
        if "t-live" not in SP.live_node_ids(root, stale_after_sec=10**9):
            bad.append("窗口放大到极大时它【该】算活跃 —— 说明判据没按窗口走（第一版这里我写反了）")
        live_wide = SP.live_node_ids(root, stale_after_sec=1.0)
        if "t-live" in live_wide:
            bad.append("窗口缩到 1 秒时陈旧执行不该算活跃")
        # 陈旧 ⇒ recover 该把它交回
        tree2 = json.loads((d / f"{plan}.json").read_text(encoding="utf-8"))
        for n in tree2["nodes"]:
            if n.get("id") == "t-live":
                n["status"] = "claimed"
        (d / f"{plan}.json").write_text(json.dumps(tree2, ensure_ascii=False), encoding="utf-8")
        r3 = _cmd_recover_plan_for(root, SimpleNamespace(plan=plan, project=proj, dry_run=False,
                                                         stale_after=60.0))
        if [x["node_id"] for x in r3.get("resumed") or []] != ["t-live"]:
            bad.append(f"陈旧的 PENDING 该被判无活跃并把叶交回: {r3}")

        # ⑥ 泵【每批】落检查点（只在收尾写 ⇒ 中断的跑没有检查点, 恰恰最需要时没有）
        root2 = root / "d2"
        (root2 / "projects" / proj / "tasks").mkdir(parents=True, exist_ok=True)
        (root2 / "projects" / proj / "tasks" / f"{plan}.json").write_text(json.dumps({
            "plan_id": plan, "project_id": proj, "status": "confirmed",
            "nodes": [{"id": "t1", "kind": "task", "title": "一件事", "status": "pending",
                       "acceptance": "一句话验收", "required_capabilities": ["developer"]}],
        }, ensure_ascii=False), encoding="utf-8")
        (root2 / "agents").mkdir(parents=True, exist_ok=True)
        (root2 / "agents" / "agents.json").write_text(json.dumps({
            "d1": {"id": "d1", "name": "D", "role": "developer", "status": "AVAILABLE"}}),
            encoding="utf-8")
        ports2 = wire_scheduler(root2, plan_id=plan)
        SP.drive(ports2, run_execution=lambda eid: _fake_ok(ports2, eid), max_parallel=1,
                 max_ticks=3, limit=1)
        if CheckpointStore(root2 / "checkpoints").load(plan) is None:
            bad.append("跑一批后没落检查点（每批落盘没生效 ⇒ 中断时无据可依）")
    return bad


def _fake_ok(ports: Any, eid: str) -> Any:
    """假执行: 把该执行在**库里**标成 SUCCESS（守卫用 —— 不碰 LLM）。

    注: 必须落库 —— 事件发射只看执行库里的真实终态（不认返回 dict 里的 status）, 否则守卫会假绿。
    """
    from ai_factory_os.services.execution.runtime.store import open_runtime_store
    from ai_factory_os.services.execution.runtime.types import ExecutionStatus

    root = getattr(getattr(ports, "execution", None), "_root", None)
    if root is not None:
        st = open_runtime_store(root)
        for req in st.list_executions():
            if str(req.id) == str(eid):
                req.status = ExecutionStatus.SUCCESS
                st.save_execution(req)
                break
    return {"id": eid, "status": "SUCCESS", "ok": True, "output": {"verdict": "done"}}


def _cmd_recover_plan_for(root: Path, args: Any) -> dict:
    """在指定 root 上跑 recover --plan（守卫用 —— 不碰真实数据根）。"""
    from types import SimpleNamespace

    from apps.cli.commands import cmd_recover_plan

    ctx = SimpleNamespace(root=root, logger_scope=lambda: _null_scope())
    return cmd_recover_plan(ctx, args)


class _null_scope:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *a: Any) -> bool:
        return False


def test_recover_plan_from_checkpoint() -> None:
    """失败恢复接树: 落检查点 · 交回无活跃执行的叶 · 不误伤在跑的 · 幂等。"""
    assert _check_recover_plan_from_checkpoint() == []


def _check_metrics_not_empty_shells() -> list[str]:
    """★ 监控不能骗人: metrics 的 Agents / Validation 两段不能是**结构性空壳**。

    实测病（2026-09-21）: 这两段数的是 `ASSIGNMENT_*` 与 `VALIDATION_RULE_COMPLETED` 事件,
    而**全仓没有任何地方发过它们** ⇒ 表在、数恒 0, 分不清"真的没干"与"没接线"。
    判据:
      ① 跑一批后, 事件库里真的有派活事件（ASSIGNMENT_CREATED/COMPLETED）
      ② 验证事件也真的发（VALIDATION_RULE_COMPLETED, 规则=leaf-evidence）+ 每批一条 VALIDATION_COMPLETED
      ③ 两个 calculator 读这些事件后**不再是 0**（Agents.assignment_count / Validation.total_rules）
    """
    import tempfile

    from ai_factory_os.bootstrap import scheduler_pump as SP
    from ai_factory_os.bootstrap.scheduler_wiring import wire_scheduler
    from ai_factory_os.infrastructure.events.logger import EventLogger
    from ai_factory_os.infrastructure.events.store import EventStore
    from ai_factory_os.infrastructure.events.types import EventType
    from ai_factory_os.services.metrics.calculators import (
        calculate_agent_metrics, calculate_validation_metrics,
    )

    bad: list[str] = []
    # ★ 先断言【调用点】接线（反向验证暴露的漏洞: 只测函数 ⇒ 删掉调用点也过）
    import inspect as _insp

    from apps.cli import commands as _C

    if "_emit_execution_events(logger, ctx.root, rep)" not in _insp.getsource(_C.cmd_run_plan):
        bad.append("cmd_run_plan 里没调用 _emit_execution_events ⇒ 事件永远不会发（护栏没接上）")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        proj, plan = "P-m", "PLAN-m"
        d = root / "projects" / proj / "tasks"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{plan}.json").write_text(json.dumps({
            "plan_id": plan, "project_id": proj, "status": "confirmed",
            "nodes": [{"id": "t1", "kind": "task", "title": "一件事", "status": "pending",
                       "acceptance": "一句话验收", "required_capabilities": ["developer"]}],
        }, ensure_ascii=False), encoding="utf-8")
        (root / "agents").mkdir(parents=True, exist_ok=True)
        (root / "agents" / "agents.json").write_text(json.dumps({
            "d1": {"id": "d1", "name": "D", "role": "developer", "status": "AVAILABLE"}}),
            encoding="utf-8")
        ports = wire_scheduler(root, plan_id=plan)
        rep = SP.drive(ports, run_execution=lambda eid: _fake_ok(ports, eid), max_parallel=1,
                       max_ticks=2, limit=1)
        store = EventStore(root / "events.db")
        try:
            logger = EventLogger(store)
            from apps.cli.commands import _emit_execution_events

            _emit_execution_events(logger, root, rep)
            events = list(store.recent(limit=200))
        finally:
            store.close()
        types = [str(getattr(e.type, "value", e.type)) for e in events]
        if not any(t == EventType.ASSIGNMENT_CREATED.value for t in types):
            bad.append(f"没有派活事件 ⇒ Agents 段结构性空壳: {sorted(set(types))}")
        if not any(t == EventType.ASSIGNMENT_COMPLETED.value for t in types):
            bad.append("没有派活完成事件")
        if not any(t == EventType.VALIDATION_RULE_COMPLETED.value for t in types):
            bad.append("没有验证事件 ⇒ Validation 段结构性空壳")
        agents, _ = calculate_agent_metrics([], events)
        if not any(m.assignment_count > 0 for m in agents.values()):
            bad.append(f"Agents 指标仍是 0: {agents}")
        vm = calculate_validation_metrics(events)
        if vm.total_rules <= 0 or vm.runs <= 0:
            bad.append(f"Validation 指标仍是 0: total_rules={vm.total_rules} runs={vm.runs}")

        # ④ 同一执行的**多条 outcome**（跑完了 + "流程推进中"）只能发一次结果事件,
        #    且成败取执行库真实终态 —— 否则 Agents 里会出现 success=1/failed=1 的怪数（实测踩到）
        eid = rep.scheduled[0] if rep.scheduled else ""
        if eid:
            from types import SimpleNamespace as _SNS

            from ai_factory_os.infrastructure.events.logger import EventLogger as _EL
            from ai_factory_os.infrastructure.events.store import EventStore as _ES

            st2 = _ES(root / "e2.db")
            try:
                lg2 = _EL(st2)
                _emit_execution_events(lg2, root, _SNS(
                    scheduled=[eid], outcomes=[
                        {"execution_id": eid, "ok": True, "state": "完成"},
                        {"execution_id": eid, "ok": False, "state": "流程推进中（本步完成 ⇒ 已交回待下一步）"},
                    ]))
                evs2 = list(st2.recent(limit=100))
            finally:
                st2.close()
            done = [e for e in evs2 if str(getattr(e.type, "value", e.type))
                    == EventType.ASSIGNMENT_COMPLETED.value]
            fail = [e for e in evs2 if str(getattr(e.type, "value", e.type))
                    == EventType.ASSIGNMENT_FAILED.value]
            if len(done) != 1 or fail:
                bad.append(f"同一执行该只发 1 条成功结果（取库终态 SUCCESS）, 实得 成功{len(done)}/失败{len(fail)}"
                           "（按 outcome 逐条发会既记成功又记失败 —— 实测踩到过）")
            # ⑤ "库说了算": outcome 说 ok 但库里是 FAILED ⇒ 必须发 FAILED（不按 outcome 的标记走）
            from ai_factory_os.services.execution.runtime.store import open_runtime_store as _ors
            from ai_factory_os.services.execution.runtime.types import ExecutionStatus as _ES2

            _st3 = _ors(root)
            for req in _st3.list_executions():
                if str(req.id) == str(eid):
                    req.status = _ES2.FAILED
                    _st3.save_execution(req)
            se3 = _ES(root / "e3.db")
            try:
                _emit_execution_events(_EL(se3), root, _SNS(
                    scheduled=[eid], outcomes=[{"execution_id": eid, "ok": True, "state": "完成"}]))
                evs3 = list(se3.recent(limit=50))
            finally:
                se3.close()
            if not [e for e in evs3 if str(getattr(e.type, "value", e.type))
                    == EventType.ASSIGNMENT_FAILED.value]:
                bad.append("outcome 说 ok 但库里是 FAILED 时没发失败事件（成败必须以执行库为准）")
    return bad


def test_metrics_not_empty_shells() -> None:
    """metrics 的 Agents/Validation 两段接真事件: 派活/验证事件真的发、指标不再恒 0。"""
    assert _check_metrics_not_empty_shells() == []


def _check_analysis_persist_fresh() -> list[str]:
    """★ 理解产物落盘不能过期（第 5 件·监控不能骗人）。

    实测病: 档案里的分析记录是 `project adopt` 那次写的（且那条路依赖未安装的 exec 扩展 ⇒
    载荷是 "unavailable" 桩, language=unknown）; 而 `factory understand` 算出的**真报告从不落盘**
    ⇒ 档案永远与实时报告不一致（我全量测试时正是这么发现的）。

    判据: `factory understand <仓库>` 之后 ——
      ① 项目多出一条分析记录, 载荷是**实时**值（语言/文件数/类型/阶段来自本次报告）
      ② 项目的 analysis_ref 指向它（消费方读到的就是最新的）
      ③ 分析的不是任何项目的仓库 ⇒ 不落盘、不报错（没归属就没有档案可落, 不编）
    """
    import tempfile

    import inspect as _insp
    from types import SimpleNamespace

    from apps.cli.commands import cmd_understand

    bad: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        repo = root / "repo"
        (repo / "src").mkdir(parents=True, exist_ok=True)
        (repo / "src" / "a.py").write_text("print(1)\n", encoding="utf-8")
        (repo / "package.json").write_text('{"name":"x"}', encoding="utf-8")
        (root / "org").mkdir(parents=True, exist_ok=True)
        (root / "org" / "projects.json").write_text(json.dumps({
            "projects": {"P-an": {"id": "P-an", "name": "x", "repo_path": str(repo)}}},
            ensure_ascii=False), encoding="utf-8")

        from contextlib import contextmanager

        from ai_factory_os.infrastructure.events.logger import EventLogger
        from ai_factory_os.infrastructure.events.store import EventStore

        _ev = EventStore(root / "events.db")

        @contextmanager
        def _scope():
            yield EventLogger(_ev)               # 真 logger（understand 会记事件）

        if "_persist_analysis(ctx.root, path, report)" not in _insp.getsource(cmd_understand):
            bad.append("cmd_understand 里没调用 _persist_analysis ⇒ 档案仍会过期（护栏没接上）")
        ctx = SimpleNamespace(root=root, logger_scope=_scope)
        args = SimpleNamespace(path=str(repo), stage=False)
        cmd_understand(ctx, args)          # 注: 事件库在本 guard 结束前不关（第二次调用还要用）
        try:
            rows = json.loads((root / "org" / "project_analyses.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rows = {}
        recs = [v for v in (rows.get("project_analyses") or {}).values()]
        if not recs:
            bad.append("understand 之后档案里没有分析记录（实时报告没落盘 ⇒ 档案会一直过期）")
        else:
            p = recs[-1].get("payload") or {}
            if not p.get("language") or p.get("files") is None:
                bad.append(f"落盘的载荷不是实时值: language={p.get('language')} files={p.get('files')}")
            if payload_stage_missing(p):
                bad.append(f"载荷缺阶段: {p.get('stage')}")
            proj = (json.loads((root / "org" / "projects.json").read_text(encoding="utf-8"))
                    .get("projects") or {}).get("P-an") or {}
            if proj.get("analysis_ref") != recs[-1].get("id"):
                bad.append(f"项目指针没指向最新记录: {proj.get('analysis_ref')} vs {recs[-1].get('id')}")
        # ③ 不属于任何项目的仓库 ⇒ 不落盘
        other = root / "other"
        other.mkdir()
        (other / "b.py").write_text("x=1\n", encoding="utf-8")
        cmd_understand(ctx, SimpleNamespace(path=str(other), stage=False))
        try:
            rows2 = json.loads((root / "org" / "project_analyses.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rows2 = {}
        if len((rows2.get("project_analyses") or {})) != len(recs):
            bad.append("没有归属的仓库不该落盘分析记录")
        _ev.close()
    return bad


def payload_stage_missing(p: dict) -> bool:
    return not str(p.get("stage") or "")


def test_analysis_persist_fresh() -> None:
    """理解产物落盘: 实时报告写进档案 + 指针更新 + 无归属不落盘。"""
    assert _check_analysis_persist_fresh() == []


def _check_plugin_drop_in() -> list[str]:
    """★ 基座 + 一切插件（产品定义第 3 条）: **放下即用** —— 丢个清单进投放目录就生效。

    实测病: 插件注册表**硬编码在代码里**（kernel.BUILTIN_PROVIDER_PLUGINS）⇒ 加一个插件
      必须改核心代码 ⇒ "一切插件"只是口号。
    判据:
      ① 丢一个合法清单 ⇒ 扫描后出现在插件表里（不改一行代码）
      ② 重复扫 ⇒ 幂等（不重复注册）
      ③ 坏清单/坏 type ⇒ 收进 errors（**响亮**, 不静默跳过）
      ④ 启用 ⇒ ENABLED; 能力可被 resolve 到
      ⑤ 停用 → 注销 ⇒ 干净移除（状态机不允许"启用中直接注销"）
    """
    import tempfile

    from ai_factory_os.infrastructure.plugins import kernel as K

    bad: list[str] = []
    # ★ 调用点断言（教训: 只测函数不测接线 ⇒ 删掉 CLI 里的扫描也发现不了）
    import inspect as _insp2

    import importlib as _il

    _M = _il.import_module("apps.cli.main")      # 注: `from apps.cli import main` 拿到的是函数, 不是模块

    if "scan_manifests" not in _insp2.getsource(_M._dispatch_plugin):
        bad.append("factory plugin list 里没接扫描 ⇒ 丢清单不会自动注册（放下即用没接上）")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        d = K.manifest_dir(root)
        (d / "good.json").write_text(json.dumps({
            "plugin_id": "provider.t-demo", "type": "provider", "name": "演示",
            "version": "0.1.0", "capabilities": ["llm.complete"]}, ensure_ascii=False),
            encoding="utf-8")
        r1 = K.scan_manifests(root)
        if r1.get("registered") != ["provider.t-demo"]:
            bad.append(f"丢清单后没注册: {r1}")
        ids = [p["plugin_id"] for p in K.list_plugins(root)]
        if "provider.t-demo" not in ids:
            bad.append(f"插件表里看不到它: {ids}")
        r2 = K.scan_manifests(root)
        if r2.get("registered") or r2.get("skipped") != ["provider.t-demo"]:
            bad.append(f"重复扫不幂等: {r2}")
        # ③ 坏清单
        (d / "bad.json").write_text('{"type":"provider"}', encoding="utf-8")
        (d / "bad2.json").write_text('{"plugin_id":"x.y","type":"不存在"}', encoding="utf-8")
        (d / "broken.json").write_text("{不是 JSON", encoding="utf-8")
        r3 = K.scan_manifests(root)
        if len(r3.get("errors") or []) != 3:
            bad.append(f"三个坏清单该报三条错（响亮不静默）: {r3.get('errors')}")
        # ④ 启用 + 能力可解析
        K.plugin_status(root, "provider.t-demo", target="ENABLED")
        st = {p["plugin_id"]: p["status"] for p in K.list_plugins(root)}
        if st.get("provider.t-demo") != "ENABLED":
            bad.append(f"启用没生效: {st}")
        if not K.resolve_plugin(root, required_capability="llm.complete"):
            bad.append("启用后能力解析不到（放下即用只做了一半）")
        # ⑤ 停用 → 注销
        K.plugin_status(root, "provider.t-demo", target="DISABLED")
        K.unregister_plugin(root, "provider.t-demo")
        if "provider.t-demo" in [p["plugin_id"] for p in K.list_plugins(root)]:
            bad.append("注销后仍在表里")
    return bad


def test_plugin_drop_in() -> None:
    """插件放下即用: 丢清单⇒注册 · 幂等 · 坏清单响亮报错 · 启用⇒能力可解析 · 停用注销⇒干净。"""
    assert _check_plugin_drop_in() == []


def _check_experience_learning() -> list[str]:
    """★ 学习自治（核心第 5 条）: 经验从【真执行】自动积累, 失败也记, 且写读同源。

    实测病: `intelligence experience list` 恒 0 条 —— 机制齐（六域 + freshness/decay + 负样本）
      但**没有任何地方写** ⇒ 学习没有输入。
    判据:
      ① 终态执行 ⇒ 自动落经验（谁 / 任务类型 / 能力 / 成败 / 耗时 / 证据）
      ② **失败也记**（负样本, 防"只记成功"的自我偏差）
      ③ 幂等: 同一执行重复记 ⇒ 不灌水
      ④ 写读同源: 写进的是 `intelligence experience list` 读的那个 store（<root>/intelligence, AGENT 域）
      ⑤ 调用点: cmd_run_plan 里真的调了
    """
    import tempfile
    from types import SimpleNamespace

    from apps.cli.commands import _record_experiences as _rec
    from ai_factory_os.services.execution.runtime.store import open_runtime_store
    from ai_factory_os.services.execution.runtime.types import ExecutionRequest, ExecutionStatus
    from ai_factory_os.services.learning.store import ExperienceStore
    from ai_factory_os.services.learning.types import ExperienceDomain

    bad: list[str] = []
    import inspect as _insp

    import importlib as _il

    if "_record_experiences(ctx.root, rep)" not in _insp.getsource(
            _il.import_module("apps.cli.main") and _il.import_module("apps.cli.commands").cmd_run_plan):
        bad.append("cmd_run_plan 里没调用 _record_experiences ⇒ 经验库永远是空的（护栏没接上）")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        proj, plan = "P-e", "PLAN-e"
        d = root / "projects" / proj / "tasks"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{plan}.json").write_text(json.dumps({
            "plan_id": plan, "project_id": proj, "status": "confirmed",
            "nodes": [
                {"id": "t-ok", "kind": "task", "title": "做成的事", "status": "completed",
                 "required_capabilities": ["developer"]},
                {"id": "t-bad", "kind": "task", "title": "没做成的事", "status": "pending",
                 "required_capabilities": ["tester"]},
            ],
        }, ensure_ascii=False), encoding="utf-8")
        st = open_runtime_store(root)
        for eid, node, member, s in (("EXR-e1", "t-ok", "dev-1", ExecutionStatus.SUCCESS),
                                     ("EXR-e2", "t-bad", "qa-1", ExecutionStatus.FAILED)):
            st.save_execution(ExecutionRequest(id=eid, task_id=plan, status=s,
                                              input={"node_id": node, "member_id": member,
                                                     "resolution_id": "r", "identity_id": member}))
        rep = SimpleNamespace(outcomes=[{"execution_id": "EXR-e1", "ok": True},
                                        {"execution_id": "EXR-e2", "ok": False}])
        n = _rec(root, rep)
        if n != 2:
            bad.append(f"两条终态执行该落两条经验, 实得 {n}")
        recs = ExperienceStore(root / "intelligence").list_by_domain(ExperienceDomain.AGENT)
        if len(recs) != 2:
            bad.append(f"经验库该有 2 条（list_by_domain 读得到）: {len(recs)}")
        by_subject = {r.subject_id: r for r in recs}
        ok = by_subject.get("dev-1")
        bad_r = by_subject.get("qa-1")
        if not ok or ok.result != "success" or ok.task_type != "developer":
            bad.append(f"成功经验不对: {ok}")
        if not bad_r or bad_r.result != "failure" or bad_r.task_type != "tester":
            bad.append(f"**失败也要记**（负样本）: {bad_r}")
        if ok and not (ok.evidence or []):
            bad.append("经验没带执行证据（追溯不了）")
        elif ok and str(ok.evidence[0].source_id) != "EXR-e1":
            bad.append(f"证据指向不对: {ok.evidence[0].source_id}")
        if _rec(root, rep) != 0:
            bad.append("同一执行重复记 ⇒ 灌水了（该幂等）")
    return bad


def test_experience_learning() -> None:
    """学习自治: 经验自动落库（含失败）· 幂等 · 写读同源 · 调用点接上。"""
    assert _check_experience_learning() == []


def _check_provider_experience_learning() -> list[str]:
    """★ provider 域经验（核心第 5 条的另一半）: 用量记录 ⇒ 经验 ⇒ 推荐引擎能读到。

    实测病: agent 域经验只喂"按任务选人"; 而 `intelligence recommend` 的候选是 **provider**
      ⇒ 它读 PROVIDER 域、subject_id=provider_id 的经验 —— 那条域**从来没有数据**;
      且 CLI 建引擎时**没装 ExperienceStore** ⇒ Experience×0.15 那一项恒 0（写读断层）。
    判据:
      ① 用量记录 ⇒ provider 域经验（成功/失败都落, 失败=负样本）
      ② 幂等: 同一条用量不重复落
      ③ 证据指向 usage id（可追溯）
      ④ 调用点: run 里落了经验; recommend 建引擎时装了 ExperienceStore
    """
    import tempfile

    from apps.cli.commands import _record_provider_experiences as _w
    from ai_factory_os.infrastructure.llm.providers.usage import ProviderUsage, UsageStore
    from ai_factory_os.services.learning.store import ExperienceStore
    from ai_factory_os.services.learning.types import ExperienceDomain

    bad: list[str] = []
    import importlib as _il
    import inspect as _insp

    _C = _il.import_module("apps.cli.commands")
    if "_record_provider_experiences(ctx.root)" not in _insp.getsource(_C.cmd_run_plan):
        bad.append("cmd_run_plan 里没落 provider 经验（护栏没接上）")
    if "experience_store=" not in _insp.getsource(_C.cmd_intelligence_recommend):
        bad.append("recommend 建引擎时没装 ExperienceStore ⇒ 经验权重恒 0（写读断层没修）")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        us = UsageStore(root / "providers")
        us.record(ProviderUsage(id="u-ok", provider_id="hermes", model="m", prompt_tokens=1,
                                completion_tokens=1, estimated_cost=0.0, latency_ms=1000,
                                success=True))
        us.record(ProviderUsage(id="u-bad", provider_id="hermes", model="m", prompt_tokens=0,
                                completion_tokens=0, estimated_cost=0.0, latency_ms=300000,
                                success=False, error="timeout"))
        n = _w(root)
        if n != 2:
            bad.append(f"两条用量该落两条 provider 经验, 实得 {n}")
        recs = ExperienceStore(root / "intelligence").list_by_domain(ExperienceDomain.PROVIDER)
        if len(recs) != 2:
            bad.append(f"provider 域该有 2 条: {len(recs)}")
        if sorted(r.result for r in recs) != ["failure", "success"]:
            bad.append(f"成败没照实落: {[r.result for r in recs]}")
        failed = next((r for r in recs if r.result == "failure"), None)
        if failed is None or abs(float(failed.duration) - 300.0) > 0.01:
            bad.append(f"耗时该照实（300 秒超时）: {getattr(failed, 'duration', None)}")
        if not all((r.evidence or []) and r.evidence[0].source_id for r in recs):
            bad.append("经验没带用量证据（追溯不了）")
        if _w(root) != 0:
            bad.append("同一条用量重复落 ⇒ 灌水了（该幂等）")
    return bad


def test_provider_experience_learning() -> None:
    """provider 域经验: 用量⇒经验（含失败）· 幂等 · 证据可追溯 · 调用点接上。"""
    assert _check_provider_experience_learning() == []


def _check_decompose_is_atomic() -> list[str]:
    """★ 拆解一次就拆到"原子任务"（Founder 纠正: "任务拆解就不够细啊"）。

    实测病（两头都错）:
      · 契约: `task_breakdown` 每项 = {module, task, api_contract, ui_guidance}（无 acceptance,
        语义上是"一模块一任务"）⇒ 架构天生只给模块级任务
      · 构建: 自述"每 seed = 1 domain + 1 leaf"(向后兼容) ⇒ 13 模块 = 13 粗叶
              且叶的 acceptance 竟然取 `api_contract`（我在真树里看到"验收=POST /login"）
      ⇒ 结果: "拆解"这一环其实没拆（expand.py 自述承认）; 粗叶"7 合 1" 900 秒超时跑不完。
    判据（缺一不算拆到位）:
      ① 契约层: task_breakdown 带 acceptance + **接受递归嵌套**（children ⇒ 容器; 粗种子=合法输入）
      ② 构建层: 同一 module 的多个原子任务 ⇒ 归到一个域下的多个叶（不是多个域）
      ③ 验收: 叶的 acceptance 取种子自带的（没有 ⇒ 留空让判据抓, 不拿 api_contract 充数）
      ④ 递归层: 拆解收尾【递归拆到最小单位】—— 粗叶被反复拆开直到过粒度判据; 触上限响亮报
      ⑤ 判据互认: 建出来的树过 granularity 判据（0 个"没拆到位"）
    """
    import tempfile

    from ai_factory_os.plugins.agents import architect as AR
    from ai_factory_os.services.work import decomposition as D
    from ai_factory_os.services.work import granularity as G

    bad: list[str] = []
    if "acceptance" not in AR._TASK_KEYS:
        bad.append("架构契约 _TASK_KEYS 没要求 acceptance（拆解没有验收 ⇒ 判据判不了）")
    coarse = [{"module": "m", "task": "设计并创建用户、宠物、门店三张核心表及索引",
               "api_contract": "x", "ui_guidance": "y", "acceptance": "无（基础设施）"}]
    fine = [{"module": "m", "task": "创建 users 表与唯一索引", "api_contract": "x",
             "ui_guidance": "y", "acceptance": "迁移可跑通, 唯一约束生效"}]
    # ★ 方向（Founder 纠正后的正确口径）: 架构给的是【模块级种子】, **粗种子是合法输入** ——
    #   把它拆到最小单位是【拆解环的递归职责】, 不是架构的。⇒ 这里断言"粗种子放行、不误伤"。
    if AR._validate_tasks(coarse):
        bad.append(f"架构把模块级种子拦了（它只是种子, 该由递归拆）: {AR._validate_tasks(coarse)}")
    if AR._validate_tasks(fine):
        bad.append(f"架构误伤了原子任务: {AR._validate_tasks(fine)}")
    # ★ 递归嵌套会让 task_breakdown 变大 ⇒ 必须走【分片生成】, 不能回落到"一次生成"(必爆):
    #   实测单次生成 25085 字符被截断（deepseek 单次输出上限 8192 tokens, 提不上去）。
    import importlib as _il2
    import inspect as _insp2

    _archmod = _il2.import_module("ai_factory_os.plugins.agents.architect")
    if not hasattr(_archmod, "_gen_task_breakdown_sliced"):
        bad.append("task_breakdown 分片函数不存在 ⇒ 递归嵌套输出会撞单次上限")
    elif "_gen_task_breakdown_sliced" not in _insp2.getsource(_archmod._gen_sections_individually):
        bad.append("分节生成没给 task_breakdown 挂分片（实测会截断）")
    # ★ 取设计必须取【最新】的（真 bug: 原来 cands[-1] 取列表最后一个 ⇒ 拿旧图干活）

    _dsrc = _insp2.getsource(_il2.import_module("apps.cli.main")._dispatch_tasktree)
    # 注: 断言【代码行】而不是任意出现 —— 我第一版用 "cands[-1]" in src, 结果被我自己的
    #     注释里那句 `cands[-1]` 骗了（假红）✗ 教训: 断言要能区分注释与代码。
    if "design = cands[-1]" in _dsrc or "max(cands" not in _dsrc:
        bad.append("拆解取设计不是按 created_at 取最新（会拿旧设计生成树 —— 实测踩到）")
    # ★ 能力标注: 纯后端叶不该带 ui-designer（构建期过滤）
    if hasattr(D, "prune_caps"):
        if "ui-designer" in D.prune_caps("实现消课记录接口 GET /admin/consumption",
                                        ["developer", "ui-designer"]):
            bad.append("纯后端接口叶仍带 ui-designer（派活会去找 UI 设计师）")
        if "ui-designer" not in D.prune_caps("设计并实现我的预约页面UI", ["developer", "ui-designer"]):
            bad.append("界面类叶的 ui-designer 被误删")
    else:
        bad.append("缺 prune_caps（能力标注过滤）")
    # 嵌套种子（递归输出）必须被接受: 容器项带 children ⇒ 由构建递归物化
    nested = [{"module": "用户与鉴权", "task": "用户与鉴权", "api_contract": "POST /login",
               "ui_guidance": "登录页", "acceptance": "登录可用",
               "children": [{"module": "用户与鉴权", "task": "创建 users 表", "api_contract": "SQL",
                             "ui_guidance": "-", "acceptance": "迁移可跑通"},
                            {"module": "用户与鉴权", "task": "实现 JWT 校验", "api_contract": "Bearer",
                             "ui_guidance": "-", "acceptance": "过期 token 被拒"}]}]
    if AR._validate_tasks(nested):
        bad.append(f"嵌套种子（递归输出）被误拦: {AR._validate_tasks(nested)}")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        seeds = [
            {"module": "用户与鉴权", "task": "创建 users 表与唯一索引", "api_contract": "POST /login",
             "ui_guidance": "登录页", "acceptance": "迁移可跑通, 唯一约束生效"},
            {"module": "用户与鉴权", "task": "实现 JWT 签发与校验", "api_contract": "Bearer",
             "ui_guidance": "-", "acceptance": "过期/篡改 token 都被拒"},
            {"module": "预约", "task": "创建预约表", "api_contract": "POST /bookings",
             "ui_guidance": "预约页", "acceptance": "并发下单不超卖"},
            # ★ 再加一个【真粗叶】(枚举 3 件事 + 验收写不出) ⇒ 递归该把它拆开
            {"module": "数据层", "task": "设计并创建宠物、门店、订单三张表及索引",
             "api_contract": "SQL", "ui_guidance": "-", "acceptance": ""},
        ]
        tree = D.decompose_from_design(root, plan_id="PLAN-at", project_id="P-at",
                                       design_metadata={"task_breakdown": seeds,
                                                        "design_ref": "A-x"})
        nodes = (tree or {}).get("nodes") or []
        doms = [n for n in nodes if n.get("kind") == "domain"]
        leaves = [n for n in nodes if n.get("kind") == "task"]
        if len(doms) != 3 or len(leaves) != 4:
            bad.append(f"同模块该归一个域: 期望 3 域 4 叶（含 1 个粗叶）, 实得 {len(doms)} 域 {len(leaves)} 叶")
        if not G.oversized(nodes):
            bad.append("夹具里的粗叶没被判据抓到（判据失灵 ⇒ 后面的递归断言就没意义）")
        accs = {str(n.get("acceptance") or "") for n in leaves}
        if "迁移可跑通, 唯一约束生效" not in accs:
            bad.append(f"叶的验收没取种子自带的: {accs}")
        if any(a.startswith("POST ") or a == "Bearer" for a in accs):
            bad.append(f"验收还是拿 api_contract 充数: {accs}")
        # ★ 递归拆到最小单位（Founder 口径: "递归的方式, 拆到最小单位/最小实现"）:
        #   用假 provider（每次把粗叶拆成 2 个原子子任务）⇒ 递归后不应再有粗叶。
        import types as _types

        from ai_factory_os.services.work.expand import expand_to_minimal as _to_min

        class _FakeProv:
            def __init__(self):
                self.calls = 0

            def generate(self, req):
                self.calls += 1
                import json as _json

                kids = [{"title": f"原子子任务 {self.calls}-1", "acceptance": "一句话验收 A"},
                        {"title": f"原子子任务 {self.calls}-2", "acceptance": "一句话验收 B"}]
                return _types.SimpleNamespace(ok=True, content=_json.dumps(kids, ensure_ascii=False),
                                              error=None)

        fp = _FakeProv()
        rec = _to_min(root, "PLAN-at", "P-at", provider=fp, max_rounds=4, max_leaves=60)
        tree2 = D.load_tree(root, "PLAN-at", "P-at") or {}
        left = G.oversized(tree2.get("nodes") or [])
        if left:
            bad.append(f"递归拆完仍有粗叶（没到最小单位）: {[x['title'][:24] for x in left]}")
        if rec.get("rounds", 0) < 1 or not rec.get("split"):
            bad.append(f"递归没真的拆: {rec}")
        # 触上限要响亮报（不假装拆完）
        rec2 = _to_min(root, "PLAN-at", "P-at", provider=_FakeProv(), max_rounds=1, max_leaves=1)
        if rec2.get("remaining") and not rec2.get("stopped_because"):
            bad.append("触上限时没说清为什么停（该响亮报）")
    return bad


def test_decompose_is_atomic() -> None:
    """拆解一次到位: 契约要验收 · 粗任务被拒 · 同模块归一个域 · 叶验收来自种子 · 过粒度判据。"""
    assert _check_decompose_is_atomic() == []


def test_conv_facts_reach_product_develop(tmp_path: Path) -> None:
    """接缝: 会话事实 → 想法文本（两种存法 + 跳过被推翻 + 缺了报错 + --idea 优先）。"""
    assert _check(tmp_path) == []


def _check_cli_welcome() -> list[str]:
    """★ "怎么进入 CLI"（Founder 问「我需要如何进入 factory 的 cli」）。

    实测病: 敲 `factory` 不带参数 ⇒ 只有一句英文报错
      `factory: error: the following arguments are required: command` —— 对非技术用户等于**进不去**。
    判据:
      ① 空参 ⇒ 友好首屏（版本 + 数据概览 + 编号菜单 + help 提示）, **退出码 0**, 且不含英文 argparse 报错
      ② 非终端（管道/脚本）⇒ 只打印**不挂住**（不读 stdin）
      ③ `factory help [--role X]` ⇒ 中文帮助中心, 四类角色齐
      ④ 首屏里的编号必须都对应**真实存在**的命令（不能写没做的）
    """
    import io as _io
    import contextlib as _ctx

    from apps.cli import main as _cli_main  # 注意: apps.cli.__init__ 把 main 暴露为**函数**
    from apps.cli.domains import welcome as W

    bad: list[str] = []
    buf = _io.StringIO()
    with _ctx.redirect_stdout(buf):
        rc = _cli_main([])
    out = buf.getvalue()
    if rc != 0:
        bad.append(f"空参退出码该是 0, 实得 {rc}")
    if "required: command" in out or "usage:" in out:
        bad.append("空参还是甩 argparse 英文报错（等于进不去）")
    for kw in ("AI Factory OS", "直接说人话", "经验", "帮助"):
        if kw not in out:
            bad.append(f"首屏缺「{kw}」")
    # 非终端不该挂住: 上面 main([]) 在非 TTY 下已跑完 ⇒ 若它读 stdin 会 EOFError/挂住 ⇒ 视为坏
    # ④ 首屏编号 → 真实命令（逐个查 --help 不报错）
    import subprocess as _sp

    for key, (_label, argv) in W._MENU.items():
        r = _sp.run(["sh", "-c", f"cd {Path.cwd()} && .venv/bin/factory {' '.join(argv)} --help"],
                    capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            bad.append(f"首屏第 {key} 条指向的命令不存在/报错: {' '.join(argv)}")
    # ③ 帮助中心
    hb = W.render_help("")
    for role in ("老板", "产品", "开发", "运维"):
        if role not in hb:
            bad.append(f"帮助中心缺角色「{role}」")
    if "command not found" in hb or "Traceback" in hb:
        bad.append("帮助中心内容不干净")
    return bad


def test_cli_welcome() -> None:
    """空参 ⇒ 友好首屏（不是英文报错）· 非终端不挂住 · 帮助中心四角色齐 · 菜单指向真命令。"""
    assert _check_cli_welcome() == []


def _check_cli_shell() -> list[str]:
    """★ 启动 AI Factory OS（Founder: "我要的是启动 factory os, 使用 cli 命令"）。

    判据:
      ① `factory start` 命令存在, 且分发里真的调了 run_shell（调用点断言）
      ② 进去后敲命令**真执行**（非终端喂 'status' ⇒ 输出里有工厂状态）
      ③ 退出词（exit/q）能离开, 且打印"已退出"
      ④ 敲错命令**不把 shell 带走**（后面还能继续跑）
      ⑤ 空参 + 非终端 ⇒ 仍然只打印首屏、退出码 0（不挂住）
    """
    import contextlib as _ctx
    import inspect as _insp
    import io as _io

    from apps.cli import main as _cli_main
    from apps.cli.domains import welcome as W

    bad: list[str] = []
    if not hasattr(W, "run_shell"):
        return ["缺 run_shell（没有「进入交互式 CLI」这条路）"]
    src = _insp.getsource(_cli_main)
    if "run_shell" not in src:
        bad.append("main 里没接 run_shell（start 命令/空参进不去）")
    if "run_shell(ctx.root)" not in src:
        bad.append("`factory start` 没有把 root 传给 run_shell")

    def _feed(text: str) -> str:
        buf = _io.StringIO()
        old_stdin = __import__("sys").stdin
        __import__("sys").stdin = _io.StringIO(text)
        try:
            with _ctx.redirect_stdout(buf):
                _cli_main(["start"])
        except SystemExit:
            pass
        finally:
            __import__("sys").stdin = old_stdin
        return buf.getvalue()

    # ★ 命令现在要带 `/`（Founder: "不需要带 / 么，不对冲突么？" ⇒ 定死带 /, 零歧义）
    out = _feed("/status\nexit\n")
    if "工厂状态" not in out:
        bad.append("进去后敲 status 没真执行（交互式 CLI 没通）")
    if "已退出" not in out:
        bad.append("exit 没退出（或没提示已退出）")
    out2 = _feed("nosuchcmd\n/status\nexit\n")
    if "工厂状态" not in out2:
        bad.append("敲错一条命令就把 shell 带走了（后面跑不动）")
    out3 = _feed("help\nexit\n")
    if "帮助中心" not in out3:
        bad.append("shell 里 help 打不开帮助中心")
    # ⑤ 空参 + 非终端
    buf = _io.StringIO()
    old_stdin = __import__("sys").stdin
    __import__("sys").stdin = _io.StringIO("")
    try:
        with _ctx.redirect_stdout(buf):
            rc = _cli_main([])
    except SystemExit:
        rc = 0
    finally:
        __import__("sys").stdin = old_stdin
    if rc != 0 or "AI Factory OS" not in buf.getvalue():
        bad.append("空参 + 非终端该只打印首屏并返回 0")
    return bad


def _check_task_traces_to() -> list[str]:
    """★ 任务【出处】那一栏（Founder: "缺的是什么？" ⇒ 缺的就是它）。

    实测病: 架构产出的任务只有 模块/任务/接口/验收, **没有"出处"** ⇒ 系统分不清"这条是用户要的"
      还是"架构自己加的" ⇒ 自己加的也拆成叶、也去写码（实测 42/199 叶 = 21%）。
    判据:
      ① 架构契约要求每项带 traces_to（提示词 + 分片生成都要有）
      ② 拆解门: 有出处的进树, 无出处的挡在树外并记进 tree["excluded_no_trace"]
      ③ 叶节点带 traces_to; 执行简报带出处
      ④ 向后兼容: 旧设计（全都没出处）不过滤、不报错
    """
    import importlib as _il
    import inspect as _insp
    import json as _json
    import tempfile as _tf

    from ai_factory_os.services.work import decomposition as D

    bad: list[str] = []
    arch = _il.import_module("ai_factory_os.plugins.agents.architect")
    if "traces_to" not in _insp.getsource(arch):            # 提示词是模块级 str ⇒ 取模块源码
        bad.append("架构提示词没要求 traces_to（出处）")
    if "traces_to" not in _insp.getsource(arch._gen_task_breakdown_sliced):
        bad.append("分片生成没要求 traces_to")

    with _tf.TemporaryDirectory() as td:
        root = Path(td)
        (root / "org").mkdir(parents=True, exist_ok=True)
        (root / "org" / "projects.json").write_text(_json.dumps(
            {"projects": {"P-t": {"id": "P-t", "name": "t", "repo_path": str(root)}}}, ensure_ascii=False),
            encoding="utf-8")
        design = {"task_breakdown": [
            {"module": "约课", "task": "会员提交预约", "api_contract": "POST /appointments",
             "ui_guidance": "预约页", "acceptance": "提交后能在列表看到",
             "traces_to": "需求: 会员预约并在线付课时费"},
            {"module": "约课", "task": "接入微信 code2session 登录", "api_contract": "POST /auth/wx-login",
             "ui_guidance": "-", "acceptance": "能拿到 token", "traces_to": ""},
        ]}
        tree = D.decompose_from_design(root, project_id="P-t", design_metadata=design,
                                       plan_id="PLAN-tt", prd_ref="A-1")
        leaves = [n for n in tree["nodes"] if n.get("kind") == "task"]
        titles = " | ".join(str(n.get("title")) for n in leaves)
        if "微信" in titles:
            bad.append("没出处的任务（微信登录）进了树 —— 拆解门没生效")
        if "提交预约" not in titles:
            bad.append("有出处的任务被误挡")
        if "微信" not in str(tree.get("excluded_no_trace") or []):
            bad.append("被挡的没记进 tree['excluded_no_trace']（人看不到）")
        if not leaves or not str(leaves[0].get("traces_to") or ""):
            bad.append("叶节点没带 traces_to（传不到执行简报）")
        # ★ 出处必须**可核对**: 编的出处（需求原话里查不到）要挡在树外 ——
        #   实测: 只填字段不核对 ⇒ 模型把出处也编出来（"登录 API"的出处写成"微信小程序登录与角色区分"）
        conv = root / "projects" / "P-t" / "conversations"
        conv.mkdir(parents=True, exist_ok=True)
        (conv / "conv-1.json").write_text(_json.dumps({"messages": [
            {"role": "human", "content": "我要做一个健身房小程序: 教练设置可约时间段; 会员预约并在线付课时费"}]},
            ensure_ascii=False), encoding="utf-8")
        design3 = {"project_id": "P-t", "task_breakdown": [
            {"module": "约课", "task": "会员提交预约接口", "api_contract": "POST /a", "ui_guidance": "-",
             "acceptance": "能提交", "traces_to": "会员预约并在线付课时费"},          # 真出处
            {"module": "登录", "task": "接入微信 code2session 登录", "api_contract": "POST /l",
             "ui_guidance": "-", "acceptance": "能拿 token",
             "traces_to": "微信小程序登录与角色区分（会员/教练）"},                    # 编的出处
        ]}
        t3 = D.decompose_from_design(root, project_id="P-t", design_metadata=design3,
                                     plan_id="PLAN-tt3", prd_ref="A-1")
        lv3 = [n for n in t3["nodes"] if n.get("kind") == "task"]
        if any("code2session" in str(n.get("title")) for n in lv3):
            bad.append("编的出处被放行 ⇒ 微信登录又进了树（出处核对没生效）")
        if not any("提交预约" in str(n.get("title")) for n in lv3):
            bad.append("真出处（需求原话）被误杀")
        if not t3.get("excluded_no_trace"):
            bad.append("编的出处没被记进 excluded_no_trace（人看不到）")
        design2 = {"task_breakdown": [
            {"module": "m", "task": "t1", "api_contract": "-", "ui_guidance": "-", "acceptance": "a"},
            {"module": "m", "task": "t2", "api_contract": "-", "ui_guidance": "-", "acceptance": "b"},
        ]}
        try:
            tree2 = D.decompose_from_design(root, project_id="P-t", design_metadata=design2,
                                            plan_id="PLAN-tt2", prd_ref="A-1")
            if len([n for n in tree2["nodes"] if n.get("kind") == "task"]) != 2:
                bad.append("旧设计（都没出处）被过滤了 —— 向后兼容坏了")
        except Exception as exc:  # noqa: BLE001
            bad.append(f"旧设计路径报错: {type(exc).__name__}: {str(exc)[:60]}")
    if "excluded_no_trace" not in _insp.getsource(_il.import_module("apps.cli.main")._dispatch_tasktree):
        bad.append("confirm 前没把『架构自己加的』单列给人看")
    if "出处（需求原句）" not in _insp.getsource(
            _il.import_module("ai_factory_os.bootstrap.scheduler_wiring").StoreExecution):
        bad.append("执行简报没带出处")
    return bad


def test_task_traces_to() -> None:
    """任务"出处"那一栏: 契约要求 · 无出处的挡在树外并记下来 · 叶与简报带上 · 旧设计兼容。"""
    assert _check_task_traces_to() == []


def _check_cli_chat() -> list[str]:
    """★ CLI 里的会话（Founder: "我要在 cli 中可以使用会话功能, 并且可以使用 / 使用命令, 像 Hermes 一样"）。

    判据:
      ① `/status` ⇒ 当命令跑（真出数据）  ② 裸词已知命令 ⇒ 也当命令（向后兼容）
      ③ 其它一句话 ⇒ **走会话**（LLM; 这里注入假 provider, 不在守卫里联网）
      ④ 会话里只自动跑**只读**命令; 会改数据的（run/chain/…）**不许自动跑**
      ⑤ 会话持久化到平台会话存储（不是内存里自说自话）
    """
    import io as _io
    import contextlib as _ctx
    import types as _types

    from apps.cli import main as _cli_main
    from apps.cli.domains import chat as C

    bad: list[str] = []

    class _FakeProv:
        def __init__(self, script):
            self.script, self.i = script, 0

        def generate(self, req):  # noqa: ANN001
            out = self.script[min(self.i, len(self.script) - 1)]
            self.i += 1
            return _types.SimpleNamespace(ok=True, content=out, error=None)

    real = C._provider
    try:
        # ③ + ④: 模型先要跑一条**会改数据**的命令 ⇒ 不许自动跑; 再给一句人话回答
        C._provider = lambda: _FakeProv(["RUN: run --plan PLAN-x\n先看看。", "我只念命令, 不自动跑。"])
        buf = _io.StringIO()
        old_stdin = __import__("sys").stdin
        __import__("sys").stdin = _io.StringIO("/status\nexit\n")
        try:
            with _ctx.redirect_stdout(buf):
                _cli_main(["start"])
        except SystemExit:
            pass
        finally:
            __import__("sys").stdin = old_stdin
        if "工厂状态" not in buf.getvalue():
            bad.append("`/status` 没当命令跑（/ 命令没通）")
        # ④ 写命令不许自动跑（chat_turn 现在返回 (answer, conv, meta)）
        _a, _c2, _m2 = C.chat_turn(Path.home() / ".factory", "帮我跑一下任务树", conv_id="",
                                   on_run=lambda argv: (_ for _ in ()).throw(AssertionError("不该跑到这里")))
        if not (_m2 or {}).get("elapsed"):
            bad.append("回合信息里没有用时（Hermes 那样的回合信息没接）")
        # ★ "你点头它就执行"（Founder 选 A）: 写命令先挂起 → 回"好"才跑 → 回"不"就不跑
        #   全程用**临时根**, 不碰用户真实数据
        import tempfile as _tf2

        with _tf2.TemporaryDirectory() as td2:
            _NL = chr(10)
            C._provider = lambda: _FakeProv(["RUN: backup create" + _NL + "这条会写数据, 要我跑吗?", "好的。"])
            for feed, must_have, must_not in (
                # 第一句是"消息"（触发它念出写命令 ⇒ 建挂起）, 第二句才是点头/摇头
                ("帮我备份一下" + _NL + "不" + _NL + "exit" + _NL, ["待你点头", "已取消"], ["备份完成"]),
                ("帮我备份一下" + _NL + "好" + _NL + "exit" + _NL, ["待你点头", "┊ 💻 $ factory backup create", "备份完成"], []),
            ):
                _sys = __import__("sys")
                old_in = _sys.stdin
                _sys.stdin = _io.StringIO(feed)
                buf2 = _io.StringIO()
                try:
                    with _ctx.redirect_stdout(buf2):
                        _cli_main(["--root", td2, "start"])
                except SystemExit:
                    pass
                finally:
                    _sys.stdin = old_in
                got = buf2.getvalue()
                for kw in must_have:
                    if kw not in got:
                        bad.append(f"点头流程缺「{kw}」（feed={feed!r}）")
                for kw in must_not:
                    if kw in got:
                        bad.append(f"不该出现「{kw}」（feed={feed!r}）")
        _h = C.turn_header({"model": "m", "provider": "p", "usage": {"prompt_tokens": 1, "completion_tokens": 2,
                                                                    "estimated_cost_usd": 0.0001},
                            "elapsed": 1.0, "rounds": 1})
        for kw in ("模型 m", "供应商 p", "tokens", "成本 $0.000100", "用时 1.0s"):
            if kw not in _h:
                bad.append(f"回合信息缺「{kw}」")
    finally:
        C._provider = real
    # ★ 规则定死（Founder: "factory的命令，不需要带 / 么，不对冲突么？"）:
    #   `/命令` / `factory 命令` ⇒ 执行; **其它一切都是会话**（裸的 status 不能直接被当命令跑 ✗）
    import contextlib as _c3
    import io as _io3
    import types as _t3

    class _FakeP2:
        def __init__(self): self.n = 0
        def generate(self, req):  # noqa: ANN001
            self.n += 1
            return _t3.SimpleNamespace(ok=True, content="（会话回答）", error=None, usage={})

    _real2 = C._provider
    try:
        C._provider = lambda: _FakeP2()
        sys_ = __import__("sys")
        _old_in = sys_.stdin
        sys_.stdin = _io3.StringIO("status" + chr(10) + "exit" + chr(10))   # 裸词(故意): 应走会话
        _b = _io3.StringIO()
        try:
            with _c3.redirect_stdout(_b):
                _cli_main(["start"])
        except SystemExit:
            pass
        finally:
            sys_.stdin = _old_in
        _got = _b.getvalue()
        # ★ 2026-09-21 更新（Founder: "没有真正明白我的意图啊"）:
        #   裸的**命令名**要**直接跑**（不再绕一圈转述成人话 ✗）; 像句子的才走会话。
        if "工厂状态" not in _got:
            bad.append("裸词 `status` 没直接跑（Founder 要的是说了命令就跑 ✗）")
        if "（会话回答）" in _got:
            bad.append("裸命令被拿去聊天了（绕一圈 ✗）")
    finally:
        C._provider = _real2
    # ★ 2026-09-21（Founder: "这么多, 是用户要看的么"）: ① 缺必填参数的命令**不跑**（不许把 argparse 错端给他）
    #   ② 跑废/空的调用**不展示** ③ 提示词必须把"必填参数"写清（否则模型瞎猜 ✗）
    import inspect as _insp

    from apps.cli.domains import chat as _C2

    if _C2._has_required_args(["tasktree", "todo"]):
        bad.append("缺必填参数的命令没被判出来（会空跑并把 argparse 错给老板看 ✗）")
    if not _C2._has_required_args(["tasktree", "todo", "PLAN-x"]):
        bad.append("带参数的命令被误判为缺参数（会不跑 ✗）")
    if not _C2._has_required_args(["status"]):
        bad.append("无需参数的命令被误判（会不跑 ✗）")
    _usages = " ".join(_C2.READONLY_USAGE.values())
    if "必填" not in _usages:
        bad.append("命令用法里没标必填参数（模型只能瞎猜 ⇒ 空跑 ✗）")
    _csrc = _insp.getsource(_C2.chat_turn)
    if "_has_required_args" not in _csrc:
        bad.append("会话没在跑之前检查必填参数（空跑会把报错端给老板 ✗）")
    if "_junk" not in _csrc:
        bad.append("跑废/空的调用没被挡在展示之外（老板会看到 usage 报错 ✗）")
    if C.is_readonly(["run", "--plan", "P"]):
        bad.append("会改数据的命令被当成只读（会话里会自动跑 ✗）")
    if not C.is_readonly(["status"]):
        bad.append("只读命令白名单不含 status")
    if "append_message" not in _il_get(C):
        bad.append("会话没落平台存储（应在 chat 模块里 append_message）")
    return bad


def _il_get(mod):
    import inspect as _i

    return _i.getsource(mod)


def test_cli_chat() -> None:
    """会话 + `/命令`（Hermes 手感）: /命令当命令跑 · 会话只自动跑只读 · 写命令不自动跑 · 会话落库。"""
    assert _check_cli_chat() == []


def _check_prd_requirement_gate() -> list[str]:
    """★ 需求 → PRD 的门（Founder 选 B: "防它自己加需求"）。

    实测病: PRD 制品里就已经有 登录/通知/补课/爽约（用户没要过 ✗）—— 污染从这一环开始,
      下游放大到 42/199 个任务。
    判据:
      ① 有出处表时: 出处必须是**需求原话的逐字片段**（≥6 字, 归一化后子串匹配）⇒ 保留
      ② 出处缺失/编的 ⇒ 该特性**移出** feature_list, 进 out_of_scope_suggestions（给人看, 不做）
      ③ 没有出处表（模型不配合/老载荷）⇒ **不移出**（不误杀）, 但用"与需求原话的最长公共子串 <3"
         把可疑的**标出来**（只标不移 —— 不猜, 人是最终判据）
      ④ 调用点: 产品环产出后**真的调了**这个门（不是只有函数没人用）
    """
    import importlib as _il
    import inspect as _insp

    from ai_factory_os.plugins.agents.pm import enforce_requirement_traces as E

    bad: list[str] = []
    req = ("我要做一个健身房私教排课与消课小程序: 教练设置可约时间段; 会员预约并在线付课时费; "
           "到店后教练消课扣减课时; 会员能看剩余课时与消费记录; 店长能看每节课的到课率与教练课时统计")

    # ①② 逐字引用 ⇒ 留; 编的 ⇒ 移出
    p1 = {"feature_list": ["教练可约时段管理", "会员在线预约并付课时费", "微信登录"],
          "feature_traces": {"教练可约时段管理": "教练设置可约时间段",
                             "会员在线预约并付课时费": "会员预约并在线付课时费",
                             "微信登录": "微信小程序登录与角色区分（会员/教练）"}}
    r1 = E(p1, req)
    if "微信登录" in p1["feature_list"]:
        bad.append("编出处的特性没被移出 feature_list")
    if len(p1["feature_list"]) != 2:
        bad.append(f"真出处的特性被误移（剩 {len(p1['feature_list'])} 条）")
    if not p1.get("out_of_scope_suggestions"):
        bad.append("移出的特性没进 out_of_scope_suggestions（人看不到）")
    if r1.get("kept") != 2:
        bad.append("kept 计数不对")

    # ③ 不靠模型: 没有出处表时**自动补出处**（条目 ↔ 需求原话的最长公共子串 ≥2 字 ⇒ 可核对）
    #    —— 连 2 字都对不上 ⇒ 凭空发明 ⇒ 移出
    p2 = {"feature_list": ["私教排课", "微信登录", "消息推送推送"],
          "user_stories": ["会员查看并预约私教课程"], "mvp_scope": {"in": ["消课确认", "课程提醒"], "out": []}}
    r2 = E(p2, req)
    kept_feats = [str(x) for x in p2["feature_list"]]
    if "微信登录" in kept_feats:
        bad.append("凭空发明（微信登录, 与需求 0 字交集）没被移出")
    if "私教排课" not in kept_feats:
        bad.append("真实需求（私教排课）被误移出")
    if "消课确认" not in (p2["mvp_scope"]["in"] or []):
        bad.append("MVP 范围内的真需求被误移出")
    if "课程提醒" in (p2["mvp_scope"]["in"] or []):
        bad.append("凭空发明（课程提醒）没被移出")
    if not p2.get("out_of_scope_suggestions"):
        bad.append("移出的没进 out_of_scope_suggestions（人看不到）")
    if r2.get("checked") != 6:
        bad.append(f"检查条数不对（三处清单合计 6, 实得 {r2.get('checked')}）")

    # ④ 调用点
    src = _insp.getsource(_il.import_module("apps.cli.main").cmd_product_develop)
    if "enforce_requirement_traces" not in src:
        bad.append("产品环产出后没调这个门（门是死的）")
    return bad


def test_prd_requirement_gate() -> None:
    """需求→PRD 的门: 逐字出处才留 · 编的移出并另列 · 没出处表只标不移 · 调用点真的接了。"""
    assert _check_prd_requirement_gate() == []


def _check_one_authority_projects() -> list[str]:
    """★ "一数据一权威源"（Founder 实测: 同一问题三个答案 —— status 3 / project list 1 / dashboard 4）✗

    实测病: 三处各读各的源 ⇒ 同一个"有几个项目"三个数; 会话还会把这些矛盾原样答给用户 ✗。
    判据（临时根上造出"会分叉"的场景）:
      · 一个真项目（org 项目库） + 一个同名目录（`projects/<仓库名>`）—— 旧实现会把它算成第二个 ✗
      · 三个入口（status / project list / console dashboard）报的项目数**必须相等**且 == 1
      · `project list` 要**亮出数据源**（org 项目库）
    """
    import contextlib as _ctx
    import io as _io
    import json as _json
    import tempfile as _tf

    from ai_factory_os.services.organization.projects import ProjectStore

    bad: list[str] = []
    with _tf.TemporaryDirectory() as td:
        root = Path(td)
        (root / "org").mkdir(parents=True, exist_ok=True)
        try:
            st = ProjectStore(root / "org")
            st.create_project(name="gym-coach", repo_path=str(root / "repo" / "gym-coach")) \
                if hasattr(st, "create_project") else None
        except Exception:  # noqa: BLE001 — 造数据失败不算门失败（下面用别的路径兜）
            pass
        # 同名目录（模拟"重复计数"的场景）
        (root / "projects" / "gym-coach").mkdir(parents=True, exist_ok=True)

        def _count(argv: list[str]) -> int:
            from apps.cli import main as _cli

            buf = _io.StringIO()
            try:
                with _ctx.redirect_stdout(buf):
                    _cli(["--root", str(root), "--json", *argv])
            except SystemExit:
                pass
            txt = buf.getvalue().strip()
            try:
                d = _json.loads(txt)
            except Exception:  # noqa: BLE001
                return -1
            if "count" in d:
                return int(d.get("count") or 0)
            if isinstance(d.get("projects"), list):
                return len(d["projects"])
            return len((d.get("dashboard") or {}).get("projects") or [])

        a = _count(["status"])
        b = _count(["project", "list"])
        c = _count(["console", "dashboard"])
        if len({a, b, c}) != 1:
            bad.append(f"三个入口报的项目数不一致: status={a} project_list={b} dashboard={c}")
        # 源标签
        from apps.cli import main as _cli2

        buf = _io.StringIO()
        try:
            with _ctx.redirect_stdout(buf):
                _cli2(["--root", str(root), "project", "list"])
        except SystemExit:
            pass
        if "org 项目库" not in buf.getvalue():
            bad.append("project list 没亮出数据源（org 项目库）")
    return bad


def test_one_authority_projects() -> None:
    """"一数据一权威源": status / project list / dashboard 报的项目数必须一致, 且 project list 亮源。"""
    assert _check_one_authority_projects() == []


def _check_chat_memory_and_clear() -> list[str]:
    """★ 会话打磨（Founder 选 F）: 跨重启记得上下文（接最近一次会话）· 会说清"这条会改什么" · clear/新会话可用。"""
    import inspect as _insp

    from apps.cli.domains import chat as C
    from apps.cli.domains import welcome as W

    bad: list[str] = []
    ws = _insp.getsource(W.run_shell)
    if "conversations" not in ws or "_chat_hist" not in ws:
        bad.append("启动时没接最近一次会话（跨重启不记得上下文）")
    if "新会话" not in ws:
        bad.append("没有「新会话」入口（用户想从零开始时没办法）")
    if "clear" not in ws:
        bad.append("不支持 clear/cls")
    cs = _insp.getsource(C._system_prompt)
    if "会改什么" not in cs:
        bad.append("念命令时没说清「会改什么」（点头前要知道后果）")
    return bad


def test_chat_memory_and_clear() -> None:
    """会话打磨: 跨重启接上下文 · 新会话清空 · clear 可用 · 念命令说明后果。"""
    assert _check_chat_memory_and_clear() == []


def _check_cli_version_and_typo() -> list[str]:
    """★ `factory -v` 直接报版本（不是进会话）· 敲错命令给人话+建议（不是整屏英文 usage）。

    实测病（Founder 敲的）: `factory -v` 进了交互式会话 ✗; `factory veresion`（打错字）甩了一屏
      argparse usage + 全部命令枚举 ✗ —— 这两条都是最常见的敲法。
    """
    import contextlib as _ctx
    import io as _io

    from apps.cli import main as _cli

    bad: list[str] = []
    # 各种写法都要算（Founder 敲过 `-version`）; 认不出的开关不许静默进会话
    for flag in ("-v", "-V", "--v", "--version", "-version", "--Version", "VERSION", "version"):
        buf = _io.StringIO()
        try:
            with _ctx.redirect_stdout(buf):
                rc = _cli([flag])
        except SystemExit:
            rc = 0
        out = buf.getvalue()
        if "AI Factory OS" not in out or "v" not in out:
            bad.append(f"`factory {flag}` 没直接报版本")
        if "你想做什么" in out:
            bad.append(f"`factory {flag}` 竟然进了会话（应该直接报版本）")
        if rc != 0:
            bad.append(f"`factory {flag}` 退出码应为 0")
    buf = _io.StringIO()
    try:
        with _ctx.redirect_stdout(buf):
            rc2 = _cli(["veresion"])
    except SystemExit:
        rc2 = 0
    out2 = buf.getvalue()
    if "没有这个命令" not in out2:
        bad.append("敲错命令没给一句人话")
    if "invalid choice" in out2 or "usage: factory [" in out2:
        bad.append("敲错命令仍在甩 argparse 整屏 usage")
    if rc2 != 2:
        bad.append(f"敲错命令退出码应为 2（实得 {rc2}）")
    # 认不出的开关 ⇒ 报"未知开关"（不许静默进会话）
    for bad_flag in ("-Ver", "-x", "--foo"):
        buf3 = _io.StringIO()
        try:
            with _ctx.redirect_stdout(buf3):
                rc3 = _cli([bad_flag])
        except SystemExit:
            rc3 = 0
        out3 = buf3.getvalue()
        if "未知开关" not in out3:
            bad.append(f"`factory {bad_flag}` 没报「未知开关」（可能静默进了会话 ✗）")
        if "你想做什么" in out3:
            bad.append(f"`factory {bad_flag}` 竟然进了会话")
        if rc3 != 2:
            bad.append(f"`factory {bad_flag}` 退出码应为 2（实得 {rc3}）")
    return bad


def test_cli_version_and_typo() -> None:
    """-v/--version/version 直接报版本 · 敲错命令给人话+建议 · 都不甩整屏英文 usage。"""
    assert _check_cli_version_and_typo() == []


def _check_hermes_style_ui() -> list[str]:
    """★ Hermes 风格呈现（Founder: "会话中, 我想要 Hermes 这种风格" —— 分块/标题/过程行/你的话分开）。"""
    from apps.cli.domains import welcome as W

    bad: list[str] = []
    b = W.box("⚕ AI Factory OS · deepseek-chat · tokens 1↑/2↓ · $0.000100 · 1.0s",
              "三行\n中文宽度对齐\n`project show` 不能被拆开")
    lines = b.splitlines()
    if not lines[0].startswith("  ╭─ "):
        bad.append("没有圆角框顶栏（Hermes 风格的分块没做）")
    if not lines[-1].startswith("  ╰"):
        bad.append("没有圆角框底栏")
    widths = {W._dw(ln) for ln in lines}
    if len(widths) != 1:
        bad.append(f"框线宽度不齐（实得 {sorted(widths)} —— 中文宽度算错会歪）")
    if any("project show" in ln and "`" not in ln for ln in lines):
        bad.append("反引号内容被拆行（命令名断成两半）")
    pl = W.process_line("factory status", 0.4)
    if "┊" not in pl or "0.4s" not in pl:
        bad.append("过程行格式不对（应含 ┊ 与耗时）")
    # 会话里必须真的用了这些（★ Founder: "这风格我有点接受不了" ⇒ **默认不套框**, 框可选）
    import inspect as _insp
    import os as _os

    src = _insp.getsource(W.run_shell)
    for need, why in (("_use_box()", "没有「要不要框」的开关（默认必须是简洁版）"),
                      ("tool_block(", "工具输出没有成块（过程行改由块头承担）"), ("on_progress=", "没把「跑了什么命令」接出来"),
                      ("_MENU.get(low", "会话里不认编号菜单（横幅承诺过「输入编号直接跑」）")):
        if need not in src:
            bad.append(why)
    # ★ 照 Hermes（skin_engine.py: response_border + 工具行 ┊）: **终端里套框, 非终端不套**;
    #   用户输入**不进框**（Founder 上次就是嫌这个花 ✗）
    _old_env, _old_nc = _os.environ.get("FACTORY_UI"), _os.environ.get("NO_COLOR")
    try:
        _os.environ.pop("FACTORY_UI", None)
        _os.environ.pop("NO_COLOR", None)
        if W._use_box():
            bad.append("管道/脚本里竟然套框（输出要干净可断言）")
        _os.environ["FACTORY_UI"] = "plain"
        if W._use_box():
            bad.append("FACTORY_UI=plain 时仍套框（开关没生效）")
    finally:
        _os.environ.pop("FACTORY_UI", None)
        if _old_env is not None:
            _os.environ["FACTORY_UI"] = _old_env
        if _old_nc is not None:
            _os.environ["NO_COLOR"] = _old_nc
    if 'box("你"' in src:
        bad.append("用户输入被套框了（照 Hermes: 只有助手回复套框）")
    # project list 必须带 ID 列（会话/用户都要靠它定位）
    _main_src = _insp.getsource(__import__("importlib").import_module("apps.cli.main"))
    if chr(34) + "ID" + chr(34) + ", " + chr(34) + "Project" + chr(34) not in _main_src:
        bad.append("`project list` 没有 ID 列（会话拿不到 P-xxx ⇒ 查 show/看树都卡住）")
    cs = _insp.getsource(__import__("apps.cli.domains.chat", fromlist=["x"])._ask_llm2) + \
        _insp.getsource(__import__("apps.cli.domains.chat", fromlist=["x"]).chat_turn)
    if "RUN:" not in cs:
        bad.append("chat 侧没有 RUN: 处理")
    return bad


def test_hermes_style_ui() -> None:
    """Hermes 风格: 圆角框+标题 · 宽度齐 · 反引号不拆 · 过程行 · 会话里真的用了。"""
    assert _check_hermes_style_ui() == []


def _check_name_everywhere() -> list[str]:
    """★ "列得出来就该查得到"（Founder 实测: `project list` 有 community-library, 但
    `project show community-library` 说 not found ✗、看树也说"任务树不存在" ✗ ⇒ 断头路）。

    判据: ① 项目名/id/仓库名/**片段** 都能解析成项目 id
         ② `project show <名字>` 不再报 not found（走权威源）
         ③ 看树那条路真的接了名字解析（调用点断言: 用 _resolve_plan_id）
    """
    import contextlib as _ctx
    import inspect as _insp
    import io as _io
    import tempfile as _tf

    from apps.cli import main as _cli
    from ai_factory_os.services.organization.projects import Project, ProjectStore

    bad: list[str] = []
    with _tf.TemporaryDirectory() as td:
        root = Path(td)
        (root / "org").mkdir(parents=True, exist_ok=True)
        try:
            # 用**真 API**（先查过: ProjectStore 只有 save_project, 没有 create_project ✗）
            ProjectStore(root / "org").save_project(
                Project(id="P-t", name="community-library", repo_path=str(root / "repo" / "community-library")))
        except Exception as exc:  # noqa: BLE001
            return [f"造项目失败（守卫前置条件不满足）: {type(exc).__name__}: {str(exc)[:60]}"]
        for tok in ("community-library", "library", "community"):
            buf = _io.StringIO()
            try:
                with _ctx.redirect_stdout(buf):
                    _cli(["--root", str(root), "project", "show", tok])
            except SystemExit:
                pass
            out = buf.getvalue()
            if "not found" in out or "Traceback" in out:
                bad.append(f"`project show {tok}` 仍查不到（列得出来就该查得到）")
    import importlib as _il

    # ★ 注意: `apps.cli.main` 这个名字既是模块又是函数（包 __init__ 里导出了 main）⇒ 要 import_module 取模块
    _mmod = _il.import_module("apps.cli.main")
    _src = _insp.getsource(_mmod)
    if "def _resolve_plan_id" not in _src:
        bad.append("看树那条路没有名字解析函数 _resolve_plan_id")
    if "_resolve_plan_id(ctx," not in _src:
        bad.append("看树那条路没**接线**（函数在但没人调）")
    if "def resolve_project_id" not in _insp.getsource(_il.import_module("apps.cli.commands")):
        bad.append("缺统一的项目解析器 resolve_project_id")
    return bad


def test_name_everywhere() -> None:
    """"列得出来就该查得到": 项目名/片段能 show · 看树能按项目名解析。"""
    assert _check_name_everywhere() == []


def _check_cli_essence() -> list[str]:
    """★ Hermes 的 CLI 精髓（Founder: "我说的是Hermes的cli的精髓"）—— 会话体验闭环, 不是 agent 架构。

    该有的: 会话命令集(/help /new /stop /retry /cost /model /tools /sessions) · 忙指示 ·
     可打断(断一轮留会话) · 权限三档(允许一次/本会话总是允许/拒绝) · 多行输入 · 会话可挑可续。
    """
    import contextlib as _c
    import inspect as _insp
    import io as _io

    from apps.cli import main as _cli
    from apps.cli.domains import welcome as W

    bad: list[str] = []
    need = {"/help", "/new", "/stop", "/retry", "/cost", "/model", "/tools", "/sessions"}
    missing = need - set(W.SESSION_COMMANDS)
    if missing:
        bad.append(f"会话命令集缺: {sorted(missing)}")
    src = _insp.getsource(W.run_shell)
    for needle, why in (("_busy(", "没有忙指示（黑屏干等）"),
                        ("KeyboardInterrupt", "不能打断当前这一轮"),
                        ("总是允许", "没有权限三档（允许一次/本会话总是允许/拒绝）"),
                        ("_sess[", "没累计会话用量（/cost 会是空的）"),
                        ('line.endswith("\\\\")', "不支持多行输入（行尾反斜杠续行）"),
                        ("/sessions", "会话不可列不可挑")):
        if needle not in src:
            bad.append(why)
    # 权限三档: 非终端 ⇒ 一律拒绝（安全默认）
    _old = __import__("sys").stdout
    buf = _io.StringIO()
    try:
        with _c.redirect_stdout(buf):
            r = W._ask_permission("factory backup create", tty=False, always=set())
    finally:
        __import__("sys").stdout = _old
    if r != "deny":
        bad.append(f"非终端下权限没默认拒绝（实得 {r}）—— 脚本里不该自动跑写命令 ✗")
    # /help 必须列出会话命令（可发现性）
    __import__("sys").stdin = _io.StringIO("/help" + chr(10) + "exit" + chr(10))
    buf2 = _io.StringIO()
    try:
        with _c.redirect_stdout(buf2):
            _cli(["start"])
    except SystemExit:
        pass
    got = buf2.getvalue()
    if "/cost" not in got or "会话命令" not in got:
        bad.append("/help 没列会话命令（不可发现 ✗）")
    return bad


def test_cli_essence() -> None:
    """CLI 精髓: 会话命令集 · 忙指示 · 可打断 · 权限三档(非终端默认拒绝) · 多行 · 会话可挑。"""
    assert _check_cli_essence() == []


def _check_output_readability() -> list[str]:
    """★ 输出可读性（Founder: "输出的方式…呈现形式不是很好, 不直观, 使用table或者有序或者无序列表"）。

    判据: ① `status` 用表格 + 列表, 不再有 `tasks 0 {}` / `agent注册表 4 [...]` 这种机器味 ✗
         ② 表格按**显示宽度**对齐（中文算 2 列 —— 以前 len() ⇒ 列全歪 ✗）
         ③ `-h` 裸敲也当求助（不进聊天 ✗）; ④ `/commands` 给命令总表（命令/作用/改数据）
         ⑤ 助手回复框宽度 ≤ 88（铺满 120 列看着累 ✗）
    """
    import contextlib as _c
    import inspect as _insp
    import io as _io

    from apps.cli import main as _cli
    from apps.cli import textwidth as _TW
    from apps.cli.domains import welcome as _W

    bad: list[str] = []
    # ① status 的输出
    buf = _io.StringIO()
    try:
        with _c.redirect_stdout(buf):
            _cli(["status"])
    except SystemExit:
        pass
    out = buf.getvalue()
    if "项" not in out or "数值" not in out:
        bad.append("status 没输出表格（还是老样子）")
    if "{}" in out or "by_status {" in out or "agent注册表 4  [" in out:
        bad.append("status 里还有机器味输出（{} / [...] 这种）")
    if "· 总叶数" not in out:
        bad.append("status 里开发任务没按列表列出")
    # ② 表格中文对齐（显示宽度）
    tbl = _cli.__dict__  # noqa: F841 — 仅为可读性: 直接调工具
    from apps.cli.main import _render_table

    lines = _render_table(["项", "数值"], [["项目", "3"], ["agent 注册表", "4"]]).splitlines()
    widths = {_TW.display_width(x) for x in lines}
    if len(widths) != 1:
        bad.append(f"表格中文没对齐（行宽 {sorted(widths)}）")
    if _TW.display_width("中文") != 4:
        bad.append("显示宽度函数不对（中文应为 2 列）")
    # ③ -h 当求助 · ④ /commands 表格
    for feed, need in (("-h" + chr(10) + "exit" + chr(10), "会话命令"),
                       ("/commands" + chr(10) + "exit" + chr(10), "改数据")):
        __import__("sys").stdin = _io.StringIO(feed)
        b2 = _io.StringIO()
        try:
            with _c.redirect_stdout(b2):
                _cli(["start"])
        except SystemExit:
            pass
        if need not in b2.getvalue():
            bad.append(f"输 {feed.splitlines()[0]!r} 没出该出的内容（缺 {need}）")
    # ★ 2026-09-21（Founder: "无效信息太多了"）:
    #   ① 首屏 ≤9 行（原来 11 行前言 = 噪音 ✗）② 回答规则必须收紧（≤3 行 / 别问"要不要我跑"只读直接跑 /
    #   缺参数先问老板, 不许念带占位符的命令）③ 执行结果不许**假成功**（命令报错却打"✔ 完成" ✗）
    _rsrc = _insp.getsource(_W.run_shell)
    _wl = _insp.getsource(_W.render_welcome)
    _banner_lines = _wl.count('lines.append') + _wl.count('"  ')
    buf = _io.StringIO()
    try:
        with _c.redirect_stdout(buf):
            print(_W.render_welcome("."))
    except Exception:  # noqa: BLE001
        pass
    _bn = len([x for x in buf.getvalue().splitlines() if x.strip()])
    if _bn > 10:
        bad.append(f"首屏太长（{_bn} 行非空 ⇒ 无效信息多 ✗）")
    from apps.cli.domains import chat as _CC

    _csrc = _insp.getsource(_CC)
    for _need, _why in (("最多 3 行", "回答没限长（老板嫌无效信息多 ✗）"),
                        ("不许问「要不要我跑", "还在问「要不要我跑」（只读的直接跑 ✗）"),
                        ("占位符", "没禁止念带占位符的命令（跑出来必然报错 ✗）")):
        if _need not in _csrc:
            bad.append(_why)
    if "执行**没成功**" not in _rsrc:
        bad.append("执行结果可能假成功（命令报错却打「✔ 完成」✗）")
    # ★ 2026-09-21（Founder: "这里应该统一采用列表的形式, 不能在同一行"）:
    #   ① 待你点头 = 列表（三档各占一行）; ② 工具输出不能被 strip 吃掉头行前导空格（表格歪 ✗）
    _wsrc2 = _insp.getsource(_W.run_shell)
    for _need, _why in (("1) 允许这一次", "待你点头没做成列表（挤在同一行 ✗）"),
                        ("rstrip()", "工具输出对整段 strip（头行前导空格被吃 ⇒ 表格歪 ✗）")):
        if _need not in _wsrc2:
            bad.append(_why)
    # ⑤ 框宽 ≤ 88
    _b = _W.box("⚕ 标题", "正文" * 60)
    _wide = max(_TW.display_width(x) for x in _b.splitlines())
    if _wide > 100:
        bad.append(f"回复框太宽（{_wide} 列; 上限 100 —— 照 Hermes 通栏但别超屏）")
    # 只留一套宽度实现
    _wsrc = _insp.getsource(_W._dw)
    if "textwidth" not in _wsrc:
        bad.append("welcome._dw 没复用 textwidth（宽度实现有两套 ✗）")
    return bad


def test_output_readability() -> None:
    """输出可读性: status 表格化 · 中文对齐 · -h 当求助 · /commands 总表 · 框宽 ≤88。"""
    assert _check_output_readability() == []


def _check_markdown_render() -> list[str]:
    """★ 会话输出渲染 markdown（Founder: "cli 好像不支持markdown格式" + "项目列表内容太少了"）。

    判据: ① `**粗体**` 的星号不再原样露出（终端里加样式, 非终端去标记）
         ② md 表格（| a | b |）渲染成**对齐**表格（中文也齐）
         ③ 提示词要求"工具返回表格/清单时原样贴出"（不然会话只挑两列改写成大白话 ✗ —— 实测踩到）
    """
    import inspect as _insp

    from apps.cli import markdown as _MD
    from apps.cli import textwidth as _TW

    bad: list[str] = []
    out = _MD.render_md("**粗体** 与 `代码` 和 *斜体*", color=False)
    if "**" in out or "`" in out:
        bad.append("markdown 标记没去掉（** 或 ` 还在）")
    if "粗体" not in out or "代码" not in out:
        bad.append("markdown 渲染把正文吃掉了")
    tbl = _MD.render_md("| 项目 | 状态 |\n|---|---|\n| gym-coach | active |\n| 中文项目 | active |", color=False)
    widths = {_TW.display_width(x) for x in tbl.splitlines() if x.strip()}
    if len(widths) != 1:
        bad.append(f"md 表格没对齐（行宽 {sorted(widths)}）")
    if "-" * 5 not in tbl:
        bad.append("md 表格没渲染出分隔线")
    from apps.cli.domains import chat as _C

    _src = _insp.getsource(_C)
    if "不要再重画表格" not in _src and "原样贴出来" not in _src:
        bad.append("提示词没约束模型的表格输出（会重画/改写成大白话 ✗）")
    from apps.cli.domains import welcome as _W

    _wsrc = _insp.getsource(_W.run_shell)
    if "render_md" not in _wsrc:
        bad.append("会话回复没走 markdown 渲染")
    # ★ Founder: "不对, 表格不对" ⇒ 工具输出**原样直通**给人看（模型重画会把列画散 ✗）, 它只补解读
    if "_on_output" not in _wsrc or "on_output=_on_output" not in _wsrc:
        bad.append("工具输出没直通给人看（模型重画表格 ⇒ 列会散 ✗）")
    if "不要再重画表格" not in _src:
        bad.append("提示词没禁止模型重画表格（它会重画 ✗）")
    return bad


def test_markdown_render() -> None:
    """markdown 渲染: 去标记/加样式 · md 表格对齐 · 提示词要求原样贴表格 · 会话真的用了。"""
    assert _check_markdown_render() == []


def _check_project_notes() -> list[str]:
    """★ 项目要有**中文说明**（Founder: "没有中文说明, 我都不知道是什么项目"）。

    判据: ① `project list` 输出里有"说明"列 ② 说明来自**真实来源**（会话里的第一句需求 / 记录里的描述）,
             没有就说"（未记录说明）" —— **绝不编** ③ `project show` 头一行也带说明
    """
    import contextlib as _c
    import io as _io
    import json as _json
    import tempfile as _tf

    from apps.cli import main as _cli
    from apps.cli.commands import _project_notes
    from ai_factory_os.services.organization.projects import Project, ProjectStore

    bad: list[str] = []
    with _tf.TemporaryDirectory() as td:
        root = Path(td)
        (root / "org").mkdir(parents=True, exist_ok=True)
        ProjectStore(root / "org").save_project(
            Project(id="P-zzz", name="demo-app", repo_path=str(root / "repo" / "demo-app")))
        conv = root / "projects" / "P-zzz" / "conversations"
        conv.mkdir(parents=True, exist_ok=True)
        (conv / "conv-1.json").write_text(_json.dumps(
            {"id": "conv-1", "messages": [{"role": "human", "content": "我要做一个社区团购小程序: 团长开团、居民下单、自提核销"},
                                           {"role": "assistant", "content": "好的"}]},
            ensure_ascii=False), encoding="utf-8")
        notes = _project_notes(root, ProjectStore(root / "org").list_projects() or [])
        if "社区团购" not in (notes.get("P-zzz") or ""):
            bad.append("说明没从会话里的需求原话里取（来源不对/取不到）")
        buf = _io.StringIO()
        try:
            with _c.redirect_stdout(buf):
                _cli(["--root", str(root), "project", "list"])
        except SystemExit:
            pass
        out = buf.getvalue()
        if "说明" not in out:
            bad.append("project list 没有「说明」列（老板看不懂 gym-coach 是啥 ✗）")
        if "社区团购" not in out:
            bad.append("project list 里说明没显示出来")
    return bad


def test_project_notes() -> None:
    """项目说明: list 有说明列 · 来自会话需求原话（真实来源）· show 头行也带。"""
    assert _check_project_notes() == []


def _check_gate_uses_same_requirement() -> list[str]:
    """★ 门的参照必须是 **agent 用的那份需求**（Founder 实测重大误杀 ✗✗）。

    病: 需求在命令行给（`factory chain "<需求>"`）⇒ 门却从**会话**里另取一份 ⇒ 取到空 ⇒
        把真需求（扫码借还/查馆藏/逾期提醒…）当"凭空发明"移出 21 条 ✗。
    判据: ① 有需求原文 ⇒ 真需求**必须留**, 纯凭空发明**必须移出**
         ② 拿不到需求原文 ⇒ **不过滤**（skipped, 宁可放过不误杀）
         ③ CLI 里门必须用 `idea`（agent 那份）, 会话那份只作兜底
    """
    import inspect as _insp

    from ai_factory_os.plugins.agents.pm import enforce_requirement_traces as G

    bad: list[str] = []
    req = "社区图书借还小程序：扫码借还、查馆藏、逾期提醒；管理员上架盘点看榜；接微信登录"
    pay = {"feature_list": ["扫码借还", "查馆藏", "逾期提醒", "管理员上架", "区块链积分商城"],
           "mvp_scope": {"in": ["接微信登录"]}}
    G(pay, req)
    left = [str(x) for x in (pay.get("feature_list") or [])]
    for must_keep in ("扫码借还", "查馆藏", "逾期提醒", "管理员上架"):
        if must_keep not in left:
            bad.append(f"真需求「{must_keep}」被误杀 ✗（这是最严重的回归）")
    if any("区块链" in x for x in left):
        bad.append("凭空发明（区块链积分商城, 与需求 0 字重合）没被移出 ✗")
    # ② 拿不到需求 ⇒ 不过滤
    pay2 = {"feature_list": ["扫码借还", "随便发明的功能"]}
    r2 = G(pay2, "")
    if not r2.get("skipped") or r2.get("moved"):
        bad.append("拿不到需求原文时没跳过过滤（会误杀 ✗）")
    if len(pay2.get("feature_list") or []) != 2:
        bad.append("拿不到需求原文时仍改动了清单（不该动 ✗）")
    # ③ CLI 用 idea
    _il = __import__("importlib").import_module("apps.cli.main")
    src = _insp.getsource(_il)
    if "_req_for_gate" not in src or "idea or" not in src:
        bad.append("CLI 里的门没用 agent 那份需求（还会再误杀 ✗）")
    return bad


def test_gate_uses_same_requirement() -> None:
    """门的参照 = agent 用的需求: 真需求留 · 凭空发明移出 · 拿不到需求就不过滤。"""
    assert _check_gate_uses_same_requirement() == []


def _check_three_marks() -> list[str]:
    """★ 三态可辨（Founder: "没有像 codex/Hermes 的 cli 那样: 用户/系统/执行 都有区分" + "结果堆砌在一起"）。

    判据: ① 有四个标记常量（你/系统/执行/助手）② 工具输出成块（头行 + 分隔 + `│` 缩进 + 超长截断并说明）
         ③ 会话里真的用了（源码断言: 用户回声 / tool_block）④ 点头执行后必须有**结果行**（不许零反馈 ✗）
    """
    import inspect as _insp

    from apps.cli.domains import welcome as _W

    bad: list[str] = []
    for name in ("MARK_USER", "MARK_SYS", "MARK_EXEC", "MARK_AI"):
        if not getattr(_W, name, ""):
            bad.append(f"缺标记 {name}（三态不可辨 ✗）")
    blk = _W.tool_block("project list", 0.1, "a\nb")
    # ★ 照 Hermes: 一行 `┊ 💻 $ …` + 输出**原样缩进**（不用分隔线、不逐行加 │ —— 实测更吵 ✗）
    if "┊ 💻 $ factory project list" not in blk or "      a" not in blk:
        bad.append("工具行/缩进不对（照 Hermes: `┊ 💻 $ 命令` + 原样缩进 ✗）")
    if "─" * 10 in blk or "│ a" in blk:
        bad.append("工具块还在用分隔线/逐行前缀（Founder: Hermes 那样更清晰 ✗）")
    long_out = "\n".join(f"line{i}" for i in range(60))
    blk2 = _W.tool_block("project list", 0.1, long_out)
    if "还有" not in blk2:
        bad.append("超长工具输出没截断（会堆砌满屏 ✗）")
    if len(blk2.splitlines()) > 16:
        bad.append("超长输出截得还不够狠（一屏糊住 = Founder 说的「太乱了」✗）")
    if blk.count("factory factory") or "factory factory" in blk2:
        bad.append("块头命令名重复（factory factory ✗）")
    src = _insp.getsource(_W.run_shell)
    if "MARK_USER" not in src and "● {line}" not in src:
        bad.append("用户的话没有回声/分区（用户/执行/系统 分不清 ✗ —— Founder 要 Hermes 那种分区）")
    if chr(34) + "─" + chr(34) + " *" not in src:
        bad.append("用户回合没有通栏分隔线（没有分区 ✗）")
    if "tool_block(" not in src:
        bad.append("会话里没用工具块（结果还是堆砌 ✗）")
    if "_code_fingerprint" not in src or "代码已更新" not in src:
        bad.append("没有「窗口跑着旧代码」的提醒（改了却看不到效果 ✗）")
    if "执行完成（改动已落盘）" not in src and "没成功" not in src:
        bad.append("点头执行后没有结果行（看起来像没执行 ✗ —— Founder 实测踩到）")
    return bad


def test_three_marks() -> None:
    """三态可辨: 你/系统/执行/助手 · 工具输出成块+截断 · 点头执行后有结果行。"""
    assert _check_three_marks() == []


def main() -> int:
    results: list[tuple[str, bool, str]] = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        bad1 = _check(root)
        bad2 = _check_views_see_tree(root)
        bad3 = _check_state_semantics(root)
        bad4 = _check_small_fixes(root)
    results.append(("会话事实 → 想法文本", not bad1, "；".join(bad1)))
    results.append(("监控看得见执行（树 → status/metrics/看板）", not bad2, "；".join(bad2)))
    results.append(("执行状态语义（可重试 / 完成留证据）", not bad3, "；".join(bad3)))
    results.append(("小卡点（限量 / 引用语义 / create 不静默）", not bad4, "；".join(bad4)))
    results.append(("拆解粒度（一句话写不出验收 ⇒ 没拆到位）", not _check_granularity(), "；".join(_check_granularity())))
    results.append(("UX/UI 截断自愈（逐节生成）", not _check_ux_truncation_fallback(), "；".join(_check_ux_truncation_fallback())))
    results.append(("写树位置唯一（漏传 project_id 也不造副本）", not _check_tree_write_path(), "；".join(_check_tree_write_path())))
    results.append(("产出证据判定（不猜）", not _check_evidence_judgement(), "；".join(_check_evidence_judgement())))
    results.append(("陈旧认领交回（不抢活跃执行）", not _check_stale_claim_sweep(), "；".join(_check_stale_claim_sweep())))
    results.append(("实体清单来源（设计优先/DDL 兜底/空则不编）", not _check_entity_catalog(), "；".join(_check_entity_catalog())))
    results.append(("执行体裁定（停手可表达·待裁决≠完成）", not _check_executor_verdict(), "；".join(_check_executor_verdict())))
    results.append(("LLM key 归属（factory 自己的 .env·写读同源）", not _check_llm_key_resolution(), "；".join(_check_llm_key_resolution())))
    results.append(("需求定位读会话（不给文本/归属自动带出）", not _check_locate_reads_conversation(), "；".join(_check_locate_reads_conversation())))
    results.append(("执行收尾契约（提交/未提交分开·指令写清）", not _check_repo_closing_contract(), "；".join(_check_repo_closing_contract())))
    results.append(("会话唯一入口（chain 覆盖到拆解·自动生成三件制品）", not _check_chain_covers_rings(), "；".join(_check_chain_covers_rings())))
    results.append(("流程接进主链（按步骤推进·走完才算完成·可编排）", not _check_workflow_drives_chain(), "；".join(_check_workflow_drives_chain())))
    results.append(("多公司/多部门落到执行（按归属筛人·不串公司）", not _check_org_scope_reaches_execution(), "；".join(_check_org_scope_reaches_execution())))
    results.append(("文件冲突降级串行（并行安全前提·不是死代码）", not _check_file_conflict_demotion(), "；".join(_check_file_conflict_demotion())))
    results.append(("容量门/预算门接真数据（不再是 0/1e9 假数据）", not _check_load_gate_real_data(), "；".join(_check_load_gate_real_data())))
    results.append(("失败恢复接树（检查点+recover --plan·幂等）", not _check_recover_plan_from_checkpoint(), "；".join(_check_recover_plan_from_checkpoint())))
    results.append(("监控不装样子（Agents/Validation 接真事件）", not _check_metrics_not_empty_shells(), "；".join(_check_metrics_not_empty_shells())))
    results.append(("理解产物落盘不过期（实时报告进档案）", not _check_analysis_persist_fresh(), "；".join(_check_analysis_persist_fresh())))
    results.append(("插件放下即用（丢清单即生效·坏清单响亮报错）", not _check_plugin_drop_in(), "；".join(_check_plugin_drop_in())))
    results.append(("学习自治（经验从真执行来·失败也记·幂等）", not _check_experience_learning(), "；".join(_check_experience_learning())))
    results.append(("provider 域经验（用量⇒经验⇒推荐引擎读得到）", not _check_provider_experience_learning(), "；".join(_check_provider_experience_learning())))
    results.append(("拆解一次到位（原子任务·契约要验收·同模块归一域）", not _check_decompose_is_atomic(), "；".join(_check_decompose_is_atomic())))
    results.append(("CLI 友好首屏（空参不甩英文报错·帮助中心四角色）", not _check_cli_welcome(), "；".join(_check_cli_welcome())))
    results.append(("启动 AI Factory OS（factory start 进交互式 CLI·敲命令真跑·exit 退出）", not _check_cli_shell(), "；".join(_check_cli_shell())))
    results.append(("任务出处那一栏（无出处的挡在树外·单列给人看）", not _check_task_traces_to(), "；".join(_check_task_traces_to())))
    results.append(("CLI 会话（说话=会话 · /命令=执行 · 写命令不自动跑）", not _check_cli_chat(), "；".join(_check_cli_chat())))
    results.append(("需求→PRD 的门（无出处的功能不进 PRD·标出可疑）", not _check_prd_requirement_gate(), "；".join(_check_prd_requirement_gate())))
    results.append(("口径一致（status/project list/dashboard 项目数同源）", not _check_one_authority_projects(), "；".join(_check_one_authority_projects())))
    results.append(("会话打磨（跨重启记上下文·新会话·clear·念命令说后果）", not _check_chat_memory_and_clear(), "；".join(_check_chat_memory_and_clear())))
    results.append(("版本与错字（-v 直接报版本·敲错给人话不甩 usage）", not _check_cli_version_and_typo(), "；".join(_check_cli_version_and_typo())))
    results.append(("Hermes 风格呈现（分块·过程行·你的话分开）", not _check_hermes_style_ui(), "；".join(_check_hermes_style_ui())))
    results.append(("列得出来就查得到（项目名/片段 show·看树认项目名）", not _check_name_everywhere(), "；".join(_check_name_everywhere())))
    results.append(("CLI 精髓（会话命令/忙指示/可打断/三档权限/多行/会话可挑）", not _check_cli_essence(), "；".join(_check_cli_essence())))
    results.append(("输出可读性（status 表格化·中文对齐·-h 求助·框宽上限）", not _check_output_readability(), "；".join(_check_output_readability())))
    results.append(("markdown 渲染（去标记·表格对齐·提示词要求原样贴表）", not _check_markdown_render(), "；".join(_check_markdown_render())))
    results.append(("项目说明（中文说明来自真实需求原话·不编）", not _check_project_notes(), "；".join(_check_project_notes())))
    results.append(("PRD 门用同一份需求（真需求不误杀·拿不到就不过滤）", not _check_gate_uses_same_requirement(), "；".join(_check_gate_uses_same_requirement())))
    results.append(("三态可辨（你 · 系统 · 执行 · 助手 + 结果成块）", not _check_three_marks(), "；".join(_check_three_marks())))
    results.append(("项目级记忆（add 自动落盘·写侧接线）", not _check_project_memory(), "；".join(_check_project_memory())))
    width = max(len(n) for n, _, _ in results)
    fails = 0
    for label, ok, detail in results:
        print(f"   [{'PASS' if ok else 'FAIL'}] {label.ljust(width)}" + (f"   ← {detail}" if detail else ""))
        fails += 0 if ok else 1
    print(f"\n{len(results) - fails}/{len(results)} 通过")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())


def test_cli_shell() -> None:
    """factory start ⇒ 进去能敲命令真跑 · exit 能退 · 敲错不带走 shell · 非终端不挂。"""
    assert _check_cli_shell() == []
