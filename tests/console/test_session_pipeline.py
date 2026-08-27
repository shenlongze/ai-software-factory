"""tests/console/test_session_pipeline.py — S10-051 AI Software Factory Pipeline (Phase 2-8)。

设计: docs/sprint10/S10-051-pipeline-design.md
覆盖 (验收 A-K):
A. ProductIntent → PRD.md (6 节: Overview/Problem/Target User/Core Features/Usage Scenario/Future)
B. EngineeringPlan → engineering.json (architecture/modules/technical_tasks)
C. TaskTree → tasks.json (Epic/Task/Priority/Agent Type)
D. AgentAssignment → execution_plan.json (复用 select_agent: frontend→flutter-dev/backend→backend-1)
E. Lifecycle: project.json status → pending_arch_review (S10-111 M3-7 审批门) → 审批后 execution_ready
F. prepare_project 一次生成 4 资产 + "Project Ready For Engineering."
G. prepare_project 敏感 → ConfirmationGate
H. Conversation: 产品创建后引导 "是否生成工程计划?"
I. 规则生成不调 LLM / 不引入依赖
J. 新增 >=50 测试全绿 + 全量 pytest 不破坏基线
K. 回归: 现有 create_product/run_task 不受影响

测试装配 (同 test_session_product): monkeypatch actions._load_org_cli 注入
FakeOrgCli (避免真实注册 ~/.factory); workspace 一律 tmp_path (零污染)。

basename 全仓库唯一 (test_session_* 前缀, tests/console 既有模式)。
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

ACT_MOD = importlib.import_module("factory-console.session.action")
ACTIONS_MOD = importlib.import_module("factory-console.session.actions")
CONF_MOD = importlib.import_module("factory-console.session.confirm")
CONV_MOD = importlib.import_module("factory-console.session.conversation")
CTX_MOD = importlib.import_module("factory-console.session.context")
INTENT_MOD = importlib.import_module("factory-console.session.intent")
PIPE_MOD = importlib.import_module("factory-console.session.pipeline")
PROD_MOD = importlib.import_module("factory-console.session.product")
ROUTER_MOD = importlib.import_module("factory-console.session.router")
SESS_MOD = importlib.import_module("factory-console.session.session")

STATES = CONV_MOD.ConversationState


# ------------------------------------------------------------------ 工具

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


def _manager(**kw):
    return CONV_MOD.ConversationManager(**kw)


def _exec_ctx(root: Path, **kw):
    return ACT_MOD.ExecutionContext(
        workspace=root,
        session=CTX_MOD.SessionContext(workspace=str(root)),
        user="user",
        **kw,
    )


class _FakeOrgCli:
    """Service Layer 桩 (monkeypatch _load_org_cli): 记录调用, 返回规范结果 (slug=scorepocket)。"""

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
            "project": self.project
            or {"id": "p1", "name": args.name, "slug": "scorepocket"},
            "analysis_ref": None,
            "baseline_ref": None,
            "snapshot_ref": None,
            "exit_code": 0,
        }


class _SpyGate:
    """Session 集成探针 gate: 记录 confirm 调用, 返回注入的决策。"""

    def __init__(self, decision: bool = True) -> None:
        self.decision = decision
        self.calls: list[tuple[str, object, object]] = []

    def confirm(self, action_name, intent, context):
        self.calls.append((action_name, intent, context))
        return self.decision


@pytest.fixture
def fake_org(monkeypatch):
    org = _FakeOrgCli()
    monkeypatch.setattr(ACTIONS_MOD, "_load_org_cli", lambda: org)
    return org


def _create_product_on_disk(root: Path, product=None, fake_org=None, **kw):
    """create_product action 落盘 product.json → 返回 (context, result)。"""
    ctx = _exec_ctx(root, **kw)
    ctx.session.product_intent = product or _complete_product()
    result = ACTIONS_MOD.create_product(ctx)
    assert result.ok, result.message
    return ctx, result


# ================================================================== 1. Intent 解析 (P1 / 验收 I)


@pytest.mark.parametrize(
    "text",
    ["生成PRD", "生成需求文档", "PRD", "帮我生成PRD文档", "生成PRD文档"],
)
def test_intent_generate_prd_keywords(text):
    intent = INTENT_MOD.KeywordIntentParser().parse(text)
    assert intent is not None
    assert intent.intent_type == INTENT_MOD.INTENT_GENERATE_PRD
    assert intent.raw == text


@pytest.mark.parametrize(
    "text",
    ["准备开发", "生成工程计划", "工程计划", "准备工程", "准备工程开发"],
)
def test_intent_prepare_project_keywords(text):
    intent = INTENT_MOD.KeywordIntentParser().parse(text)
    assert intent is not None
    assert intent.intent_type == INTENT_MOD.INTENT_PREPARE_PROJECT
    assert intent.raw == text


def test_intent_generate_prd_priority_over_product():
    """优先级: \"我想生成PRD\" → generate_prd (不被 create_product \"我想\" 抢)。"""
    intent = INTENT_MOD.KeywordIntentParser().parse("我想生成PRD")
    assert intent.intent_type == INTENT_MOD.INTENT_GENERATE_PRD


