"""S10-065 批次 C — max_execution_time 生效 + BudgetUsage.execution_time 测试套件。

覆盖 (验收 C/D/E/G):
- BudgetUsage.execution_time 聚合 (from_records sum(latency)) + ratio_with
  含 max_execution_time 维度 + BudgetEnforcer 三档判定
- _GovernanceContext: elapsed / check_execution_time (blocked /
  waiting_for_review; 无限/无预算 → 不检查)
- orchestrator: max_execution_time 生效 (慢执行 → 停止, 可解释落盘);
  未超时 → 正常执行; 回归 (无预算/缺省预算行为零变化)

装配: tmp_path + fixtures; mock execute_fn; 禁真实 LLM/网络。

"""

from __future__ import annotations

import json
import time
from pathlib import Path

from importlib import import_module

ORCH = import_module("factory-console.session.orchestrator")
B = import_module("factory-console.session.budget")
CL = import_module("factory-console.session.cost_ledger")
RG = import_module("factory-console.session.review_gate")


def _make_project(tmp_path: Path, tasks: list | None = None) -> Path:
    pd = tmp_path / "projects" / "demo"
    pd.mkdir(parents=True, exist_ok=True)
    chosen = tasks if tasks is not None else [
        {"id": "T001", "name": "计分逻辑"}, {"id": "T002", "name": "界面"}
    ]
    (pd / "execution_plan.json").write_text(
        json.dumps({"tasks": chosen, "count": len(chosen)}, ensure_ascii=False), encoding="utf-8")
    (pd / "project.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
    (pd / "product.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
    return pd


def _ok_fn(task, project_dir, workspace):
    return {"success": True, "artifact": f"/tmp/{task['id']}", "cost": "1",
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            "duration": 0.01}


def _slow_fn(sleep_s=0.35):
    def fn(task, project_dir, workspace):
        time.sleep(sleep_s)
        return {"success": True, "artifact": f"/tmp/{task['id']}", "cost": "1",
                "duration": sleep_s}
    return fn


def _gov(project_id="demo", **kw) -> ORCH._GovernanceContext:
    return ORCH._GovernanceContext(project_id, **kw)


# ================================================================== 1. BudgetUsage.execution_time


class TestBudgetUsageExecutionTime:
    def test_from_records_sums_latency(self):
        records = [
            {"estimated_cost": 0.01, "latency": 1.2, "total_tokens": 10},
            {"estimated_cost": 0.02, "latency": 2.3, "total_tokens": 20},
            {"estimated_cost": 0.03, "latency": 0.5, "total_tokens": 30},
        ]
        usage = B.BudgetUsage.from_records(records)
        assert usage.execution_time == 4.0  # 1.2+2.3+0.5

    def test_from_records_empty_zero(self):
        assert B.BudgetUsage.from_records([]).execution_time == 0.0

    def test_from_records_missing_latency_zero_contrib(self):
        usage = B.BudgetUsage.from_records(
            [{"estimated_cost": 0.01}, {"estimated_cost": 0.02, "latency": 3.0}]
        )
        assert usage.execution_time == 3.0

    def test_ratio_with_max_execution_time(self):
        usage = B.BudgetUsage(execution_time=5.0)
        budget = B.ProjectBudget(max_execution_time=10.0)
        assert usage.ratio_with(budget) == 0.5

    def test_ratio_ignores_unbounded_execution_time(self):
        usage = B.BudgetUsage(execution_time=999.0)
        budget = B.ProjectBudget(max_execution_time=0.0)  # 无限
        assert usage.ratio_with(budget) == 0.0

    def test_enforcer_block_on_execution_time(self):
        budget = B.ProjectBudget(max_execution_time=10.0)
        usage = B.BudgetUsage(execution_time=10.0)
        assert B.BudgetEnforcer.check(budget, usage)["level"] == "block"

    def test_enforcer_review_on_execution_time(self):
        budget = B.ProjectBudget(max_execution_time=10.0, review_ratio=0.9)
        usage = B.BudgetUsage(execution_time=9.5)
        assert B.BudgetEnforcer.check(budget, usage)["level"] == "review"

    def test_enforcer_warn_on_execution_time(self):
        budget = B.ProjectBudget(max_execution_time=10.0, warn_ratio=0.8)
        usage = B.BudgetUsage(execution_time=8.5)
        assert B.BudgetEnforcer.check(budget, usage)["level"] == "warn"

    def test_enforcer_ok_on_execution_time(self):
        budget = B.ProjectBudget(max_execution_time=10.0, warn_ratio=0.8)
        usage = B.BudgetUsage(execution_time=1.0)
        assert B.BudgetEnforcer.check(budget, usage)["level"] == "ok"


# ================================================================== 2. _GovernanceContext elapsed / check_execution_time


class TestGovernanceExecutionTime:
    def test_elapsed_zero_without_start(self):
        assert _gov().elapsed() == 0.0

    def test_elapsed_positive_with_start(self):
        g = _gov(execution_started=time.monotonic() - 1.5)
        assert g.elapsed() >= 1.4

    def test_check_no_budget_none(self):
        assert _gov().check_execution_time() is None

    def test_check_unbounded_none(self):
        g = _gov(budget=B.ProjectBudget(max_execution_time=0.0),
                 execution_started=time.monotonic() - 100)
        assert g.check_execution_time() is None

    def test_check_under_limit_none(self):
        g = _gov(budget=B.ProjectBudget(max_execution_time=3600.0),
                 execution_started=time.monotonic())
        assert g.check_execution_time() is None

    def test_check_timeout_blocked_without_gate(self):
        g = _gov(budget=B.ProjectBudget(max_execution_time=0.01),
                 execution_started=time.monotonic() - 5.0)
        stop = g.check_execution_time()
        assert stop is not None
        assert stop["status"] == "blocked"
        assert "执行超时" in stop["reason"]

    def test_check_timeout_waiting_review_with_gate(self, tmp_path):
        gate = RG.ReviewGate(file=tmp_path / "reviews.json")
        g = _gov(budget=B.ProjectBudget(max_execution_time=0.01),
                 review_gate=gate, execution_started=time.monotonic() - 5.0)
        stop = g.check_execution_time()
        assert stop is not None
        assert stop["status"] == "waiting_for_review"
        assert gate.status("demo") == "waiting"  # 评审已请求

    def test_usage_includes_wall_clock_execution_time(self):
        """_usage(): max_execution_time > 0 → execution_time 以 wall-clock 覆盖。"""
        g = _gov(budget=B.ProjectBudget(max_execution_time=10.0),
                 cost_ledger=CL.CostLedger(file=Path("/tmp/__none__/c.json")),
                 execution_started=time.monotonic() - 2.0)
        usage = g._usage()
        assert usage.execution_time >= 1.9

    def test_usage_unchanged_when_unbounded(self):
        """max_execution_time=0 (无限) → _usage 不覆盖 execution_time。"""
        g = _gov(budget=B.ProjectBudget(max_execution_time=0.0),
                 execution_started=time.monotonic() - 100.0)
        assert g._usage().execution_time == 0.0


# ================================================================== 3. orchestrator 集成


class TestOrchestratorMaxExecutionTime:
    def test_slow_execution_stops_blocked(self, tmp_path):
        """慢执行 → 停止 (blocked), 剩余任务不执行, 原因可解释落盘。"""
        pd = _make_project(tmp_path)
        budget = B.ProjectBudget(max_execution_time=0.15)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=_slow_fn(0.35), budget=budget)
        assert res.status == "blocked"
        assert res.completed_tasks < 2  # 至少一个任务未执行
        state = ORCH.ExecutionState.load(pd / "execution_state.json")
        assert state.governance_status == "blocked"
        assert "执行超时" in state.governance_reason

    def test_slow_execution_stops_waiting_review(self, tmp_path):
        """有 review_gate → 停止 (waiting_for_review) + 评审记录。"""
        pd = _make_project(tmp_path)
        gate = RG.ReviewGate(file=pd / "reviews.json")
        budget = B.ProjectBudget(max_execution_time=0.15)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=_slow_fn(0.35),
                                   budget=budget, review_gate=gate)
        assert res.status == "waiting_for_review"
        assert gate.status("demo") == "waiting"
        state = ORCH.ExecutionState.load(pd / "execution_state.json")
        assert state.governance_status == "waiting_for_review"

    def test_fast_execution_completes(self, tmp_path):
        """未超时 → 正常执行 (全部完成 → user_acceptance)。"""
        _make_project(tmp_path)
        budget = B.ProjectBudget(max_execution_time=3600.0)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=_ok_fn, budget=budget)
        assert res.status == "user_acceptance"
        assert res.completed_tasks == 2

    def test_no_budget_unchanged(self, tmp_path):
        """无 budget → 原行为 (无执行时间闸)。"""
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=_slow_fn(0.05))
        assert res.status == "user_acceptance"
        assert res.completed_tasks == 2

    def test_default_budget_unbounded_time(self, tmp_path):
        """缺省预算 max_execution_time=0 (无限) → 不触发超时。"""
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=_slow_fn(0.05),
                                   budget=B.ProjectBudget())
        assert res.status == "user_acceptance"

    def test_slow_execution_stops_records_execution_costs(self, tmp_path):
        """超时停止前已完成任务仍记成本 (execution_time 聚合可查)。"""
        pd = _make_project(tmp_path)
        ledger = CL.CostLedger(file=pd / "cost_records.json")
        budget = B.ProjectBudget(max_execution_time=0.15)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=_slow_fn(0.35),
                                   budget=budget, cost_ledger=ledger)
        assert res.status == "blocked"
        records = ledger.records("demo")
        assert records  # 至少完成任务的 EXECUTION 记录
        usage = B.BudgetUsage.from_records(records, budget=budget)
        assert usage.execution_time > 0.0

    def test_state_lifecycle_stays_development_on_timeout(self, tmp_path):
        """超时停止 → lifecycle 保持 DEVELOPMENT (可 resume)。"""
        pd = _make_project(tmp_path)
        budget = B.ProjectBudget(max_execution_time=0.15)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=_slow_fn(0.35), budget=budget)
        assert res.status == "blocked"
        state = ORCH.ExecutionState.load(pd / "execution_state.json")
        assert state.lifecycle == ORCH.Lifecycle.DEVELOPMENT
