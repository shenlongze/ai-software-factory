"""tests/s9/test_s9_approval_cli.py — factory-org approval CLI (Integration, S9-001)。

覆盖 (S9-001 任务清单: CLI list/show/approve/reject):
- list: 空清单 / count / --workflow --status --stage 过滤 (人类 + --json)
- show: 详情 (approval + stage + workflow) + 未找到 rc 7
- approve: →APPROVED + workflow ACTIVE + org.approval.approved 事件
  (--reviewer/--comment 审计落库)
- reject: →REJECTED + workflow FAILED + org.approval.rejected 事件
  (failed_reason 记录否决原因)
- 错误映射: 未找到 rc 7 / 非 PENDING 决定 rc 1

依赖: 本目录 conftest (sys.path 挂 factory-core + factory-org + factory-exec)。
种子 (project/workflow/stage/gate) 经生命周期直接落库 (logger=None 零事件,
factory.db 只含 CLI 行为事件) — 同 tests/s7/test_s7_workflow_cli.py 模式。
"""

from __future__ import annotations

import contextlib
import io
import json as _json
from pathlib import Path

import pytest

from events.store import EventStore


def run_cli(root: Path, *argv: str) -> int:
    from org.cli import main

    return main(["--root", str(root), *argv])


def run_cli_json(root: Path, *argv: str) -> tuple[int, dict]:
    from org.cli import main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["--root", str(root), "--json", *argv])
    return rc, _json.loads(buf.getvalue())


def cli_event_types(root: Path) -> list[str]:
    store = EventStore(root / "factory.db")
    try:
        return [e.type.value for e in store.query()]
    finally:
        store.close()


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """CLI 工厂根 (root/org 数据空间 + root/factory.db 事件库)。"""
    return tmp_path / "factory"


def _seed_pending_gate(
    root: Path,
    *,
    workflow_id: str = "WF-9",
    project_id: str = "P-9",
    stage_id: str = "STG-9",
    comment: str = "MVP scope 待确认",
) -> str:
    """种子: 项目 + workflow + approval_required stage COMPLETED + PENDING 门
    (logger=None 零事件; 返回 gate id)。"""
    from org.projects import Project, ProjectStore
    from org.workflow import WorkflowLifecycle

    store = ProjectStore(root / "org")
    store.save_project(Project(id=project_id, name="Approval App", user_id="u1"))
    lc = WorkflowLifecycle(store)
    lc.create_workflow(project_id, "Ship v1", workflow_id=workflow_id)
    lc.activate(workflow_id)  # 门语义在运行中 workflow 上 (ACTIVE→PAUSED)
    lc.create_stage(
        workflow_id,
        "product-manager",
        name="MVP scope",
        stage_id=stage_id,
        approval_required=True,
    )
    lc.transition_stage(stage_id, "ready")
    lc.transition_stage(stage_id, "running")
    lc.transition_stage(stage_id, "completed")
    gate = lc.request_approval(stage_id, comment=comment)
    return gate.id


class TestCliList:
    def test_list_empty(self, cli_root, capsys) -> None:
        rc = run_cli(cli_root, "approval", "list")
        out, err = capsys.readouterr()
        assert rc == 0
        assert "审批门清单" in out and "0" in out

    def test_list_json_shape(self, cli_root) -> None:
        _seed_pending_gate(cli_root)
        rc, data = run_cli_json(cli_root, "approval", "list")
        assert rc == 0
        assert data["ok"] is True
        assert data["count"] == 1
        assert data["approvals"][0]["status"] == "pending"
        assert data["approvals"][0]["stage_id"] == "STG-9"

    def test_list_filters(self, cli_root) -> None:
        gate_id = _seed_pending_gate(cli_root)
        rc, data = run_cli_json(cli_root, "approval", "list", "--workflow", "WF-9")
        assert rc == 0 and data["count"] == 1
        rc, data = run_cli_json(cli_root, "approval", "list", "--status", "pending")
        assert rc == 0 and data["count"] == 1
        rc, data = run_cli_json(cli_root, "approval", "list", "--status", "approved")
        assert rc == 0 and data["count"] == 0
        rc, data = run_cli_json(cli_root, "approval", "list", "--stage", "STG-9")
        assert rc == 0 and data["count"] == 1
        rc, data = run_cli_json(cli_root, "approval", "list", "--workflow", "WF-NOPE")
        assert rc == 0 and data["count"] == 0


