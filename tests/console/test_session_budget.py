"""S10-063 批次 A — ProjectBudget + BudgetUsage + BudgetEnforcer 测试套件。

覆盖: ProjectBudget 全字段/to_dict/from_dict/save/load/缺省值/失败安全;
BudgetUsage 属性 + from_records 聚合; BudgetEnforcer 三档闸门
(80% warn / 90% review / 100% block) + action enforce (block 级全禁)。

装配: tmp_path; 禁真实 LLM/网络。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from importlib import import_module

B = import_module("factory-console.session.budget")

ENFORCE_ACTIONS = ("llm", "execute", "retry", "repair", "replan", "new_task")


# ================================================================== 1. ProjectBudget 缺省值


class TestProjectBudgetDefaults:
    def test_default_max_total_tokens_unlimited(self):
        assert B.ProjectBudget().max_total_tokens == 0

    def test_default_max_total_cost_unlimited(self):
        assert B.ProjectBudget().max_total_cost == 0.0

    def test_default_max_llm_calls_unlimited(self):
        assert B.ProjectBudget().max_llm_calls == 0

    def test_default_max_replans(self):
        assert B.ProjectBudget().max_replans == 5

    def test_default_max_retries(self):
        assert B.ProjectBudget().max_retries == 1

    def test_default_max_repairs(self):
        assert B.ProjectBudget().max_repairs == 2

    def test_default_max_task_count_unlimited(self):
        assert B.ProjectBudget().max_task_count == 0

    def test_default_max_execution_time_unlimited(self):
        assert B.ProjectBudget().max_execution_time == 0.0

    def test_default_max_concurrent_agents(self):
        assert B.ProjectBudget().max_concurrent_agents == 1

    def test_default_warn_ratio(self):
        assert B.ProjectBudget().warn_ratio == pytest.approx(0.8)

    def test_default_review_ratio(self):
        assert B.ProjectBudget().review_ratio == pytest.approx(0.9)


# ================================================================== 2. ProjectBudget to_dict/from_dict


class TestProjectBudgetDict:
    def test_to_dict_all_fields(self):
        budget = B.ProjectBudget(max_total_cost=100.0, max_total_tokens=1000)
        d = budget.to_dict()
        assert d["max_total_cost"] == pytest.approx(100.0)
        assert d["max_total_tokens"] == 1000
        assert d["max_replans"] == 5
        assert d["max_retries"] == 1
        assert d["max_repairs"] == 2
        assert d["max_concurrent_agents"] == 1
        assert d["warn_ratio"] == pytest.approx(0.8)
        assert d["review_ratio"] == pytest.approx(0.9)

    def test_from_dict_roundtrip(self):
        budget = B.ProjectBudget(
            max_total_cost=250.0, max_total_tokens=100000, max_llm_calls=40,
            max_task_count=20, max_execution_time=3600.0,
        )
        restored = B.ProjectBudget.from_dict(budget.to_dict())
        assert restored == budget

    def test_from_dict_missing_keys_defaults(self):
        restored = B.ProjectBudget.from_dict({"max_total_cost": 50.0})
        assert restored.max_total_cost == pytest.approx(50.0)
        assert restored.max_total_tokens == 0
        assert restored.max_replans == 5
        assert restored.max_retries == 1
        assert restored.max_repairs == 2

    def test_from_dict_none_returns_default(self):
        assert B.ProjectBudget.from_dict(None) == B.ProjectBudget()

    def test_from_dict_string_coercion(self):
        restored = B.ProjectBudget.from_dict(
            {"max_total_cost": "99.5", "max_llm_calls": "7"}
        )
        assert restored.max_total_cost == pytest.approx(99.5)
        assert restored.max_llm_calls == 7


# ================================================================== 3. ProjectBudget save/load


class TestProjectBudgetSaveLoad:
    def test_save_writes_file(self, tmp_path):
        path = tmp_path / "project_budget.json"
        B.ProjectBudget(max_total_cost=100.0).save(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["max_total_cost"] == pytest.approx(100.0)

    def test_load_roundtrip(self, tmp_path):
        path = tmp_path / "project_budget.json"
        budget = B.ProjectBudget(
            max_total_tokens=50000, max_total_cost=200.0, max_llm_calls=30
        )
        budget.save(path)
        restored = B.ProjectBudget.load(path)
        assert restored == budget

    def test_load_missing_returns_none(self, tmp_path):
        assert B.ProjectBudget.load(tmp_path / "missing.json") is None

    def test_load_corrupt_returns_none(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        assert B.ProjectBudget.load(path) is None

    def test_load_or_default_missing(self, tmp_path):
        budget = B.ProjectBudget.load_or_default(tmp_path / "missing.json")
        assert budget == B.ProjectBudget()

    def test_load_or_default_present(self, tmp_path):
        path = tmp_path / "project_budget.json"
        B.ProjectBudget(max_total_cost=42.0).save(path)
        assert B.ProjectBudget.load_or_default(path).max_total_cost == pytest.approx(42.0)

    def test_save_fail_safe(self, tmp_path):
        # 父目录是文件 (mkdir 失败) → 不抛 (失败安全)
        blocker = tmp_path / "blocker"
        blocker.write_text("x", encoding="utf-8")
        budget = B.ProjectBudget()
        budget.save(blocker / "b.json")  # 不抛
        assert not (blocker / "b.json").exists()


# ================================================================== 4. BudgetUsage


class TestBudgetUsage:
    def test_default_usage_zero(self):
        usage = B.BudgetUsage()
        assert usage.total_cost == 0.0
        assert usage.ratio == 0.0
        assert usage.remaining == pytest.approx(1.0)

    def test_spent_is_total_cost(self):
        usage = B.BudgetUsage(total_cost=80.0)
        assert usage.spent == pytest.approx(80.0)

    def test_ratio_with_budget_cost_dimension(self):
        budget = B.ProjectBudget(max_total_cost=100.0)
        usage = B.BudgetUsage(total_cost=80.0)
        assert usage.ratio_with(budget) == pytest.approx(0.8)

    def test_ratio_takes_max_dimension(self):
        budget = B.ProjectBudget(max_total_cost=100.0, max_total_tokens=1000)
        usage = B.BudgetUsage(total_cost=80.0, total_tokens=200)
        # cost 0.8 vs tokens 0.2 → max 0.8
        assert usage.ratio_with(budget) == pytest.approx(0.8)

    def test_ratio_unlimited_budget_zero(self):
        budget = B.ProjectBudget()
        usage = B.BudgetUsage(total_cost=999.0)
        assert usage.ratio_with(budget) == 0.0

    def test_ratio_bound_usage_binds_budget(self):
        budget = B.ProjectBudget(max_total_cost=100.0)
        usage = B.BudgetUsage(total_cost=90.0, _budget=budget)
        assert usage.ratio == pytest.approx(0.9)
        assert usage.remaining == pytest.approx(0.1)

    def test_from_records_aggregates(self):
        records = [
            {"project_id": "p1", "task_id": "T1", "agent_id": "A1",
             "purpose": "EXECUTION", "input_tokens": 100, "output_tokens": 100,
             "total_tokens": 200, "estimated_cost": 0.02, "latency": 1.0},
            {"project_id": "p1", "task_id": "T1", "agent_id": "A1",
             "purpose": "REPAIR", "input_tokens": 50, "output_tokens": 50,
             "estimated_cost": 0.01, "latency": 0.5},
            {"project_id": "p1", "task_id": "T2", "agent_id": "A2",
             "purpose": "REPLANNING", "input_tokens": 10, "output_tokens": 10,
             "estimated_cost": 0.005, "latency": 2.0},
        ]
        usage = B.BudgetUsage.from_records(records)
        assert usage.llm_calls == 3
        assert usage.total_cost == pytest.approx(0.035)
        assert usage.total_tokens == 320
        assert usage.repairs == 1
        assert usage.replans == 1
        assert usage.task_count == 2
        assert usage.concurrent_agents == 2
        assert usage.execution_time == pytest.approx(3.5)

    def test_from_records_total_tokens_fallback(self):
        records = [{"input_tokens": 30, "output_tokens": 20}]
        usage = B.BudgetUsage.from_records(records)
        assert usage.total_tokens == 50

    def test_from_records_non_list_fail_safe(self):
        usage = B.BudgetUsage.from_records("not a list")
        assert usage.llm_calls == 0
        assert usage.total_cost == 0.0


# ================================================================== 5. BudgetEnforcer.check 三档


class TestBudgetEnforcerCheck:
    def _check(self, cost, limit=100.0, warn=0.8, review=0.9):
        budget = B.ProjectBudget(
            max_total_cost=limit, warn_ratio=warn, review_ratio=review
        )
        usage = B.BudgetUsage(total_cost=cost)
        return B.BudgetEnforcer.check(budget, usage)

    def test_ok_below_warn(self):
        result = self._check(10.0)
        assert result["level"] == B.BudgetEnforcer.LEVEL_OK
        assert result["ratio"] == pytest.approx(0.1)

    def test_warn_at_80_percent(self):
        result = self._check(80.0)
        assert result["level"] == B.BudgetEnforcer.LEVEL_WARN

    def test_warn_above_80_below_90(self):
        result = self._check(85.0)
        assert result["level"] == B.BudgetEnforcer.LEVEL_WARN

    def test_review_at_90_percent(self):
        result = self._check(90.0)
        assert result["level"] == B.BudgetEnforcer.LEVEL_REVIEW

    def test_review_between_90_and_100(self):
        result = self._check(95.0)
        assert result["level"] == B.BudgetEnforcer.LEVEL_REVIEW

    def test_block_at_100_percent(self):
        result = self._check(100.0)
        assert result["level"] == B.BudgetEnforcer.LEVEL_BLOCK

    def test_block_above_100(self):
        result = self._check(120.0)
        assert result["level"] == B.BudgetEnforcer.LEVEL_BLOCK

    def test_check_reason_present(self):
        result = self._check(85.0)
        assert isinstance(result["reason"], str) and result["reason"]

    def test_check_returns_usage(self):
        usage = B.BudgetUsage(total_cost=85.0)
        budget = B.ProjectBudget(max_total_cost=100.0)
        result = B.BudgetEnforcer.check(budget, usage)
        assert result["usage"] is usage

    def test_check_token_dimension_blocks(self):
        budget = B.ProjectBudget(max_total_tokens=1000)
        usage = B.BudgetUsage(total_tokens=2000)
        result = B.BudgetEnforcer.check(budget, usage)
        assert result["level"] == B.BudgetEnforcer.LEVEL_BLOCK

    def test_check_unlimited_budget_ok(self):
        budget = B.ProjectBudget()
        usage = B.BudgetUsage(total_cost=999999.0)
        result = B.BudgetEnforcer.check(budget, usage)
        assert result["level"] == B.BudgetEnforcer.LEVEL_OK

    def test_check_llm_calls_dimension(self):
        budget = B.ProjectBudget(max_llm_calls=10)
        usage = B.BudgetUsage(llm_calls=8)  # 0.8 → warn
        assert B.BudgetEnforcer.check(budget, usage)["level"] == "warn"
        usage2 = B.BudgetUsage(llm_calls=12)  # 1.2 → block
        assert B.BudgetEnforcer.check(budget, usage2)["level"] == "block"


# ================================================================== 6. BudgetEnforcer.enforce action


class TestBudgetEnforcerEnforce:
    def _usage(self, cost):
        return B.BudgetUsage(total_cost=cost)

    def test_all_actions_allowed_at_ok(self):
        budget = B.ProjectBudget(max_total_cost=100.0)
        for action in ENFORCE_ACTIONS:
            result = B.BudgetEnforcer.enforce(budget, self._usage(10.0), action)
            assert result["allowed"] is True, action
            assert result["action"] == action

    def test_all_actions_allowed_at_warn(self):
        budget = B.ProjectBudget(max_total_cost=100.0)
        for action in ENFORCE_ACTIONS:
            result = B.BudgetEnforcer.enforce(budget, self._usage(80.0), action)
            assert result["allowed"] is True, action
            assert result["level"] == "warn"

    def test_all_actions_allowed_at_review(self):
        # 90% 档: 停止等审批, 但非 block — 仍 allowed (仅 block 全禁)
        budget = B.ProjectBudget(max_total_cost=100.0)
        for action in ENFORCE_ACTIONS:
            result = B.BudgetEnforcer.enforce(budget, self._usage(90.0), action)
            assert result["allowed"] is True, action
            assert result["level"] == "review"

    def test_all_actions_blocked_at_block(self):
        budget = B.ProjectBudget(max_total_cost=100.0)
        for action in ENFORCE_ACTIONS:
            result = B.BudgetEnforcer.enforce(budget, self._usage(100.0), action)
            assert result["allowed"] is False, action
            assert result["level"] == "block"

    def test_block_reason_mentions_action(self):
        budget = B.ProjectBudget(max_total_cost=100.0)
        result = B.BudgetEnforcer.enforce(budget, self._usage(150.0), "llm")
        assert "llm" in result["reason"]
        assert "BUDGET BLOCK" in result["reason"]

    def test_unknown_action_lenient(self):
        # 未知 action 宽松处理: 跟随 level 判定
        budget = B.ProjectBudget(max_total_cost=100.0)
        result = B.BudgetEnforcer.enforce(budget, self._usage(10.0), "deploy")
        assert result["allowed"] is True
        assert result["action"] == "deploy"

    def test_block_at_retry_specific(self):
        budget = B.ProjectBudget(max_total_cost=100.0)
        result = B.BudgetEnforcer.enforce(budget, self._usage(200.0), "retry")
        assert result["allowed"] is False

    def test_enforce_returns_level_and_ratio(self):
        budget = B.ProjectBudget(max_total_cost=100.0)
        result = B.BudgetEnforcer.enforce(budget, self._usage(50.0), "execute")
        assert result["level"] == "ok"
        assert result["ratio"] == pytest.approx(0.5)
