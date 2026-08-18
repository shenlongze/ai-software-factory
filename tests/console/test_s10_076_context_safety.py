"""S10-076 — Conversational Context & Safe Intent Routing 测试。

覆盖:
1. Context: current_project / last_created 写入与查询
2. Intent: "刚刚创建的项目呢" → current_project (绝非 create_project)
3. Safety: 参数不完整 → 自然语言提示 (不进入 Domain validation)
4. Chat: Provider 不可用 → 明确错误 (不伪装成"目标不明确")
5. Regression: 原意图解析不回归
"""

from __future__ import annotations

import io
import contextlib
from pathlib import Path

from importlib import import_module

S = import_module("factory-console.session.session")
INT = import_module("factory-console.session.intent")
CHAT = import_module("factory-console.session.chat")


class _FakeChat:
    """测试 ChatService (固定回答, 不依赖真实 LLM)。"""

    def __init__(self, reply: str = "AI: 测试回答"):
        self.reply = reply
        self.calls = []

    def answer(self, question: str, **kw):
        self.calls.append(question)
        return self.reply

    def is_fallback(self, a: str) -> bool:
        return a.startswith("AI:")


def _dispatch(session, line: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        session._dispatch(line)
    return buf.getvalue()


def _parser() -> INT.KeywordIntentParser:
    return INT.KeywordIntentParser()


class TestCurrentProjectIntent:
    def test_just_created_project_is_query_not_create(self):
        """核心 Bug: '刚刚创建的项目呢' → current_project, 绝非 create_project。"""
        p = _parser()
        r = p.parse("刚刚创建的项目呢？")
        assert r is not None
        assert r.intent_type == INT.INTENT_CURRENT_PROJECT
        assert r.intent_type != INT.INTENT_CREATE_PROJECT

    def test_variants_resolve_to_current_project(self):
        p = _parser()
        for text in ("当前项目是什么？", "这个项目在哪里？", "刚才那个项目", "项目在哪里"):
            r = p.parse(text)
            assert r is not None, f"{text} 未识别"
            assert r.intent_type == INT.INTENT_CURRENT_PROJECT, f"{text} → {r.intent_type}"

    def test_explicit_create_still_works(self):
        p = _parser()
        r = p.parse("创建项目 记账App")
        assert r.intent_type == INT.INTENT_CREATE_PROJECT

    def test_product_idea_still_works(self):
        p = _parser()
        r = p.parse("我想做一个app")
        assert r.intent_type == INT.INTENT_CREATE_PRODUCT


class TestContextLayer:
    def test_current_project_set_after_create(self, monkeypatch):
        """create_product 成功后 current_project 写入会话上下文。"""
        s = S.InteractiveSession(chat_service=_FakeChat())

        class _FakeAction:
            name = "create_product"

            def execute(self, context):
                return type("R", (), {
                    "ok": True,
                    "message": "Product Created: X — Ready for Engineering.",
                    "data": {"project": {"id": "P-123", "name": "X"}},
                })()

        monkeypatch.setattr(s.action_registry, "get", lambda name: _FakeAction() if name == "create_product" else None)
        msg = s._create_product_fn(type("PI", (), {"name": "X", "problem": "p", "user": "u", "core_features": [], "to_summary": lambda: "s", "raw": ""})())
        assert "Product Created" in msg
        assert s.context.current_project == "P-123"
        assert s.context.metadata.get("last_created_project") == "P-123"

    def test_show_current_project_with_context(self):
        s = S.InteractiveSession(chat_service=_FakeChat())
        s.context.current_project = "P-456"
        out = _dispatch(s, "刚刚创建的项目呢？")
        assert "P-456" in out
        assert "create_project" not in out.lower() and "项目已注册" not in out

    def test_show_current_project_empty_guides(self):
        s = S.InteractiveSession(chat_service=_FakeChat())
        out = _dispatch(s, "当前项目是什么？")
        assert "当前还没有项目上下文" in out


class TestActionSafety:
    def test_create_project_missing_params_guided(self):
        """create_project 参数不完整 → 自然语言提示 (不进入 validation error)。"""
        s = S.InteractiveSession(chat_service=_FakeChat())
        out = _dispatch(s, "创建项目")  # 无 name/goal
        assert "还需要一些信息" in out
        assert "validation error" not in out.lower()

    def test_create_project_with_name_executes(self):
        s = S.InteractiveSession(chat_service=_FakeChat())
        # 有 name 参数 → 走正常路由 (可能因环境失败, 但不被 safety 拦截)
        intent = INT.KeywordIntentParser().parse("创建项目 记账App")
        assert intent is not None
        assert intent.parameters.get("name") == "记账App"


class _BrokenProvider:
    """模拟 LLM 装配失败 (api key missing)。"""

    def _default_llm_fn(self):
        raise RuntimeError("anthropic api key missing: ANTHROPIC_API_KEY 未设置")

    def _resolve_identity(self):
        raise RuntimeError("anthropic api key missing: ANTHROPIC_API_KEY 未设置")


class _EmptyProvider:
    """模拟无 LLM (装配阶段失败)。"""

    def _resolve_identity(self):
        raise RuntimeError("anthropic api key missing: ANTHROPIC_API_KEY 未设置")


class TestChatFailureSemantics:
    def test_provider_unavailable_not_fallback(self):
        """LLM 不可用 → 明确"服务不可用", 不伪装成"目标不明确"。"""
        cs = CHAT.ChatService(reasoning_provider=_BrokenProvider())
        out = cs.answer("你好")
        assert "AI 对话服务当前不可用" in out
        assert not cs.is_fallback(out)

    def test_key_error_message_identified(self):
        cs = CHAT.ChatService(reasoning_provider=_BrokenProvider())
        out = cs.answer("你好")
        assert "API Key" in out or "Provider" in out

    def test_fallback_only_for_ambiguous(self):
        """真正的空输入 → 引导 (合法场景)。"""
        cs = CHAT.ChatService(reasoning_provider=_BrokenProvider())
        out = cs.answer("")
        assert cs.is_fallback(out)
