"""tests/console/test_s10_109_field_routing.py — 需求分析字段错位修复 (T9) 契约测试。

设计: docs/sprint10/S10-109-field-routing-plan.md §1-§2
Bug (Founder 实测, v1.1.47): 问痛点答"给大学生用" → 被强填 problem;
"支持扫码记账和月度报表" → 被强填 user; "可以" → 被强填 core_features。
根因: _apply_field_answer 无条件 field = pending[0], 无语义校验。

覆盖 (计划 §2 契约点 1-8, ≥4):
1. T9 复现 (无 LLM 机械路径 + LLM field_answer 路径): 答非所问归类 + 确认词不当值
2. 答非所问归类: 问 user 答"支持扫码" → core_features; 问 core_features 答"记账很麻烦" → problem
3. 确认词不当值: "可以"/"好"/"y" 缺字段 → 不填 + 提示缺字段; 全字段齐 → 正常确认 (防御)
4. 正常回答零变化: 逐字节同 v1.1.47 (字段值/消息/状态)
5. 多命中优先级: "给大学生用, 支持扫码" → user (user > core_features > problem)
6. 无 LLM 同生效: analyzer=None (env -u 等价) 规则路径归类一致
7. 批量模式不受影响: 分号批量回答仍按顺序填
8. 误伤收敛: "做报表" → core_features (非确认词 — 整句匹配); "现在很痛苦" → problem
9. 版本断言 v1.1.79 (单源见 test_s10_074_deployment)

模块级: _FIELD_PATTERNS / _FIELD_MATCH_PRIORITY / _resolve_answer_field 单元 +
ConversationManager 端到端。全部测试零真实 LLM (analyzer=None / scripted analyzer)。
"""

from __future__ import annotations

import importlib

import pytest

CONV = importlib.import_module("factory-console.session.conversation")
DI = importlib.import_module("factory-console.session.discovery_intelligence")

STATES = CONV.ConversationState


# ------------------------------------------------------------------ 工具

@pytest.fixture(autouse=True)
def _no_provider(monkeypatch):
    """模拟无 LLM provider/key — 默认装配确定性失败 (规则兜底)。

    注入 scripted analyzer 的测试不受影响 (不走默认装配)。
    """
    REASON = importlib.import_module("factory-console.session.reasoning")

    class _BrokenProvider:
        def _default_llm_fn(self):
            raise REASON.ReasoningUnavailable("无可用 provider (测试模拟)")

    monkeypatch.setattr(REASON, "ReasoningProvider", _BrokenProvider)


def _manager(**kw):
    return CONV.ConversationManager(**kw)


def _scripted_llm(*responses):
    """按调用顺序返回的 mock llm_fn (超出 → 最后一个)。"""
    calls: list[tuple[str, str]] = []

    def llm_fn(prompt, operation=""):
        calls.append((prompt, operation))
        idx = min(len(calls) - 1, len(responses) - 1)
        return responses[idx]

    return llm_fn, calls


def _two_missing_analysis() -> dict:
    """product_description: 只填 problem (缺 user + core_features — 中间字段场景)。"""
    return {
        "category": "product_description",
        "reason": "描述了痛点",
        "extraction": {
            "problem": "个人记账麻烦, 月底对不上账",
            "user": "",
            "core_features": [],
            "name": "",
            "platform": "",
        },
        "missing_reasons": {
            "user": "没提到目标用户",
            "core_features": "没提到核心功能",
        },
        "smart_questions": ["主要给谁用呢?"],
        "proactive": {},
        "understanding": "",
        "suggestions": {},
    }


def _field_answer_payload() -> dict:
    """LLM field_answer 输出 (本轮回答归属由 _resolve_answer_field 决定)。"""
    return {
        "category": "field_answer",
        "reason": "用户回答了上一轮问题",
        "extraction": {},
        "missing_reasons": {},
        "smart_questions": [],
        "proactive": {},
        "understanding": "",
        "suggestions": {},
    }


def _body(msg: str) -> str:
    """去掉 guide 前缀 (生命周期行/产品定义进度行) → 消息正文。"""
    lines = msg.split("\n")
    body: list[str] = []
    started = False
    for line in lines:
        if not started and (
            line.startswith("流程:") or line.startswith("产品定义") or line.startswith("增强(可选):")
        ):
            continue
        started = True
        body.append(line)
    return "\n".join(body)


def _start_discovery(mgr, idea="我想做个记账App"):
    """启动产品发现 (机械路径, 无 LLM) → 返回首问响应。"""
    return mgr.handle(idea)


# ================================================================== 1. 模块级规则单元

