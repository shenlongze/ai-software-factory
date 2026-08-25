"""tests/console/test_s10_118_discovery_context_keep.py — 发现对话上下文保持 + 委托/求助口语全覆盖 (S10-118)。

Bug (Founder 实测 v1.1.85): "你把控一下" 后上下文断。
根因:
A. 无 LLM 机械路径: "你把控一下"/"给我一点建议" 未命中 HELP_KEYWORDS →
   _resolve_answer_field 未命中模式 → 填当前字段 (静默污染)
B. 有 LLM 路径: 同上未命中硬闸 → LLM 判 query → _escape_product_flow 调
   _reset_product_flow() 清空 product_intent/pending → 上下文断 + 宿主泛答

策略 (Founder 拍板): 未配置 LLM → 确定性兜底保留; 已配置必须走 LLM;
已配置但调用失败 → 用户可读报错 (网络/超时/限流/5xx), 状态保留可重试。

覆盖:
1. HELP_KEYWORDS 覆盖新口语变体 (把控/给我一点建议/委托系)
2. 无 LLM: "你把控一下"/"给我一点建议" → 建议展示, 不填字段 (Bug A 修复)
3. 有 LLM query 逃生 → product_intent/pending 保留 (挂起语义, Bug B 修复)
4. 已配置 LLM 失败 (429) → 可读报错 + pending 保留
5. 未配置 (ReasoningUnavailable) → 仍机械兜底 (策略保留)
6. 错误分类单元: server_error/auth/network/timeout/rate_limit
7. 正常回答零变化 (不因新关键词误伤字段归类)
8. 报错后重试可继续 (状态保留 → 下一轮正常推进)
9. 显式取消仍清空 (挂起 ≠ 永不释放)
"""

from __future__ import annotations

import importlib

import pytest

CONV = importlib.import_module("factory-console.session.conversation")
DI = importlib.import_module("factory-console.session.discovery_intelligence")
GUIDE = importlib.import_module("factory-console.session.discovery_guide")
REASON = importlib.import_module("factory-console.session.reasoning")

STATES = CONV.ConversationState


@pytest.fixture(autouse=True)
def _no_provider(monkeypatch):
    """默认模拟无 LLM provider/key (规则兜底); 显式注入 analyzer 的测试不受影响。"""

    class _BrokenProvider:
        def _default_llm_fn(self):
            raise REASON.ReasoningUnavailable("无可用 provider (测试模拟)")

    monkeypatch.setattr(REASON, "ReasoningProvider", _BrokenProvider)


def _body(msg: str) -> str:
    """去掉 guide 前缀 (生命周期/产品定义进度行) → 消息正文。"""
    lines = (msg or "").split("\n")
    out: list[str] = []
    started = False
    for ln in lines:
        if not started and (
            ln.startswith("流程:") or ln.startswith("产品定义") or ln.startswith("增强(可选):")
        ):
            continue
        started = True
        out.append(ln)
    return "\n".join(out)


def _fill_two(mgr) -> None:
    """机械路径填 problem/user (analyzer=None) → pending=[core_features]。"""
    assert mgr._product_pending == ["problem", "user", "core_features"]
    mgr.handle("简单、易用、高效")   # problem
    mgr.handle("给个人用户用")        # user
    assert mgr._product_pending == ["core_features"]


class TestHelpKeywords:
    def test_new_variants_covered(self):
        """S10-118 新口语变体全在 HELP_KEYWORDS (确定性硬闸)。"""
        for kw in ("把控", "给我一点建议", "给我建议", "提点建议", "给个方向",
                   "你来想", "帮我想想", "你拿主意"):
            assert kw in GUIDE.HELP_KEYWORDS, f"缺 {kw}"

    def test_normal_answers_not_matched(self):
        """不误伤: "建议" 单独出现 / 正常字段回答 不触发求助。"""
        assert not CONV.ConversationManager._is_help_request("建议使用扫码")
        assert not CONV.ConversationManager._is_help_request("功能包括记账、统计")


class TestMechanicalPathNoPollution:
    """Bug A: 无 LLM 路径委托/求助不当字段值。"""

    def test_ni_ba_kong_shows_suggestions(self):
        mgr = CONV.ConversationManager(analyzer=None)
        mgr.handle("我想做个记账App")
        _fill_two(mgr)
        r = mgr.handle("你把控一下")
        assert mgr._product_pending == ["core_features"]  # 不填字段
        assert "建议" in _body(r.message)

    def test_gei_wo_yidian_jianyi_shows_suggestions(self):
        mgr = CONV.ConversationManager(analyzer=None)
        mgr.handle("我想做个记账App")
        _fill_two(mgr)
        r = mgr.handle("给我一点建议")
        assert mgr._product_pending == ["core_features"]
        assert "建议" in _body(r.message)


