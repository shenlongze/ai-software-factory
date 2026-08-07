"""tests/exec/test_exec_evaluator.py — CandidateEvaluator 单元测试 (Sprint 5 T5.3)。

覆盖 (全部纯本地, 零 LLM 零网络; 5 层确定性评分可解释):
- 5 层评分纯函数: Validation (+100 / 失败降级 / 无证据保守拒绝 / 计数推断 /
  failure_reason 优先) / PatchApply (±50 / 无证据 0) / Scope (基准 +30 缩放 /
  大修改减分 / 下限) / RegressionRisk (核心文件/删码/测试减少降分, 影响面小
  保分, 下限) / RequirementCoverage (逐条 +10 / 封顶 / 无证据 0)
- score_candidate: 总分=5 层之和 / 层序固定 / qualified=验证硬条件 / verdict 可解释
- evaluate: 空列表诚实拒绝 / 全失败诚实 rejection (最不差置顶) / Best 选择 /
  硬门槛 (合格者胜出即使总分低) / ranking 合格优先 / 平局决胜 (层优先 → 输入序) /
  确定性可复现 / score_breakdown 与 ranking 同序
- 证据字段缺省 {} → 各层中性 0 (不臆造)

basename 唯一 (test_exec_* 前缀); helper 本文件自洽 (不依赖跨文件辅助)。
"""

from __future__ import annotations

from typing import Any

import pytest

from exec.candidate import (
    CANDIDATE_REASON_VALIDATION_FAILED,
    ExecutionCandidate,
)
from exec.evaluator import (
    COVERAGE_CAP,
    COVERAGE_PER_CRITERION,
    PATCH_APPLY_FAIL_SCORE,
    PATCH_APPLY_PASS_SCORE,
    RISK_CORE_FILE_PENALTY,
    RISK_DELETION_PENALTY,
    RISK_FLOOR,
    RISK_SMALL_IMPACT_BONUS,
    RISK_TESTS_REDUCED_PENALTY,
    SCOPE_BASE_BONUS,
    SCOPE_FLOOR,
    VALIDATION_PASS_SCORE,
    CandidateEvaluator,
    CandidateScore,
    EvaluationLayer,
    EvaluationResult,
    LayerScore,
    score_candidate,
)

# ================================================================ 工厂 / 工具


def make_candidate(
    *,
    candidate_id: str = "CAND-1",
    run_id: str = "run-1",
    failure_reason: str = "",
    validation_result: dict[str, Any] | None = None,
    **overrides: Any,
) -> ExecutionCandidate:
    """候选工厂: 缺省 = 验证通过的普通成功候选 (唯一 id, 显式传参覆盖)。"""
    vresult = (
        dict(validation_result)
        if validation_result is not None
        else {"passed": True}
    )
    return ExecutionCandidate(
        id=candidate_id,
        task_id="T-101",
        run_id=run_id,
        provider="mock",
        model="deepseek-v4-flash",
        validation_result=vresult,
        failure_reason=failure_reason,
        **overrides,
    )


def _layer(score: CandidateScore, layer: EvaluationLayer) -> LayerScore:
    """按层枚举取 LayerScore (层序固定 — 测试断言辅助)。"""
    return next(item for item in score.layers if item.layer is layer)


# ================================================================ ① 验证层 (硬条件)


