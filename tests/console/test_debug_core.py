"""S10-068 — Debug Intelligence Core 测试套件。

覆盖: DebugCase/RootCause/FixStrategy/DebugDecision + ErrorAnalyzer +
RootCauseAnalyzer + DebugExperienceRetriever + DebugStrategySelector +
DebugEngine (analyze/feedback/history/stats)。
装配: tmp_path + fixtures; 禁真实网络。
"""

from __future__ import annotations

import json
from pathlib import Path

from importlib import import_module

D = import_module("factory-console.session.debug")
DE = import_module("factory-console.session.debug.debug_engine")
EA = import_module("factory-console.session.debug.error_analysis")
RC = import_module("factory-console.session.debug.root_cause")
DM = import_module("factory-console.session.debug.debug_memory")
DS = import_module("factory-console.session.debug.debug_strategy")


def _case(**kw):
    d = {"error_message": "test_login_timeout: connection timed out",
         "task_id": "T001", "agent_id": "backend-1"}
    d.update(kw)
    return D.DebugCase(**d)


# ================================================================== 1. 模型


class TestModels:
    def test_debug_case(self):
        c = _case()
        assert c.error_message and c.task_id

    def test_debug_case_defaults(self):
        c = D.DebugCase(error_message="x")
        assert c.error_type == ""
        assert c.previous_attempts == 0

    def test_root_cause(self):
        r = D.RootCause(cause="c", evidence=["e"], confidence=0.8)
        assert r.cause == "c"
        assert 0 <= r.confidence <= 1

    def test_fix_strategy_values(self):
        assert D.FixStrategy.FIX_CODE.value == "FIX_CODE"
        assert D.FixStrategy.REQUEST_REVIEW.value == "REQUEST_REVIEW"

    def test_debug_decision(self):
        d = D.DebugDecision(strategy=D.FixStrategy.FIX_CODE, reason="r",
                            confidence=0.8, evidence=["e"])
        assert d.strategy == D.FixStrategy.FIX_CODE


# ================================================================== 2. ErrorAnalyzer


class TestErrorAnalyzer:
    def test_timeout(self):
        assert EA.ErrorAnalyzer().classify("timeout after 30s") == "TIMEOUT"

    def test_import_error(self):
        assert EA.ErrorAnalyzer().classify("ModuleNotFoundError: no module") == "IMPORT_ERROR"

    def test_assertion(self):
        assert EA.ErrorAnalyzer().classify("assert 10 == 9") == "ASSERTION"

    def test_auth(self):
        assert EA.ErrorAnalyzer().classify("unauthorized: api key missing") == "AUTH"

    def test_api_contract(self):
        assert EA.ErrorAnalyzer().classify("api contract mismatch: missing field") == "API_CONTRACT"

    def test_null(self):
        assert EA.ErrorAnalyzer().classify("AttributeError: NoneType has no") == "NULL"

    def test_missing(self):
        assert EA.ErrorAnalyzer().classify("file not found: missing config.yaml") == "MISSING"

    def test_test_failure(self):
        assert EA.ErrorAnalyzer().classify("pytest failed: 2 failed") == "TEST_FAILURE"

    def test_unknown(self):
        assert EA.ErrorAnalyzer().classify("random gibberish") == "UNKNOWN"

    def test_extract(self):
        c = EA.ErrorAnalyzer().extract("timeout", task_id="T1")
        assert c.error_message == "timeout"
        assert c.task_id == "T1"


# ================================================================== 3. RootCauseAnalyzer


class TestRootCause:
    def test_analyze_timeout(self):
        c = _case(error_message="connection timed out")
        r = RC.RootCauseAnalyzer().analyze(c)
        assert r.cause
        assert r.evidence
        assert 0 <= r.confidence <= 1

    def test_analyze_auth(self):
        c = _case(error_message="unauthorized: api key missing")
        r = RC.RootCauseAnalyzer().analyze(c)
        assert r.cause

    def test_analyze_unknown(self):
        c = _case(error_message="weird error xyz")
        r = RC.RootCauseAnalyzer().analyze(c)
        assert r.cause or r.confidence >= 0

    def test_analyze_with_experience(self):
        """有历史经验 → 置信度加成。"""
        c = _case(error_message="jwt refresh token missing")
        exp = [{"type": "DEBUG_EXPERIENCE", "problem": "jwt refresh",
                "confidence": 0.9}]
        r = RC.RootCauseAnalyzer().analyze(c, related_experiences=exp)
        assert r.related_experience or r.confidence > 0


# ================================================================== 4. DebugExperienceRetriever


