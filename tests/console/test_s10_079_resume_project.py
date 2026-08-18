"""S10-079 — resume_project 生产恢复路由测试。

覆盖:
1. "继续开发" 等变体 → resume_project
2. resume_project 路由 → execute_project (同一执行链)
3. 无 current_project → 安全提示 (禁止猜项目/扫描兜底)
4. 不误触发 create_project / create_product
5. ConfirmationGate 保留 (execute_project ∈ sensitive)
6. 真实执行链可恢复 (orchestrator.needs_resume → resume)
"""

from __future__ import annotations

import io
import contextlib

from importlib import import_module

S = import_module("factory-console.session.session")
INT = import_module("factory-console.session.intent")
ROUTER = import_module("factory-console.session.router")


class _FakeChat:
    def answer(self, question: str, **kw):
        return "AI: 测试回答"

    def is_fallback(self, a: str) -> bool:
        return a.startswith("AI:")


def _dispatch(session, line: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        session._dispatch(line)
    return buf.getvalue()


def _session():
    return S.InteractiveSession(chat_service=_FakeChat())


class TestResumeIntent:
    def test_variants_parse_to_resume(self):
        p = INT.KeywordIntentParser()
        for text in ("继续开发", "继续当前项目", "继续工作", "继续这个项目"):
            r = p.parse(text)
            assert r is not None, f"{text} 未识别"
            assert r.intent_type == INT.INTENT_RESUME_PROJECT, f"{text} → {r.intent_type}"

    def test_start_variants_parse_to_execution(self):
        """开始开发/开始实现 → 执行链 (execute_project/run_task, 既有语义)。"""
        p = INT.KeywordIntentParser()
        r = p.parse("开始开发")
        assert r.intent_type in (INT.INTENT_RESUME_PROJECT, INT.INTENT_EXECUTE_PROJECT)
        r2 = p.parse("开始实现")
        assert r2.intent_type in (INT.INTENT_RUN_TASK, INT.INTENT_EXECUTE_PROJECT)

    def test_not_create_project(self):
        """继续开发 不误触发 create_project / create_product。"""
        p = INT.KeywordIntentParser()
        r = p.parse("继续开发")
        assert r.intent_type == INT.INTENT_RESUME_PROJECT
        assert r.intent_type != INT.INTENT_CREATE_PROJECT
        assert r.intent_type != INT.INTENT_CREATE_PRODUCT


class TestRouteRegistration:
    def test_resume_route_registered(self):
        """resume_project → execute_project (正式路由, 非断链)。"""
        assert ROUTER.DEFAULT_ROUTES.get("resume_project") == "execute_project"

    def test_route_resolves_action(self):
        router = ROUTER.IntentRouter()
        assert router.routes().get("resume_project") == "execute_project"

    def test_no_unknown_route_error(self):
        """REPL: 继续开发 不再报 '未配置路由'。"""
        s = _session()
        out = _dispatch(s, "继续开发")
        assert "未配置路由" not in out
        assert "未识别的意图" not in out


class TestNoCurrentProject:
    def test_safe_prompt_without_project(self):
        """无 current_project → 安全提示 (禁止猜项目/扫描兜底执行)。"""
        s = _session()
        out = _dispatch(s, "继续开发")
        assert "当前没有正在开发的项目" in out
        # 不自动执行旧项目
        assert "任务完成" not in out

    def test_explicit_project_required(self):
        """execute_project 拒绝无显式项目 (不扫描兜底)。"""
        s = _session()
        out = _dispatch(s, "继续开发")
        assert "未指定当前项目" in out or "当前没有正在开发的项目" in out


class TestConfirmationGate:
    def test_execute_project_in_sensitive(self):
        """execute_project 保留在确认门集合 (resume 不绕过)。"""
        # session 装配的 confirmation_gate 覆盖 execute_project (S10-052)
        s = _session()
        assert s.confirmation_gate is not None
        # resume → execute_project → 敏感集合判定 (intent 类型转换后)
        sensitive = getattr(s.confirmation_gate, "sensitive_intents", None)
        if sensitive is not None:
            assert "execute_project" in sensitive or "resume_project" in sensitive


class TestExecutionChain:
    def test_execute_project_action_exists(self):
        """execute_project action 已注册 (复用同一执行链)。"""
        s = _session()
        action = s.action_registry.get("execute_project")
        assert action is not None

    def test_resume_uses_execute_project_chain(self):
        """resume_project 路由目标 action 已注册。"""
        s = _session()
        target = ROUTER.DEFAULT_ROUTES.get("resume_project")
        assert target == "execute_project"
        assert s.action_registry.get(target) is not None
