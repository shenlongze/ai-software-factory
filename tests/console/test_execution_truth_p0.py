"""tests/console/test_execution_truth_p0.py — P0-FIX: 数量型执行声称事实校验。

真实缺陷回归: "拆解成 6 个任务并创建到任务列表" 声称 + tool_calls=0 → 必须 BLOCK。

Outcome Contract: informational / success / partial / not_executed / failed
"""

from __future__ import annotations

import pytest

from factory_console.session.execution_truth import (
    extract_claimed_count, sanitize_hard_converge,
    validate_execution_claims,
)

# 真实 P0 漏洞原文
P0_TEXT = "我已经把开发计划拆解成 6 个具体任务并创建到任务列表里了"


def _calls(tool: str = "create_task", n: int = 1, ok: bool = True) -> list[dict]:
    return [
        {"tool": tool, "ok": ok, "output": f"任务已创建: x{i} (T-{i})" if ok else "err"}
        for i in range(n)
    ]


def test_p0_text_recognized_as_claim() -> None:
    """原漏洞文本必须被识别为任务声称 + 提取数量 6。"""
    v = validate_execution_claims(P0_TEXT, None)
    assert v["has_claims"] is True, f"必须识别声称: {v}"
    assert v["claimed_count"] == 6, f"claimed_count=6: {v}"
    assert v["ok"] is False
    assert v["outcome"] == "not_executed"


def test_zero_tool_call_blocks_success() -> None:
    """声称创建 6 + tool_calls=0 + actual=0 → NOT_EXECUTED, 禁止成功。"""
    v = validate_execution_claims("已创建 6 个任务", None, actual_count=0)
    assert v["ok"] is False
    assert v["outcome"] == "not_executed"
    assert v["reason"] == "zero_tool_call"


def test_count_mismatch_partial() -> None:
    """声称 6 + 实际 3 → PARTIAL, 阻止成功语义。"""
    v = validate_execution_claims("已创建 6 个任务", _calls(n=6), actual_count=3)
    assert v["ok"] is False
    assert v["outcome"] == "partial"
    assert v["reason"] == "count_mismatch"


def test_exact_success() -> None:
    """声称 6 + 实际 6 + 执行证据 → SUCCESS。"""
    v = validate_execution_claims("已创建 6 个任务", _calls(n=6), actual_count=6)
    assert v["ok"] is True
    assert v["outcome"] == "success"


def test_zero_actual_with_tool_call() -> None:
    """有 tool_call 但实际 0 → NOT_EXECUTED (count_zero)。"""
    v = validate_execution_claims("已创建 3 个任务", _calls(n=3), actual_count=0)
    assert v["ok"] is False
    assert v["outcome"] == "not_executed"
    assert v["reason"] == "count_zero"


def test_failed_execution() -> None:
    """tool_call 存在但全部失败 + 成功声称 → FAILED。"""
    v = validate_execution_claims("已创建 6 个任务", _calls(n=6, ok=False))
    assert v["ok"] is False
    assert v["outcome"] == "failed"


def test_informational_no_claim() -> None:
    """普通回答 (无执行声称) → informational, 不误判。"""
    v = validate_execution_claims("这是个人记账应用的设计思路。", None)
    assert v["ok"] is True
    assert v["outcome"] == "informational"


def test_intent_not_claim() -> None:
    """INTENT/PLAN 表达 (计划/准备/建议/将) 不得误判为执行声称。"""
    for t in ["我计划创建 6 个任务", "准备创建 6 个任务", "建议创建 6 个任务",
              "将创建 6 个任务", "想要创建 6 个任务"]:
        v = validate_execution_claims(t, None)
        assert v["has_claims"] is False, f"INTENT 不应是声称: {t} → {v}"


def test_existing_tasks_delta_not_needed_for_claim() -> None:
    """已有任务场景: 本轮 actual_count 是新增数 (调用方提供), 与 total 无关。"""
    v = validate_execution_claims("已创建 6 个任务", _calls(n=6), actual_count=6)
    assert v["ok"] is True  # 新增 6 个 (项目原有 2 个不影响)


def test_sanitize_partial_degrade() -> None:
    """PARTIAL → 硬收敛降级标注 (不得保留成功语义)。"""
    out = sanitize_hard_converge("已创建 6 个任务", _calls(n=6), actual_count=4)
    assert "实际成功 4 个" in out
    assert "执行真实性提示" in out


def test_sanitize_not_executed_degrade() -> None:
    """NOT_EXECUTED → 硬收敛降级标注。"""
    out = sanitize_hard_converge(P0_TEXT, None, actual_count=0)
    assert "没有真实工具执行记录" in out
