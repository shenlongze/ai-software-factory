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
    p_new.add_argument("--project", default="", help="绑定项目 id（决定记忆归属层与知识检索源; 见 factory project adopt）")

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
    p_loc = csub.add_parser(
        "locate", help="★ 需求定位（流程第一步）: 归属/类型/承接 + 判据 + 还缺什么")
    json_opt(p_loc)
    p_loc.add_argument("conversation_id", help="会话 id（conv-*）")
    p_loc.add_argument("text", help="需求原文")
    p_loc.add_argument("--type", dest="intent", default="",
                       choices=["", "新项目", "改现有", "问答", "一次性"],
                       help="显式指定类型（不给=按规则判定）")
    p_loc.add_argument("--project", default=None, help="归属项目 id（可选）")
    p_loc.add_argument("--proposer", default="", help="谁提的（承接）")
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
    if act == "locate":
        return _locate(root, args)
    if act == "prd":
        return _prd(root, args)
    raise ValueError(f"未知子命令: {act!r}")



def _locate(root: Path, args: Any) -> dict[str, Any]:
    """★ 需求定位（Founder: "需求进来先定位"）—— 判定三要素并【落盘到会话】。

    为什么落盘（R26 状态必须落盘）: 定位结果（尤其**承接**）是后续步骤的输入 ——
    "承接决定④拆解的粒度"。不落盘 ⇒ 下一步读不到 ⇒ 定位白做。
    """
    from ai_factory_os.services.conversation import understanding as U
    from ai_factory_os.services.conversation.intake import locate

    cid = str(getattr(args, "conversation_id", "") or "")
    conv = U.get_conversation(root, cid)
    if not conv:
        raise ValueError(f"会话不存在: {cid}（factory conversation list 看有哪些）")
    r = locate(
        str(getattr(args, "text", "") or ""),
        project_id=str(getattr(args, "project", None) or conv.get("project_id") or ""),
        proposer=str(getattr(args, "proposer", "") or conv.get("created_by") or ""),
        intent=str(getattr(args, "intent", "") or ""),
    )
    # ★ 落盘到会话（后续步骤读它）
    U.set_location(
        root, cid, intent=r.intent, evidence=r.evidence, proposer=r.proposer,
        suggested_role=r.suggested_role, project_id=r.project_id, missing=r.missing,
    )
    return {"ok": True, "action": "conversation-locate", "location": r.to_dict(),
            "conversation_id": cid}

def _new(root: Path, args: Any) -> dict[str, Any]:
    """建会话；可选 --project 绑定项目。

    ★ 2026-09-19 新增 --project: "会话绑项目"是**记忆隔离的核心**（决定 facts 落哪一层、
    知识检索扫哪个仓库）。绑定走既有 `U.move_conv_to_project`（幂等 + 原子搬移, 符合
    Founder 铁律「属于项目的文件必须在项目目录下」）。
    """
    conv = U.create_conversation(root, title=str(getattr(args, "title", "") or "新会话"))
    cid = conv["id"]
    out: dict[str, Any] = {"created": cid, "title": conv.get("title"), "status": conv.get("status")}
    pid = str(getattr(args, "project", "") or "")
    if pid:
        moved = False
        try:
            moved = bool(U.move_conv_to_project(root, cid, pid))
        except Exception:  # noqa: BLE001 — 绑定失败不影响建会话（但如实报出）
            moved = False
        out["project_id"] = pid
        out["moved"] = moved
    return out


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


def _root_dir(root: Any) -> Path:
    """数据根（RAG 索引的存放根 —— index_root, 不污染项目仓库）。"""
    return Path(str(root))


def _iter_projects(data: Any) -> list[dict[str, Any]]:
    """从 org/projects.json 的不同嵌套形态里取出项目 dict 列表。"""
    out: list[dict[str, Any]] = []
    if isinstance(data, list):
        out.extend(x for x in data if isinstance(x, dict))
    elif isinstance(data, dict):
        for key in ("items", "projects", "project"):
            v = data.get(key)
            if isinstance(v, list):
                out.extend(x for x in v if isinstance(x, dict))
            elif isinstance(v, dict):
                out.extend(x for x in v.values() if isinstance(x, dict))
    return out


def _project_dir(root: Any, cid: str) -> Path | None:
    """会话所属项目的**代码目录**（org 项目记录里的 repo_path）。

    拿不到 ⇒ None ⇒ 跳过知识检索（全局会话没有"项目文档"可查, 这是正确语义）。
    ★ 记忆链: `factory project adopt <repo>` 写入 repo_path ⇒ 这里读出 ⇒ 知识索引知道扫哪。
    """
    try:
        import json

        # ★ 用 _load_conv（原始文档）—— `get_conversation` 返回的是**投影**, 不含 project_id。
        doc = U._load_conv(root, cid) or {}                    # noqa: SLF001 — 同包内部读取
        pid = str(doc.get("project_id") or "").strip()          # 防御: 外部传入值可能带空白
        if not pid:
            return None
        for f in (Path(str(root)) / "org").rglob("projects.json"):
            for item in _iter_projects(json.loads(f.read_text(encoding="utf-8"))):
                if str(item.get("id") or "").strip() == pid:
                    rp = str(item.get("repo_path") or "")
                    if rp and Path(rp).is_dir():
                        return Path(rp)
    except Exception:  # noqa: BLE001 — 取不到就跳过（不阻塞理解）
        pass
    return None