class TestFieldPatterns:
    def test_patterns_cover_required_fields(self):
        """_FIELD_PATTERNS 覆盖 user/core_features/problem 三字段 (计划 §1.1)。"""
        assert set(CONV._FIELD_PATTERNS) == {"user", "core_features", "problem"}
        assert CONV._FIELD_MATCH_PRIORITY == ("user", "core_features", "problem")

    def test_resolve_answer_field_user_patterns(self):
        """user 模式: 给大学生用 / 面向白领 / 中小企业人群。"""
        pending = ["problem", "user", "core_features"]
        for text in ("给大学生用", "面向大学生", "给个人用户用", "学生用户",
                     "目标人群是白领", "给开发者用", "面向企业"):
            assert CONV._resolve_answer_field(text, list(pending)) == "user", text

    def test_resolve_answer_field_core_features_patterns(self):
        """core_features 模式: 支持扫码 / 可以做报表 / 记账记录统计。"""
        pending = ["problem", "user", "core_features"]
        for text in ("支持扫码记账", "可以导出报表", "能统计每月支出",
                     "扫码记账功能", "月度报表", "消费记录", "分类统计", "支持导出数据"):
            assert CONV._resolve_answer_field(text, list(pending)) == "core_features", text

    def test_resolve_answer_field_problem_patterns(self):
        """problem 模式: 解决对不上 / 记账麻烦 / 现在很痛苦 / 手动低效。"""
        pending = ["problem", "user", "core_features"]
        for text in ("解决月底对不上", "手动记账很麻烦", "手动对账是痛点",
                     "现在很痛苦", "对账很难", "使用不便", "手动录费时", "效率低效"):
            assert CONV._resolve_answer_field(text, list(pending)) == "problem", text

    def test_resolve_confirm_word_returns_none(self):
        """确认词整句 (APPROVE_WORDS + y/yes) → None (不当字段值)。"""
        pending = ["problem", "user", "core_features"]
        for text in ("可以", "好", "行", "是", "y", "yes", "ok", "没问题", "就这样"):
            assert CONV._resolve_answer_field(text, list(pending)) is None, text

    def test_resolve_confirm_word_whole_sentence_only(self):
        """整句才触发确认词 — "做报表" 不被 "做" 误判为确认词。"""
        pending = ["problem", "user", "core_features"]
        assert CONV._resolve_answer_field("做报表", list(pending)) == "core_features"
        assert CONV._resolve_answer_field("可以，先出prd文档", list(pending)) == "core_features"
        assert CONV._resolve_answer_field("好的", list(pending)) is None

    def test_resolve_unmatched_returns_current(self):
        """未命中任何模式 → 当前字段 (正常回答零变化)。"""
        assert CONV._resolve_answer_field("台球爱好者", ["problem", "user", "core_features"]) == "problem"
        assert CONV._resolve_answer_field("随便写写", ["user"]) == "user"

    def test_resolve_priority_user_over_core_features(self):
        """多命中优先级: user > core_features > problem。"""
        pending = ["problem", "user", "core_features"]
        assert CONV._resolve_answer_field("给大学生用, 支持扫码", list(pending)) == "user"
        assert CONV._resolve_answer_field("解决麻烦给白领用", list(pending)) == "user"
        assert CONV._resolve_answer_field("支持扫码解决对不上", list(pending)) == "core_features"

    def test_resolve_only_pending_fields(self):
        """只填 pending 中未填字段 — 已填字段即使命中也不覆盖 (回退当前字段)。"""
        assert CONV._resolve_answer_field("给大学生用", ["problem", "core_features"]) == "problem"
        assert CONV._resolve_answer_field("支持扫码", ["problem", "user"]) == "problem"


# ================================================================== 2. T9 复现 (无 LLM 机械路径)

