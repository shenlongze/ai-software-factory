"""factory-org/org/lifecycle.py — OrgLifecycle 组织生命周期编排 (事件驱动)。

设计依据 (ai-company-operating-model.md §1/§2/§3):
- create_company: 模板实例化 (Company + Department + Role + Authority 物化)
- hire/assign/transfer/leave: AI Employee Lifecycle (入职/转岗/离职)
- grant/deny/check_authority: Default Deny 权限模型 (Authority 绑定 Role,
  显式 deny 优先; 高危 release.approve 未声明即拒绝)
- add_knowledge: 企业知识入库 (公司隔离)

事件链 (全部组织变化可审计, 经 factory-core EventLogger):
- create_company:  company.created → department.created ×N → role.created ×N
                    → authority.granted/denied ×M (链序固定, 测试断言)
- hire_employee:   employee.joined → employee.role_assigned
                    → employee.capability_added ×K
- assign/transfer: employee.role_assigned (冲突组合硬拒绝前置)
- leave:           employee.left (权限即刻失效)
- grant/deny:      authority.granted / authority.denied
- check:           authority.checked (越权尝试也审计)

约束 (任务): 禁真实 LLM / Agent 执行 / 自动任务分配 (Phase 17/18) — 本层
只编排组织状态与审计事件, 零执行副作用。
"""

from __future__ import annotations

from typing import Any

from . import events as org_events
from .models import (
    Authority,
    Company,
    Department,
    Employee,
    EmployeeStatus,
    KnowledgeItem,
    Role,
    new_id,
    utcnow,
)
from .registry import EmployeeRegistry
from .store import OrgStore
from .templates import check_role_conflict, get_template


class OrgLifecycleError(Exception):
    """OrgLifecycle 基础异常。"""


class NotFoundError(OrgLifecycleError):
    """实体不存在 (company/department/role/employee/knowledge)。"""


class DuplicateError(OrgLifecycleError):
    """实体 id 重复 (唯一性约束)。"""


class RoleConflictError(OrgLifecycleError):
    """角色冲突组合 (执行权 != 审核权, 注册表硬拒绝)。"""


class CompanyMismatchError(OrgLifecycleError):
    """跨公司引用 (角色/员工所属公司不一致 — 公司隔离铁律)。"""


