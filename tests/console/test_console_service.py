"""tests/console/test_console_service.py — ConsoleService 只读聚合各域 + 失败安全 (Phase 11A, ADR-0034)。

覆盖:
- dashboard 七域一次装配 (projects/approvals/agents/decisions/cost/experience/activity)
- 各域只读聚合: 项目 (生命周期阶段/任务计数/待审批/最近活动)、审批投影
  (artifact_type/confidence/risk/evidence)、决策投影 (options/推荐/评分/
  reasoning/evidence)、推荐投影 (candidate/分项)、经验投影 (subject/结果)、
  Provider 目录 (cost/performance/experience 聚合)、成本/经验汇总
- 失败安全: 任一 store 缺失/损坏/抛异常 → 对应域空/None, Console 永不失败
  (缺 workspace → 空; broken workspace → 空; broken store → 空)

basename 全仓库唯一 (test_console_* 前缀)。
"""

from __future__ import annotations

from agents.registry import AgentRegistry
from agents.store import AgentStore

from intelligence.store import DecisionStore, ExperienceStore, RecommendationStore

from product.lifecycle import ProductLifecycleEngine, ProductService
from product.models import ProductLifecycle, ProductStageRun
from product.store import ProductStore

from providers.registry import ProviderRegistry
from providers.store import ProviderStore
from providers.usage import UsageStore

from tasks.models import Task
from tasks.store import TaskStore

from console_helpers import (
    FakeWorkspace,
    make_agent,
    make_artifact,
    make_decision,
    make_experience,
    make_idea,
    make_project,
    make_provider,
    make_recommendation,
    make_request,
    make_usage,
)

console_mod = __import__("importlib").import_module("factory-console")
ConsoleService = console_mod.ConsoleService


# ------------------------------------------------------------------ 装配


def _service(root, *, workspace=None, events=None, **kw):
    """全依赖 ConsoleService (真实 store, root 独立数据空间)。"""
    return ConsoleService(
        workspace_manager=workspace if workspace is not None else FakeWorkspace(),
        task_store=kw.get("task_store", TaskStore(root / "tasks")),
        agent_registry=kw.get("agent_registry", AgentRegistry(AgentStore(root / "agents"))),
        product_store=kw.get("product_store", ProductStore(root / "product")),
        decision_store=kw.get("decision_store", DecisionStore(root / "intelligence")),
        recommendation_store=kw.get("recommendation_store", RecommendationStore(root / "intelligence")),
        experience_store=kw.get("experience_store", ExperienceStore(root / "intelligence")),
        usage_store=kw.get("usage_store", UsageStore(root / "providers")),
        provider_registry=kw.get("provider_registry", ProviderRegistry(ProviderStore(root / "providers"))),
        event_store=events,
    )


def _seed_lifecycle(store: ProductStore, project_id: str = "demo", *, stage_status: str = "running"):
    """seed: idea(context.project) + lifecycle (research completed → prd running)。"""
    store.save_idea(make_idea(project_id=project_id))
    lifecycle = ProductLifecycle(
        id="LC-001",
        idea_id="idea-1",
        template_name="software_project",
        status=stage_status,
        stages=[
            ProductStageRun(name="research", kind="artifact_generation",
                            status="completed", artifact_type="research"),
            ProductStageRun(name="prd", kind="artifact_generation",
                            status="running", artifact_type="prd", gate="prd"),
        ],
        current_stage_index=1,
    )
    store.save_lifecycle(lifecycle)
    return lifecycle


class _BrokenStore:
    """list/get/list_all 全部抛异常 (模拟损坏 store)。"""

    def list(self, *a, **k):
        raise RuntimeError("corrupt store (simulated)")

    def list_all(self, *a, **k):
        raise RuntimeError("corrupt store (simulated)")

    def list_requests(self, *a, **k):
        raise RuntimeError("corrupt store (simulated)")

    def get(self, *a, **k):
        raise RuntimeError("corrupt store (simulated)")

    def list_ideas(self, *a, **k):
        raise RuntimeError("corrupt store (simulated)")

    def list_pending_requests(self, *a, **k):
        raise RuntimeError("corrupt store (simulated)")


