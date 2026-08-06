"""factory-core/intelligence/decision.py — DecisionIntelligence 引擎 (Phase 10A-2, ADR-0031)。

决策链 (phase10a2-status.md §范围 + phase10a-plan.md §Q1/Q2/Q4):

    Context → Analysis → Options → Evaluation → Recommendation → Risk → Decision Artifact

- **规则评分, 不绑定 LLM**: Option Score = Capability + Cost + Performance +
  Experience 四因素加权 (每项 0-1 归一, 输入来自 context 提供的评估数据 —
  DecisionOption.factors); score + reasoning 逐条解释为什么分高 (可审计)。
- **Evidence Chain (禁无证据)**: 所有 Decision 必须含 Evidence (六来源:
  artifact/event/experience/external_data/human_input/provider_output);
  context 无证据 → 拒绝分析; 选项无证据 → 拒绝评分 (inherit_context_evidence
  关闭时)。推荐必有证据支撑。
- **Risk Analysis**: 规则检测 risk_level (low/medium/high) — 高风险触发
  (architecture change / deployment strategy / provider migration / cost
  increase 关键词与决策类型); high → requires_approval=true。
- **Approval 集成 (复用 9c, 不建新状态机)**: requires_approval=true → 经
  product ApprovalGate 公共接口 (duck-typed approval_service.request_approval)
  提交请求, approval_request_id 回填 Decision。本模块零 imports product/
  (Removal Isolation) — 装配方 (CLI/测试) 注入服务。
- **只分析+推荐+解释, 不自动执行**: 本引擎不触发任何任务/执行; 执行决策权
  在人 (Approval) 或未来编排层显式调用 (phase10a-plan §Q1 边界铁律)。
- **不实现**: Recommendation Engine (10A-3) / Experience 学习 (10A-4) / LLM
  调用 / 自动执行 — 四因素权重为静态规则, 经验→权重影响链属 10A-4。
- **防自我循环 (phase10a-plan §Q4)**: 只读隔离 (不写 Core 状态) + 人工闸门
  (high 风险必经 Approval) + 证据链 + 低置信度降级为需人工。

事件 (经 intelligence/events.py, 链序):
    analysis.started → analysis.completed → option.evaluated (×N) →
    [approval.* 9c (high 风险绑定)] → decision.created (链终)

模块依赖: stdlib + pydantic + 本层 models/events/store — 零顶层 imports
product/providers/runtime/events.store (Removal Isolation, 同 store.py)。
"""

from __future__ import annotations

from typing import Any, Callable

from .events import (
    record_decision_analysis_completed,
    record_decision_analysis_started,
    record_decision_created,
    record_decision_option_evaluated,
)
from .models import (
    Decision,
    DecisionAnalysis,
    DecisionContext,
    DecisionOption,
    DecisionResult,
    DecisionStatus,
    Evidence,
    RiskAssessment,
    RiskLevel,
)
from .store import DecisionStore

# ------------------------------------------------------------------ 规则评分常量

#: 四因素键序 (capability/cost/performance/experience — phase10a-plan §Q3 影响链)
FACTOR_KEYS: tuple[str, ...] = ("capability", "cost", "performance", "experience")

#: 缺省权重: 能力匹配最重, 经验最轻 (静态规则; 经验→权重影响链属 10A-4)
DEFAULT_FACTOR_WEIGHTS: dict[str, float] = {
    "capability": 0.40,
    "cost": 0.25,
    "performance": 0.20,
    "experience": 0.15,
}

#: 缺失因素的中性分 (冷启动不偏见: 无数据不夸大也不贬低, phase10a-plan §Q3 保护)
NEUTRAL_FACTOR = 0.5

#: 低置信度阈值: 低于此值 → 需人工确认 (requires_approval, §Q4 机制 5)
LOW_CONFIDENCE_THRESHOLD = 0.5

#: 高风险决策类型 (architecture change / deployment strategy / provider
#: migration / provider selection — Provider 选择属迁移类决策: 成本/能力锁定)
HIGH_RISK_DECISION_TYPES: frozenset[str] = frozenset(
    {
        "architecture_change",
        "deployment_strategy",
        "provider_migration",
        "provider_selection",
    }
)

