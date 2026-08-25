"""factory-console/session/commands.py — 基础 Slash 命令 (S10-047 Task 004)。

/help     列出可用命令 (name + description)
/status   显示会话状态 (session/workspace/当前项目/当前 Agent — 来自 SessionContext)
/project  项目列表 (无参=查看) / 切换 current_project (有参=<id>) — 只读
          projects.json (与 FactoryCLI._project_list 同一数据口径 — 复用, 不复制业务)
/cost     成本信息 (CostLedger 只读聚合 + 会话近期活动摘要; 不写任何文件)
/exit     退出会话 (设置宿主 session.running=False)

原则 (S10-046 设计 §6 边界): 命令只做会话内编排, 业务逻辑全部在既有 Service
Layer — 本项目清单只读复用规范数据文件 projects.json (org 写入的同一文件),
零业务复制 (不触碰 ProjectStore/Lifecycle/exec 执行链)。
"""

from __future__ import annotations

import json
import unicodedata
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

    #: 自然语言示例 (输入, 说明) — 与真实意图/动作一致, 不编造
    NL_EXAMPLES: tuple[tuple[str, str], ...] = (
        ("你好 / 我想做一个记账App", "开始对话 / 创建产品 (多轮发现)"),
        ("让PM分析 / 让QA分析", "产品管线 — 7 角色资产链"),
        ("继续 旅行记账", "按名称继续项目"),
        ("给 墨笺 加个导出功能", "需求变更 → 影响分析 (ChangeControl)"),
        ("准备开发", "架构审批门 (Architecture Review)"),
        ("哪些项目有PRD", "真实文档状态"),
        ("P-xxx 改名叫 新名", "项目改名"),
        ("审计追踪 <trace_id>", "链路追踪 (K-4 trace_id 贯穿)"),
    )

    #: 系统命令展示顺序 (显式排序 — 布局稳定; 未列出的命令仍追加, 不丢)
    SLASH_ORDER: tuple[str, ...] = (
        "help", "status", "project", "board", "cost", "preview", "exit",
    )

    #: /board 子命令 (与 BoardCommand 实际子命令一致)
    BOARD_SUBCOMMANDS = (
        "mainline 主线 · graph 依赖图 · chain 任务链 · timeline 生命线 · "
        "replay 执行重放 · project 项目视图 · quality 质量 · cost 成本 · "
        "report 汇报 · done/unmark 标记 · sync 同步 · docs 文档 · default 默认项目"
    )

    #: CLI 命令分组 (系统终端运行 factory 开头; 与 cli_factory build_parser 一致)
    CLI_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("服务/诊断", ("start", "stop", "status", "service", "doctor", "config", "update", "init")),
        ("项目管理", ("project", "create", "demo", "run")),
        ("资产/员工", ("agent", "skill", "mcp", "tools", "task")),
        ("生产/执行", ("exec", "approval", "evidence", "repo", "workload", "router")),
        ("系统", ("audit", "rag", "llm", "todo", "help")),
    )

    @staticmethod
    def _disp_len(text: str) -> int:
        """终端显示宽度 (CJK 算 2 — 对齐不再乱)。"""
        return sum(
            2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
            for ch in text
        )

    def _print_rows(self, pairs: list[tuple[str, str]]) -> None:
        """对齐打印 (左列按显示宽度补空格, CJK 对齐)。"""
        width = max(self._disp_len(l) for l, _ in pairs)
        for left, right in pairs:
            print(f"  {left}{' ' * (width - self._disp_len(left))}  {right}")

    def execute(self, args: str, context: SessionContext) -> int:
        if self.registry is None:
            print("错误: 命令表不可用 (registry 未注入)")
            return 1

        # ── 自然语言 ──
        print("💬 自然语言示例 (直接输入即可):")
        self._print_rows([(left, right) for left, right in self.NL_EXAMPLES])
        print()

        # ── 系统命令 ──
        by_name = {c.name: c for c in self.registry.list()}
        items = [by_name[n] for n in self.SLASH_ORDER if n in by_name]
        items += [c for c in self.registry.list() if c.name not in self.SLASH_ORDER]
        print("📁 系统命令:")
        self._print_rows([(f"/{c.name}", c.description) for c in items])
        if "board" in by_name:
            print(f"  /board 子命令: {self.BOARD_SUBCOMMANDS}")
        print()

        # ── CLI 命令 ──
        print("🛠 CLI 命令 (系统终端运行, factory 开头):")
        group_width = max(self._disp_len(g) for g, _ in self.CLI_GROUPS)
        for group, cmds in self.CLI_GROUPS:
            pad = " " * (group_width - self._disp_len(group))
            print(f"  {group}{pad}  {' · '.join(cmds)}")
        print("  详细: factory <子命令> --help")
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
    """/project — 项目列表 (无参) / 切换当前项目 (/project <id>) /
    需求变更 (/project change <id|名称> "变更内容")。"""

    name = "project"
    description = "项目列表/切换当前项目/需求变更 (/project [<id>|change ...])"

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
        # S10-10x: workspace 优先 — 会话自定义 workspace 时, 项目清单跟随工作区
        # (org/projects.json), 而非硬编码 ~/.factory (默认 workspace=~/.factory, 行为不变)
        if self.workspace is not None:
            return Path(self.workspace) / "org" / "projects.json"
        return DEFAULT_PROJECTS_FILE

    def execute(self, args: str, context: SessionContext) -> int:
        projects = read_projects(self._projects_file())
        if not args:
            return self._show(projects, context)
        arg = args.strip()
        # S10-110: /project delete <id|全部未命名> — 危险操作, 需确认 (y/N)
        if arg.startswith("delete") or arg.startswith("删除"):
            return self._delete(arg, projects, context)
        # S10-111 M3-6: /project change <id|名称> "变更内容" — 需求变更回流
        if arg.startswith("change") or arg.startswith("变更"):
            return self._change(arg, projects, context)
        return self._switch(arg, projects, context)

    def _delete(self, arg: str, projects: list[dict[str, Any]], context: SessionContext) -> int:
        """删除项目 (危险操作): 确认目标 → y/N 确认 → 执行。"""
        parts = arg.split(None, 1)
        target = parts[1].strip() if len(parts) > 1 else ""
        if not target:
            print("用法: /project delete <项目ID 或 名称> · /project delete 全部未命名")
            return 2
        if target in ("全部未命名", "所有未命名", "all-unnamed"):
            candidates = [p for p in projects if str(p.get("name") or "").startswith("未命名产品")]
        else:
            candidates = [p for p in projects if p["id"] == target or p["name"] == target]
        if not candidates:
            print(f"未找到要删除的项目: {target}")
            return 1
        print(f"⚠️ 将删除 {len(candidates)} 个项目 (危险操作, 不可恢复):")
        for p in candidates:
            print(f"  - {p['id']}  {p['name']}")
        confirm = input("确认删除? (y/N) ")
        if confirm.strip().lower() not in ("y", "yes"):
            print("已取消删除")
            return 0
        # 执行: 复用 actions.delete_project
        from .actions import delete_project as _delete_action
        from .action import ExecutionContext, IntentObject
        import sys as _sys
        from pathlib import Path as _Path
        scope = "全部未命名" if target in ("全部未命名", "所有未命名", "all-unnamed") else ""
        pid = "" if scope else target
        intent = IntentObject(intent_type="delete_project", params={"scope": scope, "target": pid},
                              raw=arg, source="session")
        ws = self.workspace or _Path.home() / ".factory"
        ctx = ExecutionContext(workspace=ws, session=None, user="user",
                               project=None, intent=intent)
        result = _delete_action(ctx)
        print(result.message or ("✅ 删除完成" if result.ok else "❌ 删除失败"))
        return 0 if result.ok else 1

    def _change(
        self, arg: str, projects: list[dict[str, Any]], context: SessionContext
    ) -> int:
        """需求变更回流 (S10-111 M3-6): /project change <id|名称> "加导出"。

        复用 actions.change_project: propose → impact → ConfirmationGate y/N →
        y → PRD v2 + 新任务合并 tasks/plan; n → 已拒绝, 未变更。
        """
        parts = arg.split(None, 2)
        if len(parts) < 3:
            print('用法: /project change <项目ID 或 名称> "变更内容"')
            print('示例: /project change crm "加导出"')
            return 2
        target = parts[1].strip()
        request = parts[2].strip().strip('"\'')
        if not target or not request:
            print('用法: /project change <项目ID 或 名称> "变更内容"')
            return 2
        tlow = target.lower()
        candidates = [
            p for p in projects
            if p["id"].lower() == tlow or str(p["name"] or "").lower() == tlow
        ]
        if not candidates:
            print(f"未找到要变更的项目: {target}")
            return 1
        pid = candidates[0]["id"]
        pname = str(candidates[0].get("name") or "")
        slug = self._resolve_slug(pid, pname)
        from .action import ExecutionContext as _EC
        from .action import IntentObject as _IO
        from .actions import change_project as _change_action
        from pathlib import Path as _Path
        intent = _IO(
            intent_type="change_project",
            params={"project_id": slug, "request": request},
            raw=arg,
            source="session",
        )
        ws = self.workspace or _Path.home() / ".factory"
        ctx = _EC(workspace=ws, session=None, user="user", project=None, intent=intent)
        result = _change_action(ctx)
        print(result.message)
        return 0 if result.ok else 1

    def _resolve_slug(self, pid: str, pname: str) -> str:
        """org id/名称 → projects/<slug> 目录名 (S10-111 M3-6: change_control 按 slug 落盘)。

        目录名/pid 直配优先; 否则按 product.json name 扫描 (失败安全 → pid 原值)。
        """
        ws = self.workspace or Path.home() / ".factory"
        projects_root = Path(ws) / "projects"
        for direct in (pid, pname):
            if direct and (projects_root / str(direct)).is_dir():
                return str(direct)
        try:
            for pdir in sorted(projects_root.iterdir()):
                if not pdir.is_dir():
                    continue
                pf = pdir / "product.json"
                if not pf.is_file():
                    continue
                data = json.loads(pf.read_text(encoding="utf-8"))
                if str(data.get("name") or "") == pname or pdir.name == pid:
                    return pdir.name
        except Exception:  # noqa: BLE001 — 失败安全
            pass
        return str(pid)

    def _show(self, projects: list[dict[str, Any]], context: SessionContext) -> int:
        """项目清单 + 状态列 (PRD/管线资产/状态) — 识别垃圾名/文档进度。"""
        current = context.current_project
        print(f"项目清单 ({len(projects)} 个)")
        print(f"  {'id':<14} {'名称':<14} {'PRD':<4} {'生命周期':<12} {'任务':<6} 更新")
        for item in projects:
            pid = item["id"]
            marker = "  (当前)" if pid == current else ""
            prd, lifecycle, task, update = self._project_brief(pid)
            print(
                f"  {pid:<14} {str(item['name'])[:14]:<14} "
                f"{prd:<4} {lifecycle:<12} {task:<6} {update}{marker}"
            )
        if not projects:
            print("  (无项目 — 使用 `factory project create` 注册)")
        print(f"当前项目: {current or '(未选择)'}")
        print("提示: /project <id> 切换; 'P-xxx 改名叫 新名' 改名")
        return 0

    def _project_brief(self, pid: str) -> tuple[str, str, str, str]:
        """单项目多维度 (PRD/生命周期/任务进度/最近更新; 失败安全)。"""
        pdir = self.workspace / "projects" / pid
        if not pdir.is_dir():
            return "—", "—", "—", "—"
        prd = "✅" if (pdir / "PRD.md").is_file() else "—"
        lifecycle = "—"
        task = "—"
        update = "—"
        try:
            from . import board as _b
            stages = _b._project_stage_status(self.workspace, pid)
            done = sum(1 for st in stages if st["done"])
            cur = next((st for st in stages if not st["done"]), None)
            lifecycle = f"{done}/11" + (f" {cur['label']}" if cur else " 完成")
            tp = _b._project_task_progress(self.workspace, pid)
            task = f"{tp['done']}/{tp['total']}" if tp["total"] else "—"
            pf = pdir / "product.json"
            if pf.is_file():
                import datetime
                update = datetime.datetime.fromtimestamp(pf.stat().st_mtime).strftime("%m-%d %H:%M")
        except Exception:  # noqa: BLE001 — 失败安全
            pass
        return prd, lifecycle, task, update

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
    """/cost — 成本信息 (S10-119 M4-4/D-6: CostLedger 只读聚合 + 会话近期活动摘要)。"""

    name = "cost"
    description = "成本/用量信息 (CostLedger 只读聚合 + 会话近期活动)"

    def execute(self, args: str, context: SessionContext) -> int:
        print("=== 成本/用量 (只读) ===")
        # S10-119 M4-4/D-6: CostLedger 真实聚合 (只读, 不写任何文件)
        try:
            from .cost_ledger import CostLedger
            from .budget import ProjectBudget, BudgetUsage, BudgetEnforcer

            ws_val = getattr(context, "workspace", None) or str(Path.home() / ".factory")
            ws = Path(ws_val)
            ledger = CostLedger(file=ws / "cost" / "cost_records.json")
            agg = ledger.aggregate()
            if agg.get("record_count"):
                print(
                    f"总成本: ${agg['total_cost']:.4f} USD · {agg['total_tokens']} tokens"
                    f" · {agg['record_count']} 条"
                )
                print(
                    f"分项: 规划 ${agg['planning_cost']:.4f} · 执行 ${agg['execution_cost']:.4f}"
                    f" · 修复 ${agg['repair_cost']:.4f} · 重规划 ${agg['replanning_cost']:.4f}"
                )
                by_agent = agg.get("by_agent") or {}
                if by_agent:
                    top = sorted(by_agent.items(), key=lambda kv: -float(kv[1].get("cost") or 0.0))[:5]
                    print("每 Agent: " + " · ".join(
                        f"{aid} ${float(v.get('cost') or 0.0):.4f}" for aid, v in top
                    ))
                budget = ProjectBudget()
                usage = BudgetUsage.from_records(ledger.records(), budget=budget)
                print(f"预算等级: {BudgetEnforcer.check(budget, usage)['level']}")
            else:
                print("无成本记录 (执行后自动回填 cost_records.json)")
        except Exception as exc:  # noqa: BLE001 — 只读展示失败安全
            print(f"（成本聚合失败: {exc}）")
        print(f"session_id: {context.session_id}")
        recent = context.history[-RECENT_LIMIT:]
        if recent:
            print("近期活动:")
            for line in recent:
                print(f"  {line}")
        return 0


