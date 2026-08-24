"""tests/console/test_discovery_llm_intelligence.py — S10-099 发现阶段 LLM 深度介入契约测试。

设计: docs/sprint10/S10-099-discovery-llm-plan.md §2/§5
覆盖 (计划 §5 契约点 1-7):
1. 自然描述一次产出: mock LLM → product_description + 全字段 extraction →
   单次 handle 直达 PRODUCT_CONFIRMATION + 理解摘要 (验收 1/4)
2. 控制指令不被当字段: "取消" (确定性) 与 mock LLM 返回 product_description →
   确定性优先; "整理一下" (模糊) mock LLM 返回 control → 整理不创建 (验收 2)
3. 无 LLM 零变化: analyzer=None/装配失败 → 现有状态机逐字段问 (验收 3)
4. 确认摘要展示: LLM 用后确认消息含 "我理解你要做"; 未用 → 不含 (验收 4)
5. 非法 LLM 输出降级: 非 JSON / 缺 schema → 规则兜底, 不崩溃
6. 批量/编辑/逃生回归: 既有 handle_product_answer 分支在 LLM 路径下仍可达
7. 向后兼容: 既有产品/对话测试全绿 (另跑 — 本文件聚焦新契约)

模块级单元: DiscoveryIntentAnalyzer 解析宽容链 / schema 校验 / 默认装配失败
(mock LLM 注入, 不依赖真实 key; 全部测试零真实 LLM 调用)。
"""

from __future__ import annotations

import importlib
import json

import pytest

DI = importlib.import_module("factory-console.session.discovery_intelligence")
CONV = importlib.import_module("factory-console.session.conversation")

STATES = CONV.ConversationState


# ------------------------------------------------------------------ 工具

def _manager(**kw):
    return CONV.ConversationManager(**kw)


def _full_analysis(**overrides) -> dict:
    """完整 product_description 输出 (全字段 extraction — 契约点 1 用)。"""
    data = {
        "category": "product_description",
        "reason": "用户完整描述了产品想法",
        "extraction": {
            "problem": "Markdown 编辑体验割裂, Typora 与 Notepad++ 优点无法兼得",
            "user": "经常写作的移动端用户",
            "core_features": ["沉浸式编辑", "实时预览", "移动端适配"],
            "name": "简记",
            "platform": "mobile",
        },
        "missing_reasons": {},
        "smart_questions": [],
        "proactive": {
            "platform": "mobile",
            "competitors": "Typora / Notepad++",
            "scope": "MVP: 编辑器 + 预览 + 导出",
            "notes": "可考虑云同步",
        },
        "understanding": (
            "我理解你要做一个 Markdown 编辑器, 给经常写作的移动端用户用, "
            "核心是沉浸式编辑/实时预览/移动端适配"
        ),
    }
    data.update(overrides)
    return data


def _partial_analysis() -> dict:
    """缺 user 的 product_description (缺 1 必填 — 智能追问场景)。"""
    data = _full_analysis()
    data["extraction"] = {**data["extraction"], "user": ""}
    data["missing_reasons"] = {"user": "输入里没有提到目标用户"}
    data["smart_questions"] = ["主要给谁用呢? (例如: 个人用户 / 学生 / 中小企业)"]
    return data


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


# ================================================================== 1. 自然描述一次产出 (验收 1/4)

class TestNaturalDescriptionOneShot:
    def test_full_description_direct_to_confirmation(self):
        """计划 §5-1: 初始描述一次产出 → 状态直达 PRODUCT_CONFIRMATION + 理解摘要。"""
        llm_fn, calls = _mock_llm(_full_analysis())
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        resp = mgr.handle("我想做个markdown编辑器, 要typora和notepad++优点, 适配手机")
        assert resp.state == STATES.PRODUCT_CONFIRMATION
        assert resp.ai_generated is True
        assert resp.understanding and "我理解你要做" in resp.understanding
        assert "我理解你要做" in resp.message
        assert "确认创建这个产品? (y/N)" in resp.message
        # 主动分析展示 (仅 LLM 真产出)
        assert resp.proactive and resp.proactive.get("competitors")
        assert "主动建议" in resp.message and "竞品=Typora / Notepad++" in resp.message
        # 结构化提取已并入 ProductIntent (非逐字段问)
        pi = mgr.product_intent
        assert pi is not None
        assert pi.problem and "Markdown" in pi.problem
        assert pi.user and "移动端用户" in pi.user
        assert pi.core_features == ["沉浸式编辑", "实时预览", "移动端适配"]
        assert pi.platform == "mobile"
        assert pi.name == "简记"
        assert mgr._product_pending == []
        # LLM 确实被调用 (非伪造)
        assert calls and calls[0][1] == "discovery_intent"

    def test_partial_description_smart_question(self):
        """缺 1 必填 (输入真没给) → 智能追问 1 条 + 为什么缺, 不机械列全部。"""
        llm_fn, calls = _mock_llm(_partial_analysis())
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        resp = mgr.handle("我想做个markdown编辑器, 要typora优点")
        assert resp.state == STATES.DISCOVERY
        assert mgr._product_pending == ["user"]
        # 已给字段直接填上 (不再问 problem/core_features)
        assert mgr.product_intent.problem and mgr.product_intent.core_features
        assert mgr.product_intent.user is None
        # 智能追问: 最重要 1 条 + 为什么缺
        assert resp.ai_generated is True
        assert "主要给谁用呢" in resp.message
        assert "为什么还问" in resp.message and "目标用户" in resp.message
        # 不重复机械模板 (逐字段问题清单不出现)
        assert "缺失字段: problem" not in resp.message


