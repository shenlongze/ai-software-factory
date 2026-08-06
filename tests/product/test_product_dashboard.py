"""tests/product/test_product_dashboard.py — Dashboard Product View (Phase 9A, ADR-0026, 第十九视图)。

覆盖: collector include_product 默认关闭 (既有 dashboard 行为零回归) / 显式开启
聚合 (idea/artifact/approval/workflow 计数 + 明细, 失败安全: 未装配/损坏 → 空快照)
/ build_product 渲染 (有数据与空态) / renderer _SINGLE 接线 / CLI dashboard
--view product 端到端 (--json + 审计事件) / 默认 all 视图不含 Product 面板。
"""

from __future__ import annotations

import json

from dashboard.collector import DashboardCollector
from dashboard.models import FactorySnapshot
from dashboard.renderer import DashboardRenderer, _SINGLE
from dashboard.views import build_product

from cli_helpers import open_events
from product_helpers import seed_artifact, seed_idea


def _collector(task_store, agent_registry, workflow_store, runtime_store,
               event_store, checkpoint_store, product_store, include_product=False):
    return DashboardCollector(
        task_store=task_store, agent_registry=agent_registry,
        workflow_store=workflow_store, runtime_store=runtime_store,
        event_store=event_store, checkpoint_store=checkpoint_store,
        product_store=product_store, include_product=include_product,
    )


class TestViewRegistry:
    def test_product_is_19th_view(self):
        from dashboard.renderer import VIEWS

        assert "product" in VIEWS
        assert VIEWS[-1] == "product"

    def test_build_product_wired_in_renderer(self):
        assert _SINGLE["product"] is build_product


class TestCollectorDefaultOff:
    def test_default_snapshot_empty(self, task_store, agent_registry, workflow_store,
                                    runtime_store, event_store, checkpoint_store,
                                    store):
        c = _collector(task_store, agent_registry, workflow_store,
                       runtime_store, event_store, checkpoint_store, store)
        snap: FactorySnapshot = c.collect()
        assert snap.product.idea_total == 0
        assert snap.product.artifact_total == 0
        assert snap.product.approval_pending == 0
        assert snap.product.workflow_total == 0

    def test_store_ignored_when_disabled(self, task_store, agent_registry, workflow_store,
                                         runtime_store, event_store, checkpoint_store,
                                         service):
        seed_idea(service)
        c = _collector(task_store, agent_registry, workflow_store,
                       runtime_store, event_store, checkpoint_store,
                       service._store, include_product=False)
        assert c.collect().product.idea_total == 0


class TestCollectorEnabled:
    def _seed(self, service):
        idea = seed_idea(service, "AI 助手", goals=["g1"])
        a = seed_artifact(service, "prd", idea_id=idea.id)
        r = service.request_approval(a.id)
        service.start_workflow(idea.id)
        service.decide_approval(r.id, "approved")
        return idea

    def test_aggregates_counts(self, task_store, agent_registry, workflow_store,
                               runtime_store, event_store, checkpoint_store,
                               service):
        self._seed(service)
        c = _collector(task_store, agent_registry, workflow_store,
                       runtime_store, event_store, checkpoint_store,
                       service._store, include_product=True)
        p = c.collect().product
        assert p.idea_total == 1
        assert p.artifact_total == 3  # product_idea + prd + product_decision
        assert p.product_decisions == 1
        assert p.approval_pending == 0
        assert p.approval_approved == 1
        assert p.workflow_total == 1
        assert p.workflows_by_status == {"running": 1}
        assert p.artifacts_by_type.get("product_idea") == 1
        assert p.artifacts_by_type.get("product_decision") == 1

    def test_pending_approval_counted(self, task_store, agent_registry, workflow_store,
                                      runtime_store, event_store, checkpoint_store,
                                      service):
        idea = seed_idea(service)
        a = seed_artifact(service, "prd", idea_id=idea.id)
        service.request_approval(a.id)
        c = _collector(task_store, agent_registry, workflow_store,
                       runtime_store, event_store, checkpoint_store,
                       service._store, include_product=True)
        p = c.collect().product
        assert p.approval_pending == 1
        assert p.approval_approved == 0

    def test_workflow_awaiting_approval_status(self, task_store, agent_registry,
                                               workflow_store, runtime_store,
                                               event_store, checkpoint_store,
                                               service):
        idea = seed_idea(service)
        service.start_workflow(idea.id)
        a = seed_artifact(service, "prd", idea_id=idea.id)
        service.request_approval(a.id)
        c = _collector(task_store, agent_registry, workflow_store,
                       runtime_store, event_store, checkpoint_store,
                       service._store, include_product=True)
        p = c.collect().product
        assert p.workflows_by_status == {"paused": 1}  # 9c: awaiting_approval → paused 细化

    def test_unassembled_store_fail_safe(self, task_store, agent_registry, workflow_store,
                                         runtime_store, event_store, checkpoint_store):
        # include_product=True 但 product_store=None → 空快照, 不抛错
        c = _collector(task_store, agent_registry, workflow_store,
                       runtime_store, event_store, checkpoint_store, None, True)
        assert c.collect().product.idea_total == 0

    def test_corrupt_store_fail_safe(self, task_store, agent_registry, workflow_store,
                                     runtime_store, event_store, checkpoint_store,
                                     product_dir):
        # 损坏的 product 数据 → 空快照 (同 include_git 失败安全哲学), 不抛错
        from product.store import ProductStore

        (product_dir).mkdir(parents=True, exist_ok=True)
        (product_dir / "ideas.json").write_text("{ broken", encoding="utf-8")
        c = _collector(task_store, agent_registry, workflow_store,
                       runtime_store, event_store, checkpoint_store,
                       ProductStore(product_dir), True)
        assert c.collect().product.idea_total == 0


