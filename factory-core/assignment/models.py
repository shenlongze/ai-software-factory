"""assignment/models.py — AgentAssignment 领域模型 (Pydantic v2)。

设计依据:
- phase4b3-status.md: AgentAssignment (id/agent_id/task_id/execution_id/workflow_step_id/
  status/created_at/completed_at) + AssignmentStatus (ASSIGNED/WORKING/COMPLETED/FAILED/RELEASED)。
- 参照 agents/workflows/runtime models 风格: 枚举宽容 parse + id 即存储键校验 + to_dict
  (JSON 友好)。时间戳统一 UTC 带时区, JSON 持久化由 model_dump(mode="json") 输出 ISO 字符串。

原则 (phase4b3-status.md): Agent != Assignment — Assignment 只存工作关系 (agent_id/
execution_id 等引用), 不内嵌 Agent 数据 (禁止复制)。任务与步骤同样以 id 引用。

状态机 (agent_allocator 执行转换, 本模型只声明状态):
  ASSIGNED → {WORKING, COMPLETED, FAILED, RELEASED}
  WORKING  → {COMPLETED, FAILED, RELEASED}
  COMPLETED/FAILED/RELEASED → 终态 (无出口)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AssignmentStatus(str, Enum):
    """工作关系生命周期状态 (phase4b3-status.md)。"""

    ASSIGNED = "ASSIGNED"      # 已分配 (Agent 已转 WORKING, 工作尚未开始)
    WORKING = "WORKING"        # 工作中 (任务已启动, start 后)
    COMPLETED = "COMPLETED"    # 工作完成 (终态; Agent 已回 AVAILABLE)
    FAILED = "FAILED"          # 工作失败 (终态; Agent 已回 AVAILABLE)
    RELEASED = "RELEASED"      # 提前解除 (终态; Agent 已回 AVAILABLE)

    @classmethod
    def parse(cls, value: str) -> "AssignmentStatus":
        """宽容解析: 大小写不敏感; 枚举对象直接返回; 非法值抛 ValueError (CLI 转用法错误退出码 2)。"""
        if isinstance(value, AssignmentStatus):
            return value
        try:
            return cls(str(value).strip().upper())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(f"invalid assignment status: {value!r} (expected one of: {valid})") from None


def _id_sane(value: str) -> str:
    """id 即存储键: 拒绝空值、路径分隔符与相对路径 (同 agents/tasks 模式)。"""
    v = value.strip()
    if not v or v in {".", ".."} or "/" in v or "\\" in v:
        raise ValueError(f"invalid id: {value!r}")
    return v


class AgentAssignment(BaseModel):
    """一条 Agent↔任务的工作关系记录 (非 Agent 数据本身, 见模块 docstring 原则)。"""

    id: str                              # ASG-XXX 自动编号 (store.next_id)
    agent_id: str                        # AgentRegistry 引用 (不内嵌 Agent 数据)
    task_id: str                         # 任务维度
    workflow_id: str | None = None       # 可选: 工作流定义引用 (审计/展示)
    workflow_step_id: str | None = None  # 可选: 步骤引用 (required_skill/role 来源)
    execution_id: str | None = None      # 可选: ExecutionRequest 引用 (自动分配后回填 agent_id)
    status: AssignmentStatus = AssignmentStatus.ASSIGNED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None  # COMPLETED/FAILED/RELEASED 时回填

    @field_validator("id", "agent_id", "task_id")
    @classmethod
    def _ids_sane(cls, v: str) -> str:
        return _id_sane(v)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> AssignmentStatus:
        if isinstance(v, AssignmentStatus):
            return v
        return AssignmentStatus.parse(str(v))

    def to_dict(self) -> dict:
        """JSON 友好序列化 (CLI --json 输出 / 文件持久化共用)。"""
        return self.model_dump(mode="json")
