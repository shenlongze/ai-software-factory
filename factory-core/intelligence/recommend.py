"""factory-core/intelligence/recommend.py — RecommendationEngine 引擎 (Phase 10A-3, ADR-0032)。

推荐链 (phase10a3-status.md §范围 + phase10a-plan.md §Q3):

    Context → Filter → Evaluation (四因素加权) → Rank → Reasoning → Risk → Recommendation Artifact
                                        ↘ (可选) Decision Artifact → Approval (高风险 9c 复用)

- **多因素评分, 权重配置化**: Final = Capability×W1 + Performance×W2 + Cost×W3 +
  Experience×W4, 缺省权重 0.35/0.30/0.20/0.15 (10A-3 推荐权重, 与 10A-2 决策链
  权重独立 — 决策是"选方案", 推荐是"选执行资源", 能力与性能更重)。权重经构造
  参数注入 (weights), 归一化校验复用 decision.normalize_weights (DRY, 不复制) —
  支持未来 project preference / agent preference / human override 配置化, 禁硬编码。
- **Candidate 四类型统一抽象**: provider/agent/skill/workflow 同一评分公式
  ("专业的人做专业的事"); 类型只是候选属性, 不改变评分 (KISS)。
- **Experience 集成 (Q3 影响链)**: 候选有历史记录 (historical_context 或
  ExperienceStore) → experience 分 = effective_score 聚合 (score×confidence×
  freshness, ExperienceRecord.effective_score 复用); 无记录 → 候选声明经验分
  (缺省 0.5 **中性分**) — **冷启动不惩罚新候选** (phase10a-plan §Q3 保护)。
- **Reasoning 解释系统 (不黑箱)**: 每候选 reasoning 结构化 (ReasoningItem:
  factor/direction/text), 正向原因 (+ 高分因素) / 负向因素 (- 短板) / 中性说明
  (± 冷启动) / 风险提示; top 候选解释随结果输出, 逐条可审计。
- **Risk (规则检测, 不绑定 LLM)**: 无候选 → high; R1 竞争激烈 (top−runner_up <
  0.1) / R2 短板 (< 0.3) → medium; R3 严重短板 (< 0.2) → high; R4 冷启动提示
  (不升级); R5 低置信度 (< 0.5) → medium。requires_approval = high 或低置信度。
- **Decision 集成 (复用 10A-2, 不复制)**: to_decision 将 RecommendationResult →
  Decision Artifact (options/recommendation/confidence/risk/evidence 全链), 高
  风险经 DecisionIntelligence.bind_approval 复用 9c ApprovalGate (注入式, 引擎
  零 imports product/)。
- **只推荐不执行**: 本引擎不触发任何任务/Provider 切换/执行; 执行决策权在人
  (Approval) 或未来编排层显式调用 (phase10a-plan §Q1 边界铁律)。**不实现**:
  自动学习 / 自动优化权重 / 自我修改 / LLM 调用 (10A-4)。
- **防自我循环 (§Q4)**: 只读隔离 (不写 Core 状态) + 证据链 (候选 evidence 随
  Recommendation/Decision 产物) + 低置信度降级需人工 + 冷启动中性 (经验是推荐
  依据, 不是唯一依据)。

事件 (经 intelligence/events.py, 链序):
    recommendation.started → recommendation.candidate.evaluated (×N) →
    recommendation.explained → [recommendation.created (落库时, 10A-1 既有)] →
    recommendation.completed (链终)

模块依赖: stdlib + pydantic + 本层 models/events/store/decision — 零顶层
imports product/providers/runtime/events.store (Removal Isolation, 同 store.py)。
"""

from __future__ import annotations

from typing import Any, Callable

from .decision import (
    CLOSE_COMPETITION_GAP,
    LOW_CONFIDENCE_THRESHOLD,
    NEUTRAL_FACTOR,
    RISK_LEVEL_TO_NUMERIC,
    DecisionIntelligence,
    normalize_weights,
)
from .events import (
    record_recommendation_candidate_evaluated,
    record_recommendation_completed,
    record_recommendation_explained,
    record_recommendation_started,
    record_recommendation_created,
)
from .models import (
    DEFAULT_HALF_LIFE_DAYS,
    Candidate,
    CandidateEvaluation,
    Decision,
    DecisionOption,
    DecisionStatus,
    Evidence,
    ExperienceRecord,
    RecommendationContext,
    RecommendationResult,
    ReasoningDirection,
    ReasoningItem,
    RiskAssessment,
    RiskLevel,
)
from .store import RecommendationStore