# ------------------------------------------------------------------ 七域 Dashboard


class TestDashboard:
    def test_empty_factory_all_sections_empty(self, tmp_path):
        d = _service(tmp_path).dashboard()
        assert d.projects == []
        assert d.approvals == []
        assert d.agents == []
        assert d.decisions == []
        assert d.cost.calls == 0
        assert d.experience.total == 0
        assert d.activity == []

    def test_all_none_dependencies_empty(self):
        """全部依赖 None → 全空域 (冷启动/缺装照常工作)。"""
        d = ConsoleService().dashboard()
        assert d.projects == []
        assert d.approvals == []
        assert d.agents == []
        assert d.decisions == []
        assert d.cost.total_cost == 0.0
        assert d.experience.total == 0
        assert d.activity == []

    def test_dashboard_assembles_seven_domains(self, tmp_path, db_path):
        root = tmp_path / "factory"
        root.mkdir()
        product = ProductStore(root / "product")
        product.save_idea(make_idea(project_id="demo"))
        product.save_artifact(make_artifact(artifact_id="art-1", confidence=0.8))
        product.save_request(make_request(status="pending"))
        decisions = DecisionStore(root / "intelligence")
        decisions.save(make_decision())
        usage = UsageStore(root / "providers")
        usage.record(make_usage(estimated_cost=0.01))
        agents = AgentStore(root / "agents")
        agents.save(make_agent(status="WORKING"))
        from events.store import EventStore

        events = EventStore(db_path)
        service = _service(
            root,
            workspace=FakeWorkspace([make_project()]),
            product_store=product,
            decision_store=decisions,
            usage_store=usage,
            agent_registry=AgentRegistry(agents),
            events=events,
        )
        d = service.dashboard()
        assert len(d.projects) == 1
        assert len(d.pending_approvals) == 1
        assert len(d.running_agents) == 1
        assert len(d.decisions) == 1
        assert d.cost.calls == 1
        assert d.cost.total_cost == 0.01
        events.close()

    def test_recent_limit_truncates_decisions_and_activity(self, tmp_path, db_path):
        root = tmp_path / "factory"
        root.mkdir()
        decisions = DecisionStore(root / "intelligence")
        for i in range(5):
            decisions.save(make_decision(decision_id=f"dec-{i}",
                                         created_at=f"2026-01-0{i + 1}T00:00:00.000000Z"))
        from events.logger import EventLogger
        from events.store import EventStore

        events = EventStore(db_path)
        logger = EventLogger(events)
        for i in range(7):
            logger.record("console.viewed", source="cli", stage="viewed",
                          action="view", result="OK",
                          payload={"view": "x", "count": i})
        d = _service(root, decision_store=decisions, events=events).dashboard(recent_limit=3)
        assert len(d.decisions) == 3
        assert len(d.activity) == 3
        events.close()


# ------------------------------------------------------------------ GET /projects


