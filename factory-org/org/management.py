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

    S10 方案A (执行绑定+回写): exec_ref = 执行绑定 (exec request id EXR-* /
    引擎任务 id; 空 = 未绑定); exec_result = 最近执行结果 id (EXS-*)。exec
    启动/完成时由桥自动回写状态与审计 (exec:started / exec:completed /
    exec:failed)。
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
    exec_ref: str = ""
    exec_result: str = ""

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


# ------------------------------------------------------------------ 业务规则 (S10-010 Task 002)

#: 受控状态转换表 (PRD 4.3 六态约定; 异常路径 BLOCKED 显式枚举;
#: done 为终态 — 无任何合法去向)。key=当前态, value=合法目标态元组。
TASK_TRANSITIONS: dict[TaskStatus, tuple[TaskStatus, ...]] = {
    TaskStatus.TODO: (TaskStatus.READY, TaskStatus.BLOCKED),
    TaskStatus.READY: (TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED),
    TaskStatus.IN_PROGRESS: (TaskStatus.BLOCKED, TaskStatus.REVIEW),
    TaskStatus.BLOCKED: (TaskStatus.READY, TaskStatus.IN_PROGRESS),
    TaskStatus.REVIEW: (TaskStatus.IN_PROGRESS, TaskStatus.DONE),
    TaskStatus.DONE: (),
}

#: 依赖门控目标态: 进入就绪/执行前必须依赖全部满足 (PRD 4.7 依赖链串行)。
_DEPENDENCY_GATED: frozenset[TaskStatus] = frozenset(
    {TaskStatus.READY, TaskStatus.IN_PROGRESS}
)

#: 优先级权重 (P0 Critical 最高 → 排序最前; 未知值兜底排最后)。
_PRIORITY_RANK: dict[TaskPriority, int] = {
    TaskPriority.P0: 0,
    TaskPriority.P1: 1,
    TaskPriority.P2: 2,
    TaskPriority.P3: 3,
}

#: Sprint 受控状态转换表 (PRD 4.5: planning → active → completed; completed
#: 为终态 — 无任何合法去向; 跳级/回退一律拒绝)。
SPRINT_TRANSITIONS: dict[SprintStatus, tuple[SprintStatus, ...]] = {
    SprintStatus.PLANNING: (SprintStatus.ACTIVE,),
    SprintStatus.ACTIVE: (SprintStatus.COMPLETED,),
    SprintStatus.COMPLETED: (),
}


def transition_task(
    task: Task,
    target: TaskStatus | str,
    *,
    actor: str = "",
    action: str = "transition",
    result: str = "OK",
    dependency_status: dict[str, TaskStatus] | None = None,
) -> Task:
    """受控状态转换 (纯函数 — 返回新 Task, 原对象不变)。

    - 目标态不在 TASK_TRANSITIONS[当前态] → ValueError (跳级/回退/终态后/同态)
    - 依赖门控: 目标 ∈ {READY, IN_PROGRESS} 且 task.dependency 非空 →
      必须提供 dependency_status 且全部依赖 == DONE, 否则 ValueError
      (依赖未满足拒绝推进 — PRD 4.7)
    - 每次转换追加 history 条目 {time, actor, action, result} (PRD 4.6 审计链)
    """
    from_status = task.status
    target_status = TaskStatus.parse(target)
    if target_status not in TASK_TRANSITIONS[from_status]:
        raise ValueError(
            f"illegal task transition: {from_status.value} -> {target_status.value} "
            f"(allowed: {[s.value for s in TASK_TRANSITIONS[from_status]]})"
        )
    if target_status in _DEPENDENCY_GATED and task.dependency:
        if dependency_status is None:
            raise ValueError(
                "dependency status required: task has dependencies "
                f"{task.dependency} but dependency_status was not provided"
            )
        unsatisfied = [
            dep for dep in task.dependency
            if dependency_status.get(dep) != TaskStatus.DONE
        ]
        if unsatisfied:
            raise ValueError(
                f"dependency not satisfied: task {task.id} depends on "
                f"{unsatisfied} (not DONE)"
            )
    entry = HistoryEntry(
        time=utcnow().isoformat(),
        actor=actor,
        action=action,
        result=result,
    )
    return task.model_copy(
        update={
            "status": target_status,
            "history": list(task.history) + [entry],
            "updated_at": utcnow(),
        }
    )


