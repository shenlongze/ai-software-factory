"""tests/console/test_discovery_session_llm.py — S10-100 DiscoverySession 同步 LLM 化契约测试。

设计: docs/sprint10/S10-100-discovery-session-llm-plan.md §2/§4
覆盖 (计划 §4 契约点 1-9):
1. LLM 一次产出: mock extraction 全 7 字段 → start("开始做个记账App") → READY 直达,
   消息含理解摘要 + 建议名称 (非"这个产品解决什么问题?"第一问)
2. 智能追问带理由: 部分提取 (缺 user) → 追问 1 条含 "(为什么还问:" + 非机械
3. 回答并入不覆盖 (v1.1.19 边界): 对追问的回答 → field_answer → 只填对应字段,
   已填不覆盖
4. 理解摘要 + 主动分析: READY 消息含 "我理解你要做" + "主动建议:"
5. 无 LLM 零变化: analyzer=None/装配失败 → start/process_user_input 行为与既有
   108 tests 一致 (规则逐字段)
6. 控制/查询不当字段: category=control(取消) → cancel; control(非取消)/query →
   不吞为字段, 重问当前问题
7. 非法 LLM 输出: 非 JSON/schema 缺/调用异常 → 规则兜底, 不崩溃
8. 持久化 round-trip: 新字段 (_last_system_question/_ai_generated/_understanding/
   _proactive) save/load 完整 + 旧文件缺省兼容
9. 命名: LLM 可用+临时名 → 候选设名+展示; 无 LLM → 临时名保留

模块级: DiscoveryIntentAnalyzer 8 字段契约扩展 (新键归一化/缺省/ conversation 只读 5 键)。
全部测试 mock llm_fn 注入, 零真实 LLM 调用。
"""

from __future__ import annotations

import importlib
import json

import pytest

DIS = importlib.import_module("factory-console.session.discovery")
DI = importlib.import_module("factory-console.session.discovery_intelligence")
CONV = importlib.import_module("factory-console.session.conversation")

STATES = DIS.DiscoveryState


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

def _start(idea: str = "开始做个记账App", **kw):
    return DIS.DiscoverySession.start(idea, **kw)


def _assert_first_question_guided(session):
    """S10-101 验收: 首问 question 带进度/生命周期前缀 (且问题本体保留)。"""
    q = session.questions[0].question
    assert "流程:" in q and "产品定义 0/3:" in q
    assert "这个产品解决什么问题?" in q


def _full_analysis(**overrides) -> dict:
    """完整 product_description 输出 (全 7 字段 extraction — 契约点 1 用)。

    name 留空 → 触发 LLM-gated 命名 (契约点 9 分支)。
    """
    data = {
        "category": "product_description",
        "reason": "用户完整描述了产品想法",
        "extraction": {
            "problem": "个人记账麻烦, 缺乏顺手好用的记账工具",
            "user": "需要记账的个人用户",
            "core_features": ["收支记录", "分类统计", "月度报表"],
            "name": "",
            "platform": "mobile",
            "usage_scenarios": "日常消费记账、月底对账",
            "mvp_scope": "第一版只做收支记录和分类统计",
            "non_functional_requirements": "数据本地保存, 响应快",
        },
        "missing_reasons": {},
        "smart_questions": [],
        "proactive": {
            "platform": "mobile",
            "competitors": "随手记 / 鲨鱼记账",
            "scope": "MVP: 收支记录 + 分类统计",
            "notes": "可考虑多端同步",
        },
        "understanding": (
            "我理解你要做一个记账 App, 给需要记账的个人用户用, "
            "核心是收支记录/分类统计/月度报表"
        ),
    }
    data.update(overrides)
    return data


def _partial_analysis() -> dict:
    """缺 user 的 product_description (缺 1 必填 — 智能追问场景)。

    只填 problem/core_features, 增强字段也缺 → 回答 user 后仍走增强字段。
    """
    data = _full_analysis()
    data["extraction"] = {
        "problem": "个人记账麻烦, 缺乏顺手好用的记账工具",
        "user": "",
        "core_features": ["收支记录", "分类统计"],
        "name": "",
        "platform": "",
        "usage_scenarios": "",
        "mvp_scope": "",
        "non_functional_requirements": "",
    }
    data["missing_reasons"] = {"user": "输入里没有提到目标用户"}
    data["smart_questions"] = ["主要给谁用呢? (例如: 个人 / 学生 / 小商家)"]
    return data