def test_intent_prepare_project_priority_over_project():
    """优先级: \"准备开发一个APP\" → prepare_project (不被 \"开发一个\" 抢)。"""
    intent = INTENT_MOD.KeywordIntentParser().parse("准备开发一个APP")
    assert intent.intent_type == INTENT_MOD.INTENT_PREPARE_PROJECT


def test_intent_pipeline_constants_registered():
    assert INTENT_MOD.INTENT_GENERATE_PRD == "generate_prd"
    assert INTENT_MOD.INTENT_PREPARE_PROJECT == "prepare_project"


def test_intent_parse_deterministic_confidence():
    intent = INTENT_MOD.KeywordIntentParser().parse("准备开发")
    assert intent.confidence == 1.0
    assert intent.parameters == {}


# ================================================================== 2. Router 映射 (P4)


def test_router_default_routes_include_pipeline():
    routes = ROUTER_MOD.IntentRouter().routes()
    assert routes["generate_prd"] == "generate_prd"
    assert routes["prepare_project"] == "prepare_project"


def test_router_generate_prd_route_resolves():
    registry = ACTIONS_MOD.build_default_actions()
    intent = INTENT_MOD.IntentObject(intent_type="generate_prd", raw="生成PRD")
    action = ROUTER_MOD.IntentRouter().route(intent, registry)
    assert action.name == "generate_prd"
    assert action.handler is ACTIONS_MOD.generate_prd


def test_router_prepare_project_route_resolves():
    registry = ACTIONS_MOD.build_default_actions()
    intent = INTENT_MOD.IntentObject(intent_type="prepare_project", raw="准备开发")
    action = ROUTER_MOD.IntentRouter().route(intent, registry)
    assert action.name == "prepare_project"
    assert action.handler is ACTIONS_MOD.prepare_project


def test_router_existing_routes_unchanged():
    routes = ROUTER_MOD.IntentRouter().routes()
    assert routes["create_project"] == "create_project"
    assert routes["run_task"] == "agent.execute_task"


# ================================================================== 3. ProductDocument → PRD (验收 A)


def test_prd_has_six_sections():
    prd = PIPE_MOD.ProductDocument.from_product_intent(_complete_product())
    for section in PIPE_MOD.ProductDocument.SECTIONS:
        assert f"## {section}" in prd, f"缺少 PRD 节: {section}"


def test_prd_sections_constant_exact():
    # S10-111 M3-5 更新: PRD 深度化 — 追加 User Stories / Acceptance Criteria
    # (原 6 节保持不变, 新增 2 节收尾; 既有 6 节断言逐一保留)
    assert PIPE_MOD.ProductDocument.SECTIONS == (
        "Product Overview",
        "Problem",
        "Target User",
        "Core Features",
        "Usage Scenario",
        "Future Direction",
        "User Stories",
        "Acceptance Criteria",
    )


def test_prd_overview_contains_name_and_platform():
    prd = PIPE_MOD.ProductDocument.from_product_intent(
        _complete_product(platform="mobile")
    )
    assert "ScorePocket" in prd
    assert "mobile" in prd


def test_prd_problem_section_content():
    prd = PIPE_MOD.ProductDocument.from_product_intent(_complete_product())
    assert "台球比赛计分麻烦" in prd


def test_prd_target_user_section_content():
    prd = PIPE_MOD.ProductDocument.from_product_intent(_complete_product())
    assert "台球爱好者" in prd


def test_prd_core_features_listed():
    prd = PIPE_MOD.ProductDocument.from_product_intent(_complete_product())
    for feature in ("计分", "比赛记录", "排行榜"):
        assert f"- {feature}" in prd


def test_prd_usage_scenario_mentions_features():
    prd = PIPE_MOD.ProductDocument.from_product_intent(_complete_product())
    assert "计分, 比赛记录, 排行榜" in prd
    assert "核心使用场景" in prd


def test_prd_future_direction_present():
    prd = PIPE_MOD.ProductDocument.from_product_intent(_complete_product())
    assert "## Future Direction" in prd


def test_prd_missing_fields_placeholders():
    """I: 缺失字段显式占位, 不静默 (规则生成可空跑)。"""
    prd = PIPE_MOD.ProductDocument.from_product_intent(PROD_MOD.ProductIntent())
    assert "(未填写)" in prd
    assert "(待补充)" in prd


def test_prd_markdown_heading_format():
    prd = PIPE_MOD.ProductDocument.from_product_intent(_complete_product())
    assert prd.startswith("# ")


def test_prd_deterministic():
    p1 = PIPE_MOD.ProductDocument.from_product_intent(_complete_product())
    p2 = PIPE_MOD.ProductDocument.from_product_intent(_complete_product())
    assert p1 == p2


def test_prd_unnamed_product_placeholder():
    prd = PIPE_MOD.ProductDocument.from_product_intent(_complete_product(name=None))
    assert "(未命名产品)" in prd


