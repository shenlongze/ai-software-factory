"""tests/console/test_console_isolation.py — 项目数据隔离 + 零写快照 (Phase 11A, ADR-0034)。

覆盖:
- 项目隔离: ConsoleService 只读聚合按 idea.context["project"] 归属 —
  项目 A 的生命周期/待审批/任务计数不串到项目 B (9d 既有约定)
- 零写铁律 (Human Layer): 全部读方法 (dashboard/list_projects/
  project_lifecycle/list_approvals/get_decision/list_recent_decisions/
  list_recommendations/list_experience/list_providers/汇总) 前后
  数据空间逐字节一致 (唯一例外 events.db — CLI 审计事件是唯一允许的写)
- 失败安全: 缺 workspace → 空项目域, 其余域照常

basename 全仓库唯一 (test_console_* 前缀)。
"""

from __future__ import annotations

from pathlib import Path

from agents.registry import AgentRegistry
from agents.store import AgentStore

from intelligence.store import DecisionStore, ExperienceStore, RecommendationStore

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
    snapshot_domain_files,
)

console_mod = __import__("importlib").import_module("factory-console")
ConsoleService = console_mod.ConsoleService


def _service(root: Path, *, workspace=None, **kw) -> ConsoleService:
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
        event_store=kw.get("event_store"),
    )


def _seed_lifecycle(store: ProductStore, *, idea_id: str, project_id: str,
                    lifecycle_id: str, status: str = "running") -> None:
    """seed: idea(context.project) + lifecycle (research completed → prd running)。"""
    store.save_idea(make_idea(idea_id=idea_id, project_id=project_id))
    store.save_lifecycle(ProductLifecycle(
        id=lifecycle_id,
        idea_id=idea_id,
        template_name="software_project",
        status=status,
        stages=[
            ProductStageRun(name="research", kind="artifact_generation",
                            status="completed", artifact_type="research"),
            ProductStageRun(name="prd", kind="artifact_generation",
                            status="running", artifact_type="prd", gate="prd"),
        ],
        current_stage_index=1,
    ))


def _seed_two_project_factory(root: Path):
    """双项目工厂: demo 有 lifecycle + 1 pending, other 有 lifecycle + 0 pending。"""
    product = ProductStore(root / "product")
    # demo: idea-1 + lifecycle LC-001 + art-1 + pending req-1
    _seed_lifecycle(product, idea_id="idea-1", project_id="demo", lifecycle_id="LC-001")
    product.save_artifact(make_artifact(artifact_id="art-1", idea_id="idea-1"))
    product.save_request(make_request(request_id="req-1", artifact_id="art-1",
                                      idea_id="idea-1", status="pending"))
    # other: idea-2 + lifecycle LC-002 + approved req-2 (不计数)
    _seed_lifecycle(product, idea_id="idea-2", project_id="other", lifecycle_id="LC-002")
    product.save_request(make_request(request_id="req-2", artifact_id="art-1",
                                      idea_id="idea-2", status="approved"))
    tasks = TaskStore(root / "tasks")
    tasks.create(Task(id="T-1", title="t1", project="demo", status="BACKLOG"))
    tasks.create(Task(id="T-2", title="t2", project="other", status="BACKLOG"))
    workspace = FakeWorkspace([
        make_project(),  # demo
        make_project(project_id="other", name="Other"),
    ])
    return product, tasks, workspace


# ------------------------------------------------------------------ 项目隔离


class TestProjectIsolation:
    def test_lifecycle_and_pending_per_project(self, tmp_path):
        root = tmp_path / "factory"
        root.mkdir()
        product, tasks, workspace = _seed_two_project_factory(root)
        service = _service(root, workspace=workspace, product_store=product,
                           task_store=tasks)
        by_id = {p.id: p for p in service.list_projects()}
        assert by_id["demo"].lifecycle_stage == "prd"
        assert by_id["demo"].lifecycle_status == "running"
        assert by_id["demo"].pending_approvals == 1
        assert by_id["demo"].tasks == {"BACKLOG": 1}
        # other 只算自己的 lifecycle (LC-002, prd running) 与任务, 不串 demo
        assert by_id["other"].lifecycle_stage == "prd"
        assert by_id["other"].lifecycle_status == "running"
        assert by_id["other"].pending_approvals == 0  # approved 不计数
        assert by_id["other"].tasks == {"BACKLOG": 1}

    def test_approval_idea_scope_isolated(self, tmp_path):
        """req 绑定其他项目的 idea → 不污染本项目计数。"""
        root = tmp_path / "factory"
        root.mkdir()
        product = ProductStore(root / "product")
        product.save_idea(make_idea(idea_id="idea-demo", project_id="demo"))
        product.save_request(make_request(request_id="req-x", artifact_id="art-1",
                                          idea_id="idea-other", status="pending"))
        service = _service(root, workspace=FakeWorkspace([make_project()]),
                           product_store=product)
        # req-x 的 idea 不属于 demo → demo.pending_approvals == 0
        assert service.list_projects()[0].pending_approvals == 0

    def test_project_lifecycle_lookup_isolated(self, tmp_path):
        """project_lifecycle("demo") 只返回 demo 的 lifecycle (idea 归属过滤)。"""
        root = tmp_path / "factory"
        root.mkdir()
        product, tasks, workspace = _seed_two_project_factory(root)
        service = _service(root, workspace=workspace, product_store=product)
        summary = service.project_lifecycle("demo")
        assert summary is not None
        assert summary.lifecycle_id == "LC-001"
        assert summary.idea_id == "idea-1"

    def test_agents_and_approvals_not_cross_contaminated(self, tmp_path):
        """非项目维度域照常聚合 (Agent/决策全局视图, 不受项目隔离影响)。"""
        root = tmp_path / "factory"
        root.mkdir()
        product, tasks, workspace = _seed_two_project_factory(root)
        agents = AgentStore(root / "agents")
        agents.save(make_agent(status="WORKING"))
        service = _service(root, workspace=workspace, product_store=product,
                           task_store=tasks,
                           agent_registry=AgentRegistry(agents))
        d = service.dashboard()
        assert len(d.projects) == 2
        assert len(d.running_agents) == 1
        # 全局待审批只有 1 条 pending (req-1)
        assert len(d.pending_approvals) == 1
        assert len(d.approvals) == 2


