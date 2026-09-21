"""终端里的 markdown 渲染 —— 让会话回复**看着是排好版的**, 而不是一堆 `**` 和 `|`。

为什么: Founder 实测「cli 好像不支持markdown格式」—— 模型按习惯输出 markdown, 终端原样吐出
`**粗体**` / `| a | b |` 这种记号 ✗（他的要求: 会话须支持 markdown）。
策略: 非终端(管道/脚本)只**去标记**(输出干净、可断言 ✓); 终端里加 ANSI 样式 + 把 md 表格
     用平台自己的表格渲染器（CJK 对齐 ✓）。
零依赖, 只用 ANSI 与 textwidth。
"""

from __future__ import annotations

import re

from apps.cli.textwidth import display_width, pad

_BOLD = "\033[1m"
_DIM = "\033[2m"
_CYAN = "\033[36m"
_OFF = "\033[0m"


def _color_enabled(force: bool | None) -> bool:
    if force is not None:
        return force
    import os
    import sys

    if os.environ.get("NO_COLOR") is not None:
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def _inline(s: str, *, color: bool) -> str:
    """行内元素: **粗体** · `代码`（去掉标记, 终端里加样式）。"""
    s = re.sub(r"\*\*(.+?)\*\*", (lambda m: f"{_BOLD}{m.group(1)}{_OFF}") if color else r"\1", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", (lambda m: f"{_DIM}{m.group(1)}{_OFF}") if color else r"\1", s)
    s = re.sub(r"`([^`]+)`", (lambda m: f"{_CYAN}{m.group(1)}{_OFF}") if color else r"\1", s)
    return s


def _table(rows: list[list[str]], *, color: bool) -> list[str]:
    """md 表格（| a | b |）→ 平台表格渲染（CJK 对齐）。"""
    body = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", (c or "-").strip()) for c in r)]
    if not body:
        return []
    head, *rest = body
    widths = [display_width(h) for h in head]
    for r in rest:
        for i, c in enumerate(r):
            if i < len(widths):
                widths[i] = max(widths[i], display_width(c))
    # ★ 不 rstrip（否则最后一列的补齐被削掉 ⇒ 各行宽度不一致, 表格看着参差 ✗ 守卫抓到的）
    out = ["  " + "  ".join(pad(h, widths[i]) for i, h in enumerate(head))]
    out.append("  " + "  ".join("-" * w for w in widths))
    out += ["  " + "  ".join(pad(c, widths[i]) if i < len(widths) else c
                             for i, c in enumerate(r)) for r in rest]
    return out


def render_md(text: str, *, color: bool | None = None, indent: str = "    ") -> str:
    """markdown → 终端文本（标题/列表/表格/行内样式）。"""
    c = _color_enabled(color)
    lines = str(text or "").replace("\r", "").splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        # md 表格: 连续的 | ... | 行
        if raw.strip().startswith("|") and raw.strip().endswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                cells = [x.strip() for x in lines[i].strip().strip("|").split("|")]
                block.append(cells)
                i += 1
            out += _table(block, color=c)
            continue
        s = raw.rstrip()
        m = re.match(r"^(#{1,6})\s+(.*)$", s.strip())
        if m:                                   # 标题
            out.append(indent + (_BOLD if c else "") + m.group(2) + (_OFF if c else ""))
            i += 1
            continue
        if re.fullmatch(r"\s*([-*_])\s*\1\s*\1[\s\-*_]*", s):   # 分隔线
            out.append(indent + ("─" * 40))
            i += 1
            continue
        if s.strip():
            out.append(indent + _inline(s, color=c))
        else:
            out.append("")
        i += 1
    return "\n".join(out)
