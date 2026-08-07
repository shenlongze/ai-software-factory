"""factory-org/org/registry.py — EmployeeRegistry (候选人检索, 不自动分配)。

设计依据 (agent-employee-model.md §4 AI Employee Lifecycle):
```
Business Goal (缺 Java 架构师)
  → CEO/Manager 确认 → HR 流程
  → Search Existing (查 Agent Registry: 已有员工有该能力?)
  → Training / Recruit External → Create Employee → Approval
```

本阶段只做「查」: register_employee (入职落库) + find_by_capability /
find_by_role (候选人列表)。**只推荐不分配** — 自动任务分配属 Phase 18
(禁: 本阶段不产生任何 assignment/execution 副作用)。

检索语义:
- 只返回 ACTIVE 员工 (离职员工权限失效, 不进候选)
- 可选 company_id 过滤 (公司隔离: A 公司找人不串 B 公司)
- 结果按 employee id 排序 (确定性, 审计友好)
"""

from __future__ import annotations

from typing import Any

from .models import Employee
from .store import OrgStore


class EmployeeRegistry:
    """员工注册表: 入职落库 + 能力/角色检索 (只读候选, 不自动分配)。"""

    def __init__(self, store: OrgStore):
        self._store = store

    @property
    def store(self) -> OrgStore:
        return self._store

    # ------------------------------------------------------------------ 写

    def register_employee(self, employee: Employee) -> Employee:
        """入职落库 (upsert; 引用完整性校验在 OrgLifecycle 层)。"""
        self._store.save_employee(employee)
        return employee

    # ------------------------------------------------------------------ 检索

    def _active_candidates(
        self, *, company_id: str | None = None
    ) -> list[Employee]:
        """在职员工列表 (company_id 可选过滤, 按 id 排序)。"""
        employees = self._store.list_employees()
        if company_id is not None:
            employees = [e for e in employees if e.company_id == company_id]
        return [e for e in employees if e.is_active]

    def find_by_capability(
        self, capability: str, *, company_id: str | None = None
    ) -> list[Employee]:
        """按能力找候选人 (Capability 多技能集成员匹配, 大小写敏感精确匹配)。

        返回在职员工; 找不到 → [] (HR 流程据此决定培训/外部招聘, 不自动补)。
        """
        return [
            e
            for e in self._active_candidates(company_id=company_id)
            if capability in e.capabilities
        ]

    def find_by_role(
        self, role_id: str, *, company_id: str | None = None
    ) -> list[Employee]:
        """按职位找候选人 (role_ids 成员匹配; Role ≠ Capability)。"""
        return [
            e
            for e in self._active_candidates(company_id=company_id)
            if role_id in e.role_ids
        ]

    def find(
        self,
        *,
        company_id: str | None = None,
        role_id: str | None = None,
        capability: str | None = None,
    ) -> list[Employee]:
        """组合检索 (全部条件 AND; 空字符串/None 过滤 = 无过滤 → 全部在职员工)。"""
        employees = self._active_candidates(company_id=company_id)
        if role_id is not None:
            employees = [e for e in employees if role_id in e.role_ids]
        if capability:
            employees = [e for e in employees if capability in e.capabilities]
        return employees

    def candidates_for(self, requirement: Any) -> list[Employee]:
        """能力需求 → 候选列表 (duck-typed requirement.required_capabilities)。

        只推荐不分配: 返回候选不产生任何执行副作用 (Phase 18 才自动派发)。
        """
        caps = list(getattr(requirement, "required_capabilities", None) or [])
        employees = self._active_candidates()
        return [e for e in employees if all(c in e.capabilities for c in caps)]