class OrgLifecycle:
    """组织生命周期编排器: 公司/部门/角色/员工/权限/知识 全生命周期。

    只依赖 OrgStore (持久化) + EventLogger (审计); 不 import factory-core
    业务模块 (Extension 边界, 零 Core 修改)。
    """

    def __init__(self, store: OrgStore, *, logger: Any = None):
        self._store = store
        self._logger = logger
        self._registry = EmployeeRegistry(store)

    @property
    def store(self) -> OrgStore:
        return self._store

    @property
    def registry(self) -> EmployeeRegistry:
        return self._registry

    # ------------------------------------------------------------------ 公司

    def create_company(
        self, name: str, template: str = "solo", *, company_id: str | None = None
    ) -> Company:
        """模板实例化公司 (company.created → department.created ×N →
        role.created ×N → authority.granted/denied ×M)。

        knowledge_space 回填 company_id (公司知识空间 Layer 2 根)。
        """
        tpl = get_template(template)
        company_id = company_id or new_id("C")
        if self._store.get_company(company_id) is not None:
            raise DuplicateError(f"company already exists: {company_id}")
        company = Company(
            id=company_id,
            name=name,
            template=tpl.template_id,
            knowledge_space=company_id,
        )
        # 部门先落库 (company.created payload 需准确 department_count)
        created_departments: list[Department] = []
        dept_ids: dict[str, str] = {}
        for dept_name in tpl.departments:
            dept = Department(id=new_id("D"), company_id=company_id, name=dept_name)
            self._store.save_department(dept)
            company = company.model_copy(
                update={"departments": company.departments + [dept.id]}
            )
            dept_ids[dept_name] = dept.id
            created_departments.append(dept)
        self._store.save_company(company)
        org_events.record_company_created(self._logger, company=company)
        for dept in created_departments:
            org_events.record_department_created(self._logger, department=dept)
        # 角色 + 权限矩阵物化 (role.created → authority.granted/denied)
        for spec in tpl.roles:
            self.create_role(
                company_id,
                dept_ids.get(spec.department, ""),
                spec.name,
                responsibility=spec.responsibility,
                authority_policy=dict(spec.authority_policy),
                human=spec.human,
                role_ref=spec.role_ref,
            )
        return company

    def get_company(self, company_id: str) -> Company:
        """取公司; 不存在 → NotFoundError (CLI show 用)。"""
        company = self._store.get_company(company_id)
        if company is None:
            raise NotFoundError(f"company not found: {company_id}")
        return company

    def list_companies(self) -> list[Company]:
        return self._store.list_companies()

    # ------------------------------------------------------------------ 部门

    def create_department(
        self, company_id: str, name: str, *, department_id: str | None = None
    ) -> Department:
        """创建部门 (department.created); company 必须存在。

        唯一性: id 全库唯一 + 部门名公司内唯一 (模板已物化的部门名不可重复建)。
        """
        if self._store.get_company(company_id) is None:
            raise NotFoundError(f"company not found: {company_id}")
        department_id = department_id or new_id("D")
        if self._store.get_department(department_id) is not None:
            raise DuplicateError(f"department already exists: {department_id}")
        for existing in self._store.list_departments_by_company(company_id):
            if existing.name == name:
                raise DuplicateError(
                    f"department already exists: {name} in company {company_id}"
                )
        dept = Department(id=department_id, company_id=company_id, name=name)
        self._store.save_department(dept)
        org_events.record_department_created(self._logger, department=dept)
        return dept

    # ------------------------------------------------------------------ 角色

    def create_role(
        self,
        company_id: str,
        department_id: str = "",
        name: str = "",
        *,
        responsibility: str = "",
        authority_policy: dict[str, str] | None = None,
        role_id: str | None = None,
        human: bool = False,
        role_ref: str = "",
    ) -> Role:
        """创建职位 (role.created + 权限矩阵物化 authority.granted/denied)。

        department_id="" = company-level (Solo 扁平); 非空须真实存在。
        authority_policy 只接受 allow|deny 值 (非法值 → ValueError)。
        role_ref: 统一角色注册表引用 (S7-001) — exec 注册表 role_id;
        缺省 "" (Human/未接执行角色), 既有调用零影响。
        """
        if self._store.get_company(company_id) is None:
            raise NotFoundError(f"company not found: {company_id}")
        if department_id and self._store.get_department(department_id) is None:
            raise NotFoundError(f"department not found: {department_id}")
        role_id = role_id or new_id("R")
        if self._store.get_role(role_id) is not None:
            raise DuplicateError(f"role already exists: {role_id}")
        policy = dict(authority_policy or {})
        for permission, effect in policy.items():
            if effect not in ("allow", "deny"):
                raise ValueError(
                    f"authority_policy effect must be allow|deny, got {effect!r} "
                    f"for {permission!r}"
                )
        role = Role(
            id=role_id,
            company_id=company_id,
            department_id=department_id,
            name=name,
            responsibility=responsibility,
            authority_policy=policy,
            human=human,
            role_ref=role_ref,
        )
        self._store.save_role(role)
        org_events.record_role_created(self._logger, role=role)
        for permission, effect in policy.items():
            self.grant_authority(role.id, permission, effect=effect)
        return role

    # ------------------------------------------------------------------ 员工

    def resolve_role_ref(self, company_id: str, role_ref: str) -> str:
        """统一角色解析 (S7-001): 角色引用 → 公司内角色 id。

        解析链 (大小写不敏感, 单一注册表 = exec/roles.py 事实源):
          1. 角色 id 精确匹配 (store 全局唯一)
          2. 公司内角色名大小写不敏感匹配 (Developer == developer)
          3. exec 注册表统一解析 (role_id/显示名/别名, 如 "qa"/"tester")
             → 公司内 role_ref 指向该 exec role_id 的角色
        未解析 → NotFoundError (CLI 层映射 rc 7)。

        向后兼容: 既有数据 (无 role_ref 的 Role) 走 1/2 两链, 行为不变;
        3 链为双体系统一新增能力 (org 模板角色经 role_ref 引用注册表)。
        """
        if self._store.get_role(role_ref) is not None:
            return role_ref
        roles = self._store.list_roles_by_company(company_id)
        norm = str(role_ref).strip().lower()
        for role in roles:
            if role.name.strip().lower() == norm:
                return role.id
        # 3) exec 注册表统一解析 → role_ref 匹配
        exec_role_id = self._resolve_exec_role_id(role_ref)
        if exec_role_id is not None:
            for role in roles:
                if role.role_ref == exec_role_id:
                    return role.id
        raise NotFoundError(f"role not found: {role_ref!r}")

    def _resolve_exec_role_id(self, role_ref: str) -> str | None:
        """把角色引用解析为 exec 注册表 role_id (惰性; 未安装 → None)。"""
        try:
            import exec.roles  # type: ignore[import-not-found]

            try:
                return exec.roles.resolve_role(role_ref).role_id
            except exec.roles.RoleError:
                return None
        except ImportError:
            return None

    def hire_employee(
        self,
        company_id: str,
        name: str,
        role_id: str,
        *,
        capabilities: list[str] | None = None,
        employee_id: str | None = None,
    ) -> Employee:
        """员工入职 (employee.joined → role_assigned → capability_added ×K)。

        role 必须属于同一公司 (公司隔离); 入职单一角色 (多角色经 assign_role,
        冲突组合在 assign 时硬拒)。
        """
        if self._store.get_company(company_id) is None:
            raise NotFoundError(f"company not found: {company_id}")
        role = self._store.get_role(role_id)
        if role is None:
            raise NotFoundError(f"role not found: {role_id}")
        if role.company_id != company_id:
            raise CompanyMismatchError(
                f"role {role_id} belongs to company {role.company_id}, "
                f"not {company_id}"
            )
        employee_id = employee_id or new_id("E")
        if self._store.get_employee(employee_id) is not None:
            raise DuplicateError(f"employee already exists: {employee_id}")
        caps = [c for c in (capabilities or []) if c]
        employee = Employee(
            id=employee_id,
            company_id=company_id,
            name=name,
            role_ids=[role_id],
            capabilities=caps,
        )
        self._store.save_employee(employee)
        org_events.record_employee_joined(self._logger, employee=employee)
        org_events.record_employee_role_assigned(
            self._logger, employee=employee, role_id=role_id
        )
        for cap in caps:
            org_events.record_employee_capability_added(
                self._logger, employee=employee, capability=cap
            )
        return employee

    def assign_role(self, employee_id: str, role_id: str) -> Employee:
        """追加角色 (employee.role_assigned; 冲突组合硬拒绝, 跨公司拒绝)。"""
        employee = self._require_active_employee(employee_id)
        role = self._require_role_of_company(role_id, employee.company_id)
        if role_id in employee.role_ids:
            raise DuplicateError(f"role already assigned: {role_id}")
        existing_names = self._role_names(employee.role_ids)
        conflict = check_role_conflict(existing_names, role.name)
        if conflict is not None:
            raise RoleConflictError(conflict)
        new = employee.model_copy(update={"role_ids": employee.role_ids + [role_id]})
        self._store.save_employee(new)
        org_events.record_employee_role_assigned(
            self._logger, employee=new, role_id=role_id
        )
        return new

    def transfer_role(
        self, employee_id: str, old_role_id: str, new_role_id: str
    ) -> Employee:
        """转岗 (移除旧角色 + 追加新角色; 冲突组合按剩余角色集校验)。"""
        employee = self._require_active_employee(employee_id)
        if old_role_id not in employee.role_ids:
            raise NotFoundError(
                f"employee {employee_id} has no role {old_role_id}"
            )
        role = self._require_role_of_company(new_role_id, employee.company_id)
        remaining = [r for r in employee.role_ids if r != old_role_id]
        conflict = check_role_conflict(self._role_names(remaining), role.name)
        if conflict is not None:
            raise RoleConflictError(conflict)
        new = employee.model_copy(
            update={"role_ids": remaining + [new_role_id]}
        )
        self._store.save_employee(new)
        org_events.record_employee_role_assigned(
            self._logger, employee=new, role_id=new_role_id
        )
        return new

    def add_capability(self, employee_id: str, capability: str) -> Employee:
        """能力培训 (employee.capability_added; 不自动提权 — 权限看 Role)。"""
        employee = self._require_active_employee(employee_id)
        if capability in employee.capabilities:
            raise DuplicateError(f"capability already present: {capability}")
        new = employee.model_copy(
            update={"capabilities": employee.capabilities + [capability]}
        )
        self._store.save_employee(new)
        org_events.record_employee_capability_added(
            self._logger, employee=new, capability=capability
        )
        return new

    def leave(self, employee_id: str) -> Employee:
        """离职 (employee.left; 记录保留审计, 权限即刻失效, 幂等)。"""
        employee = self._store.get_employee(employee_id)
        if employee is None:
            raise NotFoundError(f"employee not found: {employee_id}")
        if employee.status == EmployeeStatus.LEFT:
            return employee  # 幂等: 已离职不重复发事件
        new = employee.model_copy(
            update={"status": EmployeeStatus.LEFT, "left_at": utcnow()}
        )
        self._store.save_employee(new)
        org_events.record_employee_left(self._logger, employee=new)
        return new

    # ------------------------------------------------------------------ 权限

    def grant_authority(
        self, role_id: str, permission: str, effect: str = "allow"
    ) -> Authority:
        """授予/更新权限 (authority.granted | authority.denied)。

        同 (role_id, permission) 已有记录 → 先删后建 (last-write-wins,
        事件日志保留完整变更序; deny 记录一旦存在, 校验时优先)。
        """
        if self._store.get_role(role_id) is None:
            raise NotFoundError(f"role not found: {role_id}")
        if effect not in ("allow", "deny"):
            raise ValueError(f"effect must be allow|deny, got {effect!r}")
        for existing in self._store.list_authorities_by_role(role_id):
            if existing.permission == permission:
                self._store.delete_authority(existing.id)
        auth = Authority(
            id=new_id("AUTH"),
            role_id=role_id,
            permission=permission,
            effect=effect,
        )
        self._store.save_authority(auth)
        if effect == "deny":
            org_events.record_authority_denied(self._logger, authority=auth)
        else:
            org_events.record_authority_granted(self._logger, authority=auth)
        return auth

    def deny_authority(self, role_id: str, permission: str) -> Authority:
        """显式拒绝 (authority.denied; deny 优先于任何 allow)。"""
        return self.grant_authority(role_id, permission, effect="deny")

    def check_authority_for_roles(self, role_ids: list[str], permission: str) -> bool:
        """按角色集校验权限 (Default Deny; 显式 deny 优先于 allow)。

        纯函数路径 (不发事件, 供服务层复用); 无记录 → False。
        """
        allowed = False
        for role_id in role_ids:
            for auth in self._store.list_authorities_by_role(role_id):
                if auth.permission != permission:
                    continue
                if auth.effect == "deny":
                    return False
                allowed = True
        return allowed

    def check_authority(self, employee_id: str, permission: str) -> bool:
        """员工权限校验 (authority.checked 审计; 离职员工一律拒绝)。"""
        employee = self._store.get_employee(employee_id)
        if employee is None:
            raise NotFoundError(f"employee not found: {employee_id}")
        if not employee.is_active:
            org_events.record_authority_checked(
                self._logger,
                permission=permission,
                allowed=False,
                role_ids=list(employee.role_ids),
                employee_id=employee_id,
            )
            return False
        allowed = self.check_authority_for_roles(employee.role_ids, permission)
        org_events.record_authority_checked(
            self._logger,
            permission=permission,
            allowed=allowed,
            role_ids=list(employee.role_ids),
            employee_id=employee_id,
        )
        return allowed

    # ------------------------------------------------------------------ 知识

    def add_knowledge(
        self,
        company_id: str,
        domain: str,
        content: str,
        *,
        knowledge_id: str | None = None,
    ) -> KnowledgeItem:
        """知识入库 (knowledge.bound; 公司隔离, 版本化)。"""
        if self._store.get_company(company_id) is None:
            raise NotFoundError(f"company not found: {company_id}")
        knowledge_id = knowledge_id or new_id("K")
        if self._store.get_knowledge(knowledge_id) is not None:
            raise DuplicateError(f"knowledge already exists: {knowledge_id}")
        item = KnowledgeItem(
            id=knowledge_id,
            company_id=company_id,
            domain=domain,
            content=content,
        )
        self._store.save_knowledge(item)
        org_events.record_knowledge_bound(self._logger, item=item)
        return item

    # ------------------------------------------------------------------ 检索 (只推荐不分配)

    def find_employees(
        self,
        *,
        company_id: str | None = None,
        capability: str | None = None,
        role_id: str | None = None,
    ) -> list[Employee]:
        """员工候选人检索 (委托 EmployeeRegistry; 只返回在职, 不自动分配)。"""
        return self._registry.find(
            company_id=company_id, capability=capability, role_id=role_id
        )

    # ------------------------------------------------------------------ 内部辅助

    def _require_active_employee(self, employee_id: str) -> Employee:
        employee = self._store.get_employee(employee_id)
        if employee is None:
            raise NotFoundError(f"employee not found: {employee_id}")
        if not employee.is_active:
            raise NotFoundError(f"employee not active: {employee_id}")
        return employee

    def _require_role_of_company(self, role_id: str, company_id: str) -> Role:
        role = self._store.get_role(role_id)
        if role is None:
            raise NotFoundError(f"role not found: {role_id}")
        if role.company_id != company_id:
            raise CompanyMismatchError(
                f"role {role_id} belongs to company {role.company_id}, "
                f"not {company_id}"
            )
        return role

    def _role_names(self, role_ids: list[str]) -> list[str]:
        names: list[str] = []
        for role_id in role_ids:
            role = self._store.get_role(role_id)
            if role is not None:
                names.append(role.name)
        return names
