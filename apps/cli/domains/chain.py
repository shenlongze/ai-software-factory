"""需求全链编排（chain）—— 把 6 环串成**一条命令**（闭环）。

Founder 定的流程:
  需求进来 → ① 定位 → ② 理解 → ③ 分析 → ④ 拆解 → ⑤ 用户视图 → ⑥ 确认/修改

【为什么需要它（Founder 问"流程闭环了么"）】
 实测核对发现: 各环**命令都有**, 但**没有"一条命令跑完整链"** ——
 用户要在命令之间手动搬数据（--project / --conversation 反复传）⇒ 不算闭环。
 ⇒ 本模块把它们串起来: 一个入口, 从需求走到视图。

【设计要点】
 · **复用各环现有实现**（`domains/conversation._say/_understand/_prd`、
   `_dispatch_tasktree` 等）—— 不重写逻辑（一能力一处）。
 · **断点续跑**: 每步先检查"产物在不在", 在就跳过 ⇒ 中途失败重跑不会重做已完成步骤;
   LLM 步骤很慢, 这一点很重要。
 · **失败停在那一步并说清**（不许静默跳过）—— 用户要知道链断在哪。
 · 范围: 到"④拆解 + 细拆"为止; ⑤⑥（视图/确认）是人工环节, 链只给出**入口提示**。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from pathlib import Path


def _ns(**kw: Any) -> SimpleNamespace:
    """构造一个"像 args 一样"的对象（供各环的实现函数复用）。"""
    return SimpleNamespace(**kw)


def _say_step(root: Path, cid: str, text: str) -> None:
    from apps.cli.domains import conversation as C
    C._say(root, _ns(conversation_id=cid, text=text))          # noqa: SLF001


def _understand_step(root: Path, cid: str) -> dict[str, Any]:
    from apps.cli.domains import conversation as C
    return C._understand(root, _ns(conversation_id=cid))       # noqa: SLF001


def _prd_step(root: Path, cid: str) -> dict[str, Any]:
    from apps.cli.domains import conversation as C
    return C._prd(root, _ns(conversation_id=cid))              # noqa: SLF001


def run_chain(
    root: Path,
    *,
    text: str,
    project_id: str = "",
    intent: str = "",
    proposer: str = "founder",
    conversation_id: str = "",
    do_expand: bool = True,
    skip_analysis: bool = False,
) -> dict[str, Any]:
    """跑完整链; 返回每步的结果与状态（供 CLI 打印）。

    步骤与"已有则跳过"的判据:
      s1 定位   —— 会话已有 location 就跳过
      s2 建会话 —— 给了 conversation_id 就复用
      s3 理解   —— 会话 understanding 里已有 facts 就跳过
      s4 PRD    —— 项目 product_truth/prds.json 已有就跳过
      s5 分析产物 —— project/ux/design 产物（缺 ⇒ 只在结果里**提示**, 不阻塞）
        ★ 为什么不阻塞: 它们各要多次 LLM 调用; 而"③分析"是设计师环节,
          链的价值在"到拆解不手动搬数据"; 缺产物时 decompose 会响亮报错（不静默）
      s6 拆解   —— 项目已有任务树就复用最新那棵
      s7 细拆   —— do_expand 且树里还有"未细拆"的模块时执行
    """
    from ai_factory_os.services.conversation.intake import locate
    from ai_factory_os.services.conversation import understanding as U
    from ai_factory_os.services.organization.projects import ProjectStore
    from ai_factory_os.services.work import decomposition as D
    from ai_factory_os.services.work.expand import expand_module

    steps: list[dict[str, Any]] = []
    cid = conversation_id

    def _log(step: str, status: str, detail: str = "") -> None:
        steps.append({"step": step, "status": status, "detail": detail})

    # ── s1 定位 ───────────────────────────────────────────────────────────
    if cid:
        conv = U.get_conversation(root, cid) or {}
        if (conv.get("location") or {}).get("intent"):
            _log("① 定位", "skip", f"已有定位: {(conv['location'] or {}).get('intent')}")
        else:
            loc = locate(text, project_id=project_id, proposer=proposer, intent=intent)
            U.set_location(root, cid, intent=loc.intent, evidence=loc.evidence,
                           proposer=loc.proposer, suggested_role=loc.suggested_role,
                           project_id=loc.project_id, missing=loc.missing)
            _log("① 定位", "ok", f"{loc.intent} · 判据: {loc.evidence[:40]}")
    else:
        _log("① 定位", "skip", "未给 --conversation（定位落在会话上, 无会话则跳过）")

    # ── s2 建会话 ─────────────────────────────────────────────────────────
    if not cid:
        conv = U.create_conversation(root, title=text[:40] or "新需求",
                                     project_id=str(project_id or ""))
        cid = str(conv.get("id") or "")
        _log("② 建会话", "ok", cid)
        loc = locate(text, project_id=project_id, proposer=proposer, intent=intent)
        U.set_location(root, cid, intent=loc.intent, evidence=loc.evidence,
                       proposer=loc.proposer, suggested_role=loc.suggested_role,
                       project_id=loc.project_id, missing=loc.missing)
        _log("① 定位", "ok", f"{loc.intent}（补做）")
    else:
        _log("② 建会话", "skip", f"复用 {cid}")

    # ── s3 理解 ───────────────────────────────────────────────────────────
    snap = U.understanding_snapshot(root, cid)
    if snap.get("facts"):
        _log("③ 理解", "skip", f"已有 {len(snap['facts'])} 条事实")
    else:
        _say_step(root, cid, text)
        r = _understand_step(root, cid)
        n = len((U.understanding_snapshot(root, cid).get("facts")) or [])
        _log("③ 理解", "ok", f"抽出 {n} 条事实" if n else "未抽出事实（话里可能没有产品语义）")

    # ── s4 PRD ────────────────────────────────────────────────────────────
    pid = project_id
    if not pid:
        pid = str((U.get_conversation(root, cid) or {}).get("project_id") or "")
    prd_file = (root / "projects" / pid / "product_truth" / "prds.json") if pid else None
    if prd_file and prd_file.is_file():
        _log("④ PRD", "skip", "已有")
    else:
        try:
            r = _prd_step(root, cid)
            _log("④ PRD", "ok", str(r.get("prd_id") or ""))
        except Exception as exc:  # noqa: BLE001 — 链要如实报告断在哪
            _log("④ PRD", "fail", str(exc)[:120])

    # ── s5 分析产物（★ 缺则**自动跑** —— 否则用户还得手动搬数据, 就不叫闭环）──
    if pid:
        store = ProjectStore(root / "org")

        def _have() -> set[str]:
            return {str(getattr(a, "type", "")) for a in store.list_artifacts()
                    if getattr(a, "project_id", "") == pid}

        types = _have()
        need = [("product", "产品定义"), ("ux_ui", "交互设计"), ("design", "架构设计")]
        missing = [(k, zh) for k, zh in need if k not in types]
        if not missing:
            _log("⑤ 分析产物", "skip", "齐了（产品定义 / 交互设计 / 架构设计）")
        else:
            # ★ 顺序有依赖: 产品定义 → 交互设计 → 架构设计（架构吃前两者）
            #   （各环的生成器自己会报"缺输入", 所以顺序不能乱）
            from apps.cli.main import (
                FactoryContext, _dispatch_arch, cmd_product_develop, cmd_product_ux,
            )

            actx = FactoryContext(root=root)
            done: list[str] = []
            fail = ""
            for key, zh in need:
                if key in _have():
                    continue
                try:
                    if key == "product":
                        # ★ 把链里的需求原文作为"想法"传进去 ——
                        #   否则 product develop 会报"无想法文本"（实测踩到）
                        cmd_product_develop(actx, _ns(project=pid, idea=text))
                    elif key == "ux_ui":
                        cmd_product_ux(actx, _ns(project=pid, product=None))
                    else:
                        _dispatch_arch(actx, _ns(arch_command="design", project=pid,
                                                 product=None, ux_ui=None, artifact_id=None))
                    done.append(zh)
                except Exception as exc:  # noqa: BLE001 — 链要如实报告断在哪
                    fail = f"{zh}: {str(exc)[:90]}"
                    break
            if fail:
                _log("⑤ 分析产物", "fail", f"自动生成失败 → {fail}")
            else:
                _log("⑤ 分析产物", "ok", f"已自动生成: {' / '.join(done)}")
    else:
        _log("⑤ 分析产物", "skip", "无项目 ⇒ 跳过")

    # ── s6 拆解 ───────────────────────────────────────────────────────────
    tree = None
    plan_id = ""
    store = ProjectStore(root / "org") if pid else None
    if pid:
        cands = [t for t in D.list_trees(root)
                 if str(t.get("project_id") or "") == pid]
        if cands:
            tree = cands[-1]
            plan_id = str(tree.get("plan_id") or "")
            _log("⑥ 拆解", "skip", f"复用 {plan_id}")
    if tree is None:
        if pid:
            designs = [a for a in store.list_artifacts()
                       if getattr(a, "project_id", "") == pid
                       and "design" in str(getattr(a, "type", "")).lower()]
            if designs:
                try:
                    conv_loc = (U.get_conversation(root, cid) or {}).get("location") or {}
                    from apps.cli.main import _decompose_refs   # ★ 与 `tasktree decompose` 共用同一份引用语义
                    _refs = _decompose_refs(designs[-1])
                    tree = D.decompose_from_design(
                        root, project_id=pid, prd_ref=_refs[0], design_metadata=_refs[1],
                        intent=str(conv_loc.get("intent") or ""),
                        suggested_role=str(conv_loc.get("suggested_role") or ""),
                    )
                    plan_id = str(tree.get("plan_id") or "")
                    _log("⑥ 拆解", "ok", plan_id)
                except Exception as exc:  # noqa: BLE001
                    _log("⑥ 拆解", "fail", str(exc)[:140])
            else:
                _log("⑥ 拆解", "fail", "无 design 产物 ⇒ 先跑 `factory arch design --project …`")
        else:
            _log("⑥ 拆解", "fail", "无项目 ⇒ 无法拆解（需求需归属项目: --project）")

    # ── s7 细拆（把模块展开成任务）────────────────────────────────────────
    if do_expand and plan_id:
        tree = D.load_tree(root, plan_id)
        ns = (tree or {}).get("nodes") or []
        doms = [n for n in ns if n.get("kind") == "domain"]
        todo = [d for d in doms
                if len([x for x in ns if str(x.get("parent_id")) == str(d.get("id"))
                        and x.get("kind") == "task"]) < 2]
        if not todo:
            _log("⑦ 细拆", "skip", "所有模块都已细拆")
        else:
            from apps.cli.main import _arch_provider          # noqa: SLF001
            prov = _arch_provider()
            ok = stopped = failed = 0
            for d in todo:
                name = str(d.get("display_name") or d.get("title") or "")
                try:
                    kids = expand_module(name, desc=str(d.get("scope") or ""),
                                         acceptance=str(d.get("acceptance") or ""),
                                         caps=list(d.get("required_capabilities") or []),
                                         provider=prov)
                    r = D.expand_domain(root, plan_id, node_id=str(d.get("id")), kids=kids,
                                        project_id=pid)
                    if len(kids) < 2:
                        stopped += 1
                    else:
                        ok += 1
                    tree = r["tree"]
                except Exception:  # noqa: BLE001 — 单模块失败不拖垮全链
                    failed += 1
            _log("⑦ 细拆", "ok" if not failed else "warn",
                 f"{ok} 个模块已展开 · {stopped} 个判定为一件事 · {failed} 个失败")

    # ── 收尾: 给人工环节的入口提示 ────────────────────────────────────────
    return {
        "ok": True,
        "conversation_id": cid,
        "project_id": pid,
        "plan_id": plan_id,
        "steps": steps,
        "next": [
            f"factory tasktree todo {plan_id}" if plan_id else "（无任务树）",
            f"factory tasktree flow {plan_id}" if plan_id else "",
            "factory tasktree confirm <plan>" if plan_id else "",
            "看界面: 先跑 factory serve（默认 http://127.0.0.1:8787/）—— 没起来就没有界面 ✓",
        ],
    }

def register(sub: Any, json_opt: Any) -> None:
    """注册 `factory chain`（顶级命令 —— 全链编排）。"""
    p = sub.add_parser(
        "chain", help="★ 全链: 需求 → 定位 → 理解 → PRD → 拆解 → 细拆（一条命令跑完）")
    json_opt(p)
    p.add_argument("text", help="需求原文（一句话）")
    p.add_argument("--project", default="", help="归属项目 id（拆解需要）")
    p.add_argument("--conversation", default="", help="复用已有会话")
    p.add_argument("--type", dest="intent", default="",
                   choices=["", "新项目", "改现有", "问答", "一次性"], help="显式指定类型")
    p.add_argument("--proposer", default="founder", help="谁提的（承接）")
    p.add_argument("--no-expand", dest="do_expand", action="store_false",
                   help="不做细拆（只到任务树）")


def run(ctx: Any, args: Any) -> dict[str, Any]:
    """dispatch 入口（main.py 的 if/elif 链调它）。"""
    return run_chain(
        Path(ctx.root),
        text=str(getattr(args, "text", "") or ""),
        project_id=str(getattr(args, "project", "") or ""),
        intent=str(getattr(args, "intent", "") or ""),
        proposer=str(getattr(args, "proposer", "") or "founder"),
        conversation_id=str(getattr(args, "conversation", "") or ""),
        do_expand=bool(getattr(args, "do_expand", True)),
    )


def render(result: dict[str, Any], as_json: bool = False) -> None:
    """终端输出: 每步状态 + 人工环节的入口。"""
    if as_json:
        return
    print()
    print("  全链执行    " + str(result.get("conversation_id") or ""))
    print(f"  {'━' * 56}")
    icon = {"ok": "✔", "skip": "·", "warn": "⚠", "fail": "✗"}
    for s in result.get("steps") or []:
        print(f"  {icon.get(s['status'], '·')} {s['step']:<10} {s['detail']}")
    if result.get("plan_id"):
        print()
        print(f"  任务树: {result['plan_id']}")
        print("  下一步（人工环节）:")
        for n in result.get("next") or []:
            if n:
                print(f"    {n}")
    print()
