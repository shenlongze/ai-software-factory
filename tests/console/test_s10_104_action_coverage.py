"""tests/console/test_s10_104_action_coverage.py — 确认阶段 next_action 全覆盖 + 会话分割线 + 删除指令 (S10-104)。

计划: docs/sprint10/S10-104-action-coverage-plan.md §2 契约测试要点 1-9
覆盖:
1. "产出份prd文档" → approved + next_action="prd" + 名称不被覆盖 (验收 1)
2. "生成PRD" / "出个html" / "出份功能清单" → next_action 分别 prd/html/feature_list + 名称不变
3. "改名叫X" → 仍走改名 (验收 2, 不被动作规则抢; "改名叫prd" 尤其验证 RENAME_RE 优先级)
4. 分割线: InteractiveSession run() 每轮回复间含 SEPARATOR (验收 3; 退出/空输入不打印)
5. "把核心功能删掉" → core_features 清空 → 迁移 DISCOVERY + 追问 (验收 4);
   "清空目标用户" 同; "把名字删掉" → 名称重置 → 重进确认; 字段收集期"清空X" → 重问
6. 无 LLM 规则兜底: 1/2/3/5 全部 analyzer=None (确定性规则, 不依赖/不伪造 LLM)
7. LLM: mock analyze_confirmation 变体 → approve_next + 各 next_action 路由
8. 宿主: next_action="prd" → PRD 执行; "feature_list"/"html"/"docs" → 信号注释 (不阻断创建)
9. 版本 v1.1.79 (单源断言见 test_s10_074_deployment)

规则纯确定性 (DIRECT_ACTION / _parse_delete_command); LLM 只做补充分类 — 全部测试
禁用真实 LLM (analyzer=None 或 mock llm_fn 注入 / _no_provider 规则兜底)。

basename 全仓库唯一 (test_s10_104_* 前缀, tests/console 既有模式)。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # factory-console/ 的父目录 (含连字符包名)
    sys.path.insert(0, str(_ROOT))

ACT = importlib.import_module("factory-console.session.action")
ACTIONS = importlib.import_module("factory-console.session.actions")
CONV = importlib.import_module("factory-console.session.conversation")
CTX = importlib.import_module("factory-console.session.context")
DI = importlib.import_module("factory-console.session.discovery_intelligence")
GUIDE = importlib.import_module("factory-console.session.discovery_guide")
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
    """ConversationManager — 动作/删除规则纯确定性, 显式禁用 LLM 分析器。"""
    kw.setdefault("analyzer", None)
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
        "reason": "用户确认并想先出产物",
    }
    data.update(overrides)
    return data


def _feed_inputs(monkeypatch, inputs):
    """把 input() 替换为按序列吐出的迭代器 (耗尽 → StopIteration 证明仍在等待)。"""
    it = iter(inputs)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(it))
    return it


# ================================================================== 1-2: 直接动作请求 → next_action (验收 1)

class TestDirectAction:
    @pytest.mark.parametrize(
        "text,action",
        [
            ("产出份prd文档", "prd"),
            ("生成PRD", "prd"),
            ("写一份prd", "prd"),
            ("可以，先出prd文档", "prd"),  # 既有 S10-102 确认+下一步 同路径
            ("出个html", "html"),
            ("生成html页面", "html"),
            ("出份功能清单", "feature_list"),
            ("功能清单", "feature_list"),
            ("出个文档", "docs"),
            ("说明书", "docs"),
        ],
    )
    def test_direct_action_approve_next(self, text, action):
        """契约点 1/2: 纯动作请求 (无确认前缀) → approved + next_action + 名称不被覆盖。"""
        mgr = _manager()
        _run_product_flow(mgr)
        name_before = mgr.product_intent.name
        resp = mgr.handle_product_confirm(text, confirm_fn=lambda pi: "ok")
        assert resp.next_action == action
        assert resp.state == STATES.DONE
        assert mgr.product_intent.name == name_before  # 名称不被覆盖 (验收 1)
        assert text not in mgr.product_intent.name

    def test_direct_action_without_fn_carries_signal(self):
        """直接动作请求 + confirm_fn 缺省 → 停留 PROJECT_CREATION, next_action 仍携带。"""
        mgr = _manager()
        _run_product_flow(mgr)
        name_before = mgr.product_intent.name
        resp = mgr.handle_product_confirm("产出份prd文档")
        assert resp.state == STATES.PROJECT_CREATION
        assert resp.next_action == "prd"
        assert mgr.product_intent.name == name_before


# ================================================================== 3: "改名叫X" 仍走改名 (验收 2)

class TestRenamePriority:
    def test_rename_prd_not_swept_by_action_rule(self):
        """契约点 3: "改名叫prd" → 改名 (RENAME_RE 最优先, 不被 DIRECT_ACTION 抢)。"""
        mgr = _manager()
        _run_product_flow(mgr)
        resp = mgr.handle_product_confirm("改名叫prd")
        assert resp.next_action is None
        assert mgr.product_intent.name == "prd"
        assert resp.state == STATES.PRODUCT_CONFIRMATION

    def test_rename_normal_unchanged(self):
        """契约点 3: "改名叫墨笺" → 改名 (S10-081/102 行为不变)。"""
        mgr = _manager()
        _run_product_flow(mgr)
        resp = mgr.handle_product_confirm("改名叫墨笺")
        assert resp.next_action is None
        assert mgr.product_intent.name == "墨笺"
        assert resp.state == STATES.PRODUCT_CONFIRMATION

    def test_bare_text_rename_fallback(self):
        """契约点 3: 裸文本 → 改名兜底 (不匹配任何动作/删除规则)。"""
        mgr = _manager()
        _run_product_flow(mgr)
        resp = mgr.handle_product_confirm("账本精灵")
        assert mgr.product_intent.name == "账本精灵"
        assert resp.state == STATES.PRODUCT_CONFIRMATION


# ================================================================== 4: 会话分割线 (验收 3)

class TestSeparator:
    def test_separator_between_reply_rounds(self, monkeypatch, capsys):
        """契约点 4: 两轮回复间含 SEPARATOR (status 输出后、退出提示前)。"""
        _feed_inputs(monkeypatch, ["/status", "exit"])
        SESS.InteractiveSession().run()
        out = capsys.readouterr().out
        assert SESS.SEPARATOR in out
        # 分割线出现在回复之后、退出提示之前 (每轮回复间)
        assert out.index(SESS.SEPARATOR) < out.index("已退出会话")

    def test_no_separator_on_exit(self, monkeypatch, capsys):
        """契约点 4: 退出路径不打印分割线。"""
        _feed_inputs(monkeypatch, ["exit"])
        SESS.InteractiveSession().run()
        out = capsys.readouterr().out
        assert SESS.SEPARATOR not in out

    def test_no_separator_on_empty_input(self, monkeypatch, capsys):
        """契约点 4: 空输入路径不打印分割线 (空输入 → 继续, 不 dispatch)。"""
        _feed_inputs(monkeypatch, ["", "exit"])
        SESS.InteractiveSession().run()
        out = capsys.readouterr().out
        assert SESS.SEPARATOR not in out

    def test_separator_length(self):
        """契约点 4: SEPARATOR = "─" * 46 (计划 §1.2)。"""
        assert SESS.SEPARATOR == "─" * 46


# ================================================================== 5: 删除/清空字段 (验收 4)

class TestDeleteCommand:
    def test_delete_core_features_clears_and_requestion(self):
        """契约点 5: "把核心功能删掉" → core_features 清空 → DISCOVERY + 追问。"""
        mgr = _manager()
        _run_product_flow(mgr)
        resp = mgr.handle_product_confirm("把核心功能删掉")
        assert mgr.product_intent.core_features == []
        assert resp.state == STATES.DISCOVERY
        assert mgr._product_pending == ["core_features"]
        assert "已清空核心功能" in resp.message
        assert "核心功能有哪些" in resp.message  # 追问该字段
        # 其余字段保留
        assert mgr.product_intent.problem == "台球比赛计分麻烦"
        assert mgr.product_intent.user == "台球爱好者"

    def test_delete_user_clears_and_requestion(self):
        """契约点 5: "清空目标用户" → user 清空 → DISCOVERY + 追问。"""
        mgr = _manager()
        _run_product_flow(mgr)
        resp = mgr.handle_product_confirm("清空目标用户")
        assert mgr.product_intent.user == ""
        assert resp.state == STATES.DISCOVERY
        assert mgr._product_pending == ["user"]
        assert "目标用户" in resp.message

    def test_delete_name_reconfirmation(self):
        """契约点 5: "把名字删掉" → 名称重置 → 重进确认 (绝不当改名)。"""
        mgr = _manager()
        _run_product_flow(mgr)
        resp = mgr.handle_product_confirm("把名字删掉")
        assert mgr.product_intent.name != "把名字删掉"  # 不当改名
        assert resp.state == STATES.PRODUCT_CONFIRMATION  # 重进确认 (摘要更新)
        assert "确认创建这个产品? (y/N)" in resp.message

    def test_delete_during_field_collection_requestion(self):
        """契约点 5: 字段收集期 "清空目标用户" → 重问 (不吞成字段答案)。"""
        mgr = _manager()
        mgr.start_product_discovery("我想开发一个台球计分APP")
        mgr.handle_product_answer("台球比赛计分麻烦")
        resp = mgr.handle_product_answer("清空目标用户")
        assert resp.state == STATES.DISCOVERY
        assert "目标用户" in resp.message  # 重问
        assert mgr.product_intent.user in (None, "")  # 未被当字段
        assert mgr.product_intent.problem == "台球比赛计分麻烦"  # 其余保留

    def test_delete_never_renames(self):
        """契约点 5 边界: 删除指令绝不当改名 — 名称保持不变。"""
        mgr = _manager()
        _run_product_flow(mgr)
        name_before = mgr.product_intent.name
        mgr.handle_product_confirm("把核心功能删掉")
        assert mgr.product_intent.name == name_before
        assert "把核心功能删掉" not in mgr.product_intent.name

    def test_parse_delete_command_unit(self):
        """契约点 5 单元: 两序匹配 (别名+动词 / 动词+别名), 复用 _EDIT_FIELD_ALIASES。"""
        assert CONV._parse_delete_command("把核心功能删掉") == "core_features"
        assert CONV._parse_delete_command("删除核心功能") == "core_features"
        assert CONV._parse_delete_command("核心功能不要") == "core_features"
        assert CONV._parse_delete_command("清空目标用户") == "user"
        assert CONV._parse_delete_command("把名字删掉") == "name"
        assert CONV._parse_delete_command("清空问题") == "problem"
        assert CONV._parse_delete_command("把用户改成职业选手") is None  # 修改指令
        assert CONV._parse_delete_command("改名叫墨笺") is None  # 改名
        assert CONV._parse_delete_command("墨笺") is None  # 裸文本
        assert CONV._parse_delete_command("可以") is None  # 纯确认


# ================================================================== guide 单元: DIRECT_ACTION_PATTERNS + match_direct_action

class TestDirectActionGuide:
    def test_direct_action_patterns_present(self):
        """DIRECT_ACTION_PATTERNS 四类词汇齐全 (prd/feature_list/html/docs)。"""
        actions = dict(GUIDE.DIRECT_ACTION_PATTERNS)
        assert set(actions) == {"prd", "feature_list", "html", "docs"}
        prd_kws = [kws for aid, kws in GUIDE.DIRECT_ACTION_PATTERNS if aid == "prd"][0]
        assert any("prd" in kw for kw in prd_kws)
        feature_kws = [kws for aid, kws in GUIDE.DIRECT_ACTION_PATTERNS if aid == "feature_list"][0]
        assert "功能清单" in feature_kws and "清单" in feature_kws

    def test_match_direct_action(self):
        """match_direct_action: lower 后匹配, 返回首个命中的 action_id。"""
        assert GUIDE.match_direct_action("产出份prd文档") == "prd"
        assert GUIDE.match_direct_action("生成PRD") == "prd"
        assert GUIDE.match_direct_action("出个html") == "html"
        assert GUIDE.match_direct_action("出份功能清单") == "feature_list"
        assert GUIDE.match_direct_action("文档") == "docs"
        assert GUIDE.match_direct_action("说明书") == "docs"
        assert GUIDE.match_direct_action("可以") is None
        assert GUIDE.match_direct_action("墨笺") is None
        # "改名叫prd" 在 guide 层命中 prd — 优先级由调用方 handle_product_confirm
        # 的 RENAME_RE 先检查保证 (见 TestRenamePriority)
        assert GUIDE.match_direct_action("改名叫prd") == "prd"


# ================================================================== 7: LLM 补充分类 → 各 next_action 路由

class TestLlmNextActionRouting:
    @pytest.mark.parametrize("action", ["prd", "feature_list", "html", "docs"])
    def test_llm_approve_next_routes(self, action):
        """契约点 7: mock analyze_confirmation approve_next → 各 next_action 路由。"""
        llm_fn, calls = _scripted_llm(
            _full_analysis(),
            _confirmation_payload(next_action=action),
        )
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        mgr.handle("我想做一个记账App, 解决记账麻烦, 给个人用户用")
        assert mgr.state == STATES.PRODUCT_CONFIRMATION
        resp = mgr.handle_product_confirm("帮我搞定", confirm_fn=lambda pi: "ok")
        assert resp.state == STATES.DONE
        assert resp.next_action == action
        assert mgr.product_intent.name == "简记"  # 名称不被覆盖
        assert calls[-1][1] == "confirm_intent"  # 1 次发现 analyze + 1 次确认分类

    def test_llm_approve_next_without_prefix(self):
        """契约点 7: approve_next 允许无确认前缀 (纯动作请求 = 隐含确认 + 下一步)。"""
        llm_fn, _ = _scripted_llm(
            _full_analysis(),
            _confirmation_payload(next_action="html"),
        )
        mgr = _manager(analyzer=DI.DiscoveryIntentAnalyzer(llm_fn=llm_fn))
        mgr.handle("我想做一个记账App, 解决记账麻烦, 给个人用户用")
        resp = mgr.handle_product_confirm("帮我出个网页", confirm_fn=lambda pi: "ok")
        assert resp.next_action == "html"
        assert resp.state == STATES.DONE


# ================================================================== 8: 宿主接线 (session 层)

class TestHostWiring:
    def _session(self, tmp_path, registry=None):
        root = tmp_path / "ws"
        root.mkdir()
        kw = dict(
            context_manager=CTX.ContextManager(workspace=str(root)),
            confirmation_gate=None,
        )
        if registry is not None:
            kw["action_registry"] = registry
        return SESS.InteractiveSession(**kw), root

    def _run_flow(self, sess, confirm_text):
        sess._dispatch("我想开发一个台球计分APP")
        sess._dispatch("解决台球比赛计分麻烦")
        sess._dispatch("台球爱好者")
        sess._dispatch("计分、比赛记录、排行榜")
        sess._dispatch(confirm_text)

    def test_host_prd_executes_generate_prd(self, fake_org, capsys, tmp_path):
        """契约点 8: "产出份prd文档" → create_product + generate_prd 执行 (PRD.md 落盘)。"""
        sess, root = self._session(tmp_path)
        self._run_flow(sess, "产出份prd文档")
        out = capsys.readouterr().out
        assert "Product Created" in out
        assert "已生成 PRD" in out
        assert (root / "projects" / "scorepocket" / "PRD.md").is_file()
        assert (root / "projects" / "scorepocket" / "product.json").is_file()

    @pytest.mark.parametrize(
        "text,label",
        [
            ("出份功能清单", "功能清单"),
            ("出个html", "HTML页面"),
            ("出个文档", "文档"),
        ],
    )
    def test_host_signal_annotation_not_blocking(
        self, fake_org, capsys, tmp_path, text, label
    ):
        """契约点 8: feature_list/html/docs → "[已记录] 将生成{label} — 产出引擎 backlog"
        (不阻断创建, 不执行 PRD)。"""
        sess, root = self._session(tmp_path)
        self._run_flow(sess, text)
        out = capsys.readouterr().out
        assert "Product Created" in out  # 创建不阻断
        assert f"[已记录] 将生成{label} — 产出引擎 backlog" in out
        assert (root / "projects" / "scorepocket" / "product.json").is_file()
        assert not (root / "projects" / "scorepocket" / "PRD.md").exists()  # 未执行 PRD

    def test_host_prd_failure_does_not_block_creation(self, fake_org, capsys, tmp_path):
        """契约点 8: PRD 失败 → 注明原因, 不阻断创建 (创建成功消息仍在)。"""
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
        sess, _ = self._session(tmp_path, registry=registry)
        self._run_flow(sess, "产出份prd文档")
        out = capsys.readouterr().out
        assert "Product Created" in out  # 创建不阻断
        assert "PRD 生成失败" in out


# ================================================================== 9: 版本 (另见 test_s10_074_deployment)

class TestVersion:
    def test_pyproject_version_bumped(self):
        """契约点 9: pyproject 版本 v1.1.79 (单源断言见 test_s10_074_deployment)。"""
        import tomllib

        ver = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
            "project"
        ]["version"]
        assert ver == "1.1.181"
