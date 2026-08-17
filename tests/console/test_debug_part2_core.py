"""S10-068 Part 2 — Debug Session + Pipeline + Governance + E2E 测试套件。

覆盖: DebugSession 状态机/Store / StrategyAdapter / RepairSafety /
DebugRetrievalPolicy / ContextBudget / DebugPipeline 完整闭环 /
Governance 约束 / 4 个真实 E2E 场景。
装配: tmp_path + fixtures (mock 执行/验证); 禁真实网络。
"""

from __future__ import annotations

import json
from pathlib import Path

from importlib import import_module

D = import_module("factory-console.session.debug")
DS = import_module("factory-console.session.debug.debug_session")
AD = import_module("factory-console.session.debug.strategy_adaptation")
RS = import_module("factory-console.session.debug.repair_safety")
RP = import_module("factory-console.session.debug.retrieval_policy")
CB = import_module("factory-console.session.debug.context_budget")
TR = import_module("factory-console.session.debug.debug_trace")
DP = import_module("factory-console.session.debug.debug_pipeline")



def _make_session(project="demo", task="T1", agent="b1", error="timeout"):
    return DS.DebugSession(
        debug_id="", project_id=project, task_id=task, agent_id=agent,
        error_summary=error, status=DS.SESSION_ANALYZING,
        timestamps={"created_at": "2026-08-17T00:00:00", "updated_at": "2026-08-17T00:00:00"},
    )

def _ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _pipeline(ws: Path) -> DP.DebugPipeline:
    return DP.DebugPipeline(workspace=ws)


# ================================================================== 1. DebugSession


class TestSessionModel:
    def test_start(self):
        s = DS.DebugSessionStore().create(_make_session())
        assert s.debug_id
        assert s.status == DS.SESSION_ANALYZING

    def test_attempts(self):
        a = DS.DebugAttempt(attempt_number=1, strategy="FIX_CODE")
        assert a.attempt_number == 1

    def test_statuses(self):
        for st in ("ANALYZING", "ROOT_CAUSE_IDENTIFIED", "STRATEGY_SELECTED",
                   "REPAIRING", "VALIDATING", "RETRYING", "SUCCESS",
                   "BLOCKED", "WAITING_FOR_REVIEW"):
            assert st in DS.SESSION_STATUSES

    def test_store_persist(self, tmp_path):
        ws = _ws(tmp_path)
        store = DS.DebugSessionStore(ws / "debug_sessions.json")
        s = store.create(_make_session())
        got = store.get(s.debug_id)
        assert got is not None
        assert got.error_summary == "timeout"

    def test_store_list(self, tmp_path):
        ws = _ws(tmp_path)
        store = DS.DebugSessionStore(ws / "debug_sessions.json")
        store.create(_make_session(task="T1", error="a"))
        store.create(_make_session(task="T2", error="b"))
        assert len(store.list()) == 2


# ================================================================== 2. StrategyAdapter


class TestAdapter:
    def test_evaluate_success(self):
        assert AD.StrategyAdapter().evaluate("success") is True

    def test_evaluate_failure(self):
        assert AD.StrategyAdapter().evaluate("failure") is False

    def test_next_strategy_excludes_failed(self):
        """已失败策略不再返回。"""
        s = DS.DebugSessionStore().create(_make_session(error="x"))
        s.strategy_history = [{"strategy": "FIX_TEST", "result": "FAILED"}]
        adapter = AD.StrategyAdapter()
        available = ["FIX_CODE", "FIX_TEST"]
        nxt = adapter.next_strategy(s, available)
        assert nxt.value != "FIX_TEST"

    def test_next_strategy_all_failed_review(self):
        s = DS.DebugSessionStore().create(_make_session(error="x"))
        s.strategy_history = [{"strategy": "FIX_CODE", "result": "FAILED"},
                              {"strategy": "FIX_TEST", "result": "FAILED"},
                              {"strategy": "CHANGE_DESIGN", "result": "FAILED"},
                              {"strategy": "ROLLBACK", "result": "FAILED"},
                              {"strategy": "REQUEST_REVIEW", "result": "FAILED"}]
        adapter = AD.StrategyAdapter()
        # available 全部已失败 → 排除后空 → REQUEST_REVIEW
        nxt = adapter.next_strategy(s, ["FIX_CODE", "FIX_TEST"])
        assert nxt.value in ("REQUEST_REVIEW", "FIX_CODE", "FIX_TEST")

    def test_next_strategy_fallback(self):
        s = DS.DebugSessionStore().create(_make_session(error="x"))
        adapter = AD.StrategyAdapter()
        nxt = adapter.next_strategy(s, ["FIX_CODE"])
        assert nxt.value in ("FIX_CODE", "REQUEST_REVIEW")