#: 高风险关键词 (约束/目标/选项风险文本命中任一 → high)
HIGH_RISK_KEYWORDS: tuple[str, ...] = (
    "architecture",
    "deployment",
    "migration",
    "cost increase",
    "cost_increase",
    "breaking change",
    "breaking_change",
)

#: 竞争激烈阈值: top 与 runner-up 分差 < 此值 → medium (需人工确认)
CLOSE_COMPETITION_GAP = 0.1

#: risk_level → Decision.risk 数值映射 (10A-1 模型 risk 0-1 兼容)
RISK_LEVEL_TO_NUMERIC: dict[str, float] = {
    RiskLevel.LOW.value: 0.2,
    RiskLevel.MEDIUM.value: 0.5,
    RiskLevel.HIGH.value: 0.8,
}


class DecisionIntelligenceError(Exception):
    """DecisionIntelligence 基础异常。"""


class NoEvidenceError(DecisionIntelligenceError):
    """证据链缺失 (禁无证据决策/推荐)。"""


def _clamp01(value: float) -> float:
    """0-1 归一 (浮点防御)。"""
    return max(0.0, min(1.0, value))


def _contains_high_risk_keyword(text: str) -> bool:
    """高风险关键词检测 (大小写不敏感, 规则评分不绑定 LLM)。"""
    low = text.lower()
    return any(kw in low for kw in HIGH_RISK_KEYWORDS)


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    """权重归一: 校验键集/非负, 并归一化到和为 1.0 (浮点防御)。

    输入 {capability: 0.4, cost: 0.4} → {capability: 0.5, cost: 0.5,
    performance: 0.0, experience: 0.0} (缺失键补 0 再归一)。零和权重
    (全 0) → ValueError。
    """
    unknown = set(weights) - set(FACTOR_KEYS)
    if unknown:
        raise ValueError(f"unknown factor keys: {sorted(unknown)} (allowed: {list(FACTOR_KEYS)})")
    full = {key: weights.get(key, 0.0) for key in FACTOR_KEYS}
    for key, value in full.items():
        if value < 0:
            raise ValueError(f"weight {key!r} must be >= 0, got {value}")
    total = sum(full.values())
    if total <= 0:
        raise ValueError("factor weights must sum to > 0")
    return {key: value / total for key, value in full.items()}


def score_option(
    option: DecisionOption,
    weights: dict[str, float] | None = None,
) -> DecisionOption:
    """规则评分 (纯函数): 四因素加权 → score + reasoning (逐条解释)。

    - option.factors 非空: score = clamp01(Σ factor × weight) (权重缺省
      DEFAULT_FACTOR_WEIGHTS); 缺失因素补中性分 NEUTRAL_FACTOR (冷启动不偏见)。
      reasoning 逐条: 每因素 值/权重/贡献 + 最高贡献因素解释 + 综合公式 —
      必须解释为什么分高 (可审计, 不黑箱)。
    - option.factors 为空: 采用 context 提供的评估分 (option.score), reasoning
      注明"未做规则加权" (数据不足不伪造因素)。
    返回新 DecisionOption (model_copy — 调用方持有的旧引用不更新)。
    """
    w = normalize_weights(weights or DEFAULT_FACTOR_WEIGHTS)
    if option.factors:
        factors = {
            key: _clamp01(float(option.factors.get(key, NEUTRAL_FACTOR))) for key in FACTOR_KEYS
        }
        contributions = {key: factors[key] * w[key] for key in FACTOR_KEYS}
        total = sum(contributions.values())
        score = round(_clamp01(total), 3)
        reasoning = [
            f"{key} {factors[key]:.2f} (权重 {w[key]:.2f}) → 贡献 {contributions[key]:.3f}"
            for key in FACTOR_KEYS
        ]
        top_key = max(FACTOR_KEYS, key=lambda k: contributions[k])
        reasoning.append(
            f"最高贡献因素 {top_key} ({contributions[top_key]:.3f}) — 该选项{_factor_explanation(top_key)}"
        )
        reasoning.append(
            f"综合评分 = Σ(因素 × 权重) = {total:.3f} → 归一 {score:.3f} (0-1)"
        )
    else:
        score = round(_clamp01(float(option.score)), 3)
        reasoning = [
            f"评分 {score:.3f} 来自 context 评估数据 (无四因素明细, 未做规则加权)"
        ]
    return option.model_copy(update={"score": score, "reasoning": reasoning})


