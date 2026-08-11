"""tests/org/test_capability_model.py — S10-012 Task 001: Capability Domain Model (TDD)。

设计依据 (唯一):
- docs/sprint10/S10-012-architecture-design.md §二 (六实体字段) + §四b (v1.1:
  CapabilityState 生命周期 DRAFT→ACTIVE→DEPRECATED→ARCHIVED, archived 终态,
  enabled 保留运行开关 — ACTIVE 且 enabled=true 才可被 binding 选用) + §四
  (v1.1: CapabilityBinding {type, id, version?} — version 可复现, 历史
  binding 无 version 兼容)

覆盖 (org/capabilities.py — 本 Task 只建实体, 不实现 Registry 逻辑):
- 六实体: Skill / Agent / MCP / WorkflowTemplate / Industry / LLMConfig
  (字段按设计 §二 + state/enabled; enabled 与 state 语义分离)
- CapabilityState 统一生命周期: DRAFT→ACTIVE→DEPRECATED→ARCHIVED
  - 受控单向转换表 (CAPABILITY_STATE_TRANSITIONS) + 非法拒绝 (跳级 DRAFT→
    ARCHIVED / 回退 / 终态后 / 同态)
  - transition_capability 纯函数 (返回新实例, 原对象不变) — 六实体通用
  - enabled 独立运行开关: ACTIVE+enabled=true 可选; ACTIVE+enabled=false
    不可选; DRAFT/DEPRECATED/ARCHIVED 一律不可选 (capability_selectable)
- CapabilityBinding: {type: agent|skill|mcp|workflow, id 非空, version?}
  - version 可选 (历史 binding 无 version → None 兼容, 零破坏)
  - type 宽容解析 (大小写不敏感) + 非法 type 拒绝; id 空串/空白/缺失拒绝
- 实体宽松解析: 旧数据 (无 state/enabled 字段) 加载 → 默认 DRAFT/enabled=True,
  零破坏 (六实体 parametrize)

basename 全仓库唯一 (test_capability_model); 不跨目录依赖 helper。
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

# noqa: E402 — tests/org/conftest.py 已挂 factory-org 到 sys.path (org 包父目录)
from org.capabilities import (  # noqa: E402
    Agent,
    BindingType,
    CAPABILITY_STATE_TRANSITIONS,
    CapabilityBinding,
    CapabilityState,
    Industry,
    LLMConfig,
    MCP,
    Skill,
    WorkflowTemplate,
    capability_selectable,
    transition_capability,
)


# ------------------------------------------------------------------ 六实体


class TestSkillModel:
    def test_skill_full_fields(self):
        """Skill 全字段: id/name/description/category/input_schema/output_schema/
        version/enabled/state (设计 §二 + v1.1)。"""
        skill = Skill(
            id="skill-backend-dev",
            name="Backend Development",
            description="后端开发",
            category="software-development",
            input_schema={"inputs": [{"name": "task"}]},
            output_schema={"outputs": [{"name": "code"}]},
            version="1.2.0",
            enabled=True,
            state="active",
        )
        assert skill.id == "skill-backend-dev"
        assert skill.name == "Backend Development"
        assert skill.description == "后端开发"
        assert skill.category == "software-development"
        assert skill.input_schema["inputs"][0]["name"] == "task"
        assert skill.output_schema["outputs"][0]["name"] == "code"
        assert skill.version == "1.2.0"
        assert skill.enabled is True
        assert skill.state == CapabilityState.ACTIVE
        d = skill.to_dict()
        assert {
            "id", "name", "description", "category", "input_schema",
            "output_schema", "version", "enabled", "state",
        } <= set(d)

    def test_skill_defaults(self):
        """默认值: 空串/空 dict, version=\"\", enabled=True, state=DRAFT。"""
        skill = Skill(id="s1", name="x")
        assert skill.description == ""
        assert skill.category == ""
        assert skill.input_schema == {}
        assert skill.output_schema == {}
        assert skill.version == ""
        assert skill.enabled is True
        assert skill.state == CapabilityState.DRAFT


