"""tests/s7/test_s7_role_resolution.py — S7-001 统一角色解析 (Unit, ADR-0039)。

覆盖 (任务清单: resolve_role 3 链/大小写/别名/org_role_coverage/模板对齐):
- resolve_role 3 链有序: role_id 精确 → 显示名大小写不敏感 → 别名
- 大小写不敏感: "Product Manager" / "PRODUCT MANAGER" / "developer" 全解析
- 别名: pm/ui/dev/qa + 多词别名 (test engineer / devops engineer)
- 空白折叠: normalize_role_ref strip+小写+折叠空白
- 未解析 → RoleError 响亮 (不静默降级); try_resolve_role → None
- 向后兼容: require_role/get_role 精确 role_id 语义逐位不变
- ORG_TEMPLATE_ROLE_MAP: org 模板角色名 → exec role_id 双体系统一映射
- org_role_coverage: 每条 resolved=True + execution_kind/capabilities 非空
- 模板 role_ref 完整性: check_template_role_integrity 零未解析 (S7-001 验收)

依赖: 本目录 conftest 已挂 factory-core + factory-org + factory-exec
(双体系统一解析链需要 exec 注册表真实可用)。
"""

from __future__ import annotations

import pytest

import exec.roles as roles
from org.templates import check_template_role_integrity, template_role_coverage


class TestResolveRoleChain:
    """resolve_role 3 链有序 (S7-001 单一注册表入口, 大小写不敏感)。"""

    def test_chain1_role_id_exact(self):
        role = roles.resolve_role("developer")
        assert role.role_id == "developer"
        assert role.is_executable

    def test_chain1_role_id_case_insensitive(self):
        """链 1 也大小写不敏感 (归一化后查键): Developer == developer。"""
        assert roles.resolve_role("Developer").role_id == "developer"
        assert roles.resolve_role("DEVELOPER").role_id == "developer"

    def test_chain2_display_name(self):
        """链 2: 显示名匹配 (注册表内建名索引)。"""
        assert roles.resolve_role("Product Manager").role_id == "product-manager"
        assert roles.resolve_role("UI Designer").role_id == "ui-designer"

    def test_chain2_display_name_case_insensitive(self):
        assert roles.resolve_role("product manager").role_id == "product-manager"
        assert roles.resolve_role("PRODUCT MANAGER").role_id == "product-manager"

    def test_chain3_alias(self):
        """链 3: 别名匹配 (ROLE_ALIASES)。"""
        assert roles.resolve_role("pm").role_id == "product-manager"
        assert roles.resolve_role("ui").role_id == "ui-designer"
        assert roles.resolve_role("dev").role_id == "developer"
        assert roles.resolve_role("qa").role_id == "tester"

    def test_chain3_alias_case_insensitive(self):
        assert roles.resolve_role("PM").role_id == "product-manager"
        assert roles.resolve_role("QA").role_id == "tester"
        assert roles.resolve_role("Dev").role_id == "developer"

    def test_chain3_multiword_alias(self):
        """多词别名: test engineer → tester; devops engineer → devops。"""
        assert roles.resolve_role("test engineer").role_id == "tester"
        assert roles.resolve_role("devops engineer").role_id == "devops"

    def test_whitespace_and_case_folded(self):
        """归一化: strip + 小写 + 折叠空白 (前后空白/多余空白安全)。"""
        assert roles.resolve_role("  developer  ").role_id == "developer"
        assert roles.resolve_role(" test   engineer ").role_id == "tester"

    def test_unknown_raises(self):
        """未解析 → RoleError 响亮 (拼写错误立即暴露, 不静默降级)。"""
        with pytest.raises(roles.RoleError, match="unknown role"):
            roles.resolve_role("no-such-role")

    def test_try_resolve_unknown_none(self):
        assert roles.try_resolve_role("no-such-role") is None

    def test_try_resolve_known(self):
        assert roles.try_resolve_role("qa").role_id == "tester"

    def test_normalize_role_ref(self):
        assert roles.normalize_role_ref("  Product   Manager  ") == "product manager"
        assert roles.normalize_role_ref("QA") == "qa"
        assert roles.normalize_role_ref("") == ""


