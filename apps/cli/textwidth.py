"""显示宽度 —— 中文/全角字符算 2 列。

为什么单独一个模块: 表格对齐、框线对齐都要用它; 以前两处各写一份/各用 len() ✗
（Founder 实测: `agent 注册表  4` 与 `项目  3` 的列对不齐 ⇒ 表格看着是歪的）。
"""

from __future__ import annotations

import unicodedata


def display_width(s: object) -> int:
    """字符串在终端里的显示宽度（东亚宽/全角 = 2, 组合符 = 0）。"""
    w = 0
    for ch in str(s):
        if unicodedata.combining(ch):
            continue
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def pad(s: object, width: int) -> str:
    """右侧补空格到指定**显示宽度**（超出则原样返回, 不截断）。"""
    text = str(s)
    return text + " " * max(0, width - display_width(text))


def ljust_display(s: str, width: int) -> str:
    """按**显示宽度**左对齐补空格（中文算 2 —— 表格/看板列对齐都用它 ✓）。"""
    return s + " " * max(0, width - display_width(s))


def truncate_display(s: str, width: int, ellipsis: str = "…") -> str:
    """按**显示宽度**截断（中文算 2; 超出加省略号 ✓）。"""
    if display_width(s) <= width:
        return s
    out, used = "", 0
    limit = max(0, width - display_width(ellipsis))
    for ch in s:
        w = display_width(ch)
        if used + w > limit:
            break
        out += ch
        used += w
    return out + ellipsis