class TestCliShow:
    def test_show_detail(self, cli_root) -> None:
        gate_id = _seed_pending_gate(cli_root)
        rc, data = run_cli_json(cli_root, "approval", "show", gate_id)
        assert rc == 0
        assert data["approval"]["id"] == gate_id
        assert data["approval"]["status"] == "pending"
        assert data["approval"]["comment"] == "MVP scope 待确认"
        assert data["stage"]["id"] == "STG-9"
        assert data["workflow"]["id"] == "WF-9"
        assert data["workflow"]["status"] == "paused"  # 门挂起

    def test_show_human_output(self, cli_root, capsys) -> None:
        gate_id = _seed_pending_gate(cli_root)
        rc = run_cli(cli_root, "approval", "show", gate_id)
        out, _ = capsys.readouterr()
        assert rc == 0
        assert gate_id in out

    def test_show_missing_rc7(self, cli_root) -> None:
        rc, data = run_cli_json(cli_root, "approval", "show", "AG-NOPE")
        assert rc == 7
        assert data["ok"] is False
        assert "not found" in data["error"]


class TestCliApprove:
    def test_approve_resumes_workflow(self, cli_root) -> None:
        gate_id = _seed_pending_gate(cli_root)
        rc, data = run_cli_json(
            cli_root, "approval", "approve", gate_id,
            "--reviewer", "alice", "--comment", "MVP ok",
        )
        assert rc == 0
        assert data["approval"]["status"] == "approved"
        assert data["approval"]["reviewer"] == "alice"
        assert data["approval"]["comment"] == "MVP ok"
        assert data["workflow"]["status"] == "active"
        assert data["event_seq"] > 0
        assert "org.approval.approved" in cli_event_types(cli_root)
        assert "org.workflow.started" in cli_event_types(cli_root)

    def test_approve_non_pending_rc1(self, cli_root) -> None:
        gate_id = _seed_pending_gate(cli_root)
        run_cli(cli_root, "approval", "approve", gate_id, "--reviewer", "alice")
        rc, data = run_cli_json(
            cli_root, "approval", "approve", gate_id, "--reviewer", "bob"
        )
        assert rc == 1
        assert "invalid approval transition" in data["error"]

    def test_approve_missing_rc7(self, cli_root) -> None:
        rc, data = run_cli_json(cli_root, "approval", "approve", "AG-NOPE")
        assert rc == 7


class TestCliReject:
    def test_reject_stops_workflow(self, cli_root) -> None:
        gate_id = _seed_pending_gate(cli_root)
        rc, data = run_cli_json(
            cli_root, "approval", "reject", gate_id,
            "--reviewer", "bob", "--comment", "scope too big",
        )
        assert rc == 0
        assert data["approval"]["status"] == "rejected"
        assert data["approval"]["reviewer"] == "bob"
        assert data["workflow"]["status"] == "failed"
        assert "scope too big" in data["workflow"]["failed_reason"]
        assert "org.approval.rejected" in cli_event_types(cli_root)
        assert "org.workflow.failed" in cli_event_types(cli_root)

    def test_reject_non_pending_rc1(self, cli_root) -> None:
        gate_id = _seed_pending_gate(cli_root)
        run_cli(cli_root, "approval", "reject", gate_id, "--reviewer", "bob")
        rc, data = run_cli_json(
            cli_root, "approval", "reject", gate_id, "--reviewer", "carol"
        )
        assert rc == 1
        assert "invalid approval transition" in data["error"]

    def test_reject_missing_rc7(self, cli_root) -> None:
        rc, data = run_cli_json(cli_root, "approval", "reject", "AG-NOPE")
        assert rc == 7
