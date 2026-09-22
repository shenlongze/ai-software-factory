"""CLI 主题（颜色）—— 结构与 Hermes 的 skin_engine 一一对应, 色板用 AI Factory 的 Apple 风。

Hermes 的元素映射（`~/.hermes/hermes-agent/hermes_cli/skin_engine.py`）:
  banner_border / banner_title / banner_accent / banner_dim / banner_text
  prompt / input_rule / response_border / response_label
  status_bar_bg / status_bar_text / status_bar_strong / status_bar_dim / good / warn / bad
本模块照同一组元素给出**我们的取值**（Apple 系统色, 见 Founder 的 UI 偏好 #f5f5f7/#0071e3）。

规矩:
  · **只在终端里上色**（非终端一色都不上 —— 管道/脚本输出必须干净可断言 ✓）
  · `NO_COLOR=1` 或 `FACTORY_UI=plain` ⇒ 全部退化为纯文本 ✓
  · 真彩（24bit ANSI）; 不支持的环境自动忽略（终端会当作无效果 ✓）
"""

from __future__ import annotations

import os
import sys

#: 元素 → 颜色（Apple 系统色; 与 Hermes 的元素名对齐）
PALETTE: dict[str, str] = {
    # ★ 采用 **Hermes 的配色**（Founder: "可以采用 Hermes 的颜色搭配"）
    #   出处: ~/.hermes/hermes-agent/hermes_cli/skin_engine.py 的默认皮肤（金/铜色系）
    #   映射: 左边是我们的元素名（与它的元素名一一对应）, 右边是它的原值。
    "banner_border": "#CD7F32",     # ← banner_border   铜色（面板边框）
    "banner_title": "#FFD700",      # ← banner_title    金色（标题）
    "banner_accent": "#FFBF00",     # ← banner_accent   琥珀（小标题/强调）
    "banner_dim": "#B8860B",        # ← banner_dim      暗金（次要文字/分隔标签）
    "prompt": "#FFF8DC",            # ← prompt          米白（提示符文字）
    "input_rule": "#CD7F32",        # ← input_rule      铜色（输入区横线）
    "user_mark": "#FFBF00",         # ← ui_accent       琥珀（`● 你的话` 的圆点）
    "tool_prefix": "#8B8682",       # ← status_bar_dim  灰（`┊` 与耗时）
    "response_border": "#FFD700",   # ← response_border 金色（回答框边框）
    "response_label": "#FFD700",    # ← banner_title    金色（回答框标题）
    "status_text": "#C0C0C0",       # ← status_bar_text  银灰（状态栏文字）
    "status_strong": "#FFD700",     # ← status_bar_strong 亮金（状态栏数值）
    "status_dim": "#8B8682",        # ← status_bar_dim  灰（状态栏分隔符）
    "good": "#4CAF50",              # ← ui_ok           绿（成功）
    "warn": "#FFA726",              # ← ui_warn         橙（提醒）
    "bad": "#EF5350",               # ← ui_error        红（失败）
    "code": "#FFBF00",              # ← ui_accent       琥珀（行内 `代码`）
    "body": "#FFF8DC",              # ← banner_text     米白（正文）
}


def color_enabled(force: bool | None = None) -> bool:
    """要不要上色（非终端/NO_COLOR/plain ⇒ 否 ✓）。"""
    if force is not None:
        return force
    if os.environ.get("NO_COLOR") is not None or os.environ.get("FACTORY_UI") == "plain":
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def _hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _truecolor() -> bool:
    """终端认不认 24 位真彩色 —— ★ 只认 `COLORTERM`。

    macOS 自带 Terminal.app **不支持真彩** ✗（发了 `38;2;r;g;b` 会被忽略 ⇒ 用户看不到颜色 ✗）;
    它认 **256 色**。所以: 没有 `COLORTERM=truecolor|24bit` 就退回 256 色 ✓。
    """
    return "truecolor" in os.environ.get("COLORTERM", "").lower() or "24bit" in os.environ.get("COLORTERM", "").lower()


def _to_256(r: int, g: int, b: int) -> int:
    """真彩 → xterm-256 色号（6×6×6 色立方; 够用且各家终端都认 ✓）。"""
    def _q(v: int) -> int:
        return 0 if v < 48 else 1 if v < 114 else (v - 35) // 40
    return 16 + 36 * _q(r) + 6 * _q(g) + _q(b)


def paint(element: str, text: str, *, force: bool | None = None) -> str:
    """给一段文字上色（按元素取色; 不需要上色就原样返回 ✓）。

    真彩可用 ⇒ 24 位; 否则 ⇒ **256 色**（macOS Terminal.app 这类只认 256 色的终端也能看到 ✓）。
    """
    if not text or not color_enabled(force):
        return text
    r, g, b = _hex_rgb(PALETTE.get(element, "#f5f5f7"))
    if _truecolor():
        return f"\033[38;2;{r};{g};{b}m{text}\033[0m"
    return f"\033[38;5;{_to_256(r, g, b)}m{text}\033[0m"


def dim(text: str, *, force: bool | None = None) -> str:
    """次要文字 —— ★ 用**实色灰**（`status_dim`）而不是 ANSI 的 `2m` 半透明:

    `\033[2m` 在很多终端里会糊成看不清 ✗（Founder: "字体颜色"）; Hermes 也是给实色。
    """
    return paint("status_dim", text, force=force)
