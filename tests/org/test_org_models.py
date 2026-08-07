"""tests/org/test_org_models.py — 组织领域模型 (Phase 16A, ADR-0036)。

覆盖: Company/Department/Role/Employee/Authority/KnowledgeItem 字段默认值、
before-validator 归一 (None → 默认)、枚举语义、to_dict JSON 友好导出、
员工生命周期状态机 (active → left)。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from org.models import (
    Authority,
    Company,
    Department,
    Employee,
    EmployeeStatus,
    KnowledgeItem,
    Role,
    new_id,
)

from org_helpers import (
    make_authority,
    make_company,
    make_department,
    make_employee,
    make_knowledge,
    make_role,
)


class TestCompanyModel:
    def test_defaults(self):
        c = Company(id="C-1", name="Acme")
        assert c.template == "solo"
        assert c.parent_company is None
        assert c.departments == []
        assert c.knowledge_space == ""
        assert c.created_at is not None

    def test_departments_none_normalized(self):
        c = Company(id="C-1", name="Acme", departments=None)
        assert c.departments == []

    def test_knowledge_space_defaults_to_company_id_in_lifecycle(self, org_store):
        from org.lifecycle import OrgLifecycle

        c = OrgLifecycle(org_store).create_company("Acme", template="solo", company_id="C-9")
        assert c.knowledge_space == "C-9"

    def test_to_dict_json_friendly(self):
        d = make_company().to_dict()
        assert d["id"] == "C-1"
        assert d["template"] == "solo"
        assert isinstance(d["created_at"], str)  # datetime → ISO 字符串

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError):
            Company(id="C-1", name="Acme", bogus=1)

    def test_new_id_prefix(self):
        assert new_id("C").startswith("C-")
        assert len(new_id("C")) > 3


class TestDepartmentModel:
    def test_fields(self):
        d = make_department()
        assert d.id == "D-1"
        assert d.company_id == "C-1"
        assert d.name == "Engineering"

    def test_to_dict(self):
        d = make_department().to_dict()
        assert d["company_id"] == "C-1"


class TestRoleModel:
    def test_defaults(self):
        r = make_role()
        assert r.department_id == ""
        assert r.authority_policy == {}
        assert r.human is False
        assert r.responsibility == ""

    def test_authority_policy_none_normalized(self):
        r = Role(
            id="R-1", company_id="C-1", name="Developer", authority_policy=None
        )
        assert r.authority_policy == {}

    def test_human_flag(self):
        assert make_role(human=True).human is True

    def test_policy_preserved(self):
        r = make_role(authority_policy={"code.modify": "allow"})
        assert r.authority_policy == {"code.modify": "allow"}


class TestEmployeeModel:
    def test_defaults(self):
        e = make_employee()
        assert e.role_ids == []
        assert e.capabilities == []
        assert e.knowledge_scope == []
        assert e.status == EmployeeStatus.ACTIVE
        assert e.experience_ref == ""
        assert e.performance == 0.0
        assert e.left_at is None

    def test_lists_none_normalized(self):
        e = Employee(
            id="E-1",
            company_id="C-1",
            name="Ada",
            role_ids=None,
            capabilities=None,
            knowledge_scope=None,
        )
        assert e.role_ids == []
        assert e.capabilities == []
        assert e.knowledge_scope == []

    def test_is_active_property(self):
        assert make_employee().is_active is True
        assert make_employee(status=EmployeeStatus.LEFT).is_active is False

    def test_status_enum_value(self):
        assert EmployeeStatus.ACTIVE.value == "active"
        assert EmployeeStatus.LEFT.value == "left"

    def test_left_at_settable(self):
        from org.models import utcnow

        e = make_employee(status=EmployeeStatus.LEFT)
        e = e.model_copy(update={"left_at": utcnow()})
        assert e.left_at is not None

    def test_to_dict_includes_status(self):
        d = make_employee(status=EmployeeStatus.LEFT).to_dict()
        assert d["status"] == "left"


class TestAuthorityModel:
    def test_default_effect_allow(self):
        a = make_authority()
        assert a.effect == "allow"

    def test_effect_none_normalized(self):
        a = Authority(id="A1", role_id="R-1", permission="p", effect=None)
        assert a.effect == "allow"

    def test_effect_deny_preserved(self):
        assert make_authority(effect="deny").effect == "deny"

    def test_effect_case_insensitive(self):
        assert Authority(id="A1", role_id="R-1", permission="p", effect="DENY").effect == "deny"

    def test_effect_invalid_rejected(self):
        with pytest.raises(ValidationError):
            Authority(id="A1", role_id="R-1", permission="p", effect="maybe")

    def test_to_dict(self):
        d = make_authority(effect="deny").to_dict()
        assert d["effect"] == "deny"


class TestKnowledgeItemModel:
    def test_default_version_one(self):
        k = make_knowledge()
        assert k.version == 1

    def test_fields(self):
        k = make_knowledge(domain="tech", content="x", version=2)
        assert k.domain == "tech"
        assert k.content == "x"
        assert k.version == 2

    def test_to_dict(self):
        d = make_knowledge().to_dict()
        assert d["company_id"] == "C-1"
        assert d["version"] == 1
