"""tests/git/test_git_dashboard.py — Dashboard Git View (Phase 6C, ADR-0018)。

覆盖: collector include_git 模式 (默认关 / 开) + GitService 注入聚合
(总览/changes/commits/commit 上限/非 git error 行) + DashboardRenderer
view="git" 渲染 (面板/空态/error 行/提交表) + CLI dashboard --view git
冒烟 (workspace.yaml + 项目 repository → 渲染 + dashboard.viewed payload)。

数据源 = FactorySnapshot.git (collector 只读聚合, 同 --json 出口);
渲染 = Rich 纯文本 (无 ANSI, 管道/CI 安全)。
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
from dashboard.renderer import DashboardRenderer, VIEWS

from git.client import GitClient
from git.service import GitChangeStore, GitService

from git_helpers import commit_all, make_repo, write_file


def _collector(root: Path, logger: EventLogger, **kw) -> DashboardCollector:
    """以独立目录装配 DashboardCollector (Git View 聚合参数经 **kw)。"""
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


def _service(root: Path, repo_path: Path, project_id: str = "p-demo") -> GitService:
    return GitService(
        GitClient(repo_path), project_id=project_id,
        changes_store=GitChangeStore(root / "git"),
    )


def _write_project(root: Path, project_id: str, repository: str) -> Path:
    d = root / "workspace" / "projects" / project_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "project.yaml").write_text(
        f"name: {project_id}\nlanguage: python\nrepository: {repository}\n"
        'description: "git dashboard test"\ntech_stack: [python]\n',
        encoding="utf-8",
    )
    return d


def _write_workspace(root: Path, *project_ids: str) -> None:
    lines = ["name: ws-test", "version: 1.0.0", "projects:"]
    lines += [f"  - {pid}" for pid in project_ids]
    (root / "workspace.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestCollectorGitMode:
    def test_default_mode_git_empty(self, tmp_path, logger: EventLogger):
        """include_git 默认关: 既有 dashboard 行为/成本完全不变。"""
        snap = _collector(tmp_path, logger).collect()
        assert snap.git.total == 0
        assert snap.git.repos == []
        assert snap.git.changes == []
        assert snap.git.commits == []

    def test_git_mode_populates(self, tmp_path, logger: EventLogger, repo_path):
        write_file(repo_path, "wip.py", "x\n")
        snap = _collector(
            tmp_path, logger,
            git_services=[_service(tmp_path, repo_path)],
            include_git=True,
        ).collect()
        assert snap.git.total == 1
        repo = snap.git.repos[0]
        assert repo.project_id == "p-demo"
        assert repo.branch == "main"
        assert repo.current_commit
        assert len(repo.changes) == 1
        assert len(snap.git.changes) == 1
        assert snap.git.changes[0].project_id == "p-demo"
        assert snap.git.changes[0].status == "untracked"
        assert len(snap.git.commits) == 2

    def test_git_mode_requires_flag(self, tmp_path, logger: EventLogger, repo_path):
        """注入 services 但 include_git=False → 不聚合 (开关独立)。"""
        snap = _collector(
            tmp_path, logger, git_services=[_service(tmp_path, repo_path)]
        ).collect()
        assert snap.git.total == 0

    def test_git_mode_no_services(self, tmp_path, logger: EventLogger):
        snap = _collector(tmp_path, logger, include_git=True).collect()
        assert snap.git.total == 0

    def test_not_repo_error_row(self, tmp_path, logger: EventLogger):
        plain = tmp_path / "plain"
        plain.mkdir()
        svc = _service(tmp_path, plain)
        snap = _collector(tmp_path, logger, git_services=[svc], include_git=True).collect()
        assert snap.git.total == 1
        assert snap.git.repos[0].is_repo is False
        assert snap.git.repos[0].error

    def test_commit_limit(self, tmp_path, logger: EventLogger, repo_path):
        for i in range(4):
            write_file(repo_path, f"f{i}.py", "x\n")
            commit_all(repo_path, f"feat: {i}")
        svc = _service(tmp_path, repo_path)
        snap = _collector(
            tmp_path, logger, git_services=[svc],
            include_git=True, git_commit_limit=3,
        ).collect()
        assert len(snap.git.commits) == 3
        assert snap.git.commits[0].message == "feat: 3"  # 最新优先

    def test_git_snapshot_to_dict_json(self, tmp_path, logger: EventLogger, repo_path):
        snap = _collector(
            tmp_path, logger,
            git_services=[_service(tmp_path, repo_path)], include_git=True,
        ).collect()
        d = snap.git.model_dump(mode="json")
        assert d["total"] == 1
        assert d["repos"][0]["branch"] == "main"
        assert isinstance(d["commits"][0]["created_at"], str)


class TestGitViewRender:
    def test_render_git_panel(self, tmp_path, logger: EventLogger, repo_path):
        write_file(repo_path, "wip.py", "x\n")
        snap = _collector(
            tmp_path, logger,
            git_services=[_service(tmp_path, repo_path)], include_git=True,
        ).collect()
        out = DashboardRenderer().render(snap, view="git")
        assert "Git" in out
        assert "1 repositories" in out
        assert "p-demo" in out
        assert "main" in out
        assert "wip.py" in out
        assert "untracked" in out

    def test_render_git_no_ansi(self, tmp_path, logger: EventLogger, repo_path):
        snap = _collector(
            tmp_path, logger,
            git_services=[_service(tmp_path, repo_path)], include_git=True,
        ).collect()
        out = DashboardRenderer().render(snap, view="git")
        assert "\x1b[" not in out

    def test_render_git_empty(self, tmp_path, logger: EventLogger):
        snap = _collector(tmp_path, logger, include_git=True).collect()
        out = DashboardRenderer().render(snap, view="git")
        assert "(no repositories)" in out
        assert "(no changes)" in out
        assert "(no commits)" in out

    def test_render_git_error_row(self, tmp_path, logger: EventLogger):
        plain = tmp_path / "plain"
        plain.mkdir()
        snap = _collector(
            tmp_path, logger,
            git_services=[_service(tmp_path, plain)], include_git=True,
        ).collect()
        out = DashboardRenderer().render(snap, view="git")
        assert "not a git repository" in out

    def test_render_git_commits_rows(self, tmp_path, logger: EventLogger, repo_path):
        snap = _collector(
            tmp_path, logger,
            git_services=[_service(tmp_path, repo_path)], include_git=True,
        ).collect()
        out = DashboardRenderer().render(snap, view="git")
        assert "feat: init" in out
        assert "feat: second" in out

    def test_render_git_commit_hash_truncated(self, tmp_path, logger: EventLogger, repo_path):
        snap = _collector(
            tmp_path, logger,
            git_services=[_service(tmp_path, repo_path)], include_git=True,
        ).collect()
        out = DashboardRenderer().render(snap, view="git")
        head = snap.git.commits[0].hash[:12]
        assert head in out
        assert snap.git.commits[0].hash not in out  # 只显示 12 位短哈希

    def test_git_in_views_registry(self):
        assert "git" in VIEWS

    def test_render_git_bind_task_backfill(self, tmp_path, logger: EventLogger, repo_path):
        """变更行回填 task 关联 (GitChangeStore 映射投影)。"""
        write_file(repo_path, "wip.py", "x\n")
        svc = _service(tmp_path, repo_path)
        svc.bind_task_change("T-001", files=["wip.py"])
        snap = _collector(tmp_path, logger, git_services=[svc], include_git=True).collect()
        out = DashboardRenderer().render(snap, view="git")
        assert "T-001" in out


class TestCliDashboardGitView:
    def test_dashboard_view_git_renders(self, cli_root, repo_path, capsys):
        _write_project(cli_root, "p-demo", str(repo_path))
        _write_workspace(cli_root, "p-demo")
        rc, out, err = run_cli(capsys, cli_root, "dashboard", "--view", "git")
        assert rc == 0, err
        assert "Git" in out
        assert "p-demo" in out
        assert "main" in out
        assert "feat: init" in out

    def test_dashboard_view_git_empty_workspace(self, cli_root, capsys):
        """无 workspace.yaml → 项目集空 → Git View 空态 (失败安全, rc 0)。"""
        rc, out, err = run_cli(capsys, cli_root, "dashboard", "--view", "git")
        assert rc == 0, err
        assert "(no repositories)" in out

    def test_dashboard_view_git_event_payload(self, cli_root, repo_path, capsys):
        _write_project(cli_root, "p-demo", str(repo_path))
        _write_workspace(cli_root, "p-demo")
        rc, _, _ = run_cli(capsys, cli_root, "dashboard", "--view", "git")
        assert rc == 0
        with open_events(cli_root) as store:
            ev = store.query()[0]
            assert ev.type.value == "dashboard.viewed"
            assert ev.payload["view"] == "git"
            assert ev.payload["git_repositories"] == 1
            assert ev.payload["git_changes"] == 0
            assert ev.payload["git_commits"] == 2

    def test_dashboard_view_git_json(self, cli_root, repo_path, capsys):
        _write_project(cli_root, "p-demo", str(repo_path))
        _write_workspace(cli_root, "p-demo")
        rc, out, _ = run_cli(capsys, cli_root, "dashboard", "--view", "git", "--json")
        assert rc == 0
        import json

        data = json.loads(out)
        assert data["view"] == "git"
        assert data["snapshot"]["git"]["total"] == 1
        assert data["snapshot"]["git"]["repos"][0]["branch"] == "main"
