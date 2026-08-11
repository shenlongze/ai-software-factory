"""factory-org/org/capabilities.py — Capability Domain Model (S10-012 Task 001)。

设计依据 (唯一):
- docs/sprint10/S10-012-architecture-design.md §二 (六实体字段) + §四 (v1.1:
  CapabilityBinding {type, id, version?} — version 可复现, 历史 binding 兼容)
  + §四b (v1.1: CapabilityState 生命周期, archived 终态, enabled 独立运行开关)

模型:
- 六实体 (Factory Capability Pool 公共注册表实体 — 只建实体不实现逻辑):
  Skill: id/name/description/category/input_schema/output_schema/version/enabled/state
  Agent: id/name/role/description/skill_bindings/workflow_bindings/llm_config/enabled/state
  MCP:   id/name/type/endpoint/auth_config/capabilities/enabled/state
  WorkflowTemplate: id/name/industry/steps/required_agents/required_skills/enabled/state
  Industry: id/name/description/workflow_templates/enabled/state
  LLMConfig: id/provider/model/endpoint/parameters/enabled/state
- CapabilityState 统一生命周期 (所有 Capability 实体):
  DRAFT → ACTIVE → DEPRECATED → ARCHIVED (受控单向 — CAPABILITY_STATE_TRANSITIONS
  定义合法路径, 跳级/回退/同态/终态后一律 ValueError; archived 终态不可逆)
  - enabled (bool) 独立运行开关: capability_selectable = ACTIVE 且 enabled=True
    (ACTIVE+enabled=false 不可选; DRAFT/DEPRECATED/ARCHIVED 一律不可选)
  - transition_capability 纯函数 (返回新实例, 原对象不变 — 同 execution.py
    transition_instance 模式)
- CapabilityBinding (Project.binding 引用, 非复制): {type: agent|skill|mcp|
  workflow, id 非空, version?} — version 可选 (历史 binding 无 version → None,
  零破坏; 能力持续升级时 binding 可 pin version 保持可复现)

宽松解析: 旧数据 (无 state/enabled 字段) → 默认 DRAFT + enabled=True, 零破坏。

约束: 本模块零 Core 依赖 (stdlib + pydantic + org.models, Removal Isolation);
Task 002 已实现 skills/ 目录信源 Registry CRUD + 默认种子; Task 003 已实现
agents/ 目录信源 Registry CRUD (register/get/list/update/delete + 生命周期 +
binding 校验 + 默认种子 5 角色); Task 004 已实现 mcps/ 目录信源 Registry
CRUD (register/get/list/update/delete + 生命周期 — MCP 不预置种子,
外部工具由用户注册); Task 005 已实现 workflows/ 目录信源 Registry CRUD
(register/get/list/update/delete + 生命周期 + steps 校验 非空/有序/step id
唯一 + required_agents/skills 引用校验 + 默认种子 software-development-lifecycle);
Task 006 才实现 industries/llm-configs 注册。
"""

from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from pydantic import Field, field_validator

from .models import _OrgModel, _norm_list

# ------------------------------------------------------------------ 枚举


class CapabilityState(str, Enum):
    """Capability 生命周期状态 (S10-012 §四b: 受控单向, archived 终态)。

    DRAFT → ACTIVE → DEPRECATED → ARCHIVED; 所有 Capability 实体
    (Skill/Agent/MCP/WorkflowTemplate/Industry/LLMConfig) 统一生命周期。
    """

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"

    @classmethod
    def parse(cls, value: Any) -> "CapabilityState":
        """宽容解析: 大小写不敏感 (ACTIVE → active); 枚举对象直接返回; 非法抛 ValueError。"""
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(
                f"invalid capability state: {value!r} (expected one of: {valid})"
            ) from None


class BindingType(str, Enum):
    """CapabilityBinding.type 合法值 (S10-012 §四: agent|skill|mcp|workflow)。

    Industry/LLMConfig 不作为 binding 类型 — 项目只绑定可执行/可选用能力。
    """

    AGENT = "agent"
    SKILL = "skill"
    MCP = "mcp"
    WORKFLOW = "workflow"

    @classmethod
    def parse(cls, value: Any) -> "BindingType":
        """宽容解析: 大小写不敏感 (SKILL → skill); 枚举对象直接返回; 非法抛 ValueError。"""
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(
                f"invalid capability binding type: {value!r} (expected one of: {valid})"
            ) from None


# ------------------------------------------------------------------ 生命周期


class CapabilityEntity(Protocol):
    """六 Capability 实体通用协议 (S10-012 §四b: 统一 state/enabled 字段)。

    Skill/Agent/MCP/WorkflowTemplate/Industry/LLMConfig 均满足 —
    生命周期转换与可选性判定六实体通用。
    """

    state: CapabilityState
    enabled: bool

    def model_copy(
        self, *, update: dict[str, Any] | None = None, deep: bool = False
    ) -> "CapabilityEntity": ...


#: 受控状态转换表 (S10-012 §四b: 单向, archived 终态无任何合法去向 — 不可逆)。
#: key=当前态, value=合法目标态元组。
CAPABILITY_STATE_TRANSITIONS: dict[CapabilityState, tuple[CapabilityState, ...]] = {
    CapabilityState.DRAFT: (CapabilityState.ACTIVE,),
    CapabilityState.ACTIVE: (CapabilityState.DEPRECATED,),
    CapabilityState.DEPRECATED: (CapabilityState.ARCHIVED,),
    CapabilityState.ARCHIVED: (),
}


