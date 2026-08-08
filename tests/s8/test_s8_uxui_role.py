"""tests/s8/test_s8_uxui_role.py — UX/UI Designer Role executable (Unit, S8-002)。

覆盖 (任务清单: ui-designer execution_kind → executable + UX/UI prompt 模板):
- roles.py: ui-designer execution_kind planning→executable; prompt 含设计
  7 节 (information_architecture/user_flow/wireframe/screen_specifications/
  component_definition/design_tokens/prototype); executable_role_ids 含
  ui-designer (按 role_id 排序: developer, product-manager, tester, ui-designer)
- workflow_stages: design → ux_ui (架构 §2 ②: Workflow stage "ux_ui",
  role_ref=ui-designer)
- 别名: ui → ui-designer (resolve_role 大小写不敏感)
- 诚实标注: devops 仍为 planning (S8-004 未实现, 不假装); architect 已
  executable (S8-003 ArchitectAgent)

依赖: 本目录 conftest (sys.path 挂 exec/org)。
"""

from __future__ import annotations

import exec.roles as roles

#: ux_ui 契约 7 节 (与 CONTRACTS ux_ui required_fields / UX/UI prompt 同源)
UXUI_SECTIONS = (
    "information_architecture",
    "user_flow",
    "wireframe",
    "screen_specifications",
    "component_definition",
    "design_tokens",
    "prototype",
)


class TestUXUIDesignerRole:
    def test_ui_designer_executable(self):
        """S8-002: UX/UI Designer execution_kind planning → executable。"""
        ui = roles.require_role("ui-designer")
        assert ui.execution_kind == "executable"
        assert ui.is_executable

    def test_ui_designer_prompt_covers_7_sections(self):
        """UX/UI prompt = Product → 设计: 覆盖 7 节 (与 CONTRACTS ux_ui 同源)。"""
        prompt = roles.require_role("ui-designer").prompt_template
        assert "UX/UI Designer" in prompt
        assert "Product" in prompt  # 输入 = Product Artifact
        for section in UXUI_SECTIONS:
            assert section in prompt, f"prompt 缺设计节: {section}"

    def test_ui_designer_prompt_requires_json(self):
        """UX/UI prompt 要求结构化 JSON 输出 (严格, 不允许多余文字)。"""
        prompt = roles.require_role("ui-designer").prompt_template
        assert "JSON" in prompt
        assert "仅输出 JSON" in prompt

    def test_executable_role_ids_include_ui_designer(self):
        """executable 角色 (S8-004): 6 角色全部 (architect + developer +
        devops + product-manager + tester + ui-designer, 按 role_id 排序)。"""
        assert roles.executable_role_ids() == [
            "architect", "developer", "devops", "product-manager",
            "tester", "ui-designer",
        ]

    def test_resolve_ui_designer_alias(self):
        """别名: ui → ui-designer (S7-001 统一解析链)。"""
        assert roles.resolve_role("ui").role_id == "ui-designer"
        assert roles.resolve_role("UI Designer").role_id == "ui-designer"
        assert roles.resolve_role("UX/UI Designer").role_id == "ui-designer"

    def test_ui_designer_workflow_stage_mapping(self):
        """UX/UI Designer 负责 workflow 阶段 ux_ui (架构 §2 ② 接入点)。"""
        ui = roles.require_role("ui-designer")
        assert "ux_ui" in ui.workflow_stages
        assert "design" not in ui.workflow_stages  # 旧阶段名已迁移

    def test_ui_designer_capabilities(self):
        """UX/UI Designer 能力集 (界面设计与原型; 注册表声明式)。"""
        caps = roles.capabilities_for_role("ui-designer")
        assert {"ui_design", "prototyping"} <= set(caps)

    def test_architect_and_devops_now_executable(self):
        """诚实标注: architect S8-003 已 executable; devops S8-004 也已
        executable (ReleaseAgent 已实现, 不假装可执行)。"""
        architect = roles.require_role("architect")
        assert architect.execution_kind == "executable"
        assert architect.is_executable
        devops = roles.require_role("devops")
        assert devops.execution_kind == "executable"
        assert devops.is_executable

    def test_product_manager_still_executable(self):
        """S8-001 保持: product-manager 仍 executable (回归, 只扩展不重写)。"""
        assert roles.require_role("product-manager").is_executable
