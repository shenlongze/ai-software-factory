"""tests/exec/exec_helpers.py — Execution Extension 测试辅助 (唯一名 helper)。

多非包测试目录共存陷阱: helper 模块名与测试文件 basename 必须唯一 (backend-
developer skill); 本文件只被 tests/exec/ 使用, 名称不与任何既有 helper 冲突。

内容:
- write_files(dir, mapping): 批量写文件 (父目录自动创建)。
- git_repo(dir, files): 建真实 git 仓库 (本地身份 + 基线提交; 不依赖全局
  user.name/email — CI/新机无全局身份 commit 必失败)。
- git_diff_text(workdir, before, after): before→after 的真实 git diff 输出
  (合法 git-applyable 补丁 — 从真实 git 产出, 保证沙箱 git apply 可应用)。
- FakeProvider: ProviderInterface mock (可配置 content/error/usage; 记录调用)。
- make_request(...): ExecutionRequest 构造 (缺省字段齐全)。
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from exec.models import ExecutionRequest
from exec.provider import ProviderRequest, ProviderResponse


def write_files(base: Path, files: dict[str, str]) -> None:
    """批量写文件到 base 目录 (父目录自动创建)。"""
    base.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        f = base / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def git_repo(repo: Path, files: dict[str, str] | None = None) -> str:
    """建真实 git 仓库 (本地身份 + 基线提交); 返回基线 commit hash。"""
    repo.mkdir(parents=True, exist_ok=True)
    init = _git(repo, "init", "-q", "-b", "main")
    if init.returncode != 0:  # 老 git 退化 init + checkout
        _git(repo, "init", "-q")
        _git(repo, "checkout", "-q", "-b", "main")
    _git(repo, "config", "user.name", "test")
    _git(repo, "config", "user.email", "test@local")
    if files:
        write_files(repo, files)
    _git(repo, "add", "-A")
    commit = _git(repo, "commit", "-q", "-m", "baseline")
    if commit.returncode == 0:
        return _git(repo, "rev-parse", "HEAD").stdout.strip()
    return ""  # 空仓库 (nothing to commit) → 无基线


def git_diff_text(workdir: Path, before: dict[str, str], after: dict[str, str]) -> str:
    """before→after 的真实 git diff 输出 (合法 git-applyable 补丁文本)。

    从真实 git 仓库产出 (init + 基线提交 + 覆盖 + diff) — 保证沙箱 git apply
    可应用 (hunk 头/上下文真实, 不手写 diff 格式)。
    """
    repo = workdir / "diff-src"
    git_repo(repo, before)
    write_files(repo, after)
    return _git(repo, "diff").stdout


class FakeProvider:
    """ProviderInterface mock: 固定 content/error/usage; 记录 generate 调用。"""

    provider_id = "mock"

    def __init__(
        self,
        content: str = "",
        *,
        error: str | None = None,
        usage: dict[str, Any] | None = None,
    ) -> None:
        self._content = content
        self._error = error
        self._usage = usage or {}
        self.calls: list[ProviderRequest] = []

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        if self._error:
            return ProviderResponse(content="", error=self._error)
        return ProviderResponse(content=self._content, usage=dict(self._usage))


def make_request(
    *,
    request_id: str = "EXR-test-1",
    task_id: str = "T-101",
    objective: str = "fix the sub function bug",
    project_dir: str | Path = "/tmp/project",
    requirement: str = "",
    capabilities: list[str] | None = None,
    provider_id: str = "mock",
) -> ExecutionRequest:
    """ExecutionRequest 构造 (input 携带 project_dir/provider_id/employee_id)。"""
    return ExecutionRequest(
        id=request_id,
        task_id=task_id,
        objective=objective,
        requirement=requirement,
        input={
            "project_dir": str(project_dir),
            "provider_id": provider_id,
            "employee_id": "E-1",
            "capabilities": capabilities or [],
        },
    )
