"""审计 域命令注册（api/cli/domains/audit）—— 样板（第一个拆出来的域）。

本域命令（依据 `apps/cli/registry.py`）:
    event  事件查询 → 子命令 logs

为什么挑 audit 做样板: 它是**零冲突**域 —— 新 CLI 里只有 `event` 一个命令,
而现有 factory 入口里 audit / history / memory / memory-lifecycle / entity 都不撞名。

搬迁范围（本刀）: **只搬参数注册**。dispatch（main.py 的 if/elif 链）与
_print_event_logs、handler（commands.py 的 cmd_event_logs）暂留原处 ——
先让"注册按域分"落地并验证命令面不变, 再逐域搬实现。
"""
from __future__ import annotations

from typing import Any, Callable


def register(sub: Any, json_opt: Callable[[Any], None]) -> None:
    """注册 audit 域的命令。sub = 主 subparsers 容器; json_opt = 共享的 --json 选项。"""
    p_event = sub.add_parser("event", help="事件查询")
    json_opt(p_event)
    esub = p_event.add_subparsers(dest="event_command", required=True)
    p_logs = esub.add_parser(
        "logs",
        help="事件日志查询, 倒序 (发 system.logs_viewed; --workspace 发 workspace.events.viewed)",
    )
    json_opt(p_logs)
    p_logs.add_argument("--limit", type=int, default=20, help="条数上限 (默认 20)")
    p_logs.add_argument("--project", default=None, help="按项目过滤")
    p_logs.add_argument("--task", default=None, help="按任务过滤")
    p_logs.add_argument("--workspace", action="store_true",
                        help="跨项目事件时间线 (全量最近事件, 含 project 列, 发 workspace.events.viewed)")

    # factory history [search|index|stats] [词] [--limit N] [--source X] —— 历史检索（FTS5）
    # 搬迁来源: 老 CLI p_hist（cli_factory L10252）· handler history_cmd（L9044）
    # 底层: 已在新地基 `services/learning/history_search`（HistoryIndex）⇒ 零老区依赖 ✓
    p_hist = sub.add_parser(
        "history", help="历史检索 (search/index/stats) — FTS5, 中文可搜; 知识域"
    )
    json_opt(p_hist)
    p_hist.add_argument("history_action", choices=["search", "index", "stats"],
                        nargs="?", default="search", help="动作 (默认 search)")
    p_hist.add_argument("history_query", nargs="?", default="", help="检索词")
    p_hist.add_argument("--limit", type=int, default=8, help="返回条数 (默认 8)")
    p_hist.add_argument("--source", default="", help="限定来源: event/trace/experience")
