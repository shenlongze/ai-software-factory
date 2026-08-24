"""tests/console/test_discovery_guide.py — S10-101 产品发现引导体验契约测试。

设计: docs/sprint10/S10-101-discovery-guide-plan.md §1/§2
覆盖 (计划 §2 契约点 1-9):
1. 进度确定性: 无 LLM 两路径消息含 "产品定义 X/3:" + 生命周期行 + 字段 ✅/待填
2. 进度推进: 每答一问进度 +1; READY 3/3
3. 中间字段智能: mock LLM field_answer + smart_questions → 下一问 LLM 追问 (非机械);
   smart_questions 空 → 机械模板
4. 求助 LLM 路径: mock help_request + suggestions → 展示 → y → 填入 → 进度更新
5. 求助关键词兜底 (无 LLM): "给些建议" → DEFAULT_SUGGESTIONS → 确认填入
6. 求助不当字段: "没有想法" 不被收为字段内容 (答案不是 "没有想法")
7. 选择/自定义: y 全填 / "2" 单选 / "自定义内容" 直填
8. 无 LLM 零变化 (语义): 问题文本/字段顺序与 v1.1.21 一致 (仅加进度前缀)
9. 两路径行为一致: 同输入 (progress/help/smart) 两路径输出结构相同

模块级: discovery_guide 单元 (lifecycle_line/format_progress/enhanced_line/
HELP_KEYWORDS/DEFAULT_SUGGESTIONS)。全部测试 mock llm_fn 注入 / analyzer=None,
零真实 LLM 调用。
"""

from __future__ import annotations

import importlib

import pytest

DI = importlib.import_module("factory-console.session.discovery_intelligence")
DIS = importlib.import_module("factory-console.session.discovery")
CONV = importlib.import_module("factory-console.session.conversation")
GUIDE = importlib.import_module("factory-console.session.discovery_guide")

STATES = CONV.ConversationState
DS_STATES = DIS.DiscoveryState


# ------------------------------------------------------------------ 工具

@pytest.fixture(autouse=True)
def _no_provider(monkeypatch):
    """模拟无 LLM provider/key — 懒装配确定性失败 (规则兜底)。

    使 "无 LLM" 类测试不依赖外部环境 (有无 DEEPSEEK_API_KEY 均确定)。
    注入 mock analyzer 的测试不受影响 (不走默认装配)。
    """
    REASON = importlib.import_module("factory-console.session.reasoning")

    class _BrokenProvider:
        def _default_llm_fn(self):
            raise REASON.ReasoningUnavailable("无可用 provider (测试模拟)")

    monkeypatch.setattr(REASON, "ReasoningProvider", _BrokenProvider)


def _manager(**kw):
    return CONV.ConversationManager(**kw)


def _start(idea: str = "开始做个记账App", **kw):
    return DIS.DiscoverySession.start(idea, **kw)


def _mock_llm(payload):
    """固定返回 payload 的 mock llm_fn (记录调用)。"""
    calls: list[tuple[str, str]] = []

    def llm_fn(prompt, operation=""):
        calls.append((prompt, operation))
        return payload

    return llm_fn, calls


def _scripted_llm(*responses):
    """按调用顺序返回的 mock llm_fn (超出 → 最后一个)。"""
    calls: list[tuple[str, str]] = []

    def llm_fn(prompt, operation=""):
        calls.append((prompt, operation))
        idx = min(len(calls) - 1, len(responses) - 1)
        return responses[idx]

    return llm_fn, calls


def _full_analysis(**overrides) -> dict:
    """完整 product_description 输出 (全 7 字段 extraction — 直达 READY 用)。"""
    data = {
        "category": "product_description",
        "reason": "用户完整描述了产品想法",
        "extraction": {
            "problem": "个人记账麻烦, 缺乏顺手好用的记账工具",
            "user": "需要记账的个人用户",
            "core_features": ["收支记录", "分类统计", "月度报表"],
            "name": "简记",
            "platform": "mobile",
            "usage_scenarios": "日常消费记账、月底对账",
            "mvp_scope": "第一版只做收支记录和分类统计",
            "non_functional_requirements": "数据本地保存, 响应快",
        },
        "missing_reasons": {},
        "smart_questions": [],
        "proactive": {},
        "understanding": "我理解你要做一个记账 App, 给需要记账的个人用户用",
        "suggestions": {},
    }
    data.update(overrides)
    return data