class BoardCommand(SlashCommand):
    """/board — 任务监控面板 (todolist+进度条+标签 / graph 依赖图 / chain 任务链 /
    timeline 生命线 / report 汇报导出)。

    用法:
      /board              主线面板（主线 vs 周边 + 进度）
      /board graph [项目]  任务依赖图（plan.json, CRITICAL=★）
      /board chain [项目]  任务链（关键路径 ★ 关键节点 ▲ 汇聚点 + 工期）
      /board timeline     生命线（最近审计事件时间线）
      /board replay <exec_id>  执行重放: dry-run 时间线 (默认) / --re-exec 同输入重跑 /
                              --compare <exec2_id> 对比 (缺省最近一次) / --save 落盘
      /board project      项目列表（select 切换）
      /board project <slug>  单项目管理视图（全生命周期, 只读）
      /board quality [项目] 执行质量展示（S10-117 K-2, 只读 — 最近执行 + PRD/工程质量）
      /board cost [项目]   成本可视化（S10-119 M4-4/D-6, 只读 — 每项目/每任务实际成本）
      /board report       生成给 Hermes 的 markdown 汇报
      /board report --save  汇报落盘到 docs/sprint10/
      /board done <id>      标记主线任务完成（如 /board done M3-1）
      /board unmark <id>    取消完成标记
      /board sync           自动同步主线（从代码证据推断完成）
    """

    name = "board"
    description = "任务监控面板 (主线todolist/依赖图/任务链/生命线/汇报)"

    def execute(self, args: str, context: SessionContext) -> int:
        from .board import (
            render_board, render_graph, render_timeline,
            render_chain, render_report, render_project_lifecycle,
            render_projects_list, render_project_report, render_quality,
            render_cost,
            _read_default_project, _set_default_project, split_task,
            read_docs_config, write_docs_config,
            mark_backlog_item, save_report, sync_mainline,
        )
        from pathlib import Path

        # S10-110: 会话未显式设 workspace → 默认 ~/.factory (与 actions.DEFAULT_WORKSPACE 同口径)
        ws_val = getattr(context, "workspace", None) or str(Path.home() / ".factory")
        workspace = Path(ws_val)
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
            elif view == "quality":
                # S10-117 K-2: 执行质量展示 (只读 — 渲染不写任何文件)
                if workspace is None:
                    print("（未设置工作区 — 无法读执行质量）")
                    return 1
                print(render_quality(workspace, project))
            elif view == "cost":
                # S10-119 M4-4/D-6: 成本可视化 (只读 — 渲染不写任何文件)
                if workspace is None:
                    print("（未设置工作区 — 无法读成本）")
                    return 1
                print(render_cost(workspace, project))
            elif view == "report":
                if project:
                    print(render_project_report(workspace, project))
                elif "--save" in (args or ""):
                    print(save_report())
                else:
                    print(render_report())
            elif view == "default":
                # S10-110: 默认项目 (首页优先打开) — /board default 查看 / default <slug> 设置
                if not project:
                    cur = _read_default_project(workspace) if workspace else ""
                    print(f"默认项目: {cur or '（未设置 — /board default <slug> 设置）'}")
                else:
                    ok = _set_default_project(workspace, project) if workspace else ""
                    print(f"✅ 默认项目已设为: {ok or project}（board 首页将优先打开它）")
            elif view == "task":
                # /board task split <slug> <任务ID> <子任务1,子任务2> — 细化任务 (L 层+1)
                if len(sub) < 5 or sub[1] != "split":
                    print("用法: /board task split <项目slug> <任务ID> <子任务1,子任务2,...>")
                    return 2
                if workspace is None:
                    print("（未设置工作区 — 无法细化任务）")
                    return 1
                slug_arg, task_id = sub[2], sub[3]
                names = [n.strip() for n in " ".join(sub[4:]).split(",") if n.strip()]
                created = split_task(workspace, slug_arg, task_id, names)
                if created:
                    print(f"✅ 已细化 {task_id} → {len(created)} 个子任务: "
                          f"{', '.join(t['id'] for t in created)}")
                else:
                    print(f"❌ 细化失败: 任务 {task_id} 不存在或子任务为空")
            elif view == "docs":
                # /board docs list <slug> / add-dir <slug> <路径> / add-ext <slug> <ext>
                if len(sub) < 2:
                    print("用法: /board docs list <项目> · add-dir <项目> <目录> · add-ext <项目> <扩展名> · rm-dir <项目> <目录>")
                    return 2
                if workspace is None:
                    print("（未设置工作区）")
                    return 1
                action, slug_arg = sub[1], sub[2] if len(sub) > 2 else ""
                cfg = read_docs_config(workspace, slug_arg)
                if action == "list":
                    print(f"📂 文档目录 ({len(cfg['dirs'])}):")
                    for d in cfg["dirs"]:
                        print(f"  {d}")
                    print(f"🔤 扩展名 ({len(cfg['exts'])}): {', '.join(cfg['exts'])}")
                elif action == "add-dir" and len(sub) >= 4:
                    path = sub[3]
                    if path not in cfg["dirs"]:
                        cfg = write_docs_config(workspace, slug_arg, dirs=cfg["dirs"] + [path])
                    print(f"✅ 文档目录已更新 ({len(cfg['dirs'])}):")
                    for d in cfg["dirs"]:
                        print(f"  {d}")
                elif action == "add-ext" and len(sub) >= 4:
                    ext = sub[3] if sub[3].startswith(".") else f".{sub[3]}"
                    if ext not in cfg["exts"]:
                        cfg = write_docs_config(workspace, slug_arg, exts=cfg["exts"] + [ext])
                    print(f"✅ 扩展名已更新: {', '.join(cfg['exts'])}")
                elif action == "rm-dir" and len(sub) >= 4:
                    path = sub[3]
                    cfg = write_docs_config(workspace, slug_arg, dirs=[d for d in cfg["dirs"] if d != path])
                    print(f"✅ 文档目录已移除 ({len(cfg['dirs'])}):")
                    for d in cfg["dirs"]:
                        print(f"  {d}")
                else:
                    print("用法: /board docs list|add-dir|add-ext|rm-dir <项目> [值]")
            elif view == "sync":
                marked = sync_mainline(
                    Path(__file__).resolve().parents[1] / ".." / "docs" / "sprint10" / "待办清单-已发现未落地.md")
                print(("✅ 自动同步主线: " + ", ".join(marked)) if marked else "主线已同步（无需新标记）")
            elif view in ("done", "unmark"):
                if len(sub) < 2:
                    print("用法: /board done <任务ID>  例: /board done M3-1")
                    return 2
                print(mark_backlog_item(Path(__file__).resolve().parents[1] / ".." / "docs" / "sprint10" / "待办清单-已发现未落地.md", sub[1], done=(view == "done")))
            elif view == "project":
                # S10-110: 单项目管理视图 (只读) — 无参=项目列表(select), 有参=生命周期视图
                if workspace is None:
                    print("（未设置工作区 — 无法读项目）")
                    return 1
                if not project:
                    print(render_projects_list(workspace))
                else:
                    print(render_project_lifecycle(workspace, project))
            elif view == "replay":
                # S10-113 M5-1: /board replay <exec_id> [--re-exec] [--compare <id2>] [--save]
                if len(sub) < 2:
                    print("用法: /board replay <exec_id> [--re-exec] [--compare <exec2_id>] [--save]")
                    print("  dry-run (默认): 重建执行时间线 (records + audit 事件)")
                    print("  --re-exec:      同输入重跑 → 新 exec_id 记录")
                    print("  --compare <id2>: 两次执行对比 (缺省对比最近一次) + --save 落盘 docs/sprint10/")
                    return 2
                exec_id = sub[1]
                rest = sub[2:]
                mode = "dry_run"
                compare_with = ""
                if "--re-exec" in rest:
                    mode = "re_exec"
                if "--compare" in rest:
                    mode = "compare"
                    idx = rest.index("--compare")
                    compare_with = rest[idx + 1] if len(rest) > idx + 1 else ""
                save = "--save" in rest
                try:
                    from .actions import _replay_rerun_runner
                    from .execution_replay import ReplayEngine, ReplayError

                    engine = ReplayEngine(workspace=workspace)
                    if mode == "re_exec":
                        runner = _replay_rerun_runner(
                            workspace,
                            context,
                            user="user",
                            project=getattr(context, "current_project", None),
                        )
                        new_id = engine.re_exec(exec_id, runner)
                        print(f"✅ 重跑完成: {exec_id} → 新执行 {new_id} (记录含 input_snapshot, 可对比)")
                    elif mode == "compare":
                        if not compare_with:
                            compare_with = engine.latest_exec_id(exclude=exec_id) or ""
                        if not compare_with:
                            print(f"❌ 对比失败: 缺少第二个 exec_id 且无最近记录 ({exec_id})")
                            return 1
                        save_path = None
                        if save:
                            save_path = (
                                Path(__file__).resolve().parents[1] / ".." / "docs" / "sprint10"
                            )
                        report = engine.compare(exec_id, compare_with, save_to=save_path)
                        print(report)
                        if save_path is not None:
                            target = save_path / f"replay-compare-{exec_id}-{compare_with}.md"
                            print(f"\n✅ 对比报告已落盘: {target}")
                    else:
                        print(engine.dry_run(exec_id).to_markdown())
                except ReplayError as exc:
                    print(f"❌ 重放失败: {exc}")
                    return 1
            elif view == "timeline":
                if workspace is None:
                    print("（未设置工作区 — 无法读审计事件）")
                    return 1
                print(render_timeline(workspace, project_id=project))
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