class TestValidationLayer:
    def test_passed_plus_100_qualified(self) -> None:
        score = score_candidate(make_candidate())
        layer = _layer(score, EvaluationLayer.VALIDATION)
        assert layer.score == VALIDATION_PASS_SCORE
        assert score.qualified is True
        assert "验证通过" in layer.reason

    def test_failed_zero_not_qualified(self) -> None:
        score = score_candidate(
            make_candidate(validation_result={"passed": False, "errors": "boom"})
        )
        layer = _layer(score, EvaluationLayer.VALIDATION)
        assert layer.score == 0.0
        assert score.qualified is False
        assert "boom" in layer.reason  # 失败原因进理由 (可解释)

    def test_failure_reason_candidate_never_qualified(self) -> None:
        """失败候选即使 validation_result 伪造 passed=True 也不可选 (证据优先)。"""
        score = score_candidate(
            make_candidate(
                failure_reason=CANDIDATE_REASON_VALIDATION_FAILED,
                validation_result={"passed": True},
            )
        )
        assert score.qualified is False
        assert "failure_reason" in _layer(score, EvaluationLayer.VALIDATION).reason

    def test_no_validation_evidence_conservative_reject(self) -> None:
        """无验证证据 → 保守按未验证 (0 分, 不可选 — 不臆造通过)。"""
        score = score_candidate(make_candidate(validation_result={}))
        assert score.qualified is False
        assert _layer(score, EvaluationLayer.VALIDATION).score == 0.0
        assert "无验证证据" in _layer(score, EvaluationLayer.VALIDATION).reason

    def test_tests_counts_infer_pass(self) -> None:
        score = score_candidate(
            make_candidate(
                validation_result={"tests_total": 5, "tests_passed": 5}
            )
        )
        assert score.qualified is True
        assert _layer(score, EvaluationLayer.VALIDATION).score == VALIDATION_PASS_SCORE

    def test_tests_counts_infer_fail(self) -> None:
        score = score_candidate(
            make_candidate(
                validation_result={"tests_total": 5, "tests_passed": 3}
            )
        )
        assert score.qualified is False

    def test_syntax_ok_infers_pass(self) -> None:
        score = score_candidate(
            make_candidate(validation_result={"syntax_ok": True})
        )
        assert score.qualified is True

    def test_verifier_passed_infers_pass(self) -> None:
        score = score_candidate(
            make_candidate(validation_result={"verifier_passed": True})
        )
        assert score.qualified is True

    def test_validation_detail_carries_counts(self) -> None:
        layer = _layer(
            score_candidate(
                make_candidate(
                    validation_result={"tests_total": 8, "tests_passed": 8}
                )
            ),
            EvaluationLayer.VALIDATION,
        )
        assert layer.detail["tests_total"] == 8
        assert layer.detail["tests_passed"] == 8


# ================================================================ ② patch 应用层


class TestPatchApplyLayer:
    def test_apply_success_plus_50(self) -> None:
        score = score_candidate(
            make_candidate(
                patch_apply_result={
                    "applied": True,
                    "files": ["calc.py"],
                    "method": "git apply --check",
                }
            )
        )
        layer = _layer(score, EvaluationLayer.PATCH_APPLY)
        assert layer.score == PATCH_APPLY_PASS_SCORE
        assert "1 文件" in layer.reason

    def test_apply_failure_minus_50_with_error(self) -> None:
        score = score_candidate(
            make_candidate(
                patch_apply_result={"applied": False, "error": "patch does not apply"}
            )
        )
        layer = _layer(score, EvaluationLayer.PATCH_APPLY)
        assert layer.score == PATCH_APPLY_FAIL_SCORE
        assert "patch does not apply" in layer.reason

    def test_no_apply_evidence_neutral_zero(self) -> None:
        score = score_candidate(make_candidate())
        layer = _layer(score, EvaluationLayer.PATCH_APPLY)
        assert layer.score == 0.0
        assert "无 patch 应用证据" in layer.reason


# ================================================================ ③ 修改范围层


