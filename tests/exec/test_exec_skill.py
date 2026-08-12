"""tests/exec/test_exec_skill.py — S10-019 Task 001 Skill System Foundation 测试。

覆盖 (Skill System — 职业能力组合模型, Tool 之上的组合层):
- Skill Model: id/name/description/version/category/tools/instructions/
  permissions/enabled/metadata 全字段 + 严格模式 (extra=forbid)
- SkillPermissionPolicy: 默认禁止 / allow_all / 白名单 (同 Tool 最小权限语义)
- SkillRegistry: register (id 冲突 → SkillConflictError 响亮) / unregister
  (不存在 → SkillNotFoundError) / get / list (id 排序) / validate (字段
  完整性 + tools 引用存在性 — 装配 tool_registry 时校验)
- 内置 Skill: with_system_skills → backend.development/testing/
  flutter.development 三个 (均含 tools: [filesystem.read] + 行为指令)
- 系统 Agent Skill 分配: backend-1→[backend.development] / tester-1→
  [testing] / flutter-dev→[flutter.development]; resolve_agent_skills 读
  agent.skills (已注册 id 优先) → 系统映射 fallback → [] 兜底
- Permission Chain (Agent has Skill → Skill includes Tool → Tool Permission
  allows): check_tool_access 三环校验, 任一失败 → 明确拒绝信息 (403 语义,
  不静默)
- SkillContext: {active_skill, instructions, available_tools, constraints} —
  传给 AgentExecutionLoop/Planner 的职业能力上下文

basename 全仓库唯一 (test_exec_* 前缀); 依赖 tests/exec/conftest.py 的
sys.path (factory-exec 挂载, `exec` 包导入)。
"""

from __future__ import annotations

import pytest

from exec.skill import (
    SKILL_CONSTRAINTS,
    SYSTEM_AGENT_SKILLS,
    Skill,
    SkillConflictError,
    SkillContext,
    SkillNotFoundError,
    SkillPermissionPolicy,
    SkillRegistry,
    SkillValidationError,
    build_system_skills,
    resolve_agent_skills,
    skill_context_for,
)
from exec.tool import Tool, ToolExecutor, ToolPermissionPolicy, ToolRegistry


# ------------------------------------------------------------------ Skill Model


class TestSkillModel:
    def test_skill_full_fields(self):
        """Skill 全字段构造 (id/name/description/version/category/tools/
        instructions/permissions/enabled/metadata — 任务约束字段齐备)。"""
        skill = Skill(
            id="backend.development",
            name="Backend Development",
            description="后端开发职业能力",
            version="1.0.0",
            category="software-development",
            tools=["filesystem.read"],
            instructions="You are a backend developer...",
            permissions=SkillPermissionPolicy(allowed_agent_ids=["backend-1"]),
            enabled=True,
            metadata={"owner": "it-department"},
        )

        assert skill.id == "backend.development"
        assert skill.name == "Backend Development"
        assert skill.version == "1.0.0"
        assert skill.category == "software-development"
        assert skill.tools == ["filesystem.read"]
        assert "backend developer" in skill.instructions.lower()
        assert skill.permissions.allowed_agent_ids == ["backend-1"]
        assert skill.enabled is True
        assert skill.metadata == {"owner": "it-department"}

    def test_skill_defaults(self):
        """Skill 缺省值: tools/instructions/permissions 等容器字段不 None
        (无 None 陷阱); permissions 默认全部禁止 (最小权限)。"""
        skill = Skill(id="testing", name="Testing")

        assert skill.tools == []
        assert skill.instructions == ""
        assert skill.permissions.allows("anyone") is False
        assert skill.enabled is True
        assert skill.metadata == {}

    def test_skill_extra_field_forbidden(self):
        """Skill 严格字段 (extra=forbid — 未知字段响亮拒绝, 不静默吞)。"""
        with pytest.raises(ValueError):
            Skill(id="x", name="X", not_a_field=True)  # type: ignore[call-arg]

    def test_permission_policy_default_deny(self):
        """SkillPermissionPolicy 默认全部禁止; allow_all 显式放行; 白名单命中。"""
        policy = SkillPermissionPolicy()
        assert policy.allows("backend-1") is False

        open_policy = SkillPermissionPolicy(allow_all=True)
        assert open_policy.allows("backend-1") is True

        whitelist = SkillPermissionPolicy(allowed_agent_ids=["backend-1"])
        assert whitelist.allows("backend-1") is True
        assert whitelist.allows("flutter-dev") is False


