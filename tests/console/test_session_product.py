
"""tests/console/test_session_product.py — S10-050 AI Product Manager Loop (Phase 2-6)。

设计: docs/sprint10/S10-050-product-manager-design.md
覆盖 (验收 A-L):
A. "我想开发一个台球计分APP" → create_product intent
B. ProductIntent 模型 (name/problem/user/core_features/is_complete/missing_fields)
C. DISCOVERY 多轮: 缺 problem → 追问; 补齐 → 追问 user; 全部 → PRODUCT_CONFIRMATION
D. 确认 y → PROJECT_CREATION → project.json + product.json 落盘 → "Product Created"
E. 确认 n → 重置 DISCOVERY
F. 缺失字段 → 明确追问 (不静默)
G. 临时名称生成 (未命名产品-<ts>)
H. SessionContext.product_intent 存取
I. 复用 create_project (桥接, 不复制业务)
K. 新增 >=40 测试全绿 + 全量 pytest 不破坏基线
L. 回归: 现有 create_project/run_task 不受影响

basename 全仓库唯一 (test_session_* 前缀, tests/console 既有模式)。

测试装配 (同 test_session_intent_execution): monkeypatch actions._load_org_cli
注入 FakeOrg (记录调用, 返回规范结果) — 避免真实注册 ~/.factory。
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

class _FakeChat075:
    """测试 ChatService (固定回答, 不依赖真实 LLM)。"""

    def answer(self, question, **kw):
        return f"AI: 测试回答 {question}"

    def is_fallback(self, a):
        return False

ACT_MOD = importlib.import_module("factory-console.session.action")
ACTIONS_MOD = importlib.import_module("factory-console.session.actions")
CONV_MOD = importlib.import_module("factory-console.session.conversation")
CTX_MOD = importlib.import_module("factory-console.session.context")
INTENT_MOD = importlib.import_module("factory-console.session.intent")
PROD_MOD = importlib.import_module("factory-console.session.product")
ROUTER_MOD = importlib.import_module("factory-console.session.router")
SESS_MOD = importlib.import_module("factory-console.session.session")

STATES = CONV_MOD.ConversationState


# ------------------------------------------------------------------ 工具

def _manager(**kw):
    return CONV_MOD.ConversationManager(**kw)


def _parser():
    return INTENT_MOD.KeywordIntentParser()


def _session_ctx(workspace: str, **kw):
    return CTX_MOD.SessionContext(workspace=workspace, **kw)


def _exec_ctx(root: Path, **kw):
    return ACT_MOD.ExecutionContext(
        workspace=root,
        session=_session_ctx(str(root)),
        user="user",
        **kw,
    )


def _complete_product(**kw):
    data = dict(
        name="ScorePocket",
        problem="台球比赛计分麻烦",
        user="台球爱好者",
        core_features=["计分", "比赛记录", "排行榜"],
        raw="我想开发一个台球计分APP",
    )
    data.update(kw)
    return PROD_MOD.ProductIntent(**data)


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
    """注入 FakeOrgCli (monkeypatch _load_org_cli) — 同既有测试模式。"""
    org = FakeOrgCli()
    monkeypatch.setattr(ACTIONS_MOD, "_load_org_cli", lambda: org)
    return org


def _run_product_flow(mgr):
    """走完整 DISCOVERY 多轮 → PRODUCT_CONFIRMATION (验收 C 主路径)。"""
    mgr.handle("我想开发一个台球计分APP")
    mgr.handle("台球比赛计分麻烦")
    mgr.handle("台球爱好者")
    return mgr.handle("计分、比赛记录、排行榜")


# ================================================================== 1. ProductIntent 模型 (验收 B)

def test_product_intent_defaults():
    pi = PROD_MOD.ProductIntent()
    assert pi.name is None
    assert pi.problem is None
    assert pi.user is None
    assert pi.platform is None
    assert pi.core_features == []
    assert pi.status == "draft"
    assert pi.raw == ""
    assert pi.session_id is None


def test_product_intent_required_fields_constant():
    assert PROD_MOD.ProductIntent.REQUIRED_FIELDS == ("problem", "user", "core_features")
    assert PROD_MOD.REQUIRED_FIELDS == ("problem", "user", "core_features")


def test_product_intent_full_fields():
    pi = _complete_product(platform="mobile", session_id="s-1")
    assert pi.name == "ScorePocket"
    assert pi.problem == "台球比赛计分麻烦"
    assert pi.user == "台球爱好者"
    assert pi.platform == "mobile"
    assert pi.core_features == ["计分", "比赛记录", "排行榜"]
    assert pi.session_id == "s-1"


def test_product_intent_is_complete_empty_false():
    assert PROD_MOD.ProductIntent().is_complete() is False


def test_product_intent_is_complete_partial_false():
    pi = PROD_MOD.ProductIntent(problem="x", user="y")
    assert pi.is_complete() is False  # core_features 缺失


def test_product_intent_is_complete_all_true():
    assert _complete_product().is_complete() is True


def test_missing_fields_empty_lists_all():
    assert PROD_MOD.ProductIntent().missing_fields() == ["产品解决什么问题", "目标用户", "核心功能"]


def test_missing_fields_partial_only_missing():
    pi = PROD_MOD.ProductIntent(problem="x", core_features=["a"])
    assert pi.missing_fields() == ["目标用户"]


def test_missing_fields_complete_empty():
    assert _complete_product().missing_fields() == []


def test_to_dict_keys_and_values():
    pi = _complete_product(platform="web")
    data = pi.to_dict()
    assert data["name"] == "ScorePocket"
    assert data["problem"] == "台球比赛计分麻烦"
    assert data["user"] == "台球爱好者"
    assert data["platform"] == "web"
    assert data["core_features"] == ["计分", "比赛记录", "排行榜"]
    assert data["status"] == "draft"
    assert data["raw"] == "我想开发一个台球计分APP"
    assert set(data) == {"name", "problem", "user", "platform", "core_features", "status", "raw", "session_id"}


def test_from_dict_roundtrip():
    pi = _complete_product(platform="mobile", session_id="s-9", status="confirmed")
    restored = PROD_MOD.ProductIntent.from_dict(pi.to_dict())
    assert restored.to_dict() == pi.to_dict()


def test_from_dict_empty_defaults():
    pi = PROD_MOD.ProductIntent.from_dict({})
    assert pi.name is None and pi.problem is None and pi.user is None
    assert pi.core_features == [] and pi.status == "draft"


def test_from_dict_core_features_string_coerced():
    pi = PROD_MOD.ProductIntent.from_dict({"core_features": "计分、排名"})
    assert pi.core_features == ["计分", "排名"]


def test_to_summary_contains_all_fields():
    summary = _complete_product().to_summary()
    assert "ScorePocket" in summary
    assert "台球比赛计分麻烦" in summary
    assert "台球爱好者" in summary
    assert "计分, 比赛记录, 排行榜" in summary


def test_to_summary_unnamed_product():
    pi = _complete_product(name=None)
    assert "(未命名)" in pi.to_summary()


def test_to_summary_includes_platform_when_set():
    assert "mobile" in _complete_product(platform="mobile").to_summary()


def test_parse_core_features_mixed_separators():
    assert PROD_MOD.parse_core_features("计分、比赛记录, 排行榜；分享") == [
        "计分", "比赛记录", "排行榜", "分享",
    ]


def test_parse_core_features_list_passthrough():
    assert PROD_MOD.parse_core_features(["计分", " 排名 "]) == ["计分", "排名"]


def test_parse_core_features_empty_safe():
    assert PROD_MOD.parse_core_features(None) == []
    assert PROD_MOD.parse_core_features("") == []
    assert PROD_MOD.parse_core_features("  ") == []


def test_to_json_roundtrip():
    pi = _complete_product()
    assert json.loads(pi.to_json()) == pi.to_dict()


# ================================================================== 2. 临时名称生成 (验收 G)

def test_temp_name_format_with_ts():
    assert PROD_MOD.generate_temp_product_name(ts=123) == "未命名产品-123"


def test_temp_name_default_prefix():
    name = PROD_MOD.generate_temp_product_name()
    assert name.startswith("未命名产品-")
    assert name[len("未命名产品-"):].isdigit()


def test_temp_name_different_ts_unique():
    assert PROD_MOD.generate_temp_product_name(ts=1) != PROD_MOD.generate_temp_product_name(ts=2)


# ================================================================== 3. create_product intent 解析 (验收 A)

def test_parse_acceptance_full_sentence():
    """验收 A: "我想开发一个台球计分APP" → create_product intent。"""
    intent = _parser().parse("我想开发一个台球计分APP")
    assert intent is not None
    assert intent.intent_type == INTENT_MOD.INTENT_CREATE_PRODUCT


def test_parse_product_idea_param():
    intent = _parser().parse("我想开发一个台球计分APP")
    assert intent.parameters.get("idea") == "开发一个台球计分APP"
    assert intent.raw == "我想开发一个台球计分APP"


def test_parse_woxiang_trigger():
    intent = _parser().parse("我想做一个记账软件")
    assert intent.intent_type == INTENT_MOD.INTENT_CREATE_PRODUCT


def test_parse_zuoyikuan_trigger():
    intent = _parser().parse("做一款台球计分APP")
    assert intent.intent_type == INTENT_MOD.INTENT_CREATE_PRODUCT
    assert intent.parameters.get("idea") == "台球计分APP"


def test_parse_chanpin_trigger():
    assert _parser().parse("我有一个产品想法").intent_type == INTENT_MOD.INTENT_CREATE_PRODUCT


def test_parse_xiangfa_trigger():
    assert _parser().parse("想法: 帮人约球").intent_type == INTENT_MOD.INTENT_CREATE_PRODUCT


def test_parse_chuangye_trigger():
    assert _parser().parse("我想创业做AI").intent_type == INTENT_MOD.INTENT_CREATE_PRODUCT


def test_parse_zhuoyige_app_contiguous_product():
    """"做一个" + 紧邻 APP → create_product (产品标记判别)。"""
    assert _parser().parse("帮我做一个APP").intent_type == INTENT_MOD.INTENT_CREATE_PRODUCT


def test_parse_kaifa_app_contiguous_product():
    assert _parser().parse("开发一个APP").intent_type == INTENT_MOD.INTENT_CREATE_PRODUCT


def test_parse_raw_preserved():
    intent = _parser().parse("我想开发一个台球计分APP")
    assert intent.raw == "我想开发一个台球计分APP"
    assert intent.confidence == 1.0


# ================================================================== 4. create_product action (验收 D/F/I)

def test_action_complete_bridges_create_project(fake_org, tmp_path):
    """I: 桥接复用 create_project → org.cli.cmd_project_register 收到 name/product 名。"""
    root = tmp_path / "ws"
    root.mkdir()
    ctx = _exec_ctx(root)
    ctx.session.product_intent = _complete_product()
    ctx.intent = INTENT_MOD.IntentObject(intent_type="create_product", raw="x")
    result = ACTIONS_MOD.create_product(ctx)
    assert result.ok is True
    assert len(fake_org.calls) == 1
    assert fake_org.calls[0][0] == root  # root = workspace (同 create_project)
    assert fake_org.calls[0][1].name == "ScorePocket"  # 产品名 → project name (桥接复用)


def test_action_success_message_exact(fake_org, tmp_path):
    """D: 成功消息 "Product Created: X — Ready for Engineering."。"""
    root = tmp_path / "ws"
    root.mkdir()
    ctx = _exec_ctx(root)
    ctx.session.product_intent = _complete_product()
    ctx.intent = INTENT_MOD.IntentObject(intent_type="create_product", raw="x")
    result = ACTIONS_MOD.create_product(ctx)
    assert result.message == "Product Created: ScorePocket — Ready for Engineering."


def test_action_writes_product_json(fake_org, tmp_path):
    """D: product.json 落盘 (projects/<slug>/product.json) + 内容 = ProductIntent.to_dict。"""
    root = tmp_path / "ws"
    root.mkdir()
    ctx = _exec_ctx(root)
    ctx.session.product_intent = _complete_product(platform="mobile")
    ctx.intent = INTENT_MOD.IntentObject(intent_type="create_product", raw="x")
    result = ACTIONS_MOD.create_product(ctx)
    product_file = root / "projects" / "scorepocket" / "product.json"
    assert result.data["product_file"] == str(product_file)
    assert product_file.is_file()
    data = json.loads(product_file.read_text(encoding="utf-8"))
    assert data["name"] == "ScorePocket"
    assert data["problem"] == "台球比赛计分麻烦"
    assert data["core_features"] == ["计分", "比赛记录", "排行榜"]
    assert data["platform"] == "mobile"
    assert data["status"] == "product_defined"  # S10-115 J-1: Lifecycle 词汇 (替代旧 project_created)


def test_action_project_file_reported(fake_org, tmp_path):
    """D: 结果报告 project.json 路径 (org project 记录同空间)。"""
    root = tmp_path / "ws"
    root.mkdir()
    ctx = _exec_ctx(root)
    ctx.session.product_intent = _complete_product()
    result = ACTIONS_MOD.create_product(ctx)
    assert result.data["project_file"] == str(root / "projects" / "scorepocket" / "project.json")


def test_action_from_intent_params_without_session_product(fake_org, tmp_path):
    """无 session.product_intent → 从 intent.parameters 构建 (直接执行入口)。"""
    root = tmp_path / "ws"
    root.mkdir()
    intent = INTENT_MOD.IntentObject(
        intent_type="create_product",
        params={
            "name": "TodoApp",
            "problem": "待办管理混乱",
            "user": "职场人",
            "core_features": ["待办", "提醒"],
        },
        raw="raw",
    )
    result = ACTIONS_MOD.create_product(_exec_ctx(root, intent=intent))
    assert result.ok is True
    assert result.message == "Product Created: TodoApp — Ready for Engineering."
    assert fake_org.calls[0][1].name == "TodoApp"


def test_action_missing_fields_explicit_error(fake_org, tmp_path):
    """F: 缺失必填 → 明确错误 (列出中文字段名, 不静默; 不调 org)。"""
    root = tmp_path / "ws"
    root.mkdir()
    intent = INTENT_MOD.IntentObject(intent_type="create_product", params={"name": "X"}, raw="x")
    result = ACTIONS_MOD.create_product(_exec_ctx(root, intent=intent))
    assert result.ok is False
    assert result.status == "error"
    assert "产品解决什么问题" in result.message
    assert "目标用户" in result.message
    assert "核心功能" in result.message
    assert fake_org.calls == []  # 不完整 → 不桥接


def test_action_missing_single_field_error(fake_org, tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    pi = _complete_product()
    pi.user = None  # 只缺 user
    ctx = _exec_ctx(root)
    ctx.session.product_intent = pi
    result = ACTIONS_MOD.create_product(ctx)
    assert result.ok is False
    assert "目标用户" in result.message
    assert "产品解决什么问题" not in result.message  # 只列缺失的


def test_action_bridge_failure_propagates(monkeypatch, tmp_path):
    """I: org 注册失败 → create_product 明确失败 (桥接错误透传)。"""
    root = tmp_path / "ws"
    root.mkdir()
    org = FakeOrgCli(ok=False, error="repo 不存在")
    monkeypatch.setattr(ACTIONS_MOD, "_load_org_cli", lambda: org)
    ctx = _exec_ctx(root)
    ctx.session.product_intent = _complete_product()
    result = ACTIONS_MOD.create_product(ctx)
    assert result.ok is False
    assert "repo 不存在" in result.message


def test_action_temp_name_when_name_missing(fake_org, tmp_path):
    """G: name 缺省 → 临时名 "未命名产品-<ts>" 用于注册。"""
    root = tmp_path / "ws"
    root.mkdir()
    pi = _complete_product(name=None)
    ctx = _exec_ctx(root)
    ctx.session.product_intent = pi
    result = ACTIONS_MOD.create_product(ctx)
    assert result.ok is True
    assert fake_org.calls[0][1].name.startswith("未命名产品-")
    assert "未命名产品-" in result.message


def test_action_slug_from_project(fake_org, tmp_path):
    """目录名优先 project.slug (org 返回) → 非业务复制的路径推导。"""
    root = tmp_path / "ws"
    root.mkdir()
    fake_org.project = {"id": "p9", "name": "ScorePocket", "slug": "score-pocket-9"}
    ctx = _exec_ctx(root)
    ctx.session.product_intent = _complete_product()
    result = ACTIONS_MOD.create_product(ctx)
    assert result.data["product_file"] == str(root / "projects" / "score-pocket-9" / "product.json")
    assert (root / "projects" / "score-pocket-9" / "product.json").is_file()


def test_action_registered_default_actions():
    """create_product 注册: metadata sensitive=True / category=product / permission=project。"""
    action = ACTIONS_MOD.build_default_actions().get("create_product")
    assert action is not None
    assert action.handler is ACTIONS_MOD.create_product
    assert action.permission == "project"
    assert action.metadata.get("sensitive") is True
    assert action.metadata.get("category") == "product"


# ================================================================== 5. Discovery Flow (验收 C/F)

def test_start_discovery_creates_product_intent():
    mgr = _manager()
    resp = mgr.start_product_discovery("我想开发一个台球计分APP")
    assert mgr.product_intent is not None
    assert mgr.product_intent.name.startswith("未命名产品-")  # 临时名
    assert mgr.product_intent.raw == "我想开发一个台球计分APP"
    assert mgr.product_intent.status == "draft"


def test_start_discovery_state_discovery():
    mgr = _manager()
    resp = mgr.start_product_discovery("我想开发一个台球计分APP")
    assert resp.state == STATES.DISCOVERY
    assert resp.needs_input is True


def test_start_discovery_first_question_problem():
    """C: 缺 problem → 第一追问明确指向 problem (不静默)。"""
    mgr = _manager()
    resp = mgr.start_product_discovery("我想开发一个台球计分APP")
    assert "痛点" in resp.message or "问题" in resp.message
    assert "problem" in resp.message


def test_start_discovery_pending_field_order():
    mgr = _manager()
    mgr.start_product_discovery("x")
    assert mgr._product_pending == ["problem", "user", "core_features"]


def test_answer_problem_asks_user():
    """C: 补齐 problem → 追问 user。"""
    mgr = _manager()
    mgr.start_product_discovery("x")
    resp = mgr.handle_product_answer("解决台球计分麻烦")
    assert mgr.product_intent.problem == "解决台球计分麻烦"
    assert resp.state == STATES.DISCOVERY
    assert "用户" in resp.message
    assert "user" in resp.message


def test_answer_user_asks_core_features():
    mgr = _manager()
    mgr.start_product_discovery("x")
    mgr.handle_product_answer("解决台球计分麻烦")
    resp = mgr.handle_product_answer("台球爱好者")
    assert mgr.product_intent.user == "台球爱好者"
    assert "核心功能" in resp.message
    assert "core_features" in resp.message


def test_answer_core_features_reaches_confirmation():
    """C: 全部补齐 → PRODUCT_CONFIRMATION + 摘要 + 确认询问。"""
    mgr = _manager()
    mgr.start_product_discovery("x")
    mgr.handle_product_answer("解决台球计分麻烦")
    mgr.handle_product_answer("台球爱好者")
    resp = mgr.handle_product_answer("计分、比赛记录")
    assert resp.state == STATES.PRODUCT_CONFIRMATION
    assert "确认创建这个产品? (y/N)" in resp.message
    assert "计分, 比赛记录" in resp.message


def test_answer_empty_does_not_skip():
    """F: 空回答 → 明确要求补充, 字段不跳 (不静默)。"""
    mgr = _manager()
    mgr.start_product_discovery("x")
    resp = mgr.handle_product_answer("   ")
    assert mgr.product_intent.problem is None
    assert "不能为空" in resp.message
    assert resp.needs_input is True


def test_answer_without_discovery_clarifies():
    mgr = _manager()
    resp = mgr.handle_product_answer("x")
    assert resp.state == STATES.CLARIFICATION
    assert "产品想法" in resp.message


# ================================================================== 6. Multi-turn handle() (验收 C)

def test_handle_create_product_starts_discovery():
    """A+C: handle("我想开发一个台球计分APP") → DISCOVERY + 追问。"""
    mgr = _manager()
    resp = mgr.handle("我想开发一个台球计分APP")
    assert resp.state == STATES.DISCOVERY
    assert mgr.product_intent is not None
    assert "痛点" in resp.message or "问题" in resp.message


def test_handle_multi_turn_to_confirmation():
    """C: 多轮 handle → 逐步补齐 → PRODUCT_CONFIRMATION。"""
    mgr = _manager()
    resp = _run_product_flow(mgr)
    assert resp.state == STATES.PRODUCT_CONFIRMATION
    assert "确认创建这个产品? (y/N)" in resp.message
    assert mgr.product_intent.problem == "台球比赛计分麻烦"
    assert mgr.product_intent.user == "台球爱好者"
    assert mgr.product_intent.core_features == ["计分", "比赛记录", "排行榜"]
    assert mgr.product_intent.is_complete()


def test_handle_confirm_y_without_fn_stays_project_creation():
    mgr = _manager()
    _run_product_flow(mgr)
    resp = mgr.handle("y")
    assert resp.state == STATES.PROJECT_CREATION  # confirm_fn 缺省 → 信号
    assert mgr.product_intent is not None


def test_handle_confirm_n_resets_discovery():
    """E: 确认 n → 重置 DISCOVERY (product_intent 清空)。"""
    mgr = _manager()
    _run_product_flow(mgr)
    resp = mgr.handle("n")
    assert resp.state == STATES.DISCOVERY
    assert mgr.product_intent is None
    assert mgr._product_pending == []


def test_handle_after_reset_new_product_flow():
    """E: 重置后可重新开始产品发现。"""
    mgr = _manager()
    _run_product_flow(mgr)
    mgr.handle("n")
    resp = mgr.handle("我想开发一个记账APP")
    assert resp.state == STATES.DISCOVERY
    assert mgr.product_intent is not None
    assert mgr.product_intent.raw == "我想开发一个记账APP"


# ================================================================== 7. Missing Parameter (验收 F)

def test_missing_problem_asked_first():
    mgr = _manager()
    mgr.start_product_discovery("x")
    assert mgr.product_intent.missing_fields() == ["产品解决什么问题", "目标用户", "核心功能"]
    # S10-082: 对话化文案 (语义不变, 文案含痛点/问题)
    assert "痛点" in mgr._next_product_question() or "问题" in mgr._next_product_question()


def test_missing_user_asked_after_problem():
    mgr = _manager()
    mgr.start_product_discovery("x")
    mgr.handle_product_answer("解决计分麻烦")
    assert mgr.product_intent.missing_fields() == ["目标用户", "核心功能"]
    assert "目标用户" in mgr._next_product_question()


def test_missing_core_features_asked_last():
    mgr = _manager()
    mgr.start_product_discovery("x")
    mgr.handle_product_answer("解决计分麻烦")
    mgr.handle_product_answer("台球爱好者")
    assert mgr.product_intent.missing_fields() == ["核心功能"]
    assert "核心功能" in mgr._next_product_question()


def test_missing_fields_never_silent():
    """F: 每轮追问都携带缺失字段名 (明确, 不静默)。"""
    mgr = _manager()
    for _ in range(3):
        resp = mgr.handle_product_answer("补充内容") if mgr.product_intent else mgr.start_product_discovery("x")
        if mgr._product_pending:
            assert "(缺失字段:" in resp.message


# ================================================================== 8. Product Confirmation (验收 D/E)

def test_confirm_y_project_creation_state():
    mgr = _manager()
    _run_product_flow(mgr)
    resp = mgr.handle_product_confirm("y")
    assert resp.state == STATES.PROJECT_CREATION
    assert resp.needs_input is False


def test_confirm_y_with_fn_executes_and_done():
    """D: y + confirm_fn → 执行回调 → DONE + Product Created 消息。"""
    mgr = _manager()
    _run_product_flow(mgr)
    seen = {}

    def confirm_fn(pi):
        seen["pi"] = pi
        return f"Product Created: {pi.name} — Ready for Engineering."

    resp = mgr.handle_product_confirm("y", confirm_fn=confirm_fn)
    assert resp.state == STATES.DONE
    assert seen["pi"] is mgr.product_intent
    assert "Product Created" in resp.message
    assert "Ready for Engineering." in resp.message


def test_confirm_yes_case_insensitive():
    mgr = _manager()
    _run_product_flow(mgr)
    for answer in ("y", "Y", "yes", "YES"):
        assert mgr.handle_product_confirm(answer, confirm_fn=lambda pi: "ok").state == STATES.DONE


def test_confirm_n_resets_discovery():
    """E: n → DISCOVERY 重置, product_intent / pending 清空。"""
    mgr = _manager()
    _run_product_flow(mgr)
    resp = mgr.handle_product_confirm("n")
    assert resp.state == STATES.DISCOVERY
    assert mgr.product_intent is None
    assert mgr._product_pending == []
    assert "已取消" in resp.message


def test_confirm_other_answer_resets():
    """S10-081: 取消词/空回答 → 重置 (y/N 约定保留); 其它文本 → 改名。"""
    for answer in ("取消", "n", "no", ""):
        mgr = _manager()
        _run_product_flow(mgr)
        resp = mgr.handle_product_confirm(answer)
        assert resp.state == STATES.DISCOVERY
        assert mgr.product_intent is None
    # 非取消文本 → 改名 (S10-081)
    mgr = _manager()
    _run_product_flow(mgr)
    resp = mgr.handle_product_confirm("账本精灵")
    assert mgr.product_intent is not None
    assert mgr.product_intent.name == "账本精灵"


def test_confirm_without_product_clarifies():
    mgr = _manager()
    resp = mgr.handle_product_confirm("y")
    assert resp.state == STATES.CLARIFICATION


def test_confirm_fn_failure_resets_with_error():
    """失败安全: confirm_fn 异常 → 重置 DISCOVERY + 明确错误消息。"""
    mgr = _manager()
    _run_product_flow(mgr)

    def boom(pi):
        raise RuntimeError("注册失败: repo 不存在")

    resp = mgr.handle_product_confirm("y", confirm_fn=boom)
    assert resp.state == STATES.DISCOVERY
    assert mgr.product_intent is None
    assert "产品创建失败" in resp.message
    assert "注册失败" in resp.message


def test_confirm_history_records_transitions():
    """状态迁移入史: DISCOVERY → PRODUCT_CONFIRMATION → PROJECT_CREATION → DONE。"""
    mgr = _manager()
    _run_product_flow(mgr)
    mgr.handle_product_confirm("y", confirm_fn=lambda pi: "ok")
    tos = [h["to"] for h in mgr.history if h.get("event") == "transition"]
    assert "product_confirmation" in tos
    assert "project_creation" in tos
    assert "done" in tos


# ================================================================== 9. Session Context (验收 H)

def test_session_context_product_intent_default_none():
    ctx = _session_ctx("/tmp/w")
    assert ctx.product_intent is None


def test_session_context_product_intent_set_get():
    cm = CTX_MOD.ContextManager(workspace="/tmp/w")
    pi = _complete_product()
    cm.update(product_intent=pi)
    assert cm.get().product_intent is pi


def test_session_context_to_dict_product_intent():
    ctx = _session_ctx("/tmp/w")
    assert ctx.to_dict()["product_intent"] is None
    ctx.product_intent = _complete_product()
    assert ctx.to_dict()["product_intent"] == ctx.product_intent.to_dict()


def test_session_context_known_fields_includes_product_intent():
    assert "product_intent" in CTX_MOD.KNOWN_FIELDS


def test_session_context_product_intent_not_in_metadata():
    """H: product_intent 是顶层字段 (KNOWN_FIELDS), 不落入 metadata。"""
    cm = CTX_MOD.ContextManager(workspace="/tmp/w")
    cm.update(product_intent=_complete_product())
    assert "product_intent" not in cm.get().metadata


# ================================================================== 10. Regression (验收 L)

def test_regression_create_project_intent():
    assert _parser().parse("创建一个APP").intent_type == INTENT_MOD.INTENT_CREATE_PROJECT


def test_regression_zhuoyige_ecommerce_keeps_create_project():
    """既有口径: "帮我做一个电商 APP" 仍 → create_project (基线测试依赖)。"""
    assert _parser().parse("帮我做一个电商 APP").intent_type == INTENT_MOD.INTENT_CREATE_PROJECT


def test_regression_kaifa_gongju_keeps_create_project():
    assert _parser().parse("开发一个工具").intent_type == INTENT_MOD.INTENT_CREATE_PROJECT


def test_regression_run_task_intent():
    assert _parser().parse("帮我实现登录功能").intent_type == INTENT_MOD.INTENT_RUN_TASK


def test_regression_woxiang_kanzhuangtai_show_status():
    """优先级回归: "我想看看状态" → show_status (不被 create_product 抢)。"""
    assert _parser().parse("我想看看状态").intent_type == INTENT_MOD.INTENT_SHOW_STATUS


def test_regression_conversation_create_project_confirmation():
    """既有 flow: handle("创建一个APP") → CONFIRMATION (非产品流程)。"""
    mgr = _manager()
    resp = mgr.handle("创建一个APP", _parser())
    assert resp.state == STATES.CONFIRMATION
    assert mgr.pending_intent.intent_type == INTENT_MOD.INTENT_CREATE_PROJECT
    assert mgr.product_intent is None


def test_regression_conversation_list_projects():
    mgr = _manager()
    resp = mgr.handle("项目列表", _parser())
    assert resp.state == STATES.CONFIRMATION
    assert mgr.pending_intent.intent_type == INTENT_MOD.INTENT_LIST_PROJECTS


def test_regression_default_routes_intact():
    routes = ROUTER_MOD.IntentRouter().routes()
    assert routes["create_project"] == "create_project"
    assert routes["run_task"] == "agent.execute_task"
    assert routes["list_projects"] == "list_projects"
    assert routes["create_product"] == "create_product"


def test_regression_create_project_action_unchanged(fake_org, tmp_path):
    """create_project action 行为不变 (name 参数照常透传 org)。"""
    root = tmp_path / "ws"
    root.mkdir()
    intent = INTENT_MOD.IntentObject(
        intent_type="create_project", params={"name": "电商APP"}, raw="创建一个APP"
    )
    result = ACTIONS_MOD.create_project(_exec_ctx(root, intent=intent))
    assert result.ok is True
    assert fake_org.calls[0][1].name == "电商APP"
    assert "项目已注册" in result.message


def test_regression_session_dispatch_create_project(monkeypatch, capsys, tmp_path):
    """既有会话派发: "创建一个APP" 走普通 action 链 (非产品流程)。"""
    root = tmp_path / "ws"
    root.mkdir()
    fake = FakeOrgCli()
    monkeypatch.setattr(ACTIONS_MOD, "_load_org_cli", lambda: fake)
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
    )
    sess._dispatch("创建一个APP")
    assert len(fake.calls) == 1
    out = capsys.readouterr().out
    assert "项目已注册" in out
    assert sess.conversation.product_intent is None


def test_regression_session_dispatch_unknown_intent(capsys):
    """S10-075: 未知输入 → AI 问答 (不再 '未识别意图')。"""
    sess = SESS_MOD.InteractiveSession(chat_service=_FakeChat075())
    sess._dispatch("foobar")
    out = capsys.readouterr().out
    assert "未识别意图" not in out
    assert "AI:" in out


# ================================================================== 11. Session 端到端产品流程 (验收 D/H)

def test_session_product_flow_end_to_end(fake_org, capsys, tmp_path):
    """端到端: 自然语言 → DISCOVERY 多轮 → 确认 y → create_product → Product Created。"""
    root = tmp_path / "ws"
    root.mkdir()
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
    )
    sess._dispatch("我想开发一个台球计分APP")
    sess._dispatch("解决台球比赛计分麻烦")
    sess._dispatch("台球爱好者")
    sess._dispatch("计分、比赛记录、排行榜")
    sess._dispatch("y")
    out = capsys.readouterr().out
    assert "痛点" in out or "问题" in out
    assert "目标用户是谁" in out
    assert "核心功能有哪些" in out
    assert "确认创建这个产品? (y/N)" in out
    assert "Product Created:" in out
    assert "Ready for Engineering." in out
    # 桥接调用 + product.json 落盘
    assert len(fake_org.calls) == 1
    # S10-081: 产品名 = 命名智能生成的有意义名称 (非"未命名产品-")
    assert not fake_org.calls[0][1].name.startswith("未命名产品-")
    assert fake_org.calls[0][1].name
    product_files = list((root / "projects").rglob("product.json"))
    assert product_files, "product.json 未落盘"
    data = json.loads(product_files[0].read_text(encoding="utf-8"))
    assert data["core_features"] == ["计分", "比赛记录", "排行榜"]
    assert data["status"] == "product_defined"  # S10-115 J-1: Lifecycle 词汇 (替代旧 project_created)


def test_session_product_flow_cancel(fake_org, capsys, tmp_path):
    """E 端到端: 确认 n → 已取消 + 重置 (不创建)。"""
    root = tmp_path / "ws"
    root.mkdir()
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
    )
    sess._dispatch("我想开发一个台球计分APP")
    sess._dispatch("解决台球比赛计分麻烦")
    sess._dispatch("台球爱好者")
    sess._dispatch("计分、比赛记录")
    sess._dispatch("n")
    out = capsys.readouterr().out
    assert "已取消产品" in out
    assert fake_org.calls == []  # 未创建
    assert sess.conversation.product_intent is None


def test_session_product_intent_stored_after_confirm(fake_org, capsys, tmp_path):
    """H: 确认后 SessionContext.product_intent 存有完整 ProductIntent。"""
    root = tmp_path / "ws"
    root.mkdir()
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
    )
    sess._dispatch("我想开发一个台球计分APP")
    sess._dispatch("解决台球比赛计分麻烦")
    sess._dispatch("台球爱好者")
    sess._dispatch("计分、比赛记录")
    sess._dispatch("y")
    capsys.readouterr()
    assert sess.context.product_intent is not None
    assert sess.context.product_intent.problem == "解决台球比赛计分麻烦"
    assert sess.context.product_intent.core_features == ["计分", "比赛记录"]


def test_session_slash_not_intercepted_by_product_flow(capsys, tmp_path):
    """slash 命令不被产品流程拦截 (状态机不接管)。"""
    root = tmp_path / "ws"
    root.mkdir()
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
    )
    sess._dispatch("我想开发一个台球计分APP")
    sess._dispatch("/status")
    out = capsys.readouterr().out
    assert "会话状态" in out  # slash 正常处理

# ================================================================== 12. 产品流程控制短语 (非答案不被吞 — S10-084)

def test_answer_cancel_phrase_resets_discovery():
    """发现阶段输入取消短语 → 重置 (不当作字段答案)。"""
    mgr = _manager()
    mgr.start_product_discovery("我想开发一个CRM")
    resp = mgr.handle_product_answer("取消")
    assert resp.state == STATES.DISCOVERY
    assert mgr.product_intent is None
    assert mgr._product_pending == []
    assert "已取消" in resp.message


def test_answer_summary_phrase_organizes_without_create():
    """transcript: '先帮我整理需求, 不要创建项目' → 输出需求整理, 绝不进入创建/确认。"""
    mgr = _manager()
    mgr.start_product_discovery("我想开发一个CRM")
    mgr.handle_product_answer("小团队用Excel管客户很混乱")
    mgr.handle_product_answer("10人以内的小团队")
    resp = mgr.handle_product_answer("你先帮我整理需求，不要创建项目。")
    assert mgr.product_intent is None
    assert mgr._product_pending == []
    assert resp.state == STATES.DISCOVERY
    assert "未创建任何项目" in resp.message
    assert "需求整理" in resp.message
    assert "小团队用Excel管客户很混乱" in resp.message
    # 命令未被吞成 core_features 答案, 不进入确认
    assert "确认创建这个产品? (y/N)" not in resp.message
    assert resp.needs_input is True


def test_answer_create_now_incomplete_nudges_batch():
    """transcript: 发现阶段输入 '现在创建项目' (必填未齐) → 引导一次性补齐, 不逃生。"""
    mgr = _manager()
    mgr.start_product_discovery("我想开发一个 Todo API")
    resp = mgr.handle_product_answer("现在创建项目")
    assert resp.passthrough is False
    assert mgr.product_intent is not None  # 产品流程保留
    assert mgr._product_batch_mode is True
    assert "可以创建，不过还缺少" in resp.message
    assert "- 产品解决什么问题" in resp.message
    assert "- 核心功能" in resp.message
    # 未被吞成 problem 答案
    assert mgr.product_intent.problem is None


def test_answer_escape_list_projects_passthrough():
    """transcript: 发现阶段输入 '我现在有哪些项目' → 逃生 (passthrough), 不吞成答案。"""
    mgr = _manager()
    mgr.start_product_discovery("x")
    resp = mgr.handle_product_answer("我现在有哪些项目")
    assert resp.passthrough is True
    assert mgr.product_intent is None
    assert mgr._product_pending == []


def test_answer_batch_phrase_lists_remaining_questions():
    """transcript: '问题有点多，你整理一下' → 一次性列出剩余必填问题 (编号) + 批量模式。"""
    mgr = _manager()
    mgr.start_product_discovery("x")
    mgr.handle_product_answer("解决痛点")
    resp = mgr.handle_product_answer("问题有点多，你整理一下")
    assert mgr._product_batch_mode is True
    assert "目标用户是谁" in resp.message
    assert "核心功能有哪些" in resp.message
    assert "1." in resp.message
    # 未被吞成 user 答案
    assert mgr.product_intent.user is None


def test_multi_part_answer_fills_all_fields():
    """分号多段回答 (带标签) → 一次填充多个字段到确认。"""
    mgr = _manager()
    mgr.start_product_discovery("x")
    resp = mgr.handle_product_answer(
        "痛点：台球计分麻烦；用户：台球爱好者；功能：计分、比赛记录、排行榜"
    )
    assert resp.state == STATES.PRODUCT_CONFIRMATION
    assert mgr.product_intent.problem == "台球计分麻烦"
    assert mgr.product_intent.user == "台球爱好者"
    assert mgr.product_intent.core_features == ["计分", "比赛记录", "排行榜"]
    assert "确认创建这个产品? (y/N)" in resp.message


def test_multi_part_partial_answer_continues():
    """分号多段但未填完 → 剩余字段继续追问。"""
    mgr = _manager()
    mgr.start_product_discovery("x")
    resp = mgr.handle_product_answer("台球计分麻烦；台球爱好者")
    assert resp.state == STATES.DISCOVERY
    assert mgr.product_intent.problem == "台球计分麻烦"
    assert mgr.product_intent.user == "台球爱好者"
    assert mgr._product_pending == ["core_features"]
    assert "核心功能" in resp.message


def test_single_field_semicolon_not_mis_split():
    """core_features 单字段待填 → 分号答案整体进入功能解析 (不误切)。"""
    mgr = _manager()
    mgr.start_product_discovery("x")
    mgr.handle_product_answer("台球计分麻烦")
    mgr.handle_product_answer("台球爱好者")
    resp = mgr.handle_product_answer("计分；比赛记录；排行榜")
    assert resp.state == STATES.PRODUCT_CONFIRMATION
    assert mgr.product_intent.core_features == ["计分", "比赛记录", "排行榜"]


def test_confirm_stage_create_now_equals_y():
    """确认阶段输入 '现在创建项目' → 等价 y (直接创建)。"""
    mgr = _manager()
    _run_product_flow(mgr)
    resp = mgr.handle_product_confirm("现在创建项目", confirm_fn=lambda pi: "created")
    assert resp.state == STATES.DONE
    assert "created" in resp.message


def test_confirm_stage_escape_passthrough():
    """确认阶段输入 '项目列表' → 逃生 (不当作改名)。"""
    mgr = _manager()
    _run_product_flow(mgr)
    resp = mgr.handle_product_confirm("项目列表")
    assert resp.passthrough is True
    assert mgr.product_intent is None


# ================================================================== 13. Session 端到端控制短语 (transcript 复现)

def test_session_summary_without_create_transcript(fake_org, capsys, tmp_path):
    """端到端复现 transcript: '先帮我整理需求, 不要创建项目' → 不创建、输出整理。"""
    root = tmp_path / "ws"
    root.mkdir()
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
    )
    sess._dispatch("你好，我想做一个软件产品")
    sess._dispatch("我想做一个帮助小团队管理客户关系的系统")
    sess._dispatch("主要给 10 人以内的小团队使用，他们现在用 Excel 管理客户，很混乱。")
    sess._dispatch("你先帮我整理需求，不要创建项目。")
    out = capsys.readouterr().out
    assert "需求整理" in out
    assert "未创建任何项目" in out
    assert "确认创建这个产品? (y/N)" not in out
    assert fake_org.calls == []  # 未创建
    assert sess.conversation.product_intent is None


def test_session_escape_list_projects_transcript(capsys, tmp_path):
    """端到端: 发现阶段输入 '我现在有哪些项目' → 走项目清单 (不吞成 user 答案)。"""
    root = tmp_path / "ws"
    root.mkdir()
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
    )
    sess._dispatch("我想开发一个 Todo 管理 API，目标是学习后端开发")
    sess._dispatch("我现在有哪些项目")
    out = capsys.readouterr().out
    # 空工作区 → 项目清单空表 (表头渲染), 而非产品追问吞掉该命令
    assert "id" in out and "name" in out
    assert sess.conversation.product_intent is None
    assert "目标用户是谁" not in out  # 未被吞成 user 追问的答案


def test_session_create_now_nudge_transcript(capsys, tmp_path):
    """端到端: 发现阶段输入 '现在创建项目' → 引导补齐剩余需求 (批量模式)。"""
    root = tmp_path / "ws"
    root.mkdir()
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
    )
    sess._dispatch("我想开发一个 Todo 管理 API，目标是学习后端开发")
    sess._dispatch("现在创建项目")
    out = capsys.readouterr().out
    assert "可以创建，不过还缺少" in out
    assert "- 核心功能" in out
    assert sess.conversation.product_intent is not None
    assert sess.conversation._product_batch_mode is True


def test_session_batch_question_transcript(capsys, tmp_path):
    """端到端: '问题有点多，你整理一下' → 一次性列出剩余问题。"""
    root = tmp_path / "ws"
    root.mkdir()
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
    )
    sess._dispatch("我想开发一个 Todo 管理 API，目标是学习后端开发")
    sess._dispatch("手动测试太慢")
    sess._dispatch("问题有点多，你整理一下")
    out = capsys.readouterr().out
    assert "剩余需求" in out
    assert "目标用户是谁" in out
    assert "核心功能有哪些" in out
    assert sess.conversation._product_batch_mode is True


def test_session_multi_part_batch_answer_transcript(capsys, tmp_path):
    """端到端: 批量模式下用分号一次补齐全部字段 → 直接到确认。"""
    root = tmp_path / "ws"
    root.mkdir()
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
    )
    sess._dispatch("我想开发一个 Todo 管理 API，目标是学习后端开发")
    sess._dispatch("现在创建项目")
    sess._dispatch("痛点：手动测试太慢；用户：想学后端的开发者；功能：增删改查、列表、认证")
    out = capsys.readouterr().out
    assert "确认创建这个产品? (y/N)" in out
    assert "手动测试太慢" in out
    assert "想学后端的开发者" in out
    assert "增删改查, 列表, 认证" in out



# ================================================================== 14. 边界: 修改已有信息 / 取消任意阶段 (reviewer 补充)

def test_edit_existing_field_during_discovery():
    """Test 5: 先填 '用户: 小团队', 再 '修改一下，目标用户改成创业公司' → 更新不重问。"""
    mgr = _manager()
    mgr.start_product_discovery("我想做一个CRM")
    mgr.handle_product_answer("客户信息散落在Excel，很难跟进")
    mgr.handle_product_answer("用户：小团队")
    assert mgr.product_intent.user == "小团队"
    assert mgr._product_pending == ["core_features"]
    resp = mgr.handle_product_answer("修改一下，目标用户改成创业公司")
    assert mgr.product_intent.user == "创业公司"
    assert mgr._product_pending == ["core_features"]  # 不推进字段, 不重问已答项
    assert "已更新目标用户" in resp.message
    assert "核心功能" in resp.message  # 继续追问剩余字段


def test_edit_pending_field_directly():
    """Test 5: 待填字段直接用 '用户改成X' → 视为编辑而非答案。"""
    mgr = _manager()
    mgr.start_product_discovery("x")
    resp = mgr.handle_product_answer("用户改成创业公司")
    assert mgr.product_intent.user == "创业公司"
    assert mgr.product_intent.problem is None
    assert "problem" in resp.message  # 仍追问剩余字段


def test_edit_normal_answer_not_misparsed():
    """Test 5 反例: '把客户管理从混乱改成有序' 是痛点回答, 不是编辑指令。"""
    mgr = _manager()
    mgr.start_product_discovery("x")
    resp = mgr.handle_product_answer("把客户管理从混乱改成有序")
    assert mgr.product_intent.problem == "把客户管理从混乱改成有序"
    assert mgr.product_intent.user is None
    assert resp.state == STATES.DISCOVERY


def test_edit_at_confirmation_stage():
    """Test 5: 确认阶段 '把用户改成职业选手' → 更新并回到确认 (不当作改名)。"""
    mgr = _manager()
    _run_product_flow(mgr)
    resp = mgr.handle_product_confirm("把用户改成职业选手")
    assert mgr.product_intent is not None
    assert mgr.product_intent.user == "职业选手"
    assert resp.state == STATES.PRODUCT_CONFIRMATION
    assert "确认创建这个产品? (y/N)" in resp.message


def test_edit_plain_rename_still_works():
    """Test 5 兼容: 确认阶段普通文本仍是改名 (S10-081 不回归)。"""
    mgr = _manager()
    _run_product_flow(mgr)
    mgr.handle_product_confirm("账本精灵")
    assert mgr.product_intent.name == "账本精灵"


def test_cancel_any_stage_resets():
    """Test 4: '取消' 在回答阶段与确认阶段都重置为 DISCOVERY。"""
    # 回答阶段
    mgr = _manager()
    mgr.start_product_discovery("x")
    resp = mgr.handle_product_answer("取消")
    assert resp.state == STATES.DISCOVERY
    assert mgr.product_intent is None
    # 确认阶段
    mgr = _manager()
    _run_product_flow(mgr)
    resp = mgr.handle_product_confirm("取消")
    assert resp.state == STATES.DISCOVERY
    assert mgr.product_intent is None
    assert "已取消" in resp.message


def test_normal_discovery_one_shot_no_requestion():
    """Test 1: 正常发现 + 一次多段填充 → 直达确认, 不逐个重问。"""
    mgr = _manager()
    mgr.start_product_discovery("我想做一个帮助小团队管理客户关系的软件")
    resp = mgr.handle_product_answer(
        "问题：客户信息散落在 Excel，很难跟进；用户：10人以内销售团队；功能：客户档案、跟进记录、提醒"
    )
    assert resp.state == STATES.PRODUCT_CONFIRMATION
    assert mgr.product_intent.problem == "客户信息散落在 Excel，很难跟进"
    assert mgr.product_intent.user == "10人以内销售团队"
    assert mgr.product_intent.core_features == ["客户档案", "跟进记录", "提醒"]
    assert "问题" in resp.message and "目标用户" in resp.message and "核心功能" in resp.message
    assert "确认创建这个产品? (y/N)" in resp.message
