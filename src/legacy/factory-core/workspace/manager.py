"""workspace/manager.py — WorkspaceManager: Workspace 生命周期 (Phase 6A, ADR-0016)。

设计依据:
- phase6a-status.md: WorkspaceManager — create_workspace/load_workspace/
  list_projects/get_project/add_project/remove_project
- 装配模式同 AgentRegistry (依赖注入 store/logger): 写操作 (create/add/remove)
  在 manager 内发事件 (workspace.created / project.registered / project.removed);
  读操作 (load/list/get) 不发事件 — viewed 事件由 CLI 命令层发出 (ADR-0002:
  所有 CLI 行为必须产生 Event, 同 dashboard/metrics 收集器边界, 避免双发)。
- 兼容: 无 workspace.yaml 时 list_projects/get_project 回落自动发现
  (examples 内置示例源), 与 Phase 5A project list/show 行为一致。
- Task 关联: Task.project 字段语义即 project_id (Phase 2), 本层不做校验 —
  引用不存在项目的 Task 仍可读可查 (不报错, 见 tests/workspace/test_compat.py)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from events.logger import EventLogger
from events.models import EventType

from .config import (
    WorkspaceConfig,
    WorkspaceConfigError,
    WorkspaceNotFoundError,
)
from .loader import (
    discover_project_ids,
    load_project_definition,
)
from .models import ProjectDefinition, Workspace
from .store import WorkspaceStore

SOURCE = "workspace"


class WorkspaceExistsError(Exception):
    """workspace.yaml 已存在 (create 未带 force)。"""


class ProjectExistsError(Exception):
    """项目已在 workspace.projects 中 (add_project 重复)。"""


class ProjectNotFoundError(Exception):
    """项目不在 workspace.projects 中 (remove_project 缺失)。"""


class WorkspaceManager:
    """一个工厂根的 Workspace 管理器 (读多写少, 单进程本地)。"""

    def __init__(
        self,
        root: str | Path,
        *,
        examples_dir: str | Path | None = None,
    ) -> None:
        self._root = Path(root)
        self._examples_dir = examples_dir
        self._store = WorkspaceStore(self._root)

    # ------------------------------------------------------------------ 属性

    @property
    def root(self) -> Path:
        return self._root

    @property
    def examples_dir(self) -> Path | None:
        return Path(self._examples_dir) if self._examples_dir is not None else None

    @property
    def workspace_path(self) -> Path:
        return self._store.path

    # ------------------------------------------------------------------ 写操作 (发事件)

    def create_workspace(
        self,
        name: str | None = None,
        *,
        projects: list[str] | None = None,
        logger: EventLogger | None = None,
        force: bool = False,
    ) -> tuple[Workspace, Any]:
        """创建 workspace.yaml (含项目引用) → (Workspace, Event|None)。

        - name 缺省 = 工厂根目录名; projects 缺省 = 自动发现 (managed ∪ examples)。
        - 已存在且未 force → WorkspaceExistsError; 引用项目解析失败 →
          WorkspaceConfigError (先解析后落盘, 不留下半写配置)。
        - 发 workspace.created (payload: name/version/projects)。
        """
        if self._store.exists() and not force:
            raise WorkspaceExistsError(
                f"workspace already exists: {self._store.path} (pass force=True to overwrite)"
            )
        resolved_name = (name or "").strip() or self._root.name or "workspace"
        project_ids = list(projects) if projects is not None else discover_project_ids(
            self._root, self._examples_dir
        )
        # 先解析全部引用 (损坏/缺失 → 明确报错, 不落盘)
        definitions = [self._resolve(pid) for pid in project_ids]
        config = WorkspaceConfig(name=resolved_name, projects=project_ids)
        self._store.save(config)
        ev = None
        if logger is not None:
            ev = logger.record(
                EventType.WORKSPACE_CREATED, source=SOURCE,
                stage="created", action="create workspace", result="OK",
                payload={
                    "name": resolved_name,
                    "version": config.version,
                    "projects": project_ids,
                    "workspace_file": str(self._store.path),
                },
            )
        workspace = self._build(resolved_name, config, definitions)
        return workspace, ev

    def add_project(
        self, project_id: str, *, logger: EventLogger | None = None,
    ) -> tuple[Workspace, Any]:
        """把项目加入 workspace.projects 引用列表 → (Workspace, Event|None)。

        前置: 项目可解析 (managed/examples 有 project.yaml), 否则 WorkspaceConfigError;
        已在列表中 → ProjectExistsError。发 project.registered。
        """
        config = self._load_config()
        if project_id in config.projects:
            raise ProjectExistsError(f"project already in workspace: {project_id}")
        definition = self._resolve(project_id)  # 解析失败 → WorkspaceConfigError
        config.projects.append(project_id)
        self._store.save(config)
        ev = None
        if logger is not None:
            ev = logger.record(
                EventType.PROJECT_REGISTERED, source=SOURCE, project_id=project_id,
                stage="registered", action="register project", result="OK",
                payload={
                    "project": project_id,
                    "language": definition.language,
                    "status": definition.status,
                    "agents": len(definition.agents),
                    "skills": len(definition.skills),
                    "workflows": len(definition.workflows),
                },
            )
        return self.load_workspace(), ev

    def remove_project(
        self, project_id: str, *, logger: EventLogger | None = None,
    ) -> tuple[Workspace, Any]:
        """把项目从 workspace.projects 移除 → (Workspace, Event|None)。

        不在列表中 → ProjectNotFoundError。发 project.removed (只移除引用,
        不删除项目配置文件 — 引用语义, KISS)。
        """
        config = self._load_config()
        if project_id not in config.projects:
            raise ProjectNotFoundError(f"project not in workspace: {project_id}")
        config.projects = [pid for pid in config.projects if pid != project_id]
        self._store.save(config)
        ev = None
        if logger is not None:
            ev = logger.record(
                EventType.PROJECT_REMOVED, source=SOURCE, project_id=project_id,
                stage="removed", action="remove project", result="OK",
                payload={"project": project_id},
            )
        return self.load_workspace(), ev

    # ------------------------------------------------------------------ 读操作 (不发事件)

    def load_workspace(self) -> Workspace:
        """读取 workspace.yaml → Workspace (含已解析项目定义)。

        缺失 → WorkspaceNotFoundError; 配置损坏/引用项目缺失 → WorkspaceConfigError。
        projects 列表为空时视为「未显式注册」→ 自动发现兜底 (项目自动发现语义)。
        """
        config = self._load_config()
        ids = list(config.projects) or discover_project_ids(self._root, self._examples_dir)
        definitions = [self._resolve(pid) for pid in ids]
        return self._build(config.name, config, definitions)

    def list_projects(self) -> list[ProjectDefinition]:
        """项目定义列表 (按 id 排序)。

        有 workspace → workspace.projects (注册列表); 无 workspace → 自动发现
        (managed ∪ examples), 兼容 Phase 5A 行为 (无 workspace 时扫 examples)。
        """
        if self._store.exists():
            return sorted(self.load_workspace().projects, key=lambda p: p.id)
        from .loader import discover_projects

        return discover_projects(self._root, self._examples_dir)

    def get_project(self, project_id: str) -> ProjectDefinition | None:
        """按 id 取项目定义; 不存在 → None。

        解析顺序: managed projects 目录 → examples 目录 (workspace 成员与否
        不影响解析 — Task.project 引用不存在的项目也兼容不报错)。
        """
        return load_project_definition(self._root, project_id, self._examples_dir)

    # ------------------------------------------------------------------ 内部

    def _load_config(self) -> WorkspaceConfig:
        if not self._store.exists():
            raise WorkspaceNotFoundError(
                f"workspace not found: {self._store.path} (run 'factory workspace init' first)"
            )
        return self._store.load()

    def _resolve(self, project_id: str) -> ProjectDefinition:
        definition = load_project_definition(self._root, project_id, self._examples_dir)
        if definition is None:
            raise WorkspaceConfigError(
                f"project referenced in workspace not found: {project_id!r} "
                f"(no project.yaml under {managed_dirs_hint(self._root, self._examples_dir, project_id)})"
            )
        return definition

    def _build(
        self, name: str, config: WorkspaceConfig, definitions: list[ProjectDefinition],
    ) -> Workspace:
        return Workspace(
            id=name,
            name=name,
            version=config.version,
            root_path=str(self._root),
            projects=sorted(definitions, key=lambda p: p.id),
        )


def managed_dirs_hint(root: Path, examples_dir: str | Path | None, project_id: str) -> str:
    """错误提示: 列出两个候选项目源目录 (定位缺失项目)。"""
    from .loader import managed_projects_dir

    parts = [str(managed_projects_dir(root) / project_id)]
    if examples_dir is not None:
        parts.append(str(Path(examples_dir) / project_id))
    return " or ".join(parts)
