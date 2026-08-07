"""tests/org/test_org_store.py — OrgStore 持久化 (Phase 16A, ADR-0036)。

覆盖: 六实体子库 CRUD (save/get/list/count/delete) / 按公司过滤查询 /
文件布局 (companies.json 等六文件) / 首次写入自动建目录 / 幂等删除 /
round-trip 字段保留 / OrgLifecycle 跨子库协同 (company 引用部门)。
"""

from __future__ import annotations

import pytest

from org.models import Company, Department, Employee, KnowledgeItem, Role
from org.store import OrgStore

from org_helpers import (
    make_authority,
    make_company,
    make_department,
    make_employee,
    make_knowledge,
    make_role,
)


class TestCompanyStore:
    def test_save_get(self, org_store: OrgStore):
        org_store.save_company(make_company())
        got = org_store.get_company("C-1")
        assert got is not None
        assert got.id == "C-1"
        assert got.name == "Acme"

    def test_get_missing_returns_none(self, org_store: OrgStore):
        assert org_store.get_company("nope") is None

    def test_list_sorted_by_id(self, org_store: OrgStore):
        org_store.save_company(make_company(company_id="C-2"))
        org_store.save_company(make_company(company_id="C-1"))
        ids = [c.id for c in org_store.list_companies()]
        assert ids == ["C-1", "C-2"]

    def test_count(self, org_store: OrgStore):
        org_store.save_company(make_company(company_id="C-1"))
        org_store.save_company(make_company(company_id="C-2"))
        assert org_store.count_companies() == 2

    def test_upsert_same_id_overwrites(self, org_store: OrgStore):
        org_store.save_company(make_company(name="Old"))
        org_store.save_company(make_company(name="New"))
        assert org_store.count_companies() == 1
        assert org_store.get_company("C-1").name == "New"

    def test_round_trip_preserves_fields(self, org_store: OrgStore):
        org_store.save_company(make_company(template="software_company"))
        got = org_store.get_company("C-1")
        assert got.template == "software_company"
        assert got.knowledge_space == "C-1"


class TestDepartmentStore:
    def test_crud(self, org_store: OrgStore):
        org_store.save_department(make_department())
        assert org_store.get_department("D-1").name == "Engineering"
        assert len(org_store.list_departments()) == 1

    def test_list_by_company(self, org_store: OrgStore):
        org_store.save_department(make_department(department_id="D-1", company_id="C-1"))
        org_store.save_department(make_department(department_id="D-2", company_id="C-2"))
        org_store.save_department(make_department(department_id="D-3", company_id="C-1"))
        result = org_store.list_departments_by_company("C-1")
        assert [d.id for d in result] == ["D-1", "D-3"]


class TestRoleStore:
    def test_crud(self, org_store: OrgStore):
        org_store.save_role(make_role())
        assert org_store.get_role("R-1").name == "Developer"
        assert len(org_store.list_roles()) == 1

    def test_list_by_company(self, org_store: OrgStore):
        org_store.save_role(make_role(role_id="R-1", company_id="C-1"))
        org_store.save_role(make_role(role_id="R-2", company_id="C-2"))
        assert [r.id for r in org_store.list_roles_by_company("C-1")] == ["R-1"]

    def test_list_by_department(self, org_store: OrgStore):
        org_store.save_role(make_role(role_id="R-1", department_id="D-1"))
        org_store.save_role(make_role(role_id="R-2", department_id=""))
        assert [r.id for r in org_store.list_roles_by_department("D-1")] == ["R-1"]

    def test_authority_policy_round_trip(self, org_store: OrgStore):
        org_store.save_role(make_role(authority_policy={"code.modify": "allow"}))
        assert org_store.get_role("R-1").authority_policy == {"code.modify": "allow"}


class TestEmployeeStore:
    def test_crud(self, org_store: OrgStore):
        org_store.save_employee(make_employee(capabilities=["python"]))
        got = org_store.get_employee("E-1")
        assert got.capabilities == ["python"]
        assert len(org_store.list_employees()) == 1

    def test_list_by_company(self, org_store: OrgStore):
        org_store.save_employee(make_employee(employee_id="E-1", company_id="C-1"))
        org_store.save_employee(make_employee(employee_id="E-2", company_id="C-2"))
        assert [e.id for e in org_store.list_employees_by_company("C-1")] == ["E-1"]

    def test_status_round_trip(self, org_store: OrgStore):
        from org.models import EmployeeStatus

        org_store.save_employee(make_employee(status=EmployeeStatus.LEFT))
        assert org_store.get_employee("E-1").status == EmployeeStatus.LEFT


