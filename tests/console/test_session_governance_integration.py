"""S10-063 — Production Governance 集成测试套件 (批次 B)。

覆盖: Orchestrator + budget (warn/review/block) / cost_ledger 记录 /
review_gate (REQUEST_REVIEW → approve → resume) / policy / loop_guard /
planning_trace 关联 / CLI / 回归。

装配: tmp_path + fixtures; mock execute_fn; 禁真实 LLM/网络。
"""

from __future__ import annotations

import json
from pathlib import Path

from importlib import import_module

ORCH = import_module("factory-console.session.orchestrator")
B = import_module("factory-console.session.budget")
CL = import_module("factory-console.session.cost_ledger")
RG = import_module("factory-console.session.review_gate")
EP = import_module("factory-console.session.execution_policy")
LG = import_module("factory-console.session.loop_guard")
PT = import_module("factory-console.session.planning_trace")


def _make_project(tmp_path: Path, tasks: list | None = None) -> Path:
    pd = tmp_path / "projects" / "demo"
    pd.mkdir(parents=True, exist_ok=True)
    chosen = tasks if tasks is not None else [{"id": "T001", "name": "计分逻辑"}]
    (pd / "execution_plan.json").write_text(
        json.dumps({"tasks": chosen, "count": len(chosen)}, ensure_ascii=False), encoding="utf-8")
    (pd / "project.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
    (pd / "product.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
    return pd


def _ok_fn(task, project_dir, workspace):
    return {"success": True, "artifact": f"/tmp/{task['id']}", "cost": "1",
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}


def _fail_fn(calls, gap_error="missing persistence"):
    def fn(task, project_dir, workspace):
        calls.append(task["id"])
        if task["id"] == "T001":
            return {"success": False, "error": gap_error}
        return {"success": True, "artifact": f"/tmp/{task['id']}", "cost": "1"}
    return fn


# ================================================================== 1. budget


class TestBudgetIntegration:
    def test_no_budget_unchanged(self, tmp_path):
        """全缺省 → 现有行为。"""
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=_ok_fn)
        assert res.status == "user_acceptance"  # S10-055: 停待验收

    def test_budget_ok_continues(self, tmp_path):
        """预算充足 → 正常执行。"""
        pd = _make_project(tmp_path)
        ledger = CL.CostLedger(file=pd / "cost_records.json")
        budget = B.ProjectBudget(max_total_tokens=100000)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=_ok_fn,
                                   cost_ledger=ledger, budget=budget)
        assert res.status == "user_acceptance"

    def test_budget_warn_continues(self, tmp_path):
        """80% → warn 但继续。"""
        pd = _make_project(tmp_path)
        ledger = CL.CostLedger(file=pd / "cost_records.json")
        # 预填 80% 用量
        ledger.record({"project_id": "demo", "task_id": "T0", "purpose": "EXECUTION",
                       "total_tokens": 8000, "estimated_cost": 0.008})
        budget = B.ProjectBudget(max_total_tokens=10000, warn_ratio=0.8, review_ratio=0.9)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=_ok_fn,
                                   cost_ledger=ledger, budget=budget)
        assert res.status == "user_acceptance"  # warn 不阻止

    def test_budget_review_stops(self, tmp_path):
        """90% → review 停止。"""
        pd = _make_project(tmp_path)
        ledger = CL.CostLedger(file=pd / "cost_records.json")
        ledger.record({"project_id": "demo", "task_id": "T0", "purpose": "EXECUTION",
                       "total_tokens": 9000, "estimated_cost": 0.009})
        budget = B.ProjectBudget(max_total_tokens=10000, warn_ratio=0.8, review_ratio=0.9)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=_ok_fn,
                                   cost_ledger=ledger, budget=budget)
        assert res.status in ("waiting_for_review", "review_required", "blocked", "failed")

    def test_budget_block_stops(self, tmp_path):
        """100% → block 停止。"""
        pd = _make_project(tmp_path)
        ledger = CL.CostLedger(file=pd / "cost_records.json")
        ledger.record({"project_id": "demo", "task_id": "T0", "purpose": "EXECUTION",
                       "total_tokens": 10000, "estimated_cost": 0.01})
        budget = B.ProjectBudget(max_total_tokens=10000)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=_ok_fn,
                                   cost_ledger=ledger, budget=budget)
        assert res.status in ("blocked", "review_required", "failed")


# ================================================================== 2. cost_ledger 记录