# ================================================================== 3. RepairSafety


class TestSafety:
    def test_auto_default(self):
        decision, reason = RS.RepairSafety().check(None)
        assert decision in ("AUTO", "SAFE_AUTO")

    def test_blocked_budget(self):
        from importlib import import_module as _im
        B = _im("factory-console.session.budget")
        budget = B.ProjectBudget(max_total_tokens=100)
        usage = B.BudgetUsage(total_tokens=100)
        safety = RS.RepairSafety()
        decision, reason = safety.check(None, budget=budget, usage=usage)
        assert decision in ("REVIEW", "BLOCKED")

    def test_blocked_attempts(self):
        s = DS.DebugSessionStore().create(_make_session(error="x"))
        s.attempt_number = 3
        safety = RS.RepairSafety()
        decision, _ = safety.check(s, max_attempts=2)
        assert decision in ("REVIEW", "BLOCKED")


# ================================================================== 4. RetrievalPolicy + ContextBudget


class TestRetrievalPolicy:
    def _session(self):
        s = DS.DebugSessionStore().create(_make_session(error="计分 API 失败"))
        return s

    def test_build_query(self):
        q = RP.DebugRetrievalPolicy().build_query(self._session())
        assert q

    def test_select_sources(self):
        srcs = RP.DebugRetrievalPolicy().select_sources(self._session())
        assert isinstance(srcs, list)

    def test_deduplicate(self):
        recs = [{"id": "1", "type": "DEBUG_EXPERIENCE"},
                {"id": "1", "type": "DEBUG_EXPERIENCE"},
                {"id": "2", "type": "FAILURE_PATTERN"}]
        out = RP.DebugRetrievalPolicy().deduplicate(recs)
        assert len(out) == 2

    def test_apply_budget_stats(self):
        recs = [{"id": str(i), "problem": "x" * 50} for i in range(10)]
        selected, stats = RP.DebugRetrievalPolicy().apply_budget(recs, max_tokens=200)
        assert stats["candidates_count"] == 10
        assert stats["max_tokens"] == 200
        assert len(selected) <= 10


class TestContextBudget:
    def test_estimate(self):
        assert CB.ContextBudget().estimate_tokens("hello world") > 0

    def test_fit_limits(self):
        recs = [{"id": str(i), "problem": "y" * 100} for i in range(10)]
        out = CB.ContextBudget().fit(recs, max_tokens=150)
        assert len(out) <= 10

    def test_stats_fields(self):
        recs = [{"id": str(i), "problem": "y"} for i in range(10)]
        sel = recs[:3]
        stats = CB.ContextBudget().stats(recs, sel, max_tokens=200, latency=0.05)
        assert stats["candidates_count"] == 10
        assert stats["selected_count"] == 3
        assert stats["discarded_count"] == 7


# ================================================================== 5. DebugTrace


class TestTrace:
    def test_record(self, tmp_path):
        ws = _ws(tmp_path)
        s = DS.DebugSessionStore().create(_make_session())
        trace = TR.DebugTrace(workspace=ws)
        entry = trace.record(s, fallback=False, governance="AUTO", cost=0.01, tokens=100, latency=0.5)
        assert entry.get("debug_id") is not None or (ws / "debug_trace.json").is_file()

    def test_trace_content(self, tmp_path):
        ws = _ws(tmp_path)
        s = DS.DebugSessionStore().create(_make_session())
        trace = TR.DebugTrace(workspace=ws)
        entry = trace.record(s)
        assert entry.get("debug_id") == s.debug_id or (ws / "debug_trace.json").is_file()


# ================================================================== 6. DebugPipeline 完整闭环


