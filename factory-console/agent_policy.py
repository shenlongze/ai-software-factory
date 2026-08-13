"""factory-console/agent_policy.py — Agent/Skill LLM 路由策略数据访问层 (S10-024 v1.1)。

职责: 读取/解析 agent.yaml 与 skill.yaml 的 llm.routing 段 → pydantic 模型。
只做"配置读取", 不做决策 (决策在 llm_router.py — 职责分离)。

设计依据: docs/sprint10/S10-024-router-design-v1.1.md (§3 数据模型 / §5 配置路径)。
- agent.yaml = <agents_dir>/<agent_id>/agent.yaml (缺省 ~/.factory/agents/<id>/agent.yaml)
- skill.yaml = <skills_dir>/<skill_id>/skill.yaml (缺省 ~/.factory/skills/<id>/skill.yaml)
- 均为可选文件: 缺失 → None; 损坏/非法 → warning + None (失败安全, 不拖垮 Router)

agent.yaml / skill.yaml 格式 (v1.1, 同构):

    name: backend-agent

    llm:
      routing:
        preferred:                    # 首选 (model 必填, provider 可选)
          model: deepseek-chat
          provider: deepseek
        fallback:                     # 备选链 (preferred 不可用 → 依次尝试)
          - model: deepseek-reasoner
            provider: deepseek
          - qwen2.5-14b               # 字符串形式兼容 (仅 model, provider 取 ControlPlane 默认)

fallback 条目兼容两种格式:
- 字符串 "deepseek-reasoner" → RouterRule(model=..., provider=None)
- dict {model, provider} → RouterRule 完整解析
pydantic 宽容解析: 多余字段忽略, 非法字段 → 跳过该条目。

依赖: PyYAML (pyproject.toml 已声明 pyyaml>=6; 6.0.3 已装) — 直接使用。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger("factory.agent_policy")


class RouterRule(BaseModel):
    """单条路由规则 (preferred / fallback 条目)。

    provider=None → 由决策层取 ControlPlane 默认 (selected_provider_id);
    model=None → 由决策层取该 provider 默认模型 (resolve_runtime_config)。
    """

    provider: str | None = None
    model: str | None = None


class AgentRoutingPolicy(BaseModel):
    """agent.yaml 的 llm.routing 段。"""

    preferred: RouterRule | None = None
    fallback: list[RouterRule] = Field(default_factory=list)


class SkillRoutingPolicy(BaseModel):
    """skill.yaml 的 llm.routing 段 (与 agent.yaml 同构, 独立类型便于审计)。"""

    preferred: RouterRule | None = None
    fallback: list[RouterRule] = Field(default_factory=list)


def _coerce_rule(raw: Any) -> RouterRule | None:
    """fallback 条目宽容解析: 字符串 (仅 model) 或 dict {model, provider}。

    非法条目 → None (跳过, 不拖垮整条策略)。
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        model = raw.strip()
        return RouterRule(model=model or None) if model else None
    if isinstance(raw, dict):
        try:
            return RouterRule.model_validate(raw)
        except ValidationError:
            logger.warning("agent_policy: invalid routing rule ignored: %r", raw)
            return None
    return None


def _parse_routing(raw: Any) -> dict[str, Any] | None:
    """从 yaml 解析结果提取 llm.routing 段 (缺失/非 dict → None)。"""
    if not isinstance(raw, dict):
        return None
    llm = raw.get("llm")
    if not isinstance(llm, dict):
        return None
    routing = llm.get("routing")
    if not isinstance(routing, dict):
        return None
    return routing


def _parse_fallback(routing: dict[str, Any]) -> list[RouterRule]:
    """fallback 段解析: 字符串列表 或 dict 列表 (兼容两种格式)。"""
    raw = routing.get("fallback")
    if raw is None:
        return []
    if not isinstance(raw, list):
        logger.warning("agent_policy: fallback must be a list, ignored: %r", raw)
        return []
    rules: list[RouterRule] = []
    for entry in raw:
        rule = _coerce_rule(entry)
        if rule is not None:
            rules.append(rule)
    return rules


class AgentPolicyStore:
    """Agent/Skill 策略数据访问层: agent.yaml / skill.yaml 读取解析。

    构造参数均可注入 (测试/冒烟用 — 不写真实 ~/.factory):
    - agents_dir: agent.yaml 根 (缺省 ~/.factory/agents)
    - skills_dir: skill.yaml 根 (缺省 ~/.factory/skills)
    """

    def __init__(
        self,
        agents_dir: str | Path | None = None,
        skills_dir: str | Path | None = None,
    ) -> None:
        self._agents_dir = (
            Path(agents_dir)
            if agents_dir is not None
            else Path.home() / ".factory" / "agents"
        )
        self._skills_dir = (
            Path(skills_dir)
            if skills_dir is not None
            else Path.home() / ".factory" / "skills"
        )

    # ------------------------------------------------------------------ 路径

    def agent_policy_path(self, agent_id: str) -> Path:
        """agent.yaml 路径: <agents_dir>/<agent_id>/agent.yaml。"""
        return self._agents_dir / agent_id / "agent.yaml"

    def skill_policy_path(self, skill_id: str) -> Path:
        """skill.yaml 路径: <skills_dir>/<skill_id>/skill.yaml。"""
        return self._skills_dir / skill_id / "skill.yaml"

    # ------------------------------------------------------------------ 读取

    def load_agent_policy(self, agent_id: str) -> AgentRoutingPolicy | None:
        """读取 agent 的 llm.routing 策略; 缺失/损坏 → None (失败安全)。"""
        raw = self._load_yaml(self.agent_policy_path(agent_id), f"agent {agent_id!r}")
        if raw is None:
            return None
        return self._policy_from_raw(raw, AgentRoutingPolicy)

    def load_skill_policy(self, skill_id: str) -> SkillRoutingPolicy | None:
        """读取 skill 的 llm.routing 策略; 缺失/损坏 → None (失败安全)。"""
        raw = self._load_yaml(self.skill_policy_path(skill_id), f"skill {skill_id!r}")
        if raw is None:
            return None
        return self._policy_from_raw(raw, SkillRoutingPolicy)

    # ------------------------------------------------------------------ 内部

    def _load_yaml(self, path: Path, label: str) -> Any | None:
        """失败安全 yaml 读取: 缺失 → None; 损坏 → warning + None。"""
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("agent_policy: unreadable %s policy: %s (%s)", label, path, exc)
            return None
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError as exc:
            logger.warning("agent_policy: corrupt %s policy yaml: %s (%s)", label, path, exc)
            return None

    def _policy_from_raw(self, raw: Any, cls: type[Any]) -> Any | None:
        """解析 llm.routing → 策略模型; 无 routing 段/结构非法 → None。"""
        routing = _parse_routing(raw)
        if routing is None:
            return None
        preferred_raw = routing.get("preferred")
        preferred = _coerce_rule(preferred_raw) if preferred_raw is not None else None
        fallback = _parse_fallback(routing)
        if preferred is None and not fallback:
            return None
        return cls(preferred=preferred, fallback=fallback)