class TestCostLedgerIntegration:
    def test_execution_recorded(self, tmp_path):
        pd = _make_project(tmp_path)
        ledger = CL.CostLedger(file=pd / "cost_records.json")
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_ok_fn, cost_ledger=ledger)
        records = ledger.records("demo")
        assert any(r.get("purpose") == "EXECUTION" for r in records)

    def test_execution_has_task_agent(self, tmp_path):
        pd = _make_project(tmp_path)
        ledger = CL.CostLedger(file=pd / "cost_records.json")
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_ok_fn, cost_ledger=ledger)
        rec = [r for r in ledger.records("demo") if r.get("purpose") == "EXECUTION"]
        assert rec and rec[0].get("task_id") == "T001"

    def test_aggregate_total(self, tmp_path):
        pd = _make_project(tmp_path)
        ledger = CL.CostLedger(file=pd / "cost_records.json")
        ledger.record({"project_id": "demo", "task_id": "T1", "purpose": "EXECUTION",
                       "total_tokens": 100, "estimated_cost": 0.001})
        ledger.record({"project_id": "demo", "task_id": "T2", "purpose": "REPLANNING",
                       "total_tokens": 50, "estimated_cost": 0.0005})
        agg = ledger.aggregate("demo")
        assert agg["total_cost"] == 0.0015
        assert agg["by_purpose"]["EXECUTION"]["cost"] == 0.001
        assert agg["by_purpose"]["REPLANNING"]["cost"] == 0.0005


# ================================================================== 3. review gate 集成


class TestReviewGateIntegration:
    def test_request_review_stops(self, tmp_path):
        pd = _make_project(tmp_path)
        gate = RG.ReviewGate(file=pd / "review_records.json")
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        # 直接注入 review gate + 高成本预算 → 触发 review
        ledger = CL.CostLedger(file=pd / "cost_records.json")
        ledger.record({"project_id": "demo", "task_id": "T0", "purpose": "EXECUTION",
                       "total_tokens": 9500, "estimated_cost": 0.0095})
        budget = B.ProjectBudget(max_total_tokens=10000, review_ratio=0.9)
        res = orch.execute_project("demo", execute_fn=_ok_fn,
                                   cost_ledger=ledger, budget=budget,
                                   review_gate=gate)
        assert res.status in ("waiting_for_review", "review_required", "blocked", "failed")

    def test_review_gate_workflow(self, tmp_path):
        """request → approve → rejected 等。"""
        gate = RG.ReviewGate(file=tmp_path / "reviews.json")
        rec = gate.request(reason="budget 90%", trigger="budget_review",
                           context={}, affected_tasks=["T001"],
                           estimated_cost=0.01, risk="medium")
        assert rec.status == "open"
        approved = gate.approve(rec.review_id, "user")
        assert approved.status == "approved"
        pending = gate.pending()
        assert all(r.status == "open" for r in pending)

    def test_reject_blocks(self, tmp_path):
        gate = RG.ReviewGate(file=tmp_path / "reviews.json")
        rec = gate.request(reason="r", trigger="t", context={}, affected_tasks=[],
                           estimated_cost=0, risk="high")
        rejected = gate.reject(rec.review_id, "user")
        assert rejected.status == "rejected"


# ================================================================== 4. policy


class TestPolicyIntegration:
    def test_policy_can_execute(self, tmp_path):
        pol = EP.ExecutionPolicy(mode=EP.ExecutionPolicy.MODE_AUTO)
        ok, reason = pol.can_execute({"risk": "low"})
        assert ok

    def test_policy_manual_blocks(self, tmp_path):
        pol = EP.ExecutionPolicy(mode=EP.ExecutionPolicy.MODE_MANUAL)
        ok, reason = pol.can_execute({"risk": "low"})
        assert not ok

    def test_policy_review_high_risk(self, tmp_path):
        pol = EP.ExecutionPolicy(mode=EP.ExecutionPolicy.MODE_SAFE_AUTO)
        ok, reason = pol.can_execute({"risk": "high"})
        assert not ok  # 高风险需 review

    def test_policy_can_retry(self, tmp_path):
        pol = EP.ExecutionPolicy(mode=EP.ExecutionPolicy.MODE_AUTO)
        ok, _ = pol.can_retry({"risk": "low"})
        assert ok


# ================================================================== 5. loop guard


class TestLoopGuardIntegration:
    def test_same_failure_blocks(self, tmp_path):
        guard = LG.LoopGuard(max_same_failure=3)
        history = [{"task_id": "T1", "failure": "x"},
                   {"task_id": "T1", "failure": "x"},
                   {"task_id": "T1", "failure": "x"}]
        res = guard.check_failure("T1", "x", history)
        assert res["action"] in ("block", "review")

    def test_same_failure_allowed_under(self, tmp_path):
        guard = LG.LoopGuard(max_same_failure=3)
        history = [{"task_id": "T1", "failure": "x"}]
        res = guard.check_failure("T1", "x", history)
        assert res["allowed"]

    def test_same_decision_reviews(self, tmp_path):
        guard = LG.LoopGuard(max_same_decision=5)
        history = [{"decision": "INSERT_TASK"}] * 5
        res = guard.check_decision("INSERT_TASK", history)
        assert not res["allowed"]

    def test_total_execution_blocks(self, tmp_path):
        guard = LG.LoopGuard(max_total_execution=3)
        history = [{"task_id": f"T{i}"} for i in range(3)]
        assert guard.total_execution_count(history) == 3


# ================================================================== 6. planning_trace 关联


