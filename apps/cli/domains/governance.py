"""治理 域命令注册（apps/cli/domains/governance）。

本域命令（依据 `apps/cli/registry.py` 的 `governance`）:
    approval           审批门（list / decide / apply）
    approval-request / governance     ← 待搬

搬迁来源: 老 CLI `_pending_migration/factory_console/cli_factory.py`
          · 参数注册 p_approval（L9432）· 处理 approval（L9444+）
          · 辅助 `_approval_via_runtime` / `_filter_approvals_by_project` / `_print_approval_result`

★ 特别之处（老 CLI 的注释）: 这个命令**已经在用绞杀者模式**:
    "默认走新实现 ai_factory_os.services.governance; 异常 fallback 旧实现
     FACTORY_APPROVAL_OLD=1 → 强制旧（对比用）; FACTORY_APPROVAL_NEW=1 → 强制新（不 fallback）"
  ⇒ 本刀把它的【新实现路径】搬进新 CLI（list / decide 直连 services/governance）,
    **不再保留 fallback 到老实现**（老实现本来就是要退役的那一侧）。
"""
from __future__ import annotations

from typing import Any, Callable


def register(sub: Any, json_opt: Callable[[Any], None]) -> None:
    """注册 governance 域的命令。sub = 主 subparsers 容器; json_opt = 共享的 --json 选项。"""
    # factory approval <动作> [id] [decision] —— 审批门（M1b/T2）
    p_approval = sub.add_parser(
        "approval", help="审批门 (M1b/T2): 待审批列表 + 决策 + 应用 (复用 ApprovalGate)"
    )
    json_opt(p_approval)
    p_approval.add_argument(
        "approval_command", choices=["list", "decide", "apply"], metavar="动作",
        help="list — 待审批列表; decide <id> approve|reject — 审批决策; "
             "apply <id> [--project <dir>] — 应用已批准 patch",
    )
    p_approval.add_argument("approval_id", nargs="?", default=None, metavar="<id>",
                            help="审批记录 id (decide/apply)")
    p_approval.add_argument("decision", nargs="?", choices=["approve", "reject"], default=None,
                            metavar="approve|reject", help="审批决定 (decide)")
    p_approval.add_argument("--project", default=None,
                            help="(list) 按项目目录过滤; (apply) 目标项目目录 (缺省取请求 project_dir)")
    p_approval.add_argument("--status", default="pending",
                            help="(list) 过滤 pending/approved/rejected (缺省 pending)")
    p_approval.add_argument("--by", default="", help="(decide) 审批人 (缺省 cli)")
    p_approval.add_argument("--comment", default="", help="(decide) 审批意见 (reject 反馈给修复循环)")
