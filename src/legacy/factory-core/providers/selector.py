"""providers/selector.py — ProviderSelector: 四层优先级选择 (Phase 8B-1, ADR-0023)。

设计依据:
- phase8-plan.md §Q5: 选择优先级 1. 显式项目配置 (project.yaml
  runtime_preferences.<task_type>.provider) > 2. Agent 要求 (Agent.runtime_preferences,
  角色级) > 3. Runtime 能力 (Runtime 声明的默认 provider) > 4. 默认 provider
  (ProviderRegistry.default)。配置驱动, 无硬编码选择逻辑 — 本模块是纯决策引擎,
  每一层都是调用方注入的数据 (dict/id), 不自己读任何存储。
- phase8b1-status.md: resolve(project_prefs, agent_prefs, runtime_default,
  registry_default) → ProviderSelection | None; 每层缺失 → 降级下一层; 全部缺失
  → None; 显式覆盖 (CLI --provider) 优先于项目配置。
- 边界: 选择只产出 provider id + 来源; 是否真去调用 Provider (adapter.generate)
  由上层 (Execution 集成层) 决定 — 本阶段仅选择 + 审计 (provider.selected),
  不实现 OpenAI/Claude Adapter (phase8b1-status.md 冻结约束)。

层级语义:
- explicit (CLI --provider 显式覆盖): 用户明确指定 — 未注册/禁用 → 抛
  ProviderNotFoundError (配置缺口显式暴露, 同 cmd_provider_test 契约), 不静默降级。
- project / agent / runtime / default: 配置层 — 条目缺失、id 为空、未注册或
  DISABLED (models.py: DISABLED 不参与选择/执行) 均视为"该层缺失" → 降级下一层。

ProviderSelection.source 取值: explicit | project | agent | runtime | default
(provider.selected 事件 payload 的 source 字段, phase8b1-status.md §3)。

注册表装配 (可选): ProviderSelector(registry) 时对配置层做存在性/状态校验
(未注册/禁用 → 降级); 不装配注册表时只做 id 链决策 (provider 定义由调用方
自行解析) — 纯函数语义, 便于无存储单测。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import preferred_provider
from .models import ProviderDefinition, ProviderStatus
from .registry import ProviderNotFoundError, ProviderRegistry

#: provider.selected 事件 payload 的 source 取值 (优先级链层名)
SELECTION_SOURCES: tuple[str, ...] = ("explicit", "project", "agent", "runtime", "default")


@dataclass(frozen=True)
class ProviderSelection:
    """一次选择结果: provider id + 定义 (注册表装配时回填) + 来源层。"""

    provider_id: str
    provider: ProviderDefinition | None = None
    source: str = "project"  # explicit|project|agent|runtime|default

    def to_dict(self) -> dict[str, Any]:
        return {"provider_id": self.provider_id, "source": self.source}


class ProviderSelector:
    """Provider 选择器: 四层优先级链 (Project > Agent > Runtime > Default), 无硬编码。

    用法 (CLI 集成层, 延迟导入 — Removal Isolation):
        selector = ProviderSelector(provider_registry)
        selection = selector.resolve(
            task_type=task.type,
            explicit=args.provider,            # CLI --provider 显式覆盖
            project_prefs=project_prefs,       # project.yaml runtime_preferences
            agent_prefs=agent_prefs,           # Agent 角色级偏好 (未来字段)
            runtime_default=runtime_default,   # Runtime 目录定义声明的默认 provider
            registry_default=registry_default, # ProviderRegistry.default().id
        )
    """

    def __init__(self, registry: ProviderRegistry | None = None):
        self._registry = registry

    @property
    def registry(self) -> ProviderRegistry | None:
        return self._registry

    # ------------------------------------------------------------------ 选择

    def resolve(
        self,
        *,
        task_type: str,
        explicit: str | None = None,
        project_prefs: dict[str, Any] | None = None,
        agent_prefs: dict[str, Any] | None = None,
        runtime_default: str | None = None,
        registry_default: str | None = None,
    ) -> ProviderSelection | None:
        """按优先级链选择 provider; 全部缺失 → None。

        层级: explicit (CLI --provider) > project (runtime_preferences.\
        <task_type>.provider) > agent (角色级偏好同构) > runtime (Runtime 声明
        默认) > default (ProviderRegistry 默认)。每层缺失 (条目/空 id/未注册/
        DISABLED) → 降级下一层; 显式层未注册/禁用 → ProviderNotFoundError。
        """
        # 层 0: 显式覆盖 (CLI --provider) — 用户意图, 不静默降级
        if explicit is not None and str(explicit).strip():
            provider_id = str(explicit).strip()
            definition = self._resolve_definition(provider_id)
            if self._registry is not None and definition is None:
                raise ProviderNotFoundError(
                    f"provider not found or disabled: {provider_id}"
                )
            return ProviderSelection(
                provider_id=provider_id, provider=definition, source="explicit",
            )
        # 层 1: 显式项目配置 (project.yaml runtime_preferences.<task_type>.provider)
        selection = self._config_layer(
            preferred_provider(project_prefs, task_type), "project",
        )
        if selection is not None:
            return selection
        # 层 2: Agent 要求 (Agent.runtime_preferences, 角色级; 与项目层同构解析)
        selection = self._config_layer(
            preferred_provider(agent_prefs, task_type), "agent",
        )
        if selection is not None:
            return selection
        # 层 3: Runtime 能力 (Runtime 目录定义声明的默认 provider)
        selection = self._config_layer(runtime_default, "runtime")
        if selection is not None:
            return selection
        # 层 4: 默认 provider (ProviderRegistry.default)
        return self._config_layer(registry_default, "default")

    # ------------------------------------------------------------------ 内部

    def _config_layer(self, provider_id: str | None, source: str) -> ProviderSelection | None:
        """配置层选择: 条目缺失/空 id/未注册/禁用 → None (降级下一层)。"""
        if provider_id is None or not str(provider_id).strip():
            return None
        provider_id = str(provider_id).strip()
        definition = self._resolve_definition(provider_id)
        if self._registry is not None and definition is None:
            return None  # 已装配注册表: 未注册/禁用 = 该层缺失
        return ProviderSelection(
            provider_id=provider_id, provider=definition, source=source,
        )

    def _resolve_definition(self, provider_id: str) -> ProviderDefinition | None:
        """按 id 解析定义 (注册表装配时); 未装配 → None (不校验, 调用方自行解析)。

        DISABLED 不参与选择/执行 (models.py ProviderStatus 契约) — 返回 None
        由 _config_layer 降级 / resolve 显式层抛错。
        """
        if self._registry is None:
            return None
        definition = self._registry.get(provider_id)
        if definition is None or definition.status is not ProviderStatus.ACTIVE:
            return None
        return definition


# ==========================================================================
# Phase 8B-2 (ADR-0024): CostAwareSelector — 能力匹配 + 成本感知推荐
# ==========================================================================

from .capability import ProviderCapabilityProfile  # noqa: E402
from .costs import ProviderCostModel, estimate_call_cost  # noqa: E402
from .models import TaskRequirement  # noqa: E402
from .usage import ProviderPerformanceStats, performance_score_from_stats  # noqa: E402

#: provider.selected (source=recommendation) 的 payload source 取值 —
#: 推荐语义 (只推荐不自动切换) 与选择链 source (explicit|project|agent|
#: runtime|default) 区分 (phase8b2-plan.md §4 评审调整 4)。
RECOMMENDATION_SOURCE = "recommendation"


@dataclass(frozen=True)
class Recommendation:
    """一次能力/成本/性能感知推荐结果 (只推荐不自动切换, 评审调整 4)。

    - provider_id: 被推荐 Provider; score: 综合推荐分 (0-1, capability 40% +
      cost 30% + performance 30% 加权, Phase 8B-3); reasons: 推荐理由列表
      (能力匹配/成本/配置优先等, 审计与展示用); source: 恒 "recommendation"
      (与选择链 source 区分)。
    - 三分数 (Phase 8B-3, ADR-0025): capability_score = 能力匹配质量分 (0-1);
      cost_score = 成本分 (free=1.0, 无成本模型=0.0 — 成本信息缺失, 同 8B-2
      \"无成本模型排最后\" 语义; 越贵越低); performance_score = 实测性能分
      (无 usage 数据 → 0.5 中性, 8B-2 兼容)。
    - estimated_cost: 估算调用成本 (USD, 无成本模型 → None, 非真实计费)。
    """

    provider_id: str
    score: float
    reasons: list[str]
    estimated_cost: float | None = None
    source: str = RECOMMENDATION_SOURCE
    provider: ProviderDefinition | None = None
    capability_score: float = 0.0
    cost_score: float = 0.0
    performance_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "provider_id": self.provider_id,
            "score": self.score,
            "reasons": list(self.reasons),
            "estimated_cost": self.estimated_cost,
            "source": self.source,
            "capability_score": self.capability_score,
            "cost_score": self.cost_score,
            "performance_score": self.performance_score,
        }
        if self.provider is not None:
            d["provider"] = self.provider.to_dict()
        return d


@dataclass(frozen=True)
class _Candidate:
    """能力过滤后的内部候选 (推荐排序中间态; Phase 8B-3 增三分数)。"""

    provider_id: str
    score: float  # 综合推荐分 (capability/cost/performance 加权)
    capability_score: float
    cost_score: float
    performance_score: float
    estimated_cost: float | None
    reasons: list[str]
    provider: ProviderDefinition | None = None


class CostAwareSelector:
    """能力感知 + 成本感知 + 性能感知的推荐器 (Phase 8B-2/8B-3, 只推荐不自动切换)。

    选择流程 (phase8b2-plan.md §4 + phase8b3-status.md §3):
      1. 能力过滤   TaskRequirement.required_capabilities 质量分 >= min_quality
                   (能力矩阵缺失/无 profile → 不参与 — 无证据不臆造);
                   budget 过滤 (估算成本 > budget → 排除)。
      2. 配置优先   复用 ProviderSelector.resolve 四层链 (Project > Agent >
                   Runtime > Default, Phase 8B-1 保持) — 配置选中的 provider
                   若通过能力过滤 → 直接推荐 (reasons 标注配置优先)。
      3. 三分数    每个候选计算 capability_score (质量分) + cost_score
                   (成本分) + performance_score (实测性能分, 无 usage → 0.5
                   中性, 8B-2 兼容); score = 0.4*capability + 0.3*cost +
                   0.3*performance (综合推荐分, Phase 8B-3)。
      4. 成本排序   候选按估算成本升序 (free=0 优先; 无成本模型排最后),
                   同成本按性能分降序 → 综合分降序 (无 usage 时性能分全
                   0.5 → 退化为 8B-2 质量分排序)。
      5. 只推荐     返回 Recommendation (provider_id/score/三分数/reasons),
                   不自动切换任何配置 — 是否采纳由调用方决定 (评审调整 4)。
      6. 记录       调用方 (CLI/集成层) 发 provider.selected
                   (source=recommendation) + usage 记录。

    能力/成本/性能数据: capability_profiles/cost_models/usage_stats 构造注入
    (dict id → 模型/统计); 缺省空 dict (无数据 → 能力过滤无候选, 不臆造;
    usage_stats 缺省 → 性能分中性)。registry 装配时配置层做存在性/状态校验
    (同 ProviderSelector); 未装配 → 无候选 (推荐需要目录)。

    兼容性: resolve (Phase 8B-1) 保持原样; 本类独立, 不修改 ProviderSelector。
    """

    def __init__(
        self,
        registry: ProviderRegistry | None = None,
        capability_profiles: dict[str, ProviderCapabilityProfile] | None = None,
        cost_models: dict[str, ProviderCostModel] | None = None,
        usage_stats: dict[str, Any] | None = None,
    ):
        self._registry = registry
        self._profiles = dict(capability_profiles or {})
        self._costs = dict(cost_models or {})
        self._usage_stats = dict(usage_stats or {})
        self._selector = ProviderSelector(registry)

    @property
    def registry(self) -> ProviderRegistry | None:
        return self._registry

    @property
    def capability_profiles(self) -> dict[str, ProviderCapabilityProfile]:
        return dict(self._profiles)

    @property
    def cost_models(self) -> dict[str, ProviderCostModel]:
        return dict(self._costs)

    @property
    def usage_stats(self) -> dict[str, Any]:
        """注入的实测性能统计 (provider_id → ProviderPerformanceStats)。"""
        return dict(self._usage_stats)

    # ------------------------------------------------------------------ 推荐

    def recommend(
        self,
        task_requirements: TaskRequirement | dict[str, Any],
        *,
        preferences: dict[str, Any] | None = None,
        explicit: str | None = None,
        agent_prefs: dict[str, Any] | None = None,
        runtime_default: str | None = None,
        registry_default: str | None = None,
        registry: ProviderRegistry | None = None,
    ) -> Recommendation | None:
        """按 TaskRequirement 推荐 Provider (能力过滤 → 配置优先 → 成本排序)。

        Args:
            task_requirements: TaskRequirement 或 dict (模型校验)。
            preferences: 项目层偏好 (project.yaml runtime_preferences)。
            explicit/agent_prefs/runtime_default/registry_default: 四层链其余
                输入 (同 ProviderSelector.resolve; 显式层未注册 → 抛
                ProviderNotFoundError, 用户意图显式暴露)。
            registry: 覆盖构造时装配的注册表 (None = 用构造装配; 均未装配
                → 无候选返回 None)。

        Returns:
            Recommendation | None (无通过能力过滤的候选 → None — 宁缺毋滥,
            不推荐无能力证据的 Provider)。
        """
        req = _coerce_task_requirement(task_requirements)
        reg = registry if registry is not None else self._registry
        candidates = self._capability_candidates(req, reg)
        if not candidates:
            return None
        # 配置优先 (Phase 8B-1 链保持): 配置选中的 provider 若通过能力过滤 →
        # 直接推荐 (配置即用户意图, 成本排序只作用于无配置/配置不匹配场景)。
        selection: ProviderSelection | None = None
        if reg is not None:
            selection = self._selector.resolve(
                task_type=req.task_type,
                explicit=explicit,
                project_prefs=preferences,
                agent_prefs=agent_prefs,
                runtime_default=runtime_default,
                registry_default=registry_default,
            )
        preferred_id = selection.provider_id if selection is not None else None
        if preferred_id is not None:
            match = next(
                (c for c in candidates if c.provider_id == preferred_id), None,
            )
            if match is not None:
                selection_source = selection.source if selection is not None else "config"
                return self._recommendation(
                    match,
                    reasons=[
                        f"配置优先: {selection_source} 层指定且能力满足要求",
                        *match.reasons,
                    ],
                )
        # 成本感知排序 (多模式归一估算, 升序; 无成本模型排最后)
        best = min(candidates, key=_cost_sort_key)
        reasons = list(best.reasons)
        if preferred_id is not None:
            reasons.append(
                f"配置 provider {preferred_id} 能力不满足要求, 推荐能力匹配的替代"
            )
        return self._recommendation(best, reasons=reasons)

    # ------------------------------------------------------------------ 内部

    def _capability_candidates(
        self,
        req: TaskRequirement,
        registry: ProviderRegistry | None,
    ) -> list[_Candidate]:
        """能力过滤 + 成本估算 + 三分数 (阶段 1/3/4 的候选集构建)。

        过滤: profile 缺失 → 跳过 (无能力证据不推荐); required_capabilities
        任一能力 quality < min_quality → 跳过; budget 非 None 且估算成本 >
        budget → 跳过。
        三分数 (Phase 8B-3): capability_score = 平均质量分 (required 为空 →
        整体矩阵平均 / 矩阵空 → 1.0); cost_score = _cost_score (free=1.0,
        无成本模型=0.5, 越贵越低); performance_score = 实测性能分 (无 usage
        统计 → 0.5 中性, 8B-2 兼容); score = 0.4*capability + 0.3*cost +
        0.3*performance。
        """
        if registry is None:
            return []
        candidates: list[_Candidate] = []
        for definition in registry.list():
            if definition.status is not ProviderStatus.ACTIVE:
                continue  # DISABLED 不参与选择/执行
            profile = self._profiles.get(definition.id)
            if profile is None:
                continue  # 无能力证据 → 不参与能力推荐
            if req.required_capabilities:
                # 过滤: 每个 required 能力须有证据 (键存在) 且 quality >=
                # min_quality; 无证据 (matrix 缺失) → 不通过 (has 语义同
                # capability.py — 不臆造能力)。
                if any(not profile.has(c, req.min_quality) for c in req.required_capabilities):
                    continue
                qualities = [profile.quality(c) for c in req.required_capabilities]
                capability_score = round(sum(qualities) / len(qualities), 4)
                matched = [
                    f"{c}={profile.quality(c):.2f}" for c in req.required_capabilities
                ]
            elif profile.matrix:
                capability_score = profile.average_quality(profile.matrix.keys())
                matched = []
            else:
                capability_score = 1.0  # 无能力要求 + 无矩阵 → 完全匹配
                matched = []
            cost_model = self._costs.get(definition.id)
            cost = estimate_call_cost(cost_model) if cost_model is not None else None
            if req.budget is not None and cost is not None and cost > req.budget:
                continue  # 超出预算上限 → 过滤
            cost_score = _cost_score(cost_model, cost)
            performance_score = performance_score_from_stats(
                self._usage_stats.get(definition.id)
            )
            score = round(
                0.4 * capability_score + 0.3 * cost_score + 0.3 * performance_score, 4,
            )
            reasons = [f"能力匹配: {', '.join(matched) or '无能力要求'}"]
            if cost is not None:
                reasons.append(f"估算成本: {cost:.4f} {self._costs[definition.id].currency}")
            else:
                reasons.append("估算成本: 无成本模型")
            reasons.append(
                f"性能分: {performance_score:.2f} "
                + (
                    f"(实测 {self._usage_stats[definition.id].execution_count} 次执行)"
                    if definition.id in self._usage_stats
                    else "(无 usage 数据, 中性)"
                )
            )
            candidates.append(
                _Candidate(
                    provider_id=definition.id,
                    score=score,
                    capability_score=capability_score,
                    cost_score=cost_score,
                    performance_score=performance_score,
                    estimated_cost=cost,
                    reasons=reasons,
                    provider=definition,
                )
            )
        return candidates

    def _recommendation(
        self, candidate: _Candidate, *, reasons: list[str],
    ) -> Recommendation:
        return Recommendation(
            provider_id=candidate.provider_id,
            score=candidate.score,
            reasons=reasons,
            estimated_cost=candidate.estimated_cost,
            source=RECOMMENDATION_SOURCE,
            provider=candidate.provider,
            capability_score=candidate.capability_score,
            cost_score=candidate.cost_score,
            performance_score=candidate.performance_score,
        )


def _coerce_task_requirement(
    task_requirements: TaskRequirement | dict[str, Any],
) -> TaskRequirement:
    if isinstance(task_requirements, TaskRequirement):
        return task_requirements
    return TaskRequirement.model_validate(task_requirements)


def _cost_sort_key(candidate: _Candidate) -> tuple:
    """成本感知排序键: 估算成本升序 (None 排最后), 同成本性能分降序 → 综合分
    降序, 再 id (Phase 8B-3, ADR-0025 — 三分数加权后排序)。

    无 usage 数据时 performance_score 全为 0.5 常数 → 性能分不区分, 排序
    退化为 8B-2 质量分排序语义 (同成本比能力, 兼容既有相对序)。
    """
    return (
        candidate.estimated_cost is None,  # 无成本模型 → 排最后
        candidate.estimated_cost if candidate.estimated_cost is not None else 0.0,
        -candidate.performance_score,  # 同成本 → 实测性能分降序 (有 usage 数据时)
        -candidate.score,  # 同成本同性能 → 综合分降序 (无 usage 时退化为能力序)
        candidate.provider_id,
    )


#: cost_score 线性衰减归一基准 (USD/次调用) — 估算模型, 非真实计费 (ADR-0025)。
#: 一次调用估算成本达到该基准即成本分归零; 低于基准线性衰减。基准常量即文档。
_COST_SCORE_DECAY: float = 0.01


def _cost_score(
    cost_model: ProviderCostModel | None, cost: float | None,
) -> float:
    """成本分 (0-1, Phase 8B-3 三分数之一, 权重 0.3)。

    - 无成本模型 (cost None) → 0.0 — 成本信息缺失 = 成本维度最劣, 与 8B-2
      \"无成本模型排最后\" 的排序语义一致 (推荐分与排序键同向)。
    - cost <= 0 (free) → 1.0 — 免费最优。
    - 否则线性衰减 max(0, 1 - cost/_COST_SCORE_DECAY) — 越贵越低, 归一基准
      常量即文档 (估算模型, 非真实计费)。
    """
    if cost is None:
        return 0.0
    if cost <= 0.0:
        return 1.0
    return round(max(0.0, 1.0 - cost / _COST_SCORE_DECAY), 4)
