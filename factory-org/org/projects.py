"""factory-org/org/projects.py — 统一生命周期模型 (Sprint 7 S7-001)。

模型层级 (sprint7-architecture.md §3):
```
User → Project → Sprint → Workflow → Stage → Task → Artifact
```
- Project: 用户想法的容器 (lifecycle: idea→active→maintained→archived)
- Sprint: 项目内任务批次 (tasks = Core Task id 列表 — Task 冻结, org 侧引用)
- Stage: 组织级 Workflow 编排壳的阶段 (role_id = exec 注册表统一角色;
  S7-005 接真实执行, 本层只建壳/流转, 不调 LLM)
- Artifact: 阶段产物 (type: prd|design|code|test|release; 阶段间流转输入)
- ProjectTaskLink: 项目 ↔ Core Task 扩展侧映射表 (Core Task 不可加字段,
  用扩展侧映射 — 任务允许路径)

设计约束:
- Core (factory-core) 冻结: 本模块零 Core 业务 import (仅事件层, 同 org
  其余模块); Task 关联经 ProjectTaskLink/Sprint.tasks 引用, 不碰 Task 模型。
- 事件: org.project.* / org.sprint.* / org.stage.* / org.artifact.*
  (org/events.py record 函数; logger=None 全静默, 同既有模式)。
- 存储: <root>/org/ 数据空间内新文件 (projects/sprints/stages/artifacts/
  project_task_links.json) — 与既有六库并存, 互不影响, 既有数据零破坏。
- 引用完整: 跨实体引用 (project/sprint/stage) 创建时校验存在性; 任务关联
  经 ProjectTaskLink 先建后加 (Sprint 只接受已关联项目的任务)。

角色引用: Stage.role_id 指向 exec/roles.py 注册表 (S7-001 单一事实源);
exec 未安装时仅跳过校验 (Removal Isolation), 不假装校验。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator

from . import events as org_events
from .lifecycle import DuplicateError, NotFoundError
from .models import _OrgModel, _norm_list, new_id, utcnow
from .store import _SectionStore

# ------------------------------------------------------------------ 枚举


class ProjectState(str, Enum):
    """项目生命周期状态 (sprint7-architecture: idea→active→maintained→archived)。"""

    IDEA = "idea"
    ACTIVE = "active"
    MAINTAINED = "maintained"
    ARCHIVED = "archived"

    @classmethod
    def parse(cls, value: Any) -> "ProjectState":
        """宽容解析: 大小写不敏感; 枚举对象直接返回; 非法值抛 ValueError。"""
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(
                f"invalid project lifecycle: {value!r} (expected one of: {valid})"
            ) from None


class ArtifactType(str, Enum):
    """阶段产物类型 (sprint7-architecture §1: 阶段产物 = 下一阶段输入)。"""

    PRD = "prd"
    DESIGN = "design"
    CODE = "code"
    TEST = "test"
    RELEASE = "release"

    @classmethod
    def parse(cls, value: Any) -> "ArtifactType":
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(
                f"invalid artifact type: {value!r} (expected one of: {valid})"
            ) from None


class StageStatus(str, Enum):
    """Stage 状态 (组织级编排壳; S7-005 接执行后流转)。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    @classmethod
    def parse(cls, value: Any) -> "StageStatus":
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(
                f"invalid stage status: {value!r} (expected one of: {valid})"
            ) from None


#: 项目生命周期合法流转 (单向无环; archived 为终态)
PROJECT_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "idea": ("active", "archived"),
    "active": ("maintained", "archived"),
    "maintained": ("archived",),
    "archived": (),
}


# ------------------------------------------------------------------ 模型


