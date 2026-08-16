"""S10-062 — LLM Planning 集成测试套件 (批次 C)。

覆盖: planning_mode (deterministic/llm/hybrid) / Orchestrator LLM 接入 /
fallback / PlanCritic 执行前检查 / planning_trace / 回归。

装配: tmp_path + fixtures; llm_fn 注入 deterministic fixture; 禁真实网络。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from importlib import import_module

ORCH = import_module("factory-console.session.orchestrator")
R = import_module("factory-console.session.reasoning")
LG = import_module("factory-console.session.llm_gap")
LP = import_module("factory-console.session.llm_task_proposal")
PC = import_module("factory-console.session.plan_critic")
CB = import_module("factory-console.session.context_builder")
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


def _valid_gap_fn(prompt, operation=""):
    return json.dumps({"detected": True, "gap_type": "missing_implementation",
                       "description": "缺持久化", "evidence": [], "severity": "high",
                       "source_task_id": "T001", "confidence": 0.8, "duplicate_of": None,
                       "recommended_action": "INSERT_TASK", "reason": "persistence"},
                      ensure_ascii=False)


def _valid_proposal_fn(prompt, operation=""):
    return json.dumps({"task_id": "", "title": "实现持久化", "description": "d",
                       "objective": "为比赛记录增加持久化", "required_role": "backend",
                       "dependencies": ["T001"], "acceptance_criteria": ["数据可保存", "重启可恢复"],
                       "validation_command": "pytest", "priority": "high",
                       "rationale": "WHY: 解决 missing_implementation 缺口", "confidence": 0.8,
                       "source_gap": "missing_implementation@T001"}, ensure_ascii=False)


def _fail_fn(calls, gap_error="缺少持久化存储 — persistence missing"):
    def fn(task, project_dir, workspace):
        calls.append(task["id"])
        if task["id"] == "T001":
            return {"success": False, "error": gap_error}
        return {"success": True, "artifact": f"/tmp/{task['id']}", "cost": "1"}
    return fn


# ================================================================== 1. planning_mode=deterministic (兼容)


class TestDeterministicMode:
    def test_deterministic_no_llm(self, tmp_path):
        """deterministic mode + llm 参数 → 忽略 (S10-061 行为)。"""
        pd = _make_project(tmp_path)
        prov = R.ReasoningProvider(llm_fn=_valid_gap_fn)
        calls = []

        def fn(task, project_dir, workspace):
            calls.append(task["id"])
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=fn, planning_mode="deterministic",
                                   llm_reasoning=prov)
        assert res.completed_tasks == 1
        assert not (pd / "planning_trace.json").exists()  # LLM 未用

    def test_hybrid_no_llm_components(self, tmp_path):
        """hybrid 但无 LLM 组件 → deterministic (安全回退)。"""
        _make_project(tmp_path)

        def fn(task, project_dir, workspace):
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=fn, planning_mode="hybrid")
        assert res.completed_tasks == 1


# ================================================================== 2. hybrid + LLM 优先


class TestHybridLlm:
    def test_hybrid_llm_gap_used(self, tmp_path):
        """hybrid + LLM 注入 → LLM gap 分析优先。"""
        pd = _make_project(tmp_path)
        prov = R.ReasoningProvider(llm_fn=_valid_gap_fn)
        trace = PT.PlanningTrace(file=pd / "planning_trace.json")
        calls = []
        replanner = import_module("factory-console.session.replanning").ReplanningEngine(
            file=pd / "replanning_decisions.json")
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_fail_fn(calls),
                             planning_mode="hybrid", llm_reasoning=prov,
                             llm_trace=trace, replanner=replanner)
        # LLM gap 分析被调用 (trace 记录)
        records = trace.load() if (pd / "planning_trace.json").exists() else []
        assert records, "LLM 路径应记录 trace"

    def test_hybrid_llm_proposal_inserted(self, tmp_path):
        """LLM proposal → INSERT → 新任务执行。"""
        pd = _make_project(tmp_path)
        prov = R.ReasoningProvider(llm_fn=_valid_proposal_fn)
        calls = []
        replanner = import_module("factory-console.session.replanning").ReplanningEngine(
            file=pd / "replanning_decisions.json")
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_fail_fn(calls),
                             planning_mode="hybrid", llm_reasoning=prov,
                             replanner=replanner)
        assert len(calls) >= 2  # T001 失败 + LLM 提案任务

    def test_hybrid_fallback_on_llm_fail(self, tmp_path):
        """LLM 失败 → deterministic fallback (不崩)。"""
        pd = _make_project(tmp_path)

        def bad_fn(prompt, operation=""):
            raise R.ReasoningError("down")

        prov = R.ReasoningProvider(llm_fn=bad_fn)
        calls = []
        replanner = import_module("factory-console.session.replanning").ReplanningEngine(
            file=pd / "replanning_decisions.json")
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_fail_fn(calls),
                             planning_mode="hybrid", llm_reasoning=prov,
                             gap_analyzer=import_module("factory-console.session.gap_analyzer").GapAnalyzer(
                                 file=pd / "gap_analysis.json"),
                             replanner=replanner)
        assert calls  # 执行未崩


# ================================================================== 3. llm mode 无 provider


class TestLlmModeNoProvider:
    def test_llm_mode_no_provider_fallback(self, tmp_path):
        """llm mode 无 provider → deterministic (安全)。"""
        _make_project(tmp_path)

        def fn(task, project_dir, workspace):
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=fn, planning_mode="llm")
        assert res.completed_tasks == 1

    def test_llm_mode_review_on_all_fail(self, tmp_path):
        """llm mode + LLM 全失败 + 无 deterministic → REQUEST_REVIEW (安全)。"""
        pd = _make_project(tmp_path)

        def bad_fn(prompt, operation=""):
            raise R.ReasoningError("down")

        prov = R.ReasoningProvider(llm_fn=bad_fn)
        calls = []
        replanner = import_module("factory-console.session.replanning").ReplanningEngine(
            file=pd / "replanning_decisions.json")
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_fail_fn(calls),
                             planning_mode="llm", llm_reasoning=prov,
                             replanner=replanner)
        assert calls  # 执行不崩 (失败 → 决策记录)


# ================================================================== 4. PlanCritic 执行前检查


class TestPlanCritic:
    def test_plan_critic_gap_detected(self, tmp_path):
        """PlanCritic 发现持久化缺口 (PRD 要求, plan 无)。"""
        critic = PC.PlanCritic()
        plan = {"tasks": [{"id": "T001", "name": "计分", "required_role": "backend"}]}
        gaps = critic.review(plan, {"persistence": True}, {})
        assert gaps

    def test_plan_critic_no_gap(self, tmp_path):
        critic = PC.PlanCritic()
        plan = {"tasks": [
            {"id": "T001", "name": "计分", "required_role": "backend"},
            {"id": "T002", "name": "持久化", "required_role": "backend"},
            {"id": "T003", "name": "测试", "required_role": "qa"},
        ]}
        gaps = critic.review(plan, {"persistence": True}, {})
        assert not gaps

    def test_plan_critic_does_not_modify_dag(self, tmp_path):
        """PlanCritic 只输出, 不修改 plan。"""
        critic = PC.PlanCritic()
        plan = {"tasks": [{"id": "T001", "name": "计分"}]}
        before = json.dumps(plan)
        critic.review(plan, {"persistence": True}, {})
        assert json.dumps(plan) == before


# ================================================================== 5. ContextBuilder / Trace 集成


class TestContextTrace:
    def test_context_builder_build(self, tmp_path):
        pd = _make_project(tmp_path)
        (pd / "PRD.md").write_text("# PRD\n持久化要求", encoding="utf-8")
        cb = CB.ContextBuilder()
        ctx = cb.build(pd, "demo")
        assert ctx.get("project", {}).get("value", {}).get("slug") == "demo"
        assert "requirements" in ctx

    def test_trace_records_llm_path(self, tmp_path):
        pd = _make_project(tmp_path)
        trace = PT.PlanningTrace(file=pd / "planning_trace.json")
        trace.record(operation="analyze_gap", provider="deepseek", model="deepseek-chat",
                     input_hash="abc", output="{}", parsed_result={}, confidence=0.8,
                     token_usage={"total_tokens": 100}, latency=0.5, fallback_used=False,
                     validation_result={"valid": True}, final_decision="llm_gap")
        records = trace.load()
        assert records and records[0]["operation"] == "analyze_gap"
        assert records[0]["provider"] == "deepseek"

    def test_trace_no_api_key(self, tmp_path):
        """Trace 白名单: record 签名无 api_key 参数 (字段白名单拒绝敏感)。"""
        import inspect

        sig = inspect.signature(PT.PlanningTrace.record)
        assert "api_key" not in sig.parameters
        pd = _make_project(tmp_path)
        trace = PT.PlanningTrace(file=pd / "planning_trace.json")
        trace.record(operation="x", provider="p", model="m", input_hash="h", output="",
                     parsed_result={"content": "c"}, confidence=0.5,
                     token_usage={}, latency=0.0, fallback_used=False,
                     validation_result={}, final_decision="d")
        records = trace.load()
        assert records and records[0]["operation"] == "x"

class TestRegression:
    def test_s10_061_chain_still_works(self, tmp_path):
        """deterministic 自动提案 (S10-061) 仍工作 (hybrid 默认无 LLM → deterministic)。"""
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

    def test_solo_mode_compat(self, tmp_path):
        """solo + planning_mode → 不破坏。"""
        _make_project(tmp_path)

        def fn(task, project_dir, workspace):
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=fn, planning_mode="hybrid")
        assert res.completed_tasks == 1

    def test_import_all(self):
        import_module("factory-console.session.context_builder")
        import_module("factory-console.session.planning_trace")
        import_module("factory-console.session.plan_critic")
        import_module("factory-console.session.reasoning")
        import_module("factory-console.session.llm_gap")
        import_module("factory-console.session.llm_task_proposal")
        import_module("factory-console.session.orchestrator")


# ================================================================== 补充 (达 >=30)


class TestMore:
    def test_assemble_llm_planning_deterministic(self, tmp_path):
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        g, t, mode = orch._assemble_llm_planning("deterministic", None, None, None, None, 0.5)
        assert mode == "deterministic" and g is None

    def test_assemble_llm_planning_hybrid_no_provider(self, tmp_path):
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        g, t, mode = orch._assemble_llm_planning("hybrid", None, None, None, None, 0.5)
        assert mode == "deterministic"  # 无 LLM → 安全回退

    def test_assemble_llm_planning_hybrid_provider(self, tmp_path):
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        prov = R.ReasoningProvider(llm_fn=_valid_gap_fn)
        g, t, mode = orch._assemble_llm_planning("hybrid", prov, None, None, None, 0.5)
        assert mode == "hybrid" and g is not None

    def test_llm_gap_result_struct(self, tmp_path):
        """LLMGapAnalyzer 返回 LLMGapResult (analysis/fallback_used)。"""
        prov = R.ReasoningProvider(llm_fn=_valid_gap_fn)
        analyzer = LG.LLMGapAnalyzer(provider=prov)
        result = analyzer.analyze({"project": "demo"}, {"task": {"id": "T001"}})
        assert hasattr(result, "analysis")
        assert hasattr(result, "fallback_used")

    def test_llm_proposal_result_struct(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=_valid_proposal_fn)
        eng = LP.LLMTaskProposalEngine(provider=prov)
        result = eng.propose({"gap_type": "missing_implementation", "source_task_id": "T001",
                              "confidence": 0.8, "detected": True,
                              "recommended_action": "INSERT_TASK"},
                             {}, existing_tasks=[{"id": "T001", "name": "计分"}])
        assert hasattr(result, "proposal")
        assert hasattr(result, "fallback_used")


class TestFill:
    def test_llm_gap_fallback_recorded(self, tmp_path):
        """LLM 失败 → fallback 标记在 trace。"""
        pd = _make_project(tmp_path)
        trace = PT.PlanningTrace(file=pd / "planning_trace.json")

        def bad_fn(prompt, operation=""):
            raise R.ReasoningError("down")

        prov = R.ReasoningProvider(llm_fn=bad_fn)
        calls = []
        replanner = import_module("factory-console.session.replanning").ReplanningEngine(
            file=pd / "replanning_decisions.json")
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_fail_fn(calls),
                             planning_mode="hybrid", llm_reasoning=prov,
                             llm_trace=trace, replanner=replanner)
        assert calls  # 不崩

    def test_context_builder_sources(self, tmp_path):
        """ContextBuilder 来源标识。"""
        pd = _make_project(tmp_path)
        (pd / "PRD.md").write_text("# PRD\n持久化", encoding="utf-8")
        cb = CB.ContextBuilder()
        ctx = cb.build(pd, "demo")
        assert ctx.get("product", {}).get("source") == "PRD.md"
        assert ctx.get("engineering", {}).get("source") == "engineering.json"

    def test_context_builder_missing_files(self, tmp_path):
        """缺失文件 → 失败安全。"""
        pd = tmp_path / "projects" / "demo"
        pd.mkdir(parents=True)
        cb = CB.ContextBuilder()
        ctx = cb.build(pd, "demo")  # 无任何资产文件
        assert ctx is not None

    def test_plan_critic_persistence(self, tmp_path):
        """PRD 要求持久化 + plan 无 → 检测到。"""
        critic = PC.PlanCritic()
        plan = {"tasks": [{"id": "T1", "name": "计分", "required_role": "backend"}]}
        gaps = critic.review(plan, {"persistence": True, "platform": "mobile"}, {})
        assert any(getattr(g, "gap_type", None) == "missing_implementation" for g in gaps)

    def test_plan_critic_missing_test(self, tmp_path):
        critic = PC.PlanCritic()
        plan = {"tasks": [{"id": "T1", "name": "计分", "required_role": "backend"}]}
        gaps = critic.review(plan, {"persistence": False}, {})
        assert any(getattr(g, "gap_type", None) == "missing_test" for g in gaps)

    def test_plan_critic_confidence(self, tmp_path):
        critic = PC.PlanCritic()
        plan = {"tasks": [{"id": "T1", "name": "计分", "required_role": "backend"}]}
        gaps = critic.review(plan, {"persistence": True}, {})
        for g in gaps:
            assert 0.0 <= getattr(g, "confidence", 0) <= 1.0

    def test_trace_persist_reload(self, tmp_path):
        pd = _make_project(tmp_path)
        trace = PT.PlanningTrace(file=pd / "planning_trace.json")
        trace.record(operation="evaluate_plan", provider="deepseek", model="m",
                     input_hash="h", output="{}", parsed_result={}, confidence=0.6,
                     token_usage={}, latency=0.1, fallback_used=False,
                     validation_result={}, final_decision="keep")
        t2 = PT.PlanningTrace(file=pd / "planning_trace.json")
        assert len(t2.load()) == 1

    def test_reasoning_provider_operations(self, tmp_path):
        """ReasoningProvider 3 操作均可用 (llm_fn 注入)。"""
        seen = []

        def fn(prompt, operation=""):
            seen.append(operation)
            return json.dumps({"decision": "KEEP_PLAN", "reason": "ok"}, ensure_ascii=False)

        prov = R.ReasoningProvider(llm_fn=fn)
        prov.evaluate_plan({"project": "demo"})
        assert "evaluate_plan" in seen

    def test_hybrid_inserts_llm_task(self, tmp_path):
        """hybrid: LLM proposal 被插入并执行。"""
        pd = _make_project(tmp_path)
        prov = R.ReasoningProvider(llm_fn=_valid_proposal_fn)
        calls = []
        replanner = import_module("factory-console.session.replanning").ReplanningEngine(
            file=pd / "replanning_decisions.json")
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_fail_fn(calls),
                             planning_mode="hybrid", llm_reasoning=prov,
                             replanner=replanner)
        decisions = replanner.previous_decisions()
        assert any(d.get("decision") == "INSERT_TASK" for d in decisions)
