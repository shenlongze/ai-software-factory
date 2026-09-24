"""cli/main.py — factory CLI 入口 (argparse, 标准库零依赖)。

命令 (phase2-status 核心子集): init / task create|list|status|update /
event logs / status / validate。
退出码 (cli-design §5): 0 成功 / 1 一般错误 / 2 用法 (argparse 默认) / 3 验证失败 / 7 未找到。

入口: `factory` console script 或 `.venv/bin/python -m cli.main`。
"""

from __future__ import annotations

from pathlib import Path

import json
import re
import sys
from typing import Any

# ★ 2026-09-15 修: 装上「旧名 → 新路径」别名桥（compat_aliases）—— 必须在任何 import 之前。
#   此前只有 bin/factory（老 CLI）和 scripts/check_imports.py 装了, 新 CLI 漏装
#   ⇒ `import exec.cli` / `import org.cli` 直接 ModuleNotFoundError
#   ⇒ console/org/exec 三类命令全误报"未安装"。
#   实现封装在 ._aliases（import 它即完成 install）, 避免在 import 区中间插语句引发 E402。
from . import _aliases  # noqa: F401  — 导入即 install 别名桥, 无导出符号

from .commands import (
    CliError,
    cmd_agent_add,
    cmd_agent_assign,
    cmd_agent_assignments,
    cmd_agent_list,
    cmd_agent_release,
    cmd_checkpoint_create,
    cmd_checkpoint_list,
    cmd_change_analyze,
    cmd_change_commits,
    cmd_change_evaluate,
    cmd_change_triggers_list,
    cmd_change_triggers_register,
    cmd_change_validate,
    cmd_change_workflows,
    cmd_console_approvals,
    cmd_console_dashboard,
    cmd_dashboard,
    cmd_demo_markpad,
    cmd_event_logs,
    cmd_execution_list,
    cmd_execution_run,
    cmd_execution_status,
    cmd_git_commits,
    cmd_git_diff,
    cmd_git_status,
    cmd_init,
    cmd_intelligence_decision_create,
    cmd_intelligence_experience_evaluate,
    cmd_intelligence_experience_list,
    cmd_intelligence_recommend,
    cmd_metrics,
    cmd_org_member_list,
    cmd_org_member_set,
    cmd_project_org,
    cmd_exec_approval_apply,
    cmd_exec_approval_approve,
    cmd_exec_approval_deny,
    cmd_exec_approval_list,
    cmd_exec_run,
    cmd_exec_status,
    cmd_project_list,
    cmd_project_adopt,
    cmd_knowledge_status,
    cmd_change_plan,
    cmd_knowledge_reindex,
    cmd_project_show,
    cmd_provider_list,
    cmd_provider_show,
    cmd_provider_test,
    cmd_provider_usage,
    cmd_provider_stats,
    cmd_provider_compare,
    cmd_provider_recommend,
    cmd_provider_add,
    cmd_provider_doctor,
    cmd_product_approval_decide,
    cmd_product_approval_history,
    cmd_product_approval_list,
    cmd_product_approval_request,
    cmd_product_experience_list,
    cmd_product_experience_record,
    cmd_product_generate,
    cmd_product_idea_create,
    cmd_product_idea_list,
    cmd_product_idea_show,
    cmd_product_lifecycle_advance,
    cmd_product_lifecycle_start,
    cmd_product_lifecycle_status,
    cmd_product_lifecycle_templates,
    cmd_product_workflow_resume,
    cmd_product_workflow_start,
    cmd_product_workflow_status,
    cmd_recover,
    cmd_recover_plan,
    cmd_runtime_add,
    cmd_runtime_catalog_list,
    cmd_runtime_catalog_show,
    cmd_runtime_list,
    cmd_run_plan,
    cmd_runtime_test,
    cmd_skill_add,
    cmd_skill_list,
    cmd_status,
    cmd_task_create,
    cmd_task_list,
    cmd_task_status,
    cmd_task_update,
    cmd_understand,
    cmd_validate,
    cmd_workflow_add,
    cmd_workflow_list,
    cmd_workflow_run,
    cmd_workflow_status,
    cmd_workspace_init,
    cmd_workspace_show,
)
from .context import DEFAULT_ROOT, FactoryContext
from .domains import architecture as _dom_architecture
from .domains import chain as _dom_chain
from .domains import audit as _dom_audit
from .domains import conversation as _dom_conversation
from .domains import governance as _dom_governance
from .domains import metrics as _dom_metrics
from .domains import decomposition as _dom_decomposition
from .domains import operations as _dom_operations
from .domains import organization as _dom_organization
from .domains import platform as _dom_platform
from .domains import validation as _dom_validation

__all__ = ["main", "build_parser"]


def _parse_optional_bool(v: str) -> bool:
    """--approved true|false 解析 (argparse type 转换, 仅在传参时调用)。

    argparse 内置 type=bool 会把 "false" 转成 True — 必须用显式字符串解析。
    """
    import argparse

    low = str(v).strip().lower()
    if low in ("true", "1", "yes", "y"):
        return True
    if low in ("false", "0", "no", "n"):
        return False
    raise argparse.ArgumentTypeError(f"expected true/false, got {v!r}")


def build_parser() -> Any:
    """argparse 树: factory [--root DIR] [--json] <command> ..."""
    import argparse

    p = argparse.ArgumentParser(
        prog="factory",
        description="AI Software Factory — 工厂控制平面 CLI",
    )
    p.add_argument("--root", default=None, help=f"工厂根目录 (默认: {DEFAULT_ROOT})")
    p.add_argument("--json", action="store_true", help="输出 JSON (脚本消费)")
    sub = p.add_subparsers(dest="command", required=True)

    def json_opt(sp: Any) -> None:
        """每个子命令也接受 --json (全局选项须在子命令前, 此处双保险)。

        default 必须为 SUPPRESS: Python 3.12 的 _SubParsersAction.__call__ 会把子解析器
        结果解析进全新 namespace 再整体拷贝回原 namespace — 子解析器任何非 SUPPRESS
        默认值都会无条件覆盖已解析的全局 --json 值。
        """
        sp.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    # factory init
    p_llm = sub.add_parser(
        "llm", help="LLM 路由产品面: OpenAI 兼容端点 (对外可交付)"
    )
    json_opt(p_llm)
    p_llm.add_argument("llm_command", choices=["serve"], help="serve — 起 OpenAI 兼容端点")
    p_llm.add_argument("--host", default="127.0.0.1")
    p_llm.add_argument("--port", type=int, default=8787)
    p_tool = sub.add_parser(
        "tool", help="工具集: 列出 / 查看 / 调用已注册工具 (39 个, 分 5 阶段)"
    )
    json_opt(p_tool)
    p_tool_sub = p_tool.add_subparsers(dest="tool_command", required=True)
    t_list = p_tool_sub.add_parser("list", help="列出工具 (可按阶段过滤)")
    json_opt(t_list)
    t_list.add_argument("--stage", default="", help="按阶段过滤: 设计/开发/测试/部署/运维")
    t_list.add_argument("--status", default="", help="按状态过滤: implemented/planned")
    t_show = p_tool_sub.add_parser("show", help="查看一个工具的完整定义")

    json_opt(t_show)
    t_show.add_argument("tool_id", help="工具 id (如 code_search)")
    t_run = p_tool_sub.add_parser("run", help="调用一个工具 (真执行)")
    json_opt(t_run)
    t_run.add_argument("tool_id", help="工具 id")
    t_run.add_argument("--param", action="append", default=[], help="参数 k=v (可多次)")
    t_run.add_argument("--project", default="", help="项目 id (可选)")

    p_mcp = sub.add_parser(
        "mcp", help="MCP 服务器: 扫描发现 / 列出 / 连接测试"
    )
    json_opt(p_mcp)
    p_mcp_sub = p_mcp.add_subparsers(dest="mcp_command", required=True)
    m_scan = p_mcp_sub.add_parser("scan", help="扫描本机可发现的 MCP 服务器")
    json_opt(m_scan)
    m_list = p_mcp_sub.add_parser("list", help="列出已注册的 MCP")
    json_opt(m_list)
    m_test = p_mcp_sub.add_parser("test", help="测试 MCP 连接")
    json_opt(m_test)
    m_test.add_argument("mcp_id", help="MCP id")

    p_disc = sub.add_parser(
        "discover", help="扫描本机可用的外部能力 (AI CLI / MCP / 项目)"
    )
    json_opt(p_disc)
    p_disc.add_argument("what", nargs="?", default="all",
                        choices=["all", "ai-clis", "mcp", "projects"], help="扫描对象")
    p_init = sub.add_parser(
        "init", help="初始化工厂: 目录骨架 + 事件库 (幂等)",
        description="初始化工厂数据目录（默认 ~/.factory）: 建目录骨架 + 事件库, 并发一条 system.init。"
                    "幂等 —— **任何命令都会自动建目录**, 所以不跑本命令也能直接用; 它的用途是"
                    "首次安装后确认环境、或想显式留一条 init 事件时。")
    json_opt(p_init)

    # factory start —— 启动 AI Factory OS（进入交互式 CLI）
    p_start = sub.add_parser(
        "start", help="启动 AI Factory OS: 进入交互式 CLI（连续敲命令, exit 离开）",
        description="启动并进入交互式 CLI: 提示符 `factory>` 下直接敲任何 factory 命令; "
                    "help 看帮助中心 · exit/q 离开 · ↑↓ 翻历史。"
                    "非终端输入（管道/脚本）⇒ 逐行执行后退出。")
    json_opt(p_start)

    # factory help —— 中文帮助中心（按角色: 老板/产品/开发/运维）
    p_help = sub.add_parser("help", help="中文帮助中心（按角色: 老板/产品/开发/运维）",
                            description="按角色列出常用命令与一句话说明（命令全部真实存在）。")
    json_opt(p_help)
    p_help.add_argument("--role", default="", help="只看某个角色: 老板 / 产品 / 开发 / 运维")

    # factory task <sub>
    p_task = sub.add_parser("task", help="任务管理")
    json_opt(p_task)
    tsub = p_task.add_subparsers(dest="task_command", required=True)
    p_create = tsub.add_parser("create", help="定义任务 (发 task.created)")
    json_opt(p_create)
    p_create.add_argument("--id", default=None, help="任务 ID (默认自动生成 T-XXX)")
    p_create.add_argument("--title", required=True, help="任务标题")
    p_create.add_argument("--project", default=None, help="项目 (默认 default)")
    p_create.add_argument("--type", default=None, help="任务类型 (默认 feature)")
    p_create.add_argument("--owner", default=None, help="负责人")
    p_create.add_argument("--workflow", default=None, help="工作流 (默认 feature-delivery)")
    p_list = tsub.add_parser("list", help="任务列表 (发 task.viewed)")
    json_opt(p_list)
    p_list.add_argument("--status", default=None, help="按状态过滤 (BACKLOG/ARCHITECTURE/DEVELOPMENT/TESTING/DONE)")
    p_list.add_argument("--project", default=None, help="按项目过滤")
    p_status = tsub.add_parser("status", help="任务详情 + 事件时间线 (发 task.viewed)")
    json_opt(p_status)
    p_status.add_argument("task_id")
    p_update = tsub.add_parser("update", help="更新任务状态 (发 task.updated)")
    json_opt(p_update)
    p_update.add_argument("task_id")
    p_update.add_argument("--status", required=True, help="新状态 (BACKLOG/ARCHITECTURE/DEVELOPMENT/TESTING/DONE)")

    # factory event <sub>
    # factory conversation —— 会话域（链路第 1 环; 2026-09-15 新建, 见 ADR-0038 遗留待办）
    _dom_conversation.register(sub, json_opt)

    # factory event —— 审计域（按域拆至 domains/audit.py; 命令面不变 ✓）
    _dom_audit.register(sub, json_opt)

    # factory status
    json_opt(sub.add_parser("status", help="工厂总览: Projects/Tasks/Agents/Events 计数 (发 system.status_viewed)"))

    # factory validate
    p_val = sub.add_parser("validate", help="验证任务 — 三层验证引擎 L1/L2/L3 (发 validation.* 事件)")
    json_opt(p_val)
    p_val.add_argument("task_id")
    p_val.add_argument("--level", default="L2", choices=["L1", "L2", "L3"], help="验证级别 (事件标记, 默认 L2)")
    p_val.add_argument("--expect-status", default=None, help="期望状态, 不匹配则验证失败 (退出码 3)")

    # factory agent <sub>
    p_agent = sub.add_parser("agent", help="Agent 管理 (注册表, 发 agent.* 事件)")
    json_opt(p_agent)
    asub = p_agent.add_subparsers(dest="agent_command", required=True)
    p_agent_add = asub.add_parser("add", help="注册 Agent (发 agent.registered)")
    json_opt(p_agent_add)
    p_agent_add.add_argument("--id", required=True, help="Agent ID (如 A-001)")
    p_agent_add.add_argument("--role", required=True, help="角色 (如 backend-developer)")
    p_agent_add.add_argument("--skills", required=True, help="技能列表, 逗号分隔 (如 backend,flutter)")
    p_agent_add.add_argument("--name", default=None, help="显示名 (默认 = id)")
    p_agent_add.add_argument("--description", default=None, help="描述")
    p_agent_list = asub.add_parser("list", help="Agent 列表 (发 agent.viewed)")
    json_opt(p_agent_list)
    p_agent_list.add_argument("--status", default=None, help="按状态过滤 (AVAILABLE/WORKING/OFFLINE)")
    p_agent_list.add_argument("--role", default=None, help="按角色过滤")
    p_agent_list.add_argument("--skill", default=None, help="按技能过滤 (find_by_skill)")
    p_agent_assign = asub.add_parser(
        "assign", help="分配 Agent: 按步骤自动匹配或显式指定 (发 agent.assignment.created)"
    )
    json_opt(p_agent_assign)
    p_agent_assign.add_argument("--task", required=True, help="任务 ID (如 T-001)")
    p_agent_assign.add_argument("--step", default=None, help="工作流步骤 (按 role/skill 自动匹配)")
    p_agent_assign.add_argument("--agent", default=None, help="显式指定 Agent ID (跳过匹配)")
    p_agent_assign.add_argument("--execution", default=None, help="执行请求 ID (回填 agent_id)")
    p_agent_assignments = asub.add_parser("assignments", help="Assignment 列表 (发 agent.assignment.viewed)")
    json_opt(p_agent_assignments)
    p_agent_assignments.add_argument("--task", default=None, help="按任务过滤")
    p_agent_assignments.add_argument("--agent", default=None, help="按 Agent 过滤")
    p_agent_assignments.add_argument("--status", default=None, help="按状态过滤 (ASSIGNED/WORKING/COMPLETED/FAILED/RELEASED)")
    p_agent_release = asub.add_parser(
        "release", help="解除分配: Agent 回 AVAILABLE (发 agent.released)"
    )
    json_opt(p_agent_release)
    p_agent_release.add_argument("assignment_id", help="Assignment ID (如 ASG-001)")

    # factory skill <sub>
    p_skill = sub.add_parser("skill", help="Skill 管理 (能力目录, 发 skill.* 事件)")
    json_opt(p_skill)
    ssub = p_skill.add_subparsers(dest="skill_command", required=True)
    p_skill_add = ssub.add_parser("add", help="注册 Skill (发 skill.registered)")
    json_opt(p_skill_add)
    p_skill_add.add_argument("--id", required=True, help="Skill ID (如 flutter)")
    p_skill_add.add_argument("--category", default="general", help="技能类别 (默认 general)")
    p_skill_add.add_argument("--capabilities", default=None, help="能力列表, 逗号分隔")
    p_skill_add.add_argument("--version", default="1.0.0", help="版本 (默认 1.0.0)")
    p_skill_add.add_argument("--name", default=None, help="技能名 (默认 = id)")
    p_skill_add.add_argument("--description", default=None, help="描述")
    p_skill_list = ssub.add_parser("list", help="Skill 列表 (发 skill.viewed)")
    json_opt(p_skill_list)
    p_skill_list.add_argument("--category", default=None, help="按类别过滤")

    # factory workflow <sub>
    p_workflow = sub.add_parser("workflow", help="工作流管理 (发 workflow.* 事件)")
    json_opt(p_workflow)
    wsub = p_workflow.add_subparsers(dest="workflow_command", required=True)
    p_wf_list = wsub.add_parser("list", help="工作流定义列表 (发 workflow.viewed)")
    json_opt(p_wf_list)
    p_wf_add = wsub.add_parser("add", help="注册工作流定义: 内置或 --steps 自定义 (发 workflow.created)")
    json_opt(p_wf_add)
    p_wf_add.add_argument("--id", required=True, help="工作流 ID (如 feature-delivery)")
    p_wf_add.add_argument("--name", default=None, help="显示名 (默认 = id 或内置名)")
    p_wf_add.add_argument("--description", default=None, help="描述")
    p_wf_add.add_argument("--steps", default=None, help="自定义步骤, 逗号分隔 (省略则用同名内置定义)")
    p_wf_run = wsub.add_parser(
        "run", help="启动任务对应工作流 (发 workflow.started); --auto 自动执行完整链路 (发 orchestration.*)"
    )
    json_opt(p_wf_run)
    p_wf_run.add_argument("task_id")
    p_wf_run.add_argument("--auto", action="store_true",
                          help="自动执行完整链路: 匹配→分配→执行→推进 (失败 → Workflow FAILED)")
    p_wf_status = wsub.add_parser("status", help="任务工作流进度: ✓ 完成 / ▶ 当前 / ○ 待办 (发 workflow.viewed)")
    json_opt(p_wf_status)
    p_wf_status.add_argument("task_id")

    # factory runtime <sub>
    p_runtime = sub.add_parser("runtime", help="Runtime 管理 (适配器注册表, 发 runtime.* 事件)")
    json_opt(p_runtime)
    rsub = p_runtime.add_subparsers(dest="runtime_command", required=True)
    p_rt_add = rsub.add_parser("add", help="注册 Runtime 身份 (发 runtime.registered)")
    json_opt(p_rt_add)
    p_rt_add.add_argument("--id", required=True, help="Runtime ID (如 R-001)")
    p_rt_add.add_argument("--type", default="agent", help="运行时类型 (默认 agent)")
    p_rt_add.add_argument("--name", default=None, help="显示名 (默认 = id)")
    p_rt_add.add_argument("--description", default=None, help="描述")
    p_rt_list = rsub.add_parser("list", help="Runtime 列表 (发 runtime.viewed)")
    json_opt(p_rt_list)
    p_rt_list.add_argument("--status", default=None, help="按状态过滤 (AVAILABLE/DISABLED)")
    p_rt_test = rsub.add_parser(
        "test", help="Runtime smoke test: 内置 Adapter 执行最小 execution (发 runtime.viewed)"
    )
    json_opt(p_rt_test)
    p_rt_test.add_argument("runtime_id", help="Runtime ID (如 hermes-runtime)")
    p_rt_test.add_argument("--instruction", default=None,
                           help="冒烟指令 (默认: Reply with exactly: OK)")
    p_rt_catalog = rsub.add_parser(
        "catalog", help="Runtime 能力目录: 默认定义 hermes/echo/mock + 注册定义 (发 runtime.catalog.viewed)"
    )
    json_opt(p_rt_catalog)
    ctsub = p_rt_catalog.add_subparsers(dest="runtime_catalog_command", required=True)
    p_rt_cat_list = ctsub.add_parser("list", help="Runtime 定义列表 (发 runtime.catalog.viewed)")
    json_opt(p_rt_cat_list)
    p_rt_cat_list.add_argument("--type", default=None, help="按类型过滤 (agent/mock)")
    p_rt_cat_show = ctsub.add_parser("show", help="Runtime 定义详情 (发 runtime.catalog.viewed)")
    json_opt(p_rt_cat_show)
    p_rt_cat_show.add_argument("definition_id", help="定义 ID (如 hermes)")

    # factory execution <sub>
    p_exec = sub.add_parser("execution", help="执行记录查询 (发 execution.viewed)")
    json_opt(p_exec)
    xsub = p_exec.add_subparsers(dest="execution_command", required=True)
    p_ex_list = xsub.add_parser("list", help="执行记录列表 (发 execution.viewed)")
    json_opt(p_ex_list)
    p_ex_list.add_argument("--task", default=None, help="按任务过滤")
    p_ex_run = xsub.add_parser(
        "run", help="执行 pending execution (发 execution.started/completed/failed; "
                    "--provider 选择 Provider 并经 input 携带, 发 provider.* 事件)"
    )
    json_opt(p_ex_run)
    p_ex_run.add_argument("execution_id", help="执行请求 ID (如 EX-001)")
    p_ex_run.add_argument(
        "--provider", default=None,
        help="显式指定 Provider id (覆盖项目配置; 优先级链: 项目 > Agent > Runtime > Default)",
    )
    p_ex_status = xsub.add_parser("status", help="查看执行状态/结果 (发 execution.viewed)")
    json_opt(p_ex_status)
    p_ex_status.add_argument("execution_id", help="执行请求 ID (如 EX-001)")

    # factory run / run-status —— 执行域（从【目标】创建并执行, 老 CLI 的用户入口）
    # 搬迁来源: 老 CLI p_run（cli_factory L10147）/ p_status（L10162）
    # 底层: `exec.cli`（经 compat_aliases 映射到新地基 services/execution/kernel/cli.py）
    # 与新 CLI 已有的 `execution run`（执行【已存在的】execution_id）语义不同, 不冲突 ✓
    p_run = sub.add_parser(
        "run",
        help="执行任务 → exec CLI (薄代理: --project 必填; --task 或 --objective 之一必填)",
    )
    p_run.add_argument("--project", default=None, help="项目目录 (沙箱副本源; 必填)")
    p_run.add_argument("--task", default=None, help="任务 ID (与 --objective 二选一; 提供则优先)")
    p_run.add_argument("--objective", default=None,
                       help="目标描述 (与 --task 二选一; 无 --task 时自动生成任务 ID)")
    p_run.add_argument("--requirement", default="", help="验收标准/约束")
    p_run.add_argument("--employee", default=None, help="员工 ID (org store 解析)")
    p_run.add_argument("--agent", default=None, help="Agent 实例 ID (默认 developer-1)")
    p_run.add_argument("--provider", default=None, help="Provider id (默认 anthropic)")
    p_run.add_argument("--test-cmd", default=None, help="沙箱内测试命令 (验证)")
    p_run.add_argument("--json", action="store_true", help="输出结构化 JSON")
    # ★ --plan: 按拓扑序跑整棵任务树（第 1 刀; 走 scheduler 平面）
    p_run.add_argument("--plan", default="", help="任务树 id（factory tasktree list）⇒ 跑整棵树")
    p_run.add_argument("--parallel", type=int, default=3, help="批内并发上限（默认 3）")
    p_run.add_argument("--force", action="store_true",
                        help="强抢运行锁（★ 会覆盖另一个进程的改动 ✗ 慎用）")
    p_run.add_argument("--limit", type=int, default=0,
                       help="★ 本次最多跑几个执行（0=不限; 小步试跑用 —— 199 叶的树不限量会一路跑完）")
    p_run.add_argument("--budget", type=float, default=1.0e9,
                       help="★ 预算上限（真实花费累计超过它 ⇒ 不再派活; 默认 1e9 = 现状）")

    p_run_status = sub.add_parser(
        "run-status", help="执行结果查询 → exec CLI (薄代理: --id 结果 ID)"
    )
    p_run_status.add_argument("--id", default=None, help="结果 ID (缺省列出全部)")
    p_run_status.add_argument("--json", action="store_true", help="输出结构化 JSON")

    # factory checkpoint + factory recover —— 运维域（按域拆至 domains/operations.py; 命令面不变 ✓）
    _dom_operations.register(sub, json_opt)

    # factory dashboard + factory metrics —— 监控域（按域拆至 domains/metrics.py; 命令面不变 ✓）
    _dom_metrics.register(sub, json_opt)

    # factory verification —— 验收域（按域拆至 domains/validation.py）
    # 底层 verification_store 已在新地基（services/validation/）, 所以本命令零老区依赖 ✓
    _dom_validation.register(sub, json_opt)

    # factory arch —— 架构域（按域拆至 domains/architecture.py）
    # ★ 2026-09-15 新增: 兑现 registry 里登记的 "architecture": ("arch",)
    _dom_architecture.register(sub, json_opt)

    # ★ factory chain —— 全链编排（需求 → … → 拆解, Founder 问'闭环了么'）
    _dom_chain.register(sub, json_opt)

    # factory create —— 平台域（按域拆至 domains/platform.py）
    # 底层 org.cli 已在新地基（services/organization/cli.py）⇒ 零老区依赖 ✓
    _dom_platform.register(sub, json_opt)

    # factory plugin —— 组织域（按域拆至 domains/organization.py）
    # 底层 plugin_kernel 已在新地基（infrastructure/plugins/kernel.py）⇒ 零老区依赖 ✓
    _dom_organization.register(sub, json_opt)

    # factory kanban —— 任务拆解域（按域拆至 domains/decomposition.py）
    _dom_decomposition.register(sub, json_opt)

    # factory approval —— 治理域（按域拆至 domains/governance.py）
    # 老 CLI 的该命令已是绞杀者模式（默认走新实现 services/governance）⇒ 本刀取其新实现路径
    _dom_governance.register(sub, json_opt)

    # factory project <sub> (Phase 5A: Example Layer, 只读)
    p_project = sub.add_parser("project", help="项目 (缺省读 org 项目库 —— 与 status 同源)")
    json_opt(p_project)
    # ★ 2026-09-21: `project list --source org|workspace|examples`（缺省 org = 权威源）
    for _child in getattr(p_project, "_actions", []):
        if hasattr(_child, "choices") and isinstance(_child.choices, dict) and "list" in _child.choices:
            _child.choices["list"].add_argument("--source", default="", choices=["", "org", "workspace", "examples"],
                                                help="数据源（缺省 org 项目库, 与 status 同源）")
            break
    prsub = p_project.add_subparsers(dest="project_command", required=True)
    p_pr_list = prsub.add_parser(
        "list",
        help="项目列表 (缺省读 org 项目库 —— 与 status 同源)", 
        description="列项目。★ 缺省数据源 = **org 项目库**（与 status 同一处, 两边必然一致）;"
                    "想看工作区/示例那份用 --source workspace|examples。")
    p_pr_list.add_argument("--source", default="", choices=["", "org", "workspace", "examples"],
                           help="数据源（缺省 org 项目库 = 权威源）")
    json_opt(p_pr_list)
    p_pr_show = prsub.add_parser("show", help="项目详情: 技术栈/Agent/技能/工作流映射 (发 project.viewed)")
    json_opt(p_pr_show)
    p_pr_show.add_argument("name", help="项目名 (如 markpad)")
    p_pr_org = prsub.add_parser(
        "org", help="★ 给项目设归属公司/部门（派活按它筛人; 不给参数=摘掉）")
    json_opt(p_pr_org)
    p_pr_org.add_argument("project_id", help="项目 id（P-*）")
    p_pr_org.add_argument("--company", default="", help="公司 id（C-*）")
    p_pr_org.add_argument("--department", default="", help="部门 id（D-*，可选）")
    p_pr_adopt = prsub.add_parser("adopt", help="把一个已有仓库注册为项目 (记忆链上游: 产生 repo_path)")
    json_opt(p_pr_adopt)
    p_pr_adopt.add_argument("path", help="仓库目录 (必须存在)")
    p_pr_adopt.add_argument("--name", default="", help="项目名 (缺省 = 目录名)")
    p_pr_adopt.add_argument("--goal", default="", help="项目目标 (可选)")
    p_pr_adopt.add_argument("--user-id", default="", help="发起人 (可选)")

    # factory knowledge <sub> —— 记忆 · 知识索引（★ 2026-09-19 mem-6）
    # ★ 项目级记忆（跨会话经验）—— 查看 / 手工追加
    #   背景（2026-09-20 全量测试）: 机制早就有（类型化 + 权威 + 衰减）, 但**写侧零调用者**、
    #   且 add() 不落盘（忘了 save 就静默丢）⇒ 给人一个能看能写的入口。
    p_mem = sub.add_parser("memory", help="项目级记忆（跨会话经验）: 查看 / 手工追加")
    json_opt(p_mem)
    msub = p_mem.add_subparsers(dest="memory_command", required=True)
    p_mem_ls = msub.add_parser("list", help="看某项目的记忆（按权威×时间衰减排序）")
    json_opt(p_mem_ls)
    p_mem_ls.add_argument("--project", required=True, help="项目 id")
    p_mem_ls.add_argument("--n", type=int, default=10, help="最多几条（默认 10）")
    p_mem_add = msub.add_parser("add", help="手工追加一条记忆")
    json_opt(p_mem_add)
    p_mem_add.add_argument("--project", required=True, help="项目 id")
    p_mem_add.add_argument("--text", required=True, help="记忆内容")
    p_mem_add.add_argument("--kind", default="observation",
                           choices=["decision", "learning", "error", "pattern", "observation"])
    p_mem_add.add_argument("--authority", default="user_intent",
                           choices=["user_intent", "verified_state", "repo_evidence",
                                    "agent_claim", "summary"])
    p_kn = sub.add_parser("knowledge", help="知识索引（记忆第 3 层）: 看是否过期 / 重建")
    json_opt(p_kn)
    knsub = p_kn.add_subparsers(dest="knowledge_command", required=True)
    p_kn_st = knsub.add_parser("status", help="看项目知识索引是否过期（记忆会不会记错）")
    json_opt(p_kn_st)
    p_kn_st.add_argument("--project", default="", help="只查某个项目 id")
    p_kn_re = knsub.add_parser("reindex", help="重建知识索引（默认增量; --full 全量）")
    json_opt(p_kn_re)
    p_kn_re.add_argument("--project", default="", help="只重建某个项目 id")
    p_kn_re.add_argument("--full", action="store_true", help="全量重建（默认增量）")

    # factory provider <sub> (Phase 8A, ADR-0022)
    p_provider = sub.add_parser(
        "provider", help="LLM Provider 管理: 智能来源目录 (默认 hermes + 注册定义, 发 provider.* 事件)"
    )
    json_opt(p_provider)
    pvsub = p_provider.add_subparsers(dest="provider_command", required=True)

    # ★ 配置引导（照 Hermes `setup model` / OpenClaw `configure`）
    pv_add = pvsub.add_parser("add", help="配置新 provider（交互: 选类型→贴 key→试连→落库）")
    json_opt(pv_add)
    pv_add.add_argument("--id", dest="provider_id", default="", help="provider id（非交互时必填）")
    pv_add.add_argument("--base-url", default="", help="OpenAI 兼容端点")
    pv_add.add_argument("--models", default="", help="模型名, 逗号分隔")
    pv_add.add_argument("--env", default="", help="存 key 的环境变量名")
    pv_add.add_argument("--key", default="", help="key（★ 只写进 env, 不落 providers.json）")
    pv_add.add_argument("--non-interactive", action="store_true", help="不做交互询问")
    pv_add.add_argument("--skip-test", action="store_true", help="跳过试连")
    pv_doctor = pvsub.add_parser("doctor", help="体检: key/端点/模型/降级链")
    json_opt(pv_doctor)
    p_pv_list = pvsub.add_parser("list", help="Provider 目录列表 (发 provider.viewed)")
    json_opt(p_pv_list)
    p_pv_list.add_argument("--type", default=None, help="按类型过滤 (cloud/local/agent)")
    p_pv_list.add_argument("--status", default=None, help="按状态过滤 (ACTIVE/DISABLED)")
    p_pv_show = pvsub.add_parser("show", help="Provider 定义详情 (发 provider.viewed)")
    json_opt(p_pv_show)
    p_pv_show.add_argument("provider_id", help="Provider ID (如 hermes)")
    p_pv_test = pvsub.add_parser(
        "test", help="Provider smoke test: 最小生成调用 (发 provider.selected/execution.*)"
    )
    json_opt(p_pv_test)
    p_pv_test.add_argument("provider_id", help="Provider ID (如 hermes)")
    p_pv_test.add_argument("--prompt", default=None,
                           help="冒烟提示词 (默认: Reply with exactly: OK)")
    p_pv_test.add_argument("--model", default=None, help="模型 (默认 Provider 默认模型)")
    # Phase 8B-2 (ADR-0024): 能力/成本/使用层读命令
    p_pv_usage = pvsub.add_parser(
        "usage", help="使用记录 (估算成本, 非真实计费; 发 provider.viewed)"
    )
    json_opt(p_pv_usage)
    p_pv_usage.add_argument("--provider", default=None, help="按 Provider ID 过滤")
    p_pv_usage.add_argument("--period", default="all", choices=["day", "week", "all"],
                            help="聚合周期 (day=今天 / week=最近 7 天 / all, 默认 all)")
    p_pv_stats = pvsub.add_parser(
        "stats", help="性能聚合 (provider/model/version/period 维度; 发 provider.viewed)"
    )
    json_opt(p_pv_stats)
    p_pv_stats.add_argument("--provider", default=None, help="按 Provider ID 过滤")
    p_pv_stats.add_argument("--period", default="all", choices=["day", "week", "all"],
                            help="聚合周期 (day=今天 / week=最近 7 天 / all, 默认 all)")
    p_pv_compare = pvsub.add_parser(
        "compare", help="能力/成本对比 (估算模型, 非真实计费; 发 provider.viewed)"
    )
    json_opt(p_pv_compare)
    p_pv_compare.add_argument("a", help="Provider A ID (如 hermes)")
    p_pv_compare.add_argument("b", help="Provider B ID")
    p_pv_recommend = pvsub.add_parser(
        "recommend", help="TaskRequirement → 能力匹配 + 成本感知推荐 (只推荐不自动切换)"
    )
    json_opt(p_pv_recommend)
    p_pv_recommend.add_argument("--task", required=True,
                                help="任务类型 (如 development)")
    p_pv_recommend.add_argument("--capabilities", default="",
                                help="逗号分隔能力列表 (如 code,reasoning)")
    p_pv_recommend.add_argument("--min-quality", type=float, default=0.0,
                                help="能力质量门槛 0-1 (默认 0.0 = 存在即可)")
    p_pv_recommend.add_argument("--budget", type=float, default=None,
                                help="估算成本上限 USD (默认不设上限)")

    # factory tasktree <sub> —— 任务拆解（产品环 ⑤: 计划层组织结构）
    #   从 Design Artifact 的 task_breakdown 物化成多级树; 产出为【候选】, 需 confirm 才进执行。
    p_tt = sub.add_parser("tasktree", help="任务拆解: list / show / decompose / confirm")
    json_opt(p_tt)
    ttsub = p_tt.add_subparsers(dest="tasktree_command", required=True)
    p_tt_l = ttsub.add_parser("list", help="任务树列表")
    json_opt(p_tt_l)
    p_tt_l.add_argument("--project", default=None, help="项目 id（缺省=全部）")
    p_tt_s = ttsub.add_parser("show", help="任务树详情（多级 + 依赖 + 验收）")
    json_opt(p_tt_s)
    p_tt_s.add_argument("plan_id", help="计划 id（如 PLAN-xxxxxxxxxx）")
    p_tt_s.add_argument("--project", default=None, help="项目 id")
    p_tt_todo = ttsub.add_parser(
        "todo", help="用户视图: 层级待办清单（人话名/状态/谁在做 —— 给普通人看）")
    json_opt(p_tt_todo)
    p_tt_todo.add_argument("plan_id", help="计划 id（如 PLAN-xxxxxxxxxx）")
    p_tt_todo.add_argument("--project", default=None, help="项目 id")
    p_tt_todo.add_argument("--ids", action="store_true",
        help="显示节点 id（★ 默认不显示 —— 普通人看不懂内部 id; 要改节点时才需要）")
    p_tt_flow = ttsub.add_parser(
        "flow", help="用户视图: 功能链路图（有哪些功能/谁依赖谁/先后顺序）")
    json_opt(p_tt_flow)
    p_tt_flow.add_argument("plan_id", help="计划 id（如 PLAN-xxxxxxxxxx）")
    p_tt_flow.add_argument("--project", default=None, help="项目 id")
    p_tt_flow.add_argument("--ids", action="store_true",
        help="显示节点 id（★ 默认不显示 —— 普通人看不懂内部 id; 要改节点时才需要）")
    p_tt_flow.add_argument("--mermaid", action="store_true",
        help="输出 mermaid 流程图源码（设计 §4.3: CLI 可渲染 mermaid, 贴进支持它的工具即成图）")
    p_tt_df = ttsub.add_parser(
        "dataflow", help="用户视图: 数据流程图（数据实体 / 哪个模块碰它 / 实体之间怎么连）")
    json_opt(p_tt_df)
    p_tt_df.add_argument("plan_id", help="计划 id（如 PLAN-xxxxxxxxxx）")
    p_tt_df.add_argument("--project", default=None, help="项目 id")
    p_tt_df.add_argument("--mermaid", action="store_true",
        help="输出 mermaid 源码（模块↔实体 与 实体↔实体 两张关系图）")
    p_tt_dec = ttsub.add_parser(
        "declare", help="★ 产线声明: 让 LLM 声明每个模块读/写哪些数据实体（数据流程图据此把线索变实线）")
    json_opt(p_tt_dec)
    p_tt_dec.add_argument("plan_id", help="计划 id（如 PLAN-xxxxxxxxxx）")
    p_tt_dec.add_argument("--project", default=None, help="项目 id")
    p_tt_dec.add_argument("--node", default=None, help="只声明这一个模块（短 id 也行）")
    p_tt_dec.add_argument("--dry-run", action="store_true", dest="dry_run",
        help="只算不落盘（先看 LLM 会声明什么）")
    p_tt_wf = ttsub.add_parser(
        "workflow", help="★ 流程: 看有哪些流程 / 给任务树挂流程（挂了 ⇒ 叶按步骤推进, 走完才算完成）")
    json_opt(p_tt_wf)
    p_tt_wf.add_argument("plan_id", nargs="?", default="", help="计划 id（--list 时可省）")
    p_tt_wf.add_argument("--project", default=None, help="项目 id")
    p_tt_wf.add_argument("--id", default=None, dest="workflow_id",
                         help="要挂的流程 id（如 feature-delivery）; 传空串 \"\" 表示摘掉")
    p_tt_wf.add_argument("--list", action="store_true", help="列出可用流程（内置 + 已注册）")
    p_tt_pri = ttsub.add_parser(
        "priority", help="★ 优先级: 看分布 / 人工设 / 按关键路径自动导出（人工 > 产线声明 > 自动）")
    json_opt(p_tt_pri)
    p_tt_pri.add_argument("plan_id", help="计划 id（如 PLAN-xxxxxxxxxx）")
    p_tt_pri.add_argument("--project", default=None, help="项目 id")
    p_tt_pri.add_argument("--auto", action="store_true",
        help="按关键路径自动导出（链上=P0 · 有人等它=P1 · 旁支=P2）—— ★ 不覆盖人工与产线声明")
    p_tt_pri.add_argument("--set-node", dest="set_node", default=None,
        help="人工设某节点（短 id 也行）—— 人工最高, 自动不再覆盖它")
    p_tt_pri.add_argument("--value", default=None, help="P0/P1/P2/P3（配 --set-node）")
    p_tt_pri.add_argument("--why", default="", help="人工排的理由（可选, 落盘）")
    p_tt_st = ttsub.add_parser(
        "staffing", help="★ 谁做: 看派工情况 / 人工指定角色（调度器按【成员角色】匹配, 不是 skills）")
    json_opt(p_tt_st)
    p_tt_st.add_argument("plan_id", help="计划 id（如 PLAN-xxxxxxxxxx）")
    p_tt_st.add_argument("--project", default=None, help="项目 id")
    p_tt_st.add_argument("--node", default=None, help="只改这一个节点（短 id 也行）")
    p_tt_st.add_argument("--role", default=None, help="主责角色（必须是真实角色清单里的值）")
    p_tt_st.add_argument("--cap", default=None,
        help="需要的角色（逗号分隔, 可多个; 缺省 = 与 --role 相同）")
    p_tt_dec.add_argument("--set", nargs="+", default=None, dest="set_spec",
        help="★ 手动改声明（须配 --node）: 写法 Order:write User:read（省略 access = both）")
    p_tt_dec.add_argument("--clear", action="store_true",
        help="★ 清空该模块的声明（须配 --node）—— 该模块回落成『线索』路径")
    p_tt_e = ttsub.add_parser(
        "edit", help="★ 逐节点编辑（改标题/验收/人话名/依赖, 或删节点）—— 改完回到候选态")
    json_opt(p_tt_e)
    p_tt_e.add_argument("plan_id", help="计划 id（如 PLAN-xxxxxxxxxx）")
    p_tt_e.add_argument("--node", required=True, help="节点 id（可用短 id, 见 show/todo 输出）")
    p_tt_e.add_argument("--title", default=None, help="改标题（专业名）")
    p_tt_e.add_argument("--acceptance", default=None, help="改验收标准")
    p_tt_e.add_argument("--display-name", dest="display_name", default=None, help="改人话名")
    p_tt_e.add_argument("--assignee", default=None, help="指派谁做（承接落地; 空串=回到待派）")
    p_tt_e.add_argument("--split", nargs="+", default=None,
                        help="★ 把该叶拆成多个子任务（给子任务标题）")
    p_tt_e.add_argument("--merge", nargs="+", default=None, dest="merge_ids",
                        help="★ 合并多个节点（给节点 id, 保留第一个）")
    p_tt_e.add_argument("--drop", action="store_true", help="删除该节点及其子树")
    p_tt_tr = ttsub.add_parser(
        "translate", help="★ 用 LLM 把技术标题翻成人话名（写进 display_name）")
    json_opt(p_tt_tr)
    p_tt_tr.add_argument("plan_id", help="计划 id（如 PLAN-xxxxxxxxxx）")
    p_tt_tr.add_argument("--project", default=None, help="项目 id")
    p_tt_ex = ttsub.add_parser(
        "expand", help="★ 细拆: 把模块展开成多个子任务（逐模块调 LLM —— 让树真的长出子任务）")
    json_opt(p_tt_ex)
    p_tt_ex.add_argument("plan_id", help="计划 id（如 PLAN-xxxxxxxxxx）")
    p_tt_ex.add_argument("--node", default="", help="只展开该节点（缺省=全部顶层模块挨个展开）")
    p_tt_ex.add_argument("--deep", action="store_true",
        help="★ 递归拆到底: 拆完的子任务若仍是多件事, 继续拆（判据: 一个 agent 一次能做完+能独立验收）")
    p_tt_ex.add_argument("--max-depth", dest="max_depth", type=int, default=3,
        help="递归深度上限（默认 3; 防无限拆）")
    p_tt_ex.add_argument("--project", default=None, help="项目 id")
    p_tt_e.add_argument("--project", default=None, help="项目 id")
    p_tt_d = ttsub.add_parser("decompose", help="从 Design Artifact 生成任务树（候选态）")
    json_opt(p_tt_d)
    p_tt_d.add_argument("--project", required=True, help="项目 id")
    p_tt_d.add_argument("--conversation", default=None,
                        help="会话 id（★ 读①定位结果: 类型/承接 —— 影响拆解粒度）")
    p_tt_d.add_argument("--plan", default=None, help="指定 plan_id（缺省自动生成）")
    p_tt_d.add_argument("--design", default=None,
                        help="用哪份设计产物（缺省=该项目最新一份; 想复现旧树就指定 id）")
    p_tt_c = ttsub.add_parser("confirm", help="人工确认（候选 → 已确认, 进入执行的前置门）")
    json_opt(p_tt_c)
    p_tt_c.add_argument("plan_id", help="计划 id")
    p_tt_c.add_argument("--project", default=None, help="项目 id")

    # factory product <sub> (Phase 9A, ADR-0026: Product Intelligence 基础)
    p_product = sub.add_parser(
        "product", help="Product Intelligence: Idea/Artifact/Approval/Workflow (独立空间 .factory/product/, 发 idea.*/approval.*/product.* 事件)"
    )
    json_opt(p_product)
    psub = p_product.add_subparsers(dest="product_command", required=True)
    # ★ factory product develop / ux —— 产品阶段执行链（2026-09-15 新增）
    #   环④「架构设计」需要 product + ux_ui 两种 7 节产物；本节补上它们的生成入口。
    #   复用 plugins/agents 里已就位的 PMAgent / UXUIDesignerAgent（不搬老区 workflow_runner）。
    p_pd = psub.add_parser(
        "develop", help="PM Agent: 想法 → Product Artifact (7 节, 注册为 org 产物 type=product)"
    )
    json_opt(p_pd)
    p_pd.add_argument("--project", required=True, help="项目 id（产物注册到该项目）")
    p_pd.add_argument("--idea", default=None, help="想法文本（缺省从项目 PRD/会话事实取）")
    p_pu = psub.add_parser(
        "ux", help="UX/UI Agent: Product Artifact → UX/UI Artifact (7 节, type=ux_ui)"
    )
    json_opt(p_pu)
    p_pu.add_argument("--project", required=True, help="项目 id")
    p_pu.add_argument("--product", default=None, help="(可选) 指定 product 产物 id; 缺省取项目最新")
    # ★ factory product breakdown —— 需求拆解（业务模块拆分）
    #   Founder 说的"两层拆解"的**业务层**: 需求由哪些业务模块组成（人话粒度, 给人看）。
    #   与 `tasktree decompose`（执行层: 具体做哪些活）是两层不同的东西。
    p_pb = psub.add_parser(
        "breakdown", help="★ 需求拆解（业务模块拆分）—— 业务层, 给人看的那层")
    json_opt(p_pb)
    p_pb.add_argument("--project", required=True, help="项目 id")
    # product idea <sub>
    p_pi = psub.add_parser("idea", help="产品想法管理 (发 idea.* 事件)")
    json_opt(p_pi)
    pisub = p_pi.add_subparsers(dest="idea_command", required=True)
    p_pi_create = pisub.add_parser(
        "create", help="创建想法: 落 ProductIdea + product_idea Artifact (发 idea.created)"
    )
    json_opt(p_pi_create)
    p_pi_create.add_argument("--title", required=True, help="想法标题")
    p_pi_create.add_argument("--description", default=None, help="想法描述")
    p_pi_create.add_argument("--goals", default=None, help="目标列表, 逗号分隔")
    p_pi_list = pisub.add_parser("list", help="想法列表 (发 idea.viewed 审计)")
    json_opt(p_pi_list)
    p_pi_show = pisub.add_parser("show", help="想法详情 + 关联 Artifact (发 idea.viewed 审计)")
    json_opt(p_pi_show)
    p_pi_show.add_argument("idea_id", help="想法 ID (如 PI-001)")
    # product approval <sub>
    p_pa = psub.add_parser(
        "approval", help="审批门管理: 任何 Artifact 可申请 (发 approval.* 事件)"
    )
    json_opt(p_pa)
    pasub = p_pa.add_subparsers(dest="approval_command", required=True)
    p_pa_request = pasub.add_parser(
        "request", help="申请审批: artifact 落 pending 请求 (发 approval.required; 关联 workflow 暂停)"
    )
    json_opt(p_pa_request)
    p_pa_request.add_argument("artifact_id", help="Artifact ID (如 ART-001)")
    p_pa_request.add_argument("--gate", default=None,
                              help="审批门 id (默认 prd|ui|architecture 之一; 门 id == artifact_type)")
    p_pa_request.add_argument("--by", default=None, help="申请人 (默认 cli)")
    p_pa_request.add_argument("--note", default=None, help="申请备注")
    p_pa_decide = pasub.add_parser(
        "decide", help="审批决定 approve|reject|changes_requested|delegate (deny=9a 兼容别名): 终态不可逆 (发 approval.approved/rejected/changes_requested/delegated; approved 产生 Product Decision Artifact)"
    )
    json_opt(p_pa_decide)
    p_pa_decide.add_argument("request_id", help="审批请求 ID (如 APR-001)")
    p_pa_decide.add_argument(
        "decision",
        choices=["approve", "reject", "changes_requested", "delegate", "deny"],
        help="决定 (deny 为 9a 兼容别名 → rejected)",
    )
    p_pa_decide.add_argument("--comment", default=None, help="决定理由 (reject/changes_requested 必填建议)")
    p_pa_decide.add_argument("--by", default=None, help="决策人 (默认 cli)")
    p_pa_list = pasub.add_parser("list", help="审批清单 (发 approval.viewed 审计)")
    json_opt(p_pa_list)
    p_pa_list.add_argument("--pending", action="store_true", help="只列待办 (pending)")
    p_pa_list.add_argument("--status", default=None,
                           help="按终态过滤 (pending|approved|rejected|changes_requested|delegated; denied 兼容)")
    p_pa_history = pasub.add_parser(
        "history", help="Artifact 审批历史: 全部请求 + 决定联表 (发 approval.viewed 审计)"
    )
    json_opt(p_pa_history)
    p_pa_history.add_argument("artifact_id", help="Artifact ID (如 ART-001)")
    # product workflow <sub>
    p_pw = psub.add_parser(
        "workflow", help="产品工作流骨架 (发 product.* 事件)"
    )
    json_opt(p_pw)
    pwsub = p_pw.add_subparsers(dest="workflow_command", required=True)
    p_pw_start = pwsub.add_parser(
        "start", help="启动工作流: stages 链 + current_stage (发 product.workflow.started)"
    )
    json_opt(p_pw_start)
    p_pw_start.add_argument("idea_id", help="想法 ID (如 PI-001)")
    p_pw_status = pwsub.add_parser(
        "status", help="工作流状态: 阶段/待批准/Product Decision (发 product.workflow.status_viewed 审计)"
    )
    json_opt(p_pw_status)
    p_pw_status.add_argument("idea_id", help="想法 ID (如 PI-001)")
    p_pw_resume = pwsub.add_parser(
        "resume", help="手动恢复暂停的工作流 paused → running (发 approval.resumed reason=manual)"
    )
    json_opt(p_pw_resume)
    p_pw_resume.add_argument("idea_id", help="想法 ID (如 PI-001)")
    # product generate (Phase 9B, ADR-0027: Provider 生成编排)
    p_pg = psub.add_parser(
        "generate", help="AI 生成产品 Artifact: TaskRequirement → CostAwareSelector → ProviderAdapter (发 product.generation.* 事件)"
    )
    json_opt(p_pg)
    p_pg.add_argument("idea_id", help="想法 ID (如 PI-001)")
    p_pg.add_argument("--type", required=True, choices=["research", "prd", "ui"],
                      help="生成类型 (research 无默认门; prd/ui 生成后自动申请审批等待人工批准)")
    p_pg.add_argument("--provider", default=None,
                      help="Provider ID 显式覆盖 (缺省经 CostAwareSelector 推荐; 未注册/禁用 → 退出码 1)")
    # product experience <sub> (Phase 9B, ADR-0027: 生成经验记录)
    p_pe = psub.add_parser(
        "experience", help="生成经验记录: 人工对生成产物的反馈 (发 product.experience.* 事件)"
    )
    json_opt(p_pe)
    pesub = p_pe.add_subparsers(dest="experience_command", required=True)
    p_pe_list = pesub.add_parser(
        "list", help="经验清单 (发 product.experience.viewed 审计)"
    )
    json_opt(p_pe_list)
    p_pe_list.add_argument("--artifact-type", default=None,
                           help="按生成类型过滤 (research/prd/ui)")
    p_pe_record = pesub.add_parser(
        "record", help="记录人工经验: 从 Artifact Lineage 推导 provider/confidence (发 product.experience.recorded)"
    )
    json_opt(p_pe_record)
    p_pe_record.add_argument("artifact_id", help="Artifact ID (如 ART-001)")
    p_pe_record.add_argument("--rating", type=int, default=None, help="评分 1-5")
    p_pe_record.add_argument("--comment", default=None, help="反馈文本")
    p_pe_record.add_argument("--approved", default=None, type=_parse_optional_bool,
                             help="人工批准判定 (true/false; None = 未判定)")
    p_pe_record.add_argument("--by", default=None, help="记录人 (默认 cli)")

    # product lifecycle <sub> (Phase 9d, ADR-0029: 生命周期编排)
    p_pl = psub.add_parser(
        "lifecycle", help="产品生命周期编排: Idea→Research→PRD→Approval→UI→Architecture→Task (发 product.lifecycle.*/stage.*/decision.* 事件)"
    )
    json_opt(p_pl)
    plsub = p_pl.add_subparsers(dest="lifecycle_command", required=True)
    p_pl_start = plsub.add_parser(
        "start", help="启动生命周期: 声明式模板阶段链 + 首阶段 (发 product.lifecycle.started)"
    )
    json_opt(p_pl_start)
    p_pl_start.add_argument("idea_id", help="想法 ID (如 PI-001)")
    p_pl_start.add_argument("--template", default=None,
                            help="生命周期模板 (默认 software_project; 多 lifecycle 类型: automation/business 预留)")
    p_pl_status = plsub.add_parser(
        "status", help="生命周期状态: 当前阶段/待审批/产物/决策链/下一步动作 (发 product.lifecycle.status_viewed 审计)"
    )
    json_opt(p_pl_status)
    p_pl_status.add_argument("idea_id", help="想法 ID (如 PI-001)")
    p_pl_advance = plsub.add_parser(
        "advance", help="手动推进当前阶段 (非 approval 阶段; 发 product.stage.completed/entered)"
    )
    json_opt(p_pl_advance)
    p_pl_advance.add_argument("idea_id", help="想法 ID (如 PI-001)")
    p_pl_templates = plsub.add_parser(
        "templates", help="生命周期模板列表 (声明式解析; 发 product.lifecycle.templates_viewed 审计)"
    )
    json_opt(p_pl_templates)

    # factory intelligence decision <sub> (Phase 10A-2, ADR-0031: Decision Intelligence)
    p_intel = sub.add_parser(
        "intelligence", help="Intelligence Layer: 决策智能 — 分析/评分/推荐/风险/Approval (独立空间 .factory/intelligence/, 发 intelligence.* 事件)"
    )
    json_opt(p_intel)
    isub = p_intel.add_subparsers(dest="intelligence_command", required=True)
    p_intel_decision = isub.add_parser(
        "decision", help="决策链: Context→Analysis→Options→Evaluation→Recommendation→Risk→Decision Artifact (规则评分四因素, 不绑定 LLM)"
    )
    json_opt(p_intel_decision)
    dsub = p_intel_decision.add_subparsers(dest="decision_command", required=True)
    p_dc_create = dsub.add_parser(
        "create", help="创建决策: 分析→选项→规则评分→推荐→风险→Approval (发 intelligence.decision.* 事件; 高风险经 9c ApprovalGate 提交审批)"
    )
    json_opt(p_dc_create)
    p_dc_create.add_argument("--type", required=True,
                             help="决策类型 (provider_selection/architecture_change/deployment_strategy/provider_migration/...)")
    p_dc_create.add_argument("--subject", required=True, help="决策对象 id (task/project/idea/artifact)")
    p_dc_create.add_argument("--objective", default="", help="决策目标描述")
    p_dc_create.add_argument("--constraint", action="append", default=[], help="约束 (可多次; 高风险关键词检测输入)")
    p_dc_create.add_argument("--option", action="append", default=[],
                             help="选项 NAME:SCORE[:reason[:EVIDENCE]] — SCORE=0-1 单值或四因素 capability,cost,performance,experience (可多次)")
    p_dc_create.add_argument("--evidence", action="append", default=[],
                             help="证据 TYPE:ID[:DESC] (六来源: artifact/event/experience/external_data/human_input/provider_output; 可多次, 必须 ≥1)")
    p_dc_create.add_argument("--context", default=None,
                             help="决策上下文 JSON 文件 (基座; CLI 标志逐字段覆盖, 列表标志追加)")
    p_dc_create.add_argument("--approval-artifact", default=None,
                             help="9c 审批绑定点: 已存在的 product Artifact id (仅高风险决策提交审批请求)")
    p_dc_create.add_argument("--gate", default=None, help="审批门 id (默认按 artifact.type 解析 9c 默认门)")

    p_intel_recommend = isub.add_parser(
        "recommend", help="推荐引擎: 多因素评分 (Capability×0.35+Performance×0.30+Cost×0.20+Experience×0.15, 权重配置化) + Reasoning 解释 + Risk (只推荐不执行; 高风险经 9c ApprovalGate)"
    )
    json_opt(p_intel_recommend)
    p_intel_recommend.add_argument("--task", required=True, help="任务类型 (如 development/testing)")
    p_intel_recommend.add_argument("--capability", default="",
                                   help="任务要求能力 (逗号分隔, 如 code,reasoning)")
    p_intel_recommend.add_argument("--constraint", action="append", default=[],
                                   help="约束 (可多次)")
    p_intel_recommend.add_argument("--candidate", action="append", default=[],
                                   help="候选 ID:CAP:PERF:COST:EXP[:TYPE] — 四因素 0-1, TYPE=provider/agent/skill/workflow (可多次, 缺省 provider)")
    p_intel_recommend.add_argument("--budget", type=float, default=None,
                                   help="成本分门槛 0-1 (候选 cost 分低于此值 → 过滤, 成本不可接受)")
    p_intel_recommend.add_argument("--quality", type=float, default=None,
                                   help="能力分门槛 0-1 (候选 capability 分低于此值 → 过滤, 能力不达标)")
    p_intel_recommend.add_argument("--weights", default=None,
                                   help="权重 W1:W2:W3:W4 (capability:performance:cost:experience; 缺省 0.35:0.30:0.20:0.15)")
    p_intel_recommend.add_argument("--approval-artifact", default=None,
                                   help="9c 审批绑定点: 已存在的 product Artifact id (仅高风险推荐提交审批请求)")
    p_intel_recommend.add_argument("--gate", default=None, help="审批门 id (默认按 artifact.type 解析 9c 默认门)")

    p_intel_experience = isub.add_parser(
        "experience", help="经验闭环: 历史经验清单 + 任务评估 (10A-4, ADR-0033; 只读不执行)"
    )
    json_opt(p_intel_experience)
    esub = p_intel_experience.add_subparsers(dest="experience_command", required=True)
    p_ie_list = esub.add_parser(
        "list", help="经验记录清单 (六域 provider/agent/skill/workflow/project/decision; 发 intelligence.viewed 审计)"
    )
    json_opt(p_ie_list)
    p_ie_list.add_argument("--subject-type", default=None,
                           help="按主体类型过滤 (provider/agent/skill/workflow/project/decision)")
    p_ie_list.add_argument("--subject-id", default=None, help="按经验对象 id 过滤")
    p_ie_eval = esub.add_parser(
        "evaluate", help="任务评估: 基于历史经验推荐执行资源 (agent/provider/skill; 发 intelligence.task.evaluated)"
    )
    json_opt(p_ie_eval)
    p_ie_eval.add_argument("--task", required=True, help="任务类型 (如 development/testing)")
    p_ie_eval.add_argument("--capability", default="",
                           help="任务要求能力 (逗号分隔, 如 code,reasoning)")

    # factory workspace <sub> (Phase 6A, ADR-0016)
    p_workspace = sub.add_parser(
        "workspace", help="Workspace 管理: 多项目组织单位 (workspace.yaml, 发 workspace.* 事件)"
    )
    json_opt(p_workspace)
    wsub = p_workspace.add_subparsers(dest="workspace_command", required=True)
    p_ws_init = wsub.add_parser(
        "init", help="初始化 workspace.yaml: 自动发现项目引用 (managed ∪ examples, 发 workspace.created)"
    )
    json_opt(p_ws_init)
    p_ws_init.add_argument("--name", default=None, help="Workspace 名 (默认 = 工厂根目录名)")
    p_ws_init.add_argument("--force", action="store_true",
                           help="覆盖已存在的 workspace.yaml (先解析后落盘, 失败不半写)")
    p_ws_show = wsub.add_parser(
        "show", help="Workspace 详情 + 项目列表 (含状态, 发 workspace.viewed)"
    )
    json_opt(p_ws_show)

    # factory git <sub> (Phase 6C, ADR-0018)
    p_git = sub.add_parser(
        "git", help="Git 只读查询: status/diff/commits (Git 只读 + 审计, 发 git.* 事件)"
    )
    json_opt(p_git)
    gsub = p_git.add_subparsers(dest="git_command", required=True)
    p_git_status = gsub.add_parser(
        "status", help="仓库状态: branch/current_commit/changes (发 git.status.viewed)"
    )
    json_opt(p_git_status)
    p_git_status.add_argument("--project", default=None, help="项目 id (从 project.yaml 解析 repository)")
    p_git_status.add_argument("--repo", default=None, help="仓库路径 (显式指定, 优先于 --project)")
    p_git_diff = gsub.add_parser(
        "diff", help="工作区变更列表 (逐文件 + 行数 + task 关联, 发 git.change.detected)"
    )
    json_opt(p_git_diff)
    p_git_diff.add_argument("--project", default=None, help="项目 id (从 project.yaml 解析 repository)")
    p_git_diff.add_argument("--repo", default=None, help="仓库路径 (显式指定, 优先于 --project)")
    p_git_commits = gsub.add_parser(
        "commits", help="提交历史 (hash/message/branch/task, 发 git.commit.viewed)"
    )
    json_opt(p_git_commits)
    p_git_commits.add_argument("--project", default=None, help="项目 id (从 project.yaml 解析 repository)")
    p_git_commits.add_argument("--repo", default=None, help="仓库路径 (显式指定, 优先于 --project)")
    p_git_commits.add_argument("--limit", type=int, default=20, help="条数上限 (默认 20)")

    # factory change <sub> (Phase 6D, ADR-0019)
    p_change = sub.add_parser(
        "change", help="Change Intelligence: 提交任务关联/路径分析/L4 验证 (Git 只读 + 审计)"
    )
    json_opt(p_change)
    csub = p_change.add_subparsers(dest="change_command", required=True)
    p_ch_commits = csub.add_parser(
        "commits", help="提交 + 任务关联解析 (message>execution>branch, 发 git.commit.linked/viewed)"
    )
    json_opt(p_ch_commits)
    p_ch_commits.add_argument("--repo", default=None, help="仓库路径 (默认工厂根目录)")
    p_ch_commits.add_argument("--limit", type=int, default=20, help="条数上限 (默认 20)")
    # ★ 2026-09-19 mem-7: 影响面分析（只分析不改）—— 接进【已有的】change 组
    #   ⚠ 教训（R25 禁重复造轮子）: 我起初另起 `sub.add_parser("change")` ⇒ argparse
    #     conflicting subparser 冲突, **整个 CLI 起不来**。加命令前必须先查是否已有该组。
    p_ch_plan = csub.add_parser(
        "plan", help="影响面: 谁调用它/受影响文件/测试覆盖/★风险 (只分析不改)"
    )
    json_opt(p_ch_plan)
    p_ch_plan.add_argument("symbol", help="符号名 (可带前缀, 如 conversation.upsert_fact)")
    p_ch_plan.add_argument("--repo", default="", help="仓库目录 (缺省用已采纳项目)")
    p_ch_analyze = csub.add_parser(
        "analyze", help="任务变更路径分析: Files/Insertions/Deletions/Modules (发 change.analyzed)"
    )
    json_opt(p_ch_analyze)
    p_ch_analyze.add_argument("task_id", help="任务 ID (如 T-001 / MP-BUG-001)")
    p_ch_analyze.add_argument("--repo", default=None, help="仓库路径 (默认工厂根目录)")
    p_ch_validate = csub.add_parser(
        "validate", help="L4 Change Validation: 任务 vs Git 变更证据 → PASS/FAIL/SKIP (发 change.validation.completed)"
    )
    json_opt(p_ch_validate)
    p_ch_validate.add_argument("task_id", help="任务 ID (如 T-001 / MP-BUG-001)")
    p_ch_validate.add_argument("--repo", default=None, help="仓库路径 (默认工厂根目录)")
    p_ch_triggers = csub.add_parser(
        "triggers", help="Change Trigger 管理: 声明式变更驱动规则 (发 change.trigger.created/viewed)"
    )
    json_opt(p_ch_triggers)
    tsub = p_ch_triggers.add_subparsers(dest="trigger_command", required=True)
    p_tr_register = tsub.add_parser(
        "register", help="注册触发器: 事件+项目/类型匹配 → 评估 PASS 启动 target-workflow (发 change.trigger.created)"
    )
    json_opt(p_tr_register)
    p_tr_register.add_argument("--id", required=True, help="触发器 ID (如 TRIG-FEATURE-RELEASE)")
    p_tr_register.add_argument("--event-type", default="workflow.completed",
                               help="触发事件域 (默认 workflow.completed)")
    p_tr_register.add_argument("--project", default=None, help="限定项目 (缺省任意)")
    p_tr_register.add_argument("--task-type", default=None, help="限定任务类型 (缺省任意; 如 feature/bug)")
    p_tr_register.add_argument("--required-validation", default="PASS",
                               help="规则①要求的 L4 Change Validation 状态 (默认 PASS)")
    p_tr_register.add_argument("--target-workflow", required=True,
                               help="评估通过后启动的工作流 ID (须已注册, 如 release)")
    p_tr_list = tsub.add_parser(
        "list", help="触发器列表 (发 change.trigger.viewed)"
    )
    json_opt(p_tr_list)
    p_ch_evaluate = csub.add_parser(
        "evaluate", help="Change 规则评估: 匹配触发器 → 4 规则 → PASS 触发并执行目标工作流 (发 change.trigger.evaluated)"
    )
    json_opt(p_ch_evaluate)
    p_ch_evaluate.add_argument("task_id", help="任务 ID (如 T-001 / MP-BUG-001)")
    p_ch_evaluate.add_argument("--no-execute", action="store_false", dest="execute",
                               default=True,
                               help="只评估不触发 (纯评估模式, 零执行副作用)")
    p_ch_workflows = csub.add_parser(
        "workflows", help="任务关联 workflow 链: 任务工作流 + 触发工作流 (只读)"
    )
    json_opt(p_ch_workflows)
    p_ch_workflows.add_argument("task_id", help="任务 ID (如 T-001 / MP-BUG-001)")

    # factory understand (Phase 7, ADR-0021)
    p_understand = sub.add_parser(
        "understand",
        help="项目理解报告: 阶段识别/产物检测/缺失分析/建议 (只读规则分析, 禁 LLM, "
             "发 understanding.* 事件)",
    )
    json_opt(p_understand)
    p_understand.add_argument("--stage", action="store_true",
                              help="仅输出阶段识别 (stage/confidence/evidence)")
    p_understand.add_argument("path", help="项目路径 (目录)")

    # factory console (Phase 11A, ADR-0034: Human Console Layer — 统一只读视图)
    p_serve = sub.add_parser("serve", help="一条命令起 API + 最小界面（只读; Ctrl-C 停）")
    json_opt(p_serve)
    p_serve.add_argument("--port", type=int, default=8011, help="端口（默认 8011）")
    p_serve.add_argument("--host", default="127.0.0.1", help="绑定地址（默认只绑本机 ✓）")
    p_console = sub.add_parser(
        "console", help="Human Console: 统一只读视图 (Human Layer, 零写操作; 发 console.* 审计事件)"
    )
    json_opt(p_console)
    csub = p_console.add_subparsers(dest="console_command", required=True)
    p_c_dash = csub.add_parser(
        "dashboard", help="Console Dashboard 七域汇总 (projects/approvals/agents/"
                          "decisions/cost/experience/activity; 发 console.dashboard.viewed)"
    )
    json_opt(p_c_dash)
    p_c_dash.add_argument("--limit", type=int, default=10,
                          help="最近决策/活动条数上限 (默认 10)")
    # ★ 2026-09-22（Founder: 看板的"活动"域 + "都要"）: 七域**可下钻**
    for _dom, _help in (
        ("activity", "活动域: 最近事件流（谁在什么时候做了什么）"),
        ("projects", "项目域: 项目清单（id/名字/状态）"),
        ("agents", "Agent 域: 舰队与在跑状态"),
        ("decisions", "决策域: 最近人工/系统决策"),
        ("cost", "成本域: 用量与花费"),
        ("experience", "经验域: 学习自治攒下的经验"),
    ):
        _pc = csub.add_parser(_dom, help=_help)
        json_opt(_pc)
        _pc.add_argument("--limit", type=int, default=20, help="条数上限（默认 20）")
    p_c_ap = csub.add_parser(
        "approvals", help="待人工审批清单 (只读不决定 — 决策权在 product approval "
                          "decide; 发 console.viewed)"
    )
    json_opt(p_c_ap)
    p_c_ap.add_argument("--pending", action="store_true", help="只列待办 (pending)")

    # factory org <sub> (Phase 16A, ADR-0036: factory-org Extension — 组织管理)
    p_org = sub.add_parser(
        "org", help="组织管理: 舰队成员归属 member (给成员设公司/部门 — 派活按归属筛人)"
    )
    json_opt(p_org)
    osub = p_org.add_subparsers(dest="org_command", required=True)

    # factory org member <sub>（舰队成员归属 —— 多公司/多部门落到执行）
    p_org_mem = osub.add_parser(
        "member", help="舰队成员归属（给成员设公司/部门 —— 派活会按归属筛人）")
    json_opt(p_org_mem)
    omsub = p_org_mem.add_subparsers(dest="member_command", required=True)
    p_om_l = omsub.add_parser("list", help="成员清单（含公司/部门归属）")
    json_opt(p_om_l)
    p_om_l.add_argument("--company", default="", help="只看该公司")
    p_om_s = omsub.add_parser("set", help="给成员设归属; --all = 把所有未归属成员一次设好")
    json_opt(p_om_s)
    p_om_s.add_argument("member_id", nargs="?", default="", help="成员 id（--all 时可省）")
    p_om_s.add_argument("--company", default="", help="公司 id（必填）")
    p_om_s.add_argument("--department", default="", help="部门 id（可选）")
    p_om_s.add_argument("--all", action="store_true", help="把所有未归属成员一次设到该公司")

    # factory exec <sub> (Phase A, ADR-0037: factory-exec Extension — 执行闭环)
    p_exec = sub.add_parser(
        "exec", help="执行闭环: run/status/approval (factory-exec Extension, 独立数据空间 <root>/exec/, 发 org.execution.* 事件)"
    )
    json_opt(p_exec)
    esub = p_exec.add_subparsers(dest="exec_command", required=True)

    # factory exec run
    p_exec_run = esub.add_parser(
        "run", help="执行请求 → Runtime (沙箱 + patch + 产物; 发 org.execution.* 链)"
    )
    json_opt(p_exec_run)
    p_exec_run.add_argument("--project", required=True, help="项目目录 (沙箱副本源, 原项目零接触)")
    p_exec_run.add_argument("--task", required=True, help="任务 ID (Task 锚点)")
    p_exec_run.add_argument("--objective", default=None, help="目标描述 (默认派生自 task)")
    p_exec_run.add_argument("--requirement", default="", help="验收标准/约束")
    p_exec_run.add_argument("--employee", default=None, help="员工 ID (org store 解析)")
    p_exec_run.add_argument("--agent", default=None, help="Agent 实例 ID (默认 developer-1)")
    p_exec_run.add_argument("--provider", default=None, help="Provider id (默认 anthropic)")
    p_exec_run.add_argument("--test-cmd", default=None, help="沙箱内测试命令 (验证)")

    # factory exec status
    p_exec_status = esub.add_parser(
        "status", help="执行结果清单/详情 (发 org.execution.viewed 审计)"
    )
    json_opt(p_exec_status)
    p_exec_status.add_argument("--id", default=None, help="结果 ID (缺省列出全部)")

    # factory exec approval <sub>
    p_exec_ap = esub.add_parser(
        "approval", help="审批门禁: approve/deny/apply/list (应用 patch 前必批)"
    )
    json_opt(p_exec_ap)
    asub = p_exec_ap.add_subparsers(dest="approval_command", required=True)
    p_exec_approve = asub.add_parser(
        "approve", help="审批通过 (发 org.execution.approved)"
    )
    json_opt(p_exec_approve)
    p_exec_approve.add_argument("--id", required=True, help="审批记录 ID")
    p_exec_approve.add_argument("--by", required=True, help="审批人 (Human 身份)")
    p_exec_approve.add_argument("--comment", default="")
    p_exec_deny = asub.add_parser(
        "deny", help="审批拒绝 (comment 反馈; 不发 approved 事件)"
    )
    json_opt(p_exec_deny)
    p_exec_deny.add_argument("--id", required=True)
    p_exec_deny.add_argument("--by", required=True)
    p_exec_deny.add_argument("--comment", default="")
    p_exec_apply = asub.add_parser(
        "apply", help="应用已批准 patch (未批 → 硬拒绝; 发 org.execution.applied)"
    )
    json_opt(p_exec_apply)
    p_exec_apply.add_argument("--id", required=True)
    p_exec_apply.add_argument("--project", default=None, help="目标项目 (缺省取请求 project_dir)")
    p_exec_list = asub.add_parser(
        "list", help="审批记录清单 (发 org.execution.viewed 审计)"
    )
    json_opt(p_exec_list)
    p_exec_list.add_argument("--status", default=None, help="过滤: pending|approved|rejected")

    # factory demo (Phase 13A: Demo Productization — 一键跑通完整生命周期)
    p_demo = sub.add_parser(
        "demo", help="产品化演示: 一键跑通完整生命周期 (Mock Provider 只生成内容, 生命周期/审批/决策真实, 临时工厂根)"
    )
    json_opt(p_demo)
    dsub = p_demo.add_subparsers(dest="demo_command", required=True)
    p_demo_markpad = dsub.add_parser(
        "markpad", help="MarkPad 表格编辑器增强: idea→research→prd→[审批]→ui→[审批]→architecture→task→experience (输出每阶段 Artifact/Event/Decision 日志)"
    )
    json_opt(p_demo_markpad)
    p_demo_markpad.add_argument(
        "--demo-dir", default=None,
        help="idea.json/requirements.json 目录 (默认 examples/markpad-demo)",
    )
    p_demo_markpad.add_argument(
        "--approver", default=None,
        help="人工审批人 (demo 自动批准, 9c 审批状态机真实; 默认 shenlongze)",
    )
    p_demo_markpad.add_argument(
        "--keep-root", action="store_true",
        help="保留临时工厂根目录 (默认退出清理; tempfile 创建, 不依赖 /tmp 固定路径)",
    )

    return p


def _top_command_names() -> set[str]:
    """全部顶层命令名（从解析器读, 不写死 —— 命令表变了它跟着变）。"""
    try:
        for a in build_parser()._actions:
            if hasattr(a, "choices") and isinstance(a.choices, dict) and "status" in a.choices:
                return {str(k) for k in a.choices}
    except Exception:  # noqa: BLE001 — 读不到就不预校验（照旧交给 argparse）
        pass
    return set()


def _resolve_plan_id(ctx: FactoryContext, token: str) -> str:
    """看树时允许用户说**项目名**（而不是记 PLAN-id）。

    ★ 2026-09-21（Founder 实测）: "看社区图书馆那棵树" ⇒ `tasktree … community-library` 报
      "任务树不存在" ✗ —— 用户/助手拿不到项目 id 就断头路。现在: 项目名/id/片段 ⇒ 取该项目最新一棵树。
    """
    tk = str(token or "").strip()
    if not tk or tk.upper().startswith("PLAN-"):
        return tk
    try:
        from ai_factory_os.services.organization.projects import ProjectStore
        from ai_factory_os.services.work import decomposition as _D

        rows = ProjectStore(ctx.root / "org").list_projects() or []
        tl = tk.lower()
        pid = ""
        for r in rows:
            nm = str(getattr(r, "name", "") or "").lower()
            rp = str(getattr(r, "repo_path", "") or "").rstrip("/").split("/")[-1].lower()
            if tl in (str(getattr(r, "id", "")).lower(), nm, rp) or (tl and (tl in nm or tl in rp)):
                pid = str(getattr(r, "id", "") or "")
                break
        if not pid:
            return tk
        trees = [t for t in (_D.list_trees(ctx.root) or [])
                 if str(t.get("project_id")) == pid and str(t.get("plan_id", "")).upper().startswith("PLAN-")]
        if not trees:
            return tk
        trees.sort(key=lambda t: str(t.get("created_at") or ""), reverse=True)
        got = str(trees[0].get("plan_id") or tk)
        if got != tk:
            print(f"  （按项目 {tk} 找到最新一棵树: {got}）")
        return got
    except Exception:  # noqa: BLE001 — 解析失败就按原样交给下游（不挡）
        return tk


def main(argv: list[str] | None = None) -> int:
    """CLI 入口: 返回退出码 (console script 以返回值作为进程退出码)。"""
    # ★ 2026-09-21（Founder: "我需要如何进入 factory 的 cli"）: 空参**不再甩英文报错**,
    #   而是进友好首屏（版本 + 你的数据概览 + 编号菜单; 有终端可交互, 非终端只打印）。
    #   实测病: 原来 `factory` ⇒ "error: the following arguments are required: command" ✗ 等于进不去。
    _argv = list(sys.argv[1:] if argv is None else argv)
    # ★ 2026-09-21 修（Founder 实测: `factory -v` 竟然进了会话 —— 应该直接报版本 ✗）:
    #   版本是最常被敲的开关之一, 必须**直接答**（`-v` / `-V` / `--version` / `version`）。
    # ★ 2026-09-21 加宽（Founder 又敲了 `-version` ⇒ 仍然进了会话 ✗）:
    #   把前导横线都去掉再比 —— `-v` / `-V` / `--v` / `version` / `-version` / `--Version` 都算要版本。
    #   （没有任何命令叫 v / version, 所以这样放宽不会抢走真命令 ✓）
    if any(a.lstrip("-").lower() in ("v", "version") for a in _argv if not a.startswith("--root")):
        try:
            from importlib.metadata import version as _ver

            _v = _ver("ai-software-factory")
        except Exception:  # noqa: BLE001 — 拿不到就如实说, 不编
            _v = "unknown（包元数据读不到）"
        print(f"AI Factory OS  v{_v}")
        print("  想看能干什么: factory help     ·  启动会话: factory start")
        return 0
    # ★ 敲错命令（如 `veresion`）⇒ 一句人话 + 像不像的提示, 不再甩整屏英文 usage ✗
    _cmdlist = _top_command_names()
    # ★ 取"第一个真正的命令词"时要**跳过取值型开关的值** ——
    #   实测踩到: `--root /tmp/xxx start` 里那个路径被当成命令名 ⇒ 报"没有这个命令: /tmp/xxx" ✗
    _takes_value = {"--root"}
    _first, _skip = "", False
    for _a in _argv:
        if _skip:
            _skip = False
            continue
        if _a in _takes_value:
            _skip = True
            continue
        if _a.startswith("-"):
            continue
        _first = _a
        break
    if _first and _cmdlist and _first not in _cmdlist:
        import difflib as _dl

        _near = _dl.get_close_matches(_first, sorted(set(_cmdlist) | {"version", "help"}), n=3, cutoff=0.6)
        print(f"没有这个命令: {_first}")
        if _near:
            print(f"  你是不是想敲: {' / '.join(_near)}")
        print("  看全部命令: factory help     ·  看版本: factory -v")
        return 2
    if not any(not a.startswith("-") for a in _argv):
        # ★ 认不出的开关（如 `-Ver`）⇒ 报"未知开关", 不静默进会话 ✗
        _known_flags = {"--json", "--root", "-h", "--help"}
        _bad_flag = next((a for a in _argv
                          if a.startswith("-") and a.split("=", 1)[0] not in _known_flags), "")
        if _bad_flag:
            print(f"未知开关: {_bad_flag}")
            print("  看版本: factory -v     ·  看全部命令: factory help     ·  启动会话: factory start")
            return 2
        from .domains.welcome import run_welcome

        _root = ""
        for _i, _a in enumerate(_argv):
            if _a == "--root" and _i + 1 < len(_argv):
                _root = _argv[_i + 1]
            elif _a.startswith("--root="):
                _root = _a.split("=", 1)[1]
        if not _root:
            from .context import DEFAULT_ROOT

            _root = str(DEFAULT_ROOT)
        # 在终端里 ⇒ **启动并进入**交互式 CLI; 非终端（管道/脚本/CI）⇒ 只打印首屏, 不挂
        if sys.stdin.isatty() and sys.stdout.isatty():
            from .domains.welcome import run_shell

            return run_shell(_root)
        return run_welcome(_root)

    parser = build_parser()
    args = parser.parse_args(_argv)
    ctx = FactoryContext(args.root)
    ctx.ensure_dirs()  # ADR-0002 决策 5: 所有命令幂等自建目录与 DB, 不强制先 init

    # ★ 跨域装配（bootstrap/wiring.py —— SSoT §一: bootstrap 是唯一可 import 全部的层）。
    #   各域用 bind_lookups() 声明"我需要什么跨域能力", 但若没人注入, hook 永远为空:
    #   实测后果 = 会话派生的 PRD 没进项目 ⇒ `factory progress` 按项目统计全是 0,
    #   而 `factory trace` 按会话看样样都有（数据在、**关联缺**）。
    #   失败安全: 装配失败不阻断命令（该项状态会记在 wiring.wired() 里, 可查）。
    try:
        from ai_factory_os.bootstrap.wiring import wire as _wire
        _wire()
    except Exception:  # noqa: BLE001 — 装配是增强, 不是命令前置条件
        pass

    try:
        if args.command == "init":
            result = cmd_init(ctx)
        elif args.command == "start":
            from .domains.welcome import run_shell

            return run_shell(ctx.root)
        elif args.command == "help":
            from .domains.welcome import render_help

            if getattr(args, "json", False):
                return 0
            print(render_help(str(getattr(args, "role", "") or "")))
            return 0
        elif args.command == "task":
            result = _dispatch_task(ctx, args)
        elif args.command == "conversation":
            result = _dom_conversation.run(ctx, args)
        elif args.command == "event":
            result = _dispatch_event(ctx, args)
        elif args.command == "status":
            result = cmd_status(ctx)
        elif args.command == "validate":
            result = cmd_validate(ctx, args)
        elif args.command == "agent":
            result = _dispatch_agent(ctx, args)
        elif args.command == "skill":
            result = _dispatch_skill(ctx, args)
        elif args.command == "workflow":
            result = _dispatch_workflow(ctx, args)
        elif args.command == "runtime":
            result = _dispatch_runtime(ctx, args)
        elif args.command == "execution":
            result = _dispatch_execution(ctx, args)
        elif args.command == "run":
            result = _dispatch_run_locked(ctx, args)
        elif args.command == "run-status":
            result = _dispatch_run_status(ctx, args)
        elif args.command == "checkpoint":
            result = _dispatch_checkpoint(ctx, args)
        elif args.command == "backup":
            result = _dispatch_backup(ctx, args)
        elif args.command == "recover":
            # ★ 第 4 件之③: 给了 --plan ⇒ 按检查点恢复树执行（人主动）; 否则走任务域老路
            result = (cmd_recover_plan(ctx, args) if str(getattr(args, "plan", "") or "")
                      else cmd_recover(ctx, args))
        elif args.command == "dashboard":
            result = cmd_dashboard(ctx, args)
        elif args.command == "metrics":
            result = cmd_metrics(ctx, args)
        elif args.command == "verification":
            result = _dispatch_verification(ctx, args)
        elif args.command == "evd":
            result = _dispatch_evd(ctx, args)
        elif args.command == "history":
            result = _dispatch_history(ctx, args)
        elif args.command == "create":
            if not str(getattr(args, "create_type", "") or "").strip():
                # ★ 2026-09-22（Founder: "create 缺位置参数只回英文 required: create_type"）
                print("  要建什么? 说清楚再跑 ✓")
                print("    factory create company     建公司（含部门/角色）")
                print("    factory create department  建部门（需 --company）")
                print("    factory create project     建项目（--name/--repo-path 等）")
                print("  想看某个的完整参数: factory create company -h")
                return 2
            result = _dispatch_create(ctx, args)
        elif args.command == "plugin":
            result = _dispatch_plugin(ctx, args)
        elif args.command == "arch":
            result = _dispatch_arch(ctx, args)
        elif args.command == "serve":
            return _run_serve(ctx, args)
        elif args.command == "kanban":
            result = _dispatch_kanban(ctx, args)
        elif args.command == "update":
            result = _dispatch_update(ctx, args)
        elif args.command == "approval":
            result = _dispatch_approval(ctx, args)
        elif args.command == "knowledge":
            result = _dispatch_knowledge(ctx, args)
        elif args.command == "memory":
            result = _dispatch_memory(ctx, args)
        elif args.command == "project":
            result = _dispatch_project(ctx, args)
        elif args.command == "llm":
            result = _dispatch_llm(ctx, args)
        elif args.command == "tool":
            result = _dispatch_tool(ctx, args)
        elif args.command == "mcp":
            result = _dispatch_mcp(ctx, args)
        elif args.command == "discover":
            result = _dispatch_discover(ctx, args)
        elif args.command == "provider":
            result = _dispatch_provider(ctx, args)
        elif args.command == "workspace":
            result = _dispatch_workspace(ctx, args)
        elif args.command == "git":
            result = _dispatch_git(ctx, args)
        elif args.command == "change":
            result = _dispatch_change(ctx, args)
        elif args.command == "understand":
            result = cmd_understand(ctx, args)
        elif args.command == "tasktree":
            result = _dispatch_tasktree(ctx, args)
        elif args.command == "product":
            result = _dispatch_product(ctx, args)
        elif args.command == "intelligence":
            result = _dispatch_intelligence(ctx, args)
        elif args.command == "console":
            result = _dispatch_console(ctx, args)
        elif args.command == "org":
            result = _dispatch_org(ctx, args)
        elif args.command == "exec":
            result = _dispatch_exec(ctx, args)
        elif args.command == "chain":
            result = _dispatch_chain(ctx, args)
        elif args.command == "demo":
            result = _dispatch_demo(ctx, args)
        else:  # pragma: no cover — argparse required=True 已拦截
            raise CliError(f"unknown command: {args.command}", exit_code=2)
    except CliError as exc:
        # ★ 2026-09-15 统一: **不再加 "error: " 前缀** —— 与老 CLI（现役入口）
        #   的错误输出对齐。老 CLI 的前缀是写在消息里的（如 "错误: history search 需要检索词"）,
        #   框架层再加一层会变成 "error: 错误: …", 两套 CLI 消息不一致。
        #   命令面（命令名/子命令/参数）与错误消息**逐字一致**才是"替换"的硬验收。
        print(exc.message, file=sys.stderr)
        return exc.exit_code
    except Exception as exc:  # 兜底: 内部异常 → 退出码 1 (cli-design §5)
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    exit_code = int(result.get("exit_code", 0))
    _print_output(args, result)
    return exit_code


def _dispatch_task(ctx: FactoryContext, args: Any) -> dict:
    if args.task_command == "create":
        return cmd_task_create(ctx, args)
    if args.task_command == "list":
        return cmd_task_list(ctx, args)
    if args.task_command == "status":
        return cmd_task_status(ctx, args)
    if args.task_command == "update":
        return cmd_task_update(ctx, args)
    raise CliError(f"unknown task command: {args.task_command}", exit_code=2)


def _dispatch_event(ctx: FactoryContext, args: Any) -> dict:
    if args.event_command == "logs":
        return cmd_event_logs(ctx, args)
    raise CliError(f"unknown event command: {args.event_command}", exit_code=2)


def _dispatch_agent(ctx: FactoryContext, args: Any) -> dict:
    if args.agent_command == "add":
        return cmd_agent_add(ctx, args)
    if args.agent_command == "list":
        return cmd_agent_list(ctx, args)
    if args.agent_command == "assign":
        return cmd_agent_assign(ctx, args)
    if args.agent_command == "assignments":
        return cmd_agent_assignments(ctx, args)
    if args.agent_command == "release":
        return cmd_agent_release(ctx, args)
    raise CliError(f"unknown agent command: {args.agent_command}", exit_code=2)


def _dispatch_skill(ctx: FactoryContext, args: Any) -> dict:
    if args.skill_command == "add":
        return cmd_skill_add(ctx, args)
    if args.skill_command == "list":
        return cmd_skill_list(ctx, args)
    raise CliError(f"unknown skill command: {args.skill_command}", exit_code=2)


def _dispatch_workflow(ctx: FactoryContext, args: Any) -> dict:
    if args.workflow_command == "list":
        return cmd_workflow_list(ctx, args)
    if args.workflow_command == "add":
        return cmd_workflow_add(ctx, args)
    if args.workflow_command == "run":
        return cmd_workflow_run(ctx, args)
    if args.workflow_command == "status":
        return cmd_workflow_status(ctx, args)
    raise CliError(f"unknown workflow command: {args.workflow_command}", exit_code=2)


def _dispatch_run_locked(ctx: FactoryContext, args: Any) -> dict:
    """`run` 外面套一层**仓库级跨进程锁**（Founder 问: "同一个仓库同一时间 两个人改？？？"）。

    为什么必须有（真实现状）:
      · `claim_leaf()` 是 CAS ⇒ **同一进程内**两个 agent 不会拿同一张卡 ✓
      · 但**跨进程**（两个终端各跑一个 run）没有锁 ✗, 而一个项目只有一个工作副本
        ⇒ 同一张卡可能被双领、同一文件互相覆盖且不报错 ✗
    行为: 抢不到 ⇒ **拒绝开跑**并把"谁在跑"告诉老板 ✓; 陈旧锁（PID 已死）自动接管 ✓;
      `--force` 强抢（会覆盖对方改动 ✗, 必须显式要求）; 无论成败都释放（只删自己的 ✓）。
    """
    from ai_factory_os.services.work import runlock as _rl

    _pid = str(getattr(args, "project", "") or "")
    _cmd = f"factory run --project {_pid}" if _pid else "factory run"
    _force = bool(getattr(args, "force", False))
    try:
        _info = _rl.acquire(ctx.root, _pid, command=_cmd, force=_force)
    except _rl.RunLockError as exc:
        raise CliError(f"{exc}", exit_code=3) from exc
    if _info.get("took_over") and _info.get("note"):
        print(f"  {_info['note']}")
    try:
        return _dispatch_run(ctx, args)
    finally:
        if _rl.release(ctx.root, _pid):
            pass                                     # 释放成功（静默 ✓）
        else:
            print("  ⚠ 锁没释放（PID 不符/已不存在）—— 不删别人的锁 ✗")


def _dispatch_runtime(ctx: FactoryContext, args: Any) -> dict:
    if args.runtime_command == "add":
        return cmd_runtime_add(ctx, args)
    if args.runtime_command == "list":
        return cmd_runtime_list(ctx, args)
    if args.runtime_command == "test":
        return cmd_runtime_test(ctx, args)
    if args.runtime_command == "catalog":
        return _dispatch_runtime_catalog(ctx, args)
    raise CliError(f"unknown runtime command: {args.runtime_command}", exit_code=2)


def _dispatch_runtime_catalog(ctx: FactoryContext, args: Any) -> dict:
    if args.runtime_catalog_command == "list":
        return cmd_runtime_catalog_list(ctx, args)
    if args.runtime_catalog_command == "show":
        return cmd_runtime_catalog_show(ctx, args)
    raise CliError(f"unknown runtime catalog command: {args.runtime_catalog_command}", exit_code=2)


def _dispatch_execution(ctx: FactoryContext, args: Any) -> dict:
    if args.execution_command == "list":
        return cmd_execution_list(ctx, args)
    if args.execution_command == "run":
        return cmd_execution_run(ctx, args)
    if args.execution_command == "status":
        return cmd_execution_status(ctx, args)
    raise CliError(f"unknown execution command: {args.execution_command}", exit_code=2)


def _dispatch_checkpoint(ctx: FactoryContext, args: Any) -> dict:
    if args.checkpoint_command == "create":
        return cmd_checkpoint_create(ctx, args)
    if args.checkpoint_command == "list":
        return cmd_checkpoint_list(ctx, args)
    raise CliError(f"unknown checkpoint command: {args.checkpoint_command}", exit_code=2)


def _dispatch_verification(ctx: FactoryContext, args: Any) -> dict:
    """factory verification [list|get] —— 验收域（底层已在新地基: services/validation）。

    与老 CLI `cli_factory.verification_cmd`（L8151）行为一致:
      list → 全部 ver-*（可按 task_run / exs 过滤）; get → 单条详情。
    """
    from ai_factory_os.services.validation.verification_store import (
        get_verification, list_verifications,
    )

    root = ctx.root
    action = getattr(args, "action", "list") or "list"
    if action == "get":
        rec = get_verification(root, getattr(args, "verification_id", "") or "")
        if rec is None:
            raise CliError(f"verification not found: {args.verification_id}", exit_code=1)
        return {"action": "get", "verification": rec}
    recs = list_verifications(root, task_run_id=getattr(args, "task_run", "") or "",
                              exs_id=getattr(args, "exs", "") or "")
    return {"action": "list", "count": len(recs), "items": recs}


def _print_verification(sub: str, r: dict) -> None:
    if sub == "get":
        v = r["verification"]
        print(f"verification_id: {v.get('verification_id') or v.get('id')}")
        print(f"  status:           {v.get('status')}")
        print(f"  task_run_id:      {v.get('task_run_id')}")
        print(f"  exs_id:           {v.get('exs_id')}")
        print(f"  type:             {v.get('verification_type')}")
        print(f"  method:           {v.get('method')}")
        print(f"  attempt:          {v.get('attempt')}")
        print(f"  created_at:       {v.get('created_at')}")
        print(f"  completed_at:     {v.get('completed_at')}")
        return
    print(f"Verifications ({r['count']}):")
    for x in r["items"]:
        print(f"  {x.get('verification_id') or x.get('id')}  {str(x.get('status')):<10} "
              f"run={x.get('task_run_id') or '-'}  {x.get('method') or x.get('verification_type') or ''}")


def _dispatch_evd(ctx: FactoryContext, args: Any) -> dict:
    """factory evd [list|get] —— 证据 SSOT（底层已在新地基: services/validation/evidence_store）。

    与老 CLI `cli_factory.evd_cmd`（L8217）行为一致。
    """
    from ai_factory_os.services.validation.evidence_store import get_evidence, list_evidence

    root = ctx.root
    action = getattr(args, "action", "list") or "list"
    if action == "get":
        ev = get_evidence(root, getattr(args, "evidence_id", "") or "")
        if ev is None:
            raise CliError(f"evidence not found: {args.evidence_id}", exit_code=1)
        return {"action": "get", "evidence": ev}
    evs = list_evidence(root, verification_id=getattr(args, "verification", "") or "")
    return {"action": "list", "count": len(evs), "items": evs}


def _print_evd(sub: str, r: dict) -> None:
    if sub == "get":
        ev = r["evidence"]
        print(f"evidence_id: {ev.get('evidence_id')}")
        print(f"  type:        {ev.get('evidence_type')}")
        print(f"  ver_refs:    {', '.join(ev.get('verification_refs') or []) or '-'}")
        print(f"  source:      {ev.get('source_ref')}")
        print(f"  created:     {ev.get('created_at')}")
        print(f"  content:     {str(ev.get('content') or '')[:200]}")
        return
    print(f"Evidence ({r['count']}):")
    for e in r["items"]:
        print(f"  {e.get('evidence_id')}  {e.get('evidence_type')}  "
              f"ver={e.get('verification_refs') or []}")


def _load_json_safe(path: Any) -> Any | None:
    """fail-safe JSON 读取（缺失/损坏 → None; 永不抛）。

    与老 CLI `cli_factory._load_json_safe` 等价 —— 在新 CLI 里**重写**而非搬原文件:
    老区有 20 处引用它, 搬文件会牵动 20 个调用点（先搬叶子纪律）。
    """
    import json as _json
    try:
        return _json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 只读展示失败安全
        return None


def _task_rows(data_dir: Any) -> list[dict[str, Any]]:
    """任务行（id/title/status/project/role/agent）—— 照老 CLI `_task_rows`（L783）逻辑。

    合并四源（WebUI/CLI 同源, P2b 同步）:
      ① tasks/*.json（每文件一条）
      ② ops/unified/entities.json 补 required_role
      ③ assignments/assignments.json 补 agent_id
      ④ workspace/projects/*/management/backlog/task.json（会话/WebUI 创建）
      ⑤ ★ 任务树的叶（开发任务 = 执行的真实账本; 判据见 services/work/progress.py）
    """
    data_dir = Path(data_dir)
    rows: list[dict[str, Any]] = []
    _role_by_task: dict[str, str] = {}
    _agent_by_task: dict[str, str] = {}
    try:
        import json as _json
        for _f in [data_dir / "ops" / "unified" / "entities.json"]:
            if _f.is_file():
                for _e in _json.loads(_f.read_text(encoding="utf-8")):
                    if isinstance(_e, dict) and _e.get("type") == "task":
                        _r = str(_e.get("required_role") or "").strip()
                        if _r:
                            _role_by_task[str(_e.get("id"))] = _r
        _af = data_dir / "assignments" / "assignments.json"
        if _af.is_file():
            _d = _json.loads(_af.read_text(encoding="utf-8"))
            for _a in (list(_d.values()) if isinstance(_d, dict) else _d):
                if isinstance(_a, dict) and _a.get("task_id"):
                    _agent_by_task[str(_a["task_id"])] = str(_a.get("agent_id") or "")
    except Exception:  # noqa: BLE001 — 失败安全 ✓ 补不上就不补 ✓
        pass

    for path in sorted((data_dir / "tasks").glob("*.json")):
        row = _load_json_safe(path)
        if not isinstance(row, dict) or not row.get("id"):
            continue
        rows.append({
            "id": row.get("id", ""),
            "title": row.get("title", ""),
            "status": row.get("status", ""),
            "project": row.get("project", ""),
            "role": _role_by_task.get(str(row.get("id", "")), ""),
            "agent": _agent_by_task.get(str(row.get("id", "")), ""),
        })
    for pdir in sorted((data_dir / "workspace" / "projects").glob("*")):
        if not pdir.is_dir():
            continue
        tf = pdir / "management" / "backlog" / "task.json"
        data = _load_json_safe(tf) or {}
        tasks = data.get("tasks") if isinstance(data, dict) else None
        if not isinstance(tasks, dict):
            continue
        for tid, t in tasks.items():
            if not isinstance(t, dict):
                continue
            rows.append({
                "id": str(t.get("id") or tid),
                "title": str(t.get("title") or ""),
                "status": str(t.get("status") or ""),
                "project": str(t.get("project") or pdir.name),
            })
    # ⑤ ★ 任务树的叶（= 开发任务 = 执行的真实账本）——
    #    实测踩到（全链路实跑, 卡点 1）: 上面四源都没有它 ⇒ 工厂干着活、看板却显示 0。
    #    判据只在 progress.py 一份（一能力一处）, 这里只做合并。
    # ★★ 读失败【不许静默】（我自己踩过: 一句 `except: pass` 把"树文件有副本 ⇒ 读树被拒"
    #    吞成了看板 0 个任务 —— 看起来像"没任务", 其实是坏了）。⇒ 显式告警到 stderr。
    try:
        from ai_factory_os.services.work import progress as _prog
        rows.extend(_prog.leaf_rows(data_dir))
    except Exception as exc:  # noqa: BLE001 — 失败安全（但必须可见）
        import sys as _sys
        print(f"⚠ 任务树读取失败（看板/清单会少掉'开发任务'那一部分）: "
              f"{type(exc).__name__}: {str(exc)[:160]}", file=_sys.stderr)
    return rows


def _dispatch_kanban(ctx: FactoryContext, args: Any) -> dict:
    """factory kanban —— 按 status/project/role/agent 分列的看板视图。

    与老 CLI `cli_factory.kanban`（L9538）**逐字一致**（含所有提示语与表格形状）。
    返回 {lines: [...]} —— print 阶段统一输出。
    """
    rows = _task_rows(ctx.root)
    pid = str(getattr(args, "project", "") or "").strip()

    # ★ Founder: "看板按项目分屏（三个项目各一屏）" ⇒ 默认**每个项目各一屏**;
    #   `--project X` 只看一个 · `--merged` 合成一块（默认不再是合在一起 ✓）
    if not pid and not bool(getattr(args, "merged", False)):
        import argparse as _ap

        _pids = sorted({str(r.get("project") or "") for r in rows if str(r.get("project") or "")})
        if len(_pids) > 1:
            # ★ 表头带项目名 + 说明（真数据: 取 org 项目库 + 会话需求原话, 不编 ✗）
            _name: dict[str, str] = {}
            _notes: dict[str, str] = {}
            try:
                from ai_factory_os.services.organization.projects import ProjectStore

                from apps.cli.commands import _project_notes

                _proj = ProjectStore(ctx.root / "org").list_projects() or []
                for _rec in _proj:
                    _name[str(getattr(_rec, "id", "") or "")] = str(getattr(_rec, "name", "") or "")
                # ★ 传**对象**（helper 用 getattr 读 id/description ✓ —— 上次我传 dict ⇒ 全取不到 ✗）
                _notes = _project_notes(ctx.root, list(_proj)) or {}
            except Exception:  # noqa: BLE001 — 拿不到就不写表头说明 ✓
                pass
            out: list[str] = []
            _tail: list[str] = []
            _n = len(_pids)
            for _i, _p in enumerate(_pids, 1):
                _sub = _ap.Namespace(**{**vars(args), "project": _p, "merged": True})
                _ls = list(_dispatch_kanban(ctx, _sub).get("lines") or [])
                # 数据源只在最后写一次 ✓（每屏都写=噪音 ✗）
                _keep = [x for x in _ls if "数据源" not in x and "列 = 任务实际流转顺序" not in x]
                _tail = [x for x in _ls if x not in _keep] or _tail
                _head = f"  ══ [{_i}/{_n}] {_name.get(_p) or _p}"
                _note = (_notes.get(_p) or "").strip()
                _head += f"（{_p}）" if _name.get(_p) else ""
                _head += ("  " + _note[:40]) if _note and _note != "（未记录说明）" else ""
                out.append(_head)
                out.extend(_keep)
                out.append("")
            out.extend(_tail)
            return {"lines": out}
    if pid:
        rows = [r for r in rows if pid in str(r.get("project") or "")]

    group = str(getattr(args, "group", "status") or "status")
    show_all = bool(getattr(args, "all", False))
    L: list[str] = []

    if group in ("project", "role", "agent"):
        key_fn = {
            "project": lambda r: str(r.get("project") or "(无项目)"),
            "role": lambda r: str(r.get("role") or "(无角色)"),
            "agent": lambda r: str(r.get("agent") or "(未分配)"),
        }[group]
        buckets_p: dict[str, list[dict]] = {}
        for r in rows:
            buckets_p.setdefault(key_fn(r), []).append(r)
        order = sorted(buckets_p, key=lambda k: (-len(buckets_p[k]), k))
        group_label = {"project": "项目", "role": "角色", "agent": "执行人"}[group]
        L.append(f"=== 看板 · 按{group_label}分列（共 {len(rows)} 个任务 · {len(order)} 列）===")
        L.append("")
        for k in (order if show_all else order[:12]):
            items = buckets_p[k]
            done = sum(1 for i in items if str(i.get("status")) == "done")
            L.append(f"  ┌─ {k[:34]}（{len(items)} 个 · 完成 {done}）")
            for r in (items if show_all else items[:3]):
                L.append(f"  │  {str(r.get('id'))[:20]:22s} {str(r.get('title'))[:38]:40s}"
                         f" [{str(r.get('status'))[:11]}]")
            if len(items) > 3 and not show_all:
                L.append(f"  │  … 另 {len(items) - 3} 条")
            L.append("  └" + "─" * 40)
        if len(order) > 12 and not show_all:
            L.append(f"  … 另 {len(order) - 12} 列（--all 看全部）")
        L.append("")
        L.append("  数据源: ①tasks/*.json ②backlog task.json ③分配记录（agent 维度 ✓）")
        if group == "role":
            L.append("  ⚠ 多数任务无 required_role ✗ → 会集中在「(无角色)」列（数据现状 ✓ 不是显示 bug ✗）")
        if group == "agent":
            L.append("  ⚠ 分配记录仅 4 条 ✗ → 「(未分配)」会很大 ✓（数据现状 ✓）")
        return {"lines": L}

    COLS = [("todo", "待办"), ("ready", "就绪"), ("in_progress", "进行中"),
            ("review", "待评审"), ("blocked", "受阻"), ("failed", "失败"),
            ("done", "完成"), ("cancelled", "取消")]
    buckets: dict[str, list[dict]] = {k: [] for k, _ in COLS}
    other: list[dict] = []
    for r in rows:
        st = str(r.get("status") or "").strip().lower()
        (buckets[st] if st in buckets else other).append(r)

    # ★ 2026-09-21 改成**横排四列**（真看板的样子; Founder 说"kanban"）+ 中文宽度对齐 + 主题色
    from apps.cli.textwidth import ljust_display as _lj, truncate_display as _tr

    shown = [(k, lb) for k, lb in COLS if buckets[k] or k in ("todo", "in_progress")]
    _limit = int(getattr(args, "limit", 10) or 10)
    _per_col = 999 if show_all else max(1, _limit)
    _colw = 30                                    # 每列宽（含缩进）
    _fits = max(1, (_term_cols() - 4) // _colw)
    L.append(f"  看板 · {'项目 ' + pid if pid else '全部'} · 共 {len(rows)} 个任务"
             + (f" · 只显示前 {_fits} 列" if len(shown) > _fits else ""))
    L.append("")
    if _fits >= 2:                                # 横排（真看板 ✓）
        for _i in range(0, len(shown), _fits):
            _grp = shown[_i:_i + _fits]
            L.append("  " + "".join(_lj(_paint_kb(k, lb, buckets[k]), _colw) for k, lb in _grp))
            _lists = [(buckets[k] if show_all else buckets[k][:_per_col], buckets[k]) for k, _ in _grp]
            for _row in range(max((len(x) for x, _ in _lists), default=0)):
                _cells: list[str] = []
                for _items, _allitems in _lists:
                    if _row < len(_items):
                        _r = _items[_row]
                        _t = _tr(str(_r.get("title") or ""), _colw - 15)
                        _cells.append(_lj("  " + _t, _colw))
                    elif _row == len(_items) and len(_allitems) > len(_items):
                        _cells.append(_lj(f"  … 另 {len(_allitems) - len(_items)} 条", _colw))
                    else:
                        _cells.append(" " * _colw)
                L.append("".join(_cells).rstrip())
            L.append("")
    else:                                         # 太窄 ⇒ 退回竖排（照旧 ✓）
        for key, label in shown:
            items = buckets[key]
            L.append(f"  ┌─ {label}（{len(items)}）")
            for r in (items if show_all else items[:_per_col]):
                L.append(f"  │  {_tr(str(r.get('id') or ''), 22):22s} {_tr(str(r.get('title') or ''), 40)}"
                         f" {str(r.get('project') or '')[:16]}")
            if len(items) > 5 and not show_all:
                L.append(f"  │  … 另 {len(items) - _per_col} 条（--all 看全部 / --limit N 调条数）")
            L.append("  └" + "─" * 40)
    if other:
        L.append(f"  （另有 {len(other)} 条状态未识别）")
    L.append("  数据源: 与 `factory task list` 同一份（①tasks ②backlog ③分配记录 ④**任务树的叶=开发任务**）✓")
    L.append("          列 = 任务实际流转顺序 ✓（叶状态 pending→claimed→completed 直接映射到列）")
    return {"lines": L}


def _term_cols() -> int:
    """终端列数（拿不到给 100; 用于决定看板列数 ✓）。"""
    try:
        import shutil as _sh

        return _sh.get_terminal_size((100, 30)).columns
    except Exception:  # noqa: BLE001
        return 100


def _paint_kb(_key: str, label: str, items: list[dict]) -> str:
    """列头（带计数 + 主题色: 待办=中性 / 进行中=琥珀 / 完成=绿 / 取消=灰 ✓）。"""
    try:
        from apps.cli.theme import paint

        _el = {"in_progress": "warn", "done": "good", "cancelled": "status_dim"}.get(_key, "status_strong")
        return paint(_el, f"{label} ({len(items)})")
    except Exception:  # noqa: BLE001
        return f"{label} ({len(items)})"


def _as_dict(x: Any) -> dict:
    """把快照里的元素统一成 dict（dict / pydantic 对象 / 普通对象都吃得下 ✓）。

    ★ 实测踩到: `Decision` 是 **pydantic 对象** ⇒ 直接 `.get` 会 AttributeError 崩 ✗
    """
    if isinstance(x, dict):
        return x
    for _m in ("model_dump", "dict"):
        _f = getattr(x, _m, None)
        if callable(_f):
            try:
                _d = _f()
                if isinstance(_d, dict):
                    return _d
            except Exception:  # noqa: BLE001
                pass
    try:
        return dict(vars(x))
    except Exception:  # noqa: BLE001
        return {}


def _print_console_domain(r: dict) -> None:
    """`console <域>` 输出 —— 表格/清单（中文宽度对齐; 空就说空, 不编 ✗）。"""
    from apps.cli.textwidth import ljust_display as _lj, truncate_display as _tr

    dom = str(r.get("domain") or "")
    snap = r.get("snapshot") or {}
    title = {"activity": "活动域 · 最近事件流", "projects": "项目域", "agents": "Agent 域",
             "decisions": "决策域", "cost": "成本域", "experience": "经验域"}.get(dom, dom)
    print(f"  {title}（只读 · 与 console dashboard 同一份快照 ✓）")
    print()
    heads: list[str] = []
    rows: list[list[str]] = []
    if dom == "activity":
        heads = ["时间", "事件", "来源", "seq"]
        for _e in (snap.get("activity") or []):
            e = _as_dict(_e)
            _t = str(e.get("type") or "-")
            _t = _t.replace("EventType.", "").lower().replace("_", ".")   # 真字段; 不编"动作/结果" ✗
            rows.append([str(e.get("timestamp") or "-")[:19], _t, str(e.get("source") or "-"),
                         str(e.get("seq") or "-")])
    elif dom == "projects":
        heads = ["ID", "项目", "状态"]
        for _p in (snap.get("projects") or []):
            p = _as_dict(_p)
            rows.append([str(p.get("id") or p.get("project") or "-"),
                         str(p.get("name") or p.get("title") or "-"), str(p.get("status") or "-")])
    elif dom == "agents":
        heads = ["Agent", "状态"]
        for _a in (snap.get("agents") or []):
            a = _as_dict(_a)
            _st = str(a.get("status") or "-").replace("AgentStatus.", "").lower()
            rows.append([str(a.get("id") or a.get("name") or "-"), _st])
    elif dom == "decisions":
        heads = ["决策类型", "摘要"]
        import re as _re

        for _d in (snap.get("decisions") or []):
            s = str(_d)
            _m = _re.search(r"decision_type='([^']+)'", s)
            _summary = _re.sub(r"\s+", " ", _re.sub(r"(id|decision_type)='[^']*'", "", s)).strip(" ,")
            rows.append([(_m.group(1) if _m else "-"), _summary[:60]])
    elif dom == "cost":
        heads = ["项", "值"]
        c = snap.get("cost") or {}
        rows = [["总花费", f"${float(c.get('total_cost') or 0):.6f}"], ["调用数", str(c.get("calls") or 0)]]
    elif dom == "experience":
        heads = ["项", "值"]
        _x = snap.get("experience") or {}
        if isinstance(_x, dict):
            _tt = _x.get("total")
            _sr = _x.get("success_rate")
            rows.append(["经验总数", str(_tt if _tt is not None else "-")])
            rows.append(["成功率", f"{float(_sr):.0%}" if isinstance(_sr, (int, float)) else "-"])
            for _k, _v in (_x.get("by_result") or {}).items():
                rows.append([f"  · {_k}", str(_v)])
        else:
            for i, _one in enumerate(_x or [], 1):
                rows.append([str(i), str(_one)[:60]])
    if not rows:
        print("  （这一域现在没有数据 —— 如实说空, 不编 ✗）")
    else:
        _cols = list(zip(*rows))
        widths = [max(len(h), max((len(_tr(str(x), 40)) for x in col), default=0))
                  for h, col in zip(heads, _cols)]
        print("  " + "  ".join(_lj(h, w) for h, w in zip(heads, widths)))
        print("  " + "  ".join("-" * w for w in widths))
        for row in rows:
            print("  " + "  ".join(_lj(_tr(str(c), 40), w) for c, w in zip(row, widths)))
    if r.get("event_seq"):
        print(f"\n  事件  console.viewed seq={r['event_seq']}")


def _print_kanban(r: dict) -> None:
    for line in r["lines"]:
        print(line)


def _pkg_version() -> str:
    """轻量读版本（update 显示用; 失败 → dev）。与老 CLI 等价。"""
    try:
        import tomllib
        from legacy_paths import REPO_ROOT
        return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    except Exception:  # noqa: BLE001
        return "dev"


def _changelog_lines(ver: str) -> list[str]:
    """update 后变更 list: 从 CHANGELOG.md 读当前版本条目（照老 CLI `_print_changelog_changes`）。"""
    from legacy_paths import REPO_ROOT
    changelog = REPO_ROOT / "CHANGELOG.md"
    if not changelog.is_file():
        return []
    try:
        text = changelog.read_text(encoding="utf-8")
    except OSError:
        return []
    import re
    m = re.search(r"## \[v" + re.escape(ver) + r"\].*?(?=## \[v|\Z)", text, re.S)
    if not m:
        return []
    lines = []
    for line in m.group(0).splitlines():
        s = line.strip()
        if s.startswith("## "):
            continue
        if s.startswith("- ") or s.startswith("**"):
            lines.append(s)
    if not lines:
        return []
    out = [f"  📋 本次变更 (v{ver}):"]
    for line in lines[:12]:
        out.append(f"    {line[:80]}")
    return out


def _dispatch_update(ctx: FactoryContext, args: Any) -> dict:
    """factory update [模块] [--check] —— 整体/模块更新（系统域）。

    与老 CLI `cli_factory.update_cmd`（L8870）逐字一致:
      --check 只读（版本 + git 状态, 区分已跟踪改动 vs 未跟踪文件）
      无参 → git pull --ff-only + pip install -e .  （★ 有副作用, 测试只跑 --check）
      <模块> → 合法集 core/console/exec/org; 单体仓库随整体更新
    """
    import subprocess
    import sys as _sys
    from legacy_paths import REPO_ROOT

    L: list[str] = []

    # ★ 关键: update 操作的对象是【仓库根】(REPO_ROOT), 不是数据根(ctx.root)!
    #   首版误用 ctx.root（~/.factory）⇒ 检查/拉取都对着数据目录, 报"工作区干净"是假的。
    # --check: 只读检查
    if getattr(args, "update_check", False):
        L.append(f"当前版本: {_pkg_version()}")
        try:
            r = subprocess.run(["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
                               capture_output=True, text=True, timeout=15)
            dirty = bool(r.stdout.strip())
            if not dirty:
                L.append("Git 状态: 工作区干净")
            else:
                modified, untracked = [], []
                for line in r.stdout.splitlines():
                    _, _, path = line.partition(" ")
                    path = path.strip()
                    if not path:
                        continue
                    if line.startswith("??"):
                        untracked.append(path)
                    else:
                        modified.append(path)
                L.append(f"Git 状态: 有未提交改动 ({len(modified)} 改 + {len(untracked)} 未跟踪)")
                for path in modified:
                    L.append(f"  M  {path}")
                for path in untracked:
                    L.append(f"  ?? {path}")
                L.append("说明: 未跟踪文件不影响 update (git pull 安全); 已跟踪改动建议先提交")
        except Exception as exc:  # noqa: BLE001
            L.append(f"Git 检查失败: {exc}")
        return {"lines": L}

    module = getattr(args, "update_module", None) or ""
    if module:
        valid = {"core", "console", "exec", "org"}
        if module not in valid:
            return {"lines": [], "errs": [f"未知模块: {module} (可用: {', '.join(sorted(valid))})"],
                    "exit_code": 2}
        L.append(f"⚠️ 更新模块 {module}: 当前为单体仓库（editable 安装）, 模块随整体更新;")
        L.append("   模块独立版本/更新见方案书 §2.4（独立配置与版本管理, 设计预留）")

    L.append("=== factory update ===")
    steps = [("拉取最新代码 (git pull)", "git"),
             ("更新依赖/包 (pip install -e .)", "pip")]
    results: dict[str, str] = {}
    for idx, (label, kind) in enumerate(steps, 1):
        L.append(f"  [{idx}/{len(steps)}] {label} ...")
        try:
            if kind == "git":
                r = subprocess.run(["git", "-C", str(REPO_ROOT), "pull", "--ff-only"],
                                   capture_output=True, text=True, timeout=60)
                if r.returncode == 0:
                    results["git"] = r.stdout.strip() or "已是最新"
                else:
                    results["git_error"] = r.stderr.strip()[:200] or r.stdout.strip()[:200]
            else:
                r = subprocess.run([_sys.executable, "-m", "pip", "install", "-e", "."],
                                   cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120)
                if r.returncode == 0:
                    results["pip"] = "ok"
                else:
                    results["pip_error"] = r.stderr.strip()[:200]
        except Exception as exc:  # noqa: BLE001
            results[f"{kind}_error"] = str(exc)

    L.append(f"  更新完成 — 当前版本: {_pkg_version()}")
    if results.get("git"):
        L.append(f"  📦 代码: {results['git']}")
    if results.get("git_error"):
        L.append(f"  ⚠️ git: {results['git_error']}")
    if results.get("pip"):
        L.append("  📦 依赖/包: 已同步（editable 指向当前仓库）")
    if results.get("pip_error"):
        L.append(f"  ⚠️ pip: {results['pip_error']}")
    L.extend(_changelog_lines(_pkg_version()))
    return {"lines": L}


def _print_update(r: dict) -> None:
    import sys as _sys
    for line in r["lines"]:
        print(line)
    for e in r.get("errs", []):
        print(e, file=_sys.stderr)


def _filter_approvals_by_project(result: dict, project: str, data_dir: Any) -> None:
    """审批列表按项目目录过滤（请求 input.project_dir 匹配; 失败安全空列表）。

    照老 CLI `_filter_approvals_by_project`（L2279）; `exec.store` 经 compat_aliases → 新地基。
    """
    filtered = []
    try:
        from exec.store import ExecStore

        store = ExecStore(Path(data_dir) / "exec")
        target = Path(project).resolve()
        for ap in result.get("approvals", []):
            req = store.get_request(str(ap.get("request_id") or ""))
            proj = ((req.input or {}).get("project_dir", "")) if req is not None else ""
            if proj and Path(proj).resolve() == target:
                filtered.append(ap)
    except Exception:  # noqa: BLE001 — 过滤失败安全 → 空列表
        filtered = []
    result["approvals"] = filtered
    result["count"] = len(filtered)


def _dispatch_approval(ctx: FactoryContext, args: Any) -> dict:
    """factory approval list|decide|apply —— 审批门（复用 ApprovalGate）。

    与老 CLI 行为一致, 但**只走新实现路径**（老 CLI 默认就是这条路; fallback 到老实现
    的那半边随老代码退役, 不在新 CLI 保留）:
      list / decide  → ai_factory_os.services.governance（ApprovalGate / ApprovalStore / decide）
      apply          → exec.cli.cmd_exec_approval_apply（exec 经 compat_aliases → 新地基）
    """
    import argparse as _argparse
    import sys as _sys

    from legacy_paths import REPO_ROOT
    if str(REPO_ROOT) not in _sys.path:
        _sys.path.insert(0, str(REPO_ROOT))
    from ai_factory_os.services.governance import ApprovalGate, ApprovalStore
    from ai_factory_os.services.governance import decide as _decide

    ctx.root.mkdir(parents=True, exist_ok=True)
    cmd = getattr(args, "approval_command", None)
    # ★ 2026-09-15 修: 审批数据在 <root>/governance/approvals.json
    #   （老区 governance_service 落这里, 84 条真实记录也在这里）;
    #   原先写 ctx.root/"exec" ⇒ 读的是不存在的 exec/approvals.json ⇒ list 永远 0 条 ✗
    store = ApprovalStore(ctx.root / "governance")

    if cmd == "list":
        recs = ApprovalGate(store).list(status=getattr(args, "status", None) or None)
        result = {"ok": True, "command": "approval list", "count": len(recs),
                  "approvals": [r.to_dict() for r in recs], "exit_code": 0}
        if getattr(args, "project", None):
            _filter_approvals_by_project(result, args.project, ctx.root)
        return {**result, "args": args}

    if cmd == "decide":
        if not args.approval_id or not args.decision:
            # ★ 与老 CLI 逐字一致: 这处是【直接 stderr + rc 2】, 不经 _print_approval_result
            #   ⇒ 消息里没有 "error: " 前缀, 也不带 [--by]/[--comment] 提示。
            import sys as _s
            print("error: 用法: factory approval decide <id> approve|reject", file=_s.stderr)
            return {"ok": True, "_already_printed": True, "exit_code": 2, "args": args}

        def _on_approved(rec: object) -> None:
            """审计挂点: approve 时发 execution.approved（best-effort）。"""
            try:
                from ai_factory_os.infrastructure.events.logger import EventLogger
                from ai_factory_os.infrastructure.events.store import EventStore
                from exec import events as exec_events
                from exec.store import ExecStore

                ev_store = EventStore(ctx.root / "factory.db")
                try:
                    old_rec = ExecStore(ctx.root / "exec").get_approval(getattr(rec, "id", ""))
                    if old_rec is not None:
                        exec_events.record_execution_approved(EventLogger(ev_store), approval=old_rec)
                finally:
                    ev_store.close()
            except Exception:  # noqa: BLE001 — 事件失败不影响决定落库
                pass

        rec = _decide(store, args.approval_id, args.decision,
                      decided_by=args.by or "cli", comment=args.comment or "",
                      on_approved=_on_approved)
        _cmd = ("approval approve" if str(args.decision).lower() == "approve" else "approval deny")
        return {"result": {"ok": True, "command": _cmd, "approval": rec.to_dict(), "exit_code": 0},
                "args": args}

    if cmd == "apply":
        if not args.approval_id:
            import sys as _s
            print("用法: factory approval apply <id> [--project <dir>]", file=_s.stderr)
            return {"ok": True, "_already_printed": True, "exit_code": 2, "args": args}
        try:
            import exec.cli as exec_cli
            sub_args = _argparse.Namespace(id=args.approval_id, project=getattr(args, "project", None))
            result = exec_cli.cmd_exec_approval_apply(root=ctx.root, args=sub_args)
        except Exception as exc:  # noqa: BLE001 — 失败安全 → 明确错误
            return {"ok": False, "exit_code": 1,
                "error": f"审批命令失败 — {exc}", "args": args}
        return {**result, "args": args}

    return {"ok": False, "exit_code": 1, "error": f"未知动作: {cmd}", "args": args}


def _print_approval(r: dict) -> None:
    """照老 CLI `_print_approval_result`（L2298）逐字实现。"""
    import sys as _sys

    result, args = r, r.get("args")
    if result.get("_already_printed"):        # 用法错误已直接打 stderr（与老 CLI 一致）
        return
    if not result.get("ok"):
        print(f"error: {result.get('error')}", file=_sys.stderr)
        return
    if result.get("command") == "approval list":
        print(f"审批记录 {result.get('count', 0)} 条 (status={getattr(args, 'status', 'pending')})")
        for ap in result.get("approvals", []):
            bundle = ap.get("bundle_id") or ""
            print(f"  {ap['id']}  {ap['decision']:<10} {ap['request_id']}  "
                  f"risk={ap.get('risk_level', 'low')}  by {ap.get('decided_by', '')}"
                  + (f"  证据包 {bundle}" if bundle else ""))
    elif result.get("command") in ("approval approve", "approval deny"):
        ap = result["approval"]
        print(f"审批 {ap['decision']}: {ap['id']}")
        print(f"  request_id  {ap['request_id']}")
        print(f"  decided_by  {ap['decided_by']}")
        if ap.get("comment"):
            print(f"  comment     {ap['comment']}")
        if result.get("command") == "approval approve":
            print(f"已批准。下一步: factory approval apply {ap['id']} --project <repo> 可应用")
    elif result.get("command") == "approval apply":
        ap = result["approval"]
        print(f"✔ patch 已应用: {ap['id']} (diff {result.get('patch_lines', 0)} 行)")
    if result.get("event_seq") is not None:
        print(f"  event_seq   {result['event_seq']}")


def _dispatch_plugin(ctx: FactoryContext, args: Any) -> dict:
    """factory plugin —— Plugin 内核（S31）: list/inspect/enable/disable/status/health/resolve。

    与老 CLI `cli_factory.plugin_cmd`（L9830）**逐字一致**（含 [E416x] 错误码）;
    底层走**新地基** `infrastructure/plugins/kernel`。
    返回结构: {lines: [...], errs: [...], exit_code: N} —— print 阶段分流出 stdout/stderr。
    """
    from ai_factory_os.infrastructure.plugins.kernel import (
        get_plugin as _get, list_plugins as _list, plugin_health as _health,
        plugin_status as _status, resolve_plugin as _resolve,
    )

    root = str(ctx.root)
    action = getattr(args, "action", "list") or "list"
    target = getattr(args, "target", None)
    out, err, code = [], [], 0

    # ★ 放下即用（产品定义第 3 条）: list/status 前先扫投放目录 —— 丢个清单进去就能看到
    if action in ("list", "status"):
        from ai_factory_os.infrastructure.plugins.kernel import scan_manifests as _scan

        _sc = _scan(root)
        for e in _sc.get("errors") or []:
            err.append(f"[E4160] 插件清单有问题: {e}")
            code = code or 1
        if _sc.get("registered"):
            out.append(f"  （扫描投放目录: 新注册 {len(_sc['registered'])} 个 "
                       f"{', '.join(_sc['registered'])}）")
    if action == "list":
        for x in _list(root):
            out.append(f"  {x['plugin_id']} | {x['type']} | {x['status']} | caps: {x['capabilities']}")
        return {"lines": out, "errs": err, "exit_code": code}

    if action == "inspect":
        if not target:
            err.append("[E4160] 错误: plugin_id 必填 (factory plugin inspect <id>)")
            code = 2
        else:
            x = _get(root, target)
            if x is None:
                err.append(f"[E4161] Plugin 不存在: {target}")
                code = 1
            else:
                out.append(f"plugin: {x['plugin_id']} | {x['name']} v{x['version']} | "
                           f"{x['type']} | {x['vendor']}")
                out.append(f"  caps: {x['capabilities']} | deps: {x['dependencies']} | "
                           f"perms: {x['permissions']}")
                out.append(f"  status: {x['status']} | history: {len(x['history'])}")
        return {"lines": out, "errs": err, "exit_code": code}

    if action in ("enable", "disable"):
        want = "ENABLED" if action == "enable" else "DISABLED"
        ecode = "[E4162] 错误: plugin_id 必填 (factory plugin enable <id>)" if action == "enable" \
            else "[E4164] 错误: plugin_id 必填 (factory plugin disable <id>)"
        xcode = "[E4163] 错误" if action == "enable" else "[E4165] 错误"
        if not target:
            err.append(ecode)
            code = 2
        else:
            try:
                x = _status(root, target, target=want)
                out.append(f"plugin: {target} | status: {x['status']}")
            except Exception as exc:  # noqa: BLE001
                err.append(f"{xcode}: {exc}")
                code = 1
        return {"lines": out, "errs": err, "exit_code": code}

    if action == "status":
        if not target:
            err.append("[E4166] 错误: plugin_id 必填 (factory plugin status <id>)")
            code = 2
        else:
            x = _get(root, target)
            if x is None:
                err.append(f"[E4167] Plugin 不存在: {target}")
                code = 1
            else:
                out.append(f"plugin: {target} | status: {x['status']}")
        return {"lines": out, "errs": err, "exit_code": code}

    if action == "health":
        if not target:
            err.append("[E4168] 错误: plugin_id 必填 (factory plugin health <id>)")
            code = 2
        else:
            try:
                h = _health(root, target)
                out.append(f"plugin: {target} | health: {h['health']} | "
                           f"deps_ok: {h['dependencies_ok']}")
            except Exception as exc:  # noqa: BLE001
                err.append(f"[E4169] 错误: {exc}")
                code = 1
        return {"lines": out, "errs": err, "exit_code": code}

    if action == "resolve":
        res = _resolve(root, required_capability=target or "")
        out.append(f"resolve: {res.get('resolved')} | {res.get('plugin_id', '')} | "
                   f"{res.get('reason', '')}")
        return {"lines": out, "errs": err, "exit_code": code}

    return {"lines": out, "errs": err, "exit_code": 1}


def _print_plugin(r: dict) -> None:
    for line in r["lines"]:
        print(line)
    import sys as _sys
    for e in r["errs"]:
        print(e, file=_sys.stderr)


def _dispatch_create(ctx: FactoryContext, args: Any) -> dict:
    """factory create <type> —— 统一创建入口（company / department / project）。

    与老 CLI `cli_factory.create_cmd`（L8600）行为一致:
      · company    → org.cli.cmd_company_create
      · department → 需 --company（缺 → rc 2）; 转 args.company_id 后 cmd_department_create
      · project    → 需 --name（缺 → rc 2 [E4003]）; repo_path 缺省 = 数据根; cmd_project_register
    """
    ctype = getattr(args, "create_type", "") or ""
    ctx.root.mkdir(parents=True, exist_ok=True)
    try:
        from ai_factory_os.services.organization import cli as org_cli
    except Exception as exc:  # noqa: BLE001
        raise CliError(f"错误: {exc}", exit_code=1) from exc

    try:
        if ctype == "company":
            result = org_cli.cmd_company_create(ctx.root, args)
        elif ctype == "department":
            if not getattr(args, "company", ""):
                raise CliError("错误: department 需要 --company <id>", exit_code=2)
            args.company_id = getattr(args, "company", "")  # 对齐 cmd_department_create
            result = org_cli.cmd_department_create(ctx.root, args)
        elif ctype == "project":
            # S10-103: create project 必须显式 --name（不落默认名）
            if not getattr(args, "project_name", None) and not getattr(args, "name", None):
                raise CliError("[E4003] 错误: create project 需要 --name <项目名> "
                               "(建议: 显式传入 --name 后重试)", exit_code=2)
            if not getattr(args, "repo_path", None):
                args.repo_path = str(ctx.root)   # 无 repo → 默认数据目录（对话/快捷场景）
            result = org_cli.cmd_project_register(ctx.root, args)
        else:
            raise CliError(f"错误: create 需要类型 (company/department/project), 收到: {ctype!r}",
                           exit_code=2)
    except CliError:
        raise
    except Exception as exc:  # noqa: BLE001 — 失败安全
        raise CliError(f"错误: create {ctype} 失败 — {exc}", exit_code=1) from exc
    # ★ 退出码必须随 result 传回（main 末尾用 result["exit_code"] 决定进程退出码）——
    #   否则业务失败（如 company already exists）会以 rc=0 静默成功, 与老 CLI 不一致。
    # ★★ 2026-09-20 修: 原来这里塞了 `"proxy": org_cli`（module 对象）⇒ 顶层 `--json` 序列化
    #   整个返回字典时炸（`TypeError: Object of type module is not JSON serializable`, 实测踩到）。
    #   ⇒ 返回值必须 **JSON 安全**; 打印方自己 import 那个 module（见 _print_create）。
    return {"action": "create", "create_type": ctype, "args": args, "result": result,
            "exit_code": int(result.get("exit_code", 0) or 0)}


def _print_create(r: dict) -> None:
    """照老 CLI `_emit_proxy_result`: --json → JSON; 否则交给底层 proxy 的 _print_result。

    ★ 2026-09-20 修两处（实测踩到）:
      · 下层 `_print_result` 按 `args.command` 分支, 而这里 command="create" ⇒ **project 一个分支都没有**
        ⇒ 建成后【一个字都不打】= 静默成功, 用户以为失败（我自己就误判成"空转"）⇒ 这里补兜底输出。
      · 返回值不再带 module（见 _dispatch_create）⇒ `--json` 不再崩。
    """
    from ai_factory_os.services.organization import cli as org_cli

    args, result = r["args"], r["result"]
    if getattr(args, "json", False) and result.get("ok"):
        import json as _json
        print(_json.dumps(result, ensure_ascii=False, indent=2))
        return
    if int(result.get("exit_code", 0)) == 2:
        return
    org_cli._print_result(args, result)
    # ★ 兜底: 下层没有这个 type 的打印分支时, 保证"建成了"看得见（禁静默）
    # ★ 2026-09-22（Founder 点单: "factory create company 成功零输出"）:
    #   company / department 也没打印分支 ⇒ 实测**真建好了却一个字不打**（静默成功 ✗）。补上 ✓
    if result.get("ok") and str(r.get("create_type") or "") == "company":
        c = dict(result.get("company") or {})
        print(f"✔ 公司已创建: {c.get('name') or c.get('id')}  ({c.get('id')})")
        print(f"  部门      {result.get('department_count', 0)} 个")
        # ★ 2026-09-23 撤掉（Founder: 「我们没有设计招人这个功能呢啊」）:
        #   原来这里写「下一步: … factory org employee list」是**我自己编的** ✗ ——
        #   "招人"是老区（src/legacy/factory-org）的命令面, 不在产品设计内
        #   （SSoT product.md: Idea → 目标表达 → 理解 → **编排** → 执行 → … ⇒ 没有"招人"这一步）。
        #   ⇒ 不发明下一步 ✓ 只如实给回执。
        return
    if result.get("ok") and str(r.get("create_type") or "") == "department":
        d = dict(result.get("department") or {})
        print(f"✔ 部门已创建: {d.get('name') or d.get('id')}  ({d.get('id')})")
        return
    if result.get("ok") and str(r.get("create_type") or "") == "project":
        p = dict(result.get("project") or {})
        print(f"✔ 项目已创建: {p.get('name') or p.get('id')}  ({p.get('id')})")
        print(f"  仓库      {p.get('repo_path') or '-'}")
        print(f"  语言/框架 {p.get('language') or '-'} / {p.get('framework') or '-'}")
        print(f"  下一步: factory conversation new --project {p.get('id')}  "
              f"（或 `factory project adopt <仓库>` 把已有仓库挂上来）")


def _dispatch_history(ctx: FactoryContext, args: Any) -> dict:
    """factory history search|index|stats —— 历史检索（底层已在新地基: services/learning/history_search）。

    与老 CLI `cli_factory.history_cmd`（L9044）行为一致。
    """
    from ai_factory_os.services.learning.history_search import HistoryIndex

    action = getattr(args, "history_action", "search") or "search"
    idx = HistoryIndex(ctx.root / "search.db")
    try:
        if action == "index":
            counts = idx.sync_from_data_dir(ctx.root)
            return {"action": "index", "counts": counts}
        if action == "stats":
            return {"action": "stats", "stats": idx.stats()}
        query = (getattr(args, "history_query", "") or "").strip()
        if not query:
            # 与老 CLI 逐字一致: 消息自带"错误: "前缀（该命令的风格）
            raise CliError("错误: history search 需要检索词", exit_code=2)
        if not idx.stats().get("total"):
            idx.sync_from_data_dir(ctx.root)
        src_raw = (getattr(args, "source", "") or "").strip()
        sources = tuple(s.strip() for s in src_raw.split(",") if s.strip()) or None
        hits = idx.search(query, limit=max(1, int(getattr(args, "limit", 8) or 8)), sources=sources)
        return {"action": "search", "query": query, "hits": hits,
                "indexed": idx.stats().get("total", 0)}
    finally:
        idx.close()


def _print_history(sub: str, r: dict) -> None:
    if sub == "index":
        counts = r["counts"]
        print("  ✓ 已索引 " + str(sum(counts.values())) + " 条: "
              + " · ".join(f"{k}={v}" for k, v in counts.items()))
        return
    if sub == "stats":
        st = r["stats"]
        print("=== 历史索引 ===")
        for s in ("event", "trace", "experience", "message"):
            print(f"  {s:12s} {st.get(s, 0):6d} 条")
        print(f"  {'合计':12s} {st.get('total', 0):6d} 条")
        return
    hits = r["hits"]
    if not hits:
        print(f"未找到与「{r['query']}」相关的历史（索引 {r['indexed']} 条）")
        return
    print(f"=== 「{r['query']}」找到 {len(hits)} 条 ===")
    for h in hits:
        title = getattr(h, "title", "") or ""
        print(f"  [{h.source}] {h.ts[:19].replace('T', ' ') or '—'}  {title[:56]}")
        print(f"    {h.snippet[:170]}")


# ------------------------------------------------------------------ 架构域（arch）

def _arch_store(ctx: FactoryContext) -> Any:
    """组织域 ProjectStore（artifact 的家）—— 架构设计产物存在这里。"""
    from ai_factory_os.services.organization.projects import ProjectStore
    return ProjectStore(ctx.root / "org")


def _arch_provider() -> Any:
    """技术设计 LLM provider（复用 exec 内核的装配: ControlPlane → Adapter）。

    ★ 取的是注册表里的 **Adapter**（ProviderInterface, 有 generate）；
      kernel 的 `_provider_registry()` 返回的是注册表本身 —— 别直接当 provider 用。
    """
    from ai_factory_os.services.execution.kernel.cli import _provider_registry
    provs = _provider_registry().list()
    if not provs:
        raise CliError("无可用 LLM provider（先 factory provider 配置 + 设 key）", exit_code=1)
    return provs[0]


def _dispatch_arch(ctx: FactoryContext, args: Any) -> dict:
    """factory arch list|show|design|gates —— 8 环第 4 环「架构设计」。

    复用（不自造）:
      · ArtifactRegistry / ProjectStore —— 产物读写与 CONTRACTS 校验（organization 域）
      · ArchitectAgent + build_arch_executor —— Product + UX/UI → Design Artifact 7 节
        （plugins/agents/architect.py; 老区 workflow_runner 的 arch_run 同源实现）
    """
    from ai_factory_os.services.organization.projects import Artifact, ArtifactType

    cmd = getattr(args, "arch_command", None) or "list"
    store = _arch_store(ctx)

    if cmd == "list":
        proj = getattr(args, "project", None)
        rows = []
        for a in store.list_artifacts():
            if str(a.type) not in ("design", "ArtifactType.DESIGN", "design_artifact"):
                if "design" not in str(a.type).lower():
                    continue
            if proj and getattr(a, "project_id", "") != proj:
                continue
            rows.append({"id": a.id, "stage": a.stage_id, "project": a.project_id,
                         "status": str(a.status), "version": a.version,
                         "sections": len(getattr(a, "metadata", {}) or {}),
                         "ref": a.ref})
        return {"ok": True, "command": "arch list", "count": len(rows),
                "designs": rows, "exit_code": 0, "args": args}

    if cmd == "show":
        aid = getattr(args, "artifact_id", None)
        if not aid:
            raise CliError("用法: factory arch show <artifact_id>", exit_code=2)
        art = store.get_artifact(aid)
        if art is None:
            raise CliError(f"artifact not found: {aid}", exit_code=7)
        meta = dict(getattr(art, "metadata", {}) or {})
        # design 契约的 7 节（顺序固定, 缺节如实标注）
        SECTIONS = ("system_architecture", "technical_stack", "database_design", "api_design",
                    "frontend_architecture", "backend_architecture", "task_breakdown")
        return {"ok": True, "command": "arch show",
                "artifact": {"id": art.id, "type": str(art.type), "stage": art.stage_id,
                             "project": art.project_id, "status": str(art.status),
                             "version": art.version, "ref": art.ref,
                             "producer_role": getattr(art, "producer_role", ""),
                             "producer_agent": getattr(art, "producer_agent", "")},
                "sections": {s: ("✓" if meta.get(s) else "缺失") for s in SECTIONS},
                "artifact_refs": meta.get("artifact_refs", []),
                "exit_code": 0, "args": args}

    if cmd == "gates":
        from ai_factory_os.services.governance.gates import POLICIES
        # ★ 诚实: POLICIES 里【没有】architecture 这个 key —— 架构设计不是独立门,
        #   它走 release 门（required_evaluation=True 那条）。如实标注, 不假装有。
        own = POLICIES.get("architecture")
        return {"ok": True, "command": "arch gates",
                "is_own_gate": own is not None,
                "policy": own or POLICIES.get("release"),
                "policy_id": "architecture" if own else "release（架构无独立门, 借 release）",
                "all_policies": sorted(POLICIES.keys()),
                "exit_code": 0, "args": args}

    if cmd == "design":
        proj = getattr(args, "project", None)
        if not proj:
            raise CliError("用法: factory arch design --project <项目 id> (需先有 product + ux_ui 产物)",
                           exit_code=2)
        arts = [a for a in store.list_artifacts()
                if getattr(a, "project_id", "") == proj]
        def _pick(type_name: str, explicit: str | None) -> Any:
            if explicit:
                a = store.get_artifact(explicit)
                if a is None:
                    raise CliError(f"{type_name} artifact not found: {explicit}", exit_code=7)
                return a
            cands = [a for a in arts if type_name in str(a.type).lower()]
            return cands[-1] if cands else None
        product = _pick("product", getattr(args, "product", None))
        ux_ui = _pick("ux_ui", getattr(args, "ux_ui", None))
        if product is None or ux_ui is None:
            raise CliError(
                f"架构设计需双输入: product={'✓' if product else '✗'} ux_ui={'✓' if ux_ui else '✗'}"
                " — 禁止脱离输入独立生成 (ArchitectAgent 强校验)", exit_code=1)
        from ai_factory_os.plugins.agents.architect import ArchitectAgent, ArchitectError
        try:
            agent = ArchitectAgent(provider=_arch_provider(),
                                   product=dict(product.metadata or {}),
                                   ux_ui=dict(ux_ui.metadata or {}))
            design = agent.design()
        except ArchitectError as exc:
            raise CliError(f"架构设计失败: {exc}", exit_code=1) from exc
        meta = design.to_dict() if hasattr(design, "to_dict") else dict(design)
        meta["artifact_refs"] = [product.id, ux_ui.id]   # 溯源（照 build_arch_executor）
        from ai_factory_os.infrastructure.ids import new_id
        new = Artifact(id=new_id("A"), stage_id="", type=ArtifactType.DESIGN,
                       ref="file:///docs/design.json", project_id=proj,
                       producer_role="software_architect", producer_agent="architect",
                       metadata=meta)
        store.save_artifact(new)
        return {"ok": True, "command": "arch design",
                "artifact": {"id": getattr(new, "id", ""), "type": "design"},
                "artifact_refs": meta["artifact_refs"],
                "sections": sorted(k for k in meta if k != "artifact_refs"),
                "exit_code": 0, "args": args}

    raise CliError(f"unknown arch action: {cmd}", exit_code=2)


def _print_arch(args: Any, r: dict) -> None:
    cmd = getattr(args, "arch_command", None) or "list"
    if cmd == "list":
        rows = r.get("designs", [])
        print(f"=== Design Artifact ({len(rows)}) ===")
        for x in rows:
            print(f"  {x['id']}  {x['status']:<10}  v{x['version']}  {x['sections']} 节  "
                  f"project={x['project'] or '-'}  {x['ref']}")
        if not rows:
            print("  （无 — 用 `factory arch design --project <id>` 生成）")
    elif cmd == "show":
        a = r["artifact"]
        print(f"Design Artifact: {a['id']}")
        print(f"  type={a['type']} status={a['status']} version={a['version']}")
        print(f"  project={a['project'] or '-'} stage={a['stage'] or '-'}")
        print(f"  producer_role={a['producer_role'] or '-'} agent={a['producer_agent'] or '-'}")
        print(f"  ref={a['ref']}")
        print(f"  溯源 artifact_refs: {r.get('artifact_refs') or '（无）'}")
        print("  7 节:")
        for k, v in r.get("sections", {}).items():
            print(f"    {k:<24} {v}")
    elif cmd == "gates":
        print("=== 架构门策略 ===")
        if not r.get("is_own_gate"):
            print("  ⚠ 架构设计【没有独立门】—— 它走 release 门（POLICIES 无 architecture key）")
        print(f"  策略来源: {r.get('policy_id')}")
        print(f"  策略内容: {r.get('policy')}")
        print(f"  全部策略: {', '.join(r.get('all_policies', []))}")
    elif cmd == "design":
        a = r["artifact"]
        print(f"✔ Design Artifact 已生成: {a['id']}")
        print(f"  溯源: {r.get('artifact_refs')}")
        print(f"  节: {', '.join(r.get('sections', []))}")


# ------------------------------------------------------------------ 产品阶段执行链（环④ 的前置）

def _prod_provider() -> Any:
    """产品分析用的 LLM provider（复用 exec 内核的装配: ControlPlane → Adapter）。

    PMAgent / UXUIDesignerAgent 要的是 `ProviderInterface.generate(ProviderRequest)`,
    与新地基 kernel/providers 的 OpenAIProvider/AnthropicProvider 一致 ⇒ 直接复用。
    """
    from ai_factory_os.services.execution.kernel.cli import _provider_registry
    reg = _provider_registry()
    provs = reg.list()
    if not provs:
        raise CliError("无可用 LLM provider（先 factory provider 配置 + 设 key）", exit_code=1)
    return provs[0]


def _iter_facts(conv: dict) -> list[dict]:
    """★ 会话里的事实 —— 兼容两种存法（只认一种 = 就是下面那个 bug）。

      · 现网: `conv["understanding"]["facts"]`（dict: 事实 id → 事实）
      · 兼容: `conv["facts"]`（list）
    ★ 跳过非活动态（SUPERSEDED/REJECTED）—— 被推翻的想法不能当依据。
    """
    out: list[dict] = []
    und = conv.get("understanding")
    nested = und.get("facts") if isinstance(und, dict) else None
    if isinstance(nested, dict):
        out.extend(x for x in nested.values() if isinstance(x, dict))
    elif isinstance(nested, list):
        out.extend(x for x in nested if isinstance(x, dict))
    legacy = conv.get("facts")
    if isinstance(legacy, list):
        out.extend(x for x in legacy if isinstance(x, dict))
    active = ("SUPERSEDED", "REJECTED")
    return [f for f in out if str(f.get("status") or "").upper() not in active]


def _prod_idea_text(ctx: FactoryContext, project_id: str, explicit: str | None) -> str:
    """想法文本: 显式 --idea > 项目 PRD 的 overview > 会话里的 IDEA 事实（诚实缺口 → 报错）。

    ★ 实测踩到（全链路实跑）: 这段原来读 `conv["facts"]`（顶层 list）——
      而事实实际存在 `conv["understanding"]["facts"]`（嵌套 dict）⇒ **永远取不到**,
      `product develop` 不带 --idea 必报"无想法文本"（chain.py 里那句注释就是当年绕过去的痕迹）。
    """
    if explicit:
        return str(explicit)
    from ai_factory_os.services.organization.projects import ProjectStore
    store = ProjectStore(ctx.root / "org")
    # 1) 项目里已有的 prd 产物（org）或 product_truth 的 PRD
    for a in store.list_artifacts():
        if getattr(a, "project_id", "") == project_id and "prd" in str(a.type).lower():
            meta = dict(getattr(a, "metadata", {}) or {})
            for k in ("overview", "problem_statement", "title"):
                if meta.get(k):
                    return str(meta[k])
    # 2) 会话事实里的 IDEA（★ 走 _iter_facts: 两种存法都认）
    conv_dir = ctx.root / "projects" / project_id / "conversations"
    if conv_dir.is_dir():
        import json as _json
        for f in sorted(conv_dir.glob("*.json")):
            try:
                d = _json.loads(f.read_text())
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(d, dict):
                continue
            for fact in _iter_facts(d):
                if str(fact.get("type") or "").upper() == "IDEA" and fact.get("content"):
                    return str(fact["content"])
    raise CliError(
        "无想法文本 —— 传 --idea, 或先 conversation understand 产出 IDEA 事实", exit_code=2)


def cmd_product_develop(ctx: FactoryContext, args: Any) -> dict:
    """factory product develop --project P [--idea TEXT] — PM Agent 产出 Product Artifact(7 节)。

    复用 plugins/agents/pm.py 的 PMAgent（老区 workflow_runner 同源实现）；
    产物注册到组织域（ProjectStore.artifacts）type=product ⇒ 供 `arch design` 作双输入。
    """
    from ai_factory_os.plugins.agents.pm import PMAgent, ProductManagerError
    from ai_factory_os.services.organization.projects import Artifact, ArtifactType, ProjectStore

    project_id = str(args.project)
    idea = _prod_idea_text(ctx, project_id, getattr(args, "idea", None))
    try:
        agent = PMAgent(provider=_prod_provider(), idea=idea)
        art = agent.develop()
    except ProductManagerError as exc:
        raise CliError(f"产品分析失败: {exc}", exit_code=1) from exc
    meta = art.to_dict()
    # ★ 2026-09-21 需求 → PRD 的门（Founder 选 B: "防它自己加需求"）:
    #   每条特性必须**逐字引用**需求原话里的片段（≥6 字, 可核对）; 引不出的 = 模型自己加的功能 ⇒
    #   移出 feature_list, 进 out_of_scope_suggestions 另列给人看（不做）。
    #   实测病: PRD 制品里就已经有 登录/通知/补课/爽约（用户没要过）⇒ 下游被放大到 42/199 个任务。
    try:
        from ai_factory_os.plugins.agents.pm import enforce_requirement_traces
        from ai_factory_os.services.work.decomposition import prd_text as _req_text

        # ★ 2026-09-21 修（Founder 实测的重大误杀 ✗✗）: 门必须用 **agent 用的那份需求**
        #   （idea —— 可能是命令行给的 `factory chain "<需求>"`）; 以前门自己从会话里另取一份 ⇒
        #   取到空 ⇒ 把真需求（扫码借还/查馆藏/逾期提醒…）全当"凭空发明"移出 21 条 ✗。会话那份只作兜底。
        _req_for_gate = str(idea or "").strip() or _req_text(ctx.root, {"project_id": project_id})
        _gate = enforce_requirement_traces(meta, _req_for_gate)
        if _gate.get("skipped"):
            print(f"  ⚠ 需求→PRD 门: {_gate.get('why') or '本次没比对'}")
        _moved = list(_gate.get("moved") or [])
        if _moved:
            print(f"  ⚠ 需求→PRD 门: 移出 {len(_moved)} 条【你需求里找不到依据的】"
                  f"（已另列 out_of_scope_suggestions, 不做）:")
            for _m in _moved[:10]:
                print(f"      - [{str(_m.get('section'))}] {str(_m.get('item'))[:44]} —— {str(_m.get('why'))[:34]}")
            if len(_moved) > 10:
                print(f"      … 还有 {len(_moved) - 10} 条")
        elif _gate.get("checked"):
            print(f"  ✓ 需求→PRD 门: {_gate['kept']}/{_gate['checked']} 条都能对回你的需求原话"
                  + ("（含自动补的出处）" if _gate.get("skipped") else ""))
        for _f in (_gate.get("flagged") or [])[:10]:
            print(f"      ? [{str(_f.get('section'))}] {str(_f.get('item'))[:46]}  "
                  f"（与需求原话共同文字仅 {_f.get('overlap')} 字）")
    except Exception as _exc:  # noqa: BLE001 — 门本身出问题不许挡产出（但要说出来）
        print(f"  ⚠ 需求→PRD 门没跑成: {type(_exc).__name__}: {str(_exc)[:80]}")
    store = ProjectStore(ctx.root / "org")
    from ai_factory_os.infrastructure.ids import new_id
    rec = Artifact(id=new_id("A"), stage_id="", type=ArtifactType.PRODUCT,
                   ref="file:///docs/product.json", project_id=project_id,
                   producer_role="product_manager", producer_agent="pm", metadata=meta)
    store.save_artifact(rec)
    return {"ok": True, "command": "product develop",
            "artifact": {"id": getattr(rec, "id", ""), "type": "product"},
            "sections": sorted(meta.keys()), "idea": idea[:120],
            "exit_code": 0, "args": args}



def cmd_product_breakdown(ctx: FactoryContext, args: Any) -> dict:
    """`factory product breakdown --project P` —— ★ 需求拆解（业务模块拆分）。

    Founder 说的"两层拆解"的**业务层**:
      · 本命令: 业务视角 —— 需求由哪些业务模块组成（「商品管理/订单/支付」）人话粒度
      · tasktree: 执行视角 —— 具体做哪些活（「编写 Prisma schema 与迁移」）
    ⇒ 业务层是**给人看的**（喂给功能链路图）; 执行层是给 agent 做的。
    """
    from ai_factory_os.services.organization.projects import (
        Artifact, ArtifactType, ProjectStore,
    )
    from ai_factory_os.services.work.business_breakdown import breakdown


    project_id = str(args.project)
    # ★ PRD 实际存在 product_truth 域（不是 org/artifacts.json —— 实测踩到过）。
    pf = ctx.root / "projects" / project_id / "product_truth" / "prds.json"
    if not pf.is_file():
        raise CliError(
            f"项目 {project_id} 内无 PRD（{pf}）—— 先跑 `factory conversation prd`"
            "（需求拆解需要 PRD 作输入）",
            exit_code=2)
    prds = json.loads(pf.read_text(encoding="utf-8")) or {}
    prd = list(prds.values())[-1] if isinstance(prds, dict) else prds[-1]
    prd_text = json.dumps(prd, ensure_ascii=False)
    mods = breakdown(prd_text, provider=_prod_provider())
    store = ProjectStore(ctx.root / "org")       # 产物注册用

    from ai_factory_os.infrastructure.ids import new_id
    rec = Artifact(id=new_id("A"), stage_id="", type=ArtifactType.PRODUCT,
                   ref="file:///docs/business_breakdown.json", project_id=project_id,
                   producer_role="product_manager", producer_agent="pm",
                   metadata={"business_modules": mods})
    store.save_artifact(rec)
    return {"ok": True, "command": "product breakdown",
            "artifact": {"id": getattr(rec, "id", ""), "type": "business_breakdown"},
            "modules": mods, "count": len(mods)}

def cmd_product_ux(ctx: FactoryContext, args: Any) -> dict:
    """factory product ux --project P — UX/UI Agent 产出 UX/UI Artifact(7 节)。

    输入 = 项目里的 product 产物（`product develop` 的产出）; 产物 type=ux_ui。
    """
    from ai_factory_os.plugins.agents.uxui import UXUIDesignerAgent, UXUIDesignerError
    from ai_factory_os.services.organization.projects import Artifact, ArtifactType, ProjectStore

    project_id = str(args.project)
    store = ProjectStore(ctx.root / "org")
    explicit = getattr(args, "product", None)
    if explicit:
        src = store.get_artifact(str(explicit))
        if src is None:
            raise CliError(f"product artifact not found: {explicit}", exit_code=7)
    else:
        cands = [a for a in store.list_artifacts()
                 if getattr(a, "project_id", "") == project_id and "product" in str(a.type).lower()]
        if not cands:
            raise CliError(
                "项目内无 product 产物 —— 先跑 factory product develop --project "
                f"{project_id}（UX 需要 product 作输入）", exit_code=2)
        src = cands[-1]
    try:
        agent = UXUIDesignerAgent(provider=_prod_provider(), product=dict(src.metadata or {}))
        art = agent.design()
    except UXUIDesignerError as exc:
        raise CliError(f"UX/UI 设计失败: {exc}", exit_code=1) from exc
    meta = art.to_dict()
    from ai_factory_os.infrastructure.ids import new_id
    rec = Artifact(id=new_id("A"), stage_id="", type=ArtifactType.UX_UI,
                   ref="file:///docs/ux_ui.json", project_id=project_id,
                   producer_role="ui_designer", producer_agent="uxui", metadata=meta)
    store.save_artifact(rec)
    return {"ok": True, "command": "product ux",
            "artifact": {"id": getattr(rec, "id", ""), "type": "ux_ui"},
            "input_product": getattr(src, "id", ""),
            "sections": sorted(meta.keys()),
            "exit_code": 0, "args": args}


# ------------------------------------------------------------------ 任务拆解（产品环 ⑤）


def _tasktree_todo(ctx: FactoryContext, args: Any) -> dict:
    """`factory tasktree todo <plan>` —— ★ 用户视图（层级待办清单）。

    与 `show` 同源（同一个树文件, 同一份数据）, 只是**换了读法** ——
    这正是 Founder 定的"两种呈现说的是同一件事":
      · show: 专业视角（role/change/files/依赖数）—— 给做的人看
      · todo: 人话视角（人话名/状态/谁在做 + 进度）—— 给普通人看
    ⇒ 同一份数据, 两个投影 ⇒ 不会不一致。
    """
    from ai_factory_os.services.work import decomposition as _D
    from ai_factory_os.services.work import user_view as _UV

    plan_id = _resolve_plan_id(ctx, str(getattr(args, "plan_id", "") or ""))
    project = str(getattr(args, "project", "") or "")
    tree = _D.load_tree(ctx.root, plan_id, project) if project else _D.load_tree(ctx.root, plan_id)
    if not tree:
        raise _plan_not_found(plan_id)
    nodes = tree.get("nodes") or []
    leaves = [n for n in nodes if n.get("kind") == "task"]
    done = sum(1 for n in leaves if str(n.get("status") or "").lower() in ("completed", "done", "accepted"))
    total = len(leaves) or 1
    return {
        "ok": True, "action": "tasktree-todo", "tree": tree,
        "summary": {
            "kinds": {},
            "leaves": len(leaves),
            "done": done,
            "percent": f"{done * 100 // total}",
        },
        # ★ 视图数据仍由服务层给（CLI 只排版）—— 关键路径标注就在里面
        "todo": _UV.build_todo(tree),
    }


def _tasktree_flow(ctx: FactoryContext, args: Any) -> dict:
    """`factory tasktree flow <plan>` —— ★ 用户视图之二（功能链路图: 看关系）。

    与 `todo` 的分工（Founder: "两种呈现, 说的是同一件事"）:
      · todo: 看【要做啥、到哪了】—— 层级待办清单
      · flow: 看【有什么功能、怎么串起来】—— 功能链路图
    ★ 同源: 同一个树文件、同一份数据 —— flow 只是按 depends_on/parent_id 换一种看法。

    ★ 视图数据的构造归服务层（`user_view.build_flow`）—— CLI 只负责排版。
      （此前 CLI 自己又写了一份 Kahn 分层, 与 API 各一套 ⇒ R25 重复造轮子; 已收口。）
    """
    from ai_factory_os.services.work import decomposition as _D
    from ai_factory_os.services.work import user_view as _UV

    plan_id = str(getattr(args, "plan_id", "") or "")
    project = str(getattr(args, "project", "") or "")
    tree = _D.load_tree(ctx.root, plan_id, project) if project else _D.load_tree(ctx.root, plan_id)
    if not tree:
        raise _plan_not_found(plan_id)
    return {"ok": True, "action": "tasktree-flow", "tree": tree, "flow": _UV.build_flow(tree)}


def _tasktree_dataflow(ctx: FactoryContext, args: Any) -> dict:
    """`factory tasktree dataflow <plan>` —— ★ 投影 C（数据流程图: 看数据）。

    与页面/API **同源**: 都调 `services/work/data_flow.build_data_flow`
    （视图数据只有服务层一个来源 —— 别在 CLI 里另写一套）。
    ★ 数据来源必须真实（DDL / 产线声明）, 文案匹配只作线索 —— 见 data_flow.py 头部。
    """
    from pathlib import Path as _Path

    from ai_factory_os.services.work import data_flow as _DF
    from ai_factory_os.services.work import decomposition as _D

    plan_id = str(getattr(args, "plan_id", "") or "")
    project = str(getattr(args, "project", "") or "")
    tree = _D.load_tree(ctx.root, plan_id, project) if project else _D.load_tree(ctx.root, plan_id)
    if not tree:
        raise _plan_not_found(plan_id)
    pid = str(tree.get("project_id") or "")
    proj_dir = (_Path(ctx.root) / "projects" / pid) if pid else None
    return {"ok": True, "action": "tasktree-dataflow", "tree": tree,
            "dataflow": _DF.build_data_flow(tree, proj_dir)}


def _tasktree_declare(ctx: FactoryContext, args: Any) -> dict:
    """`factory tasktree declare <plan>` —— ★ 产线声明「模块 ↔ 数据实体」。

    【为什么】数据流程图上模块↔实体的线默认只是【线索】（文案里碰巧出现实体名, 覆盖 7/13）。
    Founder 要的是"数据流程"成真 ⇒ 由产线**声明**每个模块读/写哪些实体, 落 `data_entities`,
    视图随之把虚线画成实线。

    ★ 不许编: LLM 只许从【项目真实数据模型】的清单里选; 清单外的丢弃并计数上报;
      拿不准 ⇒ 空数组（宁可没有, 不要瞎标）。
    """
    from pathlib import Path as _Path

    from ai_factory_os.services.work import data_flow as _DF
    from ai_factory_os.services.work import decomposition as _D
    from ai_factory_os.services.work import staffing as _ST
    from ai_factory_os.services.work.declare import declare_module, parse_entity_spec

    plan_id = str(getattr(args, "plan_id", "") or "")
    project = str(getattr(args, "project", "") or "")
    tree = _D.load_tree(ctx.root, plan_id, project) if project else _D.load_tree(ctx.root, plan_id)
    if not tree:
        raise _plan_not_found(plan_id)
    pid = str(tree.get("project_id") or "")
    proj_dir = (_Path(ctx.root) / "projects" / pid) if pid else None
    # ★ 实体清单来源: ① 架构设计制品的 database_design 节（从零场景也在）→ ② 项目里的 DDL
    #   （实跑踩到: 只认 DDL ⇒ 从零跑真实场景时这一环必然空着, 只能拒绝）
    _cat = _DF.entity_catalog(ctx.root, pid, workspace_dir=proj_dir if pid else None)
    names = list(_cat["names"])
    if not names:
        raise CliError("没有实体清单（架构设计制品里没有 database_design, 项目里也没 *.prisma / *.sql）"
                       "⇒ 无法声明（不编）", exit_code=1)
    if not getattr(args, "json", False):
        print(f"  实体清单来源: {_cat['detail']}")

    nodes = tree.get("nodes") or []
    # ★★ 手动改（人来纠产线的声明）: `--set "Order:write User:read"` / `--clear`
    #    必须配 --node（别一次改掉全部）; 名字当场对着【项目真实数据模型】校验, 写错立刻报错
    spec = list(getattr(args, "set_spec", None) or [])
    clear = bool(getattr(args, "clear", False))
    if spec or clear:
        only = str(getattr(args, "node", "") or "")
        if not only:
            raise CliError("手动改必须指定 --node（避免一次改掉全部模块）", exit_code=1)
        node = next((n for n in nodes if str(n.get("id") or "") == only
                     or str(n.get("id") or "").endswith(only)), None)
        if node is None:
            raise CliError(f"找不到节点: {only} —— --node 收的是节点 id（`tasktree show <plan> --ids` "
                           "可看 id; 也收 id 末尾片段）", exit_code=1)
        before = list(node.get("data_entities") or [])
        ents: list[dict[str, Any]] = []
        if spec:
            try:
                ents = parse_entity_spec(spec, set(names))
            except ValueError as e:
                raise CliError(str(e), exit_code=1) from e
        _D.declare_node_entities(ctx.root, plan_id, node_id=str(node.get("id") or ""),
                                 entities=ents, project_id=project)
        name = str(node.get("display_name") or node.get("title") or "")
        return {"ok": True, "action": "tasktree-declare", "tree": tree, "manual": True,
                "entities_available": names,
                "declared": [{"node": name, "entities": ents, "dropped": 0, "before": before}],
                "skipped": 0, "dropped_total": 0, "dry_run": False, "exit_code": 0, "args": args}

    dom_ids = {str(n.get("id") or "") for n in nodes if n.get("kind") == "domain"}
    targets = [n for n in nodes if n.get("kind") == "domain"
               and str(n.get("parent_id") or "") not in dom_ids]
    only = str(getattr(args, "node", "") or "")
    if only:
        targets = [n for n in nodes
                   if str(n.get("id") or "") == only or str(n.get("id") or "").endswith(only)]
        if not targets:
            raise CliError(f"找不到节点: {only}", exit_code=1)
    todo = [n for n in targets if not n.get("data_entities") or not n.get("priority")]
    dry = bool(getattr(args, "dry_run", False))

    prov = _arch_provider()
    # ★ 2026-09-21（多公司/多部门落到执行）: 项目归了公司/部门 ⇒ 只从该公司/部门的人里选
    _co, _dep = _ST.project_scope(ctx.root, str(getattr(args, "project", "") or
                                                (tree.get("project_id") if isinstance(tree, dict) else "") or ""))
    roles = _ST.role_catalog(ctx.root, company_id=_co, department_id=_dep)
    if _co and not roles:
        raise CliError(f"项目归属公司 {_co} 但该公司一个可用成员都没有 ⇒ 不猜（先给成员设归属: "
                       f"factory org member set --all --company {_co}）", exit_code=1)
    if not roles:                              # 项目未归属 ⇒ 现状（全部成员）
        roles = _ST.role_catalog(ctx.root)
    rows: list[dict[str, Any]] = []
    dropped_total = 0
    staff_dropped_total = 0
    for n in todo:
        res = declare_module(
            str(n.get("display_name") or n.get("title") or ""),
            desc=str(n.get("scope") or ""),
            acceptance=str(n.get("acceptance") or ""),
            entities=names, provider=prov, roles=list(roles))
        got, dropped = res["entities"], res["dropped"]
        dropped_total += dropped
        staff_dropped_total += len(res.get("staff_dropped") or [])
        if not dry:
            # ★ 幂等保护: 已有实体声明的不重写（LLM 有随机性, 重跑会把你验证过的那份冲掉）——
            #   本次只补"缺的那部分"（优先级 / 谁做），两者都来自同一次 LLM 调用, 不额外花钱。
            if not n.get("data_entities"):
                _D.declare_node_entities(ctx.root, plan_id, node_id=str(n.get("id") or ""),
                                         entities=got, project_id=project)
            # ★ C 产线声明优先级（来源记 declared ⇒ 只有人工能盖过它）
            if res["priority"]:
                _D.set_node_priority(ctx.root, plan_id, node_id=str(n.get("id") or ""),
                                     priority=res["priority"], source="declared",
                                     reason=res.get("reason") or "", project_id=project)
            # ★ C 产线声明"谁做"（值已按真实角色清单校验过; 空 ⇒ 不写, 不假装能派）
            if res.get("capabilities"):
                _D.set_node_staffing(ctx.root, plan_id, node_id=str(n.get("id") or ""),
                                     role=res.get("role") or res["capabilities"][0],
                                     capabilities=list(res["capabilities"]), project_id=project)
        rows.append({"node": str(n.get("display_name") or n.get("title") or ""),
                     "entities": got, "dropped": dropped,
                     "priority": res["priority"], "reason": res.get("reason") or "",
                     "role": res.get("role") or "", "capabilities": res.get("capabilities") or [],
                     "staff_dropped": res.get("staff_dropped") or []})
    return {"ok": True, "action": "tasktree-declare", "tree": tree,
            "entities_available": names, "roles_available": sorted(roles),
            "declared": rows,
            "skipped": len(targets) - len(todo), "dropped_total": dropped_total,
            "staff_dropped_total": staff_dropped_total,
            "dry_run": dry, "exit_code": 0, "args": args}


def _tasktree_priority(ctx: FactoryContext, args: Any) -> dict:
    """`factory tasktree priority <plan> [--auto | --set-node X --value P1]` —— ★ 优先级。

    Founder 定: **ABC 都要 + 支持人为干预** ⇒
      A 人工（--set-node/--value, 页面点改）· B 关键路径自动（--auto）· C 产线声明（declare 时给）
    仲裁: **人工 > 产线声明 > 关键路径自动** —— 自动导出绝不覆盖人工/声明。
    取值只有 P0..P3（调度器 `rank.py` 原文: 先到期 → 优先级 → 便宜的先做 → 声明序）。
    """
    from ai_factory_os.services.work import decomposition as _D
    from ai_factory_os.services.work import priority as _pri

    plan_id = str(getattr(args, "plan_id", "") or "")
    project = str(getattr(args, "project", "") or "")
    tree = _D.load_tree(ctx.root, plan_id, project) if project else _D.load_tree(ctx.root, plan_id)
    if not tree:
        raise _plan_not_found(plan_id)
    nodes = tree.get("nodes") or []
    did, written = "查看现状", 0
    skipped: list[str] = []
    missing: list[str] = []
    invalid: list[str] = []
    node_arg = str(getattr(args, "set_node", "") or "")
    value = str(getattr(args, "value", "") or "")
    if node_arg:
        if not value:
            raise CliError("--set-node 要配 --value P0/P1/P2/P3", exit_code=2)
        r = _D.set_node_priority(ctx.root, plan_id, node_id=node_arg, priority=value,
                                 source="manual", reason=str(getattr(args, "why", "") or ""),
                                 project_id=project)
        tree, did, written = r["tree"], "人工设置", 1
    elif bool(getattr(args, "auto", False)):
        auto = _pri.auto_from_keypath(nodes)
        by_id = {str(n.get("id") or ""): n for n in nodes}
        items = {nid: spec for nid, spec in auto.items()
                 if _pri.can_apply(by_id.get(nid) or {}, "keypath")}
        skipped = [nid for nid in auto if nid not in items]
        r2 = _D.set_priorities(ctx.root, plan_id, items=items, project_id=project)
        tree, written = r2["tree"], r2["written"]
        missing, invalid = r2["missing"], r2["invalid"]
        did = "按关键路径自动导出"
    eff = _pri.effective(tree.get("nodes") or [])
    sources: dict[str, int] = {}
    for v in eff.values():
        sources[v["source"]] = sources.get(v["source"], 0) + 1
    return {"ok": True, "action": "tasktree-priority", "tree": tree, "priority": eff,
            "distribution": _pri.distribution(eff), "sources": sources, "did": did,
            "stored": _pri.stored_stats(tree.get("nodes") or []),
            "written": written, "skipped": skipped, "missing": missing, "invalid": invalid,
            "exit_code": 0, "args": args}


def _tasktree_staffing(ctx: FactoryContext, args: Any) -> dict:
    """`factory tasktree staffing <plan> [--node X --role developer --cap developer,tester]`。

    ★ "谁做"是执行能不能派出去的前提: 调度器 `resolution_for` 拿节点的 `required_capabilities`
      与**成员的角色**求交集 ⇒ 值必须是【真实角色清单】里的（`~/.factory/agents/agents.json`）。
      （适配器 docstring 写的是 "skill 命中", 与代码不符 —— 以代码为准。）
    """
    from ai_factory_os.services.work import decomposition as _D
    from ai_factory_os.services.work import staffing as _ST

    plan_id = str(getattr(args, "plan_id", "") or "")
    project = str(getattr(args, "project", "") or "")
    tree = _D.load_tree(ctx.root, plan_id, project) if project else _D.load_tree(ctx.root, plan_id)
    if not tree:
        raise _plan_not_found(plan_id)
    _proj = str(getattr(args, "project", "") or "") or str(tree.get("project_id") or "")
    _co, _dep = _ST.project_scope(ctx.root, _proj)
    catalog = _ST.role_catalog(ctx.root, company_id=_co, department_id=_dep)   # ★ 按归属筛人
    if _co and not catalog:
        raise CliError(f"项目归属公司 {_co} 但该公司没有可用成员 ⇒ 不猜（先 `factory org member set "
                       f"--all --company {_co}`）", exit_code=1)
    if not catalog:
        catalog = _ST.role_catalog(ctx.root)
    if not catalog:
        raise CliError("读不到成员清单（~/.factory/agents/agents.json）⇒ 不知道有哪些角色可用, "
                       "不猜（先 `factory agent list` 看舰队）", exit_code=1)
    node_arg = str(getattr(args, "node", "") or "")
    role = str(getattr(args, "role", "") or "")
    did, written, dropped = "查看现状", 0, []
    if node_arg or role:
        if not (node_arg and role):
            raise CliError("--node 与 --role 要一起给（改一个节点的一个角色）", exit_code=2)
        raw_cap = str(getattr(args, "cap", "") or "") or role
        caps_in = [c for c in raw_cap.replace("，", ",").split(",") if c.strip()]
        got_role, caps, dropped = _ST.parse_staffing(role, caps_in, catalog)
        if not got_role:
            raise CliError(f"role 必须是真实角色之一: {'/'.join(sorted(catalog))}", exit_code=2)
        r = _D.set_node_staffing(ctx.root, plan_id, node_id=node_arg, role=got_role,
                                 capabilities=caps, project_id=project)
        tree, did, written = r["tree"], "人工指定", 1
    nodes = tree.get("nodes") or []
    leaves = [n for n in nodes if n.get("kind") == "task"]
    staffed = [n for n in leaves if n.get("required_capabilities")]
    by_role: dict[str, int] = {}
    for n in staffed:
        for c in n["required_capabilities"]:
            by_role[c] = by_role.get(c, 0) + 1
    return {"ok": True, "action": "tasktree-staffing", "tree": tree,
            "roles": catalog, "did": did, "written": written, "dropped": dropped,
            "leaves": len(leaves), "staffed": len(staffed),
            "unstaffed": len(leaves) - len(staffed), "by_role": by_role,
            "exit_code": 0, "args": args}


def _tasktree_edit(ctx: FactoryContext, args: Any) -> dict:
    """`factory tasktree edit <plan> --node <id> [--title/--acceptance/--display-name] [--drop]`
    —— ★ 逐节点编辑（Founder: "每一个子节点, 用户都有可能做修改"）。

    ★ 为什么改完回到候选态: 用户改完 ⇒ 与"刚才确认过的树"不再是同一棵 ⇒
      必须重新确认才进执行（否则确认门形同虚设）。
    """
    from ai_factory_os.services.work import decomposition as _D

    plan_id = str(getattr(args, "plan_id", "") or "")
    project = str(getattr(args, "project", "") or "")

    # ★ 拆分 / 合并（与"改字段"是并列的三种编辑操作）
    if getattr(args, "split", None):
        r = _D.split_node(ctx.root, plan_id, node_id=str(getattr(args, "node", "") or ""),
                          children=list(args.split), project_id=project)
        return {"ok": True, "action": "tasktree-edit", **r,
                "summary": {"kinds": {}, "leaves": len(_D.tree_leaves(r["tree"])),
                            "done": 0, "percent": "0"}}
    if getattr(args, "merge_ids", None):
        ids = list(args.merge_ids)
        r = _D.merge_nodes(ctx.root, plan_id, node_ids=ids,
                           title=str(getattr(args, "title", "") or ""), project_id=project)
        return {"ok": True, "action": "tasktree-edit", **r,
                "summary": {"kinds": {}, "leaves": len(_D.tree_leaves(r["tree"])),
                            "done": 0, "percent": "0"}}

    r = _D.edit_node(
        ctx.root, plan_id,
        node_id=str(getattr(args, "node", "") or ""),
        project_id=project,
        title=getattr(args, "title", None),
        acceptance=getattr(args, "acceptance", None),
        display_name=getattr(args, "display_name", None),
        assignee=getattr(args, "assignee", None),
        drop=bool(getattr(args, "drop", False)),
    )
    return {"ok": True, "action": "tasktree-edit", **r,
            "summary": {"kinds": {}, "leaves": len(_D.tree_leaves(r["tree"])),
                        "done": 0, "percent": "0"}}


def _tasktree_translate(ctx: FactoryContext, args: Any) -> dict:
    """`factory tasktree translate <plan>` —— ★ 用 LLM 把技术标题翻成"人话名"。

    写进节点的 `display_name` 字段（用户视图优先读它, 没有才规则派生）。
    ★ 分批 + 限长: deepseek 单次输出上限 8192 tokens, 一次翻太多会被截断
    （本仓实测踩过 arch design 截断）。失败的那批【跳过并如实报告】。
    """
    from ai_factory_os.services.work import decomposition as _D
    from ai_factory_os.services.work.name_translate import translate_titles

    plan_id = str(getattr(args, "plan_id", "") or "")
    project = str(getattr(args, "project", "") or "")
    tree = _D.load_tree(ctx.root, plan_id, project) if project else _D.load_tree(ctx.root, plan_id)
    if not tree:
        raise _plan_not_found(plan_id)

    # 只翻"还没人话名"的（已有 display_name 的不覆盖 —— 用户改过的不该被冲掉）
    items = [(str(n.get("id") or ""), str(n.get("title") or ""))
             for n in (tree.get("nodes") or [])
             if n.get("kind") in ("domain", "task") and not n.get("display_name")]
    if not items:
        return {"ok": True, "action": "tasktree-translate", "applied": 0, "total": 0,
                "hit": 0, "tree": tree,
                "summary": {"kinds": {}, "leaves": len(_D.tree_leaves(tree)), "done": 0, "percent": "0"}}

    prov = _arch_provider()
    names = translate_titles(items, provider=prov)
    r = _D.apply_display_names(ctx.root, plan_id, names, project_id=project)
    return {"ok": True, "action": "tasktree-translate", "applied": r["applied"],
            "total": len(items), "hit": r["applied"], "tree": r["tree"],
            "summary": {"kinds": {}, "leaves": len(_D.tree_leaves(r["tree"])),
                        "done": 0, "percent": "0"}}


def _tasktree_expand(ctx: FactoryContext, args: Any) -> dict:
    """`factory tasktree expand <plan> [--node <模块>]` —— ★ 细拆（逐模块展开成子任务）。

    Founder 指出的核心问题: "这现在还是呈现的是大类啊, 没有细分任务, 没有拆解"。
    ⇒ 本命令让树**真的长出子任务**: 对每个模块单独调一次 LLM 拆解
      （输出体量小 ⇒ 不被 8192 截断; 模型精力集中 ⇒ 拆得细）。
    """
    from ai_factory_os.services.work import decomposition as _D
    from ai_factory_os.services.work.expand import expand_module

    plan_id = str(getattr(args, "plan_id", "") or "")
    project = str(getattr(args, "project", "") or "")
    per = str(getattr(args, "node", "") or "")
    deep = bool(getattr(args, "deep", False))
    max_depth = int(getattr(args, "max_depth", 3) or 3)
    tree = _D.load_tree(ctx.root, plan_id, project) if project else _D.load_tree(ctx.root, plan_id)
    if not tree:
        raise _plan_not_found(plan_id)

    # ★ 目标节点: 默认顶层模块; --node 指定任意节点（含 task —— 递归拆要靠它）
    #   --deep 时把 task 也纳入候选（逐层往下走）
    def _candidates(tr: dict) -> list[dict]:
        ns = tr.get("nodes") or []
        if deep:
            return [n for n in ns if n.get("kind") in ("domain", "task")]
        return [n for n in ns if n.get("kind") == "domain"]

    doms = _candidates(tree)
    if per:
        # ★ --node 指定时**不限 kind** —— 递归拆要靠它指定 task 节点
        #   （之前这里只从 domain 里找 ⇒ 指定 task 就报"找不到模块"）
        allns = tree.get("nodes") or []
        doms = [d for d in allns
                if str(d.get("id")) == per or str(d.get("id")).endswith(per)]
        if not doms:
            raise CliError(f"找不到节点: {per}", exit_code=1)
    # ★ 跳过"已经被展开过"的（下面已有 ≥2 个 task）—— 幂等, 重复跑不会越拆越多
    todo = []
    for d in doms:
        kids = [n for n in (tree.get("nodes") or [])
                if str(n.get("parent_id")) == str(d.get("id")) and n.get("kind") == "task"]
        if len(kids) < 2:
            todo.append(d)
    if not todo:
        return {"ok": True, "action": "tasktree-expand", "done": 0, "skipped": len(doms),
                "tree": tree, "results": [],
                "summary": {"kinds": {}, "leaves": len(_D.tree_leaves(tree)),
                            "done": 0, "percent": "0"}}

    prov = _arch_provider()
    results: list[dict[str, Any]] = []
    ok = 0
    stops = 0

    def _expand_one(d: dict, depth: int) -> None:
        """拆一个节点; 返回后由调用方决定是否再扫（递归）。"""
        nonlocal ok, stops, tree
        name = str(d.get("display_name") or d.get("title") or "")
        kids = expand_module(
            name,
            desc=str(d.get("scope") or ""),
            acceptance=str(d.get("acceptance") or ""),
            caps=list(d.get("required_capabilities") or []),
            provider=prov,
        )
        r = _D.expand_domain(ctx.root, plan_id, node_id=str(d.get("id")), kids=kids,
                            project_id=project)
        tree = r["tree"]
        if len(kids) < 2:                       # ★ LLM 判定"已是一件事" ⇒ 到底
            stops += 1
            results.append({"module": name, "depth": depth, "kids": 1,
                            "titles": ["（已是一件事, 到底）"]})
        else:
            ok += 1
            results.append({"module": name, "depth": depth, "kids": len(kids),
                            "titles": [k["title"] for k in kids]})

    # 逐层往下（--deep 才递归）; 每层重扫"还没拆到一件事"的节点
    for depth in range(1, (max_depth if deep else 1) + 1):
        tree = _D.load_tree(ctx.root, plan_id, project) if project else _D.load_tree(ctx.root, plan_id)
        ns = tree.get("nodes") or []
        if per:
            todo = [n for n in ns if str(n.get("id")) == per or str(n.get("id")).endswith(per)]
        elif depth == 1:
            todo = [n for n in _candidates(tree)
                    if len([x for x in ns if str(x.get("parent_id")) == str(n.get("id"))
                            and x.get("kind") == "task"]) < 2]
        else:
            # ★ 递归: 只看"上一轮刚拆出来的"子任务（它们是叶子且还没拆过）
            todo = [n for n in ns if n.get("kind") == "task"
                    and not any(x.get("parent_id") == n.get("id") for x in ns)]
        if not todo:
            break
        for d in todo:
            try:
                _expand_one(d, depth)
            except Exception as exc:  # noqa: BLE001 — 单个失败不拖垮整批（如实报告）
                results.append({"module": str(d.get("display_name") or d.get("title") or "")[:24],
                                "depth": depth, "error": str(exc)[:100]})

    return {"ok": True, "action": "tasktree-expand", "done": ok, "stopped": stops,
            "results": results, "tree": tree,
            "summary": {"kinds": {}, "leaves": len(_D.tree_leaves(tree)), "done": 0, "percent": "0"}}

def _decompose_refs(design: Any) -> tuple[str, dict[str, Any]]:
    """★ 拆解要传给 decompose 的两个引用（语义修正, 见 docs/实跑-全链路-20260920.md 卡点 8）。

    实测踩到: 原来 `prd_ref=design.id`（设计制品 id）, 而 `design_ref` 取 design.metadata.artifact_refs
    （= product / ux_ui 的 id）—— **两个名字都不对**, 追溯时说不清"这棵树按哪份需求/设计拆的"。

    正确语义（字段名就是判据）:
      · `prd_ref`     = **需求侧制品**（product 制品; 它的 7 节含 mvp_scope / user_stories = PRD 内容）
      · `design_ref`  = **[design.id]**（本篇设计制品）
      · `lineage`     = 血缘 [product, ux_ui]（原 artifact_refs, 另存 `artifact_lineage` 不丢）
    返回 (prd_ref, design_metadata)。
    """
    meta = dict(getattr(design, "metadata", {}) or {})
    lineage = [str(x) for x in (meta.get("artifact_refs") or []) if str(x)]
    design_id = str(getattr(design, "id", "") or "")
    out = dict(meta)
    out["artifact_refs"] = [design_id] if design_id else []
    out["lineage"] = lineage
    return (lineage[0] if lineage else design_id), out


def _tasktree_workflow(ctx: FactoryContext, args: Any) -> dict:
    """★ 流程命令（"无固定流程(可编排)"的入口）。

    做三件事之一（看 args）:
      · `--list`           列出可用流程（引擎 store 里的定义 = 内置 + 用户注册的）
      · `--id <流程>`      给这棵树挂流程（挂上后: 叶按该流程步骤推进, 走完全部步骤才算完成）
      · `--id ""`          摘掉（回到现状: 一叶一次派活即完成）
      · 都不给             看这棵树当前挂的流程与其步骤
    """
    from ai_factory_os.bootstrap.scheduler_wiring import workflow_engine
    from ai_factory_os.services.work import decomposition as D

    project_id = str(getattr(args, "project", None) or "")
    plan_id = str(getattr(args, "plan_id", "") or "")
    eng = workflow_engine(ctx.root)
    wf_id = getattr(args, "workflow_id", None)

    if getattr(args, "list", False):
        attached = D.tree_workflow(ctx.root, plan_id, project_id) if plan_id else ""
        rows = []
        for w in eng.list_workflows():
            rows.append({"id": w.id, "name": w.name, "steps_total": len(w.steps),
                         "steps": [s.name for s in w.steps],
                         "attached": w.id == attached})
        return {"ok": True, "action": "tasktree-workflow", "listed": True,
                "plan_id": plan_id, "workflows": rows}

    if wf_id is not None:
        D.set_tree_workflow(ctx.root, plan_id, wf_id, project_id)
    cur = D.tree_workflow(ctx.root, plan_id, project_id)
    wf = eng.get_workflow(cur) if cur else None
    return {"ok": True, "action": "tasktree-workflow", "plan_id": plan_id,
            "attached": cur,
            "steps": [{"name": s.name, "skill": s.required_skill or ""}
                      for s in (wf.steps if wf else [])]}


def _dispatch_tasktree(ctx: FactoryContext, args: Any) -> dict:
    """factory tasktree list|show|decompose|confirm —— 产品环 ⑤「任务拆解」。

    底层: services/work/decomposition.py（服务域 work · 域 decomposition）
    输入: Design Artifact 的 task_breakdown（环④ 产物）—— 不重跑 LLM 分解,
          避免"架构说 11 个模块、任务树说 8 个"的不一致。
    产物: 多级树（Project→Domain→Leaf）+ 每叶（做什么/改哪些文件/验收断言/依赖/归属/change_type）
          落盘 projects/<P>/tasks/{plan_id}.json（遵守"项目文件在项目目录"铁律）
    状态: **candidate** —— 需 `tasktree confirm` 才进执行（人工门）
    """
    from ai_factory_os.services.work import decomposition as D

    cmd = args.tasktree_command
    project_id = str(getattr(args, "project", None) or "")

    # ★ 用户视图（Founder 设计）: 与 show 同源（同一份树数据）, 只换读法。
    #   走独立实现（_tasktree_todo）—— 它的输出结构面向"给人看", 与 show 不同。
    if cmd == "workflow":
        return _tasktree_workflow(ctx, args)
    if cmd == "todo":
        return _tasktree_todo(ctx, args)
    if cmd == "flow":
        return _tasktree_flow(ctx, args)
    if cmd == "dataflow":
        return _tasktree_dataflow(ctx, args)
    if cmd == "declare":
        return _tasktree_declare(ctx, args)
    if cmd == "priority":
        return _tasktree_priority(ctx, args)
    if cmd == "staffing":
        return _tasktree_staffing(ctx, args)
    if cmd == "edit":
        return _tasktree_edit(ctx, args)
    if cmd == "translate":
        return _tasktree_translate(ctx, args)
    if cmd == "expand":
        return _tasktree_expand(ctx, args)

    if cmd == "list":
        trees = D.list_trees(ctx.root, project_id)
        rows = []
        for t in trees:
            s = D.tree_summary(t)
            rows.append({"plan_id": t.get("plan_id"), "project": t.get("project_id"),
                         "status": t.get("status"), "leaves": s["leaves"],
                         "done": s["done"], "percent": s["percent"],
                         "created_at": t.get("created_at")})
        return {"ok": True, "command": "tasktree list", "count": len(rows),
                "trees": rows, "exit_code": 0, "args": args}

    if cmd == "show":
        tree = D.load_tree(ctx.root, str(args.plan_id), project_id)
        if tree is None:
            raise _plan_not_found(args.plan_id)
        return {"ok": True, "command": "tasktree show", "tree": tree,
                "summary": D.tree_summary(tree),
                "order": D.topological_order(tree),
                "exit_code": 0, "args": args}

    if cmd == "decompose":
        if not project_id:
            raise CliError("用法: factory tasktree decompose --project <项目 id>", exit_code=2)
        from ai_factory_os.services.organization.projects import ProjectStore
        store = ProjectStore(ctx.root / "org")
        cands = [a for a in store.list_artifacts()
                 if getattr(a, "project_id", "") == project_id
                 and "design" in str(getattr(a, "type", "")).lower()]
        if not cands:
            raise CliError(
                f"项目 {project_id} 内无 design 产物 —— 先跑 arch design（任务拆解需要架构产出作输入）",
                exit_code=2)
        # ★ 2026-09-21 修（真 bug）: `cands[-1]` 是**列表顺序的最后一个, 不是最新生成的** ——
        #   实测: 项目里同时有 11:26 的旧设计与 18:54 的新设计, 拆解取了**旧**的 ⇒ 拿旧图干活。
        #   现在: 缺省取 created_at 最新的一份; 要指定就 `--design <id>`（找不到 ⇒ 响亮拒绝）。
        _want = str(getattr(args, "design", "") or "")
        if _want:
            design = next((a for a in cands if str(getattr(a, "id", "")) == _want), None)
            if design is None:
                raise CliError(f"指定的设计不存在或不属于本项目: {_want}", exit_code=2)
        else:
            design = max(cands, key=lambda a: str(getattr(a, "created_at", "") or ""))
        # ★ 读①定位结果（若给了 --conversation）—— 传给 decompose, 影响拆解
        #   （设计: 承接决定拆解粒度; intent=问答 ⇒ decompose 会拒绝生成树）
        _loc_intent = _loc_role = ""
        _cid = str(getattr(args, "conversation", None) or "")
        if _cid:
            from ai_factory_os.services.conversation import understanding as _U
            _loc = (_U.get_conversation(ctx.root, _cid) or {}).get("location") or {}
            _loc_intent = str(_loc.get("intent") or "")
            _loc_role = str(_loc.get("suggested_role") or "")
        try:
            _prd_ref, _design_meta = _decompose_refs(design)   # ★ 引用语义修正（卡点 8）
            tree = D.decompose_from_design(
                ctx.root, project_id=project_id,
                design_metadata=_design_meta,
                plan_id=str(getattr(args, "plan", None) or ""),
                prd_ref=_prd_ref,
                # ★ 承接传进拆解（设计: 承接决定拆解粒度）——
                #   从会话读①定位结果（intent/suggested_role）, 传给 decompose。
                #   · intent=问答 ⇒ decompose 拒绝生成树（问答不该进流水线）
                #   · 并把定位记进树元数据（可追溯"这棵树为什么这么拆"）
                intent=_loc_intent,
                suggested_role=_loc_role,
            )
        except D.DecomposeLimitError as exc:
            raise CliError(f"拆解超边界: {exc}", exit_code=1) from exc
        except ValueError as exc:
            raise CliError(str(exc), exit_code=1) from exc

        # ★ 2026-09-21（Founder 定: "我们采取的是递归的方式, 拆到最小单位, 最小实现"）:
        #   拆解 = 【递归到最小单位】—— 收尾自动递归细拆, 不再依赖"另一条腿"(expand 单独跑)。
        #   手工路径(tasktree decompose) 与 chain 第⑦步从此同源; 停止判据 = 粒度判据(不是层数)。
        from ai_factory_os.services.work.expand import expand_to_minimal as _to_min

        _pid_plan = str(tree.get("plan_id") or "")
        _rec: dict = {"rounds": 0, "leaves": 0, "remaining": [], "split": [],
                      "errors": [], "stopped_because": "未跑"}
        try:
            _rec = _to_min(ctx.root, _pid_plan, project_id, provider=_arch_provider())
            tree = D.load_tree(ctx.root, _pid_plan, project_id) or tree
        except Exception as exc:  # noqa: BLE001 — 递归不可用 ⇒ 响亮说, 不假装拆完
            _rec["errors"] = [f"递归细拆未执行: {type(exc).__name__}: {str(exc)[:80]}"]
            _rec["stopped_because"] = "递归细拆未执行（见 errors）"
        return {"ok": True, "command": "tasktree decompose", "tree": tree,
                "summary": D.tree_summary(tree), "recursion": _rec,
                "exit_code": 0, "args": args}

    if cmd == "confirm":
        # ★ 2026-09-21（Founder 的"出处"那一栏）: 确认前把【架构自己加的、已挡在树外的】单列给人看 ——
        #   出初稿→人看懂→人改→确认 里的"人看懂"就是这一步。
        try:
            _pre = D.load_tree(ctx.root, str(args.plan_id), project_id) or {}
            _ex = list(_pre.get("excluded_no_trace") or [])
            if _ex:
                print(f"  ⚠ 架构还想加 {len(_ex)} 件【你需求里没有的】东西 —— 已挡在任务树外（不做）:")
                for _i, _x in enumerate(_ex[:12], 1):
                    print(f"      {_i}. {str(_x.get('task') or '')[:70]}")
                if len(_ex) > 12:
                    print(f"      … 还有 {len(_ex) - 12} 件")
                print("    （要加就明说, 我把它补进需求再重新走一遍; 不加就不用管。）")
        except Exception:  # noqa: BLE001 — 提醒是"增强", 拿不到树不挡确认
            pass
        try:
            tree = D.confirm_tree(ctx.root, str(args.plan_id), project_id)
        except FileNotFoundError as exc:
            raise CliError(str(exc), exit_code=7) from exc
        except ValueError as exc:
            raise CliError(str(exc), exit_code=1) from exc
        return {"ok": True, "command": "tasktree confirm", "tree": tree,
                "exit_code": 0, "args": args}

    raise CliError(f"unknown tasktree action: {cmd}", exit_code=2)



#: 用户视图（Todo Tree）辅助 —— ★ 人话名由【规则派生】, 不调 LLM（先能看见效果）。
def _todo_display_name(title: str) -> str:
    """把专业 title 派生成人话名（用户视图用）。

    规则（实测现有树种子的形态）:
      · 去掉 "模块 N: " 前缀（decompose 给 domain 的格式）
      · 取第一个分句（，、；前的部分）—— 专业 title 常是"动宾, 动宾, 动宾"堆叠
      · 限 24 字（超出加省略号）
    ★ 诚实: 这是**派生**（不落库）; 将来若让 LLM 翻译, 结果写进 display_name 字段。
    """
    s = str(title or "").strip()
    s = re.sub(r"^模块\s*\d+\s*[:：]\s*", "", s)
    # ★ 括号优先: "初始化 monorepo（consumer、admin…" ⇒ "初始化 monorepo"
    for sep in ("（", "(", "，", "、", "；", ";", ",", "。"):
        if sep in s:
            s = s.split(sep)[0]
            break
    return s[:24] + ("…" if len(s) > 24 else "")


def _node_progress(node: dict, by_parent: dict[str, list], leaves_only: bool = True) -> tuple[int, int]:
    """★ 完成度（派生, 不落字段）—— Founder 设计: "节点完成度 = 已完成子节点数 / 总子节点数"。

    为什么是**派生值而非字段**: 完成度完全由子节点的 status 决定 ⇒ 若存成字段,
    就会出现"存的值"与"算的值"不一致（R25 一能力一处 / 一数据一权威源）。
    叶子: DONE ⇒ (1,1), 否则 (0,1)。父节点: 递归汇总子节点。

    返回: (done, total)
    """
    kids = [k for k in by_parent.get(str(node.get("id") or ""), [])
            if k.get("kind") in ("domain", "task")]
    if not kids:
        done = 1 if str(node.get("status") or "").lower() in ("completed", "done", "accepted") else 0
        return (done, 1)
    d = t_ = 0
    for k in kids:
        kd, kt = _node_progress(k, by_parent, leaves_only)
        d += kd
        t_ += kt
    return (d, t_)


def _node_name(node: dict) -> str:
    """节点的显示名 —— ★ 优先 `display_name` 字段（用户在 `tasktree edit` 里改过的）,
    没有才用 title 规则派生。

    ★ 为什么必须有这个函数: 之前视图直接 `_todo_display_name(title)` 派生,
    于是 `tasktree edit --display-name` 改的值**根本不显示** ⇒ 用户以为改了其实没用
    （实测踩到: 改 domain 的 display_name 后视图仍显示旧派生名）。
    """
    got = str(node.get("display_name") or "").strip()
    return got or _todo_display_name(node.get("title"))


#: 能力名 → 人话（用户视图里不出现 developer/architect 这种词）
_CAP_WORDS = {
    "developer": "开发", "architect": "架构", "tester": "测试", "devops": "部署",
    "reviewer": "评审", "security": "安全", "ux_ui": "设计", "pm": "产品",
}


def _cap_word(cap: Any) -> str:
    """能力名 → 人话（认不出就原样, 不瞎译）。"""
    s = str(cap or "").strip()
    return _CAP_WORDS.get(s, s)


def _todo_mark(status: Any) -> str:
    """状态 → 人话标记（待办/进行中/完成）。"""
    st = str(getattr(status, "value", status) or "").strip().lower()
    if st in ("completed", "done", "accepted"):
        return "✅"
    if st in ("claimed", "running", "in_progress"):
        return "🚧"
    if st in ("cancelled", "failed"):
        return "⛔"
    return "☐"

def _mq(text: Any) -> str:
    """mermaid 标签里的危险字符换掉 —— 宁可换个字, 也不要渲染成乱码。"""
    return (str(text or "").replace('"', "'").replace("#", "＃")
            .replace("[", "（").replace("]", "）")
            .replace("{", "（").replace("}", "）"))


def _flow_mermaid(f: dict) -> str:
    """功能链路图 → mermaid 源码（设计 §4.3: CLI 可渲染 mermaid）。"""
    mid: dict[str, str] = {}
    lines: list[str] = ["flowchart TB"]
    core: list[str] = []
    for b in f.get("batches") or []:
        stage = "（可先做）" if b["level"] == 1 else "（等前面做完）"
        lines.append(f'  subgraph B{b["level"]}["第 {b["level"]} 批{stage}"]')
        for m in b["nodes"]:
            mid[m["id"]] = f"M{len(mid) + 1}"
            bits = ["前置: " + " / ".join(m["deps"])] if m.get("deps") else ["无前置"]
            bits.append(f'被 {m["depended_by"]} 个依赖' if m.get("depended_by") else "没人依赖它")
            if m.get("kids"):
                bits.append(f'{m["kids"]} 个子模块')
            lines.append(f'    {mid[m["id"]]}["{_mq(m["name"])}<br/>{_mq(" · ".join(bits))}"]')
            if m.get("core"):
                core.append(mid[m["id"]])
        lines.append("  end")
    for e in f.get("edges") or []:
        a, b = mid.get(e["from"]), mid.get(e["to"])
        if a and b:
            lines.append(f"  {a} --> {b}")
    if core:
        lines.append("  classDef core fill:#eaf3ff,stroke:#0071e3,color:#0058b0")
        lines.append("  class " + ",".join(core) + " core")
    return "\n".join(lines)


def _dataflow_mermaid(d: dict) -> str:
    """数据流程图 → mermaid 源码（虚线=线索, 粗线=声明, 细线+外键=真实外键）。"""
    lines: list[str] = ["flowchart LR"]
    mid: dict[str, str] = {}
    for i, m in enumerate(d.get("modules") or []):
        mid[m["id"]] = f"M{i + 1}"
        lines.append(f'  {mid[m["id"]]}["{_mq(m["name"])}"]')
    eid: dict[str, str] = {}
    for i, e in enumerate(d.get("entities") or []):
        eid[e["name"]] = f"E{i + 1}"
        tag = "（产线声明）" if e.get("from") == "declared" else f'被 {e.get("refs", 0)} 张表引用'
        lines.append(f'  {eid[e["name"]]}(["{_mq(e["name"])}<br/>{_mq(tag)}"])')
    for k in d.get("module_links") or []:
        a, b = mid.get(k.get("module_id")), eid.get(k.get("entity"))
        if not a or not b:
            continue
        lines.append(f"  {a} -. 线索 .-> {b}" if k.get("kind") == "evidence"
                     else f"  {a} == 声明 ==> {b}")
    for rel in d.get("relations") or []:
        a, b = eid.get(rel.get("from")), eid.get(rel.get("to"))
        if a and b:
            lines.append(f"  {a} -->|外键| {b}")
    return "\n".join(lines)


def _print_dataflow(d: dict) -> None:
    """数据流程图（终端文字版）—— 来源/覆盖率必须写清楚, 线索不许说成事实。"""
    if not d.get("available"):
        print()
        print("  数据流程图    没有可依据的实体清单 —— 架构设计制品里没有 database_design,"
              " 项目里也找不到 *.prisma / *.sql（不编一张图）")
        return
    cov = d.get("coverage") or {}
    print()
    print(f"  数据流程图    {len(d.get('entities') or [])} 个实体 · "
          f"{len(d.get('relations') or [])} 条真实外键 · "
          f"{len(d.get('module_links') or [])} 条模块↔实体线"
          f"（声明 {d.get('declared_count', 0)} / 线索 {d.get('evidence_count', 0)}）")
    print(f"  {'━' * 52}")
    print()
    sf = d.get("source_file") or ""
    if sf:
        print(f"  数据来源: {sf}（真实 DDL: 实体清单 + 实体间外键）")
    else:
        print("  数据来源: 产线声明（依据【架构设计制品的 database_design 节】—— 从零场景下 DDL 还没做出来）")
        print("            实体之间的外键关系需要 DDL ⇒ 暂无（不画假线）")
    ents = d.get("entities") or []
    print("  实体（被引用次数）: " + " · ".join(
        f"{e['name']} {e['refs']}" for e in ents))
    print()
    print("  ① 模块 ↔ 实体" + ("（⇢ = 线索, 不是系统记录）" if d.get("evidence_count") else ""))
    by_mod: dict[str, list[str]] = {}
    for k in d.get("module_links") or []:
        mark = "→" if k["kind"] == "declared" else "⇢"
        by_mod.setdefault(k["module"], []).append(f"{mark} {k['entity']}")
    for name, items in by_mod.items():
        print(f"    {name:<12} {'  '.join(items)}")
    print()
    print("  ② 实体之间（真实外键）")
    for r in d.get("relations") or []:
        via = f"  via {r['via']}" if r.get("via") else ""
        print(f"    {r['from']:<16} ──▶ {r['to']}{via}")
    print()
    if (cov.get("missing") or []):
        print(f"  ⚠ 未覆盖的模块（{len(cov['missing'])} 个）: " + "、".join(cov["missing"]))
        print("    （它们的文案里没出现任何实体名 ⇒ 图上没有它们的线, 不编）")
    if d.get("hint"):
        print(f"  ⚠ {d['hint']}")
    print()


def _print_tasktree(args: Any, r: dict) -> None:
    cmd = getattr(args, "tasktree_command", None) or "list"
    if cmd == "list":
        rows = r.get("trees", [])
        print(f"=== 任务树 ({len(rows)}) ===")
        for x in rows:
            print(f"  {x['plan_id']}  [{x['status']}]  {x['done']}/{x['leaves']} 叶"
                  f"  ({x['percent']}%)  project={x['project'] or '-'}")
        if not rows:
            print("  （无 — 用 `factory tasktree decompose --project <id>` 生成）")
    elif cmd == "show":
        t = r["tree"]
        s = r["summary"]
        print(f"任务树 {t.get('plan_id')}  [{t.get('status')}]  project={t.get('project_id')}")
        print(f"  节点 {s['kinds']}  ·  叶 {s['leaves']}  ·  完成 {s['done']} ({s['percent']}%)")
        if t.get("status") == "candidate":
            print("  ⚠ 候选态 —— 需 `factory tasktree confirm "
                  f"{t.get('plan_id')}` 才进执行")
        # ★ 粒度（判据: 每个叶能不能【用一句话写出验收】—— Founder 定的, 见 skill ⑥）
        try:
            from ai_factory_os.services.work import granularity as _gr
            g = _gr.summary(t.get("nodes") or [])
        except Exception:  # noqa: BLE001 — 判不了不影响看树
            g = {}
        if g:
            if g.get("oversized"):
                print(f"  ⚠ 粒度: {g['oversized']}/{g['leaves']} 个叶可能没拆到位"
                      f"（判据: {g['basis']}）")
                for s_ in g.get("samples") or []:
                    print(f"      · {s_['title'][:40]}  ← {s_['reasons'][0]}")
                print(f"      人可改: {g['how_to_fix']}")
            else:
                print(f"  ✓ 粒度: {g.get('leaves', 0)} 个叶都拆到位了（判据: {g.get('basis')}）")
        print("  ── 树:")
        for dom in [n for n in t.get("nodes", []) if n.get("kind") == "domain"]:
            print(f"    [{dom['kind']}] {dom['title']}")
            for lf in [n for n in t.get("nodes", []) if n.get("parent_id") == dom["id"]]:
                hint = f" hint={lf['role_hint']}" if lf.get("role_hint") else ""
                print(f"       └ [{lf['kind']}] {lf['title'][:56]}"
                      f"   [{str(lf.get('id'))[-8:]}]")
                print(f"          role={lf['required_role']}{hint}  change={lf['change_type'] or '-'}"
                      f"  files={lf['expected_files'] or '[]'}")
                print(f"          验收: {lf['acceptance'][:88]}")
                print(f"          依赖: {len(lf.get('depends_on') or [])} 个")
    elif cmd == "todo":
        # ★ 用户视图（Founder 设计）: 层级待办清单 —— 给**普通人**看的那一面。
        #   与 `show` 的区别: show 是专业视角（role/change/files/依赖数）;
        #   todo 只显示三样人能懂的: 人话名 · 状态 · 谁在做（+ 进度）。
        t = r["tree"]
        s = r["summary"]
        nodes = t.get("nodes", [])
        sid = str(t.get("project_id") or "")
        title = _todo_display_name(str(sid or t.get("plan_id") or "任务"))
        print()
        print(f"  {title}    {t.get('status')}")
        print(f"  {'━' * 46}  进度 {s['done']}/{s['leaves']} ({s['percent']}%)")
        if t.get("status") == "candidate":
            print("  ⚠ 还没确认（候选态）—— 确认后才会开始做")
        # ★ 关键路径说明（Founder: "待办清单中没有关键路径的说明, 需要如何判断"）
        todo = r.get("todo") or {}
        kp = todo.get("critical_path") or {}
        crit_ids = {ln.get("id") for ln in (todo.get("lines") or []) if ln.get("critical")}
        if kp.get("available"):
            head = " → ".join(str(x.get("name"))[:10] for x in (kp.get("chain_head") or []))
            print(f"  ★ 关键路径: {kp.get('total')} 条在链上（推迟它们 = 拖整棵树）")
            print(f"    判定依据: {kp.get('basis')}")
            if head:
                print(f"    链开头: {head} …")
            if kp.get("blockers"):
                b = "、".join(f"{x['name'][:12]}（等它 {x['waiting']} 条）" for x in kp["blockers"][:3])
                print(f"    谁最卡人: {b}")
            if kp.get("note"):
                print(f"    口径: {kp['note']}")
        elif kp.get("reason"):
            print(f"  ⚠ 关键路径算不出: {kp['reason']}（★ 不硬给一条假的）")
        print("  （★ = 在关键路径上; 其余是可并行的旁支）")
        # ★ 粒度提示（Founder 判据: 每个叶能不能【用一句话写出验收】不能 ⇒ 还没拆到位）
        try:
            from ai_factory_os.services.work import granularity as _gr
            g = _gr.summary(nodes)
        except Exception:  # noqa: BLE001
            g = {}
        if g.get("oversized"):
            print(f"  ⚠ 粒度: {g['oversized']}/{g.get('leaves')} 个叶可能没拆到位"
                  f"（{g.get('basis')}）⇒ 人可改: {g.get('how_to_fix')}")
        print()
        by_parent: dict[str, list] = {}
        for n in nodes:
            by_parent.setdefault(str(n.get("parent_id") or ""), []).append(n)

        def _walk(parent: str, depth: int) -> None:
            for n in by_parent.get(parent, []):
                if n.get("kind") == "project":
                    # 根节点不显示（它的名字就是标题那行）, 但要继续往下走
                    _walk(str(n.get("id") or ""), depth)
                    continue
                mark = _todo_mark(n.get("status"))
                who = str(n.get("assignee") or "").strip()
                if not who and n.get("kind") == "task":
                    caps = n.get("required_capabilities") or []
                    who = f"待派（需要: {_cap_word(caps[0])}）" if caps else "待派"
                indent = "  " * (depth + 2)
                name = _node_name(n)
                _show_id = bool(getattr(args, "ids", False))
                _idpart = f"   [{str(n.get('id'))[-8:]}]" if _show_id else ""
                _star = "★" if str(n.get("id")) in crit_ids else " "
                line = f"{indent}{mark} {_star} {name}{_idpart}"
                if n.get("kind") == "domain":
                    dd, tt = _node_progress(n, by_parent)
                    line += f"    {dd}/{tt}"
                elif depth > 0 and who:
                    line += f"    {who}"
                print(line)
                _walk(str(n.get("id") or ""), depth + 1)

        _walk("", 0)
        print()
        print("  （☐ 待办 · 🚧 进行中 · ✅ 完成 · ⛔ 已终止）")
    elif cmd == "flow":
        # ★ 功能链路图（看关系）: 有哪些模块 · 谁在谁前面 · 哪个是核心
        #   视图数据由服务层给（user_view.build_flow）—— 这里只排版, 不重算视图。
        f = r["flow"]
        if getattr(args, "mermaid", False):       # ★ 设计 §4.3: CLI 可渲染 mermaid
            print()
            print(_flow_mermaid(f))
            print()
            return
        more = f["domains"] - f["modules"]
        print()
        print(f"  功能链路    {r['tree'].get('plan_id')}    {f['modules']} 个模块"
              + (f"（另有 {more} 个细拆子模块 —— 明细见 `tasktree todo`）" if more > 0 else ""))
        print(f"  {'━' * 52}")
        print()
        show_ids = bool(getattr(args, "ids", False))
        for b in f["batches"]:
            print(f"  第 {b['level']} 批" + ("（可先做）" if b["level"] == 1 else "（等前面做完）"))
            for m in b["nodes"]:
                bits = []
                if m["deps"]:
                    bits.append("前置: " + " / ".join(m["deps"]))
                if m["core"]:
                    bits.append(f"★ 核心（被 {m['depended_by']} 个依赖）")
                elif m["depended_by"]:
                    bits.append(f"被 {m['depended_by']} 个依赖")
                if m["kids"]:
                    bits.append(f"{m['kids']} 个子模块")
                idpart = f"   [{m['id'][-8:]}]" if show_ids else ""
                tail = ("    " + " · ".join(bits)) if bits else ""
                print(f"    {_todo_mark(m['status'])} {m['name']}{idpart}{tail}")
            print()
        print("  （同一批可并行 · 批次之间有前后依赖; 前置 = 必须先做完的模块）")
    elif cmd == "workflow":
        # ★ 流程（"无固定流程(可编排)"）: 看有哪些 / 挂到树上 / 摘掉
        if r.get("listed"):
            print()
            print(f"  可用流程（{len(r['workflows'])} 个）")
            print(f"  {'━' * 60}")
            for w in r["workflows"]:
                mark = " ●已挂" if w.get("attached") else ""
                print(f"  {w['id']:<20} {w['name']:<10} {w['steps_total']} 步{mark}")
                print(f"      {' → '.join(w['steps'])}")
            print("\n  挂到树上: factory tasktree workflow <plan> --id <流程 id>")
            print("  摘掉    : factory tasktree workflow <plan> --id \"\"")
            return
        wf = r.get("attached") or ""
        print()
        print(f"  任务树 {r['plan_id']} 的流程: {wf or '（未挂 —— 现状: 一叶一次派活即完成）'}")
        if r.get("steps"):
            print(f"  {'━' * 60}")
            for i, s in enumerate(r["steps"], 1):
                print(f"  {i}. {s['name']}" + (f"   要求技能: {s['skill']}" if s.get("skill") else ""))
            print("  执行: 叶按上面顺序推进, 走完全部步骤才算完成（每步完成会交回待下一步）")
    elif cmd == "dataflow":
        # ★ 数据流程图（看数据）: 实体 · 谁碰它 · 实体之间怎么连
        if getattr(args, "mermaid", False):
            print()
            print(_dataflow_mermaid(r["dataflow"]))
            print()
            return
        _print_dataflow(r["dataflow"])
    elif cmd == "declare":
        # ★ 产线声明: 模块 → 读/写的数据实体（清单外的一律丢弃并计数）
        rows = r.get("declared") or []
        if r.get("manual"):                      # 手动改（人来纠产线的声明）
            row = rows[0]
            was = "  ".join(f"{e['name']}({e['access']})" for e in row.get("before") or [])
            now = "  ".join(f"{e['name']}({e['access']})" for e in row["entities"])
            print()
            print(f"  声明已改    {r['tree'].get('plan_id')}    {row['node']}")
            print(f"  {'━' * 52}")
            print()
            print(f"    改前: {was or '（原本没有声明）'}")
            print(f"    改后: {now or '（已清空 ⇒ 该模块回落成『线索』路径）'}")
            print()
            print("  （改完回到候选态; `tasktree dataflow <plan>` 看数据流程图）")
            return
        print()
        print(f"  产线声明    {r['tree'].get('plan_id')}    "
              f"实体清单 {len(r.get('entities_available') or [])} 个（来自项目真实数据模型）"
              + ("    【--dry-run 不落盘】" if r.get("dry_run") else ""))
        print(f"  {'━' * 52}")
        print()
        if r.get("skipped"):
            print(f"  （{r['skipped']} 个模块已有声明 ⇒ 跳过 —— 幂等, 不重复烧 token）")
        for row in rows:
            got = ("  ".join(f"{e['name']}({e['access']})" for e in row["entities"])
                   if row["entities"] else "（拿不准 ⇒ 空数组, 不瞎标）")
            pri = f"    优先级 {row['priority']}" if row.get("priority") else "    优先级（没给）"
            why = f" —— {row['reason'][:30]}" if row.get("reason") else ""
            staff = ("    谁做 " + "/".join(row.get("capabilities") or [])) if row.get("capabilities") else "    谁做（没给）"
            extra = f"    ⚠ 丢弃清单外名字 {row['dropped']} 个" if row["dropped"] else ""
            print(f"    {row['node']:<14} → {got}{pri}{staff}{why}{extra}")
        print()
        if r.get("dropped_total"):
            print(f"  ⚠ 共丢弃清单外的名字 {r['dropped_total']} 个（LLM 编的, 没写进树）")
        if not rows:
            print("  （没有需要声明的模块）")
        print("  （声明后 `tasktree dataflow <plan>` 看数据流程图 —— 线会从虚线变实线）")
    elif cmd == "priority":
        # ★ 优先级: 看分布 / 人工设 / 自动导出（仲裁: 人工 > 产线声明 > 关键路径自动）
        dist = r.get("distribution") or {}
        src = r.get("sources") or {}
        print()
        print(f"  优先级    {r['tree'].get('plan_id')}    {r.get('did')}"
              + (f" · 写入 {r.get('written')} 条" if r.get("written") else ""))
        print(f"  {'━' * 52}")
        print()
        print("  生效分布: " + " · ".join(f"{k} {dist.get(k, 0)}" for k in ("P0", "P1", "P2", "P3")))
        st = r.get("stored") or {}
        if st:
            print(f"    已落盘 {st.get('stored', 0)} 条 · 自动兜底 {st.get('fallback', 0)} 条"
                  + ("（★ 兜底只是【临时算给你看】，未写进树 ⇒ 跑 --auto 固化）" if st.get("fallback") else ""))
        print("  来源分布: " + " · ".join(f"{k} {v}" for k, v in sorted(src.items())))
        if r.get("skipped"):
            print(f"  ★ 跳过 {len(r['skipped'])} 条 —— 已由人工/产线声明定过（人工最高, 自动不许覆盖）")
        if r.get("missing"):
            print(f"  ⚠ 找不到的节点 {len(r['missing'])} 个（未静默）")
        if r.get("invalid"):
            print(f"  ⚠ 非法值被拒 {len(r['invalid'])} 个（只收 P0~P3）")
        p0 = [(nid, v) for nid, v in (r.get("priority") or {}).items() if v["priority"] == "P0"][:5]
        if p0:
            print("  P0 举例:")
            for nid, v in p0:
                print(f"    · [{v['source']}] {v.get('reason', '')[:46]}")
        print()
        print("  （取值 P0~P3; 调度器排序原文: 先到期 → 优先级 → 便宜的先做 → 声明序）")
        print("  （人工改: --set-node <id> --value P1 [--why 理由]; 页面点徽标亦可）")
    elif cmd == "staffing":
        # ★ 谁做: 派工覆盖 + 舰队可用角色（调度器能不能派出去就看这个）
        print()
        print(f"  派工(谁做)    {r['tree'].get('plan_id')}    {r.get('did')}"
              + (f" · 写入 {r['written']} 条" if r.get("written") else ""))
        print(f"  {'━' * 52}")
        print()
        avail = r.get("roles") or {}
        print("  舰队可用角色: " + " · ".join(f"{k} {v}人" for k, v in
              sorted(avail.items(), key=lambda kv: -kv[1])))
        cov = f"  派工覆盖: 叶 {r['staffed']}/{r['leaves']}"
        if r.get("unstaffed"):
            print(cov + f" · ⚠ 还有 {r['unstaffed']} 条没说谁做 ⇒ 调度器判 unresolved, 派不出去")
        else:
            print(cov + " ✓")
        if r.get("by_role"):
            print("  按角色: " + " · ".join(f"{k} {v} 条" for k, v in
                  sorted(r["by_role"].items(), key=lambda kv: -kv[1])))
        if r.get("dropped"):
            print(f"  ⚠ 清单外的值被丢弃 {len(r['dropped'])} 个: {', '.join(r['dropped'][:5])}")
        print()
        print("  （调度器匹配规则: 节点 required_capabilities ∩ 成员【role】—— 必须是真实角色名, 不是技能词）")
        print("  （人工改: --node <id> --role developer [--cap developer,tester]）")
    elif cmd == "edit":
        n = r.get("node") or {}
        print(f"✔ {r.get('action')}: {_todo_display_name(n.get('title'))}")
        print(f"  节点: {str(n.get('id'))[-8:]}")
        if n.get("acceptance"):
            print(f"  验收: {n['acceptance'][:80]}")
        if n.get("assignee"):
            print(f"  指派: {n['assignee']}")
        st = r.get("status") or (r.get("tree") or {}).get("status") or "candidate"
        print(f"  ★ 树已回到【候选态】（{st}）—— 需重新确认:")
        print(f"     factory tasktree confirm {r['tree'].get('plan_id')}")
    elif cmd == "translate":
        tot = r.get("total", 0)
        got = r.get("applied", 0)
        if not tot:
            print("  · 无需翻译（都有 display_name 了 —— 用户改过的不覆盖）")
        else:
            print(f"  ✔ 人话名: {got}/{tot} 个已写入 display_name")
            if got < tot:
                print(f"  ⚠ 有 {tot - got} 个没翻成（保持规则派生, 不影响显示）")
        print("  ★ 树已回到候选态, 需重新确认")
    elif cmd == "expand":
        print()
        print(f"  细拆结果: {r.get('done')} 个节点已展开 · {r.get('stopped', 0)} 个判定为一件事（到底）")
        print(f"  {'━' * 50}")
        for x in r.get("results") or []:
            if x.get("error"):
                print(f"  ✗ {x['module'][:22]} — {x['error'][:60]}")
            else:
                lv = f"[第{x.get('depth')}层] " if x.get('depth') else ""
                print(f"  ✔ {lv}{x['module'][:22]}  →  {x['kids']} 个子任务")
                for ttl in x.get("titles") or []:
                    print(f"        · {ttl}")
        print()
        print("  ★ 树已回到候选态 —— 用 `tasktree todo` 看结果, `tasktree confirm` 确认")
    elif cmd == "decompose":
        t = r["tree"]
        s = r["summary"]
        print(f"✔ 任务树已生成: {t['plan_id']}  [{t['status']}]")
        print(f"  节点 {s['kinds']} · 叶 {s['leaves']}")
        print(f"  落盘: {t.get('_saved_to')}")
        print(f"  边界纪律: {t.get('limits')}")
        print(f"  ⚠ 候选态 —— 人工确认后进执行: factory tasktree confirm {t['plan_id']}")
    elif cmd == "confirm":
        t = r["tree"]
        print(f"✔ 任务树已确认: {t['plan_id']}  [{t['status']}]  at {t.get('confirmed_at')}")
        print("  下一步: 执行层按拓扑序跑叶任务（factory run / exec）")


def _format_failure(error: str) -> str:
    """统一失败输出（S10-044 Task 001）: ❌ Failed + Reason + Solution 到 stdout。

    用户失败时只看 stdout —— 错误必须到 stdout（stderr 常被吞/忽略）。
    与老 CLI `cli_factory._format_failure` 行为一致。
    """
    low = error.lower()
    if "api key" in low or "未设置" in error:
        solution = "请设置对应 Provider 的 API Key（环境变量），再重试"
    elif "provider not found" in low:
        solution = "factory config check 查看可用 Provider; 或用 --provider 指定已注册的"
    elif "project dir not found" in low or "项目" in error and "不存在" in error:
        solution = "factory project create --repo-path <目录> 先创建/接入项目"
    elif "sandbox" in low:
        solution = "检查沙箱目录权限与磁盘空间, 或重试"
    else:
        solution = "查看上方 Reason; 必要时 factory doctor 做环境诊断"
    return f"❌ Failed\n\nReason:\n  {error}\n\nSolution:\n  {solution}"


def _dispatch_run(ctx: FactoryContext, args: Any) -> dict:
    # ★ 第 1 刀: 带 --plan ⇒ 跑整棵任务树（scheduler 平面）, 与逐个 --task 分开
    if str(getattr(args, "plan", "") or ""):
        return cmd_run_plan(ctx, args)
    """factory run —— 从【目标】创建并执行（薄代理 exec CLI）。

    与老 CLI `cli_factory.run_cmd`（L10147）行为一致:
      · --task 与 --objective 二选一（都缺 → rc 2）; --project 必填
      · 仅 --objective（无 task 锚点）→ 自动生成 E2-OBJ-* 后透传
    """
    import uuid

    task = getattr(args, "task", None)
    objective = getattr(args, "objective", None)
    if not task and not objective:
        raise CliError("[E4001] 错误: --task 必填 (任务 ID) / --objective 必填 "
                       "(自然语言目标), 二选一 (建议: 二选一补齐后重试)", exit_code=2)
    if not getattr(args, "project", None):
        raise CliError("错误: --project 必填 (项目目录)", exit_code=2)
    if not task:
        args.task = f"E2-OBJ-{uuid.uuid4().hex[:8]}"
    ctx.root.mkdir(parents=True, exist_ok=True)

    try:
        import exec.cli as exec_cli
        result = exec_cli.cmd_exec_run(root=ctx.root, args=args)
    except Exception as exc:  # noqa: BLE001 — 失败安全: 底层异常 → 明确错误, 不吞不裸抛
        return {"action": "run", "failed": True, "error": f"exec CLI 执行失败 — {exc}",
                "exit_code": 1}
    ok = bool(result.get("ok")) and int(result.get("exit_code", 0) or 0) == 0
    return {"action": "run", "failed": not ok, "proxy": exec_cli, "args": args,
            "result": result, "exit_code": int(result.get("exit_code", 0) or 0)}


def _print_run(r: dict) -> None:
    # ★ run --plan 的返回结构与 --task 不同 ⇒ 分流（否则 KeyError: 'proxy'）
    if r.get("plan_id"):
        _print_run_plan(r)
        return
    if r.get("failed"):
        error = r.get("error") or (r.get("result") or {}).get("error") \
            or (r.get("result") or {}).get("status") or "执行失败"
        print(_format_failure(error))
        return
    proxy, args, result = r["proxy"], r["args"], r["result"]
    if getattr(args, "json", False) and result.get("ok"):
        import json as _json
        print(_json.dumps(result, ensure_ascii=False, indent=2))
    elif int(result.get("exit_code", 0)) != 2:
        proxy._print_result(args, result)


def _dispatch_run_status(ctx: FactoryContext, args: Any) -> dict:
    """factory run-status —— 执行结果查询（薄代理 exec CLI）。

    与老 CLI `cli_factory.run_status`（L10162 附近）行为一致; 含【可读化】渲染
    （从 exec/<id>.report.md 补出"目标/做了什么" —— 数据本来就有, 只是 CLI 不展示）。
    """
    ctx.root.mkdir(parents=True, exist_ok=True)
    try:
        import exec.cli as exec_cli
        result = exec_cli.cmd_exec_status(root=ctx.root, args=args)
    except Exception as exc:  # noqa: BLE001 — 失败安全
        raise CliError(f"exec CLI 查询失败 — {exc}", exit_code=1) from exc
    return {"action": "run-status", "proxy": exec_cli, "args": args, "result": result,
            "root": ctx.root}


def _print_run_status(r: dict) -> None:
    """可读化渲染（照老 CLI `_print_exec_readable` 逐字实现）。

    数据本来就有（exec/<id>.report.md）—— 只是 CLI 不展示。
    """
    import re as _re

    proxy, args, result = r["proxy"], r["args"], r["result"]
    if not (isinstance(result, dict) and result.get("results")):
        proxy._print_result(args, result)
        return
    root = r["root"]
    rows = result.get("results") or []
    print(f"执行结果 {len(rows)} 条 (审批 {result.get('approval_count', 0)} 条)")
    for x in rows:
        rid = str(x.get("id") or "?")
        status = str(x.get("status") or "?")
        mark = "✓" if status.lower().startswith("success") else "✗"
        objective = summary = ""
        rep = root / "exec" / f"{rid}.report.md"
        if rep.is_file():
            try:
                txt = rep.read_text(encoding="utf-8")
                m = _re.search(r"^- objective: (.+)$", txt, _re.M)
                objective = (m.group(1).strip() if m else "")
                m2 = _re.search(r"## What the agent did\n(.+?)(?:\n\n|$)", txt, _re.S)
                summary = (m2.group(1).strip() if m2 else "")
                if summary.startswith("("):
                    summary = ""
            except OSError:
                pass
        what = (summary or objective or "(报告缺失)")[:64]
        extra = ""
        if rep.is_file():
            try:
                txt = rep.read_text(encoding="utf-8")
                m3 = _re.search(r"diff lines: (\d+)", txt)
                m4 = _re.search(r"result: (\w+)", txt)
                bits = []
                if m3:
                    bits.append(f"{m3.group(1)} 行补丁")
                if m4:
                    bits.append(f"验证 {m4.group(1)}")
                m5 = _re.search(r"duration: ([\d.]+s)", txt)
                if m5:
                    bits.append(m5.group(1))
                extra = ("  (" + " · ".join(bits) + ")") if bits else ""
            except OSError:
                pass
        print(f"  {rid}  {mark}{status:<8} {what}{extra}")


def _dispatch_backup(ctx: FactoryContext, args: Any) -> dict:
    """factory backup {create|list|restore} —— 运维域（底层已在新地基: services/operations/backup）。

    与老 CLI `cli_factory.backup`（L9400 注册 / 对应 handler）行为一致。
    """
    from ai_factory_os.services.operations.backup import (
        create_backup, list_backups, restore_backup,
    )

    action = getattr(args, "backup_command", "list") or "list"
    bdir = getattr(args, "dir", None) or None

    if action == "create":
        r = create_backup(ctx.root, bdir)
        if not r.get("ok"):
            raise CliError(f"备份失败: {r.get('error')}", exit_code=1)
        return {"action": "create", "result": r}
    if action == "list":
        return {"action": "list", "rows": list_backups(bdir)}

    bf = getattr(args, "backup_file", None) or ""
    if not bf:
        raise CliError("用法: factory backup restore <备份文件>", exit_code=2)
    r = restore_backup(ctx.root, bf)
    if not r.get("ok"):
        raise CliError(f"恢复失败: {r.get('error')}", exit_code=1)
    return {"action": "restore", "result": r}


def _print_backup(sub: str, r: dict) -> None:
    if sub == "create":
        x = r["result"]
        print(f"✅ 备份完成: {x['file']} ({x['size'] / 1024:.1f} KB, {x['count']} 个文件)")
        return
    if sub == "list":
        rows = r["rows"]
        if not rows:
            print("（暂无备份 — 运行 factory backup create）")
            return
        print(f"=== 数据备份 ({len(rows)}) ===")
        for row in rows:
            print(f"  - {row.get('name', row['file'])} ({row['size'] / 1024:.1f} KB)")
        return
    x = r["result"]
    print(f"✅ 恢复完成: {x['restored']} 个文件 (来自 {x['file']})")


def _dispatch_memory(ctx: FactoryContext, args: Any) -> dict:
    """`factory memory list|add` —— 项目级记忆的读写入口（一数据一源: 仍走 MemoryStore）。"""
    from ai_factory_os.services.conversation.project_memory import MemoryStore

    cmd = getattr(args, "memory_command", "") or "list"
    pid = str(getattr(args, "project", "") or "")
    if not pid:
        raise CliError("--project 必填（项目级记忆按项目隔离）", exit_code=2)
    ms = MemoryStore.load(ctx.root, pid)
    if cmd == "add":
        ok = ms.add(str(args.text), source="cli", kind=str(args.kind),
                    authority=str(args.authority))
        if not ok:
            raise CliError("记忆没写进去（落盘失败或文本为空）—— 没记住, 别当成功", exit_code=1)
        return {"ok": True, "action": "memory_add", "project_id": pid,
                "entries": len(ms.entries)}
    items = ms.recent(n=int(getattr(args, "n", 10) or 10))
    return {"ok": True, "action": "memory_list", "project_id": pid,
            "count": len(items), "items": items,
            "inject_block": ms.inject_block(n=4)}


def _print_memory(cmd: str, r: dict) -> None:
    """memory list|add 的人话输出。"""
    if r.get("action") == "memory_add":
        print(f"✔ 已记住（项目 {r['project_id']}, 现有 {r['entries']} 条）")
        return
    items = r.get("items") or []
    print(f"▲ 项目记忆: {r['project_id']} · {r.get('count', 0)} 条")
    if not items:
        print("  （空 —— 执行完成后会自动留经验; 也可以 memory add 手工加）")
    for m in items:
        print(f"  · [{m.get('kind')}|{m.get('authority')}] {str(m.get('text'))[:76]}")
        print(f"    来源 {str(m.get('source'))[:40]} · {str(m.get('ts'))[:19]}")

def _dispatch_knowledge(ctx: FactoryContext, args: Any) -> dict:
    if args.knowledge_command == "status":
        return cmd_knowledge_status(ctx, args)
    if args.knowledge_command == "reindex":
        return cmd_knowledge_reindex(ctx, args)
    raise CliError(f"unknown knowledge command: {args.knowledge_command}", exit_code=2)


def _dispatch_project(ctx: FactoryContext, args: Any) -> dict:
    if args.project_command == "list":
        return cmd_project_list(ctx, args)
    if args.project_command == "show":
        return cmd_project_show(ctx, args)
    if args.project_command == "org":
        return cmd_project_org(ctx, args)
    if args.project_command == "adopt":
        return cmd_project_adopt(ctx, args)
    raise CliError(f"unknown project command: {args.project_command}", exit_code=2)


def _print_provider_setup(sub: str, r: dict) -> None:
    """provider add / doctor 的输出（说人话: 做了什么 + 下一步做什么）。"""
    if sub == "add":
        print(f"\n  ✓ 已配置 provider: {r.get('provider')}")
        print(f"    端点   : {r.get('base_url') or '(默认)'}")
        print(f"    模型   : {', '.join(r.get('models') or []) or '(未指定)'}")
        print(f"    key 来源: {r.get('env_ref')} ← {r.get('key_source')}")
        sm = r.get("smoke") or {}
        if sm.get("attempted"):
            print(f"    试连   : {'✓ ' + str(sm.get('note','')) if sm.get('ok') else '✗ ' + str(sm.get('error'))}")
        else:
            print("    试连   : 已跳过（未提供 key 或 --skip-test）")
        print(f"\n  下一步: {r.get('next')}\n")
    else:
        print(f"\n  provider doctor: {r.get('summary')}")
        for c in (r.get("checks") or []):
            print(f"    {'✓' if c.get('ok') else '✗'} {str(c.get('item')):<30} {c.get('detail')}")
        print(f"\n  {r.get('next')}\n")


def _dispatch_tool(ctx: FactoryContext, args: Any) -> dict:
    """factory tool {list,show,run} —— 工具集的列出/查看/调用。

    照 Hermes 的 CLI 惯例: **资源做名词(tool) · 操作做动词(list/show/run)**, help 说清"能干什么"。
    """
    from ai_factory_os.plugins.tools import registry as R

    sub = str(getattr(args, "tool_command", "") or "")
    if sub == "list":
        rows = R.list_tools(stage=str(getattr(args, "stage", "") or ""))
        st = str(getattr(args, "status", "") or "")
        if st:
            rows = [r for r in rows if str((r if isinstance(r, dict) else {}).get("status", "")) == st]
        return {"count": len(rows), "tools": rows, "summary": R.summary()}
    if sub == "show":
        return {"tool": R.get_tool(str(args.tool_id))}
    if sub == "run":
        # ★ 真调用: 走 plugins/tools/adapters 的统一签名 fn(root, project_id, params)
        from ai_factory_os.plugins.tools import adapters as A

        tid = str(args.tool_id)
        params: dict[str, Any] = {}
        for kv in (getattr(args, "param", None) or []):
            if "=" in str(kv):
                k, _, v = str(kv).partition("=")
                params[k.strip()] = v.strip()
        fn = getattr(A, tid, None)
        if not callable(fn):
            raise CliError(
                f"工具未接适配器: {tid}（可用: code_search/scan/list_tasks/read_doc/"
                f"backup/git_status/monitor/quality_score）", exit_code=2)
        return {"tool_id": tid,
                "result": fn(str(ctx.root), str(getattr(args, "project", "") or ""), params)}
    raise CliError(f"unknown tool command: {sub}", exit_code=2)


def _print_tool(sub: str, r: dict) -> None:
    if sub == "list":
        s = r.get("summary") or {}
        print(f"  工具 {r.get('count')} 个 · 共 {s.get('total')} · {s.get('by_status')}")
        for x in (r.get("tools") or [])[:40]:
            d = x if isinstance(x, dict) else {}
            print(f"    {str(d.get('id')):<22} {str(d.get('name'))[:14]:<16} "
                  f"{str(d.get('stage')):<4} {str(d.get('status'))}")
    elif sub == "show":
        t = r.get("tool")
        print("  " + (json.dumps(t, ensure_ascii=False, indent=2) if t else "（未找到该工具）"))
    else:
        print(f"  {r.get('tool_id')} → {json.dumps(r.get('result'), ensure_ascii=False)[:600]}")


def _dispatch_mcp(ctx: FactoryContext, args: Any) -> dict:
    """factory mcp {scan,list,test} —— MCP 服务器的扫描/列出/连接测试。"""
    sub = str(getattr(args, "mcp_command", "") or "")
    if sub == "scan":
        from ai_factory_os.plugins.tools.discovery import discover_mcp_servers

        rows = discover_mcp_servers()
        return {"count": len(rows),
                "servers": [r if isinstance(r, dict) else r.__dict__ for r in rows]}
    if sub == "list":
        from ai_factory_os.infrastructure.plugins.kernel import list_plugins

        try:
            got = list_plugins(ctx.root)
        except TypeError:                     # 签名不同 ⇒ 退回无参调用
            got = list_plugins()
        rows = got if isinstance(got, list) else list(got or [])
        return {"count": len(rows),
                "plugins": [r if isinstance(r, (dict, str)) else getattr(r, "id", str(r))
                            for r in rows]}
    if sub == "test":

        mid = str(args.mcp_id)
        return {"mcp_id": mid, "connected": False,
                "note": f"MCPClient 可用（真连接需 {mid} 的启动命令；客户端构造见 plugins/mcp/client.py）"}
    raise CliError(f"unknown mcp command: {sub}", exit_code=2)


def _print_mcp(sub: str, r: dict) -> None:
    if sub == "scan":
        print(f"  发现 MCP 服务器 {r.get('count')} 个:")
        for s in (r.get("servers") or []):
            print(f"    {str(s.get('id') or s.get('name')):<20} {str(s.get('path') or '')[:56]}")
    elif sub == "list":
        print(f"  已注册 MCP/插件 {r.get('count')} 个")
    else:
        print(f"  {r.get('mcp_id')}: connected={r.get('connected')} {r.get('error') or r.get('note') or ''}")


def _dispatch_discover(ctx: FactoryContext, args: Any) -> dict:
    """factory discover [all|ai-clis|mcp|projects] —— 扫描本机可用的外部能力。

    ★ 这是「扫描 → 注册 → 调用」里的**第一步**。
    """
    from ai_factory_os.plugins.tools.discovery import (
        discover_ai_clis, discover_all, discover_mcp_servers,
    )

    what = str(getattr(args, "what", "all") or "all")
    if what == "ai-clis":
        rows = discover_ai_clis()
    elif what == "mcp":
        rows = discover_mcp_servers()
    elif what == "projects":
        from ai_factory_os.plugins.factories.loader import discover_projects

        ex = ctx.root / "examples"
        return {"what": what, "count": 0,
                "projects": discover_projects(ex) if ex.is_dir() else []}
    else:
        rows = discover_all()
    return {"what": what, "count": len(rows),
            "items": [r if isinstance(r, dict) else r.__dict__ for r in rows]}


def _print_discover(what: str, r: dict) -> None:
    print(f"  扫描 {r.get('what') or what}: 发现 {r.get('count')} 项")
    for x in (r.get("items") or [])[:20]:
        d = x if isinstance(x, dict) else {}
        print(f"    {str(d.get('id') or d.get('name')):<20} "
              f"{str(d.get('kind') or d.get('type') or ''):<12} "
              f"{str(d.get('path') or d.get('command') or '')[:50]}")


def _dispatch_llm(ctx: FactoryContext, args: Any) -> dict:
    """factory llm serve —— 起 OpenAI 兼容端点（LLM 路由对外产品面）。

    阻塞直到 Ctrl-C。暴露 POST /v1/chat/completions · GET /health · GET /v1/models;
    任何 OpenAI 客户端把 base_url 指向 http://<host>:<port>/v1 即可接入。
    """
    from ai_factory_os.infrastructure.llm.serve import serve

    serve(host=str(getattr(args, "host", "127.0.0.1")), port=int(getattr(args, "port", 8787)))
    return {"ok": True, "stopped": True}


def _print_llm(sub: str, r: dict) -> None:
    print(f"  llm {sub}: {'已停止' if r.get('stopped') else '完成'}")


def _dispatch_provider(ctx: FactoryContext, args: Any) -> dict:
    """provider list/show/test/usage/stats/compare/recommend 分发 (Phase 8A
    ADR-0022 + 8B-2 ADR-0024)。"""
    if args.provider_command == "list":
        return cmd_provider_list(ctx, args)
    if args.provider_command == "show":
        return cmd_provider_show(ctx, args)
    if args.provider_command == "test":
        return cmd_provider_test(ctx, args)
    if args.provider_command == "usage":
        return cmd_provider_usage(ctx, args)
    if args.provider_command == "stats":
        return cmd_provider_stats(ctx, args)
    if args.provider_command == "compare":
        return cmd_provider_compare(ctx, args)
    if args.provider_command == "recommend":
        return cmd_provider_recommend(ctx, args)
    if args.provider_command == "add":
        return cmd_provider_add(ctx, args)
    if args.provider_command == "doctor":
        return cmd_provider_doctor(ctx, args)
    raise CliError(f"unknown provider command: {args.provider_command}", exit_code=2)


def _dispatch_workspace(ctx: FactoryContext, args: Any) -> dict:
    if args.workspace_command == "init":
        return cmd_workspace_init(ctx, args)
    if args.workspace_command == "show":
        return cmd_workspace_show(ctx, args)
    raise CliError(f"unknown workspace command: {args.workspace_command}", exit_code=2)


def _dispatch_git(ctx: FactoryContext, args: Any) -> dict:
    if args.git_command == "status":
        return cmd_git_status(ctx, args)
    if args.git_command == "diff":
        return cmd_git_diff(ctx, args)
    if args.git_command == "commits":
        return cmd_git_commits(ctx, args)
    raise CliError(f"unknown git command: {args.git_command}", exit_code=2)


def _dispatch_change(ctx: FactoryContext, args: Any) -> dict:
    if args.change_command == "plan":                       # ★ mem-7: 影响面（只分析不改）
        return cmd_change_plan(ctx, args)
    if args.change_command == "commits":
        return cmd_change_commits(ctx, args)
    if args.change_command == "analyze":
        return cmd_change_analyze(ctx, args)
    if args.change_command == "validate":
        return cmd_change_validate(ctx, args)
    if args.change_command == "triggers":
        if args.trigger_command == "list":
            return cmd_change_triggers_list(ctx, args)
        if args.trigger_command == "register":
            return cmd_change_triggers_register(ctx, args)
        raise CliError(f"unknown change triggers command: {args.trigger_command}", exit_code=2)
    if args.change_command == "evaluate":
        return cmd_change_evaluate(ctx, args)
    if args.change_command == "workflows":
        return cmd_change_workflows(ctx, args)
    raise CliError(f"unknown change command: {args.change_command}", exit_code=2)


def _dispatch_product(ctx: FactoryContext, args: Any) -> dict:
    """product idea/approval/workflow/generate/experience/develop/ux 分发 (Phase 9A ADR-0026 + 9B ADR-0027)。"""
    if args.product_command == "develop":
        return cmd_product_develop(ctx, args)
    if args.product_command == "breakdown":
        return cmd_product_breakdown(ctx, args)
    if args.product_command == "ux":
        return cmd_product_ux(ctx, args)
    if args.product_command == "idea":
        if args.idea_command == "create":
            return cmd_product_idea_create(ctx, args)
        if args.idea_command == "list":
            return cmd_product_idea_list(ctx, args)
        if args.idea_command == "show":
            return cmd_product_idea_show(ctx, args)
        raise CliError(f"unknown product idea command: {args.idea_command}", exit_code=2)
    if args.product_command == "approval":
        if args.approval_command == "request":
            return cmd_product_approval_request(ctx, args)
        if args.approval_command == "decide":
            return cmd_product_approval_decide(ctx, args)
        if args.approval_command == "list":
            return cmd_product_approval_list(ctx, args)
        if args.approval_command == "history":
            return cmd_product_approval_history(ctx, args)
        raise CliError(f"unknown product approval command: {args.approval_command}", exit_code=2)
    if args.product_command == "workflow":
        if args.workflow_command == "start":
            return cmd_product_workflow_start(ctx, args)
        if args.workflow_command == "status":
            return cmd_product_workflow_status(ctx, args)
        if args.workflow_command == "resume":
            return cmd_product_workflow_resume(ctx, args)
        raise CliError(f"unknown product workflow command: {args.workflow_command}", exit_code=2)
    if args.product_command == "generate":
        return cmd_product_generate(ctx, args)
    if args.product_command == "experience":
        if args.experience_command == "list":
            return cmd_product_experience_list(ctx, args)
        if args.experience_command == "record":
            return cmd_product_experience_record(ctx, args)
        raise CliError(f"unknown product experience command: {args.experience_command}", exit_code=2)
    if args.product_command == "lifecycle":  # Phase 9d (ADR-0029)
        if args.lifecycle_command == "start":
            return cmd_product_lifecycle_start(ctx, args)
        if args.lifecycle_command == "status":
            return cmd_product_lifecycle_status(ctx, args)
        if args.lifecycle_command == "advance":
            return cmd_product_lifecycle_advance(ctx, args)
        if args.lifecycle_command == "templates":
            return cmd_product_lifecycle_templates(ctx, args)
        raise CliError(f"unknown product lifecycle command: {args.lifecycle_command}", exit_code=2)
    raise CliError(f"unknown product command: {args.product_command}", exit_code=2)


def _dispatch_intelligence(ctx: FactoryContext, args: Any) -> dict:
    """Intelligence 命令派发 (Phase 10A-2/10A-3, ADR-0031/0032)。"""
    if args.intelligence_command == "decision":
        if args.decision_command == "create":
            return cmd_intelligence_decision_create(ctx, args)
        raise CliError(
            f"unknown intelligence decision command: {args.decision_command}",
            exit_code=2,
        )
    if args.intelligence_command == "recommend":
        return cmd_intelligence_recommend(ctx, args)
    if args.intelligence_command == "experience":
        if args.experience_command == "list":
            return cmd_intelligence_experience_list(ctx, args)
        if args.experience_command == "evaluate":
            return cmd_intelligence_experience_evaluate(ctx, args)
        raise CliError(
            f"unknown intelligence experience command: {args.experience_command}",
            exit_code=2,
        )
    raise CliError(
        f"unknown intelligence command: {args.intelligence_command}", exit_code=2
    )


def _dispatch_console(ctx: FactoryContext, args: Any) -> dict:
    """console dashboard/approvals 分发 (Phase 11A, ADR-0034: Human Console 只读)。"""
    if args.console_command == "dashboard":
        return cmd_console_dashboard(ctx, args)
    if args.console_command == "approvals":
        return cmd_console_approvals(ctx, args)
    if args.console_command in ("activity", "projects", "agents", "decisions", "cost", "experience"):
        return cmd_console_domain(ctx, args)
    raise CliError(f"unknown console command: {args.console_command}", exit_code=2)


def _run_serve(ctx: FactoryContext, args: Any) -> int:
    """`factory serve` —— 一条命令起 API + 最小界面（只读视图; Ctrl-C 停 ✓）。

    ★ 2026-09-22（Founder 点单"发布交付链: factory serve 一条命令起 API + 最小界面"）:
      以前要记"哪个脚本 + 哪个端口 + 什么参数" ✗ ⇒ 现在一条命令, 起来后把地址打给人看 ✓。
    """
    import os as _os

    _host = str(getattr(args, "host", "127.0.0.1") or "127.0.0.1")
    _port = int(getattr(args, "port", 8011) or 8011)
    _os.environ.setdefault("FACTORY_ROOT", str(getattr(ctx, "root", "")))
    print("  AI Factory OS · 只读界面已启动")
    print(f"    地址: http://{_host}:{_port}/")
    print(f"    API : http://{_host}:{_port}/api/health · /api/trees …")
    print(f"    数据: {getattr(ctx, 'root', '')}（只读 ✓ 不改数据）")
    print("    Ctrl-C 停")
    try:
        import uvicorn

        from apps.api.main import app as _app

        uvicorn.run(_app, host=_host, port=_port, log_level="warning")
    except KeyboardInterrupt:
        pass
    return 0


def cmd_console_domain(ctx: FactoryContext, args: Any) -> dict:
    """factory console <域> —— 七域**下钻**（只读; 复用 dashboard 同一份快照 ⇒ 口径一致 ✓）。

    ★ 2026-09-22（Founder: "kanban 的'活动'域" + "都要"）: 以前只有七域汇总, 想看某域里**每条**得自己猜 ✗。
    """
    from ai_factory_os.infrastructure.events.types import EventType

    from apps.cli.commands import SOURCE, _open_console_service   # 复用 console 那套（同一份快照 ✓）

    dom = str(args.console_command)
    with ctx.logger_scope() as logger:
        service = _open_console_service(ctx)
        if service is None:
            raise CliError("factory-console 未安装 (缺 factory-console/ 包)", exit_code=7)
        snap = service.dashboard(recent_limit=int(getattr(args, "limit", 20) or 20))
        ev = logger.record(EventType.CONSOLE_VIEWED, source=SOURCE, stage="viewed",
                           action=f"view console {dom}", result="OK")
        return {"domain": dom, "snapshot": snap, "event_seq": getattr(ev, "seq", None)}


def _dispatch_org(ctx: FactoryContext, args: Any) -> dict:
    """org **member** 分发（舰队成员归属 —— 设计内: 派活按归属筛人 ✓）。
    ★ 2026-09-23: 老区命令面 (company/employee/authority/knowledge) 已按 Founder 指示删除 ✗"""
    if args.org_command == "member":
        if args.member_command == "list":
            return cmd_org_member_list(ctx, args)
        if args.member_command == "set":
            return cmd_org_member_set(ctx, args)
        raise CliError(f"unknown org member command: {args.member_command}", exit_code=2)
    raise CliError(f"unknown org command: {args.org_command}", exit_code=2)


def _dispatch_exec(ctx: FactoryContext, args: Any) -> dict:
    """exec run/status/approval 分发 (Phase A, ADR-0037: factory-exec Extension —
    缺包 rc 7, 其余命令零影响; 执行失败 rc 1 = 结果对象携带 status=failed, 命令
    本身成功)。"""
    if args.exec_command == "run":
        return cmd_exec_run(ctx, args)
    if args.exec_command == "status":
        return cmd_exec_status(ctx, args)
    if args.exec_command == "approval":
        if args.approval_command == "approve":
            return cmd_exec_approval_approve(ctx, args)
        if args.approval_command == "deny":
            return cmd_exec_approval_deny(ctx, args)
        if args.approval_command == "apply":
            return cmd_exec_approval_apply(ctx, args)
        if args.approval_command == "list":
            return cmd_exec_approval_list(ctx, args)
        raise CliError(f"unknown exec approval command: {args.approval_command}", exit_code=2)
    raise CliError(f"unknown exec command: {args.exec_command}", exit_code=2)


# ------------------------------------------------------------------ 输出

def _print_output(args: Any, result: dict) -> None:
    if args.json:
        # ★ 2026-09-20 修: 各命令的返回值里可能夹着非 JSON 对象（`args`=Namespace / 早先还有 module /
        #   偶尔是 dataclass）⇒ 原来在这里直接 dumps 会**崩**（实测: `factory --json create project`
        #   连崩两次: module → Namespace）。JSON 出口必须**兜底可序列化**（default=str）,
        #   否则命令本身成功了、用户却只看到 traceback。
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return
    if args.command == "init":
        _print_init(result)
    elif args.command == "task":
        _print_task(args.task_command, result)
    elif args.command == "conversation":
        _dom_conversation.render(result)
    elif args.command == "chain":
        _dom_chain.render(result)
    elif args.command == "event":
        _print_event_logs(result)
    elif args.command == "status":
        _print_status(result)
    elif args.command == "validate":
        _print_validate(result)
    elif args.command == "agent":
        _print_agent(args.agent_command, result)
    elif args.command == "skill":
        _print_skill(args.skill_command, result)
    elif args.command == "workflow":
        _print_workflow(args.workflow_command, result)
    elif args.command == "runtime":
        _print_runtime(args, result)
    elif args.command == "execution":
        _print_execution(args.execution_command, result)
    elif args.command == "run":
        _print_run(result)
    elif args.command == "run-status":
        _print_run_status(result)
    elif args.command == "checkpoint":
        _print_checkpoint(args.checkpoint_command, result)
    elif args.command == "backup":
        _print_backup(args.backup_command, result)
    elif args.command == "recover":
        if str(getattr(args, "plan", "") or ""):
            print()
            print(f"  恢复（按检查点）: 树 {result['plan_id']}"
                  + ("（dry-run: 没落盘）" if result.get("dry_run") else ""))
            print(f"  {'━' * 58}")
            cp = result.get("checkpoint")
            print("  检查点: " + (f"执行 {cp['executions']} 条 · 叶状态 {cp['node_status']} · {cp['at'][:19]}"
                                 if cp else "（无 —— 还没跑过）"))
            for x in result.get("resumed") or []:
                print(f"  ↺ 交回待跑  {x['node_id'][-12:]}  {x['title']}")
            for x in result.get("busy") or []:
                print(f"  ● 仍在跑    {x['node_id'][-12:]}  {x['title']}（有活跃执行, 不动）")
            if not (result.get("resumed") or result.get("busy")):
                print("  （没有需要恢复的叶 —— 幂等重复调用是这个结果）")
            return
        _print_recover(result)
    elif args.command == "dashboard":
        _print_dashboard(result)
    elif args.command == "metrics":
        _print_metrics(result)
    elif args.command == "verification":
        _print_verification(args.action, result)
    elif args.command == "evd":
        _print_evd(args.action, result)
    elif args.command == "history":
        _print_history(args.history_action, result)
    elif args.command == "create":
        _print_create(result)
    elif args.command == "arch":
        _print_arch(args, result)
    elif args.command == "console" and args.console_command in (
            "activity", "projects", "agents", "decisions", "cost", "experience"):
        _print_console_domain(result)
    elif args.command == "kanban":
        _print_kanban(result)
    elif args.command == "update":
        _print_update(result)
    elif args.command == "approval":
        _print_approval(result)
    elif args.command == "plugin":
        _print_plugin(result)
    elif args.command == "knowledge":
        _print_knowledge(args.knowledge_command, result)
    elif args.command == "memory":
        _print_memory(args.memory_command, result)
    elif args.command == "project":
        _print_project(args.project_command, result)
    elif args.command == "provider":
        _print_provider(args.provider_command, result)
        if args.provider_command in ("add", "doctor"):
            _print_provider_setup(args.provider_command, result)
    elif args.command == "tool":
        _print_tool(args.tool_command, result)
    elif args.command == "mcp":
        _print_mcp(args.mcp_command, result)
    elif args.command == "discover":
        _print_discover(args.what, result)
    elif args.command == "llm":
        _print_llm(args.llm_command, result)
    elif args.command == "workspace":
        _print_workspace(args.workspace_command, result)
    elif args.command == "git":
        _print_git(args.git_command, result)
    elif args.command == "change":
        _print_change(args.change_command, result)
    elif args.command == "understand":
        _print_understand(args, result)
    elif args.command == "tasktree":
        _print_tasktree(args, result)
    elif args.command == "product":
        _print_product(args, result)
    elif args.command == "intelligence":
        _print_intelligence(args, result)
    elif args.command == "console":
        _print_console(args, result)
    elif args.command == "org":
        _print_org(args, result)
    elif args.command == "exec":
        _print_exec(args, result)
    elif args.command == "demo":
        _print_demo(args, result)



def _dispatch_chain(ctx: FactoryContext, args: Any) -> dict:
    """factory chain —— 全链编排（实现复用 domains/chain.py, 不重写逻辑）。"""
    from .domains import chain as _chain
    return _chain.run(ctx, args)

def _dispatch_demo(ctx: FactoryContext, args: Any) -> dict:
    """factory demo 命令分发 (Phase 13A: Demo Productization)。"""
    if args.demo_command == "markpad":
        return cmd_demo_markpad(ctx, args)
    raise CliError(f"unknown demo command: {args.demo_command}", exit_code=2)


def _render_table(
    headers: list[str], rows: list[list[str]], *, empty: str | None = "  (无记录)",
) -> str:
    """渲染对齐表格（★ 用**显示宽度**: 中文/全角算 2 列 —— 以前用 len() ⇒ 中文列全歪 ✗）。

    空表 → empty 占位（None 则仍渲染表头, 供恒定表头场景）。
    """
    from apps.cli.textwidth import display_width, pad

    if not rows and empty is not None:
        return empty
    widths = [display_width(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], display_width(cell))
    lines = [
        "  " + "  ".join(pad(h, widths[i]) for i, h in enumerate(headers)),
        "  " + "  ".join("-" * widths[i] for i in range(len(headers))),
    ]
    lines += ["  " + "  ".join(pad(c, widths[i]) for i, c in enumerate(row)) for row in rows]
    return "\n".join(lines)

def _print_init(r: dict) -> None:
    print("✔ 初始化完成 (幂等)")
    print(f"  root      {r['root']}")
    print(f"  db        {r['db']}")
    print(f"  dirs      {' '.join(d + '/' for d in r['dirs'])}")
    print(f"  事件      system.init seq={r['event_seq']}")


def _print_task(sub: str, r: dict) -> None:
    if sub == "create":
        t = r["task"]
        print(f"✔ 任务 {t['id']} 已创建 (project: {t['project']})")
        print(f"  title     {t['title']}")
        print(f"  type      {t['type']}")
        print(f"  status    {t['status']}")
        print(f"  owner     {t['owner'] or '-'}")
        print(f"  workflow  {t['workflow'] or '-'}")
    elif sub == "list":
        # ★ 两套账本**都列 + 标签写清**（读侧归一; 存储各自保留 —— 语义不同, 见 cmd_task_list）
        ledger = r.get("tasks") or []
        dev = r.get("dev_tasks") or []
        if ledger:
            rows = [[t["id"], t["status"], t["type"], t["project"], t["title"], t["owner"] or "-"]
                    for t in ledger]
            print("  ── 台账任务（人工定义 / 带 workflow）──")
            print(_render_table(["Task", "Status", "Type", "Project", "Title", "Owner"], rows))
        if dev:
            rows = [[d.get("id", ""), d.get("status", ""), (d.get("role") or "-"),
                     d.get("project", ""), str(d.get("title") or "")[:40]] for d in dev]
            print("  ── 开发任务（任务树的叶 = 执行的真实账本）──")
            print(_render_table(["Node", "Status", "Role", "Project", "Title"], rows))
        if not ledger and not dev:
            print("  （两套账本都是空的 —— 台账可用 `factory task create` 建; 开发任务来自拆解）")
        print(f"{r.get('count', 0)} tasks（台账 {len(ledger)} + 开发 {len(dev)}）")
    elif sub == "status":
        t = r["task"]
        print(f"{t['id']}  {t['title']}  [{t['type']}]  状态: {t['status']}")
        print(f"  project   {t['project']}")
        print(f"  owner     {t['owner'] or '-'}")
        print(f"  workflow  {t['workflow'] or '-'}")
        print(f"  created   {t['created_at']}")
        print(f"  updated   {t['updated_at']}")
        print("  时间线 (最近 %d 条, 倒序)" % len(r["timeline"]))
        for e in r["timeline"]:
            print(f"    seq {e['seq']:<5} {e['type']:<18} {e['action'] or '-'}")
    elif sub == "update":
        t = r["task"]
        print(f"✔ 任务 {t['id']} 状态已更新 → {t['status']}")


def _print_event_logs(r: dict) -> None:
    rows = [[str(e["seq"]), e["timestamp"], e["type"], e["source"],
             e["task_id"] or "-", e["project_id"] or "-", e["action"] or "-", e["result"] or "-"]
            for e in r["events"]]
    print(_render_table(["seq", "timestamp", "type", "source", "task", "project", "action", "result"], rows))
    print(f"{r['count']} events")


def _print_status(r: dict) -> None:
    """`factory status` 输出 —— ★ 2026-09-21 改成表格 + 列表（Founder: 原来的输出不直观,
    用 table / 有序 / 无序列表会好很多；原样是 `tasks 0 {}`、`agent注册表 4 [...]` 这种机器味 ✗）。
    """
    print(f"  工厂状态  {r.get('root') or ''}".rstrip())
    print()
    _projects = [str(x) for x in (r.get("projects") or [])]
    _tt = r.get("dev_tasks") or r.get("tasks_tree") or {}
    _rows = [
        ["项目", str(len(_projects)), " · ".join(_projects[:6]) or "-"],
        ["任务树", str(_tt.get("plans") or "-"), "执行的真实账本（见下）"],
        ["事件", str(r.get("events_count") or "-"), "审计事件总数"],
        ["舰队", f"{r.get('fleet_count') or '-'} 人", "agents.json · 编制成员"],
        ["agent 注册表", str(r.get("agents_count") or 0), "插件域（≠ 舰队）"],
    ]
    print(_render_table(["项", "数值", "说明"], _rows))
    if _tt:
        print()
        print("  开发任务（任务树 = 执行的真实账本）")
        print(f"    · 总叶数   {_tt.get('leaves', 0)}")
        print(f"    · 已完成   {_tt.get('done', 0)}（{_tt.get('percent', 0)}%）")
        _bs = _tt.get("by_status") or {}
        if isinstance(_bs, dict) and _bs:
            print("    · 按状态")
            for _k, _v in sorted(_bs.items(), key=lambda kv: -int(kv[1] or 0)):
                print(f"        - {_k:<10} {_v}")
    _warn = []
    if _tt.get("needs_split"):
        _warn.append(f"{_tt['needs_split']} 个叶可能没拆到位（一句话写不出验收）⇒ /tasktree expand --deep")
    if _tt.get("verify_needed"):
        _warn.append(f"{_tt['verify_needed']} 个'完成'待核（无产出证据, 或产出未提交）⇒ /tasktree show <PLAN> 看 note")
    if _tt.get("needs_decision"):
        _warn.append(f"{_tt['needs_decision']} 条执行体停手待你裁决 ⇒ status --json 的 decision_reason")
    if _warn:
        print()
        print("  ⚠ 需要你留意的")
        for _w in _warn:
            print(f"    - {_w}")
    _ft = r.get("fleet_count")
    if _ft:
        print()
        print(f"  正在干活: {r.get('agents_running') or 0} 人（舰队 {_ft} 人; 其余待命）")

def _print_validate(r: dict) -> None:
    print(r["report_text"])
    if r["ok"]:
        print("✔ 验证通过 (退出码 0)")
    else:
        print(f"✘ 验证失败: {r['reason']} (退出码 {r['exit_code']})")


def _print_agent(sub: str, r: dict) -> None:
    if sub == "add":
        a = r["agent"]
        print(f"✔ Agent {a['id']} 已注册 (role: {a['role']})")
        print(f"  name        {a['name']}")
        print(f"  status      {a['status']}")
        print(f"  skills      {', '.join(a['skills']) or '-'}")
        print(f"  description {a['description'] or '-'}")
    elif sub == "list":
        rows = [[a["id"], a["name"], a["role"], a["status"], ", ".join(a["skills"]) or "-"]
                for a in r["agents"]]
        print(_render_table(["Agent", "Name", "Role", "Status", "Skills"], rows))
        print(f"{r['count']} agents")
    elif sub == "assign":
        a = r["agent"]
        asg = r["assignment"]
        print(f"Assigned: {a['name'] if a is not None else asg['agent_id']}")
        print(f"  assignment  {asg['id']}")
        print(f"  agent       {asg['agent_id']}  (status: {a['status'] if a is not None else '-'})")
        print(f"  task        {asg['task_id']}")
        print(f"  step        {asg['workflow_step_id'] or '-'}")
        print(f"  status      {asg['status']}")
    elif sub == "assignments":
        rows = [[a["id"], a["agent_id"], a["task_id"], a["workflow_step_id"] or "-", a["status"]]
                for a in r["assignments"]]
        print(_render_table(["Assignment", "Agent", "Task", "Step", "Status"], rows))
        print(f"{r['count']} assignments")
    elif sub == "release":
        asg = r["assignment"]
        print(f"✔ 已释放 {asg['agent_id']} (assignment {asg['id']}) → AVAILABLE")


def _print_skill(sub: str, r: dict) -> None:
    if sub == "add":
        s = r["skill"]
        print(f"✔ Skill {s['id']} 已注册 (category: {s['category']})")
        print(f"  name         {s['name']}")
        print(f"  version      {s['version']}")
        print(f"  capabilities {', '.join(s['capabilities']) or '-'}")
        print(f"  description  {s['description'] or '-'}")
    elif sub == "list":
        rows = [[s["id"], s["name"], s["category"], s["version"], ", ".join(s["capabilities"]) or "-"]
                for s in r["skills"]]
        print(_render_table(["Skill", "Name", "Category", "Version", "Capabilities"], rows))
        print(f"{r['count']} skills")


def _print_workflow(sub: str, r: dict) -> None:
    if sub == "add":
        w = r["workflow"]
        print(f"✔ 工作流 {w['id']} 已注册 ({len(w['steps'])} 步)")
        print(f"  name        {w['name']}")
        print(f"  description {w['description'] or '-'}")
        print(f"  steps       {' → '.join(w['steps'][i]['id'] for i in range(len(w['steps'])))}")
    elif sub == "list":
        rows = [[w["id"], w["name"], " → ".join(w["steps"][i]["id"] for i in range(len(w["steps"])))]
                for w in r["workflows"]]
        print(_render_table(["Workflow", "Name", "Steps"], rows))
        print(f"{r['count']} workflows")
    elif sub == "run":
        if r.get("auto"):
            _print_workflow_run_auto(r)
        else:
            w = r["workflow"]
            print(f"✔ 工作流已启动 (run {r['run']['run_id']})")
            print(f"  Task      {r['task_id']}")
            print(f"  Workflow  {w['id']} — {w['name']}")
            print(f"  Current   {r['current_step'] or '-'}")
    elif sub == "status":
        run = r["run"]
        print(f"{run['run_id']}  {run['workflow_id']} — {run['workflow_name']}  "
              f"任务 {r['task_id']}  状态: {run['status']}")
        for st in r["steps"]:
            print(f"  {st['symbol']} {st['step_id']:<16} {st['status']}")


def _print_workflow_run_auto(r: dict) -> None:
    """workflow run --auto 输出: Workflow/Step/Agent/Runtime/Result (phase4c2-status §3)。"""
    w = r["workflow"]
    if r["status"] == "COMPLETED":
        print(f"✔ 自动执行完成 (run {r['run_id']})")
    else:
        print(f"✘ 自动执行失败 (run {r['run_id'] or '-'})")
    print(f"  Task      {r['task_id']}")
    print(f"  Workflow  {w['id']} — {w['name'] or '-'}")
    print(f"  Status    {r['status']}")
    if r.get("error"):
        print(f"  error     {r['error']}")
    for st in r["steps"]:
        print(f"  Step      {st['step_id']:<16} {st['status']:<10} "
              f"Agent {st['agent_id'] or '-'}  Runtime {st['runtime_id'] or '-'}  "
              f"Result {st['result'] or '-'}  ({st['execution_id'] or '-'})")
    if r["events"]:
        print(f"  事件      {' → '.join(r['events'])}")


def _print_runtime(args: Any, r: dict) -> None:
    sub = args.runtime_command
    if sub == "catalog":
        _print_runtime_catalog(args.runtime_catalog_command, r)
        return
    if sub == "add":
        rt = r["runtime"]
        print(f"✔ Runtime {rt['id']} 已注册 (type: {rt['type']})")
        print(f"  name        {rt['name']}")
        print(f"  status      {rt['status']}")
        print(f"  description {rt['description'] or '-'}")
    elif sub == "list":
        rows = [[rt["id"], rt["name"], rt["type"], rt["status"]] for rt in r["runtimes"]]
        print(_render_table(["Runtime", "Name", "Type", "Status"], rows))
        print(f"{r['count']} runtimes")
    elif sub == "test":
        res = r["result"]
        print(f"Runtime {r['runtime']} smoke: {r['status']}  (execution {r['execution_id']})")
        if res.get("error"):
            print(f"  error    {res['error']}")
        else:
            stdout = (res.get("output") or {}).get("stdout", "")
            print(f"  stdout   {stdout.strip()[:200] or '(empty)'}")


def _print_runtime_catalog(sub: str, r: dict) -> None:
    if sub == "list":
        rows = [
            [d["id"], d["type"], ", ".join(d["capabilities"]) or "-",
             d["version"], d["status"]]
            for d in r["definitions"]
        ]
        print(_render_table(["Runtime", "Type", "Capabilities", "Version", "Status"], rows))
        print(f"{r['count']} definitions")
    elif sub == "show":
        d = r["definition"]
        print(f"{d['id']}  {d['name']}  [{d['type']}]  v{d['version']}  {d['status']}")
        print(f"  description   {d['description'] or '-'}")
        print(f"  capabilities  {', '.join(d['capabilities']) or '-'}")
        print(f"  tasks         {', '.join(d['supported_tasks']) or '-'}")
        if d.get("metadata"):
            print(f"  metadata      {json.dumps(d['metadata'], ensure_ascii=False)}")


def _print_execution(sub: str, r: dict) -> None:
    if sub == "list":
        rows = [
            [e["id"], e["task_id"], e["workflow_id"] or "-", e["step_id"] or "-",
             e["agent_id"] or "-", e["runtime_id"] or "-", e["status"]]
            for e in r["executions"]
        ]
        print(_render_table(["Execution", "Task", "Workflow", "Step", "Agent", "Runtime", "Status"], rows))
        print(f"{r['count']} executions")
    elif sub == "run":
        print(f"✔ 执行 {r['execution_id']} 完成 (runtime: {r['runtime'] or '-'}, status: {r['status']})")
        res = r["result"]
        if res is not None:
            print(f"  result    {res['status']}")
            if res.get("error"):
                print(f"  error     {res['error']}")
            elif res.get("output"):
                print(f"  output    {json.dumps(res['output'], ensure_ascii=False)}")
        wf = r["workflow"]
        if wf["step_completed"]:
            print("  workflow  step completed")
        if wf["workflow_failed"]:
            print("  workflow  run failed")
        if wf.get("error"):
            print(f"  workflow  linkage error: {wf['error']}")
        print(f"  事件      {' → '.join(r['events']) or '-'}")
    elif sub == "status":
        e = r["execution"]
        print(f"{e['id']}  状态: {e['status']}  runtime: {e['runtime_id'] or '-'}")
        print(f"  task      {e['task_id']}")
        print(f"  workflow  {e['workflow_id'] or '-'}  step {e['step_id'] or '-'}")
        print(f"  agent     {e['agent_id'] or '-'}")
        res = r["result"]
        if res is None:
            print("  result    (尚无结果)")
        else:
            print(f"  result    {res['status']}")
            if res.get("error"):
                print(f"  error     {res['error']}")
            elif res.get("output"):
                print(f"  output    {json.dumps(res['output'], ensure_ascii=False)}")


def _print_checkpoint(sub: str, r: dict) -> None:
    if sub == "create":
        c = r["checkpoint"]
        print(f"✔ Checkpoint {c['id']} 已创建 (event_seq: {c['event_seq']})")
        print(f"  task        {c['task_id']}")
        print(f"  workflow    {c['workflow_id'] or '-'}")
        print(f"  current     {c['current_step'] or '-'}")
        if c.get("workflow_state"):
            print(f"  run state   {c['workflow_state'].get('status', '-')}")
    elif sub == "list":
        rows = [
            [c["id"], c["task_id"], c["workflow_id"] or "-", str(c["event_seq"]),
             c["current_step"] or "-", c["created_at"]]
            for c in r["checkpoints"]
        ]
        print(_render_table(["Checkpoint", "Task", "Workflow", "EventSeq", "CurrentStep", "CreatedAt"], rows))
        print(f"{r['count']} checkpoints")


def _print_recover(r: dict) -> None:
    rec = r["recovery"]
    if rec["resume_ok"]:
        print(f"✔ 恢复完成 (task {rec['task_id']}) — 可继续")
    else:
        print(f"✘ 恢复被拒绝 (task {rec['task_id']}) — 不可继续")
    print(f"  Last Event  {rec['last_event']}")
    print(f"  State       {rec['state']}")
    print(f"  Resume      {rec['resume_ok']}")
    for action in rec["actions"]:
        print(f"  action      {action}")


def _print_dashboard(r: dict) -> None:
    from dashboard.models import FactorySnapshot
    from dashboard.renderer import DashboardRenderer

    snapshot = FactorySnapshot.model_validate(r["snapshot"])
    print(DashboardRenderer().render(snapshot, view=r.get("view") or "all"))


def _print_metrics(r: dict) -> None:
    from metrics.types import FactoryMetrics, WorkspaceComparison
    from metrics.reports import format_metrics, format_workspace_comparison

    if r.get("workspace"):  # metrics --workspace → 项目对比报告 (Phase 6B, ADR-0017)
        print(format_workspace_comparison(WorkspaceComparison.model_validate(r["comparison"])))
        return
    print(format_metrics(FactoryMetrics.model_validate(r["metrics"])))
    # ★ 开发任务（任务树）—— 上面那张表数的是【任务域】, 而执行跑的是【任务树】;
    #   两套账本都得报出来（实测踩到: 工厂干着活、这里显示 Tasks 0）
    tt = r.get("tasks_tree") or {}
    if tt:
        print("\n开发任务（任务树 = 执行的真实账本）")
        print("  total  done  percent  plans  by_status")
        print("  -----  ----  -------  -----  ---------")
        print(f"  {tt.get('leaves', 0):5d}  {tt.get('done', 0):4d}  "
              f"{str(tt.get('percent', 0)) + '%':7s}  {tt.get('plans', 0):5d}  {tt.get('by_status') or '{}'}")
        if tt.get("by_project"):
            print("  按项目: " + " · ".join(f"{k} {v['done']}/{v['leaves']}" for k, v in tt["by_project"].items()))


def _print_knowledge(sub: str, r: dict) -> None:
    """knowledge status / reindex 的输出（说人话: 会不会记错 + 做了什么）。"""
    if sub == "status":
        rows = [[x["project_id"], x["slug"], "有" if x["exists"] else "无",
                 f"★ 过期 ({x['newer_docs']} 个文档更新)" if x["stale"] else "最新"]
                for x in r.get("projects") or []]
        if rows:
            print(_render_table(["Project", "Slug", "索引", "状态"], rows))
        sc = int(r.get("stale_count") or 0)
        tail = "  ⇒ 用 factory knowledge reindex 更新" if sc else "  ✓ 记忆不会记错"
        print(f"{r.get('count')} 个项目 · 过期 {sc} 个{tail}")
        return
    if sub == "reindex":
        for x in r.get("projects") or []:
            if x.get("error"):
                print(f"  ✗ {x['project_id']}: {x['error']}")
            else:
                kind = "增量" if x.get("incremental") else "全量"
                print(f"  ✓ {x['project_id']} ({kind}): 变更 {x.get('changed', 0)} · "
                      f"删除 {x.get('removed', 0)} · 片段 {x.get('chunks', 0)} · {x.get('tiers')}")
        print(f"{r.get('count')} 个项目已重建")
        return


def _plan_not_found(plan_id: str) -> "CliError":
    """树没找到时的统一报错（★ 2026-09-24: 传错 id 类型要给正确指引 ✗）。

    Founder 实测: 会话里拿**项目 id**（P-xxx）查树 ⇒ 只回"任务树不存在"⇒
    用户/助手都以为"这个项目没有树" ✗（其实树在, 只是要 PLAN-xxx）。
    """
    _h = ""
    if str(plan_id).startswith("P-"):
        _h = (f" ← 你给的是**项目 id**; 树要传 PLAN-xxx ⇒ "
              f"`factory tasktree list --project {plan_id}` 看该项目的树 ✓")
    return CliError(f"任务树不存在: {plan_id}（`factory tasktree list` 看有哪些）{_h}", exit_code=1)

def _print_project(sub: str, r: dict) -> None:
    if sub == "org":
        # ★ 2026-09-21: 项目归属公司/部门（派活按它筛人）
        print(f"✔ 项目 {r.get('project_id')} 归属: 公司 {r.get('company_id') or '（未归属）'}"
              + (" · 部门 " + ", ".join(r.get("department_ids") or []) if r.get("department_ids") else ""))
        print("  派活会按它筛人（`factory tasktree staffing` / `tasktree declare`）")
        return
    if sub == "adopt":
        # ★ 2026-09-19: adopt 的输出（记忆链上游 —— 项目有了 repo_path, 知识索引才知道扫哪）
        print(f"\n  ✓ 已注册项目: {r.get('name')}  ({r.get('project_id')})")
        print(f"    仓库      {r.get('repo_path')}")
        print(f"    语言/框架  {r.get('language') or '-'} / {r.get('framework') or '-'}")
        print(f"\n  下一步: factory conversation new --project {r.get('project_id')}")
        print("          会话绑定项目后, 理解时会自动检索该项目的文档知识（知识记忆）")
        return
    if sub == "list":
        # ★ 2026-09-21 加**说明**列（Founder: "没有中文说明, 我都不知道是什么项目"）
        rows = [[p.get("id", ""), p["name"], (p.get("note") or "（未记录说明）")[:34],
                 p["status"], p["language"], p["repository"] or "-",
                 ", ".join(p["tech_stack"]) or "-"] for p in r["projects"]]
        print(_render_table(["ID", "Project", "说明", "Status", "Language", "Repository", "Tech Stack"], rows))
        print(f"{r['count']} projects (source: {r['source']})")
    elif sub == "show":
        p = r["project"]
        print(f"{p['name']}  {p['description'] or ''}")
        print(f"  language    {p['language']}")
        print(f"  repository  {p['repository'] or '-'}")
        # ★ 2026-09-24（Founder 实测: 「不能进入到项目看详情」✗）: 把**它的任务树与进度**打出来 ✓
        _tr = r.get("trees") or []
        if _tr:
            print(f"  任务树      {len(_tr)} 棵")
            for _x in _tr:
                print(f"    {_x['plan_id']:<22} 叶 {_x['leaves']:>4} · 完成 {_x['done']:>4}"
                      f"  {_x['percent']:>5.1f}%")
            print(f"  下一步      factory tasktree todo {_tr[0]['plan_id']}"
                  f"    （看逐叶清单; 或 factory tasktree flow {_tr[0]['plan_id']} 看链路图）")
        else:
            print("  任务树      （还没有树）⇒ 用 factory chain \"需求\" --project "
                  f"{p.get('id') or ''} 起一棵 ✓")
        print(f"  tech_stack  {', '.join(p['tech_stack']) or '-'}")
        print(f"  agents      {len(r['agents'])}")
        for a in r["agents"]:
            print(f"    {a['id']:<20} role={a['role']:<15} skills={', '.join(a['skills']) or '-'}")
        print(f"  skills      {len(r['skills'])}")
        for s in r["skills"]:
            print(f"    {s['id']:<20} category={s['category']:<12} "
                  f"{', '.join(s['capabilities']) or '-'}")
        print(f"  workflows   {len(r['workflows'])}")
        for w in r["workflows"]:
            steps = " → ".join(st["id"] for st in w["steps"])
            print(f"    {w['id']:<20} {w['name'] or '-'}  [{steps}]")


def _print_provider(sub: str, r: dict) -> None:
    """factory provider 输出: list 目录表 / show 定义详情 / test smoke 结果
    (Phase 8A, ADR-0022; --json 出口在 _print_output 前置处理)。"""
    if sub == "list":
        rows = [
            [p["id"], p["type"], ", ".join(p["capabilities"]) or "-",
             p["version"], p["status"], "*" if p["id"] == r.get("default") else ""]
            for p in r["providers"]
        ]
        print(_render_table(["Provider", "Type", "Capabilities", "Version", "Status", "Default"], rows))
        print(f"{r['count']} providers (default: {r.get('default') or 'not set'})")
    elif sub == "show":
        p = r["provider"]
        print(f"{p['id']}  {p['name']}  [{p['type']}]  v{p['version']}  {p['status']}"
              + ("  (default)" if r.get("default") else ""))
        print(f"  description   {p['description'] or '-'}")
        print(f"  capabilities  {', '.join(p['capabilities']) or '-'}")
        print(f"  models        {', '.join(p['models']) or '-'}")
        if p.get("config_schema"):
            keys = ", ".join(sorted(p["config_schema"])) or "-"
            print(f"  config        {keys}")
        if p.get("metadata"):
            print(f"  metadata      {json.dumps(p['metadata'], ensure_ascii=False)}")
    elif sub == "test":
        print(f"Provider {r['provider']} smoke: {r['status']}  (model: {r['model'] or '-'})")
        if r.get("response", {}).get("error"):
            print(f"  error    {r['response']['error']}")
        else:
            content = (r.get("response") or {}).get("content", "")
            print(f"  output   {content.strip()[:200] or '(empty)'}")
        print(f"  事件      {' → '.join(r.get('events') or []) or '-'}")
    elif sub == "usage":
        rows = [
            [u["provider_id"], u["model"] or "-", str(u["prompt_tokens"]),
             str(u["completion_tokens"]), f"{u['estimated_cost']:.6f}",
             f"{u['latency_ms']}ms", "OK" if u["success"] else "FAIL", u["recorded_at"]]
            for u in r["records"]
        ]
        print(_render_table(
            ["Provider", "Model", "In", "Out", "Cost", "Latency", "Result", "Recorded"], rows,
            empty=None,
        ))
        if not r["records"]:
            print("  (no usage records)")
        else:
            total = round(sum(u["estimated_cost"] for u in r["records"]), 6)
            print(f"{r['count']} records (estimated total cost: {total})  "
                  f"[period={r['period']}, provider={r.get('provider') or 'all'}]")
    elif sub == "stats":
        rows = [
            [s["provider_id"], s["model"] or "-", s["version"] or "-",
             str(s["execution_count"]), f"{s['success_rate'] * 100:.1f}%",
             f"{s['failure_rate'] * 100:.1f}%", f"{s['avg_cost']:.6f}",
             f"{s['avg_duration_ms']:.1f}ms", str(s["total_tokens"]),
             f"{s['total_cost']:.6f}"]
            for s in r["stats"]
        ]
        print(_render_table(
            ["Provider", "Model", "Version", "Executions", "Success", "Failure",
             "Avg Cost", "Avg Dur", "Tokens", "Cost"], rows, empty=None,
        ))
        if not r["stats"]:
            print("  (no stats — 无 usage 记录)")
        else:
            total = round(sum(s["total_cost"] for s in r["stats"]), 6)
            print(f"{r['count']} stats (estimated total cost: {total})  "
                  f"[period={r['period']}, provider={r.get('provider') or 'all'}]")
    elif sub == "compare":
        a, b = r["providers"][0], r["providers"][1]
        print(f"{a['id']}  vs  {b['id']}")
        print(f"  type        {a['type']:<10} {b['type']}")
        print(f"  version     {a['version']:<10} {b['version']}")
        print(f"  capabilities {', '.join(a['capabilities']) or '-':<24} "
              f"{', '.join(b['capabilities']) or '-'}")
        print(f"  models       {', '.join(a['models']) or '-':<24} "
              f"{', '.join(b['models']) or '-'}")
        for pid in (a["id"], b["id"]):
            profile = r["capability"].get(pid)
            cost = r["cost"].get(pid)
            est = r["estimated_call_cost"].get(pid)
            print(f"  [{pid}]")
            if profile:
                matrix = ", ".join(f"{k}={v}" for k, v in sorted(profile["matrix"].items()))
                print(f"    matrix     {matrix or '-'}")
                if profile.get("evidence"):
                    print(f"    evidence   {'; '.join(profile['evidence'])}")
            else:
                print("    matrix     (无能力数据)")
            if cost:
                print(f"    cost       mode={cost['mode']} pricing={cost['pricing']} "
                      f"free={cost['free']}")
            else:
                print("    cost       (无成本模型)")
            print(f"    est/call   {est if est is not None else '-'}")
    elif sub == "recommend":
        rec = r.get("recommended")
        if rec is None:
            print(f"No recommendation for task '{r['task']}' (无能力匹配的 Provider)")
        else:
            print(f"推荐: {rec['provider_id']}  (score: {rec['score']})")
            print(
                f"  三分数    capability {rec['capability_score']}  "
                f"cost {rec['cost_score']}  performance {rec['performance_score']}  "
                f"(est cost: {rec.get('estimated_cost') or '-'})"
            )
            for reason in rec["reasons"]:
                print(f"  - {reason}")
        print("  事件      provider.viewed"
              + (" + provider.selected (source=recommendation)" if rec else ""))


def _print_workspace(sub: str, r: dict) -> None:
    if sub == "init":
        w = r["workspace"]
        ids = [p["id"] for p in w["projects"]]
        print(f"✔ Workspace 已初始化: {w['name']} v{w['version']}")
        print(f"  file      {r['workspace_file']}")
        print(f"  projects  {', '.join(ids) or '(none)'}")
        print(f"  事件      workspace.created seq={r.get('event_seq')}")
    elif sub == "show":
        w = r["workspace"]
        print(f"{w['name']}  v{w['version']}  (root: {w['root_path']})")
        print(f"  file      {r['workspace_file']}")
        if not w["projects"]:
            print("  projects  (none)")
        for p in w["projects"]:
            print(f"    {p['id']:<16} {p['status']:<9} {p['language']:<8} "
                  f"{p['description'][:60] or '-'}")
        print(f"  事件      workspace.viewed seq={r.get('event_seq')}")


def _print_git(sub: str, r: dict) -> None:
    """factory git 输出: status 上下文 + 变更表; diff 变更表; commits 提交表。"""
    if sub == "status":
        st = r["status"]
        if st.get("error"):
            print(f"✘ {st['repository']} — {st['error']}")
        else:
            head = st.get("current_commit") or "(no commits)"
            print(f"✔ {st['repository']}  [{st.get('branch') or 'detached'}]  {head[:12]}")
        rows = [[", ".join(c["files"]), c["status"], str(c["insertions"]),
                 str(c["deletions"]), c["task_id"] or "-"] for c in st.get("changes", [])]
        print(_render_table(["File", "Status", "+", "-", "Task"], rows, empty=None))
        if not st.get("changes"):
            print("  (no changes)")
    elif sub == "diff":
        rows = [[", ".join(c["files"]), c["status"], str(c["insertions"]),
                 str(c["deletions"]), c["task_id"] or "-"] for c in r["changes"]]
        print(_render_table(["File", "Status", "+", "-", "Task"], rows))
        print(f"{r['count']} changes")
        if r.get("error"):
            print(f"  error     {r['error']}")
    elif sub == "commits":
        rows = [[c["hash"][:12], c["message"], c["branch"] or "-",
                 c["task_id"] or "-", c["created_at"]] for c in r["commits"]]
        print(_render_table(["Hash", "Message", "Branch", "Task", "Date"], rows))
        print(f"{r['count']} commits")
        if r.get("error"):
            print(f"  error     {r['error']}")



def _print_run_plan(r: dict) -> None:
    """run --plan 的输出（说人话: 跑了几个 / 为什么停 / 有没有冲突降级）。"""
    print(f"\n  ▲ 跑任务树: {r.get('plan_id')}")
    print(f"    轮次 {r.get('ticks')} · 创建执行 {len(r.get('scheduled') or [])} 个")
    # ★ 交回的陈旧认领（进程中断遗留的 claimed）—— 必须让人看见（否则"怎么又动了"说不清）
    if r.get("released"):
        print(f"    ↺ 交回陈旧认领 {len(r['released'])} 条（进程中断遗留, 无活跃执行）:")
        for x in r["released"][:3]:
            print(f"      · {str(x.get('title'))[:40]}  [{str(x.get('node_id'))[-8:]}]")
    for o in (r.get("outcomes") or [])[:12]:
        print(f"      · {str(o.get('execution_id'))[:26]:<28} {str(o.get('state'))[:44]}")
    if r.get("deferred"):
        print(f"    推迟 {len(r['deferred'])} 个（容量/预算受限）")
    if r.get("stopped_because"):
        print(f"    停止原因: {r['stopped_because']}")

def _print_change(sub: str, r: dict) -> None:
    """factory change 输出: commits 提交表; plan 影响面; analyze 路径分析; validate L4 判定;
    triggers 注册/列表; evaluate 规则判定; workflows workflow 链。"""
    if sub == "plan":
        # ★ 2026-09-19 mem-7: 影响面清单（"改全"的判据 —— 不是搜索命中数, 而是清单+验证+显式风险）
        print(f"\n  ▲ 影响面: {r.get('symbol')}   (仓库 {r.get('repo')})")
        defs = r.get("definitions") or []
        if not defs:
            print("    定义: ✗ 未找到（确认符号名, 或用全名如 mod.sub.sym）")
        for d in defs:
            print(f"    定义: {d['file']}:{d['line']}")
        print(f"\n  [静态] 调用方 {r.get('callers_count', 0)} 处 · 受影响文件 {r.get('affected_count', 0)} 个")
        for c in (r.get("callers") or [])[:12]:
            print(f"        ← {c['symbol']}  ({c['file']}:{c['line']})")
        more = int(r.get("callers_count", 0)) - 12
        if more > 0:
            print(f"        … 另有 {more} 处")
        print(f"\n  [测试] 覆盖 {r.get('tests_count', 0)} 个文件")
        for x in (r.get("tests") or [])[:6]:
            print(f"        {x}")
        chain = r.get("impact_chain") or []
        if chain:
            print(f"\n  [连锁] 依赖这些文件的还有 {len(chain)} 个（改接口时注意）")
        risks = r.get("risks") or []
        if risks:
            print("\n  [★ 风险]")
            for x in risks:
                print(f"        {x}")
        print("\n  [建议] 改完验证: bash scripts/verify.sh; 再核对上面每一处调用方")
        return
    if sub == "commits":
        rows = [[c["hash"][:12], c["message"], c["branch"] or "-",
                 c["task_id"] or "-", c["created_at"]] for c in r["commits"]]
        print(_render_table(["Hash", "Message", "Branch", "Task", "Date"], rows))
        print(f"{r['count']} commits")
        if r.get("error"):
            print(f"  error     {r['error']}")
    elif sub == "analyze":
        a = r["analysis"]
        print(f"✔ 变更分析 {r['task_id']}  (commit 关联: {len(a['commits'])})")
        print(f"  files       {len(a['files'])}")
        for f in a["files"]:
            print(f"    {f}")
        print(f"  insertions  {a['insertions']}")
        print(f"  deletions   {a['deletions']}")
        print(f"  modules     {len(a['affected_modules'])}")
        for m in a["affected_modules"]:
            print(f"    {m}")
        if a["commits"]:
            print(f"  commits     {', '.join(h[:12] for h in a['commits'])}")
    elif sub == "validate":
        res = r["result"]
        status = res["status"]
        print(f"L4 Change Validation — {r['task_id']}  →  {status}")
        print(f"  {res['message'] or '-'}")
        for c in res.get("checks", []):
            print(f"  {c['id']:<16} {c['status']:<5} {c['message']}")
        if status == "FAIL":
            print(f"✘ 验证失败 (退出码 {r['exit_code']})")
        elif status == "ERROR":
            print(f"✘ 验证错误 (退出码 {r['exit_code']})")
        else:
            print(f"✔ 验证通过 (退出码 {r['exit_code']})")
    elif sub == "triggers":
        if r.get("trigger"):
            t = r["trigger"]
            print(f"✔ 触发器已注册 {t['id']}  (event={t['event_type']} "
                  f"project={t['project_id'] or '-'} type={t['task_type'] or '-'} "
                  f"validation={t['required_validation']} → {t['target_workflow']})")
            if r.get("event_seq"):
                print(f"  事件      change.trigger.created seq={r['event_seq']}")
        else:
            rows = [[t["id"], t["event_type"], t["project_id"] or "-",
                     t["task_type"] or "-", t["required_validation"],
                     t["target_workflow"]] for t in r["triggers"]]
            print(_render_table(["Trigger", "Event", "Project", "Task Type", "Validation", "Target"], rows))
            print(f"{r['count']} triggers")
            if r.get("event_seq"):
                print(f"  事件      change.trigger.viewed seq={r['event_seq']}")
    elif sub == "evaluate":
        ev = r["evaluation"]
        status = ev["status"]
        print(f"Change 评估 — {r['task_id']}  →  {status}"
              f"  (trigger: {ev['trigger_id'] or '-'})")
        for rule in ev.get("rules", []):
            print(f"  {rule['rule_id']:<16} {rule['status']:<5} {rule['message']}")
        if ev.get("triggered_workflow"):
            print(f"  → 触发 {ev['triggered_workflow']} (run {ev['run_id']})")
        if ev.get("error"):
            print(f"  error     {ev['error']}")
        if status == "FAIL":
            print(f"✘ 评估失败 (退出码 {r['exit_code']})")
        elif status == "ERROR":
            print(f"✘ 评估错误 (退出码 {r['exit_code']})")
        else:
            print(f"✔ 评估完成 (退出码 {r['exit_code']})")
    elif sub == "workflows":
        rows = [[c["workflow_id"], c["workflow_name"] or "-", c["run_id"] or "-",
                 c["status"], "triggered" if c.get("triggered") else "task"]
                for c in r["chain"]]
        print(_render_table(["Workflow", "Name", "Run", "Status", "Origin"], rows))
        print(f"{r['count']} workflows in chain")


def _print_understand(args: Any, r: dict) -> None:
    """factory understand 输出: 阶段识别 + 基本信息 + 产物表 + 缺失 + 建议。

    --stage: 仅阶段行 + 证据列表 (--json 时结果只含 stage 段, 命令层已切分)。
    """
    if r.get("stage_only"):
        stage = r["stage"]
        print(f"✔ 阶段识别: {stage['stage']}  (confidence: {stage['confidence']:.2f})")
        for line in stage.get("evidence", []):
            print(f"    - {line}")
        return
    report = r["report"]
    stage = report["stage"]
    bi = report["basic_info"]
    print(f"✔ 项目理解报告: {r['path']}")
    print(f"  阶段       {stage['stage']}  (confidence: {stage['confidence']:.2f})")
    print(f"  类型       {bi['type']}  |  规模 {bi['scale']} "
          f"({bi['file_count']} files, {bi['dir_count']} dirs)  |  状态 {bi['status']}")
    print(f"  语言       {', '.join(bi['languages']) or '-'}")
    print(f"  技术栈     {', '.join(bi['tech_stack']) or '-'}")
    print("  证据:")
    for line in stage.get("evidence", []):
        print(f"    - {line}")
    rows = [[a["artifact"], "✓" if a["present"] else "✗", a["detail"] or "-"]
            for a in report["artifacts"]]
    print(_render_table(["Artifact", "Present", "Detail"], rows, empty=None))
    m = report["missing"]
    print(f"  缺失       {', '.join(m['missing']) or '(无)'}")
    print(f"  已存在     {', '.join(m['present']) or '(无)'}")
    print("  建议 (仅建议, 不自动执行):")
    for na in report["next_actions"]:
        flag = "  [需人工批准]" if na["approval_required"] else ""
        print(f"    - {na['action']}{flag}")
        print(f"      理由: {na['reason']}")
        print(f"      风险: {na['risk']}")


# ------------------------------------------------------------------ product 输出 (Phase 9A, ADR-0026)

def _print_product(args: Any, r: dict) -> None:
    if r.get("command") == "product breakdown":
        # ★ 需求拆解（业务层）—— 给人看的粒度
        print()
        print(f"  需求拆解（业务模块）    {r.get('count')} 个")
        print(f"  {'━' * 48}")
        for i, m in enumerate(r.get("modules") or [], 1):
            deps = m.get("depends_on") or []
            tail = f"    ← 依赖: {' / '.join(deps)}" if deps else ""
            print(f"  {i}. {m.get('name')}{tail}")
            for f in m.get("features") or []:
                print(f"       · {f}")
        print()
        print("  （业务层的粒度 —— 给人看; 执行层粒度见 tasktree todo）")
        return
    """factory product 输出: idea create/list/show + approval request/decide/list
    + workflow start/status + generate + experience list/record (发对应
    idea.*/approval.*/product.* 审计事件; Phase 9A ADR-0026 + 9B ADR-0027)。"""
    if args.product_command in ("develop", "ux"):
        # ★ 产品阶段执行链（2026-09-15）: PM / UX Agent 产出 7 节产物
        cmd = args.product_command
        a = r.get("artifact") or {}
        print(f"✔ {'Product' if cmd == 'develop' else 'UX/UI'} Artifact 已生成: {a.get('id')}")
        if cmd == "develop":
            print(f"  想法: {str(r.get('idea') or '')[:100]}")
        else:
            print(f"  输入 product: {r.get('input_product')}")
        print(f"  7 节: {', '.join(r.get('sections') or [])}")
        proj = str(getattr(args, "project", "") or "")
        nxt = f"product ux --project {proj}" if cmd == "develop" else f"arch design --project {proj}"
        print(f"  下一步: factory {nxt}")
        return
    if args.product_command == "idea":
        if args.idea_command == "list":
            _print_product_idea_list(r)
        else:  # create / show 共用想法 + 关联 Artifact 段
            _print_product_idea_detail(args, r)
    elif args.product_command == "approval":
        if args.approval_command == "list":
            _print_product_approval_list(r)
        elif args.approval_command == "decide":
            _print_product_approval_decide(r)
        elif args.approval_command == "history":
            _print_product_approval_history(r)
        else:  # request
            _print_product_approval_request(r)
    elif args.product_command == "workflow":
        _print_product_workflow(args, r)
    elif args.product_command == "generate":
        _print_product_generate(r)
    elif args.product_command == "experience":
        if args.experience_command == "list":
            _print_product_experience_list(r)
        else:  # record
            _print_product_experience_record(r)
    elif args.product_command == "lifecycle":  # Phase 9d (ADR-0029)
        _print_product_lifecycle(args, r)


def _print_product_idea_list(r: dict) -> None:
    rows = [[i["id"], i["title"], i["status"], ", ".join(i["goals"]) or "-",
             i["description"] or "-"] for i in r["ideas"]]
    print(_render_table(["Idea", "Title", "Status", "Goals", "Description"], rows))
    print(f"{r['count']} ideas")


def _print_product_idea_detail(args: Any, r: dict) -> None:
    i, a = r["idea"], r["artifact"]
    print(f"✔ 想法 {i['id']}  ({i['title']})")
    print(f"  status    {i['status']}")
    print(f"  goals     {', '.join(i['goals']) or '-'}")
    if a is not None:
        print(f"  artifact  {a['id']}  (type: {a['type']}, status: {a['status']})")
    if i.get("description"):
        print(f"  描述      {i['description']}")
    if r.get("event_seq"):
        event_name = "created" if args.idea_command == "create" else "viewed"
        print(f"  事件      idea.{event_name} seq={r['event_seq']}")


def _print_product_approval_request(r: dict) -> None:
    a = r["approval"]
    print(f"✔ 审批请求 {a['id']} 已提交 (gate: {a['gate']}, status: {a['status']})")
    print(f"  artifact  {a['artifact_id']}")
    if a.get("idea_id"):
        print(f"  idea      {a['idea_id']}")
    if a.get("comment"):
        print(f"  note      {a['comment']}")
    if r.get("event_seq"):
        print(f"  事件      approval.required seq={r['event_seq']}")


def _print_product_approval_decide(r: dict) -> None:
    a, d = r["approval"], r["decision"]
    mark = "✔" if d["decision"] == "approved" else "✘"
    print(f"{mark} 审批 {a['id']} → {d['decision'].upper()}  (by {d['decided_by']})")
    print(f"  artifact  {a['artifact_id']}  (gate: {a['gate']})")
    if d["comment"]:
        print(f"  comment   {d['comment']}")
    pd = r.get("product_decision")
    if pd:
        print(f"  product_decision  {pd['id']}  (status: {pd['status']}, "
              f"confidence: {pd['confidence']})")
    if r.get("event_seq"):
        print(f"  事件      approval.{d['decision']} seq={r['event_seq']}")


def _print_product_approval_history(r: dict) -> None:
    rows = []
    for h in r["history"]:
        decision = h.get("decision")
        rows.append([
            h["id"], h["artifact_id"], h["gate"], h["status"],
            str(h.get("artifact_version") or "-"),
            h.get("idea_id") or "-",
            decision["decision"] if decision else "-",
            decision["decided_by"] if decision else "-",
            (decision["comment"] or "-") if decision else "-",
        ])
    print(_render_table(
        ["Request", "Artifact", "Gate", "Status", "Version", "Idea", "Decision", "By", "Comment"],
        rows,
    ))
    print(f"{r['count']} history entries")


def _print_product_approval_list(r: dict) -> None:
    rows = [[a["id"], a["artifact_id"], a["gate"], a["status"],
             a.get("idea_id") or "-", a.get("by") or "-"] for a in r["approvals"]]
    print(_render_table(["Request", "Artifact", "Gate", "Status", "Idea", "By"], rows))
    print(f"{r['count']} approvals")


def _print_product_workflow(args: Any, r: dict) -> None:
    w = r["workflow"]
    print(f"✔ 工作流 {w['id']}  (idea: {w['idea_id']})")
    print(f"  status        {w['status']}")
    print(f"  current_stage {w['current_stage'] or '-'}")
    print(f"  stages        {' → '.join(w['stages']) or '-'}")
    if w.get("product_decision"):
        print(f"  product_decision {w['product_decision']}")
    if r.get("event_seq"):
        if args.workflow_command == "resume":
            event_label = "approval.resumed"  # 手动恢复 (reason=manual)
        else:
            event_label = (
                f"product.workflow."
                f"{'started' if args.workflow_command == 'start' else 'status_viewed'}"
            )
        print(f"  事件      {event_label} seq={r['event_seq']}")


# ------------------------------------------------------------------ product generate/experience 输出 (Phase 9B, ADR-0027)

def _print_product_generate(r: dict) -> None:
    a, c = r["artifact"], r["context"]
    print(f"✔ 生成 {a['type']} Artifact {a['id']}  (provider: {r['provider_id']})")
    print(f"  status     {a['status']}  |  version {a['version']}  |  confidence {a['confidence']}")
    content = (a.get("content") or {}).get("content") or "(empty)"
    print(f"  content    {str(content)[:120]}")
    if c.get("generation_time"):
        print(f"  generated  {c['generation_time']}")
    ap = r.get("approval")
    if ap:
        print(f"  approval   {ap['id']}  (gate: {ap['gate']}, status: {ap['status']}) — 等待人工批准")
    rec = r.get("recommendation")
    if rec:
        print(f"  推荐       {rec['provider_id']}  (score: {rec['score']})")
    if r.get("event_seq"):
        print(f"  事件      product.generation.completed seq={r['event_seq']}")


def _print_product_experience_list(r: dict) -> None:
    rows = [
        [e["id"][:8], e["artifact_type"], e["provider_id"] or "-",
         str(e["rating"]) if e["rating"] is not None else "-",
         "✓" if e["approved"] is True else ("✗" if e["approved"] is False else "-"),
         (e["human_feedback"] or "-")[:40], e["recorded_at"]]
        for e in r["experiences"]
    ]
    print(_render_table(
        ["Experience", "Type", "Provider", "Rating", "Approved", "Feedback", "Recorded"], rows,
    ))
    print(f"{r['count']} experiences")


def _print_product_experience_record(r: dict) -> None:
    e = r["experience"]
    print(f"✔ 经验已记录 {e['id'][:8]}  (artifact_type: {e['artifact_type']}, "
          f"provider: {e['provider_id'] or '-'})")
    print(f"  rating     {e['rating'] if e['rating'] is not None else '-'}")
    print(f"  approved   {e['approved'] if e['approved'] is not None else '-'}")
    if e.get("human_feedback"):
        print(f"  feedback   {e['human_feedback']}")
    if r.get("event_seq"):
        print(f"  事件      product.experience.recorded seq={r['event_seq']}")


# ------------------------------------------------------------------ product lifecycle 输出 (Phase 9d, ADR-0029)

def _print_product_lifecycle(args: Any, r: dict) -> None:
    """factory product lifecycle 输出: start/advance 生命周期详情; status 快照
    (当前阶段/待审批/产物/决策链/下一步动作); templates 模板表 (Phase 9d,
    ADR-0029; --json 出口在 _print_output 前置处理)。"""
    sub = args.lifecycle_command
    if sub == "templates":
        rows = [[t["name"], t["description"] or "-",
                 " → ".join(s["name"] for s in t["stages"])] for t in r["templates"]]
        print(_render_table(["Template", "Description", "Stages"], rows))
        print(f"{r['count']} lifecycle templates")
        if r.get("event_seq"):
            print(f"  事件      product.lifecycle.templates_viewed seq={r['event_seq']}")
        return
    if sub == "status":
        _print_product_lifecycle_status(r)
        return
    # start / advance: 生命周期详情
    lc = r["lifecycle"]
    print(f"✔ 生命周期 {lc['id']}  (idea: {lc['idea_id']}, template: {lc['template_name']})")
    print(f"  status        {lc['status']}")
    cur = r.get("current_stage")
    if cur is not None:
        print(f"  current_stage {cur['name']}  ({cur['kind']}, status: {cur['status']})")
    else:
        print("  current_stage (none)")
    if lc.get("completed_at"):
        print(f"  completed_at  {lc['completed_at']}")
    if r.get("event_seq"):
        event_label = "product.lifecycle.started" if sub == "start" else "product.stage.completed"
        print(f"  事件      {event_label} seq={r['event_seq']}")


def _print_product_lifecycle_status(r: dict) -> None:
    """lifecycle status 快照输出: 生命周期 + 当前阶段 + 待审批 + 产物表 +
    决策链表 + 下一步动作 (与 engine.status 同形状, Dashboard Lifecycle View 同源)。"""
    lc = r["lifecycle"]
    cur = r.get("current_stage")
    print(f"生命周期 {lc['id']}  (idea: {lc['idea_id']}, template: {lc['template_name']})")
    print(f"  status        {lc['status']}")
    if cur is not None:
        print(f"  current_stage {cur['name']}  ({cur['kind']})")
        if cur.get("entered_at"):
            print(f"  entered_at    {cur['entered_at']}")
    pa = r.get("pending_approval")
    if pa is not None:
        print(f"  pending       {pa['id']}  (gate: {pa['gate']}, artifact: {pa['artifact_id']})")
    rows = [[a["id"], a["type"], a["status"], f"v{a['version']}", str(a["created_at"])[:19]]
            for a in r.get("artifacts") or []]
    print(_render_table(["Artifact", "Type", "Status", "Version", "Created"], rows,
                        empty="  (no artifacts)"))
    drows = [[d["id"], d["type"], d.get("source_artifact_id") or "-",
              d.get("approved_reference") or "-"] for d in r.get("decisions") or []]
    print(_render_table(["Decision", "Type", "Source", "Reference"], drows,
                        empty="  (no decisions)"))
    print("  下一步:")
    for action in r.get("next_actions") or []:
        print(f"    - {action}")
    if r.get("event_seq"):
        print(f"  事件      product.lifecycle.status_viewed seq={r['event_seq']}")


# ------------------------------------------------------------------ Phase 10A-2: Intelligence (ADR-0031)


def _print_intelligence(args: Any, r: dict) -> None:
    """Intelligence 命令输出 (决策智能/推荐引擎; --json 已在 _print_output 前置处理)。"""
    if args.intelligence_command == "decision":
        _print_intelligence_decision_create(r)
    elif args.intelligence_command == "recommend":
        _print_intelligence_recommend(r)
    elif args.intelligence_command == "experience":
        if args.experience_command == "list":
            _print_intelligence_experience_list(r)
        elif args.experience_command == "evaluate":
            _print_intelligence_experience_evaluate(r)


def _print_intelligence_recommend(r: dict) -> None:
    """recommend 输出: Recommendation (score + Reasons 分项 + Risk) + Decision 绑定。"""
    rec = r["recommendation"]
    print(f"✔ 推荐 {rec['id']} (task: {rec['task_type']})")
    print(f"  推荐        {rec['top_candidate_id']}  score {rec['score']:.3f}")
    print("  Reasons")
    for item in rec["reasoning"]:
        print(f"    {item['text']}")
    print(
        f"  风险        {rec['risk_level']}  "
        f"(requires_approval: {str(rec['requires_approval']).lower()})"
    )
    for reason in rec["risk_reasons"]:
        print(f"    - {reason}")
    if rec.get("filtered_candidates"):
        print(f"  过滤        {', '.join(rec['filtered_candidates'])}")
    if r.get("decision"):
        print(f"  Decision    {r['decision']['id']} (status: {r['decision']['status']})")
        if r["decision"].get("approval_request_id"):
            print(f"  审批        {r['decision']['approval_request_id']} (9c ApprovalGate 绑定)")
    if r.get("event_seq"):
        print(f"  事件      intelligence.recommendation.completed seq={r['event_seq']}")


def _print_intelligence_decision_create(r: dict) -> None:
    """decision create 输出: Decision Artifact + 推荐/置信度/风险/Approval 绑定。"""
    d, res = r["decision"], r["result"]
    print(f"✔ 决策 {d['id']} 已创建 (status: {d['status']})")
    print(f"  type        {d['decision_type']}")
    print(f"  subject     {d['subject_id']}")
    print(f"  推荐        {res['recommendation']}")
    alts = ", ".join(res["alternatives"]) if res["alternatives"] else "-"
    print(f"  备选        {alts}")
    print(f"  置信度      {res['confidence']:.3f}")
    print(f"  风险        {res['risk_level']}  (requires_approval: {str(res['requires_approval']).lower()})")
    if res.get("approval_request_id"):
        print(f"  审批        {res['approval_request_id']} (9c ApprovalGate 绑定)")
    if r.get("event_seq"):
        print(f"  事件      intelligence.decision.created seq={r['event_seq']}")


def _print_intelligence_experience_list(r: dict) -> None:
    """experience list 输出: 经验记录清单 (subject 维度 + 结果/分数/置信度)。"""
    print(f"✔ 经验记录 {r['count']} 条")
    for e in r["experiences"]:
        print(
            f"  {e['id']}  {e['subject_type']}:{e['subject_id']}  "
            f"{e['result']}  score {e['score']:.2f}  conf {e['confidence']:.2f}"
        )
        if e.get("task_type") or e.get("capability"):
            tags = []
            if e.get("task_type"):
                tags.append(f"task={e['task_type']}")
            if e.get("capability"):
                tags.append(f"cap={','.join(e['capability'])}")
            print(f"      {' '.join(tags)}")
    if r.get("event_seq"):
        print(f"  事件      intelligence.viewed seq={r['event_seq']}")


def _print_intelligence_experience_evaluate(r: dict) -> None:
    """experience evaluate 输出: TaskEvaluation (推荐执行资源 + 置信度 + 风险)。"""
    ev = r["evaluation"]
    print(f"✔ 任务评估 (task: {ev['task_type']})")
    caps = ", ".join(ev["required_capabilities"]) if ev["required_capabilities"] else "-"
    print(f"  能力        {caps}")
    for label, key in (
        ("Agent", "recommended_agents"),
        ("Provider", "recommended_providers"),
        ("Skill", "recommended_skills"),
    ):
        entries = ev[key]
        if not entries:
            continue
        print(f"  推荐 {label}")
        for entry in entries:
            print(
                f"    {entry['id']}  score {entry['score']:.3f}  "
                f"({entry['records']} 条, 成功率 {entry['success_rate']:.0%})"
            )
    print(f"  置信度      {ev['confidence']:.3f}")
    if ev["risks"]:
        print("  风险")
        for risk in ev["risks"]:
            print(f"    - {risk}")
    if r.get("event_seq"):
        print(f"  事件      intelligence.task.evaluated seq={r['event_seq']}")


# ------------------------------------------------------------------ Phase 11A: Human Console 输出 (ADR-0034)


def _print_console(args: Any, r: dict) -> None:
    """factory console 输出: dashboard 七域汇总 / approvals 待审批清单。

    --json 已在 _print_output 前置处理; 本函数只渲染人类可读文本。
    Console 只读视图 (Human Layer): 输出不携带任何执行/审批指令
    (决策权永远在 9c Approval 状态机 product approval decide)。
    """
    if args.console_command == "dashboard":
        _print_console_dashboard(r)
    elif args.console_command == "approvals":
        _print_console_approvals(r)


def _print_console_dashboard(r: dict) -> None:
    """console dashboard 输出: 七域汇总 (项目/待审批/Agent/决策/成本/经验/活动)。"""
    d = r["dashboard"]
    projects = d.get("projects") or []
    approvals = d.get("approvals") or []
    agents = d.get("agents") or []
    decisions = d.get("decisions") or []
    cost = d.get("cost") or {}
    experience = d.get("experience") or {}
    activity = d.get("activity") or []
    print("Human Console — Dashboard 七域汇总 (只读)")
    print(
        f"  项目        {len(projects)}  "
        f"(active: {sum(1 for p in projects if p.get('status') == 'active')})"
    )
    print(
        f"  待审批      {sum(1 for a in approvals if a.get('status') == 'pending')}  "
        f"(共 {len(approvals)})"
    )
    print(
        f"  运行中 Agent {sum(1 for a in agents if a.get('status') == 'WORKING')}  "
        f"(共 {len(agents)})"
    )
    print(f"  最近决策    {len(decisions)}")
    print(f"  成本        ${cost.get('total_cost', 0.0):.6f}  ({cost.get('calls', 0)} calls)")
    print(
        f"  经验        {experience.get('total', 0)} 条  "
        f"(success_rate: {experience.get('success_rate', 0.0):.0%})"
    )
    print(f"  最近活动    {len(activity)} 条")
    if r.get("event_seq"):
        print(f"  事件      console.dashboard.viewed seq={r['event_seq']}")


def _print_console_approvals(r: dict) -> None:
    """console approvals 输出: 审批清单 (只读不决定)。"""
    rows = [
        [a["id"], a["artifact_id"], a["gate"], a["status"],
         f"{a['confidence']:.2f}", a.get("risk") or "-",
         a.get("idea_id") or "-"]
        for a in r["approvals"]
    ]
    print(_render_table(["Request", "Artifact", "Gate", "Status", "Conf", "Risk", "Idea"], rows))
    print(f"{r['count']} approvals (pending: {r['pending']})")
    if r.get("event_seq"):
        print(f"  事件      console.viewed seq={r['event_seq']} (view=approvals)")


# ------------------------------------------------------------------ Phase 16A: Organization 输出 (ADR-0036, factory-org Extension)


def _print_org(args: Any, r: dict) -> None:
    """factory org 输出 (非 JSON): company/employee/authority/knowledge 结果。

    --json 已在 _print_output 前置处理 (全局 JSON); 文本渲染与 factory-org
    独立 CLI (org/cli.py _print_result) 逐字一致 — 双 CLI 同构, 单一实现。
    错误结果 (cmd_* 返回 ok=False 错误 dict) → stderr, 不渲染正文。
    """
    if not r.get("ok"):
        print(f"error: {r.get('error')}", file=sys.stderr)
        return
    command = args.org_command
    if command == "member":
        # ★ 2026-09-21: 舰队成员归属（多公司/多部门落到执行的前提）
        if getattr(args, "member_command", "") == "list":
            rows = [[m["id"], m["role"], m["company_id"] or "（未归属）",
                     m["department_id"] or "-", m["status"]] for m in r.get("members") or []]
            print(_render_table(["成员", "角色", "公司", "部门", "状态"], rows))
            tail = f"{r.get('count', 0)} 人"
            if r.get("unassigned"):
                tail += f" · 未归属 {r['unassigned']} 人 ⇒ 用 `factory org member set --all --company <C>` 一次设好"
            print(tail)
            return
        print(f"✔ 已设归属: {r.get('count', 0)} 个成员 → 公司 {r.get('company')}"
              + (f" · 部门 {r.get('department')}" if r.get("department") else ""))
        return
    if command == "company":
        company = r["company"]
        if args.company_command == "create":
            print("✔ 公司创建成功 (模板实例化)")
            print(f"  id          {company['id']}")
            print(f"  name        {company['name']}")
            print(f"  template    {company['template']}")
            print(f"  departments {r['department_count']}")
        else:
            print(f"公司 {company['id']} — {company['name']} (模板: {company['template']})")
            for dept in r["departments"]:
                print(f"  部门  {dept['name']} ({dept['id']})")
            for role in r["roles"]:
                human = " [Human]" if role.get("human") else ""
                print(f"  角色  {role['name']} ({role['id']}){human}")
        if r.get("event_seq") is not None:
            print(f"  event_seq   {r['event_seq']}")
    elif command == "employee":
        if args.employee_command == "hire":
            emp = r["employee"]
            print("✔ 员工入职")
            print(f"  id        {emp['id']}")
            print(f"  name      {emp['name']}")
            print(f"  company   {emp['company_id']}")
            print(f"  roles     {', '.join(emp['role_ids'])}")
            print(f"  caps      {', '.join(emp['capabilities']) or '(无)'}")
            if r.get("event_seq") is not None:
                print(f"  event_seq {r['event_seq']}")
        else:
            print(f"员工清单 ({r['count']} 人)")
            for emp in r["employees"]:
                print(f"  {emp['id']}  {emp['name']}  {emp['company_id']}  "
                      f"roles={len(emp['role_ids'])} caps={len(emp['capabilities'])}")
    elif command == "authority":
        print(f"权限校验: {r['permission']} → {r['result']}")
        print(f"  roles     {', '.join(r['role_ids'])}")
        if r.get("event_seq") is not None:
            print(f"  event_seq {r['event_seq']}")
    elif command == "knowledge":
        if args.knowledge_command == "add":
            item = r["knowledge"]
            print("✔ 知识入库 (公司隔离)")
            print(f"  id        {item['id']}")
            print(f"  company   {item['company_id']}")
            print(f"  domain    {item['domain']}")
            print(f"  version   {item['version']}")
            if r.get("event_seq") is not None:
                print(f"  event_seq {r['event_seq']}")
        else:
            print(f"知识清单 ({r['count']} 条) — 公司 {r['company_id']}")
            for item in r["knowledge"]:
                print(f"  {item['id']}  [{item['domain']}] v{item['version']}  {item['content']}")


# ------------------------------------------------------------------ Phase A: Execution 输出 (ADR-0037, factory-exec Extension)


def _print_exec(args: Any, r: dict) -> None:
    """factory exec 输出 (非 JSON): run/status/approval 结果。

    --json 已在 _print_output 前置处理 (全局 JSON); 文本渲染与 factory-exec
    独立 CLI (exec/cli.py _print_result) 逐字一致 — 双 CLI 同构, 单一实现。
    错误结果 (cmd_* 返回 ok=False 错误 dict) → stderr, 不渲染正文。
    """
    if not r.get("ok"):
        print(f"error: {r.get('error')}", file=sys.stderr)
        return
    if args.exec_command == "run":
        print("✔ 执行完成" if r["status"] == "success" else "✘ 执行失败")
        print(f"  request_id  {r['request_id']}")
        print(f"  result_id   {r['result_id']}")
        print(f"  status      {r['status']}")
        if r.get("error"):
            print(f"  error       {r['error']}")
        for a in r.get("artifacts", []):
            print(f"  artifact    {a['type']:<12} {a['path']}")
        if r.get("usage"):
            print(f"  usage       {r['usage']}")
        if r.get("event_seq") is not None:
            print(f"  event_seq   {r['event_seq']}")
    elif args.exec_command == "status":
        print(f"执行结果 {r['count']} 条 (审批 {r.get('approval_count', 0)} 条)")
        for res in r.get("results", []):
            print(f"  {res['id']}  {res['status']:<8} {res['request_id']}")
        if r.get("event_seq") is not None:
            print(f"  event_seq   {r['event_seq']}")
    elif args.exec_command == "approval":
        sub = args.approval_command
        if sub in ("approve", "deny"):
            ap = r["approval"]
            print(f"审批 {ap['decision']}: {ap['id']}")
            print(f"  request_id  {ap['request_id']}")
            print(f"  decided_by  {ap['decided_by']}")
            if ap.get("comment"):
                print(f"  comment     {ap['comment']}")
            if r.get("event_seq") is not None:
                print(f"  event_seq   {r['event_seq']}")
        elif sub == "apply":
            ap = r["approval"]
            print(f"✔ patch 已应用: {ap['id']} (diff {r['patch_lines']} 行)")
            if r.get("event_seq") is not None:
                print(f"  event_seq   {r['event_seq']}")
        elif sub == "list":
            print(f"审批记录 {r['count']} 条")
            for ap in r.get("approvals", []):
                print(f"  {ap['id']}  {ap['decision']:<10} {ap['request_id']}  by {ap['decided_by']}")
            if r.get("event_seq") is not None:
                print(f"  event_seq   {r['event_seq']}")


# ------------------------------------------------------------------ Phase 13A: Demo 输出 (Demo Productization)


def _print_demo(args: Any, r: dict) -> None:
    """factory demo 输出: markpad 完整生命周期日志 (阶段/Artifact/Event/Decision/推荐/经验)。

    --json 已在 _print_output 前置处理 (全局 JSON); 本函数只渲染人类可读文本。
    """
    if args.demo_command == "markpad":
        _print_demo_markpad(r)
    else:
        print(f"✔ demo {r.get('demo', '-')} 完成")


def _print_demo_markpad(r: dict) -> None:
    """markpad demo 人类可读输出: 8 阶段日志 (Artifact/Event/Decision 三要素) + 汇总。"""
    idea = r.get("idea") or {}
    lifecycle = r.get("lifecycle") or {}
    print("✔ MarkPad Demo 完整生命周期完成")
    print(f"  idea       {idea.get('id', '-')}  {idea.get('title', '-')}")
    print(
        f"  lifecycle  {lifecycle.get('id', '-')}  "
        f"template={lifecycle.get('template', '-')}  status={lifecycle.get('status', '-')}"
    )
    if lifecycle.get("completed_at"):
        print(f"  completed  {lifecycle['completed_at']}")
    print(
        f"  root       {r.get('root', '-')}  "
        f"(临时工厂根, kept: {str(r.get('kept', False)).lower()})"
    )
    print(f"  approver   {r.get('approver', '-')}")
    print()
    for i, step in enumerate(r.get("stages") or [], start=1):
        print(f"[{i}] {step['stage']} — {step['action']}")
        artifact = step.get("artifact")
        if artifact:
            print(
                f"    Artifact  {artifact.get('id', '-')}  "
                f"{artifact.get('type', '-')}  v{artifact.get('version', '-')}  "
                f"status={artifact.get('status', '-')}"
            )
        approval = step.get("approval")
        if approval:
            print(
                f"    Decision  {approval.get('status', '-')}  "
                f"request={approval.get('id', '-')}  gate={approval.get('gate', '-')}  "
                f"by={approval.get('decided_by') or approval.get('by', '-')}"
            )
        for ev in step.get("events") or []:
            print(
                f"    Event     {ev.get('type', '-')}  "
                f"action={ev.get('action', '-')}  result={ev.get('result', '-')}  "
                f"seq={ev.get('seq', '-')}"
            )
    decisions = r.get("decisions") or []
    tasks = r.get("tasks") or []
    approvals = r.get("approvals") or []
    experiences = r.get("experiences") or []
    approval_experiences = r.get("approval_experiences") or []
    print()
    print("  汇总")
    print(f"    Decisions  {len(decisions)}")
    for d in decisions:
        print(f"      {d.get('id', '-')}  {d.get('type', '-')}  {d.get('status', '-')}")
    # ★ 2026-09-21 修（Founder 实测: 这里 Tasks 0 而工厂在干活 ⇒ 数字骗人 ✗）:
    #   这行数的是**旧任务表**（空的）; 执行的真实账本是【任务树】⇒ 两个都报, 并标清各自口径。
    print(f"    Tasks      {len(tasks)}  （旧任务表；执行真账本见下面『开发任务（任务树）』）")
    for t in tasks:
        print(f"      {t.get('id', '-')}  {t.get('title', '-')}  {t.get('status', '-')}")
    _tt = r.get("tasks_tree") or {}
    if _tt:
        print(f"    开发任务   {_tt.get('done', 0)}/{_tt.get('leaves', 0)} 叶完成"
              f"（任务树 = 执行的真实账本）· {_tt.get('plans', 0)} 棵树 · {_tt.get('by_status') or '{}'}")
    print(
        f"    Approvals  {len(approvals)}  "
        f"(pending: {sum(1 for a in approvals if a.get('status') == 'pending')})"
    )
    print(
        f"    经验       {len(experiences)} 条 + 审批经验 {len(approval_experiences)} 条"
    )
    print(
        f"    Events     {r.get('events_count', 0)}  "
        f"({', '.join(r.get('event_types') or [])})"
    )
    print("    推荐       mock (score 0.90, MockSelector — 只生成内容, 生命周期/审批/决策真实)")


if __name__ == "__main__":
    sys.exit(main())
