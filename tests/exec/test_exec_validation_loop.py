"""tests/exec/test_exec_validation_loop.py — 验证循环 (≤2 轮自动修复, 禁无限)。

覆盖 (Phase A++++++-1): 首轮通过 (1 次 work) / 失败 1 轮后修复成功 (2 次
work + 反馈注入) / 恒失败 (恰好 3 次尝试封顶 — 无无限循环) / 验证反馈进
下一轮 prompt / 循环内 Developer 错误 → FAILED + failure_reason。

设计依据: docs/architecture/developer-agent-reliability-model.md §5 验证循环
— work → apply → 验证 → 失败反馈 (禁泄 fix_hint) → 再 work, 最多 3 次总
尝试 (1 初始 + 2 修复轮); report 记录 validation_attempts。
"""

from __future__ import annotations

from pathlib import Path

from exec.agent_runtime import AgentRuntime
from exec.experience import ExperienceRecorder
from exec.models import ExecutionStatus
from exec_helpers import FakeProvider, git_diff_text, make_request, write_files

VALUE_0 = "VALUE = 0\n"
VALUE_1 = "VALUE = 1\n"
VALUE_2 = "VALUE = 2\n"

#: 验证命令: calc.py 内容含 'VALUE = 2' 才通过 (沙箱内跑, rc 语义)
#: 用 python3 而非 python — macOS 无 `python` (只有 python3); 沙箱验证
#: 命令在 /bin/sh 下执行, `python: command not found` 会让验证恒失败
#: (首轮 FAIL → 第二轮 mock 内容耗尽 → 空内容错误, 实为 fixture 错)。
CHECK_CMD = (
    "python3 -c \"import sys; "
    "sys.exit(0 if 'VALUE = 2' in open('calc.py').read() else 1)\""
)


class SequenceProvider:
    """按调用顺序返回预设回复的 Provider (验证循环分轮注入不同 patch)。"""

    provider_id = "mock-seq"

    def __init__(self, contents: list[str]) -> None:
        self._contents = list(contents)
        self.calls: list = []

    def generate(self, request):
        self.calls.append(request)
        content = self._contents.pop(0) if self._contents else ""
        return type("R", (), {"ok": True, "content": content,
                              "error": "", "usage": {}})()


def _runtime(tmp_path: Path, provider) -> AgentRuntime:
    work_root = tmp_path / "work"
    work_root.mkdir(parents=True, exist_ok=True)  # mkdtemp(dir=...) 须已存在
    return AgentRuntime(
        provider,
        validation_command=CHECK_CMD,
        artifacts_dir=tmp_path / "artifacts",
        work_root=work_root,
    )


def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    write_files(proj, {"calc.py": VALUE_0})
    return proj


def _patch(tmp_path: Path, before: str, after: str) -> str:
    """真实 git diff (沙箱 git apply 可应用)。"""
    return git_diff_text(
        tmp_path, {"calc.py": before}, {"calc.py": after}
    )


def _wrap(diff: str) -> str:
    return f"fixed\n<patch>\n{diff}\n</patch>"


