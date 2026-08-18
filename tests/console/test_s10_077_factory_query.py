"""S10-077 — Factory Query 优先路由 (不依赖 LLM)。

覆盖:
A. Project Query 全变体 → list_projects / current_project (零 LLM)
B. 路由分类: Query / Action / Chat / Discovery
C. Provider Missing: Factory Query 正常, General Chat 明确 Provider Error
D. Context: current_project / last_created_project
E. Safety: 不完整参数 → 用户友好提示 (不进 Pydantic validation)
"""

from __future__ import annotations

import io
import contextlib

from importlib import import_module

S = import_module("factory-console.session.session")
INT = import_module("factory-console.session.intent")


class _FakeChat:
    def __init__(self):
        self.calls = []

    def answer(self, question: str, **kw):
        self.calls.append(question)
        return "AI: 测试回答"

    def is_fallback(self, a: str) -> bool:
        return a.startswith("AI:")


def _dispatch(session, line: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        session._dispatch(line)
    return buf.getvalue()


def _parser() -> INT.KeywordIntentParser:
    return INT.KeywordIntentParser()


class TestProjectQueryIntents:
    def _session(self):
        return S.InteractiveSession(chat_service=_FakeChat())

    def test_all_variants_parse_to_query(self):
        p = _parser()
        for text in ("现在有什么项目", "有哪些项目？", "我有哪些项目？",
                     "当前项目是什么？", "刚刚创建的项目呢？", "最近创建了什么？"):
            r = p.parse(text)
            assert r is not None, f"{text} 未识别"
            assert r.intent_type in (INT.INTENT_LIST_PROJECTS, INT.INTENT_CURRENT_PROJECT), \
                f"{text} → {r.intent_type}"

    def test_project_list_not_chat(self):
        """项目列表查询 → list_projects (绝不被 ChatService 接住)。"""
        chat = _FakeChat()
        s = S.InteractiveSession(chat_service=chat)
        _dispatch(s, "现在有什么项目")
        assert chat.calls == [] or "现在有什么项目" not in chat.calls

    def test_no_llm_error_for_project_query(self):
        """Factory Query 不出现 Provider 不可用错误。"""
        s = self._session()
        out = _dispatch(s, "现在有什么项目")
        assert "AI 对话服务当前不可用" not in out

    def test_recent_created_is_query_not_create(self):
        p = _parser()
        r = p.parse("最近创建了什么？")
        assert r.intent_type == INT.INTENT_CURRENT_PROJECT
        assert r.intent_type != INT.INTENT_CREATE_PROJECT


class TestRoutingCategories:
    def test_factory_query(self):
        p = _parser()
        assert p.parse("有哪些项目").intent_type == INT.INTENT_LIST_PROJECTS
        assert p.parse("当前项目是什么").intent_type == INT.INTENT_CURRENT_PROJECT

    def test_factory_action(self):
        p = _parser()
        assert p.parse("继续开发").intent_type == INT.INTENT_RESUME_PROJECT
        assert p.parse("生成工程计划").intent_type == INT.INTENT_PREPARE_PROJECT

    def test_general_chat_falls_to_llm(self):
        """普通问答 (intent None) → ChatService (LLM), 非 Query。"""
        chat = _FakeChat()
        s = S.InteractiveSession(chat_service=chat)
        _dispatch(s, "什么是 Docker")
        assert "什么是 Docker" in chat.calls

    def test_product_intent_to_discovery(self):
        p = _parser()
        assert p.parse("我想做一个app").intent_type == INT.INTENT_CREATE_PRODUCT


class TestProviderIndependence:
    def test_project_query_works_without_llm(self):
        """LLM 不可用: Factory Query 仍工作。"""
        s = S.InteractiveSession(chat_service=_FakeChat())
        out = _dispatch(s, "现在有什么项目")
        assert "AI 对话服务当前不可用" not in out

    def test_chat_reports_provider_error(self):
        """LLM 不可用: General Chat → 明确 Provider Error。"""
        from importlib import import_module
        CHAT = import_module("factory-console.session.chat")

        class _Broken:
            def _default_llm_fn(self):
                raise RuntimeError("anthropic api key missing: ANTHROPIC_API_KEY 未设置")

        cs = CHAT.ChatService(reasoning_provider=_Broken())
        out = cs.answer("什么是 Docker")
        assert "AI 对话服务当前不可用" in out
        assert "API Key" in out or "Provider" in out


class TestContext:
    def test_context_preserved(self):
        s = S.InteractiveSession(chat_service=_FakeChat())
        s.context.current_project = "P-777"
        out = _dispatch(s, "刚刚创建的项目呢？")
        assert "P-777" in out

    def test_last_created_fallback(self):
        s = S.InteractiveSession(chat_service=_FakeChat())
        s.context.metadata["last_created_project"] = "P-888"
        out = _dispatch(s, "最近创建了什么？")
        assert "P-888" in out


class TestSafety:
    def test_incomplete_create_project_guided(self):
        s = S.InteractiveSession(chat_service=_FakeChat())
        out = _dispatch(s, "创建项目")
        assert "还需要一些信息" in out
        assert "validation error" not in out.lower()
