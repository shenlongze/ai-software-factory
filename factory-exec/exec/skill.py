"""factory-exec/exec/skill.py — S10-019 Task 001 Skill System Foundation。

设计依据 (S10-019-task001 用户约束 + S10-018 Tool Runtime 侦察):
```
Agent → Skill (职业能力组合) → Tool (原子能力) → Execution
              ↑
        SkillRegistry (注册表) + SkillContext (执行上下文)
```
目标: 从「Tool 原子能力」升级到「职业能力模型」— Skill = 可执行职业能力
组合 (Agent 拥有 Skill → Skill 决定可用 Tool / 行为规则 / 权限范围)。
**不实现** MCP / Multi Agent / Memory / Learning Loop / 自动 Skill 生成 /
复杂 Workflow Engine — 只建 Skill 基础模型 (组合与约束层)。

职责 (纯内部域模型 — 不绑第三方, 同 Tool 设计):
- Skill: id/name/description/version/category/tools (list[str] — Tool id
  引用)/instructions (行为规则)/permissions (Skill 级最小权限)/enabled/
  metadata — 协议无关, 未来 MCP/API Skill 都以本模型注册。
- SkillPermissionPolicy: 最小权限表 (allowed_agent_ids 白名单 / allow_all
  显式开放); 默认全部禁止 (同 ToolPermissionPolicy 语义)。
- SkillContext: {active_skill, instructions, available_tools, constraints}
  — 传给 AgentExecutionLoop / Planner 的职业能力上下文 (当前 Agent 会什么/
  怎么干/能碰什么/不能碰什么)。
- SkillRegistry: register (id 冲突 → SkillConflictError 响亮) / unregister
  (不存在 → SkillNotFoundError) / get / list (id 排序) / validate (字段
  完整性 + tools 引用存在性 — 装配 tool_registry 时校验); 启动加载系统
  Skill (with_system_skills → backend.development/testing/flutter.development,
  均含 tools: [filesystem.read])。
- 权限链 (Agent has Skill → Skill includes Tool → Tool Permission allows):
  check_tool_access(agent_id, agent_skills, tool_id) → "" 放行 / 明确拒绝
  信息 (403 语义, 不静默) — 三环任一失败即拒绝, 失败原因可审计。
- 系统 Agent 分配: SYSTEM_AGENT_SKILLS (backend-1→backend.development /
  tester-1→testing / flutter-dev→flutter.development); resolve_agent_skills
  读 agent.skills (已注册 id 优先) → 系统映射兜底 → [] (Agent 只能使用
  自身 Skill, 无 Skill → 权限链全拒)。

依赖 (Removal Isolation): 只 import stdlib + pydantic + 本层 tool 模型
(exec.tool — Tool/ToolRegistry/ToolPermissionPolicy); 不触碰
agent_runtime.py / provider.py 主逻辑。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .tool import Tool, ToolPermissionPolicy, ToolRegistry

#: Skill 行为约束 (SkillContext.constraints — 职业能力边界, 透传 Planner)。
SKILL_CONSTRAINTS: tuple[str, ...] = (
    "只使用当前 Skill 声明的 Tool (技能决定可用工具边界)",
    "遵循 Skill instructions 行为规则 (职业行为约束)",
    "禁止越权使用未分配 Skill 的能力 (最小权限铁律)",
)


class SkillError(Exception):
    """Skill 业务错误基类 (注册/校验/查找 — 响亮, 不静默)。"""


class SkillConflictError(SkillError):
    """Skill id 冲突 (register 同 id 二次 — 响亮, 不静默覆盖)。"""


class SkillNotFoundError(SkillError):
    """Skill 不存在 (unregister/API 404 语义)。"""


class SkillValidationError(SkillError):
    """Skill 校验失败 (字段不完整 / tools 引用不存在 — 注册前拒绝)。"""


class SkillPermissionPolicy(BaseModel):
    """Skill 权限策略 (最小权限表 — 默认全部禁止)。

    allowed_agent_ids: 允许使用本 Skill 的 agent id 白名单 (backend-1 →
    backend.development; 其他 Agent 默认禁止)。
    allow_all: 显式开放开关 (未来内部/系统 Skill 用; 默认 False = 最小权限)。
    """

    model_config = ConfigDict(extra="forbid")

    allowed_agent_ids: list[str] = Field(default_factory=list)
    allow_all: bool = False

    def allows(self, agent_id: str) -> bool:
        """agent 是否允许使用本 Skill (allow_all → 放行; 否则白名单命中)。"""
        if self.allow_all:
            return True
        return agent_id in self.allowed_agent_ids


class Skill(BaseModel):
    """Skill Domain Model (职业能力组合 — Tool 之上的组合与约束层)。

    id: 唯一标识 ("backend.development" — 点分命名, 职业前缀); name/
    description: 人话元信息; version: 技能版本; category: 职业类别;
    tools: 可用 Tool id 引用列表 (Skill 决定可用工具边界); instructions:
    行为规则 (职业行为约束, 传给 Planner); permissions: Skill 级最小权限
    (可选附加约束); enabled: 开关 (false → 执行前拒绝); metadata: 扩展
    元信息 (owner/标签等, 未来 Skill 市场/MCP 预留)。
    未来兼容: MCP/API Skill 都以本模型注册 (type 字段后续扩展, 本 Task
    不实现)。
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    category: str = ""
    tools: list[str] = Field(default_factory=list)
    instructions: str = ""
    permissions: SkillPermissionPolicy = Field(default_factory=SkillPermissionPolicy)
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _tools_dedup(self) -> "Skill":
        """tools 保序去重 (引用列表干净, 权限链遍历无重复)。"""
        if len(self.tools) != len(dict.fromkeys(self.tools)):
            self.tools = list(dict.fromkeys(self.tools))
        return self


