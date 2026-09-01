"""tests/console/test_execution_truth_prefix.py — P1-FIX: 完成态优先于 INTENT 前缀。

Rule 1: 完成态执行声称 (已/了/完成/成功) 优先 — "开发计划已创建完成" 是 CLAIM
Rule 2: 无完成态 + 意图引导 (我计划/准备/打算/将) → INTENT, 不拦截
Rule 3: "计划" 作为业务名词不得误伤完成态声称
"""

from __future__ import annotations

import pytest

from factory_console.session.execution_truth import (
    extract_execution_claims, validate_execution_claims,
)

CLAIM_CASES = [
    "开发计划已创建完成，共 7 个任务进入任务列表",
    "项目计划已创建，共 5 个任务",
    "执行计划创建成功，共 6 个任务",
    "测试计划已经创建完成，包含 4 个任务",
    "我已经创建了 7 个具体任务",
    "我已将 7 个任务创建到任务列表",
    "7 个任务已经添加成功",
    "已经生成 5 个任务",
    "计划创建了 7 个任务",          # 完成态 (了) → CLAIM
    "开发计划创建了 7 个任务",       # 完成态 → CLAIM
    "开发计划已经创建 7 个任务",      # 完成态 → CLAIM
    "计划已经创建完成",             # 完成态 → CLAIM
]

INTENT_CASES = [
    "我计划创建 7 个任务",
    "我准备创建 7 个任务",
    "我打算创建 7 个任务",
    "开发计划将创建 7 个任务",
    "准备把计划拆解成 7 个任务",
    "我想创建 7 个任务",
    "希望创建 7 个任务",
]


@pytest.mark.parametrize("text", CLAIM_CASES)
def test_completed_claim_detected(text: str) -> None:
    """完成态执行声称必须被识别 (业务名词 '计划' 不豁免)。"""
    assert extract_execution_claims(text), f"必须识别为 CLAIM: {text}"


@pytest.mark.parametrize("text", INTENT_CASES)
def test_intent_not_claim(text: str) -> None:
    """未来意图表达不得误判为执行声称。"""
    assert not extract_execution_claims(text), f"INTENT 不应是 CLAIM: {text}"


def test_p1_original_text_partial() -> None:
    """P1 原文: claimed=7 vs actual=1 → PARTIAL, 禁止成功语义。"""
    v = validate_execution_claims(
        "开发计划已创建完成，共 7 个任务进入任务列表",
        [],
        evidence_text="任务已创建: X (id: TASK-febc1b44)",
    )
    assert v["ok"] is False
    assert v["outcome"] == "partial"
    assert v["claimed_count"] == 7
    assert v["actual_count"] == 1


def test_full_success_still_allowed() -> None:
    """真实 7/7 → SUCCESS (防假成功不得误伤真成功)。"""
    v = validate_execution_claims(
        "开发计划已创建完成，共 7 个任务进入任务列表",
        [{"tool": "create_task", "ok": True, "output": "x"} for _ in range(7)],
        actual_count=7,
    )
    assert v["ok"] is True
    assert v["outcome"] == "success"
