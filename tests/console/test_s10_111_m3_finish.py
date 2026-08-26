"""tests/console/test_s10_111_m3_finish.py — M3 收尾三件套 (S10-111, v1.1.79)。

覆盖 (计划 §4 契约 1-12):
M3-5 (ux/qa 真引擎 + PRD 深度化):
  1. ux 资产无占位标记 + 每功能具体流程 (非 "进入 → 操作 → 完成/反馈" 通用句)
  2. qa 资产无占位标记 + 测试层级 (单元/集成/E2E/安全/性能) + 验证命令 + 每功能用例方向
  3. PRD 含 "User Stories" + "Acceptance Criteria" (手算对照: 功能数 = 故事数)
  4. 无 LLM (llm_fn=None) 确定性兜底仍产出以上 (验收 ④)
M3-6 (ChangeControl 需求变更回流):
  5. propose → ChangeProposal (request/reason 解析, 落盘)
  6. impact → 波及任务/PRD 章节可枚举 (手算对照) + 过度波及收敛
  7. approve y → PRD v2 + 新任务进 tasks.json + plan.json (+ execution_plan.json)
  8. approve n → 无变更 (PRD/任务/plan 原样), status=rejected; /project change + 自然语言入口
M3-7 (架构审批门):
  9. prepare_project → status=pending_arch_review + arch_review{summary, requested_at}
  10. approve → execution_ready; reject → 不 execution_ready + arch_review.feedback
  11. execute_project 在 pending_arch_review 时拒绝执行; 审批通过后正常执行 (与 v1.1.77 一致)
全局:
  12. 版本 v1.1.79 (pyproject + CHANGELOG + FEATURES.md + 待办清单 M3-5/6/7 ✅)

basename 全仓库唯一 (test_s10_111_* 前缀)。
"""

from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

ACT = importlib.import_module("factory-console.session.action")
ACTIONS = importlib.import_module("factory-console.session.actions")
ART = importlib.import_module("factory-console.session.artifact_registry")
CC = importlib.import_module("factory-console.session.change_control")
CMDS = importlib.import_module("factory-console.session.commands")
CTX = importlib.import_module("factory-console.session.context")
INT = importlib.import_module("factory-console.session.intent")
ORCH = importlib.import_module("factory-console.session.orchestrator")
PIPE = importlib.import_module("factory-console.session.pipeline")
PROD = importlib.import_module("factory-console.session.product")
RUNNER = importlib.import_module("factory-console.session.pipeline_runner")
SESS = importlib.import_module("factory-console.session.session")

REPO = _ROOT
PLACEHOLDER_MARKERS = ("规则占位", "进入 → 操作 → 完成/反馈")


# ------------------------------------------------------------------ 工具


def _product(**kw) -> PROD.ProductIntent:
    data = dict(
        name="ScorePocket",
        problem="台球比赛计分麻烦",
        user="台球爱好者",
        platform="mobile",
        core_features=["计分", "比赛记录", "排行榜"],
        raw="我想开发一个台球计分APP",
    )
    data.update(kw)
    return PROD.ProductIntent(**data)


def _ctx(root: Path, slug: str = "") -> ACT.ExecutionContext:
    """tmp workspace ExecutionContext (current_project 可选, 不依赖 org 注册)。"""
    sess = CTX.SessionContext(workspace=str(root))
    if slug:
        sess.current_project = slug
    return ACT.ExecutionContext(workspace=root, session=sess, user="user", project=slug or None)