# ================================================================== 2. 控制指令不被当字段 (验收 2)

class TestControlNotField:
    def test_deterministic_cancel_beats_llm(self):
        """计划 §5-2: "取消" (确定性硬闸) 优先于 mock LLM 的 product_description。"""
        llm_fn, calls = _scripted_llm(_partial_analysis())
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        mgr.handle("我想做个markdown编辑器, 要typora优点")
        n_calls = len(calls)
        resp = mgr.handle("取消")
        assert resp.state == STATES.DISCOVERY
        assert mgr.product_intent is None
        assert "已取消" in resp.message
        assert len(calls) == n_calls  # "取消" 未触发 LLM (确定性优先)

    def test_fuzzy_summary_control_not_field(self):
        """计划 §5-2: "整理一下" (模糊, 确定性漏网) mock LLM 返回 control →
        走整理不创建, 绝不被当字段答案。"""
        llm_fn, calls = _scripted_llm(
            _partial_analysis(),
            _control_analysis("整理一下 是需求整理指令"),
        )
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        mgr.handle("我想做个markdown编辑器, 要typora优点")
        assert mgr.state == STATES.DISCOVERY
        resp = mgr.handle("整理一下")
        assert resp.summary_only is True
        assert resp.state == STATES.DISCOVERY
        assert mgr.product_intent is None
        assert "整理需求" in resp.message
        assert "未创建任何项目" in resp.message
        assert "用户" in resp.message  # 整理摘要包含已收集字段

    def test_query_escapes_flow(self):
        """LLM category=query → 逃生 (passthrough, 交回宿主), 不进字段。"""
        llm_fn, calls = _scripted_llm(
            _partial_analysis(),
            {
                "category": "query",
                "reason": "用户想查看项目列表",
                "extraction": {},
                "missing_reasons": {},
                "smart_questions": [],
                "proactive": {},
                "understanding": "",
            },
        )
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        mgr.handle("我想做个markdown编辑器, 要typora优点")
        resp = mgr.handle("我想看看现在有哪些项目")
        assert resp.passthrough is True
        assert resp.state == STATES.DISCOVERY
        assert mgr.product_intent is None


# ================================================================== 3. 无 LLM 零变化 (验收 3)

class TestNoLlmZeroChange:
    def test_explicit_no_analyzer_still_asks_field_by_field(self):
        """计划 §5-3: analyzer=None → "我想做X" 仍逐字段问 (现有状态机零变化)。"""
        mgr = _manager(analyzer=None)
        resp = mgr.handle("我想做一个台球计分APP")
        assert resp.state == STATES.DISCOVERY
        assert resp.ai_generated is False
        assert "问题" in resp.message or "痛点" in resp.message
        resp = mgr.handle("台球比赛计分麻烦")
        assert mgr.product_intent.problem == "台球比赛计分麻烦"
        assert "目标用户" in resp.message
        resp = mgr.handle("台球爱好者")
        assert "核心功能" in resp.message
        resp = mgr.handle("计分、比赛记录、排行榜")
        assert resp.state == STATES.PRODUCT_CONFIRMATION
        assert resp.ai_generated is False
        assert resp.understanding is None
        assert "我理解你要做" not in resp.message

    def test_analyzer_assembly_failure_zero_change(self, monkeypatch):
        """计划 §5-3: LLM 装配失败 (无 provider/key) → 规则兜底逐字段问。"""
        REASON = importlib.import_module("factory-console.session.reasoning")

        class _BrokenProvider:
            def _default_llm_fn(self):
                raise REASON.ReasoningUnavailable("无可用 provider")

        monkeypatch.setattr(REASON, "ReasoningProvider", _BrokenProvider)
        mgr = _manager()  # 不注入 → 懒装配 → 失败 → None
        resp = mgr.handle("我想做一个台球计分APP")
        assert resp.state == STATES.DISCOVERY
        assert resp.ai_generated is False
        assert "问题" in resp.message or "痛点" in resp.message
        resp = mgr.handle("台球比赛计分麻烦")
        resp = mgr.handle("台球爱好者")
        resp = mgr.handle("计分、比赛记录、排行榜")
        assert resp.state == STATES.PRODUCT_CONFIRMATION
        assert resp.understanding is None
        assert "我理解你要做" not in resp.message


