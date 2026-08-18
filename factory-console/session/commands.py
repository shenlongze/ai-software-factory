"""factory-console/session/commands.py — 基础 Slash 命令 (S10-047 Task 004)。

/help     列出可用命令 (name + description)
/status   显示会话状态 (session/workspace/当前项目/当前 Agent — 来自 SessionContext)
/project  项目列表 (无参=查看) / 切换 current_project (有参=<id>) — 只读
          projects.json (与 FactoryCLI._project_list 同一数据口径 — 复用, 不复制业务)
/cost     成本信息接口占位 (会话近期活动摘要; 不复制 exec 用量业务)
/exit     退出会话 (设置宿主 session.running=False)

原则 (S10-046 设计 §6 边界): 命令只做会话内编排, 业务逻辑全部在既有 Service
Layer — 本项目清单只读复用规范数据文件 projects.json (org 写入的同一文件),
零业务复制 (不触碰 ProjectStore/Lifecycle/exec 执行链)。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .context import SessionContext
from .slash import SlashCommand, SlashCommandRegistry

#: 项目清单数据文件默认路径 (与 ConfigProvider.get_data_dir() 默认 ~/.factory 同口径)
DEFAULT_PROJECTS_FILE = Path.home() / ".factory" / "org" / "projects.json"

#: /cost 近期活动展示条数上限
RECENT_LIMIT = 5


def read_projects(projects_file: Path) -> list[dict[str, Any]]:
    """只读 projects.json → [{id, name}] (与 FactoryCLI._project_list 同口径)。

    复用 org 写入的规范数据文件; 失败安全铁律: 缺失/损坏 → 空列表, 永不抛。
    """
    projects: list[dict[str, Any]] = []
    try:
        if projects_file.is_file():
            raw = json.loads(projects_file.read_text(encoding="utf-8"))
            section = raw.get("projects", {}) if isinstance(raw, dict) else {}
            if isinstance(section, dict):
                for pid, record in sorted(section.items()):
                    record = record if isinstance(record, dict) else {}
                    projects.append({"id": pid, "name": record.get("name", "")})
    except Exception:  # noqa: BLE001 — 只读展示, 失败安全
        projects = []
    return projects


class HelpCommand(SlashCommand):
    """/help — 列出可用命令 (name + description)。"""

    name = "help"
    description = "显示可用命令列表"

    def execute(self, args: str, context: SessionContext) -> int:
        if self.registry is None:
            print("错误: 命令表不可用 (registry 未注入)")
            return 1
        print("你可以直接用自然语言和 AI Factory 对话。例如:")
        print("  你好")
        print("  什么是 MCP？")
        print("  我想做一个类似 OneNote 的 App")
        print("  我想开发一个博客")
        print("  继续开发当前项目")
        print("  帮我修复当前项目的登录 Bug")
        print()
        print("系统命令:")
        for cmd in self.registry.list():
            print(f"  /{cmd.name}  {cmd.description}")
        return 0


class StatusCommand(SlashCommand):
    """/status — 显示会话状态 (session/workspace/当前项目/当前 Agent)。"""

    name = "status"
    description = "显示会话状态 (session/workspace/项目/Agent)"

    def execute(self, args: str, context: SessionContext) -> int:
        snap = context.to_dict()
        print("=== 会话状态 ===")
        print(f"session_id: {snap['session_id']}")
        print(f"workspace: {snap['workspace'] or '(未设置)'}")
        print(f"当前项目: {snap['current_project'] or '(未选择)'}")
        print(f"当前 Agent: {snap['current_agent'] or '(未选择)'}")
        if snap["metadata"]:
            print(f"metadata: {snap['metadata']}")
        print(f"历史输入: {len(snap['history'])} 条")
        return 0


class ProjectCommand(SlashCommand):
    """/project — 项目列表 (无参) / 切换 current_project (/project <id>)。"""

    name = "project"
    description = "项目列表/切换当前项目 (/project [<id>])"

    def __init__(
        self,
        cli: Any = None,
        projects_file: Optional[Path] = None,
    ) -> None:
        super().__init__()
        #: 可选 FactoryCLI — 提供 data_dir 口径 (复用其数据目录解析, 不复制业务)
        self.cli = cli
        #: projects.json 路径 (缺省 → cli.data_dir 或 ~/.factory 口径)
        self.projects_file = projects_file

    def _projects_file(self) -> Path:
        if self.projects_file is not None:
            return Path(self.projects_file)
        if self.cli is not None:
            return Path(self.cli.data_dir) / "org" / "projects.json"
        return DEFAULT_PROJECTS_FILE

    def execute(self, args: str, context: SessionContext) -> int:
        projects = read_projects(self._projects_file())
        if not args:
            return self._show(projects, context)
        return self._switch(args.strip(), projects, context)

    def _show(self, projects: list[dict[str, Any]], context: SessionContext) -> int:
        current = context.current_project
        print(f"项目清单 ({len(projects)} 个)")
        for item in projects:
            marker = "  (当前)" if item["id"] == current else ""
            print(f"  {item['id']}  {item['name']}{marker}")
        if not projects:
            print("  (无项目 — 使用 `factory project create` 注册)")
        print(f"当前项目: {current or '(未选择)'}")
        return 0

    def _switch(
        self, target: str, projects: list[dict[str, Any]], context: SessionContext
    ) -> int:
        ids = sorted({item["id"] for item in projects})
        if target not in ids:
            print(f"未知项目: {target} — 可用: {', '.join(ids) or '(无)'}")
            return 1
        context.current_project = target
        print(f"已切换当前项目: {target}")
        return 0


class CostCommand(SlashCommand):
    """/cost — 成本信息接口 (占位: 会话近期活动摘要; 不复制 exec 用量业务)。"""

    name = "cost"
    description = "成本/用量信息 (占位: 会话近期活动摘要)"

    def execute(self, args: str, context: SessionContext) -> int:
        print("=== 成本/用量 ===")
        print(f"session_id: {context.session_id}")
        print(f"会话输入数: {len(context.history)}")
        recent = context.history[-RECENT_LIMIT:]
        if recent:
            print("近期活动:")
            for line in recent:
                print(f"  {line}")
        print(
            "说明: 执行成本统计接口 (provider usage / run-status) 由后续 Task 接入, "
            "本命令不复制执行业务。"
        )
        return 0


class ExitCommand(SlashCommand):
    """/exit — 退出会话 (设置宿主 session.running=False)。"""

    name = "exit"
    description = "退出会话"

    def __init__(self, session: Any = None) -> None:
        super().__init__()
        #: 宿主 InteractiveSession (构造注入, 避免 session ↔ commands 循环导入)
        self.session = session

    def execute(self, args: str, context: SessionContext) -> int:
        if self.session is not None:
            self.session.running = False
        print("已退出会话 — 再见!")
        return 0


def build_default_registry(
    session: Any = None,
    *,
    cli: Any = None,
    projects_file: Optional[Path] = None,
) -> SlashCommandRegistry:
    """装配默认 slash 命令注册表 (注册式 — 新增命令只需 register 一行)。"""
    registry = SlashCommandRegistry(session=session)
    registry.register(HelpCommand())
    registry.register(StatusCommand())
    registry.register(ProjectCommand(cli=cli, projects_file=projects_file))
    registry.register(CostCommand())
    registry.register(ExitCommand(session=session))
    return registry