# ------------------------------------------------------------------ SkillRegistry


class TestSkillRegistry:
    def test_register_get_list_unregister(self):
        """register → get 返回同对象; list id 排序; unregister 移除。"""
        registry = SkillRegistry()
        skill = Skill(id="testing", name="Testing", tools=["filesystem.read"])

        registry.register(skill)

        assert registry.get("testing") is skill
        assert registry.get("missing") is None
        assert registry.list() == [skill]
        registry.unregister("testing")
        assert registry.get("testing") is None
        assert registry.list() == []

    def test_register_conflict_raises_loudly(self):
        """register 同 id 二次 → SkillConflictError (响亮, 不静默覆盖)。"""
        registry = SkillRegistry()
        registry.register(Skill(id="testing", name="Testing"))

        with pytest.raises(SkillConflictError, match="already registered"):
            registry.register(Skill(id="testing", name="Testing v2"))

    def test_unregister_missing_raises_loudly(self):
        """unregister 不存在 id → SkillNotFoundError (响亮)。"""
        registry = SkillRegistry()
        with pytest.raises(SkillNotFoundError):
            registry.unregister("no-such-skill")

    def test_validate_rejects_empty_id_and_name(self):
        """validate: 空 id/name → SkillValidationError (字段完整性)。"""
        registry = SkillRegistry()
        with pytest.raises(SkillValidationError):
            registry.register(Skill(id="", name="X"))
        with pytest.raises(SkillValidationError):
            registry.register(Skill(id="x", name=""))

    def test_validate_checks_tool_references(self):
        """validate/register: tools 引用存在性 — 装配 tool_registry 时校验
        (引用不存在的 Tool → SkillValidationError; 无 tool_registry → 宽容)。"""
        tool_registry = ToolRegistry()
        tool_registry.register(
            Tool(
                id="filesystem.read",
                name="Filesystem Read",
                handler=lambda i, c: {"content": ""},
            )
        )
        registry = SkillRegistry(tool_registry=tool_registry)

        # 引用存在 → 通过
        registry.register(Skill(id="testing", name="Testing", tools=["filesystem.read"]))
        # 引用不存在 → 响亮拒绝
        with pytest.raises(SkillValidationError, match="filesystem.write"):
            registry.register(
                Skill(id="backend.development", name="Backend", tools=["filesystem.write"])
            )

    def test_list_sorted_by_id(self):
        """list 按 id 排序 (确定性, 审计友好)。"""
        registry = SkillRegistry()
        for sid in ("testing", "backend.development", "flutter.development"):
            registry.register(Skill(id=sid, name=sid))

        assert [s.id for s in registry.list()] == [
            "backend.development",
            "flutter.development",
            "testing",
        ]


# ------------------------------------------------------------------ 内置 Skill


class TestSystemSkills:
    def test_build_system_skills_three_skills(self):
        """内置 3 Skill: backend.development/testing/flutter.development,
        均含 tools: [filesystem.read] + 行为指令 (任务约束 8)。"""
        skills = build_system_skills()

        assert {s.id for s in skills} == {
            "backend.development",
            "testing",
            "flutter.development",
        }
        for skill in skills:
            assert "filesystem.read" in skill.tools
            assert skill.instructions.strip(), f"{skill.id} 缺行为指令"
            assert skill.enabled is True
            assert skill.category

    def test_with_system_skills_registry(self):
        """SkillRegistry.with_system_skills → 3 内置 Skill 就绪 (启动加载)。"""
        registry = SkillRegistry.with_system_skills()

        assert [s.id for s in registry.list()] == [
            "backend.development",
            "flutter.development",
            "testing",
        ]
        assert registry.get("backend.development") is not None
        assert registry.get("testing") is not None
        assert registry.get("flutter.development") is not None


