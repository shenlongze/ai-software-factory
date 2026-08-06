"""tests/change/test_change_dashboard.py — Dashboard Change View (Phase 6D, ADR-0019)。

覆盖: --view change 渲染 (Snapshots/Validations 表)、include_change 默认关闭
(既有 dashboard 行为不变)、collector 显式开启聚合、change.validation.completed
事件聚合、CLI dashboard --view change 端到端。
"""

from __future__ import annotations

import pytest

from events.models import EventType

from change.service import ChangeStore
from dashboard.collector import DashboardCollector
from dashboard.models import ChangeSnapshot, FactorySnapshot
from dashboard.renderer import DashboardRenderer

from change_helpers import make_snapshot, make_validation


class TestChangeViewRender:
    def test_render_empty_change_view(self, factory_root, logger, event_store,
                                      task_store, agent_registry, workflow_store,
                                      runtime_store, checkpoint_store):
        collector = DashboardCollector(
            task_store=task_store, agent_registry=agent_registry,
            workflow_store=workflow_store, runtime_store=runtime_store,
            event_store=event_store, checkpoint_store=checkpoint_store,
            change_store=ChangeStore(factory_root / "change"),
            include_change=True,
        )
        out = DashboardRenderer().render(collector.collect(), view="change")
        assert "Change" in out
        assert "(no snapshots)" in out
        assert "(no validations)" in out

    def test_render_snapshot_rows(self, factory_root, logger, event_store,
                                  task_store, agent_registry, workflow_store,
                                  runtime_store, checkpoint_store):
        store = ChangeStore(factory_root / "change")
        store.save(make_snapshot(execution_id="EX-001", task_id="MP-BUG-001",
                                 changed_files=["app/auth.py"]))
        collector = DashboardCollector(
            task_store=task_store, agent_registry=agent_registry,
            workflow_store=workflow_store, runtime_store=runtime_store,
            event_store=event_store, checkpoint_store=checkpoint_store,
            change_store=store, include_change=True,
        )
        out = DashboardRenderer().render(collector.collect(), view="change")
        assert "EX-001" in out
        assert "MP-BUG-001" in out
        assert "1 execution snapshots" in out

    def test_render_validation_rows(self, factory_root, logger, event_store,
                                    task_store, agent_registry, workflow_store,
                                    runtime_store, checkpoint_store):
        from change.events import record_change_validation_completed

        record_change_validation_completed(
            logger, result=make_validation(task_id="MP-BUG-001", status="PASS",
                                           message="2 个提交关联任务"))
        collector = DashboardCollector(
            task_store=task_store, agent_registry=agent_registry,
            workflow_store=workflow_store, runtime_store=runtime_store,
            event_store=event_store, checkpoint_store=checkpoint_store,
            change_store=ChangeStore(factory_root / "change"),
            include_change=True,
        )
        out = DashboardRenderer().render(collector.collect(), view="change")
        assert "MP-BUG-001" in out
        assert "PASS" in out
        assert "1 validations" in out

    def test_change_in_view_registry(self):
        from dashboard.renderer import VIEWS

        assert "change" in VIEWS
        assert "changeflow" in VIEWS  # Phase 6E: 第十六视图 (ADR-0020)
        assert "understanding" in VIEWS  # Phase 7: 第十七视图 (ADR-0021)
        assert "provider" in VIEWS  # Phase 8A: 第十八视图 (ADR-0022)
        assert "product" in VIEWS  # Phase 9A: 第十九视图 (ADR-0026)
        assert len(VIEWS) == 19  # 6D 第十五 + 6E 第十六 + Phase 7 第十七 + 8A 第十八 + 9A 第十九

    def test_unknown_view_still_raises(self, factory_root, logger, event_store,
                                       task_store, agent_registry, workflow_store,
                                       runtime_store, checkpoint_store):
        collector = DashboardCollector(
            task_store=task_store, agent_registry=agent_registry,
            workflow_store=workflow_store, runtime_store=runtime_store,
            event_store=event_store, checkpoint_store=checkpoint_store,
        )
        with pytest.raises(ValueError, match="unknown dashboard view"):
            DashboardRenderer().render(collector.collect(), view="chagne")


