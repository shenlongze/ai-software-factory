"""tests/console/test_execution_truth.py — P0-001: Execution Claim ≠ Execution Fact.

覆盖 (FIX-P0-001 REQUIRED TESTS):
- Test 1: Zero Tool Call + Fake Success → 禁止
- Test 2: Zero Tool Call + File Claim → 禁止
- Test 3: Zero Tool Call + Sleep → 禁止
- Test 4: Real Tool Call + Success → 允许
- Test 5: Real Tool Call + Failure + 声称成功 → 禁止
- Test 6: 声称输出与实际 tool_result 不符 → 以真实 result 为准 (W8 细节兜底)
- Test 7: Fake <invoke> 文本 ≠ 真实 ToolCall
- Test 8: Mixed Response (声称执行 + 零工具调用) → 禁止
- Test 9: Normal Non-execution Answer → 允许
- Test 10: DeepSeek trait contract 注入
"""

from __future__ import annotations

import pytest

from factory_console.session.execution_truth import (
    extract_execution_claims,
    has_success_semantics,
    sanitize_hard_converge,
    validate_execution_claims,
)


# ---------------------------------------------------------------- Test 1/2/3/8
# Zero Tool Call = 负证据


@pytest.mark.parametrize(
    "text",
    [
        "已执行 echo hello123，输出 hello123",          # Test 1: fake command success
        "命令执行成功，输出为 hello",                    # Test 1 variant
        "已经创建 /tmp/test-file",                       # Test 2: file claim
        "文件已经创建成功：/tmp/test-file",              # Test 2 variant
        "sleep 15 正在执行",                              # Test 3: sleep claim
        "我已经执行命令。根据结果，下面是分析",           # Test 8: mixed + zero calls
        "任务已完成，全部开发完成",                       # task completion claim
        "pytest 测试已通过，11791 passed",                # test claim
        "构建成功，编译通过",                              # build claim
        "已经部署到生产环境，服务已上线",                  # deploy claim
    ],
)
def test_zero_tool_call_execution_claim_blocked(text: str) -> None:
    """零真实工具调用 + 执行声称 → BLOCK (负证据)。"""
    v = validate_execution_claims(text, [])
    assert v["ok"] is False, f"应禁止: {text}"
    assert v["reason"] == "zero_tool_call"
    assert v["missing"], "应列出未验证声称"


# ---------------------------------------------------------------- Test 4
# Real Tool Call + Success


def test_real_tool_call_success_allowed() -> None:
    """真实工具调用成功 + 声称 → ALLOW (有执行记录支撑)。"""
    calls = [{"tool": "bash_exec", "ok": True, "output": "hello123"}]
    v = validate_execution_claims("已执行 echo hello123，输出 hello123", calls)
    assert v["ok"] is True


# ---------------------------------------------------------------- Test 5
# Real Tool Call + Failure


def test_real_tool_call_failure_with_success_claim_blocked() -> None:
    """工具调用失败 + 声称成功 → BLOCK (无成功执行记录)。"""
    calls = [{"tool": "bash_exec", "ok": False, "error": "command not found"}]
    v = validate_execution_claims("命令执行成功，输出 hello", calls)
    assert v["ok"] is False
    assert v["reason"] == "no_success_evidence"


def test_real_tool_call_failure_without_success_claim_allowed() -> None:
    """工具调用失败 + 如实陈述失败 → ALLOW。"""
    calls = [{"tool": "bash_exec", "ok": False, "error": "command not found"}]
    v = validate_execution_claims("该命令执行失败：command not found", calls)
    assert v["ok"] is True


# ---------------------------------------------------------------- Test 6
# 声称输出与实际 result 不符 → W8 细节兜底 (validator 层面有证据即放行,
# 细节不一致由 verify_details 在 agent_loop 注入修正)


def test_claim_output_mismatch_handled_by_w8() -> None:
    """声称输出与实际 result 不符: validator 有真实执行记录 → 放行, 细节交给 W8。"""
    calls = [{"tool": "bash_exec", "ok": True, "output": "XYZ"}]
    v = validate_execution_claims("命令输出为 42", calls)
    # 执行声称有证据 (ok 工具调用) → 不阻断; 具体数字/内容一致性由 W8 verify_details 兜底
    assert v["ok"] is True
    # W8 兜底在 agent_loop: calls 非空时 verify_details 比对答案细节与 reference
    from factory_console.session.answer_verify import verify_details

    chk = verify_details("命令输出为 42", "XYZ")
    assert chk["ok"] is False  # 数字 42 在 reference 中找不到 → W8 会注入修正