def transition_capability(
    capability: CapabilityEntity,
    target: CapabilityState | str,
) -> CapabilityEntity:
    """受控状态转换 (纯函数 — 返回新实例, 原对象不变; 六实体通用)。

    - 目标态不在 CAPABILITY_STATE_TRANSITIONS[当前态] → ValueError
      (跳级/回退/同态/终态后 — 非法拒绝)
    - archived 终态: 无任何合法去向 (不可逆, 可复现)
    """
    from_state = capability.state
    target_state = CapabilityState.parse(target)
    if target_state not in CAPABILITY_STATE_TRANSITIONS[from_state]:
        raise ValueError(
            f"illegal capability state transition: "
            f"{from_state.value} -> {target_state.value} "
            f"(allowed: {[s.value for s in CAPABILITY_STATE_TRANSITIONS[from_state]]})"
        )
    return capability.model_copy(update={"state": target_state})


def capability_selectable(capability: CapabilityEntity) -> bool:
    """可选性判定 (S10-012 §四b: ACTIVE 且 enabled=true 才可被 binding 选用)。

    enabled 独立运行开关: ACTIVE+enabled=false 不可选; DRAFT/DEPRECATED/
    ARCHIVED 一律不可选 (即使 enabled=true)。历史 binding (含 version) 不受
    DEPRECATED/ARCHIVED 影响 — 可复现。
    """
    return capability.state == CapabilityState.ACTIVE and bool(capability.enabled)


# ------------------------------------------------------------------ CapabilityBinding


class CapabilityBinding(_OrgModel):
    """Project binding (S10-012 §四 — 引用, 非复制)。

    {type: agent|skill|mcp|workflow, id, version?}: version 可选 (历史 binding
    无 version → None, 零破坏); 能力持续升级时 pin version 保持可复现。
    校验: type 必须合法 + id 非空 (空串/空白/缺失拒绝)。
    """

    type: BindingType
    id: str
    version: str | None = None

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, v: Any) -> BindingType:
        return BindingType.parse(v)

    @field_validator("id", mode="before")
    @classmethod
    def _id_non_empty(cls, v: Any) -> Any:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("capability binding id must be a non-empty string")
        return v


# ------------------------------------------------------------------ 六实体


class Skill(_OrgModel):
    """Skill (S10-012 §二 — 公共能力池实体; Task 002 才实现 Registry)。"""

    id: str
    name: str
    description: str = ""
    category: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    version: str = ""                     # 技能版本 (Registry 版本控制, §三)
    enabled: bool = True                  # 运行开关 (与 state 语义分离, §四b)
    state: CapabilityState = CapabilityState.DRAFT

    @field_validator("input_schema", "output_schema", mode="before")
    @classmethod
    def _schemas_none(cls, v: Any) -> Any:
        return v if v is not None else {}

    @field_validator("state", mode="before")
    @classmethod
    def _coerce_state(cls, v: Any) -> CapabilityState:
        return CapabilityState.parse(v)


class Agent(_OrgModel):
    """Agent (S10-012 §二 — Factory 员工池角色; llm_config 为 LLMConfig id 引用)。

    skill_bindings/workflow_bindings: CapabilityBinding 列表 (引用, 非包含);
    宽松解析 — dict 输入自动归一为 CapabilityBinding, 历史数据无 version 兼容。
    """

    id: str
    name: str
    role: str = ""
    description: str = ""
    skill_bindings: list[CapabilityBinding] = Field(default_factory=list)
    workflow_bindings: list[CapabilityBinding] = Field(default_factory=list)
    llm_config: str = ""                  # LLMConfig id 引用 (池内实体)
    enabled: bool = True
    state: CapabilityState = CapabilityState.DRAFT

    @field_validator("skill_bindings", "workflow_bindings", mode="before")
    @classmethod
    def _bindings_none(cls, v: Any) -> Any:
        return _norm_list(v)

    @field_validator("state", mode="before")
    @classmethod
    def _coerce_state(cls, v: Any) -> CapabilityState:
        return CapabilityState.parse(v)


class MCP(_OrgModel):
    """MCP (S10-012 §二 — 外部工具连接描述; auth_config 占位, 不实现连接)。"""

    id: str
    name: str
    type: str = ""                        # 连接类型 (http/sse/stdio ...)
    endpoint: str = ""
    auth_config: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)
    enabled: bool = True
    state: CapabilityState = CapabilityState.DRAFT

    @field_validator("auth_config", mode="before")
    @classmethod
    def _auth_none(cls, v: Any) -> Any:
        return v if v is not None else {}

    @field_validator("capabilities", mode="before")
    @classmethod
    def _caps_none(cls, v: Any) -> Any:
        return _norm_list(v)

    @field_validator("state", mode="before")
    @classmethod
    def _coerce_state(cls, v: Any) -> CapabilityState:
        return CapabilityState.parse(v)