class TestAgentModel:
    def test_agent_full_fields(self):
        """Agent 全字段: id/name/role/description/skill_bindings/workflow_bindings/
        llm_config (LLMConfig id 引用)/enabled/state。"""
        agent = Agent(
            id="agent-pm",
            name="PM Agent",
            role="product-manager",
            description="产品经理",
            skill_bindings=[{"type": "skill", "id": "skill-backend", "version": "1.0.0"}],
            workflow_bindings=[{"type": "workflow", "id": "wf-software-dev"}],
            llm_config="llm-default",
            enabled=True,
            state="active",
        )
        assert agent.id == "agent-pm"
        assert agent.role == "product-manager"
        assert agent.skill_bindings[0].type == BindingType.SKILL
        assert agent.skill_bindings[0].id == "skill-backend"
        assert agent.skill_bindings[0].version == "1.0.0"
        assert agent.workflow_bindings[0].id == "wf-software-dev"
        assert agent.workflow_bindings[0].version is None  # 未 pin → 兼容
        assert agent.llm_config == "llm-default"
        assert agent.state == CapabilityState.ACTIVE
        d = agent.to_dict()
        assert d["skill_bindings"][0]["type"] == "skill"  # JSON 干净
        assert d["workflow_bindings"][0]["version"] is None

    def test_agent_defaults(self):
        agent = Agent(id="a1", name="x")
        assert agent.role == ""
        assert agent.description == ""
        assert agent.skill_bindings == []
        assert agent.workflow_bindings == []
        assert agent.llm_config == ""
        assert agent.enabled is True
        assert agent.state == CapabilityState.DRAFT


class TestMCPModel:
    def test_mcp_full_fields(self):
        """MCP 全字段: id/name/type/endpoint/auth_config/capabilities/enabled/state。"""
        mcp = MCP(
            id="mcp-github",
            name="GitHub MCP",
            type="http",
            endpoint="https://api.github.com/mcp",
            auth_config={"token_env": "GITHUB_TOKEN"},
            capabilities=["repo.read", "pr.write"],
            enabled=False,
            state="deprecated",
        )
        assert mcp.type == "http"
        assert mcp.endpoint == "https://api.github.com/mcp"
        assert mcp.auth_config["token_env"] == "GITHUB_TOKEN"
        assert mcp.capabilities == ["repo.read", "pr.write"]
        assert mcp.enabled is False
        assert mcp.state == CapabilityState.DEPRECATED

    def test_mcp_defaults(self):
        mcp = MCP(id="m1", name="x")
        assert mcp.type == ""
        assert mcp.endpoint == ""
        assert mcp.auth_config == {}
        assert mcp.capabilities == []
        assert mcp.state == CapabilityState.DRAFT


class TestWorkflowTemplateModel:
    def test_workflow_full_fields(self):
        """WorkflowTemplate 全字段: id/name/industry/steps/required_agents/
        required_skills/enabled/state。"""
        wf = WorkflowTemplate(
            id="wf-software-dev",
            name="Software Development",
            industry="software",
            steps=[{"order": 1, "name": "plan"}, {"order": 2, "name": "build"}],
            required_agents=["agent-pm", "agent-dev"],
            required_skills=["skill-backend"],
            enabled=True,
            state="active",
        )
        assert wf.industry == "software"
        assert wf.steps[1]["name"] == "build"
        assert wf.required_agents == ["agent-pm", "agent-dev"]
        assert wf.required_skills == ["skill-backend"]
        assert wf.state == CapabilityState.ACTIVE

    def test_workflow_defaults(self):
        wf = WorkflowTemplate(id="w1", name="x")
        assert wf.industry == ""
        assert wf.steps == []
        assert wf.required_agents == []
        assert wf.required_skills == []
        assert wf.state == CapabilityState.DRAFT