# ------------------------------------------------------------------ 规则评分常量

#: 推荐因素键序 (capability/performance/cost/experience — 权重文档序, 与
#: decision.FACTOR_KEYS 同四因素集, 排序按 10A-3 权重表: 能力>性能>成本>经验)
RECOMMEND_FACTOR_KEYS: tuple[str, ...] = (
    "capability",
    "performance",
    "cost",
    "experience",
)

#: 缺省推荐权重 (10A-3, ADR-0032): 能力匹配最重, 经验最轻 — 配置化 (构造注入
#: 覆盖), 禁硬编码; 经验→权重影响链属 10A-4
DEFAULT_WEIGHTS: dict[str, float] = {
    "capability": 0.35,
    "performance": 0.30,
    "cost": 0.20,
    "experience": 0.15,
}

#: 解释方向阈值: 因素分 >= 正向阈值 → 正向原因; <= 负向阈值 → 负向因素;
#: 中间 → 中性说明 (冷启动/一般水平, 不褒不贬)
POSITIVE_THRESHOLD = 0.6
NEGATIVE_THRESHOLD = 0.4

#: 风险短板阈值: 因素分 < 明显短板 → medium; < 严重短板 → high
LOW_FACTOR_THRESHOLD = 0.3
CRITICAL_FACTOR_THRESHOLD = 0.2


class RecommendationEngineError(Exception):
    """RecommendationEngine 基础异常。"""


class NoCandidatesError(RecommendationEngineError):
    """候选集为空 (无法推荐)。"""


def _clamp01(value: float) -> float:
    """0-1 归一 (浮点防御)。"""
    return max(0.0, min(1.0, value))


def _factor_direction(value: float) -> ReasoningDirection:
    """因素分 → 解释方向 (阈值规则, 中性不褒不贬)。"""
    if value >= POSITIVE_THRESHOLD:
        return ReasoningDirection.POSITIVE
    if value <= NEGATIVE_THRESHOLD:
        return ReasoningDirection.NEGATIVE
    return ReasoningDirection.NEUTRAL


def _sign(direction: ReasoningDirection) -> str:
    """方向符号 (可读解释前缀): + 正向 / - 负向 / ± 中性。"""
    return {
        ReasoningDirection.POSITIVE: "+",
        ReasoningDirection.NEGATIVE: "-",
        ReasoningDirection.NEUTRAL: "±",
    }[direction]


def _records_for(
    context: RecommendationContext,
    candidate: Candidate,
    experience_store: Any = None,
) -> list[ExperienceRecord]:
    """候选历史经验记录: historical_context 优先, 其次 ExperienceStore.find。

    无记录 → 空列表 (冷启动, 引擎不臆造经验)。
    """
    records = list(context.historical_context.get(candidate.id) or [])
    if not records and experience_store is not None:
        records = experience_store.find(candidate.id)
    return records


