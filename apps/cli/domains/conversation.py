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
        "note": "消息已追加。要把它理解成事实, 需 LLM 通道（interpreter → proposal）—— 当前未接线。",
    }


def _facts(root: Path, args: Any) -> dict[str, Any]:
    cid = str(args.conversation_id)
    if U.get_conversation(root, cid) is None:
        return {"conversation_id": cid, "error": f"会话不存在: {cid}"}
    items = U.list_facts(root, cid, include_inactive=bool(getattr(args, "all", False)))
    return {"conversation_id": cid, "items": items, "count": len(items),
            "understanding_version": U.understanding_version(root, cid)}


# ─────────────────────────────────────────── 输出

def render(result: dict[str, Any], as_json: bool = False) -> None:
    """终端输出（--json 时由 main 统一处理, 这里只管人类可读形态）。"""
    if "error" in result and not result.get("ok", True):
        print(f"  ✗ {result['error']}")
        return
    if "created" in result:
        print(f"  ✓ 会话已建: {result['created']} — {result.get('title')}")
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
