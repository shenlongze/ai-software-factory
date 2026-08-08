"""tests/s8/test_s8_arch_role.py — Architect Role executable (Unit, S8-003)。

覆盖 (任务清单: architect execution_kind → executable + Architect prompt
7 节技术设计):
- roles.py: architect execution_kind planning→executable; prompt 含技术设计
  7 节 (system_architecture/technical_stack/database_design/api_design/
  frontend_architecture/backend_architecture/task_breakdown); 双输入
  (Product + UX/UI Artifact); executable_role_ids 含 architect (按 role_id
  排序: architect, developer, product-manager, tester, ui-designer)
- workflow_stages: architecture (架构 §2 ③: Workflow stage "architecture",
  role_ref=architect; ROLE_OUTPUT_TYPES architect→design 保持)
- 诚实标注: devops 仍为 planning (S8-004 Release 未实现, 不假装)
- 回归: pm/ui-designer/developer/tester 仍 executable (只扩展不重写)

依赖: 本目录 conftest (sys.path 挂 exec/org)。
"""

from __future__ import annotations

import exec.roles as roles

#: design 契约 7 节 (与 CONTRACTS design required_fields / Architect prompt 同源)
DESIGN_SECTIONS = (
    "system_architecture",
    "technical_stack",
    "database_design",
    "api_design",
    "frontend_architecture",
    "backend_architecture",
    "task_breakdown",
)


class TestArchitectRole:
    def test_architect_executable(self):
        """S8-003: Architect execution_kind planning → executable。"""
        arch = roles.require_role("architect")
        assert arch.execution_kind == "executable"
        assert arch.is_executable

    def test_architect_prompt_covers_7_sections(self):
        """Architect prompt = Product + UX/UI → 技术设计: 覆盖 7 节 (与
        CONTRACTS design 同源)。"""
        prompt = roles.require_role("architect").prompt_template
        assert "Architect" in prompt
        assert "Product" in prompt  # 输入 = Product Artifact
        assert "UX/UI" in prompt  # 输入 = UX/UI Artifact (双输入)
        for section in DESIGN_SECTIONS:
            assert section in prompt, f"prompt 缺技术设计节: {section}"

    def test_architect_prompt_requires_json(self):
        """Architect prompt 要求结构化 JSON 输出 (严格, 不允许多余文字)。"""
        prompt = roles.require_role("architect").prompt_template
        assert "JSON" in prompt
        assert "仅输出 JSON" in prompt

    def test_architect_prompt_developer_consumption(self):
        """task_breakdown 提示 Developer 消费 (模块/API 约定/UI 实现指导 —
        S8-005 Developer 消费准备)。"""
        prompt = roles.require_role("architect").prompt_template
        assert "api_contract" in prompt
        assert "ui_guidance" in prompt
        assert "Developer" in prompt

    def test_executable_role_ids_include_architect(self):
        """executable 角色 (S8-004): 6 角色全部 (architect + developer +
        devops + product-manager + tester + ui-designer, 按 role_id 排序)。"""
        assert roles.executable_role_ids() == [
            "architect", "developer", "devops", "product-manager",
            "tester", "ui-designer",
        ]

    def test_resolve_architect(self):
        """architect 直接可解析 (role_id 精确匹配, 大小写不敏感)。"""
        assert roles.resolve_role("architect").role_id == "architect"
        assert roles.resolve_role("Architect").role_id == "architect"
        assert roles.resolve_role("ARCHITECT").role_id == "architect"

    def test_architect_workflow_stage_mapping(self):
        """Architect 负责 workflow 阶段 architecture (架构 §2 ③ 接入点;
        ROLE_OUTPUT_TYPES architect→design 输出类型保持)。"""
        arch = roles.require_role("architect")
        assert "architecture" in arch.workflow_stages
        from org.workflow import ROLE_OUTPUT_TYPES

        assert ROLE_OUTPUT_TYPES["architect"] == "design"

    def test_architect_capabilities(self):
        """Architect 能力集 (架构设计与技术方案; 注册表声明式)。"""
        caps = roles.capabilities_for_role("architect")
        assert {"architecture", "design"} <= set(caps)

    def test_devops_now_executable(self):
        """诚实标注: devops S8-004 已 executable (ReleaseAgent 已实现 —
        Code + Test 双输入 → Release Artifact, Test 必须 VALIDATED 强校验)。"""
        devops = roles.require_role("devops")
        assert devops.execution_kind == "executable"
        assert devops.is_executable

    def test_existing_executables_unchanged(self):
        """S8-001/002/007 保持: pm/ui-designer/developer/tester 仍 executable
        (回归, 只扩展不重写)。"""
        for role_id in ("product-manager", "ui-designer", "developer", "tester"):
            assert roles.require_role(role_id).is_executable
