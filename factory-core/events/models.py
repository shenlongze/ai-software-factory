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

    # --- Phase 9C: Human Decision Intelligence 事件 (增量扩展, ADR-0028) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # approval.* 为审批决策状态机生命周期事件 (source="product" 写路径): created
    # (请求落库) → pending (进入待审队列, workflow → paused) → approved|rejected|
    # changes_requested|delegated (终态决定) + resumed (workflow paused → running,
    # 自动恢复或 CLI workflow resume)。9a 既有 approval.required/granted/denied
    # 保留 (兼容: granted↔approved, denied↔rejected 语义映射, ADR-0028 决策 1)。
    # product.approval_experience.recorded 为审批经验记录事件 (ApprovalExperience
    # 落盘 — Provider/Agent 优化数据接口, 本阶段只记录不消费)。
    APPROVAL_CREATED = "approval.created"                      # 审批请求创建 (落库)
    APPROVAL_PENDING = "approval.pending"                      # 请求进入待审队列 (等待人工)
    APPROVAL_APPROVED = "approval.approved"                    # 审批通过 (终态, Product Decision)
    APPROVAL_REJECTED = "approval.rejected"                    # 审批拒绝 (终态, 回退重生成)
    APPROVAL_CHANGES_REQUESTED = "approval.changes_requested"  # 要求修改 (终态, 修改后重新审批)
    APPROVAL_DELEGATED = "approval.delegated"                  # 审批转派他人 (终态, 待被转派人决定)
    APPROVAL_RESUMED = "approval.resumed"                      # 工作流恢复 (paused → running)
    PRODUCT_APPROVAL_EXPERIENCE_RECORDED = "product.approval_experience.recorded"  # 审批经验落盘

    # --- Phase 9D: Product Lifecycle Orchestration 事件 (增量扩展, ADR-0029) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # product.lifecycle.* / product.stage.* / product.decision.* 为生命周期编排
    # 事件 (ProductLifecycleEngine, source="product"): lifecycle.started (启动)
    # → stage.entered (阶段进入) → ... → stage.completed (阶段完成) →
    # decision.created (决策链记录落库: Product → Architecture → Task Plan) →
    # lifecycle.completed (全部阶段完成, 终态事件单一)。payload 契约见
    # product/events.py — 事件唯一事实源: 阶段产物回填 (artifact_id/
    # approval_request_id/decision_id/task_id) 可从事件 payload 重建编排进度。
    PRODUCT_LIFECYCLE_STARTED = "product.lifecycle.started"            # 生命周期启动
    PRODUCT_STAGE_ENTERED = "product.stage.entered"                    # 阶段进入
    PRODUCT_STAGE_COMPLETED = "product.stage.completed"                # 阶段完成
    PRODUCT_DECISION_CREATED = "product.decision.created"              # 决策链记录落库
    PRODUCT_LIFECYCLE_COMPLETED = "product.lifecycle.completed"        # 生命周期完成 (终态)
    PRODUCT_LIFECYCLE_STATUS_VIEWED = "product.lifecycle.status_viewed"    # 生命周期状态被查看 (只读审计)
    PRODUCT_LIFECYCLE_TEMPLATES_VIEWED = "product.lifecycle.templates_viewed"  # 模板列表被查看 (只读审计)

    # --- Phase 10A-1: Intelligence Layer 事件 (增量扩展, ADR-0030) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # intelligence.* 为认知层 (factory-core/intelligence/, source="intelligence"
    # 写路径 / "cli" 读命令审计) 的审计事件: decision.created (Decision 落库 —
    # AI 推荐产物, 与 approval.* 人工确认语义分离, phase10a1-status.md §范围)、
    # recommendation.created (推荐 + 解释落库, 不自动执行)、experience.recorded
    # (经验记录落库 — 只记录不消费, 学习算法属 10A-4)、viewed (读命令审计,
    # ADR-0002: 所有 CLI 行为必须产生 Event)。payload 契约见 intelligence/events.py。
    INTELLIGENCE_DECISION_CREATED = "intelligence.decision.created"          # Decision 落库 (AI 推荐产物)
    INTELLIGENCE_RECOMMENDATION_CREATED = "intelligence.recommendation.created"  # Recommendation 落库 (推荐+解释)
    INTELLIGENCE_EXPERIENCE_RECORDED = "intelligence.experience.recorded"    # 经验记录落库 (只记录不消费)
    INTELLIGENCE_VIEWED = "intelligence.viewed"                              # Intelligence 数据被查看 (只读审计)

    # --- Phase 10A-2: Decision Intelligence 事件 (增量扩展, ADR-0031) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # intelligence.decision.* 为 DecisionIntelligence 引擎 (decision.py) 的决策链
    # 生命周期事件 (source="intelligence" 写路径): analysis.started (分析开始,
    # 载荷含 subject/decision_type/option_count/evidence_count) → analysis.completed
    # (分析完成, 载荷含 factors/observations_count/confidence) → option.evaluated
    # (逐选项规则评分完成, 每选项一条, 载荷含 option_id/name/score/factors) →
    # decision.created (10A-1 既有, Decision 落库 — 链终事件, 载荷回填
    # approval_request_id)。payload 契约见 intelligence/events.py。
    INTELLIGENCE_DECISION_ANALYSIS_STARTED = "intelligence.decision.analysis.started"      # 决策分析开始
    INTELLIGENCE_DECISION_ANALYSIS_COMPLETED = "intelligence.decision.analysis.completed"  # 决策分析完成
    INTELLIGENCE_DECISION_OPTION_EVALUATED = "intelligence.decision.option.evaluated"      # 选项规则评分完成

    # --- Phase 10A-3: Recommendation Engine 事件 (增量扩展, ADR-0032) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # intelligence.recommendation.* 为 RecommendationEngine 引擎 (recommend.py)
    # 的推荐链生命周期事件 (source="intelligence" 写路径): started (推荐开始,
    # 载荷含 task_type/required_capabilities/candidate_count) →
    # candidate.evaluated (逐候选评分, 每候选一条, 载荷含 candidate_id/type/
    # score/factors) → explained (解释生成, 载荷含 reasoning 分项计数) →
    # [recommendation.created (10A-1 既有, 落库时)] → completed (链终, 载荷含
    # top_candidate_id/score/confidence/risk_level/decision_id)。payload 契约
    # 见 intelligence/events.py。
    INTELLIGENCE_RECOMMENDATION_STARTED = "intelligence.recommendation.started"            # 推荐开始
    INTELLIGENCE_RECOMMENDATION_COMPLETED = "intelligence.recommendation.completed"        # 推荐完成 (链终)
    INTELLIGENCE_RECOMMENDATION_CANDIDATE_EVALUATED = "intelligence.recommendation.candidate.evaluated"  # 候选评分完成
    INTELLIGENCE_RECOMMENDATION_EXPLAINED = "intelligence.recommendation.explained"        # 推荐解释生成

    # --- Phase 10A-4: Experience Loop 事件 (增量扩展, ADR-0033) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # intelligence.experience.analyzed (经验分析完成 — ExperienceAnalyzer 只读
    # 聚合, 载荷含 subject/record_count/success_rate/effective_score) →
    # intelligence.task.evaluated (任务评估完成 — TaskEvaluator, 载荷含推荐
    # agents/providers/skills 计数/置信度/风险数) → intelligence.feedback.learned
    # (反馈闭环 — record_experience 把执行结果落库为经验, 载荷含 experience_id/
    # subject/result/score)。三事件构成 Feedback Loop: Task→Recommendation→
    # Execution→Result→Experience→更好推荐 (经验分析非自我修改: 只读聚合+记录,
    # 不自动改权重/生成 Skill/复制 Agent)。payload 契约见 intelligence/events.py。
    INTELLIGENCE_EXPERIENCE_ANALYZED = "intelligence.experience.analyzed"      # 经验分析完成 (只读聚合)
    INTELLIGENCE_TASK_EVALUATED = "intelligence.task.evaluated"                # 任务评估完成 (推荐执行资源)
    INTELLIGENCE_FEEDBACK_LEARNED = "intelligence.feedback.learned"            # 反馈闭环 (执行结果→经验记录)

    # --- Phase 11A: Human Console Layer 事件 (增量扩展, ADR-0034) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # console.* 为 Human Console (factory-console/, source="console"/"cli") 的
    # 只读审计事件: console.viewed (Console 任意视图被查看 — API 路由函数/CLI
    # 通用, 载荷含 view/计数汇总)、console.approval.opened (审批详情被打开 —
    # 只读打开, 不产生任何审批决定)、console.dashboard.viewed (Console Dashboard
    # 七域汇总被查看)。全部只读不写任何状态 (Human Layer 铁律, phase11a-status.md:
    # 不自动执行/不自动批准, 与既有 dashboard.viewed/metrics.viewed 同语义)。
    CONSOLE_VIEWED = "console.viewed"                    # Console 视图被查看 (只读审计)
    CONSOLE_APPROVAL_OPENED = "console.approval.opened"  # 审批详情被打开 (只读, 非决定)
    CONSOLE_DASHBOARD_VIEWED = "console.dashboard.viewed"  # Console Dashboard 被查看 (七域汇总)

    # --- Phase 16A: Organization Extension 事件 (增量扩展, ADR-0035) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, 不改表结构/API。
    # org.* 为组织域 (factory-org/ 独立 Extension, source="org"/"cli") 的审计
    # 事件: 写路径 company.created (模板实例化, 含部门/角色/权限子链事件) /
    # department.created / role.created / employee.joined|left (入职/离职) /
    # employee.capability_added (培训, 不自动提权) / employee.role_assigned
    # (转岗, 冲突组合注册表硬拒绝) / authority.granted|denied (Role 绑定,
    # 默认 deny — 未声明即拒绝) / knowledge.bound (知识入库, 公司隔离);
    # 读命令审计 (ADR-0002: 所有 CLI 行为必须产生 Event, 同 console.viewed):
    # company.viewed / employee.viewed / authority.checked / knowledge.viewed。
    # payload 契约见 factory-org/org/events.py — 事件唯一事实源: 从 payload
    # 可重建组织变化关键字段 (company_id/role_id/employee_id/permission 等)。
    ORG_COMPANY_CREATED = "org.company.created"              # 公司创建 (模板实例化)
    ORG_COMPANY_VIEWED = "org.company.viewed"                # 公司详情被查看 (只读审计)
    ORG_DEPARTMENT_CREATED = "org.department.created"        # 部门创建
    ORG_ROLE_CREATED = "org.role.created"                    # 职位创建 (权限矩阵物化)
    ORG_EMPLOYEE_JOINED = "org.employee.joined"              # 员工入职 (含角色/能力)
    ORG_EMPLOYEE_LEFT = "org.employee.left"                  # 员工离职 (权限即刻失效)
    ORG_EMPLOYEE_CAPABILITY_ADDED = "org.employee.capability_added"  # 能力培训 (不自动提权)
    ORG_EMPLOYEE_ROLE_ASSIGNED = "org.employee.role_assigned"  # 角色分配/转岗 (冲突硬拒)
    ORG_EMPLOYEE_VIEWED = "org.employee.viewed"              # 员工清单被查看 (只读审计)
    ORG_AUTHORITY_GRANTED = "org.authority.granted"          # 权限授予 (Role 绑定)
    ORG_AUTHORITY_DENIED = "org.authority.denied"            # 显式拒绝 (deny 优先)
    ORG_AUTHORITY_CHECKED = "org.authority.checked"          # 权限校验 (只读审计)
    ORG_KNOWLEDGE_BOUND = "org.knowledge.bound"              # 知识入库 (公司隔离)
    ORG_KNOWLEDGE_VIEWED = "org.knowledge.viewed"            # 知识清单被查看 (只读审计)
    # Phase A (factory-exec Extension, ADR-0037): org.execution.* 执行闭环
    # 事件链 — requested (ExecutionRequest 落库) → started (Runtime 开始,
    # 沙箱就绪) → completed|failed (执行终态, 单一) → approved (Human 审批
    # 通过) → applied (patch 应用, 批准后)。payload 契约见
    # factory-exec/exec/events.py — 事件唯一事实源: 从 payload 可重建执行
    # 闭环关键字段 (request_id/result_id/employee_id/agent_id/error/patch_path)。
    ORG_EXECUTION_REQUESTED = "org.execution.requested"      # 执行请求创建
    ORG_EXECUTION_STARTED = "org.execution.started"          # Runtime 开始执行 (沙箱就绪)
    ORG_EXECUTION_COMPLETED = "org.execution.completed"      # 执行成功 (产物齐全)
    ORG_EXECUTION_FAILED = "org.execution.failed"            # 执行失败 (Provider/沙箱错误)
    ORG_EXECUTION_APPROVED = "org.execution.approved"        # Human 审批通过
    ORG_EXECUTION_APPLIED = "org.execution.applied"          # patch 已应用 (批准后)
    ORG_EXECUTION_VIEWED = "org.execution.viewed"            # 执行结果/审批清单被查看 (只读审计, ADR-0002)
    # Sprint 7 S7-001 (factory-org Extension, ADR-0036 同扩展路径): 统一
    # 生命周期模型事件 — User→Project→Sprint→Workflow→Stage→Task→Artifact。
    # 同 ADR-0001 决策 1 扩展路径 (加枚举成员即可); payload 契约见
    # factory-org/org/events.py — 从 payload 可重建生命周期关键字段
    # (project_id/sprint_id/stage_id/artifact_id/lifecycle/task_id/type/ref)。
    ORG_PROJECT_CREATED = "org.project.created"              # 项目创建 (想法容器)
    ORG_PROJECT_LIFECYCLE_CHANGED = "org.project.lifecycle_changed"  # 生命周期流转 (idea→active→maintained→archived)
    ORG_PROJECT_TASK_LINKED = "org.project.task_linked"      # 项目 ↔ Core Task 关联 (Task 冻结, 扩展侧映射)
    ORG_SPRINT_CREATED = "org.sprint.created"                # Sprint 创建 (任务批次)
    ORG_SPRINT_TASK_ADDED = "org.sprint.task_added"          # 任务加入 Sprint
    ORG_STAGE_CREATED = "org.stage.created"                  # 组织级编排壳 Stage 创建 (Workflow 阶段)
    ORG_ARTIFACT_CREATED = "org.artifact.created"            # 阶段产物创建 (prd|design|code|test|release)
    # Sprint 7 S7-002 (factory-org Extension, 同扩展路径): Artifact System —
    # 产物生命周期完整化 (CREATED→GENERATED→VALIDATED→CONSUMED→ARCHIVED;
    # 异常 INVALID)。同 ADR-0001 决策 1 扩展路径 (加枚举成员即可);
    # updated|validated|consumed|failed|archived 为状态机转换事件 (每转换
    # audit, payload 含 from_status/to_status/version), viewed 为读命令审计
    # (ADR-0002: 所有 CLI 行为必须产生 Event)。payload 契约见
    # factory-org/org/events.py — 事件唯一事实源: 从 payload 可重建产物
    # 流转关键字段 (artifact_id/type/from_status/to_status/version/reason/
    # missing/errors)。
    ORG_ARTIFACT_UPDATED = "org.artifact.updated"            # 产物更新 (字段/元数据, 或 →generated)
    ORG_ARTIFACT_VALIDATED = "org.artifact.validated"        # 契约校验通过 (→validated)
    ORG_ARTIFACT_CONSUMED = "org.artifact.consumed"          # 产物被下一阶段消费 (→consumed)
    ORG_ARTIFACT_FAILED = "org.artifact.failed"              # 契约校验失败/执行失败 (→invalid)
    ORG_ARTIFACT_ARCHIVED = "org.artifact.archived"          # 软删归档 (→archived, 终态)
    ORG_ARTIFACT_VIEWED = "org.artifact.viewed"              # 产物清单/详情被查看 (只读审计)


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
