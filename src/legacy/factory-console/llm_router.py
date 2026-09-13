"""factory-console/llm_router.py — LLM Router v1.1 (S10-024): 五层决策链。

统一 LLM 决策入口。输入: task / task_type / agent / skill / project / user
constraints; 输出: ModelChoice {model_id, provider_id, score, reasons, source}
(复用 model_catalog.ModelChoice — S10-022 兼容预留, 零新模型)。

决策链 (命中即返回, 禁止跳过高优先级):

    L1 User Explicit           用户直接指定 (explicit_provider/explicit_model)
    L2 Agent/Skill Policy      角色策略 (agent.yaml / skill.yaml — agent_policy.py)
    L3 Project Rule            项目规则 (project.yaml — llm.routing{default, task_types})
    L4 System Recommendation   系统推荐 (ModelCatalog.suggest())
    L5 Fallback                默认 (ControlPlane.selected_provider_id())

每层: 命中 (存在+enabled+key 可解析) → 返回 ModelChoice; 未命中/无 key →
降级下一层。L1 显式指定若 provider 不存在/禁用 → 响亮 UserExplicitError
(不静默降级, 用户意图优先)。

职责分离: agent_policy.py 读配置 (agent.yaml/skill.yaml → pydantic 模型);
本模块只做决策 (调用 policy_store 取 L2 数据)。Router 不负责 Provider 管理
/ API Key / HTTP 调用 / Runtime 生命周期 (S10-021/023 已由 ControlPlane/
Provider Adapter 承担)。

审计: route() 命中后 _emit_decided → 内存 decided_events (router.decided 事件
{provider_id, model_id, source, reason, score}) + 可选 event_logger 落库
(失败安全: 无 logger/落库异常 → 静默, 不影响决策)。

设计依据: docs/sprint10/S10-024-router-design-v1.1.md (已确认)。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from .agent_policy import AgentPolicyStore, RouterRule
from .model_catalog import ModelChoice

logger = logging.getLogger("factory.llm_router")

#: ModelChoice.source 取值 (决策层标识)
SOURCE_USER_EXPLICIT = "user-explicit"
SOURCE_AGENT_SKILL_POLICY = "agent-skill-policy"
SOURCE_PROJECT_RULE = "project-rule"
SOURCE_SYSTEM_RECOMMENDATION = "system-recommendation"
SOURCE_FALLBACK = "fallback"

#: router.decided 审计事件类型名
EVENT_DECIDED = "router.decided"


class RouterError(Exception):
    """Router 基础异常。"""


class UserExplicitError(RouterError):
    """L1 响亮错误: 用户显式指定的 provider 不存在/禁用 (不静默降级)。"""


class ProjectRoutingRules(BaseModel):
    """project.yaml 的 llm.routing 段 (S10-024 v1 格式, 保持兼容)。"""

    default: RouterRule | None = None
    task_types: dict[str, RouterRule] = Field(default_factory=dict)


class ProjectLlmConfig(BaseModel):
    """project.yaml 解析结果 (llm 段)。"""

    routing: ProjectRoutingRules = Field(default_factory=ProjectRoutingRules)


class LLMRouter:
    """统一 LLM 决策入口: L1 User > L2 Agent/Skill > L3 Project > L4 System > L5 Fallback。"""

    def __init__(
        self,
        control_plane: Any | None = None,
        model_catalog: Any | None = None,
        policy_store: AgentPolicyStore | None = None,
        event_logger: Any | None = None,
        agents_dir: str | Path | None = None,
        skills_dir: str | Path | None = None,
    ) -> None:
        """依赖可注入 (测试隔离); 缺省构造复用 ControlPlane/ModelCatalog 默认路径。

        - control_plane: LLMControlPlane (缺省 None — L5 不可用时 route 返回 None)
        - model_catalog: ModelCatalog (缺省 None — L4 跳过)
        - policy_store: AgentPolicyStore (缺省按 agents_dir/skills_dir 构造)
        - event_logger: 审计落库 (缺省 None — 只记内存 decided_events)
        """
        self._control_plane = control_plane
        self._model_catalog = model_catalog
        self._policy_store = policy_store or AgentPolicyStore(
            agents_dir=agents_dir, skills_dir=skills_dir
        )
        self._event_logger = event_logger
        #: router.decided 审计事件 (内存 — 无 logger 也可查; G 验收)
        self.decided_events: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ 决策入口

    def route(
        self,
        *,
        task_type: str | None = None,
        required_capabilities: list[str] | None = None,
        agent_id: str | None = None,
        skill_ids: list[str] | None = None,
        project_dir: str | Path | None = None,
        explicit_provider: str | None = None,
        explicit_model: str | None = None,
    ) -> ModelChoice | None:
        """五层决策链 → ModelChoice (source 标识命中层); 全未命中 → None。"""
        choice = self._layer_user_explicit(explicit_provider, explicit_model)
        if choice is None:
            choice = self._layer_agent_skill_policy(agent_id, skill_ids)
        if choice is None:
            choice = self._layer_project_rule(project_dir, task_type)
        if choice is None:
            choice = self._layer_system_recommendation(required_capabilities)
        if choice is None:
            choice = self._layer_fallback()
        if choice is not None:
            self._emit_decided(choice, task_type)
        return choice

    # ------------------------------------------------------------------ L1 User Explicit

    def _layer_user_explicit(
        self,
        explicit_provider: str | None,
        explicit_model: str | None,
    ) -> ModelChoice | None:
        """L1: 用户显式指定 → 校验存在+enabled+key → source="user-explicit"。

        provider 不存在/禁用 → 响亮 UserExplicitError (不静默降级);
        explicit_model 单独给出时经 ModelCatalog 反查 provider;
        provider 存在+enabled 但 key 缺失 → 降级下一层 (与其他层一致)。
        """
        if not explicit_provider and not explicit_model:
            return None
        plane = self._control_plane
        if plane is None:
            return None
        provider = explicit_provider
        model = explicit_model
        if provider is None and model:
            # 只给 model → 从 ModelCatalog 反查归属 provider
            info = self._model_catalog.get_model(model) if self._model_catalog else None
            if info is not None:
                provider = info.provider_id
        if not provider:
            return None
        pc = plane.get_provider(provider)
        if pc is None:
            raise UserExplicitError(
                f"L1: explicit provider {provider!r} not found in control plane"
            )
        if not pc.enabled:
            raise UserExplicitError(
                f"L1: explicit provider {provider!r} is disabled"
            )
        if not self._provider_usable(provider):
            return None  # 存在+enabled 但 key 缺失 → 降级 (与其他层一致)
        if model is None:
            cfg = plane.resolve_runtime_config(provider) or {}
            model = cfg.get("model")
        return self._make_choice(
            provider_id=provider,
            model_id=model,
            source=SOURCE_USER_EXPLICIT,
            reasons=[f"user explicit: provider={provider}, model={model or '(default)'}"],
        )

    # ------------------------------------------------------------------ L2 Agent/Skill Policy

    def _layer_agent_skill_policy(
        self,
        agent_id: str | None,
        skill_ids: list[str] | None,
    ) -> ModelChoice | None:
        """L2: Agent/Skill 策略 — Agent Policy > Skill Policy。

        决策语义 (设计 §3):
        1. agent.yaml preferred 可解析 → 用它
        2. 否则遍历 agent.skills[] 的 skill.yaml, 第一个 preferred 可解析 → 用它
        3. preferred 不可用 (key 缺失/禁用) → 该策略 fallback 链依次尝试
        4. 全部未命中 → None (降级 L3)
        """
        if not agent_id and not skill_ids:
            return None
        # 1+3: Agent 策略 (preferred → fallback 链)
        if agent_id:
            policy = self._policy_store.load_agent_policy(agent_id)
            if policy is not None:
                choice = self._try_rule(policy.preferred, SOURCE_AGENT_SKILL_POLICY)
                if choice is not None:
                    return choice
                for rule in policy.fallback:
                    choice = self._try_rule(rule, SOURCE_AGENT_SKILL_POLICY)
                    if choice is not None:
                        return choice
        # 2+3: Skill 策略 (按 skills 顺序, 第一个命中即返回)
        for skill_id in skill_ids or []:
            policy = self._policy_store.load_skill_policy(skill_id)
            if policy is None:
                continue
            choice = self._try_rule(policy.preferred, SOURCE_AGENT_SKILL_POLICY)
            if choice is not None:
                return choice
            for rule in policy.fallback:
                choice = self._try_rule(rule, SOURCE_AGENT_SKILL_POLICY)
                if choice is not None:
                    return choice
        return None

    # ------------------------------------------------------------------ L3 Project Rule

    def _layer_project_rule(
        self,
        project_dir: str | Path | None,
        task_type: str | None,
    ) -> ModelChoice | None:
        """L3: project.yaml 规则 — task_types 优先, 缺省 default。"""
        if project_dir is None:
            return None
        config = self.load_project_rules(project_dir)
        if config is None:
            return None
        rule = None
        if task_type and task_type in config.routing.task_types:
            rule = config.routing.task_types[task_type]
        if rule is None:
            rule = config.routing.default
        if rule is None:
            return None
        return self._try_rule(rule, SOURCE_PROJECT_RULE)

    # ------------------------------------------------------------------ L4 System Recommendation

    def _layer_system_recommendation(
        self,
        required_capabilities: list[str] | None,
    ) -> ModelChoice | None:
        """L4: ModelCatalog.suggest() 取第一个候选 (score/reasons 保留)。

        候选 provider 需可用 (enabled+key); 首个候选不可用 → 依次尝试后续。
        """
        catalog = self._model_catalog
        if catalog is None:
            return None
        try:
            candidates = catalog.suggest(required_capabilities=required_capabilities)
        except Exception:  # noqa: BLE001 — 失败安全: 目录异常 → 降级
            return None
        for cand in candidates:
            if self._provider_usable(cand.provider_id):
                return ModelChoice(
                    model_id=cand.model_id,
                    provider_id=cand.provider_id,
                    score=cand.score,
                    reasons=list(cand.reasons) + [f"layer: {SOURCE_SYSTEM_RECOMMENDATION}"],
                    source=SOURCE_SYSTEM_RECOMMENDATION,
                )
        return None

    # ------------------------------------------------------------------ L5 Fallback

    def _layer_fallback(self) -> ModelChoice | None:
        """L5: ControlPlane.selected_provider_id() → 第一个 enabled+key (S10-021 一致)。"""
        plane = self._control_plane
        if plane is None:
            return None
        pid = plane.selected_provider_id()
        if pid is None:
            return None
        cfg = plane.resolve_runtime_config(pid) or {}
        return self._make_choice(
            provider_id=pid,
            model_id=cfg.get("model"),
            source=SOURCE_FALLBACK,
            reasons=[f"fallback: first enabled provider {pid!r}"],
        )

    # ------------------------------------------------------------------ 配置读取 (失败安全)

    def load_project_rules(self, project_dir: str | Path) -> ProjectLlmConfig | None:
        """project.yaml 读取: <project_dir>/project.yaml 的 llm.routing。

        缺失 → None; 损坏/非法 → warning + None (失败安全, 降级 L4)。
        """
        path = Path(project_dir) / "project.yaml"
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("llm_router: unreadable project.yaml: %s (%s)", path, exc)
            return None
        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            logger.warning("llm_router: corrupt project.yaml: %s (%s)", path, exc)
            return None
        if not isinstance(raw, dict):
            return None
        llm = raw.get("llm")
        if not isinstance(llm, dict):
            return None
        try:
            return ProjectLlmConfig.model_validate(llm)
        except ValidationError as exc:
            logger.warning("llm_router: invalid project.yaml routing: %s (%s)", path, exc)
            return None

    # ------------------------------------------------------------------ 决策审计

    def _emit_decided(self, choice: ModelChoice, task_type: str | None) -> None:
        """router.decided 事件: {provider_id, model_id, source, reason, score}。

        内存 decided_events 恒记录 (G 验收); event_logger 落库失败安全。
        """
        event = {
            "provider_id": choice.provider_id,
            "model_id": choice.model_id,
            "source": choice.source,
            "reason": " | ".join(choice.reasons or []),
            "score": choice.score,
        }
        if task_type:
            event["task_type"] = task_type
        self.decided_events.append(event)
        if self._event_logger is None:
            return
        try:
            record = getattr(self._event_logger, "record", None)
            if record is None:
                return
            record(EVENT_DECIDED, source="router", payload=event)
        except Exception:  # noqa: BLE001 — 审计失败安全: 不拖垮决策
            logger.debug("llm_router: audit emit failed (ignored)")

    # ------------------------------------------------------------------ 内部

    def _try_rule(self, rule: RouterRule | None, source: str) -> ModelChoice | None:
        """单条规则尝试: provider 可用 (enabled+key) → ModelChoice; 否则 None。

        rule.provider 缺省 → ControlPlane 默认 (selected_provider_id);
        rule.model 缺省 → 该 provider 默认模型 (resolve_runtime_config)。
        """
        if rule is None:
            return None
        plane = self._control_plane
        if plane is None:
            return None
        provider = rule.provider
        if provider is None:
            provider = plane.selected_provider_id()  # ControlPlane 默认
            if provider is None:
                return None
        if not self._provider_usable(provider):
            return None
        model = rule.model
        if model is None:
            cfg = plane.resolve_runtime_config(provider) or {}
            model = cfg.get("model")
        return self._make_choice(
            provider_id=provider,
            model_id=model,
            source=source,
            reasons=[f"{source}: rule model={rule.model or '(default)'}"],
        )

    def _provider_usable(self, provider_id: str) -> bool:
        """provider 可用性: 存在 + enabled + key 可解析 (ollama 本地无需 key)。"""
        plane = self._control_plane
        if plane is None:
            return False
        pc = plane.get_provider(provider_id)
        if pc is None or not pc.enabled:
            return False
        if provider_id == "ollama":
            return True
        return bool(plane.resolve_api_key(provider_id))

    def _make_choice(
        self,
        *,
        provider_id: str,
        model_id: str | None,
        source: str,
        reasons: list[str],
    ) -> ModelChoice:
        """统一 ModelChoice 构造 (L1/L2/L3/L5: score=None, reasons 前缀 layer)。

        model_id 为空 → "" (ModelChoice.model_id 非空契约; 调用方装配时
        resolve_runtime_config 仍会取 provider 默认模型兜底)。
        """
        return ModelChoice(
            model_id=model_id or "",
            provider_id=provider_id,
            score=None,
            reasons=[f"layer: {source}"] + reasons,
            source=source,
        )