def _two_missing_analysis() -> dict:
    """只填 problem 的 product_description (缺 user + core_features — 中间字段场景)。"""
    data = _full_analysis()
    data["extraction"] = {
        "problem": "个人记账麻烦, 缺乏顺手好用的记账工具",
        "user": "",
        "core_features": [],
        "name": "",
        "platform": "",
        "usage_scenarios": "",
        "mvp_scope": "",
        "non_functional_requirements": "",
    }
    data["missing_reasons"] = {
        "user": "输入里没有提到目标用户",
        "core_features": "输入里没有提到核心功能",
    }
    data["smart_questions"] = ["主要给谁用呢? (例如: 个人用户 / 学生 / 小商家)"]
    return data


def _field_answer(user: str = "给个人用户用", *, smart: list[str] | None = None,
                  missing_reasons: dict | None = None) -> dict:
    """field_answer 输出 (回答 user; smart 给下一问核心功能智能追问/空 → 机械)。"""
    return {
        "category": "field_answer",
        "reason": "用户回答了上一轮问题",
        "extraction": {"user": user},
        "missing_reasons": missing_reasons or {},
        "smart_questions": smart or [],
        "proactive": {},
        "understanding": "",
        "suggestions": {},
    }


def _help_analysis(**overrides) -> dict:
    """help_request 输出 (LLM 建议 — 契约点 4)。"""
    data = {
        "category": "help_request",
        "reason": "用户在求建议, 不是给信息",
        "extraction": {},
        "missing_reasons": {},
        "smart_questions": [],
        "proactive": {},
        "understanding": "",
        "suggestions": {
            "field": "user",
            "items": ["个人用户", "小商家"],
            "note": "想清楚给谁用, 后续功能才好定",
        },
    }
    data.update(overrides)
    return data


def _body(msg: str) -> str:
    """去掉进度前缀 (生命周期行/产品定义行/增强可选行) → 消息正文 (契约点 8 用)。"""
    lines = msg.split("\n")
    body: list[str] = []
    started = False
    for line in lines:
        if not started and (
            line.startswith("流程:")
            or line.startswith("产品定义")
            or line.startswith("增强(可选):")
        ):
            continue
        started = True
        body.append(line)
    return "\n".join(body)


# ================================================================== 模块级: discovery_guide 单元

class TestGuideModule:
    def test_lifecycle_line_default(self):
        assert GUIDE.lifecycle_line() == (
            "流程: [发现]→确认→创建→PRD→工程→开发 (当前: 发现)"
        )

    def test_lifecycle_line_current(self):
        assert GUIDE.lifecycle_line("确认") == (
            "流程: 发现→[确认]→创建→PRD→工程→开发 (当前: 确认)"
        )

    def test_lifecycle_line_unknown_stage(self):
        # 未知阶段 → 不加 [ ] 高亮, 仅附当前标注 (不抛)
        assert GUIDE.lifecycle_line("未知") == (
            "流程: 发现→确认→创建→PRD→工程→开发 (当前: 未知)"
        )

    def test_lifecycle_constant(self):
        assert GUIDE.LIFECYCLE_LINE == "流程: 发现→确认→创建→PRD→工程→开发"

    def test_format_progress(self):
        assert GUIDE.format_progress(["problem", "user"], ["core_features"]) == (
            "产品定义 2/3: 产品解决什么问题✅ 目标用户✅ 核心功能待填"
        )

    def test_format_progress_zero(self):
        assert GUIDE.format_progress([], ["problem", "user", "core_features"]) == (
            "产品定义 0/3: 产品解决什么问题待填 目标用户待填 核心功能待填"
        )

    def test_format_progress_full(self):
        assert GUIDE.format_progress(
            ["problem", "user", "core_features"], []
        ) == "产品定义 3/3: 产品解决什么问题✅ 目标用户✅ 核心功能✅"

    def test_format_progress_pending_wins_on_overlap(self):
        # pending 权威 (防御: 调用方两集合重复) — 不双计数
        assert GUIDE.format_progress(
            ["problem", "user"], ["problem", "core_features"]
        ) == "产品定义 1/3: 产品解决什么问题待填 目标用户✅ 核心功能待填"

    def test_enhanced_line_all_pending(self):
        assert GUIDE.enhanced_line({}) == (
            "增强(可选): 使用场景待填 · MVP范围待填 · 非功能要求待填"
        )

    def test_enhanced_line_partial(self):
        assert GUIDE.enhanced_line({"usage_scenarios": "日常使用"}) == (
            "增强(可选): 使用场景✅ · MVP范围待填 · 非功能要求待填"
        )

    def test_enhanced_line_all_filled_omitted(self):
        assert GUIDE.enhanced_line({
            "usage_scenarios": "x", "mvp_scope": "y", "non_functional_requirements": "z",
        }) == ""

    def test_help_keywords_include_core(self):
        for kw in ("给些建议", "给点意见", "没有想法", "没思路", "你看着办",
                   "帮我出主意", "你来定", "推荐一下", "有什么建议"):
            assert kw in GUIDE.HELP_KEYWORDS

    def test_default_suggestions_cover_required_fields(self):
        # 计划 §1.1 例: problem/core_features ≥3 条, user 2 条 (确定性兜底非空)
        for field in ("problem", "user", "core_features"):
            assert GUIDE.DEFAULT_SUGGESTIONS.get(field)
        assert len(GUIDE.DEFAULT_SUGGESTIONS["problem"]) >= 3
        assert len(GUIDE.DEFAULT_SUGGESTIONS["core_features"]) >= 3

    def test_default_suggestions_cover_enhanced_fields(self):
        for field in ("usage_scenarios", "mvp_scope", "non_functional_requirements"):
            assert GUIDE.DEFAULT_SUGGESTIONS.get(field)