# ================================================================== 4. 确认摘要展示 (验收 4)

class TestConfirmationUnderstanding:
    def test_understanding_shown_only_when_llm_used(self):
        """计划 §5-4: LLM 用后确认含 "我理解你要做"; 未用 → 不含。"""
        # LLM 用后
        llm_fn, _ = _mock_llm(_full_analysis())
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        resp = mgr.handle("我想做个markdown编辑器, 要typora和notepad++优点, 适配手机")
        assert "我理解你要做" in resp.message
        assert resp.ai_generated is True
        # 未用 LLM
        mgr2 = _manager(analyzer=None)
        mgr2.handle("我想做一个台球计分APP")
        mgr2.handle("台球比赛计分麻烦")
        mgr2.handle("台球爱好者")
        resp2 = mgr2.handle("计分、比赛记录、排行榜")
        assert "我理解你要做" not in resp2.message
        assert resp2.ai_generated is False
        assert resp2.understanding is None
        assert resp2.proactive is None

    def test_field_answer_path_no_understanding_without_llm(self):
        """LLM 分类 field_answer → 既有逐字段逻辑; 未用理解 → 确认无摘要。"""
        llm_fn, calls = _scripted_llm(
            _partial_analysis(),  # start: 缺 user → 智能追问
            {
                "category": "field_answer",
                "reason": "用户回答了目标用户字段",
                "extraction": {},
                "missing_reasons": {},
                "smart_questions": [],
                "proactive": {},
                "understanding": "",
            },
        )
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        mgr.handle("我想做个markdown编辑器, 要typora优点")
        assert mgr._product_pending == ["user"]
        resp = mgr.handle("主要给程序员用")
        assert resp.state == STATES.PRODUCT_CONFIRMATION
        assert mgr.product_intent.user == "主要给程序员用"
        assert "确认创建这个产品? (y/N)" in resp.message


# ================================================================== 5. 非法 LLM 输出降级

class TestInvalidOutputFallback:
    @pytest.mark.parametrize("bad_output", [
        "这不是 JSON",
        "{ broken json",
        "```json\n{not json}\n```",
        "",
    ])
    def test_non_json_falls_back(self, bad_output):
        """计划 §5-5: mock 返回非 JSON → 规则兜底逐字段问, 不崩溃。"""
        llm_fn, _ = _mock_llm(bad_output)
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        resp = mgr.handle("我想做一个台球计分APP")
        assert resp.state == STATES.DISCOVERY
        assert resp.ai_generated is False
        assert mgr.product_intent is not None
        assert "问题" in resp.message or "痛点" in resp.message
        resp = mgr.handle("台球比赛计分麻烦")
        assert mgr.product_intent.problem == "台球比赛计分麻烦"
        assert "目标用户" in resp.message

    def test_missing_schema_falls_back(self):
        """计划 §5-5: 合法 JSON 但缺 category → schema 校验失败 → 规则兜底。"""
        llm_fn, _ = _mock_llm({
            "extraction": {"problem": "X", "user": "Y"},
            "understanding": "我理解你要做 X",
        })  # 无 category
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        resp = mgr.handle("我想做一个台球计分APP")
        assert resp.state == STATES.DISCOVERY
        assert resp.ai_generated is False
        assert "问题" in resp.message or "痛点" in resp.message

    def test_llm_exception_falls_back(self):
        """LLM 调用抛异常 → 规则兜底 (不 5xx, 不伪造理解)。"""
        def broken(prompt, operation=""):
            raise RuntimeError("provider timeout")

        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=broken))
        resp = mgr.handle("我想做一个台球计分APP")
        assert resp.state == STATES.DISCOVERY
        assert resp.ai_generated is False
        assert "问题" in resp.message or "痛点" in resp.message


