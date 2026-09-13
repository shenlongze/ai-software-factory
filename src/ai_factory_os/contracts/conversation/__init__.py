"""conversation — 会话。零依赖。

会话是**人类入口**：用户表达目标的地方。它不是流程，也不承载流程状态。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConversationState(str, Enum):
    OPEN = "open"
    AWAITING_INPUT = "awaiting_input"
    AWAITING_APPROVAL = "awaiting_approval"
    CLOSED = "closed"


class TurnRole(str, Enum):
    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"


@dataclass(frozen=True)
class Turn:
    """一轮对话。"""

    role: TurnRole
    text: str
    at: str = ""
    subject_ref: str = ""


@dataclass(frozen=True)
class Conversation:
    """一个会话 —— 目标的入口，产出的引用点。"""

    id: str
    subject_id: str
    state: ConversationState = ConversationState.OPEN
    goal: str = ""
    turns: tuple[Turn, ...] = ()
    project_ref: str = ""
