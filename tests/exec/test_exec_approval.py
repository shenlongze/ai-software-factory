"""tests/exec/test_exec_approval.py — ApprovalGate (应用 patch 前必批/拒绝/幂等)。

覆盖: request (成功才可申请/失败响亮) / decide (approve→approved 事件 /
reject→rejected 无 approved 事件 / 二次决定响亮 / 非法终态响亮 / 未找到) /
apply (pending 硬拒绝 / rejected 硬拒绝 / approved→git apply 真实落盘 /
重复应用幂等拒绝 / patch 缺失响亮 / 非 git 目标响亮 / 目标缺失) /
list (status 过滤)。

铁律 (设计 §2): 执行权 != 审核权 — 未批/已拒/已应用 全部 ApprovalError,
绝不静默应用。事件: approve 发 org.execution.approved, reject 不发
(拒绝经审批记录 + 修复循环审计, 报告状态转换)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from exec.approval import ApprovalError, ApprovalGate, classify_risk
from exec.models import (
    ApprovalDecision,
    Artifact,
    ArtifactType,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)
from exec_helpers import git_diff_text

BEFORE = {"calc.py": "def add(a, b):\n    return a + b\n\n"}
AFTER = {"calc.py": "def add(a, b):\n    return a * b\n\n"}


def _result_with_patch(
    tmp_path: Path,
    *,
    request_id: str = "EXR-apr-1",
    result_id: str = "EXS-apr-1",
    patch_file: str | None = None,
    status: ExecutionStatus = ExecutionStatus.SUCCESS,
) -> tuple[ExecutionResult, str]:
    """成功结果 + 真实 git diff patch 落盘; 返回 (result, patch_path)。"""
    if patch_file is None:
        patch_file = str(tmp_path / "work" / "changes.patch")
    patch_path = Path(patch_file)
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_text = git_diff_text(tmp_path, BEFORE, AFTER)
    patch_path.write_text(patch_text, encoding="utf-8")
    result = ExecutionResult(
        id=result_id,
        request_id=request_id,
        status=status,
        artifacts=[
            Artifact(
                id="ART-apr-1",
                type=ArtifactType.PATCH,
                task_id="T-apr-1",
                path=str(patch_path),
            )
        ],
    )
    return result, patch_text


def _saved_result_with_patch(store, tmp_path: Path, **kwargs) -> tuple[ExecutionResult, str]:
    """result 落库版 (apply 经 store.get_result_by_request 定位 patch 源)。"""
    result, patch_text = _result_with_patch(tmp_path, **kwargs)
    store.save_result(result)
    return result, patch_text


class TestRequest:
    def test_success_result_creates_pending(self, exec_store, tmp_path: Path):
        result, _ = _result_with_patch(tmp_path)
        record = ApprovalGate(exec_store).request(result)
        assert record.id.startswith("APR-")
        assert record.request_id == result.request_id
        assert record.decision is ApprovalDecision.PENDING
        assert not record.applied
        # 落库可查
        assert exec_store.get_approval(record.id) is not None

    def test_failed_result_raises(self, exec_store, tmp_path: Path):
        result, _ = _result_with_patch(tmp_path, status=ExecutionStatus.FAILED)
        with pytest.raises(ApprovalError, match="failed execution"):
            ApprovalGate(exec_store).request(result)


class TestDecide:
    def test_approve_sets_terminal_and_events(self, exec_store, logger, tmp_path: Path):
        result, _ = _result_with_patch(tmp_path)
        gate = ApprovalGate(exec_store, logger=logger)
        record = gate.request(result)
        updated = gate.decide(record.id, "approved", decided_by="CEO")
        assert updated.decision is ApprovalDecision.APPROVED
        assert updated.decided_by == "CEO"
        assert updated.decided_at is not None
        # 事件: org.execution.approved (仅 approve)
        types = [e.type.value for e in logger.store.query()]
        assert "org.execution.approved" in types
        assert "org.execution.applied" not in types

    def test_approve_enum_value(self, exec_store, tmp_path: Path):
        result, _ = _result_with_patch(tmp_path)
        gate = ApprovalGate(exec_store)
        record = gate.request(result)
        updated = gate.decide(record.id, ApprovalDecision.APPROVED, decided_by="CEO")
        assert updated.is_approved

    def test_reject_no_approved_event(self, exec_store, logger, tmp_path: Path):
        result, _ = _result_with_patch(tmp_path)
        gate = ApprovalGate(exec_store, logger=logger)
        record = gate.request(result)
        updated = gate.decide(record.id, "rejected", decided_by="CEO", comment="fix tests first")
        assert updated.decision is ApprovalDecision.REJECTED
        assert updated.comment == "fix tests first"
        types = [e.type.value for e in logger.store.query()]
        assert "org.execution.approved" not in types

    def test_double_decide_raises(self, exec_store, tmp_path: Path):
        result, _ = _result_with_patch(tmp_path)
        gate = ApprovalGate(exec_store)
        record = gate.request(result)
        gate.decide(record.id, "approved", decided_by="CEO")
        with pytest.raises(ApprovalError, match="already decided"):
            gate.decide(record.id, "rejected", decided_by="CEO")

    def test_invalid_decision_raises(self, exec_store, tmp_path: Path):
        result, _ = _result_with_patch(tmp_path)
        gate = ApprovalGate(exec_store)
        record = gate.request(result)
        with pytest.raises(ApprovalError, match="invalid approval decision"):
            gate.decide(record.id, "maybe", decided_by="CEO")

    def test_not_found_raises(self, exec_store):
        with pytest.raises(ApprovalError, match="approval not found"):
            ApprovalGate(exec_store).decide("APR-nope", "approved", decided_by="CEO")


class TestApply:
    def test_apply_requires_approval(self, exec_store, git_target: Path, tmp_path: Path):
        """pending 未批 → 硬拒绝 (应用 patch 前必批铁律)。"""
        result, _ = _saved_result_with_patch(exec_store, tmp_path)
        gate = ApprovalGate(exec_store)
        record = gate.request(result)
        with pytest.raises(ApprovalError, match="requires approved approval"):
            gate.apply(record.id, git_target)

    def test_apply_rejected_raises(self, exec_store, git_target: Path, tmp_path: Path):
        result, _ = _saved_result_with_patch(exec_store, tmp_path)
        gate = ApprovalGate(exec_store)
        record = gate.request(result)
        gate.decide(record.id, "rejected", decided_by="CEO")
        with pytest.raises(ApprovalError, match="requires approved approval"):
            gate.apply(record.id, git_target)

    def test_apply_applies_patch_to_target(self, exec_store, git_target: Path, tmp_path: Path):
        """approved → git apply 真实写入目标项目 (可审计路径)。"""
        result, patch_text = _saved_result_with_patch(exec_store, tmp_path)
        gate = ApprovalGate(exec_store, logger=None)
        record = gate.request(result)
        gate.decide(record.id, "approved", decided_by="CEO")
        updated, applied = gate.apply(record.id, git_target)
        assert updated.applied is True
        assert updated.applied_at is not None
        assert applied == patch_text
        # 目标项目真实变更
        assert "*" in (git_target / "calc.py").read_text()

    def test_apply_double_raises(self, exec_store, git_target: Path, tmp_path: Path):
        """已应用 → 拒绝重复应用 (幂等保护)。"""
        result, _ = _saved_result_with_patch(exec_store, tmp_path)
        gate = ApprovalGate(exec_store)
        record = gate.request(result)
        gate.decide(record.id, "approved", decided_by="CEO")
        gate.apply(record.id, git_target)
        with pytest.raises(ApprovalError, match="already applied"):
            gate.apply(record.id, git_target)

    def test_apply_missing_patch_artifact(self, exec_store, git_target: Path, tmp_path: Path):
        result = ExecutionResult(
            id="EXS-nopatch", request_id="EXR-nopatch", artifacts=[]
        )
        exec_store.save_result(result)
        gate = ApprovalGate(exec_store)
        record = gate.request(result)
        gate.decide(record.id, "approved", decided_by="CEO")
        with pytest.raises(ApprovalError, match="no patch artifact"):
            gate.apply(record.id, git_target)

    def test_apply_non_git_target_raises(self, exec_store, tmp_path: Path):
        """非 git 仓库 → 响亮错误, 不静默降级 (不可审计路径禁止)。"""
        result, _ = _saved_result_with_patch(exec_store, tmp_path)
        gate = ApprovalGate(exec_store)
        record = gate.request(result)
        gate.decide(record.id, "approved", decided_by="CEO")
        plain = tmp_path / "plain-target"
        plain.mkdir()
        with pytest.raises(ApprovalError, match="not a git repository"):
            gate.apply(record.id, plain)

    def test_apply_missing_target_raises(self, exec_store, tmp_path: Path):
        result, _ = _saved_result_with_patch(exec_store, tmp_path)
        gate = ApprovalGate(exec_store)
        record = gate.request(result)
        gate.decide(record.id, "approved", decided_by="CEO")
        with pytest.raises(ApprovalError, match="target project dir not found"):
            gate.apply(record.id, tmp_path / "nope")

    def test_apply_missing_result_raises(self, exec_store, git_target: Path):
        """request 无对应 ExecutionResult → 响亮 (patch 源缺失)。"""
        from exec.models import ApprovalRecord, new_id

        store = exec_store
        record = ApprovalRecord(id=new_id("APR"), request_id="EXR-ghost")
        store.save_approval(record)
        gate = ApprovalGate(store)
        gate.decide(record.id, "approved", decided_by="CEO")
        with pytest.raises(ApprovalError, match="execution result not found"):
            gate.apply(record.id, git_target)

    def test_apply_emits_applied_event(self, exec_store, logger, git_target: Path, tmp_path: Path):
        result, _ = _saved_result_with_patch(exec_store, tmp_path)
        gate = ApprovalGate(exec_store, logger=logger)
        record = gate.request(result)
        gate.decide(record.id, "approved", decided_by="CEO")
        gate.apply(record.id, git_target)
        types = [e.type.value for e in logger.store.query()]
        assert "org.execution.approved" in types
        assert "org.execution.applied" in types


class TestListAndGet:
    def test_get_missing_returns_none(self, exec_store):
        assert ApprovalGate(exec_store).get("APR-nope") is None

    def test_list_status_filter(self, exec_store, tmp_path: Path):
        gate = ApprovalGate(exec_store)
        r1, _ = _result_with_patch(tmp_path, request_id="EXR-f1")
        r2, _ = _result_with_patch(tmp_path, request_id="EXR-f2", result_id="EXS-f2")
        a1 = gate.request(r1)
        a2 = gate.request(r2)
        gate.decide(a1.id, "approved", decided_by="CEO")
        assert [a.id for a in gate.list(status="pending")] == [a2.id]
        assert [a.id for a in gate.list(status="approved")] == [a1.id]
        assert len(gate.list()) == 2
        assert len(gate.list(status="rejected")) == 0

    def test_request_keeps_provided_id(self, exec_store, tmp_path: Path):
        result, _ = _result_with_patch(tmp_path)
        record = ApprovalGate(exec_store).request(result, approval_id="APR-custom")
        assert record.id == "APR-custom"


class TestRiskClassify:
    """M1a 分级审批: 爆炸半径 → risk_level/required_roles。"""

    def test_low_single_file(self):
        level, roles = classify_risk(
            "--- a/main.py\n+++ b/main.py\n@@ -1 +1,2 @@\n", changed_files=1
        )
        assert level == "low"
        assert roles == ["developer"]

    def test_medium_two_files(self):
        level, roles = classify_risk(
            "--- a/a.py\n+++ b/a.py\n--- a/b.py\n+++ b/b.py\n", changed_files=2
        )
        assert level == "medium"
        assert "tech_lead" in roles

    def test_medium_three_files(self):
        level, _roles = classify_risk("--- a/x\n+++ b/x\n", changed_files=3)
        assert level == "medium"

    def test_high_dependency_upgrade(self):
        level, roles = classify_risk(
            "--- a/requirements.txt\n+++ b/requirements.txt\n+django==5.0\n", changed_files=1
        )
        assert level == "high"
        assert "compliance" in roles

    def test_high_delete(self):
        level, _roles = classify_risk(
            "--- a/legacy.py\n+++ /dev/null\n@@ -1 +0,0 @@\n", changed_files=1
        )
        assert level == "high"