def _factor_explanation(key: str) -> str:
    """因素高分语义 (reasoning 可读性, 中文规则模板)。"""
    return {
        "capability": "能力匹配度高 (覆盖需求)",
        "cost": "成本效益好 (单位产出成本低)",
        "performance": "性能表现佳 (延迟/吞吐/成功率)",
        "experience": "历史经验正 (成功样本/高新鲜度)",
    }.get(key, "因素评估占优")


def compute_confidence(
    options: list[DecisionOption],
    analysis: DecisionAnalysis | None = None,
) -> float:
    """置信度 (规则, 纯函数, 0-1 归一): 分数差距 + 证据覆盖 + 因素完整度。

    confidence = 0.5×spread + 0.3×evidence_coverage + 0.2×factor_completeness
    (analysis 存在时再以 0.2 权重混入分析置信度 — 先验)。

    - spread = top − runner-up (单选项时 = top score, 差距视为自身强度),
      clamp 0-1。
    - evidence_coverage = 携带证据的选项占比 (0-1)。
    - factor_completeness = 四因素完整度均值 (0-1)。
    - 空选项 → 0.0 (无可信推荐)。
    """
    if not options:
        return 0.0
    ranked = sorted(options, key=lambda o: o.score, reverse=True)
    top = ranked[0].score
    second = ranked[1].score if len(ranked) > 1 else 0.0
    spread = _clamp01(top - second)
    coverage = sum(1 for o in options if o.evidence) / len(options)
    completeness = sum(len(o.factors) for o in options) / (len(FACTOR_KEYS) * len(options))
    base = 0.5 * spread + 0.3 * _clamp01(coverage) + 0.2 * _clamp01(completeness)
    if analysis is not None:
        base = 0.8 * base + 0.2 * analysis.confidence
    return round(_clamp01(base), 3)


def decision_result(decision: Decision) -> DecisionResult:
    """Decision Artifact → DecisionResult (推荐/备选/置信度/风险/审批派生)。"""
    options = [DecisionOption.model_validate(o) for o in decision.options]
    recommendation = decision.recommendation or ""
    alternatives = [o.id for o in options if o.id != recommendation]
    return DecisionResult(
        decision_id=decision.id,
        recommendation=recommendation,
        alternatives=alternatives,
        confidence=decision.confidence,
        risk_level=decision.risk_level,
        requires_approval=decision.requires_approval,
        approval_request_id=decision.approval_request_id,
    )


def _dedupe_evidence(items: list[Evidence]) -> list[Evidence]:
    """证据去重 (按 lineage_ref, 保序保首条 — 证据链唯一性)。"""
    seen: set[str] = set()
    out: list[Evidence] = []
    for item in items:
        ref = item.lineage_ref()
        if ref in seen:
            continue
        seen.add(ref)
        out.append(item)
    return out


#: approval_service 公共接口 (duck-typed, 9c ProductService 或测试 Fake):
#:   request_approval(artifact_id, gate_id=None, *, by, note) -> ApprovalRequest
ApprovalService = Any


