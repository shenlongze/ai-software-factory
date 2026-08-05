"""project — Phase 5A: 项目配置示例层 (只读加载器, ADR-0013)。"""

from .loader import (
    ProjectLoadError,
    default_examples_dir,
    discover_projects,
    load_project,
)
from .models import (
    AgentMapping,
    ProjectConfig,
    ProjectDef,
    SkillDef,
    WorkflowMapping,
    WorkflowStepMapping,
)

__all__ = [
    "ProjectLoadError",
    "default_examples_dir",
    "discover_projects",
    "load_project",
    "AgentMapping",
    "ProjectConfig",
    "ProjectDef",
    "SkillDef",
    "WorkflowMapping",
    "WorkflowStepMapping",
]
