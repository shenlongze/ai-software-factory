"""运维 域命令注册（apps/cli/domains/operations）。

本域命令（依据 `apps/cli/registry.py`）:
    checkpoint  Checkpoint 管理（子命令 create / list）
    recover     恢复中断任务（事件回放重建 + 状态纠正）

搬迁范围（本刀）: **只搬参数注册** —— dispatch / print / handler 暂留原处。
命令面必须一字不变（顶层命令数 + 子命令 + 参数三项对比验证）。
"""
from __future__ import annotations

from typing import Any, Callable


def register(sub: Any, json_opt: Callable[[Any], None]) -> None:
    """注册 operations 域的命令。sub = 主 subparsers 容器; json_opt = 共享的 --json 选项。"""
    # factory checkpoint <sub>
    p_checkpoint = sub.add_parser(
        "checkpoint", help="Checkpoint 管理: 停靠点快照 (发 recovery.* 事件)"
    )
    json_opt(p_checkpoint)
    csub = p_checkpoint.add_subparsers(dest="checkpoint_command", required=True)
    p_cp_create = csub.add_parser("create", help="创建任务 checkpoint 快照 (发 recovery.started/completed)")
    json_opt(p_cp_create)
    p_cp_create.add_argument("task_id", help="任务 ID (如 T-001)")
    p_cp_list = csub.add_parser("list", help="Checkpoint 列表 (发 recovery.started)")
    json_opt(p_cp_list)

    # factory recover
    p_recover = sub.add_parser(
        "recover", help="恢复中断任务: 事件回放重建 + 状态纠正 (发 recovery.started/completed/failed)"
    )
    json_opt(p_recover)
    p_recover.add_argument("task_id", help="任务 ID (如 T-001)")

    # factory backup <动作> [文件] —— 数据保护（X-1/D-1）
    # 搬迁来源: 老 CLI p_backup（cli_factory L9400）
    # 底层: 已在新地基 `services/operations/backup.py`（本域今天刚迁入）⇒ 零老区依赖 ✓
    p_backup = sub.add_parser(
        "backup", help="数据保护 (X-1/D-1): 备份/清单/恢复 ~/.factory"
    )
    json_opt(p_backup)
    p_backup.add_argument(
        "backup_command", choices=["create", "list", "restore"], metavar="动作",
        help="create — 备份数据目录; list — 备份清单; restore <文件> — 恢复",
    )
    p_backup.add_argument("backup_file", nargs="?", default=None, help="备份文件 (restore)")
    p_backup.add_argument("--dir", default=None, help="备份目录 (缺省 ~/.factory-backups)")