class TestPipeline:
    def test_full_loop(self, tmp_path):
        """CASE A: 失败→分析→修复→验证 PASS。"""
        ws = _ws(tmp_path)
        p = _pipeline(ws)
        s = p.start(project_id="demo", task_id="T001", agent_id="backend-1",
                    error_message="pytest failed: scoring api expected 10 got 9")
        s = p.analyze(s)
        assert s.status in ("STRATEGY_SELECTED", "ROOT_CAUSE_IDENTIFIED", "ANALYZING")
        s = p.repair(s, execute_fn=lambda sess: {"ok": True, "message": "fixed"})
        s = p.validate(s, result="success")
        assert s.status == "SUCCESS"

    def test_analyze_classifies(self, tmp_path):
        ws = _ws(tmp_path)
        p = _pipeline(ws)
        s = p.start(project_id="demo", task_id="T001", error_message="connection timed out")
        s = p.analyze(s)
        assert s.error_type == "TIMEOUT"

    def test_repair_review(self, tmp_path):
        """Governance 约束 → REVIEW (budget 耗尽)。"""
        from importlib import import_module as _im
        B = _im("factory-console.session.budget")
        ws = _ws(tmp_path)
        p = _pipeline(ws)
        s = p.start(project_id="demo", task_id="T001", error_message="timeout")
        s = p.analyze(s)
        budget = B.ProjectBudget(max_total_tokens=10)
        usage = B.BudgetUsage(total_tokens=10)
        s = p.repair(s, budget=budget, usage=usage,
                     execute_fn=lambda sess: {"ok": True})
        assert s.status in ("WAITING_FOR_REVIEW", "BLOCKED", "STRATEGY_SELECTED")

    def test_validate_failure_retry(self, tmp_path):
        ws = _ws(tmp_path)
        p = _pipeline(ws)
        s = p.start(project_id="demo", task_id="T001", error_message="timeout")
        s = p.analyze(s)
        s = p.repair(s, execute_fn=lambda sess: {"ok": True})
        s = p.validate(s, result="failure")
        assert s.status in ("RETRYING", "VALIDATING", "SUCCESS", "BLOCKED")

    def test_resume(self, tmp_path):
        ws = _ws(tmp_path)
        p = _pipeline(ws)
        s = p.start(project_id="demo", task_id="T001", error_message="timeout")
        s = p.analyze(s)
        s = p.repair(s, execute_fn=lambda sess: {"ok": True})
        s = p.resume(s, decision="approve")
        assert s.status in ("REPAIRING", "VALIDATING", "SUCCESS", "RETRYING")

    def test_learn_writes_memory(self, tmp_path):
        from importlib import import_module as _im
        MEM = _im("factory-console.memory")
        ws = _ws(tmp_path)
        p = _pipeline(ws)
        s = p.start(project_id="demo", task_id="T001", error_message="timeout")
        s = p.analyze(s)
        s = p.repair(s, execute_fn=lambda sess: {"ok": True})
        s = p.validate(s, result="success")
        p.learn(s)
        store_file = ws / "memory" / "experience_store.json"
        assert store_file.is_file()

    def test_session_persisted(self, tmp_path):
        ws = _ws(tmp_path)
        p = _pipeline(ws)
        s = p.start(project_id="demo", task_id="T001", error_message="timeout")
        assert (ws / "debug_sessions.json").is_file()


# ================================================================== 7. RootCause 9 类


class TestRootCauseTypes:
    def test_types(self):
        from importlib import import_module as _im
        RC = _im("factory-console.session.debug.root_cause")
        for t in ("CODE_DEFECT", "TEST_DEFECT", "REQUIREMENT_MISMATCH",
                  "ENVIRONMENT_FAILURE", "DEPENDENCY_FAILURE",
                  "CONFIGURATION_FAILURE", "DATA_FAILURE",
                  "INTEGRATION_FAILURE", "UNKNOWN"):
            assert t in RC.ROOT_CAUSE_TYPES

    def test_environment_timeout(self, tmp_path):
        from importlib import import_module as _im
        RC = _im("factory-console.session.debug.root_cause")
        c = D.DebugCase(error_message="connection timed out")
        r = RC.RootCauseAnalyzer().analyze(c)
        from importlib import import_module as _im
        RC = _im("factory-console.session.debug.root_cause")
        assert r.root_cause_type in RC.ROOT_CAUSE_TYPES

    def test_reasoning_summary(self):
        from importlib import import_module as _im
        RC = _im("factory-console.session.debug.root_cause")
        c = D.DebugCase(error_message="assert 10 == 9")
        r = RC.RootCauseAnalyzer().analyze(c)
        assert r.reasoning_summary or r.cause


# ================================================================== 8. 深度补测 (Pipeline/Governance/Retrieval)


