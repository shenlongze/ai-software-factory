"""metrics/models.py — FactoryMetrics 领域模型 (Pydantic v2, 只读投影)。

设计依据:
- phase5b-status.md: FactoryMetrics (tasks/executions/agents/workflows/validation/failures 子模型)
- ADR-0015 决策 1/2: 指标纯计算不持久化 (event-model §6 按需聚合); 快照 = 查询时刻
  的只读投影, 与 dashboard FactorySnapshot 同模式 — to_dict() 供 CLI --json 与
  测试断言共用 (model_dump(mode="json")), 时间戳统一 UTC 带时区。

口径 (ADR-0015 决策 3, 与 events/metrics.py 任务口径 / dashboard 执行口径并存):
- Task    total = TaskStore 任务数; completed = DONE 数; failed = 有 task.fail 的
          distinct 任务数; success_rate = completed / (completed + failed), 无终态 0.0。
- Execution total = 执行请求数; success/failed = 请求状态 SUCCESS/FAILED 数;
          first_attempt_success_rate = 每任务最早执行 (created_at, id 决胜) 已到
          终态的任务中, 首次执行即 SUCCESS 的比例 (ADR-0015 决策 4)。
- Agent   agents = {agent_id: AgentMetric} — assignment_count/success_count/
          failed_count/success_rate (来自 agent.assignment.* 事件, 注册表兜底 0);
          agents_total = 注册 Agent 数。
- Workflow run_count = 运行实例数; completed/failed = COMPLETED/FAILED 数;
          success_rate = completed / run_count (全部运行, 同 dashboard 执行口径)。
- Validation total_rules = validation.rule.completed 数; pass/fail/skip/error 计数;
          pass_rate = PASS / total_rules (含 SKIP/ERROR 分母), 无规则 0.0。
- Failure  failure_reason_count = task.fail 的失败原因直方图 (payload.stage 优先,
          回落 payload.error, 再回落 "unknown"), 次数降序。

空工厂: 所有字段默认值, collect/计算永不抛错。
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class TaskMetrics(BaseModel):
    """任务指标 (TaskStore + task.fail 事件)。"""

    total: int = 0
    completed: int = 0
    failed: int = 0
    success_rate: float = 0.0
    by_status: dict[str, int] = Field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class ExecutionMetrics(BaseModel):
    """执行指标 (RuntimeStore executions, 请求状态为权威)。"""

    total: int = 0
    success: int = 0
    failed: int = 0
    first_attempt_success_rate: float = 0.0
    by_status: dict[str, int] = Field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class AgentMetric(BaseModel):
    """单个 Agent 的分配/成败指标 (agent.assignment.* 事件聚合)。"""

    assignment_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    success_rate: float = 0.0

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class WorkflowMetrics(BaseModel):
    """工作流指标 (WorkflowStore 运行实例)。"""

    run_count: int = 0
    completed: int = 0
    failed: int = 0
    success_rate: float = 0.0
    definitions: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class ValidationMetrics(BaseModel):
    """验证指标 (validation.rule.completed 结果列聚合, 粒度数据单次一条)。"""

    total_rules: int = 0
    pass_count: int = 0
    fail_count: int = 0
    skip_count: int = 0
    error_count: int = 0
    pass_rate: float = 0.0
    runs: int = 0          # validation.completed 次数
    failed_runs: int = 0   # validation.failed 次数

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class FailureMetrics(BaseModel):
    """失败原因指标 (task.fail 直方图)。"""

    failure_reason_count: dict[str, int] = Field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class FactoryMetrics(BaseModel):
    """一次工厂指标聚合的完整只读投影 (六域子模型 + 项目维度)。"""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    project_id: str | None = None
    tasks: TaskMetrics = Field(default_factory=TaskMetrics)
    executions: ExecutionMetrics = Field(default_factory=ExecutionMetrics)
    agents: dict[str, AgentMetric] = Field(default_factory=dict)  # agent_id → 指标 (排序)
    agents_total: int = 0
    workflows: WorkflowMetrics = Field(default_factory=WorkflowMetrics)
    validation: ValidationMetrics = Field(default_factory=ValidationMetrics)
    failures: FailureMetrics = Field(default_factory=FailureMetrics)

    def to_dict(self) -> dict:
        """JSON 友好序列化 (CLI --json 输出 / 测试断言共用)。"""
        return self.model_dump(mode="json")