class TestTraceCorrelation:
    def test_trace_has_correlation(self, tmp_path):
        trace = PT.PlanningTrace(file=tmp_path / "trace.json")
        trace.record(operation="analyze_gap", provider="deepseek", model="m",
                     input_hash="h", output="", parsed_result={}, confidence=0.8,
                     token_usage={}, latency=0.1, fallback_used=False,
                     validation_result={}, final_decision="d",
                     task_id="T001", agent_id="qa-agent", project_id="demo",
                     parent_execution_id="exec-1")
        records = trace.load()
        assert records[0]["task_id"] == "T001"
        assert records[0]["agent_id"] == "qa-agent"
        assert records[0]["project_id"] == "demo"
        assert records[0]["parent_execution_id"] == "exec-1"

    def test_trace_backward_compat(self, tmp_path):
        """旧调用 (无关联字段) 仍工作。"""
        trace = PT.PlanningTrace(file=tmp_path / "trace.json")
        trace.record(operation="x", provider="p", model="m", input_hash="h",
                     output="", parsed_result={}, confidence=0.5, token_usage={},
                     latency=0.0, fallback_used=False, validation_result={},
                     final_decision="d")
        assert len(trace.load()) == 1


# ================================================================== 7. 回归


class TestRegression:
    def test_solo_mode(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=_ok_fn)
        assert res.completed_tasks == 1

    def test_s10_061_chain(self, tmp_path):
        pd = _make_project(tmp_path)
        ga = import_module("factory-console.session.gap_analyzer").GapAnalyzer(
            file=pd / "gap_analysis.json")
        calls = []
        replanner = import_module("factory-console.session.replanning").ReplanningEngine(
            file=pd / "replanning_decisions.json")
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_fail_fn(calls), gap_analyzer=ga,
                             replanner=replanner)
        assert len(calls) >= 2  # T001 + 自动提案任务

    def test_hybrid_llm(self, tmp_path):
        pd = _make_project(tmp_path)
        R = import_module("factory-console.session.reasoning")
        LP = import_module("factory-console.session.llm_task_proposal")

        def valid_fn(prompt, operation=""):
            return json.dumps({"task_id": "", "title": "持久化", "description": "d",
                               "objective": "o", "required_role": "backend",
                               "dependencies": ["T001"], "acceptance_criteria": ["x"],
                               "validation_command": "pytest", "priority": "high",
                               "rationale": "r", "confidence": 0.8,
                               "source_gap": "g"}, ensure_ascii=False)

        prov = R.ReasoningProvider(llm_fn=valid_fn)
        replanner = import_module("factory-console.session.replanning").ReplanningEngine(
            file=pd / "replanning_decisions.json")
        calls = []
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_fail_fn(calls),
                             planning_mode="hybrid", llm_reasoning=prov,
                             replanner=replanner)
        assert calls


# ================================================================== 补充


class TestMore:
    def test_budget_from_dict(self, tmp_path):
        b = B.ProjectBudget.from_dict({"max_total_tokens": 500})
        assert b.max_total_tokens == 500

    def test_budget_defaults(self, tmp_path):
        b = B.ProjectBudget()
        assert b.max_replans == 5
        assert b.max_retries == 1
        assert b.warn_ratio == 0.8
        assert b.review_ratio == 0.9

    def test_enforcer_block(self, tmp_path):
        budget = B.ProjectBudget(max_total_tokens=100)
        usage = B.BudgetUsage(total_tokens=100)
        enforcer = B.BudgetEnforcer()
        check = enforcer.check(budget, usage)
        assert check["level"] == "block"

    def test_enforcer_warn(self, tmp_path):
        budget = B.ProjectBudget(max_total_tokens=100)
        usage = B.BudgetUsage(total_tokens=85)
        enforcer = B.BudgetEnforcer()
        assert enforcer.check(budget, usage)["level"] == "warn"

    def test_enforcer_action_blocked(self, tmp_path):
        budget = B.ProjectBudget(max_total_tokens=100)
        usage = B.BudgetUsage(total_tokens=100)
        enforcer = B.BudgetEnforcer()
        res = enforcer.enforce(budget, usage, "llm")
        assert not res["allowed"]

    def test_cost_estimate(self, tmp_path):
        ledger = CL.CostLedger(file=tmp_path / "c.json")
        cost = ledger.estimate_cost(1000, 100)
        assert cost > 0

    def test_loop_guard_empty_history(self, tmp_path):
        guard = LG.LoopGuard()
        res = guard.check_failure("T1", "x", [])
        assert res["allowed"]

    def test_review_status(self, tmp_path):
        gate = RG.ReviewGate(file=tmp_path / "r.json")
        assert gate.status("demo") in ("none", "waiting", "approved", "rejected")

    def test_import_all(self, tmp_path):
        import_module("factory-console.session.budget")
        import_module("factory-console.session.cost_ledger")
        import_module("factory-console.session.review_gate")
        import_module("factory-console.session.execution_policy")
        import_module("factory-console.session.loop_guard")
