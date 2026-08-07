"""tests/org/test_org_lifecycle.py — OrgLifecycle 生命周期编排 (Phase 16A, ADR-0036)。

覆盖 (任务清单: lifecycle 入职/转岗/离职 + event 链序):
- create_company: 模板物化 (部门/角色/权限矩阵落库), 唯一性, 未知模板,
  knowledge_space 回填, Solo 扁平
- hire_employee: 入职 (joined → role_assigned → capability_added 事件链),
  跨公司角色硬拒 (CompanyMismatchError), 唯一性
- assign_role: 追加角色 (冲突组合硬拒 / 跨公司拒绝 / 重复拒绝)
- transfer_role: 转岗 (旧角色移除 + 新角色追加, 剩余角色集冲突校验)
- add_capability: 能力培训 (重复拒绝; 不自动提权 — 权限只看 Role)
- leave: 离职 (left 状态 + left_at, 幂等, 权限即刻失效, 记录保留审计)
- 事件链序: create_company 链 (company.created → department.created ×N →
  role.created → authority.granted ×M, 顺序固定可审计)

约束: 禁真实 LLM / Agent 执行 / 自动任务分配 — 本层只编排组织状态与事件。
"""

from __future__ import annotations

import pytest

from org.lifecycle import (
    CompanyMismatchError,
    DuplicateError,
    NotFoundError,
    OrgLifecycle,
    RoleConflictError,
)
from org.models import EmployeeStatus
from org.store import OrgStore

from org_helpers import (
    event_sequence,
    last_event,
    make_employee,
    make_role,
    payload_of,
)


@pytest.fixture
def lifecycle(org_store: OrgStore, logger) -> OrgLifecycle:
    return OrgLifecycle(org_store, logger=logger)


def _software_company(lifecycle: OrgLifecycle) -> str:
    return lifecycle.create_company(
        "Acme", template="software_company", company_id="C-1"
    ).id


class TestCreateCompany:
    def test_software_company_materializes_departments(self, lifecycle, org_store):
        company_id = _software_company(lifecycle)
        depts = org_store.list_departments_by_company(company_id)
        assert {d.name for d in depts} == {"Product", "Engineering", "Quality"}
        assert all(d.company_id == company_id for d in depts)

    def test_software_company_materializes_roles(self, lifecycle, org_store):
        company_id = _software_company(lifecycle)
        roles = org_store.list_roles_by_company(company_id)
        assert {r.name for r in roles} == {
            "CEO", "Product Manager", "Architect", "Developer", "QA",
        }
        assert all(r.company_id == company_id for r in roles)

    def test_company_knowledge_space_backfilled(self, lifecycle, org_store):
        company_id = _software_company(lifecycle)
        company = org_store.get_company(company_id)
        assert company.knowledge_space == company_id

    def test_company_departments_ref_backfilled(self, lifecycle, org_store):
        company_id = _software_company(lifecycle)
        company = org_store.get_company(company_id)
        dept_ids = {d.id for d in org_store.list_departments_by_company(company_id)}
        assert set(company.departments) == dept_ids

    def test_duplicate_company_id_raises(self, lifecycle):
        _software_company(lifecycle)
        with pytest.raises(DuplicateError):
            lifecycle.create_company(
                "Acme 2", template="solo", company_id="C-1"
            )

    def test_unknown_template_raises(self, lifecycle):
        with pytest.raises(Exception) as exc_info:
            lifecycle.create_company("Acme", template="no_such_template")
        assert "unknown company template" in str(exc_info.value)

    def test_solo_template_flat(self, lifecycle, org_store):
        company_id = lifecycle.create_company(
            "Solo Inc", template="solo", company_id="C-9"
        ).id
        assert org_store.list_departments_by_company(company_id) == []
        roles = org_store.list_roles_by_company(company_id)
        assert {r.name for r in roles} == {
            "CEO", "Product Manager", "Architect", "Developer", "QA",
        }
        assert all(r.department_id == "" for r in roles)  # company-level 扁平

    def test_auto_company_id_generated(self, lifecycle, org_store):
        company = lifecycle.create_company("Auto", template="solo")
        assert company.id.startswith("C-")
        assert org_store.get_company(company.id) is not None


