"""workspace — Phase 6A: Multi Project Workspace Layer (ADR-0016)。

Workspace = 上层组织单位: 一个 Factory 根管理多个项目 (markpad/scorepocket/timeon);
Task 经 project 字段 (语义即 project_id) 关联; workspace.yaml + 项目自动发现
(managed projects 目录 + examples 内置示例源)。
"""

from .config import (
    WORKSPACE_FILENAME,
    WorkspaceConfig,
    WorkspaceConfigError,
    WorkspaceError,
    WorkspaceNotFoundError,
)
from .loader import (
    definition_from_config,
    discover_project_ids,
    discover_projects,
    load_project_definition,
    managed_projects_dir,
    resolve_projects_root,
)
from .manager import (
    ProjectExistsError,
    ProjectNotFoundError,
    WorkspaceExistsError,
    WorkspaceManager,
)
from .models import ProjectDefinition, Workspace
from .store import WorkspaceStore

__all__ = [
    "WORKSPACE_FILENAME",
    "WorkspaceConfig",
    "WorkspaceConfigError",
    "WorkspaceError",
    "WorkspaceNotFoundError",
    "definition_from_config",
    "discover_project_ids",
    "discover_projects",
    "load_project_definition",
    "managed_projects_dir",
    "resolve_projects_root",
    "ProjectExistsError",
    "ProjectNotFoundError",
    "WorkspaceExistsError",
    "WorkspaceManager",
    "ProjectDefinition",
    "Workspace",
    "WorkspaceStore",
]
