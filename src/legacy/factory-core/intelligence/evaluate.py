"""factory-core/intelligence/evaluate.py — TaskEvaluator 任务评估器 (Phase 10A-4, ADR-0033)。

评估链 (phase10a4-status.md §范围):

    TaskRequirement → (ExperienceAnalyzer 聚合: task_type+capability 过滤 +
    正负经验 effective_score) → 按 subject_type 分组排序 → 推荐
    agents/providers/skills + Confidence + Reasons + Risks → TaskEvaluation

- **基于历史任务表现 (ExperienceAnalyzer 复用, 不复制)**: 评估器只读经验记录,
  按 task_type+capability 匹配 → 按 (subject_type, subject_id) 分组 → 每组正负
  聚合有效分 (成功提高/失败降低, 30 天半衰期衰减) → 排序推荐。
- **推荐执行资源三类型**: agent/provider/skill (与 10A-3 CandidateType 执行
  资源同源词汇; workflow/project/decision 域记录不参与执行资源推荐 — 非执行
  候选)。推荐门槛: 有效分 ≥ 0.5 中性分 (低于中性 = 可证实的失败/负经验主导,
  不推荐 — 宁缺毋滥, 同 8B "无能力证据不推荐" 语义), 每类封顶 5 个。
- **Cold start (中性 0.5 不惩罚)**: 无匹配记录 → 空推荐 + 风险提示 + 低置信度
  (无经验不惩罚主体, 但提示人工确认 — 经验是评估依据, 不是唯一依据)。
- **Confidence (规则, 与推荐引擎同构不复制)**: 0.5×分数差距 + 0.3×类型覆盖 +
  0.2×候选深度 — 冷启动 → 低置信度 → 需人工确认。
- **Risks**: 冷启动 (无记录) / 负经验主导 (失败 > 成功的主体) / 低于中性门槛
  未推荐 / 低置信度。
- **只读评估, 非自我修改**: 评估器不修改 store/权重/配置, 不触发任何执行;
  evaluate() 只产出 TaskEvaluation (经验分析 ≠ 自我修改 — 未来 Self Evolution
  单独设计)。
- **事件**: 经 intelligence/events.py 发 intelligence.task.evaluated (唯一
  事实源; logger=None 静默)。评估基于的历史分析由 ExperienceAnalyzer 发
  intelligence.experience.analyzed (链序可审计)。

模块依赖: stdlib + pydantic + 本层 models/events/experience — 零顶层 imports
product/providers/runtime/events.store (Removal Isolation, 同 store.py 铁律)。
"""

from __future__ import annotations

from typing import Any, Callable

from .events import record_task_evaluated
from .experience import (
    MAX_RECOMMENDED_PER_TYPE,
    RECOMMEND_THRESHOLD,
    ExperienceAnalyzer,
)
from .models import (
    DEFAULT_HALF_LIFE_DAYS,
    TaskEvaluation,
    TaskRequirement,
)

#: 评估置信度权重 (与推荐引擎 compute_recommendation_confidence 同构 —
#: 分数差距/经验覆盖/候选深度; 常量即文档, 不跨模块复制实现)
CONFIDENCE_SPREAD_WEIGHT = 0.5
CONFIDENCE_COVERAGE_WEIGHT = 0.3
CONFIDENCE_DEPTH_WEIGHT = 0.2

#: 参与执行资源推荐的主体类型 (10A-3 CandidateType 同源词汇; workflow/project/
#: decision 域记录是编排/项目/决策经验, 不是执行资源候选)
EVALUATION_SUBJECT_TYPES: tuple[str, ...] = ("agent", "provider", "skill")


def _clamp01(value: float) -> float:
    """0-1 归一 (浮点防御)。"""
    return max(0.0, min(1.0, value))


def _evaluation_confidence(entries: list[dict[str, Any]]) -> float:
    """评估置信度 (规则, 纯函数, 0-1): 分数差距 + 类型覆盖 + 候选深度。

    confidence = 0.5×spread + 0.3×coverage + 0.2×depth
    - spread = top 有效分 − runner-up (单主体时 = top 分, 差距视为自身强度)。
    - coverage = 有主体的类型占比 (agent/provider/skill 三类, 冷启动 → 低)。
    - depth = min(主体数, 5) / 5 (主体越全面评估越可信, 封顶 5)。
    - 无主体 → 0.0 (无可信评估)。
    """
    if not entries:
        return 0.0
    ranked = sorted(entries, key=lambda e: e["score"], reverse=True)
    top = ranked[0]["score"]
    second = ranked[1]["score"] if len(ranked) > 1 else 0.0
    spread = _clamp01(top - second)
    types_present = {e["subject_type"] for e in entries}
    coverage = sum(1 for t in EVALUATION_SUBJECT_TYPES if t in types_present) / len(EVALUATION_SUBJECT_TYPES)
    depth = min(len(ranked), 5) / 5
    return round(
        _clamp01(
            CONFIDENCE_SPREAD_WEIGHT * spread
            + CONFIDENCE_COVERAGE_WEIGHT * coverage
            + CONFIDENCE_DEPTH_WEIGHT * depth
        ),
        3,
    )