# ================================================================== 6. 批量/编辑/逃生回归 (LLM 路径下仍可达)

class TestExistingBranchesReachable:
    def test_edit_branch_reachable_with_llm(self):
        """确定性编辑指令在 LLM 路径下仍优先 (LLM 不参与编辑)。"""
        llm_fn, calls = _mock_llm(_full_analysis())
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        mgr.start_product_discovery("x")
        n_calls = len(calls)
        resp = mgr.handle_product_answer("修改一下，目标用户改成创业公司")
        assert mgr.product_intent.user == "创业公司"
        assert "确认创建这个产品? (y/N)" in resp.message
        assert len(calls) == n_calls  # 编辑未触发 LLM

    def test_batch_mode_reachable_with_llm(self):
        """批量问题模式 (确定性) 在 LLM 路径下仍可达。"""
        llm_fn, _ = _mock_llm(_partial_analysis())
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        mgr.handle("我想做个markdown编辑器, 要typora优点")
        assert mgr._product_pending == ["user"]
        resp = mgr.handle("问题太多")
        assert mgr._product_batch_mode is True
        assert "剩余需求" in resp.message

    def test_batch_multi_part_reaches_confirmation_with_llm(self):
        """批量后分号补齐: LLM 提取合并 → 直达确认 (不逐个重问)。"""
        llm_fn, calls = _scripted_llm(_partial_analysis(), _full_analysis())
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        mgr.handle("我想做个markdown编辑器, 要typora优点")
        assert mgr._product_pending == ["user"]
        mgr.handle("问题太多")
        resp = mgr.handle("痛点：编辑体验差；用户：写作人群；功能：编辑、预览")
        assert resp.state == STATES.PRODUCT_CONFIRMATION
        assert mgr.product_intent.user and mgr.product_intent.user != "编辑体验差"
        assert "确认创建这个产品? (y/N)" in resp.message


# ================================================================== 模块级单元: 解析宽容链 / schema 校验 / 装配

