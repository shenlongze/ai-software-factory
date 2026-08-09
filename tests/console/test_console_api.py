"""tests/console/test_console_api.py — 路由函数审计 (Phase 11A, ADR-0034 + S9-002)。

覆盖 (factory-console/api/):
- 路由函数模块 (projects/lifecycle/approvals/decisions/intelligence/
  providers/workflows/artifacts — S9-002 扩展 3 模块) 全部导出 + VIEW 常量
- 每个路由函数: 只读投影返回 (响应模型/None) — 纯函数, 无 Web 依赖
- 审计集成: 有 EventLogger → 发 console.viewed (payload view/count/
  project_id/extra; ADR-0002 读审计同语义)
- logger=None → 无审计事件, 返回不受影响
- 只读铁律: 查询路由函数不携带任何执行/审批指令 (返回模型即只读投影);
  S9-002 扩展决定路由 (approve/reject — 用户解除 Console 冻结) 走 org
  Approval 状态机, 错误语义由 HTTP 层映射 (404/409)

basename 全仓库唯一 (test_console_* 前缀)。
"""

from __future__ import annotations

from types import SimpleNamespace

from events.models import EventType
from events.store import EventStore

from console_helpers import payload_of

_console = __import__("importlib").import_module("factory-console")
_api = __import__("importlib").import_module("factory-console.api")
_models = __import__("importlib").import_module("factory-console.models")

ProjectSummary = _models.ProjectSummary
LifecycleSummary = _models.LifecycleSummary
ApprovalSummary = _models.ApprovalSummary
DecisionSummary = _models.DecisionSummary
RecommendationSummary = _models.RecommendationSummary
ExperienceSummary = _models.ExperienceSummary
ProviderSummary = _models.ProviderSummary
# S9-002 org 投影模型
ApprovalGateSummary = _models.ApprovalGateSummary
ApprovalDecisionSummary = _models.ApprovalDecisionSummary
ArtifactSummary = _models.ArtifactSummary
WorkflowSummary = _models.WorkflowSummary
WorkflowDetail = _models.WorkflowDetail


class _StubService:
    """路由函数消费的最小接口桩 (返回固定投影, 审计逻辑与真实 service 解耦)。

    S9-002: 新增 org 聚合接口 (list_workflows/get_workflow/list_artifacts/
    list_approval_gates) + 审批决定接口 (approve_approval/reject_approval)。
    """

    def list_projects(self):
        return [ProjectSummary(id="demo"), ProjectSummary(id="other", status="archived")]

    def project_lifecycle(self, project_id):
        return LifecycleSummary(project_id=project_id, status="running")

    def list_approvals(self):
        return [
            ApprovalSummary(id="req-1", artifact_id="art-1", status="pending"),
            ApprovalSummary(id="req-2", artifact_id="art-2", status="approved"),
        ]

    def list_approval_gates(self, *, status=None, workflow_id=None):
        return [ApprovalGateSummary(id="AG-1", stage_id="STG-1", workflow_id="WF-1", status="pending")]

    def get_decision(self, decision_id):
        return DecisionSummary(id=decision_id, recommendation="a", score=0.9)

    def list_recommendations(self, limit=10):
        return [RecommendationSummary(id="rec-1", score=0.92)]

    def list_experience(self, limit=10):
        return [ExperienceSummary(id="exp-1", score=0.8)]

    def list_providers(self):
        return [ProviderSummary(id="hermes")]

    def list_workflows(self, *, project_id=None):
        return [
            WorkflowSummary(
                id="WF-1", project_id="demo", name="Demo Chain", status="active",
                stage_count=8, completed_count=4, progress=0.5,
            )
        ]

    def get_workflow(self, workflow_id):
        if workflow_id != "WF-1":
            return None
        return WorkflowDetail(
            id="WF-1", project_id="demo", name="Demo Chain", status="active",
            template=list(service_template),
        )

    def list_artifacts(self, *, project_id=None, workflow_id=None, type=None):
        return [ArtifactSummary(id="A-1", stage_id="STG-1", workflow_id="WF-1", project_id="demo", type="prd")]

    def approve_approval(self, approval_id, *, reviewer="", comment=""):
        if approval_id != "AG-1":
            return None  # 门不存在 → None (路由层 404 语义)
        gate = ApprovalGateSummary(id="AG-1", stage_id="STG-1", workflow_id="WF-1", status="approved")
        return ApprovalDecisionSummary(action="approve", gate=gate, workflow_id="WF-1", workflow_status="active")

    def reject_approval(self, approval_id, *, reviewer="", comment=""):
        if approval_id != "AG-1":
            return None  # 门不存在 → None (路由层 404 语义)
        gate = ApprovalGateSummary(id="AG-1", stage_id="STG-1", workflow_id="WF-1", status="rejected")
        return ApprovalDecisionSummary(action="reject", gate=gate, workflow_id="WF-1", workflow_status="failed")