class TestScopeLayer:
    def test_minimal_scope_full_bonus(self) -> None:
        score = score_candidate(
            make_candidate(scope_result={"changed_files": 1, "changed_lines": 10})
        )
        layer = _layer(score, EvaluationLayer.SCOPE)
        assert layer.score == SCOPE_BASE_BONUS

    def test_extra_files_penalty(self) -> None:
        """4 文件/10 行 → 30 - (4-1)*5 = +15。"""
        score = score_candidate(
            make_candidate(scope_result={"changed_files": 4, "changed_lines": 10})
        )
        assert _layer(score, EvaluationLayer.SCOPE).score == 15.0

    def test_large_lines_penalty(self) -> None:
        """1 文件/30 行 → 30 - (30-20)/10 = +29。"""
        score = score_candidate(
            make_candidate(scope_result={"changed_files": 1, "changed_lines": 30})
        )
        assert _layer(score, EvaluationLayer.SCOPE).score == 29.0

    def test_huge_scope_floored(self) -> None:
        """大修改减分钳制下限 -30。"""
        score = score_candidate(
            make_candidate(scope_result={"changed_files": 10, "changed_lines": 600})
        )
        assert _layer(score, EvaluationLayer.SCOPE).score == SCOPE_FLOOR

    def test_no_scope_evidence_neutral(self) -> None:
        score = score_candidate(make_candidate())
        assert _layer(score, EvaluationLayer.SCOPE).score == 0.0

    def test_scope_reason_explainable(self) -> None:
        layer = _layer(
            score_candidate(
                make_candidate(scope_result={"changed_files": 2, "changed_lines": 50})
            ),
            EvaluationLayer.SCOPE,
        )
        assert "2 文件" in layer.reason and "50 行" in layer.reason


# ================================================================ ④ 回归风险层


class TestRegressionRiskLayer:
    def test_no_evidence_neutral_keep(self) -> None:
        score = score_candidate(make_candidate())
        assert _layer(score, EvaluationLayer.REGRESSION_RISK).score == 0.0

    def test_core_files_penalty(self) -> None:
        score = score_candidate(
            make_candidate(regression_risk_result={"core_files_changed": True})
        )
        assert _layer(score, EvaluationLayer.REGRESSION_RISK).score == (
            RISK_CORE_FILE_PENALTY
        )

    def test_large_deletion_penalty(self) -> None:
        score = score_candidate(
            make_candidate(regression_risk_result={"deleted_lines": 120})
        )
        assert _layer(score, EvaluationLayer.REGRESSION_RISK).score == (
            RISK_DELETION_PENALTY
        )

    def test_tests_reduced_penalty(self) -> None:
        score = score_candidate(
            make_candidate(regression_risk_result={"tests_reduced": True})
        )
        assert _layer(score, EvaluationLayer.REGRESSION_RISK).score == (
            RISK_TESTS_REDUCED_PENALTY
        )

    def test_small_impact_bonus(self) -> None:
        """影响面小 (Call Graph 波及 ≤3 符号) → +10 保分。"""
        score = score_candidate(
            make_candidate(regression_risk_result={"affected_symbols": 2})
        )
        assert _layer(score, EvaluationLayer.REGRESSION_RISK).score == (
            RISK_SMALL_IMPACT_BONUS
        )
        assert "影响面小" in _layer(score, EvaluationLayer.REGRESSION_RISK).reason

    def test_combined_clamped_to_floor(self) -> None:
        score = score_candidate(
            make_candidate(
                regression_risk_result={
                    "core_files_changed": True,
                    "deleted_lines": 300,
                    "tests_reduced": True,
                }
            )
        )
        assert _layer(score, EvaluationLayer.REGRESSION_RISK).score == RISK_FLOOR

    def test_risk_reason_lists_signals(self) -> None:
        layer = _layer(
            score_candidate(
                make_candidate(
                    regression_risk_result={"core_files_changed": True}
                )
            ),
            EvaluationLayer.REGRESSION_RISK,
        )
        assert "核心文件改动" in layer.reason


# ================================================================ ⑤ 需求覆盖层


class TestCoverageLayer:
    def test_no_evidence_neutral(self) -> None:
        score = score_candidate(make_candidate())
        assert _layer(score, EvaluationLayer.REQUIREMENT_COVERAGE).score == 0.0

    def test_partial_coverage_per_criterion(self) -> None:
        """2/3 验收标准覆盖 → 逐条 +10 = +20。"""
        score = score_candidate(
            make_candidate(
                requirement_coverage_result={"covered": 2, "total": 3}
            )
        )
        layer = _layer(score, EvaluationLayer.REQUIREMENT_COVERAGE)
        assert layer.score == 2 * COVERAGE_PER_CRITERION
        assert "2/3" in layer.reason

    def test_coverage_capped_at_40(self) -> None:
        """5/5 覆盖 → 逐条 50 但封顶 +40。"""
        score = score_candidate(
            make_candidate(
                requirement_coverage_result={"covered": 5, "total": 5}
            )
        )
        assert _layer(score, EvaluationLayer.REQUIREMENT_COVERAGE).score == COVERAGE_CAP

    def test_total_defaults_to_covered(self) -> None:
        score = score_candidate(
            make_candidate(requirement_coverage_result={"covered": 3})
        )
        layer = _layer(score, EvaluationLayer.REQUIREMENT_COVERAGE)
        assert layer.score == 30.0
        assert "3/3" in layer.reason


