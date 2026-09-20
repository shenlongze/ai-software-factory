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
