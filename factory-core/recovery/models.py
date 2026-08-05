"""recovery/models.py — Checkpoint / RecoveryResult 领域模型 (Pydantic v2)。

设计依据:
- phase4c3-status.md: Checkpoint (id/task_id/workflow_id/event_seq/workflow_state/
  current_step/agents/executions/created_at) + RecoveryResult (task_id/last_event/
  state/resume_ok/actions)。
- 参照 agents/workflows/runtime models 风格: 枚举宽容 parse + id 即存储键校验 +
  to_dict (JSON 友好)。时间戳统一 UTC 带时区, JSON 持久化由 model_dump(mode="json")
  输出 ISO 字符串。

语义:
- Checkpoint 是"持久化状态 + 事件回放锚点"的快照: event_seq 记录该任务最近一条
  事件的 seq, 恢复时以此锚点核对事件链是否完整 (Event Audit 原则)。
- workflow_state 内嵌 WorkflowRun.to_dict() (含 step_states/status/current_step),
  与定义解耦 (run 快照自带全部运行信息); agents/executions 为 JSON 友好的
  {id: 状态字符串} 摘要 (引用不复制, 同 assignment 原则)。
- RecoveryResult 是 recover() 的分析产物: 从事件回放重建的状态 (state)、最后
  回放锚点 (last_event)、是否可继续 (resume_ok) 与恢复动作清单 (actions)。
  四场景语义: RUNNING 继续 (resume_ok=True) / Execution 重试 (resume_ok=True) /
  Agent 释放 (resume_ok=True) / 已完成拒绝 (resume_ok=False)。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator


def _id_sane(value: str) -> str:
    """id 即存储键/文件名: 拒绝空值、路径分隔符与相对路径 (同 agents/tasks 模式)。"""
    v = value.strip()
    if not v or v in {".", ".."} or "/" in v or "\\" in v:
        raise ValueError(f"invalid id: {value!r}")
    return v


class Checkpoint(BaseModel):
    """一次停靠点快照: 任务维度的持久化状态 + 事件回放锚点 (续跑生命线)。

    - id: CKPT-<task_id> (1:1 于任务; CheckpointStore 按 task_id 落单文件)。
    - event_seq: 最近一条与任务相关事件的 seq (0 = 尚无事件); 恢复时以事件链
      长度与该锚点核对, 保证回放覆盖到停靠点之后的所有新事件。
    - workflow_state: WorkflowRun.to_dict() 快照 (None = 任务尚未启动工作流)。
    - agents/executions: {id: 状态} 摘要, 供恢复比对 (引用不复制, KISS)。
    """

    id: str
    task_id: str
    workflow_id: str | None = None
    event_seq: int = 0
    workflow_state: dict[str, Any] | None = None
    current_step: str | None = None
    agents: dict[str, str] = Field(default_factory=dict)      # {agent_id: AgentStatus}
    executions: dict[str, str] = Field(default_factory=dict)  # {execution_id: ExecutionStatus}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("id", "task_id")
    @classmethod
    def _ids_sane(cls, v: str) -> str:
        return _id_sane(v)

    @field_validator("event_seq")
    @classmethod
    def _seq_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"event_seq must be >= 0, got {v}")
        return v

    def to_dict(self) -> dict:
        """JSON 友好序列化 (CLI --json 输出 / 文件持久化共用)。"""
        return self.model_dump(mode="json")


class RecoveryResult(BaseModel):
    """一次 recover() 的分析结果: 重建状态 + 恢复判定 + 动作清单 (审计/CLI 展示)。

    - state: 重建后的工作流状态 (RUNNING/COMPLETED/FAILED/none)。
    - resume_ok: 是否可继续 — 场景1-3 True (RUNNING 继续/Execution 重试/Agent 释放);
      场景4 False (已完成/已失败/无运行实例 → 拒绝)。
    - actions: 恢复动作清单 (人类可读, 也承载审计; 已执行的纠正动作与实际副作用一一对应)。
    - workflow/assignments/executions/agents: 恢复后 (纠正后) 的持久化状态快照,
      CLI --json 消费与测试断言用 (派生展示数据, 与 state/resume_ok 同源)。
    """

    task_id: str
    last_event: int = 0
    state: str = "none"
    resume_ok: bool = False
    actions: list[str] = Field(default_factory=list)
    workflow: dict[str, Any] | None = None
    assignments: list[dict[str, Any]] = Field(default_factory=list)
    executions: list[dict[str, Any]] = Field(default_factory=list)
    agents: dict[str, str] = Field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")
