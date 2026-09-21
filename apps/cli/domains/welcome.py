"""友好首屏 + 中文帮助中心 —— "怎么进入 factory" 的那个入口。

实测病（Founder 问「我需要如何进入 factory 的 cli」时暴露）:
  敲 `factory` 不带参数 ⇒ 只有一句英文报错
  `factory: error: the following arguments are required: command` ✗
  —— 对非技术用户等于"进不去": 没有欢迎屏、没有"你能做什么"、没有中文帮助。

本模块:
  · 空参 ⇒ 版本 + 你的数据概览 + 编号菜单; 有终端则**可交互**（选编号直接跑）,
    非终端（管道/脚本）⇒ 只打印, 退出码 0 ✓（绝不挂住）
  · `factory help [--role 老板|产品|开发|运维]` ⇒ 中文帮助中心（命令全部真实存在, 不写没做的）
"""

from __future__ import annotations

import sys
from pathlib import Path

#: 编号 → (菜单文字, 要执行的 argv)。★ 只列**已验证存在**的命令。
_MENU: dict[str, tuple[str, list[str]]] = {
    "1": ("看家底（项目/任务树/叶/事件）", ["status"]),
    "2": ("看七域看板（项目·审批·Agent·决策·成本·经验·活动）", ["console", "dashboard"]),
    "3": ("看某棵树的逐叶清单", ["tasktree", "todo"]),
    "4": ("提一条新需求 → 出 PRD/设计/任务树", ["chain"]),
    "5": ("跑任务（派活 + 真执行）", ["run"]),
    "6": ("经验与推荐（学习自治攒下来的）", ["intelligence", "experience", "list"]),
}

_ROLE_GUIDE: dict[str, list[tuple[str, str]]] = {
    "老板": [
        ("factory status", "一眼看家底: 有几个项目/几棵树/多少叶完成"),
        ("factory console dashboard", "七域看板: 项目·待审批·Agent·决策·成本·经验·活动"),
        ("factory kanban", "看板（按状态分列）"),
        ("factory approval --help", "审批门（高风险动作要你点头）"),
        ("factory backup create", "备份数据"),
    ],
    "产品": [
        ("factory chain \"我要做…\" --project P-…", "一条命令: 定位→会话→理解→PRD→产品/交互/架构→拆解"),
        ("factory tasktree todo <PLAN>", "逐叶清单（每叶带一句话验收 + 所需能力）"),
        ("factory tasktree confirm <PLAN>", "人工门: 你看懂了才进执行"),
        ("factory tasktree workflow <PLAN> --list", "给树挂流程（可编排）"),
        ("factory understand <目录>", "理解一个已有仓库并落盘"),
    ],
    "开发": [
        ("factory run --plan <PLAN> --project P-… --limit 3 --parallel 2", "派活 + 真执行（分批）"),
        ("factory recover --plan <PLAN> [--stale-after 60]", "中断后按检查点把叶交回"),
        ("factory execution list", "执行记录"),
        ("factory metrics", "指标（Agents / Validation 接真事件）"),
        ("factory plugin list", "插件（清单丢进投放目录即生效）"),
    ],
    "运维": [
        ("factory status / factory metrics", "巡检两条"),
        ("factory backup create / factory recover <task_id>", "备份与恢复"),
        ("factory console approvals", "待审批"),
        ("factory intelligence experience list", "经验库（含失败负样本）"),
        ("bash scripts/verify.sh", "门禁 16 项（ruff/守卫/工具健康）"),
    ],
}


def _data_overview(root: Path | str) -> dict[str, str]:
    """你的数据概览（读不到 ⇒ '?', 绝不因为读失败而崩首屏）。"""
    out = {"projects": "?", "trees": "?", "leaves": "?", "done": "?", "exp": "?"}
    try:
        from ai_factory_os.services.organization.projects import ProjectStore

        rows = ProjectStore(Path(root) / "org").list_projects() or []
        out["projects"] = str(len(rows))
    except Exception:  # noqa: BLE001 — 概览是"锦上添花", 读失败不影响入口
        pass
    try:
        from ai_factory_os.services.work import decomposition as D

        metas = D.list_trees(Path(root)) or []
        out["trees"] = str(len(metas))
        leaves = done = 0
        for m in metas[:20]:
            t = D.load_tree(Path(root), str(m.get("plan_id") or ""), str(m.get("project_id") or ""))
            for n in (t or {}).get("nodes") or []:
                if n.get("kind") == "task":
                    leaves += 1
                    done += 1 if str(n.get("status")) == "completed" else 0
        out["leaves"], out["done"] = str(leaves), str(done)
    except Exception:  # noqa: BLE001
        pass
    try:
        from ai_factory_os.services.learning.store import ExperienceStore

        out["exp"] = str(ExperienceStore(Path(root) / "intelligence").count())
    except Exception:  # noqa: BLE001
        pass
    return out


