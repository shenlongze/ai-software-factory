"""factory-core/intelligence/experience.py — ExperienceAnalyzer 经验分析器 (Phase 10A-4, ADR-0033)。

经验闭环 (phase10a4-status.md §范围 + phase10a-plan.md §Q3/Q4):

    Task → Recommendation → Execution → Usage → Result → Experience → Better Recommendation

- **只读分析, 非自我修改 (用户强制铁律)**: 分析器只读历史经验记录并输出聚合
  分析; **禁止**自动修改权重 / 自动生成 Skill / 自我复制 Agent / 自动重构 Core
  (未来 Self Evolution 单独设计)。record_experience 只"记录事实", 不触发任何
  执行/修改。
- **全字段记录**: ExperienceRecord 增强 (subject_type/task_type/capability/
  quality_score/cost/duration/evidence/... 见 models.py) — 执行结果 → 经验事实
  快照 (只记录不消费, 防自我循环: 事件/Artifact 是事实, 经验是历史依据)。
- **正负经验 (negative_signal)**: 成功经验提高未来评分, 失败经验降低 —
  聚合有效分 = clamp01(mean(sign × effective_score)), sign = +1 成功 / −1 失败
  (失败样本 = 反事实记录, §Q4 机制 4; 防"只记成功"的自我循环偏差)。全成功 →
  等于平均 effective_score (与 10A-3 语义一致, 向后兼容); 无记录 → 0.0
  (冷启动中性 0.5 由调用方/推荐引擎处理 — 冷启动不惩罚新候选)。
- **时间衰减 (30 天半衰期)**: effective_score = score × confidence × freshness,
  freshness = 0.5^(age/half_life) (模型层 decay_freshness 复用, 不复制); 历史
  经验不永久有效, 被验证 (mark_used) 的经验保持新鲜。
- **按 task_type + capability 聚合**: matches_experience 纯函数过滤 (任务类型
  相等 + 能力交集); 支持 subject_type/subject_id 维度查询。
- **Feedback Loop 入口**: record_experience 把执行结果落库为 ExperienceRecord
  (发 intelligence.feedback.learned); analyze 发 intelligence.experience.analyzed
  (经 EventLogger, 唯一事实源; logger=None 静默)。
- **只记录不执行**: 本模块不触发任何任务/Provider 切换/推荐 (推荐归 10A-3
  引擎, 评估归 evaluate.py); 本层零 imports product/providers/runtime
  (Removal Isolation, 同 store.py 铁律)。

模块依赖: stdlib + pydantic + 本层 models/events — 零顶层 imports
product/providers/runtime/events.store (Removal Isolation)。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from .events import record_experience_analyzed, record_feedback_learned
from .models import (
    DEFAULT_HALF_LIFE_DAYS,
    Evidence,
    ExperienceAggregation,
    ExperienceAnalysis,
    ExperienceDomain,
    ExperienceRecord,
    ExperienceResult,
    _coerce_csv_list,
    format_timestamp,
)

#: 推荐门槛 (10A-4): 有效经验分 ≥ 中性分 0.5 才进入推荐 (与决策层 NEUTRAL_FACTOR
#: 同值 — 常量即文档, 不 import decision 避免跨模块耦合)
RECOMMEND_THRESHOLD = 0.5

#: 每类推荐主体上限 (KISS: 封顶 5 个/类, 与推荐引擎候选深度语义一致)
MAX_RECOMMENDED_PER_TYPE = 5


def _clamp01(value: float) -> float:
    """0-1 归一 (浮点防御)。"""
    return max(0.0, min(1.0, value))


def _now_utc() -> str:
    """统一 UTC 时间戳 (与 Event 存储格式一致, 字符串排序 == 时间排序)。"""
    return format_timestamp(datetime.now(timezone.utc))


def aggregate_experience_factor(
    records: list[ExperienceRecord],
    now: str | None = None,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> float:
    """正负经验聚合有效分 (纯函数): clamp01(mean(sign × effective_score))。

    - sign = +1 成功 / −1 失败 (negative_signal: 失败经验降低未来评分)。
    - 全成功 → 等于平均 effective_score (score×confidence×freshness, 与 10A-3
      推荐引擎语义一致 — 向后兼容既有行为)。
    - 全失败 → 0.0 (失败主导 → 低于冷启动中性 0.5, 惩罚可证实的失败)。
    - 无记录 → 0.0 (调用方决定中性处理, 本函数不臆造经验)。
    """
    if not records:
        return 0.0
    total = 0.0
    for record in records:
        effective = record.effective_score(now, half_life_days)
        total += effective if record.negative_signal is False else -effective
    return _clamp01(total / len(records))


def matches_experience(
    record: ExperienceRecord,
    *,
    task_type: str | None = None,
    capability: list[str] | None = None,
) -> bool:
    """记录是否匹配 task_type + capability 过滤 (纯函数)。

    - task_type 指定: 记录 task_type 必须相等 (空记录不匹配指定任务 — 保守)。
    - capability 指定: 记录 capability 与要求能力必须有交集 (任一能力命中即
      匹配; 记录未声明能力 → 不匹配 — 不能证实则不臆造)。
    - 都未指定 → 全部匹配。
    """
    if task_type is not None and record.task_type != task_type:
        return False
    if capability:
        if not record.capability:
            return False
        if not set(record.capability) & set(_coerce_csv_list(capability)):
            return False
    return True


def aggregate_records(
    records: list[ExperienceRecord],
    *,
    subject_id: str = "",
    subject_type: str = "",
    task_type: str = "",
    capability: list[str] | None = None,
    now: str | None = None,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> ExperienceAggregation:
    """记录集 → ExperienceAggregation (统计 + 正负聚合有效分 + 推理, 纯函数)。"""
    count = len(records)
    if count == 0:
        return ExperienceAggregation(
            subject_id=subject_id,
            subject_type=subject_type,
            task_type=task_type,
            capability=_coerce_csv_list(capability),
            reasoning=["无历史经验记录 (冷启动)"],
        )
    successes = [r for r in records if not r.negative_signal]
    failures = [r for r in records if r.negative_signal]
    effective = aggregate_experience_factor(records, now, half_life_days)
    freshness_values = [r.current_freshness(now, half_life_days) for r in records]
    costs = [r.cost for r in records if r.cost is not None]
    reasoning = [
        f"历史经验 {count} 条 (成功 {len(successes)} / 失败 {len(failures)}, "
        f"成功率 {len(successes) / count:.0%})",
        f"有效经验分 {effective:.3f} = 正负聚合 (score×confidence×freshness, "
        f"{half_life_days:g} 天半衰期; 失败为负信号扣分)",
        f"平均表现 {sum(r.score for r in records) / count:.3f} / "
        f"平均置信度 {sum(r.confidence for r in records) / count:.3f} / "
        f"平均新鲜度 {sum(freshness_values) / count:.3f}",
    ]
    if costs:
        reasoning.append(f"平均成本效益分 {sum(costs) / len(costs):.3f} (高 = 单位产出成本低)")
    return ExperienceAggregation(
        subject_id=subject_id,
        subject_type=subject_type,
        task_type=task_type,
        capability=_coerce_csv_list(capability),
        record_count=count,
        success_count=len(successes),
        failure_count=len(failures),
        success_rate=len(successes) / count,
        avg_score=sum(r.score for r in records) / count,
        avg_confidence=sum(r.confidence for r in records) / count,
        avg_freshness=sum(freshness_values) / count,
        avg_cost=(sum(costs) / len(costs)) if costs else None,
        effective_score=effective,
        reasoning=reasoning,
    )


class ExperienceAnalyzer:
    """经验分析器 (10A-4, ADR-0033): 只读聚合 + 正负经验 + Feedback Loop 记录。

    装配:
    - experience_store: ExperienceStore (None = 无持久化, analyze 返回空聚合,
      record_experience 只返回记录 + 事件 — 纯内存模式)。
    - logger: EventLogger (None = 事件静默)。
    - now: 可注入时钟 (测试确定性, 缺省当前 UTC); half_life_days: 衰减半衰期
      (缺省 30 天, 配置化禁硬编码)。

    **经验分析 ≠ 自我修改**: 全部方法只读历史记录 / 落库新事实记录; 不修改
    权重、不生成 Skill、不复制 Agent、不重构 Core (未来 Self Evolution 单独
    设计, 本层显式不做)。
    """

    def __init__(
        self,
        experience_store: Any = None,
        logger: Any = None,
        *,
        now: Callable[[], str] | None = None,
        half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    ) -> None:
        self._store = experience_store
        self._logger = logger
        self._now = now
        self._half_life_days = half_life_days

    @property
    def half_life_days(self) -> float:
        """衰减半衰期 (只读)。"""
        return self._half_life_days

    def _now_value(self) -> str | None:
        return self._now() if self._now is not None else None

    # ------------------------------------------------------------------ 查询

    def records(
        self,
        *,
        subject_type: str | None = None,
        subject_id: str | None = None,
        task_type: str | None = None,
        capability: list[str] | None = None,
    ) -> list[ExperienceRecord]:
        """查询经验记录 (store 只读; 无 store/无记录 → 空列表, 冷启动不臆造)。"""
        if self._store is None:
            return []
        records = self._store.list_all()
        if subject_type is not None:
            records = [r for r in records if r.subject_type == subject_type]
        if subject_id is not None:
            records = [r for r in records if r.subject_id == subject_id]
        return [
            r for r in records
            if matches_experience(r, task_type=task_type, capability=capability)
        ]

    def aggregate(
        self,
        records: list[ExperienceRecord],
        *,
        subject_id: str = "",
        subject_type: str = "",
        task_type: str = "",
        capability: list[str] | None = None,
    ) -> ExperienceAggregation:
        """记录集聚合 (纯函数包装, 注入时钟/半衰期配置)。"""
        return aggregate_records(
            records,
            subject_id=subject_id,
            subject_type=subject_type,
            task_type=task_type,
            capability=capability,
            now=self._now_value(),
            half_life_days=self._half_life_days,
        )

    # ------------------------------------------------------------------ 分析

    def analyze(
        self,
        *,
        subject_id: str,
        subject_type: str | None = None,
        task_type: str | None = None,
        capability: list[str] | None = None,
    ) -> ExperienceAnalysis:
        """单主体经验分析: 查询 → 聚合 → 事件 (intelligence.experience.analyzed)。

        只读分析, 零副作用 (不改 store/权重/配置 — 经验分析 ≠ 自我修改)。
        无 store → 空聚合 + 事件照发 (冷启动可见)。
        """
        records = self.records(
            subject_type=subject_type,
            subject_id=subject_id,
            task_type=task_type,
            capability=capability,
        )
        agg = self.aggregate(
            records,
            subject_id=subject_id,
            subject_type=subject_type or "",
            task_type=task_type or "",
            capability=capability,
        )
        analysis = ExperienceAnalysis(
            subject_id=subject_id,
            subject_type=subject_type or "",
            task_type=task_type or "",
            capability=_coerce_csv_list(capability),
            aggregation=agg,
        )
        record_experience_analyzed(self._logger, analysis=analysis)
        return analysis

    # ------------------------------------------------------------------ Feedback Loop

    def record_experience(
        self,
        *,
        subject_type: str | ExperienceDomain,
        subject_id: str,
        task_type: str = "",
        capability: list[str] | None = None,
        result: str | ExperienceResult = ExperienceResult.SUCCESS,
        score: float,
        quality_score: float | None = None,
        cost: float | None = None,
        duration: float | None = None,
        confidence: float = 0.5,
        evidence: list[Evidence] | None = None,
        created_at: str | None = None,
    ) -> ExperienceRecord:
        """Feedback Loop 入口: 执行结果 → 经验记录 (落库 + feedback.learned 事件)。

        闭环语义: Task→Recommendation→Execution→Result→Experience→更好推荐 —
        本方法收尾闭环 (结果落库为经验事实), 未来推荐/评估自动读取 (正负聚合
        生效)。**只记录不执行**: 不修改任何权重/推荐配置, 经验是未来推荐的
        依据, 不是即时反馈。
        """
        domain = ExperienceDomain(subject_type) if isinstance(subject_type, str) else subject_type
        result_value = ExperienceResult(result) if isinstance(result, str) else result
        record = ExperienceRecord(
            domain=domain,
            subject_id=subject_id,
            subject_type=domain.value,
            task_type=task_type,
            capability=_coerce_csv_list(capability),
            result=result_value,
            score=score,
            quality_score=quality_score,
            cost=cost,
            duration=duration,
            confidence=confidence,
            evidence=list(evidence or []),
            created_at=created_at or _now_utc(),
        )
        if self._store is not None:
            self._store.save(record)
        record_feedback_learned(self._logger, experience=record)
        return record
