"""factory-org/org/management.py — Management Domain Model (S10-010 Task 001)。

设计依据 (唯一):
- docs/design/project-management-system.md (Agile Scrum 管理模型 + §十 数据存储)
- docs/design/AF-PRD-v1.md 4.3/4.4/4.5/4.6 (Requirement/Agile/Sprint/Task Management)
- docs/design/project-lifecycle.md §四 (Project Space 的 management/ 目录)

模型 (Backlog 层级 + Sprint 执行窗口 — PRD 4.4 引用非包含):
```
Backlog: Epic → Feature → Story → Task        (需求层级, children 引用 id)
Sprint:  task_refs 引用 Task (非包含 — Task 属 Backlog, Sprint 只是执行窗口,
         一个 Task 可延期/转移 Sprint/重新规划, 需求不变)
Milestone: task_refs; Roadmap: milestone_refs (生死节点)
```

存储 (目录信源 — project-management-system.md §十; management/ 为数据信源,
不依赖 org/projects.json):
```
workspace/projects/{slug}/management/
  backlog/task.json | epic.json | feature.json | story.json   # {section: {id: dict}}
  sprint/{sprint-id}.json                                     # {"sprint": {dict}}
  milestone.json                                              # {"milestones": {id: dict}}
  roadmap.md                                                  # md + 结构化注释块
```

语义:
- 懒建: 首次写才创建目录/文件; S10-009 旧项目 (无 management/ 目录) 只读访问
  返回空/None, 零破坏 (不预建目录)
- 失败安全: 损坏 JSON → get 返回 None / list 返回空 (信源可重建, 不抛错)
- 原子写: 临时文件 + os.replace (同 org/store.py 模式)
- 引用语义: Sprint 删除 Task 引用保留; 更新 task_refs 不影响 Task 本身
- 本模块零 Core 依赖 (stdlib + pydantic + org.models, Removal Isolation)
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import Field, ValidationError, field_serializer, field_validator

from .models import _OrgModel, _norm_list, utcnow

T = TypeVar("T", bound="_OrgModel")


# ------------------------------------------------------------------ 枚举


class TaskPriority(str, Enum):
    """任务优先级 (PRD 4.3 / project-management-system.md §四):

    P0 Critical / P1 Important / P2 Normal / P3 Nice To Have。
    """

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"

    @classmethod
    def parse(cls, value: Any) -> "TaskPriority":
        """宽容解析: 大小写不敏感 (p1 → P1); 枚举对象直接返回; 非法抛 ValueError。"""
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().upper())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(
                f"invalid task priority: {value!r} (expected one of: {valid})"
            ) from None


class TaskStatus(str, Enum):
    """任务状态 (本 Task 约定六态; 异常路径 BLOCKED 显式枚举)。"""

    TODO = "todo"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    REVIEW = "review"
    DONE = "done"

    @classmethod
    def parse(cls, value: Any) -> "TaskStatus":
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(
                f"invalid task status: {value!r} (expected one of: {valid})"
            ) from None


class SprintStatus(str, Enum):
    """Sprint 状态 (PRD 4.5: planning → active → completed)。"""

    PLANNING = "planning"
    ACTIVE = "active"
    COMPLETED = "completed"

    @classmethod
    def parse(cls, value: Any) -> "SprintStatus":
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(
                f"invalid sprint status: {value!r} (expected one of: {valid})"
            ) from None


# ------------------------------------------------------------------ 实体


class HistoryEntry(_OrgModel):
    """任务审计条目 (PRD 4.6: 谁什么时候干了什么 — 多 Agent 公司可审计)。"""

    time: str = ""
    actor: str = ""
    action: str = ""
    result: str = ""


class Task(_OrgModel):
    """任务 (Backlog 最细粒度 — 实际执行工作; PRD 4.3 全字段)。

    priority: P0-P3 (默认 P2 Normal); status: todo/ready/in_progress/blocked/
    review/done (默认 todo); dependency: 前置任务 id 列表; history: 审计链
    [{time, actor, action, result}]。
    """

    id: str
    title: str
    description: str = ""
    priority: TaskPriority = TaskPriority.P2
    status: TaskStatus = TaskStatus.TODO
    assignee: str = ""
    dependency: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    history: list[HistoryEntry] = Field(default_factory=list)

    @field_validator("priority", mode="before")
    @classmethod
    def _coerce_priority(cls, v: Any) -> TaskPriority:
        return TaskPriority.parse(v)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> TaskStatus:
        return TaskStatus.parse(v)

    @field_validator("dependency", mode="before")
    @classmethod
    def _dependency_none(cls, v: Any) -> Any:
        return _norm_list(v)

    @field_validator("history", mode="before")
    @classmethod
    def _history_none(cls, v: Any) -> Any:
        return _norm_list(v)

    @field_serializer("history")
    def _ser_history(self, value: Any, _info: Any) -> list[dict[str, Any]]:
        """序列化归一: model_copy 直接替换的 dict 元素 → HistoryEntry (JSON 干净,
        零 pydantic 警告 — 状态流转审计链可经 model_copy 追加 dict 条目)。"""
        return [
            h.to_dict()
            if isinstance(h, HistoryEntry)
            else HistoryEntry.model_validate(h).to_dict()
            for h in value
        ]


class Epic(_OrgModel):
    """Epic (月/季度 — 大能力; children = Feature id 引用, 非包含)。"""

    id: str
    name: str
    description: str = ""
    children: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("children", mode="before")
    @classmethod
    def _children_none(cls, v: Any) -> Any:
        return _norm_list(v)


class Feature(_OrgModel):
    """Feature (周/月 — 用户可感知功能; children = Story id 引用)。"""

    id: str
    name: str
    description: str = ""
    children: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("children", mode="before")
    @classmethod
    def _children_none(cls, v: Any) -> Any:
        return _norm_list(v)


class Story(_OrgModel):
    """Story (周 — 用户需求描述; children = Task id 引用)。"""

    id: str
    name: str
    description: str = ""
    children: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("children", mode="before")
    @classmethod
    def _children_none(cls, v: Any) -> Any:
        return _norm_list(v)


class Sprint(_OrgModel):
    """Sprint (固定周期执行窗口 — PRD 4.4/4.5: 引用 Task, 不包含)。

    task_refs: Task id 引用列表 (非包含 — Task 属 Backlog; 删除/转移 Task
    不影响需求); goal/planning: Sprint 目标与计划; daily_progress: 每日进度;
    review: Sprint Review 总结; start_date/end_date: 窗口起止 (ISO 日期串)。
    """

    id: str
    name: str
    goal: str = ""
    planning: str = ""
    task_refs: list[str] = Field(default_factory=list)
    start_date: str = ""
    end_date: str = ""
    status: SprintStatus = SprintStatus.PLANNING
    daily_progress: list[dict[str, Any]] = Field(default_factory=list)
    review: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> SprintStatus:
        return SprintStatus.parse(v)

    @field_validator("task_refs", "daily_progress", mode="before")
    @classmethod
    def _lists_none(cls, v: Any) -> Any:
        return _norm_list(v)


class Milestone(_OrgModel):
    """Milestone (项目生死节点 — project-management-system.md §五;

    Milestone → Epic → Feature → Task; task_refs 引用 Task, 非包含)。
    status: planned/in_progress/completed 等自由文本 (宽容, 不设枚举)。
    """

    id: str
    name: str
    description: str = ""
    target_date: str = ""
    status: str = "planned"
    task_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("task_refs", mode="before")
    @classmethod
    def _task_refs_none(cls, v: Any) -> Any:
        return _norm_list(v)


class Roadmap(_OrgModel):
    """Roadmap (项目路线 — 每项目单例, 存 roadmap.md; milestone_refs 引用
    Milestone, 非包含)。"""

    id: str = "roadmap"
    milestone_refs: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("milestone_refs", mode="before")
    @classmethod
    def _refs_none(cls, v: Any) -> Any:
        return _norm_list(v)


# ------------------------------------------------------------------ 存储


def _read_json_map(path: Path, section: str) -> dict[str, dict[str, Any]]:
    """读 {section: {id: dict}}; 缺失/损坏/非 dict → {} (失败安全)。"""
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    data = raw.get(section) if isinstance(raw, dict) else None
    return data if isinstance(data, dict) else {}


def _write_json_map(path: Path, section: str, records: dict[str, dict[str, Any]]) -> None:
    """原子写 {section: {id: dict}} (临时文件 + os.replace, 同 store.py 模式)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    tmp.write_text(
        json.dumps({section: dict(sorted(records.items()))}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


class _Section(Generic[T]):
    """单文件 JSON 记录库 (backlog/*.json + milestone.json 共用)。

    语义: save upsert / get 缺失或损坏 → None / list 损坏跳过 / delete 幂等。
    """

    def __init__(self, dir_: Path, filename: str, section: str, model: type[T]):
        self._dir = dir_
        self._filename = filename
        self._section = section
        self._model = model

    def _path(self) -> Path:
        return self._dir / self._filename

    def _load(self, data: dict[str, Any]) -> T | None:
        try:
            return self._model.model_validate(data)
        except ValidationError:
            return None  # 损坏记录 → None (失败安全, 不拖垮整库)

    def save(self, record: T) -> None:
        records = _read_json_map(self._path(), self._section)
        records[record.id] = record.to_dict()  # type: ignore[attr-defined]
        _write_json_map(self._path(), self._section, records)

    def get(self, record_id: str) -> T | None:
        data = _read_json_map(self._path(), self._section).get(record_id)
        if data is None:
            return None
        return self._load(data)

    def list_all(self) -> list[T]:
        return sorted(
            (
                loaded
                for data in _read_json_map(self._path(), self._section).values()
                if (loaded := self._load(data)) is not None
            ),
            key=lambda r: r.id,  # type: ignore[attr-defined, return-value]
        )

    def delete(self, record_id: str) -> bool:
        records = _read_json_map(self._path(), self._section)
        if record_id not in records:
            return False
        del records[record_id]
        _write_json_map(self._path(), self._section, records)
        return True


_ROADMAP_RE = re.compile(r"<!-- management-json: (\{.*?\}) -->", re.DOTALL)


class ManagementStore:
    """Management 目录信源门面 (workspace/projects/{slug}/management/)。

    布局 (project-management-system.md §十):
    - backlog/task.json + epic.json + feature.json + story.json (Backlog 层级信源)
    - sprint/{sprint-id}.json (每 Sprint 一文件)
    - milestone.json + roadmap.md (生死节点/路线)

    语义: 懒建 (首次写建目录; 旧项目无 management/ → 读空, 零破坏);
    失败安全 (损坏 JSON → 空/默认); 引用非包含 (Sprint/Milestone/Roadmap
    只引用 Task/Epic id, 不拷贝); 原子写。本门面只依赖 management/ 目录,
    不依赖 org/projects.json (目录信源独立)。
    """

    def __init__(self, management_dir: str | Path):
        self._dir = Path(management_dir)
        self._backlog = self._dir / "backlog"
        self._sprint_dir = self._dir / "sprint"
        self._tasks = _Section(self._backlog, "task.json", "tasks", Task)
        self._epics = _Section(self._backlog, "epic.json", "epics", Epic)
        self._features = _Section(self._backlog, "feature.json", "features", Feature)
        self._stories = _Section(self._backlog, "story.json", "stories", Story)
        self._milestones = _Section(self._dir, "milestone.json", "milestones", Milestone)

    @property
    def dir(self) -> Path:
        """管理目录 (workspace/projects/{slug}/management/)。"""
        return self._dir

    # ------------------------------------------------------------------ Task
    def save_task(self, task: Task) -> None:
        self._tasks.save(task)

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[Task]:
        return self._tasks.list_all()

    def delete_task(self, task_id: str) -> bool:
        return self._tasks.delete(task_id)

    # ------------------------------------------------------------------ Epic
    def save_epic(self, epic: Epic) -> None:
        self._epics.save(epic)

    def get_epic(self, epic_id: str) -> Epic | None:
        return self._epics.get(epic_id)

    def list_epics(self) -> list[Epic]:
        return self._epics.list_all()

    def delete_epic(self, epic_id: str) -> bool:
        return self._epics.delete(epic_id)

    # --------------------------------------------------------------- Feature
    def save_feature(self, feature: Feature) -> None:
        self._features.save(feature)

    def get_feature(self, feature_id: str) -> Feature | None:
        return self._features.get(feature_id)

    def list_features(self) -> list[Feature]:
        return self._features.list_all()

    def delete_feature(self, feature_id: str) -> bool:
        return self._features.delete(feature_id)

    # ------------------------------------------------------------------ Story
    def save_story(self, story: Story) -> None:
        self._stories.save(story)

    def get_story(self, story_id: str) -> Story | None:
        return self._stories.get(story_id)

    def list_stories(self) -> list[Story]:
        return self._stories.list_all()

    def delete_story(self, story_id: str) -> bool:
        return self._stories.delete(story_id)

    # ----------------------------------------------------------------- Sprint
    def _sprint_path(self, sprint_id: str) -> Path:
        return self._sprint_dir / f"{sprint_id}.json"

    def save_sprint(self, sprint: Sprint) -> None:
        """每 Sprint 一文件 (sprint/{sprint-id}.json = {"sprint": {...}})。"""
        path = self._sprint_path(sprint.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
        tmp.write_text(
            json.dumps({"sprint": sprint.to_dict()}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, path)

    def get_sprint(self, sprint_id: str) -> Sprint | None:
        path = self._sprint_path(sprint_id)
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        data = raw.get("sprint") if isinstance(raw, dict) else None
        if not isinstance(data, dict):
            return None
        try:
            return Sprint.model_validate(data)
        except ValidationError:
            return None

    def list_sprints(self) -> list[Sprint]:
        """扫描 sprint/*.json (损坏文件跳过 — 失败安全)。"""
        if not self._sprint_dir.is_dir():
            return []
        sprints: list[Sprint] = []
        for path in sorted(self._sprint_dir.glob("*.json")):
            sprint = self.get_sprint(path.stem)
            if sprint is not None:
                sprints.append(sprint)
        return sprints

    def delete_sprint(self, sprint_id: str) -> bool:
        path = self._sprint_path(sprint_id)
        if not path.is_file():
            return False
        path.unlink()
        return True

    # -------------------------------------------------------------- Milestone
    def save_milestone(self, milestone: Milestone) -> None:
        self._milestones.save(milestone)

    def get_milestone(self, milestone_id: str) -> Milestone | None:
        return self._milestones.get(milestone_id)

    def list_milestones(self) -> list[Milestone]:
        return self._milestones.list_all()

    def delete_milestone(self, milestone_id: str) -> bool:
        return self._milestones.delete(milestone_id)

    # ---------------------------------------------------------------- Roadmap
    def _roadmap_path(self) -> Path:
        return self._dir / "roadmap.md"

    def save_roadmap(self, roadmap: Roadmap) -> None:
        """roadmap.md 信源: markdown 文档 + 结构化注释块 (机器可读, 损坏可重建)。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        block = json.dumps(roadmap.to_dict(), ensure_ascii=False)
        lines = [
            "# Roadmap",
            "",
            f"<!-- management-json: {block} -->",
            "",
            "## Milestones",
        ]
        lines += [f"- {ref}" for ref in roadmap.milestone_refs]
        path = self._roadmap_path()
        tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(tmp, path)

    def get_roadmap(self) -> Roadmap:
        """读 roadmap.md 结构化块; 缺失/损坏/无块 → 默认空 Roadmap (失败安全)。"""
        path = self._roadmap_path()
        if not path.is_file():
            return Roadmap()
        match = _ROADMAP_RE.search(path.read_text(encoding="utf-8"))
        if match is None:
            return Roadmap()
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return Roadmap()
        try:
            return Roadmap.model_validate(data)
        except ValidationError:
            return Roadmap()