# ================================================================ score_candidate 汇总


class TestScoreCandidate:
    def test_total_is_sum_of_five_layers(self) -> None:
        """全证据候选: 100 + 50 + 30 + 10 + 30 = 220。"""
        score = score_candidate(
            make_candidate(
                patch_apply_result={"applied": True, "files": ["calc.py"]},
                scope_result={"changed_files": 1, "changed_lines": 8},
                regression_risk_result={"affected_symbols": 1},
                requirement_coverage_result={"covered": 3, "total": 3},
            )
        )
        assert len(score.layers) == 5
        assert score.total == 220.0

    def test_layer_order_fixed_priority(self) -> None:
        """层序固定 = T5.1 §4 优先级 (验证→应用→范围→风险→覆盖)。"""
        score = score_candidate(make_candidate())
        assert [layer.layer for layer in score.layers] == [
            EvaluationLayer.VALIDATION,
            EvaluationLayer.PATCH_APPLY,
            EvaluationLayer.SCOPE,
            EvaluationLayer.REGRESSION_RISK,
            EvaluationLayer.REQUIREMENT_COVERAGE,
        ]

    def test_qualified_reflects_validation_hard_gate(self) -> None:
        assert score_candidate(make_candidate()).qualified is True
        assert score_candidate(
            make_candidate(validation_result={"passed": False})
        ).qualified is False

    def test_verdict_explainable_mentions_total(self) -> None:
        score = score_candidate(make_candidate())
        assert "总分" in score.verdict
        assert "验证通过, 合格" in score.verdict
        assert "+100" in score.verdict

    def test_verdict_failed_candidate_honest(self) -> None:
        score = score_candidate(
            make_candidate(validation_result={"passed": False})
        )
        assert "验证未通过, 不合格" in score.verdict

    def test_run_id_carried_into_score(self) -> None:
        score = score_candidate(make_candidate(run_id="EXR-1-run-3"))
        assert score.run_id == "EXR-1-run-3"


# ================================================================ evaluate 决策