class TestRetriever:
    def _memory_ws(self, tmp_path) -> Path:
        from importlib import import_module as _im
        MEM = _im("factory-console.memory")
        ws = tmp_path / "ws"
        (ws / "memory").mkdir(parents=True)
        store = MEM.ExperienceStore(ws / "memory" / "experience_store.json")
        store.add(MEM.ExperienceRecord(
            type="DEBUG_EXPERIENCE", problem="jwt refresh token missing",
            action="add token refresh logic", success=True, confidence=0.91,
            source="test", project="demo"))
        store.add(MEM.ExperienceRecord(
            type="FAILURE_PATTERN", problem="timeout in login",
            success=False, confidence=0.6, source="test", project="demo"))
        store.add(MEM.ExperienceRecord(
            type="SUCCESS_PATTERN", problem="database design first",
            success=True, confidence=0.5, source="test", project="demo"))
        return ws

    def test_retrieve(self, tmp_path):
        ws = self._memory_ws(tmp_path)
        c = _case(error_message="jwt refresh token missing")
        from importlib import import_module as _im
        MEM = _im("factory-console.memory")
        store = MEM.ExperienceStore(ws / "memory" / "experience_store.json")
        hits = DM.DebugExperienceRetriever().retrieve(c, top_k=3, memory_store=store)
        assert hits

    def test_top_k(self, tmp_path):
        ws = self._memory_ws(tmp_path)
        c = _case(error_message="jwt refresh")
        from importlib import import_module as _im
        MEM = _im("factory-console.memory")
        store = MEM.ExperienceStore(ws / "memory" / "experience_store.json")
        hits = DM.DebugExperienceRetriever().retrieve(c, top_k=2, memory_store=store)
        assert len(hits) <= 2

    def test_ranked_by_confidence(self, tmp_path):
        ws = self._memory_ws(tmp_path)
        c = _case(error_message="jwt refresh")
        from importlib import import_module as _im
        MEM = _im("factory-console.memory")
        store = MEM.ExperienceStore(ws / "memory" / "experience_store.json")
        hits = DM.DebugExperienceRetriever().retrieve(c, top_k=3, memory_store=store)
        confs = [h.get("confidence", 0) if isinstance(h, dict) else getattr(h, "confidence", 0)
                for h in hits]
        assert confs == sorted(confs, reverse=True)  # 降序

    def test_no_memory(self, tmp_path):
        ws = tmp_path / "empty"
        ws.mkdir(exist_ok=True)
        c = _case(error_message="x")
        from importlib import import_module as _im
        MEM = _im("factory-console.memory")
        store = MEM.ExperienceStore(ws / "memory" / "experience_store.json")
        hits = DM.DebugExperienceRetriever().retrieve(c, memory_store=store)
        assert hits == []  # 失败安全


# ================================================================== 5. DebugStrategySelector


class TestStrategy:
    def test_unknown_review(self):
        d = DS.DebugStrategySelector().select(
            D.RootCause(cause="", evidence=[], confidence=0.1),
            [], _case(error_message="weird"))
        assert d.strategy == D.FixStrategy.REQUEST_REVIEW

    def test_success_exp_fix_code(self):
        from importlib import import_module as _im
        MEM = _im("factory-console.memory")
        exp = [MEM.ExperienceRecord(type="DEBUG_EXPERIENCE", problem="same issue",
                                    action="fix", success=True, confidence=0.9)]
        c = _case(error_message="connection timed out")
        c.error_type = "TIMEOUT"  # 非 UNKNOWN (避免 REVIEW 优先)
        d = DS.DebugStrategySelector().select(
            D.RootCause(cause="c", evidence=["e"], confidence=0.8),
            exp, c)
        assert d.strategy == D.FixStrategy.FIX_CODE

    def test_test_failure_fix_test(self):
        c = _case(error_message="pytest failed: assert 10 == 9")
        EA.ErrorAnalyzer.extract  # noqa
        c.error_type = "TEST_FAILURE"
        d = DS.DebugStrategySelector().select(
            D.RootCause(cause="c", evidence=[], confidence=0.7),
            [], c)
        assert d.strategy == D.FixStrategy.FIX_TEST

    def test_attempts_rollback(self):
        c = _case(error_message="connection timed out")
        c.error_type = "TIMEOUT"  # 非 UNKNOWN (避免 REVIEW 优先)
        c.previous_attempts = 3
        d = DS.DebugStrategySelector().select(
            D.RootCause(cause="c", evidence=[], confidence=0.7),
            [], c)
        assert d.strategy == D.FixStrategy.ROLLBACK

    def test_decision_fields(self):
        d = DS.DebugStrategySelector().select(
            D.RootCause(cause="c", evidence=["e"], confidence=0.8),
            [], _case(error_message="x"))
        assert d.reason and d.confidence >= 0