def validate_dependency(
    dependency: list[str] | None,
    task_id: str,
    *,
    known_dependencies: dict[str, list[str]] | None = None,
) -> list[str]:
    """Dependency 列表校验 + 环检测 (创建/更新 Task.dependency 时调用)。

    - 元素必须为非空 str id 引用 (规范列表); 返回去重保序的新列表
    - 自引用拒绝: task_id 出现在自身 dependency 中 → ValueError
    - 环检测: 结合 known_dependencies (其它任务依赖声明) 构图, DFS 从
      task_id 出发若可达自身 → ValueError (A→B→A 及深层环)
    """
    deps = [d for d in _norm_list(dependency)]
    for dep in deps:
        if not isinstance(dep, str) or not dep.strip():
            raise ValueError(
                f"invalid dependency reference: {dep!r} "
                "(expected non-empty str task id)"
            )
    if task_id in deps:
        raise ValueError(f"self-reference rejected: task {task_id} depends on itself")
    graph: dict[str, list[str]] = {
        k: list(v) for k, v in (known_dependencies or {}).items()
    }
    graph[task_id] = deps
    visited: set[str] = set()
    stack = list(graph.get(task_id, []))
    while stack:
        node = stack.pop()
        if node == task_id:
            raise ValueError(
                f"dependency cycle detected: task {task_id} transitively "
                f"depends on itself"
            )
        if node in visited:
            continue
        visited.add(node)
        stack.extend(graph.get(node, []))
    return list(dict.fromkeys(deps))  # 去重保序


def sort_by_priority(tasks: list[Task]) -> list[Task]:
    """按优先级排序 (P0 Critical 最前 — 纯函数, 不改入参; 稳定排序)。"""
    return sorted(tasks, key=lambda t: _PRIORITY_RANK.get(t.priority, 99))


def sort_tasks(
    tasks: list[Task],
    *,
    dependency_status: dict[str, TaskStatus] | None = None,
) -> list[Task]:
    """AI 排序预留 (纯函数): dependency 感知排序 — 依赖完成优先。

    - dependency_status 提供时: 存在未满足依赖 (非 DONE) 的任务排后
      (即使 P0); 满足组内按 priority 排序 (P0 最前)
    - dependency_status 缺省 → 退化为纯 priority 排序 (sort_by_priority)
    """
    if dependency_status is None:
        return sort_by_priority(tasks)

    def _unsatisfied(t: Task) -> int:
        return 0 if all(
            dependency_status.get(dep) == TaskStatus.DONE for dep in t.dependency
        ) else 1

    return sorted(
        tasks,
        key=lambda t: (_unsatisfied(t), _PRIORITY_RANK.get(t.priority, 99)),
    )


def transition_sprint(sprint: Sprint, target: SprintStatus | str) -> Sprint:
    """Sprint 受控状态转换 (纯函数 — 返回新 Sprint, 原对象不变)。

    - 目标态不在 SPRINT_TRANSITIONS[当前态] → ValueError (跳级/回退/终态后)
    - 合法转换 → model_copy 更新 status + updated_at (Sprint 无 history 链 —
      审计由 service/API 层事件承担)
    """
    from_status = sprint.status
    target_status = SprintStatus.parse(target)
    if target_status not in SPRINT_TRANSITIONS[from_status]:
        raise ValueError(
            f"illegal sprint transition: {from_status.value} -> {target_status.value} "
            f"(allowed: {[s.value for s in SPRINT_TRANSITIONS[from_status]]})"
        )
    return sprint.model_copy(
        update={"status": target_status, "updated_at": utcnow()}
    )


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