class WorkflowTemplate(_OrgModel):
    """WorkflowTemplate (S10-012 §二 — 标准工作流模板; steps 有序步骤列表)。"""

    id: str
    name: str
    industry: str = ""                    # Industry id 引用
    steps: list[dict[str, Any]] = Field(default_factory=list)
    required_agents: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    enabled: bool = True
    state: CapabilityState = CapabilityState.DRAFT

    @field_validator("steps", "required_agents", "required_skills", mode="before")
    @classmethod
    def _lists_none(cls, v: Any) -> Any:
        return _norm_list(v)

    @field_validator("state", mode="before")
    @classmethod
    def _coerce_state(cls, v: Any) -> CapabilityState:
        return CapabilityState.parse(v)


class Industry(_OrgModel):
    """Industry (S10-012 §二 — 行业域; workflow_templates 为模板 id 引用)。"""

    id: str
    name: str
    description: str = ""
    workflow_templates: list[str] = Field(default_factory=list)
    enabled: bool = True
    state: CapabilityState = CapabilityState.DRAFT

    @field_validator("workflow_templates", mode="before")
    @classmethod
    def _templates_none(cls, v: Any) -> Any:
        return _norm_list(v)

    @field_validator("state", mode="before")
    @classmethod
    def _coerce_state(cls, v: Any) -> CapabilityState:
        return CapabilityState.parse(v)


class LLMConfig(_OrgModel):
    """LLMConfig (S10-012 §二 — 模型配置; parameters 为 provider 参数 dict)。

    只建实体不连接: 真实 LLM 调用在 S10-012 禁止范围外 (Task 007+ 消费)。
    """

    id: str
    provider: str = ""
    model: str = ""
    endpoint: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    state: CapabilityState = CapabilityState.DRAFT

    @field_validator("parameters", mode="before")
    @classmethod
    def _params_none(cls, v: Any) -> Any:
        return v if v is not None else {}

    @field_validator("state", mode="before")
    @classmethod
    def _coerce_state(cls, v: Any) -> CapabilityState:
        return CapabilityState.parse(v)


# ------------------------------------------------------------------ Skill Registry (Task 002)

_SKILL_ID_BANNED = ("/", "\\")


def _default_skill(
    skill_id: str, name: str, description: str, category: str
) -> Skill:
    """默认种子 Skill 构造 (S10-012 §三 种子: 只建实体不实现逻辑)。"""
    return Skill(
        id=skill_id,
        name=name,
        description=description,
        category=category,
        input_schema={"inputs": [{"name": "task"}]},
        output_schema={"outputs": [{"name": "result"}]},
        version="1.0.0",
        enabled=True,
        state=CapabilityState.ACTIVE,
    )


#: 默认种子 — 标准 skills (S10-012 §三: flutter-development/backend-development 等;
#: ACTIVE+enabled → 验收场景4 可选能力池; 幂等, 已存在不覆盖)。
DEFAULT_SKILLS: tuple[Skill, ...] = (
    _default_skill(
        "backend-development",
        "Backend Development",
        "后端开发: 服务端 API/数据库/CLI (Java/Python/Shell)",
        "software-development",
    ),
    _default_skill(
        "frontend-development",
        "Frontend Development",
        "前端开发: HTML/JS/Vue/UniApp/小程序",
        "software-development",
    ),
    _default_skill(
        "qa-testing",
        "QA Testing",
        "测试: 功能/压力/自动化/PRD 验收",
        "software-development",
    ),
    _default_skill(
        "product-management",
        "Product Management",
        "产品: 需求分析/PRD/竞品调研",
        "software-development",
    ),
    _default_skill(
        "flutter-development",
        "Flutter Development",
        "Flutter 跨平台开发 (Dart/UI/状态管理)",
        "software-development",
    ),
)


def _default_agent(
    agent_id: str, name: str, role: str, description: str, skill_ids: tuple[str, ...]
) -> Agent:
    """默认种子 Agent 构造 (S10-012 §三 种子: 只建实体不实现逻辑)。

    skill_bindings: 引用 DEFAULT_SKILLS 中的标准 skill (binding 引用, 非复制);
    workflow_bindings 留空 (workflows/ 目录信源 Task 005 落地后扩展);
    llm_config 留空 (llm-configs/ 目录信源 Task 006 落地后引用)。
    """
    return Agent(
        id=agent_id,
        name=name,
        role=role,
        description=description,
        skill_bindings=[
            CapabilityBinding(type=BindingType.SKILL, id=sid) for sid in skill_ids
        ],
        workflow_bindings=[],
        llm_config="",
        enabled=True,
        state=CapabilityState.ACTIVE,
    )


#: 默认种子 — 标准 AI 员工角色 (S10-012 §三: PM/Architect/Developer/QA/UI
#: 五角色 + skill 绑定; ACTIVE+enabled → 验收场景4 可选能力池; 幂等,
#: 已存在不覆盖)。skill 引用全部落在 DEFAULT_SKILLS 内 (种子自洽, 零警告)。
DEFAULT_AGENTS: tuple[Agent, ...] = (
    _default_agent(
        "product-manager-agent",
        "Product Manager Agent",
        "product-manager",
        "产品经理: 需求分析/PRD/竞品调研/市场分析",
        ("product-management",),
    ),
    _default_agent(
        "architect-agent",
        "Architect Agent",
        "architect",
        "架构师: 系统架构设计/技术选型/方案评审",
        ("backend-development", "flutter-development"),
    ),
    _default_agent(
        "developer-agent",
        "Developer Agent",
        "developer",
        "开发工程师: 后端/前端/跨平台实现",
        ("backend-development", "frontend-development"),
    ),
    _default_agent(
        "qa-agent",
        "QA Agent",
        "qa",
        "测试工程师: 功能/压力/自动化/PRD 验收",
        ("qa-testing",),
    ),
    _default_agent(
        "ui-designer-agent",
        "UI Designer Agent",
        "ui-designer",
        "UI/UX 设计师: 界面设计/切图/设计稿输出",
        ("frontend-development",),
    ),
)


