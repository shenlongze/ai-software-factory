"""events/models.py — Event 领域模型 (Pydantic v2, 不可变)。

设计依据:
- phase1-plan.md §3: EventType 六类最小事件 + Event 模型
- event-model.md §2: 四个语义列 (stage/action/result/evidence) + project_id + payload

不可变 (frozen=True): append-only 语义的模型层保证, seq 回填经 model_copy(update=...) 返回新实例。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 统一 UTC 存储格式: 固定 26 字符, 字符串排序 == 时间排序 (SQLite 过滤/排序无歧义)
TS_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def format_timestamp(dt: datetime) -> str:
    """datetime → 统一存储格式 (UTC, 固定小数秒)。"""
    return dt.astimezone(timezone.utc).strftime(TS_FORMAT)


def parse_timestamp(s: str) -> datetime:
    """统一存储格式 → 带 UTC 时区的 datetime。"""
    return datetime.strptime(s, TS_FORMAT).replace(tzinfo=timezone.utc)


class EventType(str, Enum):
    """六类最小事件 (phase1-plan §3.1)。

    扩展策略: 后续按 event-model.md 六类字典 (task.*/agent.*/validation.*/workflow.*/system.*/human.*)
    扩类时"加枚举成员即可", 不改表结构 (type 列存字符串)。
    """

    TASK_START = "task.start"      # 任务开始: 任务定义、目标、开始时间
    TASK_END = "task.end"          # 任务结束: 结果 (done/failed)、耗时、产物指针
    TASK_FAIL = "task.fail"        # 任务失败: 失败阶段、错误摘要、证据指针
    TOOL_CALL = "tool.call"        # 工具调用: 工具名、参数摘要、结果摘要、耗时
    CHECKPOINT = "checkpoint"      # 停靠点落盘: 停靠点描述、落盘产物清单 (续跑生命线)
    SESSION_CLOSE = "session.close"  # 会话结束: 事件数、任务数、成败统计

    # --- Phase 2: Factory Control CLI 事件 (增量扩展, ADR-0002) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, type 列存字符串, 不改表结构。
    # 命名遵循 event-model.md §3 六类字典 (task.* / system.* / validation.*)。
    SYSTEM_INIT = "system.init"                # 工厂初始化
    SYSTEM_LOGS_VIEWED = "system.logs_viewed"  # 事件日志被查询
    SYSTEM_STATUS_VIEWED = "system.status_viewed"  # 工厂状态总览被查看
    TASK_CREATED = "task.created"              # 任务定义
    TASK_VIEWED = "task.viewed"                # 任务被查看 (列表/详情)
    TASK_UPDATED = "task.updated"              # 任务状态更新
    VALIDATION_STARTED = "validation.started"  # 独立验证开始
    VALIDATION_COMPLETED = "validation.completed"  # 独立验证结束 (result=PASS/FAIL)

    # --- Phase 3A: Validation Engine 事件 (增量扩展) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # 流程: validation.started → validation.rule.started → validation.rule.completed
    #       → validation.completed; 失败追加 validation.failed (phase3a-status.md)。
    VALIDATION_RULE_STARTED = "validation.rule.started"    # 单条验证规则开始
    VALIDATION_RULE_COMPLETED = "validation.rule.completed"  # 单条验证规则结束 (PASS/FAIL/SKIP/ERROR)
    VALIDATION_FAILED = "validation.failed"                # 验证失败 (result=FAIL)

    # --- Phase 3B: Agent + Skill Registry 事件 (增量扩展, ADR-0004) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # registered/updated/removed 为身份注册类事件, 与 event-model §3.2 的运行时事件
    # (started/action/summary/stopped) 互补; viewed 为读命令事件 (ADR-0002: 所有 CLI
    # 行为必须产生 Event)。
    AGENT_REGISTERED = "agent.registered"   # Agent 注册入库
    AGENT_UPDATED = "agent.updated"         # Agent 记录更新
    AGENT_REMOVED = "agent.removed"         # Agent 移除
    AGENT_VIEWED = "agent.viewed"           # Agent 列表被查看
    SKILL_REGISTERED = "skill.registered"   # Skill 注册入库
    SKILL_REMOVED = "skill.removed"         # Skill 移除
    SKILL_VIEWED = "skill.viewed"           # Skill 列表被查看

    # --- Phase 4A: Workflow Engine 事件 (增量扩展, ADR-0005) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # 运行时六事件 (phase4a-status.md §Event 集成): created → started → step.started →
    # step.completed → completed; 失败走 failed (终态)。payload 均含 workflow_id/task_id/
    # step_id/result。viewed 为读命令事件 (ADR-0002: 所有 CLI 行为必须产生 Event, 同 agent/skill)。
    WORKFLOW_CREATED = "workflow.created"          # 工作流定义注册
    WORKFLOW_STARTED = "workflow.started"          # 运行实例启动 (关联任务)
    WORKFLOW_STEP_STARTED = "workflow.step.started"    # 步骤开始执行
    WORKFLOW_STEP_COMPLETED = "workflow.step.completed"  # 步骤完成 (result=OK/FAIL/...)
    WORKFLOW_COMPLETED = "workflow.completed"      # 全部步骤完成
    WORKFLOW_FAILED = "workflow.failed"            # 运行失败 (终态)
    WORKFLOW_VIEWED = "workflow.viewed"            # 工作流列表/进度被查看

    # --- Phase 4B-1: Runtime Adapter 事件 (增量扩展, ADR-0006) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # runtime.* 为运行时注册表事件 (registered/removed); execution.* 为执行生命周期事件
    # (created → started → completed|failed, 对应 ExecutionStatus PENDING/RUNNING/SUCCESS/FAILED)。
    # 本阶段无具体 Runtime: started/completed/failed 的发射点在 4B-2 派发层 (ADR-0006 决策 1)。
    # viewed 为读命令事件 (ADR-0002: 所有 CLI 行为必须产生 Event, 同 agent/skill/workflow)。
    RUNTIME_REGISTERED = "runtime.registered"   # Runtime 身份注册入库
    RUNTIME_REMOVED = "runtime.removed"         # Runtime 移除
    RUNTIME_VIEWED = "runtime.viewed"           # Runtime 列表被查看
    EXECUTION_CREATED = "execution.created"     # 执行请求创建 (PENDING, 未派发)
    EXECUTION_STARTED = "execution.started"     # 执行开始 (派发, RUNNING)
    EXECUTION_COMPLETED = "execution.completed" # 执行成功 (SUCCESS, 终态)
    EXECUTION_FAILED = "execution.failed"       # 执行失败 (FAILED, 终态)
    EXECUTION_VIEWED = "execution.viewed"       # 执行记录列表被查看

    # --- Phase 4B-3: Agent Assignment 事件 (增量扩展, ADR-0008) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # agent.assignment.* 为工作关系生命周期事件 (created→started→completed|failed);
    # agent.released 为 Agent 回 AVAILABLE 的释放事件 (complete/fail/release 的后果,
    # 事件序 completed→released / failed→released)。viewed 为读命令事件
    # (ADR-0002: 所有 CLI 行为必须产生 Event, 同 agent/skill/workflow/execution)。
    ASSIGNMENT_CREATED = "agent.assignment.created"    # 分配创建 (ASSIGNED, Agent→WORKING)
    ASSIGNMENT_STARTED = "agent.assignment.started"    # 开始工作 (WORKING)
    ASSIGNMENT_COMPLETED = "agent.assignment.completed"  # 完成 (终态, Agent→AVAILABLE)
    ASSIGNMENT_FAILED = "agent.assignment.failed"      # 失败 (终态, Agent→AVAILABLE)
    AGENT_RELEASED = "agent.released"                  # Agent 释放回 AVAILABLE
    ASSIGNMENT_VIEWED = "agent.assignment.viewed"      # Assignment 列表被查看

    # --- Phase 4C-2: Execution Orchestration 事件 (增量扩展, ADR-0010) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # orchestration.* 为编排层 (OrchestrationEngine) 的高层流水线事件
    # (source="orchestration_engine"), 与 workflow.*/assignment.*/execution.*
    # 底层事件互补: started → (每步 step.started → step.completed) → completed;
    # 任一步失败 → failed (Workflow FAILED, 无半完成状态, phase4c2-status.md)。
    ORCHESTRATION_STARTED = "orchestration.started"          # 自动执行流水线开始
    ORCHESTRATION_STEP_STARTED = "orchestration.step.started"    # 单步编排开始 (匹配/分配/执行)
    ORCHESTRATION_STEP_COMPLETED = "orchestration.step.completed"  # 单步编排完成 (result=OK)
    ORCHESTRATION_COMPLETED = "orchestration.completed"      # 全部步骤完成 (Workflow COMPLETED)
    ORCHESTRATION_FAILED = "orchestration.failed"            # 流水线失败 (Workflow FAILED / 前置错误)

    # --- Phase 4C-3: Checkpoint Recovery 事件 (增量扩展, ADR-0011) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # recovery.* 为恢复域审计事件 (source="recovery_service"), 覆盖两个操作流:
    # checkpoint: started (stage=checkpoint) → completed; recover: started →
    # completed (result=OK 可恢复 / rejected 已终态拒绝) 或 failed (异常)。
    # 载荷均含 task_id/state/resume_ok/actions (phase4c3-status.md §Event 集成)。
    RECOVERY_STARTED = "recovery.started"      # 恢复操作开始 (checkpoint/recover)
    RECOVERY_COMPLETED = "recovery.completed"  # 恢复操作完成 (含 resume_ok/actions)
    RECOVERY_FAILED = "recovery.failed"        # 恢复失败 (异常/前置错误)

    # --- Phase 4C-4: Dashboard 事件 (增量扩展, ADR-0012) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # dashboard.* 为只读控制台审计事件 (ADR-0002: 所有 CLI 行为必须产生 Event);
    # 载荷含 view 与各域计数汇总, 只读不写任何状态 (phase4c4-status.md §Event 集成)。
    DASHBOARD_VIEWED = "dashboard.viewed"      # Dashboard 被查看 (只读查询)

    # --- Phase 5A: Project Example Layer 事件 (增量扩展, ADR-0013) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # project.* 为项目配置示例层 (examples/*/project.yaml, 只读声明, ADR-0013) 的
    # 审计事件 (ADR-0002: 所有 CLI 行为必须产生 Event); 载荷含项目名/语言/各映射计数。
    PROJECT_VIEWED = "project.viewed"          # 项目配置被查看 (list/show, 只读)

    # --- Phase 5A.1: Runtime Catalog 事件 (增量扩展, ADR-0014) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # runtime.catalog.* 为能力目录 (RuntimeCatalog, source="runtime_catalog")
    # 的审计事件: registered/removed 为写路径事件 (register/remove); viewed 为
    # 读命令事件 (ADR-0002: 所有 CLI 行为必须产生 Event, 同 runtime/agent/viewed)。
    # Catalog=能力描述层, 与 runtime.registered (实例注册表) 语义分离 (ADR-0014 决策 2)。
    RUNTIME_CATALOG_REGISTERED = "runtime.catalog.registered"  # 定义注册入库
    RUNTIME_CATALOG_REMOVED = "runtime.catalog.removed"        # 定义移除
    RUNTIME_CATALOG_VIEWED = "runtime.catalog.viewed"          # 目录被查看 (list/show)

    # --- Phase 5B: Metrics Intelligence Layer 事件 (增量扩展, ADR-0015) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # metrics.viewed 为只读指标查询的审计事件 (ADR-0002: 所有 CLI 行为必须产生
    # Event, 同 dashboard.viewed); 载荷含六域指标计数汇总, 只读不写任何状态
    # (phase5b-status.md §Event 集成)。
    METRICS_VIEWED = "metrics.viewed"      # 工厂指标被查看 (只读聚合)

    # --- Phase 6A: Multi Project Workspace 事件 (增量扩展, ADR-0016) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # workspace.* 为 Workspace (workspace.yaml + 项目组织) 生命周期事件
    # (source="workspace"): created 由 WorkspaceManager.create_workspace 发出;
    # viewed 为读命令事件 (ADR-0002: 所有 CLI 行为必须产生 Event, 同 project.viewed)。
    # project.registered/removed 为项目进出 workspace.projects 引用列表的
    # 写路径事件 (manager 发出, 载荷含语言/状态/映射计数, phase6a-status.md)。
    WORKSPACE_CREATED = "workspace.created"      # Workspace 创建 (workspace.yaml 落地)
    WORKSPACE_VIEWED = "workspace.viewed"        # Workspace 被查看 (show, 只读)
    PROJECT_REGISTERED = "project.registered"    # 项目加入 workspace.projects
    PROJECT_REMOVED = "project.removed"          # 项目从 workspace.projects 移除

    # --- Phase 6B: Workspace Operations Dashboard 事件 (增量扩展, ADR-0017) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # workspace.*.viewed 为跨项目只读运营视图的审计事件 (ADR-0002: 所有 CLI
    # 行为必须产生 Event, 同 dashboard.viewed/metrics.viewed); 载荷含各视图
    # 计数汇总, 只读不写任何状态 (phase6b-status.md §Event 集成)。
    WORKSPACE_DASHBOARD_VIEWED = "workspace.dashboard.viewed"  # Workspace Summary 被查看 (--workspace)
    WORKSPACE_METRICS_VIEWED = "workspace.metrics.viewed"      # 项目对比指标被查看 (metrics --workspace)
    WORKSPACE_EVENTS_VIEWED = "workspace.events.viewed"        # 跨项目事件时间线被查看 (event logs --workspace)

    # --- Phase 6C: Git Integration Layer 事件 (增量扩展, ADR-0018) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # git.* 为仓库只读查询 + 变更审计事件 (source="cli"/"git"): status.viewed /
    # commit.viewed 为读命令事件 (ADR-0002: 所有 CLI 行为必须产生 Event, 同
    # dashboard.viewed); change.detected 在变更被检测/绑定 (bind_task_change)
    # 时发出 — Git 只读铁律: 本域事件只审计, 不触发任何仓库写操作
    # (phase6c-status.md §禁止: 无 push/merge/rebase)。
    GIT_STATUS_VIEWED = "git.status.viewed"        # 仓库状态被查看 (branch/current_commit/changes)
    GIT_CHANGE_DETECTED = "git.change.detected"    # 工作区变更被检测/与任务关联 (审计)
    GIT_COMMIT_VIEWED = "git.commit.viewed"        # 提交历史被查看 (只读)

    # --- Phase 6D: Change Intelligence Layer 事件 (增量扩展, ADR-0019) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # git.task.bound 在 Task↔分支/变更绑定成功时发出 (linker/bind); git.commit.linked
    # 在 commit message/分支名解析出 task_id 并回填时发出 (commit parser); change.analyzed
    # 在 ChangeAnalyzer 路径分析完成时发出; change.validation.completed 在 L4 Change
    # Validation 判定完成时发出 (result=PASS/FAIL/SKIP)。全部只审计, 不触发任何仓库写
    # 操作 (Git 只读铁律, phase6d-status.md)。
    GIT_TASK_BOUND = "git.task.bound"                          # Task↔git 分支/变更绑定
    GIT_COMMIT_LINKED = "git.commit.linked"                    # commit → task_id 关联
    CHANGE_ANALYZED = "change.analyzed"                        # 变更路径分析完成
    CHANGE_VALIDATION_COMPLETED = "change.validation.completed"  # L4 Change 验证完成

    # --- Phase 6E: Change Driven Workflow Layer 事件 (增量扩展, ADR-0020) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # change.trigger.* 为触发器生命周期事件: created (register 写路径) / viewed
    # (triggers list 读命令审计, ADR-0002) / evaluated (evaluate 评估完成,
    # result=PASS/FAIL/SKIP/ERROR, 载荷含 rules/triggered_workflow/run_id)。
    # change.workflow.* 为触发工作流生命周期事件: started (触发成功, run 已创建
    # RUNNING) / completed (执行终态, result=COMPLETED/FAILED — 触发失败不级联,
    # 失败恢复语义见 ADR-0020 决策 3)。全部只审计 + 触发既有 WorkflowEngine/
    # OrchestrationPipeline (复用不复制, 不修改 workflow/execution 模块)。
    CHANGE_TRIGGER_CREATED = "change.trigger.created"        # ChangeTrigger 注册
    CHANGE_TRIGGER_VIEWED = "change.trigger.viewed"          # 触发器列表被查看 (只读)
    CHANGE_TRIGGER_EVALUATED = "change.trigger.evaluated"    # 规则评估完成 (含触发结果)
    CHANGE_WORKFLOW_STARTED = "change.workflow.started"      # 触发工作流启动 (run RUNNING)
    CHANGE_WORKFLOW_COMPLETED = "change.workflow.completed"  # 触发工作流执行终态 (COMPLETED/FAILED)

    # --- Phase 7: Project Understanding Layer 事件 (增量扩展, ADR-0021) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # understanding.* 为项目理解层 (UnderstandingService, source="understanding")
    # 的分析生命周期事件: started (分析开始) → completed (成功, payload 含
    # path/stage/confidence/artifacts/missing) | failed (异常/路径无效, payload
    # 含 path/error)。viewed 为读命令审计事件 (ADR-0002: 所有 CLI 行为必须产生
    # Event, 同 dashboard.viewed — CLI 经 source="cli" 发出)。只读分析:
    # 本域事件只审计, 不触发任何写操作 (phase7-plan.md §Core 边界)。
    UNDERSTANDING_STARTED = "understanding.started"      # 项目分析开始
    UNDERSTANDING_COMPLETED = "understanding.completed"  # 分析完成 (stage/artifacts)
    UNDERSTANDING_FAILED = "understanding.failed"        # 分析失败 (异常/路径无效)
    UNDERSTANDING_VIEWED = "understanding.viewed"        # 理解报告被查看 (CLI 只读审计)

    # --- Phase 8A: LLM Provider Abstraction 事件 (增量扩展, ADR-0022) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # provider.* 为智能来源层 (providers/, source="provider_registry"/"cli") 的
    # 审计事件: 生命周期 provider.registered / provider.removed / provider.viewed;
    # 执行 provider.selected → provider.execution.started → completed|failed
    # (phase8-plan.md §Q6)。viewed 为读命令事件 (ADR-0002: 所有 CLI 行为必须产生
    # Event, 同 runtime.catalog.viewed)。与 runtime.*/execution.* (执行机制) 语义
    # 分离 — Provider=智能来源, Runtime=执行机制 (phase8-plan.md §Q1)。
    PROVIDER_REGISTERED = "provider.registered"          # Provider 定义注册入库
    PROVIDER_REMOVED = "provider.removed"                # Provider 定义移除
    PROVIDER_VIEWED = "provider.viewed"                  # Provider 目录被查看 (list/show)
    PROVIDER_SELECTED = "provider.selected"              # Provider 被选中 (执行选择/设默认)
    PROVIDER_EXECUTION_STARTED = "provider.execution.started"    # Provider 调用开始
    PROVIDER_EXECUTION_COMPLETED = "provider.execution.completed"  # Provider 调用成功 (终态)
    PROVIDER_EXECUTION_FAILED = "provider.execution.failed"      # Provider 调用失败 (终态)

    # --- Phase 8B-2: Provider Capability & Cost Layer 事件 (增量扩展) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # provider.usage.recorded 在使用记录落盘 (UsageStore.record / 集成层) 时
    # 发出: payload 含 provider_id/execution_id/tokens/estimated_cost/latency_ms/
    # success (phase8b2-plan.md §6) — 估算计量 (非真实计费), 与 provider.*
    # 既有事件互补 (usage 是调用后的计量审计, selected 是调用前的选择审计)。
    PROVIDER_USAGE_RECORDED = "provider.usage.recorded"  # 使用记录落盘 (估算成本)

    # --- Phase 8B-3: Provider Execution Intelligence 事件 (增量扩展) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # provider.feedback.created 在人工反馈落盘 (FeedbackStore.add / 集成层) 时
    # 发出: payload 含 provider_id/execution_id/task_id/rating/approved/comment
    # (phase8b3-status.md §4) — 执行经验 (Human Feedback) 是 Intelligence
    # Loop 的最后一环, 本阶段只记录 (数据接口), 不消费/不自动切换。
    PROVIDER_FEEDBACK_CREATED = "provider.feedback.created"  # 人工反馈落盘

    # --- Phase 9A: Product Intelligence Layer 事件 (增量扩展, ADR-0026) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # idea.* 为产品想法生命周期事件 (created 写路径 / viewed 读命令审计 /
    # updated 状态流转); approval.* 为审批门生命周期事件 (required = 申请落库,
    # granted/denied = 终态决定, viewed 读命令审计 — 任何 Artifact 可申请,
    # 门不绑定 PRD/UI); product.* 为产品工作流事件 (started 启动 / status_viewed
    # 读命令审计)。全部经 product/events.py 辅助发出 (source="product" 写路径,
    # source="cli" 读命令, ADR-0002); payload 契约见 product/events.py 与
    # phase9a-status.md §Event 集成。
    IDEA_CREATED = "idea.created"                    # 产品想法创建 (含 product_idea Artifact)
    IDEA_VIEWED = "idea.viewed"                      # 想法列表/详情被查看 (只读审计)
    IDEA_UPDATED = "idea.updated"                    # 想法更新 (status 流转)
    APPROVAL_REQUIRED = "approval.required"          # 审批请求创建 (workflow → awaiting_approval)
    APPROVAL_GRANTED = "approval.granted"            # 审批通过 (产生 Product Decision Artifact)
    APPROVAL_DENIED = "approval.denied"              # 审批拒绝 (回退重生成)
    APPROVAL_VIEWED = "approval.viewed"              # 审批清单被查看 (只读审计)
    PRODUCT_WORKFLOW_STARTED = "product.workflow.started"        # 产品工作流启动
    PRODUCT_WORKFLOW_STATUS_VIEWED = "product.workflow.status_viewed"  # 工作流状态被查看 (只读审计)

    # --- Phase 9B: Product Provider Generation 事件 (增量扩展, ADR-0027) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # product.generation.* 为 AI 生成生命周期事件 (ProductGenerator 编排, source=
    # "product"): started (生成开始, 已选定 Provider) → completed (Artifact 产出 +
    # Lineage 记录 + 自动审批请求) | failed (无 Provider/无 Adapter/生成失败,
    # result=ERROR — 明确错误不静默)。product.experience.* 为人工经验记录事件
    # (GenerationExperience 落盘): recorded 为写路径 (record_experience);
    # viewed 为读命令审计 (ADR-0002: 所有 CLI 行为必须产生 Event, 同 idea.viewed)。
    PRODUCT_GENERATION_STARTED = "product.generation.started"        # 生成开始 (Provider 已选定)
    PRODUCT_GENERATION_COMPLETED = "product.generation.completed"    # 生成完成 (Artifact + Lineage)
    PRODUCT_GENERATION_FAILED = "product.generation.failed"          # 生成失败 (明确错误, result=ERROR)
    PRODUCT_EXPERIENCE_RECORDED = "product.experience.recorded"      # 人工经验记录落盘
    PRODUCT_EXPERIENCE_VIEWED = "product.experience.viewed"          # 经验清单被查看 (只读审计)


class Event(BaseModel):
    """一条事件。append-only: 写入后永不修改、永不删除。"""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: uuid4().hex)  # 全局唯一
    seq: int = 0                      # 单调递增序号, 由存储层分配 (回放锚点)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    type: EventType                   # 事件类型 (六类)
    source: str                       # 发布模块, 如 "cli" / "orchestrator" / "agent"
    project_id: str | None = None     # 可选: 项目维度
    task_id: str | None = None        # 可选: 任务维度
    agent_id: str | None = None       # 可选: Agent 维度
    stage: str | None = None          # 事件发生时对象的状态/阶段 (event-model §2.2)
    action: str | None = None         # 动作简述 (自然语言, 检索友好)
    result: str | None = None         # 判定结果, 可机读 (OK/PASS/FAIL/ERROR/done/failed/...)
    evidence: str | None = None       # 证据引用 (ref:// 或文件路径)
    payload: dict[str, Any] = Field(default_factory=dict)  # 类型相关扩展载荷 (JSON 友好)

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, v: Any) -> EventType:
        return EventType(v) if isinstance(v, str) else v

    @field_validator("payload")
    @classmethod
    def _payload_json_safe(cls, v: dict[str, Any]) -> dict[str, Any]:
        try:
            json.dumps(v)  # 序列化失败则抛错, 拒绝入库
        except TypeError as exc:  # Pydantic v2 只把 ValueError/AssertionError 转 ValidationError
            raise ValueError(f"payload must be JSON-serializable: {exc}") from exc
        return v

    @classmethod
    def create(
        cls,
        type_: EventType | str,
        *,
        source: str,
        project_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        stage: str | None = None,
        action: str | None = None,
        result: str | None = None,
        evidence: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Event:
        """工厂方法: 生成 uuid event_id + UTC 时间戳。

        type_ 传字符串时由模型 _coerce_type validator 处理 (非法值 → ValidationError)。
        """
        return cls(
            event_id=uuid4().hex,
            timestamp=datetime.now(timezone.utc),
            type=cast(EventType, type_),
            source=source,
            project_id=project_id,
            task_id=task_id,
            agent_id=agent_id,
            stage=stage,
            action=action,
            result=result,
            evidence=evidence,
            payload=payload if payload is not None else {},
        )

    def to_row(self) -> tuple:
        """转 SQLite 行 (含语义列, payload 为 JSON 字符串)。"""
        return (
            self.event_id,
            format_timestamp(self.timestamp),
            self.type.value,
            self.source,
            self.project_id,
            self.task_id,
            self.agent_id,
            self.stage,
            self.action,
            self.result,
            self.evidence,
            json.dumps(self.payload, ensure_ascii=False),
        )

    @classmethod
    def from_row(cls, row: Any) -> Event:
        """从 SQLite 行重建 Event (seq 由存储层回填)。"""
        return cls(
            event_id=row["event_id"],
            seq=row["seq"],
            timestamp=parse_timestamp(row["timestamp"]),
            type=row["type"],
            source=row["source"],
            project_id=row["project_id"],
            task_id=row["task_id"],
            agent_id=row["agent_id"],
            stage=row["stage"],
            action=row["action"],
            result=row["result"],
            evidence=row["evidence"],
            payload=json.loads(row["payload"]),
        )
