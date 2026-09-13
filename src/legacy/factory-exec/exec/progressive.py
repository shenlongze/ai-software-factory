"""factory-exec/exec/progressive.py — Progressive Loading Engine (Sprint 4 T4.2)。

设计依据 (docs/validation/sprint4-t42-progressive-loading-design.md, 已批准):
```text
Task → RankingEngine (T4.1: 候选评分 Top-K) → TopKSelector → BudgetController
  → 【T4.2】ProgressiveLoader ← 本模块
  → ContextLoader (内容加载, 延迟) → Developer Agent
```

本模块 = 通用渐进加载引擎 (Agent 无关, 零 LLM, 零 Core 依赖):
- StageSpec: 阶段定义声明式 (类型/预算/内容提取器) — 未来 Product/Finance/
  Medical Agent 配不同 StageSpec, 引擎不变 (设计 §7);
- ProgressiveLoader: 阶段通用循环 (每阶段后决策 continue|stop|fallback|skip);
- StageDecisionPolicy: 纯规则决策 (设计 §3: confidence <0.6 → 下一阶段; task
  type 深度; validation 反馈回退; missing info 扩 1 轮; 扩展计数 ≤3; 每阶段
  至多 1 次回退);
- 预算分级 (设计 §4): Stage 1 固定 1-2K / Stage 2 3-5K / Stage 3 剩余 (总 ≤30K
  chars); 超限 → 截断至锚点核心 → 降级重试 1 次 → context_overflow 标记;
- ProgressiveTrace (设计 §5): 每阶段审计 (stage/loaded_items/reason/token_cost/
  decision/final_usage) + 失败信号 (to_experience_signals → Experience Learning);
- 失败兜底 (设计 §6): Stage 1 无法定位 → 扩 1 轮 → unable_to_locate; symbol
  miss → line_range 兜底提示; 超大文件 → 符号索引+锚点段; token 超限 → 降级+
  重试 1 次; 全失败 → low_confidence 执行 (不静默)。

KISS 边界: 内容语义完全由注入的 extractor/finalizer 提供 (引擎不解释内容 —
域耦合在装配方); 字符口径同 ranking.py (4 chars/token); 本模块可独立
import — 无环 (ranking.py 单向依赖本模块, 反向不成立)。
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, Field, field_validator

# ================================================================ 常量

#: 置信度阈值 (设计 §3 ①: <0.6 → 需要更多信息 → 下一阶段)
CONFIDENCE_THRESHOLD = 0.6
#: 扩展计数上限 (设计 §3 ④: 扩 1 轮; 计数 ≤3; 超限 → low_confidence 执行)
MAX_EXTENSION_ROUNDS = 3
#: 每阶段至多回退次数 (设计 §3: 每阶段至多 1 次回退)
MAX_FALLBACK_PER_STAGE = 1
#: 总硬顶 (设计 §4: 总 ≤30K chars ≈7.5K tokens)
PROGRESSIVE_HARD_CAP_CHARS = 30_000
#: Stage 1 预算 (设计 §4: 1-2K chars 固定必载)
STAGE_1_BUDGET_CHARS = 2_000
#: Stage 2 预算 (设计 §4: 3-5K chars 符号索引级)
STAGE_2_BUDGET_CHARS = 5_000
#: 截断标记 (锚点核心裁尾)
_TRUNC_MARK = "\n// [截断]"

#: 决策取值 (设计 §1/§5: continue|stop|fallback; skip 为 greenfield 跳过中间阶段)
DECISION_CONTINUE = "continue"
DECISION_STOP = "stop"
DECISION_FALLBACK = "fallback"
DECISION_SKIP = "skip"

#: 默认跳过中间阶段的映射 (task_type → 目标阶段名; 设计 §3 ②: Greenfield 只需
#: Stage 1+3 规范+骨架); 其他 Agent 可注入自己的映射 (通用化)
DEFAULT_SKIP_STAGE_MAP: dict[str, str] = {"greenfield": "detail"}
#: 默认全深度任务类型 (设计 §3 ②: Bug Fix 需 Stage 3 代码; feature 默认档需完整
#: 执行上下文 — 预算最大档); 其他 Agent 可注入自己的集合
DEFAULT_FULL_DEPTH_TASK_TYPES: frozenset[str] = frozenset({"bug_fix", "feature"})


def _clamp01(x: Any) -> float:
    """0-1 截断 (置信度/评分统一边界)。"""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, v))


# ================================================================ StageSpec (声明式阶段配置)

class StageSpec(BaseModel):
    """阶段定义 (声明式配置 — Agent 通用, 不绑定 Developer; 设计 §2/§7)。

    - stage: 阶段标识 (overview/symbol/detail 语义化; 未来 Product/Finance/
      Medical Agent 可配不同阶段名与提取器, 引擎不变);
    - label: 显示名;
    - max_chars: 本阶段预算上限 (字符; 0 = 用剩余预算 — 末阶段语义);
    - extractor: 内容提取器名 (语义化键; 装配方注册对应实现);
    - required: 必载阶段 (总是进入 — Stage 1 语义)。

    校验: max_chars ≥ 0; 字符串 None → ""; extra=forbid (拼写错误即失败)。
    """

    model_config = {"extra": "forbid"}

    stage: str
    label: str = ""
    max_chars: int = 0
    extractor: str = ""
    required: bool = False

    @field_validator("stage", "label", "extractor", mode="before")
    @classmethod
    def _strs_none(cls, v: Any) -> str:
        return str(v) if v is not None else ""

    @field_validator("max_chars", mode="before")
    @classmethod
    def _budget_nonneg(cls, v: Any) -> int:
        v = int(v) if v is not None else 0
        return max(0, v)

    @field_validator("required", mode="before")
    @classmethod
    def _bool_none(cls, v: Any) -> bool:
        return bool(v) if v is not None else False


# ================================================================ 加载运行时模型

class LoadedItem:
    """已加载内容项 (content_ref → 实际内容; 延迟加载产物)。

    - content_ref: 内容引用 (审计锚点 — 与 ContextCandidate.content_ref 同语义);
    - content: 实际加载文本 (只在加载阶段填充 — 不预载);
    - chars: 字符成本 (缺省 = len(content); 截断后按实际重算);
    - keep: 必载锚点 (不参与截断 — 如任务需求; 设计 §4 「截断至锚点核心」);
    - payload: 域特定载荷 (finalize 用; 引擎不解释)。
    """

    __slots__ = ("content_ref", "content", "chars", "keep", "payload")

    def __init__(
        self,
        content_ref: str,
        content: str = "",
        chars: int | None = None,
        keep: bool = False,
        payload: Any = None,
    ) -> None:
        self.content_ref = str(content_ref)
        self.content = str(content)
        self.chars = len(self.content) if chars is None else max(0, int(chars))
        self.keep = bool(keep)
        self.payload = payload

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_ref": self.content_ref,
            "chars": self.chars,
            "keep": self.keep,
        }


class StageLoadResult:
    """单阶段加载产物 (提取器 → 加载器): 内容 + 决策元数据。

    - items: 本阶段加载项;
    - confidence: 本阶段置信度 0-1 (决策规则 ① 输入);
    - candidates_found: 候选文件已定位 (Stage 1 进入条件; 设计 §2);
    - anchor_found: symbol/锚点已确定或 line_range 兜底可用 (Stage 2 进入条件);
    - missing_info: 缺信息 (symbol miss / 文件未定位 → 扩 1 轮);
    - symbol_miss / large_file: 失败模式 (审计 + 经验信号);
    - warnings: 本阶段警示 (进 trace)。
    """

    def __init__(
        self,
        *,
        items: list[LoadedItem] | None = None,
        confidence: float = 0.0,
        candidates_found: bool = True,
        anchor_found: bool = True,
        missing_info: bool = False,
        symbol_miss: list[str] | None = None,
        large_file: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        self.items = list(items or [])
        self.confidence = _clamp01(confidence)
        self.candidates_found = bool(candidates_found)
        self.anchor_found = bool(anchor_found)
        self.missing_info = bool(missing_info)
        self.symbol_miss = list(symbol_miss or [])
        self.large_file = list(large_file or [])
        self.warnings = list(warnings or [])


class StageState:
    """阶段运行时状态 (扩展/重试/回退计数 — 决策规则输入; 每阶段持久)。"""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        self.widen_count = 0      # 扩展轮次 (missing info 扩 1 轮)
        self.retry_count = 0      # 降级重试 (token 超限重试 1 次)
        self.fallback_count = 0   # 本阶段回退次数


class StageDecisionInput:
    """决策规则输入 (纯函数 decide_next_stage 的显式入参)。"""

    def __init__(
        self,
        *,
        stage_index: int,
        num_stages: int,
        stage_names: tuple[str, ...] | list[str],
        stage: str,
        task_type: str,
        confidence: float,
        candidates_found: bool = True,
        anchor_found: bool = True,
        missing_info: bool = False,
        extension_count: int = 0,
        fallback_count: int = 0,
        budget_exhausted: bool = False,
        validation_failed: bool = False,
    ) -> None:
        self.stage_index = max(0, int(stage_index))
        self.num_stages = max(1, int(num_stages))
        self.stage_names = tuple(str(s) for s in stage_names)
        self.stage = str(stage)
        self.task_type = str(task_type)
        self.confidence = _clamp01(confidence)
        self.candidates_found = bool(candidates_found)
        self.anchor_found = bool(anchor_found)
        self.missing_info = bool(missing_info)
        self.extension_count = max(0, int(extension_count))
        self.fallback_count = max(0, int(fallback_count))
        self.budget_exhausted = bool(budget_exhausted)
        self.validation_failed = bool(validation_failed)


class StageDecision(BaseModel):
    """决策结果 (设计 §5: continue|stop|fallback + reason; skip 为扩展)。"""

    model_config = {"extra": "forbid"}

    decision: str = DECISION_STOP
    reason: str = ""
    next_stage: str = ""    # skip 目标阶段名
    target_stage: str = ""  # fallback 目标阶段名
    extend: bool = False    # continue 且同阶段扩展 (扩 1 轮)

    @field_validator("decision", "reason", "next_stage", "target_stage", mode="before")
    @classmethod
    def _strs_none(cls, v: Any) -> str:
        return str(v) if v is not None else ""

    @field_validator("extend", mode="before")
    @classmethod
    def _bool_none(cls, v: Any) -> bool:
        return bool(v) if v is not None else False


# ================================================================ Stage 决策 (纯规则)

def decide_next_stage(
    inp: StageDecisionInput,
    *,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
    max_extension_rounds: int = MAX_EXTENSION_ROUNDS,
    max_fallback_per_stage: int = MAX_FALLBACK_PER_STAGE,
    full_depth_task_types: frozenset[str] = DEFAULT_FULL_DEPTH_TASK_TYPES,
    skip_stage_map: dict[str, str] | None = None,
) -> StageDecision:
    """阶段决策纯规则 (设计 §2/§3; 零 LLM, 确定性, 首个命中生效)。

    规则序 (首个命中生效):
      R1 validation 反馈 → fallback(上一阶段)         — 重新定位 (Stage 3 → 2)
      R2 末阶段 → stop(final_stage)                  — 无后续可加载
      R3 预算耗尽 → stop(budget_exhausted)            — 不再深入
      R4 本阶段回退超限 → stop(fallback_limit)        — 调用方标记 low_confidence
      R5 首阶段候选未定位 → stop(unable_to_locate)    — 加载器自动扩 1 轮后仍空
      R6 missing info → continue(扩 1 轮)             — symbol miss/文件未定位; 计数 ≤3
      R7 锚点阶段锚点未定 → stop(anchor_unresolved)   — line_range 兜底后仍有锚点
      R8 task_type 跳阶段 → skip(目标阶段)            — Greenfield 只需 Stage 1+3
      R9 全深度任务类型 → continue(下一阶段)          — 代码任务需完整执行上下文
      R10 低置信 → continue(下一阶段)                 — 需要更多信息
      R11 默认 → stop(sufficient_confidence)          — 信息足够, 不再加载

    规则按阶段索引 (stage_index) 而非阶段名 — 引擎对任意 Agent 阶段配置通用
    (首阶段 = 定位/概览, 第二阶段 = 锚点/符号; 语义由装配方保证)。
    """
    if inp.validation_failed:
        target = inp.stage_names[max(0, inp.stage_index - 1)] if inp.stage_names else ""
        return StageDecision(
            decision=DECISION_FALLBACK, reason="validation_feedback", target_stage=target
        )
    if inp.stage_index >= inp.num_stages - 1:
        return StageDecision(decision=DECISION_STOP, reason="final_stage")
    if inp.budget_exhausted:
        return StageDecision(decision=DECISION_STOP, reason="budget_exhausted")
    if inp.fallback_count >= max_fallback_per_stage:
        return StageDecision(decision=DECISION_STOP, reason="fallback_limit")
    if inp.stage_index == 0 and not inp.candidates_found:
        return StageDecision(decision=DECISION_STOP, reason="unable_to_locate")
    if inp.missing_info:
        if inp.extension_count >= max_extension_rounds:
            return StageDecision(decision=DECISION_STOP, reason="extension_limit")
        return StageDecision(
            decision=DECISION_CONTINUE, reason="missing_info_widen", extend=True
        )
    if inp.stage_index == 1 and not inp.anchor_found:
        return StageDecision(decision=DECISION_STOP, reason="anchor_unresolved")
    skip_map = dict(skip_stage_map) if skip_stage_map is not None else dict(DEFAULT_SKIP_STAGE_MAP)
    if inp.stage_index == 0 and inp.task_type in skip_map:
        return StageDecision(
            decision=DECISION_SKIP, reason=f"{inp.task_type}_skip_stage",
            next_stage=skip_map[inp.task_type],
        )
    if inp.task_type in full_depth_task_types and inp.stage_index < inp.num_stages - 1:
        return StageDecision(decision=DECISION_CONTINUE, reason=f"{inp.task_type}_needs_code")
    if inp.confidence < confidence_threshold:
        return StageDecision(decision=DECISION_CONTINUE, reason="low_confidence")
    return StageDecision(decision=DECISION_STOP, reason="sufficient_confidence")


class StageDecisionPolicy:
    """纯规则决策策略 (可注入阈值/任务类型语义; 默认值 = 设计 §3)。

    构造参数均可覆盖 (通用化: Finance Agent 可配 full_depth_task_types 为
    自己的类型集 / skip_stage_map 为空 — 引擎不变)。
    """

    def __init__(
        self,
        *,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
        max_extension_rounds: int = MAX_EXTENSION_ROUNDS,
        max_fallback_per_stage: int = MAX_FALLBACK_PER_STAGE,
        full_depth_task_types: frozenset[str] = DEFAULT_FULL_DEPTH_TASK_TYPES,
        skip_stage_map: dict[str, str] | None = None,
    ) -> None:
        self._confidence_threshold = float(confidence_threshold)
        self._max_extension_rounds = max(0, int(max_extension_rounds))
        self._max_fallback_per_stage = max(0, int(max_fallback_per_stage))
        self._full_depth_task_types = frozenset(full_depth_task_types)
        self._skip_stage_map = dict(skip_stage_map) if skip_stage_map is not None else None

    def decide(self, inp: StageDecisionInput) -> StageDecision:
        """决策输入 → 决策 (委托纯函数; 引擎循环唯一调用点)。"""
        return decide_next_stage(
            inp,
            confidence_threshold=self._confidence_threshold,
            max_extension_rounds=self._max_extension_rounds,
            max_fallback_per_stage=self._max_fallback_per_stage,
            full_depth_task_types=self._full_depth_task_types,
            skip_stage_map=self._skip_stage_map,
        )


# ================================================================ 预算分级

def stage_budget(
    spec: StageSpec, used: int, hard_cap: int = PROGRESSIVE_HARD_CAP_CHARS
) -> int:
    """阶段预算 (设计 §4): 固定档 min(上限, 剩余); max_chars=0 → 剩余预算。

    used = 除本阶段外已用字符 (每阶段预算独立于自身历史轮次 — 扩轮不重复计费)。
    """
    used = max(0, int(used))
    hard_cap = max(1, int(hard_cap))
    remaining = max(0, hard_cap - used)
    if spec.max_chars and spec.max_chars > 0:
        return min(spec.max_chars, remaining)
    return remaining


def apply_stage_budget(items: list[LoadedItem], budget: int) -> tuple[list[LoadedItem], bool]:
    """阶段预算应用 (设计 §4): 超限 → 截断至锚点核心 → 仍超 → overflow 标记。

    - keep 项 (必载锚点) 不截断;
    - 其余项按剩余预算均分, 保 head 裁尾 (函数签名/关键行在前 = 锚点核心);
    - 截断后仍超 → 按序丢尾项 (提取器序 = 重要度序) → 仍超 → overflow=True
      (保留最大可用, 诚实标记 — 不静默丢弃全部)。

    返回 (最终项, overflow)。overflow=True 表示降级后仍超预算 — 调用方据此
    走降级重试 1 次 (设计 §6) 并标记 context_overflow。
    """
    budget = max(0, int(budget))
    if budget <= 0:
        return [], True
    items = list(items)
    total = sum(it.chars for it in items)
    if total <= budget:
        return items, False

    keeps = [it for it in items if it.keep]
    keeps_total = sum(it.chars for it in keeps)
    if keeps_total > budget:
        return keeps, True  # 锚点本身超预算 → 保留锚点 + overflow (诚实)

    cuttable = [it for it in items if not it.keep]
    share = max(1, (budget - keeps_total) // max(1, len(cuttable)))
    overflow = False
    final: list[LoadedItem] = []
    for it in items:  # 保原序 (重要度序)
        if it.keep or it.chars <= share:
            final.append(it)
            continue
        head_len = max(0, share - len(_TRUNC_MARK))
        if head_len <= 0:
            overflow = True  # 锚点核心都无法容纳 → 诚实 overflow (不静默)
            head = ""
        else:
            head = it.content[:head_len]
        final.append(
            LoadedItem(
                content_ref=it.content_ref,
                content=head + _TRUNC_MARK,
                chars=len(head) + len(_TRUNC_MARK),
                keep=False,
                payload=it.payload,
            )
        )
    if not overflow:
        while sum(it.chars for it in final) > budget and len(final) > len(keeps):
            final.pop()  # 丢最低优先级尾项 (降级链: 丢弃最低分相关)
            overflow = True
    if sum(it.chars for it in final) > budget:
        overflow = True  # 仍超 → 保留最大可用 + 诚实标记
    return final, overflow


def render_items(items: list[LoadedItem]) -> str:
    """阶段内容渲染 (items → 文本; 引擎不解释内容, 纯拼接)。"""
    return "\n\n".join(it.content for it in items if it.content)


# ================================================================ ProgressiveTrace (审计)

class ProgressiveTraceEntry(BaseModel):
    """单阶段审计条目 (设计 §5): 加载了什么/为什么/花多少/决策。

    - reason: 进入该阶段的依据 (initial / low_confidence / bug_fix_needs_code /
      missing_info_widen / validation_feedback ...);
    - decision_reason: 本阶段决策的依据 (stop 原因: unable_to_locate /
      extension_limit / budget_exhausted ...; 审计「为什么停止」);
    - decision: continue|stop|fallback|skip (设计 §5);
    - final_usage: {before, after} 总消耗 (字符; 4 chars/token 口径同 ranking.py)。
    """

    model_config = {"extra": "forbid"}

    stage: str = ""
    loaded_items: list[str] = Field(default_factory=list)
    reason: str = ""
    token_cost: int = 0
    decision: str = DECISION_STOP
    decision_reason: str = ""
    final_usage: dict[str, int] = Field(default_factory=dict)

    @field_validator("stage", "reason", "decision", "decision_reason", mode="before")
    @classmethod
    def _strs_none(cls, v: Any) -> str:
        return str(v) if v is not None else ""

    @field_validator("loaded_items", mode="before")
    @classmethod
    def _items_none(cls, v: Any) -> list[str]:
        return [str(x) for x in v] if v is not None else []

    @field_validator("token_cost", mode="before")
    @classmethod
    def _cost_nonneg(cls, v: Any) -> int:
        return max(0, int(v)) if v is not None else 0

    @field_validator("final_usage", mode="before")
    @classmethod
    def _usage_map(cls, v: Any) -> dict[str, int]:
        if v is None:
            return {}
        return {str(k): max(0, int(x)) for k, x in v.items()}


class ProgressiveTrace(BaseModel):
    """审计 Trace (设计 §5): 阶段条目 + 汇总 + 失败信号。

    用途 (设计 §5):
    - Experience Learning: 成功任务的阶段路径保存 (to_dict 全量可审计);
    - 失败任务: to_experience_signals() 产出失败模式 (哪阶段缺信息 → 经验权重调整);
    - 审计: 加载了什么 / 为什么 / 花多少 — 全程可追溯。
    """

    model_config = {"extra": "forbid"}

    entries: list[ProgressiveTraceEntry] = Field(default_factory=list)
    total_chars: int = 0
    token_estimate: int = 0
    context_overflow: bool = False
    low_confidence: bool = False
    unable_to_locate: bool = False
    symbol_miss: list[str] = Field(default_factory=list)
    large_file: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # T4.3 Budget Enforcement 记录 (BudgetTrace 同口径; 旧字段全兼容):
    requested_budget: int = 0     # 申请预算 (chars; 各进入阶段预算分配和)
    actual_usage: int = 0         # 实际消耗 (chars; 同 total_chars, 双口径)
    degraded_steps: list[str] = Field(default_factory=list)  # 降级链执行记录

    @field_validator("entries", mode="before")
    @classmethod
    def _entries_none(cls, v: Any) -> list[Any]:
        return list(v) if v is not None else []

    @field_validator("symbol_miss", "large_file", "warnings", "degraded_steps", mode="before")
    @classmethod
    def _lists_none(cls, v: Any) -> list[str]:
        return [str(x) for x in v] if v is not None else []

    @field_validator("total_chars", "token_estimate", "requested_budget", "actual_usage", mode="before")
    @classmethod
    def _ints_nonneg(cls, v: Any) -> int:
        return max(0, int(v)) if v is not None else 0

    @field_validator("context_overflow", "low_confidence", "unable_to_locate", mode="before")
    @classmethod
    def _bools_none(cls, v: Any) -> bool:
        return bool(v) if v is not None else False

    def add_load_meta(self, load: StageLoadResult) -> None:
        """累积失败模式元数据 (symbol_miss / large_file / warnings — 去重)。"""
        for s in load.symbol_miss:
            if s not in self.symbol_miss:
                self.symbol_miss.append(s)
        for f in load.large_file:
            if f not in self.large_file:
                self.large_file.append(f)
        for w in load.warnings:
            if w not in self.warnings:
                self.warnings.append(w)

    def to_experience_signals(self) -> list[str]:
        """失败模式信号 (供 Experience Learning; 成功路径 → 空列表)。"""
        signals: list[str] = []
        if self.unable_to_locate:
            signals.append("unable_to_locate")
        for s in self.symbol_miss:
            signals.append(f"symbol_miss:{s}")
        for f in self.large_file:
            signals.append(f"large_file:{f}")
        if self.context_overflow:
            signals.append("context_overflow")
        if self.low_confidence:
            signals.append("low_confidence")
        return signals

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries": [e.model_dump(mode="json") for e in self.entries],
            "total_chars": self.total_chars,
            "token_estimate": self.token_estimate,
            "context_overflow": self.context_overflow,
            "low_confidence": self.low_confidence,
            "unable_to_locate": self.unable_to_locate,
            "symbol_miss": list(self.symbol_miss),
            "large_file": list(self.large_file),
            "warnings": list(self.warnings),
            "requested_budget": self.requested_budget,
            "actual_usage": self.actual_usage,
            "degraded_steps": list(self.degraded_steps),
            "signals": self.to_experience_signals(),
        }


# ================================================================ ProgressiveResult

class ProgressiveResult:
    """渐进加载全产物 (审计 + 组装输入)。"""

    def __init__(self) -> None:
        self.stages: list[str] = []                        # 实际进入阶段 (去重保序)
        self.stage_items: dict[str, list[LoadedItem]] = {}  # 阶段 → 最终加载项
        self.stage_content: dict[str, str] = {}            # 阶段 → 渲染文本
        self.trace = ProgressiveTrace()
        self.assembled: Any = None                         # finalizer 产物 (域特定)
        self.total_chars: int = 0
        self.token_estimate: int = 0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "stages": list(self.stages),
            "total_chars": self.total_chars,
            "token_estimate": self.token_estimate,
            "trace": self.trace.to_dict(),
        }
        if self.assembled is not None and hasattr(self.assembled, "to_dict"):
            d["assembled"] = self.assembled.to_dict()
        return d


# ================================================================ ProgressiveLoader (通用引擎)

class ProgressiveLoader:
    """通用渐进加载引擎 (设计 §1/§2; Agent 无关, 零 LLM)。

    输入 (全部注入 — 引擎不解释内容语义):
    - stages: 声明式阶段配置 (StageSpec 列表; 末阶段 max_chars=0 → 剩余预算);
    - extractor: Callable[[StageSpec, *, widen, degrade], StageLoadResult] —
      内容提取器 (content_ref → 实际内容, 延迟加载; 域耦合在装配方);
    - policy: 决策策略 (缺省 StageDecisionPolicy — 设计 §3 默认规则);
    - finalizer: Callable[[ProgressiveResult], Any] — 最终组装 (可选; 域特定);
    - hard_cap: 总预算硬顶 (默认 30K chars — 设计 §4)。

    引擎职责: 阶段循环 / 预算分级 (截断→降级重试→overflow) / 决策应用
    (continue|stop|fallback|skip) / 审计 Trace / 失败兜底 (扩 1 轮 /
    unable_to_locate / low_confidence 不静默)。
    """

    def __init__(
        self,
        *,
        stages: list[StageSpec],
        extractor: Callable[..., StageLoadResult],
        policy: StageDecisionPolicy | None = None,
        finalizer: Callable[[ProgressiveResult], Any] | None = None,
        hard_cap: int = PROGRESSIVE_HARD_CAP_CHARS,
    ) -> None:
        self._stages = list(stages)
        self._extractor = extractor
        self._policy = policy if policy is not None else StageDecisionPolicy()
        self._finalizer = finalizer
        self._hard_cap = max(1, int(hard_cap))

    # ------------------------------------------------------------------ 内部

    @staticmethod
    def _used(stage_items: dict[str, list[LoadedItem]], exclude: str | None = None) -> int:
        """已用字符 (除指定阶段外 — 每阶段预算独立于自身历史轮次)。"""
        total = 0
        for stage, items in stage_items.items():
            if stage == exclude:
                continue
            total += sum(it.chars for it in items)
        return total

    def _index_of(self, stage_names: list[str], name: str) -> int:
        """阶段名 → 索引 (未知名 → 末阶段 — 失败安全)。"""
        if name in stage_names:
            return stage_names.index(name)
        return len(stage_names) - 1

    # ------------------------------------------------------------------ 主循环

    def run(
        self,
        *,
        task_type: str = "feature",
        validation_failed: bool = False,
    ) -> ProgressiveResult:
        """渐进加载主循环 (设计 §2: Stage 1 → 2 → 3, 每阶段后决策)。

        task_type: 任务类型 (决策规则 ② 输入; 装配方从 TaskProfile 传入);
        validation_failed: 执行验证失败反馈 (设计 §3 ③: 回上一阶段重新定位,
        仅末阶段之后生效一次 — 对应 Stage 3 验证失败 → Stage 2)。
        """
        result = ProgressiveResult()
        trace = result.trace
        stage_names = [s.stage for s in self._stages]
        stage_items: dict[str, list[LoadedItem]] = {}
        allocated: dict[str, int] = {}  # T4.3: 每进入阶段预算分配 (申请记录)
        states: dict[str, StageState] = {}
        global_ext = 0
        enter_reason = "initial"
        i = 0
        last_i = 0
        max_rounds = max(1, len(stage_names) * 8)  # 防御: 硬轮次上限 (决策规则本身有界)
        rounds = 0

        while 0 <= i < len(stage_names) and rounds < max_rounds:
            rounds += 1
            spec = self._stages[i]
            state = states.get(spec.stage)
            if state is None:
                state = StageState(spec.stage)
                states[spec.stage] = state

            # --- 1) 提取 (widen/degrade 由状态决定; 延迟加载契约) ---
            load = self._extractor(spec, widen=state.widen_count > 0, degrade=state.retry_count > 0)

            # --- 2) 预算 (设计 §4: 阶段档位 + 剩余; 超限 → 截断锚点核心) ---
            sbudget = stage_budget(spec, self._used(stage_items, exclude=spec.stage), self._hard_cap)
            if spec.stage not in allocated:
                allocated[spec.stage] = sbudget  # T4.3: 申请预算 (每阶段首次分配)
            items, overflow = apply_stage_budget(load.items, sbudget)
            if overflow and state.retry_count == 0:
                # token 超限 → 降级 + 重试 1 次 (设计 §6; extractor degrade=True
                # 返回符号索引/摘要级轻量内容 — 复用 BudgetController 降级链语义)
                state.retry_count += 1
                load = self._extractor(spec, widen=state.widen_count > 0, degrade=True)
                items, overflow = apply_stage_budget(load.items, sbudget)
                trace.warnings.append(f"stage {spec.stage}: token 超限降级重试 1 次")
                trace.degraded_steps.append(f"{spec.stage}:token_degrade_retry")
                if overflow:
                    trace.context_overflow = True  # 降级后仍超 → 执行前警示 (设计 §4)
                    trace.degraded_steps.append("context_overflow")
            stage_items[spec.stage] = items
            trace.add_load_meta(load)

            # --- 3) 决策 ---
            used_other = self._used(stage_items, exclude=spec.stage)
            stage_chars = sum(it.chars for it in items)
            used_after = used_other + stage_chars
            inp = StageDecisionInput(
                stage_index=i,
                num_stages=len(stage_names),
                stage_names=stage_names,
                stage=spec.stage,
                task_type=task_type,
                confidence=load.confidence,
                candidates_found=load.candidates_found,
                anchor_found=load.anchor_found,
                missing_info=load.missing_info,
                extension_count=state.widen_count,
                fallback_count=state.fallback_count,
                budget_exhausted=used_after >= self._hard_cap,
            )
            decision = self._policy.decide(inp)

            # --- 4) Stage 1 无法定位: 自动扩关键词 1 轮 (设计 §6) ---
            auto_widen = (
                decision.decision == DECISION_STOP
                and decision.reason == "unable_to_locate"
                and state.widen_count == 0
                and global_ext < MAX_EXTENSION_ROUNDS
            )
            if auto_widen:
                state.widen_count += 1
                global_ext += 1
                decision = StageDecision(
                    decision=DECISION_CONTINUE, reason="unable_to_locate_widen", extend=True
                )

            # --- 5) 同阶段扩展 (missing info 扩 1 轮; 扩展计数 ≤3) ---
            if decision.decision == DECISION_CONTINUE and decision.extend and not auto_widen:
                if state.widen_count >= MAX_EXTENSION_ROUNDS or global_ext >= MAX_EXTENSION_ROUNDS:
                    decision = StageDecision(decision=DECISION_STOP, reason="extension_limit")
                else:
                    state.widen_count += 1
                    global_ext += 1

            # --- 6) 审计条目 (本阶段加载: 加载了什么/为什么/花多少/决策) ---
            entry = ProgressiveTraceEntry(
                stage=spec.stage,
                loaded_items=[it.content_ref for it in items],
                reason=enter_reason,
                token_cost=stage_chars,
                decision=decision.decision,
                decision_reason=decision.reason,
                final_usage={"before": used_other, "after": used_after},
            )
            trace.entries.append(entry)
            if spec.stage not in result.stages:
                result.stages.append(spec.stage)

            # --- 7) 应用决策 ---
            if decision.decision == DECISION_CONTINUE and decision.extend:
                enter_reason = decision.reason
                continue  # 同阶段再提取 (widen=True)
            if decision.decision == DECISION_CONTINUE:
                enter_reason = decision.reason
                i += 1
                continue
            if decision.decision == DECISION_SKIP:
                enter_reason = decision.reason
                target = self._index_of(stage_names, decision.next_stage)
                if target == i:
                    i += 1  # 防御: 跳过自身 → 下一阶段
                else:
                    i = target
                continue
            if decision.decision == DECISION_FALLBACK:
                enter_reason = decision.reason
                target = self._index_of(stage_names, decision.target_stage)
                if target != i:
                    i = target
                    states[stage_names[target]].fallback_count += 1
                else:
                    i += 1  # 防御: 回退自身 → 下一阶段
                continue
            last_i = i
            break  # stop

        # --- validation 反馈回退 (设计 §3 ③: 执行验证失败 → 回上一阶段重新定位) ---
        if validation_failed and last_i >= 1:
            target_i = max(0, last_i - 1)
            spec = self._stages[target_i]
            load = self._extractor(spec, widen=True, degrade=False)
            combined = list(stage_items.get(spec.stage, [])) + list(load.items)
            combined, _ = apply_stage_budget(
                combined, stage_budget(spec, self._used(stage_items, exclude=spec.stage), self._hard_cap)
            )
            stage_items[spec.stage] = combined
            used_other = self._used(stage_items, exclude=spec.stage)
            stage_chars = sum(it.chars for it in load.items)
            trace.entries.append(
                ProgressiveTraceEntry(
                    stage=spec.stage,
                    loaded_items=[it.content_ref for it in load.items],
                    reason="validation_feedback",
                    token_cost=stage_chars,
                    decision=DECISION_FALLBACK,
                    final_usage={"before": used_other, "after": used_other + stage_chars},
                )
            )
            trace.add_load_meta(load)
            if load.missing_info:
                trace.warnings.append("验证回退后仍缺信息 — low_confidence 执行")
                trace.low_confidence = True
        if rounds >= max_rounds:
            trace.warnings.append(f"渐进加载达到轮次上限 ({max_rounds}) — 强制停止")
            trace.low_confidence = True

        # --- 汇总与失败标记 (不静默: 全失败 → low_confidence 执行) ---
        result.stage_items = stage_items
        result.stage_content = {s: render_items(items) for s, items in stage_items.items()}
        result.total_chars = sum(sum(it.chars for it in items) for items in stage_items.values())
        result.token_estimate = result.total_chars // 4
        trace.total_chars = result.total_chars
        trace.token_estimate = result.token_estimate
        # T4.3 Budget Enforcement 记录: 申请预算 = 各进入阶段预算分配和 (上限 = 总硬顶 —
        # 末阶段「剩余」按前序实际消耗计算可能使分配和虚高, 截断到总预算保持可审计);
        # 实际 = 渲染消耗。
        trace.requested_budget = min(sum(allocated.values()), self._hard_cap)
        trace.actual_usage = result.total_chars

        reasons = {e.reason for e in trace.entries}
        decision_reasons = {e.decision_reason for e in trace.entries}
        trace.unable_to_locate = "unable_to_locate" in decision_reasons
        if (
            trace.unable_to_locate
            or "extension_limit" in decision_reasons
            or "fallback_limit" in decision_reasons
            or trace.context_overflow
        ):
            trace.low_confidence = True

        result.assembled = self._finalizer(result) if self._finalizer is not None else None
        return result