class TestAnalyzerUnit:
    def test_analyze_normalizes_output(self):
        llm_fn, calls = _mock_llm(_full_analysis())
        a = DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn).analyze("我想做个markdown编辑器")
        assert a.category == "product_description"
        assert a.reason
        assert a.extraction["problem"]
        assert a.extraction["core_features"] == ["沉浸式编辑", "实时预览", "移动端适配"]
        assert a.extraction["name"] == "简记"
        assert a.proactive["competitors"] == "Typora / Notepad++"
        assert a.understanding.startswith("我理解你要做")
        assert a.smart_questions == []
        assert calls and calls[0][1] == "discovery_intent"

    def test_extract_once_is_alias(self):
        llm_fn, _ = _mock_llm(_full_analysis())
        analyzer = DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn)
        assert analyzer.extract_once("x").category == analyzer.analyze("x").category

    def test_prompt_contains_priority_and_history(self):
        llm_fn, calls = _mock_llm(_full_analysis())
        analyzer = DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn)
        analyzer.analyze("给程序员用", history=["我想做个工具", "主要是命令行工具"])
        prompt = calls[0][0]
        assert "优先级: 控制指令 > 查询 > 字段回答 > 产品描述" in prompt
        assert "我想做个工具" in prompt
        assert "主要是命令行工具" in prompt
        assert "给程序员用" in prompt
        assert "product_description" in prompt

    def test_parse_json_fence_stripped(self):
        raw = "```json\n" + json.dumps(_full_analysis(), ensure_ascii=False) + "\n```"
        parsed = DI.DiscoveryIntentAnalyzer._parse_json(raw)
        assert isinstance(parsed, dict)
        assert parsed["category"] == "product_description"

    def test_parse_json_substring_fallback(self):
        raw = "好的, 分析结果: " + json.dumps(_full_analysis(), ensure_ascii=False) + " 以上。"
        parsed = DI.DiscoveryIntentAnalyzer._parse_json(raw)
        assert isinstance(parsed, dict)
        assert parsed["category"] == "product_description"

    def test_parse_json_non_json_returns_raw(self):
        assert DI.DiscoveryIntentAnalyzer._parse_json("不是 JSON") == "不是 JSON"
        assert DI.DiscoveryIntentAnalyzer._parse_json(123) == 123
        assert DI.DiscoveryIntentAnalyzer._parse_json(None) is None

    def test_invalid_category_raises(self):
        llm_fn, _ = _mock_llm(_full_analysis(category="unknown"))
        with pytest.raises(DI.DiscoveryLLMError):
            DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn).analyze("x")

    def test_missing_category_raises(self):
        data = _full_analysis()
        del data["category"]
        llm_fn, _ = _mock_llm(data)
        with pytest.raises(DI.DiscoveryLLMError):
            DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn).analyze("x")

    def test_extraction_missing_fields_filled(self):
        llm_fn, _ = _mock_llm(_full_analysis(extraction={"problem": "P"}))
        a = DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn).analyze("x")
        assert a.extraction["problem"] == "P"
        assert a.extraction["user"] == ""
        assert a.extraction["core_features"] == []
        assert a.extraction["name"] == ""
        assert a.extraction["platform"] == ""

    def test_extraction_non_dict_tolerated(self):
        llm_fn, _ = _mock_llm(_full_analysis(extraction="oops"))
        a = DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn).analyze("x")
        assert a.extraction["problem"] == "" and a.extraction["core_features"] == []

    def test_smart_questions_truncated_to_3(self):
        llm_fn, _ = _mock_llm(_full_analysis(smart_questions=["q1", "q2", "q3", "q4", "q5"]))
        a = DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn).analyze("x")
        assert len(a.smart_questions) == 3

    def test_smart_questions_string_normalized(self):
        llm_fn, _ = _mock_llm(_full_analysis(smart_questions="谁用?"))
        a = DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn).analyze("x")
        assert a.smart_questions == ["谁用?"]

    def test_proactive_list_joined(self):
        data = _full_analysis(proactive={"competitors": ["Typora", "Notepad++"]})
        llm_fn, _ = _mock_llm(data)
        a = DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn).analyze("x")
        assert a.proactive["competitors"] == "Typora、Notepad++"

    def test_empty_input_raises(self):
        with pytest.raises(DI.DiscoveryLLMError):
            DI.DiscoveryIntentAnalyzer(llm_fn=lambda p, o="": "{}").analyze("   ")

    def test_default_llm_unavailable_raises(self, monkeypatch):
        """llm_fn=None 且装配失败 → DiscoveryLLMUnavailable (上层规则兜底)。"""
        REASON = importlib.import_module("factory-console.session.reasoning")

        class _BrokenProvider:
            def _default_llm_fn(self):
                raise REASON.ReasoningUnavailable("无 provider")

        monkeypatch.setattr(REASON, "ReasoningProvider", _BrokenProvider)
        with pytest.raises(DI.DiscoveryLLMUnavailable):
            DI.DiscoveryIntentAnalyzer()


# ============================================================== 多轮字段合并边界 (修复)

class TestMultiTurnFieldMerge:
    """LLM 多轮合并: 用户对智能追问的回答 → field_answer 并入, 不当新描述覆盖。"""

    def test_system_question_injected_and_answer_merged(self):
        """第 1 轮缺 user → 智能追问; 第 2 轮回答 → system_question 传入 + 并入。"""
        partial = _partial_analysis()  # 缺 user, 问 "主要给谁用呢?"
        field_answer = {
            "category": "field_answer",
            "reason": "用户回答上一轮问题",
            "extraction": {"user": "给经常写作的人用"},
            "missing_reasons": {},
            "smart_questions": [],
            "proactive": {},
            "understanding": "",
        }
        llm_fn, calls = _scripted_llm(partial, field_answer)
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))

        r1 = mgr.handle("我想做个 markdown 编辑器, 适配手机")
        assert r1.needs_input is True  # 智能追问
        # 第 2 轮: 回答追问
        r2 = mgr.handle("给经常写作的人用")
        assert r2 is not None
        # 断言: 第 2 轮 LLM 调用 prompt 注入了 system_question（上一轮追问）
        assert len(calls) >= 2
        second_prompt = calls[1][0]
        assert "主要给谁用呢" in second_prompt  # 系统上一轮问题在 prompt
        assert "系统上一轮问题" in second_prompt
        # 断言: user 被并入, 且未覆盖其他已填字段
        pi = mgr.product_intent
        assert pi.user == "给经常写作的人用"
        assert pi.problem  # 已填的 problem 保留（不被覆盖）
        assert pi.name  # name 保留

    def test_system_question_empty_on_first_turn(self):
        """第 1 轮 system_question 应为 (无)。"""
        llm_fn, calls = _mock_llm(_partial_analysis())
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        mgr.handle("我想做个 markdown 编辑器")
        assert len(calls) >= 1
        assert "系统上一轮问题" in calls[0][0]
        assert "(无)" in calls[0][0]
