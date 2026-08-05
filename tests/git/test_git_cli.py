"""tests/git/test_git_cli.py — factory git status/diff/commits CLI (Phase 6C, ADR-0018)。

覆盖: 人类可读输出 + --json 结构 + 退出码 (0 正常/2 用法缺参/7 项目不存在/
1 无 repository/远程 URL) + 失败安全 (非 git 目录 → rc 0 + error 呈现) +
审计事件 (git.status.viewed / git.change.detected / git.commit.viewed 落库)。

项目 repository 解析: managed 项目目录 <root>/workspace/projects/<id>/project.yaml
(与 load_project_definition 一致); --repo 显式优先。
"""

from __future__ import annotations

import json
from pathlib import Path

from cli_helpers import event_types, open_events, run_cli

from git_helpers import commit_all, init_repo, write_file


def _write_project(root: Path, project_id: str, repository: str) -> Path:
    """写 managed 项目 project.yaml (repository 可空/URL, 覆盖退出码路径)。

    repository 双引号包裹: 空值写 `repository: ""` (YAML 空值 → None 会触发
    pydantic string_type 校验错误, 走不到 CLI 的 "no repository" 分支)。
    """
    d = root / "workspace" / "projects" / project_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "project.yaml").write_text(
        f"name: {project_id}\n"
        f"language: python\n"
        f'repository: "{repository}"\n'
        'description: "git cli test project"\n'
        "tech_stack: [python]\n",
        encoding="utf-8",
    )
    return d


class TestCliGitStatus:
    def test_status_output(self, cli_root, repo_path, capsys):
        _write_project(cli_root, "p-demo", str(repo_path))
        rc, out, err = run_cli(capsys, cli_root, "git", "status", "--project", "p-demo")
        assert rc == 0, err
        assert "✔" in out
        assert "[main]" in out
        assert str(repo_path) in out
        assert "File" in out  # 变更表头
        assert "(no changes)" in out

    def test_status_repo_flag_priority(self, cli_root, repo_path, tmp_path, capsys):
        """--repo 显式指定优先于 --project (即使项目不存在)。"""
        other = init_repo(tmp_path / "other")
        rc, out, _ = run_cli(capsys, cli_root, "git", "status",
                             "--project", "ghost", "--repo", str(other))
        assert rc == 0
        assert str(other) in out

    def test_status_json(self, cli_root, repo_path, capsys):
        _write_project(cli_root, "p-demo", str(repo_path))
        rc, out, _ = run_cli(capsys, cli_root, "git", "status", "--project", "p-demo", "--json")
        assert rc == 0
        data = json.loads(out)
        assert data["ok"] is True
        assert data["error"] is None
        st = data["status"]
        assert st["is_repo"] is True
        assert st["branch"] == "main"
        assert st["current_commit"]
        assert st["changes"] == []
        assert data["event_seq"] is not None

    def test_status_json_changes(self, cli_root, repo_path, capsys):
        write_file(repo_path, "wip.py", "x = 1\n")
        _write_project(cli_root, "p-demo", str(repo_path))
        rc, out, _ = run_cli(capsys, cli_root, "git", "status", "--project", "p-demo", "--json")
        assert rc == 0
        st = json.loads(out)["status"]
        assert len(st["changes"]) == 1
        assert st["changes"][0]["files"] == ["wip.py"]
        assert st["changes"][0]["status"] == "untracked"

    def test_status_missing_args_exit_2(self, cli_root, capsys):
        rc, _, err = run_cli(capsys, cli_root, "git", "status")
        assert rc == 2
        assert "specify --project or --repo" in err

    def test_status_project_not_found_exit_7(self, cli_root, capsys):
        rc, _, err = run_cli(capsys, cli_root, "git", "status", "--project", "nope")
        assert rc == 7
        assert "project not found: nope" in err

    def test_status_project_no_repository_exit_1(self, cli_root, capsys):
        _write_project(cli_root, "p-norepo", "")
        rc, _, err = run_cli(capsys, cli_root, "git", "status", "--project", "p-norepo")
        assert rc == 1
        assert "no repository" in err

    def test_status_remote_url_exit_1(self, cli_root, capsys):
        _write_project(cli_root, "p-remote", "https://github.com/x/y.git")
        rc, _, err = run_cli(capsys, cli_root, "git", "status", "--project", "p-remote")
        assert rc == 1
        assert "remote URL" in err

    def test_status_not_repo_failsafe_rc0(self, cli_root, tmp_path, capsys):
        """非 git 目录: 只读查询执行成功 (rc 0), 错误经输出呈现 (失败安全)。"""
        plain = tmp_path / "plain"
        plain.mkdir()
        rc, out, err = run_cli(capsys, cli_root, "git", "status", "--repo", str(plain))
        assert rc == 0, err
        assert "✘" in out
        assert "not a git repository" in out
        assert "(no changes)" in out

    def test_status_emits_viewed_event(self, cli_root, repo_path, capsys):
        _write_project(cli_root, "p-demo", str(repo_path))
        rc, _, _ = run_cli(capsys, cli_root, "git", "status", "--project", "p-demo")
        assert rc == 0
        with open_events(cli_root) as store:
            assert event_types(store) == ["git.status.viewed"]
            ev = store.query()[0]
            assert ev.payload["branch"] == "main"
            assert ev.payload["is_repo"] is True
            assert ev.payload["repository"] == str(repo_path)

    def test_status_event_error_result(self, cli_root, tmp_path, capsys):
        plain = tmp_path / "plain"
        plain.mkdir()
        run_cli(capsys, cli_root, "git", "status", "--repo", str(plain))
        with open_events(cli_root) as store:
            ev = store.query()[0]
            assert ev.type.value == "git.status.viewed"
            assert ev.result == "ERROR"
            assert ev.payload["error"]


