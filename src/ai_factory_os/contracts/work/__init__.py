"""work — 项目 / 工作 / 工作流 / 任务 / 任务节点。零依赖。

层级固定：Project → Work → Workstream → Task → TaskNode
TaskNode 是**可调度的最小单位**；调度器只认它。
"""
from __future__ import annotations

from dataclasses import dataclass

PROJECT_STATES: tuple[str, ...] = ("draft", "active", "on_hold", "completed", "archived")
WORK_STATES: tuple[str, ...] = ("draft", "active", "on_hold", "completed", "archived")
WORKSTREAM_STATES: tuple[str, ...] = ("draft", "active", "on_hold", "completed", "archived")
TASK_STATES: tuple[str, ...] = ("todo", "ready", "in_progress", "blocked", "completed", "cancelled")
TASK_PRIORITIES: tuple[str, ...] = ("P0", "P1", "P2", "P3")
TASK_NODE_STATES: tuple[str, ...] = ("pending", "ready", "blocked", "running", "completed", "cancelled")


@dataclass(frozen=True)
class Acceptance:
    """验收标准 —— 必须机器可判，否则不算标准。"""

    statement: str
    check: str = ""


@dataclass(frozen=True)
class Project:
    """项目 —— 工作的容器，交付与预算归属的边界。"""

    id: str
    company_id: str
    name: str
    goal: str = ""
    acceptance: tuple[Acceptance, ...] = ()
    deadline: str = ""
    status: str = "draft"


@dataclass(frozen=True)
class Work:
    """工作 —— 项目下一级的可管理单元。"""

    id: str
    project_id: str
    name: str
    status: str = "draft"


@dataclass(frozen=True)
class Workstream:
    """工作流 —— 一条并行推进的线。"""

    id: str
    work_id: str
    name: str
    status: str = "draft"


@dataclass(frozen=True)
class Task:
    """任务 —— 有优先级、有负责人、有验收标准。"""

    id: str
    work_id: str
    name: str
    workstream_id: str = ""
    priority: str = "P2"
    owner_id: str = ""
    acceptance: tuple[Acceptance, ...] = ()
    status: str = "todo"


@dataclass(frozen=True)
class TaskNode:
    """任务节点 —— **可调度的最小单位**。

    depends_on 是节点间依赖；required_capability_refs 声明需要什么能力。
    完成的判据不是「跑完了」，而是「有 accepted Outcome」（见 execution）。
    """

    id: str
    task_id: str
    name: str
    sequence: int = 0
    depends_on: tuple[str, ...] = ()
    required_capability_refs: tuple[str, ...] = ()
    status: str = "pending"
