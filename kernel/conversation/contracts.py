"""kernel/conversation/contracts.py — 会话契约（唯一业务入口）。

只定义"做什么"，不含"怎么做"。禁止 import services/extensions。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class Message:
    """一条用户/系统消息（不可变）。"""

    message_id: str
    conversation_id: str
    role: str  # user | system | agent
    content: str
    at: str = ""


@dataclass(frozen=True)
class Goal:
    """从会话中解析出的"目标"事实。"""

    goal_id: str
    conversation_id: str
    statement: str
    facts: tuple[Message, ...] = field(default_factory=tuple)


@runtime_checkable
class ConversationService(Protocol):
    """会话服务契约：唯一业务入口。"""

    def handle(self, conversation_id: str, message: Message) -> Goal:
        """接收用户表达，产出"目标"事实。"""
        ...

    def get(self, conversation_id: str) -> dict[str, Any] | None:
        """读取会话当前状态。"""
        ...