class TestListProjects:
    def test_project_summary_shape(self, tmp_path):
        root = tmp_path / "factory"
        root.mkdir()
        product = ProductStore(root / "product")
        _seed_lifecycle(product)
        tasks = TaskStore(root / "tasks")
        tasks.create(Task(id="T-1", title="t1", project="demo",
                          status="BACKLOG"))
        tasks.create(Task(id="T-2", title="t2", project="demo",
                          status="RUNNING" if hasattr(tasks, "RUNNING") else "DEVELOPMENT"))
        service = _service(
            root,
            workspace=FakeWorkspace([make_project()]),
            product_store=product,
            task_store=tasks,
        )
        projects = service.list_projects()
        assert len(projects) == 1
        p = projects[0]
        assert p.id == "demo"
        assert p.name == "Demo Project"
        assert p.language == "python"
        assert p.repository.startswith("https://")
        assert p.tech_stack == ["python", "flask"]
        assert p.status == "active"
        assert p.lifecycle_stage == "prd"
        assert p.lifecycle_status == "running"
        assert p.tasks == {"BACKLOG": 1, "DEVELOPMENT": 1}

    def test_no_lifecycle_stage_none(self, tmp_path):
        service = _service(tmp_path, workspace=FakeWorkspace([make_project()]))
        p = service.list_projects()[0]
        assert p.lifecycle_stage is None
        assert p.lifecycle_status is None
        assert p.pending_approvals == 0

    def test_pending_approvals_per_project(self, tmp_path):
        root = tmp_path / "factory"
        root.mkdir()
        product = ProductStore(root / "product")
        product.save_idea(make_idea(idea_id="idea-1", project_id="demo"))
        product.save_artifact(make_artifact(artifact_id="art-1"))
        product.save_request(make_request(request_id="req-1", artifact_id="art-1",
                                          idea_id="idea-1", status="pending"))
        product.save_idea(make_idea(idea_id="idea-2", project_id="other"))
        product.save_request(make_request(request_id="req-2", artifact_id="art-1",
                                          idea_id="idea-2", status="approved"))
        service = _service(
            tmp_path / "factory",
            workspace=FakeWorkspace([make_project(), make_project(project_id="other", name="Other")]),
            product_store=product,
        )
        by_id = {p.id: p for p in service.list_projects()}
        assert by_id["demo"].pending_approvals == 1
        assert by_id["other"].pending_approvals == 0  # approved 不计数

    def test_last_activity_from_events(self, tmp_path, db_path):
        root = tmp_path / "factory"
        root.mkdir()
        from events.models import Event
        from events.store import EventStore

        events = EventStore(db_path)
        events.append(Event.create(
            "task.created", source="cli", project_id="demo",
            payload={"task_id": "T-1"},
        ))
        service = _service(root, workspace=FakeWorkspace([make_project()]), events=events)
        p = service.list_projects()[0]
        assert p.last_activity is not None
        assert p.last_activity.startswith("2026-") or "T" in p.last_activity
        events.close()

    def test_archived_project_status_passthrough(self, tmp_path):
        service = _service(
            tmp_path,
            workspace=FakeWorkspace([make_project(status="archived")]),
        )
        assert service.list_projects()[0].status == "archived"


# ------------------------------------------------------------------ GET /projects/{id}/lifecycle


class TestProjectLifecycle:
    def test_lifecycle_summary(self, tmp_path):
        root = tmp_path / "factory"
        root.mkdir()
        product = ProductStore(root / "product")
        _seed_lifecycle(product)
        service = _service(root, product_store=product)
        summary = service.project_lifecycle("demo")
        assert summary is not None
        assert summary.project_id == "demo"
        assert summary.lifecycle_id == "LC-001"
        assert summary.idea_id == "idea-1"
        assert summary.template_name == "software_project"
        assert summary.status == "running"
        assert summary.completed_stages == ["research"]
        assert summary.current_stage is not None
        assert summary.current_stage["name"] == "prd"
        assert isinstance(summary.next_actions, list)

    def test_unknown_project_none(self, tmp_path):
        service = _service(tmp_path)
        assert service.project_lifecycle("nope") is None

    def test_project_without_lifecycle_none(self, tmp_path):
        service = _service(tmp_path, workspace=FakeWorkspace([make_project()]))
        assert service.project_lifecycle("demo") is None


# ------------------------------------------------------------------ GET /approvals


