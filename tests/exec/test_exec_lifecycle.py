"""tests/exec/test_exec_lifecycle.py — 执行闭环全链 (Runtime → 审批 → 应用 → 经验)。

冒烟级全链 (mock Provider): request → Runtime (沙箱副本 + patch + 三产物) →
Validation → ApprovalGate (approve) → apply 真实 git 仓库 → Experience 记录 →
org.execution.* 事件链完整 (requested → started → completed → approved →
applied)。

铁律断言: 沙箱零接触原项目 (执行后原文件逐字节不变); 事件链终态单一
(completed/failed 只发一次); 失败路径 (Provider 错误 → failed 结果 +
org.execution.failed + Experience 负信号)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from exec.agent_runtime import AgentRuntime
from exec.approval import ApprovalGate
from exec.experience import ExperienceRecorder
from exec.models import ArtifactType, ExecutionStatus
from exec_helpers import FakeProvider, git_diff_text, make_request, write_files

CALC_BEFORE = "def add(a, b):\n    return a + b\n\n"
CALC_AFTER = "def add(a, b):\n    return abs(a + b)\n\n"


def _bug_project(tmp_path: Path) -> Path:
    """最小 Python 项目 (bug 任务目标; 与 git_diff_text 的 before 逐字一致)。"""
    proj = tmp_path / "bug-project"
    write_files(proj, {"calc.py": CALC_BEFORE, "README.md": "# demo\n"})
    return proj


def _patch_content(tmp_path: Path) -> str:
    """真实 git diff (context 与项目文件逐字匹配, 沙箱 git apply 可应用)。"""
    return git_diff_text(tmp_path, {"calc.py": CALC_BEFORE}, {"calc.py": CALC_AFTER})


def _provider_with_patch(tmp_path: Path) -> FakeProvider:
    return FakeProvider(
        content="fixed the sub bug\n<patch>\n" + _patch_content(tmp_path) + "\n</patch>",
        usage={"input_tokens": 12, "estimated_cost_usd": 0.02},
    )


class FakeAnalyzer:
    """ExperienceAnalyzer mock (记录 kwargs; 供闭环断言)。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def record_experience(self, **kwargs):
        self.calls.append(kwargs)
        return {"recorded": True}


def _runtime(
    provider: FakeProvider,
    store,
    logger,
    analyzer: FakeAnalyzer | None = None,
    *,
    validation_command: str | None = None,
) -> AgentRuntime:
    return AgentRuntime(
        provider,
        store=store,
        logger=logger,
        validation_command=validation_command,
        artifacts_dir=store.dir,
        experience=ExperienceRecorder(analyzer) if analyzer is not None else None,
    )


