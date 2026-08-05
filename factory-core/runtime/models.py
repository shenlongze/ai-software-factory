"""runtime/models.py — Runtime 领域模型 (Pydantic v2): 执行请求/结果 + 运行时注册信息。

设计依据:
- phase4b1-status.md: ExecutionRequest/ExecutionResult (ExecutionStatus:
  PENDING/RUNNING/SUCCESS/FAILED) + RuntimeInfo (RuntimeStatus: AVAILABLE/DISABLED)。
- 参照 tasks/agents/workflows models 风格: 枚举宽容 parse + id 即存储键校验 + to_dict
  (JSON 友好)。时间戳统一 UTC 带时区, JSON 持久化由 model_dump(mode="json") 输出 ISO 字符串。

ExecutionRequest.status: 任务指令字段清单 (id/task_id/workflow_id/step_id/agent_id/runtime_id/
input/created_at) 未列 status, 但"创建 pending execution (状态 PENDING)"与 execution.created
事件载荷均需请求级状态 — 故补 status 字段 (默认 PENDING), 见 ADR-0006 决策 2。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ExecutionStatus(str, Enum):
    """执行生命周期状态 (phase4b1-status.md: PENDING/RUNNING/SUCCESS/FAILED)。"""

    PENDING = "PENDING"    # 已创建, 待派发执行
    RUNNING = "RUNNING"    # 派发中 (Runtime 正在执行)
    SUCCESS = "SUCCESS"    # 执行成功 (终态)
    FAILED = "FAILED"      # 执行失败 (终态)

    @classmethod
    def parse(cls, value: str) -> "ExecutionStatus":
        """宽容解析: 大小写不敏感; 枚举对象直接返回; 非法值抛 ValueError。"""
        if isinstance(value, ExecutionStatus):
            return value
        try:
            return cls(str(value).strip().upper())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(f"invalid execution status: {value!r} (expected one of: {valid})") from None


class RuntimeStatus(str, Enum):
    """Runtime 注册表状态 (phase4b1-status.md: AVAILABLE/DISABLED)。"""

    AVAILABLE = "AVAILABLE"  # 可用 (参与派发)
    DISABLED = "DISABLED"    # 禁用 (不参与派发)

    @classmethod
    def parse(cls, value: str) -> "RuntimeStatus":
        """宽容解析: 大小写不敏感; 枚举对象直接返回; 非法值抛 ValueError。"""
        if isinstance(value, RuntimeStatus):
            return value
        try:
            return cls(str(value).strip().upper())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(f"invalid runtime status: {value!r} (expected one of: {valid})") from None


def _id_sane(value: str) -> str:
    """id 即存储键: 拒绝空值、路径分隔符与相对路径。"""
    v = value.strip()
    if not v or v in {".", ".."} or "/" in v or "\\" in v:
        raise ValueError(f"invalid id: {value!r}")
    return v


class ExecutionRequest(BaseModel):
    """一次执行请求 (Runtime Adapter 的输入契约, architecture.md §7.1 AgentRunRequest 落地)。

    - workflow_id/step_id/agent_id/runtime_id 均可选: 引擎创建的请求绑定工作流与步骤
      (execute_step); 独立执行的请求可留空。runtime_id 由派发层经
      RuntimeRegistry.resolve_runtime_id 填充 (Phase 4B-2)。
    - input 为运行时输入载荷 (JSON 友好 dict); 本阶段引擎创建时为空 {}。
    - status 默认 PENDING: 创建即待执行, 不自动调用 Runtime (ADR-0006 决策 2)。
    """

    id: str
    task_id: str
    workflow_id: str | None = None
    step_id: str | None = None
    agent_id: str | None = None
    runtime_id: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    status: ExecutionStatus = ExecutionStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("id")
    @classmethod
    def _execution_id_sane(cls, v: str) -> str:
        return _id_sane(v)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> ExecutionStatus:
        if isinstance(v, ExecutionStatus):
            return v
        return ExecutionStatus.parse(str(v))

    def to_dict(self) -> dict:
        """JSON 友好序列化 (CLI --json 输出 / 文件持久化共用)。"""
        return self.model_dump(mode="json")


class ExecutionResult(BaseModel):
    """一次执行的结果 (Runtime Adapter 的输出契约, architecture.md §7.1 AgentRunResult 落地)。

    - status: 终态 SUCCESS/FAILED (PENDING/RUNNING 为请求中间态, 结果不落; 校验强制)。
    - output: 结构化输出 (JSON 友好 dict); error: 失败时的错误描述。
    - request_id: 关联的 ExecutionRequest.id (一次执行至多一个结果, 存储以 request_id 为键)。
    """

    id: str
    request_id: str
    status: ExecutionStatus = ExecutionStatus.SUCCESS
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("id")
    @classmethod
    def _result_id_sane(cls, v: str) -> str:
        return _id_sane(v)

    @field_validator("request_id")
    @classmethod
    def _request_id_sane(cls, v: str) -> str:
        return _id_sane(v)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> ExecutionStatus:
        if isinstance(v, ExecutionStatus):
            return v
        return ExecutionStatus.parse(str(v))

    @field_validator("status")
    @classmethod
    def _status_terminal(cls, v: ExecutionStatus) -> ExecutionStatus:
        """结果只能是终态: PENDING/RUNNING 属于请求, 不属于结果。"""
        if v not in (ExecutionStatus.SUCCESS, ExecutionStatus.FAILED):
            raise ValueError(f"execution result status must be SUCCESS or FAILED, got {v.value}")
        return v

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class RuntimeInfo(BaseModel):
    """一个已注册 Runtime 的身份记录 (注册表数据, 非实现)。

    - type: 运行时类型 (如 "agent"); 本阶段无具体实现, 仅登记身份。
    - status: AVAILABLE/DISABLED (注册表状态; DISABLED 不参与派发)。
    """

    id: str
    name: str
    type: str = "agent"
    description: str = ""
    status: RuntimeStatus = RuntimeStatus.AVAILABLE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("id")
    @classmethod
    def _runtime_id_sane(cls, v: str) -> str:
        return _id_sane(v)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> RuntimeStatus:
        if isinstance(v, RuntimeStatus):
            return v
        return RuntimeStatus.parse(str(v))

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")
