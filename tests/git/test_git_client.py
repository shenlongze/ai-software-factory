"""tests/git/test_git_client.py — GitClient 只读查询 (真实 git subprocess, mock 仓库)。

覆盖: is_repo / current_branch / current_commit / status 上下文 / diff
(modified/untracked/added/deleted/renamed/binary/空仓库) / log (倒序/limit/空)
/ 状态归一化 / numstat 解析。失败安全专项见 test_git_failsafe.py。

仓库 = 临时目录真实 git init/commit (git_helpers), 每个测试独立隔离。
"""

from __future__ import annotations

import pytest

from git.client import GitClient, _parse_numstat

from git_helpers import commit_all, git, init_repo, make_repo, write_file


class TestRepoContext:
    def test_is_repo_true(self, client: GitClient):
        assert client.is_repo() is True

    def test_is_repo_false(self, tmp_path):
        assert GitClient(tmp_path).is_repo() is False

    def test_current_branch_main(self, client: GitClient):
        assert client.current_branch() == "main"

    def test_current_branch_other(self, repo_path):
        git(repo_path, "checkout", "-q", "-b", "feature/x")
        assert GitClient(repo_path).current_branch() == "feature/x"

    def test_current_branch_detached_head(self, repo_path):
        """detached HEAD: symbolic-ref 失败, abbrev-ref 输出 HEAD → None。"""
        head = git(repo_path, "rev-parse", "HEAD").stdout.strip()
        git(repo_path, "checkout", "-q", head)
        assert GitClient(repo_path).current_branch() is None

    def test_current_commit_full_hash(self, client: GitClient):
        h = client.current_commit()
        assert h and len(h) == 40
        assert h == git(client.repository, "rev-parse", "HEAD").stdout.strip()

    def test_current_commit_empty_repo(self, tmp_path):
        """空仓库 (init 无提交): 无 HEAD 可指 → None (失败安全)。"""
        repo = init_repo(tmp_path / "empty")
        assert GitClient(repo).current_commit() is None

    def test_status_repo_context(self, client: GitClient):
        ctx = client.status()
        assert ctx.is_repo is True
        assert ctx.branch == "main"
        assert ctx.current_commit is not None
        assert ctx.base_commit == ctx.current_commit
        assert ctx.repository == client.repository
        assert ctx.error is None

    def test_status_empty_repo(self, tmp_path):
        """空仓库: is_repo=True 但无提交可指, error=None (合法状态非失败)。"""
        repo = init_repo(tmp_path / "empty")
        ctx = GitClient(repo).status()
        assert ctx.is_repo is True
        assert ctx.current_commit is None
        assert ctx.error is None

    def test_status_not_repo_error(self, tmp_path):
        ctx = GitClient(tmp_path).status()
        assert ctx.is_repo is False
        assert "not a git repository" in (ctx.error or "")


