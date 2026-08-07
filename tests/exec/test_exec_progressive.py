"""tests/exec/test_exec_progressive.py — Progressive Loading Engine 单元测试 (Sprint 4 T4.2 子任务 1)。

覆盖 (纯引擎, 零 LLM 零网络; fake extractor 注入):
- StageSpec 声明式配置校验 (预算非负/extra=forbid/缺省)
- Stage 决策纯函数 (decide_next_stage): 末阶段/预算耗尽/回退上限/validation 回退/
  候选未定位/missing info 扩 1 轮/扩展上限/锚点未定/greenfield 跳阶段/全深度任务/
  低置信/高置信停止/自定义策略 (Agent 通用化)
- 预算分级 (stage_budget): 固定档/剩余档/硬顶截断
- 阶段预算应用 (apply_stage_budget): 不超预算无操作/截断锚点核心/keep 锚点不裁/
  overflow 诚实标记/零预算
- ProgressiveTrace 审计: 条目字段 (stage/loaded_items/reason/token_cost/decision/
  final_usage) + 失败信号 (to_experience_signals) + to_dict
- ProgressiveLoader 主循环: 3 阶段全链/预算尊重/高置信早停/missing info 扩轮/
  Stage 1 无法定位自动扩 1 轮/overflow 降级重试 1 次/validation 回退重载/
  扩展计数上限/总预算硬顶/finalizer 调用

helper: 本文件自带 (不跨目录依赖); basename 唯一 test_exec_progressive.py。
"""

from __future__ import annotations

from typing import Any

import pytest

from exec.progressive import (
    CONFIDENCE_THRESHOLD,
    DECISION_CONTINUE,
    DECISION_FALLBACK,
    DECISION_SKIP,
    DECISION_STOP,
    MAX_EXTENSION_ROUNDS,
    MAX_FALLBACK_PER_STAGE,
    PROGRESSIVE_HARD_CAP_CHARS,
    STAGE_1_BUDGET_CHARS,
    STAGE_2_BUDGET_CHARS,
    LoadedItem,
    ProgressiveLoader,
    ProgressiveResult,
    ProgressiveTrace,
    ProgressiveTraceEntry,
    StageDecision,
    StageDecisionInput,
    StageDecisionPolicy,
    StageLoadResult,
    StageSpec,
    apply_stage_budget,
    decide_next_stage,
    render_items,
    stage_budget,
)

# ================================================================ helpers

CODE_STAGES: list[StageSpec] = [
    StageSpec(stage="overview", label="Overview", max_chars=STAGE_1_BUDGET_CHARS,
              extractor="overview", required=True),
    StageSpec(stage="symbol", label="Symbol", max_chars=STAGE_2_BUDGET_CHARS, extractor="symbol"),
    StageSpec(stage="detail", label="Detail", max_chars=0, extractor="detail"),
]


def _item(ref: str = "ref:1", content: str = "x" * 50, **kw: Any) -> LoadedItem:
    return LoadedItem(content_ref=ref, content=content, **kw)


def _decision_input(**over: Any) -> StageDecisionInput:
    base: dict[str, Any] = dict(
        stage_index=0,
        num_stages=3,
        stage_names=("overview", "symbol", "detail"),
        stage="overview",
        task_type="feature",
        confidence=0.5,
        candidates_found=True,
        anchor_found=True,
        missing_info=False,
        extension_count=0,
        fallback_count=0,
        budget_exhausted=False,
        validation_failed=False,
    )
    base.update(over)
    return StageDecisionInput(**base)


class _FakeExtractor:
    """可编程提取器: plan 阶段 → StageLoadResult; 记录调用 (stage, widen, degrade)。"""

    def __init__(self, plan: dict[str, StageLoadResult] | None = None) -> None:
        self._plan = dict(plan or {})
        self.calls: list[tuple[str, bool, bool]] = []

    def __call__(self, spec: StageSpec, *, widen: bool = False, degrade: bool = False) -> StageLoadResult:
        self.calls.append((spec.stage, widen, degrade))
        return self._plan.get(
            spec.stage,
            StageLoadResult(items=[_item(f"{spec.stage}:1")], confidence=0.5),
        )


def _run_loader(
    extractor: _FakeExtractor,
    *,
    task_type: str = "feature",
    validation_failed: bool = False,
    hard_cap: int = PROGRESSIVE_HARD_CAP_CHARS,
    finalizer: Any = None,
    policy: StageDecisionPolicy | None = None,
) -> ProgressiveResult:
    loader = ProgressiveLoader(
        stages=CODE_STAGES, extractor=extractor,
        policy=policy, finalizer=finalizer, hard_cap=hard_cap,
    )
    return loader.run(task_type=task_type, validation_failed=validation_failed)