def _default_workflow(
    workflow_id: str,
    name: str,
    industry: str,
    steps: list[dict[str, Any]],
    required_agents: tuple[str, ...],
    required_skills: tuple[str, ...],
) -> WorkflowTemplate:
    """默认种子 WorkflowTemplate 构造 (S10-012 §三 种子: 只建实体不实现逻辑)。

    steps 有序 (列表顺序即执行顺序 — AF-PRD §4.8); required_agents/required_skills
    引用 DEFAULT_AGENTS/DEFAULT_SKILLS 内 id (种子自洽, 零警告)。
    """
    return WorkflowTemplate(
        id=workflow_id,
        name=name,
        industry=industry,
        steps=steps,
        required_agents=list(required_agents),
        required_skills=list(required_skills),
        enabled=True,
        state=CapabilityState.ACTIVE,
    )


#: 默认种子 — Software Development Lifecycle 工作流 (S10-012 §三 + AF-PRD §4.8:
#: Requirement Analysis → Architecture → Development → Testing → Release;
#: required_agents pm/architect/developer/qa; required_skills 对应;
#: ACTIVE+enabled → 验收场景4 可选能力池; 幂等, 已存在不覆盖)。
#: agent/skill 引用全部落在 DEFAULT_AGENTS/DEFAULT_SKILLS 内 (种子自洽, 零警告)。
DEFAULT_WORKFLOWS: tuple[WorkflowTemplate, ...] = (
    _default_workflow(
        "software-development-lifecycle",
        "Software Development Lifecycle",
        "software-development",
        [
            {"id": "requirement-analysis", "name": "Requirement Analysis",
             "description": "需求分析 (PM)"},
            {"id": "architecture", "name": "Architecture",
             "description": "系统架构设计与技术选型"},
            {"id": "development", "name": "Development",
             "description": "编码实现 (后端/前端)"},
            {"id": "testing", "name": "Testing",
             "description": "功能/压力/验收测试"},
            {"id": "release", "name": "Release",
             "description": "发布交付"},
        ],
        (
            "product-manager-agent",
            "architect-agent",
            "developer-agent",
            "qa-agent",
        ),
        (
            "product-management",
            "backend-development",
            "frontend-development",
            "qa-testing",
        ),
    ),
)


