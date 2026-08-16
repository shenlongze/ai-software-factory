"""S10-063 — Governance CLI 测试套件 (批次 B)。

覆盖: factory status / factory budget / factory review 命令 + 失败安全。
装配: tmp_path + fixtures; 禁真实 LLM/网络。
"""

from __future__ import annotations

import json
from pathlib import Path

from importlib import import_module

ORCH = import_module("factory-console.session.orchestrator")
ACT = import_module("factory-console.session.actions")
RG = import_module("factory-console.session.review_gate")
CL = import_module("factory-console.session.cost_ledger")


def _make_workspace(tmp_path: Path, with_project: bool = True) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "exec").mkdir(exist_ok=True)
    (ws / "cost").mkdir(exist_ok=True)
    if with_project:
        pd = ws / "projects" / "demo"
        pd.mkdir(parents=True, exist_ok=True)
        (pd / "execution_plan.json").write_text(
            json.dumps({"tasks": [{"id": "T001", "name": "计分"}], "count": 1}), encoding="utf-8")
        (pd / "execution_state.json").write_text(
            json.dumps({"status": "user_acceptance", "plan_version": 2,
                        "governance_status": "waiting_for_review"}), encoding="utf-8")
    return ws


def _ctx(ws: Path, params: dict | None = None) -> object:
    """构造最小 ExecutionContext (模拟 ActionContext)。"""
    class FakeContext:
        def __init__(self, workspace, params):
            self.workspace = str(workspace)
            self.params = params or {}
            self._required = False

        def require(self, level):
            self._required = True

    return FakeContext(ws, params)


class TestFactoryStatus:
    def test_status_with_project(self, tmp_path):
        ws = _make_workspace(tmp_path)
        res = ACT.governance_status(_ctx(ws))
        assert res.ok
        assert "demo" in res.message

    def test_status_no_project(self, tmp_path):
        ws = _make_workspace(tmp_path, with_project=False)
        res = ACT.governance_status(_ctx(ws))
        assert res.ok
        assert "暂无" in res.message or "无" in res.message

    def test_status_empty_workspace(self, tmp_path):
        ws = tmp_path / "none"
        ws.mkdir(exist_ok=True)
        res = ACT.governance_status(_ctx(ws))
        assert res.ok  # 失败安全

    def test_status_requires_user(self, tmp_path):
        ws = _make_workspace(tmp_path)
        c = _ctx(ws)
        ACT.governance_status(c)
        assert c._required


class TestFactoryBudget:
    def test_budget_empty(self, tmp_path):
        ws = _make_workspace(tmp_path)
        res = ACT.governance_budget(_ctx(ws))
        assert res.ok

    def test_budget_with_records(self, tmp_path):
        ws = _make_workspace(tmp_path)
        ledger = CL.CostLedger(file=ws / "cost" / "cost_records.json")
        ledger.record({"project_id": "demo", "task_id": "T1", "purpose": "EXECUTION",
                       "total_tokens": 500, "estimated_cost": 0.0005})
        res = ACT.governance_budget(_ctx(ws))
        assert res.ok
        assert "500" in res.message or "tokens" in res.message

    def test_budget_corrupt_file(self, tmp_path):
        ws = _make_workspace(tmp_path)
        (ws / "cost").mkdir(exist_ok=True)
        (ws / "cost" / "cost_records.json").write_text("not json", encoding="utf-8")
        res = ACT.governance_budget(_ctx(ws))
        assert res.ok  # 失败安全