class TestHireEmployee:
    def test_hire_basic(self, lifecycle, org_store):
        company_id = _software_company(lifecycle)
        role = org_store.list_roles_by_company(company_id)[0]
        employee = lifecycle.hire_employee(
            company_id, "Ada", role.id, capabilities=["python", "sql"],
            employee_id="E-1",
        )
        assert employee.id == "E-1"
        assert employee.company_id == company_id
        assert employee.role_ids == [role.id]
        assert employee.capabilities == ["python", "sql"]
        assert employee.is_active
        assert org_store.get_employee("E-1") is not None

    def test_hire_emits_event_chain(self, lifecycle, event_store):
        company_id = _software_company(lifecycle)
        role = lifecycle.store.list_roles_by_company(company_id)[0]
        lifecycle.hire_employee(
            company_id, "Ada", role.id, capabilities=["python", "java"],
            employee_id="E-1",
        )
        seq = event_sequence(event_store)
        assert seq[0] == "org.company.created"  # 公司事件在前
        assert seq[-4:] == [
            "org.employee.joined",
            "org.employee.role_assigned",
            "org.employee.capability_added",
            "org.employee.capability_added",
        ]
        # capability_added ×2 (python, java) — 链尾各能力一条
        assert seq.count("org.employee.capability_added") == 2
        joined = payload_of(event_store, "org.employee.joined")
        assert joined["employee_id"] == "E-1"
        assert joined["capability_count"] == 2
        assert joined["role_count"] == 1

    def test_hire_unknown_company_raises(self, lifecycle):
        with pytest.raises(NotFoundError):
            lifecycle.hire_employee("nope", "Ada", "R-1")

    def test_hire_unknown_role_raises(self, lifecycle):
        _software_company(lifecycle)
        with pytest.raises(NotFoundError):
            lifecycle.hire_employee("C-1", "Ada", "R-999")

    def test_hire_cross_company_role_raises(self, lifecycle, org_store):
        c1 = _software_company(lifecycle)
        c2 = lifecycle.create_company("Beta", template="solo", company_id="C-2")
        role_b = org_store.list_roles_by_company(c2.id)[0]
        with pytest.raises(CompanyMismatchError):
            lifecycle.hire_employee(c1, "Ada", role_b.id)

    def test_hire_duplicate_employee_id_raises(self, lifecycle, org_store):
        company_id = _software_company(lifecycle)
        role = org_store.list_roles_by_company(company_id)[0]
        lifecycle.hire_employee(company_id, "Ada", role.id, employee_id="E-1")
        with pytest.raises(DuplicateError):
            lifecycle.hire_employee(company_id, "Bob", role.id, employee_id="E-1")


class TestAssignRole:
    def test_assign_appends_role(self, lifecycle, org_store):
        company_id = _software_company(lifecycle)
        developer = next(r for r in org_store.list_roles_by_company(company_id)
                         if r.name == "Developer")
        architect = next(r for r in org_store.list_roles_by_company(company_id)
                         if r.name == "Architect")
        lifecycle.hire_employee(company_id, "Ada", developer.id, employee_id="E-1")
        updated = lifecycle.assign_role("E-1", architect.id)
        assert updated.role_ids == [developer.id, architect.id]

    def test_assign_emits_role_assigned(self, lifecycle, event_store, org_store):
        company_id = _software_company(lifecycle)
        developer = next(r for r in org_store.list_roles_by_company(company_id)
                         if r.name == "Developer")
        architect = next(r for r in org_store.list_roles_by_company(company_id)
                         if r.name == "Architect")
        lifecycle.hire_employee(company_id, "Ada", developer.id, employee_id="E-1")
        lifecycle.assign_role("E-1", architect.id)
        ev = last_event(event_store)
        assert ev.type.value == "org.employee.role_assigned"
        assert ev.payload["role_id"] == architect.id
        assert ev.payload["employee_id"] == "E-1"

    def test_assign_duplicate_role_raises(self, lifecycle, org_store):
        company_id = _software_company(lifecycle)
        developer = next(r for r in org_store.list_roles_by_company(company_id)
                         if r.name == "Developer")
        lifecycle.hire_employee(company_id, "Ada", developer.id, employee_id="E-1")
        with pytest.raises(DuplicateError):
            lifecycle.assign_role("E-1", developer.id)

    def test_assign_role_conflict_raises(self, lifecycle, org_store):
        """Developer + QA 冲突组合 (执行权 != 审核权) — 注册表硬拒绝。"""
        company_id = _software_company(lifecycle)
        developer = next(r for r in org_store.list_roles_by_company(company_id)
                         if r.name == "Developer")
        qa = next(r for r in org_store.list_roles_by_company(company_id)
                  if r.name == "QA")
        lifecycle.hire_employee(company_id, "Ada", developer.id, employee_id="E-1")
        with pytest.raises(RoleConflictError) as exc_info:
            lifecycle.assign_role("E-1", qa.id)
        assert "冲突" in str(exc_info.value)

    def test_assign_cross_company_raises(self, lifecycle, org_store):
        c1 = _software_company(lifecycle)
        c2 = lifecycle.create_company("Beta", template="solo", company_id="C-2")
        role_a = org_store.list_roles_by_company(c1)[0]
        role_b = org_store.list_roles_by_company(c2.id)[0]
        lifecycle.hire_employee(c1, "Ada", role_a.id, employee_id="E-1")
        with pytest.raises(CompanyMismatchError):
            lifecycle.assign_role("E-1", role_b.id)


