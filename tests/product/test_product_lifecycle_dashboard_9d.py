"""tests/product/test_product_lifecycle_dashboard_9d.py — Dashboard Lifecycle View (Phase 9d, ADR-0029, 第二十视图)。

覆盖: collector include_lifecycle 默认关闭 (既有 dashboard 行为零回归) / 显式
开启聚合 (lifecycle 计数/状态分布/当前阶段/pending 审批/决策链/next_actions,
失败安全: 未装配 → 空快照) / build_lifecycle 渲染 (有数据与空态) / renderer
_SINGLE 接线 / CLI dashboard --view lifecycle 端到端 (--json + 审计事件) /
默认 all 视图不含 Lifecycle 面板。
"""

from __future__ import annotations

import json

from dashboard.collector import DashboardCollector, _lifecycle_next_actions
from dashboard.models import FactorySnapshot
from dashboard.renderer import DashboardRenderer, VIEWS, _SINGLE
from dashboard.views import build_lifecycle

from cli_helpers import event_types, open_events, run_cli
from product_helpers import seed_artifact, seed_idea


def _collector(task_store, agent_registry, workflow_store, runtime_store,
               event_store, checkpoint_store, product_store,
               include_product=False, include_lifecycle=False):
    return DashboardCollector(
        task_store=task_store, agent_registry=agent_registry,
        workflow_store=workflow_store, runtime_store=runtime_store,
        event_store=event_store, checkpoint_store=checkpoint_store,
        product_store=product_store, include_product=include_product,
        include_lifecycle=include_lifecycle,
    )


def _full_chain(service, task_store, logger=None):
    """engine 全链 (决策链 + Task) — 与 CLI 冒烟同路径。"""
    from product.lifecycle import ProductLifecycleEngine

    engine = ProductLifecycleEngine(service._store, service,
                                    task_store=task_store, logger=logger)
    idea = seed_idea(service, "仪表盘全链", context={"project": "dash"})
    engine.start_lifecycle(idea.id)
    for artifact_type in ("research", "prd", "ui", "architecture"):
        seed_artifact(service, artifact_type, idea_id=idea.id)
    lc = engine.advance(idea.id)
    lc = engine.advance(idea.id)
    lc = engine.advance(idea.id)  # → approval(prd) paused
    req = service._store.get_request(lc.current_stage.approval_request_id)
    service.decide_approval(req.id, "approved")
    lc = engine.handle_approval_outcome(idea.id)
    lc = engine.advance(idea.id)  # → approval(ui) paused
    req2 = service._store.get_request(lc.current_stage.approval_request_id)
    service.decide_approval(req2.id, "approved")
    lc = engine.handle_approval_outcome(idea.id)
    engine.advance(idea.id)  # → task
    engine.advance(idea.id)  # → completed
    return idea


class TestViewRegistry:
    def test_lifecycle_is_20th_view(self):
        from dashboard.renderer import VIEWS as V

        assert "lifecycle" in V
        assert V[-1] == "lifecycle"
        assert len(V) == 20

    def test_build_lifecycle_wired_in_renderer(self):
        assert _SINGLE["lifecycle"] is build_lifecycle


class TestNextActionsPure:
    def test_completed(self):
        assert _lifecycle_next_actions("PI-1", "completed", None, None) == [
            "lifecycle completed — tasks are ready for Core Workflow execution",
        ]

    def test_paused_with_pending(self):
        actions = _lifecycle_next_actions("PI-1", "paused",
                                          {"kind": "approval"}, {"id": "APR-1"})
        assert actions[0].startswith("decide approval APR-1")

    def test_paused_approval_decided(self):
        actions = _lifecycle_next_actions("PI-1", "paused",
                                          {"kind": "approval"}, None)
        assert actions == ["waiting for approval outcome (already decided — lifecycle will advance)"]

    def test_paused_manual_resume(self):
        actions = _lifecycle_next_actions("PI-1", "paused", {"kind": "artifact_generation"}, None)
        assert actions == ["resume lifecycle (product lifecycle resume is engine API)"]

    def test_running_artifact_generation(self):
        actions = _lifecycle_next_actions(
            "PI-1", "running", {"kind": "artifact_generation", "artifact_type": "prd"}, None)
        assert actions[0].startswith("generate prd artifact (product generate --type prd PI-1)")

    def test_running_decision_and_task(self):
        assert _lifecycle_next_actions("PI-1", "running", {"kind": "decision"}, None)[0] == \
            "advance to produce architecture decision (product lifecycle advance PI-1)"
        assert _lifecycle_next_actions("PI-1", "running", {"kind": "task"}, None)[0] == \
            "advance to produce task plan + tasks (product lifecycle advance PI-1)"


class TestCollectorDefaultOff:
    def test_default_snapshot_empty(self, task_store, agent_registry, workflow_store,
                                    runtime_store, event_store, checkpoint_store, store):
        c = _collector(task_store, agent_registry, workflow_store,
                       runtime_store, event_store, checkpoint_store, store)
        snap: FactorySnapshot = c.collect()
        assert snap.product.lifecycle.lifecycle_total == 0
        assert snap.product.lifecycle.decisions == []
        assert snap.product.lifecycle.next_actions == []

    def test_store_ignored_when_disabled(self, task_store, agent_registry, workflow_store,
                                         runtime_store, event_store, checkpoint_store, service):
        seed_idea(service)
        c = _collector(task_store, agent_registry, workflow_store,
                       runtime_store, event_store, checkpoint_store,
                       service._store, include_lifecycle=False)
        assert c.collect().product.lifecycle.lifecycle_total == 0

    def test_no_product_store_fail_safe(self, task_store, agent_registry, workflow_store,
                                        runtime_store, event_store, checkpoint_store):
        c = _collector(task_store, agent_registry, workflow_store,
                       runtime_store, event_store, checkpoint_store, None,
                       include_lifecycle=True)
        assert c.collect().product.lifecycle.lifecycle_total == 0  # 未装配 → 空快照


