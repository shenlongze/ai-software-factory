"""tests/exec/test_exec_budget.py — Context Budget Model 单元测试 (Sprint 4 T4.3)。

覆盖 (纯模型/纯函数, 零 LLM 零网络, 零 Core 依赖 — 仅 import exec.budget):
- TASK_TYPES 4 类 (bug_fix/feature/refactor/greenfield — T4.3 补 refactor)
- BudgetPolicy 模型: 校验 (extra=forbid / 非负截断 / None 归一) + 推导 (token/char
  limit 从 total_budget 自动推导) + to_dict
- BUDGET_POLICIES 声明式策略表: 4 任务类型预算档 (20K/25K/22K/15K) / stage_budget
  动态档 (bug_fix symbol 4K / greenfield 1K) / priority 取向 / degradation_order 调序
- get_budget_policy: 已知/未知/注入策略表 (Agent 通用化, 设计 §7)
- stage_budget_for / content_priority / priority_of_content_ref / order_by_priority:
  类别映射 (前缀) + 优先级排序 (大者先, 稳定保序)
- BudgetTrace 模型: 校验 / to_experience_signals (overflow/degraded/failure) / to_dict
- build_budget_trace: 一次性路径 (one_shot) / 渐进路径 (progressive) / overflow →
  degraded / unable_to_locate → failure

helper: 本文件自带 (不跨目录依赖); basename 唯一 test_exec_budget.py。
"""

from __future__ import annotations

from typing import Any

import pytest

from exec.budget import (
    BUDGET_POLICIES,
    CATEGORY_ARCHITECTURE,
    CATEGORY_DEPENDENCY,
    CATEGORY_SPEC,
    CATEGORY_SYMBOL,
    CATEGORY_TARGET,
    CATEGORY_TEST,
    DEFAULT_DEGRADATION_STEPS,
    DEFAULT_POLICY_TASK_TYPE,
    HARD_CAP_CHARS,
    PRIORITY_DEFAULT,
    TASK_TYPES,
    BudgetPolicy,
    BudgetTrace,
    build_budget_trace,
    content_category,
    content_priority,
    get_budget_policy,
    order_by_priority,
    priority_of_content_ref,
    stage_budget_for,
)

# ================================================================ helpers


class _Item:
    """order_by_priority 测试对象 (带 content_ref 的最小鸭子类型)。"""

    def __init__(self, content_ref: str) -> None:
        self.content_ref = content_ref


class _FakeBudget:
    """build_budget_trace 一次性路径用的鸭子类型 BudgetResult。"""

    def __init__(
        self,
        budget_chars: int = 10_000,
        total_chars: int = 5_000,
        context_overflow: bool = False,
        degraded_steps: list[str] | None = None,
    ) -> None:
        self.budget_chars = budget_chars
        self.total_chars = total_chars
        self.context_overflow = context_overflow
        self.degraded_steps = list(degraded_steps or [])


class _FakeTrace:
    """渐进路径 trace 鸭子类型 (ProgressiveTrace 同口径字段)。"""

    def __init__(
        self,
        requested_budget: int = 12_000,
        context_overflow: bool = False,
        degraded_steps: list[str] | None = None,
        unable_to_locate: bool = False,
        low_confidence: bool = False,
    ) -> None:
        self.requested_budget = requested_budget
        self.context_overflow = context_overflow
        self.degraded_steps = list(degraded_steps or [])
        self.unable_to_locate = unable_to_locate
        self.low_confidence = low_confidence


class _FakeProgressive:
    def __init__(self, trace: _FakeTrace, total_chars: int = 8_000) -> None:
        self.trace = trace
        self.total_chars = total_chars


# ================================================================ 1. 常量契约

class TestTaskTypesConstants:
    def test_four_task_types(self) -> None:
        """T4.3: 4 类任务类型 (补 refactor), 顺序与设计 §5 一致。"""
        assert TASK_TYPES == ("bug_fix", "feature", "refactor", "greenfield")

    def test_hard_cap_alignment(self) -> None:
        """总硬顶与 ranking.py 同值 (30K chars ≈7.5K tokens)。"""
        assert HARD_CAP_CHARS == 30_000

    def test_default_policy_is_feature(self) -> None:
        """未知任务类型回退 feature 档 (最大预算保守)。"""
        assert DEFAULT_POLICY_TASK_TYPE == "feature"

    def test_default_degradation_steps(self) -> None:
        """默认降级链 = T4.1 原序 (feature 档空策略时使用)。"""
        assert DEFAULT_DEGRADATION_STEPS == [
            "related_symbol_shrink",
            "experience_one_line",
            "architecture_one_line",
            "core_full_to_symbol",
            "drop_related",
        ]


