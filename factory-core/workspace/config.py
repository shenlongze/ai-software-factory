"""workspace/config.py — workspace.yaml 配置模型与读写 (Phase 6A, ADR-0016)。

workspace.yaml 是 Workspace 的持久化形式 (简单可靠, YAML 与项目配置同族,
PyYAML 已是运行依赖 ADR-0013 决策 2)。格式:

    name: my-workspace
    version: 1.0.0
    projects:
      - markpad
      - scorepocket
      - timeon

约定 (同 project.loader / JSON store 铁律): 解析/校验失败抛
WorkspaceConfigError (CLI 转退出码 1), 绝不静默返回空; 缺省字段取默认值。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

# workspace.yaml 文件名 (位于工厂根目录, 与 factory.db 同级)
WORKSPACE_FILENAME = "workspace.yaml"


class WorkspaceError(Exception):
    """Workspace 域基础异常。"""


class WorkspaceNotFoundError(WorkspaceError):
    """workspace.yaml 不存在 (未初始化)。"""


class WorkspaceConfigError(WorkspaceError):
    """workspace.yaml 或项目配置损坏: YAML 语法 / 模型校验 / 引用项目缺失。"""


class WorkspaceConfig(BaseModel):
    """workspace.yaml 配置: name + version + projects 引用列表。"""

    name: str
    version: str = "1.0.0"
    projects: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name_sane(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("workspace name must not be empty")
        return v

    @field_validator("projects")
    @classmethod
    def _projects_clean(cls, v: list[str]) -> list[str]:
        """过滤空白项 + 保序去重 (id 引用列表语义)。"""
        return list(dict.fromkeys(s.strip() for s in v if s and s.strip()))

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def load_config(path: str | Path) -> WorkspaceConfig:
    """读取并校验 workspace.yaml; 缺失 → WorkspaceNotFoundError, 损坏 → WorkspaceConfigError。"""
    p = Path(path)
    if not p.is_file():
        raise WorkspaceNotFoundError(f"workspace not found: {p} (run 'factory workspace init' first)")
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise WorkspaceConfigError(f"invalid workspace.yaml in {p}: {exc}") from exc
    if not isinstance(data, dict):
        raise WorkspaceConfigError(f"invalid workspace.yaml in {p}: expected a mapping")
    try:
        return WorkspaceConfig.model_validate(data)
    except ValidationError as exc:
        raise WorkspaceConfigError(f"invalid workspace.yaml in {p}: {exc}") from exc


def dump_config(config: WorkspaceConfig) -> str:
    """WorkspaceConfig → YAML 文本 (稳定排序, 便于人工审计与 git 差异)。"""
    lines = [f"name: {config.name}", f"version: {config.version}"]
    if config.projects:
        lines.append("projects:")
        for pid in config.projects:
            lines.append(f"  - {pid}")
    else:
        lines.append("projects: []")
    return "\n".join(lines) + "\n"
