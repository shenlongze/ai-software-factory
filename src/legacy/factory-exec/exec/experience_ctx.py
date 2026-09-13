"""factory-exec/exec/experience_ctx.py — Context Experience (Sprint 4 T4.4)。

统一 ContextExperienceRecord (10+ 字段, 序列化可审计) + 本地 JSON Store
(禁数据库) + Experience Extractor (成功/失败自动提取) + Similar Matching +
Failure Learning (symbol miss 提权持久化)。

设计依据 (docs/validation/sprint4-t44-experience-feedback-design.md, 已批准):

    Task → Context Decision (RankingTrace) → Budget (BudgetTrace)
      → Stage (ProgressiveTrace) → Execution (ExecutionResult)
      → Validation (ValidationResult) → 【Experience】→ 下一次任务更好

全链路 Trace: 一条 ContextExperienceRecord 同时承载 ranking_trace +
progressive_trace + budget_trace + execution_result + validation_result —
任何一环可回答"为什么这么选" (可审计)。

与 10A-4 ExperienceRecord 的关联 (复用/映射, 不重复造轮子):
- 10A-4 (factory-core intelligence) = 聚合信号 (正负聚合/半衰期/推荐背书);
  本模块 = 执行侧全链路明细 (上下文决策/预算/阶段/验证全部落盘)。
- to_legacy_fields() 把本记录映射为 ExperienceAnalyzer.record_experience
  的 kwargs (domain=agent, task_type, result, score...) — 由既有
  ExperienceRecorder (exec/experience.py) 落 10A-4 库, 本模块不重复建库。

Feedback 接入 (权重 ≤20% 硬限制, 历史错误不污染未来):
- RankingEngine: experience_match (0.07) + history_success (0.08) 合计
  0.15 ≤ 0.20 — 经验只背书不替代 (ADR-0033 语义);
- BudgetController: budget_recommendation() 只取成功记录实际用量均值,
  生效预算 clamp 在 [0.8×policy, 1.2×policy] (偏差 ≤20%);
- ProgressiveLoader: stage_order_from_experience() 只取成功记录阶段路径,
  需 ≥2 条共识才重排非必载阶段 (冷启动不臆造)。

KISS 边界: 本模块只依赖 stdlib + pydantic + 本层 models (零 Core 导入 —
intelligence 经 duck-typed analyzer/store 注入); 本模块可独立 import 无环
(ranking.py 单向依赖本模块, 反向不成立)。Store 是审计增强数据 (同 8B-2
usage.json 语义): 损坏 → 失败安全空, 绝不破坏执行链。
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, Field, field_validator

from .budget import BUDGET_RECOMMEND_SPAN  # 预算推荐偏差上限 (单一事实源, 无环)

#: 相似度阈值 (find_similar 最低命中分; 冷启动保守)
SIMILARITY_THRESHOLD = 0.3
#: 相似度权重 (加权规则, 和 = 1.0 — 可复算审计)
SIMILARITY_WEIGHTS: dict[str, float] = {
    "task_type": 0.4,
    "keyword": 0.3,
    "symbol": 0.2,
    "failure_type": 0.1,
}
#: 失败类型 (结构化 — Extractor 分类/Store query/失败学习共用词汇)
FAILURE_SYMBOL_MISS = "symbol_miss"
FAILURE_CONTEXT_INSUFFICIENT = "context_insufficient"
FAILURE_TOKEN_OVERFLOW = "token_overflow"
FAILURE_OPERATION = "operation_failure"
FAILURE_VALIDATION = "validation_failure"
FAILURE_TYPES: tuple[str, ...] = (
    FAILURE_SYMBOL_MISS,
    FAILURE_CONTEXT_INSUFFICIENT,
    FAILURE_TOKEN_OVERFLOW,
    FAILURE_OPERATION,
    FAILURE_VALIDATION,
)


def _now_utc() -> str:
    """统一 UTC 时间戳 (ISO 8601, 字符串排序 == 时间排序)。"""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _new_ctx_id() -> str:
    return f"EXPCTX-{uuid.uuid4().hex[:8]}"


def _clamp01(value: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, v))


def _nonneg_int(value: Any) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, v)


def _norm_str(value: Any) -> str:
    return str(value) if value is not None else ""


def _norm_list(value: Any) -> list[Any]:
    return list(value) if value is not None else []


def _norm_dict(value: Any) -> dict[str, Any]:
    return dict(value) if value is not None else {}


# ================================================================ ContextExperienceRecord

class ContextExperienceRecord(BaseModel):
    """统一上下文经验记录 (T4.4; 10+ 字段, 全链路 Trace 可审计)。

    - task_type / task_summary: 任务分类 + 摘要 (检索键);
    - context_used: 实际使用的上下文 (candidates: {id,type,source,level} 明细 +
      content_refs: 内容引用清单 — Context Decision 的"用了什么");
    - ranking_trace: Ranking 决策明细 (候选总数/排名序/每候选分数/入选集);
    - progressive_trace: 渐进加载 Trace (阶段序列/决策/symbol_miss/overflow);
    - budget_trace: 预算审计 (planned/requested/actual/token/overflow/degraded);
    - execution_result: 执行结果事实 (status/error/duration/usage);
    - validation_result: 验证结果事实 (passed/attempts/output 摘要);
    - failure_type: 结构化失败类型 (成功 → 空; 五类受控词汇);
    - quality_score: 产出质量分 (0-1);
    - recommendation: 提取的经验建议 (供下一次任务初始化);
    - missing_symbols / missing_context: 失败学习明细 (下一次候选提权依据);
    - created_at: 记录时间 (审计锚点)。

    序列化: to_dict() 全字段 JSON 友好 (可审计); 反序列化经
    ContextExperienceRecord.model_validate (Store 读路径)。extra=forbid
    (拼写错误即失败 — 与 ProgressiveTrace/BudgetTrace 同契约)。
    """

    model_config = {"extra": "forbid"}

    id: str = Field(default_factory=_new_ctx_id)
    task_type: str = "development"
    task_summary: str = ""
    context_used: dict[str, Any] = Field(default_factory=dict)
    ranking_trace: dict[str, Any] = Field(default_factory=dict)
    progressive_trace: dict[str, Any] = Field(default_factory=dict)
    budget_trace: dict[str, Any] = Field(default_factory=dict)
    execution_result: dict[str, Any] = Field(default_factory=dict)
    validation_result: dict[str, Any] = Field(default_factory=dict)
    failure_type: str = ""
    quality_score: float = 0.0
    recommendation: str = ""
    missing_symbols: list[str] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_utc)

    @field_validator("task_type", "task_summary", "failure_type", "recommendation",
                     mode="before")
    @classmethod
    def _strs_none(cls, v: Any) -> str:
        return _norm_str(v)

    @field_validator("context_used", "ranking_trace", "progressive_trace",
                     "budget_trace", "execution_result", "validation_result",
                     mode="before")
    @classmethod
    def _dicts_none(cls, v: Any) -> dict[str, Any]:
        return _norm_dict(v)

    @field_validator("missing_symbols", "missing_context", mode="before")
    @classmethod
    def _lists_none(cls, v: Any) -> list[str]:
        return [str(x) for x in _norm_list(v)]

    @field_validator("quality_score", mode="before")
    @classmethod
    def _score_clamp(cls, v: Any) -> float:
        return _clamp01(v)

    @property
    def is_success(self) -> bool:
        """成功判定 (execution_result.status == success 且无失败类型)。"""
        status = _norm_str(self.execution_result.get("status"))
        return status == "success" and not self.failure_type

    @property
    def missing_symbols_list(self) -> list[str]:
        """missing_symbols 兼容别名 (失败学习读取面)。"""
        return list(self.missing_symbols)

    def to_dict(self) -> dict[str, Any]:
        """全字段 JSON 友好序列化 (审计/落盘/断言共用)。"""
        return self.model_dump(mode="json")

    def to_legacy_fields(self) -> dict[str, Any]:
        """→ 10A-4 ExperienceAnalyzer.record_experience kwargs (复用/映射)。

        由既有 ExperienceRecorder (exec/experience.py) 落 10A-4 ExperienceStore
        — 本模块不重复建库; 经验是背书不是替代 (score 0.8/0.2 同 exec 语义)。
        """
        success = self.is_success
        return {
            "subject_type": "agent",
            "subject_id": _norm_str(self.execution_result.get("employee_id"))
            or "unknown-employee",
            "task_type": self.task_type,
            "capability": ["development"],
            "result": "success" if success else "failure",
            "score": 0.8 if success else 0.2,
            "quality_score": self.quality_score if self.quality_score else (
                1.0 if success else 0.3
            ),
            "cost": self.budget_trace.get("cost_benefit"),
            "duration": self.execution_result.get("duration"),
            "confidence": 0.8,
            "evidence": [
                {
                    "source_type": "event",
                    "source_id": self.id,
                    "description": f"context experience: {self.failure_type or 'success'}",
                    "confidence": 1.0,
                }
            ],
        }


# ================================================================ Similar Matching (规则加权)

def _tokenize(text: str) -> set[str]:
    """摘要/引用分词 (小写; 空白 + 常见分隔符拆分; KISS)。"""
    import re

    return {
        t for t in re.split(r"[^a-zA-Z0-9_\u4e00-\u9fff]+", text.lower())
        if t and len(t) > 1
    }


def keyword_overlap(
    a_keywords: Iterable[str], b_keywords: Iterable[str]
) -> float:
    """关键词重合度 (Jaccard; 空集 → 0 — 不能证实则不臆造)。"""
    a = set(a_keywords)
    b = set(b_keywords)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def record_similarity(
    record: ContextExperienceRecord,
    *,
    task_type: str = "",
    keywords: Iterable[str] = (),
    symbols: Iterable[str] = (),
    failure_type: str = "",
) -> float:
    """记录与查询的相似度 (加权规则, 设计 §5; 可复算审计)。

    权重 (SIMILARITY_WEIGHTS, 和 = 1.0):
    - task_type 精确匹配 0.4;
    - keyword 重合度 (Jaccard, 记录摘要 + 内容引用) 0.3;
    - symbol 重合 (missing_symbols/内容引用 vs 查询符号) 0.2;
    - failure_type 精确匹配 0.1。

    查询项缺省 → 该维度中性 (不扣分, 取满权重? 否 — 缺失维度按 0 计并
    等比缩放, 避免"什么都没给"却因默认维度得高分)。实现: 只对提供了
    查询条件的维度计分, 总分按提供维度权重和归一。
    """
    provided: list[tuple[str, float]] = []
    if task_type:
        provided.append(("task_type", 1.0 if record.task_type == task_type else 0.0))
    kw = list(keywords)
    if kw:
        record_words = _tokenize(record.task_summary) | _tokenize(
            " ".join(str(x) for x in _norm_list(record.context_used.get("content_refs")))
        )
        provided.append(("keyword", keyword_overlap(kw, record_words)))
    syms = list(symbols)
    if syms:
        record_syms = set(record.missing_symbols)
        record_syms |= _tokenize(" ".join(str(x) for x in _norm_list(
            record.context_used.get("content_refs")
        )))
        provided.append(("symbol", keyword_overlap(syms, record_syms)))
    if failure_type:
        provided.append(
            ("failure_type", 1.0 if record.failure_type == failure_type else 0.0)
        )
    if not provided:
        return 0.0
    total_weight = sum(SIMILARITY_WEIGHTS[d] for d, _ in provided)
    if total_weight <= 0:
        return 0.0
    return round(
        sum(SIMILARITY_WEIGHTS[d] * score for d, score in provided) / total_weight,
        4,
    )


def find_similar_records(
    records: Iterable[ContextExperienceRecord],
    *,
    task_type: str = "",
    keywords: Iterable[str] = (),
    symbols: Iterable[str] = (),
    failure_type: str = "",
    threshold: float = SIMILARITY_THRESHOLD,
    limit: int = 5,
) -> list[tuple[ContextExperienceRecord, float]]:
    """记录集 → 相似记录 (降序; 低于阈值剔除; KISS 封顶 limit 条)。"""
    scored = [
        (r, record_similarity(
            r, task_type=task_type, keywords=keywords,
            symbols=symbols, failure_type=failure_type,
        ))
        for r in records
    ]
    scored = [pair for pair in scored if pair[1] >= threshold]
    scored.sort(key=lambda pair: (-pair[1], pair[0].created_at, pair[0].id))
    return scored[: max(0, limit)]


# ================================================================ ContextExperienceStore (本地 JSON, 禁 DB)

class ContextExperienceStore:
    """上下文经验库 (本地 JSON 单文件; 禁数据库; 原子写; 损坏失败安全)。

    - 数据空间: <root>/context_experience.json (独立于 10A-4 intelligence 库);
    - save(): 原子写 (tmp + os.replace), 并发/中断安全;
    - 损坏失败安全 (审计增强数据, 同 8B-2 usage.json 语义): 读取损坏/单条
      校验失败 → 空库/跳过该条 — 读命令永不因经验文件失败 (执行链不破坏);
    - query(): 按 task_type / failure_type / 关键词过滤;
    - find_similar(): 相似记录 (规则加权, 供下一次任务初始化);
    - statistics(): 计数/成功率/质量/预算聚合 (审计)。
    """

    def __init__(self, root: str | Path, filename: str = "context_experience.json") -> None:
        self.root = Path(root)
        self.filename = filename
        self.path = self.root / filename

    # ------------------------------------------------------------- 读写

    def _read_all(self) -> list[ContextExperienceRecord]:
        """读全部记录 (损坏 → 空库, 失败安全; 单条坏 → 跳过该条)。"""
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        records: list[ContextExperienceRecord] = []
        for item in _norm_list(raw):
            try:
                if isinstance(item, dict):
                    records.append(ContextExperienceRecord.model_validate(item))
            except Exception:  # noqa: BLE001 — 单条损坏跳过 (失败安全)
                continue
        return records

    def _write_all(self, records: list[ContextExperienceRecord]) -> None:
        """全量原子写 (tmp + os.replace); 目录自动创建。"""
        self.root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            [r.to_dict() for r in records], ensure_ascii=False, indent=2
        )
        fd, tmp = tempfile.mkstemp(
            prefix=f".{self.filename}.", suffix=".tmp", dir=str(self.root)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------- CRUD

    def save(self, record: ContextExperienceRecord) -> ContextExperienceRecord:
        """落库一条记录 (按 id 覆盖; 返回同一实例)。"""
        if not isinstance(record, ContextExperienceRecord):
            record = ContextExperienceRecord.model_validate(record)
        records = self._read_all()
        records = [r for r in records if r.id != record.id]
        records.append(record)
        self._write_all(records)
        return record

    def save_many(self, records: Iterable[ContextExperienceRecord]) -> int:
        """批量落库 (覆盖式; 返回落库条数)。"""
        items = [r if isinstance(r, ContextExperienceRecord)
                 else ContextExperienceRecord.model_validate(r) for r in records]
        current = {r.id: r for r in self._read_all()}
        for r in items:
            current[r.id] = r
        self._write_all(list(current.values()))
        return len(items)

    def list_all(self) -> list[ContextExperienceRecord]:
        """全部记录 (按 created_at 升序 — 审计友好)。"""
        return sorted(self._read_all(), key=lambda r: (r.created_at, r.id))

    def get(self, record_id: str) -> ContextExperienceRecord | None:
        for r in self._read_all():
            if r.id == record_id:
                return r
        return None

    def count(self) -> int:
        return len(self._read_all())

    # ------------------------------------------------------------- 查询

    def query(
        self,
        *,
        task_type: str = "",
        failure_type: str = "",
        keywords: Iterable[str] = (),
        success_only: bool = False,
    ) -> list[ContextExperienceRecord]:
        """组合过滤 (全缺省 → 全部; 空字符串 = 无过滤, 同 16A find 语义)。"""
        records = self._read_all()
        if task_type:
            records = [r for r in records if r.task_type == task_type]
        if failure_type:
            records = [r for r in records if r.failure_type == failure_type]
        if success_only:
            records = [r for r in records if r.is_success]
        kw = list(keywords)
        if kw:
            def _hit(r: ContextExperienceRecord) -> bool:
                hay = f"{r.task_summary} {' '.join(str(x) for x in _norm_list(r.context_used.get('content_refs')))}"
                return any(k.lower() in hay.lower() for k in kw)
            records = [r for r in records if _hit(r)]
        return sorted(records, key=lambda r: (r.created_at, r.id))

    def find_similar(
        self,
        *,
        task_type: str = "",
        keywords: Iterable[str] = (),
        symbols: Iterable[str] = (),
        failure_type: str = "",
        limit: int = 5,
    ) -> list[tuple[ContextExperienceRecord, float]]:
        """相似记录 (规则加权; 供下一次任务初始化: context 选择/预算建议)。"""
        return find_similar_records(
            self._read_all(),
            task_type=task_type, keywords=keywords, symbols=symbols,
            failure_type=failure_type, limit=limit,
        )

    # ------------------------------------------------------------- 统计

    def statistics(self) -> dict[str, Any]:
        """聚合统计 (审计): 总数/任务类型分布/失败分布/成功率/质量/预算。"""
        records = self._read_all()
        total = len(records)
        by_task: dict[str, int] = {}
        by_failure: dict[str, int] = {}
        success_count = 0
        quality_sum = 0.0
        actual_sum = 0
        actual_count = 0
        for r in records:
            by_task[r.task_type] = by_task.get(r.task_type, 0) + 1
            if r.failure_type:
                by_failure[r.failure_type] = by_failure.get(r.failure_type, 0) + 1
            if r.is_success:
                success_count += 1
            quality_sum += r.quality_score
            actual = _nonneg_int(r.budget_trace.get("actual_usage"))
            if actual > 0:
                actual_sum += actual
                actual_count += 1
        return {
            "total": total,
            "by_task_type": by_task,
            "by_failure_type": by_failure,
            "success_count": success_count,
            "failure_count": total - success_count,
            "success_rate": round(success_count / total, 3) if total else 0.0,
            "avg_quality_score": round(quality_sum / total, 3) if total else 0.0,
            "avg_budget_actual": round(actual_sum / actual_count) if actual_count else None,
        }


# ================================================================ Failure Learning (失败学习)

def symbol_miss_files_from_experience(
    records: Iterable[ContextExperienceRecord],
    files: Iterable[str] | None = None,
) -> set[str]:
    """历史 symbol_miss 失败记录 → 相关文件集 (下一次候选提权依据)。

    语义 (设计 §7): 失败记录 (failure_type == symbol_miss) 的 context_used
    candidates 里的 source 文件 = 该任务类型下 symbol 锚点易错文件 —
    下一次同名候选 experience_match +0.2 (与 T4.1 启发式合并, 持久化优先)。
    files 给定 → 只返回 files 内的 (候选集过滤, 防幻影路径)。
    """
    out: set[str] = set()
    for r in records:
        if r.failure_type != FAILURE_SYMBOL_MISS:
            continue
        for cand in _norm_list(r.context_used.get("candidates")):
            src = _norm_str(cand.get("source") if isinstance(cand, dict) else cand)
            if src:
                out.add(src)
    if files is not None:
        allowed = set(files)
        out &= allowed
    return out


def file_success_rates(
    records: Iterable[ContextExperienceRecord],
) -> dict[str, float]:
    """记录集 → 文件级成功率 (history_success 因素真实经验输入)。

    每个文件的成功率 = 该文件出现过的记录中成功占比 (未出现文件 → 无键,
    调用方按冷启动 0.5 中性处理 — 与 RankingEngine 语义一致)。
    """
    stat: dict[str, list[bool]] = {}
    for r in records:
        for cand in _norm_list(r.context_used.get("candidates")):
            src = _norm_str(cand.get("source") if isinstance(cand, dict) else cand)
            if not src:
                continue
            stat.setdefault(src, []).append(r.is_success)
    return {src: round(sum(flags) / len(flags), 3) for src, flags in stat.items()}


def budget_recommendation(
    records: Iterable[ContextExperienceRecord],
    task_type: str = "",
) -> int | None:
    """预算推荐: 同类任务成功记录实际用量均值 (设计 §4; 历史错误不污染)。

    - 只取成功记录 (失败/降级记录不参与 — 失败实际用量无参考价值);
    - 无成功记录 → None (冷启动不臆造, 用策略预算);
    - 返回推荐值后由 BudgetController clamp 到 [0.8×policy, 1.2×policy]
      (偏差 ≤20% — 经验影响上限, 见 budget.apply_budget_recommendation)。
    """
    usages: list[int] = []
    for r in records:
        if not r.is_success:
            continue
        if task_type and r.task_type != task_type:
            continue
        actual = _nonneg_int(r.budget_trace.get("actual_usage"))
        if actual > 0:
            usages.append(actual)
    if not usages:
        return None
    return round(sum(usages) / len(usages))


def stage_order_from_experience(
    records: Iterable[ContextExperienceRecord],
    default_stages: Iterable[str],
    *,
    required_stages: Iterable[str] = ("overview",),
) -> list[str]:
    """成功经验阶段路径 → 阶段优先级 (历史成功路径优先; 渐进侧接入)。

    规则 (经验影响 ≤20% 硬限制的渐进侧落地, 设计 §4):
    - 只取成功记录 (失败经验不参与排序 — 历史错误不污染未来);
    - 必载阶段 (required_stages) 位置不动 (Stage 1 恒先载);
    - 非必载阶段按成功记录首次出现序多数投票重排;
    - 成功记录 < 2 条或无共识 (票数不足) → 默认序 (冷启动不臆造)。
    """
    defaults = [str(s) for s in default_stages]
    required = [s for s in defaults if s in set(required_stages)]
    non_required = [s for s in defaults if s not in required]
    if not non_required:
        return defaults
    from collections import Counter

    votes: Counter[tuple[str, ...]] = Counter()
    for r in records:
        if not r.is_success:
            continue
        seq = [
            s for s in _norm_list(r.progressive_trace.get("stages"))
            if s in non_required
        ]
        # 去重保序 (同一阶段只计首次出现)
        seen: list[str] = []
        for s in seq:
            if s not in seen:
                seen.append(s)
        if seen:
            votes[tuple(seen)] += 1
    if not votes:
        return defaults
    best_seq, count = votes.most_common(1)[0]
    if count < 2 or list(best_seq) == non_required:
        return defaults
    reordered = required + [s for s in best_seq] + [
        s for s in non_required if s not in best_seq
    ]
    return reordered


# ================================================================ Experience Extractor

class ExperienceExtractor:
    """任务结束自动提取 (ExecutionResult + traces → ContextExperienceRecord)。

    成功提取: 有效 Context (context_used/ranking_trace) + 最佳 Budget
    (budget_trace actual) + 成功路径 (progressive_trace stages 序列);
    失败提取: 结构化 failure_type (五类) + missing_symbols/missing_context +
    recommendation (供下一次任务初始化)。

    输入 (duck-typed, 全可选 — 任何一环缺失不破坏提取):
    - result: ExecutionResult (必填);
    - request: ExecutionRequest (task_id/objective 摘要来源);
    - ranking: RankingPipelineResult (ranking_trace/context_used 来源);
    - progressive: ProgressiveResult (progressive_trace 来源);
    - budget: BudgetResult 或 BudgetTrace (budget_trace 来源);
    - validation: ValidationResult (validation_result 来源);
    - context_score: 质量分 (quality_score 来源);
    - symbols_missed: 本次 symbol miss 清单 (失败学习输入)。

    store: ContextExperienceStore (None → 只构造不落库 — 纯内存模式)。
    """

    def __init__(self, store: ContextExperienceStore | None = None) -> None:
        self._store = store

    @property
    def store(self) -> ContextExperienceStore | None:
        return self._store

    # ------------------------------------------------------------- 失败分类

    def classify_failure(
        self,
        result: Any = None,
        progressive: Any = None,
        budget: Any = None,
        validation: Any = None,
        context_score: float | None = None,
    ) -> str:
        """失败类型分类 (纯规则, 优先级: symbol_miss > overflow > validation
        > context_insufficient > operation; 成功/未知 → 空)。"""
        error = _norm_str(getattr(result, "error", "") if result is not None else "")
        if result is not None and getattr(result, "is_success", False):
            return ""
        # 1) symbol miss (渐进 trace 显式记录 或 错误文本特征)
        trace = getattr(progressive, "trace", None)
        sym_miss = []
        if trace is not None:
            sym_miss = _norm_list(getattr(trace, "symbol_miss", []))
        elif isinstance(progressive, dict):
            sym_miss = _norm_list(progressive.get("symbol_miss"))
        if sym_miss or "symbol" in error.lower():
            return FAILURE_SYMBOL_MISS
        # 2) token/context overflow (预算溢出 或 上下文超限)
        overflow = False
        if trace is not None:
            overflow = bool(getattr(trace, "context_overflow", False))
        elif isinstance(progressive, dict):
            overflow = bool(progressive.get("context_overflow"))
        if budget is not None:
            overflow = overflow or bool(getattr(budget, "context_overflow", False)) \
                or bool(getattr(budget, "overflow", False))
        if overflow or "overflow" in error.lower() or "token" in error.lower():
            return FAILURE_TOKEN_OVERFLOW
        # 3) 验证失败 (validation passed=False)
        if validation is not None and getattr(validation, "passed", True) is False:
            return FAILURE_VALIDATION
        if "validation" in error.lower() or "verifier" in error.lower():
            return FAILURE_VALIDATION
        # 4) 上下文不足 (unable_to_locate / 低质量分)
        unable = False
        if trace is not None:
            unable = bool(getattr(trace, "unable_to_locate", False))
        if unable or (context_score is not None and context_score < 0.5):
            return FAILURE_CONTEXT_INSUFFICIENT
        # 5) 操作失败 (结构化 failure_reason / operation error 文本)
        if "operation" in error.lower() or "patch" in error.lower() \
                or "no parseable patch" in error.lower() or "empty" in error.lower():
            return FAILURE_OPERATION
        return ""

    # ------------------------------------------------------------- 提取

    def extract(
        self,
        *,
        result: Any,
        request: Any = None,
        ranking: Any = None,
        progressive: Any = None,
        budget: Any = None,
        validation: Any = None,
        context_score: float | None = None,
        symbols_missed: Iterable[str] = (),
        employee_id: str = "",
        failure_reason: str = "",
    ) -> ContextExperienceRecord:
        """执行结果 + traces → ContextExperienceRecord (落库当 store 存在)。"""
        success = bool(getattr(result, "is_success", False))
        task_type = _norm_str(getattr(request, "task_id", "") if request is not None else "") \
            or _norm_str(getattr(result, "task_type", "")) or "development"
        objective = _norm_str(getattr(request, "objective", "") if request is not None else "")
        requirement = _norm_str(getattr(request, "requirement", "") if request is not None else "")
        summary = (objective or requirement)[:300]

        context_used: dict[str, Any] = {"candidates": [], "content_refs": []}
        ranking_trace: dict[str, Any] = {}
        progressive_trace: dict[str, Any] = {}
        budget_trace: dict[str, Any] = {}
        if ranking is not None:
            ranking_trace = self._ranking_trace_of(ranking)
            context_used = self._context_used_of(ranking)
        if progressive is not None:
            progressive_trace = self._progressive_trace_of(progressive)
            if not context_used.get("candidates"):
                context_used["content_refs"] = self._content_refs_of(progressive)
        if budget is not None:
            budget_trace = self._budget_trace_of(budget)

        validation_result: dict[str, Any] = {}
        if validation is not None:
            validation_result = {
                "passed": bool(getattr(validation, "passed", False)),
                "attempts": _nonneg_int(getattr(validation, "attempts", 0)),
                "output": _norm_str(getattr(validation, "output", ""))[:500],
            }

        exec_result: dict[str, Any] = {
            "status": "success" if success else "failed",
            "error": _norm_str(getattr(result, "error", ""))[:500],
            "duration": getattr(result, "duration", 0.0),
            "usage": _norm_dict(getattr(result, "usage", {})),
            "employee_id": employee_id or _norm_str(
                getattr(result, "employee_id", "")
            ),
            "request_id": _norm_str(getattr(result, "request_id", "")),
        }

        failure_type = ""
        if not success:
            failure_type = self.classify_failure(
                result, progressive, budget, validation, context_score
            )

        missing_symbols: list[str] = []
        if not success:
            missing_symbols = [str(s) for s in symbols_missed]
            trace = progressive_trace
            for s in _norm_list(trace.get("symbol_miss")):
                if s not in missing_symbols:
                    missing_symbols.append(s)
            if failure_type == FAILURE_SYMBOL_MISS and not missing_symbols:
                # 错误文本兜底: symbol <name> not defined 类特征
                import re

                m = re.search(r"symbol[^a-zA-Z0-9_]*([a-zA-Z_][a-zA-Z0-9_]*)",
                              exec_result["error"])
                if m:
                    missing_symbols.append(m.group(1))

        missing_context: list[str] = []
        if not success:
            if failure_type == FAILURE_CONTEXT_INSUFFICIENT:
                missing_context.append("core files")
            if progressive_trace.get("unable_to_locate"):
                missing_context.append("symbol locations")
            if progressive_trace.get("low_confidence"):
                missing_context.append("confidence")

        quality = _clamp01(context_score) if context_score is not None else (
            1.0 if success else 0.3
        )
        recommendation = self._recommendation(
            failure_type, progressive_trace, budget_trace
        )

        record = ContextExperienceRecord(
            task_type=task_type,
            task_summary=summary,
            context_used=context_used,
            ranking_trace=ranking_trace,
            progressive_trace=progressive_trace,
            budget_trace=budget_trace,
            execution_result=exec_result,
            validation_result=validation_result,
            failure_type=failure_type,
            quality_score=quality,
            recommendation=recommendation,
            missing_symbols=missing_symbols,
            missing_context=missing_context,
        )
        if self._store is not None:
            self._store.save(record)
        return record

    # ------------------------------------------------------------- trace 提取 (duck-typed 归一)

    def _ranking_trace_of(self, ranking: Any) -> dict[str, Any]:
        if isinstance(ranking, dict):
            return _norm_dict(ranking)
        scores: dict[str, float] = {}
        ranked = getattr(ranking, "ranked", None) or []
        for c in ranked[:10]:
            sid = _norm_str(getattr(c, "id", ""))
            if sid:
                scores[sid] = round(float(getattr(c, "relevance_score", 0.0)), 4)
        selection = getattr(ranking, "selection", None)
        selected: list[str] = []
        if selection is not None:
            selected = [str(x) for x in getattr(selection, "selected_ids", []) or []]
        if not selected and getattr(ranking, "budget", None) is not None:
            selected = [str(x) for x in getattr(ranking.budget, "selected_ids", []) or []]
        return {
            "total_candidates": len(ranked),
            "ranked_ids": [str(getattr(c, "id", "")) for c in ranked[:10]],
            "scores": scores,
            "selected_ids": selected,
        }

    def _context_used_of(self, ranking: Any) -> dict[str, Any]:
        """Ranking 产物 → context_used (candidates: {id,type,source,level})。"""
        candidates: list[dict[str, Any]] = []
        content_refs: list[str] = []
        selection = getattr(ranking, "selection", None)
        budget = getattr(ranking, "budget", None)
        levels: dict[str, str] = {}
        if budget is not None:
            levels = _norm_dict(getattr(budget, "levels", {}))
        for c in getattr(ranking, "ranked", None) or []:
            cid = _norm_str(getattr(c, "id", ""))
            if not cid:
                continue
            candidates.append({
                "id": cid,
                "type": _norm_str(getattr(c, "type", "")),
                "source": _norm_str(getattr(c, "source", "")),
                "level": _norm_str(levels.get(cid, "")),
            })
            ref = _norm_str(getattr(c, "content_ref", ""))
            if ref:
                content_refs.append(ref)
        return {"candidates": candidates, "content_refs": content_refs}

    def _progressive_trace_of(self, progressive: Any) -> dict[str, Any]:
        if isinstance(progressive, dict):
            return _norm_dict(progressive)
        trace = getattr(progressive, "trace", None)
        if trace is None:
            return {
                "stages": [str(s) for s in _norm_list(getattr(progressive, "stages", []))],
            }
        if hasattr(trace, "to_dict"):
            return _norm_dict(trace.to_dict())
        return {
            "stages": [str(s) for s in _norm_list(getattr(progressive, "stages", []))],
        }

    def _content_refs_of(self, progressive: Any) -> list[str]:
        refs: list[str] = []
        items = getattr(progressive, "stage_items", {}) or {}
        for lst in items.values():
            for it in lst:
                ref = _norm_str(getattr(it, "content_ref", ""))
                if ref and ref not in refs:
                    refs.append(ref)
        return refs

    def _budget_trace_of(self, budget: Any) -> dict[str, Any]:
        if isinstance(budget, dict):
            return _norm_dict(budget)
        if hasattr(budget, "to_dict"):
            d = _norm_dict(budget.to_dict())
            # BudgetResult 与 BudgetTrace 字段名兼容归一
            if "budget_chars" in d and "planned_budget" not in d:
                d["planned_budget"] = d["budget_chars"]
            if "total_chars" in d and "actual_usage" not in d:
                d["actual_usage"] = d["total_chars"]
            return d
        return {
            "planned_budget": _nonneg_int(getattr(budget, "budget_chars", 0)),
            "actual_usage": _nonneg_int(getattr(budget, "total_chars", 0)),
            "overflow": bool(getattr(budget, "context_overflow", False)),
            "degraded_steps": [str(x) for x in _norm_list(getattr(budget, "degraded_steps", []))],
        }

    # ------------------------------------------------------------- 建议

    def _recommendation(
        self,
        failure_type: str,
        progressive_trace: dict[str, Any],
        budget_trace: dict[str, Any],
    ) -> str:
        """失败模式 → 建议 (下一次任务初始化; 与 context.experience_advice
        映射同语义 — 单一事实源保持一致)。"""
        if not failure_type:
            return "保持最小改动, 优先结构化操作"
        if failure_type == FAILURE_SYMBOL_MISS:
            names = ", ".join(str(s) for s in _norm_list(progressive_trace.get("symbol_miss"))[:3])
            hint = f" ({names})" if names else ""
            return (
                f"历史 symbol 定位失败{hint} — 该候选已提权, 定位请用精确行号 "
                "(line_range), 勿用 symbol 锚点"
            )
        if failure_type == FAILURE_TOKEN_OVERFLOW:
            return "上下文超出预算 — 已降级符号索引/摘要级, 精确定位用 line_range, 保持最小改动"
        if failure_type == FAILURE_VALIDATION:
            return "历史验收未达较多 — 修改后逐条对照 Requirement/Acceptance criteria 核验"
        if failure_type == FAILURE_CONTEXT_INSUFFICIENT:
            return "上下文信息不足 — 建议扩大核心文件集 (同模块/影响面) 或补 symbol 索引"
        if failure_type == FAILURE_OPERATION:
            return "历史操作/补丁失败较多 — 用 <operations> 结构化操作 (系统确定性生成 diff)"
        return ""