class TestEvaluate:
    def test_empty_list_honest_rejection(self) -> None:
        result = CandidateEvaluator().evaluate([])
        assert result.selected_candidate_id is None
        assert result.ranking == []
        assert result.score_breakdown == []
        assert result.rejection_reason is not None
        assert "no candidates" in result.rejection_reason
        assert result.total_candidates == 0 and result.qualified_count == 0

    def test_all_failed_honest_rejection(self) -> None:
        """全失败: 诚实 rejection (不静默), ranking 最不差置顶。"""
        candidates = [
            make_candidate(
                candidate_id="CAND-B",
                validation_result={"passed": False, "errors": "tests broken"},
            ),
            make_candidate(
                candidate_id="CAND-A",
                validation_result={"passed": False, "errors": "syntax error"},
            ),
        ]
        result = CandidateEvaluator().evaluate(candidates)
        assert result.selected_candidate_id is None
        assert result.rejection_reason is not None
        assert "no qualified candidate" in result.rejection_reason
        assert result.qualified_count == 0
        assert set(result.ranking) == {"CAND-A", "CAND-B"}  # 全候选诚实排序
        assert len(result.score_breakdown) == 2

    def test_single_qualified_selected(self) -> None:
        result = CandidateEvaluator().evaluate([make_candidate()])
        assert result.selected_candidate_id == "CAND-1"
        assert result.rejection_reason is None
        assert result.qualified_count == 1
        assert result.ranking == ["CAND-1"]

    def test_best_qualified_selected(self) -> None:
        """多合格候选: 5 层总分最高者胜出。"""
        best = make_candidate(
            candidate_id="CAND-BEST",
            patch_apply_result={"applied": True, "files": ["calc.py"]},
            scope_result={"changed_files": 1, "changed_lines": 5},
            requirement_coverage_result={"covered": 2, "total": 2},
        )
        plain = make_candidate(candidate_id="CAND-PLAIN")
        result = CandidateEvaluator().evaluate([plain, best])
        assert result.selected_candidate_id == "CAND-BEST"

    def test_hard_gate_qualified_beats_unqualified_total(self) -> None:
        """验证硬门槛: 合格者胜出, 即使未合格候选总分更高 (设计 §4)。"""
        unqualified_higher = make_candidate(
            candidate_id="CAND-FAIL",
            validation_result={"passed": False},
            patch_apply_result={"applied": True, "files": ["a.py"]},
            scope_result={"changed_files": 1, "changed_lines": 5},
            requirement_coverage_result={"covered": 4, "total": 4},
        )
        qualified_lower = make_candidate(
            candidate_id="CAND-OK",
            patch_apply_result={"applied": False, "error": "no"},
            scope_result={"changed_files": 8, "changed_lines": 400},
        )
        result = CandidateEvaluator().evaluate([unqualified_higher, qualified_lower])
        assert result.selected_candidate_id == "CAND-OK"
        # ranking: 合格优先 (硬门槛) — 排名首位 = 选中候选
        assert result.ranking[0] == "CAND-OK"

    def test_ranking_qualified_first(self) -> None:
        candidates = [
            make_candidate(
                candidate_id="CAND-F",
                validation_result={"passed": False},
                patch_apply_result={"applied": True},
            ),
            make_candidate(candidate_id="CAND-S1"),
            make_candidate(
                candidate_id="CAND-S2",
                patch_apply_result={"applied": True},
            ),
        ]
        result = CandidateEvaluator().evaluate(candidates)
        assert result.ranking == ["CAND-S2", "CAND-S1", "CAND-F"]  # 合格在前
        assert result.selected_candidate_id == "CAND-S2"

    def test_tie_break_layer_priority(self) -> None:
        """同总分: 层优先级决胜 (Validation→Patch→Scope→Risk→Coverage)。

        A: 100 -50 +30 +10 +40 = 130 (Patch 失败, 其余层补回)
        B: 100 +50 -30 +10 +0  = 130 (Patch 成功, 范围/覆盖吃亏)
        总分平局 → PatchApply 层 (高优先级) 决定 B 胜出。
        """
        a = make_candidate(
            candidate_id="CAND-A",
            patch_apply_result={"applied": False, "error": "no"},
            scope_result={"changed_files": 1, "changed_lines": 10},
            regression_risk_result={"affected_symbols": 2},
            requirement_coverage_result={"covered": 4, "total": 4},
        )
        b = make_candidate(
            candidate_id="CAND-B",
            patch_apply_result={"applied": True, "files": ["x.py"]},
            scope_result={"changed_files": 10, "changed_lines": 600},
            regression_risk_result={"affected_symbols": 1},
        )
        result = CandidateEvaluator().evaluate([a, b])
        assert result.selected_candidate_id == "CAND-B"
        assert result.ranking == ["CAND-B", "CAND-A"]
        # 佐证: 总分确实平局 (130 == 130), 决胜在层优先级
        scores = {s.candidate_id: s.total for s in result.score_breakdown}
        assert scores["CAND-A"] == scores["CAND-B"] == 130.0

    def test_tie_break_input_order(self) -> None:
        """完全同证据平局 → 输入序 (Run 序) — 先 Run 者胜 (T5.2 语义延续)。"""
        candidates = [
            make_candidate(candidate_id="CAND-1", run_id="run-1"),
            make_candidate(candidate_id="CAND-2", run_id="run-2"),
            make_candidate(candidate_id="CAND-3", run_id="run-3"),
        ]
        result = CandidateEvaluator().evaluate(candidates)
        assert result.selected_candidate_id == "CAND-1"
        assert result.ranking == ["CAND-1", "CAND-2", "CAND-3"]

    def test_deterministic_repeat(self) -> None:
        """确定性: 同输入两次评估结果逐位一致 (禁随机)。"""
        candidates = [
            make_candidate(
                candidate_id="CAND-X",
                patch_apply_result={"applied": True},
                scope_result={"changed_files": 3, "changed_lines": 40},
                regression_risk_result={"core_files_changed": True},
                requirement_coverage_result={"covered": 2, "total": 3},
            ),
            make_candidate(candidate_id="CAND-Y"),
            make_candidate(
                candidate_id="CAND-Z",
                validation_result={"passed": False},
            ),
        ]
        first = CandidateEvaluator().evaluate(candidates)
        second = CandidateEvaluator().evaluate(candidates)
        assert first == second
        assert first.model_dump() == second.model_dump()

    def test_breakdown_ordering_matches_ranking(self) -> None:
        candidates = [
            make_candidate(
                candidate_id="CAND-A",
                validation_result={"passed": False},
            ),
            make_candidate(
                candidate_id="CAND-B",
                patch_apply_result={"applied": True},
            ),
        ]
        result = CandidateEvaluator().evaluate(candidates)
        assert [score.candidate_id for score in result.score_breakdown] == (
            result.ranking
        )

    def test_counts_reporting(self) -> None:
        candidates = [
            make_candidate(candidate_id="CAND-OK"),
            make_candidate(candidate_id="CAND-FAIL", validation_result={"passed": False}),
            make_candidate(candidate_id="CAND-FAIL2", validation_result={"passed": False}),
        ]
        result = CandidateEvaluator().evaluate(candidates)
        assert result.total_candidates == 3
        assert result.qualified_count == 1
        assert result.rejection_reason is None

    def test_ranking_includes_failed_candidates(self) -> None:
        """排名含失败候选 (诚实全排序 — 不静默丢弃, 供复盘)。"""
        candidates = [
            make_candidate(candidate_id="CAND-OK"),
            make_candidate(candidate_id="CAND-FAIL", validation_result={"passed": False}),
        ]
        result = CandidateEvaluator().evaluate(candidates)
        assert result.ranking == ["CAND-OK", "CAND-FAIL"]

    def test_unknown_evidence_keys_ignored(self) -> None:
        """未知/畸形证据键 → 层中性 0, 不抛 (确定性容错)。"""
        score = score_candidate(
            make_candidate(
                patch_apply_result={"applied": "yes"},  # 非布尔 → 0
                scope_result={"changed_files": "many", "changed_lines": None},
                regression_risk_result={"weird": 1},
                requirement_coverage_result={"covered": "x", "total": None},
            )
        )
        assert score.total == VALIDATION_PASS_SCORE  # 仅验证层得分

    def test_evaluation_result_serializable(self) -> None:
        """EvaluationResult 可 JSON 序列化 (审计/CLI 输出)。"""
        result = CandidateEvaluator().evaluate(
            [make_candidate(candidate_id="CAND-J")],
        )
        dumped = result.model_dump(mode="json")
        assert dumped["selected_candidate_id"] == "CAND-J"
        assert isinstance(dumped["score_breakdown"], list)
        assert dumped["evaluator_version"] == "1.0"

    def test_evidence_dicts_roundtrip_in_candidate(self) -> None:
        """证据字段 to_dict/from_dict round-trip (审计可持久化)。"""
        candidate = make_candidate(
            patch_apply_result={"applied": True, "files": ["calc.py"]},
            scope_result={"changed_files": 2, "changed_lines": 30},
        )
        restored = ExecutionCandidate.from_dict(candidate.to_dict())
        assert restored.patch_apply_result == candidate.patch_apply_result
        assert restored.scope_result == candidate.scope_result
        assert restored.regression_risk_result == {}
        assert restored.requirement_coverage_result == {}
