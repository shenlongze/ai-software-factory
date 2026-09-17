"""组织 域命令注册（apps/cli/domains/organization）。

本域命令（依据 `apps/cli/registry.py` 的 `organization`）:
    plugin   Plugin 内核（list/inspect/enable/disable/status/health/resolve）
    agent / agent-run / skill / org / workforce / workforce-os / variant / mcp / tools   ← 待搬

搬迁来源: 老 CLI `_pending_migration/factory_console/cli_factory.py`
          · 参数注册 p_plug（L9822）· 处理 plugin_cmd（L9830+）
底层能力: **已在新地基** `ai_factory_os.infrastructure.plugins.kernel`
          （2026-09-15 从老区迁入: services/… → infrastructure/plugins/kernel.py）
          ⇒ 本命令零老区依赖 ✓
"""
from __future__ import annotations

from typing import Any, Callable


def register(sub: Any, json_opt: Callable[[Any], None]) -> None:
    """注册 organization 域的命令。sub = 主 subparsers 容器; json_opt = 共享的 --json 选项。"""
    # factory plugin <动作> [target] —— Plugin (S31) Plugin Kernel
    p_plug = sub.add_parser(
        "plugin", help="Plugin (S31): list/inspect/enable/disable/status/health — Plugin Kernel"
    )
    json_opt(p_plug)
    p_plug.add_argument(
        "action", nargs="?", default="list",
        choices=["list", "inspect", "enable", "disable", "status", "health", "resolve"],
        help="动作: list 列表 / inspect <id> 详情 / enable <id> 启用 / disable <id> 禁用 / "
             "status <id> 状态 / health <id> 健康 / resolve <cap> 解析",
    )
    p_plug.add_argument("target", nargs="?", help="plugin_id 或 capability")