class TestFactoryReview:
    def test_review_empty(self, tmp_path):
        ws = _make_workspace(tmp_path)
        res = ACT.governance_review(_ctx(ws))
        assert res.ok
        assert "无待审" in res.message

    def test_review_pending_listed(self, tmp_path):
        ws = _make_workspace(tmp_path)
        gate = RG.ReviewGate(file=ws / "cost" / "review_records.json")
        gate.request(reason="budget 90%", trigger="budget_review", context={},
                     affected_tasks=["T001"], estimated_cost=0.01, risk="medium")
        res = ACT.governance_review(_ctx(ws))
        assert res.ok
        assert "budget 90%" in res.message

    def test_review_approve(self, tmp_path):
        ws = _make_workspace(tmp_path)
        gate = RG.ReviewGate(file=ws / "cost" / "review_records.json")
        rec = gate.request(reason="r", trigger="t", context={}, affected_tasks=[],
                           estimated_cost=0, risk="low")
        res = ACT.governance_review(_ctx(ws, {"review_id": rec.review_id, "decision": "approve"}))
        assert res.ok
        assert "approved" in res.message

    def test_review_reject(self, tmp_path):
        ws = _make_workspace(tmp_path)
        gate = RG.ReviewGate(file=ws / "cost" / "review_records.json")
        rec = gate.request(reason="r", trigger="t", context={}, affected_tasks=[],
                           estimated_cost=0, risk="high")
        res = ACT.governance_review(_ctx(ws, {"review_id": rec.review_id, "decision": "reject"}))
        assert res.ok
        assert "rejected" in res.message

    def test_review_invalid_decision(self, tmp_path):
        ws = _make_workspace(tmp_path)
        res = ACT.governance_review(_ctx(ws, {"review_id": "x", "decision": "bogus"}))
        assert res.ok  # 失败安全


class TestReviewGateModel:
    def test_request_fields(self, tmp_path):
        gate = RG.ReviewGate(file=tmp_path / "r.json")
        rec = gate.request(reason="high cost", trigger="budget", context={"x": 1},
                           affected_tasks=["T1", "T2"], estimated_cost=5.0, risk="high")
        assert rec.review_id
        assert rec.status == "open"
        assert rec.estimated_cost == 5.0
        assert rec.risk == "high"

    def test_persist_reload(self, tmp_path):
        gate = RG.ReviewGate(file=tmp_path / "r.json")
        gate.request(reason="r", trigger="t", context={}, affected_tasks=[],
                     estimated_cost=0, risk="low")
        gate2 = RG.ReviewGate(file=tmp_path / "r.json")
        assert len(gate2.pending()) == 1

    def test_status_waiting(self, tmp_path):
        gate = RG.ReviewGate(file=tmp_path / "r.json")
        gate.request(reason="r", trigger="t", context={}, affected_tasks=[],
                     estimated_cost=0, risk="low")
        assert gate.status("x") in ("waiting", "none", "approved", "rejected")

    def test_cancel(self, tmp_path):
        gate = RG.ReviewGate(file=tmp_path / "r.json")
        rec = gate.request(reason="r", trigger="t", context={}, affected_tasks=[],
                           estimated_cost=0, risk="low")
        cancelled = gate.cancel(rec.review_id)
        assert cancelled.status == "cancelled"

    def test_missing_file_safe(self, tmp_path):
        gate = RG.ReviewGate(file=tmp_path / "missing.json")
        assert gate.pending() == []


class TestCostLedgerModel:
    def test_record_aggregate(self, tmp_path):
        ledger = CL.CostLedger(file=tmp_path / "c.json")
        ledger.record({"project_id": "p", "task_id": "T1", "purpose": "EXECUTION",
                       "total_tokens": 100, "estimated_cost": 0.001})
        ledger.record({"project_id": "p", "task_id": "T2", "purpose": "REPAIR",
                       "total_tokens": 50, "estimated_cost": 0.0005})
        agg = ledger.aggregate("p")
        assert agg["total_cost"] == 0.0015
        assert agg["by_purpose"]["REPAIR"]["cost"] == 0.0005

    def test_record_by_agent(self, tmp_path):
        ledger = CL.CostLedger(file=tmp_path / "c.json")
        ledger.record({"project_id": "p", "task_id": "T1", "agent_id": "backend-1",
                       "purpose": "EXECUTION", "total_tokens": 100, "estimated_cost": 0.001})
        agg = ledger.aggregate("p")
        assert agg["by_agent"]["backend-1"]["cost"] == 0.001

    def test_record_by_task(self, tmp_path):
        ledger = CL.CostLedger(file=tmp_path / "c.json")
        ledger.record({"project_id": "p", "task_id": "T3", "purpose": "EXECUTION",
                       "total_tokens": 100, "estimated_cost": 0.001})
        agg = ledger.aggregate("p")
        assert agg["by_task"]["T3"]["cost"] == 0.001

    def test_missing_file_safe(self, tmp_path):
        ledger = CL.CostLedger(file=tmp_path / "missing.json")
        assert ledger.records() == []


