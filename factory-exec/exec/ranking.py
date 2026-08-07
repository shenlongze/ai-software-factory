"""factory-exec/exec/ranking.py — Context Ranking Engine (Sprint 4 T4.1)。

设计依据 (docs/validation/sprint4-t41-ranking-design.md, 已批准):
```text
Task Input (自然语言)
  → ① Task Analyzer     结构化任务 (目标/类型/关键词/符号候选/验收)
  → ② Candidate Generator 从数据源生成候选 (symbol 命中/影响面/同模块/测试/经验/架构)
  → ③ Feature Extractor 每候选 6 维特征
  → ④ RankingEngine     加权求和 → relevance_score + reason (可复算)
  → ⑤ TopKSelector     按预算取 Top-K (核心 ≤3 全量或符号段 + 相关 ≤5 符号索引)
  → ⑥ Budget Controller 任务类型动态预算 + 降级链 (正文→符号索引→摘要→context_overflow)
```

评分公式 (规则模型, 禁 ML/LLM 自评):
```text
score = 0.35·keyword_match + 0.25·symbol_relation + 0.15·dependency_distance
      + 0.10·test_relation + 0.08·history_success + 0.07·experience_match
```

可审计保证:
- 每候选带 reason (各因素得分明细, 可复算 — factor_scores + reason 并存);
- 评分纯规则, 无 LLM 自评, 无黑盒;
- content_ref 延迟加载 (候选列表先于内容, 审计只列引用 — 不预载全文);
- 全部确定性启发式; 失败安全 (任一环节异常 → 空候选/旧路径回退, 不破坏执行链)。

KISS 边界: 零 LLM、零数据库、零 Core 依赖; context.py 经 ranking_assemble()
函数级延迟导入接入 (本模块可独立 import — 无环)。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .budget import (  # T4.3: 通用 Context Budget 模型 (声明式; 本模块单向依赖, 无环)
    BUDGET_POLICIES,
    BudgetPolicy,
    BudgetTrace,
    DEFAULT_DEGRADATION_STEPS,
    apply_budget_recommendation,
    build_budget_trace,
    get_budget_policy,
    order_by_priority,
    stage_budget_for,
)
from .experience_ctx import (  # T4.4: Context Experience (单向依赖, 无环)
    budget_recommendation,
    file_success_rates,
    stage_order_from_experience,
    symbol_miss_files_from_experience,
)
from .progressive import (  # T4.2: 渐进加载引擎 (本模块单向依赖, 无环)
    LoadedItem,
    ProgressiveLoader,
    ProgressiveResult,
    STAGE_1_BUDGET_CHARS,
    STAGE_2_BUDGET_CHARS,
    StageLoadResult,
    StageSpec,
)

# ================================================================ 常量

#: 6 因素权重 (设计 §4; 和恒为 1.0 — 全满分 → 1.0)
#: T4.4 经验影响 ≤20% 硬限制: 经验相关因素 history_success (0.08) +
#: experience_match (0.07) = 0.15 ≤ 0.20 — 经验只背书不替代 (ADR-0033),
#: 历史错误不可能通过权重污染未来决策。
RANKING_WEIGHTS: dict[str, float] = {
    "keyword_match": 0.35,
    "symbol_relation": 0.25,
    "dependency_distance": 0.15,
    "test_relation": 0.10,
    "history_success": 0.08,
    "experience_match": 0.07,
}

#: 候选类型 (设计 §2)
CANDIDATE_TYPES: tuple[str, ...] = ("code", "test", "history", "experience", "architecture")

#: 任务类型 (设计 §5: T4.1 三档 + T4.3 补 refactor → 4 类)
TASK_TYPES: tuple[str, ...] = ("bug_fix", "feature", "refactor", "greenfield")

#: 任务类型 → 预算 (字符数; T4.3 派生自 BUDGET_POLICIES — 声明式单一事实源)
TASK_TYPE_BUDGETS: dict[str, int] = {
    t: p.total_budget for t, p in BUDGET_POLICIES.items()
}
#: 未知/缺省任务类型的预算 (保守取 Feature 档)
DEFAULT_TASK_BUDGET = 25_000
#: 硬顶: 总输入 ≤30K chars (≈7.5K tokens; 设计 §5)
HARD_CAP_CHARS = 30_000

#: 内容级别 (预算降级链: full → symbol → summary → one_line → drop)
LEVEL_FULL = "full"
LEVEL_SYMBOL = "symbol"
LEVEL_SUMMARY = "summary"
LEVEL_ONE_LINE = "one_line"
LEVEL_DROP = "drop"

#: 级别 → 字符成本基准 (token_cost 为全文预估 token; 4 chars/token 同 context.py)
_CHARS_PER_TOKEN = 4
_LEVEL_CHARS: dict[str, int] = {
    LEVEL_FULL: _CHARS_PER_TOKEN,       # × token_cost
    LEVEL_SYMBOL: _CHARS_PER_TOKEN,     # × token_cost (符号索引 ~1/5 正文)
    LEVEL_SUMMARY: 1,                   # × token_cost (摘要)
    LEVEL_ONE_LINE: 0,                  # 固定成本 (见 _ONELINE_CHARS)
    LEVEL_DROP: 0,
}
_SYMBOL_FRACTION = 0.2       # 符号索引成本 = 全文 × 0.2
_SUMMARY_FRACTION = 0.05     # 摘要成本 = 全文 × 0.05
_ONELINE_CHARS = 60          # 单行摘要固定成本 (架构/经验降级)
_FLOOR_SYMBOL_CHARS = 40     # 符号索引成本下限


def _clamp01(x: float) -> float:
    """0-1 截断 (评分/权重/特征统一边界)。"""
    return max(0.0, min(1.0, float(x)))


# ================================================================ ContextCandidate

class ContextCandidate(BaseModel):
    """候选上下文单元 (设计 §2): 引用优先, 内容延迟加载。

    - id: 唯一标识 (file:symbol / code:<rel> / test:<rel> / exp:<task_type> / arch:summary)
    - type: code|test|history|experience|architecture
    - source: 来源路径/引用 (审计锚点)
    - content_ref: 内容引用 (文件路径 + 段/行范围) — 不预载全文
    - token_cost: 全文预估 token (预算控制器据此做降级链)
    - relevance_score: 0-1 评分 (RankingEngine 产出)
    - reason: 可解释理由 (各因素得分明细, 可复算)
    - confidence: 置信度 (特征完整性 = 已评分因素占比)
    - factor_scores: 6 因素得分明细 (可复算的审计证据)

    校验: 评分/置信度 clamp 0-1; token_cost ≥ 0; 类型归一; extra=forbid。
    """

    model_config = {"extra": "forbid"}

    id: str
    type: str = "code"
    source: str = ""
    content_ref: str = ""
    token_cost: int = 0
    relevance_score: float = 0.0
    reason: str = ""
    confidence: float = 0.0
    factor_scores: dict[str, float] = Field(default_factory=dict)

    @field_validator("type", mode="before")
    @classmethod
    def _type_norm(cls, v: Any) -> str:
        v = str(v) if v is not None else "code"
        return v if v in CANDIDATE_TYPES else "code"

    @field_validator("source", "content_ref", "reason", mode="before")
    @classmethod
    def _strs_none(cls, v: Any) -> str:
        return str(v) if v is not None else ""

    @field_validator("relevance_score", "confidence", mode="before")
    @classmethod
    def _scores_clamp(cls, v: Any) -> float:
        return _clamp01(v) if v is not None else 0.0

    @field_validator("token_cost", mode="before")
    @classmethod
    def _cost_nonneg(cls, v: Any) -> int:
        v = int(v) if v is not None else 0
        return max(0, v)

    @field_validator("factor_scores", mode="before")
    @classmethod
    def _factors_clamp(cls, v: Any) -> dict[str, float]:
        if v is None:
            return {}
        return {str(k): _clamp01(x) for k, x in v.items()}

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好导出 (同 exec.models._ExecModel 语义)。"""
        return self.model_dump(mode="json")

    def char_cost(self, level: str = LEVEL_FULL) -> int:
        """级别 → 字符成本估算 (预算控制器用; 确定性, 不读文件)。"""
        if level == LEVEL_FULL:
            return self.token_cost * _CHARS_PER_TOKEN
        if level == LEVEL_SYMBOL:
            return max(_FLOOR_SYMBOL_CHARS, int(self.token_cost * _CHARS_PER_TOKEN * _SYMBOL_FRACTION))
        if level == LEVEL_SUMMARY:
            return max(1, int(self.token_cost * _CHARS_PER_TOKEN * _SUMMARY_FRACTION))
        if level == LEVEL_ONE_LINE:
            return _ONELINE_CHARS
        return 0  # LEVEL_DROP / 未知


# ================================================================ Task Analyzer

#: 任务文本中的符号样式词 (纯标识符形态, 可能是函数/方法名 — camelCase/snake,
#: 允许前导下划线: _cloneBlock / replaceCurrent / parse_row)
_SYMBOL_LIKE_RE = re.compile(
    r"\b(?:_*[a-z][A-Za-z0-9]*_[A-Za-z0-9_]*|_*[a-z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*)\b"
)

#: bug_fix 类型触发词 (中英; 命中任一 → bug_fix)
_BUG_FIX_MARKERS = (
    "fix", "bug", "bugfix", "error", "crash", "broken", "fail", "failed",
    "exception", "incorrect", "wrong", "修复", "错误", "崩溃", "故障", "异常", "缺陷",
    "报错", "打不开", "失效", "回归",
)
#: greenfield 类型触发词 (中英; 命中任一 → greenfield; bug_fix/refactor 优先判定)
_GREENFIELD_MARKERS = (
    "create", "new", "scaffold", "generate", "from scratch", "init", "setup",
    "新建", "创建", "从零", "生成", "搭建", "初始化", "脚手架", "首个版本",
)
#: refactor 类型触发词 (中英; T4.3 新增; 命中任一 → refactor; bug_fix 优先判定,
#: refactor 先于 greenfield — 「重构并新建…」语义是重构)
_REFACTOR_MARKERS = (
    "refactor", "restructure", "rename", "migrate", "extract", "split",
    "cleanup", "simplify", "reorganize",
    "重构", "重命名", "迁移", "拆分", "抽取", "清理", "简化", "拆解", "调整结构",
)
#: 验收标准提取标记 (行首/句中触发)
_ACCEPTANCE_MARKERS = (
    "验收", "accept", "criterion", "criteria", "must", "should", "要求",
    "应 ", "应能", "确保", "保证",
)
#: 验收行样式: 编号/列表项 (1. / - / * / ✓)
_ACCEPTANCE_LINE_RE = re.compile(r"^\s*(?:[-*✓]\s*|\d+[.)]\s*|\[\s*x?\s*\]\s*)")


