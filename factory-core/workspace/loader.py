"""workspace/loader.py — 项目自动发现与 ProjectDefinition 解析 (Phase 6A, ADR-0016)。

设计依据:
- phase6a-status.md: loader.py — 自动发现 workspace/projects/*/project.yaml →
  加载 ProjectDefinition; 配置错误明确报错
- 复用 factory-core/project/ 加载能力 (DRY, 不复制解析逻辑): 本模块只做
  「项目源定位 + 结果装配」, project.yaml/agents.yaml/skills.yaml/workflows.yaml
  的解析/校验全部委托 project.loader.load_project() (单一事实源 ADR-0013)。

项目源解析顺序 (managed 优先, examples 兜底):
1. <root>/workspace/projects/<id>/   — 用户管理项目 (workspace 自有)
2. <examples_dir>/<id>/             — 内置示例源 (默认仓库根/examples,
   FACTORY_EXAMPLES_DIR 覆盖, 同 project.loader.default_examples_dir)

配置错误: 引用的项目缺失 / project.yaml 损坏 → WorkspaceConfigError (CLI 转
退出码 1, 不静默跳过)。自动发现只按 project.yaml 存在性扫描 (不解析), 损坏
配置在加载定义时才报错 (延迟到使用点, 便于定位具体文件)。
"""

from __future__ import annotations

from pathlib import Path

from project.loader import (
    ProjectLoadError,
    default_examples_dir,
    load_project,
)
from project.models import ProjectConfig

from .config import WorkspaceConfigError
from .models import ProjectDefinition


def managed_projects_dir(root: str | Path) -> Path:
    """用户管理项目目录 = <root>/workspace/projects。"""
    return Path(root) / "workspace" / "projects"


def _examples(examples_dir: str | Path | None) -> Path:
    return Path(examples_dir) if examples_dir is not None else default_examples_dir()


def definition_from_config(cfg: ProjectConfig) -> ProjectDefinition:
    """ProjectConfig → ProjectDefinition (ProjectDef + 映射 id 引用 + 增强字段)。

    agents/skills/workflows 取 id 引用列表 (完整映射仍在 project 配置);
    runtime_preferences/status 透传 project.yaml 的增强字段 (Phase 6A)。
    """
    p = cfg.project
    return ProjectDefinition(
        id=p.name,
        name=p.name,
        description=p.description,
        language=p.language,
        repository=p.repository,
        tech_stack=list(p.tech_stack),
        agents=[a.id for a in cfg.agents],
        skills=[s.id for s in cfg.skills],
        workflows=[w.id for w in cfg.workflows],
        runtime_preferences=dict(p.runtime_preferences),
        status=p.status,
    )


def resolve_projects_root(
    root: str | Path, project_id: str, examples_dir: str | Path | None = None,
) -> Path | None:
    """定位包含 <project_id>/project.yaml 的项目源目录 (managed 优先)。

    返回项目源根目录 (managed projects 目录或 examples 目录), 调用方以
    load_project(<返回目录>, project_id) 加载; 两处均无 → None。
    """
    managed = managed_projects_dir(root)
    if (managed / project_id / "project.yaml").is_file():
        return managed
    ex = _examples(examples_dir)
    if (ex / project_id / "project.yaml").is_file():
        return ex
    return None


def load_project_definition(
    root: str | Path, project_id: str, examples_dir: str | Path | None = None,
) -> ProjectDefinition | None:
    """解析单个项目 → ProjectDefinition; 源不存在 → None, 配置损坏 → WorkspaceConfigError。"""
    src = resolve_projects_root(root, project_id, examples_dir)
    if src is None:
        return None
    try:
        cfg = load_project(src, project_id)
    except ProjectLoadError as exc:
        raise WorkspaceConfigError(str(exc)) from exc
    if cfg is None:  # resolve 已确认 project.yaml 存在, 理论上不可达
        return None
    return definition_from_config(cfg)


def discover_project_ids(
    root: str | Path, examples_dir: str | Path | None = None,
) -> list[str]:
    """自动发现项目 id: managed projects 目录 ∪ examples 目录 (按存在性扫描)。

    只检查 <dir>/project.yaml 是否存在, 不解析内容 (损坏配置在加载时报错);
    排序输出, managed 与 examples 重复时去重。
    """
    ids: set[str] = set()
    managed = managed_projects_dir(root)
    if managed.is_dir():
        for d in sorted(managed.iterdir()):
            if d.is_dir() and (d / "project.yaml").is_file():
                ids.add(d.name)
    ex = _examples(examples_dir)
    if ex.is_dir():
        for d in sorted(ex.iterdir()):
            if d.is_dir() and (d / "project.yaml").is_file():
                ids.add(d.name)
    return sorted(ids)


def discover_projects(
    root: str | Path, examples_dir: str | Path | None = None,
) -> list[ProjectDefinition]:
    """自动发现并加载全部项目 → ProjectDefinition 列表 (按 id 排序)。

    任一项目配置损坏 → WorkspaceConfigError (不静默跳过); 无任何项目 → []。
    """
    definitions: list[ProjectDefinition] = []
    for pid in discover_project_ids(root, examples_dir):
        definition = load_project_definition(root, pid, examples_dir)
        if definition is not None:
            definitions.append(definition)
    definitions.sort(key=lambda d: d.id)
    return definitions
