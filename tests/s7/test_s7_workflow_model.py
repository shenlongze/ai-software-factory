"""tests/s7/test_s7_workflow_model.py — Workflow Engine 枚举/转换表/模型 (Unit, S7-003)。

覆盖:
- WorkflowStatus 枚举值 + 宽容解析 (大小写不敏感 / 枚举直通 / 非法抛 ValueError)
- WORKFLOW_TRANSITIONS 受控转换表逐项断言 (单向无环; completed 终态)
- Workflow 模型默认值 (DRAFT/stage_ids []/时间戳) + is_terminal + to_dict 往返
- StageStatus S7-003 增量成员 (READY/BLOCKED) + STAGE_TRANSITIONS 转换表

依赖: 本目录 conftest (sys.path 挂 factory-core + factory-org + factory-exec)。
"""

from __future__ import annotations

import pytest

from org.projects import STAGE_TRANSITIONS, StageStatus
from org.workflow import WORKFLOW_TRANSITIONS, Workflow, WorkflowStatus


class TestWorkflowStatus:
    def test_enum_values(self):
        assert WorkflowStatus.DRAFT.value == "draft"
        assert WorkflowStatus.ACTIVE.value == "active"
        assert WorkflowStatus.PAUSED.value == "paused"
        assert WorkflowStatus.COMPLETED.value == "completed"
        assert WorkflowStatus.FAILED.value == "failed"

    def test_parse_case_insensitive(self):
        assert WorkflowStatus.parse("DRAFT") is WorkflowStatus.DRAFT
        assert WorkflowStatus.parse("  Active ") is WorkflowStatus.ACTIVE
        assert WorkflowStatus.parse("COMPLETED") is WorkflowStatus.COMPLETED

    def test_parse_enum_passthrough(self):
        assert WorkflowStatus.parse(WorkflowStatus.PAUSED) is WorkflowStatus.PAUSED

    def test_parse_invalid_raises(self):
        with pytest.raises(ValueError, match="invalid workflow status"):
            WorkflowStatus.parse("bogus")

    def test_parse_error_lists_valid(self):
        with pytest.raises(ValueError) as exc:
            WorkflowStatus.parse("nope")
        assert "draft" in str(exc.value)
        assert "completed" in str(exc.value)


class TestWorkflowTransitions:
    def test_transition_table_exact(self):
        """受控转换表逐项断言 (单向无环; completed 终态)。"""
        assert WORKFLOW_TRANSITIONS == {
            "draft": ("active",),
            "active": ("paused", "completed", "failed"),
            "paused": ("active",),
            "completed": (),
            "failed": ("paused",),
        }

    def test_completed_is_terminal(self):
        assert WORKFLOW_TRANSITIONS["completed"] == ()

    def test_failed_retry_path(self):
        """失败可重试: failed → paused → active (人工介入后恢复)。"""
        assert "paused" in WORKFLOW_TRANSITIONS["failed"]
        assert "active" in WORKFLOW_TRANSITIONS["paused"]

    def test_draft_cannot_jump_to_completed(self):
        assert "completed" not in WORKFLOW_TRANSITIONS["draft"]

    def test_no_self_transitions(self):
        for status, allowed in WORKFLOW_TRANSITIONS.items():
            assert status not in allowed


class TestWorkflowModel:
    def test_defaults(self):
        w = Workflow(id="WF-1", project_id="P-1", name="Ship v1")
        assert w.status is WorkflowStatus.DRAFT
        assert w.stage_ids == []
        assert w.started_at is None
        assert w.completed_at is None
        assert w.failed_reason == ""
        assert w.created_at is not None
        assert w.updated_at is not None

    def test_status_coerced_from_string(self):
        w = Workflow(id="WF-1", project_id="P-1", name="X", status="ACTIVE")
        assert w.status is WorkflowStatus.ACTIVE

    def test_stage_ids_none_normalized(self):
        w = Workflow(id="WF-1", project_id="P-1", name="X", stage_ids=None)
        assert w.stage_ids == []

    def test_is_terminal_true(self):
        assert Workflow(id="WF-1", project_id="P-1", name="X",
                        status="completed").is_terminal
        assert Workflow(id="WF-1", project_id="P-1", name="X",
                        status="failed").is_terminal

    def test_is_terminal_false(self):
        for status in ("draft", "active", "paused"):
            assert not Workflow(
                id="WF-1", project_id="P-1", name="X", status=status
            ).is_terminal

    def test_to_dict_roundtrip(self):
        w = Workflow(id="WF-1", project_id="P-1", name="Ship", status="active")
        data = w.to_dict()
        assert data["id"] == "WF-1"
        assert data["project_id"] == "P-1"
        assert data["status"] == "active"
        assert data["stage_ids"] == []
        assert Workflow(**{k: v for k, v in data.items()}).id == "WF-1"


class TestStageStatusExtensions:
    def test_new_members_exist(self):
        """S7-003 纯增量: READY/BLOCKED 加入, 既有值零改动。"""
        assert StageStatus.READY.value == "ready"
        assert StageStatus.BLOCKED.value == "blocked"
        assert StageStatus.PENDING.value == "pending"
        assert StageStatus.RUNNING.value == "running"
        assert StageStatus.COMPLETED.value == "completed"
        assert StageStatus.FAILED.value == "failed"

    def test_stage_transition_table_exact(self):
        assert STAGE_TRANSITIONS == {
            "pending": ("ready", "blocked"),
            "ready": ("running", "blocked"),
            "running": ("completed", "failed"),
            "blocked": ("ready", "pending"),
            "failed": ("ready", "pending"),
            "completed": (),
        }

    def test_stage_completed_is_terminal(self):
        assert STAGE_TRANSITIONS["completed"] == ()

    def test_stage_failed_retry_path(self):
        """失败重试: failed → ready (条件满足) 或 failed → pending (重置)。"""
        assert "ready" in STAGE_TRANSITIONS["failed"]
        assert "pending" in STAGE_TRANSITIONS["failed"]

    def test_stage_pending_cannot_jump_running(self):
        assert "running" not in STAGE_TRANSITIONS["pending"]
        assert "completed" not in STAGE_TRANSITIONS["pending"]
        assert "failed" not in STAGE_TRANSITIONS["pending"]
