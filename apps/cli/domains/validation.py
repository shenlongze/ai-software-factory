"""验收 域命令注册（apps/cli/domains/validation）。

本域命令（依据 `apps/cli/registry.py`）:
    verification  Verification SSOT (P0-F3): list/get — ver-* 事实查询
    evd / evidence / eval   待搬（本刀只做 verification）

搬迁来源: 老 CLI `_pending_migration/factory_console/cli_factory.py`
          · 参数注册 p_ver（L9593）· 处理 verification_cmd（L8151）
底层能力: **已在新地基** `services/validation/verification_store.py`
          （该模块 2026-09-15 从老区迁入, 所以本刀不涉及任何老区依赖）
"""
from __future__ import annotations

from typing import Any, Callable


def register(sub: Any, json_opt: Callable[[Any], None]) -> None:
    """注册 validation 域的命令。sub = 主 subparsers 容器; json_opt = 共享的 --json 选项。"""
    # factory verification [list|get] [id] [--task-run X] [--exs X]
    p_ver = sub.add_parser(
        "verification", help="Verification SSOT (P0-F3): list/get — ver-* 事实查询"
    )
    json_opt(p_ver)
    p_ver.add_argument("action", nargs="?", default="list", choices=["list", "get"],
                       help="动作: list 全部(可过滤) / get 单条")
    p_ver.add_argument("verification_id", nargs="?", help="ver-* id (get 用)")
    p_ver.add_argument("--task-run", default="", help="按 task_run_id (run-*) 过滤")
    p_ver.add_argument("--exs", default="", help="按 exs_id (EXS-*) 过滤")

    # factory evd [list|get] [id] [--verification X] —— Evidence SSOT (P0-F4)
    # 搬迁来源: 老 CLI p_evd（cli_factory L9607）· handler evd_cmd（L8217）
    # 底层: 已在新地基 `services/validation/evidence_store.py`（今天从老区迁入）⇒ 零老区依赖 ✓
    p_evd = sub.add_parser("evd", help="Evidence (P0-F4): list/get — canonical EVD-*")
    json_opt(p_evd)
    p_evd.add_argument("action", nargs="?", default="list", choices=["list", "get"],
                       help="动作: list 全部 / get 单条")
    p_evd.add_argument("evidence_id", nargs="?", help="EVD-* id (get 用)")
    p_evd.add_argument("--verification", default="", help="按 verification_id (ver-*) 过滤")
