"""tests/changeflow/test_trigger_models.py — ChangeTrigger / RuleResult / ChangeEvaluation
领域模型 (Pydantic v2, Phase 6E, ADR-0020)。

覆盖: 默认值、校验器 (id 引用键 / event_type 受控词汇宽容 / 可选字段清洗 /
required_validation)、matches() 项目/类型匹配全分支、to_dict JSON 序列化、
RuleResult 判定语义、ChangeEvaluation 评估快照。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from changeflow.models import (
    RULE_STATUSES,
    ChangeEvaluation,
    ChangeTrigger,
    RuleResult,
)

from changeflow_helpers import (
    make_evaluation,
    make_rule_result,
    make_trigger,
)


class TestChangeTriggerDefaults:
    def test_defaults(self):
        t = ChangeTrigger(id="TRIG-1", target_workflow="release")
        assert t.event_type == "workflow.completed"
        assert t.project_id is None
        assert t.task_type is None
        assert t.required_validation == "PASS"
        assert t.target_workflow == "release"

    def test_created_at_utc_aware(self):
        t = make_trigger()
        assert t.created_at.tzinfo is not None

    def test_to_dict_json_serializable(self):
        d = make_trigger(project_id="markpad", task_type="feature").to_dict()
        assert d["id"] == "TRIG-FEATURE-RELEASE"
        assert d["project_id"] == "markpad"
        assert d["task_type"] == "feature"
        assert d["target_workflow"] == "release"
        assert isinstance(d["created_at"], str)

    def test_model_validate_roundtrip(self):
        t = make_trigger(required_validation="PASS")
        t2 = ChangeTrigger.model_validate(t.to_dict())
        assert t2.id == t.id
        assert t2.required_validation == "PASS"


class TestChangeTriggerIdValidation:
    def test_id_rejects_empty(self):
        with pytest.raises(ValidationError):
            ChangeTrigger(id="", target_workflow="release")

    def test_id_rejects_whitespace_only(self):
        with pytest.raises(ValidationError):
            ChangeTrigger(id="   ", target_workflow="release")

    def test_id_rejects_slash(self):
        with pytest.raises(ValidationError):
            ChangeTrigger(id="a/b", target_workflow="release")

    def test_id_rejects_backslash(self):
        with pytest.raises(ValidationError):
            ChangeTrigger(id="a\\b", target_workflow="release")

    def test_id_strips_whitespace(self):
        t = ChangeTrigger(id="  TRIG-1  ", target_workflow="release")
        assert t.id == "TRIG-1"

    def test_target_workflow_requires_sane_id(self):
        with pytest.raises(ValidationError):
            ChangeTrigger(id="TRIG-1", target_workflow="a/b")


class TestChangeTriggerEventType:
    def test_valid_event_types_accepted(self):
        for ev in ("workflow.completed", "workflow.failed",
                   "change.validation.completed", "task.completed"):
            t = ChangeTrigger(id=f"T-{ev}", event_type=ev,
                              target_workflow="release")
            assert t.event_type == ev

    def test_case_insensitive(self):
        assert make_trigger(event_type="WORKFLOW.COMPLETED").event_type == "workflow.completed"

    def test_whitespace_stripped(self):
        assert make_trigger(event_type="  workflow.completed  ").event_type == "workflow.completed"

    def test_unknown_falls_back_workflow_completed(self):
        # 受控词汇之外的事件域 → 宽容回退 (声明式配置不因拼写崩坏)
        assert make_trigger(event_type="everything.changed").event_type == "workflow.completed"

    def test_none_falls_back_workflow_completed(self):
        assert make_trigger(event_type=None).event_type == "workflow.completed"


class TestChangeTriggerOptionalFields:
    def test_project_id_none(self):
        assert make_trigger(project_id=None).project_id is None

    def test_project_id_blank_normalized_to_none(self):
        assert make_trigger(project_id="  ").project_id is None

    def test_task_type_blank_normalized_to_none(self):
        assert make_trigger(task_type="").task_type is None

    def test_required_validation_upper(self):
        assert make_trigger(required_validation="pass").required_validation == "PASS"

    def test_required_validation_none_defaults_pass(self):
        assert make_trigger(required_validation=None).required_validation == "PASS"


class TestChangeTriggerMatches:
    def test_wildcard_matches_any(self):
        t = make_trigger()  # project/task_type 皆 None = 通配
        assert t.matches(project_id="markpad", task_type="feature")
        assert t.matches(project_id="other", task_type="bug")

    def test_project_match(self):
        t = make_trigger(project_id="markpad")
        assert t.matches(project_id="markpad", task_type="bug")
        assert not t.matches(project_id="other", task_type="feature")

    def test_project_default_normalization(self):
        # 任务 project 为空时按 "default" 处理 (模型 matches 语义)
        t = make_trigger(project_id="default")
        assert t.matches(project_id="", task_type="feature")

    def test_task_type_match(self):
        t = make_trigger(task_type="feature")
        assert t.matches(project_id="markpad", task_type="feature")
        assert not t.matches(project_id="markpad", task_type="bug")

    def test_task_type_case_insensitive(self):
        t = make_trigger(task_type="Feature")
        assert t.matches(project_id="markpad", task_type="feature")

    def test_both_constraints_and(self):
        t = make_trigger(project_id="markpad", task_type="feature")
        assert t.matches(project_id="markpad", task_type="feature")
        assert not t.matches(project_id="markpad", task_type="bug")
        assert not t.matches(project_id="other", task_type="feature")


class TestRuleResult:
    def test_default_skip(self):
        r = RuleResult(rule_id="validation.l4")
        assert r.status == "SKIP"
        assert r.message == ""

    def test_status_coerce_lowercase(self):
        assert RuleResult(rule_id="r", status="pass").status == "PASS"

    def test_status_invalid_falls_back_skip(self):
        assert RuleResult(rule_id="r", status="weird").status == "SKIP"

    def test_status_none_falls_back_skip(self):
        assert RuleResult(rule_id="r", status=None).status == "SKIP"

    def test_passed_property(self):
        assert make_rule_result(status="PASS").passed
        assert not make_rule_result(status="FAIL").passed
        assert not make_rule_result(status="SKIP").passed
        assert not make_rule_result(status="ERROR").passed

    def test_rule_statuses_enum(self):
        assert RULE_STATUSES == {"PASS", "FAIL", "SKIP", "ERROR"}

    def test_to_dict(self):
        d = make_rule_result(rule_id="commit.linked", status="FAIL",
                             message="no commit").to_dict()
        assert d["rule_id"] == "commit.linked"
        assert d["status"] == "FAIL"
        assert d["message"] == "no commit"


class TestChangeEvaluation:
    def test_default_skip(self):
        e = ChangeEvaluation(task_id="MP-BUG-001")
        assert e.status == "SKIP"
        assert e.rules == []
        assert e.triggered_workflow is None
        assert e.run_id is None
        assert e.error is None

    def test_id_auto_generated_unique(self):
        assert ChangeEvaluation(task_id="T-1").id != ChangeEvaluation(task_id="T-1").id

    def test_status_coerce(self):
        assert ChangeEvaluation(task_id="T-1", status="fail").status == "FAIL"

    def test_passed_property(self):
        assert make_evaluation(status="PASS").passed
        assert not make_evaluation(status="FAIL").passed
        assert not make_evaluation(status="SKIP").passed
        assert not make_evaluation(status="ERROR").passed

    def test_full_fields(self):
        e = make_evaluation(
            task_id="MP-BUG-001", status="PASS",
            rules=[make_rule_result()], triggered_workflow="release",
            run_id="WR-1",
        )
        assert e.triggered_workflow == "release"
        assert e.run_id == "WR-1"
        assert len(e.rules) == 1

    def test_error_evaluation(self):
        e = make_evaluation(status="ERROR", trigger_id=None,
                            error="task not found: X")
        assert e.status == "ERROR"
        assert e.error == "task not found: X"

    def test_to_dict_json_serializable(self):
        d = make_evaluation(triggered_workflow="release").to_dict()
        assert d["task_id"] == "MP-BUG-001"
        assert d["trigger_id"] == "TRIG-FEATURE-RELEASE"
        assert d["status"] == "PASS"
        assert d["triggered_workflow"] == "release"
        assert isinstance(d["created_at"], str)

    def test_model_validate_roundtrip(self):
        e = make_evaluation(rules=[make_rule_result(status="PASS")])
        e2 = ChangeEvaluation.model_validate(e.to_dict())
        assert e2.status == "PASS"
        assert e2.rules[0].rule_id == "validation.l4"
        assert e2.rules[0].status == "PASS"
