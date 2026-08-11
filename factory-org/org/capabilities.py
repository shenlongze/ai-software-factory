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
Task 002-006 才实现 Registry CRUD/目录信源/种子。
"""

from __future__ import annotations

from enum import Enum
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
