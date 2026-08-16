"""S10-062 批次 B — ReasoningProvider.analyze_gap + LLMGapAnalyzer 测试套件。

覆盖 (验收 A/B/E/F):
- ReasoningProvider: analyze_gap 接口 / prompt 组装 / 结构化输出解析
  (裸 JSON / markdown fence / dict 直返) / schema 校验 (缺字段) /
  deterministic 校验 (gap_type/severity/action/confidence 合法面) /
  ReasoningError (invalid JSON / schema error / API error / 异常包装) /
  ReasoningUnavailable (无真实 provider) / 模型不硬编码 (control plane 身份)
- LLMGapAnalyzer: 有效 LLM 响应 → GapAnalysis (source=llm, fallback_used=False);
  无效/异常 → fallback deterministic (source=deterministic); schema 错误 →
  fallback; API error → fallback; timeout → fallback; 再失败 → REQUEST_REVIEW;
  confidence 阈值 (低 confidence → fallback); duplicate 校验 (历史分析 /
  prev_decisions); fallback_used 标记; trace 落盘 (fallback_used 供 trace)

装配: tmp_path + fixtures; llm_fn 注入 deterministic fixture (有效/无效/
异常响应); 禁真实网络/LLM (真实 LLM 留 Pilot)。
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

import pytest

R = import_module("factory-console.session.reasoning")
G = import_module("factory-console.session.llm_gap")
GA = import_module("factory-console.session.gap_analyzer")
PT = import_module("factory-console.session.planning_trace")

VALID_GAP = {
    "detected": True,
    "gap_type": "missing_test",
    "description": "T001 缺少测试覆盖",
    "evidence": ["agent_output 命中 test 信号"],
    "severity": "medium",
    "source_task_id": "T001",
    "confidence": 0.85,
    "duplicate_of": None,
    "recommended_action": "INSERT_TASK",
    "reason": "LLM 判定需要测试任务",
}


def valid_gap_fn(prompt, operation=""):
    return json.dumps(VALID_GAP, ensure_ascii=False)


def invalid_json_fn(prompt, operation=""):
    return "这不是 JSON"


def schema_missing_fn(prompt, operation=""):
    return json.dumps(
        {k: v for k, v in VALID_GAP.items() if k != "detected"},
        ensure_ascii=False,
    )


def api_error_fn(prompt, operation=""):
    raise R.ReasoningError("API error: 502")


def timeout_fn(prompt, operation=""):
    raise TimeoutError("LLM timeout")


def unavailable_fn(prompt, operation=""):
    raise R.ReasoningUnavailable("no provider")


def boom_fn(prompt, operation=""):
    raise ValueError("boom")


def make_context() -> dict:
    """最小项目上下文 (prompt 面)。"""
    return {
        "project": {"name": "ScorePocket", "slug": "scorepocket"},
        "requirements": ["用户可记录分数", "数据需要持久化"],
        "current_plan": [{"id": "T001", "name": "backend api"}],
    }


def make_task_context(**overrides) -> dict:
    """执行上下文 (evidence + deterministic fallback 输入面)。"""
    tc = {
        "task": {"id": "T001", "name": "backend api"},
        "validation": {"success": False, "errors": ["测试失败: 1 failed"]},
        "result": {"agent_output": "缺少测试覆盖", "success": False},
        "agent_output": "缺少测试覆盖",
        "failures": [{"task_id": "T001", "name": "backend api",
                      "error": "validation failed"}],
        "existing_tasks": [{"id": "T001", "name": "backend api"}],
        "workspace": {"files": ["src/a.py"]},
    }
    tc.update(overrides)
    return tc


# ================================================================== 1. ReasoningProvider.analyze_gap


class TestProviderAnalyzeGap:
    def test_valid_response_returns_dict(self):
        prov = R.ReasoningProvider(llm_fn=valid_gap_fn)
        d = prov.analyze_gap(make_context())
        assert isinstance(d, dict)
        assert d["detected"] is True
        assert d["gap_type"] == "missing_test"
        assert d["confidence"] == 0.85
        assert d["recommended_action"] == "INSERT_TASK"

    def test_prompt_contains_context(self):
        captured = {}

        def builder(op, payload):
            captured["op"] = op
            captured["payload"] = payload
            return "PROMPT"

        prov = R.ReasoningProvider(
            llm_fn=lambda p, o: json.dumps(VALID_GAP),
            prompt_builder=builder,
        )
        prov.analyze_gap(make_context())
        assert captured["op"] == R.OPERATION_ANALYZE_GAP
        assert captured["payload"]["project"]["name"] == "ScorePocket"

    def test_default_prompt_contains_gap_types(self):
        prov = R.ReasoningProvider(llm_fn=valid_gap_fn)
        prompt = prov.build_prompt(
            R.OPERATION_ANALYZE_GAP, {"project": {"name": "X"}}
        )
        assert "missing_test" in prompt
        assert "REQUEST_REVIEW" in prompt
        assert "confidence" in prompt

    def test_parses_fenced_json(self):
        def fenced(prompt, operation=""):
            return "```json\n" + json.dumps(VALID_GAP) + "\n```"

        prov = R.ReasoningProvider(llm_fn=fenced)
        d = prov.analyze_gap({})
        assert d["gap_type"] == "missing_test"

    def test_accepts_dict_return(self):
        prov = R.ReasoningProvider(llm_fn=lambda p, o: dict(VALID_GAP))
        d = prov.analyze_gap({})
        assert d["gap_type"] == "missing_test"

    def test_invalid_json_raises_reasoning_error(self):
        prov = R.ReasoningProvider(llm_fn=invalid_json_fn)
        with pytest.raises(R.ReasoningError):
            prov.analyze_gap({})

    def test_empty_output_raises(self):
        prov = R.ReasoningProvider(llm_fn=lambda p, o: "")
        with pytest.raises(R.ReasoningError):
            prov.analyze_gap({})

    def test_schema_missing_field_raises(self):
        prov = R.ReasoningProvider(llm_fn=schema_missing_fn)
        with pytest.raises(R.ReasoningError) as ei:
            prov.analyze_gap({})
        assert "detected" in str(ei.value)

    def test_schema_extra_keys_tolerated(self):
        def extra(prompt, operation=""):
            d = dict(VALID_GAP)
            d["extra_llm_field"] = "ignored"
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=extra)
        d = prov.analyze_gap({})
        assert d["gap_type"] == "missing_test"

    def test_invalid_gap_type_raises(self):
        def fn(prompt, operation=""):
            d = dict(VALID_GAP)
            d["gap_type"] = "not_a_gap"
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=fn)
        with pytest.raises(R.ReasoningError) as ei:
            prov.analyze_gap({})
        assert "gap_type" in str(ei.value)

    def test_invalid_action_raises(self):
        def fn(prompt, operation=""):
            d = dict(VALID_GAP)
            d["recommended_action"] = "EXPLODE"
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=fn)
        with pytest.raises(R.ReasoningError) as ei:
            prov.analyze_gap({})
        assert "recommended_action" in str(ei.value)

    def test_invalid_severity_raises(self):
        def fn(prompt, operation=""):
            d = dict(VALID_GAP)
            d["severity"] = "catastrophic"
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=fn)
        with pytest.raises(R.ReasoningError) as ei:
            prov.analyze_gap({})
        assert "severity" in str(ei.value)

    def test_confidence_over_one_raises(self):
        def fn(prompt, operation=""):
            d = dict(VALID_GAP)
            d["confidence"] = 1.5
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=fn)
        with pytest.raises(R.ReasoningError) as ei:
            prov.analyze_gap({})
        assert "confidence" in str(ei.value)

    def test_confidence_non_number_raises(self):
        def fn(prompt, operation=""):
            d = dict(VALID_GAP)
            d["confidence"] = "high"
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=fn)
        with pytest.raises(R.ReasoningError):
            prov.analyze_gap({})

    def test_detected_false_without_description_ok(self):
        def fn(prompt, operation=""):
            return json.dumps({
                "detected": False, "gap_type": "", "description": "",
                "severity": "low", "confidence": 0.0,
                "recommended_action": "NO_ACTION", "reason": "无缺口",
            })

        prov = R.ReasoningProvider(llm_fn=fn)
        d = prov.analyze_gap({})
        assert d["detected"] is False
        assert d["recommended_action"] == "NO_ACTION"

    def test_detected_true_empty_description_raises(self):
        def fn(prompt, operation=""):
            d = dict(VALID_GAP)
            d["description"] = ""
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=fn)
        with pytest.raises(R.ReasoningError):
            prov.analyze_gap({})

    def test_llm_exception_wrapped(self):
        prov = R.ReasoningProvider(llm_fn=boom_fn)
        with pytest.raises(R.ReasoningError) as ei:
            prov.analyze_gap({})
        assert "boom" in str(ei.value)

    def test_llm_reasoning_error_passthrough(self):
        prov = R.ReasoningProvider(llm_fn=api_error_fn)
        with pytest.raises(R.ReasoningError) as ei:
            prov.analyze_gap({})
        assert "502" in str(ei.value)

    def test_llm_timeout_wrapped(self):
        prov = R.ReasoningProvider(llm_fn=timeout_fn)
        with pytest.raises(R.ReasoningError) as ei:
            prov.analyze_gap({})
        assert "timeout" in str(ei.value).lower()

    def test_no_provider_raises_unavailable(self, monkeypatch):
        prov = R.ReasoningProvider()
        monkeypatch.setattr(R.ReasoningProvider, "_assemble_provider",
                            staticmethod(lambda pid: None))
        with pytest.raises(R.ReasoningUnavailable):
            prov.analyze_gap({})

    def test_no_provider_assembly_error_raises_unavailable(self, monkeypatch):
        prov = R.ReasoningProvider()

        def broken(pid):
            raise RuntimeError("exec 不可用")

        monkeypatch.setattr(R.ReasoningProvider, "_assemble_provider",
                            staticmethod(broken))
        with pytest.raises(R.ReasoningUnavailable):
            prov.analyze_gap({})

    def test_unavailable_is_reasoning_error_subclass(self):
        assert issubclass(R.ReasoningUnavailable, R.ReasoningError)

    def test_model_not_hardcoded_identity_from_control_plane(self):
        class FakePlane:
            def select(self):
                return type("Sel", (), {"provider_id": "deepseek",
                                        "model_id": "deepseek-chat"})()

        prov = R.ReasoningProvider(llm_fn=valid_gap_fn,
                                   control_plane=FakePlane())
        pid, model = prov._resolve_identity()
        assert pid == "deepseek"
        assert model == "deepseek-chat"
        # 默认 prompt 不含硬编码模型名
        prompt = prov.build_prompt(R.OPERATION_ANALYZE_GAP, {})
        assert "deepseek-chat" not in prompt

    def test_default_prompt_no_hardcoded_model(self):
        prov = R.ReasoningProvider(llm_fn=valid_gap_fn)
        prompt = prov.build_prompt(R.OPERATION_ANALYZE_GAP, {})
        for name in ("deepseek-chat", "claude", "gpt-4"):
            assert name not in prompt

    def test_trace_recorded_on_success(self, tmp_path):
        trace = PT.PlanningTrace(file=tmp_path / "planning_trace.json")
        prov = R.ReasoningProvider(llm_fn=valid_gap_fn, trace=trace)
        prov.analyze_gap(make_context())
        records = trace.load()
        assert len(records) == 1
        assert records[0]["operation"] == "analyze_gap"
        assert records[0]["fallback_used"] is False
        assert records[0]["parsed_result"]["gap_type"] == "missing_test"
        assert records[0]["input_hash"]

    def test_trace_failure_safe(self, tmp_path):
        class BrokenTrace:
            def record(self, **kwargs):
                raise OSError("disk full")

        prov = R.ReasoningProvider(llm_fn=valid_gap_fn, trace=BrokenTrace())
        d = prov.analyze_gap({})  # 不抛
        assert d["gap_type"] == "missing_test"


# ================================================================== 2. LLMGapAnalyzer


class TestLLMGapAnalyzerValid:
    def test_valid_response_returns_gap_analysis(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=valid_gap_fn)
        ana = G.LLMGapAnalyzer(provider=prov,
                               file=tmp_path / "gap_analysis.json")
        res = ana.analyze(make_context(), make_task_context())
        assert isinstance(res.analysis, GA.GapAnalysis)
        assert res.analysis.detected is True
        assert res.analysis.gap_type == "missing_test"
        assert res.analysis.recommended_action == "INSERT_TASK"
        assert res.fallback_used is False
        assert res.source == "llm"

    def test_valid_response_fields_passed(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=valid_gap_fn)
        ana = G.LLMGapAnalyzer(provider=prov,
                               file=tmp_path / "gap_analysis.json")
        res = ana.analyze({}, {})
        a = res.analysis
        assert a.severity == "medium"
        assert a.source_task_id == "T001"
        assert a.confidence == 0.85
        assert a.reason == "LLM 判定需要测试任务"
        assert "agent_output" in a.evidence[0]

    def test_detected_false_no_action(self, tmp_path):
        def fn(prompt, operation=""):
            return json.dumps({
                "detected": False, "gap_type": "", "description": "",
                "severity": "low", "confidence": 0.0,
                "recommended_action": "NO_ACTION", "reason": "无缺口",
            })

        prov = R.ReasoningProvider(llm_fn=fn)
        ana = G.LLMGapAnalyzer(provider=prov,
                               file=tmp_path / "gap_analysis.json")
        res = ana.analyze({}, {})
        assert res.source == "llm"
        assert res.analysis.detected is False
        assert res.analysis.recommended_action == "NO_ACTION"
        assert res.fallback_used is False

    def test_prompt_contains_evidence(self, tmp_path):
        seen = {}

        def builder(context, tc):
            seen["evidence"] = context.get("evidence")
            return "PROMPT"

        prov = R.ReasoningProvider(llm_fn=valid_gap_fn)
        ana = G.LLMGapAnalyzer(provider=prov,
                               file=tmp_path / "gap_analysis.json",
                               prompt_builder=builder)
        ana.analyze(make_context(), make_task_context())
        assert any("validation.success=False" in e
                   for e in seen["evidence"])
        assert any("agent_output" in e for e in seen["evidence"])

    def test_duplicate_marked_from_previous_analyses(self, tmp_path):
        # 先落一条 deterministic 分析 (T001, missing_test)
        det = GA.GapAnalyzer(file=tmp_path / "gap_analysis.json")
        det.record(det.analyze(validation={"success": True},
                               agent_output="missing test",
                               task={"id": "T001"}))
        prov = R.ReasoningProvider(llm_fn=valid_gap_fn)
        ana = G.LLMGapAnalyzer(provider=prov,
                               deterministic=det,
                               file=tmp_path / "gap_analysis.json")
        res = ana.analyze(make_context(), make_task_context())
        assert res.analysis.duplicate_of == "T001"
        assert res.fallback_used is False  # 重复 → 标记, 不拒绝

    def test_duplicate_marked_from_prev_decisions(self, tmp_path):
        decisions = [{
            "decision": "INSERT_TASK",
            "affected_tasks": ["T001"],
            "reason": "已插入测试任务",
        }]
        prov = R.ReasoningProvider(llm_fn=valid_gap_fn)
        ana = G.LLMGapAnalyzer(provider=prov,
                               file=tmp_path / "gap_analysis.json")
        res = ana.analyze({}, {}, prev_decisions=decisions)
        assert res.analysis.duplicate_of == "T001"

    def test_no_duplicate_when_none(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=valid_gap_fn)
        ana = G.LLMGapAnalyzer(provider=prov,
                               file=tmp_path / "gap_analysis.json")
        res = ana.analyze({}, {})
        assert res.analysis.duplicate_of is None

    def test_trace_recorded_fallback_false(self, tmp_path):
        trace = PT.PlanningTrace(file=tmp_path / "planning_trace.json")
        prov = R.ReasoningProvider(llm_fn=valid_gap_fn)
        ana = G.LLMGapAnalyzer(provider=prov,
                               file=tmp_path / "gap_analysis.json",
                               trace=trace)
        ana.analyze(make_context(), make_task_context())
        records = trace.load()
        assert len(records) == 1
        assert records[0]["operation"] == "analyze_gap"
        assert records[0]["fallback_used"] is False
        assert records[0]["final_decision"] == "INSERT_TASK"


class TestLLMGapAnalyzerFallback:
    def test_invalid_json_falls_back_deterministic(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=invalid_json_fn)
        ana = G.LLMGapAnalyzer(provider=prov,
                               file=tmp_path / "gap_analysis.json")
        res = ana.analyze(make_context(), make_task_context())
        assert res.fallback_used is True
        assert res.source == "deterministic"
        # validation.success=False → deterministic validation_failure/REPAIR
        assert res.analysis.gap_type == "validation_failure"
        assert res.analysis.recommended_action == "REPAIR"

    def test_schema_error_falls_back(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=schema_missing_fn)
        ana = G.LLMGapAnalyzer(provider=prov,
                               file=tmp_path / "gap_analysis.json")
        res = ana.analyze(make_context(), make_task_context())
        assert res.fallback_used is True
        assert res.source == "deterministic"

    def test_invalid_gap_type_falls_back(self, tmp_path):
        def fn(prompt, operation=""):
            d = dict(VALID_GAP)
            d["gap_type"] = "alien_gap"
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=fn)
        ana = G.LLMGapAnalyzer(provider=prov,
                               file=tmp_path / "gap_analysis.json")
        res = ana.analyze(make_context(), make_task_context())
        assert res.fallback_used is True
        assert res.source == "deterministic"

    def test_api_error_falls_back(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=api_error_fn)
        ana = G.LLMGapAnalyzer(provider=prov,
                               file=tmp_path / "gap_analysis.json")
        res = ana.analyze(make_context(), make_task_context())
        assert res.fallback_used is True
        assert "502" in res.reason

    def test_timeout_falls_back(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=timeout_fn)
        ana = G.LLMGapAnalyzer(provider=prov,
                               file=tmp_path / "gap_analysis.json")
        res = ana.analyze(make_context(), make_task_context())
        assert res.fallback_used is True
        assert res.source == "deterministic"

    def test_unknown_exception_falls_back(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=boom_fn)
        ana = G.LLMGapAnalyzer(provider=prov,
                               file=tmp_path / "gap_analysis.json")
        res = ana.analyze(make_context(), make_task_context())
        assert res.fallback_used is True

    def test_unavailable_falls_back(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=unavailable_fn)
        ana = G.LLMGapAnalyzer(provider=prov,
                               file=tmp_path / "gap_analysis.json")
        res = ana.analyze(make_context(), make_task_context())
        assert res.fallback_used is True
        assert res.source == "deterministic"

    def test_low_confidence_falls_back(self, tmp_path):
        def fn(prompt, operation=""):
            d = dict(VALID_GAP)
            d["confidence"] = 0.2
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=fn)
        ana = G.LLMGapAnalyzer(provider=prov,
                               file=tmp_path / "gap_analysis.json")
        res = ana.analyze(make_context(), make_task_context())
        assert res.fallback_used is True
        assert "confidence" in res.reason

    def test_custom_confidence_threshold(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=valid_gap_fn)  # conf 0.85
        ana = G.LLMGapAnalyzer(provider=prov,
                               file=tmp_path / "gap_analysis.json",
                               confidence_threshold=0.9)
        res = ana.analyze(make_context(), make_task_context())
        assert res.fallback_used is True  # 0.85 < 0.9 → fallback

    def test_high_confidence_passes_custom_threshold(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=valid_gap_fn)  # conf 0.85
        ana = G.LLMGapAnalyzer(provider=prov,
                               file=tmp_path / "gap_analysis.json",
                               confidence_threshold=0.8)
        res = ana.analyze(make_context(), make_task_context())
        assert res.fallback_used is False
        assert res.source == "llm"

    def test_fallback_unknown_request_review(self, tmp_path):
        # 失败但无信号 → deterministic unknown → REQUEST_REVIEW
        prov = R.ReasoningProvider(llm_fn=invalid_json_fn)
        ana = G.LLMGapAnalyzer(provider=prov,
                               file=tmp_path / "gap_analysis.json")
        tc = make_task_context()
        tc["validation"] = {"success": True}
        tc["agent_output"] = "无法理解的问题"
        tc["result"] = {"success": False}
        tc["failures"] = [{"task_id": "T002", "name": "ui",
                           "error": "神秘失败"}]
        res = ana.analyze(make_context(), tc)
        assert res.fallback_used is True
        assert res.analysis.gap_type == "unknown"
        assert res.analysis.recommended_action == "REQUEST_REVIEW"
        assert res.source == "request_review"

    def test_deterministic_exception_request_review(self, tmp_path):
        class BrokenDet:
            def analyze(self, **kwargs):
                raise RuntimeError("deterministic broken")

            def previous_analyses(self):
                return []

        prov = R.ReasoningProvider(llm_fn=invalid_json_fn)
        ana = G.LLMGapAnalyzer(provider=prov, deterministic=BrokenDet())
        res = ana.analyze(make_context(), make_task_context())
        assert res.fallback_used is True
        assert res.source == "request_review"
        assert res.analysis.recommended_action == "REQUEST_REVIEW"
        assert res.analysis.gap_type == "unknown"

    def test_fallback_used_marker_in_trace(self, tmp_path):
        trace = PT.PlanningTrace(file=tmp_path / "planning_trace.json")
        prov = R.ReasoningProvider(llm_fn=invalid_json_fn)
        ana = G.LLMGapAnalyzer(provider=prov,
                               file=tmp_path / "gap_analysis.json",
                               trace=trace)
        ana.analyze(make_context(), make_task_context())
        records = trace.load()
        assert len(records) == 1
        assert records[0]["fallback_used"] is True
        assert records[0]["final_decision"] == "REPAIR"

    def test_analyze_never_raises(self, tmp_path):
        for fn in (invalid_json_fn, api_error_fn, timeout_fn, boom_fn,
                   unavailable_fn, schema_missing_fn):
            prov = R.ReasoningProvider(llm_fn=fn)
            ana = G.LLMGapAnalyzer(provider=prov,
                                   file=tmp_path / "gap_analysis.json")
            res = ana.analyze(make_context(), make_task_context())
            assert isinstance(res, G.LLMGapResult)
            assert isinstance(res.analysis, GA.GapAnalysis)
            assert res.fallback_used is True

    def test_provider_override_per_call(self, tmp_path):
        bad_prov = R.ReasoningProvider(llm_fn=invalid_json_fn)
        good_prov = R.ReasoningProvider(llm_fn=valid_gap_fn)
        ana = G.LLMGapAnalyzer(provider=bad_prov,
                               file=tmp_path / "gap_analysis.json")
        res = ana.analyze({}, {}, provider=good_prov)
        assert res.source == "llm"
        assert res.fallback_used is False
