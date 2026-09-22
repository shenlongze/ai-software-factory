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

import json
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
    """显示宽度（委托 apps.cli.textwidth —— 只留一套 ✗ 不再各写一份）。"""
    from apps.cli.textwidth import display_width

    return display_width(s)


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
    from apps.cli.theme import paint as _paint   # ★ banner 上色（Hermes 的 banner_border/title 同位 ✓）
    _bc, _bt = _paint("banner_border", "─" * 62), _paint("banner_title", _pad(f"AI Factory OS  v{_version()}", 60))
    lines = [
        "",
        "  " + _paint("banner_border", "╭") + _bc + _paint("banner_border", "╮"),
        "  " + _paint("banner_border", "│") + "  " + _bt + _paint("banner_border", "│"),
        "  " + _paint("banner_border", "╰") + _bc + _paint("banner_border", "╯"),
        f"  你的数据（{root}）:",
        f"    项目 {d['projects']} · 任务树 {d['trees']} · 叶 {d['done']}/{d['leaves']} 完成 · 经验 {d['exp']} 条",
        "",
        # ★ 2026-09-21 首屏压短（Founder: "没有真正明白我的意图" —— 入口是**会话**, 菜单只是快捷）:
        #   一句话讲清怎么用 + 一行快捷编号; 不再一大块提示占屏。
        # ★ 2026-09-21 首屏再砍（Founder: "无效信息太多了"）⇒ 只留: 版本 · 数据 · 怎么用 · 命令怎么敲
        "  直接说人话就行; 命令名开头就直接跑（例: status / project list）",
        "  会改数据的只念给你, 你点头才跑 · h 帮助 · exit 离开",
        "  命令: 直接敲（status / project list）; 打 / 再回车=命令表, 打 / 后按 TAB=补全",
    ]
    # （旧的 6 行菜单已并入上面那行「快捷编号」—— 入口是会话, 菜单只是快捷 ✓）
    lines += [
        "",
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


def _use_box() -> bool:
    """助手回复要不要套框（照 Hermes 的样子, 见 ~/.hermes/hermes-agent/hermes_cli/skin_engine.py:
    response_border + 工具行前缀 `┊`）。

    规则: 终端里 ⇒ **套**（Hermes 风格）; 非终端（管道/脚本/CI）⇒ 不套（输出干净、可断言 ✓）;
    `FACTORY_UI=plain` 或 `NO_COLOR` ⇒ 不套。
    """
    import os as _os
    import sys as _sys

    if str(_os.environ.get("FACTORY_UI", "")).strip().lower() == "plain":
        return False
    if _os.environ.get("NO_COLOR") is not None:
        return False
    return bool(getattr(_sys.stdout, "isatty", lambda: False)())


def _border_color() -> str:
    """回复框的边框色 —— 走 apps.cli.theme 的 `response_border`（与 Hermes 元素同位 ✓）。"""
    from apps.cli.theme import PALETTE, _hex_rgb, color_enabled

    if not color_enabled():
        return ""
    r, g, b = _hex_rgb(PALETTE["response_border"])
    return f"\033[38;2;{r};{g};{b}m"


def _color_off() -> str:
    import os as _os
    import sys as _sys

    if _os.environ.get("NO_COLOR") is not None or not getattr(_sys.stdout, "isatty", lambda: False)():
        return ""
    return "\033[0m"


def _reflow(text: str) -> list[str]:
    """把模型自己硬换的行**接回段落**（Founder 实测: 框里右边缘像狗牙 ✗）。

    规则: 一行不以句末标点结尾、且下一行不是新段落/列表/标题 ⇒ 接上（中文不靠空格断行, 必须接 ✓）。
    """
    out: list[str] = []
    for raw in (text or "").splitlines():
        s = raw.rstrip()
        _is_new = (not s) or s.lstrip()[:1] in ("-", "*", "·", "#", ">") or s.lstrip()[:2] in ("1.", "2.", "3.")
        if out and out[-1].strip() and s.strip() and not _is_new and out[-1].rstrip()[-1:] not in "。！？.!?:：;；)）」":
            out[-1] = out[-1].rstrip() + (" " if out[-1].rstrip()[-1:].isascii() and s[:1].isascii() else "") + s.lstrip()
        else:
            out.append(s)
    return out


def box(title: str, text: str, *, width: int = 0) -> str:
    """回答区（照 Founder 的意思: **左右边框去掉** —— 只留上下两条线 + 内容缩进 ✓）。

    · 顶: `  ╭─ ⚕ AI Factory OS ──…──`  （标题在顶部线上, 就像 Hermes ✓）
    · 内容: 缩进 6 格, 先**重排段落**（把模型硬换的行接回去 ✓）再按宽度折行
    · 底: `  ╰──…──`（通栏; 与顶线同宽 ✓）
    """
    w = width or min(_term_width(), 96)
    head = f"  ╭─ {title} "
    lines = [head + "─" * max(0, w - _dw(head))]
    for raw in _reflow(text):
        for seg in _wrap(raw, w - 6) if raw.strip() else [""]:
            lines.append(("      " + seg).rstrip() if seg else "")
    lines.append("  ╰" + "─" * max(0, w - 3))
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


#: 斜杠"会话命令"（照 Hermes: /help /new /stop /retry /cost /model /tools …）
SESSION_COMMANDS: dict[str, str] = {
    "/help": "列出所有会话命令（就是这份表）",
    "/new": "开新会话（上下文清空）",
    "/sessions": "列出历史会话（可直接 /resume <编号> 接着聊）",
    "/resume": "接着某个历史会话: /resume <编号>",
    "/retry": "重发上一句（重试一轮）",
    "/stop": "中断当前这一轮（会话保留）",
    "/cost": "本次会话累计 tokens / 估算成本 / 轮数",
    "/model": "当前供应商与模型",
    "/tools": "它都能跑哪些命令（只读自动 / 写要你点头）",
    "/clear": "清屏",
    "/commands": "常用命令总表（表格: 命令 / 作用 / 是否改数据）",
    "/colors": "色板预览（每个界面元素上一遍色, 指着说哪不对）",
    "/project": "会话归属哪个项目: /project <名字|id|片段>（不带参数=看当前+候选）",
}


def _busy(label: str, *, tty: bool) -> str:
    """忙指示（Hermes 有 "preparing terminal…"）—— 只在终端里画, 非终端不污染输出。"""
    return f"  ⏳ {label}…" if tty else ""


def _busy_clear(tty: bool) -> str:
    return "\r" + " " * 60 + "\r" if tty else ""


def _ask_permission(cmd: str, *, tty: bool, always: set[str]) -> str:
    """权限三档（Hermes 的 permission prompt）: 允许一次 / 总是 / 拒绝。返回 "once"/"always"/"deny"。

    `always` = 本次会话里"总是允许"过的命令（**不落盘** —— 重启即忘, 安全默认）。
    """
    key = str(cmd).split()[1] if len(str(cmd).split()) > 1 else str(cmd)
    if key in always:
        print(f"  ✓ 已记住「总是允许 {key}」（本会话）: {cmd}")
        return "always"
    if not tty:
        print(f"  ⏸ 需要你点头（非终端 ⇒ 不跑）: {cmd}")
        return "deny"
    print(f"  ⏸ 这条会改数据: {cmd}")
    print("     1) 允许这一次   2) 本会话总是允许   3) 拒绝")
    try:
        ans = input("     选 1/2/3（回车=拒绝）: ").strip()
    except (EOFError, KeyboardInterrupt):
        return "deny"
    if ans == "2":
        always.add(key)
        print(f"     ✓ 记住了: 本会话内 {key} 不再问")
        return "always"
    return "once" if ans == "1" else "deny"


def _rule_line() -> str:
    """通栏横线（分区用; 照 Hermes 的输入区上下边框）。"""
    from apps.cli.theme import paint

    return paint("input_rule", "  " + "─" * max(40, min(_term_width(), 96) - 2))


def status_bar(meta: dict) -> str:
    """回答区之后的状态栏（照 Hermes 底部: 模型 │ 用量 │ 成本 │ 耗时 │ 查了几次）。"""
    bits: list[str] = []
    if meta.get("model"):
        bits.append(str(meta["model"]))
    _pt, _ct = meta.get("prompt_tokens"), meta.get("completion_tokens")
    if _pt or _ct:
        bits.append(f"↑{_pt or 0} ↓{_ct or 0}")
    if meta.get("cost") is not None:
        bits.append(f"${float(meta['cost']):.6f}")
    if meta.get("seconds") is not None:
        bits.append(f"{float(meta['seconds']):.1f}s")
    if meta.get("tool_calls"):
        bits.append(f"查了 {meta['tool_calls']} 次")
    return "  ⚕ " + " │ ".join(bits) if bits else ""


def _rule_panel(title: str, lines: list[str], options: list[str]) -> None:
    """只**画**审批面板（不读键盘）—— 用于"下一行输入决定"的那种流程 ✓。"""
    from apps.cli.theme import paint

    w = min(_term_width(), 92)
    head = f"  ╭─ {title} "
    print()
    print(paint("warn", head) + paint("warn", "─" * max(0, w - _dw(head) - 1)) + paint("warn", "╮"))
    for ln in lines:
        print(paint("warn", "  │ ") + ln)
    print(paint("warn", "  │"))
    for i, opt in enumerate(options):
        print(paint("warn", "  │ ") + f"  {i + 1}  {opt}")
    print(paint("warn", "  ╰" + "─" * max(0, w - 4) + "╯"))


def ask_choice(title: str, lines: list[str], options: list[str], *, default: int = 0) -> int:
    """审批面板（照 Hermes 的 `⚠️ Dangerous Command` 框）—— 醒目 + 逐行选项 + **按数字即生效**。

    ★ Founder 实测三点: ① 选项不能挤一行 ② 要醒目 ③ 要快捷（按 1/2/3 直接出结果, 不用回车 ✗）
    返回选项下标（0 起）; 非终端 / Esc / q ⇒ 返回 default（默认为 0 = 最保守的那个）。
    """
    from apps.cli.theme import paint

    w = min(_term_width(), 92)
    head = f"  ╭─ {title} "
    print()
    print(paint("warn", head) + paint("warn", "─" * max(0, w - _dw(head) - 1)) + paint("warn", "╮"))
    for ln in lines:
        print(paint("warn", "  │ ") + ln)
    print(paint("warn", "  │"))
    for i, opt in enumerate(options):
        print(paint("warn", "  │ ") + f"  {i + 1}  {opt}")
    print(paint("warn", "  ╰" + "─" * max(0, w - 4) + "╯"))
    _is_tty = bool(getattr(sys.stdin, "isatty", lambda: False)() and getattr(sys.stdout, "isatty", lambda: False)())
    if not _is_tty:
        return default
    print(f"  按键选择（1-{len(options)}; Esc/q = 拒绝）: ", end="", flush=True)
    try:
        import termios
        import tty as _tty_mod

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            _tty_mod.setcbreak(fd)          # ★ 单键: 不用回车 ✓
            while True:
                ch = sys.stdin.read(1)
                if ch in ("\x03", "\x1b", "q", "Q"):
                    print("拒绝")
                    return default
                if ch.isdigit() and 1 <= int(ch) <= len(options):
                    print(str(ch))
                    return int(ch) - 1
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:  # noqa: BLE001 — 没有 termios（非 POSIX）就退回按行输入
        try:
            _s = input().strip()
        except (EOFError, KeyboardInterrupt):
            return default
        return (int(_s) - 1) if _s.isdigit() and 1 <= int(_s) <= len(options) else default


def _make_session(root: Path | str):
    """用 **prompt_toolkit** 做输入（照 Hermes: 它的 REPL 就是 prompt_toolkit）。

    ⇒ 拿到它自带能力: **边打边弹补全菜单**（打进 `/` 立刻列出命令 ✓）、历史、方向键、样式。
    """
    from prompt_toolkit import PromptSession
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.styles import Style

    class _CmdCompleter(Completer):
        def get_completions(self, document, _event):
            text = document.text_before_cursor
            if not text.startswith("/"):
                return
            for name, desc in _menu_for(text):
                yield Completion(name, start_position=-len(text), display_meta=desc)

    return PromptSession(
        completer=_CmdCompleter(),
        complete_while_typing=True,        # ★ 一打 "/" 就出候选（不用 TAB、不用回车 ✓）
        history=FileHistory(str(Path(root) / ".cli_history")),
        auto_suggest=AutoSuggestFromHistory(),
        style=Style.from_dict({"prompt": "#FFD700", "completion-menu.completion": "bg:#1a1a2e #FFF8DC",
                               "completion-menu.completion.current": "bg:#333355 #FFD700",
                               "completion-menu.meta.completion": "bg:#1a1a2e #B8860B"}),
    )


def _read_input(prompt: str, *, root: Path | str) -> str:
    """读一行: 终端 ⇒ prompt_toolkit（边打边提示 ✓）; 非终端/缺库 ⇒ input()（脚本照旧 ✓）。"""
    if not (getattr(sys.stdin, "isatty", lambda: False)() and getattr(sys.stdout, "isatty", lambda: False)()):
        return input(prompt)
    try:
        global _SESSION
        if _SESSION is None:
            _SESSION = _make_session(root)
        return _SESSION.prompt(prompt)
    except Exception:  # noqa: BLE001 — 兜底: 不让输入层把会话搞崩 ✗
        return input(prompt)


_SESSION = None


def _menu_for(prefix: str) -> list[tuple[str, str]]:
    """`/` 提示的候选（会话命令 + factory 命令, 都带 / 前缀 ✓）—— 边打边过滤 ✓。"""
    items: list[tuple[str, str]] = []
    for name, desc in SESSION_COMMANDS.items():
        items.append((name, desc))
    for c in sorted(_top_commands()):
        if "/" + c not in SESSION_COMMANDS:
            items.append(("/" + c, "factory 命令（也可不带 / 直接敲）"))
    pfx = str(prefix or "").lower()
    return [(n, d) for n, d in items if n.lower().startswith(pfx)]


def _project_candidates(root: Path | str) -> list[tuple[str, str, str]]:
    """可归属的项目候选：(名字, id, 说明) —— 权威源 = org 项目库（与 status/project list 同源 ✓）。"""
    out: list[tuple[str, str, str]] = []
    try:
        from ai_factory_os.services.organization.projects import ProjectStore

        from apps.cli.commands import _project_notes

        _rows = ProjectStore(Path(root) / "org").list_projects() or []
        _notes = _project_notes(root, list(_rows)) or {}
        for _r in _rows:
            _id = str(getattr(_r, "id", "") or "")
            out.append((str(getattr(_r, "name", "") or _id), _id, _notes.get(_id, "")))
    except Exception:  # noqa: BLE001 — 拿不到就没候选, 不编 ✗
        pass
    return out


def _install_completer() -> None:
    """装上 readline 补全: 打 `/` 后按 TAB 能补会话命令 + factory 命令名。

    ★ 2026-09-21（Founder: "Hermes 中有输入 / 后就有命令提示功能"）—— 抄它的可发现性:
      ① TAB 补全 `/xxx` ② 单独打一个 `/` 回车 ⇒ 直接出命令表（不用记）
    """
    try:
        import readline
    except Exception:  # noqa: BLE001 — 没有 readline 就算了（不影响用）
        return
    # ★ 两类都带 `/` 前缀一起补（factory 命令也支持 /status 写法 ✓ —— Founder: "factory 内命令不需要 /"?）
    names = sorted({*SESSION_COMMANDS, *("/" + c for c in _top_commands())})

    def _comp(text: str, state: int):
        buf = readline.get_line_buffer()
        if not buf.startswith("/"):
            return None
        opts = [n + " " for n in names if n.startswith(buf)]
        return opts[state] if state < len(opts) else None

    try:
        readline.set_completer(_comp)
        readline.parse_and_bind("tab: complete")
    except Exception:  # noqa: BLE001
        pass


#: 会话里三类信息各自的前缀（Founder: "没有像 codex/Hermes 的 cli 那样: 用户/系统/执行 都有区分"）
MARK_USER = "你 ▸"
MARK_SYS = "系统 ▸"
MARK_EXEC = "执行 ▸"
MARK_AI = "助手 ▸"


def tool_block(cmd: str, seconds: float | None, output: str, *, max_lines: int = 24) -> str:
    """工具执行 + 输出（★ 照 Hermes 的样子, 不用框、不用分隔线、不逐行加前缀）:

      ┊ 💻 $ factory project list  0.1s
          ID          Project      Status …
          ----------  -----------  ------
          P-019cc935  gym-coach    active

    Hermes 的清晰来自**少装饰**: 一行工具行 + 输出原样缩进; 实测我先前加的分隔线与逐行 `│` 更吵 ✗
    （Founder: "你自己看一下 Hermes 呈现的信息, 就比较清晰"）。
    """
    _c = str(cmd or "").strip()
    if _c.startswith("factory "):
        _c = _c[len("factory "):]
    from apps.cli.theme import dim as _dim

    head = _dim(f"  ┊ 💻 $ factory {_c}" + (f"   {seconds:.1f}s" if seconds is not None else ""))
    body = str(output or "").rstrip().splitlines() or ["（没有输出）"]
    _cap = 10 if len(body) > 40 else max_lines
    shown, out = body[:_cap], [head]
    out += ["      " + ln for ln in shown]          # 只缩进, 不逐行加 │ ✗
    if len(body) > len(shown):
        out.append(f"      …（还有 {len(body) - len(shown)} 行; 要看全的可用 /<命令> 自己跑）")
    return "\n".join(out)


def _looks_like_command(line: str, cmds: set[str]) -> bool:
    """这句话是不是"就是一条命令"（而不是在跟我说话）。

    跑命令: `project list` · `tasktree todo PLAN-x` · `status --json`
    走会话: `status 是什么意思?` · `我有哪些项目` · `帮我看看那棵树`
    判据: 首词命中命令名 + 全行**只有 ASCII 词/参数**（没有中文/问号/句号这些"说话的痕迹"）。
    """
    s = str(line or "").strip()
    if not s or not cmds:
        return False
    if s.split()[0] not in cmds:
        return False
    import re as _re

    return _re.fullmatch(r"[\x20-\x7E]+", s) is not None


def _code_fingerprint() -> str:
    """正在跑的这几个 CLI 模块的指纹（mtime+size）—— 用来发现"代码被改了但窗口还开着" ✗。"""
    try:
        parts = []
        for _rel in ("apps/cli/main.py", "apps/cli/domains/welcome.py", "apps/cli/domains/chat.py",
                     "apps/cli/markdown.py", "apps/cli/textwidth.py"):
            _f = Path(__file__).resolve().parents[3] / _rel
            if _f.exists():
                st = _f.stat()
                parts.append(f"{int(st.st_mtime)}:{st.st_size}")
        return "|".join(parts)
    except Exception:  # noqa: BLE001 — 拿不到就不提醒（不挡用）
        return ""


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
        if _mline:
            print(f"    模型: {_mline.replace('供应商 ', '').replace('模型 ', '')}")

    _conv_id = ""
    _chat_hist: list[dict[str, str]] = []
    _pending_cmd = ""            # ★ 待你点头的命令（会话里它念出来的写命令）
    # ★ CLI 精髓（照 Hermes）: 会话级状态 —— 累计用量 / 权限记忆 / 上一句（重试用）/ 是否终端
    _sel_project = ""           # ★ 会话归属项目（Founder 点单; `/project <名字|id>` 设置 ✓）
    _sess = {"cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "turns": 0}
    _always: set[str] = set()
    _last_input = ""
    _tty = bool(getattr(sys.stdin, "isatty", lambda: False)() and
                getattr(sys.stdout, "isatty", lambda: False)())
    _code_fp = _code_fingerprint()      # ★ 用来发现"窗口还跑着旧代码"（Founder 实测踩到 ✗）
    _install_completer()                # ★ TAB 补全 /命令（照 Hermes）
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
            print(f"  （接上次会话 {_conv_id} · {len(_chat_hist)} 条上下文; 从零开始说「新会话」）")
            break
    except Exception:  # noqa: BLE001 — 载入失败就正常开新会话
        pass
    while True:
        try:
            # ★ Founder: "输入框需要 加分割线 factory>" ⇒ 提示符**上方**一条横线（照 Hermes: ─── / ❯ / ───）
            print(_rule_line())
            line = _read_input("factory> ", root=root).strip()
            # ★ 多行输入（照 Hermes 手感）: 行尾反斜杠 ⇒ 续行（贴长需求不用拆）
            while line.endswith("\\"):
                try:
                    line = line[:-1] + " " + input("   ... ").strip()
                except (EOFError, KeyboardInterrupt):
                    break
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

            # ★ 权限三档（照 Hermes）: 1/好=允许一次 · 2=本会话总是允许 · 3/不=拒绝
            if line.strip() == "2":
                _always.add(_pending_cmd.split()[0] if _pending_cmd.split() else _pending_cmd)
                print(f"  ✓ 记住了: 本会话内 {_pending_cmd.split()[0] if _pending_cmd.split() else _pending_cmd} 不再问")
                _yes = True
            elif line.strip() == "1":
                _yes = True
            elif line.strip() == "3":
                _yes = False
            elif _pending_cmd.split() and _pending_cmd.split()[0] in _always:
                print(f"  ✓ 之前已记住「总是允许 {_pending_cmd.split()[0]}」（本会话）")
                _yes = True
            else:
                _yes = _appr(line)
            if _yes is True:
                _argv = _toargv(_pending_cmd)
                _pending_cmd = ""
                # ★ Founder: "最后的好像没有执行动作" —— 其实是**执行了却零反馈** ✗
                #   （那棵树真从 13 叶变成 199 叶 ✓）⇒ 现在抓输出 + 打块 + 明确结果行。
                import contextlib as _c9
                import io as _io9
                import time as _t9

                _buf9 = _io9.StringIO()
                _rc9, _t09 = 0, _t9.monotonic()
                try:
                    with _c9.redirect_stdout(_buf9):
                        from apps.cli.main import main as _m3

                        _m3(["--root", str(ctx.root), *_argv])
                except SystemExit as _se9:
                    _rc9 = int(getattr(_se9, "code", 0) or 0)
                except Exception as exc:  # noqa: BLE001 — 一条命令炸了不带走 shell
                    _rc9 = 1
                    print(f"  ⚠ 出错: {type(exc).__name__}: {str(exc)[:120]}")
                _out9 = _buf9.getvalue().rstrip()
                print()
                print(tool_block(" ".join(_argv), _t9.monotonic() - _t09, _out9))
                # ★ 2026-09-21 修假成功（Founder 实测: `create project … --repo-path /你的路径` 报错
                #   "repo path is not a directory" 却打「✔ 执行完成」✗）⇒ 输出里有错字样就当失败
                _err9 = any(_k in _out9 for _k in ("error:", "Error:", "Traceback",
                                                   "not a directory", "不存在", "失败"))
                _ok9 = (_rc9 == 0) and not _err9
                print(f"  {MARK_SYS} {'✔' if _ok9 else '⚠'} "
                      + ("执行完成（改动已落盘）" if _ok9 else
                         f"执行**没成功**（{'退出码 ' + str(_rc9) if _rc9 else '命令报错'}）—— 上面那条错信息就是原因"))
                print()
                continue
            if _yes is False:
                print(f"  {MARK_SYS} 已取消, 没执行")
                _pending_cmd = ""
                continue
            print("  （那条挂起的命令我先搁着; 你这句话按普通消息处理）")
            _pending_cmd = ""
        # ★ 2026-09-21（Founder 实测: 会话跑着旧代码 ⇒ "改了怎么还是老样子" ✗）:
        #   每轮看一眼"脚下的代码"变没变（CLI 几个模块的 mtime+大小）⇒ 变了就提醒重开。
        _fp = _code_fingerprint()
        if _code_fp and _fp != _code_fp:
            print(f"  {MARK_SYS} ⚠ 代码已更新（这个窗口还跑着旧代码）⇒ 建议: 输 exit 再 `factory start`")
            _code_fp = _fp
        low = line.lower()
        # ★ 三态区分（Founder: "没有像 codex/Hermes 的 cli 那样: 用户/系统/执行 都有区分"）
        #   `你 ▸` = 你说的话;  `执行 ▸` = 它跑了什么;  `系统 ▸` = 平台提示;  `⚕` = 助手回答
        if line and line.strip().lower() not in ("exit", "quit", "q", ":q", "/exit", "/quit", "/q"):
            # ★ 照 Hermes 的**用户区**（Founder 给实物对过: 横线 + `● 你的话` + 横线）:
            #   一行横线 · `● <老板原话>` · 一行横线 —— 这样历史里看得见"谁说了什么" ✓
            from apps.cli.theme import paint as _paint

            print("  " + _paint("user_mark", "●") + " " + line)
        if low in ("exit", "quit", "q", ":q", "/exit", "/quit", "/q"):
            break
        if low in ("help", "h", "?", "/h", "/?"):
            print(render_help(""))
            continue
        from apps.cli.domains import chat as _chat0

        if line.strip() == "/":        # ★ 打一个 "/" 回车 ⇒ 出命令表（照 Hermes 的可发现性）
            low = "/help"
        if low in ("/help", "-h", "--help", "-help", "?"):   # ★ 裸 -h 也算求助（Founder 敲过 ✗）
            from apps.cli.main import _render_table as _rt

            _rows = [[_k, _v, "—"] for _k, _v in SESSION_COMMANDS.items()]
            print("  会话命令（斜杠开头）")
            print(_rt(["命令", "作用", "改数据"], _rows))
            print("  常用 command 总表: 输 /commands")
            continue
        if low in ("/commands", "-c", "--commands"):
            from apps.cli.main import _render_table as _rt2

            _rows2 = [
                ["/status", "工厂总览（项目/任务树/叶/事件/舰队）", "—"],
                ["/project list", "项目清单（带 ID）", "—"],
                ["/tasktree todo <PLAN 或 项目名>", "看一棵树的逐叶清单与进度", "—"],
                ["/console dashboard", "七域看板", "—"],
                ["/metrics", "指标（执行/工作流/验证/失败原因）", "—"],
                ["/intelligence experience list", "经验库（学习自治攒的）", "—"],
                ["/backup create", "备份数据目录", "★"],
                ["/chain 「我要做…」 --project P-x", "提需求: 需求→PRD→设计→任务树", "★"],
                ["/tasktree confirm <PLAN>", "确认一棵树（确认后才允许执行）", "★"],
                ["/run --plan <PLAN> --project P-x --limit 3", "派活 + 真执行（会在仓库写码提交）", "★"],
                ["/recover --plan <PLAN>", "中断恢复（把卡住的叶交回）", "★"],
            ]
            print("  常用命令（带 / 执行; 不带 / 就是跟我说人话）")
            print(_rt2(["命令", "作用", "改数据"], _rows2))
            continue
        if low == "/project" or low.startswith("/project "):
            # ★ 2026-09-22（Founder 点单: "会话归属哪个项目"）
            _arg = line.strip()[len("/project"):].strip()
            _cands = _project_candidates(root)
            if not _arg:
                _cur = f"当前归属: {_sel_project}" if _sel_project else "当前: **没有指定**（我会按全局数据回答）"
                print(f"  {MARK_SYS} {_cur}")
                print("  可选的（说 /project <名字|id|片段> 就锁到它）:")
                for _n, _i, _note in _cands[:10]:
                    print(f"     {_i}  {_n}" + (f"   {_note[:34]}" if _note else ""))
                print("      /project 清空   ⇒ 取消归属（回到全局）")
                continue
            if _arg.lower() in ("清空", "none", "clear", "-"):
                _sel_project = ""
                print(f"  {MARK_SYS} 已取消归属（回到全局数据 ✓）")
                continue
            _hit = [c for c in _cands if _arg.lower() in (c[1] or "").lower()
                    or _arg.lower() in (c[0] or "").lower() or (c[0] or "").lower().startswith(_arg.lower())]
            if not _hit:
                print(f"  {MARK_SYS} 没找到「{_arg}」—— 打 /project 看候选（名字/id/片段都认 ✓）")
                continue
            _sel_project = f"{_hit[0][0]}（{_hit[0][1]}）"
            print(f"  {MARK_SYS} 会话已归属: {_sel_project} —— 之后默认按它回答/查它的数据 ✓")
            continue
        if low in ("/colors", "/theme"):
            from apps.cli.theme import PALETTE, color_enabled, paint

            print(f"  色板（{'终端: 已上色' if color_enabled() else '非终端/NO_COLOR: 不上色'}）")
            for _el, _hex in PALETTE.items():
                print("   " + paint(_el, f"  {_el:<16} {_hex}  ████ 示例文字  ").rstrip())
            print("   想调哪个就说元素名（例: 工具行再深一点）")
            continue
        if low in ("/new", "/clear", "/cost", "/model", "/tools", "/stop", "/retry", "/sessions"):
            if low == "/clear":
                print("\033[2J\033[H", end="")
            elif low == "/new":
                _conv_id, _chat_hist = "", []
                print(f"  {MARK_SYS} 已开新会话（上下文清空）")
            elif low == "/cost":
                print(f"  本次会话: {_sess['turns']} 轮 · tokens ↑{_sess['prompt_tokens']} / "
                      f"↓{_sess['completion_tokens']} · 估算成本 ${_sess['cost']:.6f}")
            elif low == "/model":
                _pi = _chat0.provider_info(_chat0._provider()) if hasattr(_chat0, "provider_info") else {}
                print(f"  供应商 {_pi.get('provider') or '（未知）'} · 模型 {_pi.get('model') or '（未知）'}")
            elif low == "/tools":
                print("  只读（会话里自动跑）:")
                for _n in sorted(list(getattr(_chat0, "READONLY_PREFIXES", ()) or ())):
                    print(f"    {_n}")
                print("  会改数据的 ⇒ 一律先亮给你: 1)允许一次 2)本会话总是允许 3)拒绝")
            elif low == "/stop":
                print("  （进行中的一轮按 Ctrl-C 中断; 会话保留）")
            elif low == "/retry" and _last_input:
                line = _last_input
                print(f"  ↻ 重试上一句: {line[:60]}")
            elif low == "/retry":
                print("  （还没有可重试的一句）")
            else:  # /sessions
                _cs = sorted((Path(ctx.root) / "projects").glob("*/conversations/*.json"),
                             key=lambda q: q.stat().st_mtime, reverse=True)[:8]
                if not _cs:
                    print("  （还没有历史会话）")
                else:
                    print("  历史会话（按最近排序）:")
                    for _i, _f in enumerate(_cs, 1):
                        try:
                            _d = json.loads(_f.read_text(encoding="utf-8"))
                        except Exception:  # noqa: BLE001
                            _d = {}
                        print(f"    {_i}) {_d.get('id') or _f.stem}   "
                              f"{len(_d.get('messages') or [])} 条消息   {_f.parent.parent.name}")
                    print("  接着聊: /resume <编号>")
            if low != "/retry":
                continue
            if low == "/retry" and not _last_input:
                continue
        if low.startswith("/resume"):
            _cs = sorted((Path(ctx.root) / "projects").glob("*/conversations/*.json"),
                         key=lambda q: q.stat().st_mtime, reverse=True)[:8]
            _arg = line.split()[1] if len(line.split()) > 1 else ""
            if not _cs or not _arg.isdigit() or not (1 <= int(_arg) <= len(_cs)):
                print("  用法: /resume <编号>（先 /sessions 看编号）")
                continue
            _f = _cs[int(_arg) - 1]
            try:
                _d = json.loads(_f.read_text(encoding="utf-8"))
            except Exception as _e:  # noqa: BLE001 — 读不了就说, 不假装
                print(f"  ⚠ 读会话失败: {type(_e).__name__}")
                continue
            _conv_id = str(_d.get("id") or _f.stem)
            _msgs = [m for m in (_d.get("messages") or [])
                     if str(m.get("role")) in ("human", "assistant", "ai")][-8:]
            _chat_hist = [{"role": ("assistant" if str(m.get("role")) == "ai" else str(m.get("role"))),
                           "content": str(m.get("content"))[:1500]} for m in _msgs]
            print(f"  ✓ 已接着会话 {_conv_id}（载入 {len(_chat_hist)} 条上下文）")
            continue
        # ★ 2026-09-21 修（Founder 实测: 横幅写着"输入编号直接跑", 进来敲 `1` 却被当聊天 ✗）:
        #   会话里 1-6 / h 就是菜单项 —— 与首屏承诺一致。
        if low in ("1", "2", "3", "4", "5", "6", "h") and _MENU.get(low if low != "h" else "h"):
            if low == "h":
                print(render_help(""))
                continue
            _item = _MENU[str(low)]
            _argv2 = list(_item[1])
            if _argv2 and _argv2[0] in ("tasktree", "run", "chain"):
                _extra = input(f"  `factory {' '.join(_argv2)}` 还需要参数（可留空返回）: ").strip()
                if not _extra:
                    continue
                _argv2 += _extra.split()
            print(f"  ▶ 跑: factory {' '.join(_argv2)}")
            from apps.cli.main import main as _m4

            try:
                _m4(["--root", str(ctx.root), *_argv2])
            except SystemExit:
                pass
            except Exception as exc:  # noqa: BLE001
                print(f"  ⚠ 出错: {type(exc).__name__}: {str(exc)[:120]}")
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
        # ★ 2026-09-21（Founder: "factory的命令，不需要带 / 么，不对冲突么？" —— 会冲突 ✗）:
        #   规则**定死**: `/命令` 或 `factory 命令` ⇒ 执行命令; **其它一切都是会话**。
        #   （去掉"裸词恰好是命令名就当命令"的兼容 —— 那会把 "status 是什么意思?" 这种问句抢去当命令 ✗）
        _cmds = _top_commands()
        _is_cmd = False
        if line.startswith("/"):
            line = line[1:].strip()
            if not line:
                continue
            _is_cmd = True
        elif line.split() and line.split()[0] == "factory":
            line = " ".join(line.split()[1:]).strip()       # 明确打了 factory 前缀 ⇒ 要命令
            _is_cmd = bool(line)
            if not line:
                continue
        elif _looks_like_command(line, _cmds):
            # ★ 2026-09-21（Founder: "没有真正明白我的意图啊" —— 敲 `project list` 却绕一圈转述成人话 ✗）:
            #   首词是命令名 且 **整行就是那条命令** ⇒ 直接执行; 像句子/问题的才走会话 ✓
            _is_cmd = True
        if not _is_cmd:
            # ── 会话路径
            from apps.cli.domains import chat as _chat

            def _ask_sh(cmd: str) -> bool:
                """通用命令的审批（照 Hermes 的框: 一次 / 本会话总是 / 拒绝）—— 默认**拒绝**（非终端）。"""
                key = "sh:" + str(cmd).split()[0] if str(cmd).split() else "sh"
                if key in _always:
                    return True
                if not _tty:
                    return False
                _pick = ask_choice(
                    "⚠️  需要你确认（通用命令）",
                    ["这条不是 factory 自己的命令（可能联网 / 读文件 / 跑脚本）:",
                     "",
                     f"  命令: {cmd}"],
                    ["允许这一次", "本会话总是允许（这类不再问）", "拒绝"],
                    default=2)
                if _pick == 1:
                    _always.add(key)
                    print(f"  {MARK_SYS} 记住了: 本会话 {key} 不再问")
                    return True
                return _pick == 0

            def _on_output(cmd: str, text: str) -> None:
                """★ 工具输出**原样**给老板看 + 每块**带头行与分隔线**。

                两条 Founder 实测: ① "模型重画表格会把列画散 ✗"（所以直通）;
                ② "所有结果堆砌在一起, 看不清楚, 太乱" + "用户/系统/执行 要有区分" ⇒ 分块 ✓。
                """
                _t = str(text or "").rstrip()
                if not _t:
                    return
                print()
                print(tool_block(cmd, _last_exec.get("s"), _t))

            _last_exec = {"cmd": "", "s": None}

            def _on_progress(cmd: str, seconds: float) -> None:
                # ★ 只**记录**（打印交给 tool_block 的块头 —— 否则命令名/耗时会出现两次 ✗）
                _last_exec["cmd"], _last_exec["s"] = cmd, seconds
                if _first_proc[0] and _busy_txt:      # 忙指示那行先清掉（Founder: 别黏一起 ✗）
                    print(_busy_clear(_tty), end="")
                    _first_proc[0] = False

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
                _v = buf.getvalue().rstrip()      # ★ 只去尾部: 头行的前导空格是表格对齐的一部分 ✗
                return _v or "（无输出）"

            import time as _t3

            _t0 = _t3.monotonic()
            _busy_txt = _busy("正在查", tty=_tty)          # ★ 忙指示（不再黑屏干等）
            _first_proc = [True]                            # 过程行: 忙指示那行先清掉再打
            if _busy_txt:
                print(_busy_txt, end="", flush=True)
            try:
                _ans, _conv, _meta = _chat.chat_turn(ctx.root, line, conv_id=_conv_id,
                                                     history=_chat_hist, on_run=_run_capture,
                                                     on_progress=_on_progress, on_output=_on_output,
                                                     on_approval=_ask_sh, project=_sel_project)
            except KeyboardInterrupt:                      # ★ 可打断: 断的是**这一轮**, 会话还在
                print(_busy_clear(_tty) + "  （已中断这一轮; 会话还在 —— 接着说, 或输 /retry）")
                continue
            finally:
                if _busy_txt:
                    print(_busy_clear(_tty), end="")
            _last_input = line
            _u0 = (_meta or {}).get("usage") or {}
            _sess["turns"] += 1
            _sess["prompt_tokens"] += int(_u0.get("prompt_tokens") or 0)
            _sess["completion_tokens"] += int(_u0.get("completion_tokens") or 0)
            _sess["cost"] += float(_u0.get("estimated_cost_usd") or 0.0)
            _conv_id = _conv
            _chat_hist += [{"role": "human", "content": line}, {"role": "assistant", "content": _ans}]
            # ★ 2026-09-21（Founder: "Hermes 的有分界线、有模型、有成本"）: 每回合都亮出这轮的实情
            print()
            # Hermes 风格: 标题里带这轮的模型/用量/成本/用时（真值）
            _u = _meta.get("usage") or {}
            # ★ 照 Hermes 的分区: 输入区(横线夹住) · 执行区(┊ 💻) · **回答区**(框) · **状态栏**(底下那行)
            #   ⇒ 模型/用量/成本/耗时 **不再挤在框标题里**，改到底部状态栏 ✓
            _sb: list[str] = []
            if _sel_project:
                _sb.append(_sel_project)          # ★ 归属项目显示在状态栏（一眼看到在跟谁说话 ✓）
            if _meta.get("model"):
                _sb.append(str(_meta["model"]))
            if _u.get("prompt_tokens") is not None:
                _sb.append(f"↑{_u.get('prompt_tokens')} ↓{_u.get('completion_tokens')}")
            if _u.get("estimated_cost_usd") is not None:
                _sb.append(f"${float(_u['estimated_cost_usd']):.6f}")
            _sb.append(f"{_t3.monotonic() - _t0:.1f}s")
            _rounds = int(_meta.get("rounds") or 1)
            if _rounds > 1:
                _sb.append(f"查了 {_rounds - 1} 次")
            _head = "⚕ AI Factory OS"
            from apps.cli.markdown import render_md as _md   # ★ 终端渲染 markdown（Founder: "cli 好像不支持markdown格式"）
            _body = _md(_ans or "（没答上来; 换句话再说一次?）", indent="")
            from apps.cli.theme import paint as _pb    # ★ 正文色（照 Hermes 的 banner_text ✓）

            _body = "\n".join(_pb("body", _ln) if _ln.strip() else _ln for _ln in _body.splitlines())
            if _use_box():
                # ★ 标题只留名字（用量/耗时挪到**状态栏** —— 照 Hermes: 框是回答区, 底部那行才是状态 ✓）
                _b = box("⚕ AI Factory OS", _body)
                _c, _z = _border_color(), _color_off()
                print("\n".join(_c + ln + _z for ln in _b.splitlines()) if _c else _b)
            else:
                print()
                print("    " + _head)
                print()
                for _ln in _body.splitlines():
                    print(_ln if not _ln else "    " + _ln)
            if _sb:
                from apps.cli.theme import paint as _pl

                print("  " + _pl("status_strong", "⚕ " + str(_sb[0]))
                      + _pl("status_dim", " │ ") + _pl("status_text", " │ ".join(str(x) for x in _sb[1:])))
                print()
            # ★ 它念了写命令 ⇒ 明确问一句（并显示**精确**命令, 让你看清要跑什么）
            _pend = list(_meta.get("pending") or [])
            if _pend:
                _pending_cmd = str(_pend[0])
                print()
                # ★ 跟通用命令用**同一个审批面板**（Founder: ① 不能挤一行 ② 要醒目 ③ 要快捷 ✓）
                _rule_panel("⚠️  需要你确认（这条会改数据）",
                            [f"  命令: factory {_pending_cmd}", "",
                             "  想跳过这一步: 自己敲 /命令 直接跑 ✓"],
                            ["允许这一次", "本会话总是允许（这类不再问）", "拒绝"])
            continue
        argv = line.split()
        # `/命令` 写错了 ⇒ 一句短提示（不再是 argparse 整屏 usage ✗）
        if _cmds and argv and argv[0] not in _cmds:
            print(f"  （没有这个命令: {argv[0]} —— 输入 help 看命令表, 或 /命令 -h 看用法）")
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
