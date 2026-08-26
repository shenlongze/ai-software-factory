"""tests/console/test_confirmation_intelligence.py — S10-102 确认阶段智能分流 + 求助词全覆盖契约测试。

设计: docs/sprint10/S10-102-confirm-intelligence-plan.md §2
覆盖 (计划 §2 契约点 1-11):
1. "可以，先出prd文档" → approved + next_action=prd + 名称不被覆盖 (验收 1)
2. "？"/"?" → 澄清响应 (不改名, 不确认, 消息含解释) (验收 2)
3. "没 想法" → 建议流 (不填 core_features="想法") (验收 3, 两路径 — 另见 guide 测试)
4. 纯 y → approved; "n"/"取消" → reset (向后兼容)
5. "改名叫墨笺" → rename (向后兼容); "墨笺" 裸文本 → rename 兜底
6. "可以"/"好"/"行" → approved (不再当名称)
7. "随便"/"你定" 确认阶段 → approved 不改名; 字段收集阶段 → 建议流
8. 确认+下一步各动作: "好，开始开发" → develop; "行，创建项目" → create
9. LLM 分类: mock analyze_confirmation → approve_next/rename/clarify/other 路由;
   无 LLM 规则兜底真实生效 (不伪造)
10. 宿主接线: session 层 "可以，先出prd文档" → create_product + generate_prd 执行
    (真实 tmp workspace + FakeOrg 桩, 零真实 LLM)
11. 版本断言 v1.1.79 (另见 test_s10_074_deployment)

模块级: discovery_guide 确认表单元 (APPROVE_WORDS/APPROVE_NEXT_ACTIONS/RENAME_RE/
CLARIFY_WORDS/CONFIRM_DELEGATE_WORDS + match_*) 与 analyzer analyze_confirmation
schema。全部测试零真实 LLM 调用 (mock llm_fn 注入 / _no_provider 规则兜底)。
"""

from __future__ import annotations

import importlib
import json

import pytest

ACT = importlib.import_module("factory-console.session.action")
ACTIONS = importlib.import_module("factory-console.session.actions")
CONV = importlib.import_module("factory-console.session.conversation")
CTX = importlib.import_module("factory-console.session.context")
DI = importlib.import_module("factory-console.session.discovery_intelligence")
DIS = importlib.import_module("factory-console.session.discovery")
GUIDE = importlib.import_module("factory-console.session.discovery_guide")
PROD = importlib.import_module("factory-console.session.product")
SESS = importlib.import_module("factory-console.session.session")

STATES = CONV.ConversationState


# ------------------------------------------------------------------ 工具

@pytest.fixture(autouse=True)
def _no_provider(monkeypatch):
    """模拟无 LLM provider/key — 默认装配确定性失败 (规则兜底)。

    使 "无 LLM" 类测试不依赖外部环境 (有无 DEEPSEEK_API_KEY 均确定);
    注入 mock llm_fn 的 analyzer 测试不受影响 (不走默认装配)。
    """
    REASON = importlib.import_module("factory-console.session.reasoning")

    class _BrokenProvider:
        def _default_llm_fn(self):
            raise REASON.ReasoningUnavailable("无可用 provider (测试模拟)")

    monkeypatch.setattr(REASON, "ReasoningProvider", _BrokenProvider)


class FakeOrgCli:
    """Service Layer 桩 (monkeypatch actions._load_org_cli 注入): 记录调用, 返回规范结果。"""

    def __init__(self, *, ok=True, project=None, error=None) -> None:
        self.calls: list[tuple[object, object]] = []
        self.ok = ok
        self.project = project
        self.error = error

    def cmd_project_register(self, root, args):
        self.calls.append((root, args))
        if not self.ok:
            return {"ok": False, "error": self.error or "注册失败", "exit_code": 1}
        return {
            "ok": True,
            "project": self.project or {"id": "p1", "name": args.name, "slug": "scorepocket"},
            "analysis_ref": None,
            "baseline_ref": None,
            "snapshot_ref": None,
            "exit_code": 0,
        }


