"""会话 域命令（apps/cli/domains/conversation）—— 链路第 1 环的 CLI 入口。

为什么新建（2026-09-15）:
    端到端实测（从 CLI 跑 8 环）发现 —— **8 环里第 1 环在 CLI 上是空的**:
    `factory --help` 里没有任何会话命令; 会话创建此前只存在于手写 Web/API 面,
    而那层已按 **ADR-0038**（API 层退役）删除。
    ADR-0038 同时定了「**CLI 是地基**」⇒ 会话入口必须在 CLI 上。

实现铁律（不重造）:
    直接调 `services/conversation/understanding.py`（产品认知事实层）——
    会话的**权威实现在新地基**, 本文件只做参数解析 + 包络 + 事件, 不新写会话逻辑。

本域命令（依据 `apps/cli/registry.py`, 域 = conversation）:
    conversation new   建会话（conv-*）
    conversation list  会话列表
    conversation show  详情（含事实快照）
    conversation say   追加一条用户消息（append-only）
    conversation facts 事实清单（含 superseded 等非活动态, --all）

无 LLM 也能用:
    建 / 列 / 看 / 说 / 列事实 —— **全部不依赖 LLM** ✓
    需要 LLM 的只有「把用户的话理解成事实」(interpreter → proposal), 那是
    下一步接线的事; 当前 `--understand` 若 LLM 不可用则**显式报错**, 不静默降级。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ai_factory_os.services.conversation import understanding as U
from ai_factory_os.services.conversation import interpreter as _INTERP
from ai_factory_os.services.conversation import proposal as _PROP
from ai_factory_os.services.conversation import formalization as _FORM


def register(sub: Any, json_opt: Callable[[Any], None]) -> None:
    """注册 conversation 域的命令。"""
    p = sub.add_parser("conversation", help="会话（链路第 1 环）: new/list/show/say/facts")
    json_opt(p)
    csub = p.add_subparsers(dest="conversation_command", required=True)

    p_new = csub.add_parser("new", help="建会话（conv-*）")
    json_opt(p_new)
    p_new.add_argument("--title", default="新会话", help="会话标题")

    p_list = csub.add_parser("list", help="会话列表")
    json_opt(p_list)

    p_show = csub.add_parser("show", help="会话详情（含事实快照）")
    json_opt(p_show)
    p_show.add_argument("conversation_id", help="会话 ID（conv-*）")

    p_say = csub.add_parser("say", help="追加一条用户消息")
    json_opt(p_say)
    p_say.add_argument("conversation_id", help="会话 ID（conv-*）")
    p_say.add_argument("text", help="用户要说的话")

    p_facts = csub.add_parser("facts", help="事实清单")
    json_opt(p_facts)
    p_facts.add_argument("conversation_id", help="会话 ID（conv-*）")
    p_facts.add_argument("--all", action="store_true", help="含非活动态（SUPERSEDED/REJECTED）")

    p_und = csub.add_parser(
        "understand", help="把用户的话理解成事实（LLM → proposal → facts; 链路第 2 环）")
    json_opt(p_und)
    p_und.add_argument("conversation_id", help="会话 ID（conv-*）")
    p_und.add_argument("--text", default="", help="要理解的话（缺省 = 最近一条用户消息）")

    p_prd = csub.add_parser(
        "prd", help="从理解派生 PRD（链路第 2 环; product-manager）")
    json_opt(p_prd)
    p_prd.add_argument("conversation_id", help="会话 ID（conv-*）")
    p_prd.add_argument("--title", default="", help="PRD 标题（缺省 = 会话标题）")
    p_prd.add_argument("--list", action="store_true", help="只列出 PRD，不派生")
    p_prd.add_argument("--show", default="", help="显示指定 PRD 的 Markdown（prd-*）")


# ─────────────────────────────────────────── handler

def run(ctx: Any, args: Any) -> dict[str, Any]:
    """dispatch 入口（main.py 的 if/elif 链调它）。"""
    root = Path(ctx.root)
    act = args.conversation_command
    if act == "new":
        return _new(root, args)
    if act == "list":
        return _list(root)
    if act == "show":
        return _show(root, args)
    if act == "say":
        return _say(root, args)
    if act == "facts":
        return _facts(root, args)
    if act == "understand":
        return _understand(root, args)
    if act == "prd":
        return _prd(root, args)
    raise ValueError(f"未知子命令: {act!r}")


def _new(root: Path, args: Any) -> dict[str, Any]:
    conv = U.create_conversation(root, title=str(getattr(args, "title", "") or "新会话"))
    return {"created": conv["id"], "title": conv.get("title"), "status": conv.get("status")}


def _list(root: Path) -> dict[str, Any]:
    items = U.conversations(root)
    return {"items": items, "count": len(items)}


def _show(root: Path, args: Any) -> dict[str, Any]:
    cid = str(args.conversation_id)
    snap = U.understanding_snapshot(root, cid)
    conv = U.get_conversation(root, cid)
    if conv is None:
        return {"conversation_id": cid, "found": False,
                "error": f"会话不存在: {cid}（用 factory conversation list 看现有会话）"}
    return {
        "conversation_id": cid,
        "found": True,
        "title": conv.get("title"),
        "status": conv.get("status"),
        "messages": len(U.messages(root, cid)),
        "understanding_version": snap.get("version", 0),
        "facts": snap.get("facts", []),
        "by_type": snap.get("by_type", {}),
    }


def _say(root: Path, args: Any) -> dict[str, Any]:
    cid = str(args.conversation_id)
    text = str(args.text)
    if U.get_conversation(root, cid) is None:
        return {"conversation_id": cid, "ok": False,
                "error": f"会话不存在: {cid}"}
    msg = U.append_message(root, cid, role="human", content=text)
    return {
        "conversation_id": cid,
        "ok": True,
        "message_id": msg["id"],
        "role": msg["role"],
        "note": "消息已追加。下一步: factory conversation understand <会话> —— 经 LLM 理解成事实。",
    }


def _facts(root: Path, args: Any) -> dict[str, Any]:
    cid = str(args.conversation_id)
    if U.get_conversation(root, cid) is None:
        return {"conversation_id": cid, "error": f"会话不存在: {cid}"}
    items = U.list_facts(root, cid, include_inactive=bool(getattr(args, "all", False)))
    return {"conversation_id": cid, "items": items, "count": len(items),
            "understanding_version": U.understanding_version(root, cid)}


def _llm_fn() -> Any:
    """LLM 原始调用通道（`LLMFn = (prompt) -> str | None`）。

    ★ 2026-09-15 已切新地基: 用 `infrastructure/llm/complete_text.complete_text`
      （组装自 gateway.complete + control_plane + trace —— 不再借老区 llm_raw/reasoning）。

    不可用 → None ⇒ interpreter 走**诚实降级**（CLARIFY, 不猜产品事实）, 不是静默失败。
    """
    try:
        from ai_factory_os.infrastructure.llm.complete_text import complete_text
        return complete_text
    except Exception:  # noqa: BLE001 — 通道不可用 = 降级, 不该炸
        return None


def _last_human_message(root: Path, cid: str) -> tuple[str, str]:
    """最近一条 human 消息 → (文本, message_id)。message_id 用于来源可追溯。"""
    for m in reversed(U.messages(root, cid)):
        if m.get("role") == "human":
            return str(m.get("content") or ""), str(m.get("id") or "")
    return "", ""


def _understand(root: Path, args: Any) -> dict[str, Any]:
    """把用户的话理解成事实 —— 链路第 2 环。

    管道（Golden Path §7/§8）: LLM 只产 proposal · Domain 决定 Truth
        text → interpreter(LLM) → validate_proposal → apply_operations → facts
    唯一写路径 ✓（LLM 不直接写 Truth）
    """
    cid = str(args.conversation_id)
    if U.get_conversation(root, cid) is None:
        return {"conversation_id": cid, "ok": False, "error": f"会话不存在: {cid}"}
    text = str(getattr(args, "text", "") or "")
    mid = ""
    if not text:
        text, mid = _last_human_message(root, cid)
    if not text:
        return {"conversation_id": cid, "ok": False,
                "error": "没有可理解的用户消息（先 conversation say 一句，或传 --text）"}

    llm = _llm_fn()
    snap = U.understanding_snapshot(root, cid)

    # ★ 2026-09-19（有效果的最后一环）: 让"理解"读【分层记忆】, 而不只读本会话。
    #   实测背景: 会话1 的 4 条决策已落到 knowledge/global/facts.json, 但会话2 问
    #   "我们之前的存储设计是什么" ⇒ 答"暂时查不到" —— 因为理解只喂了本会话的 facts。
    #   做法: 用 scoped_facts.effective_facts(该会话作用域) 取【继承 + 同公司横向 + 权限过滤】
    #   后的跨会话事实, 并入 snapshot 交给 interpreter; 每条标 provenance, 供引用与审计。
    #   失败安全: 分层读不到 ⇒ 退回本会话（行为与之前一致, 不阻塞理解）。
    try:
        from ai_factory_os.services.conversation import scoped_facts as _SF

        _doc = U.get_conversation(root, cid) or {}
        _scope = _SF.scope_from_conversation(_doc)
        _eff = _SF.effective_facts(root, _scope)
        _mine = {str(f.get("id") or "") for f in (snap.get("facts") or [])}
        _extra = [f for f in (_eff.get("facts") or []) if str(f.get("id") or "") not in _mine]
        if _extra:
            snap = dict(snap)
            snap["facts"] = list(snap.get("facts") or []) + _extra
            snap["memory_from"] = {
                "layers": _eff.get("by_level") or {},
                "count": len(_extra),
                "note": "跨会话记忆（来自分层）—— 与本次会话事实并列, 每条带 provenance",
            }
    except Exception:  # noqa: BLE001 — 分层不可用 ⇒ 只读本会话（不阻塞理解）
        pass

    prop = _INTERP.llm_semantic_interpreter(str(root), cid, text, snap, llm_fn=llm)
    ops = list(prop.get("operations") or [])
    applied = _PROP.apply_operations(root, cid, ops, source_message_id=mid,
                                     fallback_actor="conversation.cli") if ops else []
    return {
        "conversation_id": cid, "ok": True, "understood": text,
        "llm": "available" if llm is not None else "unavailable（诚实降级）",
        "operations": ops, "applied": applied,
        "reply": prop.get("reply") or "", "question": prop.get("question") or "",
        "understanding_version": U.understanding_version(root, cid),
        "facts_count": len(U.list_facts(root, cid)),
    }


def _prd(root: Path, args: Any) -> dict[str, Any]:
    """从理解派生 PRD —— 链路第 2 环（product-manager）。

    语义（formalization 的设计, 不在此重写）:
      · PRD **从 Understanding 派生**（`create_prd` 内部读 snapshot）
      · 带 `source_product_understanding_version` 锚点 —— 理解变了, PRD 可版本化重派生
      · 修改走 `update_prd`（新版）, 不原地改; 已有同名 draft 会抛错（防误解）
    """
    cid = str(args.conversation_id)
    if U.get_conversation(root, cid) is None:
        return {"conversation_id": cid, "ok": False, "error": f"会话不存在: {cid}"}

    if getattr(args, "show", ""):
        prd = _FORM.get_prd(root, cid, str(args.show))
        if prd is None:
            return {"conversation_id": cid, "ok": False, "error": f"PRD 不存在: {args.show}"}
        return {"conversation_id": cid, "mode": "show", "prd_id": prd.get("id"),
                "markdown": _FORM.render_prd_markdown(prd)}

    if getattr(args, "list", False):
        items = _FORM.list_prds(root, cid)
        return {"conversation_id": cid, "mode": "list", "items": items, "count": len(items)}

    facts_n = len(U.list_facts(root, cid))
    try:
        prd = _FORM.create_prd(root, cid, actor="conversation.cli",
                               title=str(getattr(args, "title", "") or ""))
    except Exception as exc:  # noqa: BLE001 — 已有同名 draft 等业务错, 转成可读提示
        return {"conversation_id": cid, "ok": False,
                "error": f"派生 PRD 失败: {exc}", "facts": facts_n}
    return {
        "conversation_id": cid, "mode": "created", "ok": True,
        "prd_id": prd.get("id"), "version": prd.get("version"),
        "title": prd.get("title"), "status": prd.get("status"),
        "source_understanding_version": prd.get("source_product_understanding_version"),
        "sections": sorted((prd.get("content") or {}).keys()),
        "facts": facts_n,
    }


# ─────────────────────────────────────────── 输出

def render(result: dict[str, Any], as_json: bool = False) -> None:
    """终端输出（--json 时由 main 统一处理, 这里只管人类可读形态）。"""
    if "error" in result and not result.get("ok", True):
        print(f"  ✗ {result['error']}")
        return
    if "created" in result:
        print(f"  ✓ 会话已建: {result['created']} — {result.get('title')}")
    elif result.get("mode") == "created":
        print(f"  ✓ PRD 已派生: {result['prd_id']} v{result.get('version')} — {result.get('title')}")
        print(f"    状态 {result.get('status')} · 锚定 understanding v{result.get('source_understanding_version')}"
              f" · 源事实 {result.get('facts')} 条")
        print(f"    章节: {', '.join(result.get('sections') or [])}")
    elif result.get("mode") == "show":
        print(result.get("markdown") or "")
    elif result.get("mode") == "list":
        for it in result.get("items") or []:
            print(f"    {it.get('id')}  v{it.get('version')}  [{it.get('status')}]  {it.get('title')}")
        print(f"  共 {result.get('count')} 份")
    elif "understood" in result:
        print(f"  理解: {result['understood']!r}")
        print(f"  LLM: {result['llm']}")
        ops = result.get("operations") or []
        if not ops:
            print("  · 无操作（未抽到产品事实 —— 可能话里没有产品语义）")
        for a in result.get("applied") or []:
            f = a.get("fact") or {}
            if f:
                print(f"    ✓ [{a.get('op')}] [{f.get('type')}/{f.get('status')}] {f.get('content')}")
            else:
                print(f"    ✓ [{a.get('op')}] {a.get('content') or ''}")
        if result.get("reply"):
            print(f"  回复: {result['reply']}")
        if result.get("question"):
            print(f"  追问: {result['question']}")
        print(f"  事实 {result.get('facts_count')} 条 · 理解版本 v{result.get('understanding_version')}")
    elif "understanding_version" in result and "items" in result:
        # facts（★ 必须先判: 它的返回值也含 count/items, 否则会被下面的 list 分支先吃掉）
        for f in result["items"]:
            print(f"    [{f.get('type')}/{f.get('status')}] {f.get('content')}")
        print(f"  共 {result['count']} 条 · 理解版本 v{result.get('understanding_version')}")
    elif "count" in result and "items" in result:
        items = result["items"]
        if not items:
            print("  （无会话）— 用 factory conversation new 建一个")
        for it in items:
            print(f"    {it.get('id')}  {it.get('title')}  [{it.get('status')}]")
        print(f"  共 {result['count']} 个")
    elif "facts" in result:
        print(f"  会话 {result['conversation_id']} — {result.get('title')} [{result.get('status')}]")
        print(f"    消息 {result.get('messages')} 条 · 理解版本 v{result.get('understanding_version')} · 事实 {len(result.get('facts', []))} 条")
        for f in result.get("facts", []):
            print(f"      [{f.get('type')}/{f.get('status')}] {f.get('content')}")
    elif "message_id" in result:
        print(f"  ✓ 已追加消息 {result['message_id']}（会话 {result['conversation_id']}）")
        print(f"    {result.get('note', '')}")
