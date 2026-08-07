"""tests/exec/test_exec_developer.py — Developer Agent MVP (prompt/patch/报告)。

覆盖: build_prompt 组装 / parse_patch 三级识别 (<patch> 标签 / ```diff 围栏 /
裸 diff / NO_CHANGE → 空) / 无 patch 响亮 DeveloperError / _strip_fence EOF
换行规范化 / build_report 结构 / work() 经 mock Provider 全链 (成功/Provider
错误/response.error/无 patch)。
"""

from __future__ import annotations

import pytest

from exec.developer import DEFAULT_CONVENTIONS, DeveloperAgent, DeveloperError
from exec_helpers import FakeProvider, make_request

VALID_DIFF = (
    "--- a/calc.py\n"
    "+++ b/calc.py\n"
    "@@ -1,3 +1,3 @@\n"
    " def add(a, b):\n"
    "     return a + b\n"
    "-def sub(a, b):\n"
    "+def sub(a, b):\n"
)


def _agent(content: str = "", **kwargs) -> DeveloperAgent:
    return DeveloperAgent(FakeProvider(content=content), **kwargs)


class TestBuildPrompt:
    def test_contains_task_and_conventions(self):
        prompt = DeveloperAgent(FakeProvider()).build_prompt(
            objective="fix bug", project_context="- calc.py", requirement="keep style"
        )
        assert "fix bug" in prompt
        assert "- calc.py" in prompt
        assert "keep style" in prompt
        assert "## Conventions" in prompt
        assert "unified diff" in prompt

    def test_requirement_optional(self):
        p1 = DeveloperAgent(FakeProvider()).build_prompt(objective="o", requirement="")
        p2 = DeveloperAgent(FakeProvider()).build_prompt(objective="o", requirement="req here")
        assert "## Requirement" not in p1
        assert "## Requirement" in p2

    def test_custom_conventions(self):
        agent = DeveloperAgent(FakeProvider(), conventions="use tabs only")
        prompt = agent.build_prompt(objective="o")
        assert "use tabs only" in prompt
        assert DEFAULT_CONVENTIONS not in prompt

    def test_sandbox_path_section(self):
        prompt = DeveloperAgent(FakeProvider()).build_prompt(
            objective="o", sandbox_path="/tmp/sbx/project"
        )
        assert "/tmp/sbx/project" in prompt


class TestParsePatch:
    def test_patch_tags(self):
        out = DeveloperAgent.parse_patch("summary here\n<patch>\n" + VALID_DIFF + "\n</patch>")
        assert out == VALID_DIFF

    def test_patch_tags_keeps_trailing_blank_context_line(self):
        """文件以空行结尾 → diff 末尾合法 ' ' context 行不可剥 (hunk 计数)。"""
        diff = VALID_DIFF + " \n"
        out = DeveloperAgent.parse_patch("summary\n<patch>\n" + diff + "\n</patch>")
        assert out == diff

    def test_patch_tags_keeps_trailing_added_blank_line(self):
        """diff 末尾合法 '+' 空行 (新增空行) 不可剥。"""
        diff = VALID_DIFF + "+\n"
        out = DeveloperAgent.parse_patch("<patch>\n" + diff + "\n</patch>")
        assert out == diff

    def test_no_change_literal(self):
        assert DeveloperAgent.parse_patch("no change needed\n<patch>NO_CHANGE</patch>") == ""

    def test_no_change_case_insensitive(self):
        assert DeveloperAgent.parse_patch("<patch>\nno_change\n</patch>") == ""

    def test_fence_diff(self):
        out = DeveloperAgent.parse_patch("```diff\n" + VALID_DIFF + "\n```")
        assert VALID_DIFF in out

    def test_fence_plain(self):
        out = DeveloperAgent.parse_patch("```\n" + VALID_DIFF + "\n```")
        assert VALID_DIFF in out

    def test_bare_diff(self):
        assert VALID_DIFF in DeveloperAgent.parse_patch("text\n" + VALID_DIFF)

    def test_missing_patch_raises(self):
        with pytest.raises(DeveloperError, match="no parseable patch"):
            DeveloperAgent.parse_patch("just a summary, no diff here")

    def test_empty_content_raises(self):
        with pytest.raises(DeveloperError, match="empty content"):
            DeveloperAgent.parse_patch("   ")

    def test_strip_fence_keeps_trailing_newline(self):
        """EOF 换行保留 (git apply corrupt patch 根因防护); strip() 会剥掉。"""
        raw = "\n\n" + VALID_DIFF + "\n\n"
        out = DeveloperAgent._strip_fence(raw)
        assert out.endswith("\n")
        assert not out.endswith("\n\n")
        assert out.startswith("--- a/calc.py")

    def test_strip_fence_empty(self):
        assert DeveloperAgent._strip_fence("") == ""


class TestBuildReport:
    def test_report_contains_key_sections(self):
        req = make_request()
        report = DeveloperAgent.build_report(
            request=req,
            raw_content="I fixed it\n<patch>\n" + VALID_DIFF + "\n</patch>",
            patch_text=VALID_DIFF,
            duration=1.5,
            usage={"estimated_cost_usd": 0.2},
        )
        assert req.id in report
        assert "I fixed it" in report
        assert "diff lines:" in report
        assert "human review required" in report
        assert "## Usage" in report
        assert "duration: 1.50s" in report

    def test_report_no_patch(self):
        req = make_request()
        report = DeveloperAgent.build_report(request=req, raw_content="nothing", patch_text="")
        assert "no code change" in report

    def test_report_validation_section(self):
        from exec.validation import ValidationResult

        req = make_request()
        report = DeveloperAgent.build_report(
            request=req, raw_content="x", patch_text="",
            validation=ValidationResult(passed=True, checks=[], output="syntax ok"),
        )
        assert "PASS" in report
        assert "syntax ok" in report

    def test_summary_cut_before_patch_tag(self):
        s = DeveloperAgent._summary_of("explanation here\n<patch>...")
        assert s == "explanation here"


class TestWork:
    def test_work_success_output(self):
        provider = FakeProvider(content="summary\n<patch>\n" + VALID_DIFF + "\n</patch>")
        agent = DeveloperAgent(provider)
        req = make_request()
        out = agent.work(request=req, project_context="- calc.py", sandbox_path="/tmp/sbx")
        assert out.patch_text == VALID_DIFF
        assert "summary" in out.report
        assert out.raw_content.startswith("summary")
        assert len(provider.calls) == 1
        # Provider 收到组装后的 prompt (含任务)
        assert "fix the sub function bug" in provider.calls[0].task_context

    def test_work_provider_error_raises(self):
        agent = DeveloperAgent(FakeProvider(error="anthropic http 429: rate limited"))
        with pytest.raises(DeveloperError, match="anthropic http 429"):
            agent.work(request=make_request())

    def test_work_response_error_raises(self):
        agent = DeveloperAgent(FakeProvider(content="x", error="provider returned error"))
        with pytest.raises(DeveloperError, match="provider returned error"):
            agent.work(request=make_request())

    def test_work_no_patch_raises(self):
        agent = DeveloperAgent(FakeProvider(content="no diff here at all"))
        with pytest.raises(DeveloperError, match="no parseable patch"):
            agent.work(request=make_request())

    def test_work_usage_passthrough(self):
        provider = FakeProvider(
            content="<patch>\n" + VALID_DIFF + "\n</patch>",
            usage={"input_tokens": 10, "estimated_cost_usd": 0.01},
        )
        out = DeveloperAgent(provider).work(request=make_request())
        assert out.usage["input_tokens"] == 10
        assert out.usage["estimated_cost_usd"] == 0.01