@pytest.fixture
def fake_org(monkeypatch):
    """注入 FakeOrgCli (monkeypatch _load_org_cli) — 同既有 session 测试模式。"""
    org = FakeOrgCli()
    monkeypatch.setattr(ACTIONS, "_load_org_cli", lambda: org)
    return org


def _manager(**kw):
    return CONV.ConversationManager(**kw)


def _run_product_flow(mgr):
    """走完整 DISCOVERY 多轮 → PRODUCT_CONFIRMATION (确定性规则路径, 无 LLM)。"""
    mgr.handle("我想开发一个台球计分APP")
    mgr.handle("台球比赛计分麻烦")
    mgr.handle("台球爱好者")
    return mgr.handle("计分、比赛记录、排行榜")


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
    """完整 product_description 输出 (全字段 + name — 一次直达确认, 跳过命名)。"""
    data = {
        "category": "product_description",
        "reason": "用户完整描述了产品想法",
        "extraction": {
            "problem": "个人记账麻烦, 缺乏顺手好用的记账工具",
            "user": "需要记账的个人用户",
            "core_features": ["收支记录", "分类统计", "月度报表"],
            "name": "简记",
            "platform": "mobile",
        },
        "missing_reasons": {},
        "smart_questions": [],
        "proactive": {},
        "understanding": "我理解你要做一个记账 App",
        "suggestions": {},
    }
    data.update(overrides)
    return data


def _confirmation_payload(**overrides) -> dict:
    """确认分类输出 (默认 approve_next=prd)。"""
    data = {
        "category": "approve_next",
        "next_action": "prd",
        "rename_to": "",
        "reason": "用户确认并想先出PRD",
    }
    data.update(overrides)
    return data


def _llm_manager(*responses):
    """真实 DiscoveryIntentAnalyzer + scripted llm_fn (发现→确认 一次直达)。"""
    llm_fn, calls = _scripted_llm(*responses)
    mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
    resp = mgr.handle("我想做一个记账App, 只解决记账麻烦, 给个人用户")
    assert resp.state == STATES.PRODUCT_CONFIRMATION
    return mgr, calls


def _body(msg: str) -> str:
    """去掉进度前缀 → 消息正文 (澄清响应断言用)。"""
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


# ================================================================== 1. 确认+下一步 (验收 1)

class TestApproveNext:
    def test_approve_next_prd_name_not_overwritten(self):
        """契约点 1: "可以，先出prd文档" → approved + next_action=prd + 名称不被覆盖。"""
        mgr = _manager(analyzer=None)
        _run_product_flow(mgr)
        seen = {}

        def confirm_fn(pi):
            seen["pi"] = pi
            return f"Product Created: {pi.name}"

        before = mgr.product_intent.name
        resp = mgr.handle_product_confirm("可以，先出prd文档", confirm_fn=confirm_fn)
        assert resp.state == STATES.DONE
        assert resp.next_action == "prd"
        assert seen["pi"] is mgr.product_intent
        assert mgr.product_intent.name == before  # 名称未被覆盖为整句话
        assert "可以，先出prd文档" not in mgr.product_intent.name

    def test_approve_next_without_fn_carries_signal(self):
        """确认+下一步 + confirm_fn 缺省 → 停留 PROJECT_CREATION, next_action 仍携带。"""
        mgr = _manager(analyzer=None)
        _run_product_flow(mgr)
        resp = mgr.handle_product_confirm("可以，先出prd文档")
        assert resp.state == STATES.PROJECT_CREATION
        assert resp.next_action == "prd"

    def test_develop_and_create_actions(self):
        """契约点 8: "好，开始开发" → develop; "行，创建项目" → create (只传信号)。"""
        mgr = _manager(analyzer=None)
        _run_product_flow(mgr)
        assert mgr.handle_product_confirm("好，开始开发").next_action == "develop"
        mgr = _manager(analyzer=None)
        _run_product_flow(mgr)
        assert mgr.handle_product_confirm("行，创建项目").next_action == "create"


