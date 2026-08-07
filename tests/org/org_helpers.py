"""tests/org/org_helpers.py — Organization 测试构造/断言 helper (唯一名)。

- make_company / make_department / make_role / make_employee /
  make_authority / make_knowledge: 模型构造工厂 (显式 id, 确定性断言)
- event_types_of / payload_of / event_sequence / last_event:
  事件库断言辅助 (org.* 事件 payload 契约)
- seed_company: 常用组合场景 (software_company 模板 + 员工) — 单函数复用,
  避免各测试文件重复造数
"""

from __future__ import annotations

from typing import Any

from org.models import (
    Authority,
    Company,
    Department,
    Employee,
    EmployeeStatus,
    KnowledgeItem,
    Role,
)

# ------------------------------------------------------------------ 模型工厂


def make_company(
    company_id: str = "C-1",
    name: str = "Acme",
    template: str = "solo",
    knowledge_space: str = "",
) -> Company:
    return Company(
        id=company_id,
        name=name,
        template=template,
        knowledge_space=knowledge_space or company_id,
    )


def make_department(
    department_id: str = "D-1",
    company_id: str = "C-1",
    name: str = "Engineering",
) -> Department:
    return Department(id=department_id, company_id=company_id, name=name)


def make_role(
    role_id: str = "R-1",
    company_id: str = "C-1",
    department_id: str = "",
    name: str = "Developer",
    authority_policy: dict[str, str] | None = None,
    human: bool = False,
) -> Role:
    return Role(
        id=role_id,
        company_id=company_id,
        department_id=department_id,
        name=name,
        authority_policy=authority_policy or {},
        human=human,
    )


def make_employee(
    employee_id: str = "E-1",
    company_id: str = "C-1",
    name: str = "Ada",
    role_ids: list[str] | None = None,
    capabilities: list[str] | None = None,
    status: EmployeeStatus = EmployeeStatus.ACTIVE,
) -> Employee:
    return Employee(
        id=employee_id,
        company_id=company_id,
        name=name,
        role_ids=role_ids or [],
        capabilities=capabilities or [],
        status=status,
    )


def make_authority(
    authority_id: str = "AUTH-1",
    role_id: str = "R-1",
    permission: str = "code.modify",
    effect: str = "allow",
) -> Authority:
    return Authority(
        id=authority_id, role_id=role_id, permission=permission, effect=effect
    )


def make_knowledge(
    knowledge_id: str = "K-1",
    company_id: str = "C-1",
    domain: str = "docs",
    content: str = "coding guidelines",
    version: int = 1,
) -> KnowledgeItem:
    return KnowledgeItem(
        id=knowledge_id,
        company_id=company_id,
        domain=domain,
        content=content,
        version=version,
    )


# ------------------------------------------------------------------ 事件断言


def event_types_of(store: Any) -> list[str]:
    return [e.type.value for e in store.query()]


def payload_of(store: Any, event_type: str) -> dict[str, Any]:
    for e in store.query():
        if e.type.value == event_type:
            return dict(e.payload)
    raise AssertionError(f"no event of type {event_type!r} found")


def event_sequence(store: Any) -> list[str]:
    return [e.type.value for e in store.query()]


def last_event(store: Any) -> Any:
    events = store.query()
    assert events, "expected at least one event"
    return events[-1]