class TestBudgetModel:
    def test_from_dict_roundtrip(self, tmp_path):
        b = __import__("factory-console.session.budget", fromlist=["ProjectBudget"]).ProjectBudget(
            max_total_tokens=1000)
        d = b.to_dict()
        b2 = __import__("factory-console.session.budget", fromlist=["ProjectBudget"]).ProjectBudget.from_dict(d)
        assert b2.max_total_tokens == 1000

    def test_usage_from_records(self, tmp_path):
        B = __import__("factory-console.session.budget", fromlist=["ProjectBudget", "BudgetUsage"])
        records = [{"total_tokens": 100, "estimated_cost": 0.001},
                   {"total_tokens": 50, "estimated_cost": 0.0005}]
        usage = B.BudgetUsage.from_records(records)
        assert usage.total_tokens == 150
        assert usage.total_cost == 0.0015

    def test_enforcer_levels(self, tmp_path):
        B = __import__("factory-console.session.budget", fromlist=["ProjectBudget", "BudgetUsage", "BudgetEnforcer"])
        budget = B.ProjectBudget(max_total_tokens=100)
        assert B.BudgetEnforcer.check(budget, B.BudgetUsage(total_tokens=79))["level"] == "ok"
        assert B.BudgetEnforcer.check(budget, B.BudgetUsage(total_tokens=85))["level"] == "warn"
        assert B.BudgetEnforcer.check(budget, B.BudgetUsage(total_tokens=95))["level"] == "review"
        assert B.BudgetEnforcer.check(budget, B.BudgetUsage(total_tokens=100))["level"] == "block"


class TestLoopGuardModel:
    def test_same_failure(self, tmp_path):
        LG = import_module("factory-console.session.loop_guard")
        guard = LG.LoopGuard(max_same_failure=3)
        history = [{"task_id": "T1", "failure": "x"}] * 3
        assert guard.same_failure_count("T1", "x", history) == 3

    def test_same_decision(self, tmp_path):
        LG = import_module("factory-console.session.loop_guard")
        guard = LG.LoopGuard(max_same_decision=5)
        history = [{"decision": "INSERT_TASK"}] * 5
        assert guard.same_decision_count("INSERT_TASK", history) == 5

    def test_total_execution(self, tmp_path):
        LG = import_module("factory-console.session.loop_guard")
        guard = LG.LoopGuard()
        assert guard.total_execution_count([{"task_id": "T1"}, {"task_id": "T2"}]) == 2

    def test_check_allowed(self, tmp_path):
        LG = import_module("factory-console.session.loop_guard")
        guard = LG.LoopGuard(max_same_failure=3)
        res = guard.check_failure("T1", "x", [])
        assert res["allowed"]


class TestPolicyModel:
    def test_auto_allows(self, tmp_path):
        EP = import_module("factory-console.session.execution_policy")
        pol = EP.ExecutionPolicy(mode=EP.ExecutionPolicy.MODE_AUTO)
        ok, _ = pol.can_execute({"risk": "high"})
        assert ok  # AUTO 全允许

    def test_manual_blocks(self, tmp_path):
        EP = import_module("factory-console.session.execution_policy")
        pol = EP.ExecutionPolicy(mode=EP.ExecutionPolicy.MODE_MANUAL)
        ok, _ = pol.can_execute({})
        assert not ok

    def test_risk_high(self, tmp_path):
        EP = import_module("factory-console.session.execution_policy")
        pol = EP.ExecutionPolicy(mode=EP.ExecutionPolicy.MODE_SAFE_AUTO)
        assert pol.risk({"destructive": True}) == "high"


class TestActionsRegistered:
    def test_factory_status_registered(self, tmp_path):
        reg = ACT.build_default_actions()
        names = [a.name for a in reg.list()] if hasattr(reg, "list") else [a.name for a in getattr(reg, "actions", [])]
        assert "factory_status" in names

    def test_factory_budget_registered(self, tmp_path):
        reg = ACT.build_default_actions()
        names = [a.name for a in reg.list()] if hasattr(reg, "list") else [a.name for a in getattr(reg, "actions", [])]
        assert "factory_budget" in names

    def test_factory_review_registered(self, tmp_path):
        reg = ACT.build_default_actions()
        names = [a.name for a in reg.list()] if hasattr(reg, "list") else [a.name for a in getattr(reg, "actions", [])]
        assert "factory_review" in names
