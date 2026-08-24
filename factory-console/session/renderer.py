"""factory-console/session/renderer.py — Renderer 输出层 (S10-047 Task 006)。

设计: docs/sprint10/S10-046-renderer-design.md (§4 渲染层架构 / §5 --json / §6 边界)
- Service Layer 返回结构化 dict, Renderer 负责展示 — 输出与逻辑解耦
- 纯函数: 输入 dict → 输出文本, 无副作用; 简单清晰, 无 ANSI 动画/进度条
- 颜色不作唯一信息通道; 少量符号增强可读性 (✔/❌/→)
- 全局 --json → renderer_for(json_flag=True) → JsonRenderer (机器可读)

组件:
- Renderer (ABC) — 渲染接口: render(result: dict) -> str
- HumanRenderer — 人类可读 (文本/简单表格/错误提示/成本)
- JsonRenderer — 机器可读 (json.dumps 结构化)
- renderer_for(json_flag) — 工厂: json=True → JsonRenderer, 否则 HumanRenderer
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any


def _require_dict(result: Any) -> dict[str, Any]:
    """render 输入契约: 必须是 dict (Service Layer 结构化结果)。"""
    if not isinstance(result, dict):
        raise TypeError(f"render 需要 dict 输入, 收到 {type(result).__name__}")
    return result


class Renderer(ABC):
    """渲染接口: render(result: dict) -> str — 纯函数 (无副作用)。"""

    @abstractmethod
    def render(self, result: dict[str, Any]) -> str:
        """结构化 dict → 展示文本。"""


class HumanRenderer(Renderer):
    """人类可读渲染器: 文本 / 简单表格 / 错误提示 / 成本 (S10-046 §3 子集)。

    按 result 形状分派:
    - 失败 (error / ok=False) → ❌ Failed + Reason + Solution
    - 表格 (header/rows) → 对齐列 (可选 title)
    - 成本 (cost/tokens) → "本次执行: N tokens · $X · Y 秒"
    - 成功 (ok=True) → "✔ <message>"
    - 其它 → "key: value" 行 (嵌套 dict/list 以 JSON 展示)
    """

    def render(self, result: dict[str, Any]) -> str:
        data = _require_dict(result)
        if data.get("error") or data.get("ok") is False:
            return self._render_error(data)
        if "header" in data or "rows" in data:
            return self._render_table(data)
        if "cost" in data or "tokens" in data:
            return self._render_cost(data)
        if data.get("ok") is True:
            return f"✔ {data.get('message') or '完成'}"
        return self._render_generic(data)

    @staticmethod
    def _render_error(data: dict[str, Any]) -> str:
        reason = data.get("reason") or data.get("error") or data.get("message") or "(无详情)"
        lines = ["❌ Failed", "", "Reason:", f"  {reason}"]
        if data.get("solution"):
            lines += ["", "Solution:", f"  {data['solution']}"]
        return "\n".join(lines)

    @staticmethod
    def _render_table(data: dict[str, Any]) -> str:
        header = [str(h) for h in data.get("header", [])]
        rows = [[str(c) for c in row] for row in data.get("rows", [])]
        widths = [len(h) for h in header]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(widths):
                    widths[i] = max(widths[i], len(cell))
        lines: list[str] = []
        if data.get("title"):
            lines.append(str(data["title"]))
        if header:
            lines.append("  " + "  ".join(h.ljust(widths[i]) for i, h in enumerate(header)))
        for row in rows:
            padded = [
                c.ljust(widths[i]) if i < len(widths) else c for i, c in enumerate(row)
            ]
            lines.append("  " + "  ".join(padded))
        return "\n".join(lines)

    @staticmethod
    def _render_cost(data: dict[str, Any]) -> str:
        parts: list[str] = []
        if "tokens" in data:
            parts.append(f"{int(data['tokens']):,} tokens")
        if "cost" in data:
            parts.append(f"${data['cost']}")
        if "seconds" in data:
            parts.append(f"{data['seconds']} 秒")
        return "本次执行: " + " · ".join(parts)

    @staticmethod
    def _render_generic(data: dict[str, Any]) -> str:
        lines = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                rendered = json.dumps(value, ensure_ascii=False)
            else:
                rendered = str(value)
            lines.append(f"{key}: {rendered}")
        return "\n".join(lines)


class JsonRenderer(Renderer):
    """机器可读渲染器 (S10-046 §5): 完整结构化结果, CI/脚本消费。"""

    def render(self, result: dict[str, Any]) -> str:
        data = _require_dict(result)
        return json.dumps(data, ensure_ascii=False, indent=2)


def renderer_for(json_flag: bool = False) -> Renderer:
    """渲染器工厂: json_flag=True → JsonRenderer (机器可读); 否则 HumanRenderer。"""
    return JsonRenderer() if json_flag else HumanRenderer()


# ---------------------------------------------------------------------------
# S10-105 — 会话 Markdown 渲染 (CLI REPL 层, 保守启发式 + rich 可选)
# 设计: docs/sprint10/S10-105-markdown-preview-plan.md §1.1
# - 只有真文档才触发 (标题/表格/代码围栏), 普通发现/确认消息零影响
# - rich 只 import 不加依赖; import 失败 → print 原样 (诚实降级, 不崩)


def looks_like_markdown(text: str) -> bool:
    """强 markdown 信号保守判断: 只有真文档才返回 True。

    触发信号 (任一):
    - 含 ``` 代码围栏
    - 任一行 ^#{1,6} 标题
    - 任一行含 | 表格
    列表标记 (-/1.) 不算 — 发现流程建议/进度消息保持纯文本 (验收: 非 markdown
    纯文本不变)。
    """
    if not isinstance(text, str) or not text:
        return False
    if "```" in text:
        return True
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^#{1,6}", stripped):
            return True
        if "|" in stripped:
            return True
    return False


def render_message(text: str) -> None:
    """输出一条用户面消息: markdown → rich 渲染; 否则 print 原样。

    rich 可 import 且 looks_like_markdown → Console().print(Markdown(text));
    否则 → print(text) 原样 (诚实降级; rich 非终端自动去 ANSI, 测试输出仍可断言)。
    """
    if looks_like_markdown(text):
        try:
            from rich.console import Console
            from rich.markdown import Markdown

            Console().print(Markdown(text))
            return
        except Exception:  # noqa: BLE001 — rich 缺失/故障 → 诚实降级 print 原样
            pass
    print(text)