class TaskEvaluator:
    """任务评估器 (10A-4, ADR-0033): TaskRequirement → TaskEvaluation。

    装配:
    - experience_store: ExperienceStore (可选; 经 ExperienceAnalyzer 只读)。
    - analyzer: ExperienceAnalyzer (可选; 注入复用 — 缺省自建, 共享时钟/半衰期)。
    - logger: EventLogger (None = 事件静默)。
    - now: 可注入时钟 (测试确定性, 缺省当前 UTC); half_life_days: 衰减半衰期
      (缺省 30 天)。

    只读评估: evaluate() 只产出 TaskEvaluation (推荐执行资源 + 置信度 + 风险),
    不触发任何任务/Provider 切换/执行, 不修改任何状态。
    """

    def __init__(
        self,
        experience_store: Any = None,
        logger: Any = None,
        *,
        analyzer: ExperienceAnalyzer | None = None,
        now: Callable[[], str] | None = None,
        half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    ) -> None:
        self._logger = logger
        self._analyzer = analyzer or ExperienceAnalyzer(
            experience_store, logger, now=now, half_life_days=half_life_days
        )

    def evaluate(self, requirement: TaskRequirement) -> TaskEvaluation:
        """完整评估链: 过滤 → 分组聚合 → 排序 → 推荐 → 置信度 → 风险 → 结果。

        发 intelligence.task.evaluated (评估完成, 唯一事实源)。基于的历史聚合
        由 ExperienceAnalyzer 内部完成 (只读, 零副作用)。
        """
        records = self._analyzer.records(
            task_type=requirement.task_type,
            capability=requirement.required_capabilities,
        )

        # 按 (subject_type, subject_id) 分组 → 每组正负聚合有效分
        groups: dict[tuple[str, str], list[Any]] = {}
        for record in records:
            stype = record.subject_type or record.domain.value  # 模型层已派生, 防御双保险
            groups.setdefault((stype, record.subject_id), []).append(record)

        all_entries: list[dict[str, Any]] = []
        by_type: dict[str, list[dict[str, Any]]] = {t: [] for t in EVALUATION_SUBJECT_TYPES}
        below_threshold: list[str] = []
        negative_dominant: list[str] = []
        for (stype, subject_id), group_records in groups.items():
            if stype not in by_type:
                continue  # workflow/project/decision 非执行资源候选, 不参与推荐
            agg = self._analyzer.aggregate(
                group_records,
                subject_id=subject_id,
                subject_type=stype,
                task_type=requirement.task_type,
                capability=requirement.required_capabilities,
            )
            entry: dict[str, Any] = {
                "id": subject_id,
                "subject_type": stype,
                "score": round(agg.effective_score, 3),
                "records": agg.record_count,
                "success_rate": round(agg.success_rate, 3),
                "reasoning": list(agg.reasoning),
            }
            all_entries.append(entry)
            if agg.failure_count > agg.success_count and agg.record_count > 0:
                negative_dominant.append(f"{stype}:{subject_id}")
            if entry["score"] >= RECOMMEND_THRESHOLD:
                by_type[stype].append(entry)
            else:
                below_threshold.append(f"{stype}:{subject_id} ({entry['score']:.2f})")

        for stype in by_type:
            by_type[stype].sort(key=lambda e: e["score"], reverse=True)
            by_type[stype] = by_type[stype][:MAX_RECOMMENDED_PER_TYPE]

        confidence = _evaluation_confidence(all_entries)

        reasoning = [
            f"基于 {len(records)} 条历史经验评估 (task_type={requirement.task_type!r}, "
            f"capability={', '.join(requirement.required_capabilities) or '-'})",
        ]
        for stype in EVALUATION_SUBJECT_TYPES:
            for entry in by_type[stype]:
                reasoning.append(
                    f"推荐 {stype} {entry['id']}: 有效经验分 {entry['score']:.3f} "
                    f"({entry['records']} 条, 成功率 {entry['success_rate']:.0%})"
                )
        if not all_entries:
            reasoning.append("无匹配历史经验 — 冷启动, 无可依据的评估")

        risks: list[str] = []
        if not all_entries:
            risks.append(
                "冷启动: 无匹配任务类型/能力的历史经验 — 评估置信度低, 建议人工确认"
            )
        if negative_dominant:
            risks.append(
                "负经验主导: " + ", ".join(negative_dominant)
                + " 失败经验多于成功 (negative_signal) — 谨慎采用"
            )
        if below_threshold:
            risks.append(
                f"{len(below_threshold)} 个主体有效经验分低于中性门槛 (失败/负经验扣分): "
                + ", ".join(below_threshold[:5])
            )
        if confidence < 0.5 and all_entries:
            risks.append(f"置信度低 ({confidence:.2f} < 0.5) — 建议人工确认")

        evaluation = TaskEvaluation(
            task_type=requirement.task_type,
            required_capabilities=list(requirement.required_capabilities),
            recommended_agents=by_type["agent"],
            recommended_providers=by_type["provider"],
            recommended_skills=by_type["skill"],
            reasoning=reasoning,
            confidence=confidence,
            risks=risks,
        )
        record_task_evaluated(self._logger, evaluation=evaluation)
        return evaluation
