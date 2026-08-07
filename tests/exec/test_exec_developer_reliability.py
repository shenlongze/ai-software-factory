"""tests/exec/test_exec_developer_reliability.py — Phase A++++++-1 Developer 可靠性。

覆盖: 操作优先 (结构化操作 → 确定性 patch) / 行号内联 / 空内容重试 /
无解析重试 / Provider 层错误不重试 / max_tokens 16384 / 失败分类
(classify_failure + DeveloperError.failure_reason) / usage 跨重试累计。

设计依据: docs/architecture/developer-agent-reliability-model.md §5 —
空内容检测 + 内建重试 (模型随机性兜底, 非 verifier 放水) + 失败必记
结构化原因 (FailureReason)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from exec.developer import (
    DeveloperAgent,
    DeveloperError,
    FailureReason,
    classify_failure,
)
from exec_helpers import FakeProvider, make_request, write_files

CALC_SRC = (
    "def add(a, b):\n"
    "    return a + b\n"
    "\n"
    "def sub(a, b):\n"
    "    return a - b\n"
)

OPS_JSON = (
    '<operations>[{"operation": "replace_block", "target": "calc.py", '
    '"location": {"symbol": "sub"}, '
    '"change": "def sub(a, b):\\n    return abs(a - b)\\n"}]</operations>'
)


class SequenceProvider:
    """按调用顺序返回预设回复的 Provider (重试/验证循环测试)。"""

    provider_id = "mock-seq"

    def __init__(self, contents: list[str], usage: dict | None = None) -> None:
        self._contents = list(contents)
        self._usage = usage or {}
        self.calls: list = []

    def generate(self, request):
        self.calls.append(request)
        content = self._contents.pop(0) if self._contents else ""
        return type("R", (), {"ok": True, "content": content,
                              "error": "", "usage": dict(self._usage)})()


def _ops_sandbox(tmp_path: Path) -> Path:
    write_files(tmp_path, {"calc.py": CALC_SRC})
    return tmp_path


class TestOperationsPriority:
    def test_work_operations_generate_patch(self, tmp_path: Path):
        """操作优先: <operations> → 引擎确定性生成 diff (非模型手写 hunk)。"""
        sandbox = _ops_sandbox(tmp_path)
        agent = DeveloperAgent(FakeProvider(content="fix\n" + OPS_JSON))
        out = agent.work(request=make_request(), sandbox_path=str(sandbox))
        assert out.operations is not None and len(out.operations) == 1
        assert "--- a/calc.py" in out.patch_text
        assert "return abs(a - b)" in out.patch_text
        assert out.failure_reason == ""
        assert "generated from 1 structured operations" in out.report

    def test_work_operations_line_range(self, tmp_path: Path):
        sandbox = _ops_sandbox(tmp_path)
        content = (
            '<operations>[{"operation": "replace_block", "target": "calc.py", '
            '"location": {"line_range": [4, 5]}, "change": "def sub(a, b):\\n    return a * b\\n"}]'
            "</operations>"
        )
        out = DeveloperAgent(FakeProvider(content=content)).work(
            request=make_request(), sandbox_path=str(sandbox)
        )
        assert "return a * b" in out.patch_text

    def test_work_operations_anchor_failure_operation_error(self, tmp_path: Path):
        """锚点定位失败 → DeveloperError failure_reason=operation_error (不重试)。"""
        sandbox = _ops_sandbox(tmp_path)
        content = (
            '<operations>[{"operation": "replace_block", "target": "calc.py", '
            '"location": {"symbol": "ghost"}, "change": "def ghost(): pass\\n"}]'
            "</operations>"
        )
        agent = DeveloperAgent(FakeProvider(content=content))
        with pytest.raises(DeveloperError) as exc:
            agent.work(request=make_request(), sandbox_path=str(sandbox))
        assert exc.value.failure_reason == FailureReason.OPERATION_ERROR.value
        assert "symbol 定位失败" in str(exc.value)

    def test_work_operations_syntax_error_operation_error(self, tmp_path: Path):
        """操作生成内容语法错误 → operation_error (响亮, 不静默)。"""
        sandbox = _ops_sandbox(tmp_path)
        content = (
            '<operations>[{"operation": "modify_file", "target": "calc.py", '
            '"change": "def broken(:"}]</operations>'
        )
        agent = DeveloperAgent(FakeProvider(content=content))
        with pytest.raises(DeveloperError) as exc:
            agent.work(request=make_request(), sandbox_path=str(sandbox))
        assert exc.value.failure_reason == FailureReason.OPERATION_ERROR.value


class TestParseOperations:
    def test_no_operations_section_returns_none(self):
        assert DeveloperAgent.parse_operations("just a summary") is None

    def test_explicit_empty_list(self):
        assert DeveloperAgent.parse_operations("<operations>[]</operations>") == []

    def test_json_fence_operations(self):
        ops = DeveloperAgent.parse_operations(
            "```operations\n" + '[{"operation": "create_file", "target": "a.py", "change": "x"}]' + "\n```"
        )
        assert ops is not None and ops[0].target == "a.py"

    def test_non_list_raises_operation_error(self):
        with pytest.raises(DeveloperError) as exc:
            DeveloperAgent.parse_operations('<operations>{"a": 1}</operations>')
        assert exc.value.failure_reason == FailureReason.OPERATION_ERROR.value

    def test_non_dict_element_raises_operation_error(self):
        with pytest.raises(DeveloperError) as exc:
            DeveloperAgent.parse_operations('<operations>[1, 2]</operations>')
        assert exc.value.failure_reason == FailureReason.OPERATION_ERROR.value

    def test_invalid_field_raises_operation_error(self):
        with pytest.raises(DeveloperError) as exc:
            DeveloperAgent.parse_operations(
                '<operations>[{"operation": "teleport", "target": "a.py"}]</operations>'
            )
        assert exc.value.failure_reason == FailureReason.OPERATION_ERROR.value


class TestRetry:
    def test_empty_content_retries_once_then_raises(self, tmp_path: Path):
        sandbox = _ops_sandbox(tmp_path)
        provider = FakeProvider(content="")  # 恒空内容
        agent = DeveloperAgent(provider)
        with pytest.raises(DeveloperError) as exc:
            agent.work(request=make_request(), sandbox_path=str(sandbox))
        assert len(provider.calls) == 2  # 内建重试 1 次
        assert exc.value.failure_reason == FailureReason.EMPTY_CONTENT.value
        # 重试提示注入第二次 prompt (强化直接输出结果)
        assert "上次输出为空" in provider.calls[1].task_context

    def test_no_patch_retries_once_then_raises(self, tmp_path: Path):
        sandbox = _ops_sandbox(tmp_path)
        provider = FakeProvider(content="just a summary, no operations no patch")
        agent = DeveloperAgent(provider)
        with pytest.raises(DeveloperError) as exc:
            agent.work(request=make_request(), sandbox_path=str(sandbox))
        assert len(provider.calls) == 2
        assert exc.value.failure_reason == FailureReason.NO_PATCH.value

    def test_retry_success_on_second_attempt_usage_accumulated(self, tmp_path: Path):
        sandbox = _ops_sandbox(tmp_path)
        provider = SequenceProvider(
            contents=["", "fixed\n<patch>\n--- a/calc.py\n+++ b/calc.py\n@@ -1,3 +1,3 @@\n"],
            usage={"input_tokens": 100, "estimated_cost_usd": 0.001},
        )
        agent = DeveloperAgent(provider)
        out = agent.work(request=make_request(), sandbox_path=str(sandbox))
        assert out.retries == 1
        # usage 跨重试累计 (两次调用的 token 求和 — 诚实总花费)
        assert out.usage["input_tokens"] == 200
        assert abs(out.usage["estimated_cost_usd"] - 0.002) < 1e-9

    def test_provider_error_not_retried(self, tmp_path: Path):
        """Provider 层错误 (HTTP/key) 是环境判定 — 不重试。"""
        sandbox = _ops_sandbox(tmp_path)
        provider = FakeProvider(error="openai http 429: rate limited")
        agent = DeveloperAgent(provider)
        with pytest.raises(DeveloperError) as exc:
            agent.work(request=make_request(), sandbox_path=str(sandbox))
        assert len(provider.calls) == 1
        assert exc.value.failure_reason == FailureReason.PROVIDER_ERROR.value

    def test_max_retries_zero_no_retry(self, tmp_path: Path):
        sandbox = _ops_sandbox(tmp_path)
        provider = FakeProvider(content="no diff here")
        agent = DeveloperAgent(provider)
        with pytest.raises(DeveloperError, match="no parseable patch"):
            agent.work(request=make_request(), sandbox_path=str(sandbox), max_retries=0)
        assert len(provider.calls) == 1


class TestMaxTokensAndInline:
    def test_default_max_tokens_16384(self, tmp_path: Path):
        sandbox = _ops_sandbox(tmp_path)
        provider = FakeProvider(content="<patch>NO_CHANGE</patch>")
        agent = DeveloperAgent(provider)
        # NO_CHANGE → 合法空 patch (成功路径, patch_text="")
        out = agent.work(request=make_request(), sandbox_path=str(sandbox))
        assert out.patch_text == ""
        assert provider.calls[0].max_tokens == 16384

    def test_custom_max_tokens(self):
        agent = DeveloperAgent(FakeProvider(), max_tokens=8192)
        assert agent.max_tokens == 8192

    def test_render_lines_adds_number_prefix(self):
        out = DeveloperAgent._render_lines("class A {\n  int x = 1;\n}\n")
        assert out == "1| class A {\n2|   int x = 1;\n3| }"

    def test_render_lines_empty_content(self):
        assert DeveloperAgent._render_lines("") == ""

    def test_prompt_instructs_no_number_prefix_in_output(self, tmp_path: Path):
        sandbox = _ops_sandbox(tmp_path)
        provider = FakeProvider(content="<patch>NO_CHANGE</patch>")
        agent = DeveloperAgent(provider)
        agent.work(
            request=make_request(), sandbox_path=str(sandbox),
            source_files=["calc.py"],
        )
        prompt = provider.calls[0].task_context
        assert "1| def add(a, b):" in prompt  # 行号内联
        assert "行号" in prompt and "绝不能包含行号前缀" in prompt


class TestClassifyFailure:
    def test_empty_content(self):
        assert classify_failure("openai empty response: message.content is empty") == \
            FailureReason.EMPTY_CONTENT.value

    def test_no_patch(self):
        assert classify_failure("provider response contains no parseable patch or operations") == \
            FailureReason.NO_PATCH.value

    def test_patch_apply_failed(self):
        assert classify_failure("patch apply failed: git apply error: corrupt patch at line 6") == \
            FailureReason.PATCH_APPLY_FAILED.value

    def test_provider_error(self):
        assert classify_failure("openai http 429: rate limited") == \
            FailureReason.PROVIDER_ERROR.value
        assert classify_failure("anthropic api key missing: ANTHROPIC_API_KEY 未设置") == \
            FailureReason.PROVIDER_ERROR.value

    def test_operation_error(self):
        assert classify_failure("operation error: symbol 定位失败: 'ghost'") == \
            FailureReason.OPERATION_ERROR.value

    def test_verifier_failed_distinct_from_validation(self):
        """verifier 失败 (验收未达) 与验证循环失败 (语法/测试命令) 分类不同。"""
        assert classify_failure("verifier failed: dirty indicator missing") == \
            FailureReason.VERIFIER_FAILED.value
        assert classify_failure("validation failed: syntax error") == \
            FailureReason.VALIDATION_FAILED.value

    def test_sandbox_error(self):
        assert classify_failure("sandbox error: copytree failed") == \
            FailureReason.SANDBOX_ERROR.value

    def test_empty_or_unknown_falls_back_other(self):
        assert classify_failure("") == FailureReason.OTHER.value
        assert classify_failure("weird error nobody knows") == FailureReason.OTHER.value

    def test_developer_error_carries_reason(self):
        err = DeveloperError("boom", failure_reason=FailureReason.PATCH_APPLY_FAILED.value)
        assert err.failure_reason == FailureReason.PATCH_APPLY_FAILED.value
        assert DeveloperError("boom").failure_reason == FailureReason.OTHER.value
