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

#: S10-076: LLM Provider 不可用 → 明确错误 (不再伪装成 "目标不明确")
_PROVIDER_UNAVAILABLE = (
    "AI 对话服务当前不可用。\n"
    "原因: LLM Provider 尚未配置或 API Key 缺失。\n"
    "建议:\n"
    "  1. 运行 factory doctor 检查当前配置\n"
    "  2. 运行 factory init 配置 AI Provider\n"
    "系统命令 (/help /status /project) 不受影响。"
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
        except Exception:  # noqa: BLE001 — 装配失败 → 明确不可用
            return False

    def _provider_unavailable_reason(self) -> str:
        """S10-076: LLM 不可用的明确原因 (诚实, 不伪装)。"""
        try:
            from .reasoning import ReasoningProvider
            from ..config import ConfigProvider

            rp = ReasoningProvider()
            pid, _model = rp._resolve_identity()  # noqa: SLF001 — 同包读取
            if not pid:
                return "未配置 LLM Provider (factory init 配置)"
            try:
                from exec.cli import _provider_registry  # noqa: PLC0415

                _provider_registry.get(pid)
                return f"Provider '{pid}' 已配置但 API Key 不可用"
            except Exception:  # noqa: BLE001
                return f"Provider '{pid}' 装配失败"
        except Exception as exc:  # noqa: BLE001
            return f"LLM 装配失败: {exc}"

    def answer(self, question: str, *, max_chars: int = 600, verbose: bool = False) -> str:
        """真实 LLM 回答普通问题; LLM 不可用 → 简洁提示 (verbose=True 含细节)。

        S10-078: 默认不向普通用户倾倒内部异常; 开发者诊断经 verbose/doctor。
        """
        q = str(question or "").strip()
        if not q:
            return _FALLBACK
        if not self._provider_ready():
            # S10-076: Provider 不可用 ≠ 用户目标不明确 — 明确区分
            if verbose:
                reason = self._provider_unavailable_reason()
                return f"{_PROVIDER_UNAVAILABLE}\n(细节: {reason})"
            return _PROVIDER_UNAVAILABLE
        try:
            llm_fn = self._provider._default_llm_fn()  # noqa: SLF001 — 同包复用装配链
            text = llm_fn(_CHAT_PROMPT.format(question=q), "chat")
            text = str(text or "").strip()
            if not text:
                return _FALLBACK
            return text[:max_chars]
        except Exception as exc:  # noqa: BLE001 — LLM 调用失败 → 明确不可用
            # S10-078: 细节仅进日志 (默认不向 REPL stderr 倾倒内部异常)
            logger.debug("chat answer failed: %s", exc)
            msg = str(exc)
            if (
                "api key" in msg.lower() or "key" in msg.lower() or "未设置" in msg
                or "missing" in msg.lower() or "无可用 llm provider" in msg.lower()
                or "未配置 enabled provider" in msg
            ):
                if verbose:
                    return f"{_PROVIDER_UNAVAILABLE}\n(细节: {msg[:200]})"
                return _PROVIDER_UNAVAILABLE
            return _FALLBACK

    def is_fallback(self, answer: str) -> bool:
        """判断回答是否为引导 (无 LLM 时测试用)。"""
        return answer == _FALLBACK