class SkillContext(BaseModel):
    """Skill 执行上下文 (职业能力快照 — 传给 AgentExecutionLoop/Planner)。

    active_skill: 当前激活 Skill id ("" = 无技能 — 权限链全拒); instructions:
    行为规则 (来自 Skill.instructions); available_tools: 可用 Tool id 列表
    (Skill.tools 投影); constraints: 行为约束 (职业能力边界)。
    """

    model_config = ConfigDict(extra="forbid")

    active_skill: str = ""
    instructions: str = ""
    available_tools: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class SkillRegistry:
    """Skill 注册表: register/unregister/get/list/validate + 启动加载系统 Skill。

    - register: id 冲突 → SkillConflictError (响亮, 不静默覆盖); 校验失败 →
      SkillValidationError (注册前拒绝非法 Skill)。
    - unregister: 不存在 id → SkillNotFoundError (响亮)。
    - list: 全部 Skill (含 disabled), 按 id 排序 (审计友好)。
    - validate: 字段完整性 (id/name 非空 + tools 列表) + tools 引用存在性
      (装配 tool_registry 时 — 引用不存在的 Tool → 注册前拒绝; 无
      tool_registry → 宽容, 运行时由权限链兜底)。
    - with_system_skills: 启动时加载系统 Skill (backend.development /
      testing / flutter.development — 均含 tools: [filesystem.read])。
    - check_tool_access: 权限链 (Agent has Skill → Skill includes Tool →
      Tool Permission allows); 任一失败 → 明确拒绝信息 (403 语义)。
    """

    def __init__(self, tool_registry: ToolRegistry | None = None) -> None:
        self._skills: dict[str, Skill] = {}
        self._tool_registry = tool_registry

    @property
    def tool_registry(self) -> ToolRegistry | None:
        """关联 ToolRegistry (权限链环 3 校验数据源; None → 环 3 宽容)。"""
        return self._tool_registry

    # ------------------------------------------------------------------ 校验

    def validate(self, skill: Skill) -> None:
        """Skill 合法性校验 (字段完整性 + tools 引用存在性)。

        字段: id/name 非空 + tools 必须 list[str]; 引用: 装配 tool_registry
        时校验每个 tool id 存在 (Skill 组合不能引用幽灵 Tool)。
        """
        if not skill.id or not str(skill.id).strip():
            raise SkillValidationError("skill id must not be empty")
        if not skill.name or not str(skill.name).strip():
            raise SkillValidationError(f"skill {skill.id!r}: name must not be empty")
        if not isinstance(skill.tools, list) or any(
            not isinstance(t, str) or not t.strip() for t in skill.tools
        ):
            raise SkillValidationError(
                f"skill {skill.id!r}: tools must be a list of non-empty tool ids"
            )
        if self._tool_registry is not None:
            for tool_id in skill.tools:
                if self._tool_registry.get(tool_id) is None:
                    raise SkillValidationError(
                        f"skill {skill.id!r}: tool {tool_id!r} not found in tool registry"
                    )

    # ------------------------------------------------------------------ CRUD

    def register(self, skill: Skill) -> Skill:
        """注册 Skill (id 冲突 → SkillConflictError 响亮; 校验失败 → 拒绝)。"""
        self.validate(skill)
        if skill.id in self._skills:
            raise SkillConflictError(f"skill already registered: {skill.id}")
        self._skills[skill.id] = skill
        return skill

    def unregister(self, skill_id: str) -> None:
        """注销 Skill (不存在 → SkillNotFoundError 响亮)。"""
        if skill_id not in self._skills:
            raise SkillNotFoundError(f"skill not found: {skill_id}")
        del self._skills[skill_id]

    def get(self, skill_id: str) -> Skill | None:
        """按 id 取 Skill (不存在 → None — 查询语义)。"""
        return self._skills.get(skill_id)

    def list(self) -> list[Skill]:
        """全部 Skill (含 disabled), 按 id 排序。"""
        return [self._skills[sid] for sid in sorted(self._skills)]

    # ------------------------------------------------------------------ 系统 Skill

    @classmethod
    def with_system_skills(
        cls, tool_registry: ToolRegistry | None = None
    ) -> "SkillRegistry":
        """启动加载系统 Skill (本 Task: 3 个职业 Skill — 组合与约束层)。"""
        registry = cls(tool_registry=tool_registry)
        for skill in build_system_skills():
            registry.register(skill)
        return registry

    # ------------------------------------------------------------------ 权限链

    def check_tool_access(
        self, agent_id: str, agent_skills: list[str], tool_id: str
    ) -> str:
        """权限链: Agent has Skill → Skill includes Tool → Tool Permission
        allows; 放行 → ""; 任一环失败 → 明确拒绝信息 (403 语义, 不静默)。

        环 1: Agent 必须拥有 Skill (无技能 / 技能未命中 → 拒绝)。
        环 2: Skill 必须包含该 Tool (Skill 决定可用工具边界)。
        环 3: Tool 最小权限表必须允许该 Agent (Tool 是最终边界; 未装配
        tool_registry 时环 3 宽容 — 由 ToolExecutor 自身校验兜底)。
        """
        agent = str(agent_id or "").strip()
        # 环 1: Agent has Skill
        skills = [s for s in (agent_skills or []) if isinstance(s, str) and s.strip()]
        if not skills:
            return (
                f"skill permission denied: agent {agent or '(unknown)'} has no skills"
            )
        # 环 2: Skill includes Tool (遍历 agent 技能找第一个包含该 Tool 的)
        candidate: Skill | None = None
        for sid in skills:
            skill = self._skills.get(sid)
            if skill is not None and tool_id in skill.tools:
                candidate = skill
                break
        if candidate is None:
            return (
                f"skill permission denied: agent {agent or '(unknown)'} skills "
                f"do not include tool {tool_id!r}"
            )
        if not candidate.enabled:
            return f"skill permission denied: skill {candidate.id!r} is disabled"
        if not candidate.permissions.allows(agent):
            return (
                f"skill permission denied: agent {agent or '(unknown)'} is not "
                f"allowed to use skill {candidate.id!r}"
            )
        # 环 3: Tool Permission allows (Tool 是最终边界)
        if self._tool_registry is not None:
            tool = self._tool_registry.get(tool_id)
            if tool is None:
                return (
                    f"skill permission denied: tool {tool_id!r} not found "
                    "in tool registry"
                )
            if not tool.enabled:
                return f"tool permission denied: tool {tool_id!r} is disabled"
            if not tool.permission_policy.allows(agent):
                return (
                    f"tool permission denied: agent {agent or '(unknown)'} is not "
                    f"allowed to use tool {tool_id!r}"
                )
        return ""