def evaluate_factors(
    candidate: Candidate,
    records: list[ExperienceRecord],
    now: str | None = None,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> tuple[dict[str, float], int, str]:
    """四因素最终分 (纯函数): experience 集成 effective_score 聚合。

    - capability/performance/cost: 候选声明分 (0-1 归一)。
    - experience: 有记录 → 平均 effective_score (score×confidence×freshness,
      ExperienceRecord.effective_score — 历史经验不永久有效); 无记录 → 候选
      声明分 (缺省 0.5 中性 — **冷启动不惩罚**); 声明恰为中性 → neutral。
    - 返回 (factors, 记录数, 来源: records/declared/neutral)。
    """
    factors = {
        "capability": _clamp01(float(candidate.capability)),
        "performance": _clamp01(float(candidate.performance)),
        "cost": _clamp01(float(candidate.cost)),
    }
    if records:
        effective = [r.effective_score(now, half_life_days) for r in records]
        factors["experience"] = _clamp01(sum(effective) / len(effective))
        return factors, len(records), "records"
    declared = _clamp01(float(candidate.experience))
    factors["experience"] = declared
    if abs(declared - NEUTRAL_FACTOR) > 1e-9:
        return factors, 0, "declared"
    return factors, 0, "neutral"


def _experience_text(
    factors: dict[str, float],
    records: list[ExperienceRecord],
    source: str,
    now: str | None = None,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> str:
    """experience 解释文本 (记录统计 / 声明 / 冷启动中性)。"""
    value = factors["experience"]
    if source == "records":
        successes = sum(1 for r in records if r.result.value == "success")
        rate = successes / len(records)
        freshness = sum(r.current_freshness(now, half_life_days) for r in records) / len(records)
        return (
            f"experience {value:.2f} (历史经验 {len(records)} 条, "
            f"成功率 {rate:.0%}, 平均新鲜度 {freshness:.2f})"
        )
    if source == "declared":
        return f"experience {value:.2f} (候选声明经验分, 无历史记录)"
    return f"experience {value:.2f} (冷启动: 无历史经验, 中性分不惩罚)"


def score_candidate(
    candidate: Candidate,
    records: list[ExperienceRecord],
    weights: dict[str, float],
    *,
    required_capabilities: list[str] | None = None,
    now: str | None = None,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> CandidateEvaluation:
    """单候选规则评分 (纯函数): 四因素加权 → score + 分项贡献 + 解释。

    score = clamp01(Σ factor × weight), reasoning 逐条 (方向 + 可读文本,
    可审计); experience 已集成 (records 聚合/声明/中性)。返回新
    CandidateEvaluation (无副作用, 不发事件 — 事件由引擎逐候选发)。
    """
    factors, record_count, source = evaluate_factors(
        candidate, records, now, half_life_days
    )
    w = normalize_weights(weights or DEFAULT_WEIGHTS)
    components = {key: factors[key] * w[key] for key in RECOMMEND_FACTOR_KEYS}
    total = sum(components.values())
    score = round(_clamp01(total), 3)

    cap_context = (
        f"任务要求能力: {', '.join(required_capabilities)}"
        if required_capabilities
        else "无显式能力要求"
    )
    items: list[ReasoningItem] = []
    items.append(
        _factor_reasoning(
            "capability", factors["capability"],
            f"capability {factors['capability']:.2f} ({cap_context})",
        )
    )
    items.append(
        _factor_reasoning(
            "performance", factors["performance"],
            _performance_text(factors["performance"]),
        )
    )
    items.append(
        _factor_reasoning("cost", factors["cost"], _cost_text(factors["cost"]))
    )
    experience_item = _factor_reasoning(
        "experience", factors["experience"],
        _experience_text(factors, records, source, now, half_life_days),
    )
    items.append(experience_item)
    items.append(
        ReasoningItem(
            factor="score",
            direction=ReasoningDirection.NEUTRAL,
            text=f"综合评分 = Σ(因素 × 权重) = {total:.3f} → 归一 {score:.3f} (0-1)",
        )
    )
    return CandidateEvaluation(
        candidate_id=candidate.id,
        candidate_type=candidate.type.value,
        score=score,
        factors=factors,
        score_components=components,
        reasoning=items,
        experience_records=record_count,
        experience_source=source,
    )


def _factor_reasoning(factor: str, value: float, text: str) -> ReasoningItem:
    """构造单因素解释: 方向按阈值 (正/负/中性), 前缀符号。"""
    direction = _factor_direction(value)
    return ReasoningItem(
        factor=factor,
        direction=direction,
        text=f"{_sign(direction)} {text}",
    )


def _performance_text(value: float) -> str:
    """performance 解释文本 (高分/低分语义, 中文规则模板)。"""
    if value >= POSITIVE_THRESHOLD:
        return f"performance {value:.2f} (性能表现佳: 延迟低/吞吐高/成功率高)"
    if value <= NEGATIVE_THRESHOLD:
        return f"performance {value:.2f} (性能短板: 延迟较高/成功率偏低)"
    return f"performance {value:.2f} (性能一般, 无显著优势)"


def _cost_text(value: float) -> str:
    """cost 解释文本 (高 = 成本效益好, 与 decision 因素语义一致)。"""
    if value >= POSITIVE_THRESHOLD:
        return f"cost {value:.2f} (成本效益好: 单位产出成本低)"
    if value <= NEGATIVE_THRESHOLD:
        return f"cost {value:.2f} (成本偏高: 预算风险)"
    return f"cost {value:.2f} (成本适中)"


def compute_recommendation_confidence(evaluations: list[CandidateEvaluation]) -> float:
    """推荐置信度 (规则, 纯函数, 0-1): 分数差距 + 经验覆盖 + 候选深度。

    confidence = 0.5×spread + 0.3×experience_coverage + 0.2×candidate_depth

    - spread = top − runner_up (单候选时 = top score, 差距视为自身强度)。
    - experience_coverage = 有历史经验记录的候选占比 (冷启动 → 低置信度 →
      需人工确认, §Q4 机制 5)。
    - candidate_depth = min(候选数, 5) / 5 (候选越全面推荐越可信, 封顶 5)。
    - 空候选 → 0.0 (无可信推荐)。
    """
    if not evaluations:
        return 0.0
    ranked = sorted(evaluations, key=lambda e: e.score, reverse=True)
    top = ranked[0].score
    second = ranked[1].score if len(ranked) > 1 else 0.0
    spread = _clamp01(top - second)
    coverage = sum(1 for e in evaluations if e.experience_records > 0) / len(evaluations)
    depth = min(len(evaluations), 5) / 5
    return round(_clamp01(0.5 * spread + 0.3 * coverage + 0.2 * depth), 3)


def assess_recommendation_risk(
    evaluations: list[CandidateEvaluation],
    confidence: float,
    filtered_candidates: list[str],
    budget: float | None,
) -> tuple[str, list[str], bool]:
    """推荐风险检测 (规则, 纯函数): risk_level + reasons + requires_approval。

    - 无候选 (全部被过滤) → high (宁缺毋滥, 同 8B 无能力证据不推荐)。
    - R1 竞争激烈: top − runner_up < 0.1 (且 ≥2 候选) → medium。
    - R2 明显短板: top 候选任一因素分 < 0.3 → medium; R3 < 0.2 → high。
    - R4 冷启动: top 无历史经验 → 风险提示 (不升级等级, 经验是推荐依据不是
      唯一依据 — 无经验不惩罚, 但提示人工确认)。
    - R5 低置信度: confidence < 0.5 → medium (需人工确认, §Q4 机制 5)。
    - requires_approval = high 或低置信度 (复用 9c ApprovalGate 语义)。
    """
    reasons: list[str] = []
    if not evaluations:
        return (
            RiskLevel.HIGH.value,
            ["无候选通过质量/预算门槛 — 无法给出推荐 (宁缺毋滥)"],
            True,
        )
    ranked = sorted(evaluations, key=lambda e: e.score, reverse=True)
    top = ranked[0]
    high = False
    medium = False

    if len(ranked) >= 2:
        gap = ranked[0].score - ranked[1].score
        if gap < CLOSE_COMPETITION_GAP:
            medium = True
            reasons.append(
                f"候选分差小 ({gap:.3f} < {CLOSE_COMPETITION_GAP}) — "
                f"竞争激烈, 需人工确认"
            )
    for factor in RECOMMEND_FACTOR_KEYS:
        value = top.factors.get(factor, 0.0)
        if value < CRITICAL_FACTOR_THRESHOLD:
            high = True
            reasons.append(
                f"推荐候选 {top.candidate_id} {factor} 分 {value:.2f} 严重不足"
            )
        elif value < LOW_FACTOR_THRESHOLD:
            medium = True
            reasons.append(
                f"推荐候选 {top.candidate_id} {factor} 分 {value:.2f} 偏低 (明显短板)"
            )
    if top.experience_records == 0:
        reasons.append(
            f"推荐候选 {top.candidate_id} 无历史经验 (冷启动) — 建议人工确认"
        )
    if filtered_candidates:
        reasons.append(
            f"{len(filtered_candidates)} 个候选被过滤 "
            f"({', '.join(filtered_candidates)}) — 推荐基于剩余候选集"
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
        reasons.append("未触发风险规则 — 风险低")
    return level.value, reasons, requires_approval


class RecommendationEngine:
    """推荐智能引擎: Context → Filter → Evaluation → Rank → Reasoning → Risk
    → Recommendation Artifact (+ 可选 Decision Artifact / 9c Approval)。

    装配:
    - recommendation_store: RecommendationStore (None = 不持久化, 纯内存)。
    - logger: EventLogger (None = 事件静默)。
    - weights: 四因素权重覆盖 (缺省 DEFAULT_WEIGHTS 0.35/0.30/0.20/0.15, 自动
      归一 — 配置化, 支持未来 project/agent/human 覆盖)。
    - experience_store: ExperienceStore (可选; 候选在 historical_context 无记录
      时按 subject_id 查询历史经验)。
    - approval_service: 9c ApprovalGate 公共接口 (ProductService 或同签名
      Fake; None = 高风险推荐仍产出但不提交审批请求, 仅标记 requires_approval)。
    - now: 可注入时钟 (测试确定性, 缺省当前 UTC)。

    只推荐不执行: recommend() 只产出 Recommendation Artifact; to_decision() 产出
    Decision Artifact (均不触发任何任务/Provider 切换/执行)。
    """

    def __init__(
        self,
        recommendation_store: RecommendationStore | None = None,
        logger: Any = None,
        *,
        weights: dict[str, float] | None = None,
        experience_store: Any = None,
        approval_service: Any = None,
        now: Callable[[], str] | None = None,
    ) -> None:
        self._store = recommendation_store
        self._logger = logger
        self._weights = normalize_weights(weights or DEFAULT_WEIGHTS)
        self._experience_store = experience_store
        self._decision = DecisionIntelligence(logger=logger, approval_service=approval_service)
        self._now = now
        self._last_candidates: dict[str, Candidate] = {}

    @property
    def weights(self) -> dict[str, float]:
        """当前生效权重 (归一化后, 只读)。"""
        return dict(self._weights)

    # ------------------------------------------------------------------ 过滤

    def _filter(
        self, context: RecommendationContext,
    ) -> tuple[list[Candidate], list[str]]:
        """质量/预算过滤: quality_target (capability 门槛) + budget (cost 门槛)。

        过滤掉的候选 id 记入 filtered_candidates (可审计, 宁缺毋滥: 能力不达标
        或成本不可接受的候选不参与推荐, 同 8B 能力过滤语义)。
        """
        accepted: list[Candidate] = []
        filtered: list[str] = []
        for candidate in context.candidates:
            if (
                context.quality_target is not None
                and candidate.capability < context.quality_target
            ):
                filtered.append(candidate.id)
                continue
            if context.budget is not None and candidate.cost < context.budget:
                filtered.append(candidate.id)
                continue
            accepted.append(candidate)
        return accepted, filtered

    # ------------------------------------------------------------------ 推荐

    def recommend(self, context: RecommendationContext) -> RecommendationResult:
        """完整推荐链: Filter → Evaluation → Rank → Reasoning → Risk → Result。

        返回 RecommendationResult (评分 + 分项解释 + 风险); 有装配 store 时落库
        Recommendation Artifact (10A-1 既有)。事件链:
            recommendation.started → candidate.evaluated (×N) → explained →
            [recommendation.created (落库时)] → completed (链终)。
        不自动执行: 本方法不触发任何任务/Provider 切换。
        """
        record_recommendation_started(self._logger, context=context)

        if not context.candidates:
            raise NoCandidatesError(
                "recommendation context has no candidates (provide at least one "
                "--candidate ID:CAP:PERF:COST:EXP[:TYPE])"
            )

        accepted, filtered = self._filter(context)
        self._last_candidates = {c.id: c for c in accepted}

        if not accepted:
            result = RecommendationResult(
                task_type=context.task_type,
                top_candidate_id=None,
                confidence=0.0,
                risk_level=RiskLevel.HIGH.value,
                risk_reasons=["无候选通过质量/预算门槛 — 无法给出推荐 (宁缺毋滥)"],
                requires_approval=True,
                filtered_candidates=filtered,
            )
            record_recommendation_completed(self._logger, result=result)
            return result

        evaluations: list[CandidateEvaluation] = []
        now_value = self._now() if self._now is not None else None
        for candidate in accepted:
            records = _records_for(context, candidate, self._experience_store)
            evaluation = score_candidate(
                candidate,
                records,
                self._weights,
                required_capabilities=context.required_capabilities,
                now=now_value,
            )
            record_recommendation_candidate_evaluated(
                self._logger, evaluation=evaluation, context=context
            )
            evaluations.append(evaluation)

        ranked = sorted(evaluations, key=lambda e: e.score, reverse=True)
        top = ranked[0]
        confidence = compute_recommendation_confidence(ranked)
        risk_level, risk_reasons, requires_approval = assess_recommendation_risk(
            ranked, confidence, filtered, context.budget
        )
        result = RecommendationResult(
            task_type=context.task_type,
            top_candidate_id=top.candidate_id,
            score=top.score,
            factor_scores=top.factors,
            evaluations=ranked,
            reasoning=list(top.reasoning),
            confidence=confidence,
            risk_level=risk_level,
            risk_reasons=risk_reasons,
            requires_approval=requires_approval,
            filtered_candidates=filtered,
        )
        record_recommendation_explained(self._logger, result=result)

        artifact: Any = None
        if self._store is not None and top.candidate_id:
            top_candidate = self._last_candidates[top.candidate_id]
            artifact = result.to_artifact(
                target_type=top.candidate_type,
                evidence=list(top_candidate.evidence),
            )
            self._store.save(artifact)
            record_recommendation_created(self._logger, recommendation=artifact)

        record_recommendation_completed(self._logger, result=result)
        return result

    # ------------------------------------------------------------------ Decision 集成 (复用 10A-2)

    def to_decision(
        self,
        result: RecommendationResult,
        context: RecommendationContext,
    ) -> Decision | None:
        """RecommendationResult → Decision Artifact (复用 10A-2, 不复制)。

        - options: 全部候选评分快照 → DecisionOption (score/factors/reasoning/
          evidence 全链可追溯); recommendation = top 候选 id。
        - confidence/risk/risk_level/requires_approval 从推荐结果派生 (推荐
          引擎已算好, 不重复调用 DecisionIntelligence 评分 — 权重口径一致)。
        - 高风险 (requires_approval) → 复用 DecisionIntelligence.bind_approval
          (9c ApprovalGate 注入式集成): 已装配 approval_service + context.
          approval 绑定点 → 提交审批请求, approval_request_id 回填。
        - 无推荐 (top_candidate_id None) → None (宁缺毋滥, 无可决策对象)。
        - 只推荐不执行: Decision Artifact 不携带任何执行指令。
        """
        if result.top_candidate_id is None:
            return None
        options: list[dict[str, Any]] = []
        evidence: list[Evidence] = []
        for evaluation in result.evaluations:
            candidate = self._last_candidates.get(evaluation.candidate_id)
            candidate_evidence = list(candidate.evidence) if candidate else []
            if evaluation.candidate_id == result.top_candidate_id:
                evidence = candidate_evidence
            options.append(
                DecisionOption(
                    id=evaluation.candidate_id,
                    name=evaluation.candidate_id,
                    description=candidate.description if candidate else "",
                    score=evaluation.score,
                    factors=dict(evaluation.factors),
                    reasoning=[r.text for r in evaluation.reasoning],
                    evidence=candidate_evidence,
                ).to_dict()
            )
        decision = Decision(
            decision_type="recommendation",
            subject_id=context.task_type,
            description=f"recommendation for task type {context.task_type!r}",
            options=options,
            recommendation=result.top_candidate_id,
            confidence=result.confidence,
            risk=RISK_LEVEL_TO_NUMERIC.get(result.risk_level, 0.2),
            risk_level=result.risk_level,
            requires_approval=result.requires_approval,
            evidence=evidence,
            status=DecisionStatus.RECOMMENDED,
        )
        if result.requires_approval:
            risk = RiskAssessment(
                risk_level=result.risk_level,
                requires_approval=True,
                reasons=list(result.risk_reasons),
            )
            # bind_approval 的 context 形参声明为 DecisionContext, 实际只消费
            # .approval 字段 — RecommendationContext 同构 (duck-typed, 9c 复用)
            decision = self._decision.bind_approval(  # type: ignore
                decision, context, risk
            )
        return decision
