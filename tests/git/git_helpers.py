"""tests/git/git_helpers.py — Git 测试辅助: 临时 mock 仓库 (真实 git subprocess)。

与既有模式一致 (tests/cli/cli_helpers 等): helper 模块唯一名 git_helpers,
测试文件 basename 统一 test_git_* 前缀 (backend-developer skill 陷阱: 多非包
目录共存时同名模块互相遮蔽)。

mock 仓库 = tmp_path 下真实 git init/commit/branch (git ≥2.28 的 -b 支持,
本机 2.50)。全部经 subprocess 只读/本地操作, 测试隔离 (每仓库独立目录)。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

GIT_USER = "Factory Test"
GIT_EMAIL = "factory@test.local"


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """在 repo 内执行 git 命令 (测试辅助, 允许写仓库状态)。"""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )


def init_repo(path: Path, *, branch: str = "main") -> Path:
    """初始化一个 git 仓库 (含本地 user 配置, 不依赖全局 config)。"""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-b", branch)
    git(path, "config", "user.name", GIT_USER)
    git(path, "config", "user.email", GIT_EMAIL)
    return path


def write_file(repo: Path, rel: str, content: str = "line1\n") -> Path:
    """在仓库工作区写文件 (父目录自动创建)。"""
    f = repo / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    return f


def commit_all(repo: Path, message: str) -> str:
    """add -A + commit, 返回完整提交哈希。"""
    git(repo, "add", "-A")
    proc = git(repo, "commit", "-m", message)
    # commit 输出首行 'hash message' 拿不到完整哈希 — 直接 rev-parse
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def make_repo(path: Path, *, branch: str = "main") -> Path:
    """标准 mock 仓库: init + 2 次提交 (feat: init / feat: second)。"""
    repo = init_repo(path, branch=branch)
    write_file(repo, "a.py", "print(1)\n")
    commit_all(repo, "feat: init")
    write_file(repo, "b.py", "x = 1\n")
    commit_all(repo, "feat: second")
    return repo
