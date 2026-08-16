"""S10-062 批次 B — ReasoningProvider.propose_task + LLMTaskProposalEngine 测试套件。

覆盖 (验收 A/C/E/F):
- ReasoningProvider: propose_task 接口 / WHY/HOW/DEPENDENCY prompt /
  schema 校验 (缺字段) / deterministic 校验 (role/command/priority/
  confidence/rationale/acceptance/dependencies 合法面) / ReasoningError
- LLMTaskProposalEngine: 有效 → TaskProposal (WHY/HOW/DEPENDENCY 字段保留);
  task_id 系统侧推导 (T0XX 递增, 冲突检查 — LLM 不决定 id); 无效 → fallback
  deterministic; Validator 拒绝 (role/cycle/duplicate/confidence/依赖缺失/
  task_id 冲突) → fallback; 再失败 → REQUEST_REVIEW (proposal=None);
  fallback_used 标记; trace 落盘

装配: tmp_path + fixtures; llm_fn 注入 deterministic fixture; 禁真实网络/LLM。
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

import pytest

R = import_module("factory-console.session.reasoning")
P = import_module("factory-console.session.llm_task_proposal")
TP = import_module("factory-console.session.task_proposal")
GA = import_module("factory-console.session.gap_analyzer")
PT = import_module("factory-console.session.planning_trace")

VALID_PROPOSAL = {
    "task_id": "",
    "title": "为 T001 增加测试",
    "description": "由 T001 的测试缺口生成",
    "objective": "为 T001 增加测试覆盖",
    "required_role": "qa",
    "dependencies": ["T001"],
    "acceptance_criteria": ["pytest 通过", "测试覆盖新增缺口场景"],
    "validation_command": "pytest",
    "source_gap": "missing_test@T001",
    "rationale": "WHY: 该任务直接解决 missing_test 缺口 (T001 缺测试)",
    "confidence": 0.85,
    "priority": "medium",
}


def valid_proposal_fn(prompt, operation=""):
    return json.dumps(VALID_PROPOSAL, ensure_ascii=False)


def invalid_json_fn(prompt, operation=""):
    return "not json"


def api_error_fn(prompt, operation=""):
    raise R.ReasoningError("API error: 429")


def unavailable_fn(prompt, operation=""):
    raise R.ReasoningUnavailable("no provider")


def boom_fn(prompt, operation=""):
    raise ValueError("boom")


def make_gap(**overrides) -> "GA.GapAnalysis":
    """触发缺口 (missing_test — deterministic 模板存在)。"""
    return GA.GapAnalysis(
        detected=True,
        gap_type="missing_test",
        description="T001 缺少测试覆盖",
        severity="medium",
        source_task_id="T001",
        confidence=0.85,
        recommended_action="INSERT_TASK",
        reason="测试缺口",
    )


def make_context() -> dict:
    return {
        "project": {"name": "ScorePocket", "slug": "scorepocket"},
        "requirements": ["用户可记录分数"],
        "current_plan": [{"id": "T001", "name": "backend api"}],
    }


class FakeDag:
    """鸭子类型依赖图 (Validator 检查 6 — cycle_detect)。"""

    def __init__(self, cyclic: bool = False):
        self._cyclic = cyclic

    def cycle_detect(self, task_id, depends_on):
        return self._cyclic


def existing_tasks() -> list[dict]:
    return [{"id": "T001", "name": "backend api", "status": "completed"}]


# ================================================================== 1. ReasoningProvider.propose_task


class TestProviderProposeTask:
    def test_valid_response_returns_dict(self):
        prov = R.ReasoningProvider(llm_fn=valid_proposal_fn)
        d = prov.propose_task(make_gap(), make_context())
        assert isinstance(d, dict)
        assert d["title"] == "为 T001 增加测试"
        assert d["required_role"] == "qa"
        assert d["confidence"] == 0.85

    def test_prompt_contains_why_how_dependency(self):
        prov = R.ReasoningProvider(llm_fn=valid_proposal_fn)
        prompt = prov.build_prompt(
            R.OPERATION_PROPOSE_TASK, {"gap": make_gap().to_dict()}
        )
        assert "WHY" in prompt and "rationale" in prompt
        assert "HOW" in prompt and "acceptance_criteria" in prompt
        assert "DEPENDENCY" in prompt and "dependencies" in prompt

    def test_prompt_contains_gap_and_context(self):
        captured = {}

        def builder(op, payload):
            captured["payload"] = payload
            return "PROMPT"

        prov = R.ReasoningProvider(llm_fn=valid_proposal_fn,
                                   prompt_builder=builder)
        prov.propose_task(make_gap(), make_context())
        assert captured["payload"]["gap"]["gap_type"] == "missing_test"
        assert captured["payload"]["project"]["name"] == "ScorePocket"

    def test_llm_fn_receives_operation(self):
        seen = {}

        def fn(prompt, operation):
            seen["operation"] = operation
            return json.dumps(VALID_PROPOSAL)

        prov = R.ReasoningProvider(llm_fn=fn)
        prov.propose_task(make_gap(), {})
        assert seen["operation"] == R.OPERATION_PROPOSE_TASK

    def test_invalid_json_raises(self):
        prov = R.ReasoningProvider(llm_fn=invalid_json_fn)
        with pytest.raises(R.ReasoningError):
            prov.propose_task(make_gap(), {})

    def test_schema_missing_field_raises(self):
        def fn(prompt, operation=""):
            d = {k: v for k, v in VALID_PROPOSAL.items() if k != "title"}
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=fn)
        with pytest.raises(R.ReasoningError) as ei:
            prov.propose_task(make_gap(), {})
        assert "title" in str(ei.value)

    def test_invalid_role_raises(self):
        def fn(prompt, operation=""):
            d = dict(VALID_PROPOSAL)
            d["required_role"] = "gopher"
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=fn)
        with pytest.raises(R.ReasoningError) as ei:
            prov.propose_task(make_gap(), {})
        assert "required_role" in str(ei.value)

    def test_invalid_validation_command_raises(self):
        def fn(prompt, operation=""):
            d = dict(VALID_PROPOSAL)
            d["validation_command"] = "rm -rf /"
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=fn)
        with pytest.raises(R.ReasoningError) as ei:
            prov.propose_task(make_gap(), {})
        assert "validation_command" in str(ei.value)

    def test_invalid_priority_raises(self):
        def fn(prompt, operation=""):
            d = dict(VALID_PROPOSAL)
            d["priority"] = "urgent"
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=fn)
        with pytest.raises(R.ReasoningError) as ei:
            prov.propose_task(make_gap(), {})
        assert "priority" in str(ei.value)

    def test_missing_rationale_raises(self):
        # WHY 缺失 → provider 层 deterministic 校验拒绝
        def fn(prompt, operation=""):
            d = dict(VALID_PROPOSAL)
            d["rationale"] = ""
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=fn)
        with pytest.raises(R.ReasoningError) as ei:
            prov.propose_task(make_gap(), {})
        assert "rationale" in str(ei.value)

    def test_missing_acceptance_criteria_raises(self):
        # HOW 缺失 → provider 层拒绝
        def fn(prompt, operation=""):
            d = dict(VALID_PROPOSAL)
            d["acceptance_criteria"] = []
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=fn)
        with pytest.raises(R.ReasoningError) as ei:
            prov.propose_task(make_gap(), {})
        assert "acceptance_criteria" in str(ei.value)

    def test_bad_dependencies_raises(self):
        # DEPENDENCY 缺失/非法 → provider 层拒绝
        def fn(prompt, operation=""):
            d = dict(VALID_PROPOSAL)
            d["dependencies"] = [{"task": "T001"}]
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=fn)
        with pytest.raises(R.ReasoningError) as ei:
            prov.propose_task(make_gap(), {})
        assert "dependencies" in str(ei.value)

    def test_missing_source_gap_raises(self):
        def fn(prompt, operation=""):
            d = dict(VALID_PROPOSAL)
            d["source_gap"] = ""
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=fn)
        with pytest.raises(R.ReasoningError) as ei:
            prov.propose_task(make_gap(), {})
        assert "source_gap" in str(ei.value)

    def test_confidence_out_of_range_raises(self):
        def fn(prompt, operation=""):
            d = dict(VALID_PROPOSAL)
            d["confidence"] = 1.2
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=fn)
        with pytest.raises(R.ReasoningError):
            prov.propose_task(make_gap(), {})

    def test_api_error_raises(self):
        prov = R.ReasoningProvider(llm_fn=api_error_fn)
        with pytest.raises(R.ReasoningError):
            prov.propose_task(make_gap(), {})

    def test_gap_dict_input_accepted(self):
        prov = R.ReasoningProvider(llm_fn=valid_proposal_fn)
        d = prov.propose_task(make_gap().to_dict(), {})
        assert d["title"] == "为 T001 增加测试"

    def test_evaluate_plan_operation_not_touched(self):
        # propose_task 不应影响 evaluate_plan 契约 (独立操作)
        prov = R.ReasoningProvider(llm_fn=valid_proposal_fn)
        with pytest.raises(R.ReasoningError):
            prov.evaluate_plan({})  # proposal JSON 无 decision → schema 拒绝


# ================================================================== 2. LLMTaskProposalEngine


class TestLLMProposalEngineValid:
    def test_valid_llm_proposal(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=valid_proposal_fn)
        eng = P.LLMTaskProposalEngine(provider=prov,
                                      confidence_threshold=0.5)
        res = eng.propose(make_gap(), make_context(),
                          existing_tasks=existing_tasks())
        assert isinstance(res.proposal, TP.TaskProposal)
        assert res.source == "llm"
        assert res.fallback_used is False
        assert res.validation_result["valid"] is True

    def test_why_how_dependency_preserved(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=valid_proposal_fn)
        eng = P.LLMTaskProposalEngine(provider=prov)
        res = eng.propose(make_gap(), make_context(),
                          existing_tasks=existing_tasks())
        p = res.proposal
        assert "WHY" in p.rationale            # WHY 保留
        assert "pytest 通过" in p.acceptance_criteria  # HOW 保留
        assert "T001" in p.dependencies        # DEPENDENCY 保留
        assert p.source_gap == "missing_test@T001"
        assert p.required_role == "qa"

    def test_task_id_assigned_when_empty(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=valid_proposal_fn)  # task_id ""
        eng = P.LLMTaskProposalEngine(provider=prov)
        # existing_tasks 含 T001 (VALID_PROPOSAL 依赖 T001 — Validator 检查 dependencies 存在)
        res = eng.propose(make_gap(), {}, existing_tasks=[{"id": "T001", "name": "计分"}])
        assert res.proposal is not None
        assert res.proposal.task_id  # 系统侧推导非空

    def test_task_id_increments_with_existing(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=valid_proposal_fn)
        eng = P.LLMTaskProposalEngine(provider=prov)
        res = eng.propose(make_gap(), {},
                          existing_tasks=[{"id": "T001"}])
        assert res.proposal.task_id == "T002"

    def test_task_id_never_collides_with_source(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=valid_proposal_fn)
        eng = P.LLMTaskProposalEngine(provider=prov)
        # 缺口来源 T003 (最大后缀) → 新 id 必须 > T003
        gap = make_gap(source_task_id="T003")
        res = eng.propose(gap, {}, existing_tasks=[{"id": "T001"},
                                                   {"id": "T003"}])
        assert res.proposal.task_id == "T004"
        assert res.proposal.task_id != "T003"

    def test_replan_count_within_limit(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=valid_proposal_fn)
        eng = P.LLMTaskProposalEngine(provider=prov)
        res = eng.propose(make_gap(), {}, existing_tasks=existing_tasks(),
                          replan_count=3, max_replan=5)
        assert res.source == "llm"
        assert res.fallback_used is False

    def test_llm_prompt_builder_injectable(self, tmp_path):
        seen = {}

        def builder(gap, context):
            seen["gap"] = gap
            return "CUSTOM PROMPT"

        prov = R.ReasoningProvider(llm_fn=valid_proposal_fn)
        eng = P.LLMTaskProposalEngine(provider=prov,
                                      prompt_builder=builder)
        gap = make_gap()
        res = eng.propose(gap, make_context(), existing_tasks=existing_tasks())
        assert getattr(seen["gap"], "gap_type", None) == "missing_test" or seen["gap"].get("gap_type") == "missing_test"
        assert res.source == "llm"

    def test_trace_recorded_llm_path(self, tmp_path):
        trace = PT.PlanningTrace(file=tmp_path / "planning_trace.json")
        prov = R.ReasoningProvider(llm_fn=valid_proposal_fn)
        eng = P.LLMTaskProposalEngine(provider=prov, trace=trace)
        res = eng.propose(make_gap(), {}, existing_tasks=[{"id": "T001", "name": "计分"}])
        records = trace.load()
        assert len(records) == 1
        assert records[0]["operation"] == "propose_task"
        assert records[0]["fallback_used"] is False
        assert records[0]["final_decision"] == res.proposal.task_id


class TestLLMProposalEngineFallback:
    def test_invalid_json_falls_back_deterministic(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=invalid_json_fn)
        eng = P.LLMTaskProposalEngine(provider=prov)
        res = eng.propose(make_gap(), {}, existing_tasks=existing_tasks())
        assert res.fallback_used is True
        assert res.source == "deterministic"
        # missing_test 模板 → qa 角色
        assert res.proposal.required_role == "qa"
        assert res.proposal.confidence == 0.85  # 继承 gap confidence

    def test_api_error_falls_back(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=api_error_fn)
        eng = P.LLMTaskProposalEngine(provider=prov)
        res = eng.propose(make_gap(), {}, existing_tasks=existing_tasks())
        assert res.fallback_used is True
        assert "429" in res.reason

    def test_unavailable_falls_back(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=unavailable_fn)
        eng = P.LLMTaskProposalEngine(provider=prov)
        res = eng.propose(make_gap(), {}, existing_tasks=existing_tasks())
        assert res.fallback_used is True
        assert res.source == "deterministic"

    def test_unknown_exception_falls_back(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=boom_fn)
        eng = P.LLMTaskProposalEngine(provider=prov)
        res = eng.propose(make_gap(), {}, existing_tasks=existing_tasks())
        assert res.fallback_used is True
        assert res.source == "deterministic"

    def test_validator_reject_role_falls_back(self, tmp_path):
        def fn(prompt, operation=""):
            d = dict(VALID_PROPOSAL)
            d["required_role"] = "gopher"
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=fn)
        eng = P.LLMTaskProposalEngine(provider=prov)
        res = eng.propose(make_gap(), {}, existing_tasks=existing_tasks())
        assert res.fallback_used is True
        assert res.source == "deterministic"
        assert res.proposal.required_role == "qa"  # fallback 模板角色

    def test_validator_reject_cycle_falls_back(self, tmp_path):
        # 环依赖 → LLM 提案被拒 → deterministic 提案同样被拒 → REQUEST_REVIEW
        prov = R.ReasoningProvider(llm_fn=valid_proposal_fn)
        eng = P.LLMTaskProposalEngine(provider=prov)
        cyclic_dag = FakeDag(cyclic=True)
        res = eng.propose(make_gap(), {}, existing_tasks=existing_tasks(),
                          dag=cyclic_dag)
        assert res.fallback_used is True
        assert res.source == "request_review"
        assert "cycle" in res.reason or "循环" in res.reason

    def test_cycle_free_dag_passes(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=valid_proposal_fn)
        eng = P.LLMTaskProposalEngine(provider=prov)
        res = eng.propose(make_gap(), {}, existing_tasks=existing_tasks(),
                          dag=FakeDag(cyclic=False))
        assert res.source == "llm"
        assert res.fallback_used is False

    def test_validator_reject_duplicate_falls_back(self, tmp_path):
        # 已有任务与 LLM 提案同 source_gap → duplicate → REJECT → fallback
        prov = R.ReasoningProvider(llm_fn=valid_proposal_fn)
        eng = P.LLMTaskProposalEngine(provider=prov)
        existing = existing_tasks() + [{
            "id": "T009", "title": "为 T001 增加测试",
            "source_gap": "missing_test@T001",
        }]
        res = eng.propose(make_gap(), {}, existing_tasks=existing)
        assert res.fallback_used is True

    def test_validator_reject_low_confidence_falls_back(self, tmp_path):
        def fn(prompt, operation=""):
            d = dict(VALID_PROPOSAL)
            d["confidence"] = 0.1
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=fn)
        eng = P.LLMTaskProposalEngine(provider=prov,
                                      confidence_threshold=0.5)
        res = eng.propose(make_gap(), {}, existing_tasks=existing_tasks())
        assert res.fallback_used is True
        assert "confidence" in res.reason

    def test_validator_reject_missing_dependency_falls_back(self, tmp_path):
        def fn(prompt, operation=""):
            d = dict(VALID_PROPOSAL)
            d["dependencies"] = ["T999"]  # 不存在 → 检查 5 拒绝
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=fn)
        eng = P.LLMTaskProposalEngine(provider=prov)
        res = eng.propose(make_gap(), {}, existing_tasks=existing_tasks())
        assert res.fallback_used is True
        assert res.source == "deterministic"

    def test_llm_conflict_task_id_falls_back(self, tmp_path):
        # LLM 提供与已有任务冲突的 task_id → Validator 检查 1 拒绝 → fallback
        def fn(prompt, operation=""):
            d = dict(VALID_PROPOSAL)
            d["task_id"] = "T001"
            return json.dumps(d)

        prov = R.ReasoningProvider(llm_fn=fn)
        eng = P.LLMTaskProposalEngine(provider=prov)
        res = eng.propose(make_gap(), {}, existing_tasks=existing_tasks())
        assert res.fallback_used is True
        assert res.source == "deterministic"
        assert res.proposal.task_id != "T001"

    def test_engine_gate_missing_rationale_falls_back(self, tmp_path):
        # provider 层放行 (自定义 fn 直返 dict 绕过 provider 校验) →
        # engine 层 WHY gate 拒绝 → fallback
        def fn(prompt, operation=""):
            d = dict(VALID_PROPOSAL)
            d["rationale"] = ""
            return d

        prov = R.ReasoningProvider(llm_fn=fn)
        eng = P.LLMTaskProposalEngine(provider=prov)
        res = eng.propose(make_gap(), {}, existing_tasks=[])
        assert res.fallback_used is True
        assert "WHY" in res.reason or "rationale" in res.reason

    def test_engine_gate_missing_how_falls_back(self, tmp_path):
        def fn(prompt, operation=""):
            d = dict(VALID_PROPOSAL)
            d["acceptance_criteria"] = []
            return d

        prov = R.ReasoningProvider(llm_fn=fn)
        eng = P.LLMTaskProposalEngine(provider=prov)
        res = eng.propose(make_gap(), {}, existing_tasks=[])
        assert res.fallback_used is True

    def test_deterministic_no_template_request_review(self, tmp_path):
        # architecture_gap → deterministic 无模板 → REQUEST_REVIEW (None)
        prov = R.ReasoningProvider(llm_fn=invalid_json_fn)
        eng = P.LLMTaskProposalEngine(provider=prov)
        gap = GA.GapAnalysis(
            detected=True, gap_type="architecture_gap",
            source_task_id="T001", confidence=0.65,
            recommended_action="REQUEST_REVIEW", description="架构风险",
        )
        res = eng.propose(gap, {}, existing_tasks=existing_tasks())
        assert res.proposal is None
        assert res.source == "request_review"
        assert res.fallback_used is True

    def test_deterministic_rejected_by_validator_request_review(self, tmp_path):
        # deterministic 模板提案与已有任务重复 → Validator 拒绝 → REVIEW
        prov = R.ReasoningProvider(llm_fn=invalid_json_fn)
        eng = P.LLMTaskProposalEngine(provider=prov)
        existing = [{"id": "T001", "name": "backend api"}] + [{
            "id": "T009", "title": "为 T001 增加测试",
            "source_gap": "missing_test@T001",
        }]
        res = eng.propose(make_gap(), {}, existing_tasks=existing)
        assert res.proposal is None
        assert res.source == "request_review"
        assert res.fallback_used is True

    def test_fallback_used_marker_in_trace(self, tmp_path):
        trace = PT.PlanningTrace(file=tmp_path / "planning_trace.json")
        prov = R.ReasoningProvider(llm_fn=invalid_json_fn)
        eng = P.LLMTaskProposalEngine(provider=prov, trace=trace)
        res = eng.propose(make_gap(), {}, existing_tasks=[])
        records = trace.load()
        assert len(records) == 1
        assert records[0]["fallback_used"] is True
        assert records[0]["parsed_result"]["required_role"] == "qa"

    def test_propose_never_raises(self, tmp_path):
        for fn in (invalid_json_fn, api_error_fn, boom_fn, unavailable_fn):
            prov = R.ReasoningProvider(llm_fn=fn)
            eng = P.LLMTaskProposalEngine(provider=prov)
            res = eng.propose(make_gap(), {}, existing_tasks=[])
            assert isinstance(res, P.LLMTaskProposalResult)
            assert res.fallback_used is True

    def test_provider_override_per_call(self, tmp_path):
        bad = R.ReasoningProvider(llm_fn=invalid_json_fn)
        good = R.ReasoningProvider(llm_fn=valid_proposal_fn)
        eng = P.LLMTaskProposalEngine(provider=bad)
        res = eng.propose(make_gap(), {}, existing_tasks=[{"id": "T001", "name": "计分"}],
                          provider=good)
        assert res.source == "llm"
        assert res.fallback_used is False

    def test_gap_dict_input_supported(self, tmp_path):
        prov = R.ReasoningProvider(llm_fn=valid_proposal_fn)
        eng = P.LLMTaskProposalEngine(provider=prov)
        res = eng.propose(make_gap().to_dict(), {},
                          existing_tasks=[{"id": "T001", "name": "计分"}])
        assert res.source == "llm"
        assert res.proposal is not None