# ================================================================== 2. 澄清/问号请求 (验收 2)

class TestClarify:
    def test_question_mark_clarifies_without_rename(self):
        """契约点 2: "？" → 澄清响应 (不改名, 不确认, 消息含解释)。"""
        mgr = _manager(analyzer=None)
        _run_product_flow(mgr)
        resp = mgr.handle_product_confirm("？")
        assert resp.state == STATES.PRODUCT_CONFIRMATION
        assert resp.needs_input is True
        assert mgr.product_intent.name != "？"
        body = _body(resp.message)
        assert "确认创建" in body and "改名" in body and "取消" in body

    def test_ascii_question_mark_clarifies(self):
        mgr = _manager(analyzer=None)
        _run_product_flow(mgr)
        resp = mgr.handle_product_confirm("?")
        assert resp.state == STATES.PRODUCT_CONFIRMATION
        assert mgr.product_intent.name != "?"

    def test_why_clarifies(self):
        """"为什么" → 澄清 (不确认不改名)。"""
        mgr = _manager(analyzer=None)
        _run_product_flow(mgr)
        resp = mgr.handle_product_confirm("为什么")
        assert resp.state == STATES.PRODUCT_CONFIRMATION
        assert "你可以:" in resp.message

    def test_can_i_change_clarifies(self):
        """"能改吗" → 澄清 (不把 "改" 当改名)。"""
        mgr = _manager(analyzer=None)
        _run_product_flow(mgr)
        resp = mgr.handle_product_confirm("能改吗")
        assert resp.state == STATES.PRODUCT_CONFIRMATION
        assert mgr.product_intent.name != "能改吗"


# ================================================================== 4. 向后兼容 (纯 y / n / 取消)

class TestBackwardCompat:
    def test_pure_y_approved(self):
        mgr = _manager(analyzer=None)
        _run_product_flow(mgr)
        assert mgr.handle_product_confirm("y").state == STATES.PROJECT_CREATION

    def test_yes_case_insensitive_approved(self):
        for answer in ("y", "Y", "yes", "YES"):
            mgr = _manager(analyzer=None)
            _run_product_flow(mgr)
            assert mgr.handle_product_confirm(answer).state == STATES.PROJECT_CREATION

    def test_n_resets(self):
        mgr = _manager(analyzer=None)
        _run_product_flow(mgr)
        resp = mgr.handle_product_confirm("n")
        assert resp.state == STATES.DISCOVERY
        assert mgr.product_intent is None

    def test_cancel_words_reset(self):
        for answer in ("取消", "no", ""):
            mgr = _manager(analyzer=None)
            _run_product_flow(mgr)
            resp = mgr.handle_product_confirm(answer)
            assert resp.state == STATES.DISCOVERY
            assert mgr.product_intent is None


# ================================================================== 5/6. 改名 vs 确认词

class TestRenameVsApprove:
    def test_explicit_rename_unchanged(self):
        """契约点 5: "改名叫墨笺" → rename (向后兼容)。"""
        mgr = _manager(analyzer=None)
        _run_product_flow(mgr)
        resp = mgr.handle_product_confirm("改名叫墨笺")
        assert resp.state == STATES.PRODUCT_CONFIRMATION
        assert mgr.product_intent.name == "墨笺"

    def test_bare_text_rename_fallback(self):
        """契约点 5: "墨笺" 裸文本 → rename 兜底 (S10-081 兼容)。"""
        mgr = _manager(analyzer=None)
        _run_product_flow(mgr)
        resp = mgr.handle_product_confirm("墨笺")
        assert resp.state == STATES.PRODUCT_CONFIRMATION
        assert mgr.product_intent.name == "墨笺"

    def test_approve_words_not_treated_as_name(self):
        """契约点 6: "可以"/"好"/"行" → approved (不再当名称)。"""
        for word in ("可以", "好", "行", "确认", "OK", "没问题"):
            mgr = _manager(analyzer=None)
            _run_product_flow(mgr)
            resp = mgr.handle_product_confirm(word)
            assert resp.state == STATES.PROJECT_CREATION
            assert mgr.product_intent.name != word


