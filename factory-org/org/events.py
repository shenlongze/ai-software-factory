"""factory-org/org/events.py — org.* 事件辅助 (经 factory-core EventLogger)。

设计依据:
- phase16-organization-model-review.md §6: org.company.created /
  org.employee.joined / org.authority.granted / ... 全部组织变化可审计。
- ADR-0001 决策 1 扩展路径: EventType 枚举加成员即可 (events/models.py 已
  扩展 137 → 151); logger 为 None 时全部静默 (同 intelligence/events.py 模式)。
- ADR-0002: 所有 CLI 行为必须产生 Event — viewed/checked 为读命令审计
  (source="cli"); 写路径事件 source="org"。

payload 契约 (事件唯一事实源: 从事件 payload 可重建组织变化关键字段):
- company.created:  company_id/name/template/department_count/role_count
- department.created: department_id/company_id/name
- role.created:     role_id/company_id/department_id/name/authority_count
- employee.joined:  employee_id/company_id/name/role_count/capability_count
- employee.left:    employee_id/company_id/name/status
- employee.capability_added: employee_id/company_id/capability
- employee.role_assigned:    employee_id/company_id/role_id
- authority.granted/denied:  authority_id/role_id/permission/effect
- authority.checked: employee_id (可选)/role_ids/permission/allowed
- knowledge.bound:  knowledge_id/company_id/domain/version
- viewed 类: company_id (可选)/count 汇总
"""

from __future__ import annotations

from typing import Any

from events.models import Event, EventType


def last_seq(logger: Any, event_type: EventType) -> int | None:
    """该事件类型最近一条的 seq (CLI 审计锚点); logger=None → None。

    事件库按 seq 升序查询, 取尾部即最近一条 (event 数少, 全量过滤可接受)。
    """
    if logger is None:
        return None
    events = logger.store.query(event_type=event_type)
    return events[-1].seq if events else None


def record_company_created(logger: Any, *, company: Any, source: str = "org") -> Event | None:
    """公司创建 (org.company.created; 模板实例化根事件)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_COMPANY_CREATED,
        source=source,
        stage="created",
        action="create company",
        result="OK",
        payload={
            "company_id": company.id,
            "name": company.name,
            "template": company.template,
            "parent_company": company.parent_company,
            "department_count": len(company.departments),
        },
    )


def record_company_viewed(logger: Any, *, company: Any, source: str = "cli") -> Event | None:
    """公司详情被查看 (org.company.viewed; 读命令审计, ADR-0002)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_COMPANY_VIEWED,
        source=source,
        stage="viewed",
        action="view company",
        result="OK",
        payload={
            "company_id": company.id,
            "name": company.name,
            "template": company.template,
        },
    )


def record_department_created(logger: Any, *, department: Any, source: str = "org") -> Event | None:
    """部门创建 (org.department.created)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_DEPARTMENT_CREATED,
        source=source,
        stage="created",
        action="create department",
        result="OK",
        payload={
            "department_id": department.id,
            "company_id": department.company_id,
            "name": department.name,
        },
    )


def record_role_created(logger: Any, *, role: Any, source: str = "org") -> Event | None:
    """职位创建 (org.role.created; 权限矩阵物化后的角色定义)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_ROLE_CREATED,
        source=source,
        stage="created",
        action="create role",
        result="OK",
        payload={
            "role_id": role.id,
            "company_id": role.company_id,
            "department_id": role.department_id,
            "name": role.name,
            "human": role.human,
            "authority_count": len(role.authority_policy),
        },
    )


