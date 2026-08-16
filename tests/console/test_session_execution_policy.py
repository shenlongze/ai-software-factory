"""S10-063 批次 A — ExecutionPolicy 测试套件。

覆盖: risk 分档 (destructive/删核心/大规模 DAG); 4 模式 (AUTO/SAFE_AUTO/
REVIEW_REQUIRED/MANUAL); can_execute/can_retry/can_repair/can_replan/
can_create_task 独立判定; 人工批准优先。

装配: 纯内存; 禁真实 LLM/网络。
"""

from __future__ import annotations

import pytest

from importlib import import_module

EP = import_module("factory-console.session.execution_policy")


def _policy(mode: str = "AUTO") -> EP.ExecutionPolicy:
    return EP.ExecutionPolicy(mode=mode)


# ================================================================== 1. risk 分档


class TestRisk:
    def test_default_low(self):
        assert _policy().risk({}) == "low"

    def test_explicit_risk_wins(self):
        assert _policy().risk({"risk": "high"}) == "high"
        assert _policy().risk({"risk_level": "medium"}) == "medium"

    def test_destructive_flag_high(self):
        assert _policy().risk({"destructive": True}) == "high"

    def test_chinese_destructive_keyword_high(self):
        assert _policy().risk({"reason": "需要删除核心模块"}) == "high"

    def test_english_destructive_keyword_high(self):
        assert _policy().risk({"description": "drop the database"}) == "high"

    def test_large_dag_high(self):
        assert _policy().risk({"dag_size": 10}) == "high"
        assert _policy().risk({"task_count": 15}) == "high"

    def test_medium_dag_medium(self):
        assert _policy().risk({"dag_size": 5}) == "medium"

    def test_large_scope_medium(self):
        assert _policy().risk({"scope": "large"}) == "medium"
        assert _policy().risk({"scope": "大"}) == "medium"

    def test_normal_reason_low(self):
        assert _policy().risk({"reason": "新增一个接口"}) == "low"


# ================================================================== 2. AUTO 模式


class TestModeAuto:
    def test_can_execute(self):
        allowed, reason = _policy("AUTO").can_execute({})
        assert allowed is True
        assert reason

    def test_can_retry(self):
        assert _policy("AUTO").can_retry({})[0] is True

    def test_can_repair(self):
        assert _policy("AUTO").can_repair({})[0] is True

    def test_can_replan(self):
        assert _policy("AUTO").can_replan({})[0] is True

    def test_can_create_task(self):
        assert _policy("AUTO").can_create_task({})[0] is True

    def test_auto_allows_high_risk(self):
        # AUTO 全自动: 高风险也放行 (策略决定, 由 budget/loop guard 兜底)
        allowed, _ = _policy("AUTO").can_execute({"risk": "high"})
        assert allowed is True


# ================================================================== 3. MANUAL 模式


class TestModeManual:
    def test_can_execute_blocked(self):
        allowed, reason = _policy("MANUAL").can_execute({})
        assert allowed is False
        assert "人工" in reason

    def test_can_retry_blocked(self):
        assert _policy("MANUAL").can_retry({})[0] is False

    def test_can_repair_blocked(self):
        assert _policy("MANUAL").can_repair({})[0] is False

    def test_can_replan_blocked(self):
        assert _policy("MANUAL").can_replan({})[0] is False

    def test_can_create_task_blocked(self):
        assert _policy("MANUAL").can_create_task({})[0] is False

    def test_approved_overrides_manual(self):
        allowed, reason = _policy("MANUAL").can_execute({"approved": True})
        assert allowed is True
        assert "批准" in reason


# ================================================================== 4. SAFE_AUTO 模式


