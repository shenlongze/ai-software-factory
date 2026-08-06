"""tests/understanding/test_understanding_dashboard.py — Dashboard Understanding View (Phase 7, ADR-0021)。

覆盖: VIEWS 第十七视图注册 (精确集合断言在 test_dashboard_renderer.py 已更新) /
collector include_understanding 默认关闭 (既有 dashboard 行为零回归) / 显式
开启聚合 (每项目阶段 + confidence + present/missing, 按 project 排序) /
失败安全 (目录缺失 → 跳过, 聚合永不抛错) / build_understanding 渲染 (有数据
与空态) / CLI dashboard --view understanding 端到端 (workspace 项目 repository
本地目录装配 → 视图有数据)。
"""

from __future__ import annotations

import json

from dashboard.collector import DashboardCollector
from dashboard.models import FactorySnapshot
from dashboard.renderer import DashboardRenderer
from dashboard.views import build_understanding

from cli_helpers import open_events
from understanding_helpers import code_project, make_project


def _snapshot(collector: DashboardCollector) -> FactorySnapshot:
    return collector.collect()


class TestViewRegistry:
    def test_understanding_is_17th_view(self):
        from dashboard.renderer import VIEWS

        assert "understanding" in VIEWS
        assert VIEWS[-1] == "understanding"
        assert len(VIEWS) == 17

    def test_build_understanding_wired_in_renderer(self):
        from dashboard.renderer import _SINGLE

        assert _SINGLE["understanding"] is build_understanding


class TestCollectorDefaultOff:
    def test_default_snapshot_empty(self, task_store, agent_registry, workflow_store,
                                    runtime_store, event_store, checkpoint_store):
        c = DashboardCollector(
            task_store=task_store, agent_registry=agent_registry,
            workflow_store=workflow_store, runtime_store=runtime_store,
            event_store=event_store, checkpoint_store=checkpoint_store,
        )
        snap = _snapshot(c)
        assert snap.understanding.total == 0
        assert snap.understanding.items == []


class TestCollectorEnabled:
    def test_aggregates_per_project(self, task_store, agent_registry, workflow_store,
                                    runtime_store, event_store, checkpoint_store,
                                    tmp_path):
        proj_a = code_project(tmp_path / "a")
        proj_b = make_project(tmp_path / "b", {"docs/prd.md": "x"})
        c = DashboardCollector(
            task_store=task_store, agent_registry=agent_registry,
            workflow_store=workflow_store, runtime_store=runtime_store,
            event_store=event_store, checkpoint_store=checkpoint_store,
            understanding_paths=[("b", str(proj_b)), ("a", str(proj_a))],
            include_understanding=True,
        )
        snap = _snapshot(c)
        assert snap.understanding.total == 2
        # 按 project 排序
        assert [i.project for i in snap.understanding.items] == ["a", "b"]
        item_a = snap.understanding.items[0]
        assert item_a.stage == "DEVELOPMENT"
        assert item_a.confidence == 0.6
        assert item_a.present == ["SOURCE_CODE"]
        assert "PRD" in item_a.missing
        item_b = snap.understanding.items[1]
        assert item_b.stage == "PRD"
        assert item_b.present == ["PRD"]

    def test_missing_dir_skipped_fail_safe(self, task_store, agent_registry,
                                           workflow_store, runtime_store,
                                           event_store, checkpoint_store, tmp_path):
        proj = code_project(tmp_path / "real")
        c = DashboardCollector(
            task_store=task_store, agent_registry=agent_registry,
            workflow_store=workflow_store, runtime_store=runtime_store,
            event_store=event_store, checkpoint_store=checkpoint_store,
            understanding_paths=[
                ("gone", str(tmp_path / "no-such-dir")),
                ("real", str(proj)),
            ],
            include_understanding=True,
        )
        snap = _snapshot(c)  # 目录缺失 → 跳过, 聚合不抛错
        assert snap.understanding.total == 1
        assert snap.understanding.items[0].project == "real"

    def test_empty_paths_still_empty(self, task_store, agent_registry, workflow_store,
                                     runtime_store, event_store, checkpoint_store):
        c = DashboardCollector(
            task_store=task_store, agent_registry=agent_registry,
            workflow_store=workflow_store, runtime_store=runtime_store,
            event_store=event_store, checkpoint_store=checkpoint_store,
            understanding_paths=[],
            include_understanding=True,
        )
        assert _snapshot(c).understanding.total == 0


