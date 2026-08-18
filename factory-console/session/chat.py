"""factory-console/session/chat.py — 普通自然语言问答 (S10-075 L2)。

复用 ReasoningProvider 的 LLM 装配链 (exec.cli provider registry), 不重建
Chat Runtime。无 LLM / 失败 → 自然语言引导 (诚实, 不假装 AI 回答)。

设计: REPL 中 intent 未识别 (你好/什么是 MCP/什么是 Docker) → ChatService.answer
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("factory.session.chat")

#: 问答 prompt 模板 (中文优先 — 产品语言)
_CHAT_PROMPT = """你是一个 AI 软件开发助手 (AI Software Factory 的对话入口)。
回答下面的用户问题, 简洁、准确、友好, 用中文回答。

用户问题: {question}
"""

#: 无 LLM 时的诚实引导 (不假装回答)
_FALLBACK = (
    "我还不确定你的目标。\n"
    "你可以:\n"
    "  • 继续描述你想做什么 (例如: 我想做一个记账 App)\n"
    "  • 问我技术问题 (例如: 什么是 MCP?)\n"
    "  • 输入 /help 查看系统命令"
)


class ChatService:
    """普通问答服务: 真实 LLM 回答, 失败 → 引导。"""

    def __init__(self, reasoning_provider: Optional[object] = None) -> None:
        self._provider = reasoning_provider

    def _provider_ready(self) -> bool:
        if self._provider is not None:
            return True
        try:
            from .reasoning import ReasoningProvider

            self._provider = ReasoningProvider()
            return True
        except Exception:  # noqa: BLE001 — 装配失败 → 引导
            return False

    def answer(self, question: str, *, max_chars: int = 600) -> str:
        """真实 LLM 回答普通问题; 无 LLM/失败 → 引导。"""
        q = str(question or "").strip()
        if not q:
            return _FALLBACK
        if not self._provider_ready():
            return _FALLBACK
        try:
            llm_fn = self._provider._default_llm_fn()  # noqa: SLF001 — 同包复用装配链
            text = llm_fn(_CHAT_PROMPT.format(question=q), "chat")
            text = str(text or "").strip()
            if not text:
                return _FALLBACK
            return text[:max_chars]
        except Exception as exc:  # noqa: BLE001 — LLM 失败 → 引导 (诚实)
            logger.warning("chat answer failed: %s", exc)
            return _FALLBACK

    def is_fallback(self, answer: str) -> bool:
        """判断回答是否为引导 (无 LLM 时测试用)。"""
        return answer == _FALLBACK