# ================================================================== 1. 进度确定性 (无 LLM, 两路径)

class TestProgressDeterministic:
    def test_conversation_messages_include_progress(self):
        """契约点 1: conversation 无 LLM 消息含进度行 + 生命周期行 + 字段 ✅/待填。"""
        mgr = _manager(analyzer=None)
        r = mgr.handle("我想做一个台球计分APP")
        assert "产品定义 0/3:" in r.message
        assert "流程: [发现]→确认→创建→PRD→工程→开发 (当前: 发现)" in r.message
        assert "产品解决什么问题待填" in r.message
        assert "✅" not in r.message
        r = mgr.handle("台球计分麻烦")
        assert "产品定义 1/3:" in r.message
        assert "产品解决什么问题✅" in r.message
        assert "目标用户待填" in r.message

    def test_discovery_session_messages_include_progress(self):
        """契约点 1: DiscoverySession 无 LLM 消息含进度行 + 生命周期行 + 增强可选。"""
        s = _start(analyzer=None)
        r = s.process_user_input("台球计分麻烦")
        assert "产品定义 1/3:" in r["message"]
        assert "流程: [发现]→确认→创建→PRD→工程→开发 (当前: 发现)" in r["message"]
        assert "产品解决什么问题✅" in r["message"]
        assert "增强(可选):" in r["message"]


# ================================================================== 2. 进度推进 (READY 3/3)

class TestProgressAdvance:
    def test_conversation_ready_3_3(self):
        """契约点 2: 每答一问进度 +1; READY 3/3 + lifecycle(current=确认)。"""
        mgr = _manager(analyzer=None)
        mgr.handle("我想做一个台球计分APP")
        r = mgr.handle("台球计分麻烦")
        assert "产品定义 1/3:" in r.message
        r = mgr.handle("台球爱好者")
        assert "产品定义 2/3:" in r.message
        r = mgr.handle("计分、比赛记录")
        assert r.state == STATES.PRODUCT_CONFIRMATION
        assert "产品定义 3/3:" in r.message
        assert "核心功能✅" in r.message
        assert "流程: 发现→[确认]→创建→PRD→工程→开发 (当前: 确认)" in r.message

    def test_discovery_session_ready_3_3(self):
        """契约点 2: DiscoverySession 全字段答完 → READY 3/3 + current=确认。"""
        s = _start(analyzer=None)
        r = None
        for text in ("台球计分麻烦", "台球爱好者", "计分、比赛记录",
                     "球房", "只做计分", "无特殊要求"):
            r = s.process_user_input(text)
        assert r is not None and r["state"] == DS_STATES.READY_FOR_CONFIRMATION
        assert "产品定义 3/3:" in r["message"]
        assert "产品解决什么问题✅" in r["message"] and "核心功能✅" in r["message"]
        assert "流程: 发现→[确认]→创建→PRD→工程→开发 (当前: 确认)" in r["message"]