class TestT9Mechanical:
    def _flow(self):
        mgr = _manager(analyzer=None)
        _start_discovery(mgr)
        return mgr

    def test_t9_repro_fields_correct(self):
        """契约点 1 (T9): 问痛点答"给大学生用" → user; "支持扫码记账和月度报表" →
        core_features; "可以" (缺 problem) → 不填 + 提示缺字段。"""
        mgr = self._flow()
        assert mgr._product_pending == ["problem", "user", "core_features"]
        # 问痛点 (当前 problem) → 答 target user → 归类到 user (非 problem)
        r = mgr.handle("给大学生用")
        assert mgr.product_intent.user == "给大学生用"
        assert mgr.product_intent.problem is None  # 未被污染
        assert mgr._product_pending == ["problem", "core_features"]
        assert mgr.state == STATES.DISCOVERY
        # 仍追问 problem (未填)
        assert "缺失字段: problem" in r.message
        # 问 problem → 答功能 → 归类到 core_features (非 user)
        r = mgr.handle("支持扫码记账和月度报表")
        assert mgr.product_intent.core_features == ["支持扫码记账和月度报表"]
        assert mgr.product_intent.user == "给大学生用"  # 未被覆盖
        assert mgr._product_pending == ["problem"]
        assert mgr.state == STATES.DISCOVERY
        # 确认词 "可以" → 不当字段值 → 不填 + 提示缺字段
        r = mgr.handle("可以")
        assert mgr.product_intent.core_features == ["支持扫码记账和月度报表"]  # 未被填
        assert mgr._product_pending == ["problem"]  # 不推进
        assert mgr.state == STATES.DISCOVERY
        assert "产品定义还不完整" in r.message
        assert "还缺 产品解决什么问题" in r.message
        assert "请先补充" in r.message
        # 补齐 problem → 进入确认门 (字段正确)
        r = mgr.handle("记账麻烦, 月底对不上")
        assert mgr.product_intent.problem == "记账麻烦, 月底对不上"
        assert mgr._product_pending == []
        assert r.state == STATES.PRODUCT_CONFIRMATION
        assert mgr.product_intent.user == "给大学生用"
        assert mgr.product_intent.core_features == ["支持扫码记账和月度报表"]

    def test_t9_llm_field_answer_path(self):
        """契约点 1+6: LLM field_answer 路径同样走 _resolve_answer_field (规则优先)。"""
        llm_fn, _ = _scripted_llm(_two_missing_analysis(), _field_answer_payload())
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        mgr.handle("我想做个记账App")  # LLM 提取 problem → 追问 user
        assert mgr._product_pending == ["user", "core_features"]
        # LLM 分类 field_answer (按当前问 user), 但内容属功能 → 规则归类 core_features
        r = mgr.handle("支持扫码记账和月度报表")
        assert mgr.product_intent.core_features == ["支持扫码记账和月度报表"]
        assert mgr.product_intent.user is None
        assert mgr._product_pending == ["user"]
        assert mgr.state == STATES.DISCOVERY
        # 确认词 → 不填 (LLM 路径 None 分支)
        r = mgr.handle("可以")
        assert mgr.product_intent.user is None
        assert mgr._product_pending == ["user"]
        assert "还缺 目标用户" in r.message


# ================================================================== 3. 答非所问归类 / 确认词不当值

class TestAnswerRouting:
    def test_answer_to_user_question_goes_core_features(self):
        """契约点 2: 问 user 答"支持扫码" → core_features。"""
        mgr = _manager(analyzer=None)
        _start_discovery(mgr)
        mgr.handle("手动记账麻烦")  # problem
        assert mgr._product_pending == ["user", "core_features"]
        mgr.handle("支持扫码")  # 当前问 user, 答功能
        assert mgr.product_intent.core_features == ["支持扫码"]
        assert mgr.product_intent.user is None
        assert mgr._product_pending == ["user"]

    def test_answer_to_features_question_goes_problem(self):
        """契约点 2: 答痛点 (problem 未填) → 归类 problem, 不落当前 core_features。"""
        mgr = _manager(analyzer=None)
        _start_discovery(mgr)
        mgr.handle("给大学生用")  # 问 problem, 答 user → 归类 user
        mgr.handle("支持扫码")  # 问 problem, 答功能 → 归类 core_features
        assert mgr._product_pending == ["problem"]
        mgr.handle("记账很麻烦")  # 当前问 problem, 答痛点 → problem
        assert mgr.product_intent.problem == "记账很麻烦"
        assert mgr.product_intent.core_features == ["支持扫码"]
        assert mgr._product_pending == []

    def test_confirm_words_not_filled_when_missing(self):
        """契约点 3: "可以"/"好"/"y" 缺字段 → 不填 + 提示缺字段。"""
        for word in ("可以", "好", "y"):
            mgr = _manager(analyzer=None)
            _start_discovery(mgr)
            assert mgr._product_pending == ["problem", "user", "core_features"]
            r = mgr.handle(word)
            assert mgr.product_intent.problem is None
            assert mgr._product_pending == ["problem", "user", "core_features"]
            assert "还缺 产品解决什么问题" in r.message
            assert r.needs_input is True

    def test_confirm_word_all_fields_filled_enters_confirmation(self):
        """契约点 3 (防御): 字段全齐后确认词 → 正常进入确认 (不受影响)。"""
        mgr = _manager(analyzer=None)
        _start_discovery(mgr)
        mgr.handle("记账麻烦")
        mgr.handle("给个人用户用")
        r = mgr.handle("支持扫码、导出报表")
        assert r.state == STATES.PRODUCT_CONFIRMATION
        r = mgr.handle("可以")
        assert r.state != STATES.DISCOVERY  # 确认门正常响应 (approved 路径)
        assert r.needs_input is False


