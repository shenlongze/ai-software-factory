"""tests/org/test_org_templates.py — 公司模板 + Role 冲突规则 (Phase 16A, ADR-0036)。

覆盖: software_company 模板结构 (3 部门 + 5 角色: CEO Human +
PM/Architect/Developer/QA AI, Default Deny 权限矩阵) / solo 模板 (扁平
5 角色) / get_template 未注册报错 / FORBIDDEN_ROLE_COMBINATIONS 冲突检测
(Developer+Reviewer, Developer+QA, 任何+CEO, 大小写/顺序无关)。
"""

from __future__ import annotations

import pytest

from org.templates import (
    FORBIDDEN_ROLE_COMBINATIONS,
    SOLO,
    SOFTWARE_COMPANY,
    TEMPLATES,
    TemplateNotFoundError,
    check_role_conflict,
    get_template,
    list_templates,
)


class TestSoftwareCompanyTemplate:
    def test_template_id(self):
        assert SOFTWARE_COMPANY.template_id == "software_company"

    def test_three_departments(self):
        assert SOFTWARE_COMPANY.departments == ("Product", "Engineering", "Quality")

    def test_five_roles(self):
        assert len(SOFTWARE_COMPANY.roles) == 5

    def test_ceo_is_human(self):
        ceo = next(r for r in SOFTWARE_COMPANY.roles if r.name == "CEO")
        assert ceo.human is True

    def test_ai_roles_not_human(self):
        for name in ("Product Manager", "Architect", "Developer", "QA"):
            role = next(r for r in SOFTWARE_COMPANY.roles if r.name == name)
            assert role.human is False

    def test_ceo_has_release_approve(self):
        ceo = next(r for r in SOFTWARE_COMPANY.roles if r.name == "CEO")
        assert ceo.authority_policy.get("release.approve") == "allow"

    def test_developer_has_no_release_approve(self):
        dev = next(r for r in SOFTWARE_COMPANY.roles if r.name == "Developer")
        assert "release.approve" not in dev.authority_policy  # Default Deny

    def test_developer_code_modify(self):
        dev = next(r for r in SOFTWARE_COMPANY.roles if r.name == "Developer")
        assert dev.authority_policy.get("code.modify") == "allow"

    def test_qa_has_review_approve(self):
        qa = next(r for r in SOFTWARE_COMPANY.roles if r.name == "QA")
        assert qa.authority_policy.get("review.approve") == "allow"

    def test_role_departments(self):
        ceo = next(r for r in SOFTWARE_COMPANY.roles if r.name == "CEO")
        qa = next(r for r in SOFTWARE_COMPANY.roles if r.name == "QA")
        assert ceo.department == "Product"
        assert qa.department == "Quality"


class TestSoloTemplate:
    def test_template_id(self):
        assert SOLO.template_id == "solo"

    def test_flat_no_departments(self):
        assert SOLO.departments == ()

    def test_five_roles(self):
        assert len(SOLO.roles) == 5

    def test_ceo_is_human(self):
        ceo = next(r for r in SOLO.roles if r.name == "CEO")
        assert ceo.human is True

    def test_roles_company_level(self):
        for role in SOLO.roles:
            assert role.department == ""

    def test_ceo_release_approve(self):
        ceo = next(r for r in SOLO.roles if r.name == "CEO")
        assert ceo.authority_policy.get("release.approve") == "allow"


class TestTemplateRegistry:
    def test_templates_contains_both(self):
        assert set(TEMPLATES) == {"software_company", "solo"}

    def test_get_template_known(self):
        assert get_template("solo").template_id == "solo"
        assert get_template("software_company").template_id == "software_company"

    def test_get_template_unknown_raises(self):
        with pytest.raises(TemplateNotFoundError):
            get_template("enterprise")

    def test_list_templates_shape(self):
        items = list_templates()
        assert len(items) == 2
        first = items[0]
        assert set(first) == {"template", "name", "description", "department_count", "role_count"}
        assert first["role_count"] == 5

    def test_software_company_department_count(self):
        items = {i["template"]: i for i in list_templates()}
        assert items["software_company"]["department_count"] == 3
        assert items["solo"]["department_count"] == 0


class TestRoleConflictRules:
    def test_forbidden_combinations_registry(self):
        assert ("developer", "reviewer") in FORBIDDEN_ROLE_COMBINATIONS
        assert ("developer", "qa") in FORBIDDEN_ROLE_COMBINATIONS
        assert ("*", "ceo") in FORBIDDEN_ROLE_COMBINATIONS

    def test_no_conflict_single_role(self):
        assert check_role_conflict([], "Developer") is None

    def test_developer_plus_reviewer_conflict(self):
        assert check_role_conflict(["Developer"], "Reviewer") is not None

    def test_developer_plus_qa_conflict(self):
        assert check_role_conflict(["Developer"], "QA") is not None

    def test_qa_plus_developer_conflict_order_free(self):
        assert check_role_conflict(["QA"], "Developer") is not None

    def test_any_plus_ceo_conflict(self):
        assert check_role_conflict(["Developer"], "CEO") is not None
        assert check_role_conflict(["QA"], "CEO") is not None

    def test_ceo_plus_any_conflict(self):
        assert check_role_conflict(["CEO"], "Developer") is not None

    def test_case_insensitive(self):
        assert check_role_conflict(["developer"], "QA") is not None
        assert check_role_conflict(["Developer"], "qa") is not None

    def test_whitespace_insensitive(self):
        assert check_role_conflict([" Developer "], "QA") is not None

    def test_unrelated_roles_ok(self):
        assert check_role_conflict(["Product Manager", "Architect"], "QA") is None

    def test_developer_plus_architect_ok(self):
        assert check_role_conflict(["Developer"], "Architect") is None