def record_employee_joined(logger: Any, *, employee: Any, source: str = "org") -> Event | None:
    """员工入职 (org.employee.joined; 子链: role_assigned/capability_added)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_EMPLOYEE_JOINED,
        source=source,
        stage="active",
        action="hire employee",
        result="OK",
        payload={
            "employee_id": employee.id,
            "company_id": employee.company_id,
            "name": employee.name,
            "role_count": len(employee.role_ids),
            "capability_count": len(employee.capabilities),
        },
    )


def record_employee_left(logger: Any, *, employee: Any, source: str = "org") -> Event | None:
    """员工离职 (org.employee.left; 权限即刻失效, 记录保留审计)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_EMPLOYEE_LEFT,
        source=source,
        stage=employee.status.value,
        action="employee left",
        result="OK",
        payload={
            "employee_id": employee.id,
            "company_id": employee.company_id,
            "name": employee.name,
        },
    )


def record_employee_capability_added(
    logger: Any, *, employee: Any, capability: str, source: str = "org"
) -> Event | None:
    """能力培训 (org.employee.capability_added; 不自动提权 — 权限看 Role)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_EMPLOYEE_CAPABILITY_ADDED,
        source=source,
        stage="training",
        action="add capability",
        result="OK",
        payload={
            "employee_id": employee.id,
            "company_id": employee.company_id,
            "capability": capability,
        },
    )


def record_employee_role_assigned(
    logger: Any, *, employee: Any, role_id: str, source: str = "org"
) -> Event | None:
    """角色分配/转岗 (org.employee.role_assigned; 冲突组合硬拒绝后发出)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_EMPLOYEE_ROLE_ASSIGNED,
        source=source,
        stage="assigned",
        action="assign role",
        result="OK",
        payload={
            "employee_id": employee.id,
            "company_id": employee.company_id,
            "role_id": role_id,
        },
    )


def record_employee_viewed(logger: Any, *, count: int, source: str = "cli") -> Event | None:
    """员工清单被查看 (org.employee.viewed; 读命令审计, ADR-0002)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_EMPLOYEE_VIEWED,
        source=source,
        stage="viewed",
        action="list employees",
        result="OK",
        payload={"count": count},
    )


def record_authority_granted(logger: Any, *, authority: Any, source: str = "org") -> Event | None:
    """权限授予 (org.authority.granted; Role 绑定, 默认 deny 语义下显式 allow)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_AUTHORITY_GRANTED,
        source=source,
        stage="granted",
        action="grant authority",
        result="OK",
        payload={
            "authority_id": authority.id,
            "role_id": authority.role_id,
            "permission": authority.permission,
            "effect": authority.effect,
        },
    )


def record_authority_denied(logger: Any, *, authority: Any, source: str = "org") -> Event | None:
    """显式拒绝 (org.authority.denied; deny 优先于任何 allow)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_AUTHORITY_DENIED,
        source=source,
        stage="denied",
        action="deny authority",
        result="OK",
        payload={
            "authority_id": authority.id,
            "role_id": authority.role_id,
            "permission": authority.permission,
            "effect": authority.effect,
        },
    )


def record_authority_checked(
    logger: Any,
    *,
    permission: str,
    allowed: bool,
    role_ids: list[str],
    employee_id: str | None = None,
    source: str = "cli",
) -> Event | None:
    """权限校验 (org.authority.checked; 读命令审计, 越权尝试也审计)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_AUTHORITY_CHECKED,
        source=source,
        stage="checked",
        action="check authority",
        result="ALLOW" if allowed else "DENY",
        payload={
            "employee_id": employee_id,
            "role_ids": role_ids,
            "permission": permission,
            "allowed": allowed,
        },
    )


def record_knowledge_bound(logger: Any, *, item: Any, source: str = "org") -> Event | None:
    """知识入库 (org.knowledge.bound; 公司隔离, 版本化)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_KNOWLEDGE_BOUND,
        source=source,
        stage="bound",
        action="add knowledge",
        result="OK",
        payload={
            "knowledge_id": item.id,
            "company_id": item.company_id,
            "domain": item.domain,
            "version": item.version,
        },
    )


def record_knowledge_viewed(logger: Any, *, count: int, source: str = "cli") -> Event | None:
    """知识清单被查看 (org.knowledge.viewed; 读命令审计, ADR-0002)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_KNOWLEDGE_VIEWED,
        source=source,
        stage="viewed",
        action="list knowledge",
        result="OK",
        payload={"count": count},
    )