# ------------------------------------------------------------------ 零写快照


class TestZeroWrite:
    def _read_methods(self, service):
        """全部只读方法清单 (零写铁律审计面)。"""
        return [
            lambda: service.dashboard(),
            lambda: service.list_projects(),
            lambda: service.project_lifecycle("demo"),
            lambda: service.list_approvals(),
            lambda: service.get_decision("dec-1"),
            lambda: service.list_recent_decisions(),
            lambda: service.list_recommendations(),
            lambda: service.list_experience(),
            lambda: service.list_providers(),
            lambda: service._cost_summary(),
            lambda: service._experience_summary(),
        ]

    def _seed_full_factory(self, root: Path):
        """全域种子 (每个读方法都有可读数据, 快照对比才有效)。"""
        product, tasks, workspace = _seed_two_project_factory(root)
        decisions = DecisionStore(root / "intelligence")
        decisions.save(make_decision())
        recommendations = RecommendationStore(root / "intelligence")
        recommendations.save(make_recommendation())
        experiences = ExperienceStore(root / "intelligence")
        experiences.save(make_experience())
        usage = UsageStore(root / "providers")
        usage.record(make_usage(estimated_cost=0.01))
        provider_store = ProviderStore(root / "providers")
        ProviderRegistry(provider_store).register(make_provider(provider_id="mock"))
        agents = AgentStore(root / "agents")
        agents.save(make_agent(status="WORKING"))
        return _service(
            root,
            workspace=workspace,
            product_store=product,
            task_store=tasks,
            decision_store=decisions,
            recommendation_store=recommendations,
            experience_store=experiences,
            usage_store=usage,
            agent_registry=AgentRegistry(agents),
            provider_registry=ProviderRegistry(provider_store),
        )

    def test_all_read_methods_are_write_free(self, tmp_path):
        """全部读方法前后数据空间逐字节一致 (零写铁律, events.db 除外)。"""
        root = tmp_path / "factory"
        root.mkdir()
        service = self._seed_full_factory(root)
        before = snapshot_domain_files(root)
        assert before, "seed 后数据空间应有内容 (快照对比才有意义)"
        for call in self._read_methods(service):
            result = call()
            assert result is not None
        after = snapshot_domain_files(root)
        assert after == before

    def test_empty_factory_zero_write(self, tmp_path):
        """空工厂: 读方法也不产生任何文件写 (冷启动纯只读)。"""
        root = tmp_path / "factory"
        root.mkdir()
        service = _service(root)
        before = snapshot_domain_files(root)
        for call in self._read_methods(service):
            call()
        assert snapshot_domain_files(root) == before

    def test_service_construction_writes_nothing(self, tmp_path):
        """ConsoleService 装配本身零写 (构造不落任何数据文件)。"""
        root = tmp_path / "factory"
        root.mkdir()
        before = snapshot_domain_files(root)
        _service(root)
        assert snapshot_domain_files(root) == before

    def test_dashboard_never_touches_task_or_agent_stores(self, tmp_path):
        """dashboard 读路径不修改 task/agent 状态 (只读投影, 无副作用)。"""
        root = tmp_path / "factory"
        root.mkdir()
        product, tasks, workspace = _seed_two_project_factory(root)
        agents = AgentStore(root / "agents")
        agents.save(make_agent(status="WORKING"))
        before = snapshot_domain_files(root)
        service = _service(root, workspace=workspace, product_store=product,
                           task_store=tasks, agent_registry=AgentRegistry(agents))
        service.dashboard()
        assert snapshot_domain_files(root) == before


# ------------------------------------------------------------------ 失败安全 (隔离退化)


class TestIsolationFailSafe:
    def test_missing_workspace_other_domains_ok(self, tmp_path):
        """缺 workspace → 项目域空, 其余域照常聚合 (失败安全)。"""
        root = tmp_path / "factory"
        root.mkdir()
        product = ProductStore(root / "product")
        product.save_request(make_request())
        service = _service(root, workspace=None, product_store=product)
        d = service.dashboard()
        assert d.projects == []
        assert len(d.approvals) == 1

    def test_missing_product_store_projects_empty(self, tmp_path):
        """缺 product store → 项目/审批域空, 不报错。"""
        service = _service(tmp_path, workspace=FakeWorkspace([make_project()]),
                           product_store=None)
        d = service.dashboard()
        assert d.projects[0].lifecycle_stage is None
        assert d.approvals == []
