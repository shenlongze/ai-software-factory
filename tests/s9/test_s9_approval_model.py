"""tests/s9/test_s9_approval_model.py — Approval Gate 领域模型 + 受控状态机。

覆盖 (S9-001 任务清单):
- ApprovalStatus 枚举: 宽容解析 / 非法值响亮拒绝
- ApprovalGate 模型: 默认 PENDING / 绑定 stage+workflow / 时间戳字段
- APPROVAL_TRANSITIONS 受控转换表: PENDING → APPROVED/REJECTED (终态);
  终态不可再流转 (决定不可撤销 — 审计铁律); 同状态幂等
- transition_approval: approved_at/rejected_at + reviewer/comment 落库

依赖: 本目录 conftest (sys.path 挂 factory-core + factory-org)。
"""

from __future__ import annotations

import pytest

from org.approval import (
    APPROVAL_TRANSITIONS,
    ApprovalGate,
    ApprovalStateError,
    ApprovalStatus,
    transition_approval,
)


# ------------------------------------------------------------------ 枚举


class TestApprovalStatus:
    def test_parse_enum_passthrough(self) -> None:
        assert ApprovalStatus.parse(ApprovalStatus.PENDING) is ApprovalStatus.PENDING

    def test_parse_case_insensitive(self) -> None:
        assert ApprovalStatus.parse("APPROVED") is ApprovalStatus.APPROVED
        assert ApprovalStatus.parse(" Rejected ") is ApprovalStatus.REJECTED

    def test_parse_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid approval status"):
            ApprovalStatus.parse("maybe")

    def test_transition_table_topology(self) -> None:
        """受控转换表: pending 可到 approved/rejected; 终态出边为空 (单向无环)。"""
        assert APPROVAL_TRANSITIONS["pending"] == ("approved", "rejected")
        assert APPROVAL_TRANSITIONS["approved"] == ()
        assert APPROVAL_TRANSITIONS["rejected"] == ()


# ------------------------------------------------------------------ 模型


class TestApprovalGateModel:
    def test_defaults_pending(self) -> None:
        gate = ApprovalGate(id="AG-1", stage_id="STG-1", workflow_id="WF-1")
        assert gate.status == ApprovalStatus.PENDING
        assert gate.reviewer == ""
        assert gate.comment == ""
        assert gate.approved_at is None
        assert gate.rejected_at is None
        assert gate.requested_at is not None
        assert gate.is_pending is True
        assert gate.is_terminal is False

    def test_serialize_roundtrip(self) -> None:
        """to_dict → model_validate 往返 (JSON 持久化路径同构)。"""
        gate = ApprovalGate(id="AG-1", stage_id="STG-1", workflow_id="WF-1")
        clone = ApprovalGate.model_validate(gate.to_dict())
        assert clone.id == gate.id
        assert clone.status == gate.status
        assert clone.requested_at == gate.requested_at

    def test_status_coerced_from_string(self) -> None:
        gate = ApprovalGate(
            id="AG-2", stage_id="STG-2", workflow_id="WF-2", status="approved"
        )
        assert gate.status == ApprovalStatus.APPROVED
        assert gate.is_terminal is True
        assert gate.is_pending is False


# ------------------------------------------------------------------ 状态机


class TestTransitionApproval:
    def test_pending_to_approved_records_decision(self) -> None:
        gate = ApprovalGate(id="AG-1", stage_id="STG-1", workflow_id="WF-1")
        updated = transition_approval(
            gate, ApprovalStatus.APPROVED, reviewer="alice", comment="MVP ok"
        )
        assert updated is not gate
        assert updated.status == ApprovalStatus.APPROVED
        assert updated.reviewer == "alice"
        assert updated.comment == "MVP ok"
        assert updated.approved_at is not None
        assert updated.rejected_at is None
        assert updated.is_terminal is True

    def test_pending_to_rejected_records_decision(self) -> None:
        gate = ApprovalGate(id="AG-1", stage_id="STG-1", workflow_id="WF-1")
        updated = transition_approval(
            gate, ApprovalStatus.REJECTED, reviewer="bob", comment="scope too big"
        )
        assert updated.status == ApprovalStatus.REJECTED
        assert updated.reviewer == "bob"
        assert updated.comment == "scope too big"
        assert updated.rejected_at is not None
        assert updated.approved_at is None

    def test_terminal_approved_cannot_retransition(self) -> None:
        gate = transition_approval(
            ApprovalGate(id="AG-1", stage_id="STG-1", workflow_id="WF-1"),
            ApprovalStatus.APPROVED,
        )
        with pytest.raises(ApprovalStateError, match="invalid approval transition"):
            transition_approval(gate, ApprovalStatus.REJECTED)

    def test_terminal_rejected_cannot_retransition(self) -> None:
        gate = transition_approval(
            ApprovalGate(id="AG-1", stage_id="STG-1", workflow_id="WF-1"),
            ApprovalStatus.REJECTED,
        )
        with pytest.raises(ApprovalStateError, match="invalid approval transition"):
            transition_approval(gate, ApprovalStatus.APPROVED)

    def test_same_status_idempotent(self) -> None:
        """同状态幂等: 返回原实例, 不重复写 (不覆盖决定时间戳)。"""
        gate = ApprovalGate(id="AG-1", stage_id="STG-1", workflow_id="WF-1")
        assert transition_approval(gate, ApprovalStatus.PENDING) is gate

    def test_invalid_target_raises_value_error(self) -> None:
        gate = ApprovalGate(id="AG-1", stage_id="STG-1", workflow_id="WF-1")
        with pytest.raises(ValueError, match="invalid approval status"):
            transition_approval(gate, "maybe")  # type: ignore[arg-type]

    def test_string_target_parsed(self) -> None:
        gate = ApprovalGate(id="AG-1", stage_id="STG-1", workflow_id="WF-1")
        updated = transition_approval(gate, "approved", reviewer="carol")
        assert updated.status == ApprovalStatus.APPROVED
        assert updated.reviewer == "carol"
