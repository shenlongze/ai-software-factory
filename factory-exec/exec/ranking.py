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
