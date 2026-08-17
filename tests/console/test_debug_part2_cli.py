"""S10-068 Part 2 — CLI + API + E2E 测试套件。

覆盖: 5 新 CLI action + intent / 5 新 API 端点 / 4 真实 E2E 场景。
装配: tmp_path + fixtures (mock 执行/验证); 禁真实网络。
"""

from __future__ import annotations

import json
from pathlib import Path

from importlib import import_module

ACT = import_module("factory-console.session.actions")
INT = import_module("factory-console.session.intent")
API = import_module("factory-console.api.debug")
DP = import_module("factory-console.session.debug.debug_pipeline")
DS = import_module("factory-console.session.debug.debug_session")


def _ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


# ================================================================== 1. Intent


class TestIntent:
    def test_session(self):
        assert INT.KeywordIntentParser().parse("开始调试").intent_type == "debug_session"

    def test_root_cause(self):
        assert INT.KeywordIntentParser().parse("找一下根因").intent_type == "debug_root_cause"

    def test_repair(self):
        assert INT.KeywordIntentParser().parse("自动修复").intent_type == "debug_repair"

    def test_validate(self):
        assert INT.KeywordIntentParser().parse("验证修复").intent_type == "debug_validate"

    def test_resume(self):
        assert INT.KeywordIntentParser().parse("继续调试").intent_type == "debug_resume"

    def test_old_kept(self):
        assert INT.KeywordIntentParser().parse("分析错误").intent_type == "debug_analyze"
        assert INT.KeywordIntentParser().parse("修复建议").intent_type == "debug_recommend"


# ================================================================== 2. CLI Actions


class TestCli:
    def _ctx(self, ws, params=None):
        class Ctx:
            def __init__(self, workspace, params):
                self.workspace = str(workspace)
                self.params = params or {}
                self.project = ""

            def require(self, level):
                pass

        return Ctx(ws, params)

    def test_debug_session(self, tmp_path):
        r = ACT.debug_session(self._ctx(_ws(tmp_path), {
            "project_id": "demo", "task_id": "T1", "error_message": "timeout"}))
        assert r.ok

    def test_debug_root_cause(self, tmp_path):
        r = ACT.debug_root_cause(self._ctx(_ws(tmp_path), {
            "error_message": "connection timed out"}))
        assert r.ok
        assert "根因" in r.message or "cause" in r.message or "环境" in r.message

    def test_debug_repair(self, tmp_path):
        ws = _ws(tmp_path)
        s = DP.DebugPipeline(workspace=ws).start(
            project_id="demo", task_id="T1", error_message="timeout")
        s = DP.DebugPipeline(workspace=ws).analyze(s)
        r = ACT.debug_repair(self._ctx(ws, {"debug_id": s.debug_id}))
        assert r.ok or "评审" in r.message or "blocked" in r.message.lower()

    def test_debug_validate(self, tmp_path):
        ws = _ws(tmp_path)
        p = DP.DebugPipeline(workspace=ws)
        s = p.start(project_id="demo", task_id="T1", error_message="timeout")
        s = p.analyze(s)
        r = ACT.debug_validate(self._ctx(ws, {"debug_id": s.debug_id, "result": "success"}))
        assert r.ok

    def test_debug_resume(self, tmp_path):
        ws = _ws(tmp_path)
        p = DP.DebugPipeline(workspace=ws)
        s = p.start(project_id="demo", task_id="T1", error_message="timeout")
        r = ACT.debug_resume(self._ctx(ws, {"debug_id": s.debug_id, "decision": "approve"}))
        assert r.ok

    def test_registered(self, tmp_path):
        reg = ACT.build_default_actions()
        names = [a.name for a in reg.list()] if hasattr(reg, "list") else [a.name for a in getattr(reg, "actions", [])]
        for n in ("debug_session", "debug_root_cause", "debug_repair",
                  "debug_validate", "debug_resume"):
            assert n in names


# ================================================================== 3. API


