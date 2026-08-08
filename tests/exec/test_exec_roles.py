"""tests/exec/test_exec_roles.py — 多角色注册表 (Sprint 6)。

覆盖: 6 角色注册 (ProductManager/UIDesigner/Architect/Developer/Tester/
DevOps) / RoleDefinition 字段 (capabilities + prompt 模板 + workflow 阶段
映射 + execution_kind) / executable 角色 (developer + tester, S7-004) /
get_role vs require_role (未注册 → RoleError 响亮) / 能力合并 (去重保序,
None 安全) / workflow 阶段 ↔ 角色映射完整性 / list_role_dicts /
executable_role_ids。

设计 (roles.py): 角色 = 声明式数据 (dataclass frozen), 零逻辑; 注册表 dict
单一事实源; 零 pydantic — 与 templates.py 同构。
"""

from __future__ import annotations

import pytest

from exec.roles import (
    ROLE_IDS,
    RoleError,
    capabilities_for_role,
    executable_role_ids,
    get_role,
    list_role_dicts,
    list_roles,
    merge_capabilities,
    require_role,
)

#: 任务要求的 6 角色 (按注册表键)
EXPECTED_ROLES = {
    "product-manager",
    "ui-designer",
    "architect",
    "developer",
    "tester",
    "devops",
}

#: 角色 → workflow 阶段 (注册表映射单一事实)
STAGE_TO_ROLE = {
    "product": "product-manager",
    "design": "ui-designer",
    "architecture": "architect",
    "development": "developer",
    "testing": "tester",
    "deployment": "devops",
}


class TestRegistry:
    def test_six_roles_registered(self):
        """6 角色全部注册 (任务要求清单), 无缺漏无多余。"""
        assert set(ROLE_IDS) == EXPECTED_ROLES
        assert len(list_roles()) == 6

    def test_roles_sorted_by_id(self):
        """角色清单按 role_id 排序 (审计友好)。"""
        assert ROLE_IDS == tuple(sorted(EXPECTED_ROLES))
        assert [r.role_id for r in list_roles()] == list(ROLE_IDS)

    def test_role_fields(self):
        """RoleDefinition 四要素: capabilities + prompt_template + workflow_stages + execution_kind。"""
        dev = require_role("developer")
        assert dev.name == "Developer"
        assert "coding" in dev.capabilities
        assert dev.prompt_template and "Developer" in dev.prompt_template
        assert "development" in dev.workflow_stages
        assert dev.execution_kind == "executable"
        assert dev.is_executable

    def test_developer_and_tester_executable(self):
        """诚实标注: developer + tester 有真实 LLM 执行路径 (S7-004 Tester
        executable), 其余 planning。"""
        for role in list_roles():
            if role.role_id in ("developer", "tester"):
                assert role.is_executable
                assert role.execution_kind == "executable"
            else:
                assert not role.is_executable
                assert role.execution_kind == "planning"

    def test_planning_roles_have_prompt_and_stages(self):
        """规划角色同样具备 prompt 模板与阶段映射 (演示拆解可用, 不假装可执行)。"""
        for role_id in EXPECTED_ROLES - {"developer", "tester"}:
            role = require_role(role_id)
            assert role.prompt_template, f"{role_id} 缺 prompt 模板"
            assert role.workflow_stages, f"{role_id} 缺 workflow 阶段映射"

    def test_workflow_stage_mapping_complete(self):
        """每阶段 → 唯一角色 (验收演示 5 阶段拆解映射完整)。"""
        for stage, role_id in STAGE_TO_ROLE.items():
            role = require_role(role_id)
            assert stage in role.workflow_stages
        # 所有注册的 workflow_stages 都被 STAGE_TO_ROLE 覆盖 (无孤儿阶段)
        all_stages = {s for r in list_roles() for s in r.workflow_stages}
        assert all_stages == set(STAGE_TO_ROLE)


class TestLookup:
    def test_get_role_known(self):
        role = get_role("tester")
        assert role is not None
        assert role.role_id == "tester"
        assert "testing" in role.capabilities

    def test_get_role_unknown_none(self):
        """未注册 → None (调用方按配置缺口处理, 不抛)。"""
        assert get_role("no-such-role") is None

    def test_require_role_unknown_raises(self):
        """未注册 → RoleError 响亮 (拼写错误立即暴露, 不静默降级)。"""
        with pytest.raises(RoleError, match="unknown role: 'no-such-role'"):
            require_role("no-such-role")

    def test_capabilities_for_role(self):
        assert set(capabilities_for_role("devops")) == {"deployment", "ops", "release"}
        with pytest.raises(RoleError):
            capabilities_for_role("nope")

    def test_executable_role_ids_developer_tester(self):
        """executable 角色 (S7-004): developer + tester (真实 LLM 路径)。"""
        assert executable_role_ids() == ["developer", "tester"]


class TestMergeCapabilities:
    def test_dedup_preserve_order(self):
        merged = merge_capabilities(
            ["coding", "python", "coding"], ("python", "debugging")
        )
        assert merged == ["coding", "python", "debugging"]

    def test_none_and_non_list_safe(self):
        """None/非 list 输入安全跳过 (员工缺能力字段不炸)。"""
        assert merge_capabilities(None) == []
        assert merge_capabilities("not-a-list", ["a"], None, {"b"}) == ["a"]

    def test_empty_strings_skipped(self):
        assert merge_capabilities(["", "  ", "real"]) == ["real"]


class TestDictView:
    def test_list_role_dicts(self):
        """CLI/报告只读视图: 字段齐全, 与注册表一致。"""
        rows = list_role_dicts()
        assert len(rows) == 6
        by_id = {r["role_id"]: r for r in rows}
        assert set(by_id) == EXPECTED_ROLES
        dev = by_id["developer"]
        assert dev["execution_kind"] == "executable"
        assert "development" in dev["workflow_stages"]
        assert set(dev["capabilities"]) == {"coding", "python", "debugging"}