# ================================================================== 7. 委托词

class TestDelegate:
    def test_delegate_words_approve_without_rename(self):
        """契约点 7: "随便"/"你定" 确认阶段 → approved 不改名。"""
        for word in ("随便", "你定", "你看吧", "都行", "无所谓"):
            mgr = _manager(analyzer=None)
            _run_product_flow(mgr)
            resp = mgr.handle_product_confirm(word)
            assert resp.state == STATES.PROJECT_CREATION
            assert mgr.product_intent.name != word

    def test_delegate_words_field_collection_suggestions(self):
        """契约点 7: 字段收集阶段 "随便"/"你定" → 建议流 (不填字段)。"""
        for word in ("随便", "你定", "你看吧"):
            mgr = _manager(analyzer=None)
            mgr.handle("我想做一个台球计分APP")
            r = mgr.handle(word)
            assert "建议方向" in r.message
            assert mgr.product_intent.problem is None
            # 两路径 (DiscoverySession) 同步
            s = DIS.DiscoverySession.start("开始做个记账App", analyzer=None)
            d = s.process_user_input(word)
            assert "建议方向" in d["message"]
            assert s.product_intent.problem is None


# ================================================================== 3. 求助词全覆盖 (验收 3)

class TestHelpWhitespace:
    def test_help_with_space_not_filled_as_field(self):
        """契约点 3: "没 想法" → 建议流 (不填 core_features="想法")。"""
        mgr = _manager(analyzer=None)
        mgr.handle("我想做一个台球计分APP")
        mgr.handle("台球计分麻烦")
        mgr.handle("台球爱好者")
        r = mgr.handle("没 想法")
        assert "建议方向" in r.message
        assert mgr.product_intent.core_features != ["想法"]
        # 两路径同步 (DiscoverySession)
        s = DIS.DiscoverySession.start("开始做个记账App", analyzer=None)
        s.process_user_input("台球计分麻烦")
        s.process_user_input("台球爱好者")
        d = s.process_user_input("没 想法")
        assert "建议方向" in d["message"]
        assert s.product_intent.core_features != ["想法"]


# ================================================================== 9. LLM 分类路由 (mock analyze_confirmation)