# ================================================================ 1. StageSpec

class TestStageSpec:
    def test_defaults_and_validation(self) -> None:
        """max_chars 非负截断; required 缺省 False; extra=forbid。"""
        spec = StageSpec(stage="overview", max_chars=-5, extractor="overview")
        assert spec.max_chars == 0
        assert spec.required is False
        assert spec.label == ""
        with pytest.raises(Exception):
            StageSpec(stage="x", max_chars=10, extractor="x", unknown_field=1)  # type: ignore[call-arg]

    def test_required_flag(self) -> None:
        """required=True 显式标记必载阶段 (Stage 1 语义)。"""
        spec = StageSpec(stage="overview", max_chars=2000, extractor="overview", required=True)
        assert spec.required is True
        assert spec.extractor == "overview"


# ================================================================ 2. Stage 决策纯函数

class TestDecideNextStage:
    def test_final_stage_stop(self) -> None:
        """R0: 末阶段 → stop(final_stage) (无后续可加载)。"""
        d = decide_next_stage(_decision_input(stage_index=2, stage="detail"))
        assert d.decision == DECISION_STOP
        assert d.reason == "final_stage"

    def test_budget_exhausted_stop(self) -> None:
        """R1: 预算耗尽 → stop(budget_exhausted) (不再深入)。"""
        d = decide_next_stage(_decision_input(budget_exhausted=True))
        assert d.decision == DECISION_STOP
        assert d.reason == "budget_exhausted"

    def test_fallback_limit_stop(self) -> None:
        """R2: 本阶段回退超限 (≥1) → stop(fallback_limit)。"""
        d = decide_next_stage(_decision_input(fallback_count=MAX_FALLBACK_PER_STAGE))
        assert d.decision == DECISION_STOP
        assert d.reason == "fallback_limit"

    def test_validation_feedback_fallback(self) -> None:
        """R3: validation 失败 → fallback 到上一阶段 (Stage 3 → Stage 2 重新定位)。"""
        d = decide_next_stage(_decision_input(stage_index=2, stage="detail", validation_failed=True))
        assert d.decision == DECISION_FALLBACK
        assert d.reason == "validation_feedback"
        assert d.target_stage == "symbol"

    def test_first_stage_no_candidates_unable_to_locate(self) -> None:
        """R4: 首阶段候选未定位 → stop(unable_to_locate)。"""
        d = decide_next_stage(_decision_input(stage_index=0, candidates_found=False))
        assert d.decision == DECISION_STOP
        assert d.reason == "unable_to_locate"

    def test_missing_info_widen_extend(self) -> None:
        """R5: missing info → continue + extend (扩 1 轮)。"""
        d = decide_next_stage(_decision_input(stage_index=1, stage="symbol", missing_info=True))
        assert d.decision == DECISION_CONTINUE
        assert d.reason == "missing_info_widen"
        assert d.extend is True

    def test_missing_info_extension_limit(self) -> None:
        """R5 上限: 扩展计数 ≥3 → stop(extension_limit)。"""
        d = decide_next_stage(
            _decision_input(stage_index=1, stage="symbol", missing_info=True,
                            extension_count=MAX_EXTENSION_ROUNDS)
        )
        assert d.decision == DECISION_STOP
        assert d.reason == "extension_limit"

    def test_anchor_stage_no_anchor_stop(self) -> None:
        """R6: 锚点阶段 (第二阶段) 锚点未定 → stop(anchor_unresolved)。"""
        d = decide_next_stage(_decision_input(stage_index=1, stage="symbol", anchor_found=False))
        assert d.decision == DECISION_STOP
        assert d.reason == "anchor_unresolved"

    def test_greenfield_skip_stage(self) -> None:
        """R7: greenfield → skip 到 detail (Stage 1+3, 规范+骨架; 设计 §3 ②)。"""
        d = decide_next_stage(_decision_input(stage_index=0, task_type="greenfield"))
        assert d.decision == DECISION_SKIP
        assert d.next_stage == "detail"

    def test_full_depth_task_types_continue(self) -> None:
        """R8: bug_fix/feature 全深度 → continue 到下一阶段 (需完整执行上下文)。"""
        for t in ("bug_fix", "feature"):
            d = decide_next_stage(_decision_input(stage_index=1, stage="symbol", task_type=t))
            assert d.decision == DECISION_CONTINUE
            assert d.reason == f"{t}_needs_code"

    def test_low_confidence_continue(self) -> None:
        """R9: 低置信 (<0.6) → continue 下一阶段 (需要更多信息; 设计 §3 ①)。"""
        d = decide_next_stage(_decision_input(task_type="analysis", confidence=0.3))
        assert d.decision == DECISION_CONTINUE
        assert d.reason == "low_confidence"

    def test_sufficient_confidence_stop(self) -> None:
        """R10: 高置信 + 非全深度类型 → stop(sufficient_confidence)。"""
        d = decide_next_stage(_decision_input(task_type="analysis", confidence=0.9))
        assert d.decision == DECISION_STOP
        assert d.reason == "sufficient_confidence"

    def test_custom_policy_generic_agent(self) -> None:
        """通用化: 自定义 full_depth/skip 映射 → 引擎规则按配置生效 (Finance Agent 语义)。"""
        policy = StageDecisionPolicy(
            full_depth_task_types=frozenset({"finance_report"}),
            skip_stage_map={},
        )
        d = policy.decide(_decision_input(task_type="finance_report", confidence=0.9))
        assert d.decision == DECISION_CONTINUE  # 全深度类型强制继续
        d2 = policy.decide(_decision_input(task_type="marketing", confidence=0.9))
        assert d2.decision == DECISION_STOP  # 非全深度 + 高置信 → 早停

    def test_threshold_configurable(self) -> None:
        """置信度阈值可注入 (StageDecisionPolicy 构造)。"""
        policy = StageDecisionPolicy(confidence_threshold=0.8)
        d = policy.decide(_decision_input(task_type="analysis", confidence=0.7))
        assert d.decision == DECISION_CONTINUE
        assert d.reason == "low_confidence"


