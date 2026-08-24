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
from .renderer import render_message
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
        print("  我想做一个类似 OneNote 的 App")
        print("  让PM分析        — 产品管线 (7 角色资产链)")
        print("  继续 旅行记账    — 按名称继续项目")
        print("  哪些项目有PRD   — 真实文档状态")
        print("  P-xxx 改名叫 新名 — 项目改名")
        print()
        print("系统命令:")
        for cmd in self.registry.list():
            print(f"  /{cmd.name}  {cmd.description}")
        print()
        print("CLI 命令 (在系统终端运行 factory 开头):")
        print("  factory doctor [--fix]   — 诊断 (--fix 修复 models.json 种子)")
        print("  factory init / start / status")
        print("  factory project list / status")
        print("  factory exec history")
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
        workspace: Optional[Path] = None,
    ) -> None:
        super().__init__()
        #: 可选 FactoryCLI — 提供 data_dir 口径 (复用其数据目录解析, 不复制业务)
        self.cli = cli
        #: projects.json 路径 (缺省 → cli.data_dir 或 ~/.factory 口径)
        self.projects_file = projects_file
        #: workspace (projects/ 根) — 用于展示 PRD/管线/状态列 (缺省 → ~/.factory)
        self.workspace = Path(workspace) if workspace is not None else Path.home() / ".factory"

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
        """项目清单 + 状态列 (PRD/管线资产/状态) — 识别垃圾名/文档进度。"""
        current = context.current_project
        print(f"项目清单 ({len(projects)} 个)")
        print(f"  {'id':<12} {'名称':<16} {'PRD':<4} {'管线':<6} 状态")
        for item in projects:
            pid = item["id"]
            marker = "  (当前)" if pid == current else ""
            prd, pipeline, status = self._project_brief(pid)
            print(
                f"  {pid:<12} {str(item['name'])[:16]:<16} "
                f"{prd:<4} {pipeline:<6} {status}{marker}"
            )
        if not projects:
            print("  (无项目 — 使用 `factory project create` 注册)")
        print(f"当前项目: {current or '(未选择)'}")
        print("提示: /project <id> 切换; 'P-xxx 改名叫 新名' 改名")
        return 0

    def _project_brief(self, pid: str) -> tuple[str, str, str]:
        """单项目文档进度 (PRD/管线资产数/状态; 失败安全)。"""
        pdir = self.workspace / "projects" / pid
        if not pdir.is_dir():
            return "—", "—", "—"
        prd = "✅" if (pdir / "PRD.md").is_file() else "—"
        artifact_dir = pdir / "artifacts"
        n = (
            len([d for d in artifact_dir.glob("*") if d.is_dir()])
            if artifact_dir.is_dir()
            else 0
        )
        pipeline = f"{n}资产" if n else "—"
        status = ""
        try:
            proj = pdir / "project.json"
            if proj.is_file():
                status = str(json.loads(proj.read_text(encoding="utf-8")).get("status") or "")
        except Exception:  # noqa: BLE001 — 失败安全
            status = ""
        return prd, pipeline, status or "—"

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


class BoardCommand(SlashCommand):
    """/board — 任务监控面板 (todolist+进度条+标签 / graph 依赖图 / chain 任务链 /
    timeline 生命线 / report 汇报导出)。

    用法:
      /board              主线面板（主线 vs 周边 + 进度）
      /board graph [项目]  任务依赖图（plan.json, CRITICAL=★）
      /board chain [项目]  任务链（关键路径 ★ 关键节点 ▲ 汇聚点 + 工期）
      /board timeline     生命线（最近审计事件时间线）
      /board report       生成给 Hermes 的 markdown 汇报
    """

    name = "board"
    description = "任务监控面板 (主线todolist/依赖图/任务链/生命线/汇报)"

    def execute(self, args: str, context: SessionContext) -> int:
        from .board import (
            render_board, render_graph, render_timeline,
            render_chain, render_report,
        )
        from pathlib import Path

        workspace = (
            Path(getattr(context, "workspace", None))
            if getattr(context, "workspace", None)
            else None
        )
        sub = (args or "").strip().split()
        view = sub[0] if sub else "board"
        project = sub[1] if len(sub) > 1 else ""
        try:
            if view == "graph":
                if workspace is None:
                    print("（未设置工作区 — 无法读项目 plan.json）")
                    return 1
                print(render_graph(workspace, project))
            elif view == "chain":
                if workspace is None:
                    print("（未设置工作区 — 无法读项目 plan.json）")
                    return 1
                print(render_chain(workspace, project))
            elif view == "report":
                print(render_report())
            elif view == "timeline":
                if workspace is None:
                    print("（未设置工作区 — 无法读审计事件）")
                    return 1
                print(render_timeline(workspace))
            else:
                print(render_board())
        except Exception as exc:  # noqa: BLE001 — 面板失败不崩溃
            print(f"（面板渲染失败: {exc}）")
            return 1
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


class PreviewCommand(SlashCommand):
    """/preview — 渲染显示 markdown 文件 (/preview PRD.md)。

    S10-105: 只读渲染显示 (rich.Markdown), 不做 HTML 导出 (backlog);
    路径解析: 绝对路径直接用; 相对 → 依次尝试 cwd / context.workspace /
    current_project 目录 (workspace/projects/<slug>) / data_dir 兜底。
    """

    name = "preview"
    description = "渲染显示 markdown 文件 (/preview PRD.md)"

    def execute(self, args: str, context: SessionContext) -> int:
        target = (args or "").strip()
        if not target:
            print("用法: /preview <文件> — 渲染显示 markdown 文件 (例如: /preview PRD.md)")
            return 2
        path = self._resolve(target, context)
        if path is None:
            print(f"❌ 文件不存在: {target} — 检查路径 (相对 cwd/workspace/项目目录)")
            return 2
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 — 读失败 → 友好错误, 不崩溃
            print(f"❌ 读取失败: {target} ({exc})")
            return 2
        render_message(content)
        return 0

    @staticmethod
    def _resolve(target: str, context: SessionContext):
        """路径解析: 绝对 → 直接用; 相对 → cwd → workspace → 项目目录 → data_dir 兜底。"""
        p = Path(target)
        if p.is_absolute():
            return p if p.is_file() else None
        candidates = [Path.cwd() / p]
        workspace = str(getattr(context, "workspace", None) or "").strip() or DEFAULT_PROJECTS_FILE.parent.parent
        ws = Path(workspace)
        candidates.append(ws / p)
        slug = str(getattr(context, "current_project", None) or "").strip()
        if slug:
            candidates.append(ws / "projects" / slug / p)
            # data_dir/projects/<slug>/PRD.md 兜底 (slug=current_project; data_dir 缺省 ~/.factory)
            candidates.append(DEFAULT_PROJECTS_FILE.parent.parent / "projects" / slug / p)
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None


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
    registry.register(
        ProjectCommand(
            cli=cli,
            projects_file=projects_file,
            workspace=(
                Path(getattr(getattr(session, "context", None), "workspace", None))
                if getattr(getattr(session, "context", None), "workspace", None)
                else None
            ),
        )
    )
    registry.register(CostCommand())
    registry.register(PreviewCommand())
    registry.register(BoardCommand())
    registry.register(ExitCommand(session=session))
    return registry