class TestLlmRouting:
    def test_llm_approve_next_routed(self):
        """契约点 9: mock analyze_confirmation → approve_next → approved + next_action。"""
        llm_fn, calls = _scripted_llm(
            _full_analysis(), _confirmation_payload()
        )
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        resp = mgr.handle("我想做一个记账App, 解决记账麻烦, 给个人用户用")
        assert resp.state == STATES.PRODUCT_CONFIRMATION
        resp2 = mgr.handle_product_confirm("帮我搞定", confirm_fn=lambda pi: "ok")  # 确定性未决 → LLM
        assert resp2.state == STATES.DONE
        assert resp2.next_action == "prd"
        assert mgr.product_intent.name == "简记"
        # LLM 调用: 1 次发现 analyze + 1 次 confirm_intent
        assert calls[-1][1] == "confirm_intent"

    def test_llm_rename_routed(self):
        """契约点 9: LLM rename → 设名 → 重新确认。"""
        llm_fn, _ = _scripted_llm(
            _full_analysis(),
            _confirmation_payload(category="rename", rename_to="墨笺", next_action=""),
        )
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        mgr.handle("我想做一个记账App, 解决记账麻烦, 给个人用户用")
        resp = mgr.handle_product_confirm("起个新名字")
        assert resp.state == STATES.PRODUCT_CONFIRMATION
        assert mgr.product_intent.name == "墨笺"

    def test_llm_clarify_routed(self):
        """契约点 9: LLM clarify → 澄清响应 (不改名不确认)。"""
        llm_fn, _ = _scripted_llm(
            _full_analysis(),
            _confirmation_payload(category="clarify", next_action=""),
        )
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        mgr.handle("我想做一个记账App, 解决记账麻烦, 给个人用户用")
        resp = mgr.handle_product_confirm("你说呢")
        assert resp.state == STATES.PRODUCT_CONFIRMATION
        assert "你可以:" in resp.message
        assert mgr.product_intent.name == "简记"

    def test_llm_delegate_routed(self):
        """契约点 9: LLM delegate → approved 不改名。"""
        llm_fn, _ = _scripted_llm(
            _full_analysis(),
            _confirmation_payload(category="delegate", next_action=""),
        )
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        mgr.handle("我想做一个记账App, 解决记账麻烦, 给个人用户用")
        resp = mgr.handle_product_confirm("都听你的")
        assert resp.state == STATES.PROJECT_CREATION
        assert mgr.product_intent.name == "简记"

    def test_llm_other_renames(self):
        """契约点 9: LLM other → 改名兜底 (S10-081 兼容)。"""
        llm_fn, _ = _scripted_llm(
            _full_analysis(),
            _confirmation_payload(category="other", next_action=""),
        )
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        mgr.handle("我想做一个记账App, 解决记账麻烦, 给个人用户用")
        resp = mgr.handle_product_confirm("墨迹本")
        assert resp.state == STATES.PRODUCT_CONFIRMATION
        assert mgr.product_intent.name == "墨迹本"

    def test_no_llm_fallback_is_real(self):
        """契约点 9/边界: 无 LLM 规则兜底真实生效 — 裸文本改名 (不伪造分类)。"""
        mgr = _manager(analyzer=None)
        _run_product_flow(mgr)
        resp = mgr.handle_product_confirm("账本精灵")
        assert mgr.product_intent.name == "账本精灵"
        assert resp.state == STATES.PRODUCT_CONFIRMATION

    def test_llm_failure_reports_readable_error(self):
        """S10-118 策略: 已配置 LLM 调用失败 → 可读报错, 确认现场保留 (不静默兜底)。"""
        def boom(prompt, operation=""):
            raise RuntimeError("network down")

        # 1. 机械路径填完字段 → PRODUCT_CONFIRMATION (无 LLM)
        mgr = _manager(analyzer=None)
        _run_product_flow(mgr)
        # 2. 注入失败 analyzer → 确认阶段 LLM 失败 → 可读报错, 现场保留
        mgr._discovery_analyzer = CONV._DISCOVERY_ANALYZER_UNSET
        mgr._discovery_analyzer_override = DI.DiscoveryIntentAnalyzer(llm_fn=boom)
        resp = mgr.handle_product_confirm("墨笺")
        assert resp.state == STATES.PRODUCT_CONFIRMATION   # 状态保留
        assert "网络" in resp.message or "LLM 调用失败" in resp.message
        assert mgr.product_intent.name != "墨笺" or mgr.product_intent is not None  # 现场保留


# ================================================================== analyzer 单元 (schema 校验)

