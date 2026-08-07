"""tests/org/test_org_registry.py — EmployeeRegistry 候选人检索 (Phase 16A, ADR-0036)。

覆盖 (任务清单: registry find_by_capability/role, 只推荐不分配):
- find_by_capability: 能力精确匹配, 只返回在职员工
- find_by_role: 按职位找候选 (Role ≠ Capability)
- 公司隔离: A 公司检索不串 B 公司员工
- 只推荐不分配: 检索零副作用 (不发事件 / 不改任何库)
- find 组合条件 AND; 无过滤 → 全部在职
- candidates_for: duck-typed requirement 能力需求
- 离职员工不进候选; register_employee upsert
"""

from __future__ import annotations

import pytest

from org.lifecycle import OrgLifecycle
from org.models import EmployeeStatus
from org.registry import EmployeeRegistry
from org.store import OrgStore

from org_helpers import event_sequence, make_employee


@pytest.fixture
def registry(org_store: OrgStore) -> EmployeeRegistry:
    return EmployeeRegistry(org_store)


def _seed_two_companies(registry: EmployeeRegistry) -> tuple[str, str]:
    """A 公司 (python 员工) + B 公司 (java 员工), 返回 (company_a, company_b)。"""
    store = registry.store
    a = "C-A"
    b = "C-B"
    store.save_employee(make_employee(
        employee_id="E-A1", company_id=a, name="Alice",
        capabilities=["python"], status=EmployeeStatus.ACTIVE,
    ))
    store.save_employee(make_employee(
        employee_id="E-B1", company_id=b, name="Bob",
        capabilities=["java"], role_ids=["R-1"], status=EmployeeStatus.ACTIVE,
    ))
    return a, b


class TestFindByCapability:
    def test_exact_match(self, registry):
        _seed_two_companies(registry)
        result = registry.find_by_capability("python")
        assert [e.id for e in result] == ["E-A1"]

    def test_no_match_returns_empty(self, registry):
        _seed_two_companies(registry)
        assert registry.find_by_capability("rust") == []

    def test_case_sensitive(self, registry):
        """大小写敏感精确匹配: Python ≠ python。"""
        _seed_two_companies(registry)
        assert registry.find_by_capability("Python") == []

    def test_company_scoped(self, registry):
        a, b = _seed_two_companies(registry)
        assert registry.find_by_capability("java", company_id=a) == []
        assert [e.id for e in registry.find_by_capability("java", company_id=b)] == [
            "E-B1"
        ]

    def test_skips_left_employees(self, registry):
        store = registry.store
        store.save_employee(make_employee(
            employee_id="E-L", company_id="C-A", name="Left",
            capabilities=["python"], status=EmployeeStatus.LEFT,
        ))
        store.save_employee(make_employee(
            employee_id="E-A", company_id="C-A", name="Active",
            capabilities=["python"], status=EmployeeStatus.ACTIVE,
        ))
        assert [e.id for e in registry.find_by_capability("python")] == ["E-A"]

    def test_result_sorted_by_id(self, registry):
        store = registry.store
        for eid in ("E-2", "E-1"):
            store.save_employee(make_employee(
                employee_id=eid, company_id="C-A", capabilities=["python"],
            ))
        assert [e.id for e in registry.find_by_capability("python")] == ["E-1", "E-2"]


class TestFindByRole:
    def test_matches_role_membership(self, registry):
        store = registry.store
        store.save_employee(make_employee(
            employee_id="E-1", role_ids=["R-dev"], capabilities=[],
        ))
        assert [e.id for e in registry.find_by_role("R-dev")] == ["E-1"]

    def test_role_is_not_capability(self, registry):
        """Role ≠ Capability: 有 capability 无 role 不命中。"""
        store = registry.store
        store.save_employee(make_employee(
            employee_id="E-1", role_ids=["R-dev"], capabilities=["python"],
        ))
        assert registry.find_by_role("R-python") == []
        assert [e.id for e in registry.find_by_capability("python")] == ["E-1"]

    def test_company_scoped(self, registry):
        a, b = _seed_two_companies(registry)
        assert registry.find_by_role("R-1", company_id=a) == []
        assert [e.id for e in registry.find_by_role("R-1", company_id=b)] == ["E-B1"]

    def test_no_match_returns_empty(self, registry):
        _seed_two_companies(registry)
        assert registry.find_by_role("R-999") == []