# ================================================================== 3. 中间字段智能 (field_answer → smart_questions[0])

class TestIntermediateFieldSmart:
    def test_conversation_field_answer_smart_next_question(self):
        """契约点 3: field_answer 后下一问用 LLM smart_questions[0] (非机械)。"""
        llm_fn, calls = _scripted_llm(
            _two_missing_analysis(),
            _field_answer(smart=["核心功能想先覆盖哪些? (比如记账、统计)"],
                          missing_reasons={"core_features": "还没提到核心功能"}),
        )
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        r1 = mgr.handle("我想做个记账App, 只解决记账麻烦")
        assert "主要给谁用呢" in r1.message  # 第一问 (缺 user)
        r2 = mgr.handle("给个人用户用")
        assert mgr.product_intent.user == "给个人用户用"
        assert mgr._product_pending == ["core_features"]
        # 智能追问 (非机械)
        assert "核心功能想先覆盖哪些" in r2.message
        assert "(为什么还问: 还没提到核心功能)" in r2.message
        assert "(缺失字段: core_features)" not in r2.message

    def test_conversation_field_answer_empty_smart_mechanical(self):
        """契约点 3: smart_questions 空 → 机械模板 (诚实降级)。"""
        llm_fn, calls = _scripted_llm(_two_missing_analysis(), _field_answer())
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        mgr.handle("我想做个记账App, 只解决记账麻烦")
        r2 = mgr.handle("给个人用户用")
        assert mgr.product_intent.user == "给个人用户用"
        assert mgr._product_pending == ["core_features"]
        # 机械模板 (无智能追问)
        assert "核心功能有哪些" in r2.message
        assert "(缺失字段: core_features)" in r2.message

    def test_discovery_field_answer_smart_next_question(self):
        """契约点 3: DiscoverySession field_answer 后下一问用 LLM smart_questions[0]。"""
        llm_fn, calls = _scripted_llm(
            _two_missing_analysis(),
            _field_answer(smart=["核心功能想先覆盖哪些? (比如记账、统计)"],
                          missing_reasons={"core_features": "还没提到核心功能"}),
        )
        session = _start(idea="开始做个记账App",
                         analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        assert session._pending_fields[0] == "user"
        r = session.process_user_input("给个人用户用")
        assert r["question"].field == "core_features"
        assert "核心功能想先覆盖哪些" in r["message"]
        assert "(为什么还问: 还没提到核心功能)" in r["message"]

    def test_discovery_field_answer_empty_smart_mechanical(self):
        """契约点 3: DiscoverySession smart_questions 空 → 机械模板。"""
        llm_fn, calls = _scripted_llm(_two_missing_analysis(), _field_answer())
        session = _start(idea="开始做个记账App",
                         analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        r = session.process_user_input("给个人用户用")
        assert r["question"].field == "core_features"
        assert "核心功能有哪些? (用逗号或顿号分隔)" in r["message"]


# ================================================================== 4. 求助 LLM 路径

class TestHelpLlmPath:
    def test_conversation_help_llm_path(self):
        """契约点 4: 求助 (非关键词) → LLM help_request + suggestions → 展示 → y 填入。"""
        llm_fn, calls = _scripted_llm(
            _two_missing_analysis(),
            _help_analysis(),
        )
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        mgr.handle("我想做个记账App, 只解决记账麻烦")
        assert mgr._product_pending == ["user", "core_features"]
        r = mgr.handle("帮我想想")  # 非关键词 → 走 LLM help_request
        assert r is not None
        assert "当前缺目标用户 — 建议方向:" in r.message
        assert "1. 个人用户" in r.message
        assert "2. 小商家" in r.message
        assert "想清楚给谁用" in r.message
        assert mgr._suggestion_proposal == {"field": "user", "items": ["个人用户", "小商家"]}
        assert mgr.product_intent.user is None  # 未确认前不当字段
        r2 = mgr.handle("y")
        assert mgr.product_intent.user == "个人用户、小商家"
        assert mgr._suggestion_proposal is None
        assert "产品定义 2/3:" in r2.message  # 进度推进 (problem 已由初始描述填入)

    def test_discovery_help_llm_path(self):
        """契约点 4: DiscoverySession 求助 → LLM help_request + suggestions → y 填入。"""
        llm_fn, calls = _scripted_llm(
            _two_missing_analysis(),
            _help_analysis(),
        )
        session = _start(idea="开始做个记账App",
                         analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        r = session.process_user_input("帮我想想")
        assert "当前缺目标用户 — 建议方向:" in r["message"]
        assert "1. 个人用户" in r["message"]
        assert session._suggestion_proposal == {"field": "user", "items": ["个人用户", "小商家"]}
        assert session.product_intent.user is None
        r2 = session.process_user_input("y")
        assert session.product_intent.user == "个人用户、小商家"
        assert "产品定义 2/3:" in r2["message"]

    def test_llm_help_empty_suggestions_falls_back_defaults(self):
        """契约点 4/5: LLM help_request 但 suggestions 空 → DEFAULT_SUGGESTIONS 兜底。"""
        llm_fn, calls = _scripted_llm(
            _two_missing_analysis(),
            _help_analysis(suggestions={}),
        )
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        mgr.handle("我想做个记账App, 只解决记账麻烦")
        r = mgr.handle("帮我想想")
        assert "当前缺目标用户 — 建议方向:" in r.message
        assert "1. 个人用户" in r.message  # DEFAULT_SUGGESTIONS["user"] 兜底


# ================================================================== 5. 求助关键词兜底 (无 LLM)

class TestHelpKeywordFallback:
    def test_conversation_keyword_fallback(self):
        """契约点 5: "给些建议" 无 LLM → DEFAULT_SUGGESTIONS → y 填入。"""
        mgr = _manager(analyzer=None)
        mgr.handle("我想做一个台球计分APP")
        r = mgr.handle("给些建议")
        assert "当前缺产品解决什么问题 — 建议方向:" in r.message
        assert "1. 现有工具太繁琐" in r.message
        assert "2. 效率低/耗时长" in r.message
        assert "3. 信息分散难管理" in r.message
        r2 = mgr.handle("y")
        assert mgr.product_intent.problem == "现有工具太繁琐、效率低/耗时长、信息分散难管理"
        assert "产品定义 1/3:" in r2.message
        assert mgr._product_pending == ["user", "core_features"]

    def test_discovery_keyword_fallback(self):
        """契约点 5: DiscoverySession "给些建议" → 默认建议 → y 填入。"""
        s = _start(analyzer=None)
        r = s.process_user_input("给些建议")
        assert "当前缺产品解决什么问题 — 建议方向:" in r["message"]
        assert "1. 现有工具太繁琐" in r["message"]
        r2 = s.process_user_input("y")
        assert s.product_intent.problem == "现有工具太繁琐、效率低/耗时长、信息分散难管理"
        assert "产品定义 1/3:" in r2["message"]
        assert s._pending_fields[0] == "user"


# ================================================================== 6. 求助不当字段

class TestHelpNotField:
    def test_conversation_help_not_swallowed(self):
        """契约点 6: "没有想法" 不被收为字段内容 (答案不是 "没有想法")。"""
        mgr = _manager(analyzer=None)
        mgr.handle("我想做一个台球计分APP")
        r = mgr.handle("没有想法")
        assert mgr.product_intent.problem is None
        assert "建议方向" in r.message
        r2 = mgr.handle("y")
        assert mgr.product_intent.problem != "没有想法"
        assert mgr.product_intent.problem.startswith("现有工具太繁琐")

    def test_discovery_help_not_swallowed(self):
        """契约点 6: DiscoverySession "没想法" 不当字段。"""
        s = _start(analyzer=None)
        r = s.process_user_input("没想法")
        assert s.product_intent.problem is None
        assert "建议方向" in r["message"]
        r2 = s.process_user_input("y")
        assert s.product_intent.problem != "没想法"
        assert s.product_intent.problem.startswith("现有工具太繁琐")


# ================================================================== 7. 选择/自定义

class TestSuggestionChoice:
    def test_single_selection(self):
        """契约点 7: "2" → 单选第二项。"""
        mgr = _manager(analyzer=None)
        mgr.handle("我想做一个台球计分APP")
        mgr.handle("给些建议")
        r = mgr.handle("2")
        assert mgr.product_intent.problem == "效率低/耗时长"
        assert "产品定义 1/3:" in r.message

    def test_custom_value(self):
        """契约点 7: "自定义内容" → 直填 (不被建议列表限制)。"""
        mgr = _manager(analyzer=None)
        mgr.handle("我想做一个台球计分APP")
        mgr.handle("给些建议")
        r = mgr.handle("手动记账太麻烦")
        assert mgr.product_intent.problem == "手动记账太麻烦"
        assert "产品定义 1/3:" in r.message

    def test_custom_value_core_features(self):
        """契约点 7: core_features 建议自定义 → 顿号解析为列表。"""
        mgr = _manager(analyzer=None)
        mgr.handle("我想做一个台球计分APP")
        mgr.handle("台球计分麻烦")
        mgr.handle("台球爱好者")
        mgr.handle("给些建议")
        r = mgr.handle("计分、统计、导出")
        assert mgr.product_intent.core_features == ["计分", "统计", "导出"]
        assert r.state == STATES.PRODUCT_CONFIRMATION
        assert "产品定义 3/3:" in r.message


# ================================================================== 8. 无 LLM 零变化 (语义)

class TestNoLlmSemantics:
    def test_conversation_question_text_and_order(self):
        """契约点 8: 非求助输入 → 问题文本/字段顺序与 v1.1.21 一致 (仅加进度前缀)。"""
        mgr = _manager(analyzer=None)
        r1 = mgr.handle("我想做一个台球计分APP")
        assert _body(r1.message) == (
            "我先帮你梳理一下。\n"
            "这个产品最主要想解决什么痛点?\n"
            "比如: 用户遇到什么困难? 为什么现在的方法不好? (缺失字段: problem)"
        )
        r2 = mgr.handle("台球计分麻烦")
        assert _body(r2.message) == (
            "目标用户是谁? (主要给谁用, 例如: 个人用户 / 学生 / 中小企业) "
            "(缺失字段: user)"
        )
        r3 = mgr.handle("台球爱好者")
        assert _body(r3.message) == (
            "核心功能有哪些? (用逗号或顿号分隔, 例如: 记账、统计、导出) "
            "(缺失字段: core_features)"
        )
        r4 = mgr.handle("计分、比赛记录")
        assert r4.state == STATES.PRODUCT_CONFIRMATION
        assert "确认创建这个产品? (y/N)" in _body(r4.message)

    def test_discovery_question_text_and_order(self):
        """契约点 8: DiscoverySession 机械追问文本与 v1.1.21 一致 (仅加进度前缀)。"""
        s = _start(analyzer=None)
        r = s.process_user_input("台球计分麻烦")
        assert _body(r["message"]) == "主要给谁使用?"
        r = s.process_user_input("台球爱好者")
        assert _body(r["message"]) == "核心功能有哪些? (用逗号或顿号分隔)"
        # 字段顺序不变 (必填 → 增强): 已答 problem/user → 下一问 core_features
        assert s._pending_fields[:3] == ["core_features", "usage_scenarios", "mvp_scope"]

    def test_non_help_input_not_triggered(self):
        """契约点 8: 正常字段回答不触发求助流 (进度前缀外零行为变化)。"""
        mgr = _manager(analyzer=None)
        mgr.handle("我想做一个台球计分APP")
        r = mgr.handle("台球计分太麻烦")
        assert mgr.product_intent.problem == "台球计分太麻烦"
        assert "建议方向" not in r.message
        assert r.message.count("产品定义") == 1  # 仅进度行一处


# ================================================================== 9. 两路径行为一致

class TestBothPathsConsistent:
    def test_same_input_help_structure(self):
        """契约点 9: 同求助输入 → 两路径输出结构相同 (进度/建议/字段中文名)。"""
        mgr = _manager(analyzer=None)
        mgr.handle("我想做一个记账App")
        c_resp = mgr.handle("给些建议")
        s = _start(idea="开始做个记账App", analyzer=None)
        d_resp = s.process_user_input("给些建议")
        for msg in (c_resp.message, d_resp["message"]):
            assert "产品定义 0/3:" in msg
            assert "流程: [发现]→确认→创建→PRD→工程→开发 (当前: 发现)" in msg
            assert "当前缺产品解决什么问题 — 建议方向:" in msg
            assert "1. 现有工具太繁琐" in msg
        c2 = mgr.handle("y")
        d2 = s.process_user_input("y")
        assert c2.message.split("\n")[1].startswith("产品定义 1/3:")
        assert d2["message"].split("\n")[1].startswith("产品定义 1/3:")
        assert mgr.product_intent.problem == s.product_intent.problem

    def test_same_input_progress_structure(self):
        """契约点 9: 同普通输入 → 两路径进度行结构一致 (X/3 与字段标记)。"""
        mgr = _manager(analyzer=None)
        mgr.handle("我想做一个记账App")
        s = _start(idea="开始做个记账App", analyzer=None)
        # 第一问后各自答 problem → 进度 1/3
        c_resp = mgr.handle("手动记账麻烦")
        d_resp = s.process_user_input("手动记账麻烦")
        assert c_resp.message.split("\n")[1] == d_resp["message"].split("\n")[1]
        assert "产品定义 1/3: 产品解决什么问题✅ 目标用户待填 核心功能待填" in c_resp.message
        assert c_resp.message.split("\n")[1] in d_resp["message"]

    def test_same_input_smart_structure(self):
        """契约点 9: 同 LLM 智能追问输入 → 两路径下一问结构一致。"""
        llm_fn, calls = _scripted_llm(_two_missing_analysis(), _two_missing_analysis())
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        c_resp = mgr.handle("我想做个记账App, 只解决记账麻烦")
        session = DIS.DiscoverySession.start(
            "开始做个记账App", analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn)
        )
        d_q = session.questions[-1]
        # 两路径都问最重要缺失字段 (user) — 智能追问文本一致
        assert "主要给谁用呢" in c_resp.message
        assert "主要给谁用呢" in d_q.question
        assert session._pending_fields[0] == "user" and mgr._product_pending[0] == "user"


# ================================================================== 冒烟: analyzer help_request 契约

class TestAnalyzerHelpRequestContract:
    def test_help_request_valid_category(self):
        """S10-101: help_request 为合法类别 (analyzer schema 接受)。"""
        assert "help_request" in DI.VALID_CATEGORIES
        # 优先级: 控制指令 > 查询 > 求助 > 字段回答 > 产品描述
        order = list(DI.VALID_CATEGORIES)
        assert order.index("control") < order.index("query") < order.index("help_request") \
            < order.index("field_answer") < order.index("product_description")

    def test_suggestions_normalized(self):
        """S10-101: suggestions 契约归一化 (field/items/note)。"""
        llm_fn, _ = _mock_llm(_help_analysis())
        a = DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn).analyze("帮我想想")
        assert a.suggestions == {
            "field": "user",
            "items": ["个人用户", "小商家"],
            "note": "想清楚给谁用, 后续功能才好定",
        }

    def test_suggestions_missing_default_empty(self):
        """S10-101: suggestions 缺省 → 空 dict (诚实降级, 上层用默认建议)。"""
        llm_fn, _ = _mock_llm(_full_analysis())  # 无 suggestions 键
        a = DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn).analyze("完整描述")
        assert a.suggestions == {}

    def test_suggestions_items_string_normalized(self):
        """S10-101: suggestions.items 字符串 → 列表化。"""
        llm_fn, _ = _mock_llm(_help_analysis(suggestions={"field": "user", "items": "个人用户"}))
        a = DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn).analyze("帮我想想")
        assert a.suggestions["items"] == ["个人用户"]

    def test_prompt_contains_help_request_and_suggestions(self):
        """S10-101: prompt 含 help_request 类别 + suggestions 输出契约 + 求助规则。"""
        llm_fn, calls = _mock_llm(_help_analysis())
        DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn).analyze("帮我想想")
        prompt = calls[0][0]
        assert "help_request" in prompt
        assert '"suggestions"' in prompt
        assert "给些建议" in prompt
        assert "3-5 条方向性建议" in prompt