# ================================================================ 2. BudgetPolicy 模型

class TestBudgetPolicyModel:
    def test_defaults(self) -> None:
        """缺省构造 → feature 档默认值 + 推导 limit。"""
        p = BudgetPolicy()
        assert p.task_type == "feature"
        assert p.total_budget == 25_000
        assert p.token_limit == 25_000 // 4
        assert p.char_limit == 25_000
        assert p.stage_budget == {}
        assert p.priority == {}
        assert p.degradation_order == []

    def test_derived_limits_from_total(self) -> None:
        """token/char limit 为 0 → 从 total_budget 推导 (4 chars/token 口径)。"""
        p = BudgetPolicy(task_type="x", total_budget=20_000)
        assert p.token_limit == 5_000
        assert p.char_limit == 20_000

    def test_nonneg_clamp(self) -> None:
        """负数 → 0 (数值安全); None → 缺省。"""
        p = BudgetPolicy(total_budget=-5, token_limit=None)  # type: ignore[arg-type]
        assert p.total_budget == 0
        assert p.token_limit == 1  # 推导: max(1, 0//4) — 保底 1
        assert p.char_limit == 0

    def test_extra_forbid(self) -> None:
        """extra=forbid: 拼写错误字段即失败。"""
        with pytest.raises(Exception):
            BudgetPolicy(total_budgt=100)  # type: ignore[call-arg]

    def test_stage_budget_map_normalized(self) -> None:
        """stage_budget 键转 str + 非负截断。"""
        p = BudgetPolicy(stage_budget={"overview": 2_000, "symbol": -1, 3: 500})
        assert p.stage_budget == {"overview": 2_000, "symbol": 0, "3": 500}

    def test_priority_map_normalized(self) -> None:
        """priority 键转 str + 非负截断。"""
        p = BudgetPolicy(priority={"code": 100, "arch": -3})
        assert p.priority == {"code": 100, "arch": 0}

    def test_degradation_order_list(self) -> None:
        """degradation_order 转 str 列表; None → 空 (默认链语义)。"""
        p = BudgetPolicy(degradation_order=["a", 1, None])  # type: ignore[list-item]
        assert p.degradation_order == ["a", "1", "None"]

    def test_to_dict_json(self) -> None:
        """to_dict → JSON 可序列化 dict (含推导字段)。"""
        d = BudgetPolicy(task_type="refactor", total_budget=22_000).to_dict()
        assert d["task_type"] == "refactor"
        assert d["token_limit"] == 5_500
        assert d["char_limit"] == 22_000


# ================================================================ 3. BUDGET_POLICIES 声明式表