def _field_answer(user: str = "给个人用户用") -> dict:
    """对智能追问的回答 (field_answer — 只填对应字段, 不覆盖其它)。"""
    return {
        "category": "field_answer",
        "reason": "用户回答了上一轮问题",
        "extraction": {"user": user},
        "missing_reasons": {},
        "smart_questions": [],
        "proactive": {},
        "understanding": "",
    }


def _control_analysis(reason: str = "用户发出控制指令") -> dict:
    return {
        "category": "control",
        "reason": reason,
        "extraction": {},
        "missing_reasons": {},
        "smart_questions": [],
        "proactive": {},
        "understanding": "",
    }


def _query_analysis() -> dict:
    return {
        "category": "query",
        "reason": "用户想查看项目列表",
        "extraction": {},
        "missing_reasons": {},
        "smart_questions": [],
        "proactive": {},
        "understanding": "",
    }


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


def _names_text() -> str:
    """suggest_names 解析的命名候选文本 (契约点 9)。"""
    return "记账本\n账本管家\n随手记"


# ================================================================== 1. LLM 一次产出 (验收 1)

class TestLlmOneShot:
    def test_full_idea_direct_to_ready(self):
        """计划 §4-1: 全 7 字段 extraction → start 直达 READY + 理解摘要 + 建议名称。"""
        llm_fn, calls = _scripted_llm(_full_analysis(), _names_text())
        session = _start(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))

        assert session.current_state == STATES.READY_FOR_CONFIRMATION
        assert session.required_filled()
        assert session._ai_generated is True
        assert session._understanding and "我理解你要做" in session._understanding
        # 建议名称: LLM-gated 命名 (候选1设名 + 展示)
        assert session.product_intent.name == "记账本"
        assert session._name_candidates == ["记账本", "账本管家", "随手记"]
        # 消息: 理解摘要首行 + to_text() + 建议名称候选 + 主动建议 + 确认提示
        msg = session._ready_response()["message"]
        assert "我理解你要做" in msg
        assert "建议名称: 记账本" in msg
        assert "主动建议" in msg
        assert "请确认产品需求" in msg
        # 非机械第一问
        assert "这个产品解决什么问题?" not in msg
        # 结构化提取已并入 (7 字段)
        pi = session.product_intent
        assert pi.problem and "记账" in pi.problem
        assert pi.user and "个人用户" in pi.user
        assert pi.core_features == ["收支记录", "分类统计", "月度报表"]
        assert pi.platform == "mobile"
        assert session.answers["usage_scenarios"] == "日常消费记账、月底对账"
        assert session.answers["mvp_scope"] == "第一版只做收支记录和分类统计"
        assert session.answers["non_functional_requirements"] == "数据本地保存, 响应快"
        # LLM 确实被调用: discovery_intent + naming (同一 llm_fn)
        assert calls[0][1] == "discovery_intent"
        assert calls[1][1] == "naming"


# ================================================================== 2. 智能追问带理由 (验收 2)

class TestSmartQuestion:
    def test_partial_idea_smart_question_with_reason(self):
        """计划 §4-2: 部分提取 (缺 user) → 追问 1 条含 "(为什么还问:" + 非机械。"""
        llm_fn, calls = _mock_llm(_partial_analysis())
        session = _start(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))

        assert session.current_state == STATES.CLARIFYING
        assert session._pending_fields[0] == "user"  # 只留真正缺失, 最重要必填在前
        assert session._ai_generated is True
        # 已给字段直接填上 (不再问 problem/core_features)
        assert session.product_intent.problem and "记账" in session.product_intent.problem
        assert session.product_intent.core_features == ["收支记录", "分类统计"]
        assert session.product_intent.user is None
        # 智能追问: 最重要 1 条 + 为什么缺 (非机械第一问)
        q = session._next_question()
        assert q is not None and q.field == "user"
        assert "主要给谁用呢" in q.question
        assert "为什么还问" in q.question and "目标用户" in q.question
        assert "这个产品解决什么问题?" not in q.question
        assert calls and calls[0][1] == "discovery_intent"


# ================================================================== 3. 回答并入不覆盖 (v1.1.19 边界)

