"""tests/console/test_console_api.py — 6 路由函数审计 (Phase 11A, ADR-0034)。

覆盖 (factory-console/api/):
- 6 个路由函数模块 (projects/lifecycle/approvals/decisions/intelligence/
  providers) 全部导出 + VIEW 常量
- 每个路由函数: 只读投影返回 (响应模型/None) — 纯函数, 无 Web 依赖
- 审计集成: 有 EventLogger → 发 console.viewed (payload view/count/
  project_id/extra; ADR-0002 读审计同语义)
- logger=None → 无审计事件, 返回不受影响
- 只读铁律: 路由函数不携带任何执行/审批指令 (返回模型即只读投影)

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


class _StubService:
    """路由函数消费的最小只读接口桩 (返回固定投影, 审计逻辑与真实 service 解耦)。"""

    def list_projects(self):
        return [ProjectSummary(id="demo"), ProjectSummary(id="other", status="archived")]

    def project_lifecycle(self, project_id):
        return LifecycleSummary(project_id=project_id, status="running")

    def list_approvals(self):
        return [
            ApprovalSummary(id="req-1", artifact_id="art-1", status="pending"),
            ApprovalSummary(id="req-2", artifact_id="art-2", status="approved"),
        ]

    def get_decision(self, decision_id):
        return DecisionSummary(id=decision_id, recommendation="a", score=0.9)

    def list_recommendations(self, limit=10):
        return [RecommendationSummary(id="rec-1", score=0.92)]

    def list_experience(self, limit=10):
        return [ExperienceSummary(id="exp-1", score=0.8)]

    def list_providers(self):
        return [ProviderSummary(id="hermes")]


# ------------------------------------------------------------------ 路由导出


class TestRouteExports:
    def test_six_route_modules_exported(self):
        """api/ 暴露 6 个路由模块的 7 个函数 (intelligence 含 2 个视图)。"""
        expected = {
            "get_decision",
            "get_project_lifecycle",
            "list_approvals",
            "list_experience",
            "list_projects",
            "list_providers",
            "list_recommendations",
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


# ------------------------------------------------------------------ 只读铁律 (路由层)


class TestReadOnlyIronRule:
    def test_routes_only_return_projection_models(self):
        """路由函数返回值全部是只读投影模型 (无写路径/无执行指令)。"""
        stub = _StubService()
        for fn, args in [
            (_api.list_projects, ()),
            (_api.list_approvals, ()),
            (_api.list_recommendations, ()),
            (_api.list_experience, ()),
            (_api.list_providers, ()),
        ]:
            for item in fn(stub, *args):
                assert hasattr(item, "to_dict"), fn.__name__
                assert isinstance(item.to_dict(), dict)

    def test_all_routes_accept_none_logger(self, event_store):
        """logger=None 全部路由正常返回 (审计可选, 不拖垮只读投影)。"""
        stub = _StubService()
        assert _api.list_projects(stub) is not None
        assert _api.get_project_lifecycle(stub, "demo") is not None
        assert _api.list_approvals(stub) is not None
        assert _api.get_decision(stub, "dec-1") is not None
        assert _api.list_recommendations(stub) is not None
        assert _api.list_experience(stub) is not None
        assert _api.list_providers(stub) is not None
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
