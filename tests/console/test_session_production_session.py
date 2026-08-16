"""S10-065 — ProductionSession 测试套件 (Batch A)。

覆盖: 聚合 ExecutionState/TeamExecutionState/CostLedger/ReviewGate →
统一视图 / get_* / progress / budget / cost / phase 映射 / to_markdown。

装配: tmp_path + fixtures; 禁真实 LLM/网络。
"""

from __future__ import annotations

import json
from pathlib import Path

from importlib import import_module

PS = import_module("factory-console.session.production_session")
CL = import_module("factory-console.session.cost_ledger")
RG = import_module("factory-console.session.review_gate")
B = import_module("factory-console.session.budget")


def _project(tmp_path: Path, slug: str = "scorepocket",
             status: str = "development", plan_version: int = 2,
             completed: int = 1, total: int = 3) -> Path:
    pd = tmp_path / "projects" / slug
    pd.mkdir(parents=True, exist_ok=True)
    (pd / "execution_state.json").write_text(json.dumps({
        "project": slug, "status": status, "lifecycle": status,
        "plan_version": plan_version, "replan_count": 1,
        "governance_status": "", "governance_reason": "",
        "tasks": [{"id": f"T00{i}", "name": f"任务{i}", "agent": f"agent-{i}",
                   "status": "completed" if i <= completed else "pending",
                   "retry_count": 0, "error": None} for i in range(1, total + 1)],
    }), encoding="utf-8")
    (pd / "team_execution_state.json").write_text(json.dumps({
        "team_id": "software-team", "status": status,
        "plan_version": plan_version,
        "tasks": {f"T00{i}": {"task_id": f"T00{i}", "agent": f"agent-{i}",
                              "status": "completed" if i < completed else "pending",
                              "name": f"任务{i}"} for i in range(1, total + 1)},
    }), encoding="utf-8")
    (pd / "product.json").write_text(json.dumps(
        {"name": "ScorePocket", "problem": "记分麻烦", "status": "confirmed"}),
        encoding="utf-8")
    (pd / "project.json").write_text(json.dumps({"name": slug}), encoding="utf-8")
    return pd


# ================================================================== 1. from_project / phase 映射


class TestFromProject:
    def test_initial(self, tmp_path):
        pd = _project(tmp_path, status="development")
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        assert s.project_id == "scorepocket"
        assert s.current_phase == PS.ProductionPhase.EXECUTING

    def test_phase_planning(self, tmp_path):
        pd = _project(tmp_path, status="engineering_ready")
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        assert s.current_phase == PS.ProductionPhase.PLANNING

    def test_phase_validating(self, tmp_path):
        pd = _project(tmp_path, status="validation_pass")
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        assert s.current_phase == PS.ProductionPhase.VALIDATING

    def test_phase_review(self, tmp_path):
        pd = _project(tmp_path, status="review_required")
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        assert s.current_phase == PS.ProductionPhase.WAITING_FOR_REVIEW

    def test_phase_blocked(self, tmp_path):
        pd = _project(tmp_path, status="blocked")
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        assert s.current_phase == PS.ProductionPhase.BLOCKED

    def test_phase_acceptance(self, tmp_path):
        pd = _project(tmp_path, status="user_acceptance")
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        assert s.current_phase == PS.ProductionPhase.USER_ACCEPTANCE

    def test_phase_delivered(self, tmp_path):
        pd = _project(tmp_path, status="delivered")
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        assert s.current_phase == PS.ProductionPhase.DELIVERED

    def test_phase_failed(self, tmp_path):
        pd = _project(tmp_path, status="failed")
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        assert s.current_phase == PS.ProductionPhase.FAILED

    def test_missing_files_safe(self, tmp_path):
        pd = tmp_path / "projects" / "ghost"
        pd.mkdir(parents=True)
        s = PS.ProductionSession.from_project(pd, "ghost")
        assert s.current_phase == PS.ProductionPhase.STARTING  # 失败安全

    def test_plan_version(self, tmp_path):
        pd = _project(tmp_path, plan_version=3)
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        assert s.plan_version == 3


# ================================================================== 2. progress


class TestProgress:
    def test_progress_value(self, tmp_path):
        pd = _project(tmp_path, completed=2, total=4)
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        assert s.completed_tasks == 2
        assert s.total_tasks == 4
        assert 0.49 <= s.get_progress() <= 0.51

    def test_progress_zero_total(self, tmp_path):
        pd = _project(tmp_path, completed=0, total=0)
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        assert s.get_progress() == 0.0  # 失败安全

    def test_progress_full(self, tmp_path):
        pd = _project(tmp_path, completed=3, total=3)
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        assert s.get_progress() == 1.0


# ================================================================== 3. team


class TestTeam:
    def test_team_status(self, tmp_path):
        pd = _project(tmp_path, completed=1, total=3)
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        team = s.get_team_status()
        assert len(team) == 3
        assert team[0]["status"] in ("completed", "done", "working", "pending", "idle")
        assert team[1]["status"] in ("completed", "done", "working", "pending", "idle")

    def test_team_members_field(self, tmp_path):
        pd = _project(tmp_path)
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        assert isinstance(s.team_members, list)


# ================================================================== 4. cost