# ------------------------------------------------------------------ 系统 Agent Skill 分配


class TestAgentSkillAssignment:
    def test_system_agent_skills_mapping(self):
        """系统 Agent → Skill 分配表: backend-1→[backend.development] /
        tester-1→[testing] / flutter-dev→[flutter.development] (任务约束 3)。"""
        assert SYSTEM_AGENT_SKILLS["backend-1"] == ("backend.development",)
        assert SYSTEM_AGENT_SKILLS["tester-1"] == ("testing",)
        assert SYSTEM_AGENT_SKILLS["flutter-dev"] == ("flutter.development",)

    def test_resolve_agent_skills_uses_agent_skills_first(self):
        """resolve_agent_skills: agent.skills 中已注册 skill id 优先 (Agent
        声明为准); 与系统映射合并去重 (系统映射兜底, 不丢职业能力)。"""

        class _Agent:
            id = "backend-1"
            skills = ["backend.development"]

        registry = SkillRegistry.with_system_skills()

        skills = resolve_agent_skills(_Agent(), registry)

        assert skills == ["backend.development"]

    def test_resolve_agent_skills_fallback_system_mapping(self):
        """agent.skills 未含系统 skill id (旧自由标签) → 系统映射兜底:
        backend-1 → [backend.development]。"""

        class _Agent:
            id = "backend-1"
            skills = ["development", "python"]  # 旧自由标签, 非系统 skill id

        registry = SkillRegistry.with_system_skills()

        assert resolve_agent_skills(_Agent(), registry) == ["backend.development"]

    def test_resolve_agent_skills_empty_when_no_skill(self):
        """agent 无 skills 且不在系统映射 → [] (无技能 → 权限链全拒)。"""

        class _Agent:
            id = "stranger-9"
            skills = []

        registry = SkillRegistry.with_system_skills()

        assert resolve_agent_skills(_Agent(), registry) == []

    def test_resolve_agent_skills_filters_unregistered(self):
        """agent.skills 中未注册的 skill id 被过滤 (只保留注册表内的)。"""

        class _Agent:
            id = "backend-1"
            skills = ["backend.development", "ghost.skill"]

        registry = SkillRegistry.with_system_skills()

        assert resolve_agent_skills(_Agent(), registry) == ["backend.development"]


# ------------------------------------------------------------------ Permission Chain


