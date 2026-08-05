"""workspace/models.py — Workspace 领域模型 (Pydantic v2, Phase 6A, ADR-0016)。

设计依据:
- phase6a-status.md: Workspace (id/name/version/root_path/projects) +
  ProjectDefinition (id/name/description/language/repository/tech_stack/agents/
  skills/workflows/runtime_preferences/status)
- Workspace = 上层组织单位: 一个 Factory 根管理多个项目 (markpad/scorepocket/timeon);
  Task 经 project 字段 (语义即 project_id) 关联到 ProjectDefinition.id。
- 风格同 tasks/models.py / project/models.py: Pydantic v2 + to_dict()
  (model_dump(mode="json")) + id 即引用键校验。

ProjectDefinition 与 project.models.ProjectDef 的关系 (DRY, 不复制解析逻辑):
- ProjectDef = examples/*/project.yaml 声明 (只读底层, Phase 5A);
- ProjectDefinition = Workspace 视图层定义 = ProjectDef + agents/skills/workflows
  id 引用 + runtime_preferences/status 增强; 由 workspace/loader.py 从
  project.loader.load_project() 结果装配 (单一事实源仍在 project 模块)。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


def _id_sane(value: str) -> str:
    """id 即引用键: 拒绝空值、路径分隔符与相对路径 (同 tasks/project 模式)。"""
    v = value.strip()
    if not v or v in {".", ".."} or "/" in v or "\\" in v:
        raise ValueError(f"invalid id: {value!r}")
    return v


class ProjectDefinition(BaseModel):
    """Workspace 内一个项目的完整定义 (声明式, 只读视图层)。"""

    id: str                       # 项目 id (唯一, = project.yaml 的 name, Task.project 引用键)
    name: str = ""                # 显示名 (默认 = id)
    description: str = ""
    language: str = ""
    repository: str = ""
    tech_stack: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)     # agents.yaml 的 agent id 引用
    skills: list[str] = Field(default_factory=list)     # skills.yaml 的 skill id 引用
    workflows: list[str] = Field(default_factory=list)  # workflows.yaml 的 workflow id 引用
    runtime_preferences: dict[str, Any] = Field(default_factory=dict)  # 运行偏好 (project.yaml 可选)
    status: str = "active"        # 项目状态: active/archived/... (project.yaml 可选)

    @field_validator("id")
    @classmethod
    def _id_sane(cls, v: str) -> str:
        return _id_sane(v)

    @field_validator("name")
    @classmethod
    def _name_default(cls, v: str) -> str:
        return v.strip()

    @field_validator("status")
    @classmethod
    def _status_clean(cls, v: str) -> str:
        v = v.strip().lower()
        return v or "active"

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class Workspace(BaseModel):
    """一个 Factory Workspace: 配置文件 + 已解析项目定义 (只读投影)。

    root_path = 工厂根目录 (workspace.yaml 所在); projects = 已解析的
    ProjectDefinition 列表 (配置引用或自动发现, 见 workspace/loader.py)。
    """

    id: str = "workspace"         # 默认 = name (slug 语义: name 即 id)
    name: str = "workspace"
    version: str = "1.0.0"
    root_path: str = ""
    projects: list[ProjectDefinition] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _id_sane(cls, v: str) -> str:
        return _id_sane(v)

    @field_validator("name")
    @classmethod
    def _name_sane(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("workspace name must not be empty")
        return v

    def project_ids(self) -> list[str]:
        """已注册项目 id 列表 (排序, JSON 友好)。"""
        return [p.id for p in self.projects]

    def get(self, project_id: str) -> ProjectDefinition | None:
        """按 id 取项目定义; 不存在返回 None。"""
        for p in self.projects:
            if p.id == project_id:
                return p
        return None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