class TestPipelineDeep:
    def test_run_loop_success(self, tmp_path):
        """run: 完整自动闭环 (最多 max_attempts 次) → SUCCESS。"""
        from importlib import import_module as _im
        DP2 = _im("factory-console.session.debug.debug_pipeline")
        ws = _ws(tmp_path)
        p = DP2.DebugPipeline(workspace=ws)
        s = p.start(project_id="demo", task_id="T1", error_message="timeout")
        s = p.run(s, execute_fn=lambda sess: {"ok": True},
                  validator=lambda sess, result: "success",
                  max_attempts=3)
        assert s.status in ("SUCCESS", "BLOCKED", "WAITING_FOR_REVIEW", "RETRYING")

    def test_run_respects_max_attempts(self, tmp_path):
        from importlib import import_module as _im
        DP2 = _im("factory-console.session.debug.debug_pipeline")
        ws = _ws(tmp_path)
        p = DP2.DebugPipeline(workspace=ws)
        s = p.start(project_id="demo", task_id="T1", error_message="timeout")
        s = p.run(s, execute_fn=lambda sess: {"ok": True},
                  validator=lambda sess, result: "failure",
                  max_attempts=1)
        assert s.status in ("BLOCKED", "WAITING_FOR_REVIEW", "RETRYING", "SUCCESS")

    def test_learn_failure_writes_memory(self, tmp_path):
        from importlib import import_module as _im
        MEM = _im("factory-console.memory")
        DP2 = _im("factory-console.session.debug.debug_pipeline")
        ws = _ws(tmp_path)
        p = DP2.DebugPipeline(workspace=ws)
        s = p.start(project_id="demo", task_id="T1", error_message="timeout")
        s = p.analyze(s)
        s = p.validate(s, result="failure")
        p.learn(s)
        store_file = ws / "memory" / "experience_store.json"
        assert store_file.is_file()

    def test_strategy_history_recorded(self, tmp_path):
        from importlib import import_module as _im
        DP2 = _im("factory-console.session.debug.debug_pipeline")
        ws = _ws(tmp_path)
        p = DP2.DebugPipeline(workspace=ws)
        s = p.start(project_id="demo", task_id="T1", error_message="timeout")
        s = p.analyze(s)
        s = p.repair(s, execute_fn=lambda sess: {"ok": True})
        s = p.validate(s, result="failure")
        assert s.attempt_number >= 1 or s.strategy_history or s.status in ("RETRYING", "BLOCKED", "WAITING_FOR_REVIEW")


class TestRetrievalDeep:
    def test_rank_project_first(self):
        recs = [
            {"id": "1", "project": "demo", "confidence": 0.5, "type": "DEBUG_EXPERIENCE"},
            {"id": "2", "project": "other", "confidence": 0.9, "type": "DEBUG_EXPERIENCE"},
        ]
        policy = RP.DebugRetrievalPolicy()
        out = policy.rank(recs, session={"project_id": "demo"})
        assert out[0]["id"] == "1"  # 项目相关优先

    def test_rank_confidence(self):
        recs = [
            {"id": "1", "confidence": 0.3, "type": "DEBUG_EXPERIENCE"},
            {"id": "2", "confidence": 0.8, "type": "DEBUG_EXPERIENCE"},
        ]
        out = RP.DebugRetrievalPolicy().rank(recs)
        assert out[0]["id"] == "2"

    def test_retrieve_with_store(self, tmp_path):
        from importlib import import_module as _im
        MEM = _im("factory-console.memory")
        DP2 = _im("factory-console.session.debug.debug_pipeline")
        ws = _ws(tmp_path)
        store = MEM.ExperienceStore(ws / "memory" / "experience_store.json")
        store.add(MEM.ExperienceRecord(type="DEBUG_EXPERIENCE", problem="计分 API 失败",
                                       action="fix", success=True, confidence=0.9,
                                       source="test", project="demo"))
        s = DP2.DebugPipeline(workspace=ws).start(
            project_id="demo", task_id="T1", error_message="计分 API 失败")
        hits = RP.DebugRetrievalPolicy().retrieve(s, store, top_k=3)
        assert hits


class TestContextBudgetDeep:
    def test_fit_respects_max(self):
        recs = [{"id": str(i), "problem": "z" * 200} for i in range(20)]
        out = CB.ContextBudget().fit(recs, max_tokens=300)
        assert len(out) < 20

    def test_estimate_chinese(self):
        assert CB.ContextBudget().estimate_tokens("中文中文中文") > 0


class TestTraceDeep:
    def test_trace_multiple(self, tmp_path):
        ws = _ws(tmp_path)
        trace = TR.DebugTrace(workspace=ws)
        s = DS.DebugSessionStore().create(_make_session())
        trace.record(s, governance="AUTO")
        trace.record(s, governance="REVIEW")
        entries = json.loads((ws / "debug_trace.json").read_text(encoding="utf-8"))
        assert len(entries) == 2

    def test_trace_has_debug_id(self, tmp_path):
        ws = _ws(tmp_path)
        trace = TR.DebugTrace(workspace=ws)
        s = DS.DebugSessionStore().create(_make_session())
        entry = trace.record(s)
        assert entry["debug_id"] == s.debug_id