class TestCliGitDiff:
    def test_diff_output(self, cli_root, repo_path, capsys):
        write_file(repo_path, "wip.py", "x = 1\n")
        _write_project(cli_root, "p-demo", str(repo_path))
        rc, out, err = run_cli(capsys, cli_root, "git", "diff", "--project", "p-demo")
        assert rc == 0, err
        assert "wip.py" in out
        assert "untracked" in out
        assert "1 changes" in out

    def test_diff_json(self, cli_root, repo_path, capsys):
        write_file(repo_path, "wip.py", "x = 1\n")
        _write_project(cli_root, "p-demo", str(repo_path))
        rc, out, _ = run_cli(capsys, cli_root, "git", "diff", "--project", "p-demo", "--json")
        assert rc == 0
        data = json.loads(out)
        assert data["ok"] is True
        assert data["count"] == 1
        assert data["changes"][0]["files"] == ["wip.py"]
        assert data["changes"][0]["status"] == "untracked"

    def test_diff_clean_zero(self, cli_root, repo_path, capsys):
        _write_project(cli_root, "p-demo", str(repo_path))
        rc, out, _ = run_cli(capsys, cli_root, "git", "diff", "--project", "p-demo")
        assert rc == 0
        assert "0 changes" in out

    def test_diff_not_repo_rc0(self, cli_root, tmp_path, capsys):
        plain = tmp_path / "plain"
        plain.mkdir()
        rc, out, _ = run_cli(capsys, cli_root, "git", "diff", "--repo", str(plain))
        assert rc == 0
        assert "0 changes" in out

    def test_diff_emits_change_detected(self, cli_root, repo_path, capsys):
        write_file(repo_path, "wip.py", "x\n")
        _write_project(cli_root, "p-demo", str(repo_path))
        run_cli(capsys, cli_root, "git", "diff", "--project", "p-demo")
        with open_events(cli_root) as store:
            assert event_types(store) == ["git.change.detected"]
            ev = store.query()[0]
            assert ev.payload["count"] == 1
            assert ev.payload["repository"] == str(repo_path)


class TestCliGitCommits:
    def test_commits_output(self, cli_root, repo_path, capsys):
        _write_project(cli_root, "p-demo", str(repo_path))
        rc, out, err = run_cli(capsys, cli_root, "git", "commits", "--project", "p-demo")
        assert rc == 0, err
        assert "feat: init" in out
        assert "feat: second" in out
        assert "main" in out      # branch 列
        assert "2 commits" in out

    def test_commits_json(self, cli_root, repo_path, capsys):
        _write_project(cli_root, "p-demo", str(repo_path))
        rc, out, _ = run_cli(capsys, cli_root, "git", "commits", "--project", "p-demo", "--json")
        assert rc == 0
        data = json.loads(out)
        assert data["ok"] is True
        assert data["count"] == 2
        assert data["commits"][0]["message"] == "feat: second"
        assert data["commits"][0]["branch"] == "main"
        assert len(data["commits"][0]["hash"]) == 40

    def test_commits_limit(self, cli_root, repo_path, capsys):
        for i in range(5):
            write_file(repo_path, f"f{i}.py", "x\n")
            commit_all(repo_path, f"feat: {i}")
        _write_project(cli_root, "p-demo", str(repo_path))
        rc, out, _ = run_cli(capsys, cli_root, "git", "commits",
                             "--project", "p-demo", "--limit", "3")
        assert rc == 0
        assert "3 commits" in out

    def test_commits_empty_repo(self, cli_root, tmp_path, capsys):
        repo = init_repo(tmp_path / "empty")
        rc, out, err = run_cli(capsys, cli_root, "git", "commits", "--repo", str(repo))
        assert rc == 0, err
        assert "0 commits" in out

    def test_commits_not_repo_rc0(self, cli_root, tmp_path, capsys):
        plain = tmp_path / "plain"
        plain.mkdir()
        rc, out, _ = run_cli(capsys, cli_root, "git", "commits", "--repo", str(plain))
        assert rc == 0
        assert "0 commits" in out

    def test_commits_emits_viewed_event(self, cli_root, repo_path, capsys):
        _write_project(cli_root, "p-demo", str(repo_path))
        run_cli(capsys, cli_root, "git", "commits", "--project", "p-demo")
        with open_events(cli_root) as store:
            assert event_types(store) == ["git.commit.viewed"]
            ev = store.query()[0]
            assert ev.payload["count"] == 2
            assert len(ev.payload["hashes"]) == 2