#: 规范 8 阶段链 (同 factory-console/service.py WORKFLOW_TEMPLATE 同源)
service_template = ("Idea", "PM", "Product", "UX/UI", "Architecture", "Development", "Test", "Release")


# ------------------------------------------------------------------ 路由导出


class TestRouteExports:
    def test_route_modules_exported(self):
        """api/ 暴露全部路由函数 (S9-002: 13 个 — 新增 workflows/artifacts/
        approval-gates + approve/reject 决定)。"""
        expected = {
            "approve_approval",
            "get_decision",
            "get_project_lifecycle",
            "get_workflow",
            "list_approval_gates",
            "list_approvals",
            "list_artifacts",
            "list_experience",
            "list_projects",
            "list_providers",
            "list_recommendations",
            "list_workflows",
            "reject_approval",
        }
        assert set(_api.__all__) == expected
        for name in expected:
            assert callable(getattr(_api, name))

    def test_view_constants(self):
        """每个路由模块有 VIEW 常量 (事件 payload view 名, 11B FastAPI 同用)。"""
        assert _api.projects.VIEW == "projects"
        assert _api.lifecycle.VIEW == "lifecycle"
        assert _api.approvals.VIEW == "approvals"
        assert _api.decisions.VIEW == "decisions"
        assert _api.intelligence.VIEW_RECOMMENDATIONS == "recommendations"
        assert _api.intelligence.VIEW_EXPERIENCE == "experience"
        assert _api.providers.VIEW == "providers"
        # S9-002: org 视图
        assert _api.workflows.VIEW == "workflows"
        assert _api.artifacts.VIEW == "artifacts"


# ------------------------------------------------------------------ 各路由只读投影


class TestProjectsRoute:
    def test_returns_project_summaries(self):
        out = _api.list_projects(_StubService())
        assert len(out) == 2
        assert all(isinstance(p, ProjectSummary) for p in out)
        assert [p.id for p in out] == ["demo", "other"]

    def test_audit_viewed_event(self, event_logger, event_store):
        _api.list_projects(_StubService(), logger=event_logger)
        payload = payload_of(event_store, "console.viewed")
        assert payload["view"] == "projects"
        assert payload["count"] == 2
        assert payload["projects"] == ["demo", "other"]

    def test_no_logger_no_event(self, event_store):
        _api.list_projects(_StubService())
        assert event_store.query() == []


class TestLifecycleRoute:
    def test_returns_lifecycle_summary(self):
        out = _api.get_project_lifecycle(_StubService(), "demo")
        assert isinstance(out, LifecycleSummary)
        assert out.project_id == "demo"
        assert out.status == "running"

    def test_audit_includes_project_id(self, event_logger, event_store):
        _api.get_project_lifecycle(_StubService(), "demo", logger=event_logger)
        payload = payload_of(event_store, "console.viewed")
        assert payload["view"] == "lifecycle"
        assert payload["count"] == 1
        assert payload["project_id"] == "demo"
        assert payload["lifecycle_status"] == "running"


class TestApprovalsRoute:
    def test_returns_approval_summaries(self):
        out = _api.list_approvals(_StubService())
        assert len(out) == 2
        assert all(isinstance(a, ApprovalSummary) for a in out)

    def test_pending_only_filters(self):
        out = _api.list_approvals(_StubService(), pending_only=True)
        assert [a.id for a in out] == ["req-1"]

    def test_audit_pending_counts(self, event_logger, event_store):
        _api.list_approvals(_StubService(), logger=event_logger, pending_only=True)
        payload = payload_of(event_store, "console.viewed")
        assert payload["view"] == "approvals"
        assert payload["count"] == 1
        assert payload["pending"] == 1
        assert payload["pending_only"] is True


class TestDecisionRoute:
    def test_returns_decision_summary(self):
        out = _api.get_decision(_StubService(), "dec-1")
        assert isinstance(out, DecisionSummary)
        assert out.id == "dec-1"

    def test_missing_decision_none_and_count_zero(self, event_logger, event_store):
        stub = SimpleNamespace(get_decision=lambda _id: None)
        out = _api.get_decision(stub, "nope", logger=event_logger)
        assert out is None
        payload = payload_of(event_store, "console.viewed")
        assert payload["view"] == "decisions"
        assert payload["count"] == 0
        assert payload["decision_id"] == "nope"


