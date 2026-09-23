"""validation/models.py — 验证领域模型 (Pydantic v2)。

设计依据:
- phase3a-status.md: Validation Engine (models.py / engine.py / rules.py / reports.py)
- 三层验证: L1 Factory / L2 Workflow / L3 Artifact Hook
- ValidationResult: id/task_id/level/rule/status/message/created_at; status 枚举 PASS/FAIL/SKIP/ERROR

时间戳统一 UTC 带时区 (与 tasks/events 模型一致), JSON 序列化走 model_dump(mode="json")。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ValidationStatus(str, Enum):
    """单条验证规则的判定结果 (event-model §2.2 result 枚举的验证子集)。"""

    PASS = "PASS"    # 通过
    FAIL = "FAIL"    # 失败 (验证不通过)
    SKIP = "SKIP"    # 跳过 (条件不满足 / Hook 占位)
    ERROR = "ERROR"  # 规则内部错误 (异常)


class ValidationResult(BaseModel):
    """一条验证规则的执行结果。"""

    id: str                            # 规则唯一 id, 如 "L1.task_exists"
    task_id: str                       # 被验证任务
    level: str                         # 层级别: "L1" / "L2" / "L3"
    rule: str                          # 规则名, 如 "task_exists"
    status: ValidationStatus           # 判定结果
    message: str = ""                  # 人类可读详情 (证据/原因)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> ValidationStatus:
        return ValidationStatus(v) if isinstance(v, str) else v

    def to_dict(self) -> dict:
        """JSON 友好序列化 (CLI --json 输出共用)。"""
        return self.model_dump(mode="json")