# ================================================================== 4. 正常回答零变化 (逐字节同 v1.1.47)

class TestNormalAnswerZeroChange:
    def test_normal_answers_byte_identical(self):
        """契约点 4: 正常回答字段值/顺序与 v1.1.47 逐字节一致 (无 LLM 机械路径)。"""
        mgr = _manager(analyzer=None)
        _start_discovery(mgr)
        r = mgr.handle("记账麻烦, 月底对不上")
        assert mgr.product_intent.problem == "记账麻烦, 月底对不上"
        assert _body(r.message) == (
            "目标用户是谁? (主要给谁用, 例如: 个人用户 / 学生 / 中小企业) "
            "(缺失字段: user)"
        )
        r = mgr.handle("给大学生用")
        assert mgr.product_intent.user == "给大学生用"
        assert _body(r.message) == (
            "核心功能有哪些? (用逗号或顿号分隔, 例如: 记账、统计、导出) "
            "(缺失字段: core_features)"
        )
        r = mgr.handle("扫码记账、月度报表")
        assert mgr.product_intent.core_features == ["扫码记账", "月度报表"]
        assert r.state == STATES.PRODUCT_CONFIRMATION
        assert "确认创建这个产品?" in _body(r.message)

    def test_feature_answer_not_mistaken_for_confirm_word(self):
        """契约点 8 (误伤收敛): 问 core_features 答"做报表" → core_features (整句匹配)。"""
        mgr = _manager(analyzer=None)
        _start_discovery(mgr)
        mgr.handle("记账麻烦")
        mgr.handle("给个人用户用")
        r = mgr.handle("做报表")
        assert mgr.product_intent.core_features == ["做报表"]
        assert r.state == STATES.PRODUCT_CONFIRMATION

    def test_problem_answer_not_mistaken_for_confirm_word(self):
        """契约点 8 (误伤收敛): 问 problem 答"现在很痛苦" → problem。"""
        mgr = _manager(analyzer=None)
        _start_discovery(mgr)
        mgr.handle("现在很痛苦")
        assert mgr.product_intent.problem == "现在很痛苦"
        assert mgr._product_pending == ["user", "core_features"]


# ================================================================== 5. 多命中优先级 / 批量模式 / 无 LLM

class TestPriorityAndBatch:
    def test_multi_match_priority_user_first(self):
        """契约点 5: "给大学生用, 支持扫码" → user (user > core_features > problem)。"""
        mgr = _manager(analyzer=None)
        _start_discovery(mgr)
        mgr.handle("给大学生用, 支持扫码")
        assert mgr.product_intent.user == "给大学生用, 支持扫码"
        assert mgr.product_intent.core_features == []
        assert mgr._product_pending == ["problem", "core_features"]

    def test_batch_mode_untouched(self):
        """契约点 7: 分号批量回答仍按顺序填 (批量模式不动)。"""
        mgr = _manager(analyzer=None)
        _start_discovery(mgr)
        r = mgr.handle("记账麻烦；给大学生用；支持扫码")
        assert mgr.product_intent.problem == "记账麻烦"
        assert mgr.product_intent.user == "给大学生用"
        assert mgr.product_intent.core_features == ["支持扫码"]
        assert r.state == STATES.PRODUCT_CONFIRMATION

    def test_no_llm_env_u_same_behavior(self, monkeypatch):
        """契约点 6: env -u DEEPSEEK_API_KEY (analyzer 装配失败) → 规则路径同生效。"""
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        # 无任何 provider 可用 → 默认装配失败 → 机械路径 (确定性规则生效)
        mgr = _manager(analyzer=CONV._DISCOVERY_ANALYZER_UNSET)
        _start_discovery(mgr)
        r = mgr.handle("给大学生用")
        assert mgr.product_intent.user == "给大学生用"
        assert mgr.product_intent.problem is None
        r = mgr.handle("可以")
        assert mgr.product_intent.core_features == []
        assert "还缺 产品解决什么问题" in r.message


# ================================================================== 6. 版本断言

class TestVersion:
    def test_pyproject_version_1_1_48(self):
        """契约点 9: pyproject 版本 v1.1.79 (单源断言见 test_s10_074_deployment)。"""
        import tomllib

        with open("pyproject.toml", "rb") as fh:
            pp = tomllib.load(fh)
        assert pp["project"]["version"] == "1.1.152"