class TestBudgetPolicies:
    def test_four_policies_declared(self) -> None:
        """策略表覆盖全部 4 任务类型。"""
        assert set(BUDGET_POLICIES) == set(TASK_TYPES)

    def test_budget_tiers(self) -> None:
        """预算档: bug_fix 20K / feature 25K / refactor 22K / greenfield 15K。"""
        assert BUDGET_POLICIES["bug_fix"].total_budget == 20_000
        assert BUDGET_POLICIES["feature"].total_budget == 25_000
        assert BUDGET_POLICIES["refactor"].total_budget == 22_000
        assert BUDGET_POLICIES["greenfield"].total_budget == 15_000

    def test_stage_budget_dynamic(self) -> None:
        """Stage 2 symbol 动态档: bug_fix 4K / feature 5K / refactor 5K / greenfield 1K。"""
        assert BUDGET_POLICIES["bug_fix"].stage_budget == {"overview": 2_000, "symbol": 4_000, "detail": 0}
        assert BUDGET_POLICIES["feature"].stage_budget["symbol"] == 5_000
        assert BUDGET_POLICIES["refactor"].stage_budget["symbol"] == 5_000
        assert BUDGET_POLICIES["greenfield"].stage_budget["symbol"] == 1_000
        # Stage 1 固定 2K (全部任务类型)
        for p in BUDGET_POLICIES.values():
            assert p.stage_budget["overview"] == 2_000
            # Stage 3 剩余 (0 = 末阶段剩余语义)
            assert p.stage_budget["detail"] == 0

    def test_priority_orientation(self) -> None:
        """各任务类型优先级取向: bug_fix 目标文件最高; refactor 依赖最高; greenfield 规格最高。"""
        assert BUDGET_POLICIES["bug_fix"].priority[CATEGORY_TARGET] > BUDGET_POLICIES["bug_fix"].priority[CATEGORY_ARCHITECTURE]
        assert BUDGET_POLICIES["refactor"].priority[CATEGORY_DEPENDENCY] > BUDGET_POLICIES["refactor"].priority[CATEGORY_ARCHITECTURE]
        assert BUDGET_POLICIES["greenfield"].priority[CATEGORY_SPEC] > BUDGET_POLICIES["greenfield"].priority[CATEGORY_DEPENDENCY]

    def test_bug_fix_degrades_architecture_first(self) -> None:
        """bug_fix 降级链: 架构摘要最先裁 (降低全局架构 — 目标文件保护最久)。"""
        order = BUDGET_POLICIES["bug_fix"].degradation_order
        assert order[0] == "architecture_one_line"
        assert order.index("core_full_to_symbol") > order.index("architecture_one_line")

    def test_feature_uses_default_chain(self) -> None:
        """feature 空 degradation_order → 默认链 (T4.1 原序)。"""
        assert BUDGET_POLICIES["feature"].degradation_order == []


# ================================================================ 4. 策略查询

class TestGetBudgetPolicy:
    def test_known_type(self) -> None:
        """已知类型 → 对应策略实例。"""
        assert get_budget_policy("bug_fix").total_budget == 20_000

    def test_unknown_type_falls_back(self) -> None:
        """未知类型 → 缺省档 (feature 保守)。"""
        p = get_budget_policy("bogus")
        assert p.task_type == "feature"

    def test_none_type_falls_back(self) -> None:
        """None → 缺省档。"""
        assert get_budget_policy(None).task_type == "feature"  # type: ignore[arg-type]

    def test_injectable_policies(self) -> None:
        """注入自定义策略表 (Agent 通用化 — 设计 §7)。"""
        custom = {"finance": BudgetPolicy(task_type="finance", total_budget=9_999)}
        assert get_budget_policy("finance", custom).total_budget == 9_999
        # 未知类型在注入表内 → 注入表缺省 (无 → 模块缺省)
        assert get_budget_policy("nope", custom).task_type == "feature"

    def test_stage_budget_for_unknown_stage(self) -> None:
        """缺省阶段 → default 值。"""
        p = get_budget_policy("bug_fix")
        assert stage_budget_for(p, "symbol") == 4_000
        assert stage_budget_for(p, "unknown") == 0
        assert stage_budget_for(p, "unknown", 777) == 777


# ================================================================ 5. 类别映射与优先级

class TestContentCategory:
    def test_prefix_mapping(self) -> None:
        """content_ref 前缀 → 类别 (审计锚点口径)。"""
        assert content_category("req:task") == CATEGORY_SPEC
        assert content_category("spec:x") == CATEGORY_SPEC
        assert content_category("arch:summary") == CATEGORY_ARCHITECTURE
        assert content_category("symbol:code:x") == CATEGORY_SYMBOL
        assert content_category("tests:mapping") == CATEGORY_TEST
        assert content_category("code:app/main.py") == CATEGORY_TARGET

    def test_unknown_ref_default(self) -> None:
        """未知前缀 → 中性 dependency 档 (不偏袒)。"""
        assert content_category("zzz:something") == CATEGORY_DEPENDENCY

    def test_none_ref_safe(self) -> None:
        """None content_ref → 中性档 (失败安全)。"""
        assert content_category(None) == CATEGORY_DEPENDENCY  # type: ignore[arg-type]