# ================================================================ 3. 预算分级

class TestStageBudget:
    def test_fixed_stage_budget(self) -> None:
        """固定档: 取 min(阶段上限, 剩余)。"""
        spec = StageSpec(stage="overview", max_chars=2000, extractor="overview")
        assert stage_budget(spec, used=0) == 2000
        assert stage_budget(spec, used=29000) == 1000  # 剩余不足 → 取剩余
        assert stage_budget(spec, used=1500) == 2000  # 剩余充足 → 固定档

    def test_remaining_budget_last_stage(self) -> None:
        """剩余档 (max_chars=0): 末阶段用剩余预算。"""
        spec = StageSpec(stage="detail", max_chars=0, extractor="detail")
        assert stage_budget(spec, used=7000) == PROGRESSIVE_HARD_CAP_CHARS - 7000
        assert stage_budget(spec, used=PROGRESSIVE_HARD_CAP_CHARS) == 0

    def test_hard_cap_clamp(self) -> None:
        """硬顶: 自定义 hard_cap 参与截断。"""
        spec = StageSpec(stage="symbol", max_chars=5000, extractor="symbol")
        assert stage_budget(spec, used=0, hard_cap=3000) == 3000  # min(5000, 3000)


# ================================================================ 4. 阶段预算应用

class TestApplyStageBudget:
    def test_under_budget_noop(self) -> None:
        """不超预算 → 原样返回, 无 overflow。"""
        items = [_item("a", "x" * 50), _item("b", "y" * 50)]
        final, overflow = apply_stage_budget(items, budget=200)
        assert overflow is False
        assert len(final) == 2
        assert final[0].content == "x" * 50

    def test_truncate_to_anchor_core(self) -> None:
        """超限 → 截断至锚点核心 (保 head + 截断标记)。"""
        items = [_item("big", "A" * 1000)]
        final, overflow = apply_stage_budget(items, budget=100)
        assert len(final) == 1
        assert "AAA" in final[0].content
        assert "截断" in final[0].content
        assert final[0].chars <= 100

    def test_keep_items_not_truncated(self) -> None:
        """keep 锚点 (任务需求) 不截断; 其余项截断。"""
        items = [_item("req", "R" * 80, keep=True), _item("arch", "A" * 500)]
        final, overflow = apply_stage_budget(items, budget=100)
        assert final[0].content == "R" * 80  # keep 完整保留
        assert final[1].chars <= 100 - 80

    def test_overflow_flag_when_still_over(self) -> None:
        """截断后仍超 (锚点核心无法容纳) → overflow=True (保留最大可用, 诚实标记)。"""
        items = [_item("huge", "H" * 5000)]
        final, overflow = apply_stage_budget(items, budget=5)
        assert overflow is True
        assert final  # 不静默丢弃全部
        assert "截断" in final[0].content  # 截断标记为证据

    def test_zero_budget(self) -> None:
        """零预算 → 空加载 + overflow。"""
        final, overflow = apply_stage_budget([_item("a", "x")], budget=0)
        assert final == []
        assert overflow is True