class TestIndustryModel:
    def test_industry_full_fields(self):
        """Industry 全字段: id/name/description/workflow_templates/enabled/state。"""
        ind = Industry(
            id="ind-software",
            name="Software",
            description="软件行业",
            workflow_templates=["wf-software-dev"],
            enabled=True,
            state="active",
        )
        assert ind.description == "软件行业"
        assert ind.workflow_templates == ["wf-software-dev"]
        assert ind.state == CapabilityState.ACTIVE

    def test_industry_defaults(self):
        ind = Industry(id="i1", name="x")
        assert ind.description == ""
        assert ind.workflow_templates == []
        assert ind.state == CapabilityState.DRAFT


class TestLLMConfigModel:
    def test_llm_config_full_fields(self):
        """LLMConfig 全字段: id/provider/model/endpoint/parameters/enabled/state。"""
        cfg = LLMConfig(
            id="llm-default",
            provider="openai",
            model="gpt-4o",
            endpoint="https://api.openai.com/v1",
            parameters={"temperature": 0.2},
            enabled=True,
            state="active",
        )
        assert cfg.provider == "openai"
        assert cfg.model == "gpt-4o"
        assert cfg.endpoint == "https://api.openai.com/v1"
        assert cfg.parameters["temperature"] == 0.2
        assert cfg.state == CapabilityState.ACTIVE

    def test_llm_config_defaults(self):
        cfg = LLMConfig(id="l1")
        assert cfg.provider == ""
        assert cfg.model == ""
        assert cfg.endpoint == ""
        assert cfg.parameters == {}
        assert cfg.enabled is True
        assert cfg.state == CapabilityState.DRAFT


# ------------------------------------------------------------------ 宽松解析 (旧数据兼容)


@pytest.mark.parametrize(
    "data,entity_cls",
    [
        ({"id": "s1", "name": "x"}, Skill),
        ({"id": "a1", "name": "x"}, Agent),
        ({"id": "m1", "name": "x"}, MCP),
        ({"id": "w1", "name": "x"}, WorkflowTemplate),
        ({"id": "i1", "name": "x"}, Industry),
        ({"id": "l1"}, LLMConfig),
    ],
    ids=["skill", "agent", "mcp", "workflow", "industry", "llm-config"],
)
def test_legacy_data_without_state_enabled_defaults(
    data: dict[str, Any], entity_cls: type
):
    """旧数据 (无 state/enabled 字段) 加载 → 默认 DRAFT + enabled=True, 零破坏。"""
    entity = entity_cls.model_validate(data)
    assert entity.state == CapabilityState.DRAFT
    assert entity.enabled is True


# ------------------------------------------------------------------ CapabilityState 生命周期