class TestCollectorAggregation:
    def test_include_change_default_off(self, factory_root, logger, event_store,
                                        task_store, agent_registry, workflow_store,
                                        runtime_store, checkpoint_store):
        store = ChangeStore(factory_root / "change")
        store.save(make_snapshot())
        collector = DashboardCollector(
            task_store=task_store, agent_registry=agent_registry,
            workflow_store=workflow_store, runtime_store=runtime_store,
            event_store=event_store, checkpoint_store=checkpoint_store,
            change_store=store,  # 装配了但 include_change 默认 False
        )
        snap = collector.collect()
        assert snap.change.total == 0  # 既有 dashboard 行为/成本不变

    def test_collector_counts(self, factory_root, logger, event_store,
                              task_store, agent_registry, workflow_store,
                              runtime_store, checkpoint_store):
        store = ChangeStore(factory_root / "change")
        store.save(make_snapshot(execution_id="EX-1"))
        store.save(make_snapshot(execution_id="EX-2"))
        collector = DashboardCollector(
            task_store=task_store, agent_registry=agent_registry,
            workflow_store=workflow_store, runtime_store=runtime_store,
            event_store=event_store, checkpoint_store=checkpoint_store,
            change_store=store, include_change=True,
        )
        snap = collector.collect()
        assert snap.change.total == 2
        assert [s["execution_id"] for s in snap.change.snapshots] == ["EX-1", "EX-2"]

    def test_project_filter(self, factory_root, logger, event_store,
                            task_store, agent_registry, workflow_store,
                            runtime_store, checkpoint_store):
        store = ChangeStore(factory_root / "change")
        store.save(make_snapshot(execution_id="EX-1", project_id="markpad"))
        store.save(make_snapshot(execution_id="EX-2", project_id="other"))
        collector = DashboardCollector(
            task_store=task_store, agent_registry=agent_registry,
            workflow_store=workflow_store, runtime_store=runtime_store,
            event_store=event_store, checkpoint_store=checkpoint_store,
            change_store=store, include_change=True, project_id="markpad",
        )
        snap = collector.collect()
        assert [s["execution_id"] for s in snap.change.snapshots] == ["EX-1"]

    def test_validation_event_aggregation(self, factory_root, logger, event_store,
                                          task_store, agent_registry,
                                          workflow_store, runtime_store,
                                          checkpoint_store):
        from change.events import record_change_validation_completed

        record_change_validation_completed(
            logger, result=make_validation(task_id="MP-BUG-001", status="FAIL",
                                           message="证据不符"))
        collector = DashboardCollector(
            task_store=task_store, agent_registry=agent_registry,
            workflow_store=workflow_store, runtime_store=runtime_store,
            event_store=event_store, checkpoint_store=checkpoint_store,
            change_store=ChangeStore(factory_root / "change"),
            include_change=True,
        )
        snap = collector.collect()
        assert snap.change.validation_total == 1
        assert snap.change.validations[0]["task_id"] == "MP-BUG-001"
        assert snap.change.validations[0]["status"] == "FAIL"

    def test_change_snapshot_model_roundtrip(self):
        s = ChangeSnapshot(total=1,
                           snapshots=[make_snapshot().to_dict()],
                           validation_total=1,
                           validations=[{"task_id": "T-1", "status": "PASS",
                                         "message": "m", "seq": 3}])
        s2 = ChangeSnapshot.model_validate(s.to_dict())
        assert s2.total == 1
        assert s2.validations[0]["seq"] == 3


class TestChangeViewCli:
    def test_dashboard_change_view_cli(self, capsys, task_cli_root):
        from cli.main import main

        rc = main(["--root", str(task_cli_root), "dashboard", "--view", "change"])
        out, _ = capsys.readouterr()
        assert rc == 0
        assert "Change" in out

    def test_dashboard_change_view_json(self, capsys, task_cli_root):
        import json

        from cli.main import main

        rc = main(["--root", str(task_cli_root), "--json", "dashboard",
                   "--view", "change"])
        out, _ = capsys.readouterr()
        assert rc == 0
        data = json.loads(out)
        assert "change" in data["snapshot"]
        assert data["snapshot"]["change"]["total"] == 0

    def test_dashboard_all_no_change_panel(self, capsys, task_cli_root):
        from cli.main import main

        rc = main(["--root", str(task_cli_root), "dashboard"])
        out, _ = capsys.readouterr()
        assert rc == 0
        assert "Change" not in out  # all 视图不含 Change 面板 (仅 --view change)
