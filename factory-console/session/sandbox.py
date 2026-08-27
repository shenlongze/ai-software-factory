"""factory-console/session/sandbox.py — 系统级沙箱最小版 (S10-127 P2.2).

背景: 外部执行器 (codex/claude/hermes CLI) 与本地命令执行缺少隔离护栏。
参考 OpenAI SandboxAgent/UnixLocalSandboxClient + agent-guard 思路 (MIT), 本地最小版:
1. validate_command: 危险模式黑名单 (删除根/格式化/写设备/下载执行等) → (ok, reason)
2. run_isolated: subprocess + 超时 + 干净环境 + 输出截断 (不失控)
3. 接入点: external_executor.executor.run (外部 agent CLI 调用前校验)

边界 (诚实): 这是"命令级"护栏, 不是操作系统级隔离 (seatbelt/docker 为后续工程);
外部 agent 内部行为由其自身沙箱负责。失败安全: 校验异常 → 拒绝 (fail-closed)。
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

#: 危险模式 (命令片段 → 拒绝; 防 rm -rf /、格式化、写设备、下载执行等)
DANGEROUS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brm\s+(-[a-z]*r[a-z]*f[a-z]*|[a-z]*f[a-z]*r[a-z]*)\s+/\s*(\s|$)"), "删除根目录"),
    (re.compile(r"\bmkfs\.?\w*\b"), "格式化磁盘"),
    (re.compile(r"\bdd\s+if=.*of=/dev/"), "写块设备"),
    (re.compile(r">\s*/dev/(sd|disk|rdisk)"), "写设备"),
    (re.compile(r"\bsudo\b"), "sudo 提权"),
    (re.compile(r"\bchmod\s+(-R\s+)?777\s+/"), "根目录权限"),
    (re.compile(r"\b(sh|bash|zsh|python3?|perl|ruby)\s+<(\s|\w)"), "stdin 脚本执行"),
    (re.compile(r"curl[^|]*\|\s*(sh|bash|zsh)"), "下载即执行"),
    (re.compile(r"wget[^|]*\|\s*(sh|bash|zsh)"), "下载即执行"),
]

#: 干净环境保留的最小变量
_KEEP_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "SHELL", "USER")

_MAX_OUTPUT = 1_000_000  # 1MB 输出上限 (防失控)
_DEFAULT_TIMEOUT = 120


def validate_command(cmd: list[str] | str) -> tuple[bool, str]:
    """危险命令校验 → (ok, reason)。命令为 list 或 shell 字符串均可。"""
    try:
        if isinstance(cmd, str):
            parts = shlex.split(cmd)
        else:
            parts = [str(c) for c in cmd]
    except Exception:  # noqa: BLE001 — 无法解析 → 拒绝 (fail-closed)
        return False, "命令无法解析"
    text = " ".join(parts)
    for pat, reason in DANGEROUS_PATTERNS:
        if pat.search(text):
            return False, f"危险命令已拦截: {reason}"
    return True, ""


def clean_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """干净环境: 只保留最小变量 (继承白名单 + 显式覆盖)。"""
    out: dict[str, str] = {}
    for k in _KEEP_ENV:
        v = os.environ.get(k)
        if v:
            out[k] = v
    if env:
        out.update({k: str(v) for k, v in env.items()})
    return out


def run_isolated(
    cmd: list[str] | str,
    *,
    cwd: str | Path | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
    env: dict[str, str] | None = None,
    max_output: int = _MAX_OUTPUT,
) -> dict[str, Any]:
    """隔离执行: 校验 → 干净环境 → 超时 → 输出截断。

    返回 {ok, output, error, exit_code, command} (与外部执行器契约一致)。
    """
    if isinstance(cmd, str):
        parts = shlex.split(cmd)
    else:
        parts = [str(c) for c in cmd]
    ok_v, reason = validate_command(parts)
    if not ok_v:
        return {"ok": False, "output": "", "error": reason, "exit_code": -1,
                "command": " ".join(parts)[:400]}
    try:
        r = subprocess.run(
            parts,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
            env=clean_env(env),
        )
        out = (r.stdout or "")[-max_output:]
        err = (r.stderr or "")[-max_output:]
        return {"ok": r.returncode == 0, "output": out, "error": err,
                "exit_code": r.returncode, "command": " ".join(parts)[:400]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": "", "error": f"执行超时 ({timeout}s)",
                "exit_code": -1, "command": " ".join(parts)[:400]}
    except FileNotFoundError:
        return {"ok": False, "output": "", "error": f"命令不存在: {parts[0] if parts else ''}",
                "exit_code": -1, "command": " ".join(parts)[:400]}
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return {"ok": False, "output": "", "error": f"执行失败: {exc}",
                "exit_code": -1, "command": " ".join(parts)[:400]}
