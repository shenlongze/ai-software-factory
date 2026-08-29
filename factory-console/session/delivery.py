"""factory-console/session/delivery.py — Patch Delivery Pipeline (S10-083 P0)。

任务成功 → patch 白名单过滤 → git apply 回真实项目目录 → 真实产物验证。

- 状态文件 (execution_state.json 等) 从 patch 剥离 (Artifact Boundary)
- 项目目录非 git → git init (保证 git apply 可用)
- 任务声明代码但项目 0 代码文件 → 失败 (消除空目录 PASS)
- 全程审计事件: PATCH_APPLIED / CODE_VALIDATED / DELIVERY_COMPLETED / DELIVERY_FAILED
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("factory.session.delivery")

#: 代码文件扩展名 (交付校验)
_CODE_SUFFIXES = (".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".kt",
                  ".go", ".rs", ".dart", ".swift", ".rb", ".php", ".cpp", ".c", ".h")

#: 任务声称生成的扩展名 (默认代码) — 由任务/工程语言推断, 缺省宽松校验
_CLAIM_SUFFIXES: tuple[str, ...] = ()


def _git(cwd: Path, *args: str) -> tuple[int, str]:
    """git 命令执行 (项目目录内)。"""
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, timeout=60,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def ensure_git_repo(project_dir: Path) -> bool:
    """项目目录确保为 git 仓库 (非 git → git init, 失败 → False)。"""
    if (project_dir / ".git").is_dir():
        return True
    code, out = _git(project_dir, "init", "-q")
    if code != 0:
        logger.debug("git init failed: %s", out)
        return False
    # 首次 apply 需要至少一个提交 (git apply 对未跟踪文件需要 --index 或基线)
    if not (project_dir / ".git" / "HEAD").is_file():
        # 空仓库: 先建立基线 (允许 git apply 后续 diff)
        _git(project_dir, "add", "-A")
        _git(project_dir, "-c", "user.email=factory@local", "-c", "user.name=factory",
             "commit", "-q", "-m", "factory baseline")
    return True


def apply_patch(project_dir: Path, patch_text: str) -> tuple[bool, str]:
    """把过滤后的 patch 应用到项目目录 (git apply + 容错重试)。

    返回 (成功, 消息)。patch 为空 → 视为无变更成功。
    容错链 (S10-083): git apply → --recount --ignore-whitespace → patch -p1 --fuzz。
    """
    text = str(patch_text or "").lstrip()
    if not text:
        return True, "no changes"
    # S1 (v1.1.307): strip() 破坏尾部换行导致 git apply "corrupt patch at line N"
    # (patch 以内容行结尾时, 最后一行必须保留 trailing newline)
    if not text.endswith("\n"):
        text += "\n"
    if not ensure_git_repo(project_dir):
        return False, "project not a git repo and git init failed"

    # 尝试 1: 标准 git apply
    proc = subprocess.run(
        ["git", "-C", str(project_dir), "apply", "--whitespace=nowarn", "-"],
        input=text, capture_output=True, text=True, timeout=60,
    )
    if proc.returncode == 0:
        return True, "patch applied"

    # 尝试 2: 宽松 (recount 行号 + 忽略空白)
    proc2 = subprocess.run(
        ["git", "-C", str(project_dir), "apply", "--recount", "--ignore-whitespace", "-"],
        input=text, capture_output=True, text=True, timeout=60,
    )
    if proc2.returncode == 0:
        return True, "patch applied (loose)"

    # 尝试 3: 系统 patch 工具 (fuzz 上下文容错)
    proc3 = subprocess.run(
        ["patch", "-p1", "--fuzz=3", "-d", str(project_dir), "-i", "-"],
        input=text, capture_output=True, text=True, timeout=60,
    )
    if proc3.returncode == 0:
        return True, "patch applied (patch -p1)"

    last_err = (proc.stderr or proc.stdout or "").strip()[:300]
    return False, f"git apply failed: {last_err}"


def count_code_files(project_dir: Path) -> int:
    """项目目录代码文件计数 (排除 .git/虚拟环境/缓存)。"""
    n = 0
    for path in project_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(project_dir)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if path.suffix in _CODE_SUFFIXES:
            n += 1
    return n


def validate_delivery(project_dir: Path, *, require_code: bool = True) -> tuple[bool, str]:
    """交付校验: 项目真实产物 + (可选) 代码文件存在。"""
    if require_code:
        n = count_code_files(project_dir)
        if n == 0:
            return False, "任务要求生成代码但项目无任何代码文件 (0 个) — 交付失败"
    return True, ""


def deliver_patch(project_dir: Path, patch_text: str, *, emit=None) -> dict:
    """完整交付: 过滤 → apply → 校验 → 审计事件。返回结果 dict。

    emit: 审计事件发射器 (workspace) — 缺省不发射 (失败安全)。
    """
    import importlib
    import sys as _sys

    # 同 actions._load_exec_cli: sys.path 挂 factory-exec (源码态连字符目录)
    root = Path(__file__).resolve().parents[2]
    path = str(root / "factory-exec")
    if path not in _sys.path:
        _sys.path.insert(0, path)
    try:
        _pf = importlib.import_module("exec.patch_filter")
    except ModuleNotFoundError:
        _pf = importlib.import_module("factory-exec.exec.patch_filter")
    filter_patch = _pf.filter_patch

    clean, blocked = filter_patch(patch_text)
    result: dict = {"blocked_files": blocked, "applied": False, "code_files": 0, "ok": False}

    if blocked:
        logger.info("patch 剥离状态文件 %d 个: %s", len(blocked), ", ".join(blocked[:5]))

    ok, msg = apply_patch(project_dir, clean)
    if not ok:
        result["error"] = msg
        if emit:
            try:
                emit("DELIVERY_FAILED", project_id=project_dir.name, decision_reason=msg)
            except Exception:  # noqa: BLE001
                pass
        return result

    result["applied"] = True
    result["code_files"] = count_code_files(project_dir)
    ok2, msg2 = validate_delivery(project_dir, require_code=True)
    result["ok"] = ok2
    result["validation"] = msg2
    if emit:
        try:
            emit("PATCH_APPLIED", project_id=project_dir.name,
                 decision_reason=f"patch applied ({len(clean.splitlines())} lines)")
            emit("CODE_VALIDATED", project_id=project_dir.name,
                 decision_reason=f"{result['code_files']} code files in project")
            if ok2:
                emit("DELIVERY_COMPLETED", project_id=project_dir.name,
                     decision_reason=f"delivery ok: {result['code_files']} code files")
            else:
                emit("DELIVERY_FAILED", project_id=project_dir.name, decision_reason=msg2)
        except Exception:  # noqa: BLE001
            pass
    return result