class TestListApprovals:
    def test_approval_projection(self, tmp_path):
        root = tmp_path / "factory"
        root.mkdir()
        product = ProductStore(root / "product")
        product.save_artifact(make_artifact(artifact_id="art-1", confidence=0.8,
                                            evidence=["event:evt-9"]))
        product.save_request(make_request(status="pending", gate="prd",
                                          comment="please review"))
        service = _service(root, product_store=product)
        approvals = service.list_approvals()
        assert len(approvals) == 1
        a = approvals[0]
        assert a.id == "req-1"
        assert a.artifact_id == "art-1"
        assert a.artifact_type == "prd"
        assert a.gate == "prd"
        assert a.status == "pending"
        assert a.confidence == 0.8
        assert a.risk is None  # confidence >= 0.5 → 无风险标记
        assert a.evidence == ["event:evt-9"]
        assert a.comment == "please review"
        assert a.artifact_version == 1

    def test_low_confidence_marks_medium_risk(self, tmp_path):
        root = tmp_path / "factory"
        root.mkdir()
        product = ProductStore(root / "product")
        product.save_artifact(make_artifact(confidence=0.3))
        product.save_request(make_request())
        service = _service(root, product_store=product)
        assert service.list_approvals()[0].risk == "medium"

    def test_missing_artifact_graceful(self, tmp_path):
        root = tmp_path / "factory"
        root.mkdir()
        product = ProductStore(root / "product")
        product.save_request(make_request(artifact_id="missing-art"))
        service = _service(root, product_store=product)
        a = service.list_approvals()[0]
        assert a.artifact_type == ""
        assert a.confidence == 0.0
        assert a.risk is None
        assert a.evidence == []

    def test_no_product_store_empty(self, tmp_path):
        assert _service(tmp_path, product_store=None).list_approvals() == []


# ------------------------------------------------------------------ GET /decisions/{id}


class TestGetDecision:
    def test_decision_projection(self, tmp_path):
        root = tmp_path / "factory"
        root.mkdir()
        store = DecisionStore(root / "intelligence")
        store.save(make_decision())
        service = _service(root, decision_store=store)
        d = service.get_decision("dec-1")
        assert d is not None
        assert d.decision_type == "provider_selection"
        assert d.subject_id == "task-1"
        assert d.status == "recommended"
        assert d.recommendation == "a"
        assert d.score == 0.9  # 推荐选项 a 的 score
        assert d.risk == 0.2
        assert d.risk_level == "medium"
        assert d.requires_approval is True
        assert d.approval_request_id is None
        assert d.reasoning == ["capability match"]
        assert d.evidence == ["event:evt-1"]
        assert [o["id"] for o in d.options] == ["a", "b"]

    def test_missing_decision_none(self, tmp_path):
        store = DecisionStore(tmp_path / "intelligence")
        service = _service(tmp_path, decision_store=store)
        assert service.get_decision("nope") is None

    def test_no_recommendation_score_zero(self, tmp_path):
        root = tmp_path / "factory"
        root.mkdir()
        store = DecisionStore(root / "intelligence")
        store.save(make_decision(recommendation=None))
        d = _service(root, decision_store=store).get_decision("dec-1")
        assert d.score == 0.0
        assert d.reasoning == []

    def test_no_store_none(self, tmp_path):
        assert _service(tmp_path, decision_store=None).get_decision("x") is None

    def test_recent_decisions_sorted_and_limited(self, tmp_path):
        root = tmp_path / "factory"
        root.mkdir()
        store = DecisionStore(root / "intelligence")
        store.save(make_decision(decision_id="old", created_at="2026-01-01T00:00:00.000000Z"))
        store.save(make_decision(decision_id="mid", created_at="2026-01-15T00:00:00.000000Z"))
        store.save(make_decision(decision_id="new", created_at="2026-03-02T00:00:00.000000Z"))
        service = _service(root, decision_store=store)
        ids = [d.id for d in service.list_recent_decisions(limit=2)]
        assert ids == ["new", "mid"]


# ------------------------------------------------------------------ GET /recommendations


