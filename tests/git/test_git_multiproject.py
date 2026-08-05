"""tests/git/test_git_multiproject.py — 多项目聚合 + 空仓库 (Phase 6C, ADR-0018)。

覆盖: 两个仓库 → Git View 聚合 (total/changes 合并/commits 跨仓库按时间倒序) /
项目维度隔离 (bound_changes 按 project_id) / CLI 两项目 git status /
空仓库全链路 (status/diff/log/commits CLI/dashboard error-free 空态)。
"""

from __future__ import annotations

from pathlib import Path

from agents.registry import AgentRegistry
from agents.store import AgentStore
from events.logger import EventLogger
from recovery.checkpoint import CheckpointStore
from runtime.store import RuntimeStore
from tasks.store import TaskStore
from workflows.store import WorkflowStore

from cli_helpers import open_events, run_cli

from dashboard.collector import DashboardCollector
from dashboard.renderer import DashboardRenderer

from git.client import GitClient
from git.service import GitChangeStore, GitService

from git_helpers import commit_all, init_repo, make_repo, write_file


def _collector(root: Path, logger: EventLogger, **kw) -> DashboardCollector:
    return DashboardCollector(
        task_store=TaskStore(root / "tasks"),
        agent_registry=AgentRegistry(AgentStore(root / "agents")),
        workflow_store=WorkflowStore(root / "workflows"),
        runtime_store=RuntimeStore(root / "runtimes"),
        catalog_store=None,
        event_store=logger.store,
        checkpoint_store=CheckpointStore(root / "checkpoints"),
        **kw,
    )


def _write_project(root: Path, project_id: str, repository: str) -> None:
    d = root / "workspace" / "projects" / project_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "project.yaml").write_text(
        f"name: {project_id}\nlanguage: python\nrepository: {repository}\n"
        'description: "git multi test"\ntech_stack: [python]\n',
        encoding="utf-8",
    )