class TaskProfile(BaseModel):
    """结构化任务解析产物 (设计 §3 步骤①)。

    - objective / requirement / task_id: 原始任务字段
    - task_type: bug_fix|feature|greenfield (规则检测, 可显式覆盖)
    - keywords: 标识符关键词 (camelCase/snake 拆分 — 复用 context.py 已有基础)
    - symbol_candidates: 符号样式词候选 (纯标识符形态, 供 symbol_relation 匹配)
    - acceptance: 验收标准条目 (规则提取)
    """

    model_config = {"extra": "forbid"}

    objective: str
    requirement: str = ""
    task_id: str = ""
    task_type: str = "feature"
    keywords: list[str] = Field(default_factory=list)
    symbol_candidates: list[str] = Field(default_factory=list)
    acceptance: list[str] = Field(default_factory=list)

    @field_validator("task_type", mode="before")
    @classmethod
    def _type_norm(cls, v: Any) -> str:
        v = str(v) if v is not None else "feature"
        return v if v in TASK_TYPES else "feature"

    @field_validator("objective", "requirement", "task_id", mode="before")
    @classmethod
    def _strs_none(cls, v: Any) -> str:
        return str(v) if v is not None else ""

    @field_validator("keywords", "symbol_candidates", "acceptance", mode="before")
    @classmethod
    def _lists_none(cls, v: Any) -> list[str]:
        if v is None:
            return []
        return [str(x) for x in v]

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def detect_task_type(objective: str, requirement: str = "") -> str:
    """任务文本 → 类型 (规则检测, 零 LLM; bug_fix > refactor > greenfield > feature)。

    判定顺序 (设计 §5 预算依据; T4.3 补 refactor):
    1. bug_fix: 命中修复/错误/崩溃/异常类触发词 (缺陷修复语义优先 — 预算最小);
    2. refactor: 命中重构/重命名/迁移/拆分类触发词 (T4.3 新增 — 中档偏大);
    3. greenfield: 命中新建/创建/从零类触发词 (从零构建 — 预算中档);
    4. 其余 → feature (默认 — 预算最大)。
    """
    text = f"{objective} {requirement}".lower()
    if any(m in text for m in _BUG_FIX_MARKERS):
        return "bug_fix"
    if any(m in text for m in _REFACTOR_MARKERS):
        return "refactor"
    if any(m in text for m in _GREENFIELD_MARKERS):
        return "greenfield"
    return "feature"


def extract_symbol_candidates(objective: str, requirement: str = "") -> list[str]:
    """任务文本 → 符号样式词候选 (camelCase/snake 整词, 保序去重)。

    与 keywords 的区别: keywords 是拆词后的匹配键 (replace/current),
    symbol_candidates 保留整词形态 (replaceCurrent/_cloneBlock) — 供
    symbol_relation 精确匹配真实符号名。
    """
    out: list[str] = []
    seen: set[str] = set()
    for m in _SYMBOL_LIKE_RE.finditer(_task_text_type(objective, requirement)):
        word = m.group(0)
        low = word.lower()
        if low not in seen and len(word) >= 2:
            out.append(word)
            seen.add(low)
    return out


def _task_text_type(objective: str, requirement: str) -> str:
    """文本拼接辅助 (detect/extract 共用; 小写用于匹配, 原样用于符号提取)。"""
    return f"{objective} {requirement}"


def extract_acceptance(objective: str, requirement: str = "") -> list[str]:
    """任务文本 → 验收标准条目 (规则提取, 零 LLM)。

    提取: 含验收标记 (验收/accept/criteria/must/should/要求/应/确保) 的独立行,
    或编号/列表样式行 (1. / - / * / ✓); 去重保序, 上限 8 条。
    """
    lines: list[str] = []
    seen: set[str] = set()
    for raw in f"{objective}\n{requirement}".splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        marker_hit = any(m in low for m in _ACCEPTANCE_MARKERS)
        style_hit = bool(_ACCEPTANCE_LINE_RE.match(line))
        if not (marker_hit or style_hit):
            continue
        entry = re.sub(r"^\s*(?:[-*✓]\s*|\d+[.)]\s*)", "", line).strip()
        if entry and entry not in seen:
            lines.append(entry)
            seen.add(entry)
    return lines[:8]


def analyze_task(task: Any, *, task_type: str | None = None) -> TaskProfile:
    """Task (duck-typed objective/requirement/task_id) → TaskProfile (规则解析)。

    task_type 显式传入 → 覆盖规则检测 (装配点/测试可控); None → 规则检测。
    关键词复用 context.py extract_task_keywords (camelCase+snake 拆分, 已有基础)。
    """
    objective = getattr(task, "objective", "") or ""
    requirement = getattr(task, "requirement", "") or ""
    task_id = (
        getattr(task, "task_id", "") or getattr(task, "id", "") or ""
    )
    return TaskProfile(
        objective=objective,
        requirement=requirement,
        task_id=task_id,
        task_type=task_type if task_type is not None else detect_task_type(objective, requirement),
        keywords=_extract_keywords(objective, requirement),
        symbol_candidates=extract_symbol_candidates(objective, requirement),
        acceptance=extract_acceptance(objective, requirement),
    )


def _extract_keywords(objective: str, requirement: str) -> list[str]:
    """关键词提取 (延迟 import context.py — 避免模块级环)。"""
    from .context import extract_task_keywords

    return extract_task_keywords(objective, requirement)


# ================================================================ Feature Extractor

#: 6 因素特征键 (与 RANKING_WEIGHTS 对齐; 特征完整性 = 已评分因素占比)
FACTOR_KEYS: tuple[str, ...] = (
    "keyword_match", "symbol_relation", "dependency_distance",
    "test_relation", "history_success", "experience_match",
)

#: 历史失败模式提取标记 (经验 evidence "failure_reason: X" 前缀 — 同 context.py)
_FAILURE_REASON_PREFIX = "failure_reason: "


def score_keyword_match(keywords: list[str], names: list[str]) -> float:
    """因素 1 — 任务关键词命中 (设计 §4): 精确 1.0 / 前缀 0.8 / 包含 0.6 / 无 0。

    names = 文件路径 + 符号名 + 内容头词 (可注入; 空 → 0)。
    取所有 关键词×名字 组合的最高分; 大小写不敏感。
    """
    if not keywords or not names:
        return 0.0
    kws = [k.lower() for k in keywords]
    best = 0.0
    for kw in kws:
        for name in names:
            low = name.lower()
            if low == kw:
                best = max(best, 1.0)
            elif low.startswith(kw):
                best = max(best, 0.8)
            elif kw in low:
                best = max(best, 0.6)
    return best


def score_symbol_relation(
    defines: set[str], calls: set[str], called_by: set[str], symbols: set[str]
) -> float:
    """因素 2 — 候选与任务符号关系 (设计 §4): 定义 1.0 / 调用 0.7 / 被调 0.5 / 无关 0。

    defines = 候选文件定义的符号; calls = 候选文件调用的符号 (call graph
    callee); called_by = 调用候选文件的调用方符号 (call graph caller);
    symbols = 任务符号候选。任一非空交集按优先级取分 (定义 > 调用 > 被调);
    大小写不敏感。
    """
    syms = {s.lower() for s in symbols}
    if {d.lower() for d in defines} & syms:
        return 1.0
    if {c.lower() for c in calls} & syms:
        return 0.7
    if {b.lower() for b in called_by} & syms:
        return 0.5
    return 0.0


def score_dependency_distance(distance: int | None) -> float:
    """因素 3 — 依赖距离 (设计 §4): 直接 1.0 / 间接 0.5 / 无关 0.1。

    distance: 0 = 候选即核心目标; 1 = 与核心文件直接依赖 (被依赖或依赖);
    2 = 间接 (2 跳); None = 无关。
    """
    if distance == 0 or distance == 1:
        return 1.0
    if distance == 2:
        return 0.5
    return 0.1


def score_test_relation(target_test: bool, related_test: bool) -> float:
    """因素 4 — 测试关系 (设计 §4): 目标测试 1.0 / 相关测试 0.6 / 无 0。"""
    if target_test:
        return 1.0
    if related_test:
        return 0.6
    return 0.0


def score_history_success(rate: float | None) -> float:
    """因素 5 — 文件历史任务成功率 (设计 §4): 经验库聚合; 冷启动 None → 0.5 中性。"""
    if rate is None:
        return 0.5
    return _clamp01(rate)


def score_experience_match(has_symbol_miss_history: bool) -> float:
    """因素 6 — 历史失败模式匹配 (设计 §4/§7): symbol miss 相关文件提权 +0.2。

    经验反馈首轮无历史 → 0; 该文件有 symbol_miss 失败史 → 0.2 (提权 —
    symbol 锚点易错, 该候选更值得优先给行号/正文级上下文)。
    """
    return 0.2 if has_symbol_miss_history else 0.0