# ================================================================ 5. ProgressiveTrace 审计

class TestProgressiveTrace:
    def test_entry_audit_fields(self) -> None:
        """条目字段完整 (stage/loaded_items/reason/token_cost/decision/final_usage)。"""
        entry = ProgressiveTraceEntry(
            stage="symbol",
            loaded_items=["symbol:code:a.py", "graph:call"],
            reason="bug_fix_needs_code",
            token_cost=1234,
            decision=DECISION_CONTINUE,
            decision_reason="bug_fix_needs_code",
            final_usage={"before": 2000, "after": 3234},
        )
        d = entry.model_dump(mode="json")
        assert d["stage"] == "symbol"
        assert d["loaded_items"] == ["symbol:code:a.py", "graph:call"]
        assert d["reason"] == "bug_fix_needs_code"
        assert d["token_cost"] == 1234
        assert d["decision"] == "continue"
        assert d["decision_reason"] == "bug_fix_needs_code"
        assert d["final_usage"] == {"before": 2000, "after": 3234}

    def test_to_experience_signals(self) -> None:
        """失败信号: 标志 → 信号列表 (经验学习输入; 成功路径空列表)。"""
        trace = ProgressiveTrace()
        assert trace.to_experience_signals() == []
        trace.unable_to_locate = True
        trace.symbol_miss = ["my_widget"]
        trace.large_file = ["huge.dart"]
        trace.context_overflow = True
        trace.low_confidence = True
        signals = trace.to_experience_signals()
        assert "unable_to_locate" in signals
        assert "symbol_miss:my_widget" in signals
        assert "large_file:huge.dart" in signals
        assert "context_overflow" in signals
        assert "low_confidence" in signals

    def test_trace_to_dict_auditable(self) -> None:
        """to_dict 全量可审计 (条目 + 汇总 + 信号)。"""
        trace = ProgressiveTrace()
        trace.add_load_meta(StageLoadResult(items=[], symbol_miss=["s1"], warnings=["w1"]))
        trace.entries.append(ProgressiveTraceEntry(stage="overview", loaded_items=["req:task"],
                                                   reason="initial", token_cost=100,
                                                   decision=DECISION_CONTINUE))
        trace.total_chars = 100
        d = trace.to_dict()
        assert d["symbol_miss"] == ["s1"]
        assert d["warnings"] == ["w1"]
        assert d["entries"][0]["stage"] == "overview"
        assert "signals" in d


# ================================================================ 6. ProgressiveLoader 主循环