class TestTransferRole:
    def test_transfer_swaps_roles(self, lifecycle, org_store):
        company_id = _software_company(lifecycle)
        developer = next(r for r in org_store.list_roles_by_company(company_id)
                         if r.name == "Developer")
        qa = next(r for r in org_store.list_roles_by_company(company_id)
                  if r.name == "QA")
        lifecycle.hire_employee(company_id, "Ada", developer.id, employee_id="E-1")
        # Developer → QA 转岗: 旧角色移除后剩余集为空, 无冲突
        updated = lifecycle.transfer_role("E-1", developer.id, qa.id)
        assert updated.role_ids == [qa.id]

    def test_transfer_missing_old_role_raises(self, lifecycle, org_store):
        company_id = _software_company(lifecycle)
        developer = next(r for r in org_store.list_roles_by_company(company_id)
                         if r.name == "Developer")
        qa = next(r for r in org_store.list_roles_by_company(company_id)
                  if r.name == "QA")
        lifecycle.hire_employee(company_id, "Ada", developer.id, employee_id="E-1")
        with pytest.raises(NotFoundError):
            lifecycle.transfer_role("E-1", qa.id, qa.id)

    def test_transfer_conflict_raises(self, lifecycle, org_store):
        """转岗校验剩余角色集: 移除旧角色后, 剩余集 + 新角色冲突 → 硬拒绝。

        Developer+Architect 并存不冲突 (执行权集内部); 转岗 Architect→QA 后
        剩余 [Developer] + 追加 QA = 执行权+审核权冲突 (冲突组合顺序无关)。
        """
        company_id = _software_company(lifecycle)
        developer = next(r for r in org_store.list_roles_by_company(company_id)
                         if r.name == "Developer")
        qa = next(r for r in org_store.list_roles_by_company(company_id)
                  if r.name == "QA")
        architect = next(r for r in org_store.list_roles_by_company(company_id)
                         if r.name == "Architect")
        lifecycle.hire_employee(company_id, "Ada", developer.id, employee_id="E-1")
        lifecycle.assign_role("E-1", architect.id)
        with pytest.raises(RoleConflictError):
            lifecycle.transfer_role("E-1", architect.id, qa.id)

    def test_transfer_emits_role_assigned(self, lifecycle, event_store, org_store):
        company_id = _software_company(lifecycle)
        developer = next(r for r in org_store.list_roles_by_company(company_id)
                         if r.name == "Developer")
        architect = next(r for r in org_store.list_roles_by_company(company_id)
                         if r.name == "Architect")
        lifecycle.hire_employee(company_id, "Ada", developer.id, employee_id="E-1")
        lifecycle.transfer_role("E-1", developer.id, architect.id)
        ev = last_event(event_store)
        assert ev.type.value == "org.employee.role_assigned"
        assert ev.payload["role_id"] == architect.id