class FeatureContext:
    """特征提取上下文 (RankingPipeline 装配; 全部可注入 — 纯函数可测)。

    - keywords / symbol_candidates: TaskProfile 解析产物
    - core_files: 核心目标文件集 (显式 source_files ∪ symbol 命中文件)
    - depends_on_core: 与核心文件直接依赖的文件集 (影响面 1 跳)
    - indirect: 间接关联文件集 (2 跳)
    - target_tests: 核心文件直接映射的测试文件集
    - related_tests: 相关文件映射的测试文件集 (非目标)
    - history_rates: 文件 → 历史成功率 (经验库聚合; 缺省空 → 冷启动 0.5;
      "__experience__" 键 = 经验候选自身聚合成功率)
    - symbol_miss_files: 有 symbol_miss 失败史的文件集 (经验提权)
    - defined_symbols: 文件 → 定义的符号名集合 (小写; 装配方从 ri 提取)
    - called_symbols: 文件 → 调用的符号名集合 (小写; call graph callee)
    - caller_symbols: 文件 → 调用它的调用方符号名集合 (小写; call graph caller)
    - headers: 文件 → 内容头文本 (内容头关键词命中; 缺省空 — 不读文件)
    """

    def __init__(
        self,
        *,
        keywords: list[str] | tuple[str, ...] = (),
        symbol_candidates: list[str] | tuple[str, ...] = (),
        core_files: set[str] | frozenset[str] = frozenset(),
        depends_on_core: set[str] | frozenset[str] = frozenset(),
        indirect: set[str] | frozenset[str] = frozenset(),
        target_tests: set[str] | frozenset[str] = frozenset(),
        related_tests: set[str] | frozenset[str] = frozenset(),
        history_rates: dict[str, float] | None = None,
        symbol_miss_files: set[str] | frozenset[str] = frozenset(),
        defined_symbols: dict[str, set[str]] | None = None,
        called_symbols: dict[str, set[str]] | None = None,
        caller_symbols: dict[str, set[str]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.keywords = list(keywords)
        self.symbol_candidates = {s.lower() for s in symbol_candidates}
        self.core_files = set(core_files)
        self.depends_on_core = set(depends_on_core)
        self.indirect = set(indirect)
        self.target_tests = set(target_tests)
        self.related_tests = set(related_tests)
        self.history_rates = dict(history_rates or {})
        self.symbol_miss_files = set(symbol_miss_files)
        self.defined_symbols = {k: set(v) for k, v in (defined_symbols or {}).items()}
        self.called_symbols = {k: set(v) for k, v in (called_symbols or {}).items()}
        self.caller_symbols = {k: set(v) for k, v in (caller_symbols or {}).items()}
        self.headers = dict(headers or {})


def _name_haystack(ctx: FeatureContext, rel: str, symbol_names: list[str]) -> list[str]:
    """关键词匹配的名字集合: 文件路径 + 符号名 + 内容头词 (设计 §4 匹配面)。"""
    names = [rel] + list(symbol_names)
    header = ctx.headers.get(rel, "")
    if header:
        names += header.split()
    return names


def extract_candidate_features(
    candidate: ContextCandidate, profile: TaskProfile, ctx: FeatureContext
) -> dict[str, float]:
    """每候选提取 6 维特征 (设计 §3 步骤③; 纯规则, 零 LLM)。

    code: 全 6 因素; test: keyword/test_relation/history/experience 为主,
    symbol/dependency 按无关基线; 聚合候选 (history/experience/architecture):
    keyword_match (content_ref) + 各自 history/experience 语义, 其余 0。
    """
    ctype = candidate.type
    features: dict[str, float] = {}

    if ctype == "code":
        syms = sorted(ctx.defined_symbols.get(candidate.source, set()))
        features = {
            "keyword_match": score_keyword_match(
                ctx.keywords, _name_haystack(ctx, candidate.source, syms)
            ),
            "symbol_relation": _code_symbol_relation(candidate.source, ctx),
            "dependency_distance": score_dependency_distance(
                _dependency_distance(candidate.source, ctx)
            ),
            "test_relation": 0.0,
            "history_success": score_history_success(
                ctx.history_rates.get(candidate.source)
            ),
            "experience_match": score_experience_match(
                candidate.source in ctx.symbol_miss_files
            ),
        }
    elif ctype == "test":
        features = {
            "keyword_match": score_keyword_match(
                ctx.keywords, _name_haystack(ctx, candidate.source, [])
            ),
            "symbol_relation": 0.0,
            "dependency_distance": 0.1,  # 测试非代码依赖 → 无关基线
            "test_relation": score_test_relation(
                candidate.source in ctx.target_tests,
                candidate.source in ctx.related_tests,
            ),
            "history_success": score_history_success(
                ctx.history_rates.get(candidate.source)
            ),
            "experience_match": score_experience_match(
                candidate.source in ctx.symbol_miss_files
            ),
        }
    else:
        # 聚合候选 (history/experience/architecture): 引用面关键词 + 各自语义
        own_rate = None
        if ctype == "experience":
            own_rate = ctx.history_rates.get("__experience__")
        features = {
            "keyword_match": score_keyword_match(ctx.keywords, [candidate.content_ref]),
            "symbol_relation": 0.0,
            "dependency_distance": 0.1,
            "test_relation": 0.0,
            "history_success": score_history_success(own_rate),
            "experience_match": 0.0,
        }
    return features


def _code_symbol_relation(rel: str, ctx: FeatureContext) -> float:
    """候选代码文件的符号关系 (定义 1.0 / 调用 0.7 / 被调 0.5 / 无关 0)。

    原始集合来自 ctx (装配方从 RepositoryIntelligence 提取): defined =
    文件定义的符号; called = 文件调用的符号 (call graph callee); caller =
    调用该文件的调用方符号 (call graph caller)。
    """
    return score_symbol_relation(
        ctx.defined_symbols.get(rel, set()),
        ctx.called_symbols.get(rel, set()),
        ctx.caller_symbols.get(rel, set()),
        ctx.symbol_candidates,
    )


def _dependency_distance(rel: str, ctx: FeatureContext) -> int | None:
    if rel in ctx.core_files:
        return 0
    if rel in ctx.depends_on_core:
        return 1
    if rel in ctx.indirect:
        return 2
    return None


# ================================================================ RankingEngine

def normalize_weights(weights: dict[str, float] | None = None) -> dict[str, float]:
    """权重归一 (装配/纯函数路径共用): 部分键合并到默认权重 → clamp 0-1 →
    和 > 1.0 时等比缩放 (权重上限保护, 设计 §4: 全满分 → 1.0)。

    未知键忽略 (评分只认 6 因素); 幂等 (已是合法权重 → 原样返回)。
    """
    w = dict(RANKING_WEIGHTS)
    if weights:
        for k, v in weights.items():
            if k in w:
                w[k] = _clamp01(v)
    total = sum(w.values())
    if total > 1.0:
        w = {k: v / total for k, v in w.items()}
    return w


def score_candidate(
    features: dict[str, float], weights: dict[str, float] | None = None
) -> dict[str, Any]:
    """6 因素特征 → 评分 (设计 §4): score + 各因素贡献 + reason + confidence。

    返回:
    - score: 加权求和, clamp 0-1, 3 位小数 (全零 → 0; 全满分 → 1.0);
    - contributions: 因素 → 加权贡献 (可复算审计);
    - reason: 逐因素明细字符串 (权重×特征值, 可复算);
    - confidence: 特征完整性 = 已出现因素占比 (缺失因素不参与评分)。

    纯函数可测: 输入特征向量 → 断言分数精确。
    """
    w = normalize_weights(weights)
    contributions: dict[str, float] = {}
    missing = 0
    for key in FACTOR_KEYS:
        if key not in features or features[key] is None:
            missing += 1
            contributions[key] = 0.0
            continue
        val = _clamp01(features[key])
        contributions[key] = round(w[key] * val, 6)
    score = round(max(0.0, min(1.0, sum(contributions.values()))), 3)
    reason_parts = [
        f"{key}={contributions[key]:.3f}({w[key]:.2f}×{_clamp01(features[key]) if key in features and features[key] is not None else 0.0:.3f})"
        for key in FACTOR_KEYS
    ]
    reason = "; ".join(reason_parts) + f" → score={score:.3f}"
    confidence = round(1.0 - missing / len(FACTOR_KEYS), 3)
    return {
        "score": score,
        "contributions": contributions,
        "reason": reason,
        "confidence": confidence,
    }


class RankingEngine:
    """加权评分引擎 (设计 §3 步骤④; 纯规则, 零 LLM)。

    构造可注入权重 (部分键 → 合并默认 + 上限保护); rank() 对候选+特征对
    产出 ContextCandidate (relevance_score/reason/confidence/factor_scores)。
    """

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = normalize_weights(weights)

    def score(self, features: dict[str, float]) -> dict[str, Any]:
        """特征向量 → 评分结果 (纯函数包装, 用引擎权重)。"""
        return score_candidate(features, self.weights)

    def rank(
        self, candidates: list[ContextCandidate], features_map: dict[str, dict[str, float]]
    ) -> list[ContextCandidate]:
        """候选+特征 → 评分排序后的候选列表 (降序; 同分按 id 升序稳定)。

        不修改入参对象 — model_copy 产出新实例 (同服务层 model_copy 语义)。
        缺失特征映射的候选 → 按 0 分全因素缺失处理 (置信度 0)。
        """
        scored: list[ContextCandidate] = []
        for c in candidates:
            features = features_map.get(c.id, {})
            result = score_candidate(features, self.weights)
            scored.append(
                c.model_copy(
                    update={
                        "relevance_score": result["score"],
                        "reason": result["reason"],
                        "confidence": result["confidence"],
                        "factor_scores": result["contributions"],
                    }
                )
            )
        scored.sort(key=lambda c: (-c.relevance_score, c.id))
        return scored


# ================================================================ TopKSelector

class TopKSelection:
    """Top-K 选择结果 (设计 §3 步骤⑤): 核心/相关分级 + 初始级别映射。

    - core: 核心候选 (≤core_limit; 初始级别 full — 全量或符号段)
    - related: 相关候选 (≤related_limit; 初始级别 symbol — 符号索引)
    - levels: 候选 id → 初始级别 (full|symbol; 预算控制器接手降级链)
    - selected_ids: 选中候选 id 序列 (core 优先, 各按评分降序)
    - all: 完整选中候选列表 (core + related, 评分降序)

    聚合候选 (history/experience/architecture) 不在 Top-K 名额内 —
    由预算控制器保留为 summary/one_line 级 (设计 §3 步骤⑤)。
    """

    def __init__(
        self,
        core: list[ContextCandidate],
        related: list[ContextCandidate],
        levels: dict[str, str],
    ) -> None:
        self.core = core
        self.related = related
        self.levels = levels

    @property
    def selected_ids(self) -> list[str]:
        return [c.id for c in self.core] + [c.id for c in self.related]

    @property
    def all(self) -> list[ContextCandidate]:
        return self.core + self.related

    def to_dict(self) -> dict[str, Any]:
        return {
            "core_ids": [c.id for c in self.core],
            "related_ids": [c.id for c in self.related],
            "levels": dict(self.levels),
        }


class TopKSelector:
    """按预算取 Top-K (设计 §3 步骤⑤; 纯规则, 零 LLM)。

    输入已按评分降序的候选列表; 核心/相关分级:
    - 核心 = caller 标记的 core_ids (依赖距离 0/1: 核心目标 + 直接依赖);
    - 相关 = 其余 code/test 候选 (影响面/同模块/测试);
    - 聚合候选 (history/experience/architecture) 自动排除 — 不占名额。

    截断: 核心 ≤3 (默认) / 相关 ≤5 (默认); 排序随入参 (评分降序稳定)。
    """

    def __init__(self, core_limit: int = 3, related_limit: int = 5) -> None:
        self.core_limit = max(0, core_limit)
        self.related_limit = max(0, related_limit)

    def select_top_k(
        self,
        ranked: list[ContextCandidate],
        *,
        core_ids: set[str] | frozenset[str] | None = None,
    ) -> TopKSelection:
        """评分排序后的候选 → 核心/相关分级截断 (不修改入参)。"""
        core_ids = set(core_ids or frozenset())
        core: list[ContextCandidate] = []
        related: list[ContextCandidate] = []
        for c in ranked:
            if c.type not in ("code", "test"):
                continue  # 聚合候选不占 Top-K 名额
            if c.id in core_ids and len(core) < self.core_limit:
                core.append(c)
            elif len(related) < self.related_limit:
                related.append(c)
        levels: dict[str, str] = {c.id: LEVEL_FULL for c in core}
        for c in related:
            levels[c.id] = LEVEL_SYMBOL
        return TopKSelection(core=core, related=related, levels=levels)


# ================================================================ Budget Controller

class BudgetResult:
    """预算控制结果 (设计 §5/§6): 级别映射 + 降级链记录 + overflow 标记。

    - selected_ids: 最终入选候选 id (drop 的排除)
    - levels: 候选 id → 最终级别 (full|symbol|summary|one_line)
    - total_chars: 最终总字符成本
    - budget_chars: 实际生效预算 (min(任务类型预算, 硬顶))
    - degraded_steps: 降级链每步记录 (审计)
    - context_overflow: 降级链走完仍超预算 (执行前警示)
    - task_type: 生效任务类型
    """

    def __init__(
        self,
        *,
        selected_ids: list[str],
        levels: dict[str, str],
        total_chars: int,
        budget_chars: int,
        degraded_steps: list[str],
        context_overflow: bool,
        task_type: str,
    ) -> None:
        self.selected_ids = list(selected_ids)
        self.levels = dict(levels)
        self.total_chars = int(total_chars)
        self.budget_chars = int(budget_chars)
        self.degraded_steps = list(degraded_steps)
        self.context_overflow = bool(context_overflow)
        self.task_type = task_type

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_ids": list(self.selected_ids),
            "levels": dict(self.levels),
            "total_chars": self.total_chars,
            "budget_chars": self.budget_chars,
            "degraded_steps": list(self.degraded_steps),
            "context_overflow": self.context_overflow,
            "task_type": self.task_type,
        }


class BudgetController:
    """任务类型预算 + 降级链 (设计 §5; 纯规则, 零 LLM)。

    预算 (chars): bug_fix 20K / feature 25K / greenfield 15K; 硬顶 30K —
    实际生效预算 = min(任务类型预算, 硬顶)。

    初始级别: 核心→full, 相关→symbol, 测试→symbol, 聚合候选→summary。
    降级链 (每步记录到 degraded_steps, 超预算才触发下一步):
      1. 相关符号索引收缩 (symbol 成本 ×0.5)
      2. 经验 → one_line 摘要
      3. 架构 → one_line 摘要
      4. 最低分核心 full → symbol (逐个, 最低分先)
      5. 丢弃最低分相关候选 (逐个)
      6. 仍超 → context_overflow=True (执行前警示)
    """

    def __init__(
        self,
        task_type: str = "feature",
        budget: int | None = None,
        hard_cap: int = HARD_CAP_CHARS,
        degradation_order: list[str] | None = None,
        policy: BudgetPolicy | None = None,
        recommended_budget: int | None = None,
    ) -> None:
        """预算控制器构造 (T4.3: 声明式策略注入 + 降级链调序)。

        - policy: 注入 BudgetPolicy (Agent 通用化 — 自定义任务类型/预算表);
          None → 从 BUDGET_POLICIES 取任务类型策略;
        - degradation_order: 显式降级链顺序; None → 策略的 degradation_order
          (空 → 默认链 T4.1 原序)。显式传入覆盖策略 (局部微调)。
        - recommended_budget (T4.4): 经验预算推荐 (历史同类任务成功记录实际
          用量均值; 经 apply_budget_recommendation clamp ±20% — 经验影响
          ≤20% 硬限制)。None → 策略预算 (旧语义逐位不变)。
        """
        if policy is not None:
            self._policy = policy
            self.task_type = policy.task_type
        else:
            self.task_type = task_type if task_type in TASK_TYPE_BUDGETS else "feature"
            self._policy = get_budget_policy(self.task_type)
        self.budget = (
            budget if budget is not None
            else TASK_TYPE_BUDGETS.get(self.task_type, self._policy.total_budget)
        )
        self.hard_cap = max(1, hard_cap)
        self.recommended_budget = recommended_budget
        self._degradation_order = (
            list(degradation_order) if degradation_order is not None
            else list(self._policy.degradation_order)
        )

    def apply_budget(
        self,
        selection: TopKSelection | None = None,
        aggregates: list[ContextCandidate] | None = None,
    ) -> BudgetResult:
        """Top-K 选择 + 聚合候选 → 级别映射/成本/降级链 (不修改入参)。"""
        selection = selection or TopKSelection(core=[], related=[], levels={})
        budget = apply_budget_recommendation(
            self.recommended_budget, self.budget, self.hard_cap
        )
        # (candidate, level, is_related)
        items: list[list[Any]] = []
        for c in selection.core:
            items.append([c, LEVEL_FULL, False])
        for c in selection.related:
            items.append([c, LEVEL_SYMBOL, True])
        for c in aggregates or []:
            items.append([c, LEVEL_SUMMARY, False])

        degraded: list[str] = []
        related_shrunk = False

        def total_cost() -> int:
            total = 0
            for cand, lvl, is_rel in items:
                cost = cand.char_cost(lvl)
                if related_shrunk and is_rel and lvl == LEVEL_SYMBOL:
                    cost //= 2  # 降级链: 相关符号索引收缩 ×0.5
                total += cost
            return total

        # --- 降级步骤表 (T4.3 声明式: 每步独立函数; 顺序由策略/显式参数决定) ---
        def step_related_shrink() -> bool:
            nonlocal related_shrunk
            if not related_shrunk and any(it[2] and it[1] == LEVEL_SYMBOL for it in items):
                related_shrunk = True
                degraded.append("related_symbol_shrink")
                return True
            return False

        def step_experience_one_line() -> bool:
            idx = next(
                (i for i, it in enumerate(items)
                 if it[0].type == "experience" and it[1] == LEVEL_SUMMARY),
                None,
            )
            if idx is None:
                return False
            items[idx][1] = LEVEL_ONE_LINE
            degraded.append("experience_one_line")
            return True

        def step_architecture_one_line() -> bool:
            idx = next(
                (i for i, it in enumerate(items)
                 if it[0].type == "architecture" and it[1] == LEVEL_SUMMARY),
                None,
            )
            if idx is None:
                return False
            items[idx][1] = LEVEL_ONE_LINE
            degraded.append("architecture_one_line")
            return True

        def step_core_full_to_symbol() -> bool:
            core_full = [i for i, it in enumerate(items) if not it[2] and it[1] == LEVEL_FULL]
            if not core_full:
                return False
            core_full.sort(key=lambda i: (items[i][0].relevance_score, items[i][0].id))
            idx = core_full[0]
            items[idx][1] = LEVEL_SYMBOL
            degraded.append(f"core_full_to_symbol:{items[idx][0].id}")
            return True

        def step_drop_related() -> bool:
            rel_symbol = [i for i, it in enumerate(items) if it[2] and it[1] == LEVEL_SYMBOL]
            if not rel_symbol:
                return False
            rel_symbol.sort(key=lambda i: (items[i][0].relevance_score, items[i][0].id))
            idx = rel_symbol[0]
            items[idx][1] = LEVEL_DROP
            degraded.append(f"drop_related:{items[idx][0].id}")
            return True

        step_table = {
            "related_symbol_shrink": step_related_shrink,
            "experience_one_line": step_experience_one_line,
            "architecture_one_line": step_architecture_one_line,
            "core_full_to_symbol": step_core_full_to_symbol,
            "drop_related": step_drop_related,
        }
        # 顺序: 显式/策略顺序 + 未列出的默认步骤追加末尾 (未知步骤名安全跳过)
        order = [s for s in self._degradation_order if s in step_table]
        for s in DEFAULT_DEGRADATION_STEPS:
            if s not in order:
                order.append(s)

        while total_cost() > budget:
            acted = False
            for step_name in order:
                if step_table[step_name]():
                    acted = True
                    break
            if not acted:
                break  # 无可降级 → overflow

        levels = {c.id: lvl for c, lvl, _ in items if lvl != LEVEL_DROP}
        selected_ids = [c.id for c, lvl, _ in items if lvl != LEVEL_DROP]
        return BudgetResult(
            selected_ids=selected_ids,
            levels=levels,
            total_chars=total_cost(),
            budget_chars=budget,
            degraded_steps=degraded,
            context_overflow=total_cost() > budget,
            task_type=self.task_type,
        )


# ================================================================ Candidate Generator

class CandidateBatch:
    """生成器产物: 候选池 + 选择元数据 (FeatureContext 装配 + 组装渲染输入)。

    - candidates: 全部候选 (code/test/history/experience/architecture)
    - core_files / related_files: 文件选择结果 (距离 0 / 1 跳语义同 context.select_files)
    - test_mapping: 核心/相关文件 → 测试文件映射 (select_tests 复用)
    - symbol_hits: select_symbols 命中 [(file, SymbolEntry, score)]
    - history_entries / experience_ctx / arch_ctx: 聚合候选的预渲染内容
    """

    def __init__(
        self,
        *,
        candidates: list[ContextCandidate],
        core_files: list[str],
        related_files: list[str],
        test_mapping: dict[str, list[str]],
        symbol_hits: list[tuple[str, Any, float]],
        history_entries: list[str],
        experience_ctx: Any,
        arch_ctx: Any,
    ) -> None:
        self.candidates = candidates
        self.core_files = core_files
        self.related_files = related_files
        self.test_mapping = test_mapping
        self.symbol_hits = symbol_hits
        self.history_entries = history_entries
        self.experience_ctx = experience_ctx
        self.arch_ctx = arch_ctx

    @property
    def aggregates(self) -> list[ContextCandidate]:
        """聚合候选 (history/experience/architecture — 不占 Top-K 名额)。"""
        return [c for c in self.candidates if c.type in ("history", "experience", "architecture")]


def _file_chars(root: Path, rel: str) -> int:
    """文件字符数 (token_cost 估算; 缺失/读失败 → 0 — 失败安全)。"""
    try:
        path = root / rel
        if not path.is_file():
            return 0
        return len(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:  # noqa: BLE001 — 失败安全
        return 0


def _arch_context(ri: Any) -> Any:
    """ArchitectureContext 预渲染 (镜像 ContextAssembler._architecture — 独立小段避免跨包私有耦合)。"""
    from .context import ArchitectureContext

    if ri is None or ri.architecture is None:
        return ArchitectureContext()
    arch = ri.architecture
    ctx = ArchitectureContext(
        entry_points=list(arch.entry_points or []),
        modules=[m.path for m in (ri.modules or [])][:12],
        tech_stack=list(arch.tech_stack or []),
    )
    try:
        ctx.summary = ri.format_context(
            max_files=80, include_modules=True,
            include_architecture=True, include_tests=False,
        )[: 8000]
    except Exception:  # noqa: BLE001 — 摘要失败安全
        ctx.summary = ""
    return ctx


class CandidateGenerator:
    """任务结构化 → ContextCandidate 候选池 (设计 §3 步骤②; 复用 context.py 选择器, 零复制)。

    复用面 (全部延迟 import context.py — 单向无环):
    - select_symbols: 任务关键词 → 符号命中;
    - select_files: 核心/相关文件选择 (source_files ∪ 符号命中 / 影响面 ∪ 同模块);
    - select_tests: 测试映射;
    - git_history / experience_advice: 历史与经验聚合。

    全部确定性启发式; ri=None (情报不可用) → 只产 source_files 代码候选 + 空聚合。
    """

    def __init__(
        self,
        root: str | Path,
        *,
        ri: Any = None,
        project_dir: str | Path | None = None,
        analyzer: Any = None,
        git_bin: str = "git",
    ) -> None:
        self._root = Path(root)
        self._ri = ri
        self._project_dir = Path(project_dir) if project_dir else self._root
        self._analyzer = analyzer
        self._git_bin = git_bin

    # ------------------------------------------------------------------ 生成

    def generate(
        self, profile: TaskProfile, source_files: list[str]
    ) -> CandidateBatch:
        """TaskProfile + 显式源文件 → 候选池 + 选择元数据。"""
        from .context import (
            experience_advice,
            git_history,
            select_files,
            select_symbols,
            select_tests,
        )
        from .repo_intelligence import TestMapper

        ri = self._ri
        keywords = profile.keywords
        symbol_hits = select_symbols(ri, keywords) if ri is not None else []
        if ri is not None:
            core_files, related_files = select_files(
                ri, source_files=source_files, symbol_hits=symbol_hits,
                keywords=keywords,
            )
        else:
            core_files = list(source_files[:6])
            related_files = []
        test_mapping = select_tests(ri, core_files) if ri is not None else {}
        history_entries = git_history(
            self._project_dir, core_files[:6], git_bin=self._git_bin
        )
        exp_ctx = experience_advice(
            self._analyzer, task_type="development", keywords=keywords
        )
        arch_ctx = _arch_context(ri)

        candidates: list[ContextCandidate] = []
        # code 候选 (核心 + 相关; 内容延迟加载 — 只估 token_cost 不预载)。
        # 相关文件里跳过测试文件 (is_test_file) — 测试由 test 候选覆盖,
        # 避免同一文件同时出现 code/test 双候选 (KISS)。
        for rel in core_files:
            candidates.append(
                ContextCandidate(
                    id=f"code:{rel}", type="code", source=rel, content_ref=rel,
                    token_cost=max(1, _file_chars(self._root, rel) // _CHARS_PER_TOKEN),
                )
            )
        for rel in related_files:
            if TestMapper.is_test_file(rel):
                continue
            candidates.append(
                ContextCandidate(
                    id=f"code:{rel}", type="code", source=rel, content_ref=rel,
                    token_cost=max(1, _file_chars(self._root, rel) // _CHARS_PER_TOKEN),
                )
            )
        # test 候选
        for _src, tests in test_mapping.items():
            for t in tests:
                if any(c.id == f"test:{t}" for c in candidates):
                    continue
                candidates.append(
                    ContextCandidate(
                        id=f"test:{t}", type="test", source=t, content_ref=t,
                        token_cost=max(1, _file_chars(self._root, t) // _CHARS_PER_TOKEN),
                    )
                )
        # 聚合候选 (summary 级; 内容 = 引用摘要)
        candidates.append(
            ContextCandidate(
                id="history:summary", type="history",
                content_ref=f"{len(history_entries)} git entries",
                token_cost=max(1, sum(len(e) for e in history_entries) // _CHARS_PER_TOKEN),
            )
        )
        candidates.append(
            ContextCandidate(
                id=f"exp:{profile.task_type}", type="experience",
                content_ref=f"experience for {profile.task_type}",
                token_cost=max(1, len(exp_ctx.advice) * 30 // _CHARS_PER_TOKEN),
            )
        )
        candidates.append(
            ContextCandidate(
                id="arch:summary", type="architecture",
                content_ref="architecture summary",
                token_cost=max(1, len(arch_ctx.summary) // _CHARS_PER_TOKEN),
            )
        )
        return CandidateBatch(
            candidates=candidates,
            core_files=core_files,
            related_files=related_files,
            test_mapping=test_mapping,
            symbol_hits=symbol_hits,
            history_entries=history_entries,
            experience_ctx=exp_ctx,
            arch_ctx=arch_ctx,
        )


# ================================================================ Progressive Loading (T4.2)

#: Developer 域渐进阶段配置 (声明式 StageSpec — 设计 §2/§4/§7; 引擎通用,
#: 未来 Product/Finance/Medical Agent 配不同 StageSpec, 引擎不变):
#: Stage 1 Overview 1-2K (必载) → Stage 2 Symbol 3-5K → Stage 3 Code Detail 剩余
#: (总 ≤30K chars — ProgressiveLoader hard_cap)。
CODE_PROGRESSIVE_STAGES: list[StageSpec] = [
    StageSpec(stage="overview", label="Overview Context", max_chars=STAGE_1_BUDGET_CHARS,
              extractor="overview", required=True),
    StageSpec(stage="symbol", label="Symbol Context", max_chars=STAGE_2_BUDGET_CHARS,
              extractor="symbol", required=False),
    StageSpec(stage="detail", label="Code Detail", max_chars=0, extractor="detail",
              required=False),
]


def code_progressive_stages_for(task_type: str = "feature") -> list[StageSpec]:
    """任务类型 → 渐进阶段配置 (T4.3 Dynamic Budget Policy)。

    Budget Enforcement 三档语义 (设计 §4):
    - Stage 1 固定: overview 恒 STAGE_1_BUDGET_CHARS (2K 必载);
    - Stage 2 动态: symbol 取任务类型策略 stage_budget (bug_fix 4K / feature 5K /
      refactor 5K / greenfield 1K — 优先级取向不同);
    - Stage 3 剩余: detail max_chars=0 → loader 给剩余预算 (总 ≤ 任务类型预算)。

    CODE_PROGRESSIVE_STAGES 保持不变 = feature 档 (声明式测试依赖)。
    """
    policy = get_budget_policy(task_type)
    return [
        StageSpec(stage="overview", label="Overview Context",
                  max_chars=STAGE_1_BUDGET_CHARS, extractor="overview", required=True),
        StageSpec(stage="symbol", label="Symbol Context",
                  max_chars=stage_budget_for(policy, "symbol", STAGE_2_BUDGET_CHARS),
                  extractor="symbol", required=False),
        StageSpec(stage="detail", label="Code Detail", max_chars=0, extractor="detail",
                  required=False),
    ]

#: 载荷哨兵 (finalize 区分「已由 6 节结构承载」与「进 notes 聚合片段」)
_PAYLOAD_REQ = "requirement"        # RequirementContext 承载
_PAYLOAD_ARCH = "architecture"      # ArchitectureContext 承载
_PAYLOAD_HIST = "history"           # HistoryContext 承载
_PAYLOAD_TEST_MAP = "test_mapping"  # TestContext.mapping 承载


class CodeProgressiveProvider:
    """Developer 域渐进内容提取器 (设计 §2/§6; StageSpec 语义化 — 引擎不解释内容)。

    三阶段内容:
    - overview (必载, 1-2K): 任务需求 (keep 锚点) + 架构摘要 + 文件/模块树 + 历史;
    - symbol (3-5K): 相关文件 symbol 索引 (payload=FileSlice related) + 核心锚点 +
      call graph + test 关系 + line_range 兜底提示 (symbol miss 扩 1 轮后加入);
    - detail (剩余): 核心代码锚点段 (≤3000 行全量 / 超长符号索引+关键块) + 测试代码。

    失败兜底 (设计 §6):
    - 候选未定位 → candidates_found=False (loader 自动扩 1 轮 → unable_to_locate);
    - symbol miss → line_range 提示 (widen 轮加入, missing_info 清除);
    - 超大文件 → 符号索引 + 命中关键词锚点段 + large_file 记录;
    - token 超限 → degrade=True 返回 symbol 级轻量内容 (loader 重试 1 次)。

    finalize: ProgressiveResult → AssembledContext (6 节旧语义; 全部已加载内容
    进 prompt — 无 payload 的 notes 项聚合为 progressive_notes 相关片段, 不丢内容)。
    """

    def __init__(
        self,
        root: str | Path,
        *,
        ri: Any,
        profile: TaskProfile,
        batch: CandidateBatch,
        budget: Any,
        symbol_miss: list[str],
    ) -> None:
        self._root = Path(root)
        self._ri = ri
        self._profile = profile
        self._batch = batch
        self._budget = budget
        self._symbol_miss = list(symbol_miss)
        self._symbol_widened = False
        self._cand_by_id = {c.id: c for c in batch.candidates}

    # ------------------------------------------------------------------ 契约

    def extract(
        self, spec: StageSpec, *, widen: bool = False, degrade: bool = False
    ) -> StageLoadResult:
        """Loader 契约: StageSpec + widen/degrade → StageLoadResult (内容+决策元数据)。"""
        if spec.stage == "overview":
            return self._overview(widen)
        if spec.stage == "symbol":
            return self._symbol(widen)
        if spec.stage == "detail":
            return self._detail(degrade)
        return StageLoadResult(items=[], confidence=0.0, candidates_found=False,
                               missing_info=True)

    def finalize(self, result: ProgressiveResult) -> Any:
        """Loader finalizer 契约: ProgressiveResult → AssembledContext (6 节, 旧语义)。"""
        from .context import (
            AssembledContext,
            CodeContext,
            FileSlice,
            HistoryContext,
            RequirementContext,
            TestContext,
            quality_score,
        )

        profile = self._profile
        batch = self._batch
        trace = result.trace
        stage_items = result.stage_items

        core_slices: list[FileSlice] = []
        related_slices: list[FileSlice] = []
        test_slices: list[FileSlice] = []
        notes: list[str] = []
        for stage in ("overview", "symbol", "detail"):
            for it in stage_items.get(stage, []):
                payload = it.payload
                if isinstance(payload, FileSlice):
                    if payload.kind == "core":
                        core_slices.append(payload)
                    elif payload.kind == "related":
                        related_slices.append(payload)
                    elif payload.kind == "test":
                        test_slices.append(payload)
                elif payload is None and it.content:
                    notes.append(it.content)  # 未由 6 节结构承载 → notes 聚合
        if notes:
            related_slices.append(
                FileSlice(rel_path="progressive_notes", kind="related",
                          content="\n\n".join(notes))
            )

        exp = batch.experience_ctx.model_copy(deep=True)
        if trace.unable_to_locate:
            exp.advice.append(
                "未能定位候选文件 — 上下文仅含任务/架构概览; 建议人工介入或补充 source_files"
            )
        if trace.symbol_miss:
            names = ", ".join(trace.symbol_miss[:3])
            exp.advice.append(
                f"任务引用符号 ({names}) 未在仓库中定义 — 定位请用 line_range "
                "(见源文件 `N|` 行号), 勿用 symbol 锚点"
            )
        if trace.large_file:
            exp.advice.append(
                "超大文件已转 symbol 索引+锚点段 (不全文) — 精确定位用 line_range"
            )
        if trace.context_overflow:
            exp.advice.append(
                "上下文超出预算已降级 (符号索引/摘要级) — 精确定位用 line_range, 保持最小改动"
            )
        if trace.low_confidence:
            exp.advice.append(
                "上下文低置信度加载 (渐进加载失败兜底) — 执行时保持最小改动, 验证逐条核验"
            )

        score = quality_score(
            core_files=core_slices, related_files=related_slices,
            mapping=batch.test_mapping, keywords=profile.keywords, experience=exp,
        )
        if trace.context_overflow or self._budget.context_overflow:
            score = round(score * 0.5, 3)  # 降级 → 质量分减半 (执行前警示)

        return AssembledContext(
            requirement=RequirementContext(
                objective=profile.objective, requirement=profile.requirement,
                task_id=profile.task_id,
            ),
            architecture=batch.arch_ctx,
            code=CodeContext(
                core_files=core_slices, related_files=related_slices,
                keywords=profile.keywords,
            ),
            history=HistoryContext(entries=batch.history_entries),
            test=TestContext(test_files=test_slices, mapping=batch.test_mapping),
            experience=exp,
            context_score=score,
            total_chars=result.total_chars,
            token_estimate=result.total_chars // 4,
        )

    # ------------------------------------------------------------------ 提取

    def _selected_code_test(self) -> list[ContextCandidate]:
        """预算后选中的 code/test 候选 (按 selected_ids 序)。"""
        out: list[ContextCandidate] = []
        for cid in self._budget.selected_ids:
            c = self._cand_by_id.get(cid)
            if c is not None and c.type in ("code", "test"):
                out.append(c)
        return out

    def _overview(self, widen: bool = False) -> StageLoadResult:
        from .context import RequirementContext

        profile = self._profile
        arch = self._batch.arch_ctx
        req = RequirementContext(
            objective=profile.objective, requirement=profile.requirement,
            task_id=profile.task_id,
        )
        selected = self._selected_code_test()
        refs = [c.content_ref for c in selected][:8]
        tree_lines = [
            "modules: " + (", ".join(arch.modules[:12]) if arch.modules else "(无模块情报)"),
            "entry_points: " + (", ".join(arch.entry_points[:6]) if arch.entry_points else "(无)"),
            "tech_stack: " + (", ".join(arch.tech_stack[:8]) if arch.tech_stack else "(无)"),
            "candidates: " + (", ".join(refs) if refs else "(无候选文件 — 未能定位)"),
        ]
        items = [
            LoadedItem(content_ref="req:task", content=req.render(), keep=True,
                       payload=_PAYLOAD_REQ),
            LoadedItem(content_ref="arch:summary",
                       content=arch.summary or "(仓库结构摘要不可用 — 仍以内联源文件为准)",
                       payload=_PAYLOAD_ARCH),
            LoadedItem(content_ref="tree:overview", content="\n".join(tree_lines)),
            LoadedItem(content_ref="history:summary",
                       content="\n".join(self._batch.history_entries[:6])
                       or "(无可用提交历史 — 沙箱基线)",
                       payload=_PAYLOAD_HIST),
        ]
        found = bool(selected)
        confidence = max((c.relevance_score for c in selected), default=0.0)
        # T4.3: 任务类型优先级影响加载顺序 (bug_fix 降低全局架构 → arch 排后)
        items = order_by_priority(items, self._profile.task_type)
        return StageLoadResult(
            items=items, confidence=confidence, candidates_found=found,
            missing_info=not found,
        )

    def _symbol(self, widen: bool = False) -> StageLoadResult:
        from .context import FileSlice, _file_symbol_index

        ri = self._ri
        items: list[LoadedItem] = []
        # 1) 相关 (symbol 级) 候选符号索引 (payload=related slice; 核心 full 在 detail)
        related = [
            c for c in self._selected_code_test()
            if c.type == "code" and self._budget.levels.get(c.id) != LEVEL_FULL
        ]
        for c in related:
            idx = _file_symbol_index(ri, c.source) if ri is not None else ""
            if not idx:
                continue
            items.append(
                LoadedItem(
                    content_ref=f"symbol:{c.id}", content=idx,
                    payload=FileSlice(rel_path=c.source, kind="related",
                                      content=idx, symbol_index=idx),
                )
            )
        # 2) call graph (callers/callees — 影响面; 设计 §2 Stage 2)
        graph_lines: list[str] = []
        if ri is not None:
            for rel in self._batch.core_files[:5]:
                callees = [e.callee_symbol for e in ri.call_graph.callees_of(rel)][:8]
                callers = [e.caller_symbol for e in ri.call_graph.callers_of(rel)][:8]
                if callees:
                    graph_lines.append(f"{rel} → calls: {', '.join(callees)}")
                if callers:
                    graph_lines.append(f"{rel} ← called_by: {', '.join(callers)}")
        if graph_lines:
            items.append(LoadedItem(content_ref="graph:call",
                                    content="\n".join(graph_lines)))
        # 3) test 关系 (test_map — 设计 §2 Stage 2)
        map_lines = [
            f"{src} → {', '.join(t[:4])}"
            for src, t in list(self._batch.test_mapping.items())[:8]
        ]
        if map_lines:
            items.append(
                LoadedItem(content_ref="tests:mapping",
                           content="\n".join(map_lines), payload=_PAYLOAD_TEST_MAP)
            )
        # 4) symbol miss → line_range 兜底提示 (widen 轮加入; 设计 §6)
        missing = bool(self._symbol_miss) and not self._symbol_widened
        if widen and missing:
            self._symbol_widened = True
            names = ", ".join(self._symbol_miss[:3])
            hint = (
                f"任务引用符号 ({names}) 未在仓库中定义 — 定位请用 line_range "
                "(见源文件 `N|` 行号), 勿用 symbol 锚点"
            )
            items.append(LoadedItem(content_ref="hint:line_range", content=hint))
            missing = False
        # 锚点确定: line_range 兜底恒可用 (设计 §2: symbol 或 line_range)
        # T4.3: 任务类型优先级 (bug_fix: symbol/test 先于架构; refactor: graph 前置)
        items = order_by_priority(items, self._profile.task_type)
        return StageLoadResult(
            items=items, confidence=1.0 if items else 0.5, anchor_found=True,
            missing_info=missing, symbol_miss=list(self._symbol_miss),
        )

    def _detail(self, degrade: bool = False) -> StageLoadResult:
        from .context import (
            CORE_LINE_CAP,
            FileSlice,
            _file_symbol_index,
            _read_file_text,
            _render_lines,
            _symbol_blocks,
        )

        ri = self._ri
        items: list[LoadedItem] = []
        large: list[str] = []
        for cid in self._budget.selected_ids:
            cand = self._cand_by_id.get(cid)
            if cand is None or cand.type not in ("code", "test"):
                continue
            lvl = self._budget.levels.get(cid)
            if cand.type == "code" and lvl == LEVEL_FULL:
                if degrade:
                    # token 超限降级: 只给 symbol 锚点 (正文 → 符号索引; 设计 §4 降级链)
                    idx = _file_symbol_index(ri, cand.source) if ri is not None else ""
                    if idx:
                        items.append(LoadedItem(content_ref=f"symbol:{cid}", content=idx))
                    continue
                lines = _read_file_text(self._root, cand.source)
                line_count = len(lines)
                if line_count <= CORE_LINE_CAP:
                    content = _render_lines("\n".join(lines)) if lines else ""
                    slice_ = FileSlice(rel_path=cand.source, kind="core",
                                       content=content, line_count=line_count)
                    items.append(LoadedItem(content_ref=f"code:{cid}", content=content,
                                            payload=slice_))
                else:
                    # 超大文件: 符号索引 + 命中关键词锚点段 (不全文; 设计 §6)
                    large.append(cand.source)
                    f = ri.index.find(cand.source) if ri is not None else None
                    symbols = f.symbols if f is not None else []
                    blocks = _symbol_blocks(lines, symbols, self._profile.keywords)
                    idx = _file_symbol_index(ri, cand.source) if ri is not None else ""
                    parts = [
                        f"// (文件 {cand.source} 共 {line_count} 行, 超过 {CORE_LINE_CAP} 行上限 —",
                        "//  以下为 symbol 索引 + 命中任务关键词的函数块; 完整文件不内联)",
                    ]
                    if idx:
                        parts.append(idx)
                    for sym, start, end in blocks[:6]:
                        block_text = "\n".join(lines[start : end + 1])
                        parts.append(
                            f"// 关键段: {sym.kind.value} {sym.name} (行 {start + 1}-{end + 1}):"
                        )
                        parts.append(_render_lines(block_text))
                    content = "\n".join(parts)
                    slice_ = FileSlice(rel_path=cand.source, kind="core",
                                       content=content, line_count=line_count,
                                       truncated=True, symbol_index=idx)
                    items.append(LoadedItem(content_ref=f"code:{cid}", content=content,
                                            payload=slice_))
            elif cand.type == "test":
                # 相关测试代码 (设计 §2 Stage 3; 小文件全量, 大文件符号索引)
                lines = _read_file_text(self._root, cand.source)
                if lines and len(lines) <= 200:
                    content = _render_lines("\n".join(lines))
                    slice_ = FileSlice(rel_path=cand.source, kind="test",
                                       content=content, line_count=len(lines))
                else:
                    idx = _file_symbol_index(ri, cand.source) if ri is not None else ""
                    content = idx or ""
                    slice_ = FileSlice(rel_path=cand.source, kind="test",
                                       content=content, symbol_index=idx)
                items.append(LoadedItem(content_ref=f"test:{cand.id}", content=content,
                                        payload=slice_))
        # T4.3: 任务类型优先级 (feature: tests 先于核心; bug_fix: 目标文件最优先)
        items = order_by_priority(items, self._profile.task_type)
        return StageLoadResult(
            items=items, confidence=1.0 if items else 0.4, anchor_found=True,
            large_file=large,
        )


# ================================================================ Ranking Pipeline

class RankingPipelineResult:
    """Pipeline 全链产物 (审计 + 组装输出)。

    progressive: T4.2 渐进加载产物 (ProgressiveResult; 旧路径 run() 缺省
    progressive=False → None — 一次性组装语义不变)。
    budget_trace: T4.3 预算审计 (BudgetTrace; 供 Experience Learning T4.4 —
    含 task_type/planned/requested/actual/token/overflow/degraded/success)。
    """

    def __init__(
        self,
        *,
        profile: TaskProfile,
        batch: CandidateBatch,
        feature_context: FeatureContext,
        ranked: list[ContextCandidate],
        selection: Any,
        budget: Any,
        assembled: Any,
        symbol_miss: list[str],
        progressive: Any = None,
        budget_trace: Any = None,
    ) -> None:
        self.profile = profile
        self.batch = batch
        self.feature_context = feature_context
        self.ranked = ranked
        self.selection = selection
        self.budget = budget
        self.assembled = assembled
        self.symbol_miss = symbol_miss
        self.progressive = progressive
        self.budget_trace = budget_trace

    def to_dict(self) -> dict[str, Any]:
        """审计摘要 (候选数/评分/预算/降级链/符号缺失/渐进 Trace/预算审计)。"""
        d: dict[str, Any] = {
            "task_type": self.profile.task_type,
            "candidates": len(self.batch.candidates),
            "ranked_ids": [c.id for c in self.ranked[:10]],
            "selected_ids": self.budget.selected_ids,
            "levels": dict(self.budget.levels),
            "total_chars": self.budget.total_chars,
            "budget_chars": self.budget.budget_chars,
            "degraded_steps": list(self.budget.degraded_steps),
            "context_overflow": self.budget.context_overflow,
            "symbol_miss": list(self.symbol_miss),
        }
        if self.progressive is not None:
            d["progressive"] = self.progressive.to_dict()
        if self.budget_trace is not None:
            d["budget_trace"] = self.budget_trace.to_dict()
        return d


class RankingPipeline:
    """Ranking Pipeline 全链 (设计 §3 六步; 零 LLM, 失败安全)。

    Task → ① analyze_task → ② CandidateGenerator → ③ Feature Extractor →
    ④ RankingEngine → ⑤ TopKSelector → ⑥ BudgetController → 组装 AssembledContext。

    构造: root (沙箱根) + project_dir (git 历史源) + ri (可注入, None → 惰性分析) +
    analyzer (经验) + git_bin + weights (评分权重) + core_limit/related_limit
    (Top-K 名额) + task_type/budget/hard_cap (预算控制; None → 规则检测/任务类型档)
    + experience_store (T4.4 ContextExperienceStore; None → 冷启动旧路径逐位
    不变; 提供 → 真实经验接入: symbol_miss 失败史提权 / 文件级成功率 /
    预算推荐 ±20% / 阶段优先级 — 经验影响权重 ≤20% 硬限制)。
    """

    def __init__(
        self,
        root: str | Path,
        *,
        project_dir: str | Path | None = None,
        ri: Any = None,
        analyzer: Any = None,
        git_bin: str = "git",
        weights: dict[str, float] | None = None,
        core_limit: int = 3,
        related_limit: int = 5,
        task_type: str | None = None,
        budget: int | None = None,
        hard_cap: int = HARD_CAP_CHARS,
        experience_store: Any = None,
    ) -> None:
        self._root = Path(root)
        self._project_dir = Path(project_dir) if project_dir else self._root
        self._ri = ri
        self._analyzer = analyzer
        self._git_bin = git_bin
        self._weights = dict(weights) if weights else None
        self._core_limit = max(0, core_limit)
        self._related_limit = max(0, related_limit)
        self._task_type = task_type
        self._budget = budget
        self._hard_cap = hard_cap
        # T4.4: ContextExperienceStore (None → 冷启动, 旧路径逐位不变;
        # 提供 → 真实经验接入: symbol_miss 失败史提权 / 文件成功率 /
        # 预算推荐 / 阶段优先级, 全部失败安全)
        self._experience_store = experience_store

    def _experience_records(self, task_type: str) -> list[Any]:
        """ContextExperienceStore → 同类任务记录 (失败安全; 无 store → 空)。"""
        if self._experience_store is None:
            return []
        try:
            return list(
                self._experience_store.query(task_type=task_type) or []
            )
        except Exception:  # noqa: BLE001 — 经验查询失败安全 (审计增强数据)
            return []

    # ------------------------------------------------------------------ 内部

    def _intelligence(self) -> Any:
        """RepositoryIntelligence 实例 (惰性 analyze; 失败 → None — 情报不可用降级)。"""
        if self._ri is None:
            try:
                from .repo_intelligence import RepositoryIntelligence

                self._ri = RepositoryIntelligence(self._root).analyze()
            except Exception:  # noqa: BLE001 — 失败安全: 情报不可用不致命
                self._ri = None
        return self._ri

    def _detect_symbol_miss(self, profile: TaskProfile) -> list[str]:
        """任务符号候选 → 仓库未定义的符号 (symbol miss → line_range 提示源)。

        规则: 符号候选 (camelCase/snake 整词) 在全部文件定义符号集中无小写命中
        → miss。确定性启发式 (零 LLM)。
        """
        ri = self._intelligence()
        if ri is None or not profile.symbol_candidates:
            return []
        defined_anywhere: set[str] = set()
        for f in ri.index.files:
            for s in f.symbols:
                defined_anywhere.add(s.name.lower())
        return [
            s for s in profile.symbol_candidates if s.lower() not in defined_anywhere
        ]

    def _symbol_miss_files(
        self, profile: TaskProfile, batch: CandidateBatch, symbol_miss: list[str]
    ) -> set[str]:
        """与缺失符号同名的候选文件 (symbol miss 失败史提权 — experience_match +0.2)。

        启发式: 候选文件路径 basename 含缺失符号名 → 该文件是任务指向目标但
        symbol 锚点会失败的候选 — 提权 (确定性, 无逐文件经验库时诚实近似)。

        T4.4 Failure Learning: 合并持久化失败史 — 同类任务历史
        symbol_miss 失败记录的 context_used 文件集 (symbol_miss_files_from_
        experience; 经验库提供时持久化优先, 启发式兜底; 失败安全)。
        """
        out: set[str] = set()
        if symbol_miss:
            for rel in list(batch.core_files) + list(batch.related_files):
                name = Path(rel).name.lower()
                if any(m.lower() in name for m in symbol_miss):
                    out.add(rel)
        if self._experience_store is not None:
            try:
                records = self._experience_records(profile.task_type)
                persisted = symbol_miss_files_from_experience(
                    records,
                    files=list(batch.core_files) + list(batch.related_files),
                )
                out |= persisted
            except Exception:  # noqa: BLE001 — 失败学习失败安全
                pass
        return out

    def _build_feature_context(
        self,
        profile: TaskProfile,
        batch: CandidateBatch,
        symbol_miss_files: set[str],
    ) -> FeatureContext:
        """候选池 → 6 因素特征上下文 (全部从 ri 提取, 确定性)。"""
        ri = self._intelligence()
        core = set(batch.core_files)
        depends: set[str] = set()
        indirect: set[str] = set()
        if ri is not None:
            for c in core:
                for d in ri.impact_of(c):
                    depends.add(d)
            depends -= core
            for d in depends:
                for f in ri.impact_of(d):
                    indirect.add(f)
            indirect -= core
            indirect -= depends
        target_tests: set[str] = set()
        related_tests: set[str] = set()
        for src, tests in batch.test_mapping.items():
            if src in core:
                target_tests.update(tests)
            else:
                related_tests.update(tests)
        defined: dict[str, set[str]] = {}
        called: dict[str, set[str]] = {}
        caller: dict[str, set[str]] = {}
        if ri is not None:
            for f in ri.index.files:
                defined[f.path] = {s.name.lower() for s in f.symbols}
            for rel in core | set(batch.related_files):
                called[rel] = {e.callee_symbol.lower() for e in ri.call_graph.callees_of(rel)}
                caller[rel] = {e.caller_symbol.lower() for e in ri.call_graph.callers_of(rel)}
        history_rates: dict[str, float] = {}
        if batch.experience_ctx.success_rate is not None:
            history_rates["__experience__"] = batch.experience_ctx.success_rate
        # T4.4: 文件级成功率 (真实经验库 → history_success 因素; 失败安全)
        if self._experience_store is not None:
            try:
                records = self._experience_records(profile.task_type)
                if records:
                    for f, rate in file_success_rates(records).items():
                        history_rates[f] = rate
                    if "__experience__" not in history_rates:
                        ok = sum(1 for r in records if r.is_success)
                        history_rates["__experience__"] = round(ok / len(records), 3)
            except Exception:  # noqa: BLE001 — 经验聚合失败安全
                pass
        return FeatureContext(
            keywords=profile.keywords,
            symbol_candidates=profile.symbol_candidates,
            core_files=core,
            depends_on_core=depends,
            indirect=indirect,
            target_tests=target_tests,
            related_tests=related_tests,
            history_rates=history_rates,
            symbol_miss_files=symbol_miss_files,
            defined_symbols=defined,
            called_symbols=called,
            caller_symbols=caller,
        )

    def _assemble(
        self,
        task: Any,
        profile: TaskProfile,
        batch: CandidateBatch,
        budget: Any,
        symbol_miss: list[str],
    ) -> Any:
        """预算后候选 → AssembledContext (6 节; 级别 → 渲染形态, 与旧路径同语义)。"""
        from .context import (
            CORE_LINE_CAP,
            AssembledContext,
            CodeContext,
            FileSlice,
            HistoryContext,
            RequirementContext,
            TestContext,
            _file_symbol_index,
            _read_file_text,
            _render_lines,
            _symbol_blocks,
            quality_score,
        )

        ri = self._intelligence()
        cand_by_id = {c.id: c for c in batch.candidates}
        code_core: list[FileSlice] = []
        code_related: list[FileSlice] = []
        test_slices: list[FileSlice] = []
        for cid in budget.selected_ids:
            cand = cand_by_id.get(cid)
            if cand is None or cand.type not in ("code", "test"):
                continue  # 聚合候选由 batch 预渲染内容组装
            lvl = budget.levels.get(cid)
            if cand.type == "test":
                idx = _file_symbol_index(ri, cand.source) if ri is not None else ""
                test_slices.append(
                    FileSlice(rel_path=cand.source, kind="test", content=idx, symbol_index=idx)
                )
            elif lvl == LEVEL_FULL:
                lines = _read_file_text(self._root, cand.source)
                line_count = len(lines)
                if line_count <= CORE_LINE_CAP:
                    content = _render_lines("\n".join(lines)) if lines else ""
                    code_core.append(
                        FileSlice(rel_path=cand.source, kind="core",
                                  content=content, line_count=line_count)
                    )
                else:
                    # 超长文件: symbol 索引 + 命中关键词函数块 (同旧路径语义)
                    f = ri.index.find(cand.source) if ri is not None else None
                    symbols = f.symbols if f is not None else []
                    blocks = _symbol_blocks(lines, symbols, profile.keywords)
                    idx = _file_symbol_index(ri, cand.source) if ri is not None else ""
                    parts = [
                        f"// (文件 {cand.source} 共 {line_count} 行, 超过 {CORE_LINE_CAP} 行上限 —",
                        "//  以下为 symbol 索引 + 命中任务关键词的函数块; 完整文件不内联)",
                    ]
                    if idx:
                        parts.append(idx)
                    for sym, start, end in blocks[:6]:
                        block_text = "\n".join(lines[start : end + 1])
                        parts.append(f"// 关键段: {sym.kind.value} {sym.name} (行 {start + 1}-{end + 1}):")
                        parts.append(_render_lines(block_text))
                    content = "\n".join(parts)
                    code_core.append(
                        FileSlice(rel_path=cand.source, kind="core", content=content,
                                  line_count=line_count, truncated=True, symbol_index=idx)
                    )
            else:  # symbol 级 (相关文件/降级核心)
                idx = _file_symbol_index(ri, cand.source) if ri is not None else ""
                code_related.append(
                    FileSlice(rel_path=cand.source, kind="related",
                              content=idx, symbol_index=idx)
                )

        exp_ctx = batch.experience_ctx
        # symbol miss → line_range 定位提示 (设计 §7 失败兜底; 进经验建议节)
        if symbol_miss:
            names = ", ".join(symbol_miss[:3])
            exp_ctx.advice.append(
                f"任务引用符号 ({names}) 未在仓库中定义 — 定位请用 line_range "
                "(见源文件 `N|` 行号), 勿用 symbol 锚点"
            )
        if budget.context_overflow:
            exp_ctx.advice.append(
                "上下文超出预算已降级 (符号索引/摘要级) — 精确定位用 line_range, 保持最小改动"
            )

        score = quality_score(
            core_files=code_core, related_files=code_related,
            mapping=batch.test_mapping, keywords=profile.keywords,
            experience=exp_ctx,
        )
        if budget.context_overflow:
            score = round(score * 0.5, 3)  # 降级 → 质量分减半 (执行前警示)
        return AssembledContext(
            requirement=RequirementContext(
                objective=profile.objective, requirement=profile.requirement,
                task_id=profile.task_id,
            ),
            architecture=batch.arch_ctx,
            code=CodeContext(
                core_files=code_core, related_files=code_related,
                keywords=profile.keywords,
            ),
            history=HistoryContext(entries=batch.history_entries),
            test=TestContext(test_files=test_slices, mapping=batch.test_mapping),
            experience=exp_ctx,
            context_score=score,
            total_chars=budget.total_chars,
            token_estimate=budget.total_chars // 4,
        )

    # ------------------------------------------------------------------ 入口

    def _progressive_assemble(
        self,
        profile: TaskProfile,
        batch: CandidateBatch,
        budget: Any,
        symbol_miss: list[str],
    ) -> ProgressiveResult:
        """T4.2: TopK→Budget 后 → ProgressiveLoader 按阶段加载组装 (设计 §1 接入点)。

        T4.3 Budget Enforcement: 阶段配置按任务类型动态化 (Stage 1 固定 2K /
        Stage 2 动态 symbol 档 / Stage 3 剩余), loader 总硬顶 = 任务类型生效预算
        (min(任务类型预算, 硬顶)) — 渐进路径不越任务预算 (requested/actual/
        overflow/degraded 由 ProgressiveTrace 记录)。

        Developer 域 StageSpec + CodeProgressiveProvider 注入通用引擎; 引擎
        逐阶段加载并决策 (continue|stop|fallback|skip), 产出 ProgressiveResult
        (审计 Trace + finalize 后的 AssembledContext)。
        """
        provider = CodeProgressiveProvider(
            self._root, ri=self._intelligence(), profile=profile,
            batch=batch, budget=budget, symbol_miss=symbol_miss,
        )
        stages = code_progressive_stages_for(profile.task_type)
        # T4.4: 阶段优先级受经验影响 (历史成功路径优先; 失败安全 —
        # 无经验/查询异常 → 默认序逐位不变)
        if self._experience_store is not None:
            try:
                records = self._experience_records(profile.task_type)
                order = stage_order_from_experience(
                    records, [s.stage for s in stages]
                )
                if order != [s.stage for s in stages]:
                    by_name = {s.stage: s for s in stages}
                    stages = (
                        [by_name[n] for n in order if n in by_name]
                        + [s for s in stages if s.stage not in order]
                    )
            except Exception:  # noqa: BLE001 — 经验阶段序失败安全
                pass
        loader = ProgressiveLoader(
            stages=stages,
            extractor=provider.extract,
            finalizer=provider.finalize,
            hard_cap=min(budget.budget_chars, self._hard_cap),
        )
        return loader.run(task_type=profile.task_type)

    def run(
        self,
        task: Any,
        *,
        source_files: list[str] | None = None,
        task_type: str | None = None,
        progressive: bool = False,
    ) -> RankingPipelineResult:
        """Task → 全链 → RankingPipelineResult (含组装好的 AssembledContext)。

        progressive=True → T4.2 渐进加载路径: Ranking→TopK→Budget 后由
        ProgressiveLoader 按阶段加载组装 (3 阶段 + 决策 + 审计 Trace);
        渐进路径异常 → 回退本路径一次性组装 (旧行为, 不破坏执行链)。

        失败安全: 任一环节异常 → 抛出 (由调用方 context.ranking_assemble 回退旧路径;
        本方法不吞异常 — 回退决策在装配点, 保持全链可审计)。
        """
        profile = analyze_task(task, task_type=task_type or self._task_type)
        src = list(source_files) if source_files is not None else (
            list(getattr(task, "source_files", None) or [])
        )
        ri = self._intelligence()  # 先惰性初始化 — 生成器/特征提取共用同一实例
        generator = CandidateGenerator(
            self._root, ri=ri, project_dir=self._project_dir,
            analyzer=self._analyzer, git_bin=self._git_bin,
        )
        batch = generator.generate(profile, src)
        symbol_miss = self._detect_symbol_miss(profile)
        miss_files = self._symbol_miss_files(profile, batch, symbol_miss)
        fctx = self._build_feature_context(profile, batch, miss_files)
        features_map = {
            c.id: extract_candidate_features(c, profile, fctx) for c in batch.candidates
        }
        ranked = RankingEngine(self._weights).rank(batch.candidates, features_map)
        # 核心 = 距离 0/1 文件 (核心目标 ∪ 直接依赖 — TopKSelector 契约;
        # 候选 id 形式 code:<rel>, 距离 1 里的测试文件已由 test 候选覆盖)
        core_ids = {f"code:{p}" for p in batch.core_files}
        core_ids |= {f"code:{p}" for p in fctx.depends_on_core}
        selection = TopKSelector(self._core_limit, self._related_limit).select_top_k(
            ranked, core_ids=core_ids
        )
        # T4.4: 预算推荐 (历史同类任务成功记录实际用量均值; 失败安全 →
        # None → 策略预算; BudgetController 内部 clamp ±20% 硬限制)
        recommended: int | None = None
        if self._experience_store is not None:
            try:
                recommended = budget_recommendation(
                    self._experience_records(profile.task_type), profile.task_type
                )
            except Exception:  # noqa: BLE001 — 预算推荐失败安全
                recommended = None
        budget = BudgetController(
            profile.task_type, budget=self._budget, hard_cap=self._hard_cap,
            recommended_budget=recommended,
        ).apply_budget(selection, aggregates=batch.aggregates)
        prog: ProgressiveResult | None = None
        if progressive:
            try:
                prog = self._progressive_assemble(profile, batch, budget, symbol_miss)
                assembled = prog.assembled
            except Exception:  # noqa: BLE001 — 渐进失败安全: 回退一次性组装
                prog = None
                assembled = self._assemble(task, profile, batch, budget, symbol_miss)
        else:
            assembled = self._assemble(task, profile, batch, budget, symbol_miss)
        # T4.3: 预算审计 (供 Experience Learning T4.4; 两路径均记录)
        budget_trace = build_budget_trace(profile.task_type, budget, prog)
        return RankingPipelineResult(
            profile=profile,
            batch=batch,
            feature_context=fctx,
            ranked=ranked,
            selection=selection,
            budget=budget,
            assembled=assembled,
            symbol_miss=symbol_miss,
            progressive=prog,
            budget_trace=budget_trace,
        )