class TestListRecommendations:
    def test_recommendation_projection(self, tmp_path):
        root = tmp_path / "factory"
        root.mkdir()
        store = RecommendationStore(root / "intelligence")
        store.save(make_recommendation())
        service = _service(root, recommendation_store=store)
        recs = service.list_recommendations()
        assert len(recs) == 1
        r = recs[0]
        assert r.candidate == "provider:hermes"
        assert r.target_type == "provider"
        assert r.score == 0.92
        assert r.confidence == 0.7
        assert r.risk == 0.1
        assert r.explanation == ["capability match", "low cost"]
        assert r.evidence == ["event:evt-1"]

    def test_factors_empty_without_structured_factors(self, tmp_path):
        """Recommendation 模型无分项字段 (factors/basis) → 空 dict 不臆造。

        (宽容解析: 模型未来增加 factors 字段时自动投影; 当前无数据源 → {}。)
        """
        root = tmp_path / "factory"
        root.mkdir()
        store = RecommendationStore(root / "intelligence")
        store.save(make_recommendation())
        r = _service(root, recommendation_store=store).list_recommendations()[0]
        assert r.factors == {}

    def test_sorted_and_limited(self, tmp_path):
        root = tmp_path / "factory"
        root.mkdir()
        store = RecommendationStore(root / "intelligence")
        store.save(make_recommendation(rec_id="old", created_at="2026-01-01T00:00:00.000000Z"))
        store.save(make_recommendation(rec_id="new", created_at="2026-03-02T00:00:00.000000Z"))
        ids = [r.id for r in _service(root, recommendation_store=store).list_recommendations(limit=1)]
        assert ids == ["new"]


# ------------------------------------------------------------------ GET /experience


class TestListExperience:
    def test_experience_projection(self, tmp_path):
        root = tmp_path / "factory"
        root.mkdir()
        store = ExperienceStore(root / "intelligence")
        store.save(make_experience(domain="provider", subject_id="hermes",
                                   result="success", score=0.95))
        service = _service(root, experience_store=store)
        records = service.list_experience()
        assert len(records) == 1
        e = records[0]
        assert e.subject == "provider:hermes"
        assert e.domain == "provider"
        assert e.result == "success"
        assert e.score == 0.95
        assert e.confidence == 0.9
        assert e.freshness == 1.0
        assert e.capability == ["code"]

    def test_sorted_and_limited(self, tmp_path):
        root = tmp_path / "factory"
        root.mkdir()
        store = ExperienceStore(root / "intelligence")
        store.save(make_experience(exp_id="old", created_at="2026-01-01T00:00:00.000000Z"))
        store.save(make_experience(exp_id="new", created_at="2026-03-02T00:00:00.000000Z"))
        ids = [e.id for e in _service(root, experience_store=store).list_experience(limit=1)]
        assert ids == ["new"]


# ------------------------------------------------------------------ GET /providers


class TestListProviders:
    def test_provider_projection_includes_defaults(self, tmp_path):
        """registry.list() 看合并视图 (默认基线 hermes 也在) — 8A 语义。"""
        root = tmp_path / "factory"
        root.mkdir()
        service = _service(root)
        providers = service.list_providers()
        ids = [p.id for p in providers]
        assert "hermes" in ids
        p = next(p for p in providers if p.id == "hermes")
        assert p.status == "ACTIVE"
        assert "chat" in p.capabilities
        assert p.cost is None  # 无 usage/经验 → 不臆造
        assert p.performance is None
        assert p.experience is None
        assert p.usage_calls == 0

    def test_custom_provider_with_usage_and_experience(self, tmp_path):
        root = tmp_path / "factory"
        root.mkdir()
        provider_store = ProviderStore(root / "providers")
        registry = ProviderRegistry(provider_store)
        registry.register(make_provider(provider_id="mock", capabilities=["code"]))
        usage = UsageStore(root / "providers")
        usage.record(make_usage(provider_id="mock", estimated_cost=0.0, success=True))
        usage.record(make_usage(provider_id="mock", estimated_cost=0.0, success=True))
        experience = ExperienceStore(root / "intelligence")
        experience.save(make_experience(exp_id="exp-mock", domain="provider",
                                        subject_id="mock", score=0.9, confidence=0.8))
        service = _service(root, usage_store=usage, experience_store=experience,
                           provider_registry=registry)
        providers = {p.id: p for p in service.list_providers()}
        mock = providers["mock"]
        assert mock.usage_calls == 2
        assert mock.cost == 1.0  # 0 成本 → 1.0
        assert mock.performance == 1.0  # 2/2 成功
        assert mock.experience is not None
        assert 0.0 <= mock.experience <= 1.0

    def test_no_registry_empty(self, tmp_path):
        assert _service(tmp_path, provider_registry=None).list_providers() == []


