"""workflows/models.py — Workflow 领域模型 (Pydantic v2)。

设计依据:
- phase4a-status.md: Workflow/WorkflowStep 模型 + 状态机
  (Workflow: CREATED/RUNNING/COMPLETED/FAILED; Step: PENDING/RUNNING/COMPLETED/FAILED)
- 参照 tasks/models.py 风格: 枚举宽容 parse + id 即文件名校验 + to_dict (JSON 友好)。
- WorkflowRun 为运行实例: 快照 workflow_id + step_states + status,
  与定义解耦 (定义可后续增改, 运行实例不受影响)。

时间戳统一 UTC 带时区, JSON 持久化由 model_dump(mode="json") 输出 ISO 字符串。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class WorkflowStatus(str, Enum):
    """工作流生命周期状态 (phase4a-status.md §状态机)。"""

    CREATED = "CREATED"        # 已创建 (尚未启动)
    RUNNING = "RUNNING"        # 运行中
    COMPLETED = "COMPLETED"    # 全部步骤完成 (终态)
    FAILED = "FAILED"          # 失败 (终态)

    @classmethod
    def parse(cls, value: str) -> "WorkflowStatus":
        """宽容解析: 大小写不敏感; 枚举对象直接返回; 非法值抛 ValueError。"""
        if isinstance(value, WorkflowStatus):
            return value
        try:
            return cls(str(value).strip().upper())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(f"invalid workflow status: {value!r} (expected one of: {valid})") from None


class StepStatus(str, Enum):
    """工作流步骤状态 (phase4a-status.md §状态机)。"""

    PENDING = "PENDING"        # 待执行
    RUNNING = "RUNNING"        # 执行中
    COMPLETED = "COMPLETED"    # 完成
    FAILED = "FAILED"          # 失败 (终态)

    @classmethod
    def parse(cls, value: str) -> "StepStatus":
        if isinstance(value, StepStatus):
            return value
        try:
            return cls(str(value).strip().upper())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(f"invalid step status: {value!r} (expected one of: {valid})") from None


def _id_sane(value: str) -> str:
    """id 即文件名/引用键: 拒绝空值、路径分隔符与相对路径。"""
    v = value.strip()
    if not v or v in {".", ".."} or "/" in v or "\\" in v:
        raise ValueError(f"invalid id: {value!r}")
    return v


class WorkflowStep(BaseModel):
    """工作流中的单个步骤定义 (纯声明: 不执行, 由后续 Phase 的 Agent Runtime 消费)。"""

    id: str
    name: str
    order: int                    # 执行顺序, 从 1 开始 (状态机按 order 推进)
    required_skill: str | None = None  # 所需技能 (Skill.id 引用, 声明性, 不自动校验)
    required_role: str | None = None   # 所需角色 (Agent.role 引用, 声明性, 不自动分配)

    @field_validator("id")
    @classmethod
    def _step_id_sane(cls, v: str) -> str:
        return _id_sane(v)

    @field_validator("order")
    @classmethod
    def _order_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"step order must be >= 1, got {v}")
        return v

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class Workflow(BaseModel):
    """一个工作流定义。定义性数据; 运行实例见 WorkflowRun。"""

    id: str
    name: str
    description: str = ""
    steps: list[WorkflowStep]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("id")
    @classmethod
    def _workflow_id_sane(cls, v: str) -> str:
        return _id_sane(v)

    @field_validator("steps")
    @classmethod
    def _steps_consistent(cls, v: list[WorkflowStep]) -> list[WorkflowStep]:
        if not v:
            raise ValueError("workflow must have at least one step")
        ids = [s.id for s in v]
        if len(set(ids)) != len(ids):
            raise ValueError(f"step ids must be unique: {ids}")
        orders = [s.order for s in v]
        if len(set(orders)) != len(orders):
            raise ValueError(f"step orders must be unique: {orders}")
        return v

    def step_ids(self) -> list[str]:
        """按 order 排序的步骤 id 列表。"""
        return [s.id for s in sorted(self.steps, key=lambda s: s.order)]

    def ordered_steps(self) -> list[WorkflowStep]:
        return sorted(self.steps, key=lambda s: s.order)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class StepState(BaseModel):
    """WorkflowRun 中单个步骤的运行状态 (可变)。"""

    step_id: str
    status: StepStatus = StepStatus.PENDING
    result: str | None = None      # 步骤结果 (complete_step 的 result; 审计/展示用)
    evidence: str | None = None    # 证据引用 (可选)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class WorkflowRun(BaseModel):
    """工作流运行实例 (任务维度): 一个 task 至多一个 run。

    - run_id: WR-XXX 自动编号 (store.next_run_id)
    - 快照 workflow_id/workflow_name: 与定义解耦, 定义被删不影响历史运行展示
    - step_states 按执行顺序排列; current_step = 下一个未完成步骤
    - 状态机: CREATED → RUNNING → COMPLETED; 任意非终态 → FAILED (终态, 无出口)
    """

    run_id: str
    workflow_id: str
    workflow_name: str = ""
    task_id: str
    step_states: list[StepState]
    status: WorkflowStatus = WorkflowStatus.CREATED
    current_step: str | None = None
    error: str | None = None       # FAILED 时的错误描述
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("run_id")
    @classmethod
    def _run_id_sane(cls, v: str) -> str:
        return _id_sane(v)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> WorkflowStatus:
        if isinstance(v, WorkflowStatus):
            return v
        return WorkflowStatus.parse(str(v))

    @classmethod
    def from_workflow(cls, *, run_id: str, workflow: Workflow, task_id: str) -> "WorkflowRun":
        """从定义创建实例: step_states 全 PENDING, 按 order 排列, current_step 指向第一步。"""
        ordered = workflow.ordered_steps()
        return cls(
            run_id=run_id,
            workflow_id=workflow.id,
            workflow_name=workflow.name,
            task_id=task_id,
            step_states=[StepState(step_id=s.id) for s in ordered],
            current_step=ordered[0].id if ordered else None,
        )

    def step_state(self, step_id: str) -> StepState | None:
        """按 step_id 取步骤状态; 不存在返回 None。"""
        for st in self.step_states:
            if st.step_id == step_id:
                return st
        return None

    def next_pending_step(self) -> StepState | None:
        """下一个待执行步骤: 按顺序第一个非 COMPLETED (含 PENDING/RUNNING/FAILED)。"""
        for st in self.step_states:
            if st.status is not StepStatus.COMPLETED:
                return st
        return None

    def all_steps_completed(self) -> bool:
        return bool(self.step_states) and all(
            st.status is StepStatus.COMPLETED for st in self.step_states
        )

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")
