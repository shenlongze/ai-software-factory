"""factory-console/external_executor/executor.py — 通用执行器 (M1)。

设计依据: 设计文档 §5 (GenericExecutor: discover→probe→invoke→record)。
只依赖适配器 Schema, 不依赖产品名。

- discover: 按 discovery 顺序定位二进制 (which + 路径)
- probe: 跑 version_probe/probe_help → {ok, usage, error} (诚实: 能跑 ≠ 任务真实成功)
- build_invocation: 按 invocation 模板渲染 (占位符替换 + shlex 转义)
- run: 统一 {exit_code, output, error, command}
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .schema import ExternalExecutorAdapter

PLACEHOLDERS = ("{prompt}", "{project_dir}", "{agent}", "{skills}")


def discover_binary(adapter: ExternalExecutorAdapter) -> str | None:
    """按 discovery 顺序定位二进制 (PATH + 绝对/家目录路径; 找不到 → None)。"""
    for entry in adapter.discovery:
        e = str(entry or "").strip()
        if not e:
            continue
        if e == "PATH":
            found = shutil.which(adapter.binary)
            if found:
                return found
            continue
        p = Path(e).expanduser()
        if p.is_dir():
            cand = p / adapter.binary
            if cand.is_file():
                return str(cand)
            continue
        if p.is_file():
            return str(p)
    return None


def probe(adapter: ExternalExecutorAdapter, path: str | None = None) -> dict[str, Any]:
    """探测可用性: 跑 version_probe/probe_help → {ok, usage, version, error}。

    诚实: 二进制可执行 + 帮助/版本命令退出 0 → ok; 否则 ok=false (可展示不可委派)。"""
    path = path or discover_binary(adapter)
    if not path:
        return {"ok": False, "usage": "", "version": "", "error": f"未找到二进制: {adapter.binary}"}
    version = ""
    usage = ""
    for args, is_version in ((list(adapter.version_probe), True), (list(adapter.probe_help or adapter.version_probe), False)):
        try:
            r = subprocess.run([path, *args], capture_output=True, text=True, timeout=15)
            text = (r.stdout or r.stderr or "").strip()
            first = text.splitlines()[0][:120] if text else ""
            if is_version and first:
                version = first
            else:
                usage = first
            if r.returncode == 0 and (is_version or not adapter.probe_help):
                if is_version and version:
                    return {"ok": True, "usage": "", "version": version, "error": ""}
        except Exception:  # noqa: BLE001 — 探测失败 → 继续下一个
            continue
    # 组合判定: version 或 usage 任一成功即认为二进制可执行
    ok = bool(version or usage)
    return {"ok": ok, "usage": usage, "version": version,
            "error": "" if ok else "probe 失败 (--version/--help 均未返回)"}


def build_invocation(
    adapter: ExternalExecutorAdapter,
    prompt: str,
    project_dir: str = "",
    *,
    agent: str = "",
    skills: list[str] | None = None,
) -> list[str]:
    """按 invocation 模板渲染命令 (占位符替换 + shlex 转义)。

    规则 (§4.2): {prompt} 必替换; project_dir 按模式 (cwd 不插入 / flag: 插入参数名);
    agent/skills 仅在对应 flag 声明时插入; 无 {prompt} 的模板在 Schema 校验时已拒绝。"""
    template = list(adapter.invocation.non_interactive) + list(adapter.invocation.extra or [])
    mode = str(adapter.invocation.project_dir or "cwd")
    pdir = str(project_dir or "").strip()

    def esc(value: str) -> str:
        return shlex.quote(value)

    out: list[str] = []
    for part in template:
        part = str(part)
        if "{prompt}" in part:
            part = part.replace("{prompt}", esc(prompt))
        if "{project_dir}" in part:
            part = part.replace("{project_dir}", esc(pdir or "."))
        if "{agent}" in part:
            part = part.replace("{agent}", esc(agent))
        if "{skills}" in part:
            part = part.replace("{skills}", esc(",".join(skills or [])))
        out.append(part)
    # project_dir flag 模式: 在模板后插入 "<参数名> <目录>" (codex: -C <dir>)
    if mode.startswith("flag:"):
        flag = mode.split(":", 1)[1].strip()
        if flag:
            out.extend([flag, esc(pdir or ".")])
    # 借壳: agent/skills 指定时插入声明的 flag (§4.2 agent_flag/skills_flag)
    if agent and adapter.invocation.agent_flag:
        for part in adapter.invocation.agent_flag:
            out.append(str(part).replace("{agent}", esc(agent)))
    if skills and adapter.invocation.skills_flag:
        for part in adapter.invocation.skills_flag:
            out.append(str(part).replace("{skills}", esc(",".join(skills))))
    return out


def run(
    adapter: ExternalExecutorAdapter,
    prompt: str,
    project_dir: str = "",
    *,
    agent: str = "",
    skills: list[str] | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """委派真实执行 (统一契约 {exit_code, output, error, command})。"""
    path = discover_binary(adapter)
    if not path:
        return {"exit_code": -1, "output": "", "error": f"未找到二进制: {adapter.binary}", "command": ""}
    cmd = build_invocation(adapter, prompt, project_dir, agent=agent, skills=skills)
    mode = str(adapter.invocation.project_dir or "cwd")
    use_cwd = mode == "cwd" and project_dir
    cwd = str(project_dir or "").strip() if use_cwd else None
    timeout = timeout or adapter.invocation.timeout
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd if cwd and Path(cwd).is_dir() else None,
        )
        return {
            "exit_code": r.returncode,
            "output": (r.stdout or "")[-8000:],
            "error": (r.stderr or "")[-3000:] if r.returncode != 0 else "",
            "command": " ".join(cmd)[:400],
        }
    except FileNotFoundError as exc:
        return {"exit_code": -1, "output": "", "error": f"CLI 不存在: {exc}", "command": " ".join(cmd)[:400]}
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "output": "", "error": f"执行超时 ({timeout}s)", "command": " ".join(cmd)[:400]}
    except Exception as exc:  # noqa: BLE001 — 执行失败 → 诚实错误
        return {"exit_code": -1, "output": "", "error": f"执行失败: {exc}", "command": " ".join(cmd)[:400]}
