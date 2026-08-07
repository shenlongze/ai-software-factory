"""tests/exec/test_exec_experience.py — Experience 记录 (成功/失败/成本/原因)。

覆盖: 成功 (score 0.8/quality 1.0/result success) / 失败 (score 0.2/
quality 0.3/evidence 含 failure_reason) / 成本映射 (estimated_cost_usd →
成本效益分 clamp01) / task_type 派生与缺省 development / capabilities 合并
去重 / 产物 evidence / analyzer 缺失失败安全 (None) / duration 透传。

映射 (设计 §8): domain/subject_type=agent, subject_id=employee_id;
经验是背书不是替代 — 只记录不执行, 失败安全 (intelligence 缺失 → None)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from exec.experience import (
    QUALITY_FAIL,
    QUALITY_PASS,
    SCORE_FAILURE,
    SCORE_SUCCESS,
    ExperienceRecorder,
)
from exec.models import (
    Artifact,
    ArtifactType,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)
from exec_helpers import make_request


class FakeAnalyzer:
    """record_experience mock: 记录 kwargs; 可配置抛错。"""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self._error = error

    def record_experience(self, **kwargs):
        if self._error is not None:
            raise self._error
        self.calls.append(kwargs)
        return {"recorded": True}


def _result(
    *,
    status: ExecutionStatus = ExecutionStatus.SUCCESS,
    usage: dict | None = None,
    duration: float = 2.5,
    error: str = "",
    artifacts: list[Artifact] | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        id="EXS-exp-1",
        request_id="EXR-exp-1",
        status=status,
        usage=usage or {},
        duration=duration,
        error=error,
        artifacts=artifacts or [],
    )


class TestRecord:
    def test_success_mapping(self):
        analyzer = FakeAnalyzer()
        recorder = ExperienceRecorder(analyzer)
        recorder.record(result=_result(), employee_id="E-9", request=make_request())
        assert len(analyzer.calls) == 1
        call = analyzer.calls[0]
        assert call["subject_type"] == "agent"
        assert call["subject_id"] == "E-9"
        assert call["result"] == "success"
        assert call["score"] == SCORE_SUCCESS
        assert call["quality_score"] == QUALITY_PASS
        assert call["duration"] == 2.5
        assert call["confidence"] == 0.8

    def test_failure_mapping_and_reason_evidence(self):
        analyzer = FakeAnalyzer()
        recorder = ExperienceRecorder(analyzer)
        result = _result(
            status=ExecutionStatus.FAILED,
            error="provider error: anthropic api key missing",
        )
        recorder.record(result=result, employee_id="E-9", request=make_request())
        call = analyzer.calls[0]
        assert call["result"] == "failure"
        assert call["score"] == SCORE_FAILURE
        assert call["quality_score"] == QUALITY_FAIL
        # 失败原因进 evidence (结构化, 供未来推荐/复盘)
        reasons = [e["description"] for e in call["evidence"]]
        assert any("failure_reason: provider error" in r for r in reasons)

    def test_cost_mapping(self):
        analyzer = FakeAnalyzer()
        ExperienceRecorder(analyzer).record(
            result=_result(usage={"estimated_cost_usd": 0.25}),
            employee_id="E-9",
            request=make_request(),
        )
        # 成本效益分 = 1 - cost (0.25 → 0.75)
        assert analyzer.calls[0]["cost"] == 0.75

    def test_cost_clamped_to_zero(self):
        analyzer = FakeAnalyzer()
        ExperienceRecorder(analyzer).record(
            result=_result(usage={"estimated_cost_usd": 3.0}),
            employee_id="E-9",
            request=make_request(),
        )
        assert analyzer.calls[0]["cost"] == 0.0

    def test_no_cost_yields_none(self):
        analyzer = FakeAnalyzer()
        ExperienceRecorder(analyzer).record(
            result=_result(usage={}), employee_id="E-9", request=make_request()
        )
        assert analyzer.calls[0]["cost"] is None

    def test_task_type_from_request(self):
        analyzer = FakeAnalyzer()
        ExperienceRecorder(analyzer).record(
            result=_result(), employee_id="E-9", request=make_request(task_id="T-777")
        )
        assert analyzer.calls[0]["task_type"] == "T-777"

    def test_task_type_default_development(self):
        analyzer = FakeAnalyzer()
        request = ExecutionRequest(
            id="EXR-exp-2", task_id="", objective="fix bug", input={}
        )
        ExperienceRecorder(analyzer).record(result=_result(), employee_id="E-9", request=request)
        assert analyzer.calls[0]["task_type"] == "development"

    def test_capabilities_merge_dedupe(self):
        analyzer = FakeAnalyzer()
        req = make_request(capabilities=["python", "development", "python"])
        ExperienceRecorder(analyzer).record(result=_result(), employee_id="E-9", request=req)
        caps = analyzer.calls[0]["capability"]
        assert caps[0] == "development"  # 基础能力前置
        assert sorted(caps) == sorted(["development", "python"])

    def test_artifact_evidence(self):
        analyzer = FakeAnalyzer()
        artifacts = [
            Artifact(id="ART-1", type=ArtifactType.PATCH, task_id="T-1", path="/tmp/x.patch"),
            Artifact(id="ART-2", type=ArtifactType.REPORT, task_id="T-1", path="/tmp/r.md"),
        ]
        ExperienceRecorder(analyzer).record(
            result=_result(artifacts=artifacts), employee_id="E-9", request=make_request()
        )
        sources = {(e["source_type"], e["source_id"]) for e in analyzer.calls[0]["evidence"]}
        assert ("artifact", "ART-1") in sources
        assert ("artifact", "ART-2") in sources

    def test_analyzer_none_fails_safe(self):
        """intelligence 缺失 → 记录静默跳过 (None), 不破坏执行链路。"""
        assert ExperienceRecorder(None).record(
            result=_result(), employee_id="E-9", request=make_request()
        ) is None

    def test_analyzer_error_swallowed_by_caller(self):
        """analyzer 抛错 → record 上抛 (Runtime 侧已包 try/except 失败安全)。"""
        recorder = ExperienceRecorder(FakeAnalyzer(error=RuntimeError("boom")))
        with pytest.raises(RuntimeError):
            recorder.record(result=_result(), employee_id="E-9", request=make_request())