class TestRender:
    def test_render_with_data(self, task_store, agent_registry, workflow_store,
                              runtime_store, event_store, checkpoint_store, tmp_path):
        proj = code_project(tmp_path / "a")
        c = DashboardCollector(
            task_store=task_store, agent_registry=agent_registry,
            workflow_store=workflow_store, runtime_store=runtime_store,
            event_store=event_store, checkpoint_store=checkpoint_store,
            understanding_paths=[("a", str(proj))],
            include_understanding=True,
        )
        out = DashboardRenderer().render(_snapshot(c), view="understanding")
        assert "Understanding" in out
        assert "1 projects analyzed" in out
        assert "DEVELOPMENT" in out
        assert "SOURCE_CODE" in out

    def test_render_empty_state(self, task_store, agent_registry, workflow_store,
                                runtime_store, event_store, checkpoint_store):
        c = DashboardCollector(
            task_store=task_store, agent_registry=agent_registry,
            workflow_store=workflow_store, runtime_store=runtime_store,
            event_store=event_store, checkpoint_store=checkpoint_store,
        )
        out = DashboardRenderer().render(_snapshot(c), view="understanding")
        assert "(no projects analyzed)" in out

    def test_render_via_build_directly(self, task_store, agent_registry,
                                       workflow_store, runtime_store,
                                       event_store, checkpoint_store, tmp_path):
        proj = code_project(tmp_path / "a")
        c = DashboardCollector(
            task_store=task_store, agent_registry=agent_registry,
            workflow_store=workflow_store, runtime_store=runtime_store,
            event_store=event_store, checkpoint_store=checkpoint_store,
            understanding_paths=[("a", str(proj))],
            include_understanding=True,
        )
        panel = build_understanding(_snapshot(c))
        assert panel is not None


class TestCliDashboard:
    def _seed_workspace(self, root, proj_dir, project_id="demo"):
        """工厂根装配 workspace.yaml + managed project (repository → 本地目录)。"""
        from workspace.config import dump_config, WorkspaceConfig
        from workspace.loader import managed_projects_dir

        managed = managed_projects_dir(root)
        (managed / project_id).mkdir(parents=True, exist_ok=True)
        (managed / project_id / "project.yaml").write_text(
            f"name: {project_id}\nlanguage: python\nrepository: {proj_dir}\n",
            encoding="utf-8",
        )
        (root / "workspace.yaml").write_text(
            dump_config(WorkspaceConfig(name="ws", projects=[project_id])),
            encoding="utf-8",
        )

    def test_cli_view_understanding(self, capsys, tmp_path, cli_root):
        proj = code_project(tmp_path / "proj")
        self._seed_workspace(cli_root, proj)
        from cli.main import main

        rc = main(["--root", str(cli_root), "dashboard", "--view", "understanding"])
        out, _ = capsys.readouterr()
        assert rc == 0
        assert "Understanding" in out
        assert "1 projects analyzed" in out
        assert "demo" in out and "DEVELOPMENT" in out

    def test_cli_dashboard_json_contains_understanding(self, capsys, tmp_path, cli_root):
        proj = code_project(tmp_path / "proj")
        self._seed_workspace(cli_root, proj)
        from cli.main import main

        rc = main(["--root", str(cli_root), "--json", "dashboard", "--view", "understanding"])
        out, _ = capsys.readouterr()
        assert rc == 0
        data = json.loads(out)
        u = data["snapshot"]["understanding"]
        assert u["total"] == 1
        assert u["items"][0]["project"] == "demo"
        assert u["items"][0]["stage"] == "DEVELOPMENT"

    def test_cli_default_all_does_not_include_understanding_panel(self, capsys, cli_root):
        # 默认 dashboard (view=all) 不渲染 Understanding 面板 — include 缺省关,
        # 零回归 (视图只经显式 --view understanding 聚合, 同 git/change 模式)
        from cli.main import main

        rc = main(["--root", str(cli_root), "dashboard"])
        out, _ = capsys.readouterr()
        assert rc == 0
        assert "Understanding" not in out

    def test_cli_view_understanding_audits_dashboard_viewed(self, capsys, tmp_path, cli_root):
        proj = code_project(tmp_path / "proj")
        self._seed_workspace(cli_root, proj)
        from cli.main import main

        rc = main(["--root", str(cli_root), "dashboard", "--view", "understanding"])
        assert rc == 0
        store = open_events(cli_root)
        types = [e.type.value for e in store.query()]
        store.close()
        assert "dashboard.viewed" in types
