"""cli/main.py — factory CLI 入口 (argparse, 标准库零依赖)。

命令 (phase2-status 核心子集): init / task create|list|status|update /
event logs / status / validate。
退出码 (cli-design §5): 0 成功 / 1 一般错误 / 2 用法 (argparse 默认) / 3 验证失败 / 7 未找到。

入口: `factory` console script 或 `.venv/bin/python -m cli.main`。
"""

from __future__ import annotations

import json
import sys
from typing import Any

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
    cmd_dashboard,
    cmd_event_logs,
    cmd_execution_list,
    cmd_execution_run,
    cmd_execution_status,
    cmd_git_commits,
    cmd_git_diff,
    cmd_git_status,
    cmd_init,
    cmd_intelligence_decision_create,
    cmd_intelligence_recommend,
    cmd_metrics,
    cmd_project_list,
    cmd_project_show,
    cmd_provider_list,
    cmd_provider_show,
    cmd_provider_test,
    cmd_provider_usage,
    cmd_provider_stats,
    cmd_provider_compare,
    cmd_provider_recommend,
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
    cmd_runtime_add,
    cmd_runtime_catalog_list,
    cmd_runtime_catalog_show,
    cmd_runtime_list,
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
    json_opt(sub.add_parser("init", help="初始化工厂: 目录骨架 + 事件库 (幂等)"))

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
    p_event = sub.add_parser("event", help="事件查询")
    json_opt(p_event)
    esub = p_event.add_subparsers(dest="event_command", required=True)
    p_logs = esub.add_parser("logs", help="事件日志查询, 倒序 (发 system.logs_viewed; --workspace 发 workspace.events.viewed)")
    json_opt(p_logs)
    p_logs.add_argument("--limit", type=int, default=20, help="条数上限 (默认 20)")
    p_logs.add_argument("--project", default=None, help="按项目过滤")
    p_logs.add_argument("--task", default=None, help="按任务过滤")
    p_logs.add_argument("--workspace", action="store_true",
                        help="跨项目事件时间线 (全量最近事件, 含 project 列, 发 workspace.events.viewed)")

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

    # factory project <sub> (Phase 5A: Example Layer, 只读)
    p_project = sub.add_parser("project", help="项目配置 (只读: examples/*/project.yaml)")
    json_opt(p_project)
    prsub = p_project.add_subparsers(dest="project_command", required=True)
    p_pr_list = prsub.add_parser("list", help="项目列表 (发 project.viewed)")
    json_opt(p_pr_list)
    p_pr_show = prsub.add_parser("show", help="项目详情: 技术栈/Agent/技能/工作流映射 (发 project.viewed)")
    json_opt(p_pr_show)
    p_pr_show.add_argument("name", help="项目名 (如 markpad)")

    # factory provider <sub> (Phase 8A, ADR-0022)
    p_provider = sub.add_parser(
        "provider", help="LLM Provider 管理: 智能来源目录 (默认 hermes + 注册定义, 发 provider.* 事件)"
    )
    json_opt(p_provider)
    pvsub = p_provider.add_subparsers(dest="provider_command", required=True)
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

    # factory product <sub> (Phase 9A, ADR-0026: Product Intelligence 基础)
    p_product = sub.add_parser(
        "product", help="Product Intelligence: Idea/Artifact/Approval/Workflow (独立空间 .factory/product/, 发 idea.*/approval.*/product.* 事件)"
    )
    json_opt(p_product)
    psub = p_product.add_subparsers(dest="product_command", required=True)
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

    return p