def _make_project(
    root: Path,
    name: str = "CRM",
    features: list[str] | None = None,
    platform: str = "web",
    slug: str | None = None,
) -> tuple[ACT.ExecutionContext, str]:
    """直接落盘 product.json (绕过 org 注册 — 变更/审批测试聚焦内核)。"""
    slug = slug or (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "crm")
    pdir = root / "projects" / slug
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "product.json").write_text(
        json.dumps(
            {
                "name": name,
                "problem": "测试问题: 数据管理混乱",
                "user": "测试用户",
                "platform": platform,
                "core_features": features or ["客户跟进", "报表"],
                "status": "project_created",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return _ctx(root, slug), slug


def _register_org(root: Path, slug: str, name: str) -> None:
    """org/projects.json 注册 (自然语言 _match_project / /project 命令消费)。"""
    org = root / "org"
    org.mkdir(parents=True, exist_ok=True)
    path = org / "projects.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    projects = data.get("projects") if isinstance(data.get("projects"), dict) else {}
    projects[f"P-{slug}"] = {"name": name, "slug": slug}
    data["projects"] = projects
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _prepared(root: Path, name: str = "CRM", features=None, slug: str | None = None):
    """create 产品 + prepare_project → (ctx, slug) (状态 pending_arch_review)。"""
    ctx, slug = _make_project(root, name=name, features=features, slug=slug)
    result = ACTIONS.prepare_project(ctx)
    assert result.ok, result.message
    return ctx, slug


def _approve(ctx: ACT.ExecutionContext, slug: str, answer: str) -> ACT.ActionResult:
    """approve_project_plan (注入 confirm_fn 答案) — M3-7 审批。"""
    intent = INT.IntentObject(
        intent_type="approve_project_plan",
        params={},
        metadata={"confirm_fn": lambda: answer},
    )
    ctx2 = ACT.ExecutionContext(
        workspace=ctx.workspace, session=ctx.session, user=ctx.user,
        project=slug, intent=intent,
    )
    return ACTIONS.approve_project_plan(ctx2)


def _change(ctx: ACT.ExecutionContext, slug: str, request: str, answer: str):
    """change_project (注入 confirm_fn 答案) — M3-6 变更。"""
    intent = INT.IntentObject(
        intent_type="change_project",
        params={"project_id": slug, "request": request},
        metadata={"confirm_fn": lambda: answer},
    )
    ctx2 = ACT.ExecutionContext(
        workspace=ctx.workspace, session=ctx.session, user=ctx.user,
        project=slug, intent=intent,
    )
    return ACTIONS.change_project(ctx2)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact_text(root: Path, slug: str, atype: str) -> str:
    reg = ART.ArtifactRegistry(root, slug)
    record = reg.latest(atype)
    assert record is not None, f"无 {atype} 资产"
    return Path(record.content_ref).read_text(encoding="utf-8")


# ================================================================== M3-5: ux/qa 真引擎 + PRD 深度化


class TestM35UxQaRealEngine:
    """契约 1-4: ux/qa 无占位 + PRD 用户故事/验收标准 + 无 LLM 兜底。"""

    def test_ux_asset_no_placeholder_with_concrete_flows(self, tmp_path):
        """契约 1: ux 资产无占位标记; 每核心功能有具体 3-5 步流程 (非通用一句)。"""
        RUNNER.ProductPipeline(tmp_path, "todo").run(_product(), source="s10-111")
        ux = _artifact_text(tmp_path, "todo", "ux_flow")
        for marker in PLACEHOLDER_MARKERS:
            assert marker not in ux, f"ux 资产含占位标记: {marker}"
        # 每功能流程 (功能名推导, 具体步骤链)
        for feature in ("计分", "比赛记录", "排行榜"):
            assert f"进入{feature}页" in ux, f"缺少 {feature} 流程"
            assert "执行" in ux and "反馈" in ux
        # 页面结构: 首页/功能页/个人中心/设置
        for page in ("首页", "个人中心", "设置", "计分页"):
            assert page in ux
        # 信息架构含用户角色
        assert "台球爱好者" in ux

    def test_qa_asset_no_placeholder_with_levels_and_commands(self, tmp_path):
        """契约 2: qa 资产无占位标记; 五层测试 + 验证命令 + 每功能用例方向。"""
        RUNNER.ProductPipeline(tmp_path, "todo").run(_product(), source="s10-111")
        qa = _artifact_text(tmp_path, "todo", "test_plan")
        assert "规则占位" not in qa
        for layer in ("单元测试", "集成测试", "E2E 测试", "安全测试", "性能测试"):
            assert layer in qa, f"缺测试层级: {layer}"
        assert "验证命令" in qa and "pytest" in qa
        for feature in ("计分", "比赛记录", "排行榜"):
            assert f"{feature} 核心逻辑单元用例" in qa
            assert f"{feature} 端到端用户路径用例" in qa

    def test_prd_has_user_stories_and_acceptance_criteria(self):
        """契约 3: PRD 含 User Stories + Acceptance Criteria; 功能数 = 故事数 (手算)。"""
        product = _product()
        prd = PIPE.ProductDocument.from_product_intent(product)
        assert "## User Stories" in prd
        assert "## Acceptance Criteria" in prd
        features = product.core_features
        # 手算对照: 每功能一条故事, 每条含 作为/我想要/以便
        for feature in features:
            assert f"- 作为 {product.user}, 我想要 {feature}, 以便" in prd, feature
        story_lines = [
            ln for ln in prd.splitlines()
            if ln.startswith("- 作为 ") and "我想要" in ln
        ]
        assert len(story_lines) == len(features)
        # 每功能验收标准 ≥2 条 (given/when/then 或清单)
        for feature in features:
            assert f"- **{feature}**:" in prd
            assert "给定用户已进入" in prd and "系统完成" in prd

    def test_deterministic_fallback_without_llm(self, tmp_path):
        """契约 4: 无 LLM (llm_fn=None) 确定性兜底仍产出合理资产 (验收 ④)。"""
        pipeline = RUNNER.ProductPipeline(tmp_path, "todo")  # llm_fn=None
        result = pipeline.run(_product(), source="s10-111")
        assert len(result.records) == 7
        for rtype in ("ux_flow", "test_plan", "prd"):
            text = _artifact_text(tmp_path, "todo", rtype)
            assert text.strip(), f"{rtype} 兜底为空"
            if rtype != "prd":
                assert "规则占位" not in text
        # PRD 确定性: 同输入同输出
        p1 = PIPE.ProductDocument.from_product_intent(_product())
        p2 = PIPE.ProductDocument.from_product_intent(_product())
        assert p1 == p2
        assert p1.count("## User Stories") == 1


# ================================================================== M3-6: ChangeControl 需求变更回流


class TestM36ChangeControl:
    """契约 5-8: propose/impact/apply(y/n) + /project change + 自然语言入口。"""

    def test_propose_parses_request_and_reason(self, tmp_path):
        """契约 5: propose → ChangeProposal (request/reason 解析) + change_control.json 落盘。"""
        root = tmp_path / "ws"
        root.mkdir()
        _prepared(root)
        controller = CC.ChangeController(root)
        proposal = controller.propose("crm", "加导出功能")
        assert proposal.id.startswith("chg-crm-")
        assert proposal.project_slug == "crm"
        assert proposal.request == "导出"  # 确定性: 去 "加/功能"
        assert proposal.reason == "新增需求"
        assert proposal.status == CC.STATUS_PROPOSED
        data = _read_json(root / "projects" / "crm" / "change_control.json")
        assert data["count"] == 1
        assert data["proposals"][0]["request"] == "导出"

    def test_impact_hand_computable_and_converged(self, tmp_path):
        """契约 6: impact 波及任务/PRD 章节可枚举 (手算对照) + 过度波及收敛。"""
        root = tmp_path / "ws"
        root.mkdir()
        _prepared(root)  # 客户跟进/报表 → task-e1-manage/task-e2-manage 含 "数据管理"
        controller = CC.ChangeController(root)
        proposal = controller.propose("crm", "加数据统计")
        impact = controller.impact(proposal)
        # 手算: "数据统计" 关键词 ["数据统计","数据","据统","统计"] →
        #   tasks.json 中 "客户跟进 数据管理" / "报表 数据管理" (task-e1-manage/e2-manage)
        assert any("task-e1-manage" in t for t in impact.affected_tasks)
        assert any("task-e2-manage" in t for t in impact.affected_tasks)
        # PRD 章节: Future Direction 含 "数据洞察" → 波及
        assert "Future Direction" in impact.affected_prd_sections
        # 过度波及收敛: 6 功能全部含 "数据管理" → 命中 > MAX_AFFECTED → 收敛 ≤5 + note
        root2 = tmp_path / "ws2"
        root2.mkdir()
        _prepared(
            root2,
            name="数据平台",
            slug="data-platform",
            features=["数据备份", "数据恢复", "数据同步", "数据统计", "数据看板", "数据导出"],
        )
        controller2 = CC.ChangeController(root2)
        p2 = controller2.propose("data-platform", "加数据")
        impact2 = controller2.impact(p2)
        assert len(impact2.affected_tasks) <= CC.MAX_AFFECTED
        assert "收敛" in impact2.note

    def test_apply_approved_updates_prd_tasks_plan(self, tmp_path):
        """契约 7: y → PRD v2 (变更记录) + 新任务进 tasks.json + plan.json + execution_plan.json。"""
        root = tmp_path / "ws"
        root.mkdir()
        ctx, slug = _prepared(root)
        prd_path = root / "projects" / slug / "PRD.md"
        tasks_before = _read_json(root / "projects" / slug / "tasks.json")["count"]
        result = _change(ctx, slug, "加导出功能", "y")
        assert result.ok, result.message
        assert result.data["apply"]["applied"] is True
        assert result.data["apply"]["prd_version"] == 2
        assert result.data["status"] == CC.STATUS_APPROVED
        # PRD v2: 文件尾含 "# 变更记录 v2: 导出" + 变更日志
        prd = prd_path.read_text(encoding="utf-8")
        assert "# 变更记录 v2: 导出" in prd
        assert "## 变更日志" in prd and "状态: 已批准 (v2)" in prd
        # tasks.json: 新任务 (feature == "导出")
        tasks = _read_json(root / "projects" / slug / "tasks.json")
        new_tasks = [t for t in tasks["tasks"] if t["feature"] == "导出"]
        assert new_tasks, "无新任务进 tasks.json"
        assert tasks["count"] == tasks_before + len(new_tasks)
        # plan.json: 含新任务 id (动态 DAG 已有 — 追加)
        plan = _read_json(root / "projects" / slug / "plan.json")
        new_ids = {t["id"] for t in new_tasks}
        plan_ids = {t["id"] for t in plan["tasks"]}
        assert new_ids <= plan_ids, "plan.json 未含新任务"
        # execution_plan.json (solo 执行路径) 同步生效
        exec_plan = _read_json(root / "projects" / slug / "execution_plan.json")
        assert new_ids <= {t["id"] for t in exec_plan["tasks"]}
        # 提案状态 approved
        cc_data = _read_json(root / "projects" / slug / "change_control.json")
        assert cc_data["proposals"][0]["status"] == CC.STATUS_APPROVED

    def test_apply_rejected_no_changes(self, tmp_path):
        """契约 8a: n → 不写不建, status=rejected, PRD/任务/plan 原样。"""
        root = tmp_path / "ws"
        root.mkdir()
        ctx, slug = _prepared(root)
        prd_before = (root / "projects" / slug / "PRD.md").read_text(encoding="utf-8")
        tasks_before = _read_json(root / "projects" / slug / "tasks.json")
        result = _change(ctx, slug, "加数据统计", "n")
        assert result.status == ACT.STATUS_CANCELLED
        assert result.message == "已拒绝, 未变更"
        assert result.data["apply"]["applied"] is False
        assert result.data["apply"]["status"] == CC.STATUS_REJECTED
        # PRD 无变更记录; tasks/plan 原样
        assert "# 变更记录 v2" not in (root / "projects" / slug / "PRD.md").read_text(encoding="utf-8")
        assert _read_json(root / "projects" / slug / "tasks.json") == tasks_before
        assert not (root / "projects" / slug / "plan.json").exists()
        cc_data = _read_json(root / "projects" / slug / "change_control.json")
        assert cc_data["proposals"][0]["status"] == CC.STATUS_REJECTED

    def test_slash_command_entry(self, tmp_path):
        """契约 8b: /project change <slug> "加导出" → 变更回流真实生效。"""
        root = tmp_path / "ws"
        root.mkdir()
        ctx, slug = _prepared(root)
        _register_org(root, slug, "CRM")
        cmd = CMDS.ProjectCommand(projects_file=root / "org" / "projects.json", workspace=root)
        # pytest 无 stdin → 内部确认门 EOF 放行 (= 批准), 变更真实落盘
        rc = cmd.execute(f'change {slug} "加导出"', ctx.session)
        assert rc == 0
        assert "# 变更记录 v2: 导出" in (root / "projects" / slug / "PRD.md").read_text(encoding="utf-8")

    def test_nl_intent_and_session_entry(self, tmp_path, capsys):
        """契约 8c: 自然语言 "给XX项目加个导出功能" → intent 规则 + 会话分发生效。"""
        parser = INT.KeywordIntentParser()
        intent = parser.parse("给XX项目加个导出功能")
        assert intent is not None
        assert intent.intent_type == INT.INTENT_CHANGE_PROJECT
        assert intent.parameters.get("request") == "导出功能"
        # 不抢既有 run_task: "加测试" 仍归 run_task
        assert parser.parse("加测试").intent_type == INT.INTENT_RUN_TASK
        # 会话分发: 项目已注册 + 已 prepare → NL 变更生效 (EOF 自动批准)
        root = tmp_path / "ws"
        root.mkdir()
        ctx, slug = _prepared(root, name="CRM")
        _register_org(root, slug, "CRM")
        sess = SESS.InteractiveSession(context_manager=CTX.ContextManager(workspace=str(root)))
        sess.context_manager.update(current_project=slug)
        sess._dispatch("给CRM项目加个导出功能")
        out = capsys.readouterr().out
        assert "变更已批准并落地" in out
        assert "# 变更记录 v2: 导出" in (root / "projects" / slug / "PRD.md").read_text(encoding="utf-8")


# ================================================================== M3-7: 架构审批门


class TestM37ArchReviewGate:
    """契约 9-11: prepare → pending_arch_review → approve/reject → execute 门控。"""

    def test_prepare_project_pending_arch_review(self, tmp_path):
        """契约 9: prepare_project → status=pending_arch_review + arch_review 摘要。"""
        root = tmp_path / "ws"
        root.mkdir()
        ctx, slug = _prepared(root)
        project = _read_json(root / "projects" / slug / "project.json")
        assert project["status"] == "pending_arch_review"
        assert "arch_review" in project
        summary = project["arch_review"]
        assert "架构选型" in summary["summary"]
        assert "任务数" in summary["summary"]
        assert summary["requested_at"]
        # 审批前 product.json 同步待审 (与 project.json 口径一致)
        assert _read_json(root / "projects" / slug / "product.json")["status"] == "pending_arch_review"

    def test_approve_sets_execution_ready(self, tmp_path):
        """契约 10a: 审批 y → execution_ready (进入拆解/执行)。"""
        root = tmp_path / "ws"
        root.mkdir()
        ctx, slug = _prepared(root)
        result = _approve(ctx, slug, "y")
        assert result.ok
        assert result.data["status"] == "execution_ready"
        project = _read_json(root / "projects" / slug / "project.json")
        assert project["status"] == "execution_ready"
        assert project["arch_review"]["decision"] == "approved"
        assert project["arch_review"]["feedback"] is None
        # 重复审批 → 明确拒绝 (已是 execution_ready)
        again = _approve(ctx, slug, "y")
        assert again.ok is False
        assert "已审批通过" in again.message

    def test_reject_keeps_pending_with_feedback(self, tmp_path):
        """契约 10b: 审批 n → 不 execution_ready + arch_review.feedback 记录。"""
        root = tmp_path / "ws"
        root.mkdir()
        ctx, slug = _prepared(root)
        result = _approve(ctx, slug, "n")
        assert result.status == ACT.STATUS_CANCELLED
        assert result.data["status"] == "pending_arch_review"
        project = _read_json(root / "projects" / slug / "project.json")
        assert project["status"] == "pending_arch_review"
        assert project["arch_review"]["decision"] == "rejected"
        assert "已拒绝" in project["arch_review"]["feedback"]
        # 计划修订: 重新 prepare_project 覆盖 arch_review (新摘要, 无旧 feedback)
        ACTIONS.prepare_project(ctx)
        project2 = _read_json(root / "projects" / slug / "project.json")
        assert project2["status"] == "pending_arch_review"
        assert "feedback" not in project2["arch_review"] or project2["arch_review"].get("feedback") is None

    def test_execute_blocked_before_approval(self, tmp_path):
        """契约 11a: execute_project 在 pending_arch_review 时拒绝执行 (明确错误)。"""
        root = tmp_path / "ws"
        root.mkdir()
        ctx, slug = _prepared(root)
        # orchestrator 直调 → ExecutionStateError "工程计划待架构审批"
        orch = ORCH.ExecutionOrchestrator(root)
        with pytest.raises(ORCH.ExecutionStateError, match="工程计划待架构审批"):
            orch.execute_project(slug)
        # action 层 → 明确错误 (M3-7 文案, 非泛化状态错误)
        result = ACTIONS.execute_project(ctx)
        assert result.ok is False
        assert "工程计划待架构审批" in result.error

    def test_execute_after_approval_matches_v1_1_77(self, tmp_path):
        """契约 11b: 审批通过后 execute_project 正常执行 (与 v1.1.77 一致)。"""
        root = tmp_path / "ws"
        root.mkdir()
        ctx, slug = _prepared(root, features=["计分"])
        _approve(ctx, slug, "y")

        def ok_fn(task, project_dir, workspace):
            return {"success": True, "artifact": f"/tmp/{task.get('id')}.patch"}

        orch = ORCH.ExecutionOrchestrator(root)
        result = orch.execute_project(slug, execute_fn=ok_fn)
        assert result.failed_tasks == 0
        assert result.completed_tasks >= 1
        project = _read_json(root / "projects" / slug / "project.json")
        assert project["status"] in ("user_acceptance", "delivered")


# ================================================================== 全局: 版本 v1.1.79 + 文档


class TestGlobalVersionDocs:
    """契约 12: 版本 v1.1.79 + CHANGELOG + FEATURES.md + 待办清单 M3-5/6/7 ✅。"""

    def test_pyproject_version_1_1_78(self):
        pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
        assert re.search(r'^version\s*=\s*"1\.1\.103"', pyproject, re.M), "pyproject 版本非 1.1.103"

    def test_changelog_has_v1_1_78_entry(self):
        changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
        assert "## [v1.1.103]" in changelog
        assert "M3-5" in changelog or "UX/QA" in changelog or "ux/qa" in changelog
        assert "M3-6" in changelog or "ChangeControl" in changelog or "变更回流" in changelog
        assert "M3-7" in changelog or "审批门" in changelog

    def test_features_md_header_and_m3_rows(self):
        features = (REPO / "docs" / "FEATURES.md").read_text(encoding="utf-8")
        # 头版本行 (版本: **v1.1.79**)
        header = next(
            (ln for ln in features.splitlines() if ln.startswith("> 版本:")),
            "",
        )
        assert "v1.1.103" in header, f"FEATURES 头版本未更新: {header}"
        # 版本对照表含 v1.1.79 行
        assert "| v1.1.103 |" in features
        # M3-5/6/7 已知缺口行 🚧 → ✅
        row = next(
            (ln for ln in features.splitlines() if "M3-5/6/7" in ln),
            "",
        )
        assert "✅" in row, "M3-5/6/7 行未标 ✅"

    def test_todo_list_m3_rows_marked(self):
        todo = (REPO / "docs" / "sprint10" / "待办清单-已发现未落地.md").read_text(encoding="utf-8")
        for num in ("M3-5", "M3-6", "M3-7"):
            row = next((ln for ln in todo.splitlines() if ln.startswith("| " + num)), "")
            assert row.startswith("| " + num + " | ✅"), f"{num} 未标 ✅: {row}"
