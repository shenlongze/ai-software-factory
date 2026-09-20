"""CLI 里的【会话】—— 直接说话就能用（Founder: "我要在 cli 中可以使用会话功能, 并且可以使用 / 使用命令, 像 Hermes 一样"）。

规矩（照 Hermes 的手感）:
  · `/xxx` 开头          ⇒ 当成命令跑（`/status`、`/tasktree todo PLAN-x`）
  · 裸词且是已知命令      ⇒ 也当命令跑（向后兼容: 以前的 `status` 照旧）
  · 其它任何一句话        ⇒ **会话**: 走 LLM + 本平台数据, 该查就查、该答就答、拿不准就问
  · 会话**持久化**在平台的会话存储里（`conversation` 那套: conv-*.json + 消息）——不是我在内存里自说自话

安全: 会话里只自动执行**只读**命令（白名单）; 会改数据的（run/chain/confirm/decompose/backup…）
      一律不自动跑, 只把命令**念给用户**让他自己确认 ⇒ 聊天不会偷偷改东西。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

#: 会话里可以**自动执行**的只读命令（白名单; 想加就加只读的, 别加会写数据的 ✗）
READONLY_PREFIXES: tuple[str, ...] = (
    "status", "metrics", "dashboard", "kanban", "console dashboard", "console approvals",
    "tasktree show", "tasktree todo", "tasktree flow",
    "tasktree dataflow", "tasktree priority", "agent list", "approval list",
    "intelligence experience list", "intelligence experience evaluate", "intelligence recommend",
    "provider list", "memory list", "knowledge status", "plugin list", "execution list",
    "event list", "history", "run-status", "recover --dry-run", "experiment list",
)

_MAX_ROUNDS = 2          # 最多两轮"查数据 → 再回答"（别让它自己转圈）


def is_readonly(argv: list[str]) -> bool:
    """这条命令是不是只读白名单里的（会话里只自动跑这类）。"""
    head = " ".join(str(x) for x in argv).strip()
    return any(head == p or head.startswith(p + " ") for p in READONLY_PREFIXES)


def _snapshot(root: Path | str) -> str:
    """给 LLM 的一页数据摘要（用平台自己的口径, 不编）。"""
    from apps.cli.domains.welcome import _data_overview

    d = _data_overview(root)
    return (f"项目 {d['projects']} 个 · 任务树 {d['trees']} 棵 · 叶 {d['done']}/{d['leaves']} 完成 · "
            f"经验 {d['exp']} 条")


def _provider() -> Any:
    """本平台自己的 LLM（与架构师同一个 registry, 不另外配置）。"""
    from ai_factory_os.services.execution.kernel.cli import _provider_registry

    provs = _provider_registry().list()      # ★ 注册表本身不是列表, 要先 .list()（抄架构师的同一句）
    return provs[0] if provs else None


def _ask_llm2(prov: Any, messages: list[dict[str, str]]) -> tuple[str, dict[str, Any]]:
    from ai_factory_os.infrastructure.llm.provider import ProviderRequest

    ctx = "\n\n".join(f"[{m['role']}] {m['content']}" for m in messages)
    resp = prov.generate(ProviderRequest(task_context=ctx, max_tokens=1200))
    return str(getattr(resp, "content", "") or "").strip(), dict(getattr(resp, "usage", None) or {})


def provider_info(prov: Any) -> dict[str, str]:
    """这次用的是什么（模型/供应商）—— 如实读, 读不到就留空（不编）。"""
    return {
        "provider": str(getattr(prov, "provider_id", "") or ""),
        "model": str(getattr(prov, "_model", "") or getattr(prov, "model", "") or ""),
    }


def turn_header(meta: dict[str, Any], *, width: int = 66) -> str:
    """Hermes 那样的一行回合信息（分界线 + 模型/用量/成本/用时）。"""
    u = meta.get("usage") or {}
    bits: list[str] = []
    if meta.get("model"):
        bits.append(f"模型 {meta['model']}")
    if meta.get("provider"):
        bits.append(f"供应商 {meta['provider']}")
    pt, ct = u.get("prompt_tokens"), u.get("completion_tokens")
    if pt is not None or ct is not None:
        bits.append(f"tokens {pt if pt is not None else '?'}↑/{ct if ct is not None else '?'}↓")
    cost = u.get("estimated_cost_usd")
    if cost is not None:
        bits.append(f"成本 ${float(cost):.6f}")
    if meta.get("elapsed") is not None:
        bits.append(f"用时 {float(meta['elapsed']):.1f}s")
    if meta.get("rounds"):
        bits.append(f"查了 {int(meta['rounds'])} 次")
    info = " · ".join(bits)
    return "  " + "─" * width + ("\n  " + info if info else "")


def _system_prompt(root: Path | str) -> str:
    cmds = "\n".join(f"  - {p}" for p in READONLY_PREFIXES[:14])
    return (
        "你是 AI Factory OS 的终端助手, 正在跟老板对话。\n"
        f"当前数据: {_snapshot(root)}\n"
        "你能自己跑这些【只读】命令来查数据（一次最多 2 条）:\n"
        f"{cmds}\n\n"
        "回答规则:\n"
        "1 用中文, 像同事汇报一样简短; 不要长篇大论, 不要堆表。\n"
        "2 需要数据时, **先**输出一行或多行 `RUN: <命令>`, 我会执行并把结果回给你, 然后你再作答。\n"
        "3 老板在提'要做什么'时, 不要自己动手; 回一句'我理解成…, 要我开始吗?'并给出建议的第一条命令。\n"
        "4 不许编数据; 查不到就说查不到。\n"
        "5 会改数据的命令(run/chain/confirm/decompose/backup 等)不许自己跑, 只能**念出来**让老板确认。\n"
    )


def chat_turn(root: Path | str, text: str, *, conv_id: str = "", history: list[dict[str, str]] | None = None,
              on_run: Any = None) -> tuple[str, str, dict[str, Any]]:
    """一轮会话: 返回 (回答文本, 会话 id)。

    on_run(argv) 用于"把这行 RUN 命令真的跑掉并把结果拿回来"——由调用方注入（CLI 里 = 跑命令）。
    """
    from ai_factory_os.services.conversation import understanding as U

    conv = conv_id
    if not conv:
        d = U.create_conversation(root, title="终端会话")
        conv = str((d or {}).get("id") or (d or {}).get("conversation_id") or "")
    if conv:
        U.append_message(root, conv, role="human", content=text)

    import time as _time

    _t0 = _time.monotonic()
    _meta: dict[str, Any] = {"rounds": 0, "cmds": [], "elapsed": 0.0, "usage": {}}
    prov = _provider()
    if prov is None:
        return "（没配置 LLM provider —— 用 factory provider add 配一个, 我才能跟你对话。）", conv, _meta
    _meta.update(provider_info(prov))

    msgs = [{"role": "system", "content": _system_prompt(root)}]
    msgs += (history or [])[-8:]
    msgs.append({"role": "human", "content": text})

    answer = ""
    for _round in range(_MAX_ROUNDS):
        answer, _usage = _ask_llm2(prov, msgs)
        if _usage:
            _meta["usage"] = _usage
        _meta["rounds"] = _round + 1
        runs = [ln.split("RUN:", 1)[1].strip() for ln in answer.splitlines() if ln.strip().startswith("RUN:")]
        runs = [r for r in runs if r][:_MAX_ROUNDS]
        if not runs or on_run is None:
            break
        results: list[str] = []
        for r in runs:
            argv = r.split()
            if argv and argv[0] == "factory":
                argv = argv[1:]
            if not is_readonly(argv):
                results.append(f"`{r}` → 这是会改数据的命令, 我不能自动跑（请你自己确认后执行）")
                continue
            try:
                results.append(f"`{r}` → " + str(on_run(argv))[:1500])
            except Exception as exc:  # noqa: BLE001 — 查询失败不该打断对话
                results.append(f"`{r}` → 出错: {type(exc).__name__}: {str(exc)[:100]}")
        msgs.append({"role": "assistant", "content": answer})
        msgs.append({"role": "human", "content": "（命令结果）\n" + "\n".join(results) + "\n请据此回答我。"})
    answer = "\n".join(ln for ln in answer.splitlines() if not ln.strip().startswith("RUN:")).strip()
    if conv:
        U.append_message(root, conv, role="assistant", content=answer)
    _meta["elapsed"] = round(_time.monotonic() - _t0, 2)
    # 记一笔用量（平台的用量账本 —— 与执行侧同一本账, 不是我自己另记）
    try:
        from ai_factory_os.infrastructure.llm.providers.usage import ProviderUsage, UsageStore

        _u = _meta.get("usage") or {}
        UsageStore(str(Path(root) / "providers")).record(ProviderUsage(
            provider_id=str(_meta.get("provider") or "unknown"),
            model=str(_meta.get("model") or "") or None,
            prompt_tokens=int(_u.get("prompt_tokens") or 0),
            completion_tokens=int(_u.get("completion_tokens") or 0),
            estimated_cost=float(_u.get("estimated_cost_usd") or 0.0),
            latency_ms=int(float(_meta.get("elapsed") or 0) * 1000),
        ))
    except Exception:  # noqa: BLE001 — 记账失败不影响对话
        pass
    return answer, conv, _meta