class TestCost:
    def test_cost_status(self, tmp_path):
        pd = _project(tmp_path)
        ledger = CL.CostLedger(file=tmp_path / "cost_records.json")
        ledger.record({"project_id": "scorepocket", "task_id": "T001",
                       "purpose": "EXECUTION", "total_tokens": 100,
                       "estimated_cost": 0.001})
        budget = B.ProjectBudget(max_total_cost=0.01)
        s = PS.ProductionSession.from_project(pd, "scorepocket",
                                              budget=budget, cost_ledger=ledger)
        cost = s.get_cost_status()
        assert cost["current_cost"] == 0.001
        assert cost["budget_limit"] == 0.01
        assert 0.09 <= cost["cost_percentage"] <= 0.11

    def test_cost_no_ledger(self, tmp_path):
        pd = _project(tmp_path)
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        cost = s.get_cost_status()
        assert cost["current_cost"] == 0.0  # 失败安全

    def test_budget_fields(self, tmp_path):
        pd = _project(tmp_path)
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        assert s.budget_limit is not None or s.budget_limit == 0.0


# ================================================================== 5. governance


class TestGovernance:
    def test_governance_status(self, tmp_path):
        pd = _project(tmp_path, status="blocked")
        pd.joinpath("execution_state.json").write_text(json.dumps({
            "project": "scorepocket", "status": "blocked",
            "governance_status": "blocked",
            "governance_reason": "budget exhausted",
        }), encoding="utf-8")
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        gov = s.get_governance_status()
        assert gov["status"] == "blocked"
        assert gov["reason"] == "budget exhausted"

    def test_governance_none(self, tmp_path):
        pd = _project(tmp_path)
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        gov = s.get_governance_status()
        assert gov["status"] in ("", "none", "ok")


# ================================================================== 6. review


class TestReview:
    def test_pending_review(self, tmp_path):
        pd = _project(tmp_path, status="review_required")
        gate = RG.ReviewGate(file=tmp_path / "review_records.json")
        gate.request(reason="budget 90%", trigger="budget_review",
                     context={"project_id": "scorepocket"},
                     affected_tasks=["T001"], estimated_cost=0.01, risk="medium")
        s = PS.ProductionSession.from_project(pd, "scorepocket", review_gate=gate)
        review = s.get_review()
        assert review is not None
        assert review["reason"] == "budget 90%"

    def test_no_review(self, tmp_path):
        pd = _project(tmp_path)
        gate = RG.ReviewGate(file=tmp_path / "review_records.json")
        s = PS.ProductionSession.from_project(pd, "scorepocket", review_gate=gate)
        assert s.get_review() is None

    def test_pending_review_flag(self, tmp_path):
        pd = _project(tmp_path, status="review_required")
        gate = RG.ReviewGate(file=tmp_path / "review_records.json")
        gate.request(reason="r", trigger="t", context={"project_id": "scorepocket"},
                     affected_tasks=[], estimated_cost=0, risk="low")
        s = PS.ProductionSession.from_project(pd, "scorepocket", review_gate=gate)
        assert s.pending_review is True


# ================================================================== 7. view / to_markdown


class TestView:
    def test_get_status(self, tmp_path):
        pd = _project(tmp_path)
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        status = s.get_status()
        assert status["project_id"] == "scorepocket"
        assert status["current_phase"] == "executing"
        assert status["completed_tasks"] == 1
        assert status["plan_version"] == 2

    def test_view(self, tmp_path):
        pd = _project(tmp_path)
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        v = s.view()
        assert v["project_id"] == "scorepocket"
        assert "phase" in v or "current_phase" in v

    def test_to_markdown(self, tmp_path):
        pd = _project(tmp_path)
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        md = s.to_markdown()
        assert "ScorePocket" in md
        assert "任务" in md
        assert "EXECUTING" in md.upper() or "executing" in md

    def test_to_markdown_budget(self, tmp_path):
        pd = _project(tmp_path)
        ledger = CL.CostLedger(file=tmp_path / "cost_records.json")
        ledger.record({"project_id": "scorepocket", "purpose": "EXECUTION",
                       "total_tokens": 100, "estimated_cost": 0.001})
        s = PS.ProductionSession.from_project(pd, "scorepocket",
                                              budget=B.ProjectBudget(max_total_cost=0.01),
                                              cost_ledger=ledger)
        md = s.to_markdown()
        assert "$" in md or "cost" in md.lower() or "预算" in md

    def test_refresh(self, tmp_path):
        pd = _project(tmp_path, completed=1, total=3)
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        # 更新底层状态
        _project(tmp_path, completed=2, total=3)
        s.refresh(pd)
        assert s.completed_tasks == 2


# ================================================================== 8. 补充


class TestMore:
    def test_import(self, tmp_path):
        assert PS.ProductionSession is not None

    def test_phase_constants(self, tmp_path):
        assert PS.ProductionPhase.EXECUTING == "executing"
        assert PS.ProductionPhase.WAITING_FOR_REVIEW == "waiting_for_review"
        assert PS.ProductionPhase.DELIVERED == "delivered"

    def test_updated_at(self, tmp_path):
        pd = _project(tmp_path)
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        assert s.updated_at

    def test_last_event_none(self, tmp_path):
        pd = _project(tmp_path)
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        # last_event 是 ProductionEvent 对象 (或 None)
        assert s.last_event is None or hasattr(s.last_event, "message")

    def test_progress_text(self, tmp_path):
        pd = _project(tmp_path, completed=1, total=3)
        s = PS.ProductionSession.from_project(pd, "scorepocket")
        assert s.completed_tasks == 1
        assert s.total_tasks == 3
