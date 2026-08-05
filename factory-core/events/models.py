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