# ================================================================== 4. EngineeringPlan (验收 B)


def test_engineering_architecture_mobile():
    plan = PIPE_MOD.EngineeringPlan.from_prd(_complete_product(platform="mobile"))
    assert plan["architecture"] == "Flutter + Backend API"


def test_engineering_architecture_web():
    plan = PIPE_MOD.EngineeringPlan.from_prd(_complete_product(platform="web"))
    assert plan["architecture"] == "Web Frontend + Backend API"


def test_engineering_architecture_desktop():
    plan = PIPE_MOD.EngineeringPlan.from_prd(_complete_product(platform="desktop"))
    assert plan["architecture"] == "Desktop App + Backend API"


def test_engineering_architecture_default():
    plan = PIPE_MOD.EngineeringPlan.from_prd(_complete_product(platform=None))
    assert plan["architecture"] == "Backend API + Frontend"
    plan2 = PIPE_MOD.EngineeringPlan.from_prd(_complete_product(platform="unknown"))
    assert plan2["architecture"] == "Backend API + Frontend"


def test_engineering_modules_from_features():
    plan = PIPE_MOD.EngineeringPlan.from_prd(_complete_product())
    modules = plan["modules"]
    assert [m["name"] for m in modules] == ["计分", "比赛记录", "排行榜"]
    assert [m["slug"] for m in modules] == ["module-1", "module-2", "module-3"]


def test_engineering_modules_english_slug():
    plan = PIPE_MOD.EngineeringPlan.from_prd(
        _complete_product(core_features=["scoring", "records"])
    )
    assert [m["slug"] for m in plan["modules"]] == ["scoring", "records"]


def test_engineering_modules_empty_fallback():
    plan = PIPE_MOD.EngineeringPlan.from_prd(
        _complete_product(core_features=[])
    )
    assert plan["modules"] == [{"name": "核心功能", "slug": "core"}]


def test_engineering_technical_tasks():
    plan = PIPE_MOD.EngineeringPlan.from_prd(_complete_product())
    tasks = plan["technical_tasks"]
    assert [t["type"] for t in tasks] == ["database", "backend", "frontend", "test"]


def test_engineering_from_prd_keys():
    plan = PIPE_MOD.EngineeringPlan.from_prd(_complete_product(), prd_text="# PRD")
    assert set(plan) >= {"architecture", "modules", "technical_tasks"}
    assert plan["name"] == "ScorePocket"
    assert plan["prd_generated"] is True


def test_engineering_deterministic():
    a = PIPE_MOD.EngineeringPlan.from_prd(_complete_product(platform="mobile"))
    b = PIPE_MOD.EngineeringPlan.from_prd(_complete_product(platform="mobile"))
    assert a == b


# ================================================================== 5. TaskTree (验收 C)


def _plan():
    return PIPE_MOD.EngineeringPlan.from_prd(_complete_product())


def test_tasktree_epics_per_module():
    tree = PIPE_MOD.TaskTree.from_engineering(_plan())
    assert len(tree["epics"]) == 3
    assert [e["module"] for e in tree["epics"]] == ["module-1", "module-2", "module-3"]


def test_tasktree_epic_format():
    tree = PIPE_MOD.TaskTree.from_engineering(_plan())
    epic = tree["epics"][0]
    assert epic["id"] == "epic-module-1"
    assert epic["name"] == "计分 系统"
    assert epic["module"] == "module-1"


def test_tasktree_tasks_per_epic():
    tree = PIPE_MOD.TaskTree.from_engineering(_plan())
    assert tree["count"] == 12  # 3 模块 × 4 任务
    for epic in tree["epics"]:
        epic_tasks = [t for t in tree["tasks"] if t["epic"] == epic["id"]]
        assert len(epic_tasks) == 4


def test_tasktree_priorities():
    tree = PIPE_MOD.TaskTree.from_engineering(_plan())
    by_type = {t["type"]: t["priority"] for t in tree["tasks"]}
    assert by_type["database"] == "P0"
    assert by_type["backend"] == "P0"
    assert by_type["frontend"] == "P1"
    assert by_type["test"] == "P1"


def test_tasktree_agent_types():
    tree = PIPE_MOD.TaskTree.from_engineering(_plan())
    by_type = {t["type"]: t["agent_type"] for t in tree["tasks"]}
    assert by_type["database"] == "backend"
    assert by_type["backend"] == "backend"
    assert by_type["frontend"] == "frontend"
    assert by_type["test"] == "qa"


def test_tasktree_task_ids_unique():
    tree = PIPE_MOD.TaskTree.from_engineering(_plan())
    ids = [t["id"] for t in tree["tasks"]]
    assert len(ids) == len(set(ids))
    assert all(tid.startswith("task-") for tid in ids)


def test_tasktree_keys():
    tree = PIPE_MOD.TaskTree.from_engineering(_plan())
    assert set(tree) == {"epics", "tasks", "count"}


def test_tasktree_epic_linkage():
    tree = PIPE_MOD.TaskTree.from_engineering(_plan())
    epic_ids = {e["id"] for e in tree["epics"]}
    assert all(t["epic"] in epic_ids for t in tree["tasks"])