def _slug_of(ws: Path, cid: str) -> str:
    """RAG 索引的 slug（按项目目录名, 稳定且可读）。"""
    return ws.name or cid


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

    # ★ 2026-09-19（mem-8 · 让"已有的记忆机制"生效）: 注入 project_memory 的项目历史记忆。
    #   背景: `project_memory`（2026-08-27, 比本轮的分层早）已经有真数据 + 类型化
    #   （decision/learning/error/pattern/observation）+ 权威等级 + 时间衰减,
    #   但 `inject_block`（注入）**零调用** ⇒ 记了却没用上（实测: P-b0adfaa6 有 3 条无人看见）。
    #   本刀只做**接线**（不改它的能力）: 有项目 ⇒ 取 top-N 注入 prompt 的「项目历史记忆」段。
    #   失败安全: 无项目/无记忆/异常 ⇒ 跳过（行为与之前一致）。
    try:
        from ai_factory_os.services.conversation.project_memory import MemoryStore

        _pm_pid = str((U._load_conv(root, cid) or {}).get("project_id") or "").strip()  # noqa: SLF001
        if _pm_pid:
            _pm = MemoryStore.load(str(root), _pm_pid)
            _blk = _pm.inject_block(n=4, query=text)
            if _blk:
                snap = dict(snap)
                snap["project_memory_block"] = _blk
    except Exception:  # noqa: BLE001 — 项目记忆不可用 ⇒ 跳过（不阻塞理解）
        pass

    # ★ 2026-09-19（记忆主线 · 知识记忆接通）: 让"理解"除事实外, 还能检索【项目文档知识】。
    #   背景: RAG 索引已修好并重建（505 文件 / 20000 片段, 含 docs/design 59 篇）,
    #         但 `rag_query` 零消费者 ⇒ 建了没人读。
    #   做法: 用本会话最新消息当查询词, 从知识库取 top-N（已按分档加权 + 单文件限流排序）,
    #         并入 snapshot 的 knowledge 段; 每条带【来源文件 + 档位】供引用与审计。
    #   失败安全: 索引不存在/检索异常 ⇒ 跳过（理解照常, 行为与之前一致）。
    #   说明: workspace=项目目录（扫描源）, index_root=数据根（索引位置）—— 见 knowledge_store 的 index_root。
    try:
        from ai_factory_os.infrastructure.retrieval import rag_query as _rag
        from ai_factory_os.infrastructure.retrieval.knowledge_store import KnowledgeStore

        _ws = _project_dir(root, cid)
        if _ws:
            # ★ 2026-09-19（mem-6 · 记忆"不过期"）: 检索前先看索引是否过期, 过期就**增量重建**。
            #   为什么: 索引原来只在 adopt 时建一次 ⇒ 文档改了检索到旧版本（记错, 比忘记更糟）。
            #   incremental_ingest 早就有但零消费者 —— 这里就是它的触发点。
            #   失败安全: 重建失败 ⇒ 照旧检索（不阻塞理解）。
            try:
                _ks = KnowledgeStore(_ws, _slug_of(_ws, cid), index_root=_root_dir(root))
                _stale, _n = _ks.is_stale()
                if _stale:
                    _ks.incremental_ingest()
            except Exception:  # noqa: BLE001 — 重建失败不阻塞
                pass
            _hits, _kmeta = _rag(_root_dir(root), _slug_of(_ws, cid), text, top_k=3)
            if _hits:
                snap = dict(snap)
                snap["knowledge"] = [
                    {
                        "file": h.file,
                        "tier": h.tier,
                        "score": round(float(h.score), 4),
                        "excerpt": str(h.fragment)[:280],
                        "reason": h.reason,
                    }
                    for h in _hits
                ]
                snap["knowledge_from"] = {
                    "count": len(_hits),
                    "tiers": sorted({h.tier for h in _hits}),
                    "note": "项目文档知识（来自 RAG 索引）—— 供引用, 非既有事实; 引用时须给出文件名",
                }
    except Exception:  # noqa: BLE001 — 知识检索失败不阻塞理解
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
    if result.get("location"):
        # ★ 需求定位（流程第一步）—— 显示三要素 + 判据 + 还缺什么
        loc = result["location"]
        g = loc.get("归属") or {}
        c = loc.get("承接") or {}
        print()
        print(f"  定位结果    {result.get('conversation_id')}")
        print(f"  {'━' * 48}")
        print(f"  归属  项目={g.get('project') or '（未指定）'}"
              f"  部门={g.get('department') or '-'}  公司={g.get('company') or '-'}")
        print(f"  类型  {loc.get('类型')}")
        print(f"  判据  {loc.get('判据')}")
        print(f"  承接  提出者={c.get('提出者') or '-'}   建议角色={c.get('建议角色') or '-'}")
        miss = loc.get("还缺") or []
        if miss:
            print()
            print("  ⚠ 还缺（不确认很可能做错）:")
            for m in miss:
                print(f"    · {m}")
        else:
            print()
            print("  ✓ 三要素齐了 —— 可进入下一步（理解）")
        print()
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
