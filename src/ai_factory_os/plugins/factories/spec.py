"""plugins.factories.spec — 工厂定义的数据形状（只读声明层）。

沿革：factory-core/project/models.py → 此处（刀21 重写替换）。

只读声明层：解析 examples/<name>/ 下的 YAML 配置（project/agents/skills/workflows），
不写任何工厂状态。Pydantic v2 + to_dict() + id 即引用键校验。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


def _id_sane(value: str) -> str:
    """id 即引用键：拒绝空值、路径分隔符与相对路径。"""
    v = value.strip()
    if not v or v in {".", ".."} or "/" in v or "\\" in v:
        raise ValueError(f"invalid id: {value!r}")
    return v


class ProjectDef(BaseModel):
    """project.yaml — 项目定义（名称/语言/仓库/技术栈 + 增强字段）。"""

    name: str
    language: str
    repository: str = ""
    description: str = ""
    tech_stack: list[str] = Field(default_factory=list)
    runtime_preferences: dict[str, Any] = Field(default_factory=dict)
    status: str = "active"

    @field_validator("name")
    @classmethod
    def _name_sane(cls, v: str) -> str:
        return _id_sane(v)

    @field_validator("status")
    @classmethod
    def _status_clean(cls, v: str) -> str:
        v = v.strip().lower()
        return v or "active"

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class AgentMapping(BaseModel):
    """agents.yaml 单个 agent 映射：id + role + skills（Skill.id 引用）。"""

    id: str
    name: str = ""
    role: str
    skills: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("id")
    @classmethod
    def _id_sane(cls, v: str) -> str:
        return _id_sane(v)

    @field_validator("skills")
    @classmethod
    def _skills_clean(cls, v: list[str]) -> list[str]:
        """过滤空白项 + 保序去重。"""
        return list(dict.fromkeys(s for s in v if s))

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class SkillDef(BaseModel):
    """skills.yaml 单个技能定义（能力目录）。"""

    id: str
    name: str = ""
    category: str = "general"
    version: str = "1.0.0"
    capabilities: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("id")
    @classmethod
    def _id_sane(cls, v: str) -> str:
        return _id_sane(v)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class WorkflowStepMapping(BaseModel):
    """workflows.yaml 步骤映射（含 role/skill 元数据）。"""

    id: str
    name: str = ""
    required_skill: str | None = None
    required_role: str | None = None

    @field_validator("id")
    @classmethod
    def _id_sane(cls, v: str) -> str:
        return _id_sane(v)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class WorkflowMapping(BaseModel):
    """workflows.yaml 单个工作流映射。"""

    id: str
    name: str = ""
    description: str = ""
    steps: list[WorkflowStepMapping] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _id_sane(cls, v: str) -> str:
        return _id_sane(v)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ProjectConfig(BaseModel):
    """一个工厂定义的完整聚合（project.yaml + agents + skills + workflows）。"""

    project: ProjectDef
    agents: list[AgentMapping] = Field(default_factory=list)
    skills: list[SkillDef] = Field(default_factory=list)
    workflows: list[WorkflowMapping] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
