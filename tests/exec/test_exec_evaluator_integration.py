"""tests/exec/test_exec_evaluator_integration.py — CandidateEvaluator 集成测试 (Sprint 5 T5.3)。

覆盖 (真实 SequentialRunner / AgentRuntime 全链, mock Provider, 零 LLM 零网络):
- Runner 级: 多候选评估 (ranking/score_breakdown 全明细) / 证据差异化 Best 选择 /
  全失败诚实 rejection (结果如实失败 + last_evaluation.rejection_reason) /
  未 run 先 evaluate 拒绝 / 同证据平局 → Run 序 (T5.2 语义延续)
- Collector → Evaluator 端到端 (证据携带候选选 Best)
- candidate_from_result → Evaluator (真实产链: validation_result 代理证据)
- Runtime 级: Flag 关旧流程不变 (last_evaluation=None 零评估) / Flag 开
  正式评估 (last_evaluation 非空, selected ∈ candidates) / 混合收集选合格 /
  全失败拒绝 / 评估无副作用 (evaluate 不触发 Provider 调用 — 禁 LLM)

basename 唯一 (test_exec_* 前缀); helper 复用 tests/exec/exec_helpers.py
+ conftest fixtures (exec_store/logger)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from exec.agent_runtime import AgentRuntime
from exec.candidate import (
    CandidateCollector,
    ExecutionCandidate,
    SequentialRunner,
    candidate_from_result,
)
from exec.evaluator import CandidateEvaluator, EvaluationLayer, EvaluationResult
from exec.models import ExecutionStatus, new_id
from exec.provider import ProviderResponse
from exec_helpers import FakeProvider, git_diff_text, make_request, write_files

CALC_BEFORE = "def add(a, b):\n    return a + b\n\n"
CALC_AFTER = "def add(a, b):\n    return abs(a + b)\n\n"


def _bug_project(tmp_path: Path) -> Path:
    proj = tmp_path / "bug-project"
    write_files(proj, {"calc.py": CALC_BEFORE, "README.md": "# demo\n"})
    return proj


def _patch_content(tmp_path: Path) -> str:
    return git_diff_text(tmp_path, {"calc.py": CALC_BEFORE}, {"calc.py": CALC_AFTER})


def _ok_content(tmp_path: Path) -> str:
    return "fixed the sub bug\n<patch>\n" + _patch_content(tmp_path) + "\n</patch>"


class _R:
    """duck-typed ExecutionResult (runner executor 产出; 属性通道与真实类一致)。"""

    def __init__(
        self,
        *,
        success: bool = True,
        error: str = "",
        usage: dict[str, Any] | None = None,
    ) -> None:
        self.id = new_id("EXS")
        self.request_id = "EXR-1"
        self.status = ExecutionStatus.SUCCESS if success else ExecutionStatus.FAILED
        self.error = error
        self.usage = usage or {}
        self.artifacts: list[Any] = []

    @property
    def is_success(self) -> bool:
        return self.status is ExecutionStatus.SUCCESS


def _evidence_runner(
    candidates: list[ExecutionCandidate],
) -> tuple[SequentialRunner, list[Any]]:
    """用预置证据候选跑 SequentialRunner, 返回 (runner, results)。

    简化产线: 候选对象由 candidate_from_result 物化, 测试在其上回填模板 id
    与 T5.3 各层证据 (与真实产线把 git apply/scope/risk/coverage 证据写入
    候选一致), 再经 runner.evaluate() 正式评估; results 供选中结果对应断言。
    """
    results = [_R(success=not bool(c.failure_reason)) for c in candidates]

    def executor(index: int) -> Any:
        return results[index - 1]

    runner = SequentialRunner(executor, runs=len(candidates))
    runner.run()
    for index, candidate in enumerate(candidates):
        current = runner.candidates[index]
        current.id = candidate.id  # 回填模板 id (断言锚点)
        current.patch_apply_result = candidate.patch_apply_result
        current.scope_result = candidate.scope_result
        current.regression_risk_result = candidate.regression_risk_result
        current.requirement_coverage_result = candidate.requirement_coverage_result
    return runner, results


class _Seq:
    """按调用序出结果的 Provider (成功/错误可编排; 无记录 — 本测试只断言结果)。"""

    provider_id = "mock"

    def __init__(self, steps: list[tuple[str, str]]) -> None:
        self._steps = list(steps)

    def generate(self, request: Any) -> ProviderResponse:
        kind, payload = self._steps.pop(0)
        if kind == "error":
            return ProviderResponse(content="", error=payload)
        return ProviderResponse(
            content=payload,
            usage={"input_tokens": 10, "estimated_cost_usd": 0.01},
        )


def _runtime(
    provider: Any,
    store: Any,
    logger: Any,
    *,
    execution_strategy_enabled: bool = False,
    execution_strategy_runs: int = 3,
) -> AgentRuntime:
    return AgentRuntime(
        provider,
        store=store,
        logger=logger,
        artifacts_dir=store.dir,
        execution_strategy_enabled=execution_strategy_enabled,
        execution_strategy_runs=execution_strategy_runs,
    )


# ================================================================ Runner 级评估


class TestRunnerEvaluation:
    def test_runner_evaluate_full_breakdown(self) -> None:
        """多候选评估: ranking/score_breakdown 全明细 (每候选 5 层)。"""
        candidates = [
            ExecutionCandidate(
                id="CAND-1", run_id="run-1",
                validation_result={"passed": True},
            ),
            ExecutionCandidate(
                id="CAND-2", run_id="run-2",
                validation_result={"passed": True},
                patch_apply_result={"applied": True, "files": ["calc.py"]},
            ),
            ExecutionCandidate(
                id="CAND-3", run_id="run-3",
                failure_reason="validation_failed",
                validation_result={"passed": False},
            ),
        ]
        runner, _results = _evidence_runner(candidates)
        evaluation = runner.evaluate()

        assert isinstance(evaluation, EvaluationResult)
        assert evaluation.total_candidates == 3
        assert evaluation.qualified_count == 2
        assert evaluation.selected_candidate_id == "CAND-2"
        assert evaluation.ranking == ["CAND-2", "CAND-1", "CAND-3"]
        assert [s.candidate_id for s in evaluation.score_breakdown] == (
            evaluation.ranking
        )
        for score in evaluation.score_breakdown:
            assert [layer.layer for layer in score.layers] == [
                EvaluationLayer.VALIDATION,
                EvaluationLayer.PATCH_APPLY,
                EvaluationLayer.SCOPE,
                EvaluationLayer.REGRESSION_RISK,
                EvaluationLayer.REQUIREMENT_COVERAGE,
            ]
        assert evaluation.rejection_reason is None

    def test_runner_select_best_success_by_evidence(self) -> None:
        """多成功候选: 证据差异化 → 5 层总分最高者被选中 (结果对应选中候选)。"""
        candidates = [
            ExecutionCandidate(id="CAND-A", run_id="run-1"),
            ExecutionCandidate(
                id="CAND-B", run_id="run-2",
                patch_apply_result={"applied": True, "files": ["calc.py"]},
                scope_result={"changed_files": 1, "changed_lines": 8},
                requirement_coverage_result={"covered": 2, "total": 2},
            ),
        ]
        runner, results = _evidence_runner(candidates)
        selected = runner.select_result()
        evaluation = runner.last_evaluation

        assert evaluation.selected_candidate_id == "CAND-B"
        assert selected is results[1]  # 选中结果 = 选中候选对应的执行结果
        assert selected.is_success

    def test_runner_tie_breaks_to_run_order(self) -> None:
        """同证据平局 → Run 序 (T5.2 第一个成功语义延续, 不破坏旧流程)。"""
        runner, results = _evidence_runner(
            [
                ExecutionCandidate(id="CAND-1", run_id="run-1"),
                ExecutionCandidate(id="CAND-2", run_id="run-2"),
            ]
        )
        result = runner.select_result()
        assert runner.last_evaluation.selected_candidate_id == "CAND-1"
        assert result is results[0]  # Run 序决胜 → 第一个成功候选的结果

    def test_runner_all_failed_honest_rejection(self) -> None:
        """全失败: select_result 如实返回失败结果 + 诚实拒绝理由 (不静默)。"""
        candidates = [
            ExecutionCandidate(
                id="CAND-F1", run_id="run-1",
                failure_reason="empty_output",
            ),
            ExecutionCandidate(
                id="CAND-F2", run_id="run-2",
                failure_reason="operation_error",
            ),
        ]
        runner, results = _evidence_runner(candidates)
        selected = runner.select_result()
        evaluation = runner.last_evaluation

        assert evaluation.selected_candidate_id is None
        assert evaluation.rejection_reason is not None
        assert "no qualified candidate" in evaluation.rejection_reason
        assert not selected.is_success  # 失败如实返回 (不静默伪装成功)
        assert selected is results[-1]  # 全失败 → 最后一个失败结果 (T5.2 语义延续)

    def test_runner_evaluate_before_run_raises(self) -> None:
        runner = SequentialRunner(lambda _index: _R(), runs=2)
        with pytest.raises(RuntimeError):
            runner.evaluate()

    def test_evaluate_is_pure_no_provider_calls(self) -> None:
        """评估禁 LLM: evaluate/select_result 不触发 executor (Provider) 调用。"""
        calls: list[int] = []

        def executor(index: int) -> Any:
            calls.append(index)
            return _R(success=index == 1)

        runner = SequentialRunner(executor, runs=2)
        runner.run()
        assert len(calls) == 2
        runner.evaluate()
        runner.evaluate()  # 重复评估无副作用
        runner.select_result()
        assert len(calls) == 2  # 评估零 Provider 调用

    def test_collector_then_evaluator_end_to_end(self) -> None:
        """CandidateCollector → CandidateEvaluator 端到端 (失败必存 → 评估)。"""
        collector = CandidateCollector()
        collector.collect(
            [
                ExecutionCandidate(
                    id="CAND-OK", run_id="run-1",
                    validation_result={"passed": True},
                    patch_apply_result={"applied": True, "files": ["calc.py"]},
                ),
                ExecutionCandidate(
                    id="CAND-FAIL", run_id="run-2",
                    failure_reason="token_limit",
                ),
            ]
        )
        result = CandidateEvaluator().evaluate(collector.candidates)
        assert result.selected_candidate_id == "CAND-OK"
        assert result.qualified_count == 1
        assert collector.failures[0].failure_reason == "token_limit"

    def test_candidate_from_result_feeds_evaluator(self) -> None:
        """真实产链: candidate_from_result → evaluate (validation 代理证据)。"""
        ok = candidate_from_result(
            _R(success=True),
            run_id="run-1",
        )
        bad = candidate_from_result(
            _R(success=False, error="validation failed: tests broken"),
            run_id="run-2",
        )
        result = CandidateEvaluator().evaluate([ok, bad])
        assert result.selected_candidate_id == ok.id
        assert result.qualified_count == 1
        assert bad.failure_reason == "validation_failed"


# ================================================================ Runtime 级 (Flag 兼容)

class TestRuntimeEvaluation:
    def test_flag_off_legacy_zero_evaluation(
        self, exec_store, logger, tmp_path: Path
    ) -> None:
        """Flag 关: 旧流程逐位不变 — 零候选 + 零评估 (last_evaluation None)。"""
        provider = FakeProvider(content=_ok_content(tmp_path))
        runtime = _runtime(provider, exec_store, logger)
        request = make_request(request_id="EXR-EV-off-1", project_dir=_bug_project(tmp_path))

        result = runtime.execute(request)

        assert result.is_success
        assert runtime.last_candidates == []
        assert runtime.last_evaluation is None  # 旧流程不产评估

    def test_flag_on_evaluation_present_selected(
        self, exec_store, logger, tmp_path: Path
    ) -> None:
        """Flag 开: 正式评估 — last_evaluation 非空, selected ∈ candidates。"""
        provider = FakeProvider(content=_ok_content(tmp_path))
        runtime = _runtime(provider, exec_store, logger, execution_strategy_enabled=True)
        request = make_request(request_id="EXR-EV-on-1", project_dir=_bug_project(tmp_path))

        result = runtime.execute(request)

        assert result.is_success
        candidates = runtime.last_candidates
        assert len(candidates) == 3
        evaluation = runtime.last_evaluation
        assert evaluation is not None
        assert evaluation.selected_candidate_id in {c.id for c in candidates}
        assert evaluation.rejection_reason is None
        assert evaluation.total_candidates == 3
        assert evaluation.qualified_count == 3

    def test_flag_on_mixed_selected_qualified(
        self, exec_store, logger, tmp_path: Path
    ) -> None:
        """混合 (失败+成功): 选中验证通过候选, 失败候选仍诚实入榜。"""
        provider = _Seq(
            [
                ("error", "provider error: empty content (after 1 retry)"),
                ("ok", _ok_content(tmp_path)),
                ("error", "provider error: empty content (after 1 retry)"),
            ]
        )
        runtime = _runtime(provider, exec_store, logger, execution_strategy_enabled=True)
        request = make_request(request_id="EXR-EV-mix-1", project_dir=_bug_project(tmp_path))

        result = runtime.execute(request)

        assert result.is_success
        evaluation = runtime.last_evaluation
        assert evaluation is not None
        assert evaluation.selected_candidate_id is not None
        # 选中候选必是验证通过的 (硬门槛)
        selected = next(
            c for c in runtime.last_candidates
            if c.id == evaluation.selected_candidate_id
        )
        assert selected.is_success
        assert evaluation.qualified_count == 1
        assert len(evaluation.ranking) == 3  # 失败候选诚实入榜

    def test_flag_on_all_failed_honest_rejection(
        self, exec_store, logger, tmp_path: Path
    ) -> None:
        """Flag 开 + 全失败: 结果如实失败 + 诚实拒绝理由可审计。"""
        provider = FakeProvider(error="anthropic http 429: rate limited")
        runtime = _runtime(provider, exec_store, logger, execution_strategy_enabled=True)
        request = make_request(request_id="EXR-EV-fail-1", project_dir=_bug_project(tmp_path))

        result = runtime.execute(request)

        assert not result.is_success
        evaluation = runtime.last_evaluation
        assert evaluation is not None
        assert evaluation.selected_candidate_id is None
        assert evaluation.rejection_reason is not None
        assert evaluation.qualified_count == 0

    def test_flag_on_ranking_stable_repeat(
        self, exec_store, logger, tmp_path: Path
    ) -> None:
        """确定性: 同一批候选重复评估 ranking 逐位一致。"""
        provider = FakeProvider(content=_ok_content(tmp_path))
        runtime = _runtime(provider, exec_store, logger, execution_strategy_enabled=True)
        request = make_request(request_id="EXR-EV-stb-1", project_dir=_bug_project(tmp_path))
        runtime.execute(request)

        runner = SequentialRunner(lambda _index: _R(), runs=3)
        runner.run()
        first = runner.evaluate()
        second = runner.evaluate()
        assert first.ranking == second.ranking
        assert first == second
        assert runtime.last_evaluation.selected_candidate_id is not None