def _dw(s: object) -> int:
    """显示宽度（CJK 算 2 列）—— 中文框线对齐必须用它, 否则右边框歪。"""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in str(s))


def _pad(s: object, width: int) -> str:
    """按显示宽度右侧补空格到 width（超宽则截断加 …）。"""
    txt = str(s)
    while _dw(txt) > width:
        txt = txt[:-1]
        if _dw(txt) + 1 > width:
            txt = txt[:-1] + "…"
            break
    return txt + " " * max(0, width - _dw(txt))


def _version() -> str:
    try:
        from importlib.metadata import version

        return version("ai-software-factory")
    except Exception:  # noqa: BLE001 — 装法不同（源码跑）⇒ 不编版本号
        return "（未安装/源码运行）"


def render_welcome(root: Path | str) -> str:
    """欢迎屏文本（首屏就是它）。"""
    d = _data_overview(root)
    lines = [
        "",
        "  ╭──────────────────────────────────────────────────────────────╮",
        "  │  " + _pad(f"AI Factory OS  v{_version()}", 60) + "│",
        "  ╰──────────────────────────────────────────────────────────────╯",
        f"  你的数据（{root}）:",
        f"    项目 {d['projects']} · 任务树 {d['trees']} · 叶 {d['done']}/{d['leaves']} 完成 · 经验 {d['exp']} 条",
        "",
        "  你想做什么?（输入编号直接跑；q 退出）",
    ]
    for k, (label, _argv) in _MENU.items():
        lines.append(f"    {k}  {label}")
    lines += [
        "    h  中文帮助中心（按角色: 老板 / 产品 / 开发 / 运维）",
        "",
        "  提示: 任何命令加 -h 看用法; `factory help` 打开帮助中心;",
        "        第一次用不会碰坏东西 —— 所有命令都是幂等的（不自建就先自建目录）。",
        "",
    ]
    return "\n".join(lines)


