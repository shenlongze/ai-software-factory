"""tests/s8/test_s8_pm_role.py — PM Role executable (Unit, S8-001)。

覆盖 (任务清单: PM execution_kind → executable / PM prompt 模板):
- roles.py: product-manager execution_kind planning→executable; prompt 含
  产品分析 7 节 (market_analysis/user_persona/user_journey/problem_statement/
  feature_list/mvp_scope/user_stories); executable_role_ids 含 product-manager
- org_role_coverage: "product manager" → execution_kind=executable (双体系)
- 别名: pm → product-manager (resolve_role 大小写不敏感)

依赖: 本目录 conftest (sys.path 挂 exec/org)。
"""

from __future__ import annotations

import exec.roles as roles

#: product 契约 7 节 (与 CONTRACTS product required_fields / PM prompt 同源)
PRODUCT_SECTIONS = (
    "market_analysis",
    "user_persona",
    "user_journey",
    "problem_statement",
    "feature_list",
    "mvp_scope",
    "user_stories",
)


class TestPMRole:
    def test_pm_executable(self):
        """S8-001: ProductManager execution_kind planning → executable。"""
        pm = roles.require_role("product-manager")
        assert pm.execution_kind == "executable"
        assert pm.is_executable

    def test_pm_prompt_covers_7_sections(self):
        """PM prompt = 想法 → 产品分析: 覆盖 7 节 (与 CONTRACTS product 同源)。"""
        prompt = roles.require_role("product-manager").prompt_template
        assert "Product Manager" in prompt
        assert "Idea" in prompt
        for section in PRODUCT_SECTIONS:
            assert section in prompt, f"prompt 缺产品分析节: {section}"

    def test_pm_prompt_requires_json(self):
        """PM prompt 要求结构化 JSON 输出 (严格, 不允许多余文字)。"""
        prompt = roles.require_role("product-manager").prompt_template
        assert "JSON" in prompt
        assert "仅输出 JSON" in prompt

    def test_executable_role_ids_include_pm(self):
        """executable 角色 (S8-004): 6 角色全部 (architect + developer +
        devops + product-manager + tester + ui-designer)。"""
        assert roles.executable_role_ids() == [
            "architect", "developer", "devops", "product-manager",
            "tester", "ui-designer",
        ]

    def test_org_coverage_pm_executable(self):
        """双体系统一: org 模板 product manager → exec product-manager。"""
        coverage = roles.org_role_coverage()
        assert coverage["product manager"]["role_id"] == "product-manager"
        assert coverage["product manager"]["resolved"] is True
        assert coverage["product manager"]["execution_kind"] == "executable"

    def test_resolve_pm_alias(self):
        """别名: pm → product-manager (S7-001 统一解析链)。"""
        assert roles.resolve_role("pm").role_id == "product-manager"
        assert roles.resolve_role("Product Manager").role_id == "product-manager"
        assert roles.resolve_role("PRODUCT-MANAGER").role_id == "product-manager"

    def test_pm_workflow_stage_mapping(self):
        """PM 负责 workflow 阶段 product (role_ref=pm 接入点)。"""
        pm = roles.require_role("product-manager")
        assert "product" in pm.workflow_stages

    def test_pm_capabilities(self):
        """PM 能力集 (含产品分析; 注册表声明式)。"""
        caps = roles.capabilities_for_role("product-manager")
        assert {"requirement", "planning", "product_analysis"} <= set(caps)

    def test_architect_executable_devops_too(self):
        """诚实标注: Architect S8-003 已 executable; DevOps S8-004 也已
        executable (ReleaseAgent 已实现, 不假装可执行的反面: 有真实路径就
        诚实标注); UX/UI Designer S8-002 已 executable。"""
        ui = roles.require_role("ui-designer")
        assert ui.execution_kind == "executable"
        assert ui.is_executable
        arch = roles.require_role("architect")
        assert arch.execution_kind == "executable"
        assert arch.is_executable
        devops = roles.require_role("devops")
        assert devops.execution_kind == "executable"
        assert devops.is_executable
