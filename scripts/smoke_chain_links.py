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