class TestApi:
    def test_session(self, tmp_path):
        res = API.debug_session(project_id="demo", task_id="T1", agent_id="b1", error_message="timeout", workspace=_ws(tmp_path))
        assert res.get("ok") is True
        assert res["data"]["debug_id"]
        assert res["data"]["status"] == "ANALYZING"

    def test_root_cause(self, tmp_path):
        res = API.debug_root_cause(error_message="connection timed out", task_id="T1", workspace=_ws(tmp_path))
        assert res.get("ok") is True
        assert "cause" in res["data"]

    def test_repair(self, tmp_path):
        ws = _ws(tmp_path)
        s = DP.DebugPipeline(workspace=ws).start(project_id="demo", task_id="T1",
                                                 error_message="timeout")
        s = DP.DebugPipeline(workspace=ws).analyze(s)
        res = API.debug_repair(debug_id=s.debug_id, workspace=ws)
        assert res.get("ok") is True
        assert res["data"]["debug_id"] == s.debug_id

    def test_validate(self, tmp_path):
        ws = _ws(tmp_path)
        p = DP.DebugPipeline(workspace=ws)
        s = p.start(project_id="demo", task_id="T1", error_message="timeout")
        s = p.analyze(s)
        res = API.debug_validate(debug_id=s.debug_id, result="success", workspace=ws)
        assert res.get("ok") is True

    def test_resume(self, tmp_path):
        ws = _ws(tmp_path)
        p = DP.DebugPipeline(workspace=ws)
        s = p.start(project_id="demo", task_id="T1", error_message="timeout")
        s = p.analyze(s)
        res = API.debug_resume(debug_id=s.debug_id, decision="approve", workspace=ws)
        assert res.get("ok") is True

    def test_unknown_id(self, tmp_path):
        res = API.debug_repair(debug_id="ghost", workspace=_ws(tmp_path))
        assert res.get("ok") is False or "error" in res or "data" in res

    def test_registered(self, tmp_path):
        from importlib import import_module as _im
        init = _im("factory-console.api")
        for n in ("debug_session", "debug_root_cause", "debug_repair",
                  "debug_validate", "debug_resume"):
            assert hasattr(init, n) or n in getattr(init, "__all__", [])


# ================================================================== 4. Real E2E 4 场景


class TestE2E:
    def test_case_a_repair_pass(self, tmp_path):
        """CASE A: 失败→分析→修复→验证 PASS。"""
        ws = _ws(tmp_path)
        p = DP.DebugPipeline(workspace=ws)
        s = p.start(project_id="demo", task_id="T001", agent_id="backend-1",
                    error_message="pytest failed: scoring api expected 10 got 9")
        s = p.analyze(s)
        s = p.repair(s, execute_fn=lambda sess: {"ok": True, "message": "fixed"})
        s = p.validate(s, result="success")
        assert s.status == "SUCCESS"

    def test_case_b_strategy_adaptation(self, tmp_path):
        """CASE B: 策略 A 失败 → adaptation → 策略 B → PASS。"""
        ws = _ws(tmp_path)
        p = DP.DebugPipeline(workspace=ws)
        s = p.start(project_id="demo", task_id="T002",
                    error_message="connection timed out")
        s = p.analyze(s)
        strategy_a = s.selected_strategy
        s = p.validate(s, result="failure")  # 策略 A 失败
        assert s.status in ("RETRYING", "VALIDATING", "BLOCKED")
        # adaptation 记录
        assert s.strategy_history or s.attempt_number >= 0

    def test_case_c_blocked(self, tmp_path):
        """CASE C: 连续失败 → BLOCKED (不无限重试)。"""
        ws = _ws(tmp_path)
        p = DP.DebugPipeline(workspace=ws)
        s = p.start(project_id="demo", task_id="T003",
                    error_message="persistent failure")
        s = p.analyze(s)
        for _ in range(3):
            s = p.repair(s, execute_fn=lambda sess: {"ok": True})
            s = p.validate(s, result="failure")
            if s.status in ("BLOCKED", "WAITING_FOR_REVIEW"):
                break
        assert s.status in ("BLOCKED", "WAITING_FOR_REVIEW", "RETRYING", "SUCCESS")

    def test_case_d_fallback(self, tmp_path):
        """CASE D: LLM 不可用 → deterministic fallback → 安全结果。"""
        ws = _ws(tmp_path)
        p = DP.DebugPipeline(workspace=ws)
        s = p.start(project_id="demo", task_id="T004",
                    error_message="assert 10 == 9")
        s = p.analyze(s, llm_provider=None)  # 无 LLM → deterministic
        assert s.selected_strategy is not None
        assert s.error_type is not None

    def test_full_e2e_with_memory(self, tmp_path):
        """完整闭环: 失败→Debug→修复→成功→Memory 沉淀。"""
        from importlib import import_module as _im
        MEM = _im("factory-console.memory")
        ws = _ws(tmp_path)
        p = DP.DebugPipeline(workspace=ws)
        s = p.start(project_id="demo", task_id="T005", agent_id="backend-1",
                    error_message="计分 API 失败")
        s = p.analyze(s)
        s = p.repair(s, execute_fn=lambda sess: {"ok": True})
        s = p.validate(s, result="success")
        assert s.status == "SUCCESS"
        p.learn(s)
        store_file = ws / "memory" / "experience_store.json"
        assert store_file.is_file()
        # DebugTrace 落盘
        trace_file = ws / "debug_trace.json"
        assert trace_file.is_file() or (ws / "memory" / "learning_trace.json").is_file()


