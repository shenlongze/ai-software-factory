"""factory-exec/exec/budget.py — Context Budget Model (Sprint 4 T4.3)。

设计依据 (docs/validation/sprint4-t43-context-budget-design.md, 已批准 — 直接实现):
```text
Task → RankingEngine (T4.1) → TopKSelector → BudgetController
  → 【T4.3】Budget Model (本模块) + Dynamic Budget Policy + BudgetTrace
  → ProgressiveLoader (T4.2, 按任务类型动态预算) → Developer Agent
```

本模块 = 通用 Context Budget 模型 (Agent 无关, 零 LLM, 零 Core 依赖):
- BudgetPolicy: 声明式预算表 (total_budget / stage_budget / token_limit /
  char_limit / priority / degradation_order) — 未来 Product/Finance/Medical
  Agent 注入自己的 BUDGET_POLICIES 字典, 引擎不变 (设计 §7 通用化);
- BUDGET_POLICIES: 4 任务类型 (bug_fix|feature|refactor|greenfield) 声明式配置
  — refactor 为 T4.3 新增 (T4.1 只有 3 类);
- Dynamic Budget Policy: 任务类型 → 内容优先级 (影响 Stage 2/3 候选加载顺序) +
  降级链调序 (设计 §5: Detail→Symbol→Summary 按任务类型调序);
- BudgetTrace: 审计 (task_type / planned_budget / requested_budget /
  actual_context / actual_usage / token_cost / overflow / degraded_steps /
  success_failure) + to_experience_signals (供 Experience Learning T4.4)。

KISS 边界: 本模块独立可 import (只依赖 pydantic — 无环); ranking.py 单向依赖
本模块 (预算常量/策略的声明式来源); 字符口径同 ranking.py (4 chars/token)。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

# ================================================================ 常量

#: 任务类型 (设计 §5: T4.3 补 refactor → 4 类)
TASK_TYPES: tuple[str, ...] = ("bug_fix", "feature", "refactor", "greenfield")

#: 缺省策略键 (未知任务类型回退; 取最大预算档保守)
DEFAULT_POLICY_TASK_TYPE = "feature"

#: 总硬顶 (设计 §4: 总 ≤30K chars ≈7.5K tokens; 与 ranking.py HARD_CAP_CHARS 同值)
HARD_CAP_CHARS = 30_000

#: 内容类别 (priority 映射键; 未来 Agent 可配自己的类别集)
CATEGORY_SPEC = "spec"                # 需求/规格/模板
CATEGORY_ARCHITECTURE = "architecture"  # 全局架构/模块树
CATEGORY_TARGET = "target"            # 目标文件/核心代码
CATEGORY_SYMBOL = "symbol"            # 符号索引/锚点
CATEGORY_CALL_GRAPH = "call_graph"    # call graph / 影响面
CATEGORY_DEPENDENCY = "dependency"    # 依赖关系
CATEGORY_TEST = "test"                # 测试
CATEGORY_HISTORY = "history"          # 变更历史
CATEGORY_EXPERIENCE = "experience"    # 经验/教训

#: 未知类别默认优先级 (中性 — 不偏袒)
PRIORITY_DEFAULT = 50

#: 默认降级链顺序 (T4.1 设计 §6; T4.3 声明式: 任务类型策略可调序)
DEFAULT_DEGRADATION_STEPS: list[str] = [
    "related_symbol_shrink",
    "experience_one_line",
    "architecture_one_line",
    "core_full_to_symbol",
    "drop_related",
]

#: 内容引用前缀 → 类别 (content_ref 审计锚点; 与 CodeProgressiveProvider 载荷对齐)
_PREFIX_CATEGORY: tuple[tuple[str, str], ...] = (
    ("req:", CATEGORY_SPEC),
    ("spec:", CATEGORY_SPEC),
    ("template:", CATEGORY_SPEC),
    ("arch:", CATEGORY_ARCHITECTURE),
    ("tree:", CATEGORY_ARCHITECTURE),
    ("code:", CATEGORY_TARGET),
    ("symbol:", CATEGORY_SYMBOL),
    ("hint:", CATEGORY_SYMBOL),
    ("graph:", CATEGORY_CALL_GRAPH),
    ("dep:", CATEGORY_DEPENDENCY),
    ("tests:", CATEGORY_TEST),
    ("test:", CATEGORY_TEST),
    ("history:", CATEGORY_HISTORY),
    ("exp:", CATEGORY_EXPERIENCE),
)


def content_category(content_ref: str) -> str:
    """内容引用 → 类别 (前缀匹配; 未知 → dependency 中性档)。"""
    ref = str(content_ref)
    for prefix, cat in _PREFIX_CATEGORY:
        if ref.startswith(prefix):
            return cat
    return CATEGORY_DEPENDENCY


def _nonneg_int(v: Any, default: int = 0) -> int:
    try:
        return max(0, int(v))
    except (TypeError, ValueError):
        return default


# ================================================================ BudgetPolicy (声明式预算表)

class BudgetPolicy(BaseModel):
    """任务类型预算表 (声明式配置 — Agent 通用, 不绑定 Developer; 设计 §5/§7)。

    - task_type: 任务类型标识 (标准 4 类; 未来 Agent 可配自定义类型);
    - total_budget: 总预算 (chars; 生效预算 = min(total_budget, HARD_CAP_CHARS));
    - stage_budget: 阶段 → 预算 (chars; 0 = 末阶段剩余预算语义; 缺省阶段 0);
    - token_limit: token 上限 (0 → total_budget // 4 自动推导);
    - char_limit: char 上限 (0 → total_budget 自动推导);
    - priority: 内容类别 → 优先级 (大者先加载/后截断 — Stage 2/3 内容选择);
    - degradation_order: 降级链顺序 (超预算时按此序降级; 空 → 默认链)。

    校验: 数值非负; extra=forbid (拼写错误即失败); 推导字段自动填充。
    """

    model_config = {"extra": "forbid"}

    task_type: str = DEFAULT_POLICY_TASK_TYPE
    total_budget: int = 25_000
    stage_budget: dict[str, int] = Field(default_factory=dict)
    token_limit: int = 0
    char_limit: int = 0
    priority: dict[str, int] = Field(default_factory=dict)
    degradation_order: list[str] = Field(default_factory=list)

    @field_validator("task_type", mode="before")
    @classmethod
    def _type_none(cls, v: Any) -> str:
        return str(v) if v is not None else DEFAULT_POLICY_TASK_TYPE

    @field_validator("total_budget", "token_limit", "char_limit", mode="before")
    @classmethod
    def _budget_nonneg(cls, v: Any) -> int:
        return _nonneg_int(v)

    @field_validator("stage_budget", mode="before")
    @classmethod
    def _stage_map(cls, v: Any) -> dict[str, int]:
        if v is None:
            return {}
        return {str(k): _nonneg_int(x) for k, x in v.items()}

    @field_validator("priority", mode="before")
    @classmethod
    def _priority_map(cls, v: Any) -> dict[str, int]:
        if v is None:
            return {}
        return {str(k): _nonneg_int(x) for k, x in v.items()}

    @field_validator("degradation_order", mode="before")
    @classmethod
    def _order_list(cls, v: Any) -> list[str]:
        return [str(x) for x in v] if v is not None else []

    @model_validator(mode="after")
    def _derive_limits(self) -> "BudgetPolicy":
        """推导字段: token_limit/char_limit 为 0 → 从 total_budget 推导。"""
        if self.token_limit <= 0:
            self.token_limit = max(1, self.total_budget // 4)
        if self.char_limit <= 0:
            self.char_limit = self.total_budget
        return self

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


# ================================================================ BUDGET_POLICIES (声明式策略表)

#: 任务类型 → 预算表 + 优先级 (设计 §5; 声明式单一事实源 — TASK_TYPE_BUDGETS 派生)。
#: 优先级影响 Stage 2/3 候选加载顺序 (大者先加载/后截断) — 各任务类型的语义取向:
#: - bug_fix:   优先 目标文件/Symbol/Test; 降低 全局架构 (先裁架构摘要);
#: - feature:   优先 Architecture/Module/Pattern/Tests;
#: - refactor:  优先 Dependency/Impact Map/Call Graph;
#: - greenfield:优先 Specification/Template/Architecture。
BUDGET_POLICIES: dict[str, BudgetPolicy] = {
    "bug_fix": BudgetPolicy(
        task_type="bug_fix",
        total_budget=20_000,
        stage_budget={"overview": 2_000, "symbol": 4_000, "detail": 0},
        priority={
            CATEGORY_TARGET: 100,
            CATEGORY_SYMBOL: 90,
            CATEGORY_TEST: 85,
            CATEGORY_CALL_GRAPH: 70,
            CATEGORY_DEPENDENCY: 65,
            CATEGORY_HISTORY: 60,
            CATEGORY_EXPERIENCE: 55,
            CATEGORY_SPEC: 50,
            CATEGORY_ARCHITECTURE: 40,
        },
        degradation_order=[
            "architecture_one_line",
            "related_symbol_shrink",
            "experience_one_line",
            "core_full_to_symbol",
            "drop_related",
        ],
    ),
    "feature": BudgetPolicy(
        task_type="feature",
        total_budget=25_000,
        stage_budget={"overview": 2_000, "symbol": 5_000, "detail": 0},
        priority={
            CATEGORY_ARCHITECTURE: 90,
            CATEGORY_TEST: 85,
            CATEGORY_SPEC: 80,
            CATEGORY_TARGET: 75,
            CATEGORY_SYMBOL: 70,
            CATEGORY_CALL_GRAPH: 60,
            CATEGORY_DEPENDENCY: 55,
            CATEGORY_HISTORY: 50,
            CATEGORY_EXPERIENCE: 45,
        },
        degradation_order=[],  # 空 → 默认降级链 (T4.1 原序)
    ),
    "refactor": BudgetPolicy(
        task_type="refactor",
        total_budget=22_000,
        stage_budget={"overview": 2_000, "symbol": 5_000, "detail": 0},
        priority={
            CATEGORY_DEPENDENCY: 100,
            CATEGORY_CALL_GRAPH: 95,
            CATEGORY_TARGET: 85,
            CATEGORY_SYMBOL: 80,
            CATEGORY_TEST: 75,
            CATEGORY_ARCHITECTURE: 65,
            CATEGORY_SPEC: 60,
            CATEGORY_HISTORY: 50,
            CATEGORY_EXPERIENCE: 45,
        },
        degradation_order=[],  # 默认链: 核心 full 保护最久 (重构需完整代码上下文)
    ),
    "greenfield": BudgetPolicy(
        task_type="greenfield",
        total_budget=15_000,
        stage_budget={"overview": 2_000, "symbol": 1_000, "detail": 0},
        priority={
            CATEGORY_SPEC: 100,
            CATEGORY_ARCHITECTURE: 90,
            CATEGORY_TARGET: 70,
            CATEGORY_SYMBOL: 60,
            CATEGORY_TEST: 55,
            CATEGORY_HISTORY: 50,
            CATEGORY_EXPERIENCE: 45,
            CATEGORY_DEPENDENCY: 40,
            CATEGORY_CALL_GRAPH: 35,
        },
        degradation_order=[
            "experience_one_line",
            "related_symbol_shrink",
            "architecture_one_line",
            "core_full_to_symbol",
            "drop_related",
        ],
    ),
}


def get_budget_policy(
    task_type: str,
    policies: dict[str, BudgetPolicy] | None = None,
) -> BudgetPolicy:
    """任务类型 → 预算策略 (声明式注入点 — Agent 通用化, 设计 §7)。

    policies: 可注入策略表 (未来 Agent 配自己的 BUDGET_POLICIES 字典, 本函数
    不变); None → 模块级 BUDGET_POLICIES。未知类型 → 缺省档 (feature)。
    """
    table = dict(policies) if policies is not None else BUDGET_POLICIES
    t = str(task_type)
    return table.get(t) or table.get(DEFAULT_POLICY_TASK_TYPE) or BudgetPolicy()


def stage_budget_for(policy: BudgetPolicy, stage: str, default: int = 0) -> int:
    """策略 → 阶段预算 (chars; 缺省阶段 → default; 0 = 末阶段剩余语义)。"""
    return _nonneg_int(policy.stage_budget.get(str(stage), default))


def content_priority(policy: BudgetPolicy, category: str) -> int:
    """策略 → 类别优先级 (缺省类别 → 中性档 PRIORITY_DEFAULT)。"""
    return _nonneg_int(policy.priority.get(str(category), PRIORITY_DEFAULT))


def priority_of_content_ref(content_ref: str, policy: BudgetPolicy) -> int:
    """内容引用 → 优先级 (类别映射 + 策略表; 确定性启发式)。"""
    return content_priority(policy, content_category(content_ref))


def order_by_priority(
    items: list[Any],
    task_type: str,
    policies: dict[str, BudgetPolicy] | None = None,
) -> list[Any]:
    """内容项按任务类型优先级排序 (稳定; 同优先级保原序 — 提取器序)。

    items: 任意带 content_ref 属性的对象 (LoadedItem / 候选); 大优先级在前,
    影响 Stage 2/3 内容选择与截断存活 (apply_stage_budget 丢尾项)。
    """
    policy = get_budget_policy(task_type, policies)
    return sorted(
        items,
        key=lambda it: -priority_of_content_ref(getattr(it, "content_ref", ""), policy),
    )


# ================================================================ BudgetTrace (审计)

class BudgetTrace(BaseModel):
    """上下文预算审计 (设计 §6; 供 Experience Learning T4.4)。

    记录 (Budget Enforcement 口径):
    - task_type: 生效任务类型;
    - planned_budget: 计划预算 (chars; 生效预算 = min(任务类型预算, 硬顶));
    - requested_budget: 申请预算 (chars; 渐进路径 = 各阶段分配和; 一次性 = 计划);
    - actual_context / actual_usage: 实际上下文消耗 (chars; 同值, 双口径);
    - token_cost: 实际 token 估算 (4 chars/token);
    - overflow: 超预算标记 (降级链/截断后仍超 — 执行前警示);
    - degraded_steps: 降级链每步记录 (审计);
    - success_failure: success|degraded|failure (经验信号输入);
    - source: 来源 (progressive|one_shot)。

    失败信号: to_experience_signals() 与 ProgressiveTrace 同语义 (成功 → 空)。
    """

    model_config = {"extra": "forbid"}

    task_type: str = DEFAULT_POLICY_TASK_TYPE
    planned_budget: int = 0
    requested_budget: int = 0
    actual_context: int = 0
    actual_usage: int = 0
    token_cost: int = 0
    overflow: bool = False
    degraded_steps: list[str] = Field(default_factory=list)
    success_failure: str = "success"
    source: str = "one_shot"

    @field_validator(
        "task_type", "success_failure", "source", mode="before"
    )
    @classmethod
    def _strs_none(cls, v: Any) -> str:
        return str(v) if v is not None else ""

    @field_validator(
        "planned_budget", "requested_budget", "actual_context",
        "actual_usage", "token_cost", mode="before"
    )
    @classmethod
    def _ints_nonneg(cls, v: Any) -> int:
        return _nonneg_int(v)

    @field_validator("overflow", mode="before")
    @classmethod
    def _bool_none(cls, v: Any) -> bool:
        return bool(v) if v is not None else False

    @field_validator("degraded_steps", mode="before")
    @classmethod
    def _steps_list(cls, v: Any) -> list[str]:
        return [str(x) for x in v] if v is not None else []

    def to_experience_signals(self) -> list[str]:
        """失败模式信号 (供 Experience Learning; 成功路径 → 空列表)。"""
        signals: list[str] = []
        if self.overflow:
            signals.append("context_overflow")
        if self.success_failure == "degraded" and not self.overflow:
            signals.append("budget_degraded")
        if self.success_failure == "failure":
            signals.append("budget_failure")
        return signals

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "planned_budget": self.planned_budget,
            "requested_budget": self.requested_budget,
            "actual_context": self.actual_context,
            "actual_usage": self.actual_usage,
            "token_cost": self.token_cost,
            "overflow": self.overflow,
            "degraded_steps": list(self.degraded_steps),
            "success_failure": self.success_failure,
            "source": self.source,
            "signals": self.to_experience_signals(),
        }


def build_budget_trace(
    task_type: str,
    budget: Any,
    progressive: Any = None,
    policy: BudgetPolicy | None = None,
) -> BudgetTrace:
    """预算产物 → BudgetTrace (装配点纯函数; budget = BudgetController 结果,
    progressive = ProgressiveResult 或 None — 一次性路径)。

    语义:
    - planned_budget = budget.budget_chars (生效预算);
    - requested_budget = 渐进路径取 trace.requested_budget (实际分配和),
      一次性路径取策略阶段预算和 (声明式申请);
    - actual = 渐进路径取 trace.total_chars (真实渲染), 一次性取 budget.total_chars;
    - overflow = 渐进路径取 trace.context_overflow, 一次性取 budget.context_overflow;
    - degraded_steps = budget.degraded_steps ∪ progressive.trace.degraded_steps;
    - success_failure: overflow → degraded; 无法定位/低置信 → failure; 其余 success。
    """
    pol = policy if policy is not None else get_budget_policy(task_type)
    planned = _nonneg_int(getattr(budget, "budget_chars", 0))
    if progressive is not None:
        trace = getattr(progressive, "trace", None)
        requested = _nonneg_int(getattr(trace, "requested_budget", 0)) if trace is not None else 0
        actual = _nonneg_int(getattr(progressive, "total_chars", 0))
        overflow = bool(getattr(trace, "context_overflow", False)) if trace is not None else False
        degraded: list[str] = list(getattr(budget, "degraded_steps", []) or [])
        if trace is not None:
            degraded += list(getattr(trace, "degraded_steps", []) or [])
        source = "progressive"
        unable = bool(getattr(trace, "unable_to_locate", False)) if trace is not None else False
        low_conf = bool(getattr(trace, "low_confidence", False)) if trace is not None else False
    else:
        requested = sum(pol.stage_budget.values())
        actual = _nonneg_int(getattr(budget, "total_chars", 0))
        overflow = bool(getattr(budget, "context_overflow", False))
        degraded = list(getattr(budget, "degraded_steps", []) or [])
        source = "one_shot"
        unable = False
        low_conf = False
    if overflow:
        success_failure = "degraded"
    elif unable or low_conf:
        success_failure = "failure"
    else:
        success_failure = "success"
    return BudgetTrace(
        task_type=str(task_type),
        planned_budget=planned,
        requested_budget=requested,
        actual_context=actual,
        actual_usage=actual,
        token_cost=actual // 4,
        overflow=overflow,
        degraded_steps=degraded,
        success_failure=success_failure,
        source=source,
    )
