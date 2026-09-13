"""factory-console/api/sprint.py — Sprint/Milestone/Roadmap API 路由函数 (S10-010 Task 004)。

设计依据:
- AF-PRD-v1.md 4.4/4.5 (Sprint 执行窗口 + Milestone/Roadmap 路线) +
  project-management-system.md §五/§十 (management/ 目录信源)
- 复用 org.management (Task 001 实体 + Task 004 Sprint 状态机/sort_tasks
  纯函数) — 本层只做参数整理 + service 调用 + 错误透传, 零领域逻辑重复。

路由函数 (纯函数调 service, 无 Web 依赖; 错误语义同 11A 惯例):
- create_sprint / list_sprints / get_sprint / update_sprint / delete_sprint:
  Sprint 执行窗口 CRUD (引用 Task, 非包含; 状态受控 planning→active→completed)
- plan_sprint: Planning 预留端点 — 只返回可执行任务建议 (sort_tasks 排序:
  依赖满足优先 + priority), 不实际调度 (S10-011)
- create_milestone / list_milestones / get_milestone / update_milestone /
  delete_milestone: Milestone CRUD (同 Sprint 引用语义; status 自由文本宽容)
- get_roadmap / add_roadmap_milestone_ref: Roadmap 单例 (引用 Milestone)

错误语义 (service 层抛, HTTP 层映射):
- 项目不存在 / 缺 store → 返回 None (HTTP 404)
- Sprint/Milestone 不存在 → BacklogNotFoundError (HTTP 404)
- 空 name、task_ref 引用不存在 Task、milestone-ref 引用不存在 Milestone →
  ValueError (HTTP 400)
- Sprint 状态机非法转换 → BacklogStateError (HTTP 409)
"""

from __future__ import annotations

from typing import Any

from ..events import record_console_viewed

#: API 路由标识 (事件 payload view 名 — 读审计; 写操作不扩 Core 事件枚举)
VIEW = "sprint"


# ------------------------------------------------------------------ Sprint


def create_sprint(
    service: Any,
    project_id: str,
    *,
    name: str,
    goal: str = "",
    start_date: str = "",
    end_date: str = "",
    task_refs: Any = None,
    logger: Any = None,
) -> dict[str, Any] | None:
    """POST /sprints — 创建 Sprint 执行窗口 (默认 planning)。

    None → 项目不存在/缺 store (HTTP 404); ValueError → 空 name /
    task_ref 引用不存在 Task (HTTP 400)。
    """
    return service.create_sprint(
        project_id,
        name=name,
        goal=goal,
        start_date=start_date,
        end_date=end_date,
        task_refs=task_refs,
    )


def list_sprints(
    service: Any,
    project_id: str,
    *,
    logger: Any = None,
) -> dict[str, Any] | None:
    """GET /sprints — Sprint 列表 (诚实空态)。

    None → 项目不存在/缺 store (HTTP 404); logger 提供 → console.viewed
    读审计 (view="sprint")。
    """
    result = service.list_sprints(project_id)
    if result is None:
        return None
    if logger is not None:
        record_console_viewed(
            logger,
            view=VIEW,
            count=len(result.get("sprints", [])),
            extra={"project_id": project_id},
        )
    return result


def get_sprint(
    service: Any,
    project_id: str,
    sprint_id: str,
    *,
    logger: Any = None,
) -> dict[str, Any] | None:
    """GET /sprints/{id} — Sprint 详情。

    None → 项目不存在 (HTTP 404); BacklogNotFoundError → Sprint 不存在 (404)。
    """
    return service.get_sprint(project_id, sprint_id)


def update_sprint(
    service: Any,
    project_id: str,
    sprint_id: str,
    *,
    goal: Any = None,
    planning: Any = None,
    task_refs: Any = None,
    start_date: Any = None,
    end_date: Any = None,
    status: Any = None,
    daily_progress: Any = None,
    review: Any = None,
    logger: Any = None,
) -> dict[str, Any] | None:
    """PATCH /sprints/{id} — 字段更新 + 受控状态转换 + task_refs 校验 (透传)。

    task_refs 引用不存在 Task → ValueError (400); status 非法值 → 400;
    状态机非法转换 → BacklogStateError (409)。
    """
    return service.update_sprint(
        project_id,
        sprint_id,
        goal=goal,
        planning=planning,
        task_refs=task_refs,
        start_date=start_date,
        end_date=end_date,
        status=status,
        daily_progress=daily_progress,
        review=review,
    )