class TestBackwardCompatExactLookup:
    """向后兼容: require_role/get_role 精确 role_id 语义逐位不变。"""

    def test_require_role_exact_still_works(self):
        assert roles.require_role("developer").role_id == "developer"

    def test_require_role_case_sensitive_unchanged(self):
        """require_role 保持精确匹配 (非新 API 不吞大小写): 大写仍报错。"""
        with pytest.raises(roles.RoleError):
            roles.require_role("Developer")

    def test_get_role_exact_still_works(self):
        assert roles.get_role("tester") is not None
        assert roles.get_role("no-such") is None


class TestOrgTemplateRoleMap:
    """org 模板角色 → exec role_id 双体系统一映射 (S7-001 单一事实源)。"""

    def test_map_keys_are_template_role_names(self):
        """键 = org 模板角色名 (归一化), 值 = exec 注册表 role_id。"""
        mapping = roles.org_template_role_map()
        assert mapping == {
            "product manager": "product-manager",
            "architect": "architect",
            "developer": "developer",
            "qa": "tester",
        }

    def test_all_values_registered(self):
        """映射值全部是注册表真实 role_id (零悬空引用)。"""
        for role_id in roles.org_template_role_map().values():
            assert roles.get_role(role_id) is not None, role_id

    def test_ceo_human_not_in_map(self):
        """CEO 为 Human 角色 (最终批准权唯一, 非 Agent) — 不入 exec 映射。"""
        assert "ceo" not in roles.org_template_role_map()

    def test_map_is_readonly_snapshot(self):
        """快照防外部改表: 改副本不影响事实源。"""
        snapshot = roles.org_template_role_map()
        snapshot["hacked"] = "x"
        assert "hacked" not in roles.org_template_role_map()


class TestOrgRoleCoverage:
    """org 模板角色 → exec 注册表覆盖审计 (双体系统一证明)。"""

    def test_all_resolved(self):
        coverage = roles.org_role_coverage()
        assert len(coverage) == 4
        for name, row in coverage.items():
            assert row["resolved"] is True, name
            assert row["role_id"], name

    def test_execution_kind_and_capabilities_populated(self):
        coverage = roles.org_role_coverage()
        qa = coverage["qa"]
        assert qa["role_id"] == "tester"
        assert qa["execution_kind"] == "executable"  # S7-004: Tester 已可执行
        assert "testing" in qa["capabilities"]

    def test_developer_executable_in_coverage(self):
        dev = roles.org_role_coverage()["developer"]
        assert dev["role_id"] == "developer"
        assert dev["execution_kind"] == "executable"
        assert "coding" in dev["capabilities"]


class TestTemplateRoleIntegrity:
    """模板 role_ref → exec 注册表完整性 (S7-001 验收: 零未解析引用)。"""

    def test_check_template_role_integrity_empty(self):
        """software_company + solo 全部 role_ref 解析成功 → 零问题。"""
        assert check_template_role_integrity() == []

    def test_template_role_coverage_exec_refs(self):
        """模板角色覆盖审计: exec_refs 计数 = 非 Human 角色数 (CEO 除外)。"""
        coverage = template_role_coverage()
        for tpl_id, row in coverage.items():
            # CEO (human=1) 无 role_ref; 其余 4 角色全部带 role_ref
            assert row["human"] == 1, tpl_id
            assert row["exec_refs"] == 4, tpl_id
            assert row["total"] == 5, tpl_id
            for role in row["roles"]:
                if role["human"]:
                    assert role["role_ref"] == "" and role["resolved"] is True
                else:
                    assert role["role_ref"], f"{tpl_id}:{role['name']}"
                    assert role["resolved"] is True
                    assert role["execution_kind"], f"{tpl_id}:{role['name']}"