# ------------------------------------------------------------------ 系统 Skill 种子


def _default_skill(
    skill_id: str,
    name: str,
    description: str,
    category: str,
    instructions: str,
    *,
    tool_ids: tuple[str, ...] = ("filesystem.read",),
) -> Skill:
    """系统 Skill 构造 (默认含 filesystem.read — 任务约束 8: 三个内置 Skill
    均含 filesystem.read; permissions 默认 allow_all=False — Skill 级最小
    权限由系统分配表 (SYSTEM_AGENT_SKILLS) 约束, 不重复设白名单)。"""
    return Skill(
        id=skill_id,
        name=name,
        description=description,
        version="1.0.0",
        category=category,
        tools=list(tool_ids),
        instructions=instructions,
        # permissions 显式开放 (allow_all=True): 谁拥有该 Skill 由系统分配表
        # (SYSTEM_AGENT_SKILLS) 决定 — 权限链环 1 (Agent has Skill) 是 gate,
        # Skill 级白名单不再重复限制 (KISS)。
        permissions=SkillPermissionPolicy(allow_all=True),
        enabled=True,
        metadata={"system": True, "builtin": True},
    )


def build_system_skills() -> list[Skill]:
    """构建系统 Skill 列表 (backend.development/testing/flutter.development —
    均含 tools: [filesystem.read] + 职业行为指令)。"""
    return [
        _default_skill(
            "backend.development",
            "Backend Development",
            "后端开发职业能力: 服务端 API/数据库/CLI/服务器运维 (Java/Python/Shell)",
            "software-development",
            "You are a backend developer. 遵循后端工程实践: 服务端 API/数据库/"
            "CLI/服务器运维。只使用当前 Skill 声明的 Tool 完成工作, 遵守"
            "workspace 沙箱边界, 不访问任意系统路径。",
        ),
        _default_skill(
            "testing",
            "Software Testing",
            "测试职业能力: 功能/压力/自动化测试与 PRD 验收",
            "software-development",
            "You are a test engineer. 遵循测试实践: 功能/压力/自动化测试与"
            "PRD 验收。只使用当前 Skill 声明的 Tool 完成工作, 遵守 workspace"
            "沙箱边界, 不访问任意系统路径。",
        ),
        _default_skill(
            "flutter.development",
            "Flutter Development",
            "Flutter 跨平台开发职业能力: Dart/UI/状态管理/构建",
            "software-development",
            "You are a Flutter developer. 遵循 Flutter 工程实践: Dart/UI/"
            "状态管理/构建。只使用当前 Skill 声明的 Tool 完成工作, 遵守"
            "workspace 沙箱边界, 不访问任意系统路径。",
        ),
    ]


