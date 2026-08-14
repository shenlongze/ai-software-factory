"""factory-console/session/conversation.py — Conversation State + Manager (S10-048 P3)。

会话状态模型 (基础 flow, 不过度开发 — 设计 §2.6):
- ConversationState(Enum) — DISCOVERY/CLARIFICATION/CONFIRMATION/EXECUTION/DONE
- ConversationResponse — handle() 产出: state + message + needs_input
- ConversationManager — 状态机: state / pending_intent / history /
  transition / handle / reset

基础 flow (handle):
  非 slash 文本 → IntentParser.parse →
    - 识别 intent → pending_intent + CONFIRMATION (返回计划确认消息)
    - 未识别     → CLARIFICATION (提示澄清)
  slash 文本 → 交命令注册表 (状态机不处理, 状态不变)

边界 (设计 §2.7):
- 只实现 state model + interface + basic flow; EXECUTION/DONE 枚举就绪
  (供后续 Task 驱动), 本 Phase 不做多轮澄清/执行编排
- 零依赖 (纯标准库), 不复制业务逻辑
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from .intent import IntentObject, IntentParser, KeywordIntentParser


class ConversationState(Enum):
    """会话状态 (设计 §2.6): 收集需求 → 澄清缺失 → 确认计划 → 执行 → 完成。"""

    DISCOVERY = "discovery"  # 收集需求
    CLARIFICATION = "clarification"  # 澄清缺失信息
    CONFIRMATION = "confirmation"  # 确认执行计划
    EXECUTION = "execution"  # 执行中
    DONE = "done"


@dataclass
class ConversationResponse:
    """ConversationManager.handle() 的产出: 当前状态 + 给用户的消息 + 是否等待输入。"""

    state: ConversationState
    message: str = ""
    needs_input: bool = False


class ConversationManager:
    """会话状态机 (基础 flow) — 跟踪对话状态与待确认意图, 历史可审计。

    - state: 当前状态 (初始 DISCOVERY)
    - pending_intent: 识别成功后挂起的 Intent (等待确认/澄清)
    - history: 事件记录 ({"event": "input"|"transition", ...}) — 可审计
    - transition(new_state): 状态迁移 (非法枚举 → ValueError, 不静默)
    - handle(text, parser): 基础 flow — 识别 → CONFIRMATION; 未识别 → CLARIFICATION
    - reset(): 回到初始 DISCOVERY (清空 pending_intent / history)
    """

    def __init__(self, parser: Optional[IntentParser] = None) -> None:
        self.state = ConversationState.DISCOVERY
        self.pending_intent: Optional[IntentObject] = None
        self.history: list[dict[str, Any]] = []
        #: 默认解析器 (handle 未显式传 parser 时使用; 可注入定制/LLM 版)
        self._parser = parser if parser is not None else KeywordIntentParser()

    def transition(self, new_state: ConversationState) -> None:
        """状态迁移: 记录 history (from → to) 后更新 state。

        非法值 (非 ConversationState) → ValueError (明确, 不静默)。
        """
        if not isinstance(new_state, ConversationState):
            raise ValueError(
                f"非法会话状态: {new_state!r} (须为 ConversationState 枚举)"
            )
        self.history.append(
            {"event": "transition", "from": self.state.value, "to": new_state.value}
        )
        self.state = new_state

    def handle(
        self, text: str, parser: Optional[IntentParser] = None
    ) -> ConversationResponse:
        """基础 flow: 非 slash 文本 → parse → 识别 → CONFIRMATION / 未识别 → CLARIFICATION。

        - 空输入 → CLARIFICATION (提示描述需求)
        - slash 文本 → 状态不变 (命令注册表处理, 不在状态机范围)
        - 识别成功 → pending_intent 挂起 + 迁移 CONFIRMATION, 返回计划确认消息
        - 未识别 → 迁移 CLARIFICATION, 提示澄清
        """
        self.history.append({"event": "input", "text": text})
        raw = (text or "").strip()
        if not raw:
            return self._clarify("请输入你的需求描述 (例如: '创建一个项目' 或 '项目列表')")
        if raw.startswith("/"):
            # slash 命令由 SlashCommandRegistry 处理, 状态机不接管 (状态不变)
            return ConversationResponse(
                state=self.state,
                message="slash 命令由命令注册表处理, 不走会话状态机",
                needs_input=False,
            )
        intent = (parser or self._parser).parse(raw)
        if intent is None:
            return self._clarify(
                "未识别意图 — 请换个说法描述需求 (例如: '创建项目' / '项目列表' / '状态')"
            )
        self.pending_intent = intent
        self.transition(ConversationState.CONFIRMATION)
        detail = f"{intent.intent_type} {intent.parameters or ''}".strip()
        return ConversationResponse(
            state=self.state,
            message=f"确认执行计划: {detail}",
            needs_input=True,
        )

    def _clarify(self, message: str) -> ConversationResponse:
        """未识别/信息不足 → CLARIFICATION (等待用户输入)。"""
        self.transition(ConversationState.CLARIFICATION)
        return ConversationResponse(
            state=self.state, message=message, needs_input=True
        )

    def reset(self) -> None:
        """回到初始状态: DISCOVERY, 清空 pending_intent 与 history (全新会话)。"""
        self.state = ConversationState.DISCOVERY
        self.pending_intent = None
        self.history = []