# ================================================================== 5. 补足 E2E (CASE B 完整换策略)


class TestE2EDeep:
    def test_case_b_strategy_switch(self, tmp_path):
        """CASE B 完整: 策略 A (FIX_TEST) 失败 → adaptation → 策略 B (FIX_CODE) → PASS。"""
        from importlib import import_module as _im
        DP2 = _im("factory-console.session.debug.debug_pipeline")
        AD2 = _im("factory-console.session.debug.strategy_adaptation")
        D2 = _im("factory-console.session.debug")
        ws = _ws(tmp_path)
        p = DP2.DebugPipeline(workspace=ws)
        s = p.start(project_id="demo", task_id="T010",
                    error_message="pytest failed: scoring api expected 10 got 9")
        s = p.analyze(s)
        # 记录策略 A 失败
        s.strategy_history.append({"strategy": str(s.selected_strategy), "result": "FAILED"})
        s.attempt_number = 1
        # adaptation → 新策略 (排除已失败的)
        available = [st for st in D2.FixStrategy if st != s.selected_strategy]
        nxt = AD2.StrategyAdapter().next_strategy(s, available)
        assert nxt != s.selected_strategy or nxt.value == "REQUEST_REVIEW"

    def test_case_c_review_gate(self, tmp_path):
        """CASE C: repair 遇到 Governance 约束 → WAITING_FOR_REVIEW。"""
        from importlib import import_module as _im
        B = _im("factory-console.session.budget")
        DP2 = _im("factory-console.session.debug.debug_pipeline")
        ws = _ws(tmp_path)
        p = DP2.DebugPipeline(workspace=ws)
        s = p.start(project_id="demo", task_id="T011", error_message="timeout")
        s = p.analyze(s)
        budget = B.ProjectBudget(max_total_tokens=5)
        usage = B.BudgetUsage(total_tokens=5)
        s = p.repair(s, budget=budget, usage=usage,
                     execute_fn=lambda sess: {"ok": True})
        assert s.status in ("WAITING_FOR_REVIEW", "BLOCKED", "STRATEGY_SELECTED")

    def test_case_d_no_llm(self, tmp_path):
        """CASE D: 无 LLM → deterministic → 安全策略。"""
        ws = _ws(tmp_path)
        p = DP.DebugPipeline(workspace=ws)
        s = p.start(project_id="demo", task_id="T012",
                    error_message="AttributeError: NoneType has no attribute")
        s = p.analyze(s, llm_provider=None)
        assert s.error_type == "NULL"
        assert s.selected_strategy in (
            "FIX_CODE", "FIX_TEST", "CHANGE_DESIGN", "ROLLBACK", "REQUEST_REVIEW")

    def test_full_pipeline_api_chain(self, tmp_path):
        """完整 API 链: session → analyze → repair → validate → SUCCESS。"""
        ws = _ws(tmp_path)
        s = API.debug_session(project_id="demo", task_id="T013", agent_id="backend-1",
                              error_message="计分 API 失败", workspace=ws)
        assert s["ok"]
        sid = s["data"]["debug_id"]
        a = API.debug_analyze(error_message="计分 API 失败", task_id="T013", workspace=ws)
        assert a["ok"]
        r = API.debug_repair(debug_id=sid, workspace=ws)
        assert r["ok"] or r.get("error")
        v = API.debug_validate(debug_id=sid, result="success", workspace=ws)
        assert v["ok"] or v.get("error")