class TestSafeAuto:
    def test_low_risk_allowed(self):
        allowed, _ = _policy("SAFE_AUTO").can_execute({})
        assert allowed is True

    def test_high_risk_blocks_execute(self):
        allowed, reason = _policy("SAFE_AUTO").can_execute({"risk": "high"})
        assert allowed is False
        assert "评审" in reason

    def test_high_risk_blocks_retry(self):
        assert _policy("SAFE_AUTO").can_retry({"risk": "high"})[0] is False

    def test_high_risk_blocks_repair(self):
        assert _policy("SAFE_AUTO").can_repair({"risk": "high"})[0] is False

    def test_high_risk_blocks_replan(self):
        assert _policy("SAFE_AUTO").can_replan({"risk": "high"})[0] is False

    def test_high_risk_blocks_create_task(self):
        assert _policy("SAFE_AUTO").can_create_task({"risk": "high"})[0] is False

    def test_low_confidence_blocks_execute(self):
        allowed, reason = _policy("SAFE_AUTO").can_execute({"confidence": 0.5})
        assert allowed is False
        assert "置信度" in reason

    def test_low_confidence_blocks_replan(self):
        assert _policy("SAFE_AUTO").can_replan({"confidence": 0.3})[0] is False

    def test_low_confidence_blocks_create_task(self):
        assert _policy("SAFE_AUTO").can_create_task({"confidence": 0.4})[0] is False

    def test_low_confidence_retry_still_allowed(self):
        # retry 低代价: SAFE_AUTO 下仅风险闸, 置信度不拦
        assert _policy("SAFE_AUTO").can_retry({"confidence": 0.5})[0] is True

    def test_low_confidence_repair_still_allowed(self):
        assert _policy("SAFE_AUTO").can_repair({"confidence": 0.5})[0] is True

    def test_high_confidence_allowed(self):
        allowed, _ = _policy("SAFE_AUTO").can_execute({"confidence": 0.9})
        assert allowed is True

    def test_medium_risk_execute_allowed_safe_auto(self):
        # medium 风险不拦 (仅 high 拦)
        assert _policy("SAFE_AUTO").can_execute({"risk": "medium"})[0] is True

    def test_approved_overrides_safe_auto(self):
        assert _policy("SAFE_AUTO").can_execute(
            {"risk": "high", "approved": True}
        )[0] is True


# ================================================================== 5. REVIEW_REQUIRED 模式


class TestReviewRequired:
    def test_can_execute_blocked(self):
        allowed, reason = _policy("REVIEW_REQUIRED").can_execute({})
        assert allowed is False
        assert "人工" in reason

    def test_can_retry_blocked(self):
        assert _policy("REVIEW_REQUIRED").can_retry({})[0] is False

    def test_can_repair_blocked(self):
        assert _policy("REVIEW_REQUIRED").can_repair({})[0] is False

    def test_can_replan_blocked(self):
        assert _policy("REVIEW_REQUIRED").can_replan({})[0] is False

    def test_can_create_task_blocked(self):
        assert _policy("REVIEW_REQUIRED").can_create_task({})[0] is False

    def test_approved_overrides(self):
        assert _policy("REVIEW_REQUIRED").can_execute(
            {"approved": True}
        )[0] is True
        assert _policy("REVIEW_REQUIRED").can_replan(
            {"approved": True}
        )[0] is True


# ================================================================== 6. 模式归一 / 常量


class TestModeNormalization:
    def test_mode_constants(self):
        assert EP.MODE_AUTO == "AUTO"
        assert EP.MODE_SAFE_AUTO == "SAFE_AUTO"
        assert EP.MODE_REVIEW == "REVIEW_REQUIRED"
        assert EP.MODE_MANUAL == "MANUAL"

    def test_invalid_mode_falls_back_auto(self):
        policy = EP.ExecutionPolicy(mode="WEIRD")
        assert policy.mode == "AUTO"
        assert policy.can_execute({})[0] is True

    def test_confidence_threshold_configurable(self):
        policy = EP.ExecutionPolicy(mode="SAFE_AUTO", confidence_threshold=0.9)
        assert policy.can_execute({"confidence": 0.8})[0] is False

    def test_risk_levels_constants(self):
        assert EP.RISK_LOW == "low"
        assert EP.RISK_MEDIUM == "medium"
        assert EP.RISK_HIGH == "high"
