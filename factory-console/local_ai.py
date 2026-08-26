"""factory-console/local_ai.py — U-6 (v1.1.188): 本机 AI 工具发现与调度。

Founder 2026-08-27: "我电脑上安装了 codex / Claude / Hermes, 怎么没有被发现?"
→ 扫描本机安装的 AI CLI (codex/claude/hermes) → 自动注册为 Agent →
exec 可委派真实执行 (调用本机 CLI, 不是 mock)。

- detect_local_ais(): 扫描 PATH + 常见安装目录, 探测版本 (失败安全跳过)
- register_local_ais(agents_file, detected): 幂等注册进 agents.json
  (已存在 → 更新 path/version; 新 → 追加; 不覆盖用户手工改的 role/name)
- run_local_ai(record, prompt, project_dir, timeout): 委派真实执行
  (subprocess 调本机 CLI; 各 CLI 参数映射见 _RUN_ARGS; 失败安全返回错误)

诚实边界: 只注册"真扫描到"的 CLI (which/PATH 找不到 → 不编造);
版本探测失败 → version=None; 执行失败 → 返回 {exit_code, output, error}。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

#: 扫描目标: (agent_id 后缀, 二进制名, 角色, 技能, 描述)
_SCAN_TARGETS: list[tuple[str, str, str, list[str], str]] = [
    ("codex", "codex", "developer",
     ["codex", "development", "coding", "agent"],
     "本机 Codex (OpenAI 编码代理) — 自动发现并注册, exec 可委派真实执行"),
    ("claude", "claude", "developer",
     ["claude", "development", "coding", "agent"],
     "本机 Claude Code (Anthropic) — 自动发现并注册, exec 可委派真实执行"),
    ("hermes", "hermes", "developer",
     ["hermes", "development", "coding", "agent"],
     "本机 Hermes — 自动发现并注册, exec 可委派真实执行"),
]

#: 常见安装目录 (PATH 之外兜底扫描; 失败安全)
_EXTRA_DIRS: list[str] = [
    "~/.local/bin", "~/.codex/bin", "~/bin", "~/.npm-global/bin",
    "/usr/local/bin", "/opt/homebrew/bin",
]


def _find_binary(name: str) -> str | None:
    """PATH + 常见目录定位二进制 (找不到 → None)。"""
    found = shutil.which(name)
    if found:
        return found
    for d in _EXTRA_DIRS:
        p = Path(d).expanduser() / name
        if p.is_file():
            return str(p)
    return None


def _probe_version(path: str, binary: str) -> str | None:
    """探测版本 (失败 → None; 诚实不编造)。"""
    for flag in ("--version", "-v", "version"):
        try:
            r = subprocess.run(
                [path, flag], capture_output=True, text=True, timeout=8
            )
            text = (r.stdout or r.stderr or "").strip().splitlines()
            if text:
                return text[0][:100]
        except Exception:  # noqa: BLE001 — 探测失败 → 试下一个 flag
            continue
    return None


def detect_local_ais() -> list[dict[str, Any]]:
    """扫描本机 AI CLI → 发现清单 (失败安全; 未装 → 空)。"""
    found: list[dict[str, Any]] = []
    for suffix, binary, role, skills, desc in _SCAN_TARGETS:
        path = _find_binary(binary)
        if path is None:
            continue
        version = _probe_version(path, binary)
        found.append(
            {
                "id": f"local-{suffix}",
                "name": f"本机 {suffix.capitalize()}",
                "role": role,
                "skills": skills,
                "binary": binary,
                "path": path,
                "version": version,
                "description": desc,
            }
        )
    return found


def _load_agents(agents_file: str | Path) -> dict[str, Any]:
    try:
        d = json.loads(Path(agents_file).read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("agents"), dict):
            return d
        if isinstance(d, dict):
            return {"agents": d}
    except Exception:  # noqa: BLE001 — 缺失/损坏 → 空
        pass
    return {"agents": {}}


def _save_agents(agents_file: str | Path, data: dict[str, Any]) -> None:
    try:
        p = Path(agents_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:  # 写失败 → 静默 (注册尽力而为)
        pass


def register_local_ais(
    agents_file: str | Path,
    detected: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """幂等注册: 已存在 → 更新 binary/path/version (不覆盖用户 role/name);
    新 → 追加。返回本次注册/更新的 Agent 记录。"""
    detected = detected if detected is not None else detect_local_ais()
    if not detected:
        return []
    data = _load_agents(agents_file)
    agents = data["agents"]
    touched: list[dict[str, Any]] = []
    for item in detected:
        aid = str(item["id"])
        existing = agents.get(aid)
        if existing is not None and isinstance(existing, dict):
            # 保留用户可改字段, 只刷新发现信息
            existing["binary"] = item["binary"]
            existing["path"] = item["path"]
            if item.get("version"):
                existing["version"] = item["version"]
            if not existing.get("skills"):
                existing["skills"] = item["skills"]
            touched.append(existing)
        else:
            record = {
                "id": aid,
                "name": item["name"],
                "role": item["role"],
                "skills": item["skills"],
                "binary": item["binary"],
                "path": item["path"],
                "version": item.get("version"),
                "description": item["description"],
            }
            agents[aid] = record
            touched.append(record)
    _save_agents(agents_file, data)
    return touched


#: 各本机 AI CLI 的调用参数映射 (project_dir 用 --cd / -C 传入; 失败安全)
_RUN_ARGS: dict[str, list[str]] = {
    "codex": ["exec", "--cd"],
    "claude": ["-p", "--output-format", "text"],
    "hermes": ["run", "--dir"],
}


def run_local_ai(
    record: dict[str, Any],
    prompt: str,
    project_dir: str = "",
    timeout: int = 600,
) -> dict[str, Any]:
    """委派真实执行: 调本机 CLI (subprocess)。失败安全 → {exit_code, output, error}。

    codex:  codex exec --cd <dir> --skip-git-repo-check "<prompt>"
    claude: claude -p --output-format text "<prompt>"  (cwd=<dir>)
    hermes: hermes run --dir <dir> "<prompt>"
    """
    binary = str(record.get("binary") or "")
    path = str(record.get("path") or binary or "")
    if not path:
        return {"exit_code": -1, "output": "", "error": "未找到本机 CLI 二进制路径"}
    cwd = str(project_dir or "").strip() or None
    args = list(_RUN_ARGS.get(binary, [binary]))  # 未知 CLI → 直接 [binary] 兜底
    cmd: list[str] = []
    if binary == "codex":
        cmd = [path, "exec", "--cd", cwd or ".", "--skip-git-repo-check", prompt]
    elif binary == "claude":
        cmd = [path, "-p", "--output-format", "text", prompt]
    elif binary == "hermes":
        cmd = [path, "run", "--dir", cwd or ".", prompt]
    else:
        cmd = [path, *args, prompt]
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd if cwd and binary != "codex" else None,
        )
        return {
            "exit_code": r.returncode,
            "output": (r.stdout or "")[-4000:],
            "error": (r.stderr or "")[-2000:] if r.returncode != 0 else "",
            "command": " ".join(cmd)[:300],
        }
    except FileNotFoundError as exc:
        return {"exit_code": -1, "output": "", "error": f"CLI 不存在: {exc}"}
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "output": "", "error": f"执行超时 ({timeout}s)"}
    except Exception as exc:  # noqa: BLE001 — 执行失败 → 诚实错误
        return {"exit_code": -1, "output": "", "error": f"执行失败: {exc}"}
