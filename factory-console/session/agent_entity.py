"""factory-console/session/agent_entity.py — AgentEntity 专家身份模型 (M2 A1, S10-087)。

M2 员工内核: "我要做CRM" → 7 个真实 Agent 实体交接产出 (parent_artifact 互引)。

职责边界 (S10-087-M2 契约):
- AgentEntity = 身份/能力描述 (谁来干活: id/role/industry/provider/技能/知识/
  流程/记忆/工具/评价/画像) — 只建模, 不执行
- DeveloperAgent (factory-exec/exec/developer.py) = 执行 (怎么干活:
  prompt → provider → patch)
- 装配 (身份 → 可执行配置) 在 expert_factory; 协作 (跨 Agent 交接) 在 handoff_bus

契约 (S10-087-M2 §2 统一):
1. id 一律 agt- 前缀: agt-<industry>-<role>-<n> (如 agt-it-pm-1)
2. to_dict/from_dict roundtrip (JSON 友好, 与 core/agents/models.py Agent 同款)
3. 缺必填字段 → 明确报错 (pydantic ValidationError, 不静默)
4. provider 可空 (None = 无 LLM → 确定性兜底可用, 见 expert_factory)
5. 基于 core/agents/models.py Agent 身份字段口径扩展执行/知识/评价/记忆字段
"""

from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

#: agt- 前缀 id 格式: agt-<industry>-<role>-<n> (小写字母数字/下划线, 数字后缀)
AGT_ID_RE = re.compile(r"^agt-[a-z0-9]+-[a-z0-9_]+-[0-9]+$")

#: 必填字段 (缺任一 → ValidationError, 明确报错不静默)
REQUIRED_FIELDS: tuple[str, ...] = ("id", "role", "industry")


class ProviderRef(BaseModel):
    """Provider 身份引用 {id, model} — 只记引用, 不装配 (装配在 expert_factory)。"""

    id: str
    model: str = ""

    @field_validator("id")
    @classmethod
    def _id_nonempty(cls, v: str) -> str:
        v = str(v or "").strip()
        if not v:
            raise ValueError("provider.id 不能为空")
        return v

    def to_dict(self) -> dict[str, str]:
        return self.model_dump(mode="json")


class AgentProfile(BaseModel):
    """专家画像 (绩效/质量/成本/速度 — evaluation 回流的聚合口径)。"""

    success_rate: float = 0.0
    quality: float = 0.0
    cost: float = 0.0
    speed: float = 0.0
    samples: int = 0

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class AgentEntity(BaseModel):
    """一个真实专家身份 (M2 员工内核核心实体)。

    字段 (S10-087-M2 A1):
    - id: agt-<industry>-<role>-<n> (唯一, 注册表键)
    - role: 角色 id (pm/market/competitive/ux/architect/qa/prd/backend ...)
    - industry: 行业命名空间 (it / ops — 见 agent_registry)
    - provider: {id, model} 或 None (无 LLM → 确定性兜底可用)
    - system_prompt: 角色系统提示词 (LLM 路径)
    - skills: 技能引用列表 (装配时校验存在 — 缺 skill 明确报错)
    - knowledge_ref / workflow_ref / memory_ref: 知识/流程/记忆挂载引用
    - tools: 工具引用列表 (MCP 真连后置, M2 仅为占位面)
    - evaluation_ref: 评价回流引用
    - profile: 画像 (success_rate/quality/cost/speed/samples)

    边界: 纯模型零依赖; 不执行任何业务 (执行装配在 expert_factory)。
    """

    id: str
    role: str
    industry: str
    provider: Optional[ProviderRef] = None
    system_prompt: str = ""
    skills: list[str] = Field(default_factory=list)
    knowledge_ref: str = ""
    workflow_ref: str = ""
    memory_ref: str = ""
    tools: list[str] = Field(default_factory=list)
    evaluation_ref: str = ""
    profile: AgentProfile = Field(default_factory=AgentProfile)

    @field_validator("id")
    @classmethod
    def _id_agt_prefix(cls, v: str) -> str:
        """id 契约: agt- 前缀 + agt-<industry>-<role>-<n> 格式 (不静默)。"""
        v = str(v or "").strip()
        if not v:
            raise ValueError("agent id 不能为空 (契约: agt-<industry>-<role>-<n>)")
        if "/" in v or "\\" in v or v in {".", ".."}:
            raise ValueError(f"非法 agent id (路径分隔符/相对路径): {v!r}")
        if not v.startswith("agt-"):
            raise ValueError(
                f"agent id 必须以 agt- 前缀 (契约: agt-<industry>-<role>-<n>): {v!r}"
            )
        if not AGT_ID_RE.match(v):
            raise ValueError(
                f"agent id 格式非法 (期望 agt-<industry>-<role>-<n>): {v!r}"
            )
        return v

    @field_validator("role")
    @classmethod
    def _role_sane(cls, v: str) -> str:
        v = str(v or "").strip()
        if not v:
            raise ValueError("role 不能为空")
        return v

    @field_validator("industry")
    @classmethod
    def _industry_sane(cls, v: str) -> str:
        v = str(v or "").strip()
        if not v:
            raise ValueError("industry 不能为空")
        return v

    @field_validator("skills", "tools")
    @classmethod
    def _lists_clean(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(s for s in v if str(s).strip()))

    @model_validator(mode="after")
    def _industry_matches_id(self) -> "AgentEntity":
        """id 前缀须与 industry 一致 (agt-<industry>-...) — 行业隔离在 id 可见。"""
        prefix = f"agt-{self.industry}-"
        if not self.id.startswith(prefix):
            raise ValueError(
                f"agent id 前缀与 industry 不一致: id={self.id!r} industry={self.industry!r}"
            )
        return self

    # ------------------------------------------------------------ 序列化

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (agents.json 落盘 / CLI --json 输出共用)。"""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: Any) -> "AgentEntity":
        """反序列化 (agents.json 读取 / 测试构造); 缺必填字段 → 明确报错。"""
        return cls(**dict(data or {}))

    def to_identity(self) -> dict[str, Any]:
        """core/agents/models.py Agent 身份字段口径视图 (注册表互操作只读面)。"""
        return {
            "id": self.id,
            "name": f"{self.role}-{self.industry}",
            "role": self.role,
            "description": self.system_prompt[:200] if self.system_prompt else "",
            "skills": list(self.skills),
            "status": "available",
            "current_task": None,
        }


__all__ = [
    "AGT_ID_RE",
    "REQUIRED_FIELDS",
    "AgentEntity",
    "AgentProfile",
    "ProviderRef",
]
