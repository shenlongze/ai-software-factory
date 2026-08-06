"""dashboard/renderer.py — DashboardRenderer: Rich 渲染 (FactorySnapshot → 文本)。

设计依据:
- dashboard-design.md §3: Rich 实时表格; 非 TTY 自动退化为单次输出 (管道/CI 安全)
- phase4c4-status.md: DashboardRenderer (Rich) 展示六视图
  (Overview/Tasks/Agents/Workflows/Executions/Recovery)
- phase5a1-status.md: 新增第七视图 Runtime Catalog (ADR-0014 决策 6)

render() 返回纯文本 (Console.export_text 剥离 ANSI 样式码) — 测试断言与管道输出
均无转义码; TTY 下由 Rich 自动着色 (颜色语义见 views.py §1.4)。

无状态渲染: 每次调用都是"快照 → 文本"纯函数, 不做事件订阅缓存 (KISS,
dashboard-design.md §1.2)。
"""

from __future__ import annotations

import io
from typing import Any

from rich.console import Console, Group

from . import views
from .models import FactorySnapshot

# 单视图名 (build_<name> 与 views.py 构建函数一一对应; "all" 为八视图同屏,
# "workspace" 为 Phase 6B Workspace Summary 视图组 — dashboard --workspace 默认)
VIEWS = (
    "overview", "tasks", "agents", "workflows", "executions", "recovery", "catalog",
    "metrics", "workspace", "projects", "agents_utilization", "runtime_usage",
    "workspace_events", "git", "change", "changeflow", "understanding", "provider",
    "product", "lifecycle",
)

_SINGLE = {
    "tasks": views.build_tasks,
    "agents": views.build_agents,
    "workflows": views.build_workflows,
    "executions": views.build_executions,
    "recovery": views.build_recovery,
    "catalog": views.build_catalog,
    "metrics": views.build_metrics,
    "projects": views.build_projects,              # Phase 6A Projects View (ADR-0016)
    "workspace": views.build_workspace,            # Phase 6B Workspace Summary (ADR-0017)
    "agents_utilization": views.build_agent_utilization,  # Phase 6B (ADR-0017)
    "runtime_usage": views.build_runtime_usage,           # Phase 6B (ADR-0017)
    "workspace_events": views.build_workspace_events,     # Phase 6B (ADR-0017)
    "git": views.build_git,                        # Phase 6C Git View (ADR-0018)
    "change": views.build_change,                  # Phase 6D Change View (ADR-0019)
    "changeflow": views.build_changeflow,          # Phase 6E Change Flow View (ADR-0020)
    "understanding": views.build_understanding,    # Phase 7 Understanding View (ADR-0021)
    "provider": views.build_provider,              # Phase 8A Provider View (ADR-0022)
    "product": views.build_product,                # Phase 9A Product View (ADR-0026)
    "lifecycle": views.build_lifecycle,            # Phase 9d Lifecycle View (ADR-0029)
}


class DashboardRenderer:
    """Rich 渲染器: FactorySnapshot → 终端文本 (七视图同屏或单视图)。"""

    def __init__(self, *, width: int = 100, limit: int = 10) -> None:
        self._width = max(40, width)
        self._limit = max(1, limit)

    # ------------------------------------------------------------------ 构建

    def build(self, snapshot: FactorySnapshot, view: str = "all") -> Any:
        """构建 Rich renderable 树 (测试可复用; 非法 view 抛 ValueError)。"""
        if view == "all":
            return Group(
                views.build_header(snapshot),
                views.build_tasks(snapshot),
                views.build_agents(snapshot),
                views.build_workflows(snapshot),
                views.build_executions(snapshot),
                views.build_projects(snapshot),  # Phase 6A Projects View (ADR-0016)
                views.build_catalog(snapshot),
                views.build_metrics(snapshot),
                views.build_recovery(snapshot),
                views.build_recent_events(snapshot, limit=self._limit),
            )
        if view == "overview":
            return Group(
                views.build_header(snapshot),
                views.build_recent_events(snapshot, limit=self._limit),
            )
        builder = _SINGLE.get(view)
        if builder is None:
            raise ValueError(
                f"unknown dashboard view: {view!r} (expected one of: all, {', '.join(VIEWS)})"
            )
        return builder(snapshot)

    # ------------------------------------------------------------------ 渲染

    def render(self, snapshot: FactorySnapshot, view: str = "all") -> str:
        """渲染为纯文本 (无 ANSI 转义码, 管道/CI 安全)。

        注意: Console 必须挂 StringIO 文件 — record=True 只负责录制, 不会抑制
        写文件; 否则 console.print 会把内容同时打到真实 stdout, 与调用方
        print(render(...)) 叠加成双份输出 (CLI 冒烟曾复现)。
        """
        console = Console(
            record=True, width=self._width, color_system=None, file=io.StringIO()
        )
        console.print(self.build(snapshot, view=view))
        return console.export_text()