class TestValidationLoop:
    def test_pass_first_attempt_single_work(self, tmp_path: Path):
        """首轮通过 → 恰好 1 次 work, 报告无循环行 (attempts=1)。"""
        proj = _project(tmp_path)
        provider = SequenceProvider([_wrap(_patch(tmp_path, VALUE_0, VALUE_2))])
        result = _runtime(tmp_path, provider).execute(
            make_request(project_dir=proj)
        )
        assert result.status is ExecutionStatus.SUCCESS
        assert len(provider.calls) == 1
        assert "validation loop:" not in result.report

    def test_fail_then_fix_second_round(self, tmp_path: Path):
        """失败 1 轮 → 反馈 → 第 2 轮修复成功 (2 次 work, 报告记 2 attempts)。"""
        proj = _project(tmp_path)
        provider = SequenceProvider(
            [
                _wrap(_patch(tmp_path, VALUE_0, VALUE_1)),  # 轮 1: 未达验收
                _wrap(_patch(tmp_path, VALUE_1, VALUE_2)),  # 轮 2: 修复成功
            ]
        )
        result = _runtime(tmp_path, provider).execute(
            make_request(project_dir=proj)
        )
        assert result.status is ExecutionStatus.SUCCESS
        assert len(provider.calls) == 2
        assert "validation loop: 2 attempts (1 automatic fix round(s))" in result.report

    def test_feedback_injected_into_second_prompt(self, tmp_path: Path):
        """验证失败输出进下一轮 prompt (extra_instruction 反馈, 禁泄 fix_hint)。"""
        proj = _project(tmp_path)
        provider = SequenceProvider(
            [
                _wrap(_patch(tmp_path, VALUE_0, VALUE_1)),
                _wrap(_patch(tmp_path, VALUE_1, VALUE_2)),
            ]
        )
        _runtime(tmp_path, provider).execute(make_request(project_dir=proj))
        second = provider.calls[1].task_context
        assert "你的修改未通过验证" in second
        assert "## Previous attempt feedback" in second
        assert "[FAIL]" in second  # 验证输出 (仅失败原因, 无修复提示)

    def test_always_failing_validation_capped_at_three(self, tmp_path: Path):
        """恒失败 → 恰好 3 次总尝试 (1 + 2 修复轮) — 禁无限循环。"""
        proj = _project(tmp_path)
        # 每轮新建不同文件 (补丁可重复应用; 验证命令恒失败)
        diffs = [
            git_diff_text(tmp_path, {}, {"fix1.py": "x = 1\n"}),
            git_diff_text(tmp_path, {}, {"fix2.py": "x = 2\n"}),
            git_diff_text(tmp_path, {}, {"fix3.py": "x = 3\n"}),
        ]
        provider = SequenceProvider([_wrap(d) for d in diffs])
        result = _runtime(tmp_path, provider).execute(
            make_request(project_dir=proj)
        )
        assert len(provider.calls) == 3  # 封顶, 不是无限
        # 验证失败不 fail 执行 (设计 §6: 留给 Human 审批例外放行)
        assert result.status is ExecutionStatus.SUCCESS
        assert "validation loop: 3 attempts (2 automatic fix round(s))" in result.report

    def test_developer_error_mid_loop_failed_with_reason(self, tmp_path: Path):
        """循环内 Developer 层错误 → FAILED 结果 + failure_reason (不静默)。"""
        proj = _project(tmp_path)
        provider = SequenceProvider(
            [
                _wrap(_patch(tmp_path, VALUE_0, VALUE_1)),  # 轮 1 失败
                "empty content, no operations, no patch",  # 轮 2 无解析 (重试后仍无)
                "",
            ]
        )
        result = _runtime(tmp_path, provider).execute(
            make_request(project_dir=proj)
        )
        assert result.status is ExecutionStatus.FAILED
        assert "no parseable patch" in result.error or "empty content" in result.error

    def test_failure_reason_propagates_to_experience(self, tmp_path: Path):
        """DeveloperError.failure_reason 透传到 Experience 记录 (不静默失败)。"""
        proj = _project(tmp_path)

        class FakeAnalyzer:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def record_experience(self, **kwargs):
                self.calls.append(kwargs)
                return {"recorded": True}

        analyzer = FakeAnalyzer()
        work_root = tmp_path / "work"
        work_root.mkdir(parents=True, exist_ok=True)
        runtime = AgentRuntime(
            FakeProvider(content="no diff, no operations at all"),
            validation_command=CHECK_CMD,
            artifacts_dir=tmp_path / "artifacts",
            work_root=work_root,
            experience=ExperienceRecorder(analyzer),
        )
        result = runtime.execute(make_request(project_dir=proj))
        assert result.status is ExecutionStatus.FAILED
        # 无解析 patch 内建重试 1 次 → failure_reason=no_patch 进经验 evidence
        reasons = [
            e["description"] for e in analyzer.calls[0]["evidence"]
        ]
        assert any("failure_reason: no_patch" in r for r in reasons)