class TestFullChain:
    def test_request_to_apply_to_experience(
        self, exec_store, logger, tmp_path: Path, git_target: Path
    ):
        """request → run → 产物 → approve → apply → experience → 事件链完整。"""
        project = _bug_project(tmp_path)
        provider = _provider_with_patch(tmp_path)
        analyzer = FakeAnalyzer()
        runtime = _runtime(provider, exec_store, logger, analyzer)

        request = make_request(
            request_id="EXR-lc-1",
            task_id="T-lc-1",
            project_dir=project,
            capabilities=["python"],
        )
        result = runtime.execute(request, employee=_Employee("E-1"))

        # ---- run: 成功 + 三产物 ----
        assert result.is_success
        assert result.status is ExecutionStatus.SUCCESS
        assert result.request_id == "EXR-lc-1"
        types = [a.type for a in result.artifacts]
        assert types == [ArtifactType.PATCH, ArtifactType.TEST_RESULT, ArtifactType.REPORT]
        patch_artifact = next(a for a in result.artifacts if a.type is ArtifactType.PATCH)
        assert patch_artifact.path and Path(patch_artifact.path).exists()
        assert patch_artifact.event_refs, "patch 携带事件链锚点"

        # ---- 落库: request/result/artifacts ----
        assert exec_store.get_request("EXR-lc-1") is not None
        assert exec_store.get_result(result.id) is not None
        assert exec_store.count_artifacts() == 3

        # ---- 沙箱零接触: 原项目逐字节不变 ----
        assert (project / "calc.py").read_text() == CALC_BEFORE
        assert "abs" not in (project / "calc.py").read_text()

        # ---- 审批: 未批前 apply 硬拒绝 ----
        gate = ApprovalGate(exec_store, logger=logger)
        approval = gate.request(result)
        with pytest.raises(Exception, match="requires approved approval"):
            gate.apply(approval.id, git_target)

        # ---- 审批通过 → 应用 patch ----
        gate.decide(approval.id, "approved", decided_by="CEO", comment="looks good")
        updated, applied_patch = gate.apply(approval.id, git_target)
        assert updated.applied
        assert "abs(a + b)" in applied_patch
        assert "abs(a + b)" in (git_target / "calc.py").read_text()

        # ---- 经验: 成功正信号 + 成本/能力/任务 ----
        assert len(analyzer.calls) == 1
        call = analyzer.calls[0]
        assert call["subject_id"] == "E-1"
        assert call["result"] == "success"
        assert call["score"] == 0.8
        assert call["quality_score"] == 1.0
        assert call["task_type"] == "T-lc-1"
        assert call["cost"] == 1.0 - 0.02
        assert "python" in call["capability"]

        # ---- 事件链: requested → started → completed → approved → applied ----
        types = [e.type.value for e in logger.store.query()]
        assert "org.execution.requested" in types
        assert "org.execution.started" in types
        assert "org.execution.completed" in types
        assert "org.execution.approved" in types
        assert "org.execution.applied" in types
        assert "org.execution.failed" not in types
        # 顺序: completed 在 approved 前 (终态单一, 报告状态转换)
        seqs = {e.type.value: e.seq for e in logger.store.query()}
        assert seqs["org.execution.requested"] < seqs["org.execution.started"]
        assert seqs["org.execution.started"] < seqs["org.execution.completed"]
        assert seqs["org.execution.completed"] < seqs["org.execution.approved"]
        assert seqs["org.execution.approved"] < seqs["org.execution.applied"]
        # 终态单一: 各类型恰一条
        for t in types:
            assert types.count(t) == 1

    def test_validation_command_runs_in_sandbox(
        self, exec_store, logger, tmp_path: Path
    ):
        """--test-cmd 在沙箱内执行; 失败不自动 fail 执行 (留给审批决定)。"""
        project = _bug_project(tmp_path)
        provider = _provider_with_patch(tmp_path)
        runtime = _runtime(
            provider,
            exec_store,
            logger,
            None,
            validation_command="python3 -c 'print(1)'",
        )
        result = runtime.execute(make_request(project_dir=project), employee=_Employee("E-1"))
        assert result.is_success
        test_artifact = next(
            a for a in result.artifacts if a.type is ArtifactType.TEST_RESULT
        )
        assert "1" in Path(test_artifact.path).read_text()

    def test_provider_failure_records_failed_and_negative_experience(
        self, exec_store, logger, tmp_path: Path
    ):
        """Provider 错误 → failed 结果 + org.execution.failed + Experience 负信号。"""
        project = _bug_project(tmp_path)
        provider = FakeProvider(error="anthropic http 429: rate limited")
        analyzer = FakeAnalyzer()
        runtime = _runtime(provider, exec_store, logger, analyzer)
        request = make_request(request_id="EXR-lc-2", project_dir=project)
        result = runtime.execute(request, employee=_Employee("E-1"))
        assert not result.is_success
        assert result.status is ExecutionStatus.FAILED
        assert "provider error" in result.error
        types = [e.type.value for e in logger.store.query()]
        assert "org.execution.failed" in types
        assert "org.execution.completed" not in types
        # 负信号经验: failure + 失败原因
        assert len(analyzer.calls) == 1
        call = analyzer.calls[0]
        assert call["result"] == "failure"
        assert call["score"] == 0.2
        assert any("failure_reason" in e["description"] for e in call["evidence"])

    def test_missing_project_dir_fails_safely(self, exec_store, logger, tmp_path: Path):
        runtime = _runtime(FakeProvider(), exec_store, logger)
        request = make_request(request_id="EXR-lc-3", project_dir=tmp_path / "nope")
        result = runtime.execute(request)
        assert not result.is_success
        assert "project dir not found" in result.error
        types = [e.type.value for e in logger.store.query()]
        assert "org.execution.failed" in types


class _Employee:
    """duck-typed Employee (org 零依赖; 含 id/capabilities 即可)。"""

    def __init__(self, employee_id: str) -> None:
        self.id = employee_id
        self.capabilities = ["python"]
