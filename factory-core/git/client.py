"""git/client.py — GitClient: subprocess 只读调 git (Phase 6C, ADR-0018)。

设计依据:
- phase6c-status.md: subprocess 调 git: status()/diff()/log()/current_branch()/
  current_commit(); 失败必须安全返回 (不抛未处理异常, 返回空/None + 错误信息)
- 工程规则: Git 只读 + 审计 — 本模块只有 git 读命令
  (status/diff/log/rev-parse/ls-files), 零写命令 (无 add/commit/push/merge/rebase)。

失败安全 (铁律): 所有公开方法经 _run() 统一防御 — 命令不存在 (FileNotFoundError)、
超时 (TimeoutExpired)、目录不存在/非 git 仓库 (git 自身 rc≠0)、空仓库 (无 HEAD)
一律不抛未处理异常: 返回空列表/None + GitContext.error 承载原因 (可审计)。
调用方 (GitService/CLI/Dashboard) 永不因 git 查询失败崩溃。

子进程形态: `git -C <repository> <args...>` (cwd 无关, 避免 chdir 副作用),
capture_output + text + timeout 上限; git_bin 可注入 (测试命令缺失路径)。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .models import GitChange, GitCommit, GitContext

# git 输出稳定性: 强制 C locale (Phase 6D 修复, ADR-0019 决策 5) — 系统 locale
# (如 zh_CN.UTF-8) 会让 git 错误信息中文化 ("致命错误：不是 Git 仓库"), 破坏
# 错误摘要解析 (_error_text 的 'fatal:'/'error:' 前缀剥离) 与测试断言 (英文
# 'not a git repository')。经 env 覆盖 LC_ALL/LANG 后所有 git 命令输出恒定英文。
def _git_env() -> dict[str, str]:
    """子进程 env: 系统环境 + 强制 C locale (每次调用取当前 os.environ, 测试可注入)。"""
    return {**os.environ, "LC_ALL": "C", "LANG": "C"}


# git 命令不存在 / 调用失败的返回码约定 (本模块内部, 非 CLI 退出码)
_RC_NOT_FOUND = 127
_RC_OS_ERROR = 126

# numstat 中二进制文件的行数占位符 (git 用 '-' 表示无法统计)
_NUMSTAT_BINARY = "-"


def _parse_numstat(value: str) -> int:
    """numstat 单元格 → int; 二进制占位 '-' → 0 (失败安全)。"""
    if value == _NUMSTAT_BINARY or not value:
        return 0
    try:
        return max(0, int(value))
    except ValueError:
        return 0


class GitClient:
    """单个本地仓库的只读 git 客户端 (无状态, 每次查询实时 subprocess)。"""

    def __init__(
        self,
        repository: str | Path,
        *,
        git_bin: str = "git",
        timeout: float = 30.0,
    ) -> None:
        self.repository = str(repository)
        self._git = git_bin
        self._timeout = max(1.0, timeout)

    # ------------------------------------------------------------------ 失败安全原语

    def _run(self, *args: str) -> tuple[int, str, str]:
        """git -C <repo> <args...>; 任何异常 → (非 0, '', 稳定错误摘要)。

        返回 (returncode, stdout, stderr)。stdout 永远可安全迭代 (失败为空)。
        """
        try:
            proc = subprocess.run(
                [self._git, "-C", self.repository, *args],
                capture_output=True,
                text=True,
                timeout=self._timeout,
                env=_git_env(),
            )
        except FileNotFoundError:
            return _RC_NOT_FOUND, "", f"git command not found: {self._git}"
        except subprocess.TimeoutExpired:
            return _RC_OS_ERROR, "", f"git timed out after {self._timeout:g}s"
        except OSError as exc:  # 防御兜底: 权限/路径等
            return _RC_OS_ERROR, "", f"git error: {exc}"
        return proc.returncode, proc.stdout or "", proc.stderr or ""

    def _error_text(self, rc: int, stderr: str, fallback: str) -> str:
        """失败原因摘要: git stderr 首行 (去 'fatal:'/'error:' 前缀) 或兜底文案。"""
        for line in stderr.splitlines():
            line = line.strip()
            if line:
                for prefix in ("fatal: ", "error: ", "warning: "):
                    if line.startswith(prefix):
                        line = line[len(prefix):]
                return line
        return fallback

    # ------------------------------------------------------------------ 仓库上下文

    def is_repo(self) -> bool:
        """目录是否为 git 仓库 (git rev-parse --git-dir 成功)。失败安全 → False。"""
        rc, _, _ = self._run("rev-parse", "--git-dir")
        return rc == 0

    def current_branch(self) -> str | None:
        """当前分支名; detached HEAD / 失败 → None。失败安全。"""
        rc, out, _ = self._run("symbolic-ref", "--short", "-q", "HEAD")
        if rc == 0 and out.strip() and out.strip() != "HEAD":
            return out.strip()
        rc2, out2, _ = self._run("rev-parse", "--abbrev-ref", "HEAD")
        if rc2 == 0 and out2.strip() and out2.strip() != "HEAD":
            return out2.strip()
        return None

    def current_commit(self) -> str | None:
        """当前 HEAD 完整哈希; 空仓库 (无提交) / 失败 → None。失败安全。"""
        rc, out, _ = self._run("rev-parse", "HEAD")
        if rc != 0:
            return None
        h = out.strip()
        return h or None

    def status(self) -> GitContext:
        """仓库状态上下文 (branch/current_commit/base_commit/is_repo/error)。

        非 git 目录/命令缺失: is_repo=False + error 承载原因 (调用方照常渲染);
        空仓库: is_repo=True, current_commit=None (无提交, error=None — 属合法状态)。
        """
        rc, _, stderr = self._run("rev-parse", "--git-dir")
        if rc != 0:
            return GitContext(
                repository=self.repository,
                is_repo=False,
                error=self._error_text(rc, stderr, "not a git repository"),
            )
        head = self.current_commit()
        return GitContext(
            repository=self.repository,
            branch=self.current_branch(),
            base_commit=head,
            current_commit=head,
            is_repo=True,
        )

    # ------------------------------------------------------------------ 变更

    def diff(self) -> list[GitChange]:
        """工作区变更列表 (逐文件, numstat 行数 + porcelain 状态)。

        HEAD 比较: `git diff --numstat HEAD` (暂存+未暂存); 空仓库 (无 HEAD)
        自动退化为 `git diff --numstat`; untracked 文件经
        `git ls-files --others --exclude-standard` 补充 (numstat 不含未跟踪)。
        失败安全 → []。
        """
        changes: dict[str, GitChange] = {}
        rc, out, _ = self._run("diff", "--numstat", "HEAD")
        if rc != 0:  # 空仓库 (无 HEAD) 兜底: 仅暂存区
            rc, out, _ = self._run("diff", "--numstat")
        if rc == 0:
            for line in out.splitlines():
                parts = line.split("\t")
                if len(parts) < 3:
                    continue
                path = "\t".join(parts[2:]).strip()
                if not path:
                    continue
                changes[path] = GitChange(
                    files=[path],
                    status="modified",
                    insertions=_parse_numstat(parts[0]),
                    deletions=_parse_numstat(parts[1]),
                )
        for path, status in self._status_rows().items():
            change = changes.setdefault(
                path, GitChange(files=[path], status=status)
            )
            if change.status == "modified" and status != "modified":
                change.status = status
            if status == "untracked" and change.insertions == 0 and change.deletions == 0:
                ins, dele = self._untracked_counts(path)
                change.insertions = ins
                change.deletions = dele
        return sorted(changes.values(), key=lambda c: c.files[0] if c.files else "")

    def _untracked_counts(self, path: str) -> tuple[int, int]:
        """untracked 文件的行数 (git diff --no-index /dev/null ↔ 文件; 失败安全 → 0,0)。

        numstat 不含未跟踪文件 — 行数经 /dev/null 对比补充 (纯读命令, 只读铁律);
        输出 'ins\tdel\t/dev/null => path', 只取前两个 tab 字段。
        """
        rc, out, _ = self._run("diff", "--no-index", "--numstat", "/dev/null", path)
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                return _parse_numstat(parts[0]), _parse_numstat(parts[1])
        return 0, 0

    def _status_rows(self) -> dict[str, str]:
        """`git status --porcelain=v1` → {path: 归一化状态}。失败安全 → {}。

        XY 码归一化 (五类): ??→untracked, A/C→added, D→deleted, R→renamed,
        M/T/U/其他→modified。重命名取目标路径 (porcelain 的 'old -> new')。
        """
        rc, out, _ = self._run("status", "--porcelain=v1")
        if rc != 0:
            return {}
        rows: dict[str, str] = {}
        for line in out.splitlines():
            if len(line) < 4:  # 至少 'XY path'
                continue
            xy, rest = line[:2], line[3:]
            path = rest.split(" -> ")[-1]  # 重命名 'old -> new' 取目标
            path = path.strip().strip('"')
            if not path:
                continue
            rows[path] = self._normalize_status(xy)
        return rows

    @staticmethod
    def _normalize_status(xy: str) -> str:
        """porcelain XY 码 → 五类归一化状态 (未识别归 modified)。"""
        code = (xy or "  ").strip()[:1]
        if code == "?":
            return "untracked"
        if code in ("A", "C"):
            return "added"
        if code == "D":
            return "deleted"
        if code == "R":
            return "renamed"
        return "modified"

    # ------------------------------------------------------------------ 提交历史

    def log(self, limit: int = 20) -> list[GitCommit]:
        """最近提交 (hash/author/日期/message), 倒序; 空仓库/失败 → []。

        --format 用 %x1f (单元分隔符) 切列: %H 完整哈希, %an 作者,
        %aI 严格 ISO8601 日期 (fromisoformat 可解析), %s 单行主题。
        """
        limit = max(1, min(int(limit), 500))
        rc, out, _ = self._run(
            "log", "-n", str(limit), "--format=%H%x1f%an%x1f%aI%x1f%s"
        )
        if rc != 0:
            return []
        commits: list[GitCommit] = []
        for line in out.splitlines():
            if not line:
                continue
            parts = line.split("\x1f")
            if len(parts) < 4:
                continue
            h, author, iso, subject = parts[0], parts[1], parts[2], "\x1f".join(parts[3:])
            commits.append(
                GitCommit(
                    hash=h.strip(),
                    author=author.strip(),
                    message=subject.strip(),
                    created_at=_parse_iso(iso),
                )
            )
        return commits


def _parse_iso(value: str):
    """git %aI 输出 → UTC datetime; 解析失败 → 当前 UTC (失败安全兜底)。"""
    from datetime import datetime, timezone

    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)