class TestAnswerMergeBoundary:
    def test_field_answer_fills_current_only(self):
        """计划 §4-3: 对追问的回答 → field_answer → 只填对应字段, 已填不覆盖。"""
        llm_fn, calls = _scripted_llm(_partial_analysis(), _field_answer())
        session = _start(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        assert session._pending_fields[0] == "user"
        problem_before = session.product_intent.problem
        features_before = list(session.product_intent.core_features)

        r = session.process_user_input("给个人用户用")
        # 只填当前字段 (user), 已填不覆盖
        assert session.product_intent.user == "给个人用户用"
        assert session.product_intent.problem == problem_before
        assert session.product_intent.core_features == features_before
        # system_question 注入 (v1.1.19 多轮字段合并边界)
        assert len(calls) >= 2
        assert "主要给谁用呢" in calls[1][0]
        assert "系统上一轮问题" in calls[1][0]
        # 队列推进 → 下一问 (增强字段, 不重问已填)
        assert r["state"] == STATES.CLARIFYING
        assert r["question"].field == "usage_scenarios"
        # S10-101 进度前缀: 消息 = 生命周期行 + 必填进度 (+增强可选) + 问题
        assert r["message"] == (
            "流程: [发现]→确认→创建→PRD→工程→开发 (当前: 发现)\n"
            "产品定义 3/3: 产品解决什么问题✅ 目标用户✅ 核心功能✅\n"
            "增强(可选): 使用场景待填 · MVP范围待填 · 非功能要求待填\n"
            "主要在哪些场景使用?"
        )


# ================================================================== 4. 理解摘要 + 主动分析 (验收 4)

class TestReadyMessageContent:
    def test_understanding_and_proactive_in_ready(self):
        """计划 §4-4: READY 消息含 "我理解你要做" + "主动建议:"。"""
        # name 由 extraction 提供 → 不触发命名候选, 聚焦摘要/主动分析
        data = _full_analysis(name="简记")
        llm_fn, calls = _mock_llm(data)
        session = _start(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        assert session.current_state == STATES.READY_FOR_CONFIRMATION
        msg = session._ready_response()["message"]
        assert "我理解你要做" in msg
        assert "主动建议:" in msg
        assert "竞品=随手记 / 鲨鱼记账" in msg
        assert "范围=MVP: 收支记录 + 分类统计" in msg
        assert session._ai_generated is True
        assert session._proactive.get("competitors") == "随手记 / 鲨鱼记账"

    def test_no_understanding_when_llm_not_used(self):
        """无 LLM → READY 消息不含 "我理解你要做" (规则兜底逐字节不变)。"""
        session = _start()  # 装配失败 (autouse 模拟无 provider) → 规则兜底
        r = None
        for text in ("记账太麻烦", "需要记账的个人", "收支、统计、报表",
                     "日常记账", "第一版只做记账", "无特殊要求"):
            r = session.process_user_input(text)
        assert r is not None and r["state"] == STATES.READY_FOR_CONFIRMATION
        assert session._ai_generated is False
        assert "我理解你要做" not in r["message"]
        assert "主动建议" not in r["message"]


# ================================================================== 5. 无 LLM 零变化 (验收 3)

class TestNoLlmZeroChange:
    def test_explicit_none_analyzer_still_asks_field_by_field(self):
        """计划 §4-5: analyzer=None → 规则逐字段问, 与既有 108 tests 一致。"""
        session = _start(analyzer=None)  # 无 provider → 懒装配失败 → 规则兜底
        assert session.current_state == STATES.DISCOVERING
        assert session._ai_generated is False
        _assert_first_question_guided(session)
        r = session.process_user_input("记账太麻烦")
        assert r["state"] == STATES.CLARIFYING
        assert r["question"].field == "user"
        r = session.process_user_input("需要记账的个人")
        assert r["question"].field == "core_features"
        r = session.process_user_input("收支、统计、报表")
        assert r["question"].field == "usage_scenarios"  # 必填齐仍建议增强
        r = session.process_user_input("日常记账")
        assert r["question"].field == "mvp_scope"
        r = session.process_user_input("第一版只做记账")
        assert r["question"].field == "non_functional_requirements"
        # 最终 READY 消息与规则一致 (无理解摘要, 临时名保留)
        r = session.process_user_input("无特殊要求")
        assert r["state"] == STATES.READY_FOR_CONFIRMATION
        assert "产品:" in r["message"] and "请确认产品需求" in r["message"]
        assert "我理解你要做" not in r["message"]
        assert session.product_intent.name.startswith("未命名产品")

    def test_analyzer_assembly_failure_zero_change(self, monkeypatch):
        """LLM 装配失败 (无 provider/key) → 规则兜底逐字段问 (不伪造)。"""
        REASON = importlib.import_module("factory-console.session.reasoning")

        class _BrokenProvider:
            def _default_llm_fn(self):
                raise REASON.ReasoningUnavailable("无可用 provider")

        monkeypatch.setattr(REASON, "ReasoningProvider", _BrokenProvider)
        session = _start()  # 不注入 → 懒装配失败 → None → 规则
        assert session.current_state == STATES.DISCOVERING
        assert session._ai_generated is False
        _assert_first_question_guided(session)
        session.process_user_input("记账太麻烦")
        assert session.product_intent.problem == "记账太麻烦"
        assert "未命名产品" in session.product_intent.name


# ================================================================== 6. 控制/查询不当字段

class TestControlQueryNotField:
    def test_control_cancel_cancels(self):
        """计划 §4-6: category=control(取消类) → cancel, 不当字段。"""
        llm_fn, calls = _scripted_llm(_partial_analysis(), _control_analysis("用户取消"))
        session = _start(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        assert session.current_state == STATES.CLARIFYING
        r = session.process_user_input("算了不做了")
        assert session.current_state == STATES.CANCELLED
        assert r["state"] == STATES.CANCELLED
        assert "已取消" in r["message"]
        # 未被吞为字段
        assert session.product_intent.user is None

    def test_control_non_cancel_requestion(self):
        """category=control(非取消) → 不吞为字段, 重问当前问题。"""
        llm_fn, calls = _scripted_llm(
            _partial_analysis(),
            _control_analysis("整理一下 是控制指令"),
        )
        session = _start(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        assert session._pending_fields[0] == "user"
        r = session.process_user_input("整理一下")
        assert session.current_state == STATES.CLARIFYING
        assert session.product_intent.user is None  # 不当字段
        assert "主要给谁用呢" in r["message"]  # 重问当前问题

    def test_query_not_swallowed(self):
        """category=query → 不吞为字段, 重问当前问题 (模型层不逃生)。"""
        llm_fn, calls = _scripted_llm(_partial_analysis(), _query_analysis())
        session = _start(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        r = session.process_user_input("现在有哪些项目")
        assert session.current_state == STATES.CLARIFYING
        assert session.product_intent.user is None  # 不当字段
        assert "主要给谁用呢" in r["message"]


# ================================================================== 6.5 S10-101: 求助流 + 中间字段智能 (两路径新增用例)

class TestHelpRequestFlow:
    """求助: 关键词兜底 (无 LLM) + LLM help_request + 不当字段 + 确认填入。"""

    def test_keyword_fallback_without_llm(self):
        """S10-101 契约 5: analyzer=None "给些建议" → 默认建议 → y 填入。"""
        session = _start(analyzer=None)
        resp = session.process_user_input("给些建议")
        assert "当前缺产品解决什么问题 — 建议方向:" in resp["message"]
        assert "1. 现有工具太繁琐" in resp["message"]
        assert session.product_intent.problem is None  # 未确认前不当字段
        resp = session.process_user_input("y")
        assert session.product_intent.problem == (
            "现有工具太繁琐、效率低/耗时长、信息分散难管理"
        )
        assert "产品定义 1/3:" in resp["message"]
        assert session._pending_fields[0] == "user"

    def test_help_not_swallowed_as_field(self):
        """S10-101 契约 6: "没思路" 不当字段内容。"""
        session = _start(analyzer=None)
        resp = session.process_user_input("没思路")
        assert session.product_intent.problem is None
        assert "建议方向" in resp["message"]
        resp = session.process_user_input("y")
        assert session.product_intent.problem != "没思路"
        assert session.product_intent.problem.startswith("现有工具太繁琐")

    def test_llm_help_request_suggestions_fill(self):
        """S10-101 契约 4: 非关键词求助 → LLM help_request + suggestions → y 填入。"""
        help_analysis = {
            "category": "help_request",
            "reason": "用户求建议",
            "extraction": {},
            "missing_reasons": {},
            "smart_questions": [],
            "proactive": {},
            "understanding": "",
            "suggestions": {
                "field": "user",
                "items": ["给开发者用", "给写作爱好者用"],
                "note": "想清楚给谁用, 功能才好定",
            },
        }
        llm_fn, calls = _scripted_llm(_partial_analysis(), help_analysis)
        session = _start(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        resp = session.process_user_input("帮我想想")  # 非关键词 → LLM help_request
        assert "当前缺目标用户 — 建议方向:" in resp["message"]
        assert "1. 给开发者用" in resp["message"]
        assert session._suggestion_proposal == {
            "field": "user", "items": ["给开发者用", "给写作爱好者用"],
        }
        resp = session.process_user_input("y")
        assert session.product_intent.user == "给开发者用、给写作爱好者用"
        assert "产品定义 3/3:" in resp["message"]

    def test_field_answer_smart_next_question(self):
        """S10-101 契约 3: field_answer 后下一问用 LLM smart_questions[0] (非机械)。"""
        two_missing = _partial_analysis()
        two_missing["extraction"] = {
            "problem": "个人记账麻烦",
            "user": "",
            "core_features": [],
            "name": "",
            "platform": "",
            "usage_scenarios": "",
            "mvp_scope": "",
            "non_functional_requirements": "",
        }
        two_missing["missing_reasons"] = {
            "user": "没提到目标用户",
            "core_features": "没提到核心功能",
        }
        field_answer = {
            "category": "field_answer",
            "reason": "回答目标用户",
            "extraction": {"user": "给个人用户用"},
            "missing_reasons": {"core_features": "还没提到核心功能"},
            "smart_questions": ["核心功能想先覆盖哪些?"],
            "proactive": {},
            "understanding": "",
        }
        llm_fn, calls = _scripted_llm(two_missing, field_answer)
        session = _start(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        assert session._pending_fields[0] == "user"
        resp = session.process_user_input("给个人用户用")
        assert session.product_intent.user == "给个人用户用"
        assert resp["question"].field == "core_features"
        assert "核心功能想先覆盖哪些?" in resp["message"]
        assert "为什么还问" in resp["message"]
        assert "核心功能有哪些? (用逗号或顿号分隔)" not in resp["message"]  # 非机械


# ================================================================== 6.6 S10-101 验收修复: 首问带进度前缀 (幂等 / 原始 system_question)

class TestS101FirstQuestionGuidePrefix:
    def test_start_first_question_has_guide_prefix(self):
        """验收: start() 的 questions[0].question 含 流程: + 产品定义 (无 LLM 也成立)。"""
        s = _start(idea="开始做个记账App", analyzer=None)
        q = s.questions[0].question
        assert q.startswith(
            "流程: [发现]→确认→创建→PRD→工程→开发 (当前: 发现)\n产品定义 0/3:"
        )
        assert "这个产品解决什么问题?" in q
        # 任何消费方 (actions.discovery_start 渲染 / resume / 模型字段) 拿到带进度问题
        nxt = s._next_question()
        assert nxt is not None and nxt.question == q

    def test_process_message_prefix_only_once(self):
        """验收: process_user_input 的 message 前缀只出现一次 (幂等, 不双重)。"""
        s = _start(idea="开始做个记账App", analyzer=None)
        r = s.process_user_input("记账太麻烦")
        msg = r["message"]
        assert msg.count("流程:") == 1
        assert msg.count("产品定义") == 1
        assert msg.count("增强(可选):") == 1
        # 问题对象与 message 同为带前缀版本 (消费方一致)
        assert r["question"].question == msg

    def test_last_system_question_is_raw(self):
        """验收: _last_system_question 不含 流程:/产品定义 (原始问题, LLM 上下文干净)。"""
        s = _start(idea="开始做个记账App", analyzer=None)
        assert s._last_system_question == "这个产品解决什么问题?"
        r = s.process_user_input("记账太麻烦")
        assert r["state"] == STATES.CLARIFYING
        assert s._last_system_question == "主要给谁使用?"
        assert "流程:" not in s._last_system_question
        assert "产品定义" not in s._last_system_question

    def test_guide_message_idempotent(self):
        """验收: _guide_message 幂等 — 已带前缀的 body 原样返回。"""
        s = _start(idea="开始做个记账App", analyzer=None)
        prefixed = s.questions[0].question
        assert s._guide_message(prefixed) == prefixed
        # 未带前缀 → 正常加前缀 (一次)
        raw = "这个产品解决什么问题?"
        guided = s._guide_message(raw)
        assert guided.startswith("流程:") and guided.endswith(raw)
        assert guided.count("流程:") == 1

    def test_llm_smart_question_llm_text_raw(self):
        """验收: LLM 智能追问 q_item 带前缀, 但 _llm_question_text/_last_system_question 保持原始。"""
        llm_fn, calls = _mock_llm(_partial_analysis())
        session = _start(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        q = session.questions[-1]
        assert "流程:" in q.question and "产品定义" in q.question
        assert "主要给谁用呢" in q.question
        assert "流程:" not in session._llm_question_text
        assert "产品定义" not in session._llm_question_text
        assert session._last_system_question == "主要给谁用呢? (例如: 个人 / 学生 / 小商家)"


# ================================================================== 7. 非法 LLM 输出降级

class TestInvalidOutputFallback:
    @pytest.mark.parametrize("bad_output", [
        "这不是 JSON",
        "{ broken json",
        "```json\n{not json}\n```",
        "",
    ])
    def test_non_json_falls_back(self, bad_output):
        """计划 §4-7: mock 返回非 JSON → 规则兜底第一问, 不崩溃。"""
        llm_fn, _ = _mock_llm(bad_output)
        session = _start(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        assert session.current_state == STATES.DISCOVERING
        assert session._ai_generated is False
        _assert_first_question_guided(session)
        r = session.process_user_input("记账太麻烦")
        assert session.product_intent.problem == "记账太麻烦"

    def test_missing_schema_falls_back(self):
        """合法 JSON 但缺 category → schema 校验失败 → 规则兜底。"""
        llm_fn, _ = _mock_llm({
            "extraction": {"problem": "X", "user": "Y"},
            "understanding": "我理解你要做 X",
        })  # 无 category
        session = _start(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        assert session.current_state == STATES.DISCOVERING
        assert session._ai_generated is False
        assert "这个产品解决什么问题?" in session.questions[0].question

    def test_llm_exception_falls_back(self):
        """LLM 调用抛异常 → 规则兜底 (不崩溃, 不伪造理解)。"""
        def broken(prompt, operation=""):
            raise RuntimeError("provider timeout")

        session = _start(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=broken))
        assert session.current_state == STATES.DISCOVERING
        assert session._ai_generated is False
        _assert_first_question_guided(session)


# ================================================================== 8. 持久化 round-trip

class TestPersistence:
    def test_new_fields_roundtrip(self, tmp_path):
        """计划 §4-8: _last_system_question/_ai_generated/_understanding/_proactive
        save/load 完整。"""
        data = _full_analysis(name="简记")
        llm_fn, _ = _mock_llm(data)
        session = _start(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        session._last_system_question = "主要给谁用呢?"
        assert session.current_state == STATES.READY_FOR_CONFIRMATION

        d = session.to_dict()
        assert d["_ai_generated"] is True
        assert d["_understanding"] and "我理解你要做" in d["_understanding"]
        assert d["_proactive"]["competitors"] == "随手记 / 鲨鱼记账"
        assert d["_last_system_question"] == "主要给谁用呢?"

        restored = DIS.DiscoverySession.from_dict(d)
        assert restored is not None
        assert restored._ai_generated is True
        assert restored._understanding == session._understanding
        assert restored._proactive == session._proactive
        assert restored._last_system_question == "主要给谁用呢?"
        assert restored.current_state == STATES.READY_FOR_CONFIRMATION

        # save/load 文件级 round-trip
        path = session.save(tmp_path)
        assert path is not None
        loaded = DIS.DiscoverySession.load(tmp_path, session.session_id)
        assert loaded is not None
        assert loaded._ai_generated is True
        assert loaded._understanding == session._understanding
        assert loaded._proactive == session._proactive

    def test_old_file_defaults_compatible(self):
        """旧会话文件无新键 → 缺省默认值, 不崩 (兼容)。"""
        data = _full_analysis(name="简记")
        llm_fn, _ = _mock_llm(data)
        session = _start(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        d = session.to_dict()
        for key in ("_last_system_question", "_ai_generated", "_understanding", "_proactive"):
            d.pop(key, None)
        compat = DIS.DiscoverySession.from_dict(d)
        assert compat is not None
        assert compat._ai_generated is False
        assert compat._understanding == ""
        assert compat._proactive == {}
        assert compat._last_system_question == ""


# ================================================================== 9. 命名 (LLM-gated)

class TestNaming:
    def test_llm_available_temp_name_sets_candidate(self):
        """计划 §4-9: LLM 可用+临时名 → 候选1设名 + 展示候选。"""
        llm_fn, calls = _scripted_llm(_full_analysis(), _names_text())
        session = _start(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        assert session.current_state == STATES.READY_FOR_CONFIRMATION
        assert session.product_intent.name == "记账本"
        assert session._name_candidates == ["记账本", "账本管家", "随手记"]
        msg = session._ready_response()["message"]
        assert "建议名称: 记账本" in msg
        assert "  2. 账本管家" in msg
        assert calls[1][1] == "naming"

    def test_no_llm_temp_name_preserved(self):
        """计划 §4-9: 无 LLM → 临时名保留 (零变化)。"""
        session = _start(analyzer=None)
        for text in ("记账太麻烦", "需要记账的个人", "收支、统计、报表",
                     "日常记账", "第一版只做记账", "无特殊要求"):
            session.process_user_input(text)
        assert session.current_state == STATES.READY_FOR_CONFIRMATION
        assert session.product_intent.name.startswith("未命名产品")
        assert session._name_candidates == []


# ================================================================== 模块级: analyzer 8 字段契约扩展

class TestAnalyzerExtension:
    def test_extraction_includes_new_keys(self):
        """EXTRACTION_FIELDS 含 usage_scenarios/mvp_scope/non_functional_requirements。"""
        assert "usage_scenarios" in DI.EXTRACTION_FIELDS
        assert "mvp_scope" in DI.EXTRACTION_FIELDS
        assert "non_functional_requirements" in DI.EXTRACTION_FIELDS
        assert len(DI.EXTRACTION_FIELDS) == 8

    def test_new_keys_normalized(self):
        """新键归一化: 字符串原样 / list 顿号连接。"""
        data = _full_analysis()
        llm_fn, _ = _mock_llm(data)
        a = DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn).analyze("x")
        assert a.extraction["usage_scenarios"] == "日常消费记账、月底对账"
        assert a.extraction["mvp_scope"] == "第一版只做收支记录和分类统计"
        assert a.extraction["non_functional_requirements"] == "数据本地保存, 响应快"
        # list 输入 → 顿号连接
        data2 = _full_analysis(extraction={"usage_scenarios": ["日常记账", "月底对账"]})
        llm_fn2, _ = _mock_llm(data2)
        a2 = DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn2).analyze("x")
        assert a2.extraction["usage_scenarios"] == "日常记账、月底对账"

    def test_new_keys_default_empty(self):
        """新键缺省补空 (不影响既有 5 键校验)。"""
        llm_fn, _ = _mock_llm(_full_analysis(extraction={"problem": "P"}))
        a = DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn).analyze("x")
        assert a.extraction["usage_scenarios"] == ""
        assert a.extraction["mvp_scope"] == ""
        assert a.extraction["non_functional_requirements"] == ""

    def test_prompt_contains_new_keys_and_rule(self):
        """prompt 输出 schema 含 3 新键 + 规则行。"""
        llm_fn, calls = _mock_llm(_full_analysis())
        DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn).analyze("x")
        prompt = calls[0][0]
        assert "usage_scenarios" in prompt
        assert "mvp_scope" in prompt
        assert "non_functional_requirements" in prompt
        assert "明确提到" in prompt and "才填" in prompt

    def test_conversation_ignores_new_extraction_keys(self):
        """conversation 路径只读 5 键 — 新键被忽略, 行为零变化。"""
        llm_fn, _ = _mock_llm(_full_analysis())
        mgr = CONV.ConversationManager(
            analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn)
        )
        resp = mgr.handle("我想做个记账App, 给个人用户, 核心是收支记录")
        assert resp.state == CONV.ConversationState.PRODUCT_CONFIRMATION
        pi = mgr.product_intent
        assert pi is not None
        assert pi.problem and pi.user and pi.core_features
        assert not hasattr(pi, "usage_scenarios")  # 新键不进入 ProductIntent


# ================================================================== 冒烟: 响应键集合保持既有 5 键 (规则路径)

class TestResponseContract:
    def test_rule_path_response_keys_unchanged(self):
        """规则路径响应 dict 仍为既有 5 键 (零变化)。"""
        session = _start(analyzer=None)
        r = session.process_user_input("记账太麻烦")
        assert set(r.keys()) == {"state", "question", "summary", "missing_fields", "message"}
