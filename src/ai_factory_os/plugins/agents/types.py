"""agents/models.py — Agent / Skill 领域模型 (Pydantic v2)。

设计依据:
- phase3b-status.md: Agent 身份管理 + Skill 能力管理 (能力描述非执行)
- event-model.md §3.2: agent.* 事件 (本阶段为身份注册类: registered/updated/removed)
- tasks/models.py 同款模式: 时间戳 UTC 带时区, JSON 持久化由 model_dump(mode="json")
  输出 ISO 字符串; id 即文件名/键, 拒绝路径分隔符。

Agent.skills 为 Skill.id 引用列表 (不自动校验存在性 — 注册表解耦, KISS);
Task 集成边界 (phase3b-status.md): Task.owner 可引用 Agent.id, 不自动分配, 本模块不涉及。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AgentStatus(str, Enum):
    """Agent 生命周期状态 (phase3b-status.md: AVAILABLE/WORKING/OFFLINE)。"""

    AVAILABLE = "AVAILABLE"
    WORKING = "WORKING"
    OFFLINE = "OFFLINE"

    @classmethod
    def parse(cls, value: str) -> "AgentStatus":
        """宽容解析: 大小写不敏感; 枚举对象直接返回; 非法值抛 ValueError (CLI 转用法错误退出码 2)。"""
        if isinstance(value, AgentStatus):
            return value
        try:
            return cls(str(value).strip().upper())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(f"invalid agent status: {value!r} (expected one of: {valid})") from None


class Agent(BaseModel):
    """一个工厂 Agent。身份与能力描述; 状态流转经 registry.update。"""

    id: str
    name: str
    role: str
    description: str = ""
    skills: list[str] = Field(default_factory=list)  # Skill.id 引用列表 (去重保序)
    status: AgentStatus = AgentStatus.AVAILABLE
    current_task: str | None = None                  # 当前任务 id (Task.owner 引用, 不自动分配)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> AgentStatus:
        if isinstance(v, AgentStatus):
            return v
        return AgentStatus.parse(str(v))

    @field_validator("id")
    @classmethod
    def _id_sane(cls, v: str) -> str:
        """id 即存储键: 拒绝空值、路径分隔符与相对路径。"""
        v = v.strip()
        if not v or v in {".", ".."} or "/" in v or "\\" in v:
            raise ValueError(f"invalid agent id: {v!r}")
        return v

    @field_validator("skills")
    @classmethod
    def _skills_clean(cls, v: list[str]) -> list[str]:
        """过滤空白项 + 保序去重 (find_by_skill 语义干净)。"""
        return list(dict.fromkeys(s for s in v if s))

    def to_dict(self) -> dict:
        """JSON 友好序列化 (CLI --json 输出 / 文件持久化共用)。"""
        return self.model_dump(mode="json")


class Skill(BaseModel):
    """一个工厂技能。能力描述非执行 (Capability Catalog, 无运行时绑定)。"""

    id: str
    name: str
    category: str = "general"
    description: str = ""
    capabilities: list[str] = Field(default_factory=list)  # 能力点列表 (去重保序)
    version: str = "1.0.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("id")
    @classmethod
    def _id_sane(cls, v: str) -> str:
        v = v.strip()
        if not v or v in {".", ".."} or "/" in v or "\\" in v:
            raise ValueError(f"invalid skill id: {v!r}")
        return v

    @field_validator("capabilities")
    @classmethod
    def _capabilities_clean(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(s for s in v if s))

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")
