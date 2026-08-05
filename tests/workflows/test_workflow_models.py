"""tests/workflows/test_workflow_models.py — Workflow/WorkflowStep/WorkflowRun 模型。

覆盖: 默认值 / 校验 (非法 id/order/空 steps/重复) / 序列化往返 / 状态解析 / run 构造。
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from workflows.models import StepState, StepStatus, Workflow, WorkflowRun, WorkflowStatus, WorkflowStep

from workflow_helpers import FEATURE_STEP_IDS, make_step, make_workflow


# ------------------------------------------------------------------ WorkflowStep

class TestWorkflowStep:
    def test_defaults(self):
        s = make_step("architecture", 1)
        assert s.required_skill is None
        assert s.required_role is None
        assert s.name == "architecture"

    def test_order_must_be_positive(self):
        with pytest.raises(ValidationError, match="order"):
            WorkflowStep(id="s", name="s", order=0)

    def test_id_sane_rejects_path(self):
        with pytest.raises(ValidationError, match="invalid id"):
            WorkflowStep(id="a/b", name="x", order=1)
        with pytest.raises(ValidationError, match="invalid id"):
            WorkflowStep(id="", name="x", order=1)

    def test_to_dict_roundtrip(self):
        s = WorkflowStep(id="dev", name="编码开发", order=2, required_skill="development")
        d = s.to_dict()
        assert d["order"] == 2
        restored = WorkflowStep.model_validate(d)
        assert restored == s


# ------------------------------------------------------------------ Workflow

class TestWorkflow:
    def test_defaults(self):
        w = make_workflow("wf-1")
        assert w.description == "测试定义"
        assert w.created_at.tzinfo is not None
        assert w.updated_at.tzinfo is not None

    def test_empty_steps_rejected(self):
        with pytest.raises(ValidationError, match="at least one step"):
            Workflow(id="wf", name="x", steps=[])

    def test_duplicate_step_ids_rejected(self):
        steps = [make_step("a", 1), make_step("a", 2)]
        with pytest.raises(ValidationError, match="unique"):
            Workflow(id="wf", name="x", steps=steps)

    def test_duplicate_orders_rejected(self):
        steps = [make_step("a", 1), make_step("b", 1)]
        with pytest.raises(ValidationError, match="unique"):
            Workflow(id="wf", name="x", steps=steps)

    def test_id_sane_rejects_path(self):
        with pytest.raises(ValidationError, match="invalid id"):
            Workflow(id="wf/x", name="x", steps=[make_step("a", 1)])

    def test_step_ids_sorted_by_order(self):
        w = Workflow(id="wf", name="x", steps=[
            make_step("b", 2), make_step("a", 1), make_step("c", 3),
        ])
        assert w.step_ids() == ["a", "b", "c"]

    def test_ordered_steps(self):
        w = Workflow(id="wf", name="x", steps=[
            make_step("dev", 2), make_step("arch", 1),
        ])
        assert [s.id for s in w.ordered_steps()] == ["arch", "dev"]

    def test_to_dict_json_roundtrip(self):
        w = make_workflow("wf-rt")
        d = w.to_dict()
        assert d["id"] == "wf-rt"
        assert d["steps"][0]["order"] == 1
        restored = Workflow.model_validate(json.loads(json.dumps(d)))
        assert restored == w


# ------------------------------------------------------------------ 状态枚举解析

class TestStatusParsing:
    def test_workflow_status_parse_case_insensitive(self):
        assert WorkflowStatus.parse("running") is WorkflowStatus.RUNNING
        assert WorkflowStatus.parse("RUNNING") is WorkflowStatus.RUNNING
        assert WorkflowStatus.parse(WorkflowStatus.CREATED) is WorkflowStatus.CREATED

    def test_workflow_status_parse_invalid(self):
        with pytest.raises(ValueError, match="invalid workflow status"):
            WorkflowStatus.parse("DONE")

    def test_step_status_parse(self):
        assert StepStatus.parse("pending") is StepStatus.PENDING
        with pytest.raises(ValueError, match="invalid step status"):
            StepStatus.parse("DONE")


# ------------------------------------------------------------------ WorkflowRun

class TestWorkflowRun:
    def test_from_workflow_builds_pending_states(self):
        w = make_workflow("wf-run")
        run = WorkflowRun.from_workflow(run_id="WR-001", workflow=w, task_id="T-001")
        assert run.status is WorkflowStatus.CREATED
        assert run.workflow_id == "wf-run"
        assert run.workflow_name == "wf-run 测试"
        assert [st.step_id for st in run.step_states] == FEATURE_STEP_IDS
        assert all(st.status is StepStatus.PENDING for st in run.step_states)
        assert run.current_step == "architecture"

    def test_step_state_lookup(self):
        w = make_workflow()
        run = WorkflowRun.from_workflow(run_id="WR-001", workflow=w, task_id="T-001")
        assert run.step_state("development").step_id == "development"
        assert run.step_state("nope") is None

    def test_next_pending_and_all_completed(self):
        w = make_workflow()
        run = WorkflowRun.from_workflow(run_id="WR-001", workflow=w, task_id="T-001")
        assert run.next_pending_step().step_id == "architecture"
        assert not run.all_steps_completed()
        for st in run.step_states:
            st.status = StepStatus.COMPLETED
        assert run.next_pending_step() is None
        assert run.all_steps_completed()

    def test_to_dict_roundtrip(self):
        w = make_workflow()
        run = WorkflowRun.from_workflow(run_id="WR-001", workflow=w, task_id="T-001")
        run.status = WorkflowStatus.RUNNING
        d = run.to_dict()
        assert d["status"] == "RUNNING"
        assert d["step_states"][0]["status"] == "PENDING"
        restored = WorkflowRun.model_validate(json.loads(json.dumps(d)))
        assert restored == run

    def test_status_coerced_from_string(self):
        w = make_workflow()
        run = WorkflowRun.from_workflow(run_id="WR-001", workflow=w, task_id="T-001")
        d = run.to_dict()
        d["status"] = "running"  # 小写字符串 → 宽容解析
        restored = WorkflowRun.model_validate(d)
        assert restored.status is WorkflowStatus.RUNNING

    def test_empty_workflow_run_current_step_none(self):
        # 防御: 空 steps 的 run (模型层允许, engine 不产生; 仅验证不炸)
        run = WorkflowRun(
            run_id="WR-000", workflow_id="x", task_id="T-000", step_states=[],
        )
        assert run.current_step is None
        assert run.next_pending_step() is None
        assert not run.all_steps_completed()

    def test_step_state_result_fields(self):
        st = StepState(step_id="s1")
        st.status = StepStatus.COMPLETED
        st.result = "OK"
        st.evidence = "ref://report"
        assert st.to_dict()["result"] == "OK"
