"""tests/s7/s7_helpers.py — S7-001 统一生命周期测试构造/断言 helper (唯一名)。

- event_sequence / payload_of / last_event: 事件库断言辅助 (org.project.* /
  org.sprint.* / org.stage.* / org.artifact.* payload 契约)
- make_project / make_sprint: 模型构造工厂 (显式 id, 确定性断言)
"""

from __future__ import annotations

from typing import Any

from org.projects import Artifact, Project, ProjectTaskLink, Sprint, Stage


def make_project(
    project_id: str = "P-1",
    name: str = "Build App",
    user_id: str = "",
    goal: str = "",
    lifecycle: str = "idea",
) -> Project:
    return Project(id=project_id, name=name, user_id=user_id, goal=goal, lifecycle=lifecycle)


def make_sprint(
    sprint_id: str = "S-1",
    project_id: str = "P-1",
    name: str = "Sprint 1",
    tasks: list[str] | None = None,
) -> Sprint:
    return Sprint(id=sprint_id, project_id=project_id, name=name, tasks=tasks or [])


def make_stage(
    stage_id: str = "STG-1",
    workflow_id: str = "WF-1",
    role_id: str = "developer",
    order: int = 1,
) -> Stage:
    return Stage(id=stage_id, workflow_id=workflow_id, role_id=role_id, order=order)


def make_artifact(
    artifact_id: str = "A-1",
    stage_id: str = "STG-1",
    type_: str = "prd",
    ref: str = "",
) -> Artifact:
    return Artifact(id=artifact_id, stage_id=stage_id, type=type_, ref=ref)


def make_artifact_full(
    artifact_id: str = "A-1",
    stage_id: str = "STG-1",
    type_: str = "prd",
    *,
    project_id: str = "",
    task_id: str = "",
    ref: str = "",
    producer_role: str = "",
    producer_agent: str = "",
    version: str = "1",
    status: str = "created",
    location: str = "",
    metadata: dict[str, Any] | None = None,
) -> Artifact:
    """S7-002 完整模型构造工厂 (显式 id, 确定性断言)。"""
    return Artifact(
        id=artifact_id,
        stage_id=stage_id,
        type=type_,
        ref=ref,
        project_id=project_id,
        task_id=task_id,
        producer_role=producer_role,
        producer_agent=producer_agent,
        version=version,
        status=status,
        location=location,
        metadata=metadata or {},
    )


def seed_stage(
    plife: Any,
    *,
    stage_id: str = "STG-1",
    workflow_id: str = "WF-1",
    role_id: str = "developer",
    order: int = 1,
) -> Any:
    """创建 Stage (经 ProjectLifecycle, role 经 exec 注册表校验)。"""
    return plife.create_stage(workflow_id, role_id, order=order, stage_id=stage_id)


def seed_project_chain(
    plife: Any,
    *,
    project_id: str = "P-1",
    task_id: str = "T-1",
    stage_id: str = "STG-1",
) -> None:
    """最小关联链: project → link task → stage (产物关联校验前置条件)。"""
    plife.create_project("Build App", project_id=project_id)
    plife.link_task(project_id, task_id)
    plife.create_stage("WF-1", "developer", stage_id=stage_id)


def make_task_link(
    link_id: str = "PTL-1",
    project_id: str = "P-1",
    task_id: str = "T-1",
) -> ProjectTaskLink:
    return ProjectTaskLink(id=link_id, project_id=project_id, task_id=task_id)


# ------------------------------------------------------------------ 事件断言


def event_sequence(store: Any) -> list[str]:
    return [e.type.value for e in store.query()]


def payload_of(store: Any, event_type: str) -> dict[str, Any]:
    for e in store.query():
        if e.type.value == event_type:
            return dict(e.payload)
    raise AssertionError(f"no event of type {event_type!r} found")


def last_event(store: Any) -> Any:
    events = store.query()
    assert events, "expected at least one event"
    return events[-1]