def delete_sprint(
    service: Any,
    project_id: str,
    sprint_id: str,
    *,
    logger: Any = None,
) -> dict[str, Any] | None:
    """DELETE /sprints/{id} — 删除 Sprint ({deleted: true}; Task 保留)。"""
    return service.delete_sprint(project_id, sprint_id)


def plan_sprint(
    service: Any,
    project_id: str,
    sprint_id: str,
    *,
    goal: str = "",
    logger: Any = None,
) -> dict[str, Any] | None:
    """POST /sprints/{id}/plan — Planning 预留端点 (建议, 不调度)。

    返回 {sprint_id, goal, suggestions}: 候选池 = sprint.task_refs (非空)
    否则全量 Backlog Task; org.management.sort_tasks 纯函数排序 (依赖满足
    组优先, 组内 priority P0 最前); 不落库不执行 (S10-011 才实际调度)。
    """
    return service.plan_sprint(project_id, sprint_id, goal=goal)


# -------------------------------------------------------------- Milestone


def create_milestone(
    service: Any,
    project_id: str,
    *,
    name: str,
    description: str = "",
    target_date: str = "",
    task_refs: Any = None,
    logger: Any = None,
) -> dict[str, Any] | None:
    """POST /milestones — 创建 Milestone (默认 planned; 引用 Task)。"""
    return service.create_milestone(
        project_id,
        name=name,
        description=description,
        target_date=target_date,
        task_refs=task_refs,
    )


def list_milestones(
    service: Any,
    project_id: str,
    *,
    logger: Any = None,
) -> dict[str, Any] | None:
    """GET /milestones — Milestone 列表 (诚实空态)。"""
    result = service.list_milestones(project_id)
    if result is None:
        return None
    if logger is not None:
        record_console_viewed(
            logger,
            view="milestone",
            count=len(result.get("milestones", [])),
            extra={"project_id": project_id},
        )
    return result


def get_milestone(
    service: Any,
    project_id: str,
    milestone_id: str,
    *,
    logger: Any = None,
) -> dict[str, Any] | None:
    """GET /milestones/{id} — Milestone 详情。"""
    return service.get_milestone(project_id, milestone_id)


def update_milestone(
    service: Any,
    project_id: str,
    milestone_id: str,
    *,
    name: Any = None,
    description: Any = None,
    target_date: Any = None,
    status: Any = None,
    task_refs: Any = None,
    logger: Any = None,
) -> dict[str, Any] | None:
    """PATCH /milestones/{id} — 字段更新 (status 自由文本, 无状态机)。"""
    return service.update_milestone(
        project_id,
        milestone_id,
        name=name,
        description=description,
        target_date=target_date,
        status=status,
        task_refs=task_refs,
    )


def delete_milestone(
    service: Any,
    project_id: str,
    milestone_id: str,
    *,
    logger: Any = None,
) -> dict[str, Any] | None:
    """DELETE /milestones/{id} — 删除 Milestone (Roadmap 引用可留)。"""
    return service.delete_milestone(project_id, milestone_id)


# ---------------------------------------------------------------- Roadmap


def get_roadmap(
    service: Any,
    project_id: str,
    *,
    logger: Any = None,
) -> dict[str, Any] | None:
    """GET /roadmap — 路线单例 {project_id, milestone_refs, updated_at}。"""
    result = service.get_roadmap(project_id)
    if result is None:
        return None
    if logger is not None:
        record_console_viewed(
            logger,
            view="roadmap",
            count=len(result.get("milestone_refs", [])),
            extra={"project_id": project_id},
        )
    return result


def add_roadmap_milestone_ref(
    service: Any,
    project_id: str,
    milestone_id: str,
    *,
    logger: Any = None,
) -> dict[str, Any] | None:
    """POST /roadmap/milestone-ref — 追加 Milestone 引用 (去重幂等)。

    ValueError → milestone 不存在 (HTTP 400, 同 task_ref 引用校验语义)。
    """
    return service.add_roadmap_milestone_ref(project_id, milestone_id)