# ------------------------------------------------------------------ 统一生命周期 (S7-001)
# org.project.* / org.sprint.* / org.stage.* / org.artifact.* 事件 — 模型见
# org/projects.py (User→Project→Sprint→Workflow→Stage→Task→Artifact)。
# 同既有 org.* 模式: logger=None 全静默; payload 唯一事实源。

PROJECT_LIFECYCLES = ("idea", "active", "maintained", "archived")
ARTIFACT_TYPES = ("prd", "design", "code", "test", "release")


def record_project_created(logger: Any, *, project: Any, source: str = "org") -> Event | None:
    """项目创建 (org.project.created; 用户想法的生命周期容器)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_PROJECT_CREATED,
        source=source,
        stage=project.lifecycle.value,
        action="create project",
        result="OK",
        payload={
            "project_id": project.id,
            "name": project.name,
            "user_id": project.user_id,
            "goal": project.goal,
            "lifecycle": project.lifecycle.value,
        },
    )


def record_project_lifecycle_changed(
    logger: Any,
    *,
    project: Any,
    from_lifecycle: str,
    to_lifecycle: str,
    source: str = "org",
) -> Event | None:
    """项目生命周期流转 (org.project.lifecycle_changed; idea→active→...)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_PROJECT_LIFECYCLE_CHANGED,
        source=source,
        stage=to_lifecycle,
        action="transition project lifecycle",
        result="OK",
        payload={
            "project_id": project.id,
            "from_lifecycle": from_lifecycle,
            "to_lifecycle": to_lifecycle,
        },
    )


def record_project_task_linked(
    logger: Any, *, project_id: str, task_id: str, source: str = "org"
) -> Event | None:
    """项目 ↔ Core Task 关联 (org.project.task_linked; Task 冻结, 扩展侧映射表)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_PROJECT_TASK_LINKED,
        source=source,
        stage="linked",
        action="link task to project",
        result="OK",
        task_id=task_id,
        payload={"project_id": project_id, "task_id": task_id},
    )


def record_sprint_created(logger: Any, *, sprint: Any, source: str = "org") -> Event | None:
    """Sprint 创建 (org.sprint.created; 项目内任务批次)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_SPRINT_CREATED,
        source=source,
        stage="created",
        action="create sprint",
        result="OK",
        payload={
            "sprint_id": sprint.id,
            "project_id": sprint.project_id,
            "name": sprint.name,
        },
    )


def record_sprint_task_added(
    logger: Any, *, sprint: Any, task_id: str, source: str = "org"
) -> Event | None:
    """任务加入 Sprint (org.sprint.task_added; 任务须先关联项目)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_SPRINT_TASK_ADDED,
        source=source,
        stage="added",
        action="add task to sprint",
        result="OK",
        task_id=task_id,
        payload={"sprint_id": sprint.id, "project_id": sprint.project_id, "task_id": task_id},
    )


def record_stage_created(logger: Any, *, stage: Any, source: str = "org") -> Event | None:
    """Stage 创建 (org.stage.created; 组织级 Workflow 编排壳阶段, S7-005 接执行)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_STAGE_CREATED,
        source=source,
        stage=stage.status.value,
        action="create stage",
        result="OK",
        payload={
            "stage_id": stage.id,
            "workflow_id": stage.workflow_id,
            "role_id": stage.role_id,
            "order": stage.order,
        },
    )


def record_artifact_created(logger: Any, *, artifact: Any, source: str = "org") -> Event | None:
    """阶段产物创建 (org.artifact.created; prd|design|code|test|release)。"""
    if logger is None:
        return None
    return logger.record(
        EventType.ORG_ARTIFACT_CREATED,
        source=source,
        stage=artifact.type.value,
        action="create artifact",
        result="OK",
        payload={
            "artifact_id": artifact.id,
            "stage_id": artifact.stage_id,
            "type": artifact.type.value,
            "ref": artifact.ref,
        },
    )