class TestEscapeSuspendsContext:
    """Bug B: 逃生 → 挂起而非清空 (有 LLM query / 宿主重分发同路径)。"""

    def test_escape_keeps_product_state(self):
        mgr = CONV.ConversationManager(analyzer=None)
        mgr.handle("我想做个记账App")
        _fill_two(mgr)  # pending=[core_features]
        before = (list(mgr._product_pending),
                  mgr.product_intent.problem if mgr.product_intent else None)
        r = mgr._escape_product_flow("项目列表")  # 逃生 (宿主要求查看列表)
        after = (list(mgr._product_pending),
                 mgr.product_intent.problem if mgr.product_intent else None)
        assert before == after
        assert before[0] == ["core_features"]   # 现场保留, 可继续
        assert getattr(r, "passthrough", False) is True

    def test_llm_query_escape_keeps_state(self):
        """LLM 判 query → 逃生后 pending/product_intent 保留 (end-to-end)。"""
        def query_llm(prompt, operation=""):
            return {"category": "query", "reason": "非发现意图",
                    "extraction": {}, "missing_reasons": {}, "smart_questions": [],
                    "proactive": {}, "understanding": "", "suggestions": {}}

        mgr = CONV.ConversationManager(analyzer=None)
        mgr.handle("我想做个记账App")
        _fill_two(mgr)
        # 注入 query LLM 分析器 (重置缓存), 验证 LLM 判 query 路径不丢现场
        mgr._discovery_analyzer = CONV._DISCOVERY_ANALYZER_UNSET
        mgr._discovery_analyzer_override = DI.DiscoveryIntentAnalyzer(llm_fn=query_llm)
        before = (list(mgr._product_pending),
                  mgr.product_intent.problem if mgr.product_intent else None)
        mgr.handle("看看项目列表")
        after = (list(mgr._product_pending),
                 mgr.product_intent.problem if mgr.product_intent else None)
        assert before == after
        assert before[0] == ["core_features"]

    def test_cancel_still_clears(self):
        """挂起 ≠ 永不释放: 显式取消仍清空。"""
        mgr = CONV.ConversationManager(analyzer=None)
        mgr.handle("我想做个记账App")
        _fill_two(mgr)
        mgr._escape_product_flow("项目列表")
        assert mgr._product_pending == ["core_features"]  # 挂起保留
        mgr._cancel_product_discovery()
        assert mgr._product_pending == []
        assert mgr.product_intent is None


class TestLlmFailurePolicy:
    """Founder 策略: 已配置 LLM 失败 → 可读报错 + 状态保留; 未配置 → 兜底。"""

    def test_configured_failure_readable_error_and_state_kept(self):
        def fail_llm(prompt, operation=""):
            raise REASON.ReasoningError("openai http 429: rate limited")

        mgr = CONV.ConversationManager(
            analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=fail_llm)
        )
        mgr.handle("我想做个记账App")
        r = mgr.handle("简单、易用")
        body = _body(r.message)
        assert "限流" in body          # 用户可读
        assert "429" in body
        assert mgr._product_pending     # 状态保留 (可重试)

    def test_unconfigured_still_fallback(self):
        """未配置 (ReasoningUnavailable) → 机械兜底, 不报错。"""
        def unavail_llm(prompt, operation=""):
            raise REASON.ReasoningUnavailable("未配置 provider")

        mgr = CONV.ConversationManager(
            analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=unavail_llm)
        )
        mgr.handle("我想做个记账App")
        r = mgr.handle("简单、易用")
        assert "限流" not in _body(r.message)

    def test_error_classification(self):
        cases = [
            ("openai http 500: internal", "server_error"),
            ("openai http 401: bad key", "auth"),
            ("openai http 429: rate limited", "rate_limit"),
            ("openai request failed: ConnectError", "network"),
            ("openai request failed: ReadTimeout", "timeout"),
        ]
        for msg, want in cases:
            got = CONV._classify_llm_error(REASON.ReasoningError(msg)).kind
            assert got == want, f"{msg} → {got}, 期望 {want}"

    def test_retry_after_error_continues(self):
        """报错后用户重发 → 正常推进 (状态保留)。"""
        calls: list[str] = []

        def flaky_llm(prompt, operation=""):
            calls.append(operation)
            if len(calls) == 1:
                raise REASON.ReasoningError("openai http 500: boom")
            return {"category": "field_answer", "reason": "回答当前问题",
                    "extraction": {}, "missing_reasons": {}, "smart_questions": [],
                    "proactive": {}, "understanding": "", "suggestions": {}}

        mgr = CONV.ConversationManager(
            analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=flaky_llm)
        )
        mgr.handle("我想做个记账App")     # call1: 失败 → 报错
        mgr.handle("简单、易用")           # call2: field_answer → problem
        assert mgr.product_intent.problem == "简单、易用"
        assert mgr._product_pending == ["user", "core_features"]
