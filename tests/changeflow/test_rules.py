"""tests/changeflow/test_rules.py — Change Rule Engine: 4 规则全分支 + 总判定 (Phase 6E, ADR-0020)。

覆盖:
- 规则① validation.l4: 未评估→SKIP / 达标→PASS / 不达标→FAIL / 自定义 required_validation
- 规则② commit.linked: 无证据→SKIP / 有关联提交→PASS / 有文件无提交→FAIL
- 规则③ required.files: 未配置→SKIP / 全覆盖→PASS / 缺失→FAIL
- 规则④ runtime.pref: 未配置→SKIP / 可用→PASS / 不可用→FAIL
- evaluate_rules: RULES 注册表顺序恒定 / 恒 4 条不短路
- overall_status: ERROR>FAIL>PASS>SKIP 优先级 + SKIP 不拉低 PASS
"""

from __future__ import annotations

from changeflow.models import RuleResult
from changeflow.rules import (
    RULES,
    RuleContext,
    evaluate_rules,
    overall_status,
    rule_commit_linked,
    rule_required_files,
    rule_runtime_pref,
    rule_validation_l4,
)

from changeflow_helpers import make_rule_result


def ctx(**kw) -> RuleContext:
    base = {"task_id": "MP-BUG-001", "project_id": "markpad"}
    base.update(kw)
    return RuleContext(**base)


class TestRuleValidationL4:
    def test_no_validation_result_skip(self):
        r = rule_validation_l4(ctx())
        assert r.status == "SKIP"
        assert r.rule_id == "validation.l4"

    def test_matching_status_pass(self):
        r = rule_validation_l4(ctx(validation_status="PASS"))
        assert r.status == "PASS"

    def test_mismatch_fail(self):
        r = rule_validation_l4(ctx(validation_status="FAIL"))
        assert r.status == "FAIL"

    def test_skip_validation_fails_against_required_pass(self):
        # L4 判定 SKIP != 要求 PASS → FAIL (评估不通过, 不触发)
        r = rule_validation_l4(ctx(validation_status="SKIP"))
        assert r.status == "FAIL"

    def test_error_validation_fails(self):
        r = rule_validation_l4(ctx(validation_status="ERROR"))
        assert r.status == "FAIL"

    def test_custom_required_validation(self):
        r = rule_validation_l4(ctx(validation_status="SKIP",
                                   required_validation="SKIP"))
        assert r.status == "PASS"

    def test_message_contains_both_statuses(self):
        r = rule_validation_l4(ctx(validation_status="PASS"))
        assert "PASS" in r.message
        assert "要求" in r.message


class TestRuleCommitLinked:
    def test_no_evidence_skip(self):
        r = rule_commit_linked(ctx())
        assert r.status == "SKIP"
        assert r.rule_id == "commit.linked"

    def test_linked_commits_pass(self):
        r = rule_commit_linked(ctx(linked_commits=["abc123"]))
        assert r.status == "PASS"

    def test_multiple_commits_pass(self):
        r = rule_commit_linked(ctx(linked_commits=["a", "b"]))
        assert r.status == "PASS"
        assert "2" in r.message

    def test_changed_files_but_no_commit_fail(self):
        r = rule_commit_linked(ctx(changed_files=["app/auth.py"]))
        assert r.status == "FAIL"

    def test_both_pass(self):
        r = rule_commit_linked(ctx(linked_commits=["abc123"],
                                   changed_files=["app/auth.py"]))
        assert r.status == "PASS"


class TestRuleRequiredFiles:
    def test_not_configured_skip(self):
        r = rule_required_files(ctx())
        assert r.status == "SKIP"
        assert r.rule_id == "required.files"

    def test_all_required_files_changed_pass(self):
        r = rule_required_files(
            ctx(required_files=["CHANGELOG.md", "VERSION"],
                changed_files=["CHANGELOG.md", "VERSION", "app/auth.py"]))
        assert r.status == "PASS"

    def test_missing_required_file_fail(self):
        r = rule_required_files(
            ctx(required_files=["CHANGELOG.md", "VERSION"],
                changed_files=["VERSION"]))
        assert r.status == "FAIL"
        assert "CHANGELOG.md" in r.message

    def test_empty_changed_files_fail_when_configured(self):
        r = rule_required_files(ctx(required_files=["VERSION"]))
        assert r.status == "FAIL"

    def test_extra_files_do_not_hurt(self):
        r = rule_required_files(
            ctx(required_files=["VERSION"],
                changed_files=["VERSION", "wip.py"]))
        assert r.status == "PASS"