class TestSkillPermissionChain:
    """权限链 (Agent has Skill → Skill includes Tool → Tool Permission allows):
    任一环失败 → 明确拒绝信息 (403 语义, 不静默)。"""

    @staticmethod
    def _registry_with_tool(*, tool_allowed: str) -> SkillRegistry:
        """带 filesystem.read Tool 的 SkillRegistry (backend-1 白名单可调)。"""
        tool_registry = ToolRegistry()
        tool_registry.register(
            Tool(
                id="filesystem.read",
                name="Filesystem Read",
                handler=lambda i, c: {"content": ""},
                permission_policy=ToolPermissionPolicy(
                    allowed_agent_ids=[tool_allowed]
                ),
            )
        )
        return SkillRegistry.with_system_skills(tool_registry=tool_registry)

    def test_agent_has_no_skill_rejected(self):
        """环 1 失败: Agent 无任何 Skill → 明确拒绝 (不静默放行)。"""
        registry = self._registry_with_tool(tool_allowed="backend-1")

        error = registry.check_tool_access("backend-1", [], "filesystem.read")

        assert error
        assert "no skills" in error.lower()

    def test_skill_does_not_include_tool_rejected(self):
        """环 2 失败: Skill 不含该 Tool → 明确拒绝 (Skill 决定可用 Tool)。"""
        registry = SkillRegistry()
        registry.register(
            Skill(id="backend.development", name="Backend", tools=["filesystem.read"])
        )
        registry.register(
            Skill(id="testing", name="Testing", tools=["filesystem.read"])
        )

        error = registry.check_tool_access(
            "backend-1", ["testing"], "ghost.tool"
        )

        assert error
        assert "not include" in error.lower()

    def test_tool_permission_denied_rejected(self):
        """环 3 失败: Tool 最小权限表不允许 agent → 明确拒绝 (Tool 权限
        是最终边界)。"""
        registry = self._registry_with_tool(tool_allowed="backend-1")

        error = registry.check_tool_access(
            "flutter-dev", ["flutter.development"], "filesystem.read"
        )

        assert error
        assert "permission denied" in error.lower()
        assert "flutter-dev" in error

    def test_tool_reference_resolved_allowed(self):
        """Skill 引用的 Tool 在注册表存在 + 权限允许 → 放行 (环 2/3 通过)。"""
        registry = self._registry_with_tool(tool_allowed="backend-1")

        error = registry.check_tool_access(
            "backend-1", ["backend.development"], "filesystem.read"
        )

        assert error == ""  # 系统 skill 引用存在 → 放行

    def test_full_chain_allowed(self):
        """完整权限链通过: Agent has Skill (backend.development) → Skill
        includes Tool (filesystem.read) → Tool Permission allows (backend-1)
        → 放行 (error == "")。"""
        registry = self._registry_with_tool(tool_allowed="backend-1")

        error = registry.check_tool_access(
            "backend-1", ["backend.development"], "filesystem.read"
        )

        assert error == ""

    def test_disabled_skill_rejected(self):
        """Skill enabled=false → 明确拒绝 (Skill 开关是执行前置)。"""
        registry = SkillRegistry()
        registry.register(
            Skill(
                id="backend.development",
                name="Backend",
                tools=["filesystem.read"],
                enabled=False,
            )
        )

        error = registry.check_tool_access(
            "backend-1", ["backend.development"], "filesystem.read"
        )

        assert error
        assert "disabled" in error.lower()


# ------------------------------------------------------------------ SkillContext


class TestSkillContext:
    def test_skill_context_fields(self):
        """SkillContext 全字段: {active_skill, instructions, available_tools,
        constraints} (任务约束 5 — 传给 AgentExecutionLoop 的职业能力上下文)。"""
        ctx = SkillContext(
            active_skill="backend.development",
            instructions="You are a backend developer...",
            available_tools=["filesystem.read"],
            constraints=["workspace 沙箱内只读"],
        )

        assert ctx.active_skill == "backend.development"
        assert "backend developer" in ctx.instructions.lower()
        assert ctx.available_tools == ["filesystem.read"]
        assert ctx.constraints == ["workspace 沙箱内只读"]

    def test_skill_context_defaults(self):
        """SkillContext 缺省: 空技能/空指令/空工具/空约束 (无 None 陷阱)。"""
        ctx = SkillContext()

        assert ctx.active_skill == ""
        assert ctx.instructions == ""
        assert ctx.available_tools == []
        assert ctx.constraints == []

    def test_skill_context_for_agent(self):
        """skill_context_for: agent + skills + registry → SkillContext
        (active_skill = 第一个 skill; instructions/tools/constraints 落位)。"""
        registry = SkillRegistry.with_system_skills()
        ctx = skill_context_for("backend-1", ["backend.development"], registry)

        assert ctx.active_skill == "backend.development"
        assert ctx.available_tools == ["filesystem.read"]
        assert ctx.instructions
        assert ctx.constraints == list(SKILL_CONSTRAINTS)

    def test_skill_context_for_no_skill(self):
        """无 skill → 空 SkillContext (active_skill="" — 不伪造职业能力)。"""
        registry = SkillRegistry.with_system_skills()
        ctx = skill_context_for("stranger-9", [], registry)

        assert ctx.active_skill == ""
        assert ctx.available_tools == []
        assert ctx.instructions == ""

    def test_skill_context_serializable(self):
        """SkillContext model_dump → dict (Planner 上下文 JSON 友好)。"""
        ctx = skill_context_for(
            "backend-1", ["backend.development"], SkillRegistry.with_system_skills()
        )

        data = ctx.model_dump()
        assert data["active_skill"] == "backend.development"
        assert isinstance(data["available_tools"], list)