#: 系统 Agent → Skill 分配表 (任务约束 3: backend-1→backend.development /
#: tester-1→testing / flutter-dev→flutter.development)。Skill 组合由系统
#: 定义, Agent 只能使用自身分配的 Skill (权限链环 1)。
SYSTEM_AGENT_SKILLS: dict[str, tuple[str, ...]] = {
    "backend-1": ("backend.development",),
    "tester-1": ("testing",),
    "flutter-dev": ("flutter.development",),
}


def resolve_agent_skills(agent: Any, registry: SkillRegistry) -> list[str]:
    """解析 Agent 的技能列表 (Agent 只能使用自身 Skill — 权限链数据源)。

    优先级: agent.skills 中已注册的 Skill id (Agent 声明为准, 过滤未注册
    id) → 系统分配表 SYSTEM_AGENT_SKILLS 兜底 (旧自由标签数据兼容) → []
    (无技能 → 权限链全拒)。保序去重。
    """
    declared = [
        s for s in (getattr(agent, "skills", None) or []) if isinstance(s, str)
    ]
    resolved: list[str] = []
    for sid in declared:
        if sid in resolved:
            continue
        if registry.get(sid) is not None:
            resolved.append(sid)
    if not resolved:
        for sid in SYSTEM_AGENT_SKILLS.get(getattr(agent, "id", ""), ()):
            if sid not in resolved and registry.get(sid) is not None:
                resolved.append(sid)
    return resolved


def skill_context_for(
    agent_id: str, agent_skills: list[str], registry: SkillRegistry
) -> SkillContext:
    """Agent 技能 → SkillContext (职业能力快照 — 传给 Planner)。

    active_skill = 第一个已注册技能; instructions/tools 取自该 Skill;
    constraints = 行为约束常量。无技能 → 空 SkillContext (不伪造职业能力,
    权限链全拒)。
    """
    for sid in agent_skills or []:
        skill = registry.get(sid)
        if skill is not None:
            return SkillContext(
                active_skill=skill.id,
                instructions=skill.instructions,
                available_tools=list(skill.tools),
                constraints=list(SKILL_CONSTRAINTS),
            )
    return SkillContext()


__all__ = [
    "SKILL_CONSTRAINTS",
    "SYSTEM_AGENT_SKILLS",
    "Skill",
    "SkillConflictError",
    "SkillContext",
    "SkillError",
    "SkillNotFoundError",
    "SkillPermissionPolicy",
    "SkillRegistry",
    "SkillValidationError",
    "build_system_skills",
    "resolve_agent_skills",
    "skill_context_for",
]
