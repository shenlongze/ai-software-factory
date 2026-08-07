"""tests/exec/test_exec_candidate.py — Candidate Execution Engine 单元测试 (Sprint 5 T5.2)。

覆盖 (全部纯本地, 零 LLM 零网络):
- ExecutionCandidate: 字段/必填/extra=forbid/容器 None 归一/quality clamp 0-100/
  latency ≥0/to_dict↔from_dict round-trip (ISO 时间戳)/is_success/
  to_experience_signals (candidate_success + 五类失败)
- candidate_from_result: 成功/失败结果映射/patch Artifact 读取/token_usage/
  validation_result 缺省代理/显式覆盖
- ExecutionRun 状态机: pending→running→success|failed 合法链 + 全部非法迁移拒绝
- CandidateCollector: 收集/顺序保持/successes-failures 拆分/失败无 reason 拒绝/
  类型校验
- classify_candidate_failure: 四类 + other 兜底
- SequentialRunner: N=3 默认/可配/顺序执行 (禁并发)/Run 状态记录/异常→失败候选/
  信号汇总/select_result 临时选择

basename 唯一 (test_exec_* 前缀); helper 复用 tests/exec/exec_helpers.py。
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from exec.candidate import (
    CANDIDATE_FAILURE_REASONS,
    CANDIDATE_REASON_EMPTY_OUTPUT,
    CANDIDATE_REASON_OPERATION_ERROR,
    CANDIDATE_REASON_OTHER,
    CANDIDATE_REASON_TOKEN_LIMIT,
    CANDIDATE_REASON_VALIDATION_FAILED,
    QUALITY_SCORE_PASS,
    CandidateCollector,
    ExecutionCandidate,
    ExecutionRun,
    RunStatus,
    SequentialRunner,
    candidate_failure_signal,
    candidate_from_result,
    classify_candidate_failure,
)
from exec.experience_ctx import (
    FAILURE_CONTEXT_INSUFFICIENT,
    FAILURE_OPERATION,
    FAILURE_TOKEN_OVERFLOW,
    FAILURE_VALIDATION,
)
from exec.models import Artifact, ArtifactType, ExecutionResult, ExecutionStatus, new_id
from exec_helpers import make_request

# ================================================================ 工厂 / 工具


def make_candidate(
    *,
    candidate_id: str = "CAND-1",
    run_id: str = "EXR-1-run-1",
    failure_reason: str = "",
    quality_score: float = QUALITY_SCORE_PASS,
    **overrides: Any,
) -> ExecutionCandidate:
    """候选工厂 (唯一缺省 id; 显式传参覆盖)。"""
    return ExecutionCandidate(
        id=candidate_id,
        task_id="T-101",
        run_id=run_id,
        provider="mock",
        model="deepseek-v4-flash",
        quality_score=quality_score,
        failure_reason=failure_reason,
        **overrides,
    )


class _R:
    """duck-typed ExecutionResult (runner/映射测试; 属性通道与真实类一致)。"""

    def __init__(
        self,
        *,
        success: bool = True,
        error: str = "",
        usage: dict[str, Any] | None = None,
        artifacts: list[Any] | None = None,
    ) -> None:
        self.id = new_id("EXS")
        self.request_id = "EXR-1"
        self.status = ExecutionStatus.SUCCESS if success else ExecutionStatus.FAILED
        self.error = error
        self.usage = usage or {}
        self.artifacts = artifacts or []

    @property
    def is_success(self) -> bool:
        return self.status is ExecutionStatus.SUCCESS


# ================================================================ ExecutionCandidate 模型


class TestCandidateModel:
    def test_defaults_filled(self) -> None:
        c = ExecutionCandidate(id="CAND-1", run_id="R-1")
        assert c.task_id == ""
        assert c.provider == "" and c.model == ""
        assert c.context_trace == {} and c.budget_trace == {}
        assert c.generated_output == "" and c.patch == "" and c.reference == ""
        assert c.token_usage == {} and c.validation_result == {}
        assert c.latency == 0.0 and c.quality_score == 0.0
        assert c.failure_reason == "" and c.created_at is not None

    def test_required_id_and_run_id(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionCandidate(run_id="R-1")  # type: ignore[call-arg]
        with pytest.raises(ValidationError):
            ExecutionCandidate(id="CAND-1")  # type: ignore[call-arg]

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionCandidate(id="CAND-1", run_id="R-1", nope=1)  # type: ignore[call-arg]

    def test_dict_fields_none_default(self) -> None:
        c = ExecutionCandidate(
            id="CAND-1", run_id="R-1",
            context_trace=None, budget_trace=None, token_usage=None,
            validation_result=None,  # type: ignore[arg-type]
        )
        assert c.context_trace == {} and c.budget_trace == {}
        assert c.token_usage == {} and c.validation_result == {}

    def test_str_fields_none_default(self) -> None:
        c = ExecutionCandidate(
            id="CAND-1", run_id="R-1",
            provider=None, patch=None, failure_reason=None,  # type: ignore[arg-type]
        )
        assert c.provider == "" and c.patch == "" and c.failure_reason == ""

    def test_quality_clamp_high(self) -> None:
        assert make_candidate(quality_score=150.0).quality_score == 100.0

    def test_quality_clamp_low(self) -> None:
        assert make_candidate(quality_score=-5.0).quality_score == 0.0

    def test_latency_negative_clamped(self) -> None:
        c = ExecutionCandidate(id="CAND-1", run_id="R-1", latency=-1.5)
        assert c.latency == 0.0

    def test_created_at_is_utc_aware(self) -> None:
        c = make_candidate()
        assert c.created_at.tzinfo is not None
        assert c.created_at.utcoffset() is not None

    def test_to_dict_roundtrip(self) -> None:
        c = make_candidate(
            candidate_id="CAND-rt",
            context_trace={"ranked": ["a", "b"]},
            patch="--- a/x\n+++ b/x\n",
            token_usage={"input_tokens": 10},
            latency=1.25,
            validation_result={"passed": True, "attempts": 1},
        )
        data = c.to_dict()
        got = ExecutionCandidate.from_dict(data)
        assert got.id == c.id and got.run_id == c.run_id
        assert got.context_trace == c.context_trace
        assert got.patch == c.patch and got.token_usage == c.token_usage
        assert got.latency == c.latency
        assert got.validation_result == c.validation_result
        assert got.created_at == c.created_at  # 时间戳 round-trip 保留

    def test_from_dict_iso_timestamp(self) -> None:
        data = {
            "id": "CAND-iso",
            "run_id": "R-1",
            "created_at": "2026-08-08T00:00:00.123456Z",
        }
        c = ExecutionCandidate.from_dict(data)
        assert c.created_at.isoformat().replace("+00:00", "Z") == "2026-08-08T00:00:00.123456Z"

    def test_is_success_empty_reason(self) -> None:
        assert make_candidate(failure_reason="").is_success
        assert not make_candidate(failure_reason="operation_error").is_success

    def test_quality_pass_constant(self) -> None:
        assert QUALITY_SCORE_PASS == 80.0


class TestCandidateSignals:
    def test_success_signal(self) -> None:
        assert make_candidate().to_experience_signals() == ["candidate_success"]

    def test_failure_signal_mapping_table(self) -> None:
        # 五类失败词汇全覆盖 (T5.2 §6 → experience_ctx T4.4 词汇)
        cases = {
            CANDIDATE_REASON_EMPTY_OUTPUT: FAILURE_TOKEN_OVERFLOW,
            CANDIDATE_REASON_TOKEN_LIMIT: FAILURE_TOKEN_OVERFLOW,
            CANDIDATE_REASON_OPERATION_ERROR: FAILURE_OPERATION,
            CANDIDATE_REASON_VALIDATION_FAILED: FAILURE_VALIDATION,
            CANDIDATE_REASON_OTHER: FAILURE_CONTEXT_INSUFFICIENT,
        }
        for reason, expected in cases.items():
            c = make_candidate(failure_reason=reason)
            assert c.to_experience_signals() == [expected], reason

    def test_failure_signal_ctx_type_passthrough(self) -> None:
        # 已是 experience_ctx 失败类型 (symbol_miss 等) → 原样透传
        c = make_candidate(failure_reason="symbol_miss")
        assert c.to_experience_signals() == ["symbol_miss"]

    def test_candidate_failure_signal_unknown_fallback(self) -> None:
        assert candidate_failure_signal("") == FAILURE_CONTEXT_INSUFFICIENT
        assert candidate_failure_signal("bogus") == FAILURE_CONTEXT_INSUFFICIENT


# ================================================================ candidate_from_result


class TestCandidateFromResult:
    def test_success_result_mapping(self) -> None:
        r = _R(success=True, usage={"input_tokens": 12, "estimated_cost_usd": 0.01})
        c = candidate_from_result(r, run_id="R-1", request=make_request())
        assert c.is_success and c.failure_reason == ""
        assert c.task_id == "T-101"
        assert c.token_usage == {"input_tokens": 12, "estimated_cost_usd": 0.01}
        assert c.quality_score == QUALITY_SCORE_PASS
        assert c.validation_result == {"passed": True}

    def test_failed_result_classified(self) -> None:
        r = _R(success=False, error="provider error: empty content (after 1 retry)")
        c = candidate_from_result(r, run_id="R-1")
        assert not c.is_success
        assert c.failure_reason == CANDIDATE_REASON_EMPTY_OUTPUT
        assert c.quality_score == 0.0
        assert c.validation_result == {"passed": False}

    def test_patch_read_from_artifact_file(self, tmp_path: Path) -> None:
        patch_file = tmp_path / "EXS-1.patch"
        patch_file.write_text("--- a/calc.py\n+++ b/calc.py\n@@ -1 +1 @@\n", encoding="utf-8")
        artifact = Artifact(
            id=new_id("ART"), type=ArtifactType.PATCH,
            task_id="T-1", path=str(patch_file),
        )
        r = _R(success=True, artifacts=[artifact])
        c = candidate_from_result(r, run_id="R-1")
        assert c.patch == "--- a/calc.py\n+++ b/calc.py\n@@ -1 +1 @@\n"

    def test_patch_artifact_missing_file_empty(self) -> None:
        artifact = Artifact(
            id=new_id("ART"), type=ArtifactType.PATCH,
            task_id="T-1", path="/nonexistent/x.patch",
        )
        r = _R(success=True, artifacts=[artifact])
        c = candidate_from_result(r, run_id="R-1")
        assert c.patch == ""

    def test_explicit_overrides_win(self) -> None:
        r = _R(success=True)
        c = candidate_from_result(
            r, run_id="R-1",
            provider="anthropic", model="claude-x",
            quality_score=95.0, failure_reason="",
            validation_result={"passed": True, "attempts": 2},
            latency=3.5,
        )
        assert c.provider == "anthropic" and c.model == "claude-x"
        assert c.quality_score == 95.0
        assert c.validation_result == {"passed": True, "attempts": 2}
        assert c.latency == 3.5

    def test_task_id_from_request(self) -> None:
        req = make_request(task_id="T-abc")
        c = candidate_from_result(_R(success=True), run_id="R-1", request=req)
        assert c.task_id == "T-abc"


# ================================================================ ExecutionRun 状态机


class TestExecutionRunStateMachine:
    def test_initial_pending(self) -> None:
        r = ExecutionRun(run_id="R-1")
        assert r.status is RunStatus.PENDING
        assert r.start_time is None and r.end_time is None and r.candidate_id == ""

    def test_start_records_time(self) -> None:
        r = ExecutionRun(run_id="R-1")
        r.start()
        assert r.status is RunStatus.RUNNING
        assert r.start_time is not None

    def test_complete_success(self) -> None:
        r = ExecutionRun(run_id="R-1")
        r.start()
        r.complete("CAND-1")
        assert r.status is RunStatus.SUCCESS
        assert r.candidate_id == "CAND-1"
        assert r.end_time is not None

    def test_fail(self) -> None:
        r = ExecutionRun(run_id="R-1")
        r.start()
        r.fail()
        assert r.status is RunStatus.FAILED
        assert r.end_time is not None

    def test_start_twice_rejected(self) -> None:
        r = ExecutionRun(run_id="R-1")
        r.start()
        with pytest.raises(ValueError):
            r.start()

    def test_complete_from_pending_rejected(self) -> None:
        r = ExecutionRun(run_id="R-1")
        with pytest.raises(ValueError):
            r.complete("CAND-1")

    def test_fail_from_pending_rejected(self) -> None:
        r = ExecutionRun(run_id="R-1")
        with pytest.raises(ValueError):
            r.fail()

    def test_complete_twice_rejected(self) -> None:
        r = ExecutionRun(run_id="R-1")
        r.start()
        r.complete("CAND-1")
        with pytest.raises(ValueError):
            r.complete("CAND-2")

    def test_fail_after_success_rejected(self) -> None:
        r = ExecutionRun(run_id="R-1")
        r.start()
        r.complete("CAND-1")
        with pytest.raises(ValueError):
            r.fail()

    def test_start_after_failed_rejected(self) -> None:
        r = ExecutionRun(run_id="R-1")
        r.start()
        r.fail()
        with pytest.raises(ValueError):
            r.start()

    def test_status_enum_values(self) -> None:
        assert [s.value for s in RunStatus] == ["pending", "running", "success", "failed"]

    def test_to_dict_serialization(self) -> None:
        r = ExecutionRun(run_id="R-1")
        r.start()
        r.complete("CAND-1")
        d = r.to_dict()
        assert d["run_id"] == "R-1" and d["status"] == "success"
        assert d["candidate_id"] == "CAND-1"
        assert d["start_time"] is not None and d["end_time"] is not None


# ================================================================ CandidateCollector


class TestCandidateCollector:
    def test_add_and_candidates(self) -> None:
        col = CandidateCollector()
        col.add(make_candidate(candidate_id="CAND-1", run_id="R-1"))
        col.add(make_candidate(candidate_id="CAND-2", run_id="R-2"))
        assert [c.id for c in col.candidates] == ["CAND-1", "CAND-2"]
        assert len(col) == 2

    def test_order_preserved(self) -> None:
        col = CandidateCollector()
        for i in range(5):
            col.add(make_candidate(candidate_id=f"CAND-{i}", run_id=f"R-{i}"))
        assert [c.run_id for c in col.candidates] == [f"R-{i}" for i in range(5)]

    def test_failure_without_reason_rejected(self) -> None:
        """Collector 防御: 失败候选必须带 failure_reason (禁静默丢弃)。

        模型语义下空 failure_reason = 成功候选 (失败候选无法经正常构造表达),
        该守卫是防御性不变式 — 用 is_success 被篡改的子类直接验证守卫逻辑。
        """

        class _BrokenCandidate(ExecutionCandidate):
            @property
            def is_success(self) -> bool:
                return False  # 声称失败却不带 reason (未来重构的防御场景)

        col = CandidateCollector()
        with pytest.raises(ValueError):
            col.add(_BrokenCandidate(id="CAND-bad", run_id="R-bad"))

    def test_failure_with_reason_accepted(self) -> None:
        col = CandidateCollector()
        col.add(make_candidate(
            candidate_id="CAND-f", run_id="R-f",
            failure_reason=CANDIDATE_REASON_OPERATION_ERROR, quality_score=0.0,
        ))
        assert len(col.failures) == 1

    def test_successes_failures_split(self) -> None:
        col = CandidateCollector()
        col.add(make_candidate(candidate_id="CAND-1", run_id="R-1"))
        col.add(make_candidate(
            candidate_id="CAND-2", run_id="R-2",
            failure_reason=CANDIDATE_REASON_TOKEN_LIMIT, quality_score=0.0,
        ))
        col.add(make_candidate(candidate_id="CAND-3", run_id="R-3"))
        assert [c.id for c in col.successes] == ["CAND-1", "CAND-3"]
        assert [c.id for c in col.failures] == ["CAND-2"]

    def test_collect_batch(self) -> None:
        col = CandidateCollector()
        out = col.collect([
            make_candidate(candidate_id="CAND-1", run_id="R-1"),
            make_candidate(
                candidate_id="CAND-2", run_id="R-2",
                failure_reason=CANDIDATE_REASON_VALIDATION_FAILED, quality_score=0.0,
            ),
        ])
        assert len(out) == 2

    def test_non_candidate_rejected(self) -> None:
        col = CandidateCollector()
        with pytest.raises(TypeError):
            col.add({"id": "x"})  # type: ignore[arg-type]

    def test_candidates_returns_copy(self) -> None:
        col = CandidateCollector()
        col.add(make_candidate())
        snapshot = col.candidates
        snapshot.clear()
        assert len(col.candidates) == 1


# ================================================================ classify_candidate_failure


class TestClassifyCandidateFailure:
    def test_empty_output(self) -> None:
        assert classify_candidate_failure("provider error: empty content (after 1 retry)") == (
            CANDIDATE_REASON_EMPTY_OUTPUT
        )
        assert classify_candidate_failure("empty response from provider") == (
            CANDIDATE_REASON_EMPTY_OUTPUT
        )

    def test_token_limit(self) -> None:
        assert classify_candidate_failure("finish_reason=length: max_tokens exhausted") == (
            CANDIDATE_REASON_TOKEN_LIMIT
        )
        assert classify_candidate_failure("context length exceeded") == CANDIDATE_REASON_TOKEN_LIMIT

    def test_operation_error(self) -> None:
        assert classify_candidate_failure("operation error: symbol not found: foo") == (
            CANDIDATE_REASON_OPERATION_ERROR
        )

    def test_validation_failed(self) -> None:
        assert classify_candidate_failure("validation failed: syntax error in calc.py") == (
            CANDIDATE_REASON_VALIDATION_FAILED
        )
        assert classify_candidate_failure("verifier failed: acceptance not met") == (
            CANDIDATE_REASON_VALIDATION_FAILED
        )

    def test_other_fallback(self) -> None:
        assert classify_candidate_failure("unexpected cosmic ray") == CANDIDATE_REASON_OTHER

    def test_empty_string_other(self) -> None:
        assert classify_candidate_failure("") == CANDIDATE_REASON_OTHER

    def test_vocabulary_has_five(self) -> None:
        assert len(CANDIDATE_FAILURE_REASONS) == 5


# ================================================================ SequentialRunner


class _SeqProvider:
    """可编程顺序结果 (每次调用弹出下一个; 记录调用序 + 线程名)。"""

    def __init__(self, results: list[Any]) -> None:
        self._results = list(results)
        self.calls: list[int] = []
        self.threads: list[str] = []

    def __call__(self, index: int) -> Any:
        self.calls.append(index)
        self.threads.append(threading.current_thread().name)
        if not self._results:
            return _R(success=True)
        return self._results.pop(0)


class TestSequentialRunner:
    def test_default_runs_three(self) -> None:
        prov = _SeqProvider([_R() for _ in range(3)])
        runner = SequentialRunner(prov)
        candidates = runner.run(request=make_request())
        assert len(candidates) == 3
        assert prov.calls == [1, 2, 3]

    def test_custom_runs(self) -> None:
        prov = _SeqProvider([_R(), _R()])
        runner = SequentialRunner(prov, runs=2)
        candidates = runner.run()
        assert len(candidates) == 2

    def test_runs_minimum_one(self) -> None:
        prov = _SeqProvider([_R()])
        runner = SequentialRunner(prov, runs=0)
        assert len(runner.run()) == 1

    def test_run_ids_and_states_recorded(self) -> None:
        prov = _SeqProvider([_R(), _R()])
        runner = SequentialRunner(prov, runs=2)
        runner.run(request=make_request(request_id="EXR-seq"))
        runs = runner.runs
        assert len(runs) == 2
        assert [r.run_id for r in runs] == ["EXR-seq-run-1", "EXR-seq-run-2"]
        assert all(r.status is RunStatus.SUCCESS for r in runs)
        assert all(r.candidate_id for r in runs)
        assert all(r.start_time and r.end_time for r in runs)

    def test_failed_result_saved_not_discarded(self) -> None:
        prov = _SeqProvider([
            _R(success=False, error="provider error: empty content"),
            _R(success=True),
        ])
        runner = SequentialRunner(prov, runs=2)
        candidates = runner.run()
        assert len(candidates) == 2  # 失败必存 — 禁静默丢弃
        assert not candidates[0].is_success
        assert candidates[0].failure_reason == CANDIDATE_REASON_EMPTY_OUTPUT
        assert candidates[1].is_success
        assert runner.runs[0].status is RunStatus.FAILED
        assert runner.runs[1].status is RunStatus.SUCCESS

    def test_executor_exception_saved_as_failed_candidate(self) -> None:
        def boom(_index: int) -> Any:
            raise RuntimeError("operation error: symbol foo not found")

        runner = SequentialRunner(boom, runs=3)
        candidates = runner.run()
        assert len(candidates) == 3
        assert all(not c.is_success for c in candidates)
        assert all(c.failure_reason == CANDIDATE_REASON_OPERATION_ERROR for c in candidates)
        assert all(r.status is RunStatus.FAILED for r in runner.runs)

    def test_signals_recorded(self) -> None:
        prov = _SeqProvider([
            _R(success=True),
            _R(success=False, error="finish_reason=length"),
        ])
        runner = SequentialRunner(prov, runs=2)
        runner.run()
        assert runner.signals == [
            ("candidate_success", "run-run-1"),
            (FAILURE_TOKEN_OVERFLOW, "run-run-2"),
        ]

    def test_select_result_first_success(self) -> None:
        prov = _SeqProvider([
            _R(success=False, error="validation failed: tests broken"),
            _R(success=True),
            _R(success=True),
        ])
        runner = SequentialRunner(prov, runs=3)
        runner.run()
        selected = runner.select_result()
        assert selected.is_success

    def test_select_result_all_failed_returns_last(self) -> None:
        prov = _SeqProvider([
            _R(success=False, error="empty content"),
            _R(success=False, error="operation error: x"),
        ])
        runner = SequentialRunner(prov, runs=2)
        runner.run()
        selected = runner.select_result()
        assert not selected.is_success  # 失败如实返回 — 不静默伪装成功
        assert selected.error == "operation error: x"

    def test_select_result_before_run_raises(self) -> None:
        runner = SequentialRunner(_SeqProvider([]))
        with pytest.raises(RuntimeError):
            runner.select_result()

    def test_sequential_no_concurrency(self) -> None:
        prov = _SeqProvider([_R(), _R(), _R()])
        runner = SequentialRunner(prov, runs=3)
        runner.run()
        # 禁并发: 全部调用同一线程 (无 threading/asyncio 派生), 且严格按 1→2→3
        assert len(set(prov.threads)) == 1
        assert prov.calls == [1, 2, 3]

    def test_non_callable_executor_rejected(self) -> None:
        with pytest.raises(TypeError):
            SequentialRunner("not callable")  # type: ignore[arg-type]

    def test_reentrant_run_resets_state(self) -> None:
        prov = _SeqProvider([_R()])
        runner = SequentialRunner(prov, runs=1)
        runner.run()
        runner.run()
        assert len(runner.candidates) == 1
        assert len(runner.runs) == 1
        assert len(runner.signals) == 1