class TestPriorityOfContentRef:
    def test_priority_from_policy(self) -> None:
        """内容引用 → 任务类型策略优先级 (类别映射 + 策略表)。"""
        p = get_budget_policy("bug_fix")
        assert priority_of_content_ref("code:app/main.py", p) == p.priority[CATEGORY_TARGET]
        assert priority_of_content_ref("arch:summary", p) == p.priority[CATEGORY_ARCHITECTURE]

    def test_unknown_category_default_priority(self) -> None:
        """策略缺失类别 → 中性档 50。"""
        p = get_budget_policy("feature")  # feature priority 有 9 类, 但缺自定义类
        assert content_priority(p, "no_such_category") == PRIORITY_DEFAULT


class TestOrderByPriority:
    def test_high_priority_first(self) -> None:
        """大优先级在前 (bug_fix: 目标文件先于架构摘要; 同档稳定保原序)。"""
        items = [_Item("arch:summary"), _Item("code:app/main.py"), _Item("tree:overview")]
        out = order_by_priority(items, "bug_fix")
        assert out[0].content_ref == "code:app/main.py"
        assert out[-1].content_ref == "tree:overview"  # 与 arch 同档 40, 稳定保序

    def test_stable_for_equal_priority(self) -> None:
        """同优先级保原序 (稳定排序 — 提取器序)。"""
        items = [_Item("a:1"), _Item("a:2"), _Item("a:3")]  # 同类别 → 同优先级
        out = order_by_priority(items, "feature")
        assert [i.content_ref for i in out] == ["a:1", "a:2", "a:3"]

    def test_task_type_changes_order(self) -> None:
        """不同任务类型 → 不同排序 (refactor: 依赖 100 > call graph 95; bug_fix: 依赖 65 < call graph 70)。"""
        items = [_Item("dep:module"), _Item("graph:call")]
        bug = [i.content_ref for i in order_by_priority(items, "bug_fix")]
        ref = [i.content_ref for i in order_by_priority(items, "refactor")]
        assert bug != ref
        assert bug[0] == "graph:call"     # bug_fix: call graph 70 > dependency 65
        assert ref[0] == "dep:module"     # refactor: dependency 100 > call graph 95


# ================================================================ 6. BudgetTrace 模型

class TestBudgetTraceModel:
    def test_defaults(self) -> None:
        """缺省构造: success / one_shot / 零数值。"""
        t = BudgetTrace()
        assert t.task_type == "feature"
        assert t.success_failure == "success"
        assert t.source == "one_shot"
        assert t.planned_budget == 0 and t.requested_budget == 0
        assert t.actual_context == 0 and t.actual_usage == 0
        assert t.overflow is False
        assert t.degraded_steps == []
        assert t.token_cost == 0

    def test_nonneg_and_none_safe(self) -> None:
        """数值非负截断; None → 缺省 (失败安全)。"""
        t = BudgetTrace(planned_budget=-1, token_cost=None, overflow=None)  # type: ignore[arg-type]
        assert t.planned_budget == 0
        assert t.token_cost == 0
        assert t.overflow is False

    def test_extra_forbid(self) -> None:
        """extra=forbid: 拼写错误字段即失败。"""
        with pytest.raises(Exception):
            BudgetTrace(sucess_failure="x")  # type: ignore[call-arg]

    def test_signals_success_empty(self) -> None:
        """成功路径 → 无经验信号。"""
        assert BudgetTrace().to_experience_signals() == []

    def test_signals_overflow(self) -> None:
        """overflow → context_overflow 信号。"""
        t = BudgetTrace(overflow=True)
        assert t.to_experience_signals() == ["context_overflow"]

    def test_signals_degraded_no_overflow(self) -> None:
        """degraded 且无 overflow → budget_degraded 信号 (降级未越界也记录)。"""
        t = BudgetTrace(success_failure="degraded")
        assert t.to_experience_signals() == ["budget_degraded"]

    def test_signals_failure(self) -> None:
        """failure → budget_failure 信号。"""
        t = BudgetTrace(success_failure="failure")
        assert t.to_experience_signals() == ["budget_failure"]

    def test_to_dict_contains_signals(self) -> None:
        """to_dict 含全部审计字段 + signals。"""
        t = BudgetTrace(task_type="bug_fix", overflow=True, degraded_steps=["x"])
        d = t.to_dict()
        for key in ("task_type", "planned_budget", "requested_budget", "actual_context",
                    "actual_usage", "token_cost", "overflow", "degraded_steps",
                    "success_failure", "source", "signals"):
            assert key in d
        assert d["signals"] == ["context_overflow"]