class TestDiff:
    def test_diff_clean_repo_empty(self, client: GitClient):
        assert client.diff() == []

    def test_diff_modified_counts(self, repo_path, client: GitClient):
        write_file(repo_path, "a.py", "print(1)\nprint(2)\n")
        changes = client.diff()
        assert len(changes) == 1
        c = changes[0]
        assert c.files == ["a.py"]
        assert c.status == "modified"
        assert c.insertions == 1
        assert c.deletions == 0

    def test_diff_modified_deletions(self, repo_path, client: GitClient):
        write_file(repo_path, "a.py", "")  # 删光原有 1 行
        changes = client.diff()
        assert len(changes) == 1
        assert changes[0].status == "modified"
        assert changes[0].insertions == 0
        assert changes[0].deletions == 1

    def test_diff_untracked(self, repo_path, client: GitClient):
        write_file(repo_path, "new.py", "x = 1\n")
        changes = client.diff()
        assert len(changes) == 1
        assert changes[0].files == ["new.py"]
        assert changes[0].status == "untracked"

    def test_diff_added_staged(self, repo_path, client: GitClient):
        write_file(repo_path, "new.py", "x = 1\n")
        git(repo_path, "add", "new.py")
        changes = client.diff()
        assert len(changes) == 1
        assert changes[0].status == "added"
        assert changes[0].files == ["new.py"]

    def test_diff_deleted(self, repo_path, client: GitClient):
        git(repo_path, "rm", "-q", "a.py")
        changes = client.diff()
        deleted = [c for c in changes if c.status == "deleted"]
        assert len(deleted) == 1
        assert deleted[0].files == ["a.py"]

    def test_diff_renamed(self, repo_path, client: GitClient):
        git(repo_path, "mv", "a.py", "c.py")
        changes = client.diff()
        renamed = [c for c in changes if c.status == "renamed"]
        assert len(renamed) == 1
        assert renamed[0].files == ["c.py"]  # 重命名取目标路径

    def test_diff_binary_counts_zero(self, repo_path, client: GitClient):
        (repo_path / "bin.dat").write_bytes(b"\x00\x01\x02")
        git(repo_path, "add", "bin.dat")
        git(repo_path, "commit", "-m", "feat: bin")
        (repo_path / "bin.dat").write_bytes(b"\x00\x01\x02\x03")
        changes = client.diff()
        c = next(x for x in changes if x.files == ["bin.dat"])
        assert c.insertions == 0  # numstat '-' → 0 (失败安全)
        assert c.deletions == 0

    def test_diff_sorted_by_path(self, repo_path, client: GitClient):
        write_file(repo_path, "b.py", "x\n")
        write_file(repo_path, "a.py", "y\n")
        assert [c.files[0] for c in client.diff()] == ["a.py", "b.py"]

    def test_diff_mixed_statuses(self, repo_path, client: GitClient):
        """一个 modified + 一个 untracked 同屏, 状态各自归一化。"""
        write_file(repo_path, "a.py", "print(1)\nprint(2)\n")
        write_file(repo_path, "u.py", "z\n")
        by_path = {c.files[0]: c.status for c in client.diff()}
        assert by_path == {"a.py": "modified", "u.py": "untracked"}

    def test_diff_empty_repo_untracked(self, tmp_path):
        repo = init_repo(tmp_path / "empty")
        write_file(repo, "x.py", "print(1)\n")
        changes = GitClient(repo).diff()
        assert len(changes) == 1
        assert changes[0].status == "untracked"

    def test_diff_empty_repo_staged_added(self, tmp_path):
        repo = init_repo(tmp_path / "empty")
        write_file(repo, "x.py", "print(1)\n")
        git(repo, "add", "x.py")
        changes = GitClient(repo).diff()
        assert len(changes) == 1
        assert changes[0].status == "added"

    def test_diff_not_repo_empty(self, tmp_path):
        assert GitClient(tmp_path).diff() == []


class TestLog:
    def test_log_commits_desc(self, client: GitClient):
        commits = client.log()
        assert len(commits) == 2
        assert commits[0].message == "feat: second"   # 最新在前
        assert commits[1].message == "feat: init"
        assert commits[0].hash != commits[1].hash
        assert commits[0].author == "Factory Test"
        assert commits[0].created_at.tzinfo is not None
        assert isinstance(commits[0].hash, str) and len(commits[0].hash) == 40

    def test_log_limit(self, repo_path, client: GitClient):
        for i in range(5):
            write_file(repo_path, f"f{i}.py", f"x = {i}\n")
            commit_all(repo_path, f"feat: {i}")
        assert len(client.log()) == 7
        assert len(client.log(limit=3)) == 3
        assert client.log(limit=3)[0].message == "feat: 4"

    def test_log_limit_clamped(self, client: GitClient):
        """limit 越界钳制: ≤1 → 1, ≥500 → 500 (不抛错)。"""
        assert len(client.log(limit=0)) == 1
        assert len(client.log(limit=-5)) == 1
        assert len(client.log(limit=9999)) == 2  # 仓库只有 2 提交

    def test_log_empty_repo(self, tmp_path):
        repo = init_repo(tmp_path / "empty")
        assert GitClient(repo).log() == []

    def test_log_not_repo_empty(self, tmp_path):
        assert GitClient(tmp_path).log() == []


class TestStatusNormalization:
    @pytest.mark.parametrize("xy,expected", [
        ("??", "untracked"),
        ("A ", "added"),
        ("C ", "added"),
        ("D ", "deleted"),
        ("R ", "renamed"),
        ("M ", "modified"),
        (" T", "modified"),
        (" U", "modified"),
        ("MM", "modified"),
        ("  ", "modified"),
        ("X?", "modified"),
    ])
    def test_normalize_status(self, xy: str, expected: str):
        assert GitClient._normalize_status(xy) == expected


class TestParseNumstat:
    def test_parse_positive(self):
        assert _parse_numstat("5") == 5
        assert _parse_numstat("0") == 0

    def test_parse_binary_placeholder(self):
        assert _parse_numstat("-") == 0

    def test_parse_empty(self):
        assert _parse_numstat("") == 0

    def test_parse_garbage(self):
        assert _parse_numstat("abc") == 0
        assert _parse_numstat("-3") == 0
        assert _parse_numstat("1.5") == 0