def _write_workspace(root: Path, *project_ids: str) -> None:
    lines = ["name: ws-multi", "version: 1.0.0", "projects:"]
    lines += [f"  - {pid}" for pid in project_ids]
    (root / "workspace.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestMultiProjectAggregation:
    def test_two_repos_aggregated(self, tmp_path, logger: EventLogger):
        repo_a = make_repo(tmp_path / "a")
        repo_b = make_repo(tmp_path / "b")
        write_file(repo_a, "wip-a.py", "x\n")
        store = GitChangeStore(tmp_path / "git")
        svc_a = GitService(GitClient(repo_a), project_id="p-a", changes_store=store)
        svc_b = GitService(GitClient(repo_b), project_id="p-b", changes_store=store)
        snap = _collector(
            tmp_path, logger, git_services=[svc_a, svc_b], include_git=True
        ).collect()
        assert snap.git.total == 2
        assert {r.project_id for r in snap.git.repos} == {"p-a", "p-b"}
        assert len(snap.git.changes) == 1
        assert snap.git.changes[0].project_id == "p-a"
        assert len(snap.git.commits) == 4  # 2 + 2

    def test_commits_sorted_desc_across_repos(self, tmp_path, logger: EventLogger):
        """跨仓库提交按 created_at 倒序 (最新在前)。"""
        repo_a = make_repo(tmp_path / "a")
        repo_b = make_repo(tmp_path / "b")
        store = GitChangeStore(tmp_path / "git")
        svc_a = GitService(GitClient(repo_a), project_id="p-a", changes_store=store)
        svc_b = GitService(GitClient(repo_b), project_id="p-b", changes_store=store)
        snap = _collector(
            tmp_path, logger, git_services=[svc_a, svc_b], include_git=True
        ).collect()
        dates = [c.created_at for c in snap.git.commits]
        assert dates == sorted(dates, reverse=True)

    def test_two_repos_render(self, tmp_path, logger: EventLogger):
        repo_a = make_repo(tmp_path / "a")
        repo_b = make_repo(tmp_path / "b")
        store = GitChangeStore(tmp_path / "git")
        svc_a = GitService(GitClient(repo_a), project_id="p-a", changes_store=store)
        svc_b = GitService(GitClient(repo_b), project_id="p-b", changes_store=store)
        snap = _collector(
            tmp_path, logger, git_services=[svc_a, svc_b], include_git=True
        ).collect()
        out = DashboardRenderer().render(snap, view="git")
        assert "2 repositories" in out
        assert "p-a" in out and "p-b" in out

    def test_project_scoped_bound_changes(self, tmp_path, logger: EventLogger, repo_path):
        """项目维度隔离: 同 store 两 service, bound_changes 各看各的。"""
        store = GitChangeStore(tmp_path / "git")
        svc_a = GitService(GitClient(repo_path), project_id="p-a", changes_store=store)
        svc_b = GitService(GitClient(repo_path), project_id="p-b", changes_store=store)
        svc_a.bind_task_change("T-1", files=["a.py"])
        svc_b.bind_task_change("T-2", files=["b.py"])
        assert [c.task_id for c in svc_a.bound_changes()] == ["T-1"]
        assert [c.task_id for c in svc_b.bound_changes()] == ["T-2"]

    def test_cli_git_status_two_projects(self, cli_root, tmp_path, capsys):
        repo_a = make_repo(tmp_path / "a")
        repo_b = make_repo(tmp_path / "b")
        _write_project(cli_root, "p-a", str(repo_a))
        _write_project(cli_root, "p-b", str(repo_b))
        rc, out, err = run_cli(capsys, cli_root, "git", "status", "--project", "p-b")
        assert rc == 0, err
        assert str(repo_b) in out
        assert str(repo_a) not in out

    def test_cli_dashboard_view_git_multi(self, cli_root, tmp_path, capsys):
        repo_a = make_repo(tmp_path / "a")
        repo_b = make_repo(tmp_path / "b")
        _write_project(cli_root, "p-a", str(repo_a))
        _write_project(cli_root, "p-b", str(repo_b))
        _write_workspace(cli_root, "p-a", "p-b")
        rc, out, err = run_cli(capsys, cli_root, "dashboard", "--view", "git")
        assert rc == 0, err
        assert "2 repositories" in out
        assert "p-a" in out and "p-b" in out

    def test_cli_dashboard_git_event_payload_multi(self, cli_root, tmp_path, capsys):
        repo_a = make_repo(tmp_path / "a")
        repo_b = make_repo(tmp_path / "b")
        _write_project(cli_root, "p-a", str(repo_a))
        _write_project(cli_root, "p-b", str(repo_b))
        _write_workspace(cli_root, "p-a", "p-b")
        run_cli(capsys, cli_root, "dashboard", "--view", "git")
        with open_events(cli_root) as store:
            ev = store.query()[0]
            assert ev.payload["git_repositories"] == 2
            assert ev.payload["git_commits"] == 4


class TestEmptyRepository:
    def test_status_empty_repo(self, tmp_path):
        repo = init_repo(tmp_path / "empty")
        ctx = GitClient(repo).status()
        assert ctx.is_repo is True
        assert ctx.current_commit is None
        assert ctx.branch == "main"  # init -b main 后无提交, 分支名仍可读
        assert ctx.error is None

    def test_diff_empty_repo(self, tmp_path):
        repo = init_repo(tmp_path / "empty")
        assert GitClient(repo).diff() == []
        write_file(repo, "x.py", "print(1)\n")
        changes = GitClient(repo).diff()
        assert len(changes) == 1
        assert changes[0].status == "untracked"

    def test_log_empty_repo(self, tmp_path):
        repo = init_repo(tmp_path / "empty")
        assert GitClient(repo).log() == []

    def test_service_status_empty_repo(self, tmp_path, changes_dir):
        repo = init_repo(tmp_path / "empty")
        svc = GitService(GitClient(repo), project_id="p", changes_store=GitChangeStore(changes_dir))
        ctx = svc.get_status()
        assert ctx.is_repo is True
        assert ctx.current_commit is None
        assert svc.get_commits() == []

    def test_cli_commits_empty_repo(self, cli_root, tmp_path, capsys):
        repo = init_repo(tmp_path / "empty")
        rc, out, err = run_cli(capsys, cli_root, "git", "commits", "--repo", str(repo))
        assert rc == 0, err
        assert "0 commits" in out
        with open_events(cli_root) as store:
            assert [e.type.value for e in store.query()] == ["git.commit.viewed"]

    def test_cli_status_empty_repo(self, cli_root, tmp_path, capsys):
        repo = init_repo(tmp_path / "empty")
        rc, out, _ = run_cli(capsys, cli_root, "git", "status", "--repo", str(repo))
        assert rc == 0
        assert "(no commits)" in out  # current_commit None → 占位
        assert "(no changes)" in out

    def test_cli_diff_empty_repo_untracked(self, cli_root, tmp_path, capsys):
        repo = init_repo(tmp_path / "empty")
        write_file(repo, "x.py", "print(1)\n")
        rc, out, _ = run_cli(capsys, cli_root, "git", "diff", "--repo", str(repo))
        assert rc == 0
        assert "x.py" in out
        assert "untracked" in out

    def test_dashboard_empty_repo(self, tmp_path, logger: EventLogger):
        repo = init_repo(tmp_path / "empty")
        svc = GitService(GitClient(repo), project_id="p-empty", changes_store=GitChangeStore(tmp_path / "git"))
        snap = _collector(tmp_path, logger, git_services=[svc], include_git=True).collect()
        assert snap.git.total == 1
        assert snap.git.repos[0].current_commit is None
        assert snap.git.changes == []
        assert snap.git.commits == []
        out = DashboardRenderer().render(snap, view="git")
        assert "(no commits)" in out

    def test_commit_after_empty_repo(self, tmp_path):
        """空仓库提交后 current_commit 可读 (init → commit 生命周期)。"""
        repo = init_repo(tmp_path / "empty")
        write_file(repo, "x.py", "print(1)\n")
        commit_all(repo, "feat: first")
        client = GitClient(repo)
        assert client.current_commit() is not None
        assert len(client.log()) == 1
        assert client.log()[0].message == "feat: first"