class TestProgressiveLoaderLoop:
    def test_full_three_stage_flow(self) -> None:
        """feature 全深度: 3 阶段顺序进入, 决策 continue→continue→stop。"""
        ex = _FakeExtractor()
        res = _run_loader(ex, task_type="feature")
        assert res.stages == ["overview", "symbol", "detail"]
        decisions = [e.decision for e in res.trace.entries]
        assert decisions == [DECISION_CONTINUE, DECISION_CONTINUE, DECISION_STOP]
        # 每阶段至多一轮 (无 missing info / 无 overflow)
        assert len(ex.calls) == 3

    def test_stage_budgets_respected(self) -> None:
        """每阶段预算: overview ≤2K / symbol ≤5K / 总 ≤30K (超限截断至锚点核心)。"""
        plan = {
            "overview": StageLoadResult(
                items=[_item("req", "R" * 300, keep=True), _item("arch", "A" * 8000)]
            ),
            "symbol": StageLoadResult(items=[_item("idx", "I" * 8000)]),
            "detail": StageLoadResult(items=[_item("code", "C" * 8000)]),
        }
        res = _run_loader(_FakeExtractor(plan), task_type="feature")
        assert res.total_chars <= PROGRESSIVE_HARD_CAP_CHARS
        # overview: keep 锚点完整保留, 可裁项截断到 2K 档内 (token_cost = 预算后字符)
        assert "R" * 300 in res.stage_content["overview"]
        assert res.trace.entries[0].token_cost <= STAGE_1_BUDGET_CHARS
        assert res.trace.entries[1].token_cost <= STAGE_2_BUDGET_CHARS
        assert res.trace.context_overflow is False

    def test_early_stop_high_confidence(self) -> None:
        """通用类型 + 高置信 → 首阶段后早停 (不再加载; 设计 §3 ①)。"""
        ex = _FakeExtractor({
            "overview": StageLoadResult(items=[_item("o")], confidence=0.9),
        })
        res = _run_loader(ex, task_type="analysis")  # 非全深度类型
        assert res.stages == ["overview"]
        assert res.trace.entries[0].decision == DECISION_STOP
        assert res.trace.entries[0].decision_reason == "sufficient_confidence"

    def test_low_confidence_continues_to_next_stage(self) -> None:
        """低置信 → 触发下一阶段 (confidence 驱动扩展; 设计 §3 ①)。"""
        ex = _FakeExtractor({
            "overview": StageLoadResult(items=[_item("o")], confidence=0.3),
            "symbol": StageLoadResult(items=[_item("s")], confidence=0.9),
        })
        res = _run_loader(ex, task_type="analysis")
        assert res.stages == ["overview", "symbol"]
        assert res.trace.entries[0].decision == DECISION_CONTINUE
        assert res.trace.entries[0].decision_reason == "low_confidence"
        assert res.trace.entries[1].reason == "low_confidence"  # 进入 symbol 的依据

    def test_missing_info_widen_round(self) -> None:
        """missing info → 扩 1 轮: 同阶段重提取 (widen=True), 计数 ≤3。"""
        calls: list[tuple[str, bool, bool]] = []

        def extractor(spec: StageSpec, *, widen: bool = False, degrade: bool = False) -> StageLoadResult:
            calls.append((spec.stage, widen, degrade))
            if spec.stage == "symbol":
                return StageLoadResult(
                    items=[_item("s")], confidence=0.5,
                    missing_info=not widen,  # 扩 1 轮后信息补齐
                )
            return StageLoadResult(items=[_item(spec.stage)], confidence=0.5)

        loader = ProgressiveLoader(
            stages=CODE_STAGES,
            extractor=extractor,  # type: ignore[arg-type]
            hard_cap=PROGRESSIVE_HARD_CAP_CHARS,
        )
        res = loader.run(task_type="feature")
        assert res.trace.symbol_miss == []  # 无 symbol_miss 元数据
        widen_calls = [c for c in calls if c[0] == "symbol" and c[1] is True]
        assert len(widen_calls) == 1  # 恰好扩 1 轮
        reasons = [e.reason for e in res.trace.entries]
        assert "missing_info_widen" in reasons

    def test_stage1_unable_to_locate_auto_widen_once(self) -> None:
        """Stage 1 无法定位: 自动扩 1 轮 → 仍空 → unable_to_locate + low_confidence。"""
        calls: list[tuple[str, bool, bool]] = []

        def extractor(spec: StageSpec, *, widen: bool = False, degrade: bool = False) -> StageLoadResult:
            calls.append((spec.stage, widen, degrade))
            return StageLoadResult(items=[_item("o")], candidates_found=False, missing_info=True)

        loader = ProgressiveLoader(stages=CODE_STAGES, extractor=extractor)  # type: ignore[arg-type]
        res = loader.run(task_type="feature")
        assert res.trace.unable_to_locate is True
        assert res.trace.low_confidence is True
        # 恰好 1 轮 widen (扩关键词 1 轮 → 仍空 → 标记; 设计 §6)
        overview_calls = [c for c in calls if c[0] == "overview"]
        assert len(overview_calls) == 2
        assert overview_calls[1][1] is True
        assert res.stages == ["overview"]

    def test_overflow_retry_degrade_once(self) -> None:
        """token 超限 → 降级重试 1 次 (degrade=True) → 仍超 → context_overflow 标记。"""
        degrade_calls: list[bool] = []

        def extractor(spec: StageSpec, *, widen: bool = False, degrade: bool = False) -> StageLoadResult:
            if spec.stage == "detail":
                degrade_calls.append(degrade)
                # 锚点 (keep) 超预算 → 降级后仍超 → context_overflow (不静默)
                return StageLoadResult(
                    items=[_item("code", "D" * 200, keep=True)],
                    confidence=1.0,
                )
            return StageLoadResult(items=[_item(spec.stage)], confidence=0.5)

        loader = ProgressiveLoader(
            stages=CODE_STAGES, extractor=extractor, hard_cap=150,  # type: ignore[arg-type]
        )
        res = loader.run(task_type="feature")
        assert degrade_calls == [False, True]  # 首轮 + 降级重试 1 次
        assert res.trace.context_overflow is True
        assert res.trace.low_confidence is True
        assert any("降级重试" in w for w in res.trace.warnings)

    def test_overflow_retry_degrade_saved(self) -> None:
        """降级重试后 fit → context_overflow 不标记 (降级链生效; 设计 §4)。"""
        degrade_calls: list[bool] = []

        def extractor(spec: StageSpec, *, widen: bool = False, degrade: bool = False) -> StageLoadResult:
            if spec.stage == "detail":
                degrade_calls.append(degrade)
                if degrade:
                    return StageLoadResult(items=[_item("code", "d" * 40)], confidence=1.0)
                return StageLoadResult(items=[_item("code", "D" * 200, keep=True)], confidence=1.0)
            return StageLoadResult(items=[_item(spec.stage)], confidence=0.5)

        loader = ProgressiveLoader(
            stages=CODE_STAGES, extractor=extractor, hard_cap=150,  # type: ignore[arg-type]
        )
        res = loader.run(task_type="feature")
        assert degrade_calls == [False, True]
        assert res.trace.context_overflow is False  # 降级后 fit → 无 overflow
        assert "d" * 40 in res.stage_content["detail"]

    def test_validation_fallback_reload(self) -> None:
        """validation 反馈 → 回退上一阶段重载 (Stage 3 验证失败 → Stage 2; 设计 §3 ③)。"""
        ex = _FakeExtractor()
        res = _run_loader(ex, task_type="feature", validation_failed=True)
        last = res.trace.entries[-1]
        assert last.stage == "symbol"
        assert last.decision == DECISION_FALLBACK
        assert last.reason == "validation_feedback"
        # 回退后 symbol 内容 = 补充 (原 + 重载)
        assert len(res.stage_items["symbol"]) >= 1

    def test_extension_limit_global_cap(self) -> None:
        """扩展计数全局 ≤3: 持续 missing info → 第 4 次决策 stop(extension_limit)。"""
        rounds: list[int] = []

        def extractor(spec: StageSpec, *, widen: bool = False, degrade: bool = False) -> StageLoadResult:
            if spec.stage == "symbol":
                rounds.append(1)
                return StageLoadResult(items=[_item("s")], confidence=0.5,
                                       missing_info=True, anchor_found=True)
            return StageLoadResult(items=[_item(spec.stage)], confidence=0.5, anchor_found=True)

        loader = ProgressiveLoader(stages=CODE_STAGES, extractor=extractor)  # type: ignore[arg-type]
        res = loader.run(task_type="feature")
        assert len(rounds) == MAX_EXTENSION_ROUNDS + 1  # 首轮 + 3 轮扩展
        decision_reasons = [e.decision_reason for e in res.trace.entries]
        assert "extension_limit" in decision_reasons
        assert res.trace.low_confidence is True

    def test_finalizer_called_with_result(self) -> None:
        """finalizer 收到 ProgressiveResult (组装契约: 引擎不解释内容, 交给装配方)。"""
        seen: list[Any] = []

        def finalizer(result: ProgressiveResult) -> str:
            seen.append(result)
            return f"assembled:{len(result.stages)}"

        res = _run_loader(_FakeExtractor(), task_type="feature", finalizer=finalizer)
        assert seen and seen[0] is res
        assert res.assembled == "assembled:3"

    def test_generic_non_code_stage_specs(self) -> None:
        """Agent 通用化: 非代码 StageSpec (Finance 语义) 引擎照常运行。"""
        finance_stages = [
            StageSpec(stage="report", label="报表概览", max_chars=1000, extractor="report", required=True),
            StageSpec(stage="metrics", label="指标", max_chars=3000, extractor="metrics"),
            StageSpec(stage="detail", label="明细", max_chars=0, extractor="line_items"),
        ]
        calls: list[str] = []

        def extractor(spec: StageSpec, *, widen: bool = False, degrade: bool = False) -> StageLoadResult:
            calls.append(spec.stage)
            return StageLoadResult(items=[_item(f"{spec.stage}:row")], confidence=0.4)

        loader = ProgressiveLoader(stages=finance_stages, extractor=extractor)  # type: ignore[arg-type]
        res = loader.run(task_type="finance")  # 非全深度 → 低置信逐阶段
        assert res.stages == ["report", "metrics", "detail"]
        assert calls == ["report", "metrics", "detail"]
        # 阶段名/预算完全由配置决定 (引擎零代码语义耦合)
        assert len(res.stage_content["report"]) > 0
