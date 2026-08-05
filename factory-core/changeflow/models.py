"""changeflow/models.py — Change Driven Workflow Layer 领域模型 (Pydantic v2, Phase 6E, ADR-0020)。

设计依据:
- phase6e-status.md: ChangeTrigger (id/event_type/project_id/task_type/
  required_validation/target_workflow) + RuleResult + ChangeEvaluation
  (task_id/rules/results/triggered_workflow)
- 风格同 change/models.py / workflows/models.py: Pydantic v2 + to_dict()
  (model_dump(mode="json")) + 时间戳统一 UTC 带时区 + id 即引用键校验。

语义:
- ChangeTrigger: 声明式"变更驱动"规则 — 当某事件的变更满足条件 (项目/任务类型
  匹配 + 4 规则评估通过) 时, 自动启动 target_workflow (如 development 完成 →
  release)。
- RuleResult: 单条规则判定 (PASS/FAIL/SKIP/ERROR + message), 4 规则见 rules.py。
- ChangeEvaluation: 一次 evaluate 的完整结果快照 (task_id/trigger_id/status/
  rules/triggered_workflow/run_id/error) — 评估判定与触发结果一体,
  Dashboard Change Flow View 与 CLI --json 共用。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

# 规则判定状态 (与 validation / change 判定语义对齐)
RULE_STATUSES = frozenset({"PASS", "FAIL", "SKIP", "ERROR"})

# ChangeTrigger.event_type 受控词汇 (触发事件的来源域; 解析时宽容大写)
_TRIGGER_EVENT_TYPES = frozenset({
    "workflow.completed",     # 任务 development workflow 完成 → 变更评估
    "workflow.failed",        # 工作流失败 (不推荐触发, 语义上禁止级联)
    "change.validation.completed",  # L4 验证完成 → 评估
    "task.completed",         # 任务完成 → 评估
})

# ChangeTrigger.id 即引用键: 拒绝空值/路径分隔符 (同 tasks/workflows 模式)
def _id_sane(value: str) -> str:
    v = value.strip()
    if not v or v in {".", ".."} or "/" in v or "\\" in v:
        raise ValueError(f"invalid id: {value!r}")
    return v


def _coerce_status(value: Any, default: str = "SKIP") -> str:
    """宽容归一化规则状态 (大小写不敏感; 非法值回退 default)。"""
    v = str(value or default).strip().upper()
    return v if v in RULE_STATUSES else default


class ChangeTrigger(BaseModel):
    """一条"变更驱动"触发器: 条件匹配时启动目标工作流。

    - id: 触发器引用键 (如 TRIG-FEATURE-RELEASE)。
    - event_type: 触发事件域 (受控词汇: workflow.completed 等)。
    - project_id: 限定项目 (None = 任意项目)。
    - task_type: 限定任务类型 (None = 任意类型; 如 feature/bug/release)。
    - required_validation: 规则①要求的 L4 Change Validation 状态 (默认 PASS)。
    - target_workflow: 评估通过后启动的工作流 id (须已注册, 引擎层校验)。
    """

    id: str
    event_type: str = "workflow.completed"
    project_id: str | None = None
    task_type: str | None = None
    required_validation: str = "PASS"
    target_workflow: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("id")
    @classmethod
    def _id_sane(cls, v: str) -> str:
        return _id_sane(v)

    @field_validator("event_type", mode="before")
    @classmethod
    def _event_type_clean(cls, v: Any) -> str:
        s = str(v or "workflow.completed").strip().lower()
        return s if s in _TRIGGER_EVENT_TYPES else "workflow.completed"

    @field_validator("project_id", "task_type")
    @classmethod
    def _optional_str_clean(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    @field_validator("required_validation", mode="before")
    @classmethod
    def _required_validation_clean(cls, v: Any) -> str:
        return str(v or "PASS").strip().upper() or "PASS"

    @field_validator("target_workflow")
    @classmethod
    def _target_workflow_sane(cls, v: str) -> str:
        return _id_sane(v)

    def matches(self, *, project_id: str, task_type: str) -> bool:
        """任务是否命中该触发器 (项目/类型维度; 两者皆 None = 通配)。"""
        if self.project_id is not None and self.project_id != (project_id or "default"):
            return False
        if self.task_type is not None and (task_type or "").lower() != self.task_type.lower():
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class RuleResult(BaseModel):
    """单条变更规则的判定结果 (4 规则: validation L4 / commit linked / required
    files / runtime pref — 见 rules.py)。"""

    rule_id: str
    status: str = "SKIP"  # PASS/FAIL/SKIP/ERROR
    message: str = ""

    @field_validator("status", mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> str:
        return _coerce_status(v)

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ChangeEvaluation(BaseModel):
    """一次 change evaluate 的完整结果 (评估 + 触发一体快照)。

    - status: PASS (全部规则通过 → 触发) / FAIL (有规则失败, 不触发) /
      SKIP (无匹配触发器或全部规则 SKIP) / ERROR (评估内部错误 — 失败安全,
      不抛不级联)。
    - triggered_workflow/run_id: 触发成功后的目标工作流与运行实例 (未触发为 None)。
    - error: 触发失败原因 (如目标工作流未注册 / 任务已有 run / 执行失败)。
    """

    id: str = Field(default_factory=lambda: uuid4().hex)
    task_id: str
    trigger_id: str | None = None
    status: str = "SKIP"
    rules: list[RuleResult] = Field(default_factory=list)
    triggered_workflow: str | None = None
    run_id: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("status", mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> str:
        return _coerce_status(v)

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