def run_welcome(root: Path | str, *, interactive: bool | None = None) -> int:
    """打印首屏; 有终端则可交互（选编号 → 直接跑那条命令）。返回退出码。"""
    print(render_welcome(root))
    if interactive is None:
        interactive = sys.stdin.isatty() and sys.stdout.isatty()
    if not interactive:
        return 0
    while True:
        try:
            choice = input("  选择 > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if choice in ("q", "quit", "exit", ""):
            return 0
        if choice == "h":
            print(render_help(""))
            continue
        item = _MENU.get(choice)
        if item is None:
            print("  （没这个编号; 输入 1-6 / h / q）")
            continue
        argv = list(item[1])
        if argv[0] in ("tasktree", "run", "chain"):
            extra = input(f"  `factory {' '.join(argv)}` 还需要参数（可留空返回）: ").strip()
            if not extra:
                continue
            argv += extra.split()
        from apps.cli.main import main as _main  # 局部导入: 避免模块环

        print(f"  ── 跑: factory {' '.join(argv)}")
        try:
            _main(argv)
        except SystemExit:
            pass
        print()


def _term_width(default: int = 100) -> int:
    try:
        import shutil

        return max(60, min(120, shutil.get_terminal_size((default, 24)).columns - 2))
    except Exception:  # noqa: BLE001
        return default


def box(title: str, text: str, *, width: int = 0) -> str:
    """Hermes 那样把一段话装进圆角框（标题在顶栏, 中文字宽算 2）。"""
    # ★ 宽度必须**三条线一致**（实测踩到: 差 1-2 列 ⇒ 框看着是歪的 ✗）
    #   三条线各自的目标宽度都是 W: 顶 `  ╭─ T ` + dash + `╮`; 内容 `  │ ` + 文本 + space + `│`;
    #   底 `  ╰` + dash + `╯`（_dw 按显示宽度算, 中文=2）
    w = width or _term_width()
    head = f"  ╭─ {title} "
    lines = [head + "─" * max(0, w - _dw(head) - 1) + "╮"]
    for raw in (text or "").splitlines() or [""]:
        for seg in _wrap(raw, w - 6):
            lines.append("  │ " + seg + " " * max(0, w - _dw(seg) - 5) + "│")
    lines.append("  ╰" + "─" * max(0, w - 4) + "╯")
    return "\n".join(lines)


def _tokens(para: str) -> list[str]:
    """按空格切词, 但**反引号里的内容不拆**（`project show` 要整块走, 不然框里看着像坏了）。"""
    out: list[str] = []
    cur, in_tick = "", False
    for ch in para:
        if ch == "`":
            in_tick = not in_tick
            cur += ch
        elif ch == " " and not in_tick:
            if cur:
                out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out or [""]


def _wrap(s: str, width: int) -> list[str]:
    """按**显示宽度**折行（中文算 2）; **优先在空格处断** —— 命令名/英文词不再被拆开。"""
    out: list[str] = []
    for para in (str(s) or "").splitlines() or [""]:
        cur = ""
        for word in _tokens(para):
            cand = word if not cur else cur + " " + word
            if _dw(cand) <= width:
                cur = cand
                continue
            if cur:
                out.append(cur)
                cur = ""
            # 单"词"就超宽（长中文句 / 长 URL）⇒ 按显示宽度硬折
            piece = ""
            for ch in word:
                if _dw(piece + ch) > width:
                    out.append(piece)
                    piece = ch
                else:
                    piece += ch
            cur = piece
        out.append(cur)
    return out or [""]


def process_line(cmd: str, seconds: float | None = None, *, n: int = 1) -> str:
    """Hermes 风格的过程行: `┊ 💻 $ <命令>  <耗时>`。"""
    tail = []
    if n > 1:
        tail.append(f"+{n - 1} commands")
    if seconds is not None:
        tail.append(f"{seconds:.1f}s")
    return "  ┊ 💻 $ " + cmd + ("  " + "  ".join(tail) if tail else "")


def _top_commands() -> set[str]:
    """全部顶层命令名（从解析器里读, 不写死 —— 命令表变了它跟着变）。"""
    try:
        from apps.cli.main import build_parser

        for a in build_parser()._actions:
            if hasattr(a, "choices") and isinstance(a.choices, dict) and "status" in a.choices:
                return {str(k) for k in a.choices}
    except Exception:  # noqa: BLE001 — 读不到就不预校验（照旧交给 argparse）
        pass
    return set()


def run_shell(root: Path | str, *, banner: bool = True) -> int:
    """★ 启动 AI Factory OS —— 进入交互式 CLI（Founder: "我要的是启动 factory os, 使用 cli 命令"）。

    和"敲一条命令做一件事"的区别: 这里是**进去**, 然后在里面**连续敲**命令, 直到 exit/q/Ctrl-D。
    行为:
      · 提示符 `factory> `; 任意命令直接执行（与外面 `factory …` 完全同一套, 结果一致）
      · 支持 ↑↓ 历史（readline, 历史存 <root>/.cli_history）· Tab 不做补全（没实现就不假装）
      · `help`/`h`/`?` ⇒ 中文帮助中心 · `exit`/`quit`/`q`/Ctrl-D ⇒ 离开 · 空行忽略
      · Ctrl-C ⇒ 只取消当前这一行, **不退出**
      · `--root` 从启动这里继承（每条命令自动带上, 不会中途换数据目录）
    非终端输入（管道/脚本）⇒ 逐行读, EOF 结束（可测、不挂）。
    """

    from apps.cli.context import FactoryContext

    ctx = FactoryContext(root)
    ctx.ensure_dirs()
    _hist = ""
    try:
        import readline

        hp = Path(ctx.root) / ".cli_history"
        if hp.exists():
            readline.read_history_file(str(hp))
        readline.set_history_length(500)
        _hist = str(hp)
    except Exception:  # noqa: BLE001 — 历史是"锦上添花", 没有 readline 也能用
        pass

    if banner:
        print(render_welcome(ctx.root))
        # ★ 亮出"当前用什么模型"（Hermes 那样）—— 读真值, 读不到就留空
        try:
            from apps.cli.domains.chat import _provider as _p, provider_info as _pi

            _info = _pi(_p()) if _p() is not None else {}
            _zh = {"model": "模型", "provider": "供应商"}
            _mline = " · ".join(f"{_zh.get(k, k)} {v}" for k, v in _info.items() if v)
        except Exception:  # noqa: BLE001 — 拿不到就不显示
            _mline = ""
        print("  ★ 已进入交互式 CLI —— 直接说人话 = 会话; `/命令` = 执行命令（例: /status）; exit 离开")
        if _mline:
            print(f"     当前: {_mline}")
        print("     help 帮助中心 · 会话里只会自动跑**只读**命令, 会改数据的只念给你确认")
        print()

    _conv_id = ""
    _chat_hist: list[dict[str, str]] = []
    _pending_cmd = ""            # ★ 待你点头的命令（会话里它念出来的写命令）
    # ★ F2 多轮上下文持久化（跨重启还记得）: 启动时接上**最近一次会话**的最后几条消息。
    try:
        import json as _json

        for _f in sorted((Path(ctx.root) / "projects").glob("*/conversations/*.json"),
                         key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
            try:
                _d = _json.loads(_f.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 — 坏文件跳过（继续找下一个）
                continue
            _msgs = [m for m in (_d.get("messages") or [])
                     if str(m.get("role")) in ("human", "assistant", "ai")][-6:]
            if not _msgs:
                continue
            _conv_id = str(_d.get("id") or _f.stem)
            _chat_hist = [{"role": ("assistant" if str(m.get("role")) == "ai" else str(m.get("role"))),
                           "content": str(m.get("content"))[:1500]} for m in _msgs]
            print(f"  （接着上次的会话 {_conv_id} · 已载入 {len(_chat_hist)} 条上下文;"
                  f" 想从零开始就说「新会话」）")
            break
    except Exception:  # noqa: BLE001 — 载入失败就正常开新会话
        pass
    while True:
        try:
            line = input("factory> ").strip()
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print("  （Ctrl-C: 当前行取消, 没退出; 要离开输入 exit）")
            continue
        if not line:
            continue
        # ★ 2026-09-21（Founder 选 A）: 有挂起的命令 ⇒ 先看这一句是不是"点头/摇头"
        if _pending_cmd:
            from apps.cli.domains.chat import approval as _appr, to_argv as _toargv

            _yes = _appr(line)
            if _yes is True:
                _argv = _toargv(_pending_cmd)
                print(f"  ▶ 执行: factory {' '.join(_argv)}")
                _pending_cmd = ""
                try:
                    from apps.cli.main import main as _m3

                    _m3(["--root", str(ctx.root), *_argv])
                except SystemExit:
                    pass
                except Exception as exc:  # noqa: BLE001 — 一条命令炸了不带走 shell
                    print(f"  ⚠ 出错: {type(exc).__name__}: {str(exc)[:120]}")
                continue
            if _yes is False:
                print("  （已取消那条命令, 没执行）")
                _pending_cmd = ""
                continue
            print("  （那条挂起的命令我先搁着; 你这句话按普通消息处理）")
            _pending_cmd = ""
        low = line.lower()
        if low in ("exit", "quit", "q", ":q", "/exit", "/quit", "/q"):
            break
        if low in ("help", "h", "?", "/help", "/h", "/?"):
            print(render_help(""))
            continue
        if low in ("新会话", "new", "new session", "/new"):
            _conv_id, _chat_hist = "", []
            print("  （已开新会话: 上下文清空, 后面说的从零开始记）")
            continue
        if low in ("clear", "cls", "/clear", "/cls"):
            print("\033[2J\033[H", end="")     # ANSI 清屏（Founder 在会话里敲过 clear）
            continue
        if low in ("welcome", "menu", "/welcome", "/menu"):
            print(render_welcome(ctx.root))
            continue
        # ★ 2026-09-21（Founder: "我要在 cli 中可以使用会话功能, 并且可以使用 / 使用命令, 像 Hermes 一样"）:
        #   `/xxx` ⇒ 命令; 裸词且是已知命令 ⇒ 也当命令（向后兼容）; **其它任何一句话 ⇒ 会话**（LLM + 本平台数据）。
        if line.startswith("/"):
            line = line[1:].strip()
            if not line:
                continue
        _cmds = _top_commands()
        _is_cmd = bool(_cmds) and line.split()[0] in _cmds
        if not _is_cmd and (_cmds or line.startswith("/")):
            # ── 会话路径
            from apps.cli.domains import chat as _chat

            def _on_progress(cmd: str, seconds: float) -> None:
                print(process_line(cmd, seconds))

            def _run_capture(argv: list[str]) -> str:
                import contextlib as _c
                import io as _io

                buf = _io.StringIO()
                try:
                    with _c.redirect_stdout(buf):
                        from apps.cli.main import main as _m2

                        _m2(["--root", str(ctx.root), *[str(a) for a in argv]])
                except SystemExit:
                    pass
                return buf.getvalue().strip() or "（无输出）"

            import time as _t3

            _t0 = _t3.monotonic()
            print(box("你", line))
            _ans, _conv, _meta = _chat.chat_turn(ctx.root, line, conv_id=_conv_id, history=_chat_hist,
                                                 on_run=_run_capture, on_progress=_on_progress)
            _conv_id = _conv
            _chat_hist += [{"role": "human", "content": line}, {"role": "assistant", "content": _ans}]
            # ★ 2026-09-21（Founder: "Hermes 的有分界线、有模型、有成本"）: 每回合都亮出这轮的实情
            print()
            # Hermes 风格: 标题里带这轮的模型/用量/成本/用时（真值）
            _u = _meta.get("usage") or {}
            _bits = [f"⚕ AI Factory OS · {_meta.get('model') or '?'}"]
            if _u.get("prompt_tokens") is not None:
                _bits.append(f"tokens {_u.get('prompt_tokens')}↑/{_u.get('completion_tokens')}↓")
            if _u.get("estimated_cost_usd") is not None:
                _bits.append(f"${float(_u['estimated_cost_usd']):.6f}")
            _bits.append(f"{_t3.monotonic() - _t0:.1f}s")
            print(box(" · ".join(_bits), _ans or "（没答上来; 换句话再说一次?）"))
            # ★ 它念了写命令 ⇒ 明确问一句（并显示**精确**命令, 让你看清要跑什么）
            _pend = list(_meta.get("pending") or [])
            if _pend:
                _pending_cmd = str(_pend[0])
                print()
                print(box("⏸ 待你点头", f"factory {_pending_cmd}\n回「好」我就跑; 回「不」就取消"
                                          f"（也可以自己敲 /命令 直接跑）"))
            continue
        argv = line.split()
        # 敲错命令 ⇒ 一句短提示（不再是 argparse 整屏 usage + 长报错 ✗）
        if _cmds and argv and argv[0] not in _cmds:
            print(f"  （没有这个命令: {argv[0]} —— 输入 help 看命令表, 或 <命令> -h 查用法;"
                  f" 想聊天就直接说人话）")
            continue
        from apps.cli.main import main as _main  # 局部导入: 避免模块环

        try:
            _main(["--root", str(ctx.root), *argv])
        except SystemExit as exc:          # 命令自己退出(如 --help) ⇒ 留在 shell 里
            if exc.code not in (0, None):
                print(f"  （命令退出码 {exc.code}）")
        except KeyboardInterrupt:
            print("  （已取消）")
        except Exception as exc:  # noqa: BLE001 — 一条命令炸了不该把 shell 带走
            print(f"  ⚠ 这条命令出错: {type(exc).__name__}: {str(exc)[:120]}")
    if _hist:
        try:
            import readline

            readline.write_history_file(_hist)
        except Exception:  # noqa: BLE001
            pass
    print("  已退出 AI Factory OS。")
    return 0


def render_help(role: str) -> str:
    """中文帮助中心（按角色; 命令全部真实存在）。"""
    want = str(role or "").strip()
    roles = [want] if want in _ROLE_GUIDE else list(_ROLE_GUIDE)
    lines = ["", "  ╔═ " + _pad("帮助中心（中文）", 58) + "╗"]
    for r in roles:
        lines.append("  ║ " + _pad(f"【{r}】", 59) + "║")
        for cmd, desc in _ROLE_GUIDE[r]:
            lines.append(f"      {cmd}")
            lines.append(f"        ↳ {desc}")
    lines += [
        "  ╚" + "═" * 60 + "╝",
        "  完整命令表: factory --help（按字母列全部顶层命令）· 任何命令加 -h 看用法",
        "",
    ]
    return "\n".join(lines)
