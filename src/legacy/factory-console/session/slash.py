"""factory-console/session/slash.py — Slash Command 框架 (S10-047 Task 003)。

注册式命令分发: 命令 = SlashCommand 子类 (name / description / execute), 注册进
SlashCommandRegistry 后即被 "/name args" 路由 — 零硬编码 if, 新增命令只需 register。
设计: docs/sprint10/S10-046-slash-command-design.md §3 路由规则 / §6 边界。

用法:
    registry = SlashCommandRegistry(session=session)   # session 可选宿主
    registry.register(MyCommand())
    registry.execute("/help", context)   # → 分发到命令; 未知 → 明确提示 (不静默)

边界 (S10-046 §6):
- 不新增命令系统: 命令只做会话内编排, 业务全部在既有 Service Layer
- 未知 Slash → 提示可用列表 (不静默)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .context import SessionContext

#: 未知 slash 提示后缀 (含 /help 指引; 前缀与 session.py UNKNOWN_PREFIX 同风格)
UNKNOWN_SLASH_SUFFIX = " — 输入 /help 查看可用命令"


class SlashCommand(ABC):
    """Slash 命令基类 (注册式): name / description / execute(args, context) -> int。"""

    #: 命令名 (不带斜杠; 注册表按此路由, 全小写)
    name: str = ""
    #: 一行说明 (/help 展示)
    description: str = ""

    def __init__(self) -> None:
        #: 注册后由 registry 注入反向引用 (命令可访问 registry / registry.session)
        self.registry: Optional[SlashCommandRegistry] = None

    @abstractmethod
    def execute(self, args: str, context: SessionContext) -> int:
        """执行命令。

        args: "/name args" 中 args 的原始字符串 (无参 → "")
        context: 当前会话上下文 (SessionContext, 可读写)
        返回: 0 成功; 非 0 失败 (仅展示语义, 不阻断会话循环)
        """


class SlashCommandRegistry:
    """Slash 命令注册表: 解析 "/name args" → 注册表分发 (无硬编码 if)。"""

    def __init__(self, session: Optional[object] = None) -> None:
        self._commands: dict[str, SlashCommand] = {}
        #: 可选宿主 (InteractiveSession) — /exit 等需写会话状态的命令经此访问
        self.session = session

    def register(self, cmd: SlashCommand) -> SlashCommand:
        """注册命令 (name 重复 → 后者覆盖; 注入 registry 反向引用)。"""
        cmd.registry = self
        self._commands[cmd.name] = cmd
        return cmd

    def get(self, name: str) -> Optional[SlashCommand]:
        """按命令名取命令 (未注册 → None)。"""
        return self._commands.get(name)

    def list(self) -> list[SlashCommand]:
        """全部已注册命令 (按 name 排序 — /help 展示顺序稳定)。"""
        return sorted(self._commands.values(), key=lambda cmd: cmd.name)

    def execute(self, line: str, context: SessionContext) -> int:
        """解析并分发一行输入: "/name args" → 命令; 未知 → 明确提示 (不静默)。"""
        text = line.strip()
        if not text.startswith("/"):
            print(f"错误: slash 命令需以 / 开头 — 收到: {line!r}")
            return 1
        body = text[1:].strip()
        name, sep, args = body.partition(" ")
        name = name.strip().lower()
        args = args.strip() if sep else ""
        cmd = self.get(name)
        if cmd is None:
            print(f"未知命令: {f'/{name}' if name else '/'}{UNKNOWN_SLASH_SUFFIX}")
            return 1
        return cmd.execute(args, context)
