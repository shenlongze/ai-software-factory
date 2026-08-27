"""S10-081 — Product Identity & Naming Intelligence 测试。

覆盖:
P0: 命名候选 (deterministic fallback, 无 LLM) + 改名 + 确认
P1: CLI rename 参数/路由
P2: 自然语言改名 intent + 复用 confirm_project
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
    return S.InteractiveSession(
        chat_service=_FakeChat(),
        # 确定性测试模式: 发现流程禁用 LLM (不依赖真实 LLM/网络)
        conversation_manager=CONV.ConversationManager(analyzer=None),
    )


class TestNamingIntelligence:
    def test_deterministic_name_from_idea(self):
        """无 LLM: 从 idea 提取有意义产品名 (非临时名)。"""
        name = NAMING.suggest_name("我想做一个命令行记账 App")
        assert name
        assert not name.startswith("未命名产品")
        assert "记账" in name

    def test_name_from_problem(self):
        name = NAMING.suggest_name("水利工程监控")
        assert name
        assert not name.startswith("未命名产品")

    def test_llm_used_when_available(self):
        """LLM 可用 → 使用 AI 建议。"""
        name = NAMING.suggest_name("我想做一个台球计分 App", llm_fn=lambda p, o="": "记分板")
        assert name == "记分板"

    def test_is_temp_name(self):
        assert NAMING.is_temp_name("未命名产品-123")
        assert not NAMING.is_temp_name("台球计分")

    def test_discovery_generates_name(self):
        """Discovery 确认前生成候选名 (不覆盖用户已给名)。"""
        s = _session()
        _dispatch(s, "我想做一个命令行记账 App")
        _dispatch(s, "记账麻烦")
        _dispatch(s, "个人用户")
        _dispatch(s, "记录支出")
        pi = s.conversation.product_intent
        assert pi is not None
        assert pi.name
        assert not pi.name.startswith("未命名产品")

    def test_user_can_rename_at_confirmation(self):
        """确认阶段输入新名 → 改名 (非取消)。"""
        s = _session()
        _dispatch(s, "我想做一个命令行记账 App")
        _dispatch(s, "记账麻烦")
        _dispatch(s, "个人用户")
        _dispatch(s, "记录支出")
        _dispatch(s, "账本精灵")  # 改名
        pi = s.conversation.product_intent
        assert pi is not None
        assert pi.name == "账本精灵"

    def test_cancel_word_still_cancels(self):
        """取消词 (n/取消) 仍取消 (验收 E 保留)。"""
        s = _session()
        _dispatch(s, "我想做一个app")
        _dispatch(s, "问题")
        _dispatch(s, "用户")
        _dispatch(s, "功能")
        _dispatch(s, "取消")
        assert s.conversation.product_intent is None


class TestRenameIntent:
    def test_variants_parse_to_rename(self):
        p = INT.KeywordIntentParser()
        for text, expected in (
            ("这个项目改名叫 记账助手", "记账助手"),
            ("把项目名称改成 台球计分", "台球计分"),
            ("项目改名 旅行账本", "旅行账本"),
        ):
            r = p.parse(text)
            assert r is not None, text
            assert r.intent_type == INT.INTENT_RENAME_PROJECT, f"{text} → {r.intent_type}"
            assert r.parameters.get("name") == expected

    def test_current_project_query_not_affected(self):
        p = INT.KeywordIntentParser()
        r = p.parse("刚刚创建的项目呢？")
        assert r.intent_type == INT.INTENT_CURRENT_PROJECT

    def test_rename_without_name_guides(self):
        """无新名 → 引导。"""
        s = _session()
        s.context.current_project = "P-1"
        out = _dispatch(s, "项目改名")
        assert "新名称" in out or "改名叫" in out

    def test_rename_without_project_guides(self):
        """无当前项目 → 引导。"""
        s = _session()
        out = _dispatch(s, "项目改名叫 记账助手")
        assert "当前没有正在开发的项目" in out


class TestNamingExtractionFixes:
    """2026-08-19 修复: 目标从句/目的词不再进入产品名。"""

    def test_goal_clause_truncated(self):
        """'目标是学习后端' 不再进入名字 (原产出 'Todo管理API目标是')。"""
        assert NAMING.suggest_name("我想开发一个 Todo 管理 API，目标是学习后端开发。") == "Todo管理"

    def test_help_phrase_not_truncated(self):
        """'帮助小团队管理客户关系' 是产品价值, 不是目标从句 (原产出 '我想做一')。"""
        name = NAMING.suggest_name("我想做一个帮助小团队管理客户关系的软件")
        assert name != "我想做一"
        assert "管理客户关系" in name

    def test_purpose_clause_after_comma_truncated(self):
        """'，目的是坚持学习' 从句截断 (原产出 '打卡记录学习时长目是坚持')。"""
        assert NAMING.suggest_name(
            "我想做一个打卡记录学习时长的 App，目的是坚持学习"
        ) == "打卡记录学习时长"

    def test_soft_purpose_word_truncated(self):
        """'，方便人事管理' 从句截断。"""
        assert NAMING.suggest_name(
            "我想开发一个员工考勤管理系统，方便人事管理"
        ) == "员工考勤管理"
