"""监控 域命令注册（api/cli/domains/metrics）。

本域命令（依据 `apps/cli/registry.py`）:
    dashboard  只读控制台总览（Rich 视图; --workspace 跨项目运营视图组）
    metrics    工厂生产指标（六域指标 + 失败原因; --workspace 项目对比表）

搬迁范围（本刀）: **只搬参数注册** —— dispatch / print / handler 暂留原处。
命令面必须一字不变（顶层命令数 + 子命令 + 参数三项对比验证）。
"""
from __future__ import annotations

from typing import Any, Callable


def register(sub: Any, json_opt: Callable[[Any], None]) -> None:
    """注册 metrics 域的命令。sub = 主 subparsers 容器; json_opt = 共享的 --json 选项。"""
    # factory dashboard
    p_dashboard = sub.add_parser(
        "dashboard", help="只读控制台总览: Rich 视图 (发 dashboard.viewed; --workspace 发 workspace.dashboard.viewed)"
    )
    json_opt(p_dashboard)
    p_dashboard.add_argument(
        "--view", default=None,
        help="单视图: overview/tasks/agents/workflows/executions/recovery/catalog/metrics/"
             "workspace/projects/agents_utilization/runtime_usage/workspace_events/git "
             "(默认 all 同屏; --workspace 默认 workspace 视图组)",
    )
    p_dashboard.add_argument("--limit", type=int, default=10, help="最近事件条数上限 (默认 10)")
    p_dashboard.add_argument("--project", default=None, help="按项目过滤 (任务/事件维度)")
    p_dashboard.add_argument("--workspace", action="store_true",
                             help="Workspace Summary: 跨项目运营视图组 (Projects/Agent Utilization/Runtime/Metrics/Events)")

    # factory metrics (Phase 5B, ADR-0015; Phase 6B --workspace, ADR-0017)
    p_metrics = sub.add_parser(
        "metrics", help="工厂生产指标: 六域指标 + 失败原因 (只读, 发 metrics.viewed; --workspace 发 workspace.metrics.viewed)"
    )
    json_opt(p_metrics)
    p_metrics.add_argument("--project", default=None, help="按项目过滤 (任务/事件维度)")
    p_metrics.add_argument("--workspace", action="store_true",
                           help="Workspace 项目对比表 (复用 MetricsCollector 每项目聚合)")