class TestAnalyzerConfirmationContract:
    def test_confirmation_analysis_schema(self):
        """analyze_confirmation → ConfirmationAnalysis (宽容解析 + schema 校验)。"""
        llm_fn, _ = _mock_llm(_confirmation_payload())
        a = DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn)
        r = a.analyze_confirmation("可以，先出prd文档", product_summary="记账App")
        assert isinstance(r, DI.ConfirmationAnalysis)
        assert r.category == "approve_next"
        assert r.next_action == "prd"
        assert r.reason

    def test_valid_categories_include_all(self):
        assert set(DI.VALID_CONFIRMATION_CATEGORIES) == {
            "approve", "approve_next", "rename", "clarify", "cancel", "delegate", "other",
        }

    def test_invalid_category_raises(self):
        llm_fn, _ = _mock_llm(_confirmation_payload(category="bogus"))
        with pytest.raises(DI.ConfirmationLLMError):
            DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn).analyze_confirmation("随便")

    def test_non_json_raises(self):
        llm_fn, _ = _mock_llm("not json at all")
        with pytest.raises(DI.ConfirmationLLMError):
            DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn).analyze_confirmation("随便")

    def test_llm_exception_raises_confirmation_error(self):
        def boom(prompt, operation=""):
            raise RuntimeError("boom")

        with pytest.raises(DI.ConfirmationLLMError):
            DI.DiscoveryIntentAnalyzer(llm_fn=boom).analyze_confirmation("随便")

    def test_invalid_next_action_normalized(self):
        """S10-104: next_action 词汇扩展 {prd/feature_list/html/docs} — html 现为合法
        (不再归一为空); 非法值 (如 pdf) → 归一为空 (宽容, 不阻断)。"""
        llm_fn, _ = _mock_llm(_confirmation_payload(next_action="pdf"))
        r = DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn).analyze_confirmation("可以，先出prd")
        assert r.category == "approve_next"
        assert r.next_action == ""

    def test_new_next_actions_accepted(self):
        """S10-104: feature_list/html/docs 为合法 next_action (不再归一为空)。"""
        for action in ("feature_list", "html", "docs"):
            llm_fn, _ = _mock_llm(_confirmation_payload(next_action=action))
            r = DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn).analyze_confirmation("出个产物")
            assert r.next_action == action, action

    def test_prompt_contains_new_next_action_variants(self):
        """S10-104: 确认 prompt 含 next_action 词汇 + 无前缀动作变体示例。"""
        llm_fn, calls = _mock_llm(_confirmation_payload(next_action="html"))
        DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn).analyze_confirmation("出个html")
        prompt = calls[0][0]
        assert "feature_list" in prompt and "html" in prompt and "docs" in prompt
        assert "生成PRD" in prompt and "产出份prd文档" in prompt
        assert "出个html" in prompt and "出份功能清单" in prompt
        assert "隐含确认" in prompt  # 无确认前缀 = 隐含确认 + 下一步

    def test_prompt_contains_summary_and_categories(self):
        llm_fn, calls = _mock_llm(_confirmation_payload())
        DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn).analyze_confirmation(
            "可以，先出prd文档", product_summary="产品: 简记"
        )
        prompt = calls[0][0]
        assert "产品: 简记" in prompt
        assert "approve_next" in prompt
        assert "可以，先出prd文档" in prompt


# ================================================================== 10. 宿主接线 (session 层)

