"""factory-console/session/tools.py — 工具发现与注册 (M1 内核切片 · 增强层)。

发现本机 AI CLI (codex/hermes/openclaw/claude) + MCP server 配置
(~/.codex/config.toml / ~/.claude.json / 项目 .mcp.json), 供 `factory tools list/doctor`。

铁律 (愿景): 工具是**增强层**, 任何任务不依赖外部 CLI 完成 —
AI Factory 自己的 Agent 用自身运行时 + 自身 LLM 完成任务, 工具只做锦上添花。

组件:
- ToolInfo — 工具条目 {name, kind: ai_cli|mcp, path/binary, version, command/args, server, enabled}
- discover_ai_clis() — PATH 扫描 + --version 探测 (失败安全)
- discover_mcp_servers() — 配置扫描 (toml/json), 只读不修改
- format_tools() — 人类可读表格
边界: 纯标准库 (shutil/os/subprocess/pathlib/json); 只读; 失败安全 (缺失/损坏 → 跳过)
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

#: 本机 AI CLI 候选 (增强层 — 发现但不依赖)
AI_CLI_NAMES: tuple[str, ...] = ("codex", "hermes", "openclaw", "claude")

#: 扫描的 MCP 配置文件 (home 相对路径 → 配置段说明)
MCP_CONFIG_HINTS: tuple[tuple[str, str], ...] = (
    (".codex/config.toml", "codex mcp_servers"),
    (".claude.json", "claude mcpServers"),
)


@dataclass
class ToolInfo:
    """单个工具条目 (CLI 或 MCP server)。"""

    name: str
    kind: str                 # ai_cli | mcp
    binary: str = ""          # ai_cli: 可执行路径
    version: str = ""         # ai_cli: --version 探测
    command: str = ""         # mcp: server command
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    source: str = ""          # 配置文件路径
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "binary": self.binary,
            "version": self.version,
            "command": self.command,
            "args": list(self.args),
            "env": dict(self.env),
            "source": self.source,
            "enabled": self.enabled,
        }


# ------------------------------------------------------------------ AI CLI 发现


def _probe_version(binary: str) -> str:
    """探测 CLI 版本 (失败安全 → ""; 超时 5s)。"""
    try:
        proc = subprocess.run(
            [binary, "--version"],
            capture_output=True, text=True, timeout=5,
        )
        line = (proc.stdout or proc.stderr or "").strip().splitlines()
        return (line[0] if line else "").strip()[:60]
    except Exception:  # noqa: BLE001 — 探测失败 → 无版本
        return ""


def discover_ai_clis() -> list[ToolInfo]:
    """PATH 扫描本机 AI CLI (codex/hermes/openclaw/claude) → ToolInfo 列表。"""
    tools: list[ToolInfo] = []
    for name in AI_CLI_NAMES:
        binary = shutil.which(name)
        if not binary:
            continue
        tools.append(ToolInfo(
            name=name,
            kind="ai_cli",
            binary=binary,
            version=_probe_version(binary),
            source="PATH",
        ))
    return tools


# ------------------------------------------------------------------ MCP 配置发现


def _parse_codex_toml(path: Path) -> list[ToolInfo]:
    """解析 ~/.codex/config.toml 的 [mcp_servers.*] (轻量行解析, 不引第三方)。"""
    tools: list[ToolInfo] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 — 只读失败安全
        return tools
    current: Optional[str] = None
    command = ""
    args: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("["):
            # 收尾上一段
            if current and command:
                tools.append(ToolInfo(
                    name=current, kind="mcp", command=command,
                    args=list(args), source=str(path),
                ))
            current = None
            command = ""
            args = []
            if line.startswith("[mcp_servers."):
                current = line[len("[mcp_servers."):].rstrip("]").strip()
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"')
            if key == "command" and current:
                command = value
            elif key == "args" and current and value.startswith("["):
                args = [a.strip().strip('"') for a in value[1:-1].split(",") if a.strip()]
    if current and command:
        tools.append(ToolInfo(
            name=current, kind="mcp", command=command,
            args=list(args), source=str(path),
        ))
    return tools


def _parse_claude_json(path: Path) -> list[ToolInfo]:
    """解析 ~/.claude.json 的 mcpServers (dict: name → {command,args,env})。"""
    tools: list[ToolInfo] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 只读失败安全
        return tools
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        return tools
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            continue
        tools.append(ToolInfo(
            name=str(name), kind="mcp",
            command=str(cfg.get("command") or ""),
            args=[str(a) for a in (cfg.get("args") or [])],
            env={str(k): str(v) for k, v in (cfg.get("env") or {}).items()},
            source=str(path),
        ))
    return tools


def discover_mcp_servers(home: Optional[Path] = None) -> list[ToolInfo]:
    """配置扫描 → MCP server 列表 (只读; 缺失/损坏 → 跳过)。"""
    home = Path(home or Path.home())
    tools: list[ToolInfo] = []
    for rel, _label in MCP_CONFIG_HINTS:
        path = home / rel
        if not path.is_file():
            continue
        tools.extend(
            _parse_codex_toml(path) if path.suffix == ".toml" else _parse_claude_json(path)
        )
    # 项目级 .mcp.json (cwd)
    project_mcp = Path.cwd() / ".mcp.json"
    if project_mcp.is_file():
        tools.extend(_parse_claude_json(project_mcp))
    # 去重 (name+command)
    seen: set[tuple[str, str]] = set()
    deduped: list[ToolInfo] = []
    for t in tools:
        key = (t.name, t.command)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(t)
    return deduped


def discover_all(home: Optional[Path] = None) -> list[ToolInfo]:
    """全部工具 (AI CLI + MCP), CLI 在前。"""
    return discover_ai_clis() + discover_mcp_servers(home=home)


# ------------------------------------------------------------------ 展示


def format_tools(tools: list[ToolInfo]) -> str:
    """人类可读表格 (名称/类型/来源/版本/命令)。"""
    if not tools:
        return "未发现外部工具 (AI Factory 自身能力即可完成任务 — 工具仅增强)\n" \
               "提示: 安装 codex/hermes/openclaw/claude 或配置 MCP server 后可见"
    lines = ["工具清单 (增强层 — 不依赖):"]
    lines.append(f"  {'名称':<12} {'类型':<8} {'来源':<32} 版本/命令")
    for t in tools:
        src = (t.source or "")[:32]
        detail = t.version or f"{t.command} {' '.join(t.args[:3])}".strip()
        lines.append(f"  {t.name:<12} {t.kind:<8} {src:<32} {detail[:44]}")
    return "\n".join(lines)
