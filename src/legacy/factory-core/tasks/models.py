"""tasks/models.py — Task 领域模型 (Pydantic v2)。

设计依据:
- phase2-status.md: Task Model (Pydantic) + 五状态 BACKLOG/ARCHITECTURE/DEVELOPMENT/TESTING/DONE
- cli-design.md §2.3: 任务定义字段 (id/title/project/type/owner/workflow)

时间戳统一 UTC 带时区, JSON 持久化由 model_dump(mode="json") 输出 ISO 字符串。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TaskStatus(str, Enum):
    """任务生命周期五状态 (phase2-status.md)。"""

    BACKLOG = "BACKLOG"
    ARCHITECTURE = "ARCHITECTURE"
    DEVELOPMENT = "DEVELOPMENT"
    TESTING = "TESTING"
    DONE = "DONE"

    @classmethod
    def parse(cls, value: str) -> "TaskStatus":
        """宽容解析: 大小写不敏感; 枚举对象直接返回; 非法值抛 ValueError (CLI 转用法错误退出码 2)。"""
        if isinstance(value, TaskStatus):
            return value
        try:
            return cls(str(value).strip().upper())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(f"invalid task status: {value!r} (expected one of: {valid})") from None


class Task(BaseModel):
    """一个工厂任务。定义性数据; 状态机流转经 TaskStore.update_status。"""

    id: str
    title: str
    project: str = "default"
    type: str = "feature"
    status: TaskStatus = TaskStatus.BACKLOG
    owner: str | None = None
    workflow: str | None = "feature-delivery"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> TaskStatus:
        if isinstance(v, TaskStatus):
            return v
        return TaskStatus.parse(str(v))

    @field_validator("id")
    @classmethod
    def _id_sane(cls, v: str) -> str:
        """id 即文件名: 拒绝空值、路径分隔符与相对路径。"""
        v = v.strip()
        if not v or v in {".", ".."} or "/" in v or "\\" in v:
            raise ValueError(f"invalid task id: {v!r}")
        return v

    def to_dict(self) -> dict:
        """JSON 友好序列化 (CLI --json 输出 / 文件持久化共用)。"""
        return self.model_dump(mode="json")
