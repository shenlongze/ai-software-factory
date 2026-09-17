"""任务拆解 域命令注册（apps/cli/domains/decomposition）。

本域命令（依据 `apps/cli/registry.py` 的 `decomposition`）:
    kanban     看板: 按状态/项目/角色/执行人分列显示任务
    task / tasktree / todo     ← 待搬

搬迁来源: 老 CLI `_pending_migration/factory_console/cli_factory.py`
          · 参数注册 p_kb（L9528）· 处理 kanban（L9538+）
          · 辅助 `_task_rows`（L783, 合并两源读任务）+ `_load_json_safe`（同文件）

★ 为什么辅助函数在新 CLI 里【重写】而不是搬原文件:
  `_load_json_safe` 在老区被 20 处引用 —— 搬它会牵动 20 个调用点（违反"先搬叶子"）。
  它是 7 行纯函数（读 JSON, 失败返 None）, 重写零风险。
  `_task_rows` 只被 4 处引用, 照搬其逻辑（读 tasks/*.json + workspace backlog + 角色/分配补列）。
"""
from __future__ import annotations

from typing import Any, Callable


def register(sub: Any, json_opt: Callable[[Any], None]) -> None:
    """注册 decomposition 域的命令。sub = 主 subparsers 容器; json_opt = 共享的 --json 选项。"""
    # factory kanban —— 看板视图
    p_kb = sub.add_parser("kanban", help="看板: 按状态分列显示任务（复用 task 数据 ✓）")
    json_opt(p_kb)
    p_kb.add_argument("--project", default="", help="只看某个项目 (可选)")
    p_kb.add_argument("--all", action="store_true", help="每列不限条数")
    p_kb.add_argument("--group", default="status",
                      choices=["status", "project", "role", "agent"],
                      help="分列维度: status(默认)/project/role/agent")