# ---------------------------------------------------------------- Test 7
# Fake <invoke> 文本 ≠ 真实 ToolCall


def test_fake_invoke_text_is_not_real_toolcall() -> None:
    """模型文本中的 <invoke> 不等于真实 ToolCall — 兑现机制处理后才有证据。"""
    text = "<invoke name=\"bash_exec\"><parameter name=\"command\">echo hi</parameter></invoke>"
    # invoke 文本本身不是执行声称 (validator 不误判), 兑现机制 (agent_loop 1791)
    # 负责把文本模拟兑现为真实执行; 未兑现前 calls=[] → 声称被拦截
    claims = extract_execution_claims(text)
    assert claims == []
    # 但文本里若声称了执行事实 + calls=[] → 仍拦截
    v = validate_execution_claims("已执行 echo hi，输出 hi", [])
    assert v["ok"] is False
    # 兑现后 (真实记录存在) → 放行
    calls = [{"tool": "bash_exec", "ok": True, "output": "hi"}]
    v2 = validate_execution_claims("已执行 echo hi，输出 hi", calls)
    assert v2["ok"] is True


# ---------------------------------------------------------------- Test 9
# Normal Non-execution Answer


@pytest.mark.parametrize(
    "text",
    [
        "你可以运行 bash_exec 来执行这个命令。",          # 建议
        "如果你刚才执行成功，应该看到输出。",              # 条件表达
        "建议先用 pytest 跑一遍测试。",                    # 建议
        "你好！有什么可以帮你的吗？",                      # 普通对话
        "执行 bash 命令通常可以这样做：先确认环境。",       # 一般描述
        "这个项目共有 15 个项目。",                        # 非执行事实
    ],
)
def test_normal_answer_allowed(text: str) -> None:
    """普通回答/建议/条件表达 → ALLOW (不误伤)。"""
    v = validate_execution_claims(text, [])
    assert v["ok"] is True, f"不应拦截: {text}"
    assert v["has_claims"] is False


# ---------------------------------------------------------------- extract / sanitize


def test_extract_claims_structured_types() -> None:
    claims = extract_execution_claims("已创建文件 /tmp/a 且命令执行成功，测试通过，已部署上线")
    types = {c["type"] for c in claims}
    assert "file" in types
    assert "command" in types
    assert "test" in types
    assert "deploy" in types


def test_has_success_semantics() -> None:
    assert has_success_semantics([{"type": "command", "text": "命令执行成功"}]) is True
    assert has_success_semantics([{"type": "command", "text": "正在执行 sleep"}]) is False


def test_sanitize_hard_converge_appends_honest_note() -> None:
    """硬收敛兜底: 无据声称 → 追加诚实标注, 不裸放行。"""
    content = "已执行命令，输出 hello"
    out = sanitize_hard_converge(content, [])
    assert "执行真实性提示" in out
    assert content in out  # 保留原文但加标注


def test_sanitize_hard_converge_passthrough_when_ok() -> None:
    content = "这是一个普通回答"
    assert sanitize_hard_converge(content, []) == content


# ---------------------------------------------------------------- Test 10
# DeepSeek trait contract


def test_deepseek_trait_injects_execution_truth_contract() -> None:
    """deepseek 系模型: A0 prompt contract 注入 (辅助防线)。"""
    from factory_console.session.model_prompt import pick_prompt, traits_for_provider

    traits = traits_for_provider("deepseek")
    assert traits.get("no_fabricated_execution") is True

    p = pick_prompt(capabilities=["tool_calling"], context_window=64000, provider_id="deepseek")
    assert "执行真实性契约" in p["system"]
    assert "禁止声称『已执行/已创建/执行成功』" in p["system"]


def test_non_deepseek_no_contract() -> None:
    """非 deepseek: 不注入契约 (不污染强模型)。"""
    from factory_console.session.model_prompt import pick_prompt

    p = pick_prompt(capabilities=["tool_calling"], context_window=200000, provider_id="anthropic")
    assert "执行真实性契约" not in p["system"]
