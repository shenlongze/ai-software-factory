"""tests/git/test_git_service.py — GitService 查询聚合 + task↔git 关联 + GitChangeStore 持久化。

覆盖: get_status (仓库/空仓库/非 git) / get_changes (task 回填/过滤) /
get_commits (branch 回填/limit/task 过滤) / bind_task_change (缺省文件=全部变更、
显式文件、行数对账、任务存在性校验、旧 Task 兼容、commits 去重) / bound_changes
项目过滤 / GitChangeStore 增查映射 (save/load/list/task_by_path/task_by_commit)。

GitChangeStore 失败安全 (损坏读) 见 test_git_failsafe.py。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from git.client import GitClient
from git.models import GitChange
from git.service import GitChangeStore, GitService, GitTaskNotFoundError

from git_helpers import commit_all, init_repo, write_file


class TestGetStatus:
    def test_status_repo_context(self, service: GitService):
        ctx = service.get_status()
        assert ctx.is_repo is True
        assert ctx.project_id == "markpad"
        assert ctx.branch == "main"
        assert ctx.current_commit is not None
        assert ctx.error is None

    def test_status_includes_changes(self, repo_path, service: GitService):
        write_file(repo_path, "wip.py", "y = 2\n")
        ctx = service.get_status()
        assert len(ctx.changes) == 1
        assert ctx.changes[0].files == ["wip.py"]
        assert ctx.changes[0].status == "untracked"

    def test_status_empty_repo(self, tmp_path, changes_dir):
        repo = init_repo(tmp_path / "empty")
        svc = GitService(GitClient(repo), project_id="p", changes_store=GitChangeStore(changes_dir))
        ctx = svc.get_status()
        assert ctx.is_repo is True
        assert ctx.current_commit is None
        assert ctx.error is None

    def test_status_not_repo_failsafe(self, tmp_path, changes_dir):
        svc = GitService(GitClient(tmp_path), project_id="p", changes_store=GitChangeStore(changes_dir))
        ctx = svc.get_status()
        assert ctx.is_repo is False
        assert ctx.error

    def test_status_no_changes_clean(self, service: GitService):
        assert service.get_status().changes == []


class TestGetChanges:
    def test_changes_task_backfill(self, repo_path, service: GitService):
        """bind 后实时变更回填 task_id + project_id。"""
        write_file(repo_path, "wip.py", "x\n")
        service.bind_task_change("T-001", files=["wip.py"])
        changes = service.get_changes()
        assert len(changes) == 1
        assert changes[0].task_id == "T-001"
        assert changes[0].project_id == "markpad"

    def test_changes_clean_empty(self, service: GitService):
        assert service.get_changes() == []

    def test_changes_filter_by_task(self, repo_path, service: GitService):
        write_file(repo_path, "wip.py", "x\n")
        service.bind_task_change("T-001", files=["wip.py"])
        assert len(service.get_changes(task_id="T-001")) == 1
        assert service.get_changes(task_id="T-999") == []

    def test_changes_old_task_no_link_none(self, repo_path, service: GitService):
        """旧 Task 兼容: 无关联路径 task_id=None。"""
        write_file(repo_path, "wip.py", "x\n")
        assert service.get_changes()[0].task_id is None

    def test_changes_not_repo_empty(self, tmp_path, changes_dir):
        svc = GitService(GitClient(tmp_path), changes_store=GitChangeStore(changes_dir))
        assert svc.get_changes() == []


class TestGetCommits:
    def test_commits_branch_backfill(self, service: GitService):
        commits = service.get_commits()
        assert len(commits) == 2
        assert commits[0].message == "feat: second"
        assert commits[0].branch == "main"  # 查询时分支回填

    def test_commits_limit(self, repo_path, service: GitService):
        for i in range(4):
            write_file(repo_path, f"f{i}.py", "x\n")
            commit_all(repo_path, f"feat: {i}")
        assert len(service.get_commits(limit=3)) == 3

    def test_commits_task_backfill(self, repo_path, service: GitService):
        head = service.get_commits()[0].hash
        service.bind_task_change("T-001", commits=[head])
        out = service.get_commits()
        assert next(c for c in out if c.hash == head).task_id == "T-001"
        assert next(c for c in out if c.hash != head).task_id is None

    def test_commits_filter_by_task(self, repo_path, service: GitService):
        head = service.get_commits()[0].hash
        service.bind_task_change("T-001", commits=[head])
        assert len(service.get_commits(task_id="T-001")) == 1
        assert service.get_commits(task_id="T-999") == []

    def test_commits_empty_repo(self, tmp_path, changes_dir):
        repo = init_repo(tmp_path / "empty")
        svc = GitService(GitClient(repo), changes_store=GitChangeStore(changes_dir))
        assert svc.get_commits() == []

    def test_commits_not_repo_empty(self, tmp_path, changes_dir):
        svc = GitService(GitClient(tmp_path), changes_store=GitChangeStore(changes_dir))
        assert svc.get_commits() == []


class TestBindTaskChange:
    def test_bind_default_files_all_changes(self, repo_path, service: GitService, store: GitChangeStore):
        write_file(repo_path, "w1.py", "a\n")
        write_file(repo_path, "w2.py", "b\n")
        c = service.bind_task_change("T-001")
        assert c.task_id == "T-001"
        assert c.files == ["w1.py", "w2.py"]
        assert c.project_id == "markpad"
        assert c.repository == str(repo_path)
        # 持久化: store 落盘, 重新加载一致
        assert [x.id for x in store.load()] == [c.id]
        assert store.list(task_id="T-001")[0].id == c.id

    def test_bind_explicit_files(self, service: GitService):
        """显式 files: 不在实时变更中的路径照常记录 (0 行数)。"""
        c = service.bind_task_change("T-001", files=["a.py", "b.py"])
        assert c.files == ["a.py", "b.py"]
        assert c.insertions == 0
        assert c.deletions == 0

    def test_bind_counts_from_live_diff(self, repo_path, service: GitService):
        write_file(repo_path, "a.py", "print(1)\nprint(2)\n")
        c = service.bind_task_change("T-001", files=["a.py"])
        assert c.insertions == 1
        assert c.deletions == 0

    def test_bind_files_dedup_sorted(self, service: GitService):
        c = service.bind_task_change("T-001", files=["b.py", "a.py", "b.py"])
        assert c.files == ["a.py", "b.py"]

    def test_bind_commits_dedup(self, service: GitService):
        c = service.bind_task_change("T-001", commits=["abc", "abc", "def"])
        assert c.commits == ["abc", "def"]

    def test_bind_task_not_found_raises(self, repo_path, tmp_path, changes_dir):
        from tasks.models import Task
        from tasks.store import TaskStore

        svc = GitService(
            GitClient(repo_path),
            task_store=TaskStore(tmp_path / "tasks"),
            changes_store=GitChangeStore(changes_dir),
        )
        with pytest.raises(GitTaskNotFoundError):
            svc.bind_task_change("T-nope")

    def test_bind_task_exists_ok(self, repo_path, tmp_path, changes_dir):
        from tasks.models import Task
        from tasks.store import TaskStore

        ts = TaskStore(tmp_path / "tasks")
        ts.create(Task(id="T-001", title="x"))
        svc = GitService(
            GitClient(repo_path),
            task_store=ts,
            changes_store=GitChangeStore(changes_dir),
        )
        c = svc.bind_task_change("T-001")
        assert c.task_id == "T-001"

    def test_bind_no_task_store_old_task_compat(self, service: GitService):
        """未装配 task_store: 任意 task_id 可绑 (旧 Task/纯服务场景兼容)。"""
        c = service.bind_task_change("legacy-1")
        assert c.task_id == "legacy-1"

    def test_bind_status_detected_default(self, service: GitService):
        c = service.bind_task_change("T-001")
        assert c.status == "detected"

    def test_bound_changes_persisted(self, repo_path, service: GitService):
        assert service.bound_changes() == []
        c = service.bind_task_change("T-001", files=["a.py"])
        assert len(service.bound_changes()) == 1
        assert service.bound_changes()[0].id == c.id

    def test_bound_changes_filter_task(self, service: GitService):
        service.bind_task_change("T-001", files=["a.py"])
        service.bind_task_change("T-002", files=["b.py"])
        assert len(service.bound_changes(task_id="T-001")) == 1
        assert service.bound_changes(task_id="T-001")[0].files == ["a.py"]

    def test_bound_changes_filter_project(self, repo_path, tmp_path, changes_dir):
        """项目维度隔离: 同 store 不同 service 只看到自己的绑定。"""
        store = GitChangeStore(changes_dir)
        svc_a = GitService(GitClient(repo_path), project_id="p-a", changes_store=store)
        svc_b = GitService(GitClient(repo_path), project_id="p-b", changes_store=store)
        svc_a.bind_task_change("T-1", files=["a.py"])
        svc_b.bind_task_change("T-2", files=["b.py"])
        assert [c.task_id for c in svc_a.bound_changes()] == ["T-1"]
        assert [c.task_id for c in svc_b.bound_changes()] == ["T-2"]


class TestGitChangeStore:
    def test_save_load_roundtrip(self, store: GitChangeStore):
        c = GitChange(task_id="T-1", files=["a.py"], insertions=2)
        store.save(c)
        back = store.load()
        assert len(back) == 1
        assert back[0].task_id == "T-1"
        assert back[0].files == ["a.py"]
        assert back[0].insertions == 2
        assert back[0].id == c.id

    def test_save_appends_in_order(self, store: GitChangeStore):
        store.save(GitChange(task_id="T-1", files=["a"]))
        store.save(GitChange(task_id="T-2", files=["b"]))
        assert [c.task_id for c in store.load()] == ["T-1", "T-2"]

    def test_save_creates_parent_dirs(self, tmp_path):
        store = GitChangeStore(tmp_path / "deep" / "nested")
        store.save(GitChange(task_id="T-1", files=["a"]))
        assert store.path.is_file()

    def test_list_filter_task(self, store: GitChangeStore):
        store.save(GitChange(task_id="T-1", files=["a"]))
        store.save(GitChange(task_id="T-2", files=["b"]))
        assert len(store.list(task_id="T-1")) == 1
        assert store.list(task_id="T-1")[0].files == ["a"]
        assert store.list(task_id="T-x") == []

    def test_list_filter_project(self, store: GitChangeStore):
        store.save(GitChange(task_id="T-1", project_id="p1", files=["a"]))
        store.save(GitChange(task_id="T-2", project_id="p2", files=["b"]))
        assert [c.task_id for c in store.list(project_id="p1")] == ["T-1"]
        assert store.list(project_id="p9") == []

    def test_list_filters_both(self, store: GitChangeStore):
        store.save(GitChange(task_id="T-1", project_id="p1", files=["a"]))
        store.save(GitChange(task_id="T-1", project_id="p2", files=["b"]))
        assert len(store.list(task_id="T-1", project_id="p1")) == 1

    def test_task_by_path_latest_wins(self, store: GitChangeStore):
        """path → task_id 映射: 最近绑定优先。"""
        store.save(GitChange(task_id="T-1", files=["a.py"]))
        store.save(GitChange(task_id="T-2", files=["a.py"]))
        assert store.task_by_path()["a.py"] == "T-2"

    def test_task_by_path_skips_unbound(self, store: GitChangeStore):
        store.save(GitChange(task_id=None, files=["a.py"]))
        assert store.task_by_path() == {}

    def test_task_by_commit(self, store: GitChangeStore):
        store.save(GitChange(task_id="T-1", commits=["abc", "def"]))
        store.save(GitChange(task_id="T-2", commits=["abc"]))  # 最近绑定优先
        assert store.task_by_commit()["abc"] == "T-2"
        assert store.task_by_commit()["def"] == "T-1"

    def test_default_path_home(self):
        s = GitChangeStore()
        assert s.path == Path.home() / ".factory" / "git" / "changes.json"

    def test_path_accepts_file(self, tmp_path):
        f = tmp_path / "custom.json"
        s = GitChangeStore(f)
        assert s.path == f

    def test_path_accepts_dir(self, tmp_path):
        d = tmp_path / "git"
        s = GitChangeStore(d)
        assert s.path == d / "changes.json"