class TestCollectorEnabled:
    def test_aggregates_lifecycle_counts(self, task_store, agent_registry, workflow_store,
                                         runtime_store, event_store, checkpoint_store,
                                         service):
        _full_chain(service, task_store)
        c = _collector(task_store, agent_registry, workflow_store,
                       runtime_store, event_store, checkpoint_store,
                       service._store, include_product=True, include_lifecycle=True)
        lc = c.collect().product.lifecycle
        assert lc.lifecycle_total == 1
        assert lc.by_status == {"completed": 1}
        assert lc.lifecycles[0]["template_name"] == "software_project"
        assert len(lc.lifecycles[0]["stages"]) == 8

    def test_current_stages_and_decisions(self, task_store, agent_registry, workflow_store,
                                          runtime_store, event_store, checkpoint_store,
                                          service):
        idea = _full_chain(service, task_store)
        c = _collector(task_store, agent_registry, workflow_store,
                       runtime_store, event_store, checkpoint_store,
                       service._store, include_lifecycle=True)
        lc = c.collect().product.lifecycle
        assert lc.current_stages == []  # completed → 无当前阶段
        assert [d["type"] for d in lc.decisions] == ["product", "architecture", "task_plan"]
        # 产物按创建序: 前置种子 (research/prd/ui/architecture) + 决策产物;
        # prd 与 ui 两次审批各产一条 product_decision (9c decide 语义), 决策链
        # 记录只锚定 prd 审批 (approval 阶段 decision_type=product)。
        assert [a["type"] for a in lc.artifacts] == [
            "product_idea", "research", "prd", "ui", "architecture",
            "product_decision", "product_decision",
            "architecture_decision", "task_plan",
        ]
        assert lc.next_actions[0]["idea_id"] == idea.id
        assert lc.next_actions[0]["status"] == "completed"

    def test_pending_approval_captured(self, task_store, agent_registry, workflow_store,
                                       runtime_store, event_store, checkpoint_store,
                                       service):
        """暂停于 approval 阶段 → pending_approvals 捕获 + paused 状态。"""
        from product.lifecycle import ProductLifecycleEngine

        engine = ProductLifecycleEngine(service._store, service, task_store=task_store)
        idea = seed_idea(service, "暂停")
        for artifact_type in ("research", "prd"):
            seed_artifact(service, artifact_type, idea_id=idea.id)
        engine.start_lifecycle(idea.id)
        engine.advance(idea.id)
        engine.advance(idea.id)
        engine.advance(idea.id)  # → approval(prd) paused
        c = _collector(task_store, agent_registry, workflow_store,
                       runtime_store, event_store, checkpoint_store,
                       service._store, include_lifecycle=True)
        lc = c.collect().product.lifecycle
        assert lc.lifecycle_total == 1
        assert lc.by_status == {"paused": 1}
        assert lc.current_stages[0]["name"] == "approval"
        assert lc.current_stages[0]["kind"] == "approval"
        assert len(lc.pending_approvals) == 1
        assert lc.pending_approvals[0]["gate"] == "prd"
        assert lc.next_actions[0]["actions"][0].startswith("decide approval")


class TestBuildLifecycleView:
    def test_render_empty_state(self):
        out = DashboardRenderer().render(FactorySnapshot(), view="lifecycle")
        assert "Product Lifecycle" in out
        assert "(no lifecycles)" in out
        assert "(no pending approvals)" in out
        assert "(no decisions)" in out

    def test_render_with_data(self, task_store, agent_registry, workflow_store,
                              runtime_store, event_store, checkpoint_store, service):
        _full_chain(service, task_store)
        c = _collector(task_store, agent_registry, workflow_store,
                       runtime_store, event_store, checkpoint_store,
                       service._store, include_lifecycle=True)
        out = DashboardRenderer().render(c.collect(), view="lifecycle")
        assert "1 lifecycles" in out
        assert "completed" in out
        assert "LC-001" in out
        assert "product" in out and "architecture" in out and "task_plan" in out
        assert "lifecycle completed" in out

    def test_renderer_iterates_lifecycle_view(self, collector):
        out = DashboardRenderer().render(collector.collect(), view="lifecycle")
        assert isinstance(out, str)
        assert "Product Lifecycle" in out

    def test_all_view_does_not_include_lifecycle_panel(self, collector):
        out = DashboardRenderer().render(collector.collect(), view="all")
        assert "Product Lifecycle" not in out  # 默认 all 同屏不含 9d 面板 (零回归)

    def test_unknown_view_still_raises(self, collector):
        import pytest

        with pytest.raises(ValueError, match="unknown dashboard view"):
            DashboardRenderer().render(collector.collect(), view="lifecyclex")


class TestCLIEndToEnd:
    def test_dashboard_view_lifecycle_json(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "--json", "dashboard", "--view", "lifecycle")
        assert rc == 0, err
        data = json.loads(out)
        assert data["snapshot"]["product"]["lifecycle"]["lifecycle_total"] == 0
        with open_events(cli_root) as store:
            assert "dashboard.viewed" in event_types(store)

    def test_dashboard_view_lifecycle_renders(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "dashboard", "--view", "lifecycle")
        assert rc == 0, err
        assert "Product Lifecycle" in out