# ================================================================ 7. build_budget_trace 装配

class TestBuildBudgetTrace:
    def test_one_shot_path(self) -> None:
        """一次性路径: source=one_shot / requested=策略阶段预算和 / actual=budget.total_chars。"""
        budget = _FakeBudget(budget_chars=20_000, total_chars=6_200)
        t = build_budget_trace("bug_fix", budget)
        assert t.task_type == "bug_fix"
        assert t.planned_budget == 20_000
        assert t.requested_budget == 6_000  # 2000+4000 (bug_fix 阶段预算和)
        assert t.actual_context == 6_200
        assert t.actual_usage == 6_200
        assert t.token_cost == 6_200 // 4
        assert t.overflow is False
        assert t.source == "one_shot"
        assert t.success_failure == "success"

    def test_one_shot_overflow_degraded(self) -> None:
        """一次性 overflow → degraded + context_overflow 信号。"""
        budget = _FakeBudget(budget_chars=100, total_chars=300, context_overflow=True,
                             degraded_steps=["architecture_one_line"])
        t = build_budget_trace("feature", budget)
        assert t.overflow is True
        assert t.success_failure == "degraded"
        assert t.degraded_steps == ["architecture_one_line"]
        assert t.to_experience_signals() == ["context_overflow"]

    def test_progressive_path(self) -> None:
        """渐进路径: source=progressive / requested=trace.requested_budget / actual=progressive.total_chars。"""
        budget = _FakeBudget(budget_chars=20_000, total_chars=1_500)
        prog = _FakeProgressive(_FakeTrace(requested_budget=18_000), total_chars=1_568)
        t = build_budget_trace("bug_fix", budget, prog)
        assert t.source == "progressive"
        assert t.planned_budget == 20_000
        assert t.requested_budget == 18_000
        assert t.actual_context == 1_568
        assert t.actual_usage == 1_568
        assert t.token_cost == 1_568 // 4
        assert t.success_failure == "success"

    def test_progressive_overflow_merges_degraded(self) -> None:
        """渐进 overflow: budget 降级链 ∪ trace 降级链 (审计合并)。"""
        budget = _FakeBudget(budget_chars=500, total_chars=600, context_overflow=True,
                             degraded_steps=["architecture_one_line"])
        prog = _FakeProgressive(
            _FakeTrace(requested_budget=500, context_overflow=True,
                       degraded_steps=["overview:token_degrade_retry", "context_overflow"]),
            total_chars=700,
        )
        t = build_budget_trace("bug_fix", budget, prog)
        assert t.overflow is True
        assert t.degraded_steps == [
            "architecture_one_line", "overview:token_degrade_retry", "context_overflow",
        ]
        assert t.success_failure == "degraded"

    def test_progressive_unable_to_locate_failure(self) -> None:
        """渐进 unable_to_locate → failure (经验信号: 定位失败)。"""
        budget = _FakeBudget(budget_chars=20_000, total_chars=500)
        prog = _FakeProgressive(
            _FakeTrace(requested_budget=2_000, unable_to_locate=True), total_chars=500
        )
        t = build_budget_trace("feature", budget, prog)
        assert t.success_failure == "failure"
        assert t.to_experience_signals() == ["budget_failure"]

    def test_progressive_low_confidence_failure(self) -> None:
        """渐进 low_confidence → failure (执行前警示)。"""
        budget = _FakeBudget(budget_chars=20_000, total_chars=800)
        prog = _FakeProgressive(_FakeTrace(low_confidence=True), total_chars=800)
        t = build_budget_trace("feature", budget, prog)
        assert t.success_failure == "failure"

    def test_injectable_policy(self) -> None:
        """注入自定义策略 → requested 按注入策略阶段预算和计算。"""
        custom = BudgetPolicy(task_type="finance", total_budget=9_999,
                              stage_budget={"a": 100, "b": 200})
        budget = _FakeBudget(budget_chars=9_999, total_chars=300)
        t = build_budget_trace("finance", budget, policy=custom)
        assert t.requested_budget == 300
        assert t.planned_budget == 9_999