class TestAddCapability:
    def test_add_capability_appends_and_emits(self, lifecycle, event_store, org_store):
        company_id = _software_company(lifecycle)
        developer = next(r for r in org_store.list_roles_by_company(company_id)
                         if r.name == "Developer")
        lifecycle.hire_employee(company_id, "Ada", developer.id, employee_id="E-1")
        updated = lifecycle.add_capability("E-1", "rust")
        assert updated.capabilities == ["rust"]
        ev = last_event(event_store)
        assert ev.type.value == "org.employee.capability_added"
        assert ev.payload["capability"] == "rust"

    def test_add_capability_duplicate_raises(self, lifecycle, org_store):
        company_id = _software_company(lifecycle)
        developer = next(r for r in org_store.list_roles_by_company(company_id)
                         if r.name == "Developer")
        lifecycle.hire_employee(
            company_id, "Ada", developer.id, capabilities=["python"],
            employee_id="E-1",
        )
        with pytest.raises(DuplicateError):
            lifecycle.add_capability("E-1", "python")

    def test_add_capability_does_not_grant_authority(self, lifecycle, org_store):
        """能力培训不自动提权 (权限看 Role, Capability ≠ Authority)。"""
        company_id = _software_company(lifecycle)
        developer = next(r for r in org_store.list_roles_by_company(company_id)
                         if r.name == "Developer")
        lifecycle.hire_employee(company_id, "Ada", developer.id, employee_id="E-1")
        lifecycle.add_capability("E-1", "release.ship")
        assert lifecycle.check_authority("E-1", "release.ship") is False


class TestLeave:
    def test_leave_marks_left(self, lifecycle, org_store):
        company_id = _software_company(lifecycle)
        developer = next(r for r in org_store.list_roles_by_company(company_id)
                         if r.name == "Developer")
        lifecycle.hire_employee(company_id, "Ada", developer.id, employee_id="E-1")
        employee = lifecycle.leave("E-1")
        assert employee.status == EmployeeStatus.LEFT
        assert employee.left_at is not None
        saved = org_store.get_employee("E-1")  # 记录保留审计 (不物理删除)
        assert saved is not None
        assert saved.status == EmployeeStatus.LEFT

    def test_leave_emits_left_event(self, lifecycle, event_store, org_store):
        company_id = _software_company(lifecycle)
        developer = next(r for r in org_store.list_roles_by_company(company_id)
                         if r.name == "Developer")
        lifecycle.hire_employee(company_id, "Ada", developer.id, employee_id="E-1")
        lifecycle.leave("E-1")
        ev = last_event(event_store)
        assert ev.type.value == "org.employee.left"
        assert ev.payload["employee_id"] == "E-1"
        assert ev.payload["name"] == "Ada"

    def test_leave_idempotent_no_new_event(self, lifecycle, event_store, org_store):
        company_id = _software_company(lifecycle)
        developer = next(r for r in org_store.list_roles_by_company(company_id)
                         if r.name == "Developer")
        lifecycle.hire_employee(company_id, "Ada", developer.id, employee_id="E-1")
        lifecycle.leave("E-1")
        before = len(event_sequence(event_store))
        lifecycle.leave("E-1")  # 幂等: 已离职不重复发事件
        assert len(event_sequence(event_store)) == before

    def test_leave_revokes_authority_immediately(self, lifecycle, org_store):
        """离职员工权限即刻失效 (即使 role 仍允许该权限)。"""
        company_id = _software_company(lifecycle)
        ceo = next(r for r in org_store.list_roles_by_company(company_id)
                   if r.name == "CEO")
        lifecycle.hire_employee(company_id, "Boss", ceo.id, employee_id="E-1")
        assert lifecycle.check_authority("E-1", "release.approve") is True
        lifecycle.leave("E-1")
        assert lifecycle.check_authority("E-1", "release.approve") is False

    def test_leave_then_assign_raises(self, lifecycle, org_store):
        company_id = _software_company(lifecycle)
        developer = next(r for r in org_store.list_roles_by_company(company_id)
                         if r.name == "Developer")
        architect = next(r for r in org_store.list_roles_by_company(company_id)
                         if r.name == "Architect")
        lifecycle.hire_employee(company_id, "Ada", developer.id, employee_id="E-1")
        lifecycle.leave("E-1")
        with pytest.raises(NotFoundError):
            lifecycle.assign_role("E-1", architect.id)

    def test_leave_unknown_employee_raises(self, lifecycle):
        with pytest.raises(NotFoundError):
            lifecycle.leave("E-999")