# ------------------------------------------------------------------ 成本/经验汇总


class TestCostSummary:
    def test_cost_aggregation(self, tmp_path):
        root = tmp_path / "factory"
        root.mkdir()
        usage = UsageStore(root / "providers")
        usage.record(make_usage(provider_id="hermes", estimated_cost=0.01, success=True,
                                prompt_tokens=100, completion_tokens=50))
        usage.record(make_usage(provider_id="hermes", estimated_cost=0.03, success=False,
                                prompt_tokens=200, completion_tokens=100))
        c = _service(root, usage_store=usage)._cost_summary()
        assert c.calls == 2
        assert c.total_cost == 0.04
        assert c.success_rate == 0.5
        assert c.avg_cost == 0.02
        assert c.total_tokens == 450
        assert c.by_provider["hermes"]["calls"] == 2
        assert c.by_provider["hermes"]["success_rate"] == 0.5

    def test_cost_empty_without_usage(self, tmp_path):
        c = _service(tmp_path)._cost_summary()
        assert c.calls == 0
        assert c.total_cost == 0.0
        assert c.by_provider == {}

    def test_cost_broken_store_fail_safe(self, tmp_path):
        c = _service(tmp_path, usage_store=_BrokenStore())._cost_summary()
        assert c.calls == 0


class TestExperienceSummary:
    def test_experience_aggregation(self, tmp_path):
        root = tmp_path / "factory"
        root.mkdir()
        store = ExperienceStore(root / "intelligence")
        store.save(make_experience(exp_id="e1", domain="provider", result="success", score=0.9))
        store.save(make_experience(exp_id="e2", domain="provider", result="failure", score=0.4))
        store.save(make_experience(exp_id="e3", domain="agent", result="success", score=0.8))
        s = _service(root, experience_store=store)._experience_summary()
        assert s.total == 3
        assert s.by_domain == {"provider": 2, "agent": 1}
        assert s.success_rate == round(2 / 3, 4)  # 汇总 round(…, 4) 口径
        assert round(s.avg_score, 4) == round((0.9 + 0.4 + 0.8) / 3, 4)
        assert s.avg_confidence == 0.9

    def test_empty_without_store(self, tmp_path):
        s = _service(tmp_path)._experience_summary()
        assert s.total == 0
        assert s.by_domain == {}

    def test_broken_store_fail_safe(self, tmp_path):
        s = _service(tmp_path, experience_store=_BrokenStore())._experience_summary()
        assert s.total == 0


# ------------------------------------------------------------------ 失败安全


class TestFailureSafety:
    def test_broken_workspace_empty_projects(self, tmp_path):
        service = _service(tmp_path, workspace=FakeWorkspace(broken=True))
        assert service.list_projects() == []
        d = service.dashboard()
        assert d.projects == []

    def test_broken_product_store_graceful(self, tmp_path):
        service = _service(tmp_path, product_store=_BrokenStore())
        assert service.list_approvals() == []
        assert service.list_projects() == []  # _lifecycle_for_project 失败安全
        d = service.dashboard()
        assert d.approvals == []

    def test_broken_agent_registry_empty_agents(self, tmp_path):
        service = _service(tmp_path, agent_registry=_BrokenStore())
        d = service.dashboard()
        assert d.agents == []

    def test_broken_decision_store_empty_decisions(self, tmp_path):
        service = _service(tmp_path, decision_store=_BrokenStore())
        assert service.list_recent_decisions() == []
        assert service.get_decision("x") is None

    def test_broken_event_store_empty_activity(self, tmp_path):
        service = _service(tmp_path, event_store=_BrokenStore())
        assert service.dashboard().activity == []