class TestFindCombined:
    def test_all_filters_are_and(self, registry):
        store = registry.store
        store.save_employee(make_employee(
            employee_id="E-1", company_id="C-A", name="Both",
            role_ids=["R-1"], capabilities=["python", "sql"],
        ))
        store.save_employee(make_employee(
            employee_id="E-2", company_id="C-A", name="CapOnly",
            capabilities=["python"],
        ))
        result = registry.find(
            company_id="C-A", capability="python", role_id="R-1"
        )
        assert [e.id for e in result] == ["E-1"]

    def test_no_filters_returns_all_active(self, registry):
        a, b = _seed_two_companies(registry)
        store = registry.store
        store.save_employee(make_employee(
            employee_id="E-L", company_id="C-A", status=EmployeeStatus.LEFT,
        ))
        assert {e.id for e in registry.find()} == {"E-A1", "E-B1"}

    def test_company_only_filter(self, registry):
        a, b = _seed_two_companies(registry)
        assert [e.id for e in registry.find(company_id=a)] == ["E-A1"]

    def test_empty_capability_filter_matches_all(self, registry):
        """空字符串 capability 过滤 = 无过滤 (不匹配空能力集成员)。"""
        a, _ = _seed_two_companies(registry)
        assert [e.id for e in registry.find(company_id=a, capability="")] == ["E-A1"]


class TestCandidatesFor:
    def test_requirement_duck_typing(self, registry):
        store = registry.store
        store.save_employee(make_employee(
            employee_id="E-1", capabilities=["python", "sql"],
        ))
        store.save_employee(make_employee(
            employee_id="E-2", capabilities=["python"],
        ))

        class _Req:
            required_capabilities = ["python", "sql"]

        assert [e.id for e in registry.candidates_for(_Req())] == ["E-1"]

    def test_requirement_without_caps_matches_all(self, registry):
        a, b = _seed_two_companies(registry)

        class _Empty:
            required_capabilities = []

        assert {e.id for e in registry.candidates_for(_Empty())} == {"E-A1", "E-B1"}


class TestReadOnlyRecommendation:
    def test_find_emits_no_events(self, registry, logger):
        """只推荐不分配: 检索零副作用 — 不产生任何事件。"""
        _seed_two_companies(registry)
        registry.find_by_capability("python")
        registry.find_by_role("R-1")
        registry.find(company_id="C-A")
        registry.candidates_for(type("R", (), {"required_capabilities": ["python"]})())
        assert event_sequence(logger.store) == []

    def test_find_does_not_modify_store(self, registry):
        a, b = _seed_two_companies(registry)
        registry.find_by_capability("python")
        assert len(registry.store.list_employees()) == 2
        assert {e.id for e in registry.store.list_employees()} == {"E-A1", "E-B1"}

    def test_register_employee_upsert(self, registry):
        registry.register_employee(make_employee(name="Ada", capabilities=["c"]))
        registry.register_employee(make_employee(name="Ada v2", capabilities=["c", "c++"]))
        assert len(registry.store.list_employees()) == 1
        assert registry.store.get_employee("E-1").name == "Ada v2"


class TestRegistryThroughLifecycle:
    def test_hired_employee_appears_in_registry(self, org_store, logger):
        """生命周期入职 → 注册表可见 (同一 OrgStore 实例共享)。"""
        lifecycle = OrgLifecycle(org_store, logger=logger)
        company_id = lifecycle.create_company(
            "Acme", template="solo", company_id="C-1"
        ).id
        role = org_store.list_roles_by_company(company_id)[0]
        lifecycle.hire_employee(
            company_id, "Ada", role.id,
            capabilities=["python"], employee_id="E-1",
        )
        found = lifecycle.registry.find_by_capability("python", company_id=company_id)
        assert [e.id for e in found] == ["E-1"]

    def test_after_leave_not_found_by_any_filter(self, org_store, logger):
        lifecycle = OrgLifecycle(org_store, logger=logger)
        company_id = lifecycle.create_company(
            "Acme", template="solo", company_id="C-1"
        ).id
        role = org_store.list_roles_by_company(company_id)[0]
        lifecycle.hire_employee(
            company_id, "Ada", role.id, capabilities=["python"], employee_id="E-1",
        )
        lifecycle.leave("E-1")
        assert lifecycle.registry.find_by_capability("python") == []
        assert lifecycle.registry.find_by_role(role.id) == []