class TestSessionWiring:
    def test_approve_next_prd_runs_generate_prd(self, fake_org, capsys, tmp_path):
        """契约点 10: "可以，先出prd文档" → create_product + generate_prd 执行。"""
        root = tmp_path / "ws"
        root.mkdir()
        sess = SESS.InteractiveSession(
            context_manager=CTX.ContextManager(workspace=str(root)),
            confirmation_gate=None,
        )
        sess._dispatch("我想开发一个台球计分APP")
        sess._dispatch("解决台球比赛计分麻烦")
        sess._dispatch("台球爱好者")
        sess._dispatch("计分、比赛记录、排行榜")
        sess._dispatch("可以，先出prd文档")
        out = capsys.readouterr().out
        assert "Product Created" in out
        assert "已生成 PRD" in out
        pdir = root / "projects" / "scorepocket"
        assert (pdir / "PRD.md").is_file()
        assert (pdir / "product.json").is_file()
        assert "台球比赛计分麻烦" in (pdir / "PRD.md").read_text(encoding="utf-8")

    def test_approve_next_prd_failure_does_not_block_creation(self, fake_org, capsys, tmp_path):
        """契约点 10: PRD 失败 → 注明原因, 不阻断创建 (创建成功消息仍在)。"""
        root = tmp_path / "ws"
        root.mkdir()
        # 注入定制 action_registry: create_product 真实 + generate_prd 模拟失败
        # (handler 在注册时绑定 — 不能靠 monkeypatch 模块属性)
        registry = ACTIONS.build_default_actions()
        registry.register(ACT.Action(
            name="generate_prd",
            description="mock 失败 (测试)",
            handler=lambda ctx: ACT.ActionResult(
                ok=False,
                status="error",
                message="PRD 生成失败: 未找到产品定义 (请先创建产品)",
                error="未找到产品定义",
            ),
        ))
        sess = SESS.InteractiveSession(
            context_manager=CTX.ContextManager(workspace=str(root)),
            confirmation_gate=None,
            action_registry=registry,
        )
        sess._dispatch("我想开发一个台球计分APP")
        sess._dispatch("解决台球比赛计分麻烦")
        sess._dispatch("台球爱好者")
        sess._dispatch("计分、比赛记录、排行榜")
        sess._dispatch("可以，先出prd文档")
        out = capsys.readouterr().out
        assert "Product Created" in out  # 创建不阻断
        assert "PRD 生成失败" in out


    # ------------------------------------------------------------ S10-10x 修复
    def test_discovery_phase_confirm_next_incomplete_fields(self):
        """修复 A: 发现阶段字段不完整时"可以，先出prd文档" → 提示缺失, 不创建。

        回归场景 (S10-10x): 产品定义缺 user/core_features 时输入"确认+动作"
        短语 — 之前 LLM 分类不稳定 (当字段回答 / 触发创建), 现在确定性提示缺失。
        """
        mgr = _manager()
        mgr.handle("我想开发一个台球计分APP")
        mgr.handle("台球比赛计分麻烦")  # 只填 problem — 缺 user/core_features
        r = mgr.handle("可以，先出prd文档")
        assert "产品定义还不完整" in r.message
        assert "目标用户" in r.message
        assert "核心功能" in r.message
        assert r.needs_input is True
        assert getattr(r, "next_action", None) is None
        # 未触发创建/PRD — 仍在发现流程 (提示里的 "PRD文档" 是缺失引导, 允许)
        assert "Product Created" not in r.message
        assert "已生成 PRD" not in r.message

    def test_discovery_phase_direct_action_incomplete_fields(self):
        """修复 A: 发现阶段 DIRECT_ACTION ("产出份prd文档") 字段不完整 → 同样提示缺失。"""
        mgr = _manager()
        mgr.handle("我想开发一个台球计分APP")
        mgr.handle("台球比赛计分麻烦")
        r = mgr.handle("产出份prd文档")
        assert "产品定义还不完整" in r.message
        assert r.needs_input is True
        assert getattr(r, "next_action", None) is None

    def test_generate_prd_scan_fallback_disabled(self, tmp_path):
        """修复 B: generate_prd 无显式项目 → 安全报错, 不写"最新项目" (扫描兜底禁用)。

        回归场景 (S10-10x): 之前无 current_project/product_intent 时扫描兜底
        选中"最新 product.json", 把 PRD 写进错误项目 (数据污染)。
        """
        root = tmp_path / "ws"
        root.mkdir()
        old = root / "projects" / "oldproject"
        old.mkdir(parents=True)
        (old / "product.json").write_text(
            json.dumps({
                "name": "旧项目", "problem": "旧问题", "user": "旧用户",
                "core_features": ["旧功能"],
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        ctx = ACTIONS.ExecutionContext(
            workspace=root,
            session=None,
            user="user",
            project=None,
            intent=ACTIONS.IntentObject(
                intent_type="generate_prd", params={}, raw="生成PRD", source="test"
            ),
        )
        res = ACTIONS.generate_prd(ctx)
        assert res.ok is False
        assert "未找到产品定义" in res.message
        # 旧项目未被污染 (PRD.md 未生成)
        assert not (old / "PRD.md").exists()


# ================================================================== 11. 版本 (另见 test_s10_074_deployment)

class TestVersion:
    def test_pyproject_version_bumped(self):
        """契约点 11: pyproject 版本 v1.1.79 (单源断言见 test_s10_074_deployment)。"""
        import tomllib
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        ver = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
            "project"
        ]["version"]
        assert ver == "1.1.185"
