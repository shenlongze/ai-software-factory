"""tests/change/test_change_multiproject.py — 多项目 Change Intelligence 隔离。

覆盖: ChangeStore project_id 过滤 / ChangeService project_id 传播 (快照
project_id 落库) / 双项目快照互不串扰 / 项目维度 L4 验证 / Dashboard Change
View 项目过滤。
"""

from __future__ import annotations

import pytest

from git.client import GitClient

from change.service import ChangeService, ChangeStore

from git_helpers import commit_all, init_repo, write_file


@pytest.fixture
def two_projects(tmp_path):
    """两个独立项目仓库 (markpad / blog), 各含一个任务提交。"""
    markpad = init_repo(tmp_path / "markpad")
    write_file(markpad, "app/auth.py", "def login(): ...\n")
    commit_all(markpad, "MP-BUG-001: fix login crash")

    blog = init_repo(tmp_path / "blog")
    write_file(blog, "posts/api.py", "def list_posts(): ...\n")
    commit_all(blog, "MP-FEATURE-002: blog posts api")
    return markpad, blog


class TestServiceProjectIsolation:
    def test_snapshot_project_id_persisted(self, two_projects, change_dir, logger):
        markpad, _ = two_projects
        svc = ChangeService(client=GitClient(markpad), logger=logger,
                            change_store=ChangeStore(change_dir),
                            project_id="markpad")
        svc.snapshot_execution(execution_id="EX-1", task_id="MP-BUG-001")
        snap = svc.snapshots(task_id="MP-BUG-001")[0]
        assert snap.project_id == "markpad"

    def test_snapshots_filtered_by_project(self, two_projects, change_dir, logger):
        markpad, blog = two_projects
        store = ChangeStore(change_dir)
        ChangeService(client=GitClient(markpad), logger=logger,
                      change_store=store, project_id="markpad"
                      ).snapshot_execution(execution_id="EX-1", task_id="MP-BUG-001")
        ChangeService(client=GitClient(blog), logger=logger,
                      change_store=store, project_id="blog"
                      ).snapshot_execution(execution_id="EX-2", task_id="MP-FEATURE-002")
        assert [s.execution_id for s in store.list(project_id="markpad")] == ["EX-1"]
        assert [s.execution_id for s in store.list(project_id="blog")] == ["EX-2"]
        assert store.list().__len__() == 2  # 同库共存, 项目维度隔离

    def test_validate_project_scoped(self, two_projects, change_dir, logger):
        markpad, blog = two_projects
        # markpad 仓库只有 MP-BUG-001 → 该任务 PASS; 另一项目任务无关联
        svc = ChangeService(client=GitClient(markpad), logger=logger,
                            change_store=ChangeStore(change_dir),
                            project_id="markpad")
        assert svc.validate("MP-BUG-001").status == "PASS"
        assert svc.validate("MP-FEATURE-002").status == "FAIL"  # 证据在别处

    def test_analyze_project_repo(self, two_projects, change_dir, logger):
        _, blog = two_projects
        svc = ChangeService(client=GitClient(blog), logger=logger,
                            change_store=ChangeStore(change_dir),
                            project_id="blog")
        a = svc.analyze("MP-FEATURE-002", limit=10)
        assert a.task_id == "MP-FEATURE-002"
        assert len(a.commits) == 1


class TestDashboardProjectFilter:
    def test_change_view_project_filter(self, two_projects, change_dir, event_store,
                                        task_store, agent_registry, workflow_store,
                                        runtime_store, checkpoint_store):
        from dashboard.collector import DashboardCollector

        markpad, blog = two_projects
        store = ChangeStore(change_dir)
        ChangeService(client=GitClient(markpad), logger=None, change_store=store,
                      project_id="markpad"
                      ).snapshot_execution(execution_id="EX-1", task_id="MP-BUG-001")
        ChangeService(client=GitClient(blog), logger=None, change_store=store,
                      project_id="blog"
                      ).snapshot_execution(execution_id="EX-2", task_id="MP-FEATURE-002")

        collector = DashboardCollector(
            task_store=task_store, agent_registry=agent_registry,
            workflow_store=workflow_store, runtime_store=runtime_store,
            event_store=event_store, checkpoint_store=checkpoint_store,
            change_store=store, include_change=True, project_id="markpad",
        )
        snap = collector.collect()
        assert [s["execution_id"] for s in snap.change.snapshots] == ["EX-1"]

    def test_change_view_aggregates_all_projects(self, two_projects, change_dir,
                                                 event_store, task_store,
                                                 agent_registry, workflow_store,
                                                 runtime_store, checkpoint_store):
        from dashboard.collector import DashboardCollector

        markpad, blog = two_projects
        store = ChangeStore(change_dir)
        ChangeService(client=GitClient(markpad), logger=None, change_store=store,
                      project_id="markpad"
                      ).snapshot_execution(execution_id="EX-1", task_id="MP-BUG-001")
        ChangeService(client=GitClient(blog), logger=None, change_store=store,
                      project_id="blog"
                      ).snapshot_execution(execution_id="EX-2", task_id="MP-FEATURE-002")

        collector = DashboardCollector(
            task_store=task_store, agent_registry=agent_registry,
            workflow_store=workflow_store, runtime_store=runtime_store,
            event_store=event_store, checkpoint_store=checkpoint_store,
            change_store=store, include_change=True,
        )
        snap = collector.collect()
        assert snap.change.total == 2