class CapabilityRegistry:
    """Factory Capability Pool 注册表 (S10-012 §三 — skills/ 目录信源, Task 002)。

    目录信源: <root>/workspace/capabilities/skills/{id}.json (单实体单文件;
    id 主键, version 字段记录 — 同 id 新 version → 覆盖, 升级 = update)。

    语义:
    - register_skill: upsert (重复 id 覆盖 — 同 store.save 模式); 原子写
      (临时文件 + os.replace); 懒迁移 (无 capabilities/ 目录 → 首次写创建)
    - get_skill: 缺失 → None; 损坏 JSON / schema 非法 → None (失败安全)
    - list_skills(enabled_only): 按 id 排序; enabled_only=True → 只返回
      ACTIVE+enabled (capability_selectable — §四b 可选能力)
    - update_skill(id, updates): 部分字段更新 (pydantic 重校验, 未知字段/
      非法 state 拒绝); 缺失 → None
    - transition_skill(id, target): 受控生命周期转换并落盘; 非法转换
      ValueError 不落盘; 缺失 → None
    - delete_skill(id): 缺失 → False (幂等)
    - seed_defaults(): 幂等默认种子 (已存在不覆盖 — 用户注册/修改优先)

    约束: 零 Core/console 依赖 (stdlib + pydantic + 本模块实体 — Removal
    Isolation, 同 org/store.py 模式)。
    """

    def __init__(self, root: str | Path):
        self._root = Path(root)
        self._capabilities_dir = self._root / "workspace" / "capabilities"
        self._skills_dir = self._capabilities_dir / "skills"
        self._agents_dir = self._capabilities_dir / "agents"
        self._mcps_dir = self._capabilities_dir / "mcps"
        self._workflows_dir = self._capabilities_dir / "workflows"

    # ------------------------------------------------------------------ 布局
    @property
    def root(self) -> Path:
        return self._root

    @property
    def capabilities_dir(self) -> Path:
        """能力池根目录 (<root>/workspace/capabilities)。"""
        return self._capabilities_dir

    @property
    def skills_dir(self) -> Path:
        """skills 目录信源 (<root>/workspace/capabilities/skills)。"""
        return self._skills_dir

    @property
    def agents_dir(self) -> Path:
        """agents 目录信源 (<root>/workspace/capabilities/agents)。"""
        return self._agents_dir

    @property
    def mcps_dir(self) -> Path:
        """mcps 目录信源 (<root>/workspace/capabilities/mcps)。"""
        return self._mcps_dir

    @property
    def workflows_dir(self) -> Path:
        """workflows 目录信源 (<root>/workspace/capabilities/workflows)。"""
        return self._workflows_dir

    def _skill_path(self, skill_id: str) -> Path:
        return self._skills_dir / f"{skill_id}.json"

    def _agent_path(self, agent_id: str) -> Path:
        return self._agents_dir / f"{agent_id}.json"

    def _mcp_path(self, mcp_id: str) -> Path:
        return self._mcps_dir / f"{mcp_id}.json"

    def _workflow_path(self, workflow_id: str) -> Path:
        return self._workflows_dir / f"{workflow_id}.json"

    @staticmethod
    def _validate_skill_id(skill_id: str) -> None:
        """id 防御: 非空 + 无路径分隔符 (防目录信源路径穿越)。"""
        if not isinstance(skill_id, str) or not skill_id.strip():
            raise ValueError("skill id must be a non-empty string")
        if any(ch in skill_id for ch in _SKILL_ID_BANNED):
            raise ValueError(f"skill id must not contain path separators: {skill_id!r}")

    @staticmethod
    def _validate_agent_id(agent_id: str) -> None:
        """id 防御: 非空 + 无路径分隔符 (防目录信源路径穿越)。"""
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError("agent id must be a non-empty string")
        if any(ch in agent_id for ch in _SKILL_ID_BANNED):
            raise ValueError(f"agent id must not contain path separators: {agent_id!r}")

    @staticmethod
    def _validate_mcp_id(mcp_id: str) -> None:
        """id 防御: 非空 + 无路径分隔符 (防目录信源路径穿越)。"""
        if not isinstance(mcp_id, str) or not mcp_id.strip():
            raise ValueError("mcp id must be a non-empty string")
        if any(ch in mcp_id for ch in _SKILL_ID_BANNED):
            raise ValueError(f"mcp id must not contain path separators: {mcp_id!r}")

    @staticmethod
    def _validate_workflow_id(workflow_id: str) -> None:
        """id 防御: 非空 + 无路径分隔符 (防目录信源路径穿越)。"""
        if not isinstance(workflow_id, str) or not workflow_id.strip():
            raise ValueError("workflow id must be a non-empty string")
        if any(ch in workflow_id for ch in _SKILL_ID_BANNED):
            raise ValueError(
                f"workflow id must not contain path separators: {workflow_id!r}"
            )

    @staticmethod
    def _validate_workflow_steps(steps: Any) -> None:
        """steps 校验 (S10-012 §二 + Task 005): 非空 + 有序 (列表顺序即执行顺序)。

        - steps 必须为非空 list (无步骤的工作流无意义 → 拒绝)
        - 每个 step 必须为 dict 且含非空 id (步骤可标识)
        - step id 唯一 (无重复步骤, 审计/调度可寻址)
        顺序语义: 列表顺序即执行顺序 — 校验不重排, register→get 顺序保持。
        """
        if not isinstance(steps, list) or not steps:
            raise ValueError("workflow steps must be a non-empty list")
        seen: set[str] = set()
        for step in steps:
            if not isinstance(step, dict):
                raise ValueError(f"workflow step must be a dict: {step!r}")
            step_id = step.get("id")
            if not isinstance(step_id, str) or not step_id.strip():
                raise ValueError(
                    f"workflow step must have a non-empty id: {step!r}"
                )
            if step_id in seen:
                raise ValueError(f"duplicate workflow step id: {step_id!r}")
            seen.add(step_id)

    # ------------------------------------------------------------------ 原子写
    @staticmethod
    def _atomic_write(path: Path, data: dict[str, Any]) -> None:
        """原子写 JSON: 临时文件 + os.replace (同 store.py/space.py 模式)。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, path)

    # ------------------------------------------------------------------ 读 (失败安全)
    @staticmethod
    def _parse_skill(data: Any) -> Skill | None:
        """dict → Skill; JSON 结构非法 (缺字段/extra/state 非法) → None。"""
        if not isinstance(data, dict):
            return None
        try:
            return Skill.model_validate(data)
        except ValueError:
            return None

    def _read_skill_file(self, path: Path) -> Skill | None:
        """读单文件; 损坏 JSON / 非法 schema → None (失败安全, 不崩溃)。"""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return self._parse_skill(data)

    def get_skill(self, skill_id: str) -> Skill | None:
        """按 id 取技能; 缺失 / 损坏 → None。"""
        path = self._skill_path(skill_id)
        if not path.is_file():
            return None
        return self._read_skill_file(path)

    def list_skills(self, *, enabled_only: bool = False) -> list[Skill]:
        """全部技能 (按 id 排序, 确定性); 损坏文件静默跳过。

        enabled_only=True → 只返回 ACTIVE+enabled (capability_selectable,
        S10-012 §四b 可选能力过滤)。
        """
        result: list[Skill] = []
        if self._skills_dir.is_dir():
            for path in sorted(self._skills_dir.glob("*.json")):
                skill = self._read_skill_file(path)
                if skill is None:
                    continue  # 失败安全: 损坏/非法文件跳过
                if enabled_only and not capability_selectable(skill):
                    continue
                result.append(skill)
        return result

    # ------------------------------------------------------------------ 写
    def register_skill(self, skill: Skill) -> Skill:
        """注册/覆盖技能 (upsert — 重复 id 覆盖; 原子写; 懒迁移建目录)。"""
        self._validate_skill_id(skill.id)
        self._atomic_write(self._skill_path(skill.id), skill.to_dict())
        return skill

    def update_skill(self, skill_id: str, updates: dict[str, Any]) -> Skill | None:
        """部分字段更新 (升级 = 更新 version 字段); 缺失 → None。

        全量重校验 (model_validate): 未知字段 (extra=forbid) / 非法 state
        → ValueError, 不落盘 (原文件保持)。
        """
        current = self.get_skill(skill_id)
        if current is None:
            return None
        merged = Skill.model_validate({**current.to_dict(), **(updates or {})})
        self.register_skill(merged)
        return merged

    def delete_skill(self, skill_id: str) -> bool:
        """删除技能文件; 缺失 → False (幂等); 删除失败 → False (失败安全)。"""
        path = self._skill_path(skill_id)
        if not path.is_file():
            return False
        try:
            path.unlink()
            return True
        except OSError:
            return False

    # ------------------------------------------------------------------ 生命周期
    def transition_skill(self, skill_id: str, target: CapabilityState | str) -> Skill | None:
        """受控生命周期转换并落盘 (DRAFT→ACTIVE→DEPRECATED→ARCHIVED)。

        非法转换 (跳级/回退/终态后) → ValueError, 不落盘 (原文件保持);
        缺失 id → None。
        """
        current = self.get_skill(skill_id)
        if current is None:
            return None
        updated = transition_capability(current, target)
        if not isinstance(updated, Skill):
            raise TypeError("transition_capability must return a Skill instance")
        self.register_skill(updated)
        return updated

    # ------------------------------------------------------------------ 默认种子
    def seed_defaults(self) -> int:
        """预置标准 skills + 标准 AI 员工角色 + 标准 workflows (幂等 — 已存在
        文件不覆盖, 用户修改保留); 返回新建总数。种子 workflow 的 agent/skill
        引用全部落在 DEFAULT_AGENTS/DEFAULT_SKILLS 内 — 同次种子后自洽
        (validate_agent_bindings / validate_workflow_refs 零警告)。"""
        seeded = 0
        for skill in DEFAULT_SKILLS:
            if not self._skill_path(skill.id).is_file():
                self.register_skill(skill)
                seeded += 1
        for agent in DEFAULT_AGENTS:
            if not self._agent_path(agent.id).is_file():
                self.register_agent(agent)
                seeded += 1
        for workflow in DEFAULT_WORKFLOWS:
            if not self._workflow_path(workflow.id).is_file():
                self.register_workflow(workflow)
                seeded += 1
        return seeded

    # ------------------------------------------------------------------ Agent Registry (Task 003)

    # 读 (失败安全)
    @staticmethod
    def _parse_agent(data: Any) -> Agent | None:
        """dict → Agent; JSON 结构非法 (缺字段/extra/state 非法) → None。"""
        if not isinstance(data, dict):
            return None
        try:
            return Agent.model_validate(data)
        except ValueError:
            return None

    def _read_agent_file(self, path: Path) -> Agent | None:
        """读单文件; 损坏 JSON / 非法 schema → None (失败安全, 不崩溃)。"""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return self._parse_agent(data)

    def get_agent(self, agent_id: str) -> Agent | None:
        """按 id 取角色; 缺失 / 损坏 → None。"""
        path = self._agent_path(agent_id)
        if not path.is_file():
            return None
        return self._read_agent_file(path)

    def list_agents(self, *, enabled_only: bool = False) -> list[Agent]:
        """全部角色 (按 id 排序, 确定性); 损坏文件静默跳过。

        enabled_only=True → 只返回 ACTIVE+enabled (capability_selectable,
        S10-012 §四b 可选能力过滤)。
        """
        result: list[Agent] = []
        if self._agents_dir.is_dir():
            for path in sorted(self._agents_dir.glob("*.json")):
                agent = self._read_agent_file(path)
                if agent is None:
                    continue  # 失败安全: 损坏/非法文件跳过
                if enabled_only and not capability_selectable(agent):
                    continue
                result.append(agent)
        return result

    # 写
    def register_agent(self, agent: Agent) -> Agent:
        """注册/覆盖角色 (upsert — 重复 id 覆盖; 原子写; 懒迁移建目录)。"""
        self._validate_agent_id(agent.id)
        self._atomic_write(self._agent_path(agent.id), agent.to_dict())
        return agent

    def update_agent(self, agent_id: str, updates: dict[str, Any]) -> Agent | None:
        """部分字段更新 (含 skill_bindings/workflow_bindings/llm_config);
        缺失 → None。

        全量重校验 (model_validate): 未知字段 (extra=forbid) / 非法 state
        / 非法 binding → ValueError, 不落盘 (原文件保持)。
        """
        current = self.get_agent(agent_id)
        if current is None:
            return None
        merged = Agent.model_validate({**current.to_dict(), **(updates or {})})
        self.register_agent(merged)
        return merged

    def delete_agent(self, agent_id: str) -> bool:
        """删除角色文件; 缺失 → False (幂等); 删除失败 → False (失败安全)。"""
        path = self._agent_path(agent_id)
        if not path.is_file():
            return False
        try:
            path.unlink()
            return True
        except OSError:
            return False

    # 生命周期
    def transition_agent(self, agent_id: str, target: CapabilityState | str) -> Agent | None:
        """受控生命周期转换并落盘 (DRAFT→ACTIVE→DEPRECATED→ARCHIVED)。

        非法转换 (跳级/回退/终态后) → ValueError, 不落盘 (原文件保持);
        缺失 id → None。
        """
        current = self.get_agent(agent_id)
        if current is None:
            return None
        updated = transition_capability(current, target)
        if not isinstance(updated, Agent):
            raise TypeError("transition_capability must return an Agent instance")
        self.register_agent(updated)
        return updated

    # binding 校验 (S10-012 §四: 缺失 → 警告标注, 不崩溃)
    def validate_agent_bindings(self, agent_id: str) -> list[str] | None:
        """校验 agent.skill_bindings 引用是否存在于 Registry (缺失 → 警告标注)。

        - 返回警告字符串列表 (每条一个缺失引用); 全部解析 → 空列表
        - 缺失 agent → None (同 get_agent 语义)
        - 不崩溃: 缺失引用只是警告, 不影响 agent 本身读取/使用
        - 当前范围 (Task 003): 只校验 skill_bindings 对 skills/ 目录的引用;
          workflow_bindings 校验随 Task 005 (workflows/ 目录信源) 落地
        """
        agent = self.get_agent(agent_id)
        if agent is None:
            return None
        known_skills = {s.id for s in self.list_skills()}
        warnings: list[str] = []
        for binding in agent.skill_bindings:
            if binding.id not in known_skills:
                warnings.append(
                    f"agent {agent_id}: skill binding missing: {binding.id}"
                )
        return warnings

    # ------------------------------------------------------------------ MCP Registry (Task 004)

    # 读 (失败安全)
    @staticmethod
    def _parse_mcp(data: Any) -> MCP | None:
        """dict → MCP; JSON 结构非法 (缺字段/extra/state 非法) → None。"""
        if not isinstance(data, dict):
            return None
        try:
            return MCP.model_validate(data)
        except ValueError:
            return None

    def _read_mcp_file(self, path: Path) -> MCP | None:
        """读单文件; 损坏 JSON / 非法 schema → None (失败安全, 不崩溃)。"""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return self._parse_mcp(data)

    def get_mcp(self, mcp_id: str) -> MCP | None:
        """按 id 取 MCP; 缺失 / 损坏 → None。

        auth_config 为占位 dict (不实现认证逻辑 — S10-012 禁止范围)。
        """
        path = self._mcp_path(mcp_id)
        if not path.is_file():
            return None
        return self._read_mcp_file(path)

    def list_mcps(self, *, enabled_only: bool = False) -> list[MCP]:
        """全部 MCP (按 id 排序, 确定性); 损坏文件静默跳过。

        enabled_only=True → 只返回 ACTIVE+enabled (capability_selectable,
        S10-012 §四b 可选能力过滤)。
        """
        result: list[MCP] = []
        if self._mcps_dir.is_dir():
            for path in sorted(self._mcps_dir.glob("*.json")):
                mcp = self._read_mcp_file(path)
                if mcp is None:
                    continue  # 失败安全: 损坏/非法文件跳过
                if enabled_only and not capability_selectable(mcp):
                    continue
                result.append(mcp)
        return result

    # 写
    def register_mcp(self, mcp: MCP) -> MCP:
        """注册/覆盖 MCP (upsert — 重复 id 覆盖; 原子写; 懒迁移建目录)。"""
        self._validate_mcp_id(mcp.id)
        self._atomic_write(self._mcp_path(mcp.id), mcp.to_dict())
        return mcp

    def update_mcp(self, mcp_id: str, updates: dict[str, Any]) -> MCP | None:
        """部分字段更新 (含 type/endpoint/auth_config/capabilities); 缺失 → None。

        全量重校验 (model_validate): 未知字段 (extra=forbid) / 非法 state
        → ValueError, 不落盘 (原文件保持)。
        """
        current = self.get_mcp(mcp_id)
        if current is None:
            return None
        merged = MCP.model_validate({**current.to_dict(), **(updates or {})})
        self.register_mcp(merged)
        return merged

    def delete_mcp(self, mcp_id: str) -> bool:
        """删除 MCP 文件; 缺失 → False (幂等); 删除失败 → False (失败安全)。"""
        path = self._mcp_path(mcp_id)
        if not path.is_file():
            return False
        try:
            path.unlink()
            return True
        except OSError:
            return False

    # 生命周期
    def transition_mcp(self, mcp_id: str, target: CapabilityState | str) -> MCP | None:
        """受控生命周期转换并落盘 (DRAFT→ACTIVE→DEPRECATED→ARCHIVED)。

        非法转换 (跳级/回退/终态后) → ValueError, 不落盘 (原文件保持);
        缺失 id → None。
        """
        current = self.get_mcp(mcp_id)
        if current is None:
            return None
        updated = transition_capability(current, target)
        if not isinstance(updated, MCP):
            raise TypeError("transition_capability must return an MCP instance")
        self.register_mcp(updated)
        return updated

    # ------------------------------------------------------------------ Workflow Template Registry (Task 005)

    # 读 (失败安全)
    @staticmethod
    def _parse_workflow(data: Any) -> WorkflowTemplate | None:
        """dict → WorkflowTemplate; JSON 结构非法 (缺字段/extra/state 非法) → None。"""
        if not isinstance(data, dict):
            return None
        try:
            return WorkflowTemplate.model_validate(data)
        except ValueError:
            return None

    def _read_workflow_file(self, path: Path) -> WorkflowTemplate | None:
        """读单文件; 损坏 JSON / 非法 schema → None (失败安全, 不崩溃)。"""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return self._parse_workflow(data)

    def get_workflow(self, workflow_id: str) -> WorkflowTemplate | None:
        """按 id 取工作流模板; 缺失 / 损坏 → None。"""
        path = self._workflow_path(workflow_id)
        if not path.is_file():
            return None
        return self._read_workflow_file(path)

    def list_workflows(self, *, enabled_only: bool = False) -> list[WorkflowTemplate]:
        """全部工作流模板 (按 id 排序, 确定性); 损坏文件静默跳过。

        enabled_only=True → 只返回 ACTIVE+enabled (capability_selectable,
        S10-012 §四b 可选能力过滤)。
        """
        result: list[WorkflowTemplate] = []
        if self._workflows_dir.is_dir():
            for path in sorted(self._workflows_dir.glob("*.json")):
                workflow = self._read_workflow_file(path)
                if workflow is None:
                    continue  # 失败安全: 损坏/非法文件跳过
                if enabled_only and not capability_selectable(workflow):
                    continue
                result.append(workflow)
        return result

    # 写
    def register_workflow(self, workflow: WorkflowTemplate) -> WorkflowTemplate:
        """注册/覆盖工作流模板 (upsert — 重复 id 覆盖; 原子写; 懒迁移建目录)。

        steps 校验 (非空 + step id 唯一) 在写前执行 — 非法拒绝不落盘。
        """
        self._validate_workflow_id(workflow.id)
        self._validate_workflow_steps(workflow.steps)
        self._atomic_write(self._workflow_path(workflow.id), workflow.to_dict())
        return workflow

    def update_workflow(
        self, workflow_id: str, updates: dict[str, Any]
    ) -> WorkflowTemplate | None:
        """部分字段更新 (含 industry/steps/required_agents/required_skills);
        缺失 → None。

        全量重校验 (model_validate): 未知字段 (extra=forbid) / 非法 state
        → ValueError; steps 校验 (非空/step id 唯一) → ValueError — 均不落盘
        (原文件保持)。
        """
        current = self.get_workflow(workflow_id)
        if current is None:
            return None
        merged = WorkflowTemplate.model_validate(
            {**current.to_dict(), **(updates or {})}
        )
        self._validate_workflow_steps(merged.steps)
        self.register_workflow(merged)
        return merged

    def delete_workflow(self, workflow_id: str) -> bool:
        """删除工作流模板文件; 缺失 → False (幂等); 删除失败 → False (失败安全)。"""
        path = self._workflow_path(workflow_id)
        if not path.is_file():
            return False
        try:
            path.unlink()
            return True
        except OSError:
            return False

    # 生命周期
    def transition_workflow(
        self, workflow_id: str, target: CapabilityState | str
    ) -> WorkflowTemplate | None:
        """受控生命周期转换并落盘 (DRAFT→ACTIVE→DEPRECATED→ARCHIVED)。

        非法转换 (跳级/回退/终态后) → ValueError, 不落盘 (原文件保持);
        缺失 id → None。
        """
        current = self.get_workflow(workflow_id)
        if current is None:
            return None
        updated = transition_capability(current, target)
        if not isinstance(updated, WorkflowTemplate):
            raise TypeError(
                "transition_capability must return a WorkflowTemplate instance"
            )
        self.register_workflow(updated)
        return updated

    # 引用校验 (S10-012 §四: 缺失 → 警告标注, 不崩溃)
    def validate_workflow_refs(self, workflow_id: str) -> list[str] | None:
        """校验 workflow.required_agents/required_skills 引用是否存在于 Registry。

        - required_agents 引用 agents/ 目录 (Agent 实体); required_skills
          引用 skills/ 目录 (Skill 实体)
        - 返回警告字符串列表 (每条一个缺失引用); 全部解析 → 空列表
        - 缺失 workflow → None (同 get_workflow 语义)
        - 不崩溃: 缺失引用只是警告, 不影响 workflow 本身读取/使用
        """
        workflow = self.get_workflow(workflow_id)
        if workflow is None:
            return None
        known_agents = {a.id for a in self.list_agents()}
        known_skills = {s.id for s in self.list_skills()}
        warnings: list[str] = []
        for agent_id in workflow.required_agents:
            if agent_id not in known_agents:
                warnings.append(
                    f"workflow {workflow_id}: required agent missing: {agent_id}"
                )
        for skill_id in workflow.required_skills:
            if skill_id not in known_skills:
                warnings.append(
                    f"workflow {workflow_id}: required skill missing: {skill_id}"
                )
        return warnings

    # ------------------------------------------------------------------ Workflow 默认种子 (Task 005)
