"""tests/s8/test_s8_release_role.py — DevOps Role executable (Unit, S8-004)。

覆盖 (任务清单: devops execution_kind → executable + Release prompt 5 节):
- roles.py: devops execution_kind planning→executable; prompt 含发布产物
  5 节 (build_result/version/package/release_notes/deployment); 双输入
  (Code + Test Artifact); executable_role_ids 含 devops (按 role_id 排序:
  architect, developer, devops, product-manager, tester, ui-designer —
  S8-004 后注册表 6 角色全部 executable)
- workflow_stages: release (架构 §2 ⑥: Workflow stage "release",
  role_ref=devops; ROLE_OUTPUT_TYPES devops→release 保持)
- 诚实标注: S8-004 后注册表无 planning 角色 (6 角色全 executable);
  S7-005 Demo 的 release 阶段仍注入 mock 占位 (Demo 零 LLM, mock 与
  角色 execution_kind 分离)
- 回归: pm/ui-designer/architect/developer/tester 仍 executable
  (只扩展不重写)

依赖: 本目录 conftest (sys.path 挂 exec/org)。
"""

from __future__ import annotations

import exec.roles as roles

#: release 契约 5 节 (与 CONTRACTS release required_fields / DevOps prompt 同源)
RELEASE_SECTIONS = (
    "build_result",
    "version",
    "package",
    "release_notes",
    "deployment",
)


class TestDevOpsRole:
    def test_devops_executable(self):
        """S8-004: devops execution_kind planning → executable。"""
        devops = roles.require_role("devops")
        assert devops.execution_kind == "executable"
        assert devops.is_executable

    def test_devops_prompt_covers_5_sections(self):
        """DevOps prompt = Code + Test → 发布产物: 覆盖 5 节 (与 CONTRACTS
        release 同源)。"""
        prompt = roles.require_role("devops").prompt_template
        assert "DevOps" in prompt
        assert "Code" in prompt  # 输入 = Code Artifact
        assert "Test" in prompt  # 输入 = Test Artifact (双输入)
        for section in RELEASE_SECTIONS:
            assert section in prompt, f"prompt 缺发布产物节: {section}"

    def test_devops_prompt_requires_json(self):
        """DevOps prompt 要求结构化 JSON 输出 (严格, 不允许多余文字)。"""
        prompt = roles.require_role("devops").prompt_template
        assert "JSON" in prompt
        assert "仅输出 JSON" in prompt

    def test_devops_prompt_test_gate(self):
        """Test VALIDATED 强校验: prompt 声明未通过测试禁止发布 (质量门禁)。"""
        prompt = roles.require_role("devops").prompt_template
        assert "passed" in prompt
        assert "禁止发布" in prompt or "未通过测试" in prompt

    def test_executable_role_ids_include_devops(self):
        """executable 角色 (S8-004): 6 角色全部 executable (按 role_id 排序:
        architect, developer, devops, product-manager, tester, ui-designer)。"""
        assert roles.executable_role_ids() == [
            "architect", "developer", "devops", "product-manager",
            "tester", "ui-designer",
        ]

    def test_no_planning_roles_remain(self):
        """诚实标注: S8-004 后注册表 6 角色全部 executable — 无 planning
        角色 (不假装可执行的反面: 有真实路径就诚实标注)。"""
        assert [r.role_id for r in roles.list_roles() if not r.is_executable] == []

    def test_resolve_devops(self):
        """devops 直接可解析 (role_id 精确匹配, 大小写不敏感 + 别名)。"""
        assert roles.resolve_role("devops").role_id == "devops"
        assert roles.resolve_role("DevOps").role_id == "devops"
        assert roles.resolve_role("devops engineer").role_id == "devops"

    def test_devops_workflow_stage_mapping(self):
        """DevOps 负责 workflow 阶段 release (架构 §2 ⑥ 接入点;
        ROLE_OUTPUT_TYPES devops→release 输出类型保持)。"""
        devops = roles.require_role("devops")
        assert "release" in devops.workflow_stages
        assert "deployment" not in devops.workflow_stages  # 旧阶段名已迁移
        from org.workflow import ROLE_OUTPUT_TYPES

        assert ROLE_OUTPUT_TYPES["devops"] == "release"

    def test_devops_capabilities(self):
        """DevOps 能力集 (部署/运维/发布; 注册表声明式)。"""
        caps = roles.capabilities_for_role("devops")
        assert {"deployment", "ops", "release"} <= set(caps)

    def test_existing_executables_unchanged(self):
        """S8-001/002/003/007 保持: pm/ui-designer/architect/developer/tester
        仍 executable (回归, 只扩展不重写)。"""
        for role_id in (
            "product-manager", "ui-designer", "architect", "developer", "tester",
        ):
            assert roles.require_role(role_id).is_executable