class TestAuthorityStore:
    def test_crud(self, org_store: OrgStore):
        org_store.save_authority(make_authority())
        assert org_store.get_authority("AUTH-1").permission == "code.modify"
        assert len(org_store.list_authorities()) == 1

    def test_list_by_role(self, org_store: OrgStore):
        org_store.save_authority(make_authority(authority_id="A1", role_id="R-1"))
        org_store.save_authority(make_authority(authority_id="A2", role_id="R-2"))
        assert [a.id for a in org_store.list_authorities_by_role("R-1")] == ["A1"]

    def test_delete(self, org_store: OrgStore):
        org_store.save_authority(make_authority())
        assert org_store.delete_authority("AUTH-1") is True
        assert org_store.get_authority("AUTH-1") is None
        assert org_store.delete_authority("AUTH-1") is False  # 幂等


class TestKnowledgeStore:
    def test_crud(self, org_store: OrgStore):
        org_store.save_knowledge(make_knowledge())
        got = org_store.get_knowledge("K-1")
        assert got.content == "coding guidelines"
        assert len(org_store.list_knowledge()) == 1

    def test_list_by_company(self, org_store: OrgStore):
        org_store.save_knowledge(make_knowledge(knowledge_id="K-1", company_id="C-1"))
        org_store.save_knowledge(make_knowledge(knowledge_id="K-2", company_id="C-2"))
        org_store.save_knowledge(make_knowledge(knowledge_id="K-3", company_id="C-1"))
        result = org_store.list_knowledge_by_company("C-1")
        assert [k.id for k in result] == ["K-1", "K-3"]

    def test_version_round_trip(self, org_store: OrgStore):
        org_store.save_knowledge(make_knowledge(version=3))
        assert org_store.get_knowledge("K-1").version == 3


class TestOrgStoreDataSpace:
    def test_dir_created_on_first_write(self, org_dir):
        assert not org_dir.exists()  # 目录由首次原子写创建
        store = OrgStore(org_dir)
        store.save_company(make_company())
        assert org_dir.exists()
        assert (org_dir / "companies.json").exists()

    def test_six_data_files(self, org_store: OrgStore):
        for rec in (
            make_company(),
            make_department(),
            make_role(),
            make_employee(),
            make_authority(),
            make_knowledge(),
        ):
            cls = type(rec)
            if cls is Company:
                org_store.save_company(rec)
            elif cls is Department:
                org_store.save_department(rec)
            elif cls is Role:
                org_store.save_role(rec)
            elif cls is Employee:
                org_store.save_employee(rec)
            elif cls is KnowledgeItem:
                org_store.save_knowledge(rec)
            else:
                org_store.save_authority(rec)
        files = {p.name for p in org_store.files()}
        assert files == {
            "companies.json",
            "departments.json",
            "roles.json",
            "employees.json",
            "authorities.json",
            "knowledge.json",
        }

    def test_empty_store_files_empty(self, org_dir):
        assert OrgStore(org_dir).files() == []

    def test_missing_file_is_empty_store(self, org_dir):
        store = OrgStore(org_dir)
        assert store.list_companies() == []
        assert store.count_companies() == 0
        assert store.get_company("C-1") is None

    def test_company_department_cross_store(self, org_store: OrgStore):
        """OrgLifecycle 协同: 公司创建时部门引用回填 (跨子库一致性)。

        部门 id 为随机 uuid (new_id), list_departments_by_company 按 id 排序
        — 与模板声明顺序无关; 一致性断言看 id 集合与部门名集合, 不看顺序。
        """
        from org.lifecycle import OrgLifecycle

        company = OrgLifecycle(org_store).create_company(
            "Acme", template="software_company", company_id="C-1"
        )
        assert company.departments  # 部门 id 已回填
        depts = org_store.list_departments_by_company("C-1")
        assert {d.id for d in depts} == set(company.departments)
        assert {d.name for d in depts} == {"Product", "Engineering", "Quality"}
        assert [d.company_id for d in depts] == ["C-1"] * 3