class TestCapabilityState:
    def test_state_values(self):
        assert CapabilityState.parse("draft") == CapabilityState.DRAFT
        assert CapabilityState.parse("active") == CapabilityState.ACTIVE
        assert CapabilityState.parse("deprecated") == CapabilityState.DEPRECATED
        assert CapabilityState.parse("archived") == CapabilityState.ARCHIVED

    def test_state_parse_case_insensitive(self):
        assert CapabilityState.parse("DRAFT") == CapabilityState.DRAFT
        assert CapabilityState.parse("Active") == CapabilityState.ACTIVE
        assert CapabilityState.parse("ARCHIVED") == CapabilityState.ARCHIVED

    def test_state_parse_invalid_rejected(self):
        with pytest.raises(ValueError):
            CapabilityState.parse("bogus")

    def test_transition_table_controlled_one_way(self):
        """受控单向转换表: 仅 DRAFT→ACTIVE / ACTIVE→DEPRECATED /
        DEPRECATED→ARCHIVED; ARCHIVED 终态无去向。"""
        assert CAPABILITY_STATE_TRANSITIONS[CapabilityState.DRAFT] == (
            CapabilityState.ACTIVE,
        )
        assert CAPABILITY_STATE_TRANSITIONS[CapabilityState.ACTIVE] == (
            CapabilityState.DEPRECATED,
        )
        assert CAPABILITY_STATE_TRANSITIONS[CapabilityState.DEPRECATED] == (
            CapabilityState.ARCHIVED,
        )
        assert CAPABILITY_STATE_TRANSITIONS[CapabilityState.ARCHIVED] == ()

    def test_full_lifecycle_transition(self):
        """合法全链路: DRAFT → ACTIVE → DEPRECATED → ARCHIVED。"""
        skill = Skill(id="s1", name="x")
        skill = transition_capability(skill, "active")
        assert skill.state == CapabilityState.ACTIVE
        skill = transition_capability(skill, CapabilityState.DEPRECATED)
        assert skill.state == CapabilityState.DEPRECATED
        skill = transition_capability(skill, "archived")
        assert skill.state == CapabilityState.ARCHIVED

    def test_transition_pure_function_returns_new_instance(self):
        """纯函数: 返回新实例, 原对象不变 (同 transition_instance 模式)。"""
        skill = Skill(id="s1", name="x")
        activated = transition_capability(skill, "active")
        assert skill.state == CapabilityState.DRAFT
        assert activated.state == CapabilityState.ACTIVE

    def test_skip_level_transition_rejected(self):
        """跳级拒绝: DRAFT → ARCHIVED 非法 (受控表无此路径)。"""
        skill = Skill(id="s1", name="x")
        with pytest.raises(ValueError):
            transition_capability(skill, "archived")

    def test_backward_transition_rejected(self):
        """回退拒绝: ACTIVE → DRAFT 非法。"""
        skill = transition_capability(Skill(id="s1", name="x"), "active")
        with pytest.raises(ValueError):
            transition_capability(skill, "draft")

    def test_same_state_transition_rejected(self):
        """同态拒绝: ACTIVE → ACTIVE 非法。"""
        skill = transition_capability(Skill(id="s1", name="x"), "active")
        with pytest.raises(ValueError):
            transition_capability(skill, "active")

    def test_archived_is_terminal(self):
        """archived 终态: 任何转换 (含回退) 一律拒绝。"""
        skill = transition_capability(
            transition_capability(
                transition_capability(Skill(id="s1", name="x"), "active"),
                "deprecated",
            ),
            "archived",
        )
        assert skill.state == CapabilityState.ARCHIVED
        for target in ("draft", "active", "deprecated", "archived"):
            with pytest.raises(ValueError):
                transition_capability(skill, target)

    def test_transition_applies_to_all_six_entities(self):
        """六实体统一生命周期: transition_capability 对 Skill/Agent/MCP/
        WorkflowTemplate/Industry/LLMConfig 通用。"""
        entities: list[Any] = [
            Skill(id="s1", name="x"),
            Agent(id="a1", name="x"),
            MCP(id="m1", name="x"),
            WorkflowTemplate(id="w1", name="x"),
            Industry(id="i1", name="x"),
            LLMConfig(id="l1"),
        ]
        for entity in entities:
            activated = transition_capability(entity, "active")
            assert activated.state == CapabilityState.ACTIVE
            assert entity.state == CapabilityState.DRAFT  # 原对象不变


# ------------------------------------------------------------------ enabled 独立运行开关


class TestCapabilitySelectable:
    def test_active_and_enabled_selectable(self):
        """ACTIVE + enabled=true → 可被 binding 选用。"""
        skill = Skill(id="s1", name="x", enabled=True, state="active")
        assert capability_selectable(skill) is True

    def test_active_but_disabled_not_selectable(self):
        """ACTIVE + enabled=false → 运行开关关闭, 不可选 (enabled 独立于 state)。"""
        skill = Skill(id="s1", name="x", enabled=False, state="active")
        assert capability_selectable(skill) is False

    def test_non_active_states_not_selectable(self):
        """DRAFT / DEPRECATED / ARCHIVED 一律不可选 (即使 enabled=True)。"""
        draft = Skill(id="s1", name="x", enabled=True)  # DRAFT
        deprecated = Skill(id="s2", name="x", enabled=True, state="deprecated")
        archived = Skill(id="s3", name="x", enabled=True, state="archived")
        assert capability_selectable(draft) is False
        assert capability_selectable(deprecated) is False
        assert capability_selectable(archived) is False

    def test_selectable_applies_to_all_entities(self):
        """可选性判定六实体通用 (模块级纯函数)。"""
        entities: list[Any] = [
            Skill(id="s1", name="x", enabled=True, state="active"),
            Agent(id="a1", name="x", enabled=True, state="active"),
            MCP(id="m1", name="x", enabled=True, state="active"),
            WorkflowTemplate(id="w1", name="x", enabled=True, state="active"),
            Industry(id="i1", name="x", enabled=True, state="active"),
            LLMConfig(id="l1", enabled=True, state="active"),
        ]
        for entity in entities:
            assert capability_selectable(entity) is True
        assert capability_selectable(Skill(id="s1", name="x", state="active")) is True
        assert capability_selectable(
            Skill(id="s1", name="x", enabled=False, state="active")
        ) is False