class Project(_OrgModel):
    """项目 (用户想法的生命周期容器; lifecycle 状态机单向流转)。"""

    id: str
    name: str
    user_id: str = ""                    # User (想法来源)
    goal: str = ""
    lifecycle: ProjectState = ProjectState.IDEA
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("lifecycle", mode="before")
    @classmethod
    def _coerce_lifecycle(cls, v: Any) -> ProjectState:
        return ProjectState.parse(v)

    @property
    def is_archived(self) -> bool:
        """终态判断 (archived 后不可再流转)。"""
        return self.lifecycle == ProjectState.ARCHIVED


class Sprint(_OrgModel):
    """Sprint (项目内任务批次; tasks = Core Task id 列表, org 侧引用)。"""

    id: str
    project_id: str
    name: str
    tasks: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("tasks", mode="before")
    @classmethod
    def _tasks_none(cls, v: Any) -> Any:
        return _norm_list(v)


class Stage(_OrgModel):
    """Stage (组织级 Workflow 编排壳阶段; role_id = exec 注册表统一角色)。

    workflow_id: 组织级 workflow run id (S7-005 编排壳创建; 本层不校验
    Core workflow 存在性 — 编排壳与任务级 WorkflowEngine 解耦)。
    artifact_ref: 产出 Artifact id (阶段产物引用, 流转输入)。
    """

    id: str
    workflow_id: str
    role_id: str                         # exec 注册表 role_id (单一事实源)
    order: int = 1
    status: StageStatus = StageStatus.PENDING
    artifact_ref: str = ""               # 产出 Artifact id
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> StageStatus:
        return StageStatus.parse(v)


class Artifact(_OrgModel):
    """阶段产物 (type: prd|design|code|test|release; ref = 产物引用)。"""

    id: str
    stage_id: str
    type: ArtifactType
    ref: str = ""                        # 产物引用 (file:// / ref:// / 描述)
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, v: Any) -> ArtifactType:
        return ArtifactType.parse(v)


class ProjectTaskLink(_OrgModel):
    """项目 ↔ Core Task 扩展侧映射 (Core Task 冻结 — 不加字段, org 侧存储)。"""

    id: str
    project_id: str
    task_id: str
    created_at: datetime = Field(default_factory=utcnow)


# ------------------------------------------------------------------ 存储


class ProjectSection(_SectionStore[Project]):
    """Project 持久化 (projects.json)。"""

    _filename = "projects.json"
    _section = "projects"
    _model = Project


class SprintSection(_SectionStore[Sprint]):
    """Sprint 持久化 (sprints.json)。"""

    _filename = "sprints.json"
    _section = "sprints"
    _model = Sprint


class StageSection(_SectionStore[Stage]):
    """Stage 持久化 (stages.json)。"""

    _filename = "stages.json"
    _section = "stages"
    _model = Stage


class ArtifactSection(_SectionStore[Artifact]):
    """Artifact 持久化 (artifacts.json)。"""

    _filename = "artifacts.json"
    _section = "artifacts"
    _model = Artifact


class ProjectTaskLinkSection(_SectionStore[ProjectTaskLink]):
    """ProjectTaskLink 持久化 (project_task_links.json)。"""

    _filename = "project_task_links.json"
    _section = "project_task_links"
    _model = ProjectTaskLink