# ================================================================== 6. AgentAssignment (验收 D)


def _tree():
    return PIPE_MOD.TaskTree.from_engineering(_plan())


def test_assignment_frontend_flutter_dev():
    """D: frontend 任务 → flutter-dev (复用 select_agent 关键词规则)。"""
    exec_plan = PIPE_MOD.AgentAssignment.from_tasks(
        _tree(), select_agent_fn=ACTIONS_MOD.select_agent
    )
    frontend = [
        a for a in exec_plan["tasks"] if a["agent_type"] == "frontend"
    ]
    assert frontend, "应有 frontend 任务"
    assert all(a["agent"] == "flutter-dev" for a in frontend)


def test_assignment_backend_backend_1():
    exec_plan = PIPE_MOD.AgentAssignment.from_tasks(
        _tree(), select_agent_fn=ACTIONS_MOD.select_agent
    )
    backend = [a for a in exec_plan["tasks"] if a["agent_type"] == "backend"]
    assert backend
    assert all(a["agent"] == "backend-1" for a in backend)


def test_assignment_qa_backend_1_fallback():
    """qa 无专属 agent → backend-1 兜底。"""
    exec_plan = PIPE_MOD.AgentAssignment.from_tasks(
        _tree(), select_agent_fn=ACTIONS_MOD.select_agent
    )
    qa = [a for a in exec_plan["tasks"] if a["agent_type"] == "qa"]
    assert qa
    assert all(a["agent"] == "backend-1" for a in qa)


def test_assignment_all_tasks_assigned():
    exec_plan = PIPE_MOD.AgentAssignment.from_tasks(
        _tree(), select_agent_fn=ACTIONS_MOD.select_agent
    )
    assert exec_plan["count"] == 12
    assert len(exec_plan["tasks"]) == 12
    assert all(a["agent"] for a in exec_plan["tasks"])


def test_assignment_ids_preserved():
    tree = _tree()
    exec_plan = PIPE_MOD.AgentAssignment.from_tasks(
        tree, select_agent_fn=ACTIONS_MOD.select_agent
    )
    tree_ids = {t["id"] for t in tree["tasks"]}
    assert {a["id"] for a in exec_plan["tasks"]} == tree_ids


def test_assignment_custom_select_fn():
    exec_plan = PIPE_MOD.AgentAssignment.from_tasks(
        _tree(), select_agent_fn=lambda intent, context=None: "custom-agent"
    )
    assert all(a["agent"] == "custom-agent" for a in exec_plan["tasks"])


def test_assignment_select_fn_intent_only_signature():
    """select_agent_fn 只收 intent (单参签名) 也能工作 (TypeError 兜底)。"""
    exec_plan = PIPE_MOD.AgentAssignment.from_tasks(
        _tree(), select_agent_fn=lambda intent: "solo-agent"
    )
    assert all(a["agent"] == "solo-agent" for a in exec_plan["tasks"])


def test_assignment_default_select_lazy():
    """缺省 select_agent_fn → 惰性复用 actions.select_agent (无循环依赖)。"""
    exec_plan = PIPE_MOD.AgentAssignment.from_tasks(_tree())
    frontend = [a for a in exec_plan["tasks"] if a["agent_type"] == "frontend"]
    assert all(a["agent"] == "flutter-dev" for a in frontend)


# ================================================================== 7. Lifecycle (验收 E)


def test_lifecycle_statuses_order():
    assert PIPE_MOD.Lifecycle.STATUSES == (
        "idea", "product_defined", "engineering_ready", "execution_ready", "development", "testing", "validation_pass", "user_acceptance", "delivered",
    )

def test_lifecycle_next_status_chain():
    lc = PIPE_MOD.Lifecycle
    status = lc.IDEA
    expected = [
        lc.PRODUCT_DEFINED,
        lc.ENGINEERING_READY,
        lc.EXECUTION_READY,
        lc.DEVELOPMENT,
        lc.TESTING,
        lc.VALIDATION_PASS,
        lc.USER_ACCEPTANCE,
        lc.DELIVERED,
        None,
    ]
    for nxt in expected:
        assert lc.next_status(status) == nxt
        status = nxt if nxt is not None else status


def test_lifecycle_next_status_unknown_none():
    assert PIPE_MOD.Lifecycle.next_status("bogus") is None
    assert PIPE_MOD.Lifecycle.next_status(None) is None


def test_lifecycle_next_status_terminal_none():
    assert PIPE_MOD.Lifecycle.next_status(PIPE_MOD.Lifecycle.DELIVERED) is None


def test_lifecycle_execution_ready_value():
    assert PIPE_MOD.Lifecycle.EXECUTION_READY == "execution_ready"


