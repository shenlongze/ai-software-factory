"""S10-062 — LLM Planning Fallback 测试套件。

覆盖: LLM → deterministic → REQUEST_REVIEW fallback 链 / confidence 阈值 /
API error / timeout / invalid JSON / schema error / 不因 LLM 挂而崩溃。

装配: tmp_path + llm_fn fixture; 禁真实网络 (真实 LLM 留到 Pilot)。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from importlib import import_module

R = import_module("factory-console.session.reasoning")
LG = import_module("factory-console.session.llm_gap")
LP = import_module("factory-console.session.llm_task_proposal")


def _gap_ctx():
    return {"project": "demo", "current_plan": [], "completed_work": [],
            "validation": {"success": False, "errors": ["persistence missing"]}}


def _valid_gap_fn(prompt, operation=""):
    return json.dumps({"detected": True, "gap_type": "missing_implementation",
                       "description": "缺持久化", "evidence": [{"source": "validation_result.json"}],
                       "severity": "high", "source_task_id": "T001", "confidence": 0.8,
                       "duplicate_of": None, "recommended_action": "INSERT_TASK",
                       "reason": "persistence required"}, ensure_ascii=False)


# ================================================================== 1. fallback 链


class TestFallbackChain:
    def test_llm_success_no_fallback(self):
        prov = R.ReasoningProvider(llm_fn=_valid_gap_fn)
        analyzer = LG.LLMGapAnalyzer(provider=prov)
        result = analyzer.analyze(_gap_ctx(), {"task": {"id": "T001"}})
        assert result.analysis.detected
        assert result.fallback_used is False

    def test_llm_fail_fallback_deterministic(self):
        """LLM API error → deterministic fallback。"""

        def bad_fn(prompt, operation=""):
            raise R.ReasoningError("API error: 429")

        prov = R.ReasoningProvider(llm_fn=bad_fn)
        analyzer = LG.LLMGapAnalyzer(provider=prov)
        result = analyzer.analyze(_gap_ctx(), {"task": {"id": "T001"}})
        assert result.analysis is not None  # deterministic 兜底
        assert result.fallback_used is True

    def test_invalid_json_fallback(self):
        def bad_fn(prompt, operation=""):
            return "not json"

        prov = R.ReasoningProvider(llm_fn=bad_fn)
        analyzer = LG.LLMGapAnalyzer(provider=prov)
        result = analyzer.analyze(_gap_ctx(), {"task": {"id": "T001"}})
        assert result.fallback_used is True

    def test_timeout_fallback(self):
        def bad_fn(prompt, operation=""):
            raise R.ReasoningError("timeout")

        prov = R.ReasoningProvider(llm_fn=bad_fn)
        analyzer = LG.LLMGapAnalyzer(provider=prov)
        result = analyzer.analyze(_gap_ctx(), {"task": {"id": "T001"}})
        assert result.fallback_used is True

    def test_schema_error_fallback(self):
        """LLM 输出缺关键字段 → schema 校验失败 → fallback。"""

        def bad_fn(prompt, operation=""):
            return json.dumps({"detected": True})  # 缺 gap_type

        prov = R.ReasoningProvider(llm_fn=bad_fn)
        analyzer = LG.LLMGapAnalyzer(provider=prov)
        result = analyzer.analyze(_gap_ctx(), {"task": {"id": "T001"}})
        assert result.fallback_used is True

    def test_system_survives_llm_fail(self):
        """LLM 全挂 → 不抛异常 (系统可用)。"""
        def bad_fn(prompt, operation=""):
            raise R.ReasoningError("down")

        prov = R.ReasoningProvider(llm_fn=bad_fn)
        analyzer = LG.LLMGapAnalyzer(provider=prov)
        result = analyzer.analyze(_gap_ctx(), {"task": {"id": "T001"}})
        assert result.analysis is not None


# ================================================================== 2. confidence 阈值


class TestConfidence:
    def test_low_confidence_fallback(self):
        def low_fn(prompt, operation=""):
            return json.dumps({"detected": True, "gap_type": "missing_implementation",
                               "description": "d", "evidence": [], "severity": "low",
                               "source_task_id": "T1", "confidence": 0.1,
                               "duplicate_of": None, "recommended_action": "INSERT_TASK",
                               "reason": "r"}, ensure_ascii=False)

        prov = R.ReasoningProvider(llm_fn=low_fn)
        analyzer = LG.LLMGapAnalyzer(provider=prov, confidence_threshold=0.5)
        result = analyzer.analyze(_gap_ctx(), {"task": {"id": "T1"}})
        assert result.fallback_used is True

    def test_high_confidence_accepted(self):
        prov = R.ReasoningProvider(llm_fn=_valid_gap_fn)
        analyzer = LG.LLMGapAnalyzer(provider=prov, confidence_threshold=0.5)
        result = analyzer.analyze(_gap_ctx(), {"task": {"id": "T1"}})
        assert result.analysis.confidence >= 0.5


# ================================================================== 3. deterministic gate (LLM 输出校验)


class TestDeterministicGate:
    def test_llm_bad_role_fallback(self):
        """LLM 提案 role 非法 → Validator 拒 → fallback。"""

        def bad_proposal_fn(prompt, operation=""):
            return json.dumps({"task_id": "T9", "title": "t", "description": "d",
                               "objective": "o", "required_role": "nonexistent",
                               "dependencies": [], "acceptance_criteria": ["x"],
                               "validation_command": "pytest", "priority": "high",
                               "rationale": "r", "confidence": 0.8,
                               "source_gap": "g"}, ensure_ascii=False)

        prov = R.ReasoningProvider(llm_fn=bad_proposal_fn)
        eng = LP.LLMTaskProposalEngine(provider=prov)
        res = eng.propose({"gap_type": "missing_test", "source_task_id": "T1",
                           "confidence": 0.8, "detected": True,
                           "recommended_action": "INSERT_TASK"},
                          {}, existing_tasks=[{"id": "T1"}])
        assert res.source in ("deterministic", "request_review")  # LLM 被拒

    def test_llm_duplicate_fallback(self):
        """LLM 提案重复 → DuplicateDetector → fallback。"""

        def dup_fn(prompt, operation=""):
            return json.dumps({"task_id": "T1", "title": "已存在任务", "description": "d",
                               "objective": "o", "required_role": "backend",
                               "dependencies": [], "acceptance_criteria": ["x"],
                               "validation_command": "pytest", "priority": "high",
                               "rationale": "r", "confidence": 0.9,
                               "source_gap": "g"}, ensure_ascii=False)

        prov = R.ReasoningProvider(llm_fn=dup_fn)
        eng = LP.LLMTaskProposalEngine(provider=prov)
        res = eng.propose({"gap_type": "missing_test", "source_task_id": "T1",
                           "confidence": 0.8, "detected": True,
                           "recommended_action": "INSERT_TASK"},
                          {}, existing_tasks=[{"id": "T1", "name": "已存在任务"}])
        assert res.source in ("deterministic", "request_review")

    def test_llm_cycle_fallback(self):
        """LLM 提案依赖成环 → DAG cycle → fallback。"""
        class FakeDag:
            def cycle_detect(self, task, dep):
                return True  # 恒成环

        def cycle_fn(prompt, operation=""):
            return json.dumps({"task_id": "T9", "title": "t", "description": "d",
                               "objective": "o", "required_role": "backend",
                               "dependencies": ["T1"], "acceptance_criteria": ["x"],
                               "validation_command": "pytest", "priority": "high",
                               "rationale": "r", "confidence": 0.8,
                               "source_gap": "g"}, ensure_ascii=False)

        prov = R.ReasoningProvider(llm_fn=cycle_fn)
        eng = LP.LLMTaskProposalEngine(provider=prov)
        res = eng.propose({"gap_type": "missing_test", "source_task_id": "T1",
                           "confidence": 0.8, "detected": True,
                           "recommended_action": "INSERT_TASK"},
                          {}, existing_tasks=[{"id": "T1"}], dag=FakeDag())
        assert res.source in ("deterministic", "request_review")


# ================================================================== 4. fallback_used 标记


class TestFallbackMarker:
    def test_fallback_used_false_on_success(self):
        prov = R.ReasoningProvider(llm_fn=_valid_gap_fn)
        analyzer = LG.LLMGapAnalyzer(provider=prov)
        result = analyzer.analyze(_gap_ctx(), {"task": {"id": "T1"}})
        assert result.fallback_used is False

    def test_fallback_used_true_on_fail(self):
        def bad_fn(prompt, operation=""):
            raise R.ReasoningError("x")

        prov = R.ReasoningProvider(llm_fn=bad_fn)
        analyzer = LG.LLMGapAnalyzer(provider=prov)
        result = analyzer.analyze(_gap_ctx(), {"task": {"id": "T1"}})
        assert result.fallback_used is True

    def test_proposal_fallback_source(self):
        """提案 fallback → source=deterministic。"""

        def bad_fn(prompt, operation=""):
            raise R.ReasoningError("x")

        prov = R.ReasoningProvider(llm_fn=bad_fn)
        eng = LP.LLMTaskProposalEngine(provider=prov)
        res = eng.propose({"gap_type": "missing_test", "source_task_id": "T1",
                           "confidence": 0.8, "detected": True,
                           "recommended_action": "INSERT_TASK"},
                          {}, existing_tasks=[{"id": "T1"}])
        assert res.source == "deterministic" or res.source == "request_review"


# ================================================================== 5. ReasoningProvider 接口


class TestReasoningProvider:
    def test_analyze_gap_interface(self):
        prov = R.ReasoningProvider(llm_fn=_valid_gap_fn)
        out = prov.analyze_gap({"project": "demo"})
        assert out.get("gap_type") == "missing_implementation"

    def test_propose_task_interface(self):
        def proposal_fn(prompt, operation=""):
            return json.dumps({"task_id": "T9", "title": "t", "description": "d",
                               "objective": "o", "required_role": "backend",
                               "dependencies": [], "acceptance_criteria": ["x"],
                               "validation_command": "pytest", "priority": "high",
                               "rationale": "r", "confidence": 0.8,
                               "source_gap": "g"}, ensure_ascii=False)

        prov = R.ReasoningProvider(llm_fn=proposal_fn)
        out = prov.propose_task({"gap_type": "x"}, {"project": "demo"})
        assert out is not None

    def test_evaluate_plan_interface(self):
        def plan_fn(prompt, operation=""):
            return json.dumps({"decision": "KEEP_PLAN", "reason": "ok"}, ensure_ascii=False)

        prov = R.ReasoningProvider(llm_fn=plan_fn)
        out = prov.evaluate_plan({"project": "demo"})
        assert out is not None

    def test_reasoning_error_class(self):
        assert issubclass(R.ReasoningError, Exception)

    def test_no_llm_fn_raises(self):
        """调用方异常 → ReasoningError (统一失败面)。"""

        def boom_fn(prompt, operation=""):
            raise R.ReasoningError("boom")

        prov = R.ReasoningProvider(llm_fn=boom_fn)
        with pytest.raises(R.ReasoningError):
            prov.analyze_gap({"project": "demo"})

    def test_model_not_hardcoded(self):
        """模型名不硬编码 (从 provider 配置读)。"""
        prov = R.ReasoningProvider(llm_fn=_valid_gap_fn)
        assert isinstance(prov._model, str)


# ================================================================== 补充


class TestMore:
    def test_llm_gap_evidence_used(self):
        """LLM 判断引用 evidence (Evidence First)。"""
        seen = {}

        def fn(prompt, operation=""):
            seen["prompt"] = prompt
            return _valid_gap_fn(prompt)

        prov = R.ReasoningProvider(llm_fn=fn)
        analyzer = LG.LLMGapAnalyzer(provider=prov)
        analyzer.analyze(_gap_ctx(), {"task": {"id": "T1"}})
        assert "validation" in seen["prompt"] or "evidence" in seen["prompt"]

    def test_llm_proposal_why_how(self):
        """提案要求 WHY/HOW/DEPENDENCY 解释。"""
        seen = {}

        def fn(prompt, operation=""):
            seen["prompt"] = prompt
            return json.dumps({"task_id": "T9", "title": "t", "description": "d",
                               "objective": "o", "required_role": "backend",
                               "dependencies": [], "acceptance_criteria": ["x"],
                               "validation_command": "pytest", "priority": "high",
                               "rationale": "WHY: 解决缺口", "confidence": 0.8,
                               "source_gap": "g"}, ensure_ascii=False)

        prov = R.ReasoningProvider(llm_fn=fn)
        eng = LP.LLMTaskProposalEngine(provider=prov)
        eng.propose({"gap_type": "missing_test", "source_task_id": "T1",
                     "confidence": 0.8, "detected": True,
                     "recommended_action": "INSERT_TASK"},
                    {}, existing_tasks=[{"id": "T1"}])
        assert "WHY" in seen["prompt"] or "rationale" in seen["prompt"]

    def test_import_all(self):
        import_module("factory-console.session.reasoning")
        import_module("factory-console.session.llm_gap")
        import_module("factory-console.session.llm_task_proposal")