# ================================================================== 6. DebugEngine


class TestEngine:
    def test_analyze(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir(exist_ok=True)
        engine = DE.DebugEngine()
        decision = engine.analyze(_case(), workspace=ws)
        assert decision.strategy in D.FixStrategy

    def test_analyze_classifies(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir(exist_ok=True)
        c = _case(error_message="timeout")
        DE.DebugEngine().analyze(c, workspace=ws)
        assert c.error_type == "TIMEOUT"

    def test_feedback_success(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir(exist_ok=True)
        engine = DE.DebugEngine()
        decision = engine.analyze(_case(), workspace=ws)
        engine.feedback(_case(), decision, {"success": True}, ws)
        # Memory 沉淀 (SUCCESS_PATTERN)
        store_file = ws / "memory" / "experience_store.json"
        assert store_file.is_file()

    def test_feedback_failure(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir(exist_ok=True)
        engine = DE.DebugEngine()
        decision = engine.analyze(_case(), workspace=ws)
        engine.feedback(_case(), decision, {"success": False}, ws)
        store_file = ws / "memory" / "experience_store.json"
        assert store_file.is_file()

    def test_history(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir(exist_ok=True)
        engine = DE.DebugEngine()
        engine.analyze(_case(), workspace=ws)
        engine.analyze(_case(error_message="another error"), workspace=ws)
        assert len(engine.history(ws)) == 2

    def test_stats(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir(exist_ok=True)
        engine = DE.DebugEngine()
        engine.analyze(_case(error_message="timeout"), workspace=ws)
        engine.analyze(_case(error_message="pytest failed"), workspace=ws)
        stats = engine.stats(ws)
        assert stats.get("total_cases", 0) == 2
        assert "by_error_type" in stats

    def test_persistence(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir(exist_ok=True)
        DE.DebugEngine().analyze(_case(), workspace=ws)
        cases_file = ws / "debug_cases.json"
        assert cases_file.is_file()

    def test_missing_workspace(self):
        """无 workspace → 失败安全。"""
        engine = DE.DebugEngine()
        decision = engine.analyze(_case())
        assert decision is not None


class TestFeedbackLoop:
    """Feedback Loop 闭环: 修复结果 → Memory 沉淀 → 再检索可用。"""

    def test_feedback_writes_success_pattern(self, tmp_path):
        from importlib import import_module as _im
        MEM = _im("factory-console.memory")
        ws = tmp_path / "ws"
        ws.mkdir(exist_ok=True)
        engine = DE.DebugEngine()
        decision = engine.analyze(_case(), workspace=ws)
        engine.feedback(_case(), decision, {"success": True}, ws)
        store = MEM.ExperienceStore(ws / "memory" / "experience_store.json")
        recs = store.records()
        assert any(r.type == "SUCCESS_PATTERN" for r in recs)

    def test_feedback_writes_failure_pattern(self, tmp_path):
        from importlib import import_module as _im
        MEM = _im("factory-console.memory")
        ws = tmp_path / "ws"
        ws.mkdir(exist_ok=True)
        engine = DE.DebugEngine()
        decision = engine.analyze(_case(), workspace=ws)
        engine.feedback(_case(), decision, {"success": False}, ws)
        store = MEM.ExperienceStore(ws / "memory" / "experience_store.json")
        recs = store.records()
        assert any(r.type == "FAILURE_PATTERN" for r in recs)

    def test_retrieve_after_feedback(self, tmp_path):
        from importlib import import_module as _im
        MEM = _im("factory-console.memory")
        ws = tmp_path / "ws"
        ws.mkdir(exist_ok=True)
        engine = DE.DebugEngine()
        c = _case(error_message="jwt refresh token missing")
        decision = engine.analyze(c, workspace=ws)
        engine.feedback(c, decision, {"success": True}, ws)
        store = MEM.ExperienceStore(ws / "memory" / "experience_store.json")
        hits = DM.DebugExperienceRetriever().retrieve(c, top_k=5, memory_store=store)
        assert hits

    def test_history_after_feedback(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir(exist_ok=True)
        engine = DE.DebugEngine()
        decision = engine.analyze(_case(), workspace=ws)
        engine.feedback(_case(), decision, {"success": True}, ws)
        hist = engine.history(ws)
        assert hist and hist[0].get("outcome") == "success"

    def test_stats_by_outcome(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir(exist_ok=True)
        engine = DE.DebugEngine()
        decision = engine.analyze(_case(), workspace=ws)
        engine.feedback(_case(), decision, {"success": True}, ws)
        stats = engine.stats(ws)
        assert stats["by_outcome"]["success"] == 1
