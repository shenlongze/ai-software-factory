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
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ================================================================ 常量

#: 6 因素权重 (设计 §4; 和恒为 1.0 — 全满分 → 1.0)
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

#: 任务类型 (设计 §5: Bug Fix 20K / Feature 25K / Greenfield 15K chars)
TASK_TYPES: tuple[str, ...] = ("bug_fix", "feature", "greenfield")

#: 任务类型 → 预算 (字符数)
TASK_TYPE_BUDGETS: dict[str, int] = {
    "bug_fix": 20_000,
    "feature": 25_000,
    "greenfield": 15_000,
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
#: greenfield 类型触发词 (中英; 命中任一 → greenfield; bug_fix 优先判定)
_GREENFIELD_MARKERS = (
    "create", "new", "scaffold", "generate", "from scratch", "init", "setup",
    "新建", "创建", "从零", "生成", "搭建", "初始化", "脚手架", "首个版本",
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
    """任务文本 → 类型 (规则检测, 零 LLM; bug_fix > greenfield > feature)。

    判定顺序 (设计 §5 预算依据):
    1. bug_fix: 命中修复/错误/崩溃/异常类触发词 (缺陷修复语义优先 — 预算最小);
    2. greenfield: 命中新建/创建/从零类触发词 (从零构建 — 预算中档);
    3. 其余 → feature (默认 — 预算最大)。
    """
    text = f"{objective} {requirement}".lower()
    if any(m in text for m in _BUG_FIX_MARKERS):
        return "bug_fix"
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