class ProjectStore:
    """统一生命周期数据空间门面 (五实体: project/sprint/stage/artifact/link)。

    与 OrgStore 同目录 (<root>/org/) 但独立文件 — 既有六库 (companies/
    departments/roles/employees/authorities/knowledge.json) 零接触,
    向后兼容 (既有 org 数据不受破坏)。
    """

    def __init__(self, org_dir: str | Path):
        self._dir = Path(org_dir)
        self._projects = ProjectSection(self._dir)
        self._sprints = SprintSection(self._dir)
        self._stages = StageSection(self._dir)
        self._artifacts = ArtifactSection(self._dir)
        self._links = ProjectTaskLinkSection(self._dir)

    @property
    def dir(self) -> Path:
        return self._dir

    # ------------------------------------------------------------- Project
    def save_project(self, project: Project) -> None:
        self._projects.save(project)

    def get_project(self, project_id: str) -> Project | None:
        return self._projects.get(project_id)

    def list_projects(self) -> list[Project]:
        return self._projects.list_all()

    def count_projects(self) -> int:
        return self._projects.count()

    # ------------------------------------------------------------- Sprint
    def save_sprint(self, sprint: Sprint) -> None:
        self._sprints.save(sprint)

    def get_sprint(self, sprint_id: str) -> Sprint | None:
        return self._sprints.get(sprint_id)

    def list_sprints(self) -> list[Sprint]:
        return self._sprints.list_all()

    def list_sprints_by_project(self, project_id: str) -> list[Sprint]:
        return [s for s in self.list_sprints() if s.project_id == project_id]

    # -------------------------------------------------------------- Stage
    def save_stage(self, stage: Stage) -> None:
        self._stages.save(stage)

    def get_stage(self, stage_id: str) -> Stage | None:
        return self._stages.get(stage_id)

    def list_stages(self) -> list[Stage]:
        return self._stages.list_all()

    def list_stages_by_workflow(self, workflow_id: str) -> list[Stage]:
        return [s for s in self.list_stages() if s.workflow_id == workflow_id]

    # ----------------------------------------------------------- Artifact
    def save_artifact(self, artifact: Artifact) -> None:
        self._artifacts.save(artifact)

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        return self._artifacts.get(artifact_id)

    def list_artifacts(self) -> list[Artifact]:
        return self._artifacts.list_all()

    def list_artifacts_by_stage(self, stage_id: str) -> list[Artifact]:
        return [a for a in self.list_artifacts() if a.stage_id == stage_id]

    # -------------------------------------------------------- ProjectTaskLink
    def save_task_link(self, link: ProjectTaskLink) -> None:
        self._links.save(link)

    def get_task_link(self, link_id: str) -> ProjectTaskLink | None:
        return self._links.get(link_id)

    def list_task_links(self) -> list[ProjectTaskLink]:
        return self._links.list_all()

    def list_task_links_by_project(self, project_id: str) -> list[ProjectTaskLink]:
        return [l for l in self.list_task_links() if l.project_id == project_id]

    def list_task_links_by_task(self, task_id: str) -> list[ProjectTaskLink]:
        return [l for l in self.list_task_links() if l.task_id == task_id]

    # -------------------------------------------------------------- 数据空间
    def files(self) -> list[Path]:
        """五个数据文件 (存在者; 测试/审计用)。"""
        return sorted(
            p
            for p in (
                self._dir / "projects.json",
                self._dir / "sprints.json",
                self._dir / "stages.json",
                self._dir / "artifacts.json",
                self._dir / "project_task_links.json",
            )
            if p.exists()
        )


# ------------------------------------------------------------------ 编排


def _validate_exec_role(role_id: str) -> None:
    """Stage.role_id 校验 (exec 注册表单一事实源; 未安装 → 跳过, 不假装)。"""
    try:
        import exec.roles  # type: ignore[import-not-found]

        exec.roles.require_role(role_id)
    except ImportError:
        return
    except exec.roles.RoleError as exc:  # type: ignore[attr-defined]
        raise ValueError(str(exc)) from exc


