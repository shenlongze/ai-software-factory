"""factory-console/api/backlog.py — Backlog API 路由函数 (S10-010 Task 003)。

设计依据:
- AF-PRD-v1.md 4.3 (Requirement Management: Backlog 层级 Epic→Feature→
  Story→Task) + project-management-system.md §十 (management/ 目录信源)
- 复用 org.management (Task 001 实体 + Task 002 状态机/priority/dependency
  校验) — 本层只做参数整理 + service 调用 + 错误透传, 零领域逻辑重复。

路由函数 (纯函数调 service, 无 Web 依赖; 错误语义同 11A 惯例):
- create_epic / create_feature / create_story / create_task: 创建层级项
  (可选绑定: Feature→Epic / Story→Feature / Task→Story — 宽松, 引用非包含)
- list_backlog: 全量分组 (epics/features/stories/tasks; 发 console.viewed
  读审计 view="backlog")
- get_task / update_task / delete_task: Task 详情 / PATCH (字段 + 状态机 +
  依赖校验) / DELETE (引用可留)

错误语义 (service 层抛, HTTP 层映射):
- 项目不存在 / 缺 store → 返回 None (HTTP 404)
- 任务/绑定目标不存在 → BacklogNotFoundError (HTTP 404)
- 空 name/title、非法 priority/status、依赖环/自引用/未满足 → ValueError
  (HTTP 400)
- 状态机非法转换 → BacklogStateError (HTTP 409)
"""

from __future__ import annotations

from typing import Any

from ..events import record_console_viewed

#: API 路由标识 (事件 payload view 名 — 读审计; 写操作不扩 Core 事件枚举)
VIEW = "backlog"


# ------------------------------------------------------------------ 创建


def create_epic(
    service: Any,
    project_id: str,
    *,
    name: str,
    description: str = "",
    logger: Any = None,
) -> dict[str, Any] | None:
    """POST /backlog/epic — 创建 Epic (id/created_at/children=[])。

    None → 项目不存在/缺 store (HTTP 404); ValueError → 空 name (HTTP 400)。
    """
    return service.create_epic(project_id, name=name, description=description)


def create_feature(
    service: Any,
    project_id: str,
    *,
    name: str,
    description: str = "",
    epic_id: str = "",
    maturity: str = "refined",
    logger: Any = None,
) -> dict[str, Any] | None:
    """POST /backlog/feature — 创建 Feature (可选绑定 Epic; epic.children 追加;
    maturity idea|refined — 想法模块 💡, 默认 refined 兼容)。

    BacklogNotFoundError → epic_id 不存在 (HTTP 404, 子级绑定不存在);
    ValueError → 空 name / 非法 maturity (HTTP 400)。
    """
    return service.create_feature(
        project_id,
        name=name,
        description=description,
        epic_id=epic_id,
        maturity=maturity,
    )


def create_story(
    service: Any,
    project_id: str,
    *,
    name: str,
    description: str = "",
    feature_id: str = "",
    logger: Any = None,
) -> dict[str, Any] | None:
    """POST /backlog/story — 创建 Story (可选绑定 Feature; feature.children 追加)。"""
    return service.create_story(
        project_id, name=name, description=description, feature_id=feature_id
    )


def create_task(
    service: Any,
    project_id: str,
    *,
    title: str,
    description: str = "",
    priority: Any = None,
    dependency: Any = None,
    story_id: str = "",
    logger: Any = None,
) -> dict[str, Any] | None:
    """POST /backlog/task — 创建 Task (可选绑定 Story; 校验 priority/dependency)。

    ValueError → 空 title / priority 非法 / 依赖环或自引用 (HTTP 400);
    BacklogNotFoundError → story_id 不存在 (HTTP 404)。
    """
    return service.create_task(
        project_id,
        title=title,
        description=description,
        priority=priority,
        dependency=dependency,
        story_id=story_id,
    )


# ------------------------------------------------------------------ 读


def list_backlog(
    service: Any,
    project_id: str,
    *,
    logger: Any = None,
) -> dict[str, Any] | None:
    """GET /backlog — 全量分组 {project_id, epics, features, stories, tasks}。

    None → 项目不存在/缺 store (HTTP 404); 无数据 → 空分组 (诚实空态);
    logger 提供 → console.viewed 读审计 (view="backlog")。
    """
    result = service.list_backlog(project_id)
    if result is None:
        return None
    if logger is not None:
        record_console_viewed(
            logger,
            view=VIEW,
            count=sum(
                len(result[k])
                for k in ("epics", "features", "stories", "tasks")
            ),
            extra={"project_id": project_id},
        )
    return result


def get_task(
    service: Any,
    project_id: str,
    task_id: str,
    *,
    logger: Any = None,
) -> dict[str, Any] | None:
    """GET /backlog/task/{id} — Task 详情。

    None → 项目不存在 (HTTP 404); BacklogNotFoundError → 任务不存在 (HTTP 404)。
    """
    return service.get_task(project_id, task_id)


# ------------------------------------------------------------------ 更新 / 删除


def update_task(
    service: Any,
    project_id: str,
    task_id: str,
    *,
    title: Any = None,
    description: Any = None,
    priority: Any = None,
    status: Any = None,
    assignee: Any = None,
    dependency: Any = None,
    logger: Any = None,
) -> dict[str, Any] | None:
    """PATCH /backlog/task/{id} — 字段更新 + 状态机转换 + 依赖校验 (透传)。"""
    return service.update_task(
        project_id,
        task_id,
        title=title,
        description=description,
        priority=priority,
        status=status,
        assignee=assignee,
        dependency=dependency,
    )


def delete_task(
    service: Any,
    project_id: str,
    task_id: str,
    *,
    logger: Any = None,
) -> dict[str, Any] | None:
    """DELETE /backlog/task/{id} — 删除 Task ({deleted: true, task_id}; 引用可留)。"""
    return service.delete_task(project_id, task_id)
