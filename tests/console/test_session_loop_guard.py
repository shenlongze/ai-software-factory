"""S10-063 批次 A — LoopGuard 测试套件。

覆盖: same_failure/same_decision/total_execution 计数; check_failure
retry→repair→replan 阶梯 + review/block; check_decision (同决策/生成任务/
总执行); 失败安全 (空/非列表 history)。

装配: 纯内存; 禁真实 LLM/网络。
"""

from __future__ import annotations

import pytest

from importlib import import_module

LG = import_module("factory-console.session.loop_guard")


def _guard(**kwargs) -> LG.LoopGuard:
    defaults = dict(
        max_retry=1, max_repair=2, max_replan=5,
        max_generated_tasks=10, max_same_failure=3,
        max_same_decision=5, max_total_execution=50,
    )
    defaults.update(kwargs)
    return LG.LoopGuard(**defaults)


def _entry(task_id="T1", failure="f1", action="retry") -> dict:
    return {"task_id": task_id, "failure": failure, "action": action}


# ================================================================== 1. 计数


class TestCounts:
    def test_same_failure_count(self):
        history = [_entry("T1", "f1"), _entry("T1", "f1"), _entry("T2", "f1")]
        assert _guard().same_failure_count("T1", "f1", history) == 2

    def test_same_failure_count_uses_failure_key_alias(self):
        history = [{"task_id": "T1", "failure_key": "f1"}]
        assert _guard().same_failure_count("T1", "f1", history) == 1

    def test_same_decision_count_dict(self):
        history = [{"decision": "INSERT_TASK"}, {"decision": "INSERT_TASK"}]
        assert _guard().same_decision_count("INSERT_TASK", history) == 2

    def test_same_decision_count_string_entries(self):
        history = ["INSERT_TASK", "INSERT_TASK", "KEEP_PLAN"]
        assert _guard().same_decision_count("INSERT_TASK", history) == 2

    def test_total_execution_count(self):
        history = [_entry(), _entry("T2", "f2"), {"decision": "X"}]
        assert _guard().total_execution_count(history) == 2

    def test_counts_fail_safe_non_list(self):
        guard = _guard()
        assert guard.same_failure_count("T1", "f1", "nope") == 0
        assert guard.same_decision_count("d", None) == 0
        assert guard.total_execution_count(123) == 0


# ================================================================== 2. check_failure


class TestCheckFailure:
    def test_empty_history_allowed_retry(self):
        result = _guard().check_failure("T1", "f1", [])
        assert result["allowed"] is True
        assert result["action"] == LG.ACTION_RETRY

    def test_empty_history_fail_safe_none(self):
        result = _guard().check_failure("T1", "f1", None)
        assert result["allowed"] is True

    def test_retry_after_one_failure(self):
        history = [_entry("T1", "f1")]  # 1 次 retry 记录
        result = _guard().check_failure("T1", "f1", history)
        assert result["allowed"] is True
        assert result["action"] == LG.ACTION_REPAIR  # retry 上限 1 已到 → repair

    def test_repair_after_retry_exhausted(self):
        history = [_entry("T1", "f1", "retry")]
        guard = _guard()
        assert guard.check_failure("T1", "f1", history)["action"] == "repair"

    def test_replan_after_repair_exhausted(self):
        # max_same_failure 调高以隔离阶梯逻辑 (同失败评审优先于机械升级)
        guard = _guard(max_same_failure=10)
        history = [
            _entry("T1", "f1", "retry"),
            _entry("T1", "f1", "repair"),
            _entry("T1", "f1", "repair"),  # repairs=2 >= max_repair=2
        ]
        result = guard.check_failure("T1", "f1", history)
        assert result["action"] == LG.ACTION_REPLAN
        assert result["allowed"] is True

    def test_review_after_replan_exhausted(self):
        history = [_entry("T0", f"f{i}", "replan") for i in range(5)]
        result = _guard().check_failure("T1", "f1", history)
        assert result["allowed"] is False
        assert result["action"] == LG.ACTION_REVIEW

    def test_review_same_failure_threshold(self):
        guard = _guard(max_same_failure=3)
        history = [_entry("T1", "f1") for _ in range(3)]
        result = guard.check_failure("T1", "f1", history)
        assert result["allowed"] is False
        assert result["action"] == LG.ACTION_REVIEW

    def test_block_same_failure_double_threshold(self):
        guard = _guard(max_same_failure=3)
        history = [_entry("T1", "f1") for _ in range(6)]
        result = guard.check_failure("T1", "f1", history)
        assert result["allowed"] is False
        assert result["action"] == LG.ACTION_BLOCK

    def test_block_total_execution(self):
        guard = _guard(max_total_execution=5)
        history = [_entry(f"T{i}", f"f{i}") for i in range(5)]
        result = guard.check_failure("T1", "f1", history)
        assert result["allowed"] is False
        assert result["action"] == LG.ACTION_BLOCK

    def test_different_failure_not_counted(self):
        guard = _guard(max_same_failure=3)
        history = [_entry("T1", "other") for _ in range(5)]
        result = guard.check_failure("T1", "f1", history)
        assert result["allowed"] is True

    def test_different_task_not_counted(self):
        guard = _guard(max_same_failure=3)
        history = [_entry("T2", "f1") for _ in range(5)]
        result = guard.check_failure("T1", "f1", history)
        assert result["allowed"] is True

    def test_reason_present(self):
        result = _guard().check_failure("T1", "f1", [])
        assert isinstance(result["reason"], str) and result["reason"]


# ================================================================== 3. check_decision


class TestCheckDecision:
    def test_allowed_first_time(self):
        result = _guard().check_decision("INSERT_TASK", [])
        assert result["allowed"] is True

    def test_review_same_decision_repeated(self):
        guard = _guard(max_same_decision=3)
        history = [{"decision": "INSERT_TASK"} for _ in range(3)]
        result = guard.check_decision("INSERT_TASK", history)
        assert result["allowed"] is False

    def test_below_threshold_allowed(self):
        guard = _guard(max_same_decision=3)
        history = [{"decision": "INSERT_TASK"} for _ in range(2)]
        assert guard.check_decision("INSERT_TASK", history)["allowed"] is True

    def test_block_generated_tasks(self):
        guard = _guard(max_generated_tasks=3)
        history = [{"kind": "new_task"} for _ in range(3)]
        result = guard.check_decision("INSERT_TASK", history)
        assert result["allowed"] is False

    def test_block_total_execution(self):
        guard = _guard(max_total_execution=4)
        history = [_entry(f"T{i}") for i in range(4)]
        result = guard.check_decision("KEEP_PLAN", history)
        assert result["allowed"] is False

    def test_fail_safe_non_list(self):
        assert _guard().check_decision("d", None)["allowed"] is True


# ================================================================== 4. 默认值 / 常量


class TestDefaults:
    def test_default_limits(self):
        guard = LG.LoopGuard()
        assert guard.max_retry == 1
        assert guard.max_repair == 2
        assert guard.max_replan == 5
        assert guard.max_generated_tasks == 10
        assert guard.max_same_failure == 3
        assert guard.max_same_decision == 5
        assert guard.max_total_execution == 50

    def test_action_constants(self):
        assert LG.ACTION_RETRY == "retry"
        assert LG.ACTION_REPAIR == "repair"
        assert LG.ACTION_REPLAN == "replan"
        assert LG.ACTION_REVIEW == "review"
        assert LG.ACTION_BLOCK == "block"

    def test_custom_limits(self):
        guard = _guard(max_retry=3, max_total_execution=10)
        assert guard.max_retry == 3
        assert guard.max_total_execution == 10