class TestRuleRuntimePref:
    def test_no_pref_skip(self):
        r = rule_runtime_pref(ctx())
        assert r.status == "SKIP"
        assert r.rule_id == "runtime.pref"

    def test_pref_available_pass(self):
        r = rule_runtime_pref(ctx(runtime_pref="echo",
                                  available_runtimes={"echo", "hermes"}))
        assert r.status == "PASS"

    def test_pref_unavailable_fail(self):
        r = rule_runtime_pref(ctx(runtime_pref="echo",
                                  available_runtimes={"hermes"}))
        assert r.status == "FAIL"

    def test_pref_empty_available_fail(self):
        r = rule_runtime_pref(ctx(runtime_pref="echo"))
        assert r.status == "FAIL"

    def test_message_contains_runtime_id(self):
        r = rule_runtime_pref(ctx(runtime_pref="echo",
                                  available_runtimes={"echo"}))
        assert "echo" in r.message


class TestEvaluateRules:
    def test_rule_registry_order_stable(self):
        assert RULES == ("validation.l4", "commit.linked",
                         "required.files", "runtime.pref")

    def test_evaluates_four_rules_in_order(self):
        results = evaluate_rules(ctx())
        assert [r.rule_id for r in results] == list(RULES)
        assert len(results) == 4

    def test_all_skip_when_no_evidence(self):
        results = evaluate_rules(ctx())
        assert all(r.status == "SKIP" for r in results)

    def test_no_short_circuit_on_fail(self):
        # 规则① FAIL 不阻断后续规则评估 (Dashboard 展示完整 4 行)
        results = evaluate_rules(
            ctx(validation_status="FAIL", linked_commits=["abc123"]))
        statuses = [r.status for r in results]
        assert statuses[0] == "FAIL"
        assert statuses[1] == "PASS"

    def test_full_pass_scenario(self):
        results = evaluate_rules(ctx(
            validation_status="PASS",
            linked_commits=["abc123"],
            changed_files=["CHANGELOG.md"],
            required_files=["CHANGELOG.md"],
            runtime_pref="echo",
            available_runtimes={"echo"},
        ))
        assert all(r.status == "PASS" for r in results)
        assert overall_status(results) == "PASS"

    def test_result_objects_are_rule_results(self):
        results = evaluate_rules(ctx())
        assert all(isinstance(r, RuleResult) for r in results)


class TestOverallStatus:
    def test_all_skip(self):
        assert overall_status([make_rule_result(status="SKIP")]) == "SKIP"

    def test_any_pass_wins_over_skip(self):
        assert overall_status([
            make_rule_result(status="SKIP"),
            make_rule_result(status="PASS"),
        ]) == "PASS"

    def test_any_fail_wins_over_pass(self):
        assert overall_status([
            make_rule_result(status="PASS"),
            make_rule_result(status="FAIL"),
        ]) == "FAIL"

    def test_any_error_wins_over_fail(self):
        assert overall_status([
            make_rule_result(status="FAIL"),
            make_rule_result(status="ERROR"),
        ]) == "ERROR"

    def test_error_wins_over_everything(self):
        assert overall_status([
            make_rule_result(status="PASS"),
            make_rule_result(status="FAIL"),
            make_rule_result(status="ERROR"),
            make_rule_result(status="SKIP"),
        ]) == "ERROR"

    def test_skip_never_lowers_pass(self):
        assert overall_status([
            make_rule_result(status="PASS"),
            make_rule_result(status="SKIP"),
            make_rule_result(status="SKIP"),
        ]) == "PASS"

    def test_skip_never_lowers_fail(self):
        assert overall_status([
            make_rule_result(status="FAIL"),
            make_rule_result(status="SKIP"),
        ]) == "FAIL"

    def test_empty_results_skip(self):
        assert overall_status([]) == "SKIP"

    def test_mixed_pass_fail_error_full_priority(self):
        # ERROR > FAIL > PASS > SKIP (ADR-0020 总判定语义)
        assert overall_status([
            make_rule_result(status="PASS"),
            make_rule_result(status="SKIP"),
            make_rule_result(status="FAIL"),
            make_rule_result(status="ERROR"),
        ]) == "ERROR"