def main(argv: list[str] | None = None) -> int:
    """CLI 入口: 返回退出码 (console script 以返回值作为进程退出码)。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    ctx = FactoryContext(args.root)
    ctx.ensure_dirs()  # ADR-0002 决策 5: 所有命令幂等自建目录与 DB, 不强制先 init
    try:
        if args.command == "init":
            result = cmd_init(ctx)
        elif args.command == "task":
            result = _dispatch_task(ctx, args)
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
        elif args.command == "checkpoint":
            result = _dispatch_checkpoint(ctx, args)
        elif args.command == "recover":
            result = cmd_recover(ctx, args)
        elif args.command == "dashboard":
            result = cmd_dashboard(ctx, args)
        elif args.command == "metrics":
            result = cmd_metrics(ctx, args)
        elif args.command == "project":
            result = _dispatch_project(ctx, args)
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
        elif args.command == "product":
            result = _dispatch_product(ctx, args)
        elif args.command == "intelligence":
            result = _dispatch_intelligence(ctx, args)
        else:  # pragma: no cover — argparse required=True 已拦截
            raise CliError(f"unknown command: {args.command}", exit_code=2)
    except CliError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
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


def _dispatch_project(ctx: FactoryContext, args: Any) -> dict:
    if args.project_command == "list":
        return cmd_project_list(ctx, args)
    if args.project_command == "show":
        return cmd_project_show(ctx, args)
    raise CliError(f"unknown project command: {args.project_command}", exit_code=2)


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
    """product idea/approval/workflow/generate/experience 分发 (Phase 9A ADR-0026 + 9B ADR-0027)。"""
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
    raise CliError(
        f"unknown intelligence command: {args.intelligence_command}", exit_code=2
    )


# ------------------------------------------------------------------ 输出

def _print_output(args: Any, result: dict) -> None:
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.command == "init":
        _print_init(result)
    elif args.command == "task":
        _print_task(args.task_command, result)
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
    elif args.command == "checkpoint":
        _print_checkpoint(args.checkpoint_command, result)
    elif args.command == "recover":
        _print_recover(result)
    elif args.command == "dashboard":
        _print_dashboard(result)
    elif args.command == "metrics":
        _print_metrics(result)
    elif args.command == "project":
        _print_project(args.project_command, result)
    elif args.command == "provider":
        _print_provider(args.provider_command, result)
    elif args.command == "workspace":
        _print_workspace(args.workspace_command, result)
    elif args.command == "git":
        _print_git(args.git_command, result)
    elif args.command == "change":
        _print_change(args.change_command, result)
    elif args.command == "understand":
        _print_understand(args, result)
    elif args.command == "product":
        _print_product(args, result)
    elif args.command == "intelligence":
        _print_intelligence(args, result)


def _render_table(
    headers: list[str], rows: list[list[str]], *, empty: str | None = "  (无记录)",
) -> str:
    """渲染对齐表格; 空表 → empty 占位 (None 则仍渲染表头, 供恒定表头场景)。"""
    if not rows:
        if empty is None:
            widths = [len(h) for h in headers]
            return "\n".join([
                "  " + "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)),
                "  " + "  ".join("-" * widths[i] for i in range(len(headers))),
            ])
        return empty
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    lines = [
        "  " + "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)),
        "  " + "  ".join("-" * widths[i] for i in range(len(headers))),
    ]
    lines += ["  " + "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)) for row in rows]
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
        rows = [[t["id"], t["status"], t["type"], t["project"], t["title"], t["owner"] or "-"]
                for t in r["tasks"]]
        print(_render_table(["Task", "Status", "Type", "Project", "Title", "Owner"], rows))
        print(f"{r['count']} tasks")
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
    print(f"✔ 工厂状态 (root: {r['root']})")
    print(f"  projects  {r['projects_count']}  {r['projects']}")
    print(f"  tasks     {r['tasks_count']}  {r['tasks_by_status']}")
    print(f"  agents    {r['agents_count']}  {r['agents']}")
    print(f"  events    {r['events_count']}")


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
    from metrics.models import FactoryMetrics, WorkspaceComparison
    from metrics.reports import format_metrics, format_workspace_comparison

    if r.get("workspace"):  # metrics --workspace → 项目对比报告 (Phase 6B, ADR-0017)
        print(format_workspace_comparison(WorkspaceComparison.model_validate(r["comparison"])))
        return
    print(format_metrics(FactoryMetrics.model_validate(r["metrics"])))


def _print_project(sub: str, r: dict) -> None:
    if sub == "list":
        rows = [[p["name"], p["status"], p["language"], p["repository"] or "-",
                 ", ".join(p["tech_stack"]) or "-"] for p in r["projects"]]
        print(_render_table(["Project", "Status", "Language", "Repository", "Tech Stack"], rows))
        print(f"{r['count']} projects (source: {r['source']})")
    elif sub == "show":
        p = r["project"]
        print(f"{p['name']}  {p['description'] or ''}")
        print(f"  language    {p['language']}")
        print(f"  repository  {p['repository'] or '-'}")
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
        print(f"  事件      provider.viewed"
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


def _print_change(sub: str, r: dict) -> None:
    """factory change 输出: commits 提交表; analyze 路径分析; validate L4 判定;
    triggers 注册/列表; evaluate 规则判定; workflows workflow 链。"""
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
    """factory product 输出: idea create/list/show + approval request/decide/list
    + workflow start/status + generate + experience list/record (发对应
    idea.*/approval.*/product.* 审计事件; Phase 9A ADR-0026 + 9B ADR-0027)。"""
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


if __name__ == "__main__":
    sys.exit(main())
