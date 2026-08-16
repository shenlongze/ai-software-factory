"""S10-065 批次 C — CostLedger ↔ PlanningTrace 关联测试套件。

覆盖 (验收 A/B/F/G):
- CostRecord trace_id / planning_decision_id 字段 (to_dict/from_dict/缺省)
- record(trace_id=..., planning_decision_id=...) → 落盘关联
- cost_by_trace / cost_by_task / cost_by_agent / cost_by_planning_decision
- aggregate by_trace (trace 级聚合)
- 向后兼容 (无 trace_id 调用 / 旧格式 ledger 文件不变)
- orchestrator 实际使用: planning_trace 记录 → cost_ledger.record(trace_id)
  同步 (GAP_ANALYSIS / PLANNING) + 失败安全

装配: tmp_path + fixtures; mock execute_fn + llm_fn; 禁真实 LLM/网络。

"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from importlib import import_module

CL = import_module("factory-console.session.cost_ledger")
ORCH = import_module("factory-console.session.orchestrator")
R = import_module("factory-console.session.reasoning")
PT = import_module("factory-console.session.planning_trace")


def _ledger(tmp_path: Path) -> CL.CostLedger:
    return CL.CostLedger(file=tmp_path / "cost_records.json")


def _base(**overrides) -> dict:
    base = {
        "project_id": "p1",
        "task_id": "T1",
        "agent_id": "A1",
        "purpose": "EXECUTION",
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "estimated_cost": 0.02,
        "latency": 1.0,
    }
    base.update(overrides)
    return base


def _make_project(tmp_path: Path, tasks: list | None = None) -> Path:
    pd = tmp_path / "projects" / "demo"
    pd.mkdir(parents=True, exist_ok=True)
    chosen = tasks if tasks is not None else [{"id": "T001", "name": "计分逻辑"}]
    (pd / "execution_plan.json").write_text(
        json.dumps({"tasks": chosen, "count": len(chosen)}, ensure_ascii=False), encoding="utf-8")
    (pd / "project.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
    (pd / "product.json").write_text(json.dumps({"name": "D", "status": "execution_ready"}), encoding="utf-8")
    return pd


def _fail_fn(calls, gap_error="缺少持久化存储 — persistence missing"):
    def fn(task, project_dir, workspace):
        calls.append(task["id"])
        if task["id"] == "T001":
            return {"success": False, "error": gap_error}
        return {"success": True, "artifact": f"/tmp/{task['id']}", "cost": "1"}
    return fn


_GAP_JSON = {
    "detected": True, "gap_type": "missing_implementation",
    "description": "缺持久化", "evidence": [], "severity": "high",
    "source_task_id": "T001", "confidence": 0.8, "duplicate_of": None,
    "recommended_action": "INSERT_TASK", "reason": "persistence",
}

_PROPOSAL_JSON = {
    "task_id": "", "title": "实现持久化", "description": "d",
    "objective": "为比赛记录增加持久化", "required_role": "backend",
    "dependencies": ["T001"], "acceptance_criteria": ["数据可保存"],
    "validation_command": "pytest", "priority": "high",
    "rationale": "WHY: 解决 missing_implementation 缺口", "confidence": 0.8,
    "source_gap": "missing_implementation@T001",
}


def _gap_fn(prompt, operation=""):
    return json.dumps(_GAP_JSON, ensure_ascii=False)


def _combo_fn(prompt, operation=""):
    if "propose" in str(operation).lower():
        return json.dumps(_PROPOSAL_JSON, ensure_ascii=False)
    return json.dumps(_GAP_JSON, ensure_ascii=False)


# ================================================================== 1. CostRecord trace 字段


class TestCostRecordTrace:
    def test_from_dict_trace_fields(self):
        rec = CL.CostRecord.from_dict(
            _base(trace_id="tr-1", planning_decision_id="llm_gap")
        )
        assert rec.trace_id == "tr-1"
        assert rec.planning_decision_id == "llm_gap"
        assert rec.to_dict()["trace_id"] == "tr-1"
        assert rec.to_dict()["planning_decision_id"] == "llm_gap"

    def test_from_dict_missing_trace_defaults_empty(self):
        rec = CL.CostRecord.from_dict({})
        assert rec.trace_id == ""
        assert rec.planning_decision_id == ""

    def test_legacy_record_no_trace_fields(self):
        """旧格式 dict (无 trace 字段) → 归一化后 trace 字段为空 (向后兼容)。"""
        d = CL.CostRecord.from_dict(_base()).to_dict()
        assert d["trace_id"] == ""
        assert d["planning_decision_id"] == ""
        assert d["estimated_cost"] == 0.02  # 原字段不变

    def test_record_with_trace_id_persists(self, tmp_path):
        ledger = _ledger(tmp_path)
        ledger.record(_base(), trace_id="tr-1")
        records = ledger.load()
        assert records[0]["trace_id"] == "tr-1"

    def test_record_with_planning_decision_id_persists(self, tmp_path):
        ledger = _ledger(tmp_path)
        ledger.record(_base(), planning_decision_id="llm_proposal")
        records = ledger.load()
        assert records[0]["planning_decision_id"] == "llm_proposal"

    def test_record_dict_with_trace_key(self, tmp_path):
        """trace_id 直接放 dict 内也可关联 (from_dict 归一化)。"""
        ledger = _ledger(tmp_path)
        ledger.record(_base(trace_id="tr-x", planning_decision_id="d1"))
        assert ledger.load()[0]["trace_id"] == "tr-x"
        assert ledger.load()[0]["planning_decision_id"] == "d1"


# ================================================================== 2. cost_by_* 查询


class TestCostByQueries:
    def test_cost_by_trace_sums_matching(self, tmp_path):
        ledger = _ledger(tmp_path)
        ledger.record(_base(estimated_cost=0.02), trace_id="tr-1")
        ledger.record(_base(task_id="T2", estimated_cost=0.03), trace_id="tr-1")
        assert ledger.cost_by_trace("tr-1") == 0.05

    def test_cost_by_trace_excludes_other_traces(self, tmp_path):
        ledger = _ledger(tmp_path)
        ledger.record(_base(estimated_cost=0.02), trace_id="tr-1")
        ledger.record(_base(task_id="T2", estimated_cost=0.09), trace_id="tr-2")
        assert ledger.cost_by_trace("tr-1") == 0.02
        assert ledger.cost_by_trace("tr-2") == 0.09

    def test_cost_by_trace_empty_key_zero(self, tmp_path):
        ledger = _ledger(tmp_path)
        ledger.record(_base())
        assert ledger.cost_by_trace("") == 0.0
        assert ledger.cost_by_trace(None) == 0.0

    def test_cost_by_trace_no_match_zero(self, tmp_path):
        ledger = _ledger(tmp_path)
        ledger.record(_base(), trace_id="tr-1")
        assert ledger.cost_by_trace("tr-999") == 0.0

    def test_cost_by_task_sums(self, tmp_path):
        ledger = _ledger(tmp_path)
        ledger.record(_base(estimated_cost=0.02))
        ledger.record(_base(purpose="REPAIR", estimated_cost=0.01))
        ledger.record(_base(task_id="T2", estimated_cost=0.05))
        assert ledger.cost_by_task("T1") == 0.03
        assert ledger.cost_by_task("T2") == 0.05

    def test_cost_by_task_no_match_zero(self, tmp_path):
        ledger = _ledger(tmp_path)
        ledger.record(_base(task_id="T1"))
        assert ledger.cost_by_task("T9") == 0.0

    def test_cost_by_agent_sums(self, tmp_path):
        ledger = _ledger(tmp_path)
        ledger.record(_base(estimated_cost=0.02))
        ledger.record(_base(task_id="T2", estimated_cost=0.03))
        ledger.record(_base(agent_id="A2", estimated_cost=0.07))
        assert ledger.cost_by_agent("A1") == 0.05
        assert ledger.cost_by_agent("A2") == 0.07

    def test_cost_by_planning_decision_sums(self, tmp_path):
        ledger = _ledger(tmp_path)
        ledger.record(_base(estimated_cost=0.02), planning_decision_id="llm_gap")
        ledger.record(_base(task_id="T2", estimated_cost=0.03), planning_decision_id="llm_gap")
        ledger.record(_base(task_id="T3", estimated_cost=0.06), planning_decision_id="llm_proposal")
        assert ledger.cost_by_planning_decision("llm_gap") == 0.05
        assert ledger.cost_by_planning_decision("llm_proposal") == 0.06

    def test_cost_by_planning_decision_no_match_zero(self, tmp_path):
        ledger = _ledger(tmp_path)
        ledger.record(_base(), planning_decision_id="llm_gap")
        assert ledger.cost_by_planning_decision("other") == 0.0


# ================================================================== 3. aggregate by_trace


class TestAggregateByTrace:
    def test_aggregate_by_trace_buckets(self, tmp_path):
        ledger = _ledger(tmp_path)
        ledger.record(_base(estimated_cost=0.02, total_tokens=15), trace_id="tr-1")
        ledger.record(_base(task_id="T2", estimated_cost=0.03, total_tokens=25), trace_id="tr-1")
        ledger.record(_base(task_id="T3", estimated_cost=0.04, total_tokens=35), trace_id="tr-2")
        agg = ledger.aggregate("p1")
        assert agg["by_trace"]["tr-1"]["cost"] == 0.05
        assert agg["by_trace"]["tr-1"]["tokens"] == 40
        assert agg["by_trace"]["tr-1"]["calls"] == 2
        assert agg["by_trace"]["tr-2"]["cost"] == 0.04
        assert agg["by_trace"]["tr-2"]["calls"] == 1

    def test_aggregate_by_trace_excludes_empty(self, tmp_path):
        ledger = _ledger(tmp_path)
        ledger.record(_base())  # 无 trace_id
        ledger.record(_base(task_id="T2"), trace_id="tr-1")
        agg = ledger.aggregate("p1")
        assert set(agg["by_trace"].keys()) == {"tr-1"}

    def test_aggregate_by_trace_empty_when_none(self, tmp_path):
        ledger = _ledger(tmp_path)
        ledger.record(_base())
        assert ledger.aggregate("p1")["by_trace"] == {}

    def test_aggregate_total_unchanged_with_trace(self, tmp_path):
        """by_trace 不影响既有聚合口径。"""
        ledger = _ledger(tmp_path)
        ledger.record(_base(estimated_cost=0.02), trace_id="tr-1")
        ledger.record(_base(task_id="T2", estimated_cost=0.03, purpose="REPAIR"))
        agg = ledger.aggregate("p1")
        assert agg["total_cost"] == 0.05
        assert agg["record_count"] == 2
        assert agg["execution_cost"] == 0.02
        assert agg["repair_cost"] == 0.03


# ================================================================== 4. 向后兼容


class TestBackwardCompat:
    def test_record_without_trace_id_unchanged(self, tmp_path):
        """无 trace_id 调用 → 记录形状与 S10-063 一致 (仅新增空字段)。"""
        ledger = _ledger(tmp_path)
        rec = ledger.record(_base())
        assert rec["trace_id"] == ""
        assert rec["planning_decision_id"] == ""
        for key in ("project_id", "task_id", "agent_id", "purpose",
                    "estimated_cost", "latency", "timestamp"):
            assert key in rec

    def test_legacy_ledger_file_loaded(self, tmp_path):
        """旧格式 cost_records.json (无 trace 字段) → 读回兼容, 查询失败安全。"""
        file = tmp_path / "cost_records.json"
        file.write_text(json.dumps([_base()], ensure_ascii=False), encoding="utf-8")
        ledger = CL.CostLedger(file=file)
        records = ledger.load()
        assert records[0]["trace_id"] == ""
        assert records[0]["task_id"] == "T1"
        assert ledger.cost_by_trace("tr-1") == 0.0
        assert ledger.cost_by_task("T1") == 0.02
        assert ledger.cost_by_planning_decision("d") == 0.0

    def test_cost_by_queries_missing_file_zero(self, tmp_path):
        ledger = CL.CostLedger(file=tmp_path / "nope.json")
        assert ledger.cost_by_trace("tr-1") == 0.0
        assert ledger.cost_by_task("T1") == 0.0
        assert ledger.cost_by_agent("A1") == 0.0
        assert ledger.cost_by_planning_decision("d") == 0.0


# ================================================================== 5. orchestrator 实际使用 (同步)


class TestOrchestratorSync:
    def test_sync_gap_analysis_trace(self, tmp_path):
        """planning_trace 记录 → cost ledger 同步 (GAP_ANALYSIS + trace_id)。"""
        pd = _make_project(tmp_path)
        ledger = CL.CostLedger(file=pd / "cost_records.json")
        trace = PT.PlanningTrace(file=pd / "planning_trace.json")
        calls = []
        replanner = import_module("factory-console.session.replanning").ReplanningEngine(
            file=pd / "replanning_decisions.json")
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project(
            "demo", execute_fn=_fail_fn(calls), planning_mode="hybrid",
            llm_reasoning=R.ReasoningProvider(llm_fn=_gap_fn),
            llm_trace=trace, replanner=replanner, cost_ledger=ledger,
        )
        trace_ids = {t["trace_id"] for t in trace.load() if t.get("trace_id")}
        assert trace_ids, "LLM 路径应产生 planning trace"
        synced = [r for r in ledger.records("demo") if r.get("purpose") == "GAP_ANALYSIS"]
        assert synced, "planning trace 应同步成本记录"
        assert all(r.get("trace_id") in trace_ids for r in synced)

    def test_sync_propose_task_planning_decision(self, tmp_path):
        """propose_task trace → PLANNING 成本 + planning_decision_id 关联。"""
        pd = _make_project(tmp_path)
        ledger = CL.CostLedger(file=pd / "cost_records.json")
        trace = PT.PlanningTrace(file=pd / "planning_trace.json")
        calls = []
        replanner = import_module("factory-console.session.replanning").ReplanningEngine(
            file=pd / "replanning_decisions.json")
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project(
            "demo", execute_fn=_fail_fn(calls), planning_mode="hybrid",
            llm_reasoning=R.ReasoningProvider(llm_fn=_combo_fn),
            llm_trace=trace, replanner=replanner, cost_ledger=ledger,
        )
        recs = [r for r in ledger.records("demo") if r.get("purpose") == "PLANNING"]
        assert recs, "propose_task 应同步 PLANNING 成本"
        assert any(r.get("planning_decision_id") == "llm_proposal" for r in recs)
        # trace_id 与 planning_trace 对应
        trace_ids = {t["trace_id"] for t in trace.load() if t.get("trace_id")}
        assert any(r.get("trace_id") in trace_ids for r in recs)

    def test_sync_ledger_absent_noop(self, tmp_path):
        """无 cost_ledger → 同步 noop, 执行不中断。"""
        pd = _make_project(tmp_path)
        trace = PT.PlanningTrace(file=pd / "planning_trace.json")
        calls = []
        replanner = import_module("factory-console.session.replanning").ReplanningEngine(
            file=pd / "replanning_decisions.json")
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project(
            "demo", execute_fn=_fail_fn(calls), planning_mode="hybrid",
            llm_reasoning=R.ReasoningProvider(llm_fn=_gap_fn),
            llm_trace=trace, replanner=replanner,
        )
        assert trace.load()  # trace 仍记录
        assert res.status in ("user_acceptance", "failed", "review_required", "blocked")

    def test_sync_failure_safe(self, tmp_path):
        """同步时 ledger 抛异常 → 不中断执行流。"""
        pd = _make_project(tmp_path)
        trace = PT.PlanningTrace(file=pd / "planning_trace.json")
        calls = []
        replanner = import_module("factory-console.session.replanning").ReplanningEngine(
            file=pd / "replanning_decisions.json")
        orch = ORCH.ExecutionOrchestrator(tmp_path)

        class TraceBoomLedger(CL.CostLedger):
            """仅 trace_id 同步路径抛异常 (record_execution 路径委托真实 ledger)。"""

            def record(self, cost, trace_id=None, planning_decision_id=None):
                if trace_id is not None:
                    raise RuntimeError("sync boom")
                return super().record(cost, trace_id=trace_id,
                                      planning_decision_id=planning_decision_id)

        res = orch.execute_project(
            "demo", execute_fn=_fail_fn(calls), planning_mode="hybrid",
            llm_reasoning=R.ReasoningProvider(llm_fn=_gap_fn),
            llm_trace=trace, replanner=replanner,
            cost_ledger=TraceBoomLedger(file=pd / "cost_records.json"),
        )
        assert res.status in ("user_acceptance", "failed", "review_required", "blocked")

    def test_sync_planning_cost_helper_failure_safe(self):
        """_sync_planning_cost 直接调用: 无 governance/无 ledger → noop 不抛。"""
        orch = ORCH.ExecutionOrchestrator(Path("/tmp/__none__"))
        orch._sync_planning_cost(None, {"trace_id": "t"}, "PLANNING", {})  # noop
        gov = SimpleNamespace(cost_ledger=None, project_id="p")
        orch._sync_planning_cost(gov, {"trace_id": "t"}, "PLANNING", {})  # noop
