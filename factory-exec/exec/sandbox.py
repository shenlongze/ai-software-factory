"""factory-exec/exec/sandbox.py — Sandbox MVP (临时目录项目副本 + git 追踪 + patch 导出)。

设计依据 (docs/architecture/phase-a-execution-mvp-design.md §5):
```
workspace clone:  项目副本 → 临时目录 (git clone/copy)
change tracking:  git status/diff 追踪修改
patch export:     git diff → patch 文件
```

沙箱铁律 (设计 §5 为什么不用直接修改):
1. 安全: Agent 错误/恶意行为不伤真实环境
2. 可审计: 修改前后 diff 全记录
3. 可回滚: 不应用 = 无影响; 应用后也可 revert
4. 可批准: Human 看 patch 再决定
5. 可隔离: 多任务并行不冲突

实现 (KISS):
- create(): 项目副本 → 临时目录 (忽略 .git/.venv/__pycache__ 等) → git init
  + 本地身份 → 基线提交 (空项目无基线, diff 走空树对比)。
- apply_patch(text): 补丁写入副本 (git apply — 沙箱内, 不影响原项目)。
- diff()/export_patch(): git diff → 统一 diff 文本/文件 (patch 产物)。
- 全部 git 经 subprocess, git_bin 可注入 (测试命令缺失路径);
  失败 → SandboxError (响亮, 带 git stderr)。

验证语义 (与 factory-core git 层对齐): 副本 git init 后 `git add -A` 暂存全部
变更, diff = `git diff --cached HEAD` (有基线) / `git diff --cached` (空树,
git ≥ 2.20 对比空树, 实测可用) — 新建/修改/删除文件全覆盖。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .models import SandboxSession, new_id, utcnow

#: 副本拷贝忽略项 (依赖/构建产物/vcs 元数据 — 沙箱只追踪源码变更)
_IGNORE_PATTERNS = shutil.ignore_patterns(
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "node_modules",
    "*.pyc",
    "*.pyo",
    ".DS_Store",
)


class SandboxError(Exception):
    """沙箱操作失败 (拷贝/git 命令/补丁应用失败 — 响亮, 不静默)。"""


class Sandbox:
    """项目副本沙箱: 创建 → 修改 → diff → patch 导出 (Agent 唯一可写空间)。

    构造:
    - project_dir: 源项目目录 (只读输入, 副本创建后原项目零接触)。
    - work_root: 副本父目录 (None → 系统临时目录; 测试可注入 tmp_path,
      退出后自动清理依赖临时目录语义)。
    - git_bin: git 可执行 (测试注入假命令测缺失路径)。
    """

    def __init__(
        self,
        project_dir: str | Path,
        *,
        work_root: str | Path | None = None,
        git_bin: str = "git",
    ) -> None:
        self._project_dir = Path(project_dir)
        self._work_root = Path(work_root) if work_root is not None else None
        self._git_bin = git_bin
        self._copy_dir: Path | None = None
        self._baseline_commit: str | None = None

    # ------------------------------------------------------------- 内部 git

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """在副本目录跑 git; 失败 → SandboxError (带 stderr, 诊断友好)。"""
        if self._copy_dir is None:
            raise SandboxError("sandbox not created: call create() first")
        try:
            proc = subprocess.run(
                [self._git_bin, "-C", str(self._copy_dir), *args],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except FileNotFoundError as exc:
            raise SandboxError(f"git command not found: {self._git_bin}") from exc
        except subprocess.TimeoutExpired as exc:
            raise SandboxError(f"git timed out: {' '.join(args)}") from exc
        if check and proc.returncode != 0:
            raise SandboxError(
                f"git {' '.join(args)} failed (rc {proc.returncode}): "
                f"{proc.stderr.strip()[:300]}"
            )
        return proc

    # ------------------------------------------------------------- 生命周期

    def create(self, *, request_id: str = "") -> SandboxSession:
        """创建沙箱: 副本 + git init + 基线提交; 返回会话记录。

        副本目录: <work_root>/exec-sandbox-<id>/project (id = 会话 id)。
        基线: git add -A + commit; 空项目 (nothing to commit) → 无基线
        (diff 走空树对比, 新增文件仍可导出)。
        """
        session_id = new_id("SBX")
        if self._copy_dir is not None:
            raise SandboxError("sandbox already created")
        if not self._project_dir.is_dir():
            raise SandboxError(f"project dir not found: {self._project_dir}")
        base = Path(
            tempfile.mkdtemp(prefix="exec-sandbox-", dir=self._work_root)
        ) if self._work_root is not None else Path(
            tempfile.mkdtemp(prefix="exec-sandbox-")
        )
        copy_dir = base / "project"
        try:
            shutil.copytree(self._project_dir, copy_dir, ignore=_IGNORE_PATTERNS)
        except OSError as exc:
            raise SandboxError(f"copy project failed: {exc}") from exc
        self._copy_dir = copy_dir
        # git init (带 -b main; 老 git 不支持则退化 init + checkout)
        init = subprocess.run(
            [self._git_bin, "-C", str(copy_dir), "init", "-q", "-b", "main"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if init.returncode != 0:
            self._git("init", "-q", check=False)
            self._git("checkout", "-q", "-b", "main", check=False)
        self._git("config", "user.name", "factory-exec sandbox")
        self._git("config", "user.email", "sandbox@factory-exec.local")
        self._git("add", "-A")
        commit = self._git("commit", "-q", "-m", "baseline", check=False)
        if commit.returncode == 0:
            self._baseline_commit = self._git("rev-parse", "HEAD").stdout.strip()
        return SandboxSession(
            id=session_id,
            request_id=request_id,
            workspace_copy_path=str(copy_dir),
            baseline_commit=self._baseline_commit,
        )

    @property
    def copy_dir(self) -> Path:
        """项目副本目录 (create 后可用; Agent 唯一可写空间)。"""
        if self._copy_dir is None:
            raise SandboxError("sandbox not created: call create() first")
        return self._copy_dir

    # ------------------------------------------------------------- 修改追踪

    def apply_patch(self, patch_text: str) -> None:
        """把补丁写入副本 (git apply; 沙箱内修改, 原项目零影响)。

        patch_text 空 → 静默返回 (无变更, 合法状态 — Agent 判断无需修改)。
        """
        if self._copy_dir is None:
            raise SandboxError("sandbox not created: call create() first")
        if not patch_text.strip():
            return
        patch_path = self._copy_dir / ".factory-exec-apply.patch"
        patch_path.write_text(patch_text, encoding="utf-8")
        try:
            self._git("apply", "--whitespace=nowarn", str(patch_path))
        finally:
            patch_path.unlink(missing_ok=True)

    def _stage_and_diff(self) -> str:
        """暂存全部变更后导出统一 diff (新建/修改/删除全覆盖)。"""
        self._git("add", "-A")
        if self._baseline_commit is not None:
            proc = self._git("diff", "--cached", self._baseline_commit, "--", ".")
        else:
            proc = self._git("diff", "--cached", "--", ".")
        return proc.stdout

    def diff(self) -> str:
        """当前变更 diff (git diff; 无变更 → 空字符串)。"""
        return self._stage_and_diff()

    def change_summary(self) -> str:
        """变更摘要 (git status --porcelain 行, 审计/展示用; 无变更 → 空)。"""
        if self._copy_dir is None:
            raise SandboxError("sandbox not created: call create() first")
        proc = self._git("status", "--porcelain")
        return proc.stdout.strip()

    def export_patch(self, patch_path: str | Path) -> str:
        """diff 导出到 patch 文件; 返回 patch 文本 (空 diff 也写空文件)。"""
        text = self._stage_and_diff()
        target = Path(patch_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return text