class TestRender:
    def test_render_with_data(self, task_store, agent_registry, workflow_store,
                              runtime_store, event_store, checkpoint_store,
                              service):
        idea = seed_idea(service, "AI 助手")
        a = seed_artifact(service, "prd", idea_id=idea.id)
        r = service.request_approval(a.id)
        service.start_workflow(idea.id)
        service.decide_approval(r.id, "approved")
        c = _collector(task_store, agent_registry, workflow_store,
                       runtime_store, event_store, checkpoint_store,
                       service._store, include_product=True)
        out = DashboardRenderer().render(c.collect(), view="product")
        assert "Product Intelligence" in out
        assert "1 ideas" in out
        assert "AI 助手" in out
        assert "APR-001" in out
        assert "PW-001" in out
        assert "product decisions" in out

    def test_render_empty_state(self, task_store, agent_registry, workflow_store,
                                runtime_store, event_store, checkpoint_store):
        c = _collector(task_store, agent_registry, workflow_store,
                       runtime_store, event_store, checkpoint_store, None)
        out = DashboardRenderer().render(c.collect(), view="product")
        assert "(no ideas)" in out
        assert "(no approvals)" in out
        assert "(no workflows)" in out

    def test_render_via_build_directly(self, task_store, agent_registry, workflow_store,
                                       runtime_store, event_store, checkpoint_store):
        c = _collector(task_store, agent_registry, workflow_store,
                       runtime_store, event_store, checkpoint_store, None)
        assert build_product(c.collect()) is not None


class TestCliDashboard:
    def test_cli_view_product_empty(self, capsys, cli_root):
        from cli.main import main

        rc = main(["--root", str(cli_root), "dashboard", "--view", "product"])
        out, _ = capsys.readouterr()
        assert rc == 0
        assert "Product Intelligence" in out
        assert "(no ideas)" in out

    def test_cli_view_product_with_data(self, capsys, cli_root):
        from cli.main import main

        # 先经 CLI 落 product 数据 (清空首次输出的 capsys)
        main(["--root", str(cli_root), "product", "idea", "create", "--title", "AI 助手"])
        capsys.readouterr()
        rc = main(["--root", str(cli_root), "dashboard", "--view", "product"])
        out, _ = capsys.readouterr()
        assert rc == 0
        assert "1 ideas" in out
        assert "AI 助手" in out

    def test_cli_dashboard_json_contains_product(self, capsys, cli_root):
        from cli.main import main

        main(["--root", str(cli_root), "product", "idea", "create", "--title", "t"])
        capsys.readouterr()  # 排空 idea create 输出, 只留 dashboard JSON
        rc = main(["--root", str(cli_root), "--json", "dashboard", "--view", "product"])
        out, _ = capsys.readouterr()
        assert rc == 0
        data = json.loads(out)
        p = data["snapshot"]["product"]
        assert p["idea_total"] == 1
        assert p["artifact_total"] == 1
        assert p["artifacts_by_type"]["product_idea"] == 1

    def test_cli_default_all_excludes_product_panel(self, capsys, cli_root):
        from cli.main import main

        rc = main(["--root", str(cli_root), "dashboard"])
        out, _ = capsys.readouterr()
        assert rc == 0
        assert "Product Intelligence" not in out

    def test_cli_view_product_audits_dashboard_viewed(self, capsys, cli_root):
        from cli.main import main

        rc = main(["--root", str(cli_root), "dashboard", "--view", "product"])
        assert rc == 0
        store = open_events(cli_root)
        types = [e.type.value for e in store.query()]
        store.close()
        assert "dashboard.viewed" in types