class DecisionIntelligence:
    """决策智能引擎: Context → Analysis → Options → Evaluation → Recommendation
    → Risk → Decision Artifact (规则驱动, 不绑定 LLM, 不自动执行)。

    装配:
    - decision_store: DecisionStore (None = 不持久化, 纯内存 — 测试友好)。
    - logger: EventLogger (None = 事件静默)。
    - factor_weights: 四因素权重覆盖 (缺省 DEFAULT_FACTOR_WEIGHTS, 自动归一)。
    - approval_service: 9c ApprovalGate 公共接口 (ProductService 或同签名
      Fake; None = 高风险决策仍产出但不提交审批请求, 仅标记 requires_approval)。
    - inherit_context_evidence: 选项无自身证据时继承 context.evidence_sources
      (缺省 True, CLI 便捷路径; False → 无证据选项拒绝评分)。
    - now: 可注入时钟 (测试确定性, 缺省当前 UTC)。
    """

    def __init__(
        self,
        decision_store: DecisionStore | None = None,
        logger: Any = None,
        *,
        factor_weights: dict[str, float] | None = None,
        approval_service: ApprovalService | None = None,
        inherit_context_evidence: bool = True,
        now: Callable[[], str] | None = None,
    ) -> None:
        self._store = decision_store
        self._logger = logger
        self._weights = normalize_weights(factor_weights or DEFAULT_FACTOR_WEIGHTS)
        self._approval_service = approval_service
        self._inherit_context_evidence = inherit_context_evidence
        self._now = now

    # ------------------------------------------------------------------ 1. Analysis

    def analyze(self, context: DecisionContext) -> DecisionAnalysis:
        """Context → Analysis: 证据链校验 + 观察 + 因素聚合 + 置信度 (规则)。

        - 禁无证据: context.evidence_sources 为空 → NoEvidenceError (拒绝分析)。
        - observations: 决策类型/目标/约束/候选数 (逐条规则生成, 可读)。
        - factors: 四因素聚合 = 各选项因素均值 (无选项/无因素 → 中性分 0.5,
          冷启动不偏见)。
        - confidence: 0.4 + 0.15 × 证据数 (≤4 封顶, 0-1 归一) — 证据越全
          分析越可信。
        事件: analysis.started → analysis.completed。
        """
        if not context.evidence_sources:
            raise NoEvidenceError(
                "decision context requires at least one evidence source (evidence chain)"
            )
        record_decision_analysis_started(self._logger, context=context)

        observations: list[str] = [f"决策类型: {context.decision_type}"]
        if context.objective:
            observations.append(f"目标: {context.objective}")
        observations.extend(f"约束: {c}" for c in context.constraints)
        observations.append(f"候选选项: {len(context.available_options)}")

        factors: dict[str, float] = {}
        for key in FACTOR_KEYS:
            values = [
                _clamp01(float(o.factors.get(key, NEUTRAL_FACTOR)))
                for o in context.available_options
            ]
            factors[key] = round(sum(values) / len(values), 3) if values else NEUTRAL_FACTOR

        confidence = round(_clamp01(0.4 + 0.15 * min(len(context.evidence_sources), 4)), 3)
        analysis = DecisionAnalysis(
            decision_type=context.decision_type,
            subject=context.subject,
            factors=factors,
            observations=observations,
            confidence=confidence,
            evidence=list(context.evidence_sources),
        )
        record_decision_analysis_completed(self._logger, analysis=analysis, context=context)
        return analysis

    # ------------------------------------------------------------------ 2. Options + Evaluation

    def evaluate_options(
        self,
        context: DecisionContext,
        analysis: DecisionAnalysis | None = None,
    ) -> list[DecisionOption]:
        """Options → Evaluation: 证据校验 + 规则评分 (四因素) + option.evaluated 事件。

        - 无候选选项 → DecisionIntelligenceError (无法推荐)。
        - 禁无证据: 选项无证据且继承关闭 (或 context 也无证据) →
          NoEvidenceError (拒绝评分 — 禁无证据推荐)。
        - 逐选项 score_option → 回填 score/reasoning; 每选项发
          intelligence.decision.option.evaluated。
        """
        if not context.available_options:
            raise DecisionIntelligenceError("decision context has no available options")
        scored: list[DecisionOption] = []
        for raw in context.available_options:
            option = self._ensure_option_evidence(context, raw)
            evaluated = score_option(option, self._weights)
            record_decision_option_evaluated(
                self._logger, option=evaluated, context=context
            )
            scored.append(evaluated)
        return scored

    def _ensure_option_evidence(
        self, context: DecisionContext, option: DecisionOption
    ) -> DecisionOption:
        """选项证据链保障: 无证据 → 继承 context 证据 (缺省) 或 NoEvidenceError。

        继承是"评估依据 = 决策上下文证据链"语义 (选项评分基于上下文事实),
        非伪造: 选项可显式携带自身证据覆盖继承。
        """
        if option.evidence:
            return option
        if self._inherit_context_evidence and context.evidence_sources:
            return option.model_copy(update={"evidence": list(context.evidence_sources)})
        raise NoEvidenceError(
            f"option {option.id!r} has no evidence (evidence chain required; "
            f"use --option ...:TYPE:ID or disable inherit_context_evidence with "
            f"context evidence)"
        )

    # ------------------------------------------------------------------ 3. Recommendation

    def recommend(
        self,
        context: DecisionContext,
        analysis: DecisionAnalysis,
        options: list[DecisionOption],
    ) -> tuple[str, list[str]]:
        """Evaluation → Recommendation: 最高分选项 + 备选 (次高分排序)。

        同分并列 → 按 context 顺序取先者 (稳定排序, 确定性)。只推荐不执行:
        返回选项 id, 不触发任何任务/执行。
        """
        if not options:
            raise DecisionIntelligenceError("no options evaluated")
        ranked = sorted(options, key=lambda o: o.score, reverse=True)
        top = ranked[0]
        alternatives = [o.id for o in ranked[1:]]
        return top.id, alternatives

    # ------------------------------------------------------------------ 4. Risk Analysis

    def assess_risk(
        self,
        context: DecisionContext,
        analysis: DecisionAnalysis,
        options: list[DecisionOption],
        recommendation: str,
    ) -> Any:
        """Risk Analysis (规则检测): risk_level + requires_approval + reasons。

        高风险规则 (命中任一 → high):
          R1 决策类型 ∈ HIGH_RISK_DECISION_TYPES (架构变更/部署策略/Provider
             迁移/Provider 选择)。
          R2 任一选项 risks 文本含高风险关键词 (cost increase/migration/...)。
          R3 约束/目标文本含高风险关键词。
        中风险 (未 high):
          R4 竞争激烈: top − runner-up < CLOSE_COMPETITION_GAP (0.1)。
          R5 低置信度: 最终 confidence < LOW_CONFIDENCE_THRESHOLD (0.5) —
             需人工确认 (§Q4 机制 5, 不自动采纳)。
        requires_approval = (level == high) or (低置信度) — 复用 9c ApprovalGate。
        """
        reasons: list[str] = []
        triggered: list[str] = []

        if context.decision_type in HIGH_RISK_DECISION_TYPES:
            triggered.append(f"decision_type:{context.decision_type}")
            reasons.append(
                f"决策类型 {context.decision_type!r} 属高风险类 "
                f"(架构变更/部署策略/Provider 迁移/选择)"
            )
        for opt in options:
            for risk in opt.risks:
                if _contains_high_risk_keyword(risk):
                    triggered.append(f"option:{opt.id}:{risk}")
                    reasons.append(f"选项 {opt.id!r} 风险信号: {risk}")
        for text in [*context.constraints, context.objective or ""]:
            if text and _contains_high_risk_keyword(text):
                triggered.append(f"context:{text}")
                reasons.append(f"约束/目标含高风险信号: {text}")

        high = bool(triggered)
        confidence = compute_confidence(options, analysis)
        medium = False
        if len(options) >= 2 and not high:
            ranked = sorted(options, key=lambda o: o.score, reverse=True)
            gap = ranked[0].score - ranked[1].score
            if gap < CLOSE_COMPETITION_GAP:
                medium = True
                reasons.append(
                    f"候选分差小 ({gap:.3f} < {CLOSE_COMPETITION_GAP}) — "
                    f"竞争激烈, 需人工确认"
                )
        low_confidence = confidence < LOW_CONFIDENCE_THRESHOLD
        if low_confidence and not high and not medium:
            medium = True
            reasons.append(
                f"置信度低 ({confidence:.2f} < {LOW_CONFIDENCE_THRESHOLD}) — "
                f"需人工确认 (不自动采纳)"
            )

        level = RiskLevel.HIGH if high else (RiskLevel.MEDIUM if medium else RiskLevel.LOW)
        requires_approval = level == RiskLevel.HIGH or low_confidence
        if not reasons:
            reasons.append("未触发高风险规则 — 风险低")
        return RiskAssessment(
            risk_level=level.value,
            requires_approval=requires_approval,
            reasons=reasons,
            rules_triggered=triggered,
        )

    # ------------------------------------------------------------------ 5. Decision Artifact

    def build_decision(
        self,
        context: DecisionContext,
        analysis: DecisionAnalysis,
        options: list[DecisionOption],
        recommendation: str,
        alternatives: list[str],
        risk: Any,
    ) -> Decision:
        """组装 Decision Artifact: 选项全链 + 推荐 + 置信度 + 风险 + 分析快照。

        - evidence = context 证据 ∪ 各选项证据 (lineage_ref 去重, 保序)。
        - confidence = compute_confidence (分数差距/证据覆盖/因素完整度 +
          分析先验); risk = risk_level → 数值映射 (low 0.2/medium 0.5/high 0.8)。
        - status → recommended (已给出推荐); analysis 快照入 Decision.analysis
          (分析全链可审计)。
        """
        evidence = _dedupe_evidence([*context.evidence_sources, *(e for o in options for e in o.evidence)])
        confidence = compute_confidence(options, analysis)
        return Decision(
            decision_type=context.decision_type,
            subject_id=context.subject,
            description=context.objective or f"decision for {context.subject}",
            options=[o.to_dict() for o in options],
            recommendation=recommendation,
            confidence=confidence,
            risk=RISK_LEVEL_TO_NUMERIC[risk.risk_level],
            risk_level=risk.risk_level,
            requires_approval=risk.requires_approval,
            analysis=analysis.to_dict(),
            evidence=evidence,
            status=DecisionStatus.RECOMMENDED,
        )

    # ------------------------------------------------------------------ 6. Approval 集成 (复用 9c)

    def bind_approval(self, decision: Decision, context: DecisionContext, risk: Any) -> Decision:
        """9c Approval 集成 (复用不复制): high 风险 → ApprovalGate 提交请求。

        - requires_approval=false → 原样返回 (低风险无需审批)。
        - requires_approval=true + 已装配 approval_service + context.approval
          绑定点 → request_approval(artifact_id, gate, by, note) →
          approval_request_id 回填 (返回新实例, 落库用返回值)。
        - 装配缺失 (无服务/无绑定点) → 不静默降级: Decision 保持
          requires_approval=true + approval_request_id=None (标记待人工提交;
          引擎不自动执行, 无绕过风险)。
        - 审批服务抛错 (重复申请/门不存在等) → DecisionIntelligenceError
          (响亮失败, 不吞错)。
        """
        if not risk.requires_approval:
            return decision
        binding = context.approval
        if self._approval_service is None or binding is None:
            return decision
        try:
            request = self._approval_service.request_approval(
                binding.artifact_id,
                gate_id=binding.gate,
                by=binding.by,
                note=binding.note or f"intelligence decision {decision.id}",
            )
        except DecisionIntelligenceError:
            raise
        except Exception as exc:  # 9c ProductError/NotFound → 引擎异常 (装配方转 CLI 错误)
            raise DecisionIntelligenceError(f"approval binding failed: {exc}") from exc
        return decision.model_copy(update={"approval_request_id": request.id})

    # ------------------------------------------------------------------ 全链

    def decide(self, context: DecisionContext) -> Decision:
        """完整决策链: Context → Analysis → Options → Evaluation → Recommendation
        → Risk → Decision Artifact (持久化 + 事件 + approval 绑定)。

        返回已落库 (若装配 store) 的 Decision。事件链:
            analysis.started → analysis.completed → option.evaluated (×N)
            → [approval.* 9c, 高风险绑定] → decision.created (链终, 载荷含
            approval_request_id 回填)。
        """
        analysis = self.analyze(context)
        options = self.evaluate_options(context, analysis)
        recommendation, alternatives = self.recommend(context, analysis, options)
        risk = self.assess_risk(context, analysis, options, recommendation)
        decision = self.build_decision(
            context, analysis, options, recommendation, alternatives, risk
        )
        decision = self.bind_approval(decision, context, risk)
        if self._store is not None:
            self._store.save(decision)
        record_decision_created(self._logger, decision=decision)
        return decision

    # ------------------------------------------------------------------ 结果

    def result(self, decision: Decision) -> DecisionResult:
        """Decision Artifact → DecisionResult (CLI/消费方摘要)。"""
        return decision_result(decision)