# ------------------------------------------------------------------ CapabilityBinding


class TestCapabilityBinding:
    def test_binding_full_fields(self):
        """CapabilityBinding 全字段: {type, id, version?} (设计 §四 v1.1)。"""
        binding = CapabilityBinding(type="skill", id="skill-backend", version="1.2.0")
        assert binding.type == BindingType.SKILL
        assert binding.id == "skill-backend"
        assert binding.version == "1.2.0"
        d = binding.to_dict()
        assert d["type"] == "skill"
        assert d["id"] == "skill-backend"
        assert d["version"] == "1.2.0"

    def test_binding_version_optional_legacy_compat(self):
        """历史 binding 无 version → None, 零破坏 (version 可选)。"""
        binding = CapabilityBinding.model_validate({"type": "agent", "id": "agent-pm"})
        assert binding.type == BindingType.AGENT
        assert binding.id == "agent-pm"
        assert binding.version is None

    def test_binding_type_values(self):
        """type 合法值: agent/skill/mcp/workflow。"""
        assert BindingType.parse("agent") == BindingType.AGENT
        assert BindingType.parse("skill") == BindingType.SKILL
        assert BindingType.parse("mcp") == BindingType.MCP
        assert BindingType.parse("workflow") == BindingType.WORKFLOW

    def test_binding_type_parse_case_insensitive(self):
        assert CapabilityBinding(type="SKILL", id="x").type == BindingType.SKILL
        assert CapabilityBinding(type="Agent", id="x").type == BindingType.AGENT

    def test_binding_illegal_type_rejected(self):
        """非法 type (如 llm-config / industry) 拒绝。"""
        with pytest.raises(ValidationError):
            CapabilityBinding(type="llm-config", id="x")
        with pytest.raises(ValidationError):
            CapabilityBinding(type="industry", id="x")
        with pytest.raises(ValidationError):
            CapabilityBinding(type="bogus", id="x")

    def test_binding_missing_type_rejected(self):
        with pytest.raises(ValidationError):
            CapabilityBinding(id="x")

    def test_binding_empty_id_rejected(self):
        """id 非空校验: 空串/空白/缺失 一律拒绝。"""
        with pytest.raises(ValidationError):
            CapabilityBinding(type="skill", id="")
        with pytest.raises(ValidationError):
            CapabilityBinding(type="skill", id="   ")
        with pytest.raises(ValidationError):
            CapabilityBinding(type="skill")

    def test_binding_in_agent_entity_json_roundtrip(self):
        """Agent.skill_bindings 内嵌 CapabilityBinding: dict 输入 → 实体,
        to_dict JSON 干净 (Registry 落盘可复现)。"""
        agent = Agent(
            id="a1",
            name="x",
            skill_bindings=[
                {"type": "skill", "id": "s1", "version": "1.0.0"},
                {"type": "skill", "id": "s2"},
            ],
        )
        assert agent.skill_bindings[0].version == "1.0.0"
        assert agent.skill_bindings[1].version is None
        d = agent.to_dict()
        assert d["skill_bindings"] == [
            {"type": "skill", "id": "s1", "version": "1.0.0"},
            {"type": "skill", "id": "s2", "version": None},
        ]