class TestRecommendationsRoute:
    def test_returns_recommendation_summaries(self):
        out = _api.list_recommendations(_StubService(), limit=5)
        assert len(out) == 1
        assert isinstance(out[0], RecommendationSummary)

    def test_audit_records_limit(self, event_logger, event_store):
        _api.list_recommendations(_StubService(), logger=event_logger, limit=5)
        payload = payload_of(event_store, "console.viewed")
        assert payload["view"] == "recommendations"
        assert payload["count"] == 1
        assert payload["limit"] == 5


class TestExperienceRoute:
    def test_returns_experience_summaries(self):
        out = _api.list_experience(_StubService())
        assert len(out) == 1
        assert isinstance(out[0], ExperienceSummary)

    def test_audit_view_experience(self, event_logger, event_store):
        _api.list_experience(_StubService(), logger=event_logger)
        assert payload_of(event_store, "console.viewed")["view"] == "experience"


class TestProvidersRoute:
    def test_returns_provider_summaries(self):
        out = _api.list_providers(_StubService())
        assert len(out) == 1
        assert isinstance(out[0], ProviderSummary)
        assert out[0].id == "hermes"

    def test_audit_provider_ids(self, event_logger, event_store):
        _api.list_providers(_StubService(), logger=event_logger)
        payload = payload_of(event_store, "console.viewed")
        assert payload["view"] == "providers"
        assert payload["providers"] == ["hermes"]


# ------------------------------------------------------------------ S9-002 org 路由 (审计)


class TestWorkflowRoutes:
    def test_list_workflows_returns_summaries(self):
        out = _api.list_workflows(_StubService())
        assert len(out) == 1
        assert isinstance(out[0], WorkflowSummary)
        assert out[0].id == "WF-1"
        assert out[0].progress == 0.5

    def test_list_workflows_passes_project_filter(self):
        calls: list[dict[str, str | None]] = []

        class _FilterStub:
            def list_workflows(self, *, project_id=None):
                calls.append({"project_id": project_id})
                return []

        _api.list_workflows(_FilterStub(), project_id="demo")
        assert calls == [{"project_id": "demo"}]

    def test_list_workflows_audit(self, event_logger, event_store):
        _api.list_workflows(_StubService(), logger=event_logger)
        payload = payload_of(event_store, "console.viewed")
        assert payload["view"] == "workflows"
        assert payload["count"] == 1
        assert payload["workflows"] == ["WF-1"]

    def test_get_workflow_returns_detail(self):
        out = _api.get_workflow(_StubService(), "WF-1")
        assert isinstance(out, WorkflowDetail)
        assert out.id == "WF-1"
        assert out.template == list(service_template)

    def test_get_workflow_missing_none(self, event_logger, event_store):
        out = _api.get_workflow(_StubService(), "nope", logger=event_logger)
        assert out is None
        payload = payload_of(event_store, "console.viewed")
        assert payload["view"] == "workflow_detail"
        assert payload["count"] == 0
        assert payload["workflow_id"] == "nope"


class TestArtifactRoutes:
    def test_list_artifacts_returns_summaries(self):
        out = _api.list_artifacts(_StubService())
        assert len(out) == 1
        assert isinstance(out[0], ArtifactSummary)
        assert out[0].type == "prd"

    def test_list_artifacts_passes_filters(self):
        calls: list[dict[str, str | None]] = []

        class _FilterStub:
            def list_artifacts(self, *, project_id=None, workflow_id=None, type=None):
                calls.append({"project_id": project_id, "workflow_id": workflow_id, "type": type})
                return []

        _api.list_artifacts(_FilterStub(), project_id="demo", workflow_id="WF-1", type="prd")
        assert calls == [{"project_id": "demo", "workflow_id": "WF-1", "type": "prd"}]

    def test_list_artifacts_audit(self, event_logger, event_store):
        _api.list_artifacts(_StubService(), logger=event_logger)
        payload = payload_of(event_store, "console.viewed")
        assert payload["view"] == "artifacts"
        assert payload["count"] == 1
        assert payload["type"] is None