class ProjectLifecycle:
    """统一生命周期编排: Project/Sprint/Stage/Artifact/Task 关联 (事件驱动)。

    只编排组织状态与审计事件, 零 LLM/零执行副作用 (真实执行 S7-005 编排壳
    接入, 本层 KISS 建壳 + 流转)。只依赖 ProjectStore + EventLogger。
    """

    def __init__(self, store: ProjectStore, *, logger: Any = None):
        self._store = store
        self._logger = logger

    @property
    def store(self) -> ProjectStore:
        return self._store

    # ------------------------------------------------------------------ Project

    def create_project(
        self,
        name: str,
        *,
        user_id: str = "",
        goal: str = "",
        project_id: str | None = None,
    ) -> Project:
        """创建项目 (org.project.created; lifecycle 默认 idea)。"""
        project_id = project_id or new_id("P")
        if self._store.get_project(project_id) is not None:
            raise DuplicateError(f"project already exists: {project_id}")
        project = Project(id=project_id, name=name, user_id=user_id, goal=goal)
        self._store.save_project(project)
        org_events.record_project_created(self._logger, project=project)
        return project

    def get_project(self, project_id: str) -> Project:
        project = self._store.get_project(project_id)
        if project is None:
            raise NotFoundError(f"project not found: {project_id}")
        return project

    def list_projects(self) -> list[Project]:
        return self._store.list_projects()

    def transition_lifecycle(
        self, project_id: str, to_lifecycle: ProjectState | str
    ) -> Project:
        """生命周期流转 (org.project.lifecycle_changed; 非法流转 → ValueError)。

        流转表 PROJECT_TRANSITIONS (单向无环; archived 终态)。目标值经
        ProjectState.parse 宽容解析 (大小写不敏感)。
        """
        project = self.get_project(project_id)
        target = ProjectState.parse(to_lifecycle)
        if target == project.lifecycle:
            return project  # 幂等: 同状态不重复发事件
        allowed = PROJECT_TRANSITIONS.get(project.lifecycle.value, ())
        if target.value not in allowed:
            raise ValueError(
                f"invalid project lifecycle transition: "
                f"{project.lifecycle.value} → {target.value} "
                f"(allowed from {project.lifecycle.value}: "
                f"{', '.join(allowed) or 'none'})"
            )
        from_value = project.lifecycle.value
        updated = project.model_copy(
            update={"lifecycle": target, "updated_at": utcnow()}
        )
        self._store.save_project(updated)
        org_events.record_project_lifecycle_changed(
            self._logger, project=updated, from_lifecycle=from_value,
            to_lifecycle=target.value,
        )
        return updated

    def link_task(
        self, project_id: str, task_id: str, *, link_id: str | None = None
    ) -> ProjectTaskLink:
        """项目 ↔ Core Task 关联 (org.project.task_linked; 扩展侧映射表)。

        task_id 为 Core Task id 引用 (Task 冻结 — 不校验 Core store,
        由调用方保证任务存在; 扩展侧映射保持单向解耦)。
        """
        self.get_project(project_id)  # 项目必须存在 (引用完整)
        for existing in self._store.list_task_links_by_project(project_id):
            if existing.task_id == task_id:
                raise DuplicateError(
                    f"task already linked to project: {task_id} in {project_id}"
                )
        link_id = link_id or new_id("PTL")
        if self._store.get_task_link(link_id) is not None:
            raise DuplicateError(f"task link already exists: {link_id}")
        link = ProjectTaskLink(id=link_id, project_id=project_id, task_id=task_id)
        self._store.save_task_link(link)
        org_events.record_project_task_linked(
            self._logger, project_id=project_id, task_id=task_id
        )
        return link

    def list_project_tasks(self, project_id: str) -> list[str]:
        """项目已关联任务 id 列表 (按关联记录 id 排序, 审计友好)。"""
        return [
            l.task_id for l in self._store.list_task_links_by_project(project_id)
        ]

    # ------------------------------------------------------------------ Sprint

    def create_sprint(
        self, project_id: str, name: str, *, sprint_id: str | None = None
    ) -> Sprint:
        """创建 Sprint (org.sprint.created; 项目内任务批次)。"""
        self.get_project(project_id)  # 项目必须存在 (引用完整)
        sprint_id = sprint_id or new_id("S")
        if self._store.get_sprint(sprint_id) is not None:
            raise DuplicateError(f"sprint already exists: {sprint_id}")
        sprint = Sprint(id=sprint_id, project_id=project_id, name=name)
        self._store.save_sprint(sprint)
        org_events.record_sprint_created(self._logger, sprint=sprint)
        return sprint

    def get_sprint(self, sprint_id: str) -> Sprint:
        sprint = self._store.get_sprint(sprint_id)
        if sprint is None:
            raise NotFoundError(f"sprint not found: {sprint_id}")
        return sprint

    def add_task_to_sprint(self, sprint_id: str, task_id: str) -> Sprint:
        """任务加入 Sprint (org.sprint.task_added; 任务须先关联该项目)。

        引用完整: task_id 必须先经 link_task 关联到 sprint 所属项目, 否则
        NotFoundError (防跨项目任务混入 — 项目隔离铁律)。
        """
        sprint = self.get_sprint(sprint_id)
        if task_id in sprint.tasks:
            raise DuplicateError(f"task already in sprint: {task_id}")
        linked = {
            l.task_id
            for l in self._store.list_task_links_by_project(sprint.project_id)
        }
        if task_id not in linked:
            raise NotFoundError(
                f"task {task_id} not linked to project {sprint.project_id} "
                f"(link_task 先关联)"
            )
        updated = sprint.model_copy(update={"tasks": sprint.tasks + [task_id]})
        self._store.save_sprint(updated)
        org_events.record_sprint_task_added(self._logger, sprint=updated, task_id=task_id)
        return updated

    # ------------------------------------------------------------------ Stage

    def create_stage(
        self,
        workflow_id: str,
        role_id: str,
        *,
        order: int = 1,
        stage_id: str | None = None,
    ) -> Stage:
        """创建 Stage (org.stage.created; 组织级编排壳阶段, 不执行)。

        role_id 指向 exec 注册表 (S7-001 单一事实源): 未注册 → ValueError
        (拼写错误立即暴露); exec 未安装 → 跳过校验 (Removal Isolation)。
        """
        _validate_exec_role(role_id)
        stage_id = stage_id or new_id("STG")
        if self._store.get_stage(stage_id) is not None:
            raise DuplicateError(f"stage already exists: {stage_id}")
        stage = Stage(
            id=stage_id,
            workflow_id=workflow_id,
            role_id=role_id,
            order=int(order),
        )
        self._store.save_stage(stage)
        org_events.record_stage_created(self._logger, stage=stage)
        return stage

    def get_stage(self, stage_id: str) -> Stage:
        stage = self._store.get_stage(stage_id)
        if stage is None:
            raise NotFoundError(f"stage not found: {stage_id}")
        return stage

    def list_stages_by_workflow(self, workflow_id: str) -> list[Stage]:
        """Workflow 编排壳的阶段序列 (按 order 排序, 编排消费)。"""
        return sorted(
            self._store.list_stages_by_workflow(workflow_id),
            key=lambda s: s.order,
        )

    # ------------------------------------------------------------------ Artifact

    def create_artifact(
        self,
        stage_id: str,
        type_: ArtifactType | str,
        *,
        ref: str = "",
        artifact_id: str | None = None,
    ) -> Artifact:
        """创建阶段产物 (org.artifact.created; prd|design|code|test|release)。

        stage_id 必须存在 (引用完整); type 经 ArtifactType.parse 宽容解析。
        """
        self.get_stage(stage_id)  # 阶段必须存在 (引用完整)
        artifact_id = artifact_id or new_id("A")
        if self._store.get_artifact(artifact_id) is not None:
            raise DuplicateError(f"artifact already exists: {artifact_id}")
        artifact = Artifact(id=artifact_id, stage_id=stage_id, type=type_, ref=ref)
        self._store.save_artifact(artifact)
        org_events.record_artifact_created(self._logger, artifact=artifact)
        return artifact

    def get_artifact(self, artifact_id: str) -> Artifact:
        artifact = self._store.get_artifact(artifact_id)
        if artifact is None:
            raise NotFoundError(f"artifact not found: {artifact_id}")
        return artifact

    def list_artifacts_by_stage(self, stage_id: str) -> list[Artifact]:
        return self._store.list_artifacts_by_stage(stage_id)