def test_lifecycle_prepare_target_is_execution_ready():
    """工程准备目标状态 = EXECUTION_READY (验收 E 口径)。

    S10-111 M3-7 说明: 线性生命周期链不变 (engineering_ready → execution_ready);
    prepare_project 实际落盘前先进入 pending_arch_review 审批门 (独立于线性链,
    审批通过 → execution_ready), 见 test_prepare_project_project_json_status_pending_arch_review。
    """
    target = PIPE_MOD.Lifecycle.next_status(PIPE_MOD.Lifecycle.ENGINEERING_READY)
    assert target == PIPE_MOD.Lifecycle.EXECUTION_READY


# ================================================================== 8. generate_prd Action (P2)


def test_generate_prd_writes_prd_file(fake_org, tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    ctx, _ = _create_product_on_disk(root)
    result = ACTIONS_MOD.generate_prd(ctx)
    assert result.ok
    prd_path = root / "projects" / "scorepocket" / "PRD.md"
    assert prd_path.is_file()
    assert result.data["prd_file"] == str(prd_path)


def test_generate_prd_file_has_six_sections(fake_org, tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    ctx, _ = _create_product_on_disk(root)
    ACTIONS_MOD.generate_prd(ctx)
    content = (root / "projects" / "scorepocket" / "PRD.md").read_text(encoding="utf-8")
    for section in PIPE_MOD.ProductDocument.SECTIONS:
        assert f"## {section}" in content


def test_generate_prd_updates_product_status(fake_org, tmp_path):
    """S10-115 J-1: 无 canonical → product.status=engineering_ready (旧 prd_ready 的 Lifecycle 等价)。"""
    root = tmp_path / "ws"
    root.mkdir()
    ctx, _ = _create_product_on_disk(root)
    result = ACTIONS_MOD.generate_prd(ctx)
    assert result.data["status"] == "engineering_ready"
    data = json.loads(
        (root / "projects" / "scorepocket" / "product.json").read_text(encoding="utf-8")
    )
    assert data["status"] == "engineering_ready"
    assert data["name"] == "ScorePocket"


def test_generate_prd_no_product_error(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    result = ACTIONS_MOD.generate_prd(_exec_ctx(root))
    assert result.ok is False
    assert "未找到产品定义" in result.message
    assert not (root / "projects").exists() or not list((root / "projects").glob("*/PRD.md"))


def test_generate_prd_incomplete_product_error(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    ctx = _exec_ctx(root)
    ctx.session.product_intent = PROD_MOD.ProductIntent(name="X")
    result = ACTIONS_MOD.generate_prd(ctx)
    assert result.ok is False
    assert "产品信息不完整" in result.message


def test_generate_prd_registered_metadata():
    action = ACTIONS_MOD.build_default_actions().get("generate_prd")
    assert action is not None
    assert action.handler is ACTIONS_MOD.generate_prd
    assert action.metadata.get("sensitive") is False
    assert action.metadata.get("category") == "product"


def test_generate_prd_message_and_data(fake_org, tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    ctx, _ = _create_product_on_disk(root)
    result = ACTIONS_MOD.generate_prd(ctx)
    assert result.ok
    assert "PRD 已生成" in result.message
    # S10-111 M3-5 更新: PRD 8 节 (原 6 节 + User Stories/Acceptance Criteria)
    assert len(result.data["sections"]) == 8


def test_generate_prd_current_project_lookup(fake_org, tmp_path):
    """current_project 显式指向 → 从磁盘读 product.json (无会话 product_intent)。"""
    root = tmp_path / "ws"
    root.mkdir()
    ctx, _ = _create_product_on_disk(root)
    ctx2 = _exec_ctx(root)
    ctx2.session.current_project = "scorepocket"
    result = ACTIONS_MOD.generate_prd(ctx2)
    assert result.ok
    assert (root / "projects" / "scorepocket" / "PRD.md").is_file()


# ================================================================== 9. prepare_project Action (P3 / 验收 F+E)


def test_prepare_project_creates_four_assets(fake_org, tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    ctx, _ = _create_product_on_disk(root)
    result = ACTIONS_MOD.prepare_project(ctx)
    assert result.ok
    pdir = root / "projects" / "scorepocket"
    for name in ("PRD.md", "engineering.json", "tasks.json", "execution_plan.json"):
        assert (pdir / name).is_file(), f"缺少资产: {name}"


def test_prepare_project_message_ready(fake_org, tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    ctx, _ = _create_product_on_disk(root)
    result = ACTIONS_MOD.prepare_project(ctx)
    assert result.ok
    assert result.message == "Project Ready For Engineering."


def test_prepare_project_project_json_status_pending_arch_review(fake_org, tmp_path):
    """E + S10-111 M3-7: project.json status → pending_arch_review + arch_review 摘要。

    (原断言 execution_ready 已按新门控更新 — 审批通过后才 execution_ready,
    见 approve_project_plan; 生命周期线性链常量不变, test_lifecycle_* 仍绿)
    """
    root = tmp_path / "ws"
    root.mkdir()
    ctx, _ = _create_product_on_disk(root)
    ACTIONS_MOD.prepare_project(ctx)
    data = json.loads(
        (root / "projects" / "scorepocket" / "project.json").read_text(encoding="utf-8")
    )
    assert data["status"] == "pending_arch_review"
    assert "arch_review" in data
    assert "summary" in data["arch_review"]
    assert "requested_at" in data["arch_review"]


def test_prepare_project_engineering_json_content(fake_org, tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    ctx, _ = _create_product_on_disk(root)
    ACTIONS_MOD.prepare_project(ctx)
    data = json.loads(
        (root / "projects" / "scorepocket" / "engineering.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(data) >= {"architecture", "modules", "technical_tasks"}
    assert data["architecture"] == "Backend API + Frontend"  # platform 未指定 → 默认


def test_prepare_project_tasks_json_content(fake_org, tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    ctx, _ = _create_product_on_disk(root)
    ACTIONS_MOD.prepare_project(ctx)
    data = json.loads(
        (root / "projects" / "scorepocket" / "tasks.json").read_text(encoding="utf-8")
    )
    assert data["epics"] and data["tasks"]
    assert data["count"] == len(data["tasks"])
    assert all(t["priority"] in ("P0", "P1") for t in data["tasks"])


def test_prepare_project_execution_plan_json_content(fake_org, tmp_path):
    """D 落盘: execution_plan.json 中 frontend→flutter-dev / backend→backend-1。"""
    root = tmp_path / "ws"
    root.mkdir()
    ctx, _ = _create_product_on_disk(root)
    ACTIONS_MOD.prepare_project(ctx)
    data = json.loads(
        (root / "projects" / "scorepocket" / "execution_plan.json").read_text(
            encoding="utf-8"
        )
    )
    by_type = {a["agent_type"]: a["agent"] for a in data["tasks"]}
    assert by_type["frontend"] == "flutter-dev"
    assert by_type["backend"] == "backend-1"
    # S10-055: 功能级任务无 qa 专属类型; 验证 frontend/backend 即可
    assert "backend" in by_type and "frontend" in by_type


def test_prepare_project_no_product_error(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    result = ACTIONS_MOD.prepare_project(_exec_ctx(root))
    assert result.ok is False
    assert "未找到产品定义" in result.message


def test_prepare_project_incomplete_error(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    ctx = _exec_ctx(root)
    ctx.session.product_intent = PROD_MOD.ProductIntent(name="X")
    result = ACTIONS_MOD.prepare_project(ctx)
    assert result.ok is False
    assert "产品信息不完整" in result.message


def test_prepare_project_registered_sensitive():
    """G: prepare_project 注册 sensitive=True / category=product。"""
    action = ACTIONS_MOD.build_default_actions().get("prepare_project")
    assert action is not None
    assert action.handler is ACTIONS_MOD.prepare_project
    assert action.metadata.get("sensitive") is True
    assert action.metadata.get("category") == "product"


def test_prepare_project_preserves_existing_project_json_fields(fake_org, tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    ctx, _ = _create_product_on_disk(root)
    pdir = root / "projects" / "scorepocket"
    (pdir / "project.json").write_text(
        json.dumps({"id": "p1", "repo_path": "/tmp/repo"}), encoding="utf-8"
    )
    ACTIONS_MOD.prepare_project(ctx)
    data = json.loads((pdir / "project.json").read_text(encoding="utf-8"))
    assert data["id"] == "p1"  # org 字段保留
    assert data["repo_path"] == "/tmp/repo"
    # S10-111 M3-7 更新: prepare 后待架构审批 (原 execution_ready 断言更新)
    assert data["status"] == "pending_arch_review"
    assert data["arch_review"]["summary"]


def test_prepare_project_assets_paths_in_data(fake_org, tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    ctx, _ = _create_product_on_disk(root)
    result = ACTIONS_MOD.prepare_project(ctx)
    for key in ("prd_file", "engineering_file", "tasks_file", "execution_file"):
        assert key in result.data
        assert Path(result.data[key]).is_file()
    # S10-111 M3-7 更新: prepare 后待架构审批 (原 execution_ready 断言更新)
    assert result.data["status"] == "pending_arch_review"
    assert "arch_review" in result.data


def test_prepare_project_scan_fallback_lookup(fake_org, tmp_path):
    """无 product_intent / 无 current_project → 扫描 projects/*/product.json 兜底。"""
    root = tmp_path / "ws"
    root.mkdir()
    _create_product_on_disk(root)
    ctx = _exec_ctx(root)  # 空会话
    result = ACTIONS_MOD.prepare_project(ctx)
    assert result.ok
    assert (root / "projects" / "scorepocket" / "execution_plan.json").is_file()


# ================================================================== 10. Confirmation Flow (验收 G/H)


def test_gate_prepare_project_rejected(capsys):
    """G: prepare_project 敏感 → 拒绝 (n) → 不执行。"""
    gate = CONF_MOD.ConfirmationGate()
    gate.sensitive_actions = set(gate.sensitive_actions) | {"prepare_project"}
    intent = INTENT_MOD.IntentObject(intent_type="prepare_project", raw="准备开发")
    assert gate.confirm("prepare_project", intent, confirm_fn=lambda: "n") is False
    assert "将执行: prepare_project" in capsys.readouterr().out


def test_gate_prepare_project_approved(capsys):
    gate = CONF_MOD.ConfirmationGate()
    gate.sensitive_actions = set(gate.sensitive_actions) | {"prepare_project"}
    intent = INTENT_MOD.IntentObject(intent_type="prepare_project", raw="准备开发")
    assert gate.confirm("prepare_project", intent, confirm_fn=lambda: "y") is True


def test_session_default_gate_includes_prepare_project():
    """G: 默认装配会话的确认门将 prepare_project 纳入敏感集合 (仅实例, 不改类默认)。"""
    sess = SESS_MOD.InteractiveSession()
    assert isinstance(sess.confirmation_gate, CONF_MOD.ConfirmationGate)
    assert "prepare_project" in sess.confirmation_gate.sensitive_actions


def test_gate_class_default_untouched():
    """回归护栏: ConfirmationGate 类默认敏感集合保持基线 {create_project, run_task}。"""
    assert CONF_MOD.ConfirmationGate().sensitive_actions == {
        "create_project",
        "run_task",
        "delete_project",
    }


def test_session_dispatch_prepare_project_rejected(fake_org, capsys, tmp_path):
    """G 端到端: 拒绝 → "已取消", 不生成资产。"""
    root = tmp_path / "ws"
    root.mkdir()
    ctx, _ = _create_product_on_disk(root)
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
        confirmation_gate=_SpyGate(decision=False),
    )
    sess._dispatch("准备开发")
    out = capsys.readouterr().out
    assert "已取消" in out
    assert not (root / "projects" / "scorepocket" / "execution_plan.json").exists()


def test_session_dispatch_prepare_project_approved(fake_org, capsys, tmp_path):
    """G 端到端: 确认通过 → prepare_project 执行 → 4 资产 + Ready 消息。"""
    root = tmp_path / "ws"
    root.mkdir()
    ctx, _ = _create_product_on_disk(root)
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
        confirmation_gate=_SpyGate(decision=True),
    )
    sess._dispatch("准备开发")
    out = capsys.readouterr().out
    assert "Project Ready For Engineering." in out
    assert (root / "projects" / "scorepocket" / "execution_plan.json").is_file()


def test_session_gate_receives_prepare_project_intent(fake_org, capsys, tmp_path):
    """确认判定以 intent 类型为准: gate 收到 prepare_project。"""
    root = tmp_path / "ws"
    root.mkdir()
    _create_product_on_disk(root)
    spy = _SpyGate(decision=True)
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
        confirmation_gate=spy,
        # 确定性测试模式: 发现流程禁用 LLM (不依赖真实 LLM/网络)
        conversation_manager=CONV_MOD.ConversationManager(analyzer=None),
    )
    sess._dispatch("准备开发")
    assert len(spy.calls) == 1
    assert spy.calls[0][0] == "prepare_project"


def test_conversation_guide_after_product_created():
    """H: 产品创建成功后引导 \"是否生成工程计划?\"。"""
    mgr = _manager()
    mgr.start_product_discovery("我想开发一个台球计分APP")
    mgr.handle_product_answer("解决台球计分麻烦")
    mgr.handle_product_answer("台球爱好者")
    mgr.handle_product_answer("计分、比赛记录、排行榜")
    resp = mgr.handle_product_confirm(
        "y", confirm_fn=lambda pi: "Product Created: ScorePocket — Ready for Engineering."
    )
    assert resp.state == STATES.DONE
    assert "是否生成工程计划?" in resp.message
    assert "'准备开发'" in resp.message
    assert "'生成工程计划'" in resp.message
    assert "Ready for Engineering." in resp.message


def test_conversation_guide_default_message_when_fn_returns_none():
    """confirm_fn 返回 None → 默认消息 + 引导。"""
    mgr = _manager()
    mgr.start_product_discovery("x")
    mgr.handle_product_answer("p")
    mgr.handle_product_answer("u")
    mgr.handle_product_answer("f1、f2")
    resp = mgr.handle_product_confirm("y", confirm_fn=lambda pi: None)
    assert "Ready for Engineering." in resp.message
    assert "是否生成工程计划?" in resp.message


def test_conversation_cancel_no_guide():
    """取消 (n) 不出现工程计划引导。"""
    mgr = _manager()
    mgr.start_product_discovery("x")
    mgr.handle_product_answer("p")
    mgr.handle_product_answer("u")
    mgr.handle_product_answer("f1、f2")
    resp = mgr.handle_product_confirm("n")
    assert "是否生成工程计划?" not in resp.message
    assert resp.state == STATES.DISCOVERY


# ================================================================== 11. 完整 Pipeline Demo (验收 F)


def test_full_pipeline_create_then_prepare(fake_org, tmp_path):
    """F: create_product → prepare_project → 5 资产 + 状态链路 (tmp workspace 零污染)。"""
    root = tmp_path / "ws"
    root.mkdir()
    ctx, created = _create_product_on_disk(root)
    assert created.data["product_file"] == str(
        root / "projects" / "scorepocket" / "product.json"
    )
    result = ACTIONS_MOD.prepare_project(ctx)
    assert result.ok
    pdir = root / "projects" / "scorepocket"
    expected = [
        "PRD.md",  # 大写 P 排序在前
        "PRD.quality.json",  # S10-117 B-6: PRD 质量分落盘
        "artifacts.manifest.json",  # C-1/C-2: 产出物契约清单 (S10-125 引擎接线)
        "engineering.json",
        "engineering.quality.json",  # S10-117 B-6: 工程计划质量分落盘
        "execution_plan.json",
        "history",  # C-1/C-2: 产出物历史归档目录 (set_artifact 二次写归档)
        "product.json",
        "project.json",
        "tasks.json",
    ]
    assert sorted(p.name for p in pdir.iterdir()) == expected
    project = json.loads((pdir / "project.json").read_text(encoding="utf-8"))
    # S10-111 M3-7 更新: prepare 后待架构审批 (原 execution_ready 断言更新)
    assert project["status"] == "pending_arch_review"


def test_full_pipeline_generate_prd_then_prepare(fake_org, tmp_path):
    """generate_prd 先行 → prepare_project 复用 (幂等, 资产一致)。"""
    root = tmp_path / "ws"
    root.mkdir()
    ctx, _ = _create_product_on_disk(root)
    ACTIONS_MOD.generate_prd(ctx)
    result = ACTIONS_MOD.prepare_project(ctx)
    assert result.ok
    prd = (root / "projects" / "scorepocket" / "PRD.md").read_text(encoding="utf-8")
    assert "## Product Overview" in prd
    assert "## Future Direction" in prd


def test_full_session_flow_end_to_end(fake_org, capsys, tmp_path):
    """端到端: 产品发现 → 确认 → 引导 → \"准备开发\" → 确认门 → 全资产。"""
    root = tmp_path / "ws"
    root.mkdir()
    spy = _SpyGate(decision=True)
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
        confirmation_gate=spy,
        # 确定性测试模式: 发现流程禁用 LLM (不依赖真实 LLM/网络)
        conversation_manager=CONV_MOD.ConversationManager(analyzer=None),
    )
    sess._dispatch("我想开发一个台球计分APP")
    sess._dispatch("解决台球比赛计分麻烦")
    sess._dispatch("台球爱好者")
    sess._dispatch("计分、比赛记录、排行榜")
    sess._dispatch("y")
    sess._dispatch("准备开发")
    out = capsys.readouterr().out
    assert "产品定义完成 — 是否生成工程计划?" in out
    assert "Project Ready For Engineering." in out
    pdir = root / "projects" / "scorepocket"
    assert (pdir / "PRD.md").is_file()
    assert (pdir / "engineering.json").is_file()
    assert (pdir / "tasks.json").is_file()
    assert (pdir / "execution_plan.json").is_file()
    # S10-111 M3-7 更新: 会话 prepare 后待架构审批 (原 execution_ready 断言更新;
    # 审批见 approve_project_plan / test_s10_111_m3_finish M3-7)
    assert json.loads((pdir / "project.json").read_text(encoding="utf-8"))[
        "status"
    ] == "pending_arch_review"


def test_full_session_generate_prd_phrase_requires_context(fake_org, capsys, tmp_path):
    """修复 B: "生成PRD" 无当前项目/进行中产品 → 安全提示, 不猜项目 (扫描兜底禁用)。

    旧行为: 扫描兜底选中"最新 product.json" → 把 PRD 写进任意项目 (多项目环境
    数据污染, S10-10x 修复)。新行为: 无显式上下文 → 明确提示, 不写。
    """
    root = tmp_path / "ws"
    root.mkdir()
    _create_product_on_disk(root)  # 磁盘存在项目 — 但会话无 current_project
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(root)),
        confirmation_gate=_SpyGate(decision=True),
    )
    sess._dispatch("生成PRD")
    out = capsys.readouterr().out
    assert "未找到产品定义" in out  # 安全提示, 不猜项目
    assert not (root / "projects" / "scorepocket" / "PRD.md").exists()


# ================================================================== 12. 回归 (验收 K)


def test_regression_create_product_unchanged(fake_org, tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    ctx, result = _create_product_on_disk(root)
    assert result.message == "Product Created: ScorePocket — Ready for Engineering."
    assert fake_org.calls[0][1].name == "ScorePocket"


def test_regression_run_task_intent_unchanged():
    intent = INTENT_MOD.KeywordIntentParser().parse("帮我实现登录功能")
    assert intent.intent_type == INTENT_MOD.INTENT_RUN_TASK
    assert intent.parameters["objective"] == "登录功能"


def test_regression_product_intent_unchanged():
    intent = INTENT_MOD.KeywordIntentParser().parse("我想开发一个台球计分APP")
    assert intent.intent_type == INTENT_MOD.INTENT_CREATE_PRODUCT


def test_regression_show_status_unchanged():
    intent = INTENT_MOD.KeywordIntentParser().parse("看看状态")
    assert intent.intent_type == INTENT_MOD.INTENT_SHOW_STATUS