class TestApprovalGateRoutes:
    def test_list_approval_gates_returns_gates(self):
        out = _api.list_approval_gates(_StubService())
        assert len(out) == 1
        assert isinstance(out[0], ApprovalGateSummary)
        assert out[0].status == "pending"

    def test_list_approval_gates_audit(self, event_logger, event_store):
        _api.list_approval_gates(_StubService(), logger=event_logger, status="pending")
        payload = payload_of(event_store, "console.viewed")
        assert payload["view"] == "approval_gates"
        assert payload["count"] == 1
        assert payload["pending"] == 1
        assert payload["status"] == "pending"


class TestApprovalDecisionRoutes:
    def test_approve_returns_decision_projection(self):
        out = _api.approve_approval(_StubService(), "AG-1", reviewer="console")
        assert isinstance(out, ApprovalDecisionSummary)
        assert out.action == "approve"
        assert out.gate.status == "approved"
        assert out.workflow_status == "active"

    def test_reject_returns_decision_projection(self):
        out = _api.reject_approval(_StubService(), "AG-1", reviewer="console", comment="重做")
        assert isinstance(out, ApprovalDecisionSummary)
        assert out.action == "reject"
        assert out.gate.status == "rejected"
        assert out.workflow_status == "failed"

    def test_missing_gate_returns_none(self):
        assert _api.approve_approval(_StubService(), "nope") is None
        assert _api.reject_approval(_StubService(), "nope") is None

    def test_reviewer_comment_forwarded(self):
        seen: dict[str, str] = {}

        class _DecideStub:
            def approve_approval(self, approval_id, *, reviewer="", comment=""):
                seen.update({"reviewer": reviewer, "comment": comment})
                return ApprovalDecisionSummary(
                    action="approve",
                    gate=ApprovalGateSummary(id=approval_id, status="approved"),
                )

        _api.approve_approval(_DecideStub(), "AG-1", reviewer="console", comment="OK")
        assert seen == {"reviewer": "console", "comment": "OK"}


# ------------------------------------------------------------------ 只读铁律 (路由层)


class TestReadOnlyIronRule:
    def test_routes_only_return_projection_models(self):
        """查询路由函数返回值全部是只读投影模型 (无写路径/无执行指令)。"""
        stub = _StubService()
        for fn, args in [
            (_api.list_projects, ()),
            (_api.list_approvals, ()),
            (_api.list_recommendations, ()),
            (_api.list_experience, ()),
            (_api.list_providers, ()),
            # S9-002: org 查询
            (_api.list_workflows, ()),
            (_api.list_artifacts, ()),
            (_api.list_approval_gates, ()),
        ]:
            for item in fn(stub, *args):
                assert hasattr(item, "to_dict"), fn.__name__
                assert isinstance(item.to_dict(), dict)

    def test_decision_routes_return_single_projection(self):
        """单对象路由 (workflow detail / approve / reject) 返回投影模型或 None。"""
        stub = _StubService()
        assert _api.get_workflow(stub, "WF-1").to_dict()["id"] == "WF-1"
        assert _api.approve_approval(stub, "AG-1").to_dict()["action"] == "approve"
        assert _api.reject_approval(stub, "AG-1").to_dict()["action"] == "reject"
        assert _api.approve_approval(stub, "nope") is None  # 门不存在 → None (404 语义)
        assert _api.reject_approval(stub, "nope") is None

    def test_all_routes_accept_none_logger(self, event_store):
        """logger=None 全部路由正常返回 (审计可选, 不拖垮投影)。"""
        stub = _StubService()
        assert _api.list_projects(stub) is not None
        assert _api.get_project_lifecycle(stub, "demo") is not None
        assert _api.list_approvals(stub) is not None
        assert _api.get_decision(stub, "dec-1") is not None
        assert _api.list_recommendations(stub) is not None
        assert _api.list_experience(stub) is not None
        assert _api.list_providers(stub) is not None
        # S9-002: org 查询 + 决定
        assert _api.list_workflows(stub) is not None
        assert _api.get_workflow(stub, "WF-1") is not None
        assert _api.list_artifacts(stub) is not None
        assert _api.list_approval_gates(stub) is not None
        assert _api.approve_approval(stub, "AG-1") is not None
        assert _api.reject_approval(stub, "AG-1") is not None
        assert event_store.query() == []

    def test_no_web_framework_dependency(self):
        """api/ 纯函数: 顶层零 import FastAPI/starlette/flask (11B 薄层待挂)。"""
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parents[2] / "factory-console"
        pattern = re.compile(
            r"(?m)^(?:import (fastapi|starlette|flask|django)\b|from (fastapi|starlette|flask|django)\b)"
        )
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            assert not pattern.search(path.read_text(encoding="utf-8")), path