class TestDepartmentRoleLifecycle:
    def test_create_department_unknown_company_raises(self, lifecycle):
        with pytest.raises(NotFoundError):
            lifecycle.create_department("C-999", "Ops")

    def test_create_department_duplicate_raises(self, lifecycle, org_store):
        company_id = _software_company(lifecycle)
        with pytest.raises(DuplicateError):
            lifecycle.create_department(
                company_id, "Engineering", department_id="D-1"
            )
        lifecycle.create_department(company_id, "Ops", department_id="D-99")
        with pytest.raises(DuplicateError):
            lifecycle.create_department(company_id, "Ops2", department_id="D-99")

    def test_create_role_unknown_company_raises(self, lifecycle):
        with pytest.raises(NotFoundError):
            lifecycle.create_role("C-999", "", "SRE")

    def test_create_role_unknown_department_raises(self, lifecycle):
        _software_company(lifecycle)
        with pytest.raises(NotFoundError):
            lifecycle.create_role("C-1", "D-999", "SRE")

    def test_create_role_invalid_effect_raises(self, lifecycle):
        _software_company(lifecycle)
        with pytest.raises(ValueError):
            lifecycle.create_role(
                "C-1", "", "SRE",
                authority_policy={"code.modify": "maybe"},
            )

    def test_create_role_materializes_authority(self, lifecycle, org_store):
        company_id = _software_company(lifecycle)
        role = lifecycle.create_role(
            "C-1", "", "SRE",
            authority_policy={"deploy.run": "allow", "prod.access": "deny"},
            role_id="R-99",
        )
        assert role.authority_policy == {"deploy.run": "allow", "prod.access": "deny"}
        auths = org_store.list_authorities_by_role("R-99")
        assert {a.permission: a.effect for a in auths} == {
            "deploy.run": "allow",
            "prod.access": "deny",
        }


class TestCreateCompanyEventChain:
    """create_company 事件链序 (company.created → department.created ×3 →
    role.created → authority.granted ×M 交错, 顺序固定可审计)。"""

    @staticmethod
    def _chain_counts(event_store) -> tuple[int, int, int, int]:
        seq = event_sequence(event_store)
        return (
            seq.count("org.company.created"),
            seq.count("org.department.created"),
            seq.count("org.role.created"),
            seq.count("org.authority.granted"),
        )

    def test_chain_starts_with_company_created(self, lifecycle, event_store):
        _software_company(lifecycle)
        seq = event_sequence(event_store)
        assert seq[0] == "org.company.created"
        # 部门事件紧跟公司事件 (department.created ×3)
        assert seq[1:4] == ["org.department.created"] * 3

    def test_chain_counts_match_template(self, lifecycle, event_store):
        """software_company: 1 company + 3 departments + 5 roles +
        9 authority (CEO 3 + PM 2 + Architect 1 + Developer 1 + QA 2)。"""
        _software_company(lifecycle)
        company_n, dept_n, role_n, auth_n = self._chain_counts(event_store)
        assert (company_n, dept_n, role_n, auth_n) == (1, 3, 5, 9)

    def test_each_role_created_followed_by_its_authorities(
        self, lifecycle, event_store
    ):
        """每个 role.created 之后紧跟该角色的权限物化事件 (authority_count
        payload 与后续 granted 条数一致) — 链序不变式。"""
        import org.templates as tpl

        _software_company(lifecycle)
        seq = event_sequence(event_store)
        # create_company 按模板声明顺序创建角色; 角色事件位于
        # company.created(1) + department.created(3) 之后
        names = [r.name for r in tpl.SOFTWARE_COMPANY.roles]
        expected = {r.name: len(r.authority_policy) for r in tpl.SOFTWARE_COMPANY.roles}
        role_created_idx = [
            i for i, t in enumerate(seq) if t == "org.role.created"
        ]
        assert [i for i, _ in enumerate(role_created_idx)] == list(range(len(names)))
        for offset, idx in enumerate(role_created_idx):
            n = expected[names[offset]]
            assert seq[idx + 1: idx + 1 + n] == ["org.authority.granted"] * n

    def test_company_created_payload(self, lifecycle, event_store):
        company_id = _software_company(lifecycle)
        payload = payload_of(event_store, "org.company.created")
        assert payload["company_id"] == company_id
        assert payload["name"] == "Acme"
        assert payload["template"] == "software_company"
        assert payload["department_count"] == 3

    def test_role_created_payload_authority_count(self, lifecycle, event_store):
        _software_company(lifecycle)
        payload = payload_of(event_store, "org.role.created")
        assert payload["company_id"] == "C-1"
        assert "authority_count" in payload
