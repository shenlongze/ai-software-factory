"""S10-082 — Conversational Intelligence & PM Experience 测试。

覆盖:
1. "你好" → Chat
2. "我正在学习 AI Agent" → Chat (不再 UnknownIntentError)
3. "什么是 MCP" → Chat
4. "我想做一个密码管理 App" → Discovery
5. 命名: 不产生"未命名产品"
6. LLM 不可用: Chat 失败 → 友好 Provider 提示 (非 UnknownIntent)
7. 无路由 intent → 安全降级 Chat
"""

from __future__ import annotations

import io
import contextlib

from importlib import import_module

S = import_module("factory-console.session.session")
CONV = import_module("factory-console.session.conversation")
INT = import_module("factory-console.session.intent")
NAMING = import_module("factory-console.session.naming")


class _FakeChat:
    def __init__(self):
        self.calls = []

    def answer(self, question: str, **kw):
        self.calls.append(question)
        return f"AI: {question}"

    def is_fallback(self, a: str) -> bool:
        return a.startswith("AI:")


def _dispatch(session, line: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        session._dispatch(line)
    return buf.getvalue()


def _session():
    return S.InteractiveSession(
        chat_service=_FakeChat(),
        # 确定性测试模式: 发现流程禁用 LLM (不依赖真实 LLM/网络)
        conversation_manager=CONV.ConversationManager(analyzer=None),
    )


class TestChatFallback:
    def test_greeting_chat(self):
        """你好 → Chat。"""
        chat = _FakeChat()
        s = S.InteractiveSession(chat_service=chat)
        out = _dispatch(s, "你好")
        assert "AI:" in out
        assert "你好" in chat.calls

    def test_learning_agent_chat(self):
        """我正在学习 AI Agent → Chat (核心 P0: 不再 UnknownIntentError)。"""
        chat = _FakeChat()
        s = S.InteractiveSession(chat_service=chat)
        out = _dispatch(s, "我正在学习 AI Agent")
        assert "AI:" in out
        assert "未识别的意图" not in out
        assert "未配置路由" not in out
        assert "我正在学习 AI Agent" in chat.calls

    def test_what_is_mcp_chat(self):
        chat = _FakeChat()
        s = S.InteractiveSession(chat_service=chat)
        out = _dispatch(s, "什么是 MCP")
        assert "AI:" in out

    def test_no_unknown_intent_error_ever(self):
        """用户永远看不到 UnknownIntentError / intent 名。"""
        chat = _FakeChat()
        s = S.InteractiveSession(chat_service=chat)
        for t in ("我正在学习 AI Agent", "什么是 Docker", "帮我看看这个"):
            out = _dispatch(s, t)
            assert "UnknownIntent" not in out
            assert "未配置路由" not in out
            assert "未识别的意图" not in out

    def test_routed_intent_not_chat(self):
        """明确 Factory 操作仍进 action (不降级)。"""
        chat = _FakeChat()
        s = S.InteractiveSession(chat_service=chat)
        out = _dispatch(s, "继续开发")
        assert "正在开发的项目" in out or "AI:" not in out  # 无项目 → 引导; 非 chat


class TestIntentRoutingCompleteness:
    def test_audit_events_route_via_same_name_action(self):
        """同名 action 兜底: audit_events → 路由 (不再断链)。"""
        s = _session()
        action = s.action_registry.get("audit_events")
        assert action is not None

    def test_memory_learn_same_name_action(self):
        s = _session()
        assert s.action_registry.get("memory_learn") is not None

    def test_all_same_name_actions_routable(self):
        """所有 intent 类型 + 同名 action 注册 → 可路由。"""
        s = _session()
        for name in ("audit_events", "memory_learn", "memory_search",
                     "debug_analyze", "product_intelligence"):
            assert s.action_registry.get(name) is not None, name


class TestNamingCandidates:
    def test_deterministic_candidates(self):
        """无 LLM: 多候选 (核心词 + 后缀变体), 非临时名。"""
        cands = NAMING.suggest_names("个人密码管理")
        assert cands
        assert len(cands) <= 3
        for c in cands:
            assert c
            assert not c.startswith("未命名产品")

    def test_candidates_include_core(self):
        cands = NAMING.suggest_names("个人密码管理")
        assert any("密码" in c for c in cands)

    def test_llm_candidates(self):
        cands = NAMING.suggest_names("个人密码管理 App", llm_fn=lambda p, o="": "密钥管家\n保险箱\n密码夹")
        assert len(cands) == 3
        assert cands[0] == "密钥管家"

    def test_discovery_no_temp_name(self):
        """Discovery 生成候选, 不产生未命名产品。"""
        s = _session()
        _dispatch(s, "我想做一个个人密码管理 App")
        _dispatch(s, "密码容易忘")
        _dispatch(s, "个人用户")
        _dispatch(s, "密码存储")
        pi = s.conversation.product_intent
        assert pi is not None
        assert pi.name
        assert not pi.name.startswith("未命名产品")


class TestProviderFallback:
    def test_provider_unavailable_friendly(self):
        """LLM 不可用: Chat 失败 → 友好 Provider 提示 (非 UnknownIntent)。"""
        from importlib import import_module
        CHAT = import_module("factory-console.session.chat")

        class _Broken:
            def _default_llm_fn(self):
                raise RuntimeError("api key missing")

        cs = CHAT.ChatService(reasoning_provider=_Broken())
        out = cs.answer("你好")
        assert "AI 对话服务当前不可用" in out
        assert "UnknownIntent" not in out


class TestDiscoveryConversational:
    def test_conversational_problem_prompt(self):
        """P1: Discovery 问题对话化 (引导 + 示例)。"""
        s = _session()
        out = _dispatch(s, "我想做一个密码管理 App")
        assert "梳理" in out or "痛点" in out or "解决" in out
        assert "缺失字段" in out
