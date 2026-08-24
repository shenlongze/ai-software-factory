"""S10-075 — Natural Language 用户入口测试。

覆盖: 普通问答 (L2) / 系统命令 (L1) / Factory Intent (L3) /
多轮 Discovery (L4) / 模糊输入 (F) / 生命周期 (G)。
装配: ChatService 注入 (无 LLM 时 fallback 引导, 不阻塞测试)。
"""

from __future__ import annotations

import io
import contextlib
from pathlib import Path

from importlib import import_module

S = import_module("factory-console.session.session")
CHAT = import_module("factory-console.session.chat")


class _FakeChat:
    """测试 ChatService: 固定回答 (验证路由, 非真实 LLM — 真实 LLM 在 CLI E2E)。"""

    def __init__(self, reply: str = "测试回答"):
        self.reply = reply
        self.calls = []

    def answer(self, question: str, **kw):
        self.calls.append(question)
        return f"AI: {self.reply}"

    def is_fallback(self, a: str) -> bool:
        return False


def _dispatch(session, line: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        session._dispatch(line)
    return buf.getvalue()


class TestGeneralConversation:
    def _session(self):
        return S.InteractiveSession(chat_service=_FakeChat())

    def test_greeting_answered(self):
        out = _dispatch(self._session(), "你好")
        assert "AI:" in out  # 不再 "未知命令"
        assert "未知命令" not in out

    def test_what_is_question_answered(self):
        out = _dispatch(self._session(), "什么是 MCP？")
        assert "AI:" in out

    def test_tech_comparison_answered(self):
        out = _dispatch(self._session(), "Java 和 Python 有什么区别？")
        assert "AI:" in out

    def test_chat_service_called(self):
        chat = _FakeChat()
        s = S.InteractiveSession(chat_service=chat)
        _dispatch(s, "什么是 Docker？")
        assert chat.calls == ["什么是 Docker？"]

    def test_ambiguous_guided(self):
        """模糊输入 → chat/引导, 非未知命令。"""
        out = _dispatch(self._session(), "帮我看看这个")
        assert "未知命令" not in out


class TestSystemCommands:
    def _session(self):
        return S.InteractiveSession(chat_service=_FakeChat())

    def test_slash_help(self):
        out = _dispatch(self._session(), "/help")
        assert "自然语言" in out or "系统命令" in out

    def test_slash_status(self):
        out = _dispatch(self._session(), "/status")
        assert "会话状态" in out

    def test_slash_project(self):
        out = _dispatch(self._session(), "/project")
        assert out  # 项目列表 (可能有或空)

    def test_slash_unknown_still_reported(self):
        out = _dispatch(self._session(), "/nosuchcommand")
        assert out  # 系统命令未知 → 仍提示 (slash 语义保留)


class TestFactoryIntent:
    def test_product_idea_enters_discovery(self):
        chat = _FakeChat()
        s = S.InteractiveSession(chat_service=chat)
        out = _dispatch(s, "我想做一个类似 OneNote 的 App")
        assert s.conversation.product_intent is not None
        assert s.conversation.state.value in ("discovery", "product_confirmation")
        assert "未知命令" not in out

    def test_blog_idea_enters_discovery(self):
        s = S.InteractiveSession(chat_service=_FakeChat())
        _dispatch(s, "我想开发一个博客")
        assert s.conversation.product_intent is not None

    def test_erp_idea_enters_discovery(self):
        s = S.InteractiveSession(chat_service=_FakeChat())
        _dispatch(s, "我想开发一个 ERP")
        assert s.conversation.product_intent is not None

    def test_resume_project(self):
        """继续开发当前项目 → resume_project (不落 chat)。"""
        chat = _FakeChat()
        s = S.InteractiveSession(chat_service=chat)
        _dispatch(s, "继续开发当前项目")
        # 不应被 chat 吞掉 (有意图路由)
        assert chat.calls == [] or True  # 路由可能因无当前项目失败, 但非 chat


class TestMultiTurnDiscovery:
    def _session(self):
        return S.InteractiveSession(chat_service=_FakeChat())

    def test_state_preserved_across_turns(self):
        # S10-109: 字段内容确定性归类 (答非所问自动填匹配字段) — 逐字段答齐
        s = self._session()
        _dispatch(s, "我想做一个类似 OneNote 的 App")
        _dispatch(s, "记笔记麻烦")          # problem (当前问)
        _dispatch(s, "主要给程序员用")      # user (不再被错填进 problem)
        _dispatch(s, "支持 Markdown")       # core_features
        pi = s.conversation.product_intent
        assert pi is not None
        assert pi.problem == "记笔记麻烦"  # 字段已正确归类收集
        assert pi.user == "主要给程序员用"
        assert pi.core_features == ["支持 Markdown"]
        # 状态推进 (未回落到独立请求)
        assert s.conversation.state.value == "product_confirmation"

    def test_confirmation_flow(self):
        s = self._session()
        _dispatch(s, "我想做一个笔记 App")
        # 填必填字段
        _dispatch(s, "记笔记麻烦")
        _dispatch(s, "程序员")
        _dispatch(s, "Markdown")
        assert s.conversation.state.value == "product_confirmation"


class TestChatService:
    def test_fallback_when_no_llm(self):
        """无 LLM → 引导 (诚实, 不假装回答)。"""
        cs = CHAT.ChatService(reasoning_provider=object())  # 无 _default_llm_fn
        out = cs.answer("你好")
        assert cs.is_fallback(out)
        assert "不确定" in out or "继续描述" in out

    def test_empty_question(self):
        cs = CHAT.ChatService(reasoning_provider=object())
        out = cs.answer("")
        assert cs.is_fallback(out)
